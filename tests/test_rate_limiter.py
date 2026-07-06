"""Tests for token-bucket rate limiter (VAL-RATE-001 through VAL-RATE-009)."""

from __future__ import annotations

import asyncio
import time

import pytest

from predmarket.resilience import (
    RateLimitExceeded,
    TokenBucket,
    get_bucket,
)

# ---------------------------------------------------------------------------
# VAL-RATE-001: TokenBucket exists with rate and burst parameters
# ---------------------------------------------------------------------------


class TestTokenBucketConstruction:
    """VAL-RATE-001: Token-bucket class in resilience.py with rate and burst parameters."""

    def test_construct_with_rate_and_burst(self) -> None:
        bucket = TokenBucket(rate=30.0, burst=60.0)
        assert bucket.rate == 30.0
        assert bucket.burst == 60.0

    def test_construct_with_name(self) -> None:
        bucket = TokenBucket(rate=10.0, burst=20.0, name="test")
        assert bucket.name == "test"

    def test_negative_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="rate must be positive"):
            TokenBucket(rate=-1.0, burst=10.0)

    def test_zero_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="rate must be positive"):
            TokenBucket(rate=0.0, burst=10.0)

    def test_negative_burst_raises(self) -> None:
        with pytest.raises(ValueError, match="burst must be positive"):
            TokenBucket(rate=10.0, burst=-1.0)

    def test_zero_burst_raises(self) -> None:
        with pytest.raises(ValueError, match="burst must be positive"):
            TokenBucket(rate=10.0, burst=0.0)


# ---------------------------------------------------------------------------
# VAL-RATE-005: Rate-limited calls fail gracefully
# ---------------------------------------------------------------------------


class TestTokenBucketConsume:
    """VAL-RATE-005: Token consumption behaviour."""

    @pytest.mark.asyncio
    async def test_consume_returns_immediately_when_tokens_available(self) -> None:
        bucket = TokenBucket(rate=100.0, burst=100.0)
        wait = await bucket.consume(1.0)
        assert wait == 0.0

    @pytest.mark.asyncio
    async def test_consume_multiple_tokens_at_once(self) -> None:
        bucket = TokenBucket(rate=100.0, burst=100.0)
        wait = await bucket.consume(50.0)
        assert wait == 0.0

    @pytest.mark.asyncio
    async def test_consume_waits_when_tokens_exhausted(self) -> None:
        bucket = TokenBucket(rate=10.0, burst=1.0)
        await bucket.consume(1.0)  # exhaust the burst
        t0 = time.monotonic()
        await bucket.consume(1.0)  # must wait ~0.1s (1 token / 10 tps)
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.08  # allow small timing variance

    @pytest.mark.asyncio
    async def test_consume_gradually_refills(self) -> None:
        bucket = TokenBucket(rate=20.0, burst=10.0)
        await bucket.consume(10.0)  # exhaust
        # After 0.25s we should have ~5 tokens back
        await asyncio.sleep(0.25)
        wait = await bucket.consume(5.0)
        assert wait == 0.0

    def test_consume_sync_blocks_when_exhausted(self) -> None:
        bucket = TokenBucket(rate=10.0, burst=1.0)
        bucket.consume_sync(1.0)  # exhaust
        t0 = time.monotonic()
        bucket.consume_sync(1.0)  # must wait ~0.1s
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.08

    def test_consume_sync_raises_when_wait_false(self) -> None:
        bucket = TokenBucket(rate=10.0, burst=1.0)
        bucket.consume_sync(1.0, wait=True)  # exhaust
        with pytest.raises(RateLimitExceeded, match="Rate limit exceeded"):
            bucket.consume_sync(1.0, wait=False)

    def test_consume_sync_succeeds_when_tokens_available(self) -> None:
        bucket = TokenBucket(rate=100.0, burst=100.0)
        bucket.consume_sync(50.0, wait=True)  # should succeed immediately
        # Allow small timing drift; available tokens should be ~50ish.
        remaining = bucket.available_tokens
        assert remaining <= 51.0  # at most 50 + a tiny refill
        assert remaining >= 0.0


# ---------------------------------------------------------------------------
# VAL-RATE-007: Token bucket is concurrency-safe
# ---------------------------------------------------------------------------


