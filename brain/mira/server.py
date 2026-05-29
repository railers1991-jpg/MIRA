from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .agent.bridge import ToolBridge
from .agent.cli_bridge import allowed_tool_patterns, write_mcp_config
from .agent.orchestrator import Orchestrator
from .config import settings
from .learning import distill_recent_turns
from .llm.anthropic_client import AnthropicClient
from .llm.subscription import ClaudeCodeProvider
from .mcp import MCPManager
from .memory.store import MemoryStore
from .scheduler import scheduler
from .skills import SkillExecutor, SkillForge, SkillStore

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
    assistant_neuron_id: str | None = None


class FeedbackRequest(BaseModel):
    signal: str  # "positive" | "negative"


class DecayRequest(BaseModel):
    half_life_days: float = 30.0
    prune_below: float | None = 0.05


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings.ensure_dirs()
    app.state.memory = MemoryStore(settings.data_dir)
    app.state.skills = SkillStore(settings.data_dir)
    app.state.bridge = ToolBridge()
    app.state.mcp = MCPManager(settings.mcp_config_path)
    await app.state.mcp.start()

    brain_url = f"http://{settings.host}:{settings.port}"
    app.state.agent_mcp_config = str(write_mcp_config(settings.data_dir, brain_url))
    app.state.agent_allowed_tools = allowed_tool_patterns()

    claude = AnthropicClient() if settings.anthropic_api_key else None
    app.state.skill_executor = SkillExecutor(
        store=app.state.skills, anthropic_client=claude, mcp=app.state.mcp
    )
    app.state.orchestrator = Orchestrator(
        memory=app.state.memory,
        mcp=app.state.mcp,
        skills=app.state.skills,
        skill_executor=app.state.skill_executor,
    )
    app.state.skill_forge = (
        SkillForge(
            store=app.state.skills,
            anthropic_client=claude,
            available_tools_provider=app.state.orchestrator._available_tools,
        )
        if claude
        else None
    )
    app.state.started_at = time.time()
    log.info("MIRA brain ready on %s:%d", settings.host, settings.port)
    try:
        async with scheduler(app.state.memory):
            yield
    finally:
        await app.state.mcp.stop()


app = FastAPI(title="MIRA Brain", version="0.3.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


class BridgeExecute(BaseModel):
    name: str
    input: dict[str, Any] = {}


@app.post("/bridge/execute")
async def bridge_execute(req: BridgeExecute) -> dict[str, Any]:
    """Run a Mac-side tool via the connected Mac executor (used by the
    stdio MCP tools server when a subscription CLI drives agent mode)."""
    return await app.state.bridge.request(req.name, req.input)


@app.websocket("/ws/agent")
async def ws_agent(ws: WebSocket) -> None:
    """The Mac connects here to act as MIRA's tool executor for the bridge."""
    await ws.accept()
    bridge: ToolBridge = app.state.bridge
    bridge.attach()

    async def pump() -> None:
        while True:
            call = await bridge.next_outbound()
            await ws.send_json(call)

    pump_task = asyncio.create_task(pump())
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "tool_result":
                bridge.resolve(msg["id"], msg.get("output", ""), msg.get("image_b64"))
    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()
        bridge.detach()


@app.get("/providers")
async def providers() -> dict[str, Any]:
    from .llm.router import LLMRouter

    return {
        "selected": settings.provider,
        "available": LLMRouter.availability(),
        "tools_require": "cloud",
    }


@app.get("/tools")
async def tools_list() -> dict[str, Any]:
    orch: Orchestrator = app.state.orchestrator
    tools = orch._available_tools()
    return {
        "tools": [{"name": t["name"], "description": t["description"]} for t in tools],
        "mcp_servers": app.state.mcp.server_status(),
        "skills": [s["name"] for s in app.state.skills.list_all()],
    }


class SkillUpsert(BaseModel):
    name: str
    description: str
    when_to_use: str = ""
    parameters: dict = {"type": "object", "properties": {}}
    steps: list[dict] = []
    returns: str = "{{_result}}"
    lessons: list[str] = []


class ForgeRequest(BaseModel):
    session_id: str
    mode: str = "agentic"


class LessonRequest(BaseModel):
    outcome: str


@app.get("/skills")
async def skills_list() -> list[dict]:
    return app.state.skills.list_all()


@app.get("/skill/{name}")
async def skill_get(name: str) -> dict:
    skill = app.state.skills.get(name)
    if not skill:
        raise HTTPException(404, "skill not found")
    return skill


@app.put("/skill/{name}")
async def skill_put(name: str, req: SkillUpsert) -> dict[str, str]:
    payload = req.model_dump()
    payload["name"] = name
    try:
        app.state.skills.upsert(payload)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"status": "ok"}


@app.delete("/skill/{name}")
async def skill_delete(name: str) -> dict[str, str]:
    if not app.state.skills.delete(name):
        raise HTTPException(404, "skill not found")
    return {"status": "ok"}


