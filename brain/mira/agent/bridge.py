"""Bridge that lets the brain execute Mac-side tools out of band.

In the API-key tool-loop the Mac executes tools inside the /chat HTTP
round-trip. But when a subscription agent CLI drives the loop, tool calls
arrive asynchronously (via the MCP tools server → /bridge/execute) while
the Mac is busy awaiting its /chat response on a different connection.

The Mac keeps a WebSocket open to /ws/agent and registers as the executor.
`request()` pushes a tool call to the Mac and awaits the matching result;
`resolve()` is called by the WS handler when the Mac replies. If no Mac is
connected, requests fail fast so the CLI gets a clear error instead of
hanging.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

log = logging.getLogger(__name__)


class ToolBridge:
    def __init__(self, timeout_s: float = 120.0) -> None:
        self.timeout_s = timeout_s
        self._pending: dict[str, asyncio.Future] = {}
        self._outbox: asyncio.Queue[dict] = asyncio.Queue()
        self._connected = 0

    @property
    def connected(self) -> bool:
        return self._connected > 0

    def attach(self) -> None:
        self._connected += 1

    def detach(self) -> None:
        self._connected = max(0, self._connected - 1)
        # Fail any in-flight calls if the last executor dropped.
        if self._connected == 0:
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_result({"output": "ERROR: Mac executor disconnected", "error": True})
            self._pending.clear()

    async def request(self, name: str, tool_input: dict) -> dict:
        if not self.connected:
            return {"output": "ERROR: no Mac client connected to execute tools", "error": True}
        call_id = uuid.uuid4().hex
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[call_id] = fut
        await self._outbox.put(
            {"type": "tool_call", "id": call_id, "name": name, "input": tool_input}
        )
        try:
            return await asyncio.wait_for(fut, timeout=self.timeout_s)
        except asyncio.TimeoutError:
            return {"output": f"ERROR: tool '{name}' timed out after {self.timeout_s}s", "error": True}
        finally:
            self._pending.pop(call_id, None)

    def resolve(self, call_id: str, output: str, image_b64: str | None = None) -> bool:
        fut = self._pending.get(call_id)
        if fut is None or fut.done():
            return False
        fut.set_result({"output": output, "image_b64": image_b64, "error": False})
        return True

    async def next_outbound(self) -> dict:
        """Block until there's a tool call to push to the Mac."""
        return await self._outbox.get()
