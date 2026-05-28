"""System control tools — Stage 3.

These are invoked by the agent through a tool-use loop. The Mac app
exposes the actual capabilities (AppleScript, Accessibility) and the
brain only sends declarative commands. Each first-time tool kind
requires user confirmation surfaced in the UI.

Tools planned:
- run_applescript(script: str)
- click(element_query: str)
- type_text(text: str)
- open_app(bundle_id: str)
- read_screen() -> image
- shell(cmd: str, allowlist: bool = True)
"""
