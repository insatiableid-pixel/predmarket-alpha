from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kalshi_ev_review_queue.py"
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_queue_module():
    spec = importlib.util.spec_from_file_location("kalshi_ev_review_queue", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def ledger_payload(*rows):
    return {
        "schema_version": 1,
        "generated_utc": "2026-07-01T20:00:00Z",
        "status": "kalshi_ev_ledger_ready_with_usable_contract_edges",
        "research_only": True,
        "execution_enabled": False,
        "rows": list(rows),
    }


def usable_row(**overrides):
    row = {
        "contract_ticker": "KXNFLGAME-26SEP13ARILAC-ARI",
        "event_ticker": "KXNFLGAME-26SEP13ARILAC",
        "side": "yes",
        "selection": "ARI",
        "source_repo_id": "nfl_quant_glm51_greenfield",
        "market_type": "nfl_game_moneyline",
        "resolution_rule": "If Arizona wins, then this market resolves to Yes.",
        "resolution_rule_source": "local_kalshi_contract_evidence_scout",
        "resolution_rule_status": "verified_official_terms",
        "resolution_rule_source_artifact": "/tmp/kalshi.json",
        "executable_price": 0.19,
        "fee_estimate": 0.0108,
        "all_in_break_even_probability": 0.2008,
        "calibrated_probability": 0.2082,
        "calibrated_probability_source": "unit_test",
        "calibrated_probability_source_artifact": "/tmp/probability.json",
        "margin_probability": 0.0074,
        "expected_value_per_contract": 0.0074,
        "expected_roi": 0.0368,
        "gate_status": "pass",
        "gate_reasons": [],
        "timing_status": "pregame_clean",
        "usable": True,
        "cost_quality": "estimated_fee_from_executable_price",
    }
    row.update(overrides)
    return row


def blocked_row():
    return usable_row(
        contract_ticker="BLOCKED",
        usable=False,
        gate_status="blocked",
        gate_reasons=["calibrated contract probability is missing"],
        calibrated_probability=None,
        margin_probability=None,
    )


def test_review_queue_labels_thin_positive_margin(tmp_path: Path) -> None:
    queue = load_queue_module()
    ledger_path = tmp_path / "ledger.json"
    write_json(ledger_path, ledger_payload(usable_row(), blocked_row()))

    report = queue.build_review_queue(
        ledger_path=ledger_path,
        generated_utc="2026-07-01T20:01:00Z",
        min_robust_margin=0.02,
    )

    assert report["status"] == "kalshi_ev_review_queue_positive_candidates_need_robustness"
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["summary"]["queued_row_count"] == 1
    assert report["summary"]["thin_positive_watch_count"] == 1
    assert report["summary"]["positive_watch_count"] == 0
    assert report["summary"]["robust_candidate_count"] == 0
    row = report["rows"][0]
    assert row["queue_rank"] == 1
    assert row["disposition"] == "thin_positive_ev_watch"
    assert row["all_in_break_even_probability"] == 0.2008
    assert row["calibrated_probability"] == 0.2082
    assert "margin below robust review threshold" in row["robustness_reasons"][0]
    assert "calibrated contract probability is missing" in report["summary"]["rejected_reason_counts"]


def test_review_queue_promotes_robust_research_candidate(tmp_path: Path) -> None:
    queue = load_queue_module()
    ledger_path = tmp_path / "ledger.json"
    write_json(
        ledger_path,
        ledger_payload(
            usable_row(contract_ticker="THIN", margin_probability=0.005, expected_roi=0.01),
            usable_row(
                contract_ticker="ROBUST",
                margin_probability=0.04,
                expected_roi=0.09,
                cost_quality="explicit_all_in_cost",
            ),
        ),
    )

    report = queue.build_review_queue(
        ledger_path=ledger_path,
        generated_utc="2026-07-01T20:01:00Z",
        min_robust_margin=0.02,
    )

    assert report["status"] == "kalshi_ev_review_queue_ready_with_robust_candidates"
    assert report["summary"]["queued_row_count"] == 2
    assert report["summary"]["robust_candidate_count"] == 1
    assert report["rows"][0]["contract_ticker"] == "ROBUST"
    assert report["rows"][0]["disposition"] == "robust_positive_ev_review"
    assert report["rows"][1]["disposition"] == "thin_positive_ev_watch"


def test_review_queue_labels_positive_watch_when_only_cost_caveat_remains(tmp_path: Path) -> None:
    queue = load_queue_module()
    ledger_path = tmp_path / "ledger.json"
    write_json(
        ledger_path,
        ledger_payload(usable_row(contract_ticker="WATCH", margin_probability=0.04, expected_roi=0.09)),
    )

    report = queue.build_review_queue(
        ledger_path=ledger_path,
        generated_utc="2026-07-01T20:01:00Z",
        min_robust_margin=0.02,
    )

    assert report["status"] == "kalshi_ev_review_queue_positive_candidates_need_robustness"
    assert report["summary"]["positive_watch_count"] == 1
    assert report["summary"]["thin_positive_watch_count"] == 0
    assert report["rows"][0]["disposition"] == "positive_ev_watch"
    assert report["rows"][0]["robustness_reasons"] == ["fee is estimated from executable price"]


def test_review_queue_writer_emits_json_markdown_and_csv(tmp_path: Path) -> None:
    queue = load_queue_module()
    queue.MACRO_DIR = tmp_path / "macro"
    report = queue.build_review_queue(
        ledger_path=tmp_path / "missing-ledger.json",
        generated_utc="2026-07-01T20:01:00Z",
    )

    paths = queue.write_review_queue(report, out_dir=tmp_path / "out")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    assert Path(paths["latest_json_path"]).exists()
    assert "Kalshi EV Review Queue" in Path(paths["markdown_path"]).read_text(encoding="utf-8")


def test_makefile_exposes_review_queue_target() -> None:
    content = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-ev-review-queue" in content
    assert "scripts/kalshi_ev_review_queue.py" in content
