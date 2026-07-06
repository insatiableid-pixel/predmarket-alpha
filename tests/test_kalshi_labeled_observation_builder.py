from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_labeled_observation_builder.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_builder_module():
    spec = importlib.util.spec_from_file_location("kalshi_labeled_observation_builder", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def safe_payload(**overrides):
    payload = {
        "schema_version": 1,
        "generated_utc": "2026-07-01T20:00:00Z",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }
    payload.update(overrides)
    return payload


def registry_payload():
    return safe_payload(
        status="hypothesis_registry_ready_falsification_blocked_missing_labeled_oos_evidence",
        hypotheses=[
            {
                "schema_version": "HypothesisCandidateV1",
                "hypothesis_id": "hyp_nfl_decay",
                "source": "contract_ev_ledger",
                "classification": "nfl",
                "model_route": "nfl_quant_glm51_greenfield",
                "feature_family": "calibrated_probability_decay",
                "market_universe_filter": {
                    "source_repo_id": "nfl_quant_glm51_greenfield",
                    "market_type": "nfl_game_moneyline",
                    "feature_family": "calibrated_probability_decay",
                },
            },
            {
                "schema_version": "HypothesisCandidateV1",
                "hypothesis_id": "hyp_nfl_positive",
                "source": "contract_ev_ledger",
                "classification": "nfl",
                "model_route": "nfl_quant_glm51_greenfield",
                "feature_family": "legacy_positive_margin_survival",
                "market_universe_filter": {
                    "source_repo_id": "nfl_quant_glm51_greenfield",
                    "market_type": "nfl_game_moneyline",
                    "feature_family": "legacy_positive_margin_survival",
                },
            },
        ],
    )


def ev_ledger_payload():
    return safe_payload(
        status="kalshi_ev_ledger_ready_with_usable_contract_edges",
        rows=[
            {
                "source_repo_id": "nfl_quant_glm51_greenfield",
                "market_type": "nfl_game_moneyline",
                "contract_ticker": "KXNFLGAME-26SEP13MIALV-MIA",
                "event_ticker": "KXNFLGAME-26SEP13MIALV",
                "side": "yes",
                "calibrated_probability": 0.64,
                "calibrated_probability_source": "unit_model",
                "all_in_break_even_probability": 0.58,
                "break_even_source": "unit_cost",
                "expected_value_per_contract": 0.06,
                "gate_status": "pass",
                "usable": True,
                "decision_time": "2026-07-01T20:00:00Z",
                "quote_time": "2026-07-01T19:59:00Z",
                "model_time": "2026-07-01T19:58:00Z",
            },
            {
                "source_repo_id": "nfl_quant_glm51_greenfield",
                "market_type": "nfl_game_moneyline",
                "contract_ticker": "KXNFLGAME-26SEP13MIALV-LV",
                "side": "yes",
                "all_in_break_even_probability": 0.48,
                "gate_status": "blocked",
            },
        ],
    )


def test_builder_records_pending_observations_without_settlement(tmp_path: Path) -> None:
    builder = load_builder_module()
    registry = tmp_path / "registry.json"
    ledger = tmp_path / "ledger.json"
    universe = tmp_path / "universe.json"
    write_json(registry, registry_payload())
    write_json(ledger, ev_ledger_payload())
    write_json(universe, safe_payload(candidates=[]))

    report = builder.build_labeled_observation_report(
        registry_path=registry,
        ev_ledger_path=ledger,
        universe_scan_path=universe,
        settled_snapshot_path=tmp_path / "missing-settled.json",
        pending_dir=tmp_path / "pending",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-01T20:01:00Z",
    )

    assert report["status"] == "labeled_observation_builder_pending_observations_waiting_settlement"
    assert report["summary"]["eligible_pending_row_count"] == 2
    assert report["summary"]["label_row_count"] == 0
    assert report["summary"]["blocked_reason_counts"]["missing_calibrated_model_probability"] == 2
    assert report["pending_packet"]["rows"][0]["hypothesis_id"] == "hyp_nfl_decay"
    assert report["safety"]["market_execution"] is False


def test_builder_emits_label_rows_from_pending_and_settled_snapshot(tmp_path: Path) -> None:
    builder = load_builder_module()
    pending_dir = tmp_path / "pending"
    pending_row = {
        "hypothesis_id": "hyp_nfl_decay",
        "contract_ticker": "KXNFLGAME-26SEP13MIALV-MIA",
        "event_ticker": "KXNFLGAME-26SEP13MIALV",
        "side": "yes",
        "decision_time": "2026-07-01T20:00:00Z",
        "quote_time": "2026-07-01T19:59:00Z",
        "model_time": "2026-07-01T19:58:00Z",
        "model_probability": 0.64,
        "all_in_break_even_probability": 0.58,
        "cost_source": "unit_cost",
        "source_artifact": "/tmp/unit-ledger.json",
    }
    write_json(pending_dir / "pending.json", safe_payload(rows=[pending_row]))
    settled = safe_payload(
        markets=[
            {
                "ticker": "KXNFLGAME-26SEP13MIALV-MIA",
                "event_ticker": "KXNFLGAME-26SEP13MIALV",
                "result": "yes",
                "settlement_value_dollars": "1.0000",
                "close_time": "2026-09-13T20:00:00Z",
                "settlement_ts": 1789338600,
            }
        ]
    )
    settled_path = tmp_path / "settled.json"
    write_json(settled_path, settled)
    registry = tmp_path / "registry.json"
    ledger = tmp_path / "ledger.json"
    universe = tmp_path / "universe.json"
    write_json(registry, registry_payload())
    write_json(ledger, safe_payload(rows=[]))
    write_json(universe, safe_payload(candidates=[]))

    report = builder.build_labeled_observation_report(
        registry_path=registry,
        ev_ledger_path=ledger,
        universe_scan_path=universe,
        settled_snapshot_path=settled_path,
        pending_dir=pending_dir,
        label_dir=tmp_path / "labels",
        generated_utc="2026-09-13T21:00:00Z",
    )

    assert report["status"] == "labeled_observation_builder_label_packet_ready"
    label = report["label_packet"]["rows"][0]
    assert label["side_outcome"] == 1
    assert label["close_time"] == "2026-09-13T20:00:00Z"
    assert label["label_source"] == "public_kalshi_settled_market_payload"


def test_writer_keeps_packets_outside_repo(tmp_path: Path) -> None:
    builder = load_builder_module()
    builder.MACRO_DIR = tmp_path / "repo/macro"
    report = safe_payload(
        status="labeled_observation_builder_pending_observations_waiting_settlement",
        summary={
            "total_pending_row_count": 1,
            "eligible_pending_row_count": 1,
            "settled_market_count": 0,
            "label_row_count": 0,
        },
        gates=[],
        pending_packet=safe_payload(
            rows=[
                {
                    "hypothesis_id": "hyp",
                    "contract_ticker": "KX",
                    "side": "yes",
                    "decision_time": "2026-07-01T00:00:00Z",
                }
            ]
        ),
        label_packet=safe_payload(rows=[]),
        pending_rows_sample=[],
        blocked_source_rows_sample=[],
    )

    paths = builder.write_labeled_observation_outputs(
        report,
        out_dir=tmp_path / "repo/out",
        pending_dir=tmp_path / "manual/pending",
        label_dir=tmp_path / "manual/labels",
    )

    assert Path(paths["json_path"]).exists()
    assert Path(paths["pending_packet_path"]).exists()
    assert str(paths["pending_packet_path"]).startswith(str(tmp_path / "manual"))
    assert Path(paths["latest_json_path"]).exists()


def test_makefile_exposes_labeled_observation_builder() -> None:
    content = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-labeled-observation-builder" in content
    assert "kalshi-labeled-observation-watch-once" in content
    assert "scripts/kalshi_labeled_observation_builder.py" in content
