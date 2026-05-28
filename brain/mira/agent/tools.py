"""Tool schemas exposed to the LLM.

These are *declarative* — the brain doesn't execute them. When Claude emits
a tool_use block, the orchestrator returns it to the Mac app, which runs
the action with user consent and posts back a tool_result.
"""

from __future__ import annotations

TOOLS: list[dict] = [
    {
        "name": "run_applescript",
        "description": (
            "Execute an AppleScript on the user's Mac. Use this for app control, "
            "window management, file operations, and most system actions. "
            "Returns the script's stdout, or an error message."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": "Complete AppleScript source code.",
                },
                "timeout_s": {"type": "number", "default": 10},
            },
            "required": ["script"],
        },
    },
    {
        "name": "shell",
        "description": (
            "Run a shell command on the user's Mac. The user is asked to approve "
            "each invocation. Prefer AppleScript for GUI control."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout_s": {"type": "number", "default": 30},
            },
            "required": ["command"],
        },
    },
    {
        "name": "open_url",
        "description": "Open a URL in the user's default browser.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "notify",
        "description": "Show a macOS notification with a title and body.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["title", "body"],
        },
    },
    {
        "name": "get_active_app",
        "description": "Return the bundle id and window title of the frontmost app.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_screen",
        "description": (
            "Capture one of the user's displays as a PNG and feed it back "
            "to you as an image. Use this to read what is currently on "
            "screen, diagnose UI state, or assist with whatever the user "
            "is doing. display_index defaults to 0 (main display)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "display_index": {
                    "type": "integer",
                    "default": 0,
                    "minimum": 0,
                    "description": "Which display to capture (0-based).",
                },
            },
        },
    },
    {
        "name": "remember",
        "description": (
            "Persist a long-term fact about the user (preference, name, project, "
            "skill). Use sparingly — only when the user states something durable."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": ["fact", "preference", "skill", "observation"],
                    "default": "fact",
                },
            },
            "required": ["content"],
        },
    },
]

TOOL_NAMES = {t["name"] for t in TOOLS}

# Tools the brain handles itself (don't round-trip to the Mac).
BRAIN_TOOLS = {"remember"}
