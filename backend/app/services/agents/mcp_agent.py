"""MCP Agent — derives all tools from configured MCP servers.

Uses the same agentic loop pattern as CodingAgent (LLM -> tool calls -> execute
-> repeat) but without git worktree or hardcoded tools.  Adds ``done`` and
``fail`` terminal tools so the LLM can signal completion.
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.database import async_session
from app.models.agent_iteration import AgentIteration
from app.models.tool_usage import ToolUsage
from app.services.agents.base import BaseAgent
from app.services.event_bus import event_bus
from app.services.llm_client import MODEL_REGISTRY, get_default_model_for_agent
from app.services.mcp_client import MCPServerConfig, MCPSession

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 50


async def _record_tool_usage(
    agent_type: str,
    tool_name: str,
    task_id: str,
    action_id: str,
    success: bool,
    duration_ms: int,
    error: str | None = None,
) -> None:
    """Fire-and-forget: insert a ToolUsage row."""
    try:
        async with async_session() as db:
            db.add(ToolUsage(
                agent_type=agent_type,
                tool_name=tool_name,
                task_id=task_id,
                action_id=action_id,
                success=success,
                duration_ms=duration_ms,
                error=error[:2000] if error else None,
            ))
            await db.commit()
    except Exception:
        logger.debug("Failed to record tool usage", exc_info=True)

TERMINAL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Signal that the task is complete. Provide a summary of what was accomplished.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Summary of what was done and the results.",
                    },
                },
                "required": ["summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fail",
            "description": "Signal that the task cannot be completed. Explain what went wrong.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Explanation of why the task cannot be completed.",
                    },
                },
                "required": ["reason"],
            },
        },
    },
]

SYSTEM_PROMPT = """\
You are an agent that uses MCP (Model Context Protocol) tools to accomplish tasks.

You have access to tools provided by MCP servers, plus two control tools:
- done: Signal task completion with a summary
- fail: Signal that the task cannot be completed

