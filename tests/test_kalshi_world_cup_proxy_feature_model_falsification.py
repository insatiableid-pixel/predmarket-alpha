from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "kalshi_world_cup_proxy_feature_model_falsification.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_model_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_world_cup_proxy_feature_model_falsification", SCRIPT_PATH
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


def world_cup_label_row(
    idx: int,
    *,
    ticker: str | None = None,
    consensus: str | None = "yes",
    longshot_fade: str | None = None,
    outcome: int = 1,
    yes_bid: float = 0.61,
    yes_ask: float = 0.63,
):
    hour = 8 + idx // 6
    minute = (idx % 6) * 10
    return {
        "contract_ticker": ticker or f"KXWCGAME-26JUL03MATCH{idx:04d}-YES",
        "event_ticker": f"KXWCGAME-26JUL03MATCH{idx:04d}",
        "series_ticker": "KXWCGAME",
        "market_type": "game",
        "selection_token": "YES",
        "market_consensus_prediction": consensus,
        "longshot_fade_prediction": longshot_fade,
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "yes_mid": round((yes_bid + yes_ask) / 2, 6),
        "yes_outcome": outcome,
        "decision_time": f"2026-07-03T{hour:02d}:{minute:02d}:00Z",
        "close_time": f"2026-07-03T{hour + 1:02d}:{minute:02d}:00Z",
        "settled_time": f"2026-07-03T{hour + 1:02d}:{minute + 1:02d}:00Z",
        "label_status": "labeled_from_public_kalshi_settled_market",
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


def test_world_cup_falsification_promotes_significant_market_structure_rule(
    tmp_path: Path,
) -> None:
    module = load_model_module()
    label_dir = tmp_path / "labels"
    rows = [world_cup_label_row(idx, consensus="yes", outcome=1) for idx in range(40)]
    write_json(label_dir / "packet.json", safe_packet(rows=rows))

    report = module.build_world_cup_proxy_feature_model_falsification(
        label_dir=label_dir,
        generated_utc="2026-07-04T02:00:00Z",
        min_independent_labels=30,
        min_oos_labels=10,
        fdr_alpha=0.10,
    )

    assert (
        report["status"]
        == "world_cup_proxy_feature_model_falsification_ready_with_research_candidates"
    )
    assert report["summary"]["research_candidate_count"] == 1
    consensus_eval = next(
        item
        for item in report["evaluations"]
        if item["model_id"] == "world_cup_market_consensus_directional_accuracy"
    )
    assert consensus_eval["status"] == "research_candidate_fdr_passed"
    assert consensus_eval["oos_accuracy"] == 1.0
    assert consensus_eval["q_value"] <= 0.10


def test_world_cup_falsification_evaluates_longshot_fade_rule_separately(
    tmp_path: Path,
) -> None:
    module = load_model_module()
    label_dir = tmp_path / "labels"
    rows = [
        world_cup_label_row(
            idx,
            consensus=None,
            longshot_fade="no",
            outcome=0,
            yes_bid=0.18,
            yes_ask=0.22,
        )
        for idx in range(40)
    ]
    write_json(label_dir / "packet.json", safe_packet(rows=rows))

    report = module.build_world_cup_proxy_feature_model_falsification(
        label_dir=label_dir,
        generated_utc="2026-07-04T02:00:00Z",
        min_independent_labels=30,
        min_oos_labels=10,
        fdr_alpha=0.10,
    )

    fade_eval = next(
        item
        for item in report["evaluations"]
        if item["model_id"] == "world_cup_longshot_fade_directional_accuracy"
    )
    assert fade_eval["status"] == "research_candidate_fdr_passed"
    assert fade_eval["oos_accuracy"] == 1.0


def test_world_cup_falsification_blocks_missing_labels(tmp_path: Path) -> None:
    module = load_model_module()
    label_dir = tmp_path / "empty"
    label_dir.mkdir()

    report = module.build_world_cup_proxy_feature_model_falsification(label_dir=label_dir)

    assert report["status"] == "world_cup_proxy_feature_model_falsification_blocked_missing_labels"
    gates = {item["name"]: item for item in report["gates"]}
    assert gates["independent_label_minimum"]["status"] == "blocked"


def test_world_cup_falsification_rejects_rows_without_proxy_prediction(
    tmp_path: Path,
) -> None:
    module = load_model_module()
    label_dir = tmp_path / "labels"
    rows = [
        world_cup_label_row(idx, consensus=None, longshot_fade=None, outcome=1) for idx in range(5)
    ]
    write_json(label_dir / "packet.json", safe_packet(rows=rows))

    report = module.build_world_cup_proxy_feature_model_falsification(
        label_dir=label_dir,
        min_independent_labels=1,
        min_oos_labels=1,
    )

    assert report["summary"]["raw_label_row_count"] == 5
    assert report["summary"]["valid_label_row_count"] == 0
    assert report["summary"]["invalid_label_row_count"] == 5
    assert report["status"] == "world_cup_proxy_feature_model_falsification_blocked_missing_labels"


def test_world_cup_falsification_rows_remain_research_only(tmp_path: Path) -> None:
    module = load_model_module()
    label_dir = tmp_path / "labels"
    rows = [world_cup_label_row(idx, consensus="yes", outcome=1) for idx in range(40)]
    write_json(label_dir / "packet.json", safe_packet(rows=rows))

    report = module.build_world_cup_proxy_feature_model_falsification(
        label_dir=label_dir,
        min_independent_labels=30,
        min_oos_labels=10,
    )

    for item in report["evaluations"]:
        assert item["usable"] is False
        assert item["calibrated_probability"] is None
        assert item["expected_value_per_contract"] is None
    gates = {item["name"]: item for item in report["gates"]}
    assert gates["no_probability_ev_or_execution_claims"]["status"] == "pass"


def test_world_cup_proxy_falsification_makefile_targets_are_registered() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-world-cup-proxy-feature-model-falsification" in text
    assert "KALSHI_WORLD_CUP_PROXY_MODEL_OUT_DIR" in text
