from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic

from ..config import settings

log = logging.getLogger(__name__)


@dataclass
class ToolUse:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class CompletionResult:
    text: str
    tool_uses: list[ToolUse] = field(default_factory=list)
    stop_reason: str | None = None
    raw_content: list[dict] = field(default_factory=list)


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

    async def complete_with_tools(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
    ) -> CompletionResult:
        resp = await self.client.messages.create(
            model=self.model,
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=4096,
        )
        text_parts: list[str] = []
        tool_uses: list[ToolUse] = []
        raw: list[dict] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
                raw.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                args = dict(block.input)
                tool_uses.append(ToolUse(id=block.id, name=block.name, input=args))
                raw.append(
                    {"type": "tool_use", "id": block.id, "name": block.name, "input": args}
                )
        return CompletionResult(
            text="".join(text_parts),
            tool_uses=tool_uses,
            stop_reason=resp.stop_reason,
            raw_content=raw,
        )

    async def stream(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        async with self.client.messages.stream(
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=4096,
        ) as stream:
            async for text in stream.text_stream:
                yield text
