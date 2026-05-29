"""Stdio MCP server exposing MIRA's Mac-side tools to agent CLIs.

A subscription CLI (`claude`, `codex`) spawns this as a subprocess and
discovers MIRA's tools through it. Each tool call is forwarded to the
running MIRA brain over HTTP (`POST /bridge/execute`), which routes it to
the connected Mac app for consented execution and returns the result
(optionally an image, e.g. read_screen).

Entry point: `mira-tools-server` (see pyproject scripts).
"""

from __future__ import annotations

import asyncio
import os

import httpx
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from .agent.cli_bridge import MAC_TOOL_NAMES
from .agent.tools import TOOLS

BRAIN_URL = os.environ.get("MIRA_BRAIN_URL", "http://127.0.0.1:7842")

_MAC_TOOLS = [t for t in TOOLS if t["name"] in set(MAC_TOOL_NAMES)]


def build_server() -> Server:
    server: Server = Server("mira")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=t["name"],
                description=t["description"],
                inputSchema=t["input_schema"],
            )
            for t in _MAC_TOOLS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.ContentBlock]:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{BRAIN_URL}/bridge/execute",
                json={"name": name, "input": arguments or {}},
            )
            resp.raise_for_status()
            data = resp.json()
        blocks: list[types.ContentBlock] = [
            types.TextContent(type="text", text=data.get("output", ""))
        ]
        if data.get("image_b64"):
            blocks.append(
                types.ImageContent(
                    type="image", data=data["image_b64"], mimeType="image/png"
                )
            )
        return blocks

    return server


async def _main() -> None:
    server = build_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
