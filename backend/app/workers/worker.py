"""arq worker settings: `arq app.workers.worker.WorkerSettings`."""

from __future__ import annotations

from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import dispose_engine, init_engine
from app.services.registry import get_services
from app.workers.tasks import ingest_document, post_approval, review_date_reminders


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    init_engine()
    services = get_services()
    services.embedder.embed_query("warmup")


async def shutdown(ctx: dict[str, Any]) -> None:
    await dispose_engine()


class WorkerSettings:
    functions: ClassVar[list[Any]] = [ingest_document, post_approval, review_date_reminders]
    cron_jobs: ClassVar[list[Any]] = [cron(review_date_reminders, hour={7}, minute={0})]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 2
    job_timeout = 900
