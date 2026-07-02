"""Request tracing via X-Request-ID propagation.

Provides Starlette/FastAPI middleware that assigns a unique request ID to
every incoming HTTP request, propagates it through the logging context,
and returns it in the ``X-Request-ID`` response header. This allows following
a request through the system end-to-end.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign or propagate an X-Request-ID for every request.

    If the incoming request has an ``X-Request-ID`` header, it is reused.
    Otherwise a new UUID4 is generated. The ID is stored on
    ``request.state.request_id`` and set on the response header.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request_completed method=%s path=%s status=%s request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            request_id,
        )
        return response


def get_request_id(request: Request) -> str | None:
    """Get the request ID from the request state, if set by middleware."""
    return getattr(request.state, "request_id", None)


def install_request_tracing(app: Any) -> None:
    """Install the X-Request-ID middleware on a Starlette/FastAPI app."""
    app.add_middleware(RequestIdMiddleware)
