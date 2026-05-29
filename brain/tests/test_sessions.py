from __future__ import annotations

import time
from pathlib import Path

from mira.memory.store import MemoryStore


def test_session_save_and_load_roundtrip(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    store.session_save("s1", history, mode="plain")
    loaded = store.session_load("s1")
    assert loaded is not None
    assert loaded["history"] == history
    assert loaded["mode"] == "plain"
    assert loaded["title"] is None


def test_session_update_preserves_title(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.session_save("s1", [{"role": "user", "content": "first"}], mode="plain")
    assert store.session_set_title("s1", "First chat") is True

    store.session_save("s1", [{"role": "user", "content": "later"}], mode="plain")
    loaded = store.session_load("s1")
    assert loaded["title"] == "First chat"
    assert loaded["history"][-1]["content"] == "later"


def test_session_list_ordered_by_recent(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.session_save("a", [], mode="plain")
    time.sleep(0.01)
    store.session_save("b", [], mode="agentic")
    listed = store.session_list(limit=10)
    assert [s["id"] for s in listed[:2]] == ["b", "a"]
    assert listed[0]["mode"] == "agentic"


def test_session_delete(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.session_save("s1", [], mode="plain")
    assert store.session_load("s1") is not None
    assert store.session_delete("s1") is True
    assert store.session_load("s1") is None
    assert store.session_delete("missing") is False


def test_session_with_structured_content(tmp_path: Path) -> None:
    """Agentic sessions store nested content (tool_use / tool_result blocks)."""
    store = MemoryStore(tmp_path)
    history = [
        {"role": "user", "content": "open Safari"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "On it."},
                {"type": "tool_use", "id": "tu_1", "name": "open_url",
                 "input": {"url": "https://safari"}},
            ],
        },
    ]
    store.session_save("s1", history, mode="agentic")
    loaded = store.session_load("s1")
    assert loaded["history"] == history
