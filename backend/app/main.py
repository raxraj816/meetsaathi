"""MeetSaathi API application."""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .api import auth, memory, packs, public_share, realtime, sessions
from .config import get_settings
from .db import db
from .errors import ApiError, correlation_id_var, new_correlation_id
from .intelligence.reasoner import get_reasoner
from .memory.embeddings import get_embedder
from .speech.adapters import get_asr, get_diarizer
from . import telemetry
from .openapi import install_exact_integer_bounds


class RedactingFilter(logging.Filter):
    """Default logs carry metadata only - never transcript text, notes or audio (INT-080, LC-042)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get() or "-"
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s cid=%(correlation_id)s %(message)s"))
    root = logging.getLogger("meetsaathi")
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    root.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    telemetry.configure()
    await db.connect()
    stop = asyncio.Event()
    task = None
    if get_settings().run_inline_worker:
        from .workers.runner import loop

        task = asyncio.create_task(loop(stop))
    try:
        yield
    finally:
        stop.set()
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        await db.close()
        telemetry.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="MeetSaathi API", version="1.0.0", lifespan=lifespan,
                  description="One companion, four contexts. See packages/contracts/openapi_v1.yaml.")

    @app.middleware("http")
    async def correlation(request: Request, call_next):
        cid = request.headers.get("X-Correlation-Id") or new_correlation_id()
        token = correlation_id_var.set(cid[:64])
        started = time.monotonic()
        try:
            with telemetry.tracer.start_as_current_span("HTTP request", record_exception=False, set_status_on_exception=False) as span:
                response = await call_next(request)
                route = getattr(request.scope.get("route"), "path", "unmatched")
                attrs = {"http.request.method": request.method, "http.route": route, "http.response.status_code": response.status_code}
                span.update_name(f"{request.method} {route}")
                span.set_attributes(attrs)
                telemetry.request_duration.record(time.monotonic() - started, attrs)
        finally:
            correlation_id_var.reset(token)
        response.headers["X-Correlation-Id"] = cid[:64]
        response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
        return response

    @app.exception_handler(ApiError)
    async def api_error(_request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content=exc.body())

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        fields = [".".join(str(p) for p in e.get("loc", [])) for e in exc.errors()]
        err = ApiError(422, "VALIDATION_FAILED", "Some fields are missing or invalid.", details={"fields": fields})
        return JSONResponse(status_code=422, content=err.body())

    @app.exception_handler(Exception)
    async def unhandled(_request: Request, exc: Exception):
        logging.getLogger("meetsaathi.api").error("unhandled %s", type(exc).__name__)
        err = ApiError(500, "INTERNAL", "Something went wrong. Capture controls still work; try again.", retryable=True)
        return JSONResponse(status_code=500, content=err.body())

    @app.get("/v1/health")
    async def health():
        s = get_settings()
        return {"status": "ok", "region": s.processing_region, "policy_version": s.policy_version,
                "processing_disclosure_version": s.processing_disclosure_version,
                "capabilities": {"asr": get_asr().available(), "diarization": get_diarizer().available(),
                                 "reasoner": get_reasoner().available(), "embeddings": get_embedder().available()}}

    @app.get("/v1/ready", include_in_schema=False)
    async def ready():
        try:
            async with db.system_tx() as conn:
                await asyncio.wait_for(conn.fetchval("SELECT 1"), timeout=2)
        except Exception:
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return {"status": "ready"}

    for r in (auth.router, sessions.router, realtime.router, memory.router, packs.router, public_share.router):
        app.include_router(r)
    install_exact_integer_bounds(app, (auth, sessions, realtime, memory, packs))
    return app


app = create_app()
