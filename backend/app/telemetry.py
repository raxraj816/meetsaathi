"""Deliberate metadata-only telemetry: no bodies, queries, bearer tokens or raw URL paths.

Generic HTTP/SDK auto-instrumentation is deliberately absent because transcripts and model prompts
must not reach tracing vendors. An OTLP collector receives bounded route/kind dimensions only.
"""
from __future__ import annotations

from opentelemetry import metrics, trace

from .config import get_settings

_configured = False
tracer = trace.get_tracer("meetsaathi")
meter = metrics.get_meter("meetsaathi")
request_duration = meter.create_histogram("http.server.request.duration", unit="s")
job_duration = meter.create_histogram("meetsaathi.job.duration", unit="s")
job_count = meter.create_counter("meetsaathi.job.count")


def configure() -> None:
    global _configured
    s = get_settings()
    if _configured or not s.telemetry_enabled:
        return
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": s.telemetry_service_name, "deployment.environment.name": s.env})
    endpoint = s.telemetry_otlp_endpoint.rstrip("/")
    traces = TracerProvider(resource=resource)
    traces.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint + "/v1/traces", timeout=5)))
    trace.set_tracer_provider(traces)
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint + "/v1/metrics", timeout=5))]))
    _configured = True


def shutdown() -> None:
    if not _configured:
        return
    for provider in (trace.get_tracer_provider(), metrics.get_meter_provider()):
        provider.shutdown()
