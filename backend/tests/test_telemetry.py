from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app import telemetry
from .conftest import new_session, signup


async def test_http_trace_uses_route_template_and_never_records_content_or_token(client, monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "tracer", provider.get_tracer("privacy-test"))
    api = await signup(client)
    session = await new_session(api, capture="NONE", title="PRIVATE_TITLE_NEVER_IN_TRACES")
    sid = session["session_id"]
    await api.get(f"/v1/sessions/{sid}?secret=PRIVATE_QUERY_NEVER_IN_TRACES")
    spans = exporter.get_finished_spans()
    traced = [s for s in spans if s.name == "GET /v1/sessions/{session_id}"]
    assert traced
    serialized = str([(s.name, dict(s.attributes), s.events) for s in spans])
    for secret in (sid, "PRIVATE_TITLE_NEVER_IN_TRACES", "PRIVATE_QUERY_NEVER_IN_TRACES", api.tokens["access_token"]):
        assert secret not in serialized
    assert set(traced[0].attributes) == {"http.request.method", "http.route", "http.response.status_code"}
    provider.shutdown()
