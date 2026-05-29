"""Wire MIRA's Mac tools into a subscription agent CLI via MCP.

Generates the `--mcp-config` file that points the `claude` CLI at MIRA's
stdio tools server (`mira-tools-server`), plus the list of allowed tool
names so the CLI runs them without per-call prompts (MIRA's own
ConsentManager still gates execution on the Mac side).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .tools import BRAIN_TOOLS, TOOLS

MCP_SERVER_NAME = "mira"

# Tools that physically run on the Mac (everything except brain-only ones).
MAC_TOOL_NAMES = [t["name"] for t in TOOLS if t["name"] not in BRAIN_TOOLS]


def allowed_tool_patterns() -> list[str]:
    """CLI-visible names for MIRA's Mac tools, e.g. mcp__mira__run_applescript."""
    return [f"mcp__{MCP_SERVER_NAME}__{name}" for name in MAC_TOOL_NAMES]


def tools_server_command() -> str:
    """Path to the mira-tools-server entrypoint in the active environment."""
    candidate = Path(sys.executable).with_name("mira-tools-server")
    return str(candidate) if candidate.exists() else "mira-tools-server"


def build_mcp_config(brain_url: str) -> dict:
    return {
        "mcpServers": {
            MCP_SERVER_NAME: {
                "command": tools_server_command(),
                "args": [],
                "env": {"MIRA_BRAIN_URL": brain_url},
            }
        }
    }


def write_mcp_config(data_dir: Path, brain_url: str) -> Path:
    path = data_dir / "agent-mcp.json"
    path.write_text(json.dumps(build_mcp_config(brain_url), indent=2))
    return path
