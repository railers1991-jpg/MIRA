"""Hybrid LLM router: pick Claude (cloud) or Ollama (local) per request."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import AsyncIterator

from ..config import settings
from .anthropic_client import AnthropicClient, CompletionResult
from .ollama_client import OllamaClient

log = logging.getLogger(__name__)

PRIVATE_PATTERNS = re.compile(
    r"\b(password|пароль|секрет|secret|api[_ ]?key|token|ssn|credit card)\b",
    re.IGNORECASE,
)


@dataclass
class RoutedResponse:
    text: str
    model_used: str


class LLMRouter:
    """Choose model by privacy, complexity, and explicit hints."""

    def __init__(self) -> None:
        self._claude: AnthropicClient | None = None
        self._ollama: OllamaClient | None = None

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

    def choose(self, prompt: str, hint: str | None = None) -> str:
        if hint in {"local", "cloud"}:
            return hint
        if PRIVATE_PATTERNS.search(prompt):
            return "local"
        if settings.anthropic_api_key is None:
            return "local"
        if len(prompt) < 200 and "?" not in prompt and "code" not in prompt.lower():
            return "local"
        return "cloud"

    async def complete(
        self, system: str, messages: list[dict], hint: str | None = None
    ) -> RoutedResponse:
        target = self.choose(messages[-1]["content"] if messages else "", hint)
        log.info("routing → %s", target)
        if target == "cloud":
            text = await self.claude.complete(system=system, messages=messages)
            return RoutedResponse(text=text, model_used=f"claude:{settings.anthropic_model}")
        text = await self.ollama.complete(system=system, messages=messages)
        return RoutedResponse(text=text, model_used=f"ollama:{settings.ollama_model}")

    async def complete_with_tools(
        self, system: str, messages: list[dict], tools: list[dict]
    ) -> tuple[CompletionResult, str]:
        """Tool-use always routes to Claude — local models are unreliable here."""
        if settings.anthropic_api_key is None:
            raise RuntimeError("Tool use requires ANTHROPIC_API_KEY (Claude only for now)")
        result = await self.claude.complete_with_tools(
            system=system, messages=messages, tools=tools
        )
        return result, f"claude:{settings.anthropic_model}"

    async def stream(
        self, system: str, messages: list[dict], hint: str | None = None
    ) -> AsyncIterator[tuple[str, str]]:
        """Yield (chunk, model_used). Model is repeated on every chunk so the
        caller can label streamed tokens — overhead is tiny and lets the UI
        switch label mid-conversation."""
        target = self.choose(messages[-1]["content"] if messages else "", hint)
        log.info("routing (stream) → %s", target)
        if target == "cloud":
            model_used = f"claude:{settings.anthropic_model}"
            async for chunk in self.claude.stream(system=system, messages=messages):
                yield chunk, model_used
        else:
            model_used = f"ollama:{settings.ollama_model}"
            async for chunk in self.ollama.stream(system=system, messages=messages):
                yield chunk, model_used
