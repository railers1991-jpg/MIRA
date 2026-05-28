"""Background task that runs distill + decay + prune on an interval.

Lives inside the FastAPI lifespan. Disabled when `distill_interval_s == 0`
or when no `ANTHROPIC_API_KEY` is configured (distillation needs Claude).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from .config import settings
from .learning import distill_recent_turns
from .memory.store import MemoryStore

log = logging.getLogger(__name__)

PROTECTED_KINDS = ("fact", "preference", "skill")


@asynccontextmanager
async def scheduler(memory: MemoryStore) -> AsyncIterator[None]:
    """Spawn the background loop for the duration of the surrounding scope."""
    interval = settings.distill_interval_s
    if interval <= 0:
        log.info("scheduler disabled (MIRA_DISTILL_INTERVAL_S=0)")
        yield
        return

    task = asyncio.create_task(_run(memory, interval), name="mira-scheduler")
    log.info("scheduler started: every %ds", interval)
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def _run(memory: MemoryStore, interval: int) -> None:
    while True:
        try:
            await asyncio.sleep(interval)
            await _tick(memory)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("scheduler tick failed; continuing")


async def _tick(memory: MemoryStore) -> None:
    if settings.anthropic_api_key:
        result = await distill_recent_turns(memory, limit=settings.distill_limit)
        log.info(
            "scheduler distilled: +%d new, %d dupes", result.added, result.skipped_duplicates
        )
    else:
        log.info("scheduler skipped distill: no ANTHROPIC_API_KEY")

    updated = memory.apply_decay(half_life_days=settings.decay_half_life_days)
    pruned = memory.prune(
        min_strength=settings.decay_prune_below, keep_kinds=PROTECTED_KINDS
    )
    log.info("scheduler decay: updated=%d pruned=%d", updated, pruned)
