from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from mira.config import settings
from mira.memory.store import MemoryStore
from mira.scheduler import _tick, scheduler


async def test_tick_runs_decay_without_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "decay_half_life_days", 30.0)
    monkeypatch.setattr(settings, "decay_prune_below", 0.0)
    store = MemoryStore(tmp_path)
    store.remember("user turn", kind="turn")
    # Without an API key the tick should still apply decay and not crash.
    await _tick(store)


async def test_scheduler_yields_when_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "distill_interval_s", 0)
    store = MemoryStore(tmp_path)
    async with scheduler(store):
        await asyncio.sleep(0)  # let the loop run
    # No exception means success.


@pytest.mark.asyncio
async def test_scheduler_starts_and_cancels(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "distill_interval_s", 3600)
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    store = MemoryStore(tmp_path)
    async with scheduler(store):
        # The background task is sleeping; entering and exiting the
        # context proves start + clean cancellation.
        await asyncio.sleep(0.05)
