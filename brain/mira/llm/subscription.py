"""Subscription-backed providers via local agent CLIs.

Instead of a metered API key, MIRA can borrow the auth of agent CLIs the
user already signed into with their subscription:

- ``claude`` (Claude Code)   — Claude Pro / Max,  via ``claude login``
- ``codex``  (OpenAI Codex)  — ChatGPT Plus / Pro / Codex, via ``codex login``

We invoke them in non-interactive ("print" / "exec") mode and read stdout.
MIRA never reads, stores, or transmits the credentials — each CLI owns its
own session on disk. This is the same headless path those tools document.

Limitations (v1):
- These providers cover plain reasoning: chat replies and skill ``prompt``
  steps. MIRA's native system-control tool-loop still needs an API key
  (the custom tool schemas aren't bridged through the CLIs yet).
- Streaming is non-incremental: the CLI runs to completion, then the full
  text is yielded as one chunk.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import AsyncIterator

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 180


def _conversation_to_text(messages: list[dict]) -> str:
    """Flatten an Anthropic-shaped message list into a plain transcript.

    The trailing user message is the live query; earlier turns are context.
    Non-text content blocks (tool_use / tool_result) are summarised so the
    CLI still gets coherent context.
    """
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "user").capitalize()
        content = msg.get("content")
        if isinstance(content, str):
            lines.append(f"{role}: {content}")
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    lines.append(f"{role}: {block['text']}")
                elif block.get("type") == "tool_use":
                    lines.append(f"{role}: [used tool {block.get('name')}]")
                elif block.get("type") == "tool_result":
                    snippet = str(block.get("content", ""))[:300]
                    lines.append(f"{role}: [tool result] {snippet}")
    return "\n\n".join(lines)


async def _run(
    args: list[str], stdin_text: str | None, timeout_s: int = DEFAULT_TIMEOUT_S
) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if stdin_text is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(stdin_text.encode() if stdin_text is not None else None),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError as e:
        proc.kill()
        raise RuntimeError(f"agent CLI timed out after {timeout_s}s") from e
    if proc.returncode != 0:
        detail = err.decode(errors="replace").strip()[:500] or "no stderr"
        raise RuntimeError(f"agent CLI exited {proc.returncode}: {detail}")
    return out.decode(errors="replace").strip()


class ClaudeCodeProvider:
    """Drive the `claude` (Claude Code) CLI using the user's subscription."""

    def __init__(self, cli_path: str = "claude", model: str | None = None) -> None:
        self.cli = cli_path
        self.model = model

    @staticmethod
    def available(cli_path: str = "claude") -> bool:
        return shutil.which(cli_path) is not None

    @property
    def label(self) -> str:
        return f"claude-code:{self.model or 'default'}"

    def _args(self) -> list[str]:
        args = [self.cli, "-p", "--output-format", "text"]
        if self.model:
            args += ["--model", self.model]
        return args

    async def complete(self, system: str, messages: list[dict]) -> str:
        args = self._args()
        if system:
            args += ["--append-system-prompt", system]
        prompt = _conversation_to_text(messages)
        return await _run(args, stdin_text=prompt)

    async def stream(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        # Non-incremental: run to completion, emit once.
        text = await self.complete(system=system, messages=messages)
        yield text


class CodexProvider:
    """Drive the `codex` (OpenAI Codex) CLI using the user's subscription."""

    def __init__(self, cli_path: str = "codex", model: str | None = None) -> None:
        self.cli = cli_path
        self.model = model

    @staticmethod
    def available(cli_path: str = "codex") -> bool:
        return shutil.which(cli_path) is not None

    @property
    def label(self) -> str:
        return f"codex:{self.model or 'default'}"

    def _args(self) -> list[str]:
        args = [self.cli, "exec"]
        if self.model:
            args += ["-m", self.model]
        return args

    async def complete(self, system: str, messages: list[dict]) -> str:
        # Codex exec has no separate system flag; prepend it to the prompt.
        body = _conversation_to_text(messages)
        prompt = f"{system}\n\n{body}" if system else body
        return await _run([*self._args(), prompt], stdin_text=None)

    async def stream(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        text = await self.complete(system=system, messages=messages)
        yield text
