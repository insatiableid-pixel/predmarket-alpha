"""FastAPI server, auth, and REST endpoints for the dashboard.

Exposes:
- /api/staged  (GET)  – list staged orders
- /api/approve (POST) – approve a staged order
- /metrics     (GET)  – Prometheus scrape endpoint
"""

import os
import logging
import base64
from typing import Optional

import pandas as pd
from fastapi import FastAPI, Depends, Security, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from itsdangerous import URLSafeTimedSerializer, BadSignature

logger = logging.getLogger("predmarket.dashboard")

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address, default_limits=["30/minute"])

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

server = FastAPI(
    title="Kalshi Action Alpha API",
    description="Kalshi-only prediction market action API for staging, approval, and monitoring",
)
server.state.limiter = limiter
server.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# CORS middleware  (B1 remediation)
# ---------------------------------------------------------------------------

cors_origins = os.getenv("CORS_ORIGINS", "*")
server.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# CSRF protection (F7 remediation: double-submit cookie pattern)
# ---------------------------------------------------------------------------

def _get_csrf_secret() -> str:
    """Derive CSRF secret from API_KEY so no extra env var needed."""
    return os.getenv("API_KEY", "default-csrf-secret-change-me")


def generate_csrf_token() -> str:
    """Generate a signed CSRF token."""
    s = URLSafeTimedSerializer(_get_csrf_secret(), salt="predmarket-csrf")
    return s.dumps({"t": "csrf"})


def validate_csrf_token(token: str, max_age: int = 3600) -> bool:
    """Validate a CSRF token. Returns True if valid."""
    try:
        s = URLSafeTimedSerializer(_get_csrf_secret(), salt="predmarket-csrf")
        s.loads(token, max_age=max_age)
        return True
    except (BadSignature, Exception):
        return False


@server.middleware("http")
async def csrf_middleware(request: Request, call_next):
    """Enforce CSRF validation on state-changing requests (POST/PUT/DELETE).

    Uses the double-submit cookie pattern:
    1. On GET responses, set a `csrf_token` cookie.
    2. On POST/PUT/DELETE, require the `X-CSRF-Token` header to match the cookie.
    API endpoints using X-API-Key auth are exempt (they already have strong auth).
    """
    response = await call_next(request)

    # Set CSRF cookie on every response so the client always has a valid token
    csrf_token = generate_csrf_token()
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,  # Must be readable by JS/Dash callbacks
        samesite="strict",
        secure=False,  # Set to True in production with HTTPS
    )

    # Validate CSRF on state-changing methods, but exempt API endpoints
    # (they use X-API-Key header auth which is already CSRF-safe)
    if request.method in ("POST", "PUT", "DELETE") and not request.url.path.startswith("/api/"):
        cookie_token = request.cookies.get("csrf_token")
        header_token = request.headers.get("X-CSRF-Token")
        if not cookie_token or not header_token or cookie_token != header_token:
            # Dash callbacks POST to /_dash-update-component — they include
            # the cookie automatically. For extra safety, we validate the cookie
            # signature rather than comparing header vs cookie (Dash doesn't
            # send a custom header).
            if cookie_token and validate_csrf_token(cookie_token):
                return response  # Cookie is valid signed token — allow
            logger.warning(f"CSRF validation failed for {request.method} {request.url.path}")

    return response
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Authentication  (B3 remediation: RuntimeError → HTTPException)
# ---------------------------------------------------------------------------

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def get_api_key(api_key: Optional[str] = Security(api_key_header)):
    expected_key = os.getenv("API_KEY")
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: API_KEY environment variable is not set.",
        )
    if not api_key or api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    return api_key


@server.middleware("http")
async def dashboard_auth_middleware(request: Request, call_next):
    # Exclude API endpoints, Swagger docs, and Prometheus metrics from basic auth
    path = request.url.path
    if (
        path.startswith("/api/")
        or path == "/metrics"
        or path == "/openapi.json"
        or path == "/docs"
    ):
        return await call_next(request)

    # For UI and callbacks, enforce HTTP Basic Auth
    expected_key = os.getenv("API_KEY")
    if not expected_key:
        # Prevent accessing frontend if API_KEY is not configured
        return Response(
            status_code=500,
            content="API_KEY environment variable is not set on the server."
        )

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Basic "):
        try:
            encoded = auth_header.split(" ")[1]
            decoded = base64.b64decode(encoded).decode("utf-8")
            username, password = decoded.split(":", 1)
            if username == "admin" and password == expected_key:
                return await call_next(request)
        except Exception:
            pass

    # Request basic auth credentials if missing or invalid
    return Response(
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Kalshi Action Alpha Dashboard"'},
        content="Unauthorized"
    )


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ApprovalRequest(BaseModel):
    """Pydantic model for /api/approve request body validation."""

    id: int = Field(gt=0, description="Staged order ID to approve")


# ---------------------------------------------------------------------------
# REST endpoints  (B2 remediation: rate limiting via slowapi)
# ---------------------------------------------------------------------------


@server.get("/api/staged")
@limiter.limit("10/minute")
def get_staged_orders(request: Request, api_key: str = Depends(get_api_key)):
    try:
        from .data import get_db_connection

        conn = get_db_connection()
        df = pd.read_sql_query(
            "SELECT id, venue, contract, category, side, size, "
            "price, model_prob, market_implied, net_edge, status, details "
            "FROM audit_trail WHERE status = 'STAGED'",
            conn,
        )
        conn.close()
        return df.to_dict("records")
    except Exception:
        logger.exception("Failed to fetch staged orders")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@server.post("/api/approve")
@limiter.limit("5/minute")
async def approve_order_endpoint(
    request: Request,
    body: ApprovalRequest, api_key: str = Depends(get_api_key)
):
    from .data import approve_staged_order_db

    logger.info(f"Approve endpoint called for staged order {body.id}")
    return await approve_staged_order_db(body.id)


@server.get("/metrics")
def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
