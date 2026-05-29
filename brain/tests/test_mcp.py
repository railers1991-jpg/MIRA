from __future__ import annotations

import json
from pathlib import Path

import pytest

from mira.mcp import MCPManager


def test_load_configs_missing_file(tmp_path: Path) -> None:
    mgr = MCPManager(tmp_path / "nope.json")
    assert mgr.load_configs() == []


def test_load_configs_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text("{ this is not json")
    mgr = MCPManager(path)
    assert mgr.load_configs() == []


def test_load_configs_parses_servers(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({
        "servers": [
            {"name": "gmail", "command": "node", "args": ["/x/y"]},
            {"name": "calendar", "command": "python", "args": ["-m", "cal"],
             "env": {"K": "V"}},
            {"missing_name": True},  # ignored
        ]
    }))
    mgr = MCPManager(path)
    configs = mgr.load_configs()
    assert [c.name for c in configs] == ["gmail", "calendar"]
    assert configs[1].args == ["-m", "cal"]
    assert configs[1].env == {"K": "V"}


def test_is_mcp_tool_and_parse() -> None:
    assert MCPManager.is_mcp_tool("mcp__gmail__send")
    assert not MCPManager.is_mcp_tool("run_applescript")
    assert MCPManager.parse_tool_name("mcp__gmail__send") == ("gmail", "send")
    assert MCPManager.parse_tool_name("mcp__gmail") is None
    assert MCPManager.parse_tool_name("not_mcp") is None


def test_tools_empty_until_started(tmp_path: Path) -> None:
    mgr = MCPManager(tmp_path / "mcp.json")
    assert mgr.tools() == []
    assert mgr.tool_names() == set()
    assert mgr.server_status() == []


@pytest.mark.asyncio
async def test_start_without_config_is_noop(tmp_path: Path) -> None:
    mgr = MCPManager(tmp_path / "mcp.json")
    await mgr.start()
    try:
        assert mgr.tools() == []
    finally:
        await mgr.stop()


@pytest.mark.asyncio
async def test_call_unknown_tool_returns_error(tmp_path: Path) -> None:
    mgr = MCPManager(tmp_path / "mcp.json")
    result = await mgr.call_tool("run_applescript", {})
    assert result.startswith("ERROR: not an MCP tool")
    result = await mgr.call_tool("mcp__nothere__do", {})
    assert "not connected" in result
