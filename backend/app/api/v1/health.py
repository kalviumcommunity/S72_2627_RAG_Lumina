from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from app import __version__
from app.api.deps import DbSession, ServicesDep
from app.services import jobs

router = APIRouter(tags=["health"])

_llm_cache: dict[str, Any] = {"at": 0.0, "value": None}


@router.get("/health")
async def health(session: DbSession, services: ServicesDep) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    try:
        version = (
            await session.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
        ).scalar_one_or_none()
        chunks: int = (await session.execute(text("SELECT count(*) FROM chunks"))).scalar_one()
        checks["db"] = {"ok": version is not None, "pgvector": version, "chunks": chunks}
    except Exception as exc:
        checks["db"] = {"ok": False, "error": type(exc).__name__}

    pool = await jobs._get_pool()
    checks["jobs"] = {"ok": True, "mode": "arq+redis" if pool is not None else "inline"}

    if services.llm is None:
        checks["llm"] = {"ok": True, "provider": "none", "detail": "deterministic extractive mode"}
    else:
        now = time.monotonic()
        if _llm_cache["value"] is None or now - _llm_cache["at"] > 60:
            try:
                ok, detail = await asyncio.wait_for(services.llm.health(), timeout=8)
            except TimeoutError:
                ok, detail = False, "timeout"
            _llm_cache.update(
                at=now,
                value={
                    "ok": ok,
                    "provider": services.llm.name,
                    "model": services.llm.model_id,
                    "detail": detail,
                },
            )
        checks["llm"] = _llm_cache["value"]

    checks["models"] = {
        "ok": True,
        "embedding": services.embedder.model_id,
        "reranker": services.reranker.model_id,
        "nli": bool(services.nli),
        "pii_engine": services.redactor.engine,
    }
    status = "ok" if checks["db"]["ok"] and checks["llm"]["ok"] else ("degraded" if checks["db"]["ok"] else "down")
    return {"status": status, "version": __version__, "checks": checks}
