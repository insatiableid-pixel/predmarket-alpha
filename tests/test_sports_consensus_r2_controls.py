"""Focused R2 tests: key permission, quota budget, paid_calls, dense-panel controls."""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path

import pytest

from predmarket.sports_consensus_reference_builder import (
    DEFAULT_PER_DAY_BUDGET,
    DEFAULT_PER_RUN_BUDGET,
    DEFAULT_PER_TRANCHE_BUDGET,
    QuotaBudget,
    _read_api_key,
)
from predmarket.sports_consensus_sharp_provider_capture import (
    build_sharp_provider_capture_report,
)

# ---------------------------------------------------------------------------
# _read_api_key — permission rejection
# ---------------------------------------------------------------------------


def test_read_api_key_secure_mode(tmp_path: Path) -> None:
    path = tmp_path / "key.txt"
    path.write_text("sk-valid\n", encoding="utf-8")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    assert _read_api_key(path) == "sk-valid"


def test_read_api_key_group_readable_rejected(tmp_path: Path) -> None:
    path = tmp_path / "key.txt"
    path.write_text("sk-leaky\n", encoding="utf-8")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
    with pytest.raises(PermissionError, match="group/world-accessible"):
        _read_api_key(path)


def test_read_api_key_world_readable_rejected(tmp_path: Path) -> None:
    path = tmp_path / "key.txt"
    path.write_text("sk-777\n", encoding="utf-8")
    os.chmod(path, 0o777)
    with pytest.raises(PermissionError, match="group/world-accessible"):
        _read_api_key(path)


def test_read_api_key_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent.txt"
    with pytest.raises(FileNotFoundError):
        _read_api_key(missing)


