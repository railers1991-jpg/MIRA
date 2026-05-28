from __future__ import annotations

from pathlib import Path

from mira.memory.store import MemoryStore


def test_stats_counts_by_kind(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.remember("a turn", kind="turn")
    store.remember("another turn", kind="turn")
    store.remember("a fact", kind="fact")
    stats = store.stats()
    assert stats["neurons_total"] == 3
    assert stats["neurons_by_kind"] == {"turn": 2, "fact": 1}
    assert stats["edges_total"] == 0
    assert stats["avg_strength"] > 0


def test_stats_on_empty_store(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    stats = store.stats()
    assert stats["neurons_total"] == 0
    assert stats["neurons_by_kind"] == {}
    assert stats["edges_total"] == 0
    assert stats["avg_strength"] == 0
