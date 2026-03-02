"""Coding agent with LLM-driven agentic loop.

Runs inside a git worktree and iteratively uses tools (read, write, edit,
glob, grep, bash) to solve programming tasks.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.database import async_session
from app.models.agent_iteration import AgentIteration
from app.models.artifact import Artifact
from app.models.tool_usage import ToolUsage
from app.services.agents.base import BaseAgent
from app.services.agents.coding_tools import (
    bash_run,
    edit_file,
    glob_search,
    grep_search,
    read_file,
    write_file,
)
from app.services.event_bus import event_bus
from app.services.llm_client import MODEL_REGISTRY, get_default_model_for_agent
from app.services.pause_manager import pause_manager
from app.services.worktree_manager import create_worktree, remove_worktree

ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "artifacts"

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

# ── Tool schemas for LLM function calling ────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to workspace root.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file (creates parent dirs). Use for new files or full rewrites.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to workspace root.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full file content to write.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edit a file by replacing an exact string with a new string. Returns a unified diff.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to workspace root.",
                    },
                    "old_str": {
                        "type": "string",
                        "description": "Exact string to find and replace.",
                    },
                    "new_str": {
                        "type": "string",
                        "description": "Replacement string.",
                    },
                },
                "required": ["path", "old_str", "new_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Search for files matching a glob pattern (e.g. '**/*.py').",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to match files.",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search file contents for a regex pattern. Returns matching lines with file and line number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for.",
                    },
                    "glob_filter": {
                        "type": "string",
                        "description": "Optional glob filter for files (e.g. '*.py').",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Execute a shell command in the workspace. Use for running tests, installing deps, git operations, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 120).",
                    },
                },
                "required": ["command"],
            },
        },
    },
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
                        "description": "Summary of what was done, files changed, and any test results.",
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
You are a coding agent working inside a git worktree. Your goal is to complete the given programming task.

You have these tools available:
- read_file: Read file contents
- write_file: Create or overwrite a file
- edit_file: Replace an exact string in a file (returns diff)
- glob: Find files by pattern
- grep: Search file contents with regex
- bash: Run shell commands (tests, builds, git, etc.)
- done: Signal task completion with summary
- fail: Signal task cannot be completed

Guidelines:
1. Start by exploring the codebase to understand the structure.
2. Make changes incrementally and verify with tests/builds.
3. Keep changes focused and minimal.
4. When done, call the 'done' tool with a summary.
5. If you truly cannot complete the task, call 'fail' with reason.
6. Do NOT call done/fail until you have verified your changes work.
"""


def _truncate(text: str, max_len: int = 2000) -> str:
    """Truncate text for logging/storage, preserving head and tail."""
    if len(text) <= max_len:
        return text
    half = max_len // 2
    return text[:half] + f"\n... ({len(text) - max_len} chars truncated) ...\n" + text[-half:]


