import logging
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("pios.trace")


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Assigns a trace id, and converts unhandled exceptions into a response.

    The exception handling is not decorative. Starlette generates its default
    500 in ServerErrorMiddleware, which sits *outside* every user middleware
    including CORSMiddleware, so that response carries no
    Access-Control-Allow-Origin header. A browser then reports a same-origin
    policy failure ("Load failed" in Safari) instead of the 500 that actually
    occurred, which hides real backend faults - a database outage looks
    identical to a CORS misconfiguration.

    Catching here, beneath CORSMiddleware, means the error response is created
    inside the CORS layer and is therefore returned to the browser with the
    correct headers and a real status code.
    """

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())
        request.state.trace_id = trace_id
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("unhandled error trace_id=%s path=%s", trace_id, request.url.path)
            response = JSONResponse(
                status_code=500,
                content={
                    "code": "INTERNAL_ERROR",
                    "message": "Internal server error",
                    "trace_id": trace_id,
                },
            )
        response.headers["x-trace-id"] = trace_id
        return response
