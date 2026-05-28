from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .agent.orchestrator import Orchestrator
from .config import settings
from .memory.store import MemoryStore

log = logging.getLogger("mira")


class ChatRequest(BaseModel):
    text: str
    model_hint: str | None = None
    stream: bool = True


class ChatResponse(BaseModel):
    text: str
    model_used: str
    neurons_recalled: int


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings.ensure_dirs()
    app.state.memory = MemoryStore(settings.data_dir)
    app.state.orchestrator = Orchestrator(memory=app.state.memory)
    log.info("MIRA brain ready on %s:%d", settings.host, settings.port)
    yield


app = FastAPI(title="MIRA Brain", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse | StreamingResponse:
    orch: Orchestrator = app.state.orchestrator
    if req.stream:
        return StreamingResponse(
            orch.stream(req.text, model_hint=req.model_hint),
            media_type="text/event-stream",
        )
    result = await orch.respond(req.text, model_hint=req.model_hint)
    return ChatResponse(**result)


@app.get("/memory/recent")
async def memory_recent(limit: int = 20) -> list[dict]:
    return app.state.memory.recent(limit=limit)


@app.post("/memory/search")
async def memory_search(query: str, k: int = 8) -> list[dict]:
    if not query.strip():
        raise HTTPException(400, "empty query")
    return app.state.memory.recall(query, k=k)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    uvicorn.run("mira.server:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
