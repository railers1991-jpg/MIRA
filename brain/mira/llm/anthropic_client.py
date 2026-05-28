from __future__ import annotations

import logging
from typing import AsyncIterator

from anthropic import AsyncAnthropic

from ..config import settings

log = logging.getLogger(__name__)


class AnthropicClient:
    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    async def complete(self, system: str, messages: list[dict]) -> str:
        resp = await self.client.messages.create(
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=4096,
        )
        return "".join(block.text for block in resp.content if block.type == "text")

    async def stream(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        async with self.client.messages.stream(
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=4096,
        ) as stream:
            async for text in stream.text_stream:
                yield text
