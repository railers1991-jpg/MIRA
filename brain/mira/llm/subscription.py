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
import os
import shutil
from pathlib import Path
from typing import AsyncIterator

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 180


def _resolve_cli(name: str, configured: str | None = None) -> str | None:
    """Locate an agent CLI binary.

    The brain often runs under launchd with a minimal PATH that excludes the
    user's install dirs, so we probe common locations in addition to PATH.
    `configured` may be a bare command name or an absolute path override.
    Returns an absolute path, or None if not found.
    """
    candidate = configured or name
    if os.path.isabs(candidate):
        return candidate if os.access(candidate, os.X_OK) else None
    found = shutil.which(candidate)
    if found:
        return found
    home = Path.home()
    for path in (
        home / ".local/bin" / name,
        home / ".claude/local" / name,
        Path("/opt/homebrew/bin") / name,
        Path("/usr/local/bin") / name,
        home / "bin" / name,
    ):
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


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
        self.cli = _resolve_cli("claude", cli_path) or cli_path
        self.model = model

    @staticmethod
    def available(cli_path: str = "claude") -> bool:
        return _resolve_cli("claude", cli_path) is not None

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

    async def complete_agentic(
        self,
        system: str,
        messages: list[dict],
        mcp_config_path: str,
        allowed_tools: list[str],
        timeout_s: int = 600,
    ) -> str:
        """Run the CLI's own agent loop with MIRA's tools attached over MCP.

        The CLI discovers MIRA's Mac tools through the MCP config and
        executes them via the brain bridge → Mac. We only get the final
        text back; tool side-effects already happened on the Mac.
        """
        args = [
            self.cli, "-p", "--output-format", "text",
            "--mcp-config", mcp_config_path,
            # Headless: there's no TTY to answer permission prompts, so bypass
            # Claude Code's own gate. Safety stays with MIRA: mcp__mira__* tools
            # run through the Mac's ConsentManager, and the user opted into
            # agent mode explicitly.
            "--permission-mode", "bypassPermissions",
        ]
        if allowed_tools:
            args += ["--allowedTools", ",".join(allowed_tools)]
        if self.model:
            args += ["--model", self.model]
        if system:
            args += ["--append-system-prompt", system]
        prompt = _conversation_to_text(messages)
        return await _run(args, stdin_text=prompt, timeout_s=timeout_s)


class CodexProvider:
    """Drive the `codex` (OpenAI Codex) CLI using the user's subscription."""

    def __init__(self, cli_path: str = "codex", model: str | None = None) -> None:
        self.cli = _resolve_cli("codex", cli_path) or cli_path
        self.model = model

    @staticmethod
    def available(cli_path: str = "codex") -> bool:
        return _resolve_cli("codex", cli_path) is not None

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
