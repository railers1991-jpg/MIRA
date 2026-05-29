"""Hybrid LLM router.

Routes each request to one of four providers by privacy, complexity, and
explicit preference:

- ``cloud``       — Anthropic API (metered key); the only provider that can
                    drive MIRA's native tool-use loop
- ``claude_code`` — Claude Code CLI on the user's Claude Pro/Max subscription
- ``codex``       — OpenAI Codex CLI on the user's ChatGPT subscription
- ``local``       — Ollama (fully offline / private)

Provider precedence is controlled by ``settings.provider`` (default ``auto``).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import AsyncIterator

from ..config import settings
from .anthropic_client import AnthropicClient, CompletionResult
from .ollama_client import OllamaClient
from .subscription import ClaudeCodeProvider, CodexProvider

log = logging.getLogger(__name__)

PRIVATE_PATTERNS = re.compile(
    r"\b(password|пароль|секрет|secret|api[_ ]?key|token|ssn|credit card)\b",
    re.IGNORECASE,
)

# Hint aliases the caller may pass through `model_hint`.
HINT_ALIASES = {
    "cloud": "cloud",
    "api": "cloud",
    "local": "local",
    "ollama": "local",
    "subscription": "claude_code",
    "claude_code": "claude_code",
    "claude": "claude_code",
    "codex": "codex",
}


@dataclass
class RoutedResponse:
    text: str
    model_used: str


class LLMRouter:
    """Choose a provider by privacy, complexity, and explicit preference."""

    def __init__(self) -> None:
        self._claude: AnthropicClient | None = None
        self._ollama: OllamaClient | None = None
        self._claude_code: ClaudeCodeProvider | None = None
        self._codex: CodexProvider | None = None

    # ---- lazy provider handles ----

    @property
    def claude(self) -> AnthropicClient:
        if self._claude is None:
            self._claude = AnthropicClient()
        return self._claude

    @property
    def ollama(self) -> OllamaClient:
        if self._ollama is None:
            self._ollama = OllamaClient()
        return self._ollama

    @property
    def claude_code(self) -> ClaudeCodeProvider:
        if self._claude_code is None:
            self._claude_code = ClaudeCodeProvider(
                cli_path=settings.claude_cli_path, model=settings.claude_cli_model
            )
        return self._claude_code

    @property
    def codex(self) -> CodexProvider:
        if self._codex is None:
            self._codex = CodexProvider(
                cli_path=settings.codex_cli_path, model=settings.codex_cli_model
            )
        return self._codex

    # ---- availability ----

    @staticmethod
    def availability() -> dict[str, bool]:
        return {
            "cloud": settings.anthropic_api_key is not None,
            "claude_code": ClaudeCodeProvider.available(settings.claude_cli_path),
            "codex": CodexProvider.available(settings.codex_cli_path),
            "local": True,  # Ollama is assumed reachable; ping happens on use
        }

    def _auto_chain(self) -> str:
        if settings.anthropic_api_key is not None:
            return "cloud"
        if ClaudeCodeProvider.available(settings.claude_cli_path):
            return "claude_code"
        if CodexProvider.available(settings.codex_cli_path):
            return "codex"
        return "local"

    def _resolve_preference(self) -> str:
        pref = settings.provider
        if pref == "auto":
            return self._auto_chain()
        if pref in {"api", "cloud"}:
            return "cloud"
        if pref == "subscription":
            if ClaudeCodeProvider.available(settings.claude_cli_path):
                return "claude_code"
            if CodexProvider.available(settings.codex_cli_path):
                return "codex"
            return self._auto_chain()
        if pref in {"claude_code", "claude"}:
            return "claude_code"
        if pref == "codex":
            return "codex"
        if pref in {"local", "ollama"}:
            return "local"
        return self._auto_chain()

    def choose(self, prompt: str, hint: str | None = None) -> str:
        if hint:
            aliased = HINT_ALIASES.get(hint)
            if aliased:
                return aliased
        # Anything sensitive stays fully offline.
        if PRIVATE_PATTERNS.search(prompt):
            return "local"
        return self._resolve_preference()

    # ---- dispatch ----

    def _provider_for(self, target: str):
        if target == "cloud":
            return self.claude, f"claude:{settings.anthropic_model}"
        if target == "claude_code":
            return self.claude_code, self.claude_code.label
        if target == "codex":
            return self.codex, self.codex.label
        return self.ollama, f"ollama:{settings.ollama_model}"

    async def complete(
        self, system: str, messages: list[dict], hint: str | None = None
    ) -> RoutedResponse:
        target = self.choose(messages[-1]["content"] if messages else "", hint)
        log.info("routing → %s", target)
        provider, label = self._provider_for(target)
        text = await provider.complete(system=system, messages=messages)
        return RoutedResponse(text=text, model_used=label)

    async def complete_with_tools(
        self, system: str, messages: list[dict], tools: list[dict]
    ) -> tuple[CompletionResult, str]:
        """Tool-use always routes to the Anthropic API.

        The subscription CLIs and local models can't drive MIRA's custom
        tool schemas yet, so an API key is required for the agentic loop.
        """
        if settings.anthropic_api_key is None:
            raise RuntimeError(
                "Tool use needs an Anthropic API key. Subscription providers "
                "(Claude Code / Codex) power chat and skills, but not MIRA's "
                "native tool-loop yet — set ANTHROPIC_API_KEY for agent mode."
            )
        result = await self.claude.complete_with_tools(
            system=system, messages=messages, tools=tools
        )
        return result, f"claude:{settings.anthropic_model}"

    async def stream(
        self, system: str, messages: list[dict], hint: str | None = None
    ) -> AsyncIterator[tuple[str, str]]:
        """Yield (chunk, model_used). Model is repeated on every chunk so the
        UI can label streamed tokens and switch label mid-conversation."""
        target = self.choose(messages[-1]["content"] if messages else "", hint)
        log.info("routing (stream) → %s", target)
        provider, label = self._provider_for(target)
        async for chunk in provider.stream(system=system, messages=messages):
            yield chunk, label
