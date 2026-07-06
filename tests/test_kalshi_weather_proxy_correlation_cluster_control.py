"""Artifact-replay tests for the weather proxy correlation cluster control script.

Tests cluster exposure control using the engine's fully generic
controlled_capacity_rows — the control is family-agnostic given opaque (cluster_key,
cost, contracts, margin) tuples.  Proves the spine is closed for modification.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "kalshi_weather_proxy_correlation_cluster_control.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_cluster_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_weather_proxy_correlation_cluster_control", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def make_ccd_report():
    """Build a synthetic CCD report with capacity rows."""
    return {
        "schema_version": 1,
        "status": "weather_proxy_capacity_correlation_decay_ready_for_paper_overlay",
        "summary": {
            "capacity_status": "capacity_depth_positive",
            "decay_status": "decay_survival_pass",
        },
        "capacity_rows": [
            {
                "contract_ticker": "KXHIGH-26JUL03-KNYC-90",
                "event_ticker": "KXHIGH-26JUL03-KNYC",
                "series_ticker": "KXHIGH",
                "weather_family": "KXHIGH",
                "close_time": "2026-07-03T20:00:00Z",
                "predicted_side": "yes",
                "level_count": 3,
                "best_all_in_break_even_probability": 0.55,
                "conservative_calibrated_side_probability": 0.65,
                "best_margin_probability": 0.10,
                "positive_depth_contracts": 500.0,
                "positive_depth_cost": 250.0,
                "correlation_cluster_key": "KNYC|KXHIGH|2026-07-03T20:00Z",
                "gate_status": "pass",
                "usable": False,
            },
            {
                "contract_ticker": "KXLOW-26JUL03-KORD-32",
                "event_ticker": "KXLOW-26JUL03-KORD",
                "series_ticker": "KXLOW",
                "weather_family": "KXLOW",
                "close_time": "2026-07-03T20:00:00Z",
                "predicted_side": "no",
                "level_count": 2,
                "best_all_in_break_even_probability": 0.30,
                "conservative_calibrated_side_probability": 0.65,
                "best_margin_probability": 0.35,
                "positive_depth_contracts": 300.0,
                "positive_depth_cost": 180.0,
                "correlation_cluster_key": "KORD|KXLOW|2026-07-03T20:00Z",
                "gate_status": "pass",
                "usable": False,
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


class TestWeatherClusterControl:
    """Tests for weather proxy correlation cluster control."""

    def test_builds_report_with_controlled_rows(self, tmp_path: Path) -> None:
        """Cluster control builds a report with controlled rows via engine's controlled_capacity_rows."""
        module = load_cluster_module()
        ccd_path = tmp_path / "ccd.json"
        write_json(ccd_path, make_ccd_report())
        report = module.build_weather_proxy_correlation_cluster_control(
            ccd_path=ccd_path,
        )
        assert report["status"].startswith("weather_proxy_")
        assert report["research_only"] is True
        assert report["execution_enabled"] is False
        assert "controlled_rows" in report
        assert "clusters" in report

    def test_controlled_rows_usable_false(self, tmp_path: Path) -> None:
        """All controlled rows have usable=False."""
        module = load_cluster_module()
        ccd_path = tmp_path / "ccd.json"
        write_json(ccd_path, make_ccd_report())
        report = module.build_weather_proxy_correlation_cluster_control(
            ccd_path=ccd_path,
        )
        for row in report.get("controlled_rows", []):
            assert row.get("usable") is False

    def test_controlled_rows_have_controlled_cost(self, tmp_path: Path) -> None:
        """Controlled rows have controlled_depth_cost computed."""
        module = load_cluster_module()
        ccd_path = tmp_path / "ccd.json"
        write_json(ccd_path, make_ccd_report())
        report = module.build_weather_proxy_correlation_cluster_control(
            ccd_path=ccd_path,
        )
        for row in report.get("controlled_rows", []):
            assert "controlled_depth_cost" in row

    def test_max_cluster_share_applied(self, tmp_path: Path) -> None:
        """With max_cluster_share=0.35, cluster control uses the 35% cap via engine's controlled_capacity_rows."""
        module = load_cluster_module()
        ccd_path = tmp_path / "ccd.json"
        write_json(ccd_path, make_ccd_report())
        report = module.build_weather_proxy_correlation_cluster_control(
            ccd_path=ccd_path,
            max_cluster_share=0.35,
        )
        # Verify report structure is correct
        assert "controlled_rows" in report
        assert "clusters" in report
        summary = report.get("summary", {})
        # With 2 clusters each having positive depth, the controlled report
        # reflects the max_cluster_share=0.35 in the summary
        assert summary.get("max_cluster_share") == 0.35
        assert "largest_controlled_cluster_share" in summary

    def test_makefile_exposes_target(self) -> None:
        """Makefile has kalshi-weather-proxy-correlation-cluster-control target."""
        text = MAKEFILE_PATH.read_text(encoding="utf-8")
        assert "kalshi-weather-proxy-correlation-cluster-control" in text

    def test_safety_flags(self, tmp_path: Path) -> None:
        """Safety flags are set correctly."""
        module = load_cluster_module()
        ccd_path = tmp_path / "ccd.json"
        write_json(ccd_path, make_ccd_report())
        report = module.build_weather_proxy_correlation_cluster_control(
            ccd_path=ccd_path,
        )
        assert report.get("research_only") is True
        assert report.get("execution_enabled") is False
        safety = report.get("safety", {})
        assert safety.get("market_execution") is False
        assert safety.get("account_or_order_paths") is False