class CodingAgent(BaseAgent):
    async def execute(
        self,
        task_id: str,
        prompt: str,
        dependency_outputs: dict[str, Any],
        log_callback: Any = None,
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Run the agentic loop inside a git worktree."""
        model = model or get_default_model_for_agent("coding")
        action_id = await self._get_action_id(task_id)

        if log_callback:
            await log_callback("info", f"Starting coding agent (model: {model})")

        # Create worktree
        try:
            worktree_path, branch_name = await create_worktree(task_id)
        except Exception as e:
            if log_callback:
                await log_callback("error", f"Failed to create worktree: {e}")
            raise RuntimeError(f"Worktree creation failed: {e}") from e

        if log_callback:
            await log_callback("info", f"Created worktree: {worktree_path} (branch: {branch_name})")

        # Connect to MCP servers if configured
        mcp_session = None
        mcp_tools: list[dict] = []
        if self.mcp_config and self.mcp_config.get("servers"):
            try:
                from app.services.mcp_client import MCPServerConfig, MCPSession
                mcp_session = MCPSession()
                configs = [MCPServerConfig.from_dict(s) for s in self.mcp_config["servers"]]
                await mcp_session.connect(configs)
                discovered = await mcp_session.list_tools()
                mcp_tools = [t.openai_schema for t in discovered]
                if log_callback:
                    await log_callback("info", f"MCP: discovered {len(mcp_tools)} tools from {len(configs)} server(s)")
            except Exception as e:
                if log_callback:
                    await log_callback("warn", f"MCP setup failed, continuing without MCP tools: {e}")
                mcp_session = None
                mcp_tools = []

        try:
            result = await self._run_loop(
                task_id=task_id,
                action_id=action_id,
                prompt=prompt,
                dependency_outputs=dependency_outputs,
                model=model,
                workspace=worktree_path,
                branch_name=branch_name,
                log_callback=log_callback,
                mcp_tools=mcp_tools,
                mcp_session=mcp_session,
            )
        except Exception:
            # On failure, try to clean up worktree
            try:
                await remove_worktree(worktree_path)
            except Exception:
                logger.warning(f"Failed to clean up worktree {worktree_path}")
            raise
        finally:
            if mcp_session:
                await mcp_session.close()

        # Store workspace info on the task
        await self._update_task_workspace(task_id, worktree_path, branch_name)

        # Generate completion artifacts (diff + enriched summary)
        try:
            result = await self._generate_completion_artifacts(
                task_id=task_id,
                action_id=action_id,
                workspace=worktree_path,
                branch_name=branch_name,
                agent_summary=result.get("summary", "Task completed."),
                log_callback=log_callback,
            )
        except Exception:
            logger.exception(f"Failed to generate completion artifacts for task {task_id}")
            # Fall back to basic result if artifact generation fails
            pass

        return result

    async def _run_loop(
        self,
        task_id: str,
        action_id: str,
        prompt: str,
        dependency_outputs: dict[str, Any],
        model: str,
        workspace: str,
        branch_name: str,
        log_callback: Any,
        mcp_tools: list[dict] | None = None,
        mcp_session: Any = None,
    ) -> dict[str, Any]:
        """Core agentic loop: LLM → tool calls → repeat."""

        # Build initial messages
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
                    f"## Task\n{prompt}\n\n"
                    f"## Workspace\nYou are working in: {workspace}\n"
                    f"Branch: {branch_name}\n"
                    + (f"\n## Dependency Outputs\n{dep_context}" if dep_context else "")
                ),
            },
        ]

        config = MODEL_REGISTRY.get(model)
        if not config:
            raise ValueError(f"Unknown model: {model}")

        for iteration in range(1, MAX_ITERATIONS + 1):
            # ── Check for pause signal ────────────────────────────────────
            if pause_manager.is_paused(task_id):
                if log_callback:
                    await log_callback("info", "Task paused by user. Waiting for resume...")

                # Update task status to paused
                await self._set_task_status(task_id, "paused")

                await event_bus.publish(action_id, "task.paused", {
                    "task_id": task_id,
                    "action_id": action_id,
                    "iteration_number": iteration,
                })

                # Block until resumed
                await pause_manager.wait_for_resume(task_id)

                if log_callback:
                    await log_callback("info", "Task resumed by user.")

                # Check if user provided guidance
                guidance = pause_manager.take_guidance(task_id)
                if guidance:
                    if log_callback:
                        await log_callback("info", f"User guidance: {guidance[:200]}")
                    messages.append({
                        "role": "user",
                        "content": f"[USER GUIDANCE — The user has paused and provided new instructions]\n{guidance}\n\n[Continue working on the task with the above guidance in mind.]",
                    })

                # Restore running status
                await self._set_task_status(task_id, "running")

            iter_start = time.time()

            if log_callback:
                await log_callback("info", f"Iteration {iteration}/{MAX_ITERATIONS}")

            await event_bus.publish(action_id, "iteration.started", {
                "task_id": task_id,
                "iteration_number": iteration,
                "loop_type": "primary",
                "attempt_number": 0,
            })

            # Call LLM with tools
            try:
                response_message = await self._call_llm_with_tools(
                    model=model, config=config, messages=messages,
                    extra_tools=mcp_tools,
                )
            except Exception as e:
                # Save failed iteration and raise
                await self._save_iteration(
                    task_id=task_id,
                    action_id=action_id,
                    iteration_number=iteration,
                    reasoning=None,
                    tool_calls_data=[],
                    outcome="failed",
                    error=str(e),
                    duration_ms=int((time.time() - iter_start) * 1000),
                )
                raise

            # Extract reasoning (text content before/alongside tool calls)
            reasoning = response_message.get("content") or ""

            if reasoning:
                await event_bus.publish(action_id, "iteration.reasoning", {
                    "task_id": task_id,
                    "iteration_number": iteration,
                    "reasoning": _truncate(reasoning, 2000),
                })

            # Check for tool calls
            tool_calls = response_message.get("tool_calls") or []

            if not tool_calls:
                # No tool calls — LLM is just responding with text
                # Append and continue (ask it to use a tool)
                messages.append(response_message)
                messages.append({
                    "role": "user",
                    "content": "Please use your tools to proceed with the task, or call 'done' if finished.",
                })
                await self._save_iteration(
                    task_id=task_id,
                    action_id=action_id,
                    iteration_number=iteration,
                    reasoning=reasoning,
                    tool_calls_data=[],
                    outcome="continue",
                    duration_ms=int((time.time() - iter_start) * 1000),
                )
                await event_bus.publish(action_id, "iteration.completed", {
                    "task_id": task_id,
                    "iteration_number": iteration,
                    "outcome": "continue",
                })
                continue

            # Execute tool calls
            messages.append(response_message)
            tool_calls_data = []
            final_result = None

            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    tool_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    tool_args = {}

                tc_start = time.time()

                input_summary = _truncate(json.dumps(tool_args), 200)

                if log_callback:
                    await log_callback("info", f"Tool: {tool_name}({input_summary})")

                await event_bus.publish(action_id, "iteration.tool_call", {
                    "task_id": task_id,
                    "iteration_number": iteration,
                    "tool": tool_name,
                    "input_summary": input_summary,
                })

                # Check for terminal tools
                if tool_name == "done":
                    summary = tool_args.get("summary", "Task completed.")
                    tool_calls_data.append({
                        "tool": "done",
                        "input": tool_args,
                        "output": summary,
                        "duration_ms": int((time.time() - tc_start) * 1000),
                        "success": True,
                    })
                    await self._save_iteration(
                        task_id=task_id,
                        action_id=action_id,
                        iteration_number=iteration,
                        reasoning=reasoning,
                        tool_calls_data=tool_calls_data,
                        outcome="completed",
                        duration_ms=int((time.time() - iter_start) * 1000),
                    )
                    if log_callback:
                        await log_callback("info", f"Agent completed: {_truncate(summary, 200)}")
                    return {"summary": summary}

                if tool_name == "fail":
                    reason = tool_args.get("reason", "Unknown failure.")
                    tool_calls_data.append({
                        "tool": "fail",
                        "input": tool_args,
                        "output": reason,
                        "duration_ms": int((time.time() - tc_start) * 1000),
                        "success": False,
                    })
                    await self._save_iteration(
                        task_id=task_id,
                        action_id=action_id,
                        iteration_number=iteration,
                        reasoning=reasoning,
                        tool_calls_data=tool_calls_data,
                        outcome="failed",
                        error=reason,
                        duration_ms=int((time.time() - iter_start) * 1000),
                    )
                    if log_callback:
                        await log_callback("error", f"Agent failed: {reason}")
                    raise RuntimeError(f"Coding agent failed: {reason}")

                # Execute regular tool
                try:
                    output = await self._execute_tool(
                        tool_name, tool_args, workspace,
                        mcp_session=mcp_session, log_callback=log_callback,
                    )
                    output_str = json.dumps(output) if not isinstance(output, str) else output
                    success = True
                except Exception as e:
                    output_str = f"Error: {e}"
                    success = False

                tc_duration = int((time.time() - tc_start) * 1000)
                tool_calls_data.append({
                    "tool": tool_name,
                    "input": tool_args,
                    "output": _truncate(output_str, 5000),
                    "duration_ms": tc_duration,
                    "success": success,
                })

                # Record tool usage (fire-and-forget)
                asyncio.create_task(_record_tool_usage(
                    agent_type="coding", tool_name=tool_name,
                    task_id=task_id, action_id=action_id,
                    success=success, duration_ms=tc_duration,
                    error=output_str if not success else None,
                ))

                if log_callback:
                    status = "OK" if success else "FAILED"
                    await log_callback("info", f"  → {status} ({tc_duration}ms)")

                await event_bus.publish(action_id, "iteration.tool_result", {
                    "task_id": task_id,
                    "iteration_number": iteration,
                    "tool": tool_name,
                    "output_summary": _truncate(output_str, 500),
                    "success": success,
                    "duration_ms": tc_duration,
                })

                # Emit specialized events for file diffs and terminal output
                if tool_name in ("edit_file", "write_file") and success:
                    file_path = tool_args.get("path", "")
                    diff_text = output_str if tool_name == "edit_file" else f"Wrote file: {file_path}"
                    await event_bus.publish(action_id, "iteration.file_diff", {
                        "task_id": task_id,
                        "iteration_number": iteration,
                        "file_path": file_path,
                        "diff": _truncate(diff_text, 5000),
                    })

                if tool_name == "bash":
                    bash_result = output if isinstance(output, dict) else {}
                    await event_bus.publish(action_id, "iteration.terminal", {
                        "task_id": task_id,
                        "iteration_number": iteration,
                        "command": tool_args.get("command", ""),
                        "stdout": _truncate(bash_result.get("stdout", "") if success else "", 2000),
                        "stderr": _truncate(bash_result.get("stderr", "") if success else output_str, 2000),
                        "exit_code": bash_result.get("exit_code", -1) if success else -1,
                    })

                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": _truncate(output_str, 10000),
                })

            # Save iteration
            await self._save_iteration(
                task_id=task_id,
                action_id=action_id,
                iteration_number=iteration,
                reasoning=reasoning,
                tool_calls_data=tool_calls_data,
                outcome="continue",
                duration_ms=int((time.time() - iter_start) * 1000),
            )

        # Max iterations reached
        if log_callback:
            await log_callback("warn", f"Max iterations ({MAX_ITERATIONS}) reached")

        raise RuntimeError(f"Coding agent exceeded max iterations ({MAX_ITERATIONS})")

    async def _call_llm_with_tools(
        self,
        model: str,
        config: Any,
        messages: list[dict],
        extra_tools: list[dict] | None = None,
    ) -> dict:
        """Call the LLM with tool definitions and return the response message dict."""
        from app.config import settings

        api_key = getattr(settings, config.api_key_setting, "")
        if not api_key:
            raise ValueError(f"No API key for {model} (set {config.api_key_setting})")

        all_tools = TOOL_DEFINITIONS + (extra_tools or [])

        if config.provider == "anthropic":
            return await self._call_anthropic_with_tools(config, api_key, messages, all_tools)
        else:
            return await self._call_openai_with_tools(config, api_key, messages, all_tools)

    async def _call_openai_with_tools(
        self,
        config: Any,
        api_key: str,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict:
        """Call OpenAI-compatible API with function calling."""
        from openai import AsyncOpenAI

        client_kwargs: dict = {"api_key": api_key}
        if config.base_url:
            client_kwargs["base_url"] = config.base_url

        client = AsyncOpenAI(**client_kwargs)

        call_kwargs: dict = {
            "model": config.model_id,
            "messages": messages,
            "tools": tools or TOOL_DEFINITIONS,
        }

        # Handle newer models that use max_completion_tokens
        _new_models = {"gpt-5", "gpt-5-mini", "gpt-5-nano", "o3", "o3-mini", "o4-mini"}
        if config.provider == "openai" and config.model_id in _new_models:
            call_kwargs["max_completion_tokens"] = 16384
        else:
            call_kwargs["max_tokens"] = 16384

        response = await client.chat.completions.create(**call_kwargs)
        msg = response.choices[0].message

        # Convert to dict format
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

    async def _call_anthropic_with_tools(
        self,
        config: Any,
        api_key: str,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict:
        """Call Anthropic API with tool use."""
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key)

        # Convert OpenAI-style tool defs to Anthropic format
        anthropic_tools = []
        for tool_def in (tools or TOOL_DEFINITIONS):
            func = tool_def["function"]
            anthropic_tools.append({
                "name": func["name"],
                "description": func["description"],
                "input_schema": func["parameters"],
            })

        # Extract system message
        system_text = ""
        filtered_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_text += msg["content"] + "\n"
            elif msg["role"] == "tool":
                # Anthropic expects tool_result blocks
                filtered_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.get("tool_call_id", ""),
                            "content": msg.get("content", ""),
                        }
                    ],
                })
            elif msg["role"] == "assistant" and "tool_calls" in msg:
                # Convert tool_calls to Anthropic tool_use blocks
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

        # Convert Anthropic response to OpenAI-like format
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

    async def _execute_tool(
        self,
        tool_name: str,
        args: dict,
        workspace: str,
        mcp_session: Any = None,
        log_callback: Any = None,
    ) -> Any:
        """Dispatch a tool call to the appropriate function."""
        if tool_name == "read_file":
            return await read_file(args["path"], workspace)
        elif tool_name == "write_file":
            return await write_file(args["path"], args["content"], workspace)
        elif tool_name == "edit_file":
            return await edit_file(args["path"], args["old_str"], args["new_str"], workspace)
        elif tool_name == "glob":
            return await glob_search(args["pattern"], workspace)
        elif tool_name == "grep":
            return await grep_search(args["pattern"], workspace, args.get("glob_filter"))
        elif tool_name == "bash":
            return await bash_run(args["command"], workspace, args.get("timeout", 120))
        elif tool_name.startswith("mcp__") and mcp_session:
            return await mcp_session.call_tool(tool_name, args, log_callback)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

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
        loop_type: str = "primary",
        attempt_number: int = 0,
    ) -> None:
        """Save an AgentIteration record to the database."""
        try:
            async with async_session() as db:
                iteration = AgentIteration(
                    id=str(uuid.uuid4()),
                    task_id=task_id,
                    action_id=action_id,
                    iteration_number=iteration_number,
                    loop_type=loop_type,
                    attempt_number=attempt_number,
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

    async def _set_task_status(self, task_id: str, status: str) -> None:
        """Update the task status in the database."""
        from app.models.task import Task
        from sqlalchemy import select

        async with async_session() as db:
            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one_or_none()
            if task:
                task.status = status
                await db.commit()

    async def _get_action_id(self, task_id: str) -> str:
        """Get the action_id for a task."""
        from app.models.task import Task
        from sqlalchemy import select

        async with async_session() as db:
            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one_or_none()
            if task is None:
                raise ValueError(f"Task not found: {task_id}")
            return task.action_id

    async def _update_task_workspace(
        self, task_id: str, workspace_path: str, branch_name: str
    ) -> None:
        """Store workspace_path and workspace_branch on the Task."""
        from app.models.task import Task
        from sqlalchemy import select

        async with async_session() as db:
            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one_or_none()
            if task:
                task.workspace_path = workspace_path
                task.workspace_branch = branch_name
                await db.commit()

    async def _generate_completion_artifacts(
        self,
        task_id: str,
        action_id: str,
        workspace: str,
        branch_name: str,
        agent_summary: str,
        log_callback: Any,
    ) -> dict[str, Any]:
        """Generate a git diff artifact and enriched summary on completion."""

        # Get the diff of all changes on the worktree branch vs its merge base
        diff_text = ""
        files_changed = 0
        try:
            # First try diffing against the merge base with main/master
            proc = await asyncio.create_subprocess_exec(
                "git", "diff", "--stat", "HEAD",
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stat_stdout, _ = await proc.communicate()
            stat_output = stat_stdout.decode(errors="replace").strip()

            # Count files changed from --stat output
            if stat_output:
                # Last line of git diff --stat is like " 3 files changed, ..."
                for line in stat_output.splitlines():
                    if "file" in line and "changed" in line:
                        parts = line.strip().split()
                        if parts and parts[0].isdigit():
                            files_changed = int(parts[0])

            # Get the full unified diff
            proc = await asyncio.create_subprocess_exec(
                "git", "diff", "HEAD",
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            diff_stdout, _ = await proc.communicate()
            diff_text = diff_stdout.decode(errors="replace")

            # If no uncommitted changes, try diff against the initial commit
            if not diff_text.strip():
                # Try to find the merge base with the default branch
                for base_ref in ("main", "master"):
                    proc = await asyncio.create_subprocess_exec(
                        "git", "merge-base", base_ref, "HEAD",
                        cwd=workspace,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    mb_stdout, _ = await proc.communicate()
                    if proc.returncode == 0:
                        merge_base = mb_stdout.decode().strip()
                        proc2 = await asyncio.create_subprocess_exec(
                            "git", "diff", merge_base, "HEAD",
                            cwd=workspace,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        d_stdout, _ = await proc2.communicate()
                        diff_text = d_stdout.decode(errors="replace")

                        # Also get stat
                        proc3 = await asyncio.create_subprocess_exec(
                            "git", "diff", "--stat", merge_base, "HEAD",
                            cwd=workspace,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        s_stdout, _ = await proc3.communicate()
                        stat_output = s_stdout.decode(errors="replace").strip()
                        for line in stat_output.splitlines():
                            if "file" in line and "changed" in line:
                                parts = line.strip().split()
                                if parts and parts[0].isdigit():
                                    files_changed = int(parts[0])
                        break

        except Exception as e:
            logger.warning(f"Failed to generate git diff for task {task_id}: {e}")
            diff_text = f"# Error generating diff: {e}"

        # Save diff to disk as an artifact file
        artifact_id = str(uuid.uuid4())
        artifact_dir = ARTIFACTS_DIR / action_id / task_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        diff_filename = f"changes-{task_id[:8]}.diff"
        diff_path = artifact_dir / diff_filename
        diff_path.write_text(diff_text or "# No changes detected", encoding="utf-8")
        diff_size = diff_path.stat().st_size

        # Create Artifact record
        async with async_session() as db:
            artifact = Artifact(
                id=artifact_id,
                task_id=task_id,
                action_id=action_id,
                type="file",
                mime_type="text/x-diff",
                storage_path=str(diff_path),
                size_bytes=diff_size,
            )
            db.add(artifact)
            await db.commit()

        if log_callback:
            await log_callback("info", f"Created diff artifact: {files_changed} files changed")

        # Build enriched summary
        summary_text = (
            f"{agent_summary}\n\n"
            f"**Branch:** `{branch_name}`\n"
            f"**Files changed:** {files_changed}\n"
        )

        output_summary = (
            f"Modified {files_changed} file(s) on branch {branch_name}."
        )

        return {
            "summary": summary_text,
            "output_summary": output_summary,
            "artifact_ids": [artifact_id],
        }
