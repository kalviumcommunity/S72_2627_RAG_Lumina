"""Background job dispatch: arq (Redis) when available, otherwise in-process asyncio tasks.

Docker deployments run the arq worker (app/workers/worker.py). Native/dev runs without Redis fall
back to running the same task functions inside the API process (INGEST_INLINE=true forces this).
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_pool: Any = None
_pool_checked = False
_inline_tasks: set[asyncio.Task[Any]] = set()


async def _get_pool() -> Any:
    global _pool, _pool_checked
    if _pool_checked:
        return _pool
    _pool_checked = True
    settings = get_settings()
    if settings.ingest_inline:
        return None
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        _pool = await asyncio.wait_for(create_pool(RedisSettings.from_dsn(settings.redis_url)), timeout=2)
    except Exception as exc:
        log.info("job_queue_inline_mode", reason=type(exc).__name__)
        _pool = None
    return _pool


async def enqueue(name: str, *args: Any) -> str:
    """Queue a task from app.workers.tasks; returns "queued" or "inline"."""
    pool = await _get_pool()
    if pool is not None:
        await pool.enqueue_job(name, *args)
        return "queued"
    from app.workers import tasks

    func = getattr(tasks, name)
    task = asyncio.create_task(func({}, *args))
    _inline_tasks.add(task)
    task.add_done_callback(_inline_tasks.discard)
    return "inline"


async def drain_inline(max_wait: float = 120.0) -> None:
    """Wait for in-process jobs (tests and the sample loader use this)."""
    if _inline_tasks:
        await asyncio.wait_for(asyncio.gather(*list(_inline_tasks), return_exceptions=True), max_wait)


def reset() -> None:
    global _pool, _pool_checked
    _pool, _pool_checked = None, False
