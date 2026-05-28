from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from ..config import settings

log = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self) -> None:
        self.base = settings.ollama_url.rstrip("/")
        self.model = settings.ollama_model

    def _payload(self, system: str, messages: list[dict], stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": stream,
        }

    async def complete(self, system: str, messages: list[dict]) -> str:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{self.base}/api/chat", json=self._payload(system, messages, False))
            r.raise_for_status()
            return r.json()["message"]["content"]

    async def stream(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST", f"{self.base}/api/chat", json=self._payload(system, messages, True)
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    obj = json.loads(line)
                    chunk = obj.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
                    if obj.get("done"):
                        break
