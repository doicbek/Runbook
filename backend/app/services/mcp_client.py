"""MCP client manager — connects to MCP servers, discovers tools, dispatches calls.

Tool names are prefixed ``mcp__{server_name}__{tool_name}`` to avoid collisions
with hardcoded tools.  The ``openai_schema`` on each MCPTool is ready to be
inserted directly into the ``tools`` list for OpenAI-style function calling.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    name: str
    transport: str  # "stdio" only for now
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30

    @classmethod
    def from_dict(cls, data: dict) -> "MCPServerConfig":
        return cls(
            name=data["name"],
            transport=data.get("transport", "stdio"),
            command=data["command"],
            args=data.get("args", []),
            env=data.get("env", {}),
            timeout_seconds=data.get("timeout_seconds", 30),
        )


@dataclass
class MCPTool:
    server_name: str
    name: str
    openai_schema: dict  # ready for OpenAI tool defs
    raw_input_schema: dict


def _prefixed_name(server_name: str, tool_name: str) -> str:
    return f"mcp__{server_name}__{tool_name}"


def _parse_prefixed_name(prefixed: str) -> tuple[str, str]:
    """Return (server_name, tool_name) from a prefixed tool name."""
    parts = prefixed.split("__", 2)
    if len(parts) != 3 or parts[0] != "mcp":
        raise ValueError(f"Invalid MCP tool name format: {prefixed}")
    return parts[1], parts[2]


class _ServerHandle:
    """Holds the context managers and session for one MCP server."""

    def __init__(self) -> None:
        self.session: ClientSession | None = None
        self._stdio_cm: Any = None
        self._session_cm: Any = None
        self._read: Any = None
        self._write: Any = None


class MCPSession:
    """Manages connections to one or more MCP servers for a single task execution."""

    def __init__(self) -> None:
        self._handles: dict[str, _ServerHandle] = {}

    async def connect(self, configs: list[MCPServerConfig]) -> None:
        """Spawn stdio subprocesses and initialise sessions for each server."""
        for cfg in configs:
            if cfg.transport != "stdio":
                logger.warning(f"Unsupported MCP transport '{cfg.transport}' for server '{cfg.name}', skipping")
                continue

            handle = _ServerHandle()
            env = {**os.environ, **cfg.env} if cfg.env else None

            server_params = StdioServerParameters(
                command=cfg.command,
                args=cfg.args,
                env=env,
            )

            try:
                handle._stdio_cm = stdio_client(server_params)
                read_stream, write_stream = await handle._stdio_cm.__aenter__()
                handle._read = read_stream
                handle._write = write_stream

                handle._session_cm = ClientSession(read_stream, write_stream)
                handle.session = await handle._session_cm.__aenter__()

                await asyncio.wait_for(
                    handle.session.initialize(),
                    timeout=cfg.timeout_seconds,
                )

                self._handles[cfg.name] = handle
                logger.info(f"MCP server '{cfg.name}' connected")

            except Exception:
                logger.exception(f"Failed to connect to MCP server '{cfg.name}'")
                # Try to clean up partial connection
                await self._close_handle(handle)

    async def list_tools(self) -> list[MCPTool]:
        """Discover tools from all connected servers."""
        tools: list[MCPTool] = []
        for server_name, handle in self._handles.items():
            if not handle.session:
                continue
            try:
                result = await handle.session.list_tools()
                for tool in result.tools:
                    prefixed = _prefixed_name(server_name, tool.name)
                    input_schema = tool.inputSchema if hasattr(tool, "inputSchema") else {}
                    openai_schema = {
                        "type": "function",
                        "function": {
                            "name": prefixed,
                            "description": f"[MCP:{server_name}] {tool.description or tool.name}",
                            "parameters": input_schema,
                        },
                    }
                    tools.append(MCPTool(
                        server_name=server_name,
                        name=tool.name,
                        openai_schema=openai_schema,
                        raw_input_schema=input_schema,
                    ))
            except Exception:
                logger.exception(f"Failed to list tools from MCP server '{server_name}'")
        return tools

    async def call_tool(
        self,
        prefixed_name: str,
        arguments: dict[str, Any],
        log_callback: Any = None,
    ) -> str:
        """Dispatch a tool call to the correct MCP server and return the text result."""
        server_name, tool_name = _parse_prefixed_name(prefixed_name)
        handle = self._handles.get(server_name)
        if not handle or not handle.session:
            raise RuntimeError(f"MCP server '{server_name}' is not connected")

        if log_callback:
            await log_callback("info", f"MCP tool call: {server_name}/{tool_name}")

        result = await handle.session.call_tool(tool_name, arguments)

        # Extract text from result content blocks
        texts: list[str] = []
        for block in result.content:
            if hasattr(block, "text"):
                texts.append(block.text)
            elif hasattr(block, "data"):
                texts.append(f"[binary data: {getattr(block, 'mimeType', 'unknown')}]")
            else:
                texts.append(str(block))

        return "\n".join(texts)

    async def close(self) -> None:
        """Clean up all sessions and subprocesses."""
        for name, handle in list(self._handles.items()):
            await self._close_handle(handle)
        self._handles.clear()

    @staticmethod
    async def _close_handle(handle: _ServerHandle) -> None:
        try:
            if handle._session_cm:
                await handle._session_cm.__aexit__(None, None, None)
        except Exception:
            logger.debug("Error closing MCP session", exc_info=True)
        try:
            if handle._stdio_cm:
                await handle._stdio_cm.__aexit__(None, None, None)
        except Exception:
            logger.debug("Error closing MCP stdio", exc_info=True)
