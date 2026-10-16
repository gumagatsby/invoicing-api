"""Tracing with OpenTelemetry. Off unless APP_OTEL_ENDPOINT is set, so tests and CI need no collector."""
from fastapi import FastAPI

from .config import settings
from .db import engine


def setup(app: FastAPI, service: str = "invoicing-api") -> None:
    endpoint = settings().otel_endpoint
    if not endpoint:
        return
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/metrics,/health")
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