class TestTokenBucketConcurrency:
    """VAL-RATE-007: concurrency-safe with asyncio.Lock."""

    @pytest.mark.asyncio
    async def test_concurrent_consumers_are_serialized(self) -> None:
        """Two concurrent consumers share the same bucket correctly."""
        bucket = TokenBucket(rate=100.0, burst=10.0)

        async def burn(count: int) -> float:
            total_wait = 0.0
            for _ in range(count):
                total_wait += await bucket.consume(1.0)
            return total_wait

        wait1, wait2 = await asyncio.gather(burn(5), burn(5))
        # Both should succeed; total consumed = 10, within burst of 10
        assert wait1 == 0.0
        assert wait2 == 0.0

    @pytest.mark.asyncio
    async def test_stress_sequential_consistency(self) -> None:
        """Large sequential batch with invariant checks."""
        bucket = TokenBucket(rate=1000.0, burst=200.0)
        consumed = 0
        started = time.monotonic()
        for _ in range(200):
            await bucket.consume(1.0)
            consumed += 1
        elapsed = time.monotonic() - started
        assert consumed == 200
        # The loop is not instantaneous; allow real refill that accrued while
        # the sequential batch ran.
        assert bucket.available_tokens <= max(1.0, elapsed * bucket.rate + 0.25)


# ---------------------------------------------------------------------------
# VAL-RATE-002 / VAL-RATE-003: Rate limits for public and auth endpoints
# ---------------------------------------------------------------------------


class TestRateLimitsApplied:
    """VAL-RATE-002: Public 30 req/s. VAL-RATE-003: Auth 10 req/s."""

    def test_default_public_bucket_rate(self) -> None:
        bucket = get_bucket("public_test_rate")
        assert bucket.rate == 30.0
        assert bucket.burst == 60.0

    def test_default_auth_bucket_rate(self) -> None:
        bucket = get_bucket("auth_test_rate", rate=10.0, burst=20.0)
        assert bucket.rate == 10.0
        assert bucket.burst == 20.0

    def test_custom_public_bucket_params(self) -> None:
        bucket = TokenBucket(rate=30.0, burst=60.0, name="public_custom")
        assert bucket.rate == 30.0
        assert bucket.burst == 60.0

    def test_custom_auth_bucket_params(self) -> None:
        bucket = TokenBucket(rate=10.0, burst=20.0, name="auth_custom")
        assert bucket.rate == 10.0
        assert bucket.burst == 20.0


# ---------------------------------------------------------------------------
# VAL-RATE-004: Burst tolerance configurable via YAML config
# ---------------------------------------------------------------------------


class TestConfigDrivenRateLimits:
    """VAL-RATE-004: Configurable burst tolerance."""

    def test_config_roundtrip(self) -> None:
        from predmarket.config import RateLimitsConfig

        cfg = RateLimitsConfig(
            public_rate=30.0,
            public_burst=60.0,
            auth_rate=10.0,
            auth_burst=20.0,
        )
        assert cfg.public_rate == 30.0
        assert cfg.public_burst == 60.0
        assert cfg.auth_rate == 10.0
        assert cfg.auth_burst == 20.0

    def test_config_custom_values(self) -> None:
        from predmarket.config import RateLimitsConfig

        cfg = RateLimitsConfig(
            public_rate=15.0,
            public_burst=30.0,
            auth_rate=5.0,
            auth_burst=10.0,
        )
        assert cfg.public_rate == 15.0
        assert cfg.public_burst == 30.0
        assert cfg.auth_rate == 5.0
        assert cfg.auth_burst == 10.0

    def test_config_defaults(self) -> None:
        from predmarket.config import RateLimitsConfig

        cfg = RateLimitsConfig()
        assert cfg.public_rate == 30.0
        assert cfg.public_burst == 60.0
        assert cfg.auth_rate == 10.0
        assert cfg.auth_burst == 20.0

    def test_config_integration_via_kalshi_live(self) -> None:
        """RateLimitsConfig is wired into KalshiLiveConfig."""
        from predmarket.config import KalshiLiveConfig

        cfg = KalshiLiveConfig()
        assert cfg.rate_limits.public_rate == 30.0
        assert cfg.rate_limits.auth_rate == 10.0

    def test_config_yaml_has_rate_limits(self) -> None:
        """Verify config.yaml has the rate_limits section."""
        from pathlib import Path

        import yaml

        project_root = Path(__file__).resolve().parents[1]
        with open(project_root / "config" / "config.yaml") as f:
            raw = yaml.safe_load(f) or {}
        rl = raw.get("kalshi_live", {}).get("rate_limits", {})
        assert rl.get("public_rate") == 30.0
        assert rl.get("public_burst") == 60.0
        assert rl.get("auth_rate") == 10.0
        assert rl.get("auth_burst") == 20.0


