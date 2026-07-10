from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from predmarket.sports_executable_horizon import (
    apply_fdr,
    build_executable_labels,
    evaluate_hypothesis,
    hypothesis_registry,
    synthetic_leakage_tests,
    validate_book,
)


def load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_executable_horizon_research.py"
    spec = importlib.util.spec_from_file_location("kalshi_sports_executable_horizon_research", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_rows() -> list[dict]:
    rows = []
    for index in range(6):
        mid = 0.50 + 0.01 * index
        rows.append(
            {
                "snapshot_id": f"snap-{index}",
                "contract_ticker": "KXMLBGAME-26JUL05BOSNYY-BOS",
                "event_ticker": "KXMLBGAME-26JUL05BOSNYY",
                "series_ticker": "KXMLBGAME",
                "sport_surface": "mlb",
                "observed_at_utc": f"2026-07-05T00:{index * 5:02d}:00Z",
                "settlement_time": "2026-07-05T04:00:00Z",
                "best_yes_bid": round(mid - 0.01, 4),
                "best_yes_ask": round(mid + 0.01, 4),
                "best_no_bid": round(1 - (mid + 0.01), 4),
                "best_no_ask": round(1 - (mid - 0.01), 4),
                "yes_bid_depth_top1": 20.0,
                "yes_ask_depth_top1": 18.0,
                "no_bid_depth_top1": 15.0,
                "no_ask_depth_top1": 16.0,
                "yes_mid": mid,
                "yes_spread": 0.02,
                "depth_imbalance_yes": 0.4 if index % 2 == 0 else -0.4,
                "depth_imbalance_delta": 0.1,
                "total_depth_contracts": 200.0,
                "time_to_settlement_seconds": 14400 - index * 300,
                "_source_path": "test",
                "_source_sha256": "test",
            }
        )
    return rows


def test_validate_book_detects_crossed() -> None:
    ok, reason = validate_book(0.6, 0.5)
    assert not ok
    assert reason == "crossed_book"


def test_synthetic_leakage_suite_passes() -> None:
    results = synthetic_leakage_tests()
    assert results
    assert all(item["passed"] for item in results)


def test_executable_labels_censor_and_fee_adjust() -> None:
    labels, summary = build_executable_labels(sample_rows(), horizons=(300,))
    assert summary["label_row_count"] == len(labels)
    labeled = [row for row in labels if row["label_status"] == "executable_labeled"]
    assert labeled
    row = labeled[0]
    assert row["yes_gross_return_per_contract"] is not None
    assert row["yes_net_return_per_contract"] < row["yes_gross_return_per_contract"]
    assert row["exit_observed_at_utc"] > row["observed_at_utc"]


def test_hypothesis_registry_is_finite_and_includes_controls() -> None:
    registry = hypothesis_registry()
    assert 5 <= len(registry) <= 20
    assert any(row["negative_control"] for row in registry)
    assert all(row.get("model_id") for row in registry)


def test_evaluate_and_fdr_on_synthetic_family() -> None:
    # Build a multi-event corpus with a planted positive edge on spread-norm imbalance.
    rows: list[dict] = []
    for event_i in range(40):
        for step in range(4):
            imbalance = 0.5
            mid = 0.45 + 0.03 * step
            rows.append(
                {
                    "snapshot_id": f"e{event_i}-s{step}",
                    "contract_ticker": f"KXMLBGAME-E{event_i}-HOME",
                    "event_ticker": f"KXMLBGAME-E{event_i}",
                    "series_ticker": "KXMLBGAME",
                    "sport_surface": "mlb",
                    "observed_at_utc": f"2026-07-0{(event_i % 5) + 1}T{step:02d}:00:00Z",
                    "settlement_time": f"2026-07-0{(event_i % 5) + 1}T12:00:00Z",
                    "best_yes_bid": round(mid - 0.01, 4),
                    "best_yes_ask": round(mid + 0.01, 4),
                    "best_no_bid": round(1 - (mid + 0.01), 4),
                    "best_no_ask": round(1 - (mid - 0.01), 4),
                    "yes_bid_depth_top1": 25.0,
                    "yes_ask_depth_top1": 25.0,
                    "no_bid_depth_top1": 25.0,
                    "no_ask_depth_top1": 25.0,
                    "yes_mid": mid,
                    "yes_spread": 0.02,
                    "depth_imbalance_yes": imbalance,
                    "depth_imbalance_delta": 0.1,
                    "total_depth_contracts": 100.0,
                    "time_to_settlement_seconds": 10000.0,
                    "_source_path": "test",
                    "_source_sha256": "test",
                }
            )
    labels, _ = build_executable_labels(rows, horizons=(300, 900))
    specs = hypothesis_registry()
    evaluations = [
        evaluate_hypothesis(labels, spec, min_oos_labels=5, min_events=3) for spec in specs
    ]
    evaluations = apply_fdr(evaluations, alpha=0.05)
    assert len(evaluations) == len(specs)
    assert all("status" in row for row in evaluations)
    # Negative control should not become research_ready.
    assert all(
        not (row.get("negative_control") and row.get("status") == "research_ready")
        for row in evaluations
    )


def test_script_builds_report(tmp_path: Path) -> None:
    module = load_script()
    obs_dir = tmp_path / "obs"
    obs_dir.mkdir()
    payload = {
        "schema_version": 1,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "rows": sample_rows(),
    }
    (obs_dir / "sports_microstructure_observations_20260705T000000Z.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    report = module.build_report(
        observation_dir=obs_dir,
        label_dir=tmp_path / "labels",
        tick_dir=tmp_path / "ticks",
        discovery_cutoff_utc="2026-07-10T00:00:00Z",
        fdr_alpha=0.05,
        min_oos_labels=100,
        min_events=20,
    )
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["summary"]["usable_row_count"] == 0
    assert report["phase0_truth_leakage_audit"]["synthetic_tests_passed"] is True
    assert report["hypothesis_registry"]
    out_dir = tmp_path / "out"
    paths = module.write_outputs(
        report, out_dir=out_dir, export_label_dir=tmp_path / "export_labels"
    )
    assert Path(paths["json_path"]).is_file()
    assert Path(paths["audit_path"]).is_file()
    assert Path(paths["frontier_path"]).is_file()