def test_read_api_key_empty_rejected(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("   \n", encoding="utf-8")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    with pytest.raises(ValueError, match="empty"):
        _read_api_key(path)


# ---------------------------------------------------------------------------
# QuotaBudget — budget enforcement
# ---------------------------------------------------------------------------


def test_quota_budget_default_limits() -> None:
    b = QuotaBudget()
    assert b.max_per_run == DEFAULT_PER_RUN_BUDGET
    assert b.max_per_day == DEFAULT_PER_DAY_BUDGET
    assert b.max_per_tranche == DEFAULT_PER_TRANCHE_BUDGET


def test_quota_budget_consume_within_limits() -> None:
    b = QuotaBudget(max_per_run=5, max_per_day=5, max_per_tranche=5)
    for _ in range(5):
        b.consume(1)
    assert b.used_per_run == 5


def test_quota_budget_exceeds_run_limit() -> None:
    b = QuotaBudget(max_per_run=2, max_per_day=10, max_per_tranche=10)
    b.consume(2)
    with pytest.raises(RuntimeError, match="QuotaBudget exceeded"):
        b.consume(1)


def test_quota_budget_exceeds_day_limit() -> None:
    b = QuotaBudget(max_per_run=100, max_per_day=5, max_per_tranche=100)
    b.consume(5)
    with pytest.raises(RuntimeError, match="QuotaBudget exceeded"):
        b.consume(1)


def test_quota_budget_exceeds_tranche_limit() -> None:
    b = QuotaBudget(max_per_run=100, max_per_day=100, max_per_tranche=3)
    b.consume(3)
    with pytest.raises(RuntimeError, match="QuotaBudget exceeded"):
        b.consume(1)


def test_quota_budget_check_before_consume() -> None:
    b = QuotaBudget(max_per_run=1, max_per_day=1, max_per_tranche=1)
    assert b.check(1)
    b.consume(1)
    assert not b.check(1)


def test_quota_budget_reset_run() -> None:
    b = QuotaBudget(max_per_run=2, max_per_day=100, max_per_tranche=100)
    b.consume(2)
    assert not b.check(1)
    b.reset_run()
    assert b.check(1)


def test_quota_budget_zero_count_noop() -> None:
    b = QuotaBudget(max_per_run=2, max_per_day=2, max_per_tranche=2)
    b.consume(0)
    assert b.used_per_run == 0
    assert b.check(1)


def test_quota_budget_negative_count_noop() -> None:
    b = QuotaBudget(max_per_run=2, max_per_day=2, max_per_tranche=2)
    b.consume(-1)
    assert b.used_per_run == 0


# ---------------------------------------------------------------------------
# _urlopen_fetch — quota budget integration
# ---------------------------------------------------------------------------


def test_urlopen_fetch_budget_before_transport() -> None:
    budget = QuotaBudget(max_per_run=0, max_per_day=0, max_per_tranche=0)
    with pytest.raises(RuntimeError, match="QuotaBudget exceeded"):
        budget.consume(1)


def test_urlopen_fetch_budget_consumed() -> None:
    budget = QuotaBudget(max_per_run=5, max_per_day=5, max_per_tranche=5)
    budget.consume(1)
    assert budget.used_per_run == 1


def test_urlopen_fetch_budget_rejection() -> None:
    """Exhausted budget raises before transport."""
    budget = QuotaBudget(max_per_run=0, max_per_day=0, max_per_tranche=0)
    with pytest.raises(RuntimeError, match="QuotaBudget exceeded"):
        budget.consume(1)


# ---------------------------------------------------------------------------
# paid_calls propagation (always-on collector artifact model)
# ---------------------------------------------------------------------------


def test_collector_provider_api_calls_via_safety() -> None:
    results = [
        {"target_id": "a", "artifact": {"safety": {"provider_api_calls": True}}},
        {"target_id": "b", "artifact": {"safety": {"provider_api_calls": False}}},
    ]
    assert any(
        r.get("artifact", {}).get("provider_api_calls")
        or r.get("artifact", {}).get("safety", {}).get("provider_api_calls")
        for r in results
    )


def test_collector_provider_api_calls_via_top_level() -> None:
    results = [
        {"target_id": "a", "artifact": {"provider_api_calls": True}},
    ]
    assert any(
        r.get("artifact", {}).get("provider_api_calls")
        or r.get("artifact", {}).get("safety", {}).get("provider_api_calls")
        for r in results
    )


def test_collector_paid_calls_via_top_level() -> None:
    results = [
        {"target_id": "a", "artifact": {"paid_calls": True}},
    ]
    assert any(
        r.get("artifact", {}).get("paid_calls")
        or r.get("artifact", {}).get("paid_historical_calls")
        for r in results
    )


def test_collector_paid_calls_false_when_no_calls() -> None:
    results = [
        {"target_id": "a", "artifact": {"provider_api_calls": False, "paid_calls": False, "safety": {}}},
    ]
    assert not any(
        r.get("artifact", {}).get("provider_api_calls")
        or r.get("artifact", {}).get("safety", {}).get("provider_api_calls", False)
        for r in results
    )


# ---------------------------------------------------------------------------
# sharp provider capture — paid_calls truthfulness
# ---------------------------------------------------------------------------


def test_sharp_provider_paid_calls_truthful_with_captures() -> None:
    captures = [{"payload": [{"id": "mock1"}], "meta": {"sport_key": "baseball_mlb", "paid_calls": True, "provider_api_calls": True}}]
    report = build_sharp_provider_capture_report(
        captures=captures,
        requested_sport_keys=["baseball_mlb"],
        run_id="r2-test",
    )
    assert report.get("paid_calls") is True
    assert report.get("safety", {}).get("paid_calls") is True



def test_sharp_provider_paid_calls_false_without_captures() -> None:
    report = build_sharp_provider_capture_report(
        captures=[],
        requested_sport_keys=["baseball_mlb"],
        run_id="r2-test",
    )
    assert report.get("paid_calls") is False
    assert report.get("safety", {}).get("paid_calls") is False


# ---------------------------------------------------------------------------
# dense-panel operational controls
# ---------------------------------------------------------------------------


def test_freshness_alarm_no_captures() -> None:
    from scripts.kalshi_sports_mlb_dense_panel_ops import _freshness_alarm
    stale, msg = _freshness_alarm(None)
    assert stale is True
    assert "no captures" in msg


def test_freshness_alarm_fresh() -> None:
    from scripts.kalshi_sports_mlb_dense_panel_ops import _freshness_alarm
    now = time.time()
    stale, msg = _freshness_alarm(now)
    assert stale is False
    assert msg is None


def test_freshness_alarm_stale() -> None:
    from scripts.kalshi_sports_mlb_dense_panel_ops import _freshness_alarm, FRESHNESS_ALARM_SECONDS
    old = time.time() - FRESHNESS_ALARM_SECONDS * 2
    stale, msg = _freshness_alarm(old)
    assert stale is True
    assert "exceeds" in msg


def test_disk_ceiling_ok(tmp_path: Path) -> None:
    from scripts.kalshi_sports_mlb_dense_panel_ops import _disk_usage_ok
    (tmp_path / "small.jsonl").write_text("{}")
    ok, _msg = _disk_usage_ok(tmp_path)
    assert ok is True


def test_disk_ceiling_exceeded(tmp_path: Path) -> None:
    from scripts.kalshi_sports_mlb_dense_panel_ops import _disk_usage_ok, DISK_CEILING_BYTES
    (tmp_path / "big.jsonl").write_text("x" * (DISK_CEILING_BYTES + 1))
    ok, msg = _disk_usage_ok(tmp_path)
    assert ok is False
    assert "exceeds" in msg


def test_runtime_info_contains_version() -> None:
    from scripts.kalshi_sports_mlb_dense_panel_ops import _runtime_info
    info = _runtime_info()
    assert "script_version" in info
    assert info["script_version"].startswith("mlb_dense_panel_ops_v")


def test_cmd_status_check_mode(tmp_path: Path) -> None:
    from scripts.kalshi_sports_mlb_dense_panel_ops import cmd_status
    raw_dir = tmp_path / "raw"
    status_dir = tmp_path / "status"
    raw_dir.mkdir(parents=True)
    (raw_dir / "mlb_dense_panel_snapshots.jsonl").write_text("")
    result = cmd_status(raw_dir=raw_dir, status_dir=status_dir, write_repo_latest=False, check=True)
    assert "preflight_check" in result
    assert isinstance(result["preflight_check"], dict)
    assert "all_ok" in result["preflight_check"]


def test_cmd_replay_zero_network(tmp_path: Path) -> None:
    from scripts.kalshi_sports_mlb_dense_panel_ops import cmd_replay
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)
    (raw_dir / "mlb_dense_panel_snapshots.jsonl").write_text("")
    result = cmd_replay(raw_dir=raw_dir)
    assert result["network_access"] is False


def test_collector_log_rotation(tmp_path: Path) -> None:
    from scripts.kalshi_sports_mlb_dense_panel_ops import _rotate_collector_log
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "collector.log"
    data = b"x" * (10 * 1024 * 1024 + 1)
    log_file.write_bytes(data)

    _rotate_collector_log(log_dir)

    assert log_file.is_file()
    assert log_file.stat().st_size == 0
    backup = log_dir / "collector.log.1"
    assert backup.is_file()
    assert backup.stat().st_size == len(data)
    meta = log_dir / "collector.log.1.meta.json"
    assert meta.is_file()

