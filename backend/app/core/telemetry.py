"""Optional OpenTelemetry tracing (enabled when OTEL_EXPORTER_OTLP_ENDPOINT is set)."""

from __future__ import annotations

from fastapi import FastAPI

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger(__name__)


def setup_telemetry(app: FastAPI, settings: Settings) -> bool:
    if not settings.otel_exporter_otlp_endpoint:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": "lumina-api"}))
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint.rstrip("/") + "/v1/traces")
            )
        )
        trace.set_tracer_provider(provider)
        log.info("telemetry_enabled")
        return True
    except Exception as exc:  # pragma: no cover - optional
        log.warning("telemetry_disabled", error_type=type(exc).__name__)
        return False
