"""Orchestrator with session state and tool-use loop.

Two paths:
- Plain chat (text in → text/stream out): legacy behavior, no tools.
- Agentic chat (`tools_enabled=true`): Claude may emit tool_use blocks.
  The brain returns those to the Mac app, which runs them with user consent
  and posts back tool_result entries on the next request keyed by session_id.
  `remember` is handled brain-side and never round-trips.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, AsyncIterator

from ..llm.router import LLMRouter
from ..memory.store import MemoryStore
from .tools import BRAIN_TOOLS, TOOLS

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are MIRA — a personal assistant living on the user's Mac.
You have persistent memory across sessions and the ability to control the Mac
through tools (AppleScript, shell, notifications, etc.). Use tools when an
action would help; explain briefly what you're doing before doing it. When
unsure, ask one focused question. Be direct and warm."""


class Orchestrator:
    def __init__(self, memory: MemoryStore) -> None:
        self.memory = memory
        self.router = LLMRouter()
        # session_id → message history (Anthropic-shaped: role+content lists)
        self.sessions: dict[str, list[dict]] = {}

    # ---- context ----

    def _build_system(self, query: str) -> tuple[str, list[str]]:
        if not query.strip():
            return SYSTEM_PROMPT, []
        recalled = self.memory.recall(query, k=6)
        if not recalled:
            return SYSTEM_PROMPT, []
        block = "\n".join(f"- [{n['kind']}] {n['content']}" for n in recalled)
        system = f"{SYSTEM_PROMPT}\n\n# Relevant memories\n{block}"
        return system, [n["id"] for n in recalled]

    # ---- legacy non-agentic chat (kept for streaming UX) ----

    async def respond(self, user_text: str, model_hint: str | None = None) -> dict:
        system, linked = self._build_system(user_text)
        user_id = self.memory.remember(
            user_text, kind="turn", meta={"role": "user"}, link_to=linked
        )
        resp = await self.router.complete(
            system=system, messages=[{"role": "user", "content": user_text}], hint=model_hint
        )
        assistant_id = self.memory.remember(
            resp.text,
            kind="turn",
            meta={"role": "assistant", "model": resp.model_used},
            link_to=[user_id, *linked],
        )
        return {
            "text": resp.text,
            "model_used": resp.model_used,
            "neurons_recalled": len(linked),
            "assistant_neuron_id": assistant_id,
        }

    async def stream(self, user_text: str, model_hint: str | None = None) -> AsyncIterator[bytes]:
        system, linked = self._build_system(user_text)
        user_id = self.memory.remember(
            user_text, kind="turn", meta={"role": "user"}, link_to=linked
        )
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

    # ---- agentic chat with tools ----

    async def agentic(
        self,
        session_id: str | None,
        user_text: str | None,
        tool_results: list[dict] | None,
    ) -> dict[str, Any]:
        sid = session_id or uuid.uuid4().hex
        history = self.sessions.setdefault(sid, [])

        # Build the next user turn.
        if user_text is not None:
            history.append({"role": "user", "content": user_text})
        if tool_results:
            history.append(
                {
                    "role": "user",
                    "content": [self._tool_result_block(r) for r in tool_results],
                }
            )

        # Memory recall keyed on the most recent textual user input.
        query = ""
        for entry in reversed(history):
            if entry["role"] == "user" and isinstance(entry["content"], str):
                query = entry["content"]
                break
        system, linked = self._build_system(query)

        if user_text and query == user_text:
            self.memory.remember(user_text, kind="turn", meta={"role": "user"}, link_to=linked)

        result, model_used = await self.router.complete_with_tools(
            system=system, messages=history, tools=TOOLS
        )

        history.append({"role": "assistant", "content": result.raw_content})

        # Handle brain-side tools inline so the Mac doesn't see them.
        client_tool_calls: list[dict] = []
        brain_results: list[dict] = []
        for use in result.tool_uses:
            if use.name in BRAIN_TOOLS:
                output = self._run_brain_tool(use.name, use.input)
                brain_results.append({"id": use.id, "output": output})
            else:
                client_tool_calls.append({"id": use.id, "name": use.name, "input": use.input})

        if brain_results and not client_tool_calls:
            # Loop once more so the model can use the remember-tool result.
            return await self.agentic(session_id=sid, user_text=None, tool_results=brain_results)

        assistant_id: str | None = None
        if result.text:
            assistant_id = self.memory.remember(
                result.text,
                kind="turn",
                meta={"role": "assistant", "model": model_used},
                link_to=linked,
            )

        return {
            "session_id": sid,
            "text": result.text,
            "model_used": model_used,
            "tool_calls": client_tool_calls,
            "neurons_recalled": len(linked),
            "assistant_neuron_id": assistant_id,
        }

    @staticmethod
    def _tool_result_block(r: dict) -> dict:
        """Build an Anthropic tool_result block from a Mac-side tool result.

        If the Mac attached a base64 PNG (e.g. read_screen), the result
        content is a list of [text, image] blocks so Claude can see it.
        Otherwise it's a plain text result.
        """
        if r.get("image_b64"):
            return {
                "type": "tool_result",
                "tool_use_id": r["id"],
                "content": [
                    {"type": "text", "text": r.get("output", "")},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": r["image_b64"],
                        },
                    },
                ],
            }
        return {"type": "tool_result", "tool_use_id": r["id"], "content": r.get("output", "")}

    def _run_brain_tool(self, name: str, args: dict) -> str:
        if name == "remember":
            self.memory.remember(args["content"], kind=args.get("kind", "fact"))
            return "ok"
        return f"unknown brain tool: {name}"

    def reset_session(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)