Guidelines:
1. Explore available tools and understand what they can do.
2. Use the tools to accomplish the given task.
3. When finished, call 'done' with a summary of results.
4. If you truly cannot complete the task, call 'fail' with the reason.
"""


def _truncate(text: str, max_len: int = 2000) -> str:
    if len(text) <= max_len:
        return text
    half = max_len // 2
    return text[:half] + f"\n... ({len(text) - max_len} chars truncated) ...\n" + text[-half:]


class MCPAgent(BaseAgent):
    async def execute(
        self,
        task_id: str,
        prompt: str,
        dependency_outputs: dict[str, Any],
        log_callback: Any = None,
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        model = model or get_default_model_for_agent("mcp")
        action_id = await self._get_action_id(task_id)

        if not self.mcp_config or not self.mcp_config.get("servers"):
            raise RuntimeError(
                "MCP agent requires mcp_config with at least one server. "
                "Configure servers via the agent definition."
            )

        if log_callback:
            await log_callback("info", f"Starting MCP agent (model: {model})")

        # Connect to MCP servers
        mcp_session = MCPSession()
        configs = [MCPServerConfig.from_dict(s) for s in self.mcp_config["servers"]]

        try:
            await mcp_session.connect(configs)
            discovered = await mcp_session.list_tools()
            mcp_tools = [t.openai_schema for t in discovered]

            if log_callback:
                tool_names = [t.name for t in discovered]
                await log_callback(
                    "info",
                    f"MCP: discovered {len(mcp_tools)} tools: {tool_names[:20]}",
                )

            if not mcp_tools:
                raise RuntimeError("No tools discovered from MCP servers")

            all_tools = mcp_tools + TERMINAL_TOOLS

            result = await self._run_loop(
                task_id=task_id,
                action_id=action_id,
                prompt=prompt,
                dependency_outputs=dependency_outputs,
                model=model,
                tools=all_tools,
                mcp_session=mcp_session,
                log_callback=log_callback,
            )
            return result
        finally:
            await mcp_session.close()

    async def _run_loop(
        self,
        task_id: str,
        action_id: str,
        prompt: str,
        dependency_outputs: dict[str, Any],
        model: str,
        tools: list[dict],
        mcp_session: MCPSession,
        log_callback: Any,
    ) -> dict[str, Any]:
        dep_context = ""
        if dependency_outputs:
            parts = []
            for dep_id, output in dependency_outputs.items():
                parts.append(f"### Output from dependency task {dep_id}:\n{output}")
            dep_context = "\n\n".join(parts)

        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"## Task\n{prompt}"
                    + (f"\n\n## Dependency Outputs\n{dep_context}" if dep_context else "")
                ),
            },
        ]

        config = MODEL_REGISTRY.get(model)
        if not config:
            raise ValueError(f"Unknown model: {model}")

        for iteration in range(1, MAX_ITERATIONS + 1):
            iter_start = time.time()

            if log_callback:
                await log_callback("info", f"Iteration {iteration}/{MAX_ITERATIONS}")

            # Call LLM
            try:
                response_message = await self._call_llm(config, messages, tools)
            except Exception as e:
                await self._save_iteration(
                    task_id, action_id, iteration, None, [], "failed",
                    int((time.time() - iter_start) * 1000), error=str(e),
                )
                raise

            reasoning = response_message.get("content") or ""
            tool_calls = response_message.get("tool_calls") or []

            if not tool_calls:
                messages.append(response_message)
                messages.append({
                    "role": "user",
                    "content": "Please use your tools to proceed with the task, or call 'done' if finished.",
                })
                await self._save_iteration(
                    task_id, action_id, iteration, reasoning, [], "continue",
                    int((time.time() - iter_start) * 1000),
                )
                continue

            messages.append(response_message)
            tool_calls_data = []

            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    tool_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    tool_args = {}

                tc_start = time.time()

                if log_callback:
                    await log_callback("info", f"Tool: {tool_name}({_truncate(json.dumps(tool_args), 200)})")

                # Terminal tools
                if tool_name == "done":
                    summary = tool_args.get("summary", "Task completed.")
                    tool_calls_data.append({
                        "tool": "done", "input": tool_args,
                        "output": summary, "success": True,
                        "duration_ms": int((time.time() - tc_start) * 1000),
                    })
                    await self._save_iteration(
                        task_id, action_id, iteration, reasoning,
                        tool_calls_data, "completed",
                        int((time.time() - iter_start) * 1000),
                    )
                    if log_callback:
                        await log_callback("info", f"Agent completed: {_truncate(summary, 200)}")
                    return {"summary": summary}

                if tool_name == "fail":
                    reason = tool_args.get("reason", "Unknown failure.")
                    tool_calls_data.append({
                        "tool": "fail", "input": tool_args,
                        "output": reason, "success": False,
                        "duration_ms": int((time.time() - tc_start) * 1000),
                    })
                    await self._save_iteration(
                        task_id, action_id, iteration, reasoning,
                        tool_calls_data, "failed",
                        int((time.time() - iter_start) * 1000),
                        error=reason,
                    )
                    if log_callback:
                        await log_callback("error", f"Agent failed: {reason}")
                    raise RuntimeError(f"MCP agent failed: {reason}")

                # MCP tool call
                try:
                    output_str = await mcp_session.call_tool(tool_name, tool_args, log_callback)
                    success = True
                except Exception as e:
                    output_str = f"Error: {e}"
                    success = False

                tc_duration = int((time.time() - tc_start) * 1000)
                tool_calls_data.append({
                    "tool": tool_name, "input": tool_args,
                    "output": _truncate(output_str, 5000),
                    "duration_ms": tc_duration, "success": success,
                })

                # Record tool usage (fire-and-forget)
                asyncio.create_task(_record_tool_usage(
                    agent_type="mcp", tool_name=tool_name,
                    task_id=task_id, action_id=action_id,
                    success=success, duration_ms=tc_duration,
                    error=output_str if not success else None,
                ))

                if log_callback:
                    status = "OK" if success else "FAILED"
                    await log_callback("info", f"  → {status} ({tc_duration}ms)")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": _truncate(output_str, 10000),
                })

            await self._save_iteration(
                task_id, action_id, iteration, reasoning,
                tool_calls_data, "continue",
                int((time.time() - iter_start) * 1000),
            )

        raise RuntimeError(f"MCP agent exceeded max iterations ({MAX_ITERATIONS})")

    async def _call_llm(
        self,
        config: Any,
        messages: list[dict],
        tools: list[dict],
    ) -> dict:
        from app.config import settings

        api_key = getattr(settings, config.api_key_setting, "")
        if not api_key:
            raise ValueError(f"No API key for model (set {config.api_key_setting})")

        if config.provider == "anthropic":
            return await self._call_anthropic(config, api_key, messages, tools)
        else:
            return await self._call_openai(config, api_key, messages, tools)

    async def _call_openai(
        self, config: Any, api_key: str, messages: list[dict], tools: list[dict],
    ) -> dict:
        from openai import AsyncOpenAI

        client_kwargs: dict = {"api_key": api_key}
        if config.base_url:
            client_kwargs["base_url"] = config.base_url

        client = AsyncOpenAI(**client_kwargs)
        call_kwargs: dict = {
            "model": config.model_id,
            "messages": messages,
            "tools": tools,
        }

        _new_models = {"gpt-5", "gpt-5-mini", "gpt-5-nano", "o3", "o3-mini", "o4-mini"}
        if config.provider == "openai" and config.model_id in _new_models:
            call_kwargs["max_completion_tokens"] = 16384
        else:
            call_kwargs["max_tokens"] = 16384

        response = await client.chat.completions.create(**call_kwargs)
        msg = response.choices[0].message

        result: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        return result

    async def _call_anthropic(
        self, config: Any, api_key: str, messages: list[dict], tools: list[dict],
    ) -> dict:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key)

        anthropic_tools = []
        for tool_def in tools:
            func = tool_def["function"]
            anthropic_tools.append({
                "name": func["name"],
                "description": func["description"],
                "input_schema": func["parameters"],
            })

        system_text = ""
        filtered_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_text += msg["content"] + "\n"
            elif msg["role"] == "tool":
                filtered_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", ""),
                        "content": msg.get("content", ""),
                    }],
                })
            elif msg["role"] == "assistant" and "tool_calls" in msg:
                content_blocks: list[dict] = []
                if msg.get("content"):
                    content_blocks.append({"type": "text", "text": msg["content"]})
                for tc in msg["tool_calls"]:
                    try:
                        tc_input = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        tc_input = {}
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": tc_input,
                    })
                filtered_messages.append({"role": "assistant", "content": content_blocks})
            else:
                filtered_messages.append({"role": msg["role"], "content": msg["content"]})

        anthropic_kwargs: dict = {
            "model": config.model_id,
            "messages": filtered_messages,
            "max_tokens": 16384,
            "tools": anthropic_tools,
        }
        if system_text.strip():
            anthropic_kwargs["system"] = system_text.strip()

        response = await client.messages.create(**anthropic_kwargs)

        result: dict[str, Any] = {"role": "assistant", "content": ""}
        tool_calls_list = []
        for block in response.content:
            if block.type == "text":
                result["content"] = (result["content"] or "") + block.text
            elif block.type == "tool_use":
                tool_calls_list.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.input),
                    },
                })
        if tool_calls_list:
            result["tool_calls"] = tool_calls_list
        return result

    async def _get_action_id(self, task_id: str) -> str:
        from app.models.task import Task
        from sqlalchemy import select

        async with async_session() as db:
            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one_or_none()
            if task is None:
                raise ValueError(f"Task not found: {task_id}")
            return task.action_id

    async def _save_iteration(
        self,
        task_id: str,
        action_id: str,
        iteration_number: int,
        reasoning: str | None,
        tool_calls_data: list[dict],
        outcome: str,
        duration_ms: int,
        error: str | None = None,
    ) -> None:
        try:
            async with async_session() as db:
                iteration = AgentIteration(
                    id=str(uuid.uuid4()),
                    task_id=task_id,
                    action_id=action_id,
                    iteration_number=iteration_number,
                    loop_type="primary",
                    attempt_number=0,
                    reasoning=reasoning,
                    tool_calls=tool_calls_data,
                    outcome=outcome,
                    error=error,
                    created_at=datetime.now(timezone.utc),
                    duration_ms=duration_ms,
                )
                db.add(iteration)
                await db.commit()
        except Exception:
            logger.exception(f"Failed to save iteration {iteration_number} for task {task_id}")
