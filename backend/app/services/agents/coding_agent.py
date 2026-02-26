"""Coding agent with LLM-driven agentic loop.

Runs inside a git worktree and iteratively uses tools (read, write, edit,
glob, grep, bash) to solve programming tasks.
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.database import async_session
from app.models.agent_iteration import AgentIteration
from app.services.agents.base import BaseAgent
from app.services.agents.coding_tools import (
    bash_run,
    edit_file,
    glob_search,
    grep_search,
    read_file,
    write_file,
)
from app.services.llm_client import MODEL_REGISTRY, get_default_model_for_agent
from app.services.worktree_manager import create_worktree, remove_worktree

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 50

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
            )
        except Exception:
            # On failure, try to clean up worktree
            try:
                await remove_worktree(worktree_path)
            except Exception:
                logger.warning(f"Failed to clean up worktree {worktree_path}")
            raise

        # Store workspace info on the task
        await self._update_task_workspace(task_id, worktree_path, branch_name)

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
            iter_start = time.time()

            if log_callback:
                await log_callback("info", f"Iteration {iteration}/{MAX_ITERATIONS}")

            # Call LLM with tools
            try:
                response_message = await self._call_llm_with_tools(
                    model=model, config=config, messages=messages
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

                if log_callback:
                    input_summary = _truncate(json.dumps(tool_args), 200)
                    await log_callback("info", f"Tool: {tool_name}({input_summary})")

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
                    output = await self._execute_tool(tool_name, tool_args, workspace)
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

                if log_callback:
                    status = "OK" if success else "FAILED"
                    await log_callback("info", f"  → {status} ({tc_duration}ms)")

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
    ) -> dict:
        """Call the LLM with tool definitions and return the response message dict."""
        from app.config import settings

        api_key = getattr(settings, config.api_key_setting, "")
        if not api_key:
            raise ValueError(f"No API key for {model} (set {config.api_key_setting})")

        if config.provider == "anthropic":
            return await self._call_anthropic_with_tools(config, api_key, messages)
        else:
            return await self._call_openai_with_tools(config, api_key, messages)

    async def _call_openai_with_tools(
        self,
        config: Any,
        api_key: str,
        messages: list[dict],
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
            "tools": TOOL_DEFINITIONS,
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
    ) -> dict:
        """Call Anthropic API with tool use."""
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key)

        # Convert OpenAI-style tool defs to Anthropic format
        anthropic_tools = []
        for tool_def in TOOL_DEFINITIONS:
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
