"""Artifact-replay tests for the weather proxy falsification script.

Tests the falsification pipeline using the engine's build_falsification with
WeatherFamily's prediction_rule and model_evaluators. Mirrors the sports
falsification test pattern.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "kalshi_weather_proxy_feature_model_falsification.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_model_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_weather_proxy_feature_model_falsification", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def safe_packet(rows=None, **overrides):
    payload = {
        "schema_version": 1,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "rows": rows or [],
        "safety": {
            "research_only": True,
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
            "staking_or_sizing_guidance": False,
        },
    }
    payload.update(overrides)
    return payload


def weather_label_row(
    idx: int,
    *,
    ticker: str | None = None,
    predicted_side: str = "no",
    bracket_probability: float = 0.35,
    outcome: int = 0,
    yes_ask: float = 0.48,
):
    """Create a synthetic weather label row."""
    hour = 8 + idx // 6
    minute = (idx % 6) * 10
    return {
        "contract_ticker": ticker or f"KXHIGH-26JUL03-STN{idx:02d}-90",
        "event_ticker": f"KXHIGH-26JUL03-STN{idx:02d}",
        "series_ticker": "KXHIGH",
        "weather_family": "KXHIGH",
        "station_id": f"STN{idx:02d}",
        "bracket_probability": bracket_probability,
        "predicted_side": predicted_side,
        "yes_ask": yes_ask,
        "yes_bid": 0.40,
        "yes_outcome": outcome,
        "decision_time": f"2026-07-03T{hour:02d}:{minute:02d}:00Z",
        "close_time": f"2026-07-03T{hour + 2:02d}:{minute:02d}:00Z",
        "label_status": "labeled_from_public_kalshi_settled_market",
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


# ── Tests ─────────────────────────────────────────────────────────────────


class TestWeatherFalsification:
    """Tests for weather proxy falsification via the engine."""

    def test_accepts_weather_family_descriptor(self, tmp_path: Path) -> None:
        """Weather falsification runs weather-specific model evaluators through engine.build_falsification."""
        module = load_model_module()
        label_dir = tmp_path / "labels"
        rows = [
            weather_label_row(idx, predicted_side="no", outcome=0, bracket_probability=0.35)
            for idx in range(20)
        ]
        write_json(label_dir / "packet_01.json", safe_packet(rows=rows))
        report = module.build_weather_proxy_feature_model_falsification(
            label_dir=label_dir,
            min_independent_labels=30,
            min_oos_labels=10,
        )
        assert report["status"].startswith("weather_proxy_")
        assert report["research_only"] is True
        assert report["execution_enabled"] is False
        assert "evaluations" in report
        assert "gates" in report

    def test_bracket_directional_evaluator_present(self, tmp_path: Path) -> None:
        """The weather bracket directional evaluator appears in evaluations."""
        module = load_model_module()
        label_dir = tmp_path / "labels"
        rows = [
            weather_label_row(idx, predicted_side="no", outcome=0, bracket_probability=0.35)
            for idx in range(40)
        ]
        write_json(label_dir / "packet_01.json", safe_packet(rows=rows))
        report = module.build_weather_proxy_feature_model_falsification(
            label_dir=label_dir,
            min_independent_labels=30,
            min_oos_labels=10,
        )
        model_ids = [e.get("model_id") for e in report.get("evaluations", [])]
        assert "weather_bracket_directional_accuracy" in model_ids

    def test_market_baseline_evaluator_present(self, tmp_path: Path) -> None:
        """The weather market baseline evaluator appears in evaluations."""
        module = load_model_module()
        label_dir = tmp_path / "labels"
        rows = [
            weather_label_row(idx, predicted_side="no", outcome=0, bracket_probability=0.35)
            for idx in range(40)
        ]
        write_json(label_dir / "packet_01.json", safe_packet(rows=rows))
        report = module.build_weather_proxy_feature_model_falsification(
            label_dir=label_dir,
            min_independent_labels=30,
            min_oos_labels=10,
        )
        model_ids = [e.get("model_id") for e in report.get("evaluations", [])]
        assert "weather_market_yes_ask_probability_baseline" in model_ids

    def test_blocked_missing_labels(self, tmp_path: Path) -> None:
        """Empty label directory yields a blocked status, not a crash."""
        module = load_model_module()
        label_dir = tmp_path / "empty_labels"
        label_dir.mkdir()
        report = module.build_weather_proxy_feature_model_falsification(label_dir=label_dir)
        assert "blocked" in (report.get("status") or "")

    def test_rejects_label_rows_with_station_ticker_mismatch(self, tmp_path: Path) -> None:
        """A weather label must not survive when station provenance contradicts the ticker."""
        module = load_model_module()
        label_dir = tmp_path / "labels"
        row = weather_label_row(
            0,
            ticker="KXHIGHMIA-26JUL03-B90.5",
            predicted_side="yes",
            bracket_probability=0.75,
            outcome=1,
        )
        row.update(
            {
                "event_ticker": "KXHIGHMIA-26JUL03",
                "series_ticker": "KXHIGHMIA",
                "weather_family": "KXHIGHMIA",
                "station_id": "KNYC",
            }
        )
        write_json(label_dir / "packet_01.json", safe_packet(rows=[row]))

        report = module.build_weather_proxy_feature_model_falsification(
            label_dir=label_dir,
            min_independent_labels=1,
            min_oos_labels=1,
        )

        assert report["summary"]["raw_label_row_count"] == 1
        assert report["summary"]["valid_label_row_count"] == 0
        assert report["summary"]["station_mismatch_label_row_count"] == 1
        gates = {item["name"]: item for item in report["gates"]}
        assert gates["station_provenance_matches_ticker"]["status"] == "blocked"
        assert (
            report["status"] == "weather_proxy_feature_model_falsification_blocked_missing_labels"
        )

    def test_every_row_usable_false(self, tmp_path: Path) -> None:
        """Every evaluation row has usable=False and no calibrated probability."""
        module = load_model_module()
        label_dir = tmp_path / "labels"
        rows = [
            weather_label_row(idx, predicted_side="no", outcome=0, bracket_probability=0.35)
            for idx in range(40)
        ]
        write_json(label_dir / "packet_01.json", safe_packet(rows=rows))
        report = module.build_weather_proxy_feature_model_falsification(
            label_dir=label_dir,
            min_independent_labels=30,
            min_oos_labels=10,
        )
        for item in report.get("evaluations", []):
            assert item.get("usable") is False
            assert item.get("calibrated_probability") is None

    def test_safety_flags(self, tmp_path: Path) -> None:
        """Safety flags are set correctly."""
        module = load_model_module()
        label_dir = tmp_path / "labels"
        rows = [
            weather_label_row(idx, predicted_side="no", outcome=0, bracket_probability=0.35)
            for idx in range(40)
        ]
        write_json(label_dir / "packet_01.json", safe_packet(rows=rows))
        report = module.build_weather_proxy_feature_model_falsification(
            label_dir=label_dir,
            min_independent_labels=30,
            min_oos_labels=10,
        )
        assert report.get("research_only") is True
        assert report.get("execution_enabled") is False
        assert report.get("market_execution") is not True
        assert report.get("account_or_order_paths") is not True
        safety = report.get("safety", {})
        assert safety.get("market_execution") is False
        assert safety.get("account_or_order_paths") is False
        assert safety.get("database_writes") is False

    def test_makefile_exposes_target(self) -> None:
        """Makefile has kalshi-weather-proxy-feature-model-falsification target."""
        text = MAKEFILE_PATH.read_text(encoding="utf-8")
        assert "kalshi-weather-proxy-feature-model-falsification" in text

    def test_report_status_uses_weather_prefix(self, tmp_path: Path) -> None:
        """Status strings use weather_proxy prefix."""
        module = load_model_module()
        label_dir = tmp_path / "labels"
        rows = [
            weather_label_row(idx, predicted_side="no", outcome=0, bracket_probability=0.35)
            for idx in range(20)
        ]
        write_json(label_dir / "packet_01.json", safe_packet(rows=rows))
        report = module.build_weather_proxy_feature_model_falsification(
            label_dir=label_dir,
            min_independent_labels=30,
            min_oos_labels=10,
        )
        assert report["status"].startswith("weather_proxy")
