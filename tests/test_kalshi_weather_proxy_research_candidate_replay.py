"""Artifact-replay tests for the weather proxy research candidate replay script.

Tests the replay pipeline using the engine's build_replay_calibration with
WeatherFamily's prediction_rule and weather_cluster_key_composer.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "kalshi_weather_proxy_research_candidate_replay.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_replay_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_weather_proxy_research_candidate_replay", SCRIPT_PATH
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


def model_report(*, research_candidate: bool = True):
    status = (
        "research_candidate_fdr_passed" if research_candidate else "testable_research_candidate"
    )
    return safe_packet(
        status="weather_proxy_feature_model_falsification_ready_with_research_candidates"
        if research_candidate
        else "weather_proxy_feature_model_falsification_ready_no_research_candidates",
        method={"test_fraction": 0.30},
        summary={"research_candidate_count": 1 if research_candidate else 0},
        evaluations=[
            {
                "model_id": "weather_bracket_directional_accuracy",
                "status": status,
                "independent_label_count": 40,
                "oos_count": 12,
                "oos_correct_count": 12 if research_candidate else 6,
                "oos_accuracy": 1.0 if research_candidate else 0.5,
                "p_value": 0.001,
                "q_value": 0.001,
                "usable": False,
                "calibrated_probability": None,
                "expected_value_per_contract": None,
            }
        ],
    )


def weather_label_row(
    idx: int,
    *,
    predicted_side: str = "no",
    bracket_probability: float = 0.35,
    outcome: int = 0,
    yes_ask: float = 0.48,
):
    """Create a synthetic weather label row."""
    hour = 8 + idx // 12
    minute = (idx % 12) * 5
    return {
        "contract_ticker": f"KXHIGH-26JUL03-STN{idx:02d}-90",
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


class TestWeatherReplay:
    """Tests for weather proxy replay via the engine."""

    def test_replay_accepts_weather_family(self, tmp_path: Path) -> None:
        """Weather replay runs through engine.build_replay_calibration."""
        module = load_replay_module()
        label_dir = tmp_path / "labels"
        model_path = tmp_path / "model.json"
        rows = [
            weather_label_row(idx, predicted_side="no", outcome=0, bracket_probability=0.35)
            for idx in range(40)
        ]
        write_json(label_dir / "packet_01.json", safe_packet(rows=rows))
        write_json(model_path, model_report(research_candidate=True))
        report = module.build_weather_proxy_research_candidate_replay(
            label_dir=label_dir,
            model_falsification_path=model_path,
        )
        assert report["status"].startswith("weather_proxy_")
        assert report["research_only"] is True
        assert report["execution_enabled"] is False
        assert "replay_rows" in report
        assert "calibration" in report

    def test_replay_rows_have_all_in_cost(self, tmp_path: Path) -> None:
        """Every replay row has all-in cost computed."""
        module = load_replay_module()
        label_dir = tmp_path / "labels"
        model_path = tmp_path / "model.json"
        rows = [
            weather_label_row(idx, predicted_side="no", outcome=0, bracket_probability=0.35)
            for idx in range(40)
        ]
        write_json(label_dir / "packet_01.json", safe_packet(rows=rows))
        write_json(model_path, model_report(research_candidate=True))
        report = module.build_weather_proxy_research_candidate_replay(
            label_dir=label_dir,
            model_falsification_path=model_path,
        )
        for row in report.get("replay_rows", []):
            assert row.get("all_in_cost") is not None

    def test_replay_rows_usable_false(self, tmp_path: Path) -> None:
        """All replay rows have usable=False."""
        module = load_replay_module()
        label_dir = tmp_path / "labels"
        model_path = tmp_path / "model.json"
        rows = [
            weather_label_row(idx, predicted_side="no", outcome=0, bracket_probability=0.35)
            for idx in range(40)
        ]
        write_json(label_dir / "packet_01.json", safe_packet(rows=rows))
        write_json(model_path, model_report(research_candidate=True))
        report = module.build_weather_proxy_research_candidate_replay(
            label_dir=label_dir,
            model_falsification_path=model_path,
        )
        for row in report.get("replay_rows", []):
            assert row.get("usable") is False

    def test_replay_has_correlation_cluster_key(self, tmp_path: Path) -> None:
        """Replay rows have weather-specific correlation cluster key (station|bracket|date)."""
        module = load_replay_module()
        label_dir = tmp_path / "labels"
        model_path = tmp_path / "model.json"
        rows = [
            weather_label_row(idx, predicted_side="no", outcome=0, bracket_probability=0.35)
            for idx in range(40)
        ]
        write_json(label_dir / "packet_01.json", safe_packet(rows=rows))
        write_json(model_path, model_report(research_candidate=True))
        report = module.build_weather_proxy_research_candidate_replay(
            label_dir=label_dir,
            model_falsification_path=model_path,
        )
        for row in report.get("replay_rows", []):
            key = row.get("correlation_cluster_key", "")
            assert "|" in key
            parts = key.split("|")
            assert len(parts) >= 3

    def test_replay_blocked_no_research_candidate(self, tmp_path: Path) -> None:
        """Without a research candidate, replay is blocked."""
        module = load_replay_module()
        label_dir = tmp_path / "labels"
        model_path = tmp_path / "model.json"
        rows = [
            weather_label_row(idx, predicted_side="no", outcome=0, bracket_probability=0.35)
            for idx in range(40)
        ]
        write_json(label_dir / "packet_01.json", safe_packet(rows=rows))
        write_json(model_path, model_report(research_candidate=False))
        report = module.build_weather_proxy_research_candidate_replay(
            label_dir=label_dir,
            model_falsification_path=model_path,
        )
        assert "blocked" in (report.get("status") or "")

    def test_safety_flags(self, tmp_path: Path) -> None:
        """Safety flags are set correctly."""
        module = load_replay_module()
        label_dir = tmp_path / "labels"
        model_path = tmp_path / "model.json"
        rows = [
            weather_label_row(idx, predicted_side="no", outcome=0, bracket_probability=0.35)
            for idx in range(40)
        ]
        write_json(label_dir / "packet_01.json", safe_packet(rows=rows))
        write_json(model_path, model_report(research_candidate=True))
        report = module.build_weather_proxy_research_candidate_replay(
            label_dir=label_dir,
            model_falsification_path=model_path,
        )
        assert report.get("research_only") is True
        assert report.get("execution_enabled") is False
        safety = report.get("safety", {})
        assert safety.get("market_execution") is False
        assert safety.get("account_or_order_paths") is False
        assert safety.get("database_writes") is False

    def test_makefile_exposes_target(self) -> None:
        """Makefile has kalshi-weather-proxy-research-candidate-replay target."""
        text = MAKEFILE_PATH.read_text(encoding="utf-8")
        assert "kalshi-weather-proxy-research-candidate-replay" in text
