import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.api.v1.router import router
from app.core.config import get_settings
from app.core.trace import TraceIdMiddleware
from app.db.session import get_db

settings = get_settings()
CORS_ORIGINS = settings.cors_origin_list
_cors_problems = settings.cors_origin_problems()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Print the resolved allowed origins so deployment logs prove what loaded.

    Origins are public values, not secrets. Without this there is no way to tell
    from outside the process whether a platform environment variable actually
    reached it - which is exactly the question that arises when a browser
    reports an opaque CORS failure.
    """
    # uvicorn configures only its own loggers and leaves the root logger without
    # a handler, so application log records are discarded by default. Without
    # this the startup proof below never reaches the platform log, which is the
    # one place it is needed.
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=getattr(logging, str(settings.log_level).upper(), logging.INFO),
            format="%(levelname)s:     %(name)s - %(message)s",
        )
    log = logging.getLogger("pios.cors")
    log.info("CORS allowed origins resolved: %s", CORS_ORIGINS or "(none)")
    for bad in _cors_problems:
        log.error("CORS origin ignored, must start with http:// or https:// -> %r", bad)
    if not CORS_ORIGINS:
        log.error("No usable CORS origins configured; browser requests will be blocked. Set PIOS_CORS_ORIGINS.")
    yield


app = FastAPI(
    title="PIOS MVP API",
    version="1.4.0",
    description="Pharmacy Intelligence Operating System - Sprint 13 institutional pilot execution, identity binding, provenance and outcome reporting",
    lifespan=lifespan,
)

# Starlette's add_middleware prepends, so the LAST call is the outermost layer.
# TraceIdMiddleware is added first so CORSMiddleware ends up outside it: every
# response, including the 500 that TraceIdMiddleware synthesises for an
# unhandled exception, then passes back out through the CORS layer and carries
# Access-Control-Allow-Origin. Without this a backend fault reaches the browser
# as an opaque same-origin failure instead of its real status code.
app.add_middleware(TraceIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Trace-ID"],
    expose_headers=["X-Trace-ID", "Content-Disposition"],
)


@app.get("/__diagnostics/cors", tags=["Platform"])
def cors_diagnostics():
    """Public, secret-free proof of the CORS configuration actually in effect.

    Returns only the resolved origin allowlist and the header/method policy -
    all values a browser can already observe from response headers - so it
    exposes nothing new while making a misconfigured deployment self-evident.
    """
    return {
        "allowed_origins": CORS_ORIGINS,
        "rejected_entries": _cors_problems,
        "allow_credentials": True,
        "allow_methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        "allow_headers": ["Authorization", "Content-Type", "Idempotency-Key", "X-Trace-ID"],
        "raw_configured_value_present": bool(settings.cors_origins.strip()),
    }
app.include_router(router, prefix=settings.api_prefix)


@app.get("/health", tags=["Platform"])
def health():
    return {"status": "ok", "service": "pios-mvp-backend", "version": "1.4.0"}


@app.get("/ready", tags=["Platform"])
def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "reachable", "version": "1.4.0", "object_storage_backend": settings.object_storage_backend, "auth_mode": settings.auth_mode}


@app.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
def metrics(db: Session = Depends(get_db)):
    reachable = 1
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        reachable = 0
    lines = [
        "# HELP pios_up PIOS API process availability",
        "# TYPE pios_up gauge",
        "pios_up 1",
        "# HELP pios_database_reachable Database connectivity state",
        "# TYPE pios_database_reachable gauge",
        f"pios_database_reachable {reachable}",
        "# HELP pios_release_info Immutable release metadata",
        "# TYPE pios_release_info gauge",
        f'pios_release_info{{version="1.4.0",environment="{settings.env}"}} 1',
    ]
    return "\n".join(lines) + "\n"


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=422, content={"code": "VALIDATION_ERROR", "message": str(exc), "trace_id": getattr(request.state, "trace_id", None)})