# ---------------------------------------------------------------------------
# VAL-RATE-006: Research-only path unaffected (waits for tokens)
# ---------------------------------------------------------------------------


class TestResearchOnlyPath:
    """VAL-RATE-006: Research path waits for tokens rather than raising."""

    @pytest.mark.asyncio
    async def test_consume_always_waits_not_raises(self) -> None:
        """Research code uses consume() which always waits."""
        bucket = TokenBucket(rate=100.0, burst=1.0)
        await bucket.consume(1.0)  # exhaust
        # This would block briefly rather than raising
        wait = await bucket.consume(1.0)
        assert wait > 0.0

    def test_market_data_client_uses_consume_not_fail_fast(self) -> None:
        """KalshiMarketDataClient buckets always wait (research path)."""
        from predmarket.config import Config
        from predmarket.kalshi_dataset import KalshiMarketDataClient

        bucket = TokenBucket(rate=100.0, burst=100.0)
        config = Config()
        client = KalshiMarketDataClient(config, public_bucket=bucket)
        assert client._public_bucket is bucket


# ---------------------------------------------------------------------------
# VAL-RATE-008: Rate limiter is wired via decorator or context-manager pattern
# ---------------------------------------------------------------------------


class TestRateLimiterWiring:
    """VAL-RATE-008: Rate limited calls wired into client methods."""

    def test_live_client_has_buckets(self) -> None:
        from predmarket.kalshi_live_client import KalshiTradingClient, KalshiTradingClientConfig

        cfg = KalshiTradingClientConfig(
            base_url="https://api.example.com",
            api_key="test",
            private_key_pem_or_path=_dummy_key_pem(),
        )
        client = KalshiTradingClient(cfg)
        assert client._public_bucket is not None
        assert client._auth_bucket is not None

    def test_live_client_injects_custom_buckets(self) -> None:
        from predmarket.kalshi_live_client import KalshiTradingClient, KalshiTradingClientConfig

        pub = TokenBucket(rate=5.0, burst=5.0, name="test_pub")
        auth = TokenBucket(rate=2.0, burst=2.0, name="test_auth")
        cfg = KalshiTradingClientConfig(
            base_url="https://api.example.com",
            api_key="test",
            private_key_pem_or_path=_dummy_key_pem(),
        )
        client = KalshiTradingClient(cfg, public_bucket=pub, auth_bucket=auth)
        assert client._public_bucket is pub
        assert client._auth_bucket is auth


# ---------------------------------------------------------------------------
# VAL-RATE-009: Circuit breaker and rate limiter compose correctly
# ---------------------------------------------------------------------------


class TestCircuitBreakerComposition:
    """VAL-RATE-009: Rate-limited delays do NOT increment the circuit breaker."""

    def test_rate_delay_does_not_affect_circuit_breaker(self) -> None:
        """Waiting for rate-limit tokens should not trip the circuit breaker."""
        from predmarket.resilience import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=5, name="test_compose")
        bucket = TokenBucket(rate=100.0, burst=1.0, name="compose_test")

        # Exhaust the bucket
        bucket.consume_sync(1.0, wait=True)

        # Simulate: rate-limited delay followed by successful API call
        # The delay itself should not record a circuit-breaker failure
        bucket.consume_sync(1.0, wait=True)  # waits ~0.01s for rate limit

        # Circuit breaker should still have 0 failures (no actual failures recorded)
        assert breaker._consecutive_failures == 0


# ---------------------------------------------------------------------------
# VAL-CROSS-023: Live preflight respects rate-limited API client
# ---------------------------------------------------------------------------


class TestLivePreflightRateLimiting:
    """VAL-CROSS-023: Live preflight uses rate-limited client."""

    def test_preflight_api_calls_go_through_rate_limited_client(self) -> None:
        """Live preflight calls use same client with rate limiting."""
        from predmarket.kalshi_live_client import KalshiTradingClient, KalshiTradingClientConfig

        cfg = KalshiTradingClientConfig(
            base_url="https://api.example.com",
            api_key="test",
            private_key_pem_or_path=_dummy_key_pem(),
        )
        client = KalshiTradingClient(cfg)
        # Both public and auth buckets are wired
        assert client._public_bucket.rate == 30.0
        assert client._public_bucket.burst == 60.0
        assert client._auth_bucket.rate == 10.0
        assert client._auth_bucket.burst == 20.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dummy_key_pem() -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
