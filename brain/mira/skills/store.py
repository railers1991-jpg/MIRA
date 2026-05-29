"""Persistent skill catalogue.

A skill is a named procedure MIRA can re-execute. It's generated either
explicitly via the forge endpoint or autonomously after successful
conversations. Skills are exposed to Claude as tools named
`skill__<name>`; calling one routes to the SkillExecutor.

Each skill carries lessons — short strings MIRA writes after each
invocation to refine itself over time.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS skill (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    when_to_use TEXT NOT NULL DEFAULT '',
    parameters TEXT NOT NULL DEFAULT '{"type":"object","properties":{}}',
    steps TEXT NOT NULL DEFAULT '[]',
    returns TEXT NOT NULL DEFAULT '',
    lessons TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL,
    last_used_at REAL NOT NULL,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_skill_last_used ON skill(last_used_at DESC);
"""


class SkillStore:
    def __init__(self, data_dir: Path) -> None:
        self.db_path = data_dir / "neurons.db"
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---- validation ----

    @staticmethod
    def validate(definition: dict) -> list[str]:
        errors: list[str] = []
        name = definition.get("name", "")
        if not isinstance(name, str) or not NAME_RE.match(name):
            errors.append("name must be snake_case, 2-64 chars, [a-z0-9_]")
        if not isinstance(definition.get("description"), str) or not definition.get("description"):
            errors.append("description is required")
        steps = definition.get("steps", [])
        if not isinstance(steps, list) or not steps:
            errors.append("steps must be a non-empty list")
        else:
            for i, step in enumerate(steps):
                if not isinstance(step, dict):
                    errors.append(f"step {i}: must be an object")
                    continue
                t = step.get("type")
                if t not in {"prompt", "tool"}:
                    errors.append(f"step {i}: type must be 'prompt' or 'tool'")
                if t == "prompt" and not step.get("prompt"):
                    errors.append(f"step {i}: prompt steps need a 'prompt' string")
                if t == "tool" and not step.get("tool"):
                    errors.append(f"step {i}: tool steps need a 'tool' name")
        params = definition.get("parameters", {})
        if not isinstance(params, dict) or params.get("type") != "object":
            errors.append("parameters must be a JSON Schema object")
        return errors

    # ---- writes ----

    def upsert(self, definition: dict) -> None:
        errors = self.validate(definition)
        if errors:
            raise ValueError("invalid skill: " + "; ".join(errors))
        now = time.time()
        existing = self.get(definition["name"])
        self.conn.execute(
            """INSERT INTO skill(name, description, when_to_use, parameters, steps,
                                  returns, lessons, created_at, last_used_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   description = excluded.description,
                   when_to_use = excluded.when_to_use,
                   parameters = excluded.parameters,
                   steps = excluded.steps,
                   returns = excluded.returns,
                   last_used_at = excluded.last_used_at""",
            (
                definition["name"],
                definition.get("description", ""),
                definition.get("when_to_use", ""),
                json.dumps(definition.get("parameters", {"type": "object", "properties": {}})),
                json.dumps(definition.get("steps", [])),
                definition.get("returns", "{{_result}}"),
                json.dumps(existing["lessons"] if existing else definition.get("lessons", [])),
                now,
                now,
            ),
        )
        self.conn.commit()

    def delete(self, name: str) -> bool:
        cur = self.conn.execute("DELETE FROM skill WHERE name = ?", (name,))
        self.conn.commit()
        return cur.rowcount > 0

    def add_lesson(self, name: str, lesson: str, max_lessons: int = 20) -> bool:
        existing = self.get(name)
        if not existing:
            return False
        lessons = existing["lessons"]
        lesson = lesson.strip()
        if not lesson or lesson in lessons:
            return False
        lessons.append(lesson)
        if len(lessons) > max_lessons:
            lessons = lessons[-max_lessons:]
        self.conn.execute(
            "UPDATE skill SET lessons = ? WHERE name = ?",
            (json.dumps(lessons), name),
        )
        self.conn.commit()
        return True

    def record_success(self, name: str) -> None:
        self.conn.execute(
            "UPDATE skill SET success_count = success_count + 1, last_used_at = ? "
            "WHERE name = ?",
            (time.time(), name),
        )
        self.conn.commit()

    def record_failure(self, name: str) -> None:
        self.conn.execute(
            "UPDATE skill SET failure_count = failure_count + 1, last_used_at = ? "
            "WHERE name = ?",
            (time.time(), name),
        )
        self.conn.commit()

    # ---- reads ----

    def get(self, name: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM skill WHERE name = ?", (name,)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_all(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM skill ORDER BY last_used_at DESC"
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def as_tools(self) -> list[dict]:
        """Anthropic-shaped tool schemas for every skill."""
        return [
            {
                "name": f"skill__{r['name']}",
                "description": self._tool_description(r),
                "input_schema": json.loads(r["parameters"]),
            }
            for r in self.conn.execute("SELECT * FROM skill").fetchall()
        ]

    @staticmethod
    def _tool_description(row: sqlite3.Row) -> str:
        parts = [row["description"]]
        if row["when_to_use"]:
            parts.append(f"When to use: {row['when_to_use']}")
        lessons = json.loads(row["lessons"])
        if lessons:
            joined = "; ".join(lessons[-3:])
            parts.append(f"Past lessons: {joined}")
        return "\n".join(parts)[:1024]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        return {
            "name": row["name"],
            "description": row["description"],
            "when_to_use": row["when_to_use"],
            "parameters": json.loads(row["parameters"]),
            "steps": json.loads(row["steps"]),
            "returns": row["returns"],
            "lessons": json.loads(row["lessons"]),
            "created_at": row["created_at"],
            "last_used_at": row["last_used_at"],
            "success_count": row["success_count"],
            "failure_count": row["failure_count"],
        }
