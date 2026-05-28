"""Stage-1 orchestrator: recall → LLM → remember.

Stages 2-4 will add: tool use, voice I/O hooks, screen-context.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from ..llm.router import LLMRouter
from ..memory.store import MemoryStore

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are MIRA — a personal assistant living on the user's Mac.
You have persistent memory across sessions; relevant memories are injected below.
Be direct, warm, and useful. When you commit to an action, say what you'll do
and then do it. When unsure, ask one clear question rather than guess."""


class Orchestrator:
    def __init__(self, memory: MemoryStore) -> None:
        self.memory = memory
        self.router = LLMRouter()

    def _build_context(self, user_text: str) -> tuple[str, list[str]]:
        recalled = self.memory.recall(user_text, k=6)
        if not recalled:
            return SYSTEM_PROMPT, []
        block = "\n".join(f"- [{n['kind']}] {n['content']}" for n in recalled)
        system = f"{SYSTEM_PROMPT}\n\n# Relevant memories\n{block}"
        return system, [n["id"] for n in recalled]

    async def respond(self, user_text: str, model_hint: str | None = None) -> dict:
        system, linked = self._build_context(user_text)
        user_id = self.memory.remember(user_text, kind="turn", meta={"role": "user"}, link_to=linked)
        resp = await self.router.complete(
            system=system, messages=[{"role": "user", "content": user_text}], hint=model_hint
        )
        self.memory.remember(
            resp.text,
            kind="turn",
            meta={"role": "assistant", "model": resp.model_used},
            link_to=[user_id, *linked],
        )
        return {"text": resp.text, "model_used": resp.model_used, "neurons_recalled": len(linked)}

    async def stream(self, user_text: str, model_hint: str | None = None) -> AsyncIterator[bytes]:
        system, linked = self._build_context(user_text)
        user_id = self.memory.remember(user_text, kind="turn", meta={"role": "user"}, link_to=linked)
        full: list[str] = []
        model_used = ""
        async for chunk, model in self.router.stream(
            system=system, messages=[{"role": "user", "content": user_text}], hint=model_hint
        ):
            full.append(chunk)
            model_used = model
            yield f"data: {chunk}\n\n".encode()
        self.memory.remember(
            "".join(full),
            kind="turn",
            meta={"role": "assistant", "model": model_used},
            link_to=[user_id, *linked],
        )
        yield b"data: [DONE]\n\n"
