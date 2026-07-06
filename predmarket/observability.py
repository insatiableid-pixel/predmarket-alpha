"""Error tracking and alerting infrastructure.

Provides structured error reporting with context (breadcrumbs, tags) and
configurable alert routing (Slack webhook, GitHub issue creation). Designed
for the research platform's local/staging operation rather than cloud prod.

Sentry integration is supported but optional: if ``SENTRY_DSN`` is set,
errors are sent to Sentry with full stack traces and breadcrumbs. If not,
errors are logged with the same structured context for local debugging.
"""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# Optional Sentry integration (only active if SENTRY_DSN is set).
_SENTRY_AVAILABLE = False
try:
    if os.getenv("SENTRY_DSN"):
        import sentry_sdk  # type: ignore[import-untyped]

        sentry_sdk.init(
            dsn=os.getenv("SENTRY_DSN"),
            environment=os.getenv("SENTRY_ENVIRONMENT", "research"),
            traces_sample_rate=0.0,  # Disable perf monitoring (research platform)
            send_default_pii=False,
        )
        _SENTRY_AVAILABLE = True
        logger.info("sentry_initialized dsn_set=true environment=research")
except ImportError:
    pass


@dataclass
class Breadcrumb:
    """A breadcrumb for error context tracking."""

    timestamp: str
    category: str
    message: str
    level: str = "info"
    data: dict[str, Any] = field(default_factory=dict)


class ErrorTracker:
    """Tracks errors with breadcrumbs and routes alerts.

    Maintains a ring buffer of breadcrumbs per category for error context.
    When ``capture_exception`` is called, the error is sent to Sentry (if
    configured), logged with full context, and optionally routed to a
    Slack webhook or GitHub issue.
    """

    def __init__(self, max_breadcrumbs: int = 50) -> None:
        self._breadcrumbs: deque[Breadcrumb] = deque(maxlen=max_breadcrumbs)
        self._slack_webhook = os.getenv("ALERT_SLACK_WEBHOOK")
        self._error_count = 0

    def add_breadcrumb(self, category: str, message: str, **data: Any) -> None:
        self._breadcrumbs.append(
            Breadcrumb(
                timestamp=datetime.now(UTC).isoformat(),
                category=category,
                message=message,
                data=data,
            )
        )

    def capture_exception(self, exc: Exception, *, context: dict[str, Any] | None = None) -> str:
        """Capture an exception with full context and route alerts.

        Returns an error reference ID for correlation.
        """
        self._error_count += 1
        error_id = f"err-{self._error_count:06d}"
        context = context or {}
        breadcrumb_data = [b.__dict__ for b in self._breadcrumbs]

        # Log with structured context
        logger.error(
            "error_captured id=%s type=%s message=%s context=%s breadcrumbs=%d",
            error_id,
            type(exc).__name__,
            str(exc),
            json.dumps(context, default=str),
            len(breadcrumb_data),
            exc_info=True,
        )

        # Send to Sentry if available
        if _SENTRY_AVAILABLE:
            sentry_sdk.set_context("breadcrumbs", {"values": breadcrumb_data})  # type: ignore[union-attr]
            for key, value in context.items():
                sentry_sdk.set_tag(key, str(value))  # type: ignore[union-attr]
            sentry_sdk.capture_exception(exc)  # type: ignore[union-attr]

        # Route to Slack webhook if configured
        if self._slack_webhook:
            self._send_slack_alert(error_id, exc, context)

        return error_id

    def _send_slack_alert(self, error_id: str, exc: Exception, context: dict[str, Any]) -> None:
        """Send a structured alert to Slack (fire-and-forget, non-blocking)."""
        try:
            payload = {
                "text": ":rotating_light: Error in predmarket-alpha",
                "attachments": [
                    {
                        "color": "danger",
                        "fields": [
                            {"title": "Error ID", "value": error_id, "short": True},
                            {"title": "Type", "value": type(exc).__name__, "short": True},
                            {"title": "Message", "value": str(exc)[:500]},
                            {"title": "Context", "value": json.dumps(context, default=str)[:500]},
                        ],
                    }
                ],
            }
            req = Request(
                self._slack_webhook,  # type: ignore[arg-type]
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            urlopen(req, timeout=5)
        except Exception:
            logger.debug("slack_alert_failed error_id=%s", error_id, exc_info=True)


# Singleton instance for app-wide use.
_tracker: ErrorTracker | None = None


def get_error_tracker() -> ErrorTracker:
    """Get the singleton ErrorTracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = ErrorTracker()
    return _tracker


def capture_exception(exc: Exception, **context: Any) -> str:
    """Capture an exception with context. Convenience function."""
    return get_error_tracker().capture_exception(exc, context=context if context else None)


# ---------------------------------------------------------------------------
# Product analytics: lightweight feature-usage tracking
# ---------------------------------------------------------------------------

_ANALYTICS_LOG = Path(__file__).resolve().parents[1] / "data" / "processed" / "analytics.jsonl"


def track_event(event_name: str, **properties: Any) -> None:
    """Record a feature-usage event to the local analytics log.

    This provides lightweight product analytics for the research platform:
    which research-desk features are used, how often, and with what parameters.
    Events are written as JSONL to ``data/processed/analytics.jsonl``.

    Example::

        from predmarket.observability import track_event

        track_event("kalshi_universe_scan", candidates=1420, window_hours=72)
    """
    event = {
        "event": event_name,
        "timestamp": datetime.now(UTC).isoformat(),
        "properties": {k: str(v) for k, v in properties.items()},
    }
    try:
        _ANALYTICS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_ANALYTICS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")
    except OSError:
        logger.debug("analytics_log_write_failed event=%s", event_name)
