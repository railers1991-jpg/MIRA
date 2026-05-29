from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from mira.agent.bridge import ToolBridge
from mira.agent.cli_bridge import (
    MAC_TOOL_NAMES,
    allowed_tool_patterns,
    build_mcp_config,
    write_mcp_config,
)


# ---- ToolBridge ----


@pytest.mark.asyncio
async def test_request_without_client_fails_fast() -> None:
    bridge = ToolBridge(timeout_s=1)
    result = await bridge.request("run_applescript", {"script": "x"})
    assert result["error"] is True
    assert "no Mac client" in result["output"]


@pytest.mark.asyncio
async def test_request_resolves_via_executor() -> None:
    bridge = ToolBridge(timeout_s=5)
    bridge.attach()

    async def executor() -> None:
        call = await bridge.next_outbound()
        assert call["type"] == "tool_call"
        assert call["name"] == "open_url"
        bridge.resolve(call["id"], "opened https://x")

    asyncio.create_task(executor())
    result = await bridge.request("open_url", {"url": "https://x"})
    assert result["error"] is False
    assert result["output"] == "opened https://x"


@pytest.mark.asyncio
async def test_request_carries_image() -> None:
    bridge = ToolBridge(timeout_s=5)
    bridge.attach()

    async def executor() -> None:
        call = await bridge.next_outbound()
        bridge.resolve(call["id"], "captured", image_b64="aGk=")

    asyncio.create_task(executor())
    result = await bridge.request("read_screen", {})
    assert result["image_b64"] == "aGk="


@pytest.mark.asyncio
async def test_request_times_out() -> None:
    bridge = ToolBridge(timeout_s=0.2)
    bridge.attach()
    # No executor consumes the outbox → timeout.
    result = await bridge.request("shell", {"command": "sleep 99"})
    assert result["error"] is True
    assert "timed out" in result["output"]


@pytest.mark.asyncio
async def test_detach_fails_pending() -> None:
    bridge = ToolBridge(timeout_s=5)
    bridge.attach()

    async def drop_after_enqueue() -> None:
        await bridge.next_outbound()
        bridge.detach()

    asyncio.create_task(drop_after_enqueue())
    result = await bridge.request("notify", {"title": "a", "body": "b"})
    assert result["error"] is True
    assert "disconnected" in result["output"]


def test_resolve_unknown_id_returns_false() -> None:
    bridge = ToolBridge()
    assert bridge.resolve("does-not-exist", "x") is False


def test_connected_flag() -> None:
    bridge = ToolBridge()
    assert bridge.connected is False
    bridge.attach()
    assert bridge.connected is True
    bridge.detach()
    assert bridge.connected is False


# ---- cli_bridge ----


def test_allowed_tool_patterns_namespaced() -> None:
    patterns = allowed_tool_patterns()
    assert all(p.startswith("mcp__mira__") for p in patterns)
    assert "mcp__mira__run_applescript" in patterns
    # remember is brain-only, must not be exposed to the Mac executor
    assert "mcp__mira__remember" not in patterns


def test_mac_tool_names_exclude_brain_tools() -> None:
    assert "remember" not in MAC_TOOL_NAMES
    assert "run_applescript" in MAC_TOOL_NAMES
    assert "read_screen" in MAC_TOOL_NAMES


def test_build_mcp_config_shape() -> None:
    cfg = build_mcp_config("http://127.0.0.1:7842")
    assert "mcpServers" in cfg
    assert "mira" in cfg["mcpServers"]
    entry = cfg["mcpServers"]["mira"]
    assert entry["env"]["MIRA_BRAIN_URL"] == "http://127.0.0.1:7842"
    assert entry["command"]


def test_write_mcp_config_writes_file(tmp_path: Path) -> None:
    path = write_mcp_config(tmp_path, "http://127.0.0.1:7842")
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["mcpServers"]["mira"]["env"]["MIRA_BRAIN_URL"].endswith(":7842")
