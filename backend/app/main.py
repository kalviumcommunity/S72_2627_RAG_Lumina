"""FastAPI application factory."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app import __version__
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import RequestContextMiddleware, configure_logging, get_logger
from app.core.telemetry import setup_telemetry
from app.db.session import dispose_engine, get_sessionmaker, init_engine
from app.services.registry import get_services, load_corpus_vocabulary

log = get_logger(__name__)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_docs = scope.get("path", "").startswith(("/docs", "/redoc"))

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                extra = {
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"DENY",
                    b"referrer-policy": b"no-referrer",
                    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
                    b"cross-origin-opener-policy": b"same-origin",
                }
                if not is_docs:
                    extra[b"content-security-policy"] = b"default-src 'none'; frame-ancestors 'none'"
                if self.hsts:
                    extra[b"strict-transport-security"] = b"max-age=63072000; includeSubDomains"
                present = {k.lower() for k, _ in headers}
                headers += [(k, v) for k, v in extra.items() if k not in present]
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        init_engine()
        services = get_services()
        try:
            async with get_sessionmaker()() as session:
                words = await load_corpus_vocabulary(session)
            log.info("corpus_vocabulary_loaded", words=words)
        except Exception as exc:
            log.warning("corpus_vocabulary_unavailable", error_type=type(exc).__name__)
        if settings.warmup_models:
            await asyncio.to_thread(services.warmup)
        log.info("api_started", version=__version__, env=settings.app_env, model=services.model_id)
        yield
        await dispose_engine()

    app = FastAPI(
        title="Lumina API",
        version=__version__,
        description=(
            "Source-backed answers from approved institutional documents. Lumina retrieves and displays "
            "approved documents; it does not provide diagnoses or patient-specific treatment or dosing "
            "recommendations."
        ),
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_prod else None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    install_error_handlers(app)

    from app.api.v1.router import api_router

    app.include_router(api_router, prefix="/api/v1")
    from app.web import mount_web

    if mount_web(app, settings.web_dist_dir):
        log.info("web_app_mounted", path=str(settings.web_dist_dir))

    # Middleware (last added = outermost).
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        same_site="lax",
        https_only=settings.is_prod,
        max_age=600,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_prod)
    app.add_middleware(RequestContextMiddleware)
    setup_telemetry(app, settings)
    return app


app = create_app()
