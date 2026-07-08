from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

REPLAY_PATH = SCRIPTS / "kalshi_world_cup_proxy_research_candidate_replay.py"
CCD_PATH = SCRIPTS / "kalshi_world_cup_proxy_capacity_correlation_decay.py"
CLUSTER_PATH = SCRIPTS / "kalshi_world_cup_proxy_correlation_cluster_control.py"
LEDGER_PATH = SCRIPTS / "kalshi_contract_ev_ledger.py"
MAKEFILE_PATH = ROOT / "Makefile"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def safe_packet(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "rows": rows,
        "safety": {
            "research_only": True,
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
            "staking_or_sizing_guidance": False,
        },
    }


def world_cup_label(idx: int, *, outcome: int = 0) -> dict[str, Any]:
    hour = 1 + idx // 6
    minute = (idx % 6) * 5
    return {
        "contract_ticker": f"KXWCGAME-26JUL04AAABBB-{idx:03d}",
        "event_ticker": f"KXWCGAME-26JUL04AAABBB-{idx:03d}",
        "series_ticker": "KXWCGAME",
        "market_type": "game",
        "selection_token": f"S{idx:03d}",
        "league": "WORLD_CUP",
        "market_consensus_prediction": "yes",
        "longshot_fade_prediction": "no",
        "yes_bid": 0.18,
        "yes_ask": 0.20,
        "yes_mid": 0.19,
        "yes_outcome": outcome,
        "decision_time": f"2026-07-04T{hour:02d}:{minute:02d}:00Z",
        "close_time": f"2026-07-04T{hour:02d}:{minute + 1:02d}:00Z",
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


def world_cup_model_report() -> dict[str, Any]:
    return safe_packet([]) | {
        "status": "world_cup_proxy_feature_model_falsification_ready_with_research_candidates",
        "method": {"test_fraction": 0.30},
        "summary": {"research_candidate_count": 2},
        "evaluations": [
            {
                "model_id": "world_cup_market_consensus_directional_accuracy",
                "status": "research_candidate_fdr_passed",
                "independent_label_count": 40,
                "oos_count": 12,
                "oos_correct_count": 7,
                "oos_accuracy": 7 / 12,
                "p_value": 0.1,
                "q_value": 0.01,
                "usable": False,
            },
            {
                "model_id": "world_cup_longshot_fade_directional_accuracy",
                "status": "research_candidate_fdr_passed",
                "independent_label_count": 40,
                "oos_count": 12,
                "oos_correct_count": 12,
                "oos_accuracy": 1.0,
                "p_value": 0.0001,
                "q_value": 0.0001,
                "usable": False,
            },
        ],
    }


def test_world_cup_replay_uses_family_model_without_clobbering_sports_names(
    tmp_path: Path,
) -> None:
    module = load_module("kalshi_world_cup_proxy_research_candidate_replay", REPLAY_PATH)
    label_dir = tmp_path / "labels"
    model_path = tmp_path / "model.json"
    write_json(label_dir / "labels.json", safe_packet([world_cup_label(i) for i in range(40)]))
    write_json(model_path, world_cup_model_report())

    report = module.build_world_cup_proxy_research_candidate_replay(
        label_dir=label_dir,
        model_falsification_path=model_path,
        generated_utc="2026-07-04T10:00:00Z",
        min_side_oos_labels=3,
        min_decay_buckets=2,
        min_decay_labels=10,
    )

    assert (
        report["status"] == "world_cup_proxy_research_candidate_replay_blocked_predeployment_gates"
    )
    assert report["family_id"] == "world_cup_soccer"
    assert report["summary"]["selected_replay_model_id"] == (
        "world_cup_longshot_fade_directional_accuracy"
    )
    assert {row["predicted_side"] for row in report["replay_rows"]} == {"no"}
    assert all(row["usable"] is False for row in report["replay_rows"])


def test_world_cup_ccd_reads_observation_packet_current_rows(tmp_path: Path) -> None:
    module = load_module("kalshi_world_cup_proxy_capacity_correlation_decay", CCD_PATH)
    feature_path = write_json(
        tmp_path / "world_cup_obs.json",
        {
            "status": "world_cup_proxy_observation_loop_label_rows_ready",
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "safety": {
                "research_only": True,
                "market_execution": False,
                "account_or_order_paths": False,
                "database_writes": False,
            },
            "observation_packet": {
                "rows": [
                    {
                        "contract_ticker": "KXWCGAME-26JUL09AAABBB-AAA",
                        "event_ticker": "KXWCGAME-26JUL09AAABBB",
                        "series_ticker": "KXWCGAME",
                        "market_consensus_prediction": "yes",
                        "yes_bid": 0.38,
                        "yes_ask": 0.40,
                        "close_time": "2026-07-09T21:00:00Z",
                    }
                ]
            },
        },
    )
    replay_path = write_json(
        tmp_path / "world_cup_replay.json",
        {
            "status": "world_cup_proxy_research_candidate_replay_blocked_predeployment_gates",
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "summary": {
                "selected_replay_model_id": "world_cup_market_consensus_directional_accuracy",
                "conservative_calibrated_side_probability": 0.75,
                "decay_status": "recent_bucket_not_worse_than_random",
                "independent_contract_label_count": 120,
                "decay_bucket_count": 3,
            },
            "safety": {
                "research_only": True,
                "market_execution": False,
                "account_or_order_paths": False,
                "database_writes": False,
            },
        },
    )
    raw_dir = tmp_path / "orderbooks"
    write_json(
        raw_dir / "kalshi_sports_proxy_orderbooks_latest.json",
        {
            "status": "kalshi_public_orderbook_fetch_ok",
            "orderbooks": [
                {
                    "ticker": "KXWCGAME-26JUL09AAABBB-AAA",
                    "payload": {"orderbook": {"no": [[60, 10]]}},
                }
            ],
            "errors": [],
        },
    )

    report = module.build_world_cup_proxy_capacity_correlation_decay(
        feature_packet_path=feature_path,
        replay_path=replay_path,
        raw_orderbook_dir=raw_dir,
        generated_utc="2026-07-08T00:00:00Z",
        max_close_hours=72,
        max_tickers=10,
    )

    assert (
        report["status"]
        == "world_cup_proxy_capacity_correlation_decay_blocked_correlation_concentration"
    )
    assert report["summary"]["candidate_row_count"] == 1
    assert report["summary"]["capacity_status"] == "capacity_depth_positive"
    assert report["capacity_rows"][0]["source_model_id"] == (
        "world_cup_market_consensus_directional_accuracy"
    )
    assert report["capacity_rows"][0]["league"] == "WORLD_CUP"


def test_world_cup_cluster_wrapper_emits_world_cup_ready_status(tmp_path: Path) -> None:
    module = load_module("kalshi_world_cup_proxy_correlation_cluster_control", CLUSTER_PATH)
    ccd_path = write_json(
        tmp_path / "world_cup_ccd.json",
        {
            "status": "world_cup_proxy_capacity_correlation_decay_ready_for_paper_overlay",
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "summary": {
                "capacity_status": "capacity_depth_positive",
                "decay_status": "decay_survival_pass",
            },
            "capacity_rows": [
                {
                    "contract_ticker": f"KXWCGAME-26JUL09AAABBB-{idx}",
                    "event_ticker": f"KXWCGAME-26JUL09AAABBB-{idx}",
                    "league": "WORLD_CUP",
                    "predicted_side": "yes",
                    "positive_depth_cost": 10.0,
                    "positive_depth_contracts": 25.0,
                    "best_margin_probability": 0.1,
                    "correlation_cluster_key": f"WORLD_CUP|match-{idx}|2026-07-09T21:00Z",
                }
                for idx in range(3)
            ],
            "safety": {
                "research_only": True,
                "market_execution": False,
                "account_or_order_paths": False,
                "database_writes": False,
            },
        },
    )

    report = module.build_world_cup_proxy_correlation_cluster_control(ccd_path=ccd_path)

    assert report["status"] == "world_cup_proxy_correlation_cluster_control_ready_for_paper_overlay"
    assert report["family_id"] == "world_cup_soccer"
    assert report["summary"]["controlled_positive_row_count"] == 3


def test_world_cup_ev_row_is_not_blocked_as_projection_model(tmp_path: Path) -> None:
    module = load_module("kalshi_contract_ev_ledger", LEDGER_PATH)
    source = write_json(tmp_path / "world_cup_cluster.json", {"status": "unit"})

    row = module.world_cup_ccd_paper_overlay_ev_row(
        repo_id="predmarket-alpha",
        source_artifact=source,
        source_row_index=0,
        capacity={
            "contract_ticker": "KXWCGAME-26JUL09AAABBB-AAA",
            "event_ticker": "KXWCGAME-26JUL09AAABBB",
            "league": "WORLD_CUP",
            "predicted_side": "yes",
            "source_model_id": "world_cup_longshot_fade_directional_accuracy",
            "best_all_in_break_even_probability": 0.40,
            "conservative_calibrated_side_probability": 0.70,
            "controlled_depth_cost": 12.0,
            "controlled_depth_contracts": 30.0,
            "correlation_cluster_key": "WORLD_CUP|KXWCGAME-26JUL09AAABBB|2026-07-09T21:00Z",
            "close_time": "2026-07-09T21:00:00Z",
        },
        official_terms={
            "KXWCGAME-26JUL09AAABBB-AAA": {
                "resolution_rule": "Official Kalshi World Cup game terms.",
                "source_artifact": str(source),
                "source_sha256": "abc",
            }
        },
    )

    assert row["usable"] is True
    assert row["family_id"] == "world_cup_soccer"
    assert row["model_id"] == "world_cup_longshot_fade_directional_accuracy"
    assert row["sports_probability_source_gate_status"] == "pass_price_bucket_bias_family"
    assert row["source_gate_status"] == "pass"
    assert not any("projection or strength-model" in reason for reason in row["gate_reasons"])
    assert row["capacity_estimate"] == 12.0


def test_world_cup_gate_chain_make_targets_exist() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    assert "kalshi-world-cup-proxy-research-candidate-replay" in makefile
    assert "kalshi-world-cup-proxy-capacity-correlation-decay" in makefile
    assert "kalshi-world-cup-proxy-correlation-cluster-control" in makefile
