from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mira.skills import SkillExecutor, SkillStore
from mira.skills.executor import render, render_args
from mira.skills.forge import _format_history, _parse_json


# ---------- store ----------


def _valid_skill(name: str = "demo") -> dict:
    return {
        "name": name,
        "description": "Demo skill",
        "when_to_use": "when testing",
        "parameters": {"type": "object", "properties": {"x": {"type": "string"}}},
        "steps": [{"type": "prompt", "prompt": "echo {{x}}", "save_as": "_result"}],
        "returns": "{{_result}}",
    }


def test_store_validate_rejects_bad_name() -> None:
    bad = _valid_skill(name="BadName")
    assert any("name" in e for e in SkillStore.validate(bad))


def test_store_validate_rejects_empty_steps() -> None:
    bad = _valid_skill()
    bad["steps"] = []
    assert any("steps" in e for e in SkillStore.validate(bad))


def test_store_validate_rejects_unknown_step_type() -> None:
    bad = _valid_skill()
    bad["steps"] = [{"type": "magic"}]
    assert any("type" in e for e in SkillStore.validate(bad))


def test_store_validate_accepts_minimal_valid() -> None:
    assert SkillStore.validate(_valid_skill()) == []


def test_store_upsert_and_get(tmp_path: Path) -> None:
    store = SkillStore(tmp_path)
    store.upsert(_valid_skill())
    skill = store.get("demo")
    assert skill is not None
    assert skill["description"] == "Demo skill"
    assert skill["steps"][0]["save_as"] == "_result"
    assert skill["success_count"] == 0


def test_store_upsert_preserves_lessons(tmp_path: Path) -> None:
    store = SkillStore(tmp_path)
    store.upsert(_valid_skill())
    assert store.add_lesson("demo", "be concise") is True
    store.upsert(_valid_skill())  # re-upsert
    skill = store.get("demo")
    assert "be concise" in skill["lessons"]


def test_store_add_lesson_dedupes_and_caps(tmp_path: Path) -> None:
    store = SkillStore(tmp_path)
    store.upsert(_valid_skill())
    assert store.add_lesson("demo", "alpha") is True
    assert store.add_lesson("demo", "alpha") is False  # duplicate
    for i in range(25):
        store.add_lesson("demo", f"lesson {i}")
    lessons = store.get("demo")["lessons"]
    assert len(lessons) <= 20


def test_store_counts_success_and_failure(tmp_path: Path) -> None:
    store = SkillStore(tmp_path)
    store.upsert(_valid_skill())
    store.record_success("demo")
    store.record_success("demo")
    store.record_failure("demo")
    skill = store.get("demo")
    assert skill["success_count"] == 2
    assert skill["failure_count"] == 1


def test_store_as_tools_namespaces(tmp_path: Path) -> None:
    store = SkillStore(tmp_path)
    store.upsert(_valid_skill())
    store.upsert(_valid_skill(name="other"))
    tools = store.as_tools()
    names = {t["name"] for t in tools}
    assert names == {"skill__demo", "skill__other"}


def test_store_delete(tmp_path: Path) -> None:
    store = SkillStore(tmp_path)
    store.upsert(_valid_skill())
    assert store.delete("demo") is True
    assert store.delete("demo") is False
    assert store.get("demo") is None


# ---------- templating ----------


def test_render_substitutes_simple_var() -> None:
    assert render("hi {{name}}", {"name": "World"}) == "hi World"


def test_render_dotted_lookup_into_dict() -> None:
    ctx = {"user": {"name": "Alex", "role": "engineer"}}
    assert render("{{user.name}} ({{user.role}})", ctx) == "Alex (engineer)"


def test_render_unknown_key_becomes_empty() -> None:
    assert render("hello {{nope}}", {}) == "hello "


def test_render_json_encodes_collections() -> None:
    out = render("ids={{ids}}", {"ids": [1, 2, 3]})
    assert out == "ids=[1, 2, 3]"


def test_render_args_walks_nested_structure() -> None:
    ctx = {"q": "milk", "n": 5}
    args = {"query": "{{q}}", "limit": "{{n}}", "nested": {"k": "{{q}}-{{n}}"}}
    out = render_args(args, ctx)
    assert out == {"query": "milk", "limit": "5", "nested": {"k": "milk-5"}}


# ---------- executor ----------


class _FakeAnthropic:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def complete(self, system: str, messages: list[dict]) -> str:
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        return f"<echo: {prompt}>"


class _FakeMCP:
    @staticmethod
    def is_mcp_tool(name: str) -> bool:
        return name.startswith("mcp__")

    async def call_tool(self, name: str, args: dict) -> str:
        return f"called {name} with {args}"


@pytest.mark.asyncio
async def test_executor_runs_prompt_step(tmp_path: Path) -> None:
    store = SkillStore(tmp_path)
    store.upsert(_valid_skill())
    fake = _FakeAnthropic()
    exec_ = SkillExecutor(store=store, anthropic_client=fake, mcp=None)  # type: ignore[arg-type]
    out = await exec_.execute("demo", {"x": "hi"})
    assert "<echo: echo hi>" in out
    assert store.get("demo")["success_count"] == 1


@pytest.mark.asyncio
async def test_executor_unknown_skill_returns_error(tmp_path: Path) -> None:
    exec_ = SkillExecutor(store=SkillStore(tmp_path), anthropic_client=None, mcp=None)
    out = await exec_.execute("missing")
    assert out.startswith("ERROR: unknown skill")


@pytest.mark.asyncio
async def test_executor_failure_increments_failure_count(tmp_path: Path) -> None:
    store = SkillStore(tmp_path)
    store.upsert(_valid_skill())
    exec_ = SkillExecutor(store=store, anthropic_client=None, mcp=None)
    out = await exec_.execute("demo", {"x": "hi"})
    # prompt step with no anthropic client → failure
    assert out.startswith("ERROR:")
    assert store.get("demo")["failure_count"] == 1


@pytest.mark.asyncio
async def test_executor_runs_tool_step_via_mcp(tmp_path: Path) -> None:
    store = SkillStore(tmp_path)
    store.upsert({
        "name": "mcp_runner",
        "description": "Call an MCP tool",
        "when_to_use": "demo",
        "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
        "steps": [
            {
                "type": "tool",
                "tool": "mcp__search__query",
                "args": {"q": "{{q}}"},
                "save_as": "hits",
            }
        ],
        "returns": "{{hits}}",
    })
    exec_ = SkillExecutor(
        store=store, anthropic_client=None, mcp=_FakeMCP()  # type: ignore[arg-type]
    )
    out = await exec_.execute("mcp_runner", {"q": "tea"})
    assert "called mcp__search__query" in out
    assert "tea" in out


# ---------- forge helpers ----------


def test_parse_json_strips_code_fences() -> None:
    raw = '```json\n{"name": "do_thing"}\n```'
    assert _parse_json(raw) == {"name": "do_thing"}


def test_parse_json_returns_none_for_null_text() -> None:
    assert _parse_json("null") is None
    assert _parse_json("```json\nnull\n```") is None


def test_format_history_truncates_left() -> None:
    history = [{"role": "user", "content": "x" * 6000}]
    formatted = _format_history(history, max_chars=200)
    assert len(formatted) == 200
    assert formatted.endswith("x")


def test_format_history_flattens_blocks() -> None:
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": [
            {"type": "text", "text": "hello"},
            {"type": "tool_use", "name": "do"},
        ]},
    ]
    out = _format_history(history)
    assert "[user] hi" in out
    assert "[assistant] hello" in out
    assert "(tool_use do)" in out


def _coerce(value: Any) -> Any:
    return value