@app.post("/skill/{name}/run")
async def skill_run(name: str, params: dict[str, Any] | None = None) -> dict[str, str]:
    output = await app.state.skill_executor.execute(name, params or {})
    return {"output": output}


@app.post("/skills/forge")
async def skills_forge(req: ForgeRequest) -> dict[str, Any]:
    if app.state.skill_forge is None:
        raise HTTPException(503, "forge requires ANTHROPIC_API_KEY")
    session = app.state.memory.session_load(req.session_id)
    if not session:
        raise HTTPException(404, "session not found")
    skill = await app.state.skill_forge.forge_from_history(session["history"])
    if skill is None:
        return {"created": None}
    return {"created": skill}


@app.post("/skill/{name}/lesson")
async def skill_lesson(name: str, req: LessonRequest) -> dict[str, Any]:
    if app.state.skill_forge is None:
        raise HTTPException(503, "reflection requires ANTHROPIC_API_KEY")
    lesson = await app.state.skill_forge.reflect_lesson(name, req.outcome)
    return {"lesson": lesson}


@app.get("/metrics")
async def metrics() -> dict[str, Any]:
    memory: MemoryStore = app.state.memory
    orch: Orchestrator = app.state.orchestrator
    uptime = time.time() - app.state.started_at
    return {
        "uptime_s": round(uptime, 1),
        "sessions_active": sum(1 for k in orch.sessions if not k.startswith("_plain:")),
        "sessions_plain": sum(1 for k in orch.sessions if k.startswith("_plain:")),
        **memory.stats(),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse | StreamingResponse:
    orch: Orchestrator = app.state.orchestrator

    if req.tools_enabled or req.tool_results:
        if req.stream:
            raise HTTPException(400, "streaming is not supported with tools_enabled yet")
        # API key → native tool-loop. Otherwise, if a subscription CLI is
        # available, let it drive the loop with MIRA's tools over MCP.
        if settings.anthropic_api_key is None and not req.tool_results:
            if ClaudeCodeProvider.available(settings.claude_cli_path):
                result = await orch.agentic_via_cli(
                    session_id=req.session_id,
                    user_text=req.text,
                    mcp_config_path=app.state.agent_mcp_config,
                    allowed_tools=app.state.agent_allowed_tools,
                )
                return ChatResponse(**result)
            raise HTTPException(
                503,
                "Agent mode needs an Anthropic API key or the Claude Code CLI "
                "(claude login). Chat and skills work on any provider.",
            )
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
            orch.stream(req.text, session_id=req.session_id, model_hint=req.model_hint),
            media_type="text/event-stream",
        )
    result = await orch.respond(
        req.text, session_id=req.session_id, model_hint=req.model_hint
    )
    return ChatResponse(**result)


@app.post("/session/{session_id}/reset")
async def session_reset(session_id: str) -> dict[str, str]:
    app.state.orchestrator.reset_session(session_id)
    return {"status": "ok"}


@app.get("/sessions")
async def sessions_list(limit: int = 50) -> list[dict]:
    return app.state.memory.session_list(limit=limit)


@app.get("/session/{session_id}")
async def session_get(session_id: str) -> dict:
    data = app.state.memory.session_load(session_id)
    if not data:
        raise HTTPException(404, "session not found")
    return data


class TitleRequest(BaseModel):
    title: str


@app.patch("/session/{session_id}")
async def session_patch(session_id: str, req: TitleRequest) -> dict[str, str]:
    if not app.state.memory.session_set_title(session_id, req.title):
        raise HTTPException(404, "session not found")
    return {"status": "ok"}


@app.delete("/session/{session_id}")
async def session_delete(session_id: str) -> dict[str, str]:
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


@app.post("/memory/{neuron_id}/feedback")
async def memory_feedback(neuron_id: str, req: FeedbackRequest) -> dict[str, str]:
    if req.signal not in {"positive", "negative"}:
        raise HTTPException(400, "signal must be 'positive' or 'negative'")
    ok = app.state.memory.feedback(neuron_id, req.signal)
    if not ok:
        raise HTTPException(404, "neuron not found")
    return {"status": "ok"}


@app.post("/learn/distill")
async def learn_distill(limit: int = 50) -> dict[str, Any]:
    result = await distill_recent_turns(app.state.memory, limit=limit)
    return {
        "added": result.added,
        "skipped_duplicates": result.skipped_duplicates,
        "items": result.raw,
    }


@app.post("/learn/decay")
async def learn_decay(req: DecayRequest) -> dict[str, int]:
    updated = app.state.memory.apply_decay(half_life_days=req.half_life_days)
    pruned = 0
    if req.prune_below is not None:
        pruned = app.state.memory.prune(
            min_strength=req.prune_below,
            keep_kinds=("fact", "preference", "skill"),
        )
    return {"updated": updated, "pruned": pruned}


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s — %(message)s"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    uvicorn.run("mira.server:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
