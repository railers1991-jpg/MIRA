from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .agent.orchestrator import Orchestrator
from .config import settings
from .memory.store import MemoryStore

log = logging.getLogger("mira")


class ToolResult(BaseModel):
    id: str
    output: str
    image_b64: str | None = None


class ChatRequest(BaseModel):
    text: str | None = None
    model_hint: str | None = None
    stream: bool = True
    tools_enabled: bool = False
    session_id: str | None = None
    tool_results: list[ToolResult] | None = None


class ToolCall(BaseModel):
    id: str
    name: str
    input: dict[str, Any]


class ChatResponse(BaseModel):
    text: str
    model_used: str
    neurons_recalled: int = 0
    session_id: str | None = None
    tool_calls: list[ToolCall] = []


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings.ensure_dirs()
    app.state.memory = MemoryStore(settings.data_dir)
    app.state.orchestrator = Orchestrator(memory=app.state.memory)
    log.info("MIRA brain ready on %s:%d", settings.host, settings.port)
    yield


app = FastAPI(title="MIRA Brain", version="0.3.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse | StreamingResponse:
    orch: Orchestrator = app.state.orchestrator

    if req.tools_enabled or req.tool_results:
        if req.stream:
            raise HTTPException(400, "streaming is not supported with tools_enabled yet")
        result = await orch.agentic(
            session_id=req.session_id,
            user_text=req.text,
            tool_results=[r.model_dump() for r in (req.tool_results or [])],
        )
        return ChatResponse(**result)

    if not req.text:
        raise HTTPException(400, "text is required for non-agentic chat")

    if req.stream:
        return StreamingResponse(
            orch.stream(req.text, model_hint=req.model_hint),
            media_type="text/event-stream",
        )
    result = await orch.respond(req.text, model_hint=req.model_hint)
    return ChatResponse(**result)


@app.post("/session/{session_id}/reset")
async def session_reset(session_id: str) -> dict[str, str]:
    app.state.orchestrator.reset_session(session_id)
    return {"status": "ok"}


@app.get("/memory/recent")
async def memory_recent(limit: int = 20) -> list[dict]:
    return app.state.memory.recent(limit=limit)


@app.post("/memory/search")
async def memory_search(query: str, k: int = 8) -> list[dict]:
    if not query.strip():
        raise HTTPException(400, "empty query")
    return app.state.memory.recall(query, k=k)


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s — %(message)s"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    uvicorn.run("mira.server:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
