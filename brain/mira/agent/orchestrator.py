"""Orchestrator with session state and tool-use loop.

Both paths share session memory keyed by `session_id`:
- Plain chat (streaming text out): conversation history is preserved across
  turns; SSE emits JSON events `{chunk}` and ends with `{done, neuron_id}`.
- Agentic chat (`tools_enabled=true`): Claude may emit tool_use blocks.
  The brain returns those to the Mac app, which runs them with user consent
  and posts back tool_result entries on the next request keyed by session_id.
  `remember` is handled brain-side and never round-trips.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncIterator

from ..config import settings
from ..llm.anthropic_client import AnthropicClient
from ..llm.router import LLMRouter
from ..mcp import MCPManager
from ..memory.store import MemoryStore
from .tools import BRAIN_TOOLS, TOOLS

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are MIRA — a personal assistant living on the user's Mac.
You have persistent memory across sessions and the ability to control the Mac
through tools (AppleScript, shell, notifications, etc.). Use tools when an
action would help; explain briefly what you're doing before doing it. When
unsure, ask one focused question. Be direct and warm."""


def _sse(event: dict) -> bytes:
    """Encode one SSE event as JSON — survives newlines and special chars."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")


class Orchestrator:
    def __init__(self, memory: MemoryStore, mcp: MCPManager | None = None) -> None:
        self.memory = memory
        self.router = LLMRouter()
        self.mcp = mcp
        # Internal key: '_plain:<sid>' or '<sid>' (agentic). Maps to a list
        # of Anthropic-shaped messages.
        self.sessions: dict[str, list[dict]] = {}
        # Title generation tasks per sid — kept so we can await on shutdown.
        self._title_tasks: dict[str, asyncio.Task] = {}

    def _available_tools(self) -> list[dict]:
        mcp_tools = self.mcp.tools() if self.mcp else []
        return [*TOOLS, *mcp_tools]

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

    # ---- session persistence ----

    def _key(self, sid: str, mode: str) -> str:
        return f"_plain:{sid}" if mode == "plain" else sid

    def _history(self, sid: str, mode: str) -> list[dict]:
        """Load lazily from SQLite the first time a sid is referenced."""
        key = self._key(sid, mode)
        if key not in self.sessions:
            persisted = self.memory.session_load(sid)
            if persisted and persisted["mode"] == mode:
                self.sessions[key] = persisted["history"]
            else:
                self.sessions[key] = []
        return self.sessions[key]

    def _persist(self, sid: str, mode: str) -> None:
        history = self.sessions.get(self._key(sid, mode), [])
        self.memory.session_save(sid, history, mode=mode)
        # Spawn an auto-title task after the first exchange (2 messages).
        if len(history) >= 2 and sid not in self._title_tasks:
            if settings.anthropic_api_key:
                self._title_tasks[sid] = asyncio.create_task(self._title_session(sid, mode))

    async def _title_session(self, sid: str, mode: str) -> None:
        try:
            history = self.sessions.get(self._key(sid, mode), [])
            preview = self._first_text(history, max_chars=600)
            if not preview:
                return
            client = AnthropicClient()
            text = await client.complete(
                system=(
                    "Write a 3-5 word title for this conversation. "
                    "Plain text only, no quotes, no punctuation at the end."
                ),
                messages=[{"role": "user", "content": preview}],
            )
            title = text.strip().strip("\"'`").splitlines()[0][:60]
            if title:
                self.memory.session_set_title(sid, title)
        except Exception:
            log.exception("auto-title failed for %s", sid)
        finally:
            self._title_tasks.pop(sid, None)

    @staticmethod
    def _first_text(history: list[dict], max_chars: int = 600) -> str:
        parts: list[str] = []
        for msg in history[:4]:
            content = msg.get("content")
            if isinstance(content, str):
                parts.append(f"{msg['role']}: {content}")
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(f"{msg['role']}: {block['text']}")
        joined = "\n".join(parts)
        return joined[:max_chars]

    # ---- plain chat with session memory ----

    def _plain_history(self, sid: str) -> list[dict]:
        return self._history(sid, "plain")

    async def respond(
        self, user_text: str, session_id: str | None = None, model_hint: str | None = None
    ) -> dict:
        sid = session_id or uuid.uuid4().hex
        history = self._plain_history(sid)
        system, linked = self._build_system(user_text)
        user_id = self.memory.remember(
            user_text, kind="turn", meta={"role": "user"}, link_to=linked
        )
        history.append({"role": "user", "content": user_text})
        resp = await self.router.complete(system=system, messages=history, hint=model_hint)
        history.append({"role": "assistant", "content": resp.text})
        assistant_id = self.memory.remember(
            resp.text,
            kind="turn",
            meta={"role": "assistant", "model": resp.model_used},
            link_to=[user_id, *linked],
        )
        self._persist(sid, "plain")
        return {
            "text": resp.text,
            "model_used": resp.model_used,
            "neurons_recalled": len(linked),
            "session_id": sid,
            "assistant_neuron_id": assistant_id,
        }

    async def stream(
        self, user_text: str, session_id: str | None = None, model_hint: str | None = None
    ) -> AsyncIterator[bytes]:
        sid = session_id or uuid.uuid4().hex
        history = self._plain_history(sid)
        system, linked = self._build_system(user_text)
        user_id = self.memory.remember(
            user_text, kind="turn", meta={"role": "user"}, link_to=linked
        )
        history.append({"role": "user", "content": user_text})

        yield _sse({"session_id": sid})

        full: list[str] = []
        model_used = ""
        async for chunk, model in self.router.stream(
            system=system, messages=history, hint=model_hint
        ):
            full.append(chunk)
            model_used = model
            yield _sse({"chunk": chunk})

        assistant_text = "".join(full)
        history.append({"role": "assistant", "content": assistant_text})
        assistant_id = self.memory.remember(
            assistant_text,
            kind="turn",
            meta={"role": "assistant", "model": model_used},
            link_to=[user_id, *linked],
        )
        self._persist(sid, "plain")
        yield _sse({"done": True, "neuron_id": assistant_id, "model_used": model_used})

    # ---- agentic chat with tools ----

    async def agentic(
        self,
        session_id: str | None,
        user_text: str | None,
        tool_results: list[dict] | None,
    ) -> dict[str, Any]:
        sid = session_id or uuid.uuid4().hex
        history = self._history(sid, "agentic")

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
            system=system, messages=history, tools=self._available_tools()
        )

        history.append({"role": "assistant", "content": result.raw_content})

        # Handle brain-side tools (local + MCP) inline so the Mac doesn't see them.
        client_tool_calls: list[dict] = []
        brain_results: list[dict] = []
        for use in result.tool_uses:
            if use.name in BRAIN_TOOLS:
                output = self._run_brain_tool(use.name, use.input)
                brain_results.append({"id": use.id, "output": output})
            elif self.mcp and MCPManager.is_mcp_tool(use.name):
                output = await self.mcp.call_tool(use.name, use.input)
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

        self._persist(sid, "agentic")
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
        self.sessions.pop(f"_plain:{session_id}", None)
        self.memory.session_delete(session_id)
