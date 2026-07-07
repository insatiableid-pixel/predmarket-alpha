from __future__ import annotations

from pathlib import Path

from scripts.kalshi_sports_historical_consensus_feasibility import build_feasibility

MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def test_five_minute_snapshots_pass_180_second_skew_gate() -> None:
    report = build_feasibility(
        generated_utc="2026-07-06T00:00:00Z",
        snapshot_interval_seconds=300,
        max_allowed_skew_seconds=180,
    )

    assert (
        report["status"]
        == "kalshi_sports_historical_consensus_feasibility_ready_paid_access_unverified"
    )
    assert report["summary"]["max_expected_absolute_skew_seconds"] == 150.0
    assert report["summary"]["skew_gate_pass"] is True
    assert report["summary"]["paid_access_verified"] is False
    assert report["execution_enabled"] is False
    assert report["market_execution"] is False


def test_ten_minute_snapshots_fail_180_second_skew_gate() -> None:
    report = build_feasibility(
        generated_utc="2026-07-06T00:00:00Z",
        snapshot_interval_seconds=600,
        max_allowed_skew_seconds=180,
    )

    assert (
        report["status"] == "kalshi_sports_historical_consensus_feasibility_blocked_snapshot_skew"
    )
    assert report["summary"]["max_expected_absolute_skew_seconds"] == 300.0
    assert report["summary"]["skew_gate_pass"] is False


def test_paid_probe_success_promotes_to_backfill_ready() -> None:
    report = build_feasibility(
        generated_utc="2026-07-06T00:00:00Z",
        snapshot_interval_seconds=300,
        max_allowed_skew_seconds=180,
        paid_probe={"status": "historical_probe_access_verified"},
    )

    assert report["status"] == "kalshi_sports_historical_consensus_feasibility_ready_for_backfill"
    assert report["summary"]["paid_access_verified"] is True
    assert report["paid_historical_calls"] is True


def test_paid_probe_failure_blocks_paid_access_explicitly() -> None:
    report = build_feasibility(
        generated_utc="2026-07-06T00:00:00Z",
        snapshot_interval_seconds=300,
        max_allowed_skew_seconds=180,
        paid_probe={"status": "historical_probe_blocked_http_error", "status_code": 401},
    )

    assert (
        report["status"]
        == "kalshi_sports_historical_consensus_feasibility_blocked_paid_access_probe"
    )
    assert report["summary"]["paid_access_verified"] is False
    assert report["summary"]["paid_probe_status"] == "historical_probe_blocked_http_error"
    assert report["paid_historical_calls"] is True


def test_makefile_exposes_historical_consensus_feasibility_target() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-historical-consensus-feasibility:" in text
    assert "scripts/kalshi_sports_historical_consensus_feasibility.py" in text
    assert "KALSHI_SPORTS_HISTORICAL_CONSENSUS_PROBE ?= 0" in text
