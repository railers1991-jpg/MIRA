"""Neuron memory: SQLite for episodic + graph edges, Chroma for embeddings.

A "neuron" is one piece of memory (a chat turn, a learned fact, a preference).
Neurons connect by edges with weights that strengthen on co-recall — a
simple Hebbian rule. Recall combines vector similarity and graph traversal.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS neuron (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    meta TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    last_used_at REAL NOT NULL,
    strength REAL NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS idx_neuron_kind ON neuron(kind);
CREATE INDEX IF NOT EXISTS idx_neuron_created ON neuron(created_at DESC);

CREATE TABLE IF NOT EXISTS edge (
    src_id TEXT NOT NULL,
    dst_id TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'co_recall',
    weight REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (src_id, dst_id, kind),
    FOREIGN KEY (src_id) REFERENCES neuron(id) ON DELETE CASCADE,
    FOREIGN KEY (dst_id) REFERENCES neuron(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_edge_src ON edge(src_id);
"""


class MemoryStore:
    """Persistent neuron memory with vector + graph recall."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.db_path = data_dir / "neurons.db"
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._embedder = None
        self._chroma = None

    # ---- embeddings (lazy-loaded; heavy import) ----

    def _ensure_vector_store(self) -> None:
        if self._chroma is not None:
            return
        import chromadb
        from sentence_transformers import SentenceTransformer

        from ..config import settings

        self._embedder = SentenceTransformer(settings.embedding_model)
        client = chromadb.PersistentClient(path=str(self.data_dir / "chroma"))
        self._chroma = client.get_or_create_collection("neurons")

    def _embed(self, text: str) -> list[float]:
        self._ensure_vector_store()
        assert self._embedder is not None
        return self._embedder.encode(text, normalize_embeddings=True).tolist()

    # ---- writes ----

    def remember(
        self,
        content: str,
        kind: str = "turn",
        meta: dict[str, Any] | None = None,
        link_to: list[str] | None = None,
    ) -> str:
        nid = uuid.uuid4().hex
        now = time.time()
        self.conn.execute(
            "INSERT INTO neuron(id, kind, content, meta, created_at, last_used_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (nid, kind, content, json.dumps(meta or {}), now, now),
        )
        if link_to:
            self.conn.executemany(
                "INSERT OR IGNORE INTO edge(src_id, dst_id, kind, weight) "
                "VALUES (?, ?, 'co_recall', 1.0)",
                [(nid, dst) for dst in link_to],
            )
            self.conn.executemany(
                "UPDATE edge SET weight = weight + 0.5 "
                "WHERE src_id = ? AND dst_id = ? AND kind = 'co_recall'",
                [(nid, dst) for dst in link_to],
            )
        self.conn.commit()

        try:
            self._ensure_vector_store()
            assert self._chroma is not None
            self._chroma.add(ids=[nid], documents=[content], embeddings=[self._embed(content)])
        except Exception:
            log.exception("vector store add failed; neuron stored without embedding")

        return nid

    # ---- reads ----

    def recall(self, query: str, k: int = 8) -> list[dict]:
        """Top-k by embedding similarity, then bump strength and edge weights."""
        try:
            self._ensure_vector_store()
            assert self._chroma is not None
            res = self._chroma.query(query_embeddings=[self._embed(query)], n_results=k)
            ids: list[str] = res.get("ids", [[]])[0]
        except Exception:
            log.exception("vector recall failed; falling back to recent")
            return self.recent(k)

        if not ids:
            return []

        placeholders = ",".join("?" * len(ids))
        rows = self.conn.execute(
            f"SELECT * FROM neuron WHERE id IN ({placeholders})", ids
        ).fetchall()
        now = time.time()
        self.conn.executemany(
            "UPDATE neuron SET last_used_at = ?, strength = strength + 0.1 WHERE id = ?",
            [(now, nid) for nid in ids],
        )
        self.conn.commit()
        by_id = {r["id"]: r for r in rows}
        return [self._row_to_dict(by_id[nid]) for nid in ids if nid in by_id]

    def recent(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM neuron ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ---- learning ----

    def feedback(self, neuron_id: str, signal: str) -> bool:
        """Reinforce ('positive') or weaken ('negative') a single neuron.

        Returns True if the neuron existed.
        """
        delta = 1.0 if signal == "positive" else -1.0 if signal == "negative" else 0.0
        if delta == 0.0:
            return False
        cur = self.conn.execute(
            "UPDATE neuron SET strength = MAX(0.0, strength + ?) WHERE id = ?",
            (delta, neuron_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def apply_decay(self, half_life_days: float = 30.0) -> int:
        """Exponentially decay strength for all neurons.

        After `half_life_days` of accrued time since `last_used_at`, a
        neuron's strength halves. Returns the number of neurons updated.
        """
        if half_life_days <= 0:
            return 0
        rows = self.conn.execute(
            "SELECT id, last_used_at, strength FROM neuron"
        ).fetchall()
        now = time.time()
        decay_per_sec = 0.5 ** (1.0 / (half_life_days * 86400.0))
        updates: list[tuple[float, str]] = []
        for r in rows:
            age = max(0.0, now - r["last_used_at"])
            new_strength = max(0.0, r["strength"] * (decay_per_sec**age))
            updates.append((new_strength, r["id"]))
        self.conn.executemany("UPDATE neuron SET strength = ? WHERE id = ?", updates)
        self.conn.commit()
        return len(updates)

    def prune(self, min_strength: float = 0.05, keep_kinds: tuple[str, ...] = ()) -> int:
        """Delete neurons whose strength fell below `min_strength`.

        `keep_kinds` is an opt-out list — facts/preferences typically
        shouldn't be pruned even when weak.
        """
        placeholders = ",".join("?" * len(keep_kinds)) or "''"
        cur = self.conn.execute(
            f"DELETE FROM neuron WHERE strength < ? AND kind NOT IN ({placeholders})",
            (min_strength, *keep_kinds),
        )
        self.conn.commit()
        return cur.rowcount

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "kind": row["kind"],
            "content": row["content"],
            "meta": json.loads(row["meta"]),
            "created_at": row["created_at"],
            "last_used_at": row["last_used_at"],
            "strength": row["strength"],
        }
