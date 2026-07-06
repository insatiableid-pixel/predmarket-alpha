"""Tests for feature flags, log sanitizer, resilience, request context, and observability."""

from __future__ import annotations

import logging

from predmarket.feature_flags import FeatureFlag, all_flags, is_enabled
from predmarket.log_sanitizer import SanitizingFilter, redact_value
from predmarket.observability import ErrorTracker
from predmarket.resilience import CircuitBreaker, CircuitBreakerOpen, resilient_external_call

# --- Feature flags ---


def test_feature_flag_defaults_disabled() -> None:
    assert is_enabled(FeatureFlag.CRYPTO_PROXY_DECAY_MONITORING) is False
    assert is_enabled(FeatureFlag.DASHBOARD_REAL_TIME) is False


def test_feature_flag_env_override(monkeypatch: object) -> None:
    monkeypatch.setenv("FEATURE_DASHBOARD_REAL_TIME", "true")  # type: ignore[attr-defined]
    assert is_enabled(FeatureFlag.DASHBOARD_REAL_TIME) is True
    monkeypatch.setenv("FEATURE_DASHBOARD_REAL_TIME", "false")  # type: ignore[attr-defined]
    assert is_enabled(FeatureFlag.DASHBOARD_REAL_TIME) is False


def test_all_flags_returns_dict() -> None:
    flags = all_flags()
    assert isinstance(flags, dict)
    assert len(flags) == len(FeatureFlag)
    assert all(isinstance(v, bool) for v in flags.values())


# --- Log sanitizer ---


def test_redact_api_key() -> None:
    result = redact_value("api_key=aaaaaaaaaaaaaaaa")
    assert "[REDACTED]" in result
    assert "aaaaaaaa" not in result


def test_redact_bearer_token() -> None:
    result = redact_value("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
    assert "[REDACTED]" in result


def test_redact_hex_secret() -> None:
    result = redact_value("signature=abcdef0123456789abcdef0123456789abcdef01")
    assert "[REDACTED]" in result


def test_redact_preserves_normal_text() -> None:
    result = redact_value("Processed 42 markets from Kalshi universe scan")
    assert result == "Processed 42 markets from Kalshi universe scan"


def test_sanitizing_filter_scrubs_record() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="api_key=bbbbbbbbbbbbbbbb",
        args=None,
        exc_info=None,
    )
    f = SanitizingFilter()
    assert f.filter(record) is True
    assert "bbbbbbbb" not in str(record.msg)


# --- Circuit breaker ---


def test_circuit_breaker_opens_after_failures() -> None:
    cb = CircuitBreaker(failure_threshold=3, recovery_seconds=300, name="test")
    assert cb.is_open is False

    cb.record_failure()
    cb.record_failure()
    assert cb.is_open is False

    cb.record_failure()
    assert cb.is_open is True


def test_circuit_breaker_resets_on_success() -> None:
    cb = CircuitBreaker(failure_threshold=3, recovery_seconds=300, name="test2")
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb.is_open is False
    assert cb._consecutive_failures == 0


def test_circuit_breaker_rejects_when_open() -> None:
    cb = CircuitBreaker(failure_threshold=1, recovery_seconds=300, name="test3")
    cb.record_failure()
    assert cb.is_open is True

    def should_not_run() -> str:
        return "ran"

    try:
        cb.call(should_not_run)
        assert False, "Should have raised CircuitBreakerOpen"
    except CircuitBreakerOpen:
        pass


def test_circuit_breaker_passes_through_success() -> None:
    cb = CircuitBreaker(failure_threshold=3, recovery_seconds=300, name="test4")
    result = cb.call(lambda: "ok")
    assert result == "ok"
    assert cb.is_open is False


def test_resilient_external_call_retries_on_network_error() -> None:
    call_count = [0]

    def flaky() -> str:
        call_count[0] += 1
        if call_count[0] < 2:
            raise ConnectionError("transient")
        return "success"

    result = resilient_external_call(flaky, breaker_name="test_retry")
    assert result == "success"
    assert call_count[0] == 2


# --- Error tracker / observability ---


def test_error_tracker_captures_exception() -> None:
    tracker = ErrorTracker()
    tracker.add_breadcrumb("test", "before error", extra="val")
    exc = ValueError("test error")
    error_id = tracker.capture_exception(exc, context={"module": "test"})
    assert error_id.startswith("err-")
    assert len(tracker._breadcrumbs) == 1


def test_error_tracker_breadcrumb_ring_buffer() -> None:
    tracker = ErrorTracker(max_breadcrumbs=3)
    for i in range(5):
        tracker.add_breadcrumb("cat", f"msg {i}")
    assert len(tracker._breadcrumbs) == 3
    # Should keep the most recent 3
    assert tracker._breadcrumbs[0].message == "msg 2"
    assert tracker._breadcrumbs[-1].message == "msg 4"
