"""Distillation: read recent chat turns and extract durable user facts.

Run on demand via POST /learn/distill. The intent is to convert ephemeral
"turn" neurons into longer-lived "fact" / "preference" / "skill" neurons
that recall surfaces in future conversations.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from ..llm.anthropic_client import AnthropicClient
from ..memory.store import MemoryStore

log = logging.getLogger(__name__)

ALLOWED_KINDS = {"fact", "preference", "skill", "observation"}

DISTILL_PROMPT = """You are reviewing recent conversation turns between MIRA and the user.
Extract DURABLE knowledge about the user — things that should still be
true tomorrow. Examples: name, role, projects, preferences, recurring
goals, skills, dislikes.

DO NOT extract ephemeral things: the current request, today's plans, a
one-off question, an in-progress task, a fact about the world.

Return a strict JSON array (no prose, no fences) of items:
[{"kind": "fact"|"preference"|"skill"|"observation", "content": "<sentence>"}]
Use at most 10 items. Be concise. If nothing durable, return []."""


@dataclass
class DistillResult:
    added: int
    skipped_duplicates: int
    raw: list[dict]


async def distill_recent_turns(memory: MemoryStore, limit: int = 50) -> DistillResult:
    turns = [n for n in memory.recent(limit=limit) if n["kind"] == "turn"]
    if not turns:
        return DistillResult(added=0, skipped_duplicates=0, raw=[])

    transcript_lines: list[str] = []
    for n in reversed(turns):  # chronological
        role = n["meta"].get("role", "?")
        transcript_lines.append(f"[{role}] {n['content']}")
    transcript = "\n".join(transcript_lines)

    client = AnthropicClient()
    text = await client.complete(
        system=DISTILL_PROMPT,
        messages=[{"role": "user", "content": f"# Recent transcript\n{transcript}"}],
    )

    items = _parse_items(text)

    added = 0
    skipped = 0
    for item in items:
        kind = item.get("kind")
        content = item.get("content", "").strip()
        if kind not in ALLOWED_KINDS or not content:
            continue
        if _has_similar_fact(memory, content):
            skipped += 1
            continue
        memory.remember(content, kind=kind, meta={"source": "distill"})
        added += 1

    log.info("distill: %d turns → %d new, %d duplicates", len(turns), added, skipped)
    return DistillResult(added=added, skipped_duplicates=skipped, raw=items)


def _parse_items(text: str) -> list[dict]:
    """Tolerate light formatting noise from the model."""
    s = text.strip()
    # Strip code fences if the model added them despite instructions.
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```\s*$", "", s)
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        log.warning("distill parse failed: %r", s[:200])
        return []
    return data if isinstance(data, list) else []


def _has_similar_fact(memory: MemoryStore, content: str, threshold: float = 0.85) -> bool:
    """Dedupe against existing facts/preferences via the vector store.

    Reuses MemoryStore.recall which already returns nearest neighbors;
    we treat anything in the top-1 hit of a fact-kind row as a duplicate
    when its strength is healthy.
    """
    hits = memory.recall(content, k=3)
    for h in hits:
        if h["kind"] in ALLOWED_KINDS and h["content"].strip().lower() == content.strip().lower():
            return True
    return False
