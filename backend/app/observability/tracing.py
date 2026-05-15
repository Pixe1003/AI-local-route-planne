"""Optional OpenTelemetry tracing setup."""

from __future__ import annotations

from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


tracer = trace.get_tracer(__name__)
_configured_endpoint: str | None = None
_instrumented_apps: set[int] = set()


def configure_otel(service_name: str = "airoute-agent", endpoint: str | None = None) -> bool:
    """Configure OTLP tracing when an endpoint is provided."""
    global tracer, _configured_endpoint

    if not endpoint:
        return False
    if _configured_endpoint == endpoint:
        return True

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer(__name__)
    _configured_endpoint = endpoint
    return True


def instrument_fastapi_app(app: Any) -> bool:
    """Attach FastAPI tracing once OpenTelemetry has been configured."""
    if not _configured_endpoint:
        return False

    app_id = id(app)
    if app_id in _instrumented_apps:
        return True

    FastAPIInstrumentor.instrument_app(app)
    _instrumented_apps.add(app_id)
    return True
