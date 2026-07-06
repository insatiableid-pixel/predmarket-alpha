"""Log sanitization for credential and sensitive-data redaction.

Provides a logging filter that scrubs known secret patterns (API keys,
tokens, passwords) from log records before they reach any handler.
Integrated into the platform's structured JSON logging in ``main.py``.
"""

from __future__ import annotations

import logging
import re
from typing import Any

# Patterns that match common secret formats. Each is replaced with [REDACTED].
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    # Kalshi-style API keys (hex/alphanumeric, 20+ chars after key/secret label)
    re.compile(
        r"(?i)(api[_-]?key|api[_-]?secret|token|password|secret)\s*[=:]\s*['\"]?([A-Za-z0-9_\-]{16,})",
        re.IGNORECASE,
    ),
    # Bearer tokens
    re.compile(r"(?i)bearer\s+([A-Za-z0-9_\-\.]{20,})"),
    # Generic hex secrets (40+ hex chars, typical of HMAC keys)
    re.compile(r"\b([a-f0-9]{40,})\b", re.IGNORECASE),
    # Private key headers
    re.compile(r"-----BEGIN\s+[A-Z\s]+PRIVATE\s+KEY-----"),
]

# Field names that should always be redacted in structured log dicts.
_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "password",
        "passwd",
        "token",
        "access_token",
        "refresh_token",
        "private_key",
        "kalshi_api_key",
        "kalshi_api_secret",
    }
)


def redact_value(value: Any) -> Any:
    """Redact sensitive string values, returning [REDACTED] for known secret fields."""
    if isinstance(value, str):
        redacted = value
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted
    return value


def sanitize_record(record: logging.LogRecord) -> bool:
    """Logging filter: scrub secrets from message and structured extra fields."""
    if isinstance(record.msg, str):
        record.msg = redact_value(record.msg)
    # Sanitize extra fields passed via logger.info(msg, extra={...})
    for key in list(record.__dict__):
        if key in _SENSITIVE_KEYS:
            setattr(record, key, "[REDACTED]")
    return True


class SanitizingFilter(logging.Filter):
    """Logging filter that redacts secrets from all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        return sanitize_record(record)
