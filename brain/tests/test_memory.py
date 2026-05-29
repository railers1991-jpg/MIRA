from __future__ import annotations

from pathlib import Path

from mira.memory.store import MemoryStore


def test_remember_and_recent(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    nid = store.remember("hello world", kind="turn", meta={"role": "user"})
    assert nid
    rows = store.recent(10)
    assert len(rows) == 1
    assert rows[0]["content"] == "hello world"
    assert rows[0]["kind"] == "turn"
    assert rows[0]["meta"] == {"role": "user"}


def test_edges_link_neurons(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    a = store.remember("first")
    b = store.remember("second", link_to=[a])
    edge = store.conn.execute(
        "SELECT weight FROM edge WHERE src_id = ? AND dst_id = ?", (b, a)
    ).fetchone()
    assert edge is not None
    assert edge["weight"] >= 1.0


def test_keyword_recall_without_embeddings(tmp_path: Path) -> None:
    """When the embedding stack is unavailable, recall degrades to a
    query-relevant keyword search rather than plain recency."""
    store = MemoryStore(tmp_path)

    def boom() -> None:
        raise ImportError("no embeddings installed")

    store._ensure_vector_store = boom  # type: ignore[method-assign]

    store.remember("User loves strong black coffee in the morning", kind="fact")
    store.remember("The weather is cold today", kind="turn")
    store.remember("User prefers Python over JavaScript", kind="preference")

    coffee = store.recall("what coffee does the user like", k=3)
    assert coffee and "coffee" in coffee[0]["content"].lower()

    py = store.recall("python language preference", k=3)
    assert py and "python" in py[0]["content"].lower()


def test_keyword_recall_no_tokens_falls_back_to_recent(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store._ensure_vector_store = lambda: (_ for _ in ()).throw(ImportError())  # type: ignore[method-assign]
    store.remember("first", kind="turn")
    store.remember("second", kind="turn")
    # Query with no usable (>=3 char) tokens → recency fallback.
    hits = store.recall("a", k=5)
    assert len(hits) == 2


def test_router_chooses_local_for_private(tmp_path: Path, monkeypatch) -> None:
    from mira.config import settings
    from mira.llm.router import LLMRouter

    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    monkeypatch.setattr(settings, "provider", "auto")
    router = LLMRouter()
    assert router.choose("my password is hunter2") == "local"
    assert router.choose("Мой пароль 12345") == "local"


def test_router_chooses_local_without_key_or_clis(monkeypatch) -> None:
    from mira.config import settings
    from mira.llm.router import LLMRouter
    from mira.llm.subscription import ClaudeCodeProvider, CodexProvider

    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "provider", "auto")
    monkeypatch.setattr(ClaudeCodeProvider, "available", staticmethod(lambda *_a: False))
    monkeypatch.setattr(CodexProvider, "available", staticmethod(lambda *_a: False))
    router = LLMRouter()
    assert router.choose("Write me a long essay about quantum computing.") == "local"
