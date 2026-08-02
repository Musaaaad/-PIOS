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
app = FastAPI(
    title="PIOS MVP API",
    version="1.4.0",
    description="Pharmacy Intelligence Operating System - Sprint 13 institutional pilot execution, identity binding, provenance and outcome reporting",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Trace-ID"],
    expose_headers=["X-Trace-ID", "Content-Disposition"],
)
app.add_middleware(TraceIdMiddleware)
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
