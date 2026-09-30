"""Structured JSON logging with request IDs and a last-line PII scrubber.

Raw questions are never passed to the logger (the orchestrator only logs redacted text), but a
regex scrubber runs on every event as defence in depth for identifiers with a fixed shape
(phone numbers, 12/14-digit IDs, MRN/UHID labels).
"""

from __future__ import annotations

import logging
import re
import sys
import uuid
from contextvars import ContextVar
from typing import Any

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_SCRUB_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)"), "<PHONE>"),
    (re.compile(r"(?<!\d)\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)"), "<ABHA>"),
    (re.compile(r"(?<!\d)[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?!\d)"), "<ID_NUMBER>"),
    (
        re.compile(r"\b(?:UHID|MRN|IP\s?No\.?|CR\s?No\.?)\s*[:#-]?\s*[A-Z0-9/-]{4,20}", re.IGNORECASE),
        "<MRN>",
    ),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "<EMAIL>"),
]


def scrub(value: str) -> str:
    for pattern, replacement in _SCRUB_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def _scrub_processor(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            event_dict[key] = scrub(value)
    return event_dict


def _add_request_id(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    rid = request_id_var.get()
    if rid:
        event_dict.setdefault("request_id", rid)
    return event_dict


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _add_request_id,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _scrub_processor,
    ]
    renderer: Any = structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer(colors=False)
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    formatter = structlog.stdlib.ProcessorFormatter(foreign_pre_chain=shared, processor=renderer)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Uvicorn's access log prints full URLs (query strings may contain questions): replaced by
    # our own access middleware, which logs the path only.
    logging.getLogger("uvicorn.access").disabled = True
    for noisy in ("httpx", "httpcore", "sentence_transformers", "urllib3", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    for chatty in ("huggingface_hub", "transformers", "filelock", "presidio-analyzer", "presidio-anonymizer"):
        logging.getLogger(chatty).setLevel(logging.ERROR)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]


class RequestContextMiddleware:
    """Assigns a request ID and emits one access-log line per request (path only, no query)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.log = get_logger("protocite.access")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        import time

        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode()[:64]
        rid = incoming if re.fullmatch(r"[A-Za-z0-9-]{8,64}", incoming or "") else uuid.uuid4().hex
        token = request_id_var.set(rid)
        status_holder = {"status": 500}
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", rid.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            self.log.info(
                "http_request",
                method=scope.get("method"),
                path=scope.get("path"),
                status=status_holder["status"],
                duration_ms=round((time.perf_counter() - start) * 1000, 1),
            )
            request_id_var.reset(token)
