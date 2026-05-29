"""Deterministic playbook interpreter for skills.

A skill's `steps` are walked in order. Each step writes its result to
`save_as` in a shared context dict; later steps reference earlier results
via `{{var}}` templating. The final `returns` field is rendered against
the same context and returned to the caller.

v1 supports two step types:
- `prompt` — call Claude with a templated user message
- `tool`  — call a brain-side tool (MCP server or another skill)

Mac-side tools (run_applescript, type_text, etc.) are not callable
directly from a skill in v1; compose them by having the skill emit a
prompt that asks Claude to use them, or call the skill through the
agentic loop where tools naturally round-trip.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Awaitable, Callable

from ..llm.anthropic_client import AnthropicClient
from ..mcp import MCPManager
from .store import SkillStore

log = logging.getLogger(__name__)

VAR_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def render(template: str, ctx: dict[str, Any]) -> str:
    """Replace `{{path.to.var}}` placeholders using dotted lookups in ctx.

    Lists and dicts are JSON-encoded. Missing paths render as the empty
    string so partial contexts don't blow up mid-execution.
    """

    def replace(m: re.Match[str]) -> str:
        path = m.group(1).split(".")
        val: Any = ctx
        for key in path:
            if isinstance(val, dict):
                val = val.get(key, "")
            elif isinstance(val, list) and key.isdigit():
                idx = int(key)
                val = val[idx] if 0 <= idx < len(val) else ""
            else:
                val = ""
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        return str(val)

    return VAR_RE.sub(replace, template)


def render_args(args: dict, ctx: dict[str, Any]) -> dict:
    """Render every leaf string in a JSON-shaped args dict against ctx."""

    def walk(v: Any) -> Any:
        if isinstance(v, str):
            return render(v, ctx)
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return v

    return walk(args)


ExecuteToolFn = Callable[[str, dict], Awaitable[str]]


class SkillExecutor:
    """Runs a stored skill end-to-end and returns the rendered result."""

    SYSTEM_PROMPT = (
        "You are executing one step of a named procedure. Be precise, "
        "return only what the next step needs — no preamble or pleasantries."
    )

    def __init__(
        self,
        store: SkillStore,
        anthropic_client: AnthropicClient | None,
        mcp: MCPManager | None,
    ) -> None:
        self.store = store
        self.anthropic = anthropic_client
        self.mcp = mcp

    async def execute(self, name: str, params: dict | None = None) -> str:
        skill = self.store.get(name)
        if not skill:
            return f"ERROR: unknown skill '{name}'"
        try:
            output = await self._run(skill, params or {})
        except Exception as e:
            log.exception("skill '%s' failed", name)
            self.store.record_failure(name)
            return f"ERROR: skill '{name}' failed: {e}"
        self.store.record_success(name)
        return output

    async def _run(self, skill: dict, params: dict) -> str:
        ctx: dict[str, Any] = {**params}
        ctx["_lessons"] = skill["lessons"]
        for i, step in enumerate(skill["steps"]):
            save_as = step.get("save_as", f"_step{i}")
            step_type = step.get("type")
            if step_type == "prompt":
                if self.anthropic is None:
                    raise RuntimeError("prompt steps require ANTHROPIC_API_KEY")
                rendered = render(step["prompt"], ctx)
                ctx[save_as] = await self.anthropic.complete(
                    system=self.SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": rendered}],
                )
            elif step_type == "tool":
                tool_name = step["tool"]
                args = render_args(step.get("args", {}), ctx)
                ctx[save_as] = await self._call_tool(tool_name, args)
            else:
                raise RuntimeError(f"unknown step type: {step_type}")
        template = skill["returns"] or "{{_result}}"
        return render(template, ctx)

    async def _call_tool(self, name: str, args: dict) -> str:
        if name.startswith("skill__"):
            return await self.execute(name[len("skill__"):], args)
        if self.mcp and MCPManager.is_mcp_tool(name):
            return await self.mcp.call_tool(name, args)
        raise RuntimeError(
            f"tool '{name}' is not callable from a skill (only MCP tools "
            "and other skills are supported in v1)"
        )
