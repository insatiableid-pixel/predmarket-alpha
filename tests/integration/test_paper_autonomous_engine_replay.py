"""Integration replay tests for the paper-autonomous Kalshi EV engine."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from predmarket.external_artifact_bridge import load_external_artifact
from predmarket.paper_decision_engine import build_paper_decision_candidates
from predmarket.signal_decay_retirement import build_signal_decay_retirement_ledger
from predmarket.source_inventory import SourceRepoDescriptor
from scripts.kalshi_external_artifact_preflight import build_external_artifact_preflight


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def safe_artifact(*rows: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "integration_artifact_ready",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "rows": list(rows),
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }


def ledger_payload(*rows: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "kalshi_ev_ledger_ready_with_usable_contract_edges",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "rows": list(rows),
    }


def pass_ready_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "contract_ticker": "KXINTEGRATION-YES",
        "side": "yes",
        "family_id": "integration_family",
        "model_id": "integration_model",
        "source_repo_id": "integration_donor",
        "signal_formula_key": "model_minus_market",
        "usable": True,
        "calibrated_probability": 0.60,
        "display_price": 0.40,
        "all_in_cost": 0.40,
        "expected_value_per_contract": 0.20,
        "capacity_estimate": 50.0,
        "correlation_cluster_key": "integration|cluster",
        "close_time": "2026-07-03T00:00:00Z",
        "resolution_rule_status": "verified_official_terms",
        "gate_status": "pass",
        "timing_status": "clean",
        "capacity_gate_status": "pass",
        "correlation_cluster_gate_status": "pass",
        "decay_gate_status": "pass",
    }
    row.update(overrides)
    return row


def test_external_artifact_reaches_blocked_paper_decision(tmp_path: Path) -> None:
    control_repo = tmp_path / "control"
    donor_artifact = tmp_path / "donor" / "artifact.json"
    write_json(
        donor_artifact,
        safe_artifact(
            {
                "contract_ticker": "KXINTEGRATION-YES",
                "side": "yes",
                "calibrated_probability": 0.61,
            }
        ),
    )

    loaded = load_external_artifact(
        path=donor_artifact,
        source_repo_id="integration_donor",
        family_id="integration_family",
        model_id="integration_model",
        control_repo=control_repo,
        requires_exact_contract_mapping=True,
    )

    assert loaded["status"] == "external_artifact_loaded"
    assert loaded["safe"] is True
    assert loaded["row_count"] == 1

    ledger_path = tmp_path / "ledger.json"
    source_row = loaded["rows"][0]
    write_json(
        ledger_path,
        ledger_payload(
            pass_ready_row(
                calibrated_probability=source_row["calibrated_probability"],
                gate_status="blocked_insufficient_labeled_oos",
            )
        ),
    )

    report = build_paper_decision_candidates(
        ledger_path=ledger_path,
        generated_utc="2026-07-03T00:00:00Z",
        paper_bankroll=1000.0,
    )

    candidate = report["candidates"][0]
    assert report["status"] == "paper_decision_candidates_ready_all_rows_blocked"
    assert candidate["paper_stake"] == 0.0
    assert "ledger gate status is not pass" in candidate["blocker_list"]
    assert candidate["execution_enabled"] is False
    assert candidate["market_execution"] is False


def test_preflight_auto_wrap_admits_synthetic_donor_artifact(tmp_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="predmarket-donor-", dir="/tmp") as external_dir:
        raw = Path(external_dir) / "donor" / "artifact.json"
        write_json(
            raw,
            {
                "status": "raw_donor_ready",
                "rows": [
                    {
                        "contract_ticker": "KXINTEGRATION-YES",
                        "side": "yes",
                        "model_prob_home": 0.61,
                    }
                ],
            },
        )
        descriptor = SourceRepoDescriptor(
            repo_id="integration-donor",
            path=str(raw.parent),
            donor_type="model-output",
            admission_status="admit_via_external_artifact_bridge",
            family_ids=("integration_family",),
            admissible_artifacts=(str(raw),),
        )

        report = build_external_artifact_preflight(
            generated_utc="2026-07-03T00:00:00Z",
            wrap_root=tmp_path / "wrapped",
            descriptors=(descriptor,),
        )

    assert report["summary"]["artifact_count"] == 1
    assert report["summary"]["safe_artifact_count"] == 1
    assert report["summary"]["safe_wrapped_artifact_count"] == 1
    assert report["summary"]["safe_row_count"] == 1
    assert report["artifacts"][0]["wrapped"] is True


def test_decayed_paper_signal_is_retired_and_excluded_next_run(tmp_path: Path) -> None:
    settled_rows = [
        pass_ready_row(
            contract_ticker=f"KXINTEGRATION-{index}",
            close_time=f"2026-07-03T00:0{index}:00Z",
            close_bucket="2026-07-03T00:00Z",
            settled_outcome=0,
        )
        for index in range(3)
    ]
    ledger_path = tmp_path / "ledger.json"
    paper_path = tmp_path / "paper.json"
    write_json(ledger_path, ledger_payload(*settled_rows))

    paper_report = build_paper_decision_candidates(
        ledger_path=ledger_path,
        generated_utc="2026-07-03T00:10:00Z",
        paper_bankroll=1000.0,
        kelly_fraction=0.25,
        max_fraction_per_contract=0.02,
        covariance_penalty_lambda=0.0,
    )
    write_json(paper_path, paper_report)

    assert paper_report["summary"]["paper_usable_count"] == 3
    assert paper_report["summary"]["total_paper_stake"] == 60.0

    retirement = build_signal_decay_retirement_ledger(
        paper_decisions_path=paper_path,
        generated_utc="2026-07-03T00:20:00Z",
        min_recent_decisions=3,
        min_recent_accuracy=0.5,
        max_calibration_error=1.0,
    )

    assert retirement["summary"]["retired_signal_count"] == 1
    assert retirement["signals"][0]["next_generator_action"] == "deprioritize_or_avoid"

    next_ledger_path = tmp_path / "next-ledger.json"
    write_json(
        next_ledger_path, ledger_payload(pass_ready_row(contract_ticker="KXINTEGRATION-NEXT"))
    )
    next_report = build_paper_decision_candidates(
        ledger_path=next_ledger_path,
        retirement_ledger=retirement,
        generated_utc="2026-07-03T00:30:00Z",
        paper_bankroll=1000.0,
    )

    next_candidate = next_report["candidates"][0]
    assert next_candidate["paper_stake"] == 0.0
    assert "signal is retired" in next_candidate["blocker_list"]
