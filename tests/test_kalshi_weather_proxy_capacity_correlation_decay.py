"""Artifact-replay tests for the weather proxy CCD script.

Tests capacity, correlation, and decay gates using the engine's ask_levels
and build_decay_summary with weather-specific cluster keys.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "kalshi_weather_proxy_capacity_correlation_decay.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_ccd_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_weather_proxy_capacity_correlation_decay", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def make_feature_packet():
    """Build a synthetic weather feature packet."""
    return {
        "schema_version": 1,
        "generated_utc": "NOON_DATETIME",
        "status": "weather_proxy_feature_packet_ready",
        "feature_rows": [
            {
                "contract_ticker": "KXHIGH-26JUL03-KNYC-90",
                "event_ticker": "KXHIGH-26JUL03-KNYC",
                "series_ticker": "KXHIGH",
                "weather_family": "KXHIGH",
                "close_time": "EVENING_DATETIME",
                "expected_expiration_time": "2026-07-03T21:00:00Z",
                "fresh_time_to_close_hours": 8.0,
                "yes_bid": 0.45,
                "yes_ask": 0.55,
                "no_bid": 0.42,
                "no_ask": 0.52,
                "yes_spread": 0.10,
                "station_id": "KNYC",
                "forecast_high": 78.0,
                "forecast_low": 55.0,
                "observation_temperature": 72.0,
                "bracket_probability": 0.60,
                "predicted_side": "yes",
                "feature_status": "weather_features_ready",
                "usable": False,
                "calibrated_probability": None,
                "expected_value_per_contract": None,
            },
            {
                "contract_ticker": "KXLOW-26JUL03-KORD-32",
                "event_ticker": "KXLOW-26JUL03-KORD",
                "series_ticker": "KXLOW",
                "weather_family": "KXLOW",
                "close_time": "EVENING_DATETIME",
                "expected_expiration_time": "2026-07-03T21:00:00Z",
                "fresh_time_to_close_hours": 8.0,
                "yes_bid": 0.35,
                "yes_ask": 0.42,
                "no_bid": 0.55,
                "no_ask": 0.65,
                "yes_spread": 0.07,
                "station_id": "KORD",
                "forecast_high": 45.0,
                "forecast_low": 28.0,
                "observation_temperature": 30.0,
                "bracket_probability": 0.65,
                "predicted_side": "no",
                "feature_status": "weather_features_ready",
                "usable": False,
                "calibrated_probability": None,
                "expected_value_per_contract": None,
            },
        ],
        "research_only": True,
        "execution_enabled": False,
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }


def make_replay_report():
    """Build a synthetic weather replay report."""
    return {
        "schema_version": 1,
        "status": "weather_proxy_research_candidate_replay_blocked_predeployment_gates",
        "summary": {
            "conservative_calibrated_side_probability": 0.65,
            "independent_contract_label_count": 200,
            "decay_bucket_count": 5,
            "decay_status": "recent_bucket_not_worse_than_random",
            "recent_bucket_key": "RECENT_BUCKET_PLACEHOLDER",
            "recent_bucket_accuracy": 0.62,
            "recent_bucket_label_count": 30,
            "total_decay_labels": 200,
            "cumulative_decay_accuracy": 0.58,
            "passing_bucket_count": 3,
            "decay_buckets": [
                {"bucket": "2026-07-03T18:00Z", "label_count": 40, "accuracy": 0.55},
                {"bucket": "2026-07-03T19:00Z", "label_count": 50, "accuracy": 0.60},
                {"bucket": "EVENING_BUCKET", "label_count": 30, "accuracy": 0.62},
            ],
        },
        "research_only": True,
        "execution_enabled": False,
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }


class TestWeatherCCD:
    """Tests for weather proxy capacity correlation decay."""

    def test_builds_report_with_capacity_rows(self, tmp_path: Path) -> None:
        """CCD builds a report with capacity rows using engine's ask_levels."""
        module = load_ccd_module()
        fp_path = tmp_path / "feature_packet.json"
        replay_path = tmp_path / "replay.json"
        ob_dir = tmp_path / "orderbooks"
        ob_dir.mkdir()
        write_json(fp_path, make_feature_packet())
        write_json(replay_path, make_replay_report())
        report = module.build_weather_proxy_capacity_correlation_decay(
            feature_packet_path=fp_path,
            replay_path=replay_path,
            raw_orderbook_dir=ob_dir,
        )
        assert report["status"].startswith("weather_proxy_")
        assert report["research_only"] is True
        assert report["execution_enabled"] is False
        assert "capacity_rows" in report
        assert "gates" in report

    def test_capacity_rows_have_weather_cluster_key(self, tmp_path: Path) -> None:
        """Capacity rows use weather_cluster_key_composer (station|bracket|date)."""
        module = load_ccd_module()
        fp_path = tmp_path / "feature_packet.json"
        replay_path = tmp_path / "replay.json"
        ob_dir = tmp_path / "orderbooks"
        ob_dir.mkdir()
        write_json(fp_path, make_feature_packet())
        write_json(replay_path, make_replay_report())
        report = module.build_weather_proxy_capacity_correlation_decay(
            feature_packet_path=fp_path,
            replay_path=replay_path,
            raw_orderbook_dir=ob_dir,
        )
        for row in report.get("capacity_rows", []):
            key = row.get("correlation_cluster_key", "")
            assert "|" in key

    def test_capacity_rows_usable_false(self, tmp_path: Path) -> None:
        """All capacity rows have usable=False."""
        module = load_ccd_module()
        fp_path = tmp_path / "feature_packet.json"
        replay_path = tmp_path / "replay.json"
        ob_dir = tmp_path / "orderbooks"
        ob_dir.mkdir()
        write_json(fp_path, make_feature_packet())
        write_json(replay_path, make_replay_report())
        report = module.build_weather_proxy_capacity_correlation_decay(
            feature_packet_path=fp_path,
            replay_path=replay_path,
            raw_orderbook_dir=ob_dir,
        )
        for row in report.get("capacity_rows", []):
            assert row.get("usable") is False

    def test_safety_flags(self, tmp_path: Path) -> None:
        """Safety flags are set correctly."""
        module = load_ccd_module()
        fp_path = tmp_path / "feature_packet.json"
        replay_path = tmp_path / "replay.json"
        ob_dir = tmp_path / "orderbooks"
        ob_dir.mkdir()
        write_json(fp_path, make_feature_packet())
        write_json(replay_path, make_replay_report())
        report = module.build_weather_proxy_capacity_correlation_decay(
            feature_packet_path=fp_path,
            replay_path=replay_path,
            raw_orderbook_dir=ob_dir,
        )
        assert report.get("research_only") is True
        assert report.get("execution_enabled") is False
        safety = report.get("safety", {})
        assert safety.get("market_execution") is False

    def test_makefile_exposes_target(self) -> None:
        """Makefile has kalshi-weather-proxy-capacity-correlation-decay target."""
        text = MAKEFILE_PATH.read_text(encoding="utf-8")
        assert "kalshi-weather-proxy-capacity-correlation-decay" in text

    def test_blocked_no_candidates_on_out_of_window(self, tmp_path: Path) -> None:
        """When all candidates are out of window, CCD is blocked."""
        module = load_ccd_module()
        fp_path = tmp_path / "feature_packet.json"
        replay_path = tmp_path / "replay.json"
        ob_dir = tmp_path / "orderbooks"
        ob_dir.mkdir()
        fp = make_feature_packet()
        # Set close_time far in the past
        for row in fp.get("feature_rows", []):
            row["close_time"] = "YESTERDAY_EVENING"
        write_json(fp_path, fp)
        write_json(replay_path, make_replay_report())
        report = module.build_weather_proxy_capacity_correlation_decay(
            feature_packet_path=fp_path,
            replay_path=replay_path,
            raw_orderbook_dir=ob_dir,
            max_close_hours=1.0,
        )
        assert "blocked" in (report.get("status") or "")
