"""FastAPI server, auth, and REST endpoints for the dashboard.

Exposes:
- /api/staged  (GET)  – list staged orders
- /api/approve (POST) – approve a staged order
- /metrics     (GET)  – Prometheus scrape endpoint
"""

import os
import logging
from typing import Optional

import pandas as pd
from fastapi import FastAPI, Depends, Security, HTTPException, status
from fastapi.responses import Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

logger = logging.getLogger("predmarket.dashboard")

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

server = FastAPI()

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def get_api_key(api_key: Optional[str] = Security(api_key_header)):
    expected_key = os.getenv("API_KEY", "predmarket_secret_key_123")
    if not api_key or api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    return api_key


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ApprovalRequest(BaseModel):
    """Pydantic model for /api/approve request body validation."""

    id: int = Field(gt=0, description="Staged order ID to approve")


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@server.get("/api/staged")
def get_staged_orders(api_key: str = Depends(get_api_key)):
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
async def approve_order_endpoint(
    body: ApprovalRequest, api_key: str = Depends(get_api_key)
):
    from .data import approve_staged_order_db

    logger.info(f"Approve endpoint called for staged order {body.id}")
    return await approve_staged_order_db(body.id)


@server.get("/metrics")
def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
