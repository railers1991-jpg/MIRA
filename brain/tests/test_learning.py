from __future__ import annotations

import time
from pathlib import Path

from mira.learning.distill import _has_similar_fact, _parse_items
from mira.memory.store import MemoryStore


def test_feedback_strength(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    nid = store.remember("hello", kind="fact")
    assert store.feedback(nid, "positive") is True
    rows = store.recent(5)
    assert rows[0]["strength"] > 1.0
    assert store.feedback(nid, "negative") is True
    assert store.feedback("nonexistent", "positive") is False


def test_feedback_invalid_signal_is_noop(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    nid = store.remember("hello", kind="fact")
    assert store.feedback(nid, "bogus") is False


def test_decay_halves_strength_at_half_life(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    nid = store.remember("aged", kind="fact")
    # Backdate last_used_at by one day; with half_life=1d the strength halves.
    one_day_ago = time.time() - 86400
    store.conn.execute(
        "UPDATE neuron SET last_used_at = ?, strength = 1.0 WHERE id = ?",
        (one_day_ago, nid),
    )
    store.conn.commit()
    store.apply_decay(half_life_days=1.0)
    row = store.recent(5)[0]
    assert 0.4 < row["strength"] < 0.6


def test_prune_keeps_protected_kinds(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    a = store.remember("weak turn", kind="turn")
    b = store.remember("weak fact", kind="fact")
    store.conn.execute("UPDATE neuron SET strength = 0.0 WHERE id IN (?, ?)", (a, b))
    store.conn.commit()
    pruned = store.prune(min_strength=0.5, keep_kinds=("fact",))
    assert pruned == 1
    remaining_kinds = {r["kind"] for r in store.recent(10)}
    assert "fact" in remaining_kinds
    assert "turn" not in remaining_kinds


def test_distill_parse_items_strips_fences() -> None:
    raw = '```json\n[{"kind": "fact", "content": "User likes tea"}]\n```'
    items = _parse_items(raw)
    assert items == [{"kind": "fact", "content": "User likes tea"}]


def test_distill_dedupes_exact_match(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.remember("User likes tea", kind="fact", meta={"source": "manual"})
    assert _has_similar_fact(store, "User likes tea") is True
    assert _has_similar_fact(store, "User likes coffee") is False