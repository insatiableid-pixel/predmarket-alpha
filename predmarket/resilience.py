"""Resilience patterns for external API calls (Kalshi, Polymarket, Coinbase).

Provides retry-with-exponential-backoff and circuit-breaker semantics using
``tenacity``. External venue clients should wrap their network calls with
``resilient_call`` to avoid cascading failures and respect rate limits.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Maximum retries for transient failures (network errors, 5xx responses).
MAX_RETRIES = 5
# Base delay in seconds for exponential backoff.
BASE_DELAY = 0.5
# Maximum delay cap for a single retry.
MAX_DELAY = 30.0


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is open and calls are being rejected."""


class CircuitBreaker:
    """Simple circuit breaker for external service calls.

    Tracks consecutive failures. After ``failure_threshold`` consecutive
    failures the breaker opens and rejects all calls for ``recovery_seconds``.
    After recovery, one trial call is allowed (half-open state); if it succeeds
    the breaker closes, if it fails the breaker re-opens.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_seconds: float = 60.0,
        name: str = "default",
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self.name = name
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        import time
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self.recovery_seconds:
            return False  # Recovery period elapsed -> half-open
        return True

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        import time
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._opened_at = time.monotonic()
            logger.warning(
                "circuit_breaker_opened name=%s failures=%d threshold=%d",
                self.name,
                self._consecutive_failures,
                self.failure_threshold,
            )

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        if self.is_open:
            raise CircuitBreakerOpen(
                f"Circuit breaker '{self.name}' is open after {self._consecutive_failures} failures"
            )
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise


# Registry of named circuit breakers for external services.
_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(name: str, **kwargs: Any) -> CircuitBreaker:
    """Get or create a named circuit breaker instance."""
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name=name, **kwargs)
    return _breakers[name]


def resilient_external_call(
    func: Callable[..., T],
    *args: Any,
    breaker_name: str = "default",
    max_retries: int = MAX_RETRIES,
    **kwargs: Any,
) -> T:
    """Call an external API with retry+backoff and circuit-breaker protection.

    This is the standard wrapper for all Kalshi/Polymarket/Coinbase calls.
    It retries on network errors with exponential jitter backoff, and trips
    a named circuit breaker after consecutive failures.
    """
    breaker = get_breaker(breaker_name)

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential_jitter(initial=BASE_DELAY, max=MAX_DELAY),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _call() -> T:
        return breaker.call(func, *args, **kwargs)

    return _call()
