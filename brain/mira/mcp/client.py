"""Manage connections to user-configured MCP servers.

Reads `~/.mira/mcp.json`:

```
{
  "servers": [
    {"name": "gmail", "command": "node",
     "args": ["/path/to/gmail-mcp/index.js"]},
    {"name": "calendar", "command": "python",
     "args": ["-m", "calendar_mcp"], "env": {"GOOGLE_CLIENT_ID": "..."}}
  ]
}
```

Each entry is launched over stdio at brain startup. Their tools are
discovered via `list_tools()` and exposed to Claude alongside MIRA's
native tools — namespaced as `mcp__<server>__<tool>` so names don't
collide with the local set.

When Claude emits a `tool_use` for an MCP tool, the orchestrator routes
it back to this manager via `call_tool()` instead of round-tripping to
the Mac. From Claude's perspective they're just more tools.
"""

from __future__ import annotations

import json
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

log = logging.getLogger(__name__)

NAMESPACE_SEP = "__"


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class _ConnectedServer:
    config: MCPServerConfig
    session: ClientSession
    tools: list[dict]


class MCPManager:
    """Lifecycle owner for all configured MCP server connections."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self._stack: AsyncExitStack | None = None
        self._servers: dict[str, _ConnectedServer] = {}

    # ---- config ----

    def load_configs(self) -> list[MCPServerConfig]:
        if not self.config_path.exists():
            return []
        try:
            raw = json.loads(self.config_path.read_text())
        except json.JSONDecodeError:
            log.exception("invalid mcp.json — ignoring")
            return []
        return [
            MCPServerConfig(
                name=s["name"],
                command=s["command"],
                args=s.get("args", []),
                env=s.get("env", {}),
            )
            for s in raw.get("servers", [])
            if "name" in s and "command" in s
        ]

    # ---- lifecycle ----

    async def start(self) -> None:
        configs = self.load_configs()
        if not configs:
            log.info("MCP: no servers configured at %s", self.config_path)
            return
        stack = AsyncExitStack()
        self._stack = stack
        for cfg in configs:
            try:
                await self._connect(cfg, stack)
            except Exception:
                log.exception("MCP: failed to connect %s — skipping", cfg.name)
        log.info(
            "MCP: %d server(s) connected: %s",
            len(self._servers), ", ".join(self._servers) or "—",
        )

    async def stop(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
        self._servers.clear()

    async def _connect(self, cfg: MCPServerConfig, stack: AsyncExitStack) -> None:
        params = StdioServerParameters(
            command=cfg.command, args=cfg.args, env=cfg.env or None
        )
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        listing = await session.list_tools()
        tools = [self._schema_for(cfg.name, t) for t in listing.tools]
        self._servers[cfg.name] = _ConnectedServer(cfg, session, tools)

    @staticmethod
    def _schema_for(server: str, tool: Any) -> dict:
        return {
            "name": f"mcp{NAMESPACE_SEP}{server}{NAMESPACE_SEP}{tool.name}",
            "description": (tool.description or "")[:1024],
            "input_schema": tool.inputSchema or {"type": "object", "properties": {}},
        }

    # ---- introspection ----

    def tools(self) -> list[dict]:
        return [t for s in self._servers.values() for t in s.tools]

    def tool_names(self) -> set[str]:
        return {t["name"] for t in self.tools()}

    def server_status(self) -> list[dict]:
        return [
            {"name": name, "tools": len(s.tools)}
            for name, s in self._servers.items()
        ]

    # ---- execution ----

    @staticmethod
    def is_mcp_tool(name: str) -> bool:
        return name.startswith(f"mcp{NAMESPACE_SEP}")

    @staticmethod
    def parse_tool_name(name: str) -> tuple[str, str] | None:
        prefix = f"mcp{NAMESPACE_SEP}"
        if not name.startswith(prefix):
            return None
        parts = name[len(prefix):].split(NAMESPACE_SEP, 1)
        if len(parts) != 2:
            return None
        return parts[0], parts[1]

    async def call_tool(self, name: str, args: dict) -> str:
        parsed = self.parse_tool_name(name)
        if parsed is None:
            return f"ERROR: not an MCP tool: {name}"
        server_name, tool_name = parsed
        server = self._servers.get(server_name)
        if server is None:
            return f"ERROR: MCP server '{server_name}' not connected"
        try:
            result = await server.session.call_tool(tool_name, args)
        except Exception as e:
            return f"ERROR: {e}"
        # Flatten content blocks to plain text. The MCP SDK exposes content
        # as a list of blocks; for v1 we stringify all text-like parts.
        parts: list[str] = []
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            if text is not None:
                parts.append(text)
            else:
                parts.append(str(block))
        return "\n".join(parts) if parts else "ok"
