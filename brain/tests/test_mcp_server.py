from __future__ import annotations

import pytest

from mira.mcp_server import _MAC_TOOLS, build_server


def test_mac_tools_exclude_brain_only() -> None:
    names = {t["name"] for t in _MAC_TOOLS}
    assert "remember" not in names
    assert "run_applescript" in names
    assert "read_screen" in names


def test_build_server_constructs() -> None:
    server = build_server()
    assert server.name == "mira"


@pytest.mark.asyncio
async def test_server_lists_mac_tools() -> None:
    server = build_server()
    # The low-level Server stores handlers keyed by request type; exercise
    # the registered list_tools handler directly.
    from mcp import types

    handler = server.request_handlers[types.ListToolsRequest]
    result = await handler(
        types.ListToolsRequest(method="tools/list")
    )
    tool_names = {t.name for t in result.root.tools}
    assert "run_applescript" in tool_names
    assert "remember" not in tool_names
