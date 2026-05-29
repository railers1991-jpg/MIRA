"""Forge new skills from conversation history.

The forge looks at recent successful agentic turns and asks Claude:
"Is there a re-usable procedure here? If so, write it as a skill."
The returned skill is validated and persisted.

The forge can also reflect on an existing skill's outcome and append a
short "lesson" — a one-line wisdom string the skill carries forward.
"""

from __future__ import annotations

import json
import logging
import re

from ..llm.anthropic_client import AnthropicClient
from .store import SkillStore

log = logging.getLogger(__name__)

FORGE_PROMPT = """You are MIRA's skill forge. You distil a conversation excerpt
into a reusable, parameterised SKILL that MIRA can re-execute next time a
similar request comes up.

A skill is a JSON document with:
- name: snake_case identifier, 2-64 chars, [a-z0-9_]
- description: one sentence, what it does
- when_to_use: natural-language trigger description (used by Claude to pick the skill)
- parameters: JSON Schema object describing inputs
- steps: ordered list of either
    {"type": "prompt", "prompt": "<templated text>", "save_as": "<var>"}
  or
    {"type": "tool", "tool": "mcp__server__name" or "skill__other",
     "args": {...}, "save_as": "<var>"}
  Templates can reference parameters and earlier step results via {{name}}.
- returns: template string for the final answer.

Only emit a skill if the conversation reflects a procedure that the user
is likely to want again. If it's a one-off chat, return literally `null`.

Available tools you can reference in `tool` steps:
{tools}

Respond with strict JSON (no fences, no prose). Either a valid skill object
or `null`."""

LESSON_PROMPT = """A MIRA skill just finished. Reflect in ONE short sentence
(<= 20 words) on something MIRA should remember for next time — a quirk that
worked or failed, a preference the user voiced, a corner case to handle.
If nothing's worth recording, output literally `none`. Plain text only."""


def _strip_fences(text: str) -> str:
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    return re.sub(r"\s*```\s*$", "", s).strip()


def _parse_json(text: str) -> object | None:
    stripped = _strip_fences(text)
    if stripped.lower() == "null":
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        log.warning("forge: failed to parse JSON: %r", stripped[:200])
        return None


def _format_history(history: list[dict], max_chars: int = 4000) -> str:
    parts: list[str] = []
    for msg in history:
        role = msg.get("role", "?")
        content = msg.get("content")
        if isinstance(content, str):
            parts.append(f"[{role}] {content}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(f"[{role}] {block['text']}")
                    elif block.get("type") == "tool_use":
                        parts.append(f"[{role}] (tool_use {block['name']})")
                    elif block.get("type") == "tool_result":
                        snippet = str(block.get("content", ""))[:200]
                        parts.append(f"[{role}] (tool_result) {snippet}")
    joined = "\n".join(parts)
    return joined[-max_chars:] if len(joined) > max_chars else joined


class SkillForge:
    def __init__(
        self,
        store: SkillStore,
        anthropic_client: AnthropicClient,
        available_tools_provider: callable,
    ) -> None:
        self.store = store
        self.anthropic = anthropic_client
        self._tools_provider = available_tools_provider

    async def forge_from_history(self, history: list[dict]) -> dict | None:
        if not history:
            return None
        tool_lines = "\n".join(
            f"- {t['name']}: {t['description'][:160]}"
            for t in self._tools_provider()
        )
        system = FORGE_PROMPT.format(tools=tool_lines or "(none)")
        excerpt = _format_history(history)
        response = await self.anthropic.complete(
            system=system,
            messages=[{"role": "user", "content": excerpt}],
        )
        parsed = _parse_json(response)
        if not isinstance(parsed, dict):
            return None
        try:
            self.store.upsert(parsed)
        except ValueError as e:
            log.info("forge: skill rejected by validator: %s", e)
            return None
        return self.store.get(parsed["name"])

    async def reflect_lesson(self, skill_name: str, outcome: str) -> str | None:
        skill = self.store.get(skill_name)
        if not skill:
            return None
        response = await self.anthropic.complete(
            system=LESSON_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Skill: {skill['name']}\nDescription: {skill['description']}\n"
                        f"Outcome:\n{outcome}"
                    ),
                }
            ],
        )
        lesson = response.strip().splitlines()[0] if response.strip() else ""
        if not lesson or lesson.lower() == "none":
            return None
        return lesson if self.store.add_lesson(skill_name, lesson) else None
