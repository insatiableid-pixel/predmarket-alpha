from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kalshi_labeled_oos_backtest.py"
SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "codex"
    / "macro"
    / "kalshi-labeled-oos-observation.schema.json"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_backtest_module():
    spec = importlib.util.spec_from_file_location("kalshi_labeled_oos_backtest", SCRIPT_PATH)
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


def registry_payload(*hypothesis_ids: str):
    return safe_packet(
        status="hypothesis_registry_ready_falsification_blocked_missing_labeled_oos_evidence",
        summary={"hypothesis_count": len(hypothesis_ids)},
        hypotheses=[
            {
                "schema_version": "HypothesisCandidateV1",
                "hypothesis_id": hypothesis_id,
                "status": "candidate_unvalidated",
                "classification": "nfl",
                "model_route": "nfl_quant_glm51_greenfield",
                "feature_family": "calibrated_probability_decay",
                "multiple_testing_family": f"unit::{hypothesis_id}",
                "safety": {
                    "research_only": True,
                    "market_execution": False,
                    "account_or_order_paths": False,
                },
            }
            for hypothesis_id in hypothesis_ids
        ],
    )


def observation(hypothesis_id: str, idx: int, *, outcome: int = 1, model_prob: float = 0.70):
    day = 1 + idx
    return {
        "hypothesis_id": hypothesis_id,
        "contract_ticker": f"KXUNIT-{idx:03d}",
        "side": "yes",
        "quote_time": f"2026-01-{day:02d}T10:00:00Z",
        "model_time": f"2026-01-{day:02d}T10:01:00Z",
        "decision_time": f"2026-01-{day:02d}T10:02:00Z",
        "close_time": f"2026-01-{day:02d}T20:00:00Z",
        "settled_time": f"2026-01-{day:02d}T22:00:00Z",
        "model_probability": model_prob,
        "all_in_break_even_probability": 0.40,
        "side_outcome": outcome,
        "label_source": "unit_test",
        "cost_source": "unit_test_all_in_cost",
    }


def test_backtest_blocks_when_labels_are_missing(tmp_path: Path) -> None:
    module = load_backtest_module()
    registry = tmp_path / "registry.json"
    write_json(registry, registry_payload("hyp_0000000000000001"))

    report = module.build_labeled_oos_backtest(
        registry_path=registry,
        label_dir=tmp_path / "missing-labels",
        generated_utc="2026-07-01T23:40:00Z",
    )

    assert report["status"] == "labeled_oos_backtest_blocked_missing_labeled_observations"
    assert report["summary"]["valid_observation_count"] == 0
    assert report["summary"]["blocked_hypothesis_count"] == 1
    assert (
        report["falsification_gate"]["status"]
        == "falsification_gate_blocked_missing_labeled_oos_evidence"
    )
    assert report["safety"]["market_execution"] is False


def test_backtest_ignores_unsafe_label_packets(tmp_path: Path) -> None:
    module = load_backtest_module()
    registry = tmp_path / "registry.json"
    label_dir = tmp_path / "labels"
    write_json(registry, registry_payload("hyp_0000000000000001"))
    write_json(
        label_dir / "unsafe.json",
        {
            "research_only": True,
            "execution_enabled": True,
            "rows": [observation("hyp_0000000000000001", 0)],
            "safety": {
                "market_execution": True,
                "account_or_order_paths": True,
                "database_writes": False,
            },
        },
    )

    report = module.build_labeled_oos_backtest(
        registry_path=registry,
        label_dir=label_dir,
        generated_utc="2026-07-01T23:40:00Z",
    )

    assert report["summary"]["unsafe_label_packet_count"] == 1
    assert report["summary"]["valid_observation_count"] == 0
    assert report["status"] == "labeled_oos_backtest_blocked_missing_labeled_observations"


def test_backtest_promotes_only_after_oos_cost_and_fdr_pass(tmp_path: Path) -> None:
    module = load_backtest_module()
    registry = tmp_path / "registry.json"
    label_dir = tmp_path / "labels"
    hypothesis_id = "hyp_0000000000000001"
    write_json(registry, registry_payload(hypothesis_id))
    rows = [observation(hypothesis_id, idx, outcome=1, model_prob=0.75) for idx in range(20)]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))

    report = module.build_labeled_oos_backtest(
        registry_path=registry,
        label_dir=label_dir,
        min_observations=12,
        min_oos_observations=5,
        fdr_alpha=0.10,
        generated_utc="2026-07-01T23:40:00Z",
    )

    evaluation = report["evaluations"][0]
    assert report["status"] == "labeled_oos_backtest_ready_with_research_promotions"
    assert report["summary"]["testable_hypothesis_count"] == 1
    assert report["summary"]["promoted_research_hypothesis_count"] == 1
    assert evaluation["status"] == "hypothesis_promoted_research_fdr_passed"
    assert evaluation["q_value"] <= 0.10
    assert evaluation["mean_realized_pnl_per_contract"] > 0
    assert report["falsification_gate"]["promoted_hypothesis_count"] == 1


def test_backtest_blocks_time_unsafe_rows(tmp_path: Path) -> None:
    module = load_backtest_module()
    registry = tmp_path / "registry.json"
    label_dir = tmp_path / "labels"
    hypothesis_id = "hyp_0000000000000001"
    row = observation(hypothesis_id, 0)
    row["decision_time"] = "2026-01-01T23:00:00Z"
    row["close_time"] = "2026-01-01T20:00:00Z"
    write_json(registry, registry_payload(hypothesis_id))
    write_json(label_dir / "labels.json", safe_packet(rows=[row]))

    report = module.build_labeled_oos_backtest(
        registry_path=registry,
        label_dir=label_dir,
        generated_utc="2026-07-01T23:40:00Z",
    )

    assert report["summary"]["valid_observation_count"] == 0
    assert report["summary"]["invalid_observation_count"] == 1
    assert report["invalid_observation_samples"][0]["errors"] == ["not_time_safe"]


def test_writer_emits_latest_outputs(tmp_path: Path) -> None:
    module = load_backtest_module()
    module.MACRO_DIR = tmp_path / "macro"
    registry = tmp_path / "registry.json"
    write_json(registry, registry_payload("hyp_0000000000000001"))
    report = module.build_labeled_oos_backtest(
        registry_path=registry,
        label_dir=tmp_path / "missing-labels",
        generated_utc="2026-07-01T23:40:00Z",
    )

    paths = module.write_labeled_oos_backtest(report, out_dir=tmp_path / "out")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    assert Path(paths["latest_json_path"]).exists()
    assert Path(paths["latest_falsification_gate_json_path"]).exists()
    assert "Kalshi Labeled OOS Backtest" in Path(paths["markdown_path"]).read_text(encoding="utf-8")


def test_schema_and_makefile_target_exist() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert schema["title"] == "KalshiLabeledOosObservationPacketV1"
    assert "rows" in schema["required"]
    assert "kalshi-labeled-oos-backtest" in makefile
    assert "scripts/kalshi_labeled_oos_backtest.py" in makefile
