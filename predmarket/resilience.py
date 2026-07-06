"""Resilience patterns for external API calls (Kalshi, Polymarket, Coinbase).

Provides retry-with-exponential-backoff, circuit-breaker, and token-bucket
rate-limiting semantics. External venue clients should wrap their network calls
with ``resilient_call`` or the ``TokenBucket`` rate limiter to avoid cascading
failures and respect API rate limits.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

if TYPE_CHECKING:
    from predmarket.config import Config

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


# ---------------------------------------------------------------------------
# Token-bucket rate limiter
# ---------------------------------------------------------------------------


class RateLimitExceeded(RuntimeError):  # noqa: N818
    """Raised when a rate-limited call is rejected (no-token-consumed mode)."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        retry_after_seconds: float = 0.0,
        bucket_name: str = "",
    ) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
        self.bucket_name = bucket_name


class TokenBucket:
    """Token-bucket rate limiter with async and synchronous consumption paths.

    Parameters
    ----------
    rate : float
        Token replenishment rate in tokens per second.
    burst : float
        Maximum accumulated tokens (bucket capacity).
    name : str
        Human-readable name for logging/tracking.

    The bucket supports both ``await consume()`` (asyncio callers) and
    ``consume_sync()`` (synchronous callers).  Both are concurrency-safe using
    independent locks for each path.  When tokens are exhausted the caller
    blocks/awaits until sufficient tokens are available.
    """

    def __init__(self, rate: float, burst: float, name: str = "") -> None:
        if rate <= 0:
            raise ValueError(f"rate must be positive, got {rate}")
        if burst <= 0:
            raise ValueError(f"burst must be positive, got {burst}")
        self.rate = rate
        self.burst = burst
        self.name = name
        self._tokens: float = float(burst)
        self._last_refill: float = 0.0
        self._async_lock = asyncio.Lock()
        self._sync_lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        if self._last_refill == 0.0:
            self._last_refill = now
            return
        elapsed = now - self._last_refill
        self._last_refill = now
        self._tokens = min(self.burst, self._tokens + elapsed * self.rate)

    async def consume(self, tokens: float = 1.0) -> float:
        """Wait until *tokens* are available, consume them, return wait time."""
        async with self._async_lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0
            deficit = tokens - self._tokens
            wait = deficit / self.rate
            await asyncio.sleep(wait)
            self._refill()
            self._tokens = min(self._tokens, tokens)
            self._tokens -= tokens
            return wait

    def consume_sync(self, tokens: float = 1.0, wait: bool = True) -> None:
        """Synchronous token consumption.

        If *wait* is ``True`` (default) the call blocks until tokens are
        available.  If *wait* is ``False`` and insufficient tokens exist,
        raises :class:`RateLimitExceeded`.
        """
        with self._sync_lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return
            if not wait:
                deficit = tokens - self._tokens
                raise RateLimitExceeded(
                    f"Rate limit exceeded for bucket '{self.name}' "
                    f"(rate={self.rate}/s, burst={self.burst})",
                    retry_after_seconds=deficit / self.rate,
                    bucket_name=self.name,
                )
            deficit = tokens - self._tokens
            wait_time = deficit / self.rate
        time.sleep(wait_time)
        with self._sync_lock:
            self._refill()
            self._tokens = min(self._tokens, tokens)
            self._tokens -= tokens

    @property
    def available_tokens(self) -> float:
        """Current stored token count (best-effort, not locked)."""
        return min(self.burst, self._tokens)


# Registry of named token buckets for rate limiting.
_buckets: dict[str, TokenBucket] = {}


def get_bucket(
    name: str,
    rate: float = 30.0,
    burst: float = 60.0,
) -> TokenBucket:
    """Get or create a named token bucket instance."""
    if name not in _buckets:
        _buckets[name] = TokenBucket(rate=rate, burst=burst, name=name)
    return _buckets[name]


def rate_limit_config_from_app_config(
    config: Config,
) -> dict[str, tuple[float, float]]:
    """Read rate-limit parameters from the application config.

    Returns a dict mapping bucket names to ``(rate, burst)`` tuples:
    - ``"public"`` — public/unauthenticated endpoints
    - ``"auth"`` — authenticated endpoints
    """
    rl = config.kalshi_live.rate_limits
    return {
        "public": (rl.public_rate, rl.public_burst),
        "auth": (rl.auth_rate, rl.auth_burst),
    }
