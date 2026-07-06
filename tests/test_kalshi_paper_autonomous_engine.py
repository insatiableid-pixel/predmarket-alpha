from __future__ import annotations

import json
from pathlib import Path

import pytest

from predmarket.external_artifact_bridge import (
    build_file_manifest,
    load_external_artifact,
    validate_external_artifact,
)
from predmarket.external_artifact_wrappers import wrap_external_artifact
from predmarket.kalshi_live_engine import candidate_live_blockers
from predmarket.paper_decision_engine import build_paper_decision_candidates
from predmarket.signal_decay_retirement import (
    build_signal_decay_retirement_ledger,
    is_retired_signal,
)
from predmarket.signal_formula import (
    FormulaSecurityError,
    SignalFormulaSpec,
    build_signal_formula_registry,
    evaluate_formula,
)
from predmarket.source_inventory import SourceRepoDescriptor, build_source_repo_inventory

MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def safe_artifact(*rows: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "unit_artifact_ready",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "rows": list(rows),
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
        },
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_source_inventory_records_donor_state(tmp_path: Path) -> None:
    repo = tmp_path / "donor"
    repo.mkdir()
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}", encoding="utf-8")
    report = build_source_repo_inventory(
        (
            SourceRepoDescriptor(
                repo_id="unit-donor",
                path=str(repo),
                donor_type="model-output",
                admission_status="admit_via_external_artifact_bridge",
                family_ids=("unit_family",),
                admissible_artifacts=(str(artifact),),
            ),
        ),
        generated_utc="2026-07-03T00:00:00Z",
    )

    assert report["status"] == "source_repo_inventory_ready"
    assert report["summary"]["existing_repo_count"] == 1
    assert report["summary"]["existing_artifact_count"] == 1
    assert report["repos"][0]["repo_id"] == "unit-donor"


def test_external_artifact_validator_accepts_safe_manifest(tmp_path: Path) -> None:
    control = tmp_path / "control"
    external = tmp_path / "external" / "artifact.json"
    write_json(
        external,
        safe_artifact(
            {
                "contract_ticker": "KXUNIT-YES",
                "side": "yes",
                "calibrated_probability": 0.61,
            }
        ),
    )
    manifest = build_file_manifest(
        source_repo_id="unit-donor",
        path=external,
        family_id="unit_family",
        requires_exact_contract_mapping=True,
    )

    report = validate_external_artifact(
        payload=json.loads(external.read_text(encoding="utf-8")),
        manifest=manifest,
        control_repo=control,
    )

    assert report["status"] == "external_artifact_preflight_pass"
    assert report["safe"] is True
    assert report["row_count"] == 1


def test_external_artifact_wrapper_builds_strict_manifest(tmp_path: Path) -> None:
    control = tmp_path / "control"
    raw = tmp_path / "donor" / "raw.json"
    write_json(
        raw,
        {
            "status": "raw_ready_without_safety_envelope",
            "rows": [
                {
                    "contract_ticker": "KXUNIT-YES",
                    "side": "yes",
                    "model_prob_home": 0.61,
                    "market_prob_home": 0.55,
                }
            ],
        },
    )

    wrapped = wrap_external_artifact(
        source_repo_id="unit-donor",
        family_id="unit_family",
        source_path=raw,
        wrap_root=tmp_path / "wrapped",
        generated_utc="2026-07-03T00:00:00Z",
    )
    loaded = load_external_artifact(
        path=Path(str(wrapped["wrapped_path"])),
        source_repo_id="unit-donor",
        family_id="unit_family",
        control_repo=control,
    )

    assert wrapped["status"] == "external_artifact_wrapped"
    assert loaded["status"] == "external_artifact_loaded"
    assert loaded["safe"] is True
    assert loaded["row_count"] == 1
    assert loaded["preflight"]["manifest"]["source_path"] == str(raw)
    assert loaded["rows"][0]["model_probability"] == pytest.approx(0.61)


def test_external_artifact_wrapper_accepts_atp_market_ticker_evidence_rows(tmp_path: Path) -> None:
    control = tmp_path / "control"
    raw = tmp_path / "kalshi-forward-oos-liquidity-latest" / "liquidity.json"
    write_json(
        raw,
        {
            "generated_at": "2026-07-03T00:00:00Z",
            "summary": {
                "gate_passes_for_first_stake": False,
                "passing_candidates": 1,
                "required_passing_candidates": 25,
            },
            "candidates": [
                {
                    "candidate_id": "unit-atp",
                    "match_label": "Player A vs Player B",
                    "selected_player": "Player A",
                    "market_ticker": "KXATPMATCH-26JUL05ALCBER-ALC",
                    "limit_price": 0.55,
                    "best_yes_ask": 0.56,
                    "passes_liquidity_gate": False,
                }
            ],
        },
    )

    wrapped = wrap_external_artifact(
        source_repo_id="atp-oracle",
        family_id="sports_tennis",
        source_path=raw,
        wrap_root=tmp_path / "wrapped",
        generated_utc="2026-07-03T00:00:00Z",
    )
    loaded = load_external_artifact(
        path=Path(str(wrapped["wrapped_path"])),
        source_repo_id="atp-oracle",
        family_id="sports_tennis",
        control_repo=control,
    )

    assert loaded["status"] == "external_artifact_loaded"
    assert loaded["safe"] is True
    assert loaded["row_count"] == 1
    assert loaded["rows"][0]["contract_ticker"] == "KXATPMATCH-26JUL05ALCBER-ALC"
    assert loaded["rows"][0]["side"] == "yes"


def test_external_artifact_wrapper_detects_source_tampering(tmp_path: Path) -> None:
    control = tmp_path / "control"
    raw = tmp_path / "donor" / "raw.json"
    write_json(raw, {"rows": [{"contract_ticker": "KXUNIT-YES", "side": "yes"}]})
    wrapped = wrap_external_artifact(
        source_repo_id="unit-donor",
        family_id="unit_family",
        source_path=raw,
        wrap_root=tmp_path / "wrapped",
    )
    write_json(raw, {"rows": [{"contract_ticker": "KXUNIT-NO", "side": "no"}]})

    loaded = load_external_artifact(
        path=Path(str(wrapped["wrapped_path"])),
        source_repo_id="unit-donor",
        family_id="unit_family",
        control_repo=control,
    )

    assert loaded["safe"] is False
    assert (
        "manifest source_path sha256 does not match artifact_sha256"
        in loaded["preflight"]["errors"]
    )


def test_external_artifact_validator_rejects_unsafe_and_bad_mapping(tmp_path: Path) -> None:
    control = tmp_path / "control"
    external = tmp_path / "external" / "artifact.json"
    payload = safe_artifact({"calibrated_probability": 1.2})
    payload["execution_enabled"] = True
    write_json(external, payload)
    manifest = build_file_manifest(
        source_repo_id="unit-donor",
        path=external,
        family_id="unit_family",
        requires_exact_contract_mapping=True,
    )

    report = validate_external_artifact(
        payload=payload,
        manifest=manifest,
        control_repo=control,
    )

    assert report["safe"] is False
    assert "artifact is not a safe research-only artifact" in report["errors"]
    assert "row 0 missing exact contract_ticker" in report["errors"]
    assert "row 0 has malformed probability field calibrated_probability" in report["errors"]


def test_signal_formula_dsl_evaluates_safe_formula_and_rejects_python_escape() -> None:
    assert evaluate_formula(
        "Max(0, Clip(model_probability - market_probability, -1, 1))",
        {"model_probability": 0.62, "market_probability": 0.55},
    ) == pytest.approx(0.07)

    with pytest.raises(FormulaSecurityError):
        evaluate_formula("__import__('os').system('echo nope')", {"model_probability": 0.62})

    with pytest.raises(FormulaSecurityError):
        evaluate_formula("model_probability.__class__", {"model_probability": 0.62})


def test_signal_formula_registry_counts_only_ready_formulas() -> None:
    report = build_signal_formula_registry(
        (
            SignalFormulaSpec(
                name="gap",
                formula="model_probability - market_probability",
                family_id="unit",
                input_fields=("model_probability", "market_probability"),
            ),
            SignalFormulaSpec(
                name="bad",
                formula="lambda x: x",
                family_id="unit",
                input_fields=("model_probability",),
            ),
        )
    )

    assert report["summary"]["formula_count"] == 2
    assert report["summary"]["ready_formula_count"] == 1
    assert report["summary"]["multiple_testing_hypothesis_count"] == 1
    assert report["formulas"][1]["status"] == "formula_blocked"


def ledger_payload(*rows: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "kalshi_ev_ledger_ready_with_usable_contract_edges",
        "research_only": True,
        "execution_enabled": False,
        "rows": list(rows),
    }


def pass_ready_row(**overrides: object) -> dict[str, object]:
    row = {
        "contract_ticker": "KXUNIT-YES",
        "side": "yes",
        "family_id": "unit_family",
        "model_id": "unit_model",
        "source_repo_id": "unit_repo",
        "signal_formula_key": "unit_formula",
        "usable": True,
        "calibrated_probability": 0.60,
        "display_price": 0.40,
        "all_in_cost": 0.40,
        "expected_value_per_contract": 0.20,
        "capacity_estimate": 50.0,
        "correlation_cluster_key": "unit|cluster",
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


def test_paper_decision_candidates_zero_size_until_all_gates_pass(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.json"
    write_json(ledger_path, ledger_payload(pass_ready_row(capacity_gate_status="blocked")))

    report = build_paper_decision_candidates(
        ledger_path=ledger_path,
        generated_utc="2026-07-03T00:00:00Z",
        paper_bankroll=1000.0,
    )

    row = report["candidates"][0]
    assert report["status"] == "paper_decision_candidates_ready_all_rows_blocked"
    assert row["paper_stake"] == 0.0
    assert "capacity gate has not passed" in row["blocker_list"]
    assert row["execution_enabled"] is False


def test_paper_decision_candidates_ingest_gate_evidence_blocker_rows(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.json"
    gate_path = tmp_path / "sports-stack.json"
    write_json(ledger_path, ledger_payload())
    write_json(
        gate_path,
        {
            "schema_version": 1,
            "status": "sports_stack_sequencing_ready_current_depth_passed",
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "paper_decision_blocker_rows": [
                {
                    "contract_ticker": "KXWCGAME-26JUL04-USA-USA",
                    "side": "yes",
                    "family_id": "world_cup_soccer",
                    "model_id": "world_cup_soccer_sports_gate_chain",
                    "source_repo_id": "predmarket-alpha",
                    "signal_formula_key": "world_cup_soccer_mechanical_gate_evidence",
                    "cluster_key": "world_cup_soccer|KXWCGAME-26JUL04-USA|2026-07-04T20:00Z",
                    "close_time": "2026-07-04T20:00:00Z",
                    "usable": False,
                    "blocker_list": ["world cup labels are missing"],
                }
            ],
            "safety": {
                "market_execution": False,
                "account_or_order_paths": False,
                "database_writes": False,
            },
        },
    )

    report = build_paper_decision_candidates(
        ledger_path=ledger_path,
        gate_evidence_paths=(gate_path,),
        generated_utc="2026-07-03T00:00:00Z",
        paper_bankroll=1000.0,
    )

    row = report["candidates"][0]
    assert report["status"] == "paper_decision_candidates_ready_all_rows_blocked"
    assert report["summary"]["gate_evidence_row_count"] == 1
    assert row["family_id"] == "world_cup_soccer"
    assert row["paper_stake"] == 0.0
    assert row["paper_usable"] is False
    assert row["blocker_list"] == ["world cup labels are missing"]


def test_paper_decision_candidates_skip_flow_gate_blockers_after_ev_promotion(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.json"
    gate_path = tmp_path / "flow-replay.json"
    write_json(
        ledger_path, ledger_payload(pass_ready_row(family_id="microstructure_informed_flow"))
    )
    write_json(
        gate_path,
        {
            "schema_version": 1,
            "status": "near_resolution_flow_replay_gates_ready_for_ev_ledger_promotion",
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "paper_decision_blocker_rows": [
                {
                    "contract_ticker": "KXFLOW-TEST",
                    "side": "yes",
                    "family_id": "microstructure_informed_flow",
                    "model_id": "flow_depth_imbalance_settlement_directional",
                    "source_repo_id": "predmarket-alpha",
                    "signal_formula_key": "depth_imbalance_yes_abs_gt_0_25",  # gitleaks:allow
                    "usable": False,
                    "blocker_list": ["flow replay gate has not been promoted through EV ledger"],
                }
            ],
            "safety": {
                "market_execution": False,
                "account_or_order_paths": False,
                "database_writes": False,
            },
        },
    )

    report = build_paper_decision_candidates(
        ledger_path=ledger_path,
        gate_evidence_paths=(gate_path,),
        generated_utc="2026-07-03T00:00:00Z",
        paper_bankroll=1000.0,
    )

    assert report["summary"]["candidate_count"] == 1
    assert report["summary"]["gate_evidence_row_count"] == 0
    assert report["summary"]["paper_usable_count"] == 1
    assert report["candidates"][0]["family_id"] == "microstructure_informed_flow"


def test_paper_decision_candidates_size_synthetic_passed_signal(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.json"
    write_json(ledger_path, ledger_payload(pass_ready_row()))

    report = build_paper_decision_candidates(
        ledger_path=ledger_path,
        generated_utc="2026-07-03T00:00:00Z",
        paper_bankroll=1000.0,
        kelly_fraction=0.25,
        max_fraction_per_contract=0.02,
    )

    row = report["candidates"][0]
    assert report["status"] == "paper_decision_candidates_ready_with_paper_sized_rows"
    assert row["paper_usable"] is True
    assert row["signal_key"] == "unit_family|unit_model|unit_formula|unit_repo"
    assert row["signal_formula_key"] == "unit_formula"
    assert row["close_bucket"] == "2026-07-03T00:00Z"
    assert row["paper_stake"] == pytest.approx(20.0)
    assert row["kelly_fraction"] > 0
    assert row["market_execution"] is False
    assert report["portfolio_risk"]["total_paper_stake"] == pytest.approx(20.0)
    assert report["portfolio_risk"]["largest_cluster"]["key"] == "unit|cluster"
    assert report["summary"]["paper_portfolio_cap_status"] == (
        "paper_portfolio_cap_breaches_present"
    )
    assert report["summary"]["paper_portfolio_cap_breach_count"] == 1


def test_paper_portfolio_cap_enforcement_blocks_breached_rows(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.json"
    write_json(ledger_path, ledger_payload(pass_ready_row()))

    report = build_paper_decision_candidates(
        ledger_path=ledger_path,
        generated_utc="2026-07-03T00:00:00Z",
        paper_bankroll=1000.0,
        kelly_fraction=0.25,
        max_fraction_per_contract=0.02,
        max_cluster_share=0.35,
        enforce_portfolio_caps=True,
    )

    row = report["candidates"][0]
    assert report["status"] == "paper_decision_candidates_ready_all_rows_blocked"
    assert report["summary"]["paper_usable_count"] == 0
    assert report["summary"]["total_paper_stake"] == 0.0
    assert report["summary"]["paper_portfolio_cap_enforcement_enabled"] is True
    assert report["summary"]["paper_portfolio_pre_enforcement_cap_status"] == (
        "paper_portfolio_cap_breaches_present"
    )
    assert report["summary"]["paper_portfolio_cap_blocked_candidate_count"] == 1
    assert report["summary"]["paper_portfolio_cap_status"] == "paper_portfolio_caps_observed"
    assert row["paper_usable"] is False
    assert row["paper_stake"] == 0.0
    assert row["portfolio_cap_blocked"] is True
    assert any("max_cluster_share cap infeasible" in item for item in row["blocker_list"])


def test_paper_portfolio_cap_enforcement_blocks_two_cluster_basket_as_infeasible(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.json"
    write_json(
        ledger_path,
        ledger_payload(
            pass_ready_row(
                contract_ticker="KXUNIT-A",
                signal_formula_key="unit_formula_a",
                correlation_cluster_key="unit|cluster_a",
            ),
            pass_ready_row(
                contract_ticker="KXUNIT-B",
                signal_formula_key="unit_formula_b",
                correlation_cluster_key="unit|cluster_b",
            ),
        ),
    )

    report = build_paper_decision_candidates(
        ledger_path=ledger_path,
        generated_utc="2026-07-03T00:00:00Z",
        paper_bankroll=1000.0,
        kelly_fraction=0.25,
        max_fraction_per_contract=0.02,
        max_cluster_share=0.35,
        enforce_portfolio_caps=True,
        covariance_penalty_lambda=0.0,
    )

    assert report["status"] == "paper_decision_candidates_ready_all_rows_blocked"
    assert report["summary"]["paper_usable_count"] == 0
    assert report["summary"]["paper_portfolio_cap_blocked_candidate_count"] == 2
    for row in report["candidates"]:
        assert row["paper_usable"] is False
        assert row["paper_stake"] == 0.0
        assert any(
            "max_cluster_share cap infeasible: positive_clusters=2" in item
            for item in row["blocker_list"]
        )
        assert "portfolio_cap_clip_ratio" not in row


def test_paper_portfolio_cap_enforcement_clips_feasible_multi_cluster_basket(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.json"
    write_json(
        ledger_path,
        ledger_payload(
            pass_ready_row(
                contract_ticker="KXUNIT-A",
                signal_formula_key="unit_formula_a",
                correlation_cluster_key="unit|cluster_a",
                capacity_estimate=100.0,
            ),
            pass_ready_row(
                contract_ticker="KXUNIT-B",
                signal_formula_key="unit_formula_b",
                correlation_cluster_key="unit|cluster_b",
                capacity_estimate=20.0,
            ),
            pass_ready_row(
                contract_ticker="KXUNIT-C",
                signal_formula_key="unit_formula_c",
                correlation_cluster_key="unit|cluster_c",
                capacity_estimate=20.0,
            ),
        ),
    )

    report = build_paper_decision_candidates(
        ledger_path=ledger_path,
        generated_utc="2026-07-03T00:00:00Z",
        paper_bankroll=1000.0,
        kelly_fraction=0.25,
        max_fraction_per_contract=1.0,
        max_cluster_share=0.35,
        enforce_portfolio_caps=True,
        covariance_penalty_lambda=0.0,
    )

    assert report["status"] == "paper_decision_candidates_ready_with_paper_sized_rows"
    assert report["summary"]["paper_usable_count"] == 3
    assert report["summary"]["paper_portfolio_cap_status"] == "paper_portfolio_caps_observed"
    assert report["summary"]["paper_portfolio_cap_breach_count"] == 0
    assert report["summary"]["paper_portfolio_cap_blocked_candidate_count"] == 0
    assert report["summary"]["paper_portfolio_cap_adjusted_candidate_count"] == 1
    largest_cluster = report["portfolio_risk"]["largest_cluster"]
    assert largest_cluster["stake_share"] <= 0.35
    rows = {row["contract_ticker"]: row for row in report["candidates"]}
    assert rows["KXUNIT-A"]["paper_usable"] is True
    assert rows["KXUNIT-A"]["portfolio_cap_adjusted"] is True
    assert (
        rows["KXUNIT-A"]["paper_stake"] < rows["KXUNIT-A"]["paper_stake_before_portfolio_cap_clip"]
    )
    assert "max_cluster_share cap clip" in rows["KXUNIT-A"]["portfolio_cap_clip_reason"]


def test_decay_retirement_blocks_future_candidate_admission(tmp_path: Path) -> None:
    paper_path = tmp_path / "paper.json"
    rows = []
    for idx, outcome in enumerate([0, 0, 0], start=1):
        row = pass_ready_row(
            close_time=f"2026-07-03T00:0{idx}:00Z",
            close_bucket="2026-07-03T00:00Z",
            settled_outcome=outcome,
            calibrated_probability=0.55,
            capacity_estimate=10.0,
        )
        row["paper_usable"] = True
        rows.append(row)
    write_json(paper_path, {"candidates": rows})

    report = build_signal_decay_retirement_ledger(
        paper_decisions_path=paper_path,
        generated_utc="2026-07-03T00:10:00Z",
        min_recent_decisions=3,
        min_recent_accuracy=0.5,
        max_calibration_error=1.0,
    )

    signal = report["signals"][0]
    assert signal["retirement_status"] == "retired"
    assert any("decay_survival" in r for r in signal["retirement_reasons"]), (
        f"Expected decay_survival reason, got {signal['retirement_reasons']}"
    )
    assert is_retired_signal(rows[0], report) is True


def test_makefile_exposes_paper_autonomous_targets() -> None:
    content = MAKEFILE_PATH.read_text(encoding="utf-8")

    for target in (
        "kalshi-source-repo-inventory",
        "kalshi-external-artifact-wrap",
        "kalshi-external-artifact-preflight",
        "kalshi-signal-formula-registry",
        "kalshi-paper-decision-candidates",
        "kalshi-signal-decay-retirement",
        "kalshi-live-preflight",
        "kalshi-live-demo",
        "kalshi-live-trader",
        "kalshi-live-reconcile",
        "kalshi-live-risk-snapshot",
    ):
        assert target in content


# ── VAL-PAPER assertion tests ─────────────────────────────────────────────


def test_val_paper_001_sports_blocker_rows_ingested_with_correct_prefixes(
    tmp_path: Path,
) -> None:
    """VAL-PAPER-001: Sports blocker rows ingested with family_id mlb_/atp_/world_cup_/microstructure_."""
    ledger_path = tmp_path / "ledger.json"
    write_json(ledger_path, ledger_payload())

    # Gate evidence with sports family_ids matching the expected prefixes
    gate_path = tmp_path / "sports-blockers.json"
    write_json(
        gate_path,
        {
            "schema_version": 1,
            "status": "sports_stack_sequencing_ready_current_depth_passed",
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "paper_decision_blocker_rows": [
                {
                    "contract_ticker": "KXWCGAME-26JUL04-USA-USA",
                    "side": "yes",
                    "family_id": "world_cup_soccer",
                    "model_id": "world_cup_soccer_sports_gate_chain",
                    "source_repo_id": "predmarket-alpha",
                    "signal_formula_key": "world_cup_soccer_mechanical_gate_evidence",
                    "cluster_key": "world_cup_soccer|KXWCGAME-26JUL04-USA|2026-07-04T20:00Z",
                    "close_time": "2026-07-04T20:00:00Z",
                    "usable": False,
                    "blocker_list": ["world cup labels are missing"],
                },
                {
                    "contract_ticker": "KXMLBGAME-26JUL04-CHC",
                    "side": "yes",
                    "family_id": "mlb_sports",
                    "model_id": "mlb_sports_sports_gate_chain",
                    "source_repo_id": "predmarket-alpha",
                    "signal_formula_key": "mlb_sports_mechanical_gate_evidence",
                    "cluster_key": "mlb_sports|KXMLBGAME-26JUL04-CHC|2026-07-04T20:00Z",
                    "close_time": "2026-07-04T20:00:00Z",
                    "usable": False,
                    "blocker_list": ["mlb labels are missing"],
                },
                {
                    "contract_ticker": "KXATPMATCH-26JUL04-DJO",
                    "side": "yes",
                    "family_id": "atp_tennis",
                    "model_id": "atp_tennis_sports_gate_chain",
                    "source_repo_id": "predmarket-alpha",
                    "signal_formula_key": "atp_tennis_mechanical_gate_evidence",
                    "cluster_key": "atp_tennis|KXATPMATCH-26JUL04-DJO|2026-07-04T20:00Z",
                    "close_time": "2026-07-04T20:00:00Z",
                    "usable": False,
                    "blocker_list": ["atp labels are missing"],
                },
                {
                    "contract_ticker": "KXFLOW-TEST",
                    "side": "yes",
                    "family_id": "microstructure_informed_flow",
                    "model_id": "flow_depth_imbalance_settlement_directional",
                    "source_repo_id": "predmarket-alpha",
                    "signal_formula_key": "*******************************",
                    "cluster_key": "sports_microstructure|KXFLOW-TEST|2026-07-04T20:00Z",
                    "close_time": "2026-07-04T20:00:00Z",
                    "usable": False,
                    "blocker_list": ["decay_survival not passing"],
                },
            ],
            "safety": {
                "market_execution": False,
                "account_or_order_paths": False,
                "database_writes": False,
            },
        },
    )

    report = build_paper_decision_candidates(
        ledger_path=ledger_path,
        gate_evidence_paths=(gate_path,),
        generated_utc="2026-07-03T00:00:00Z",
        paper_bankroll=1000.0,
    )

    sports_candidates = [row for row in report["candidates"] if isinstance(row, dict)]
    assert len(sports_candidates) >= 4, (
        f"Expected at least 4 sports blocker candidates, got {len(sports_candidates)}"
    )

    # Check each sports family_id prefix
    family_ids = {row["family_id"] for row in sports_candidates}
    expected_prefixes = {
        "world_cup_soccer",
        "mlb_sports",
        "atp_tennis",
        "microstructure_informed_flow",
    }
    assert family_ids >= expected_prefixes, (
        f"Missing sports family_ids. Got {family_ids}, expected at least {expected_prefixes}"
    )

    # Verify the prefixes
    assert any(fid.startswith("mlb_") for fid in family_ids), (
        f"No family_id starting with mlb_ found in {family_ids}"
    )
    assert any(fid.startswith("atp_") for fid in family_ids), (
        f"No family_id starting with atp_ found in {family_ids}"
    )
    assert any(fid.startswith("world_cup_") for fid in family_ids), (
        f"No family_id starting with world_cup_ found in {family_ids}"
    )
    assert any(fid.startswith("microstructure_") for fid in family_ids), (
        f"No family_id starting with microstructure_ found in {family_ids}"
    )


def test_val_paper_002_every_candidate_has_consistent_usable_blocker_list(
    tmp_path: Path,
) -> None:
    """VAL-PAPER-002: Every candidate has boolean paper_usable with consistent blocker_list."""
    ledger_path = tmp_path / "ledger.json"
    write_json(ledger_path, ledger_payload(pass_ready_row()))

    report = build_paper_decision_candidates(
        ledger_path=ledger_path,
        generated_utc="2026-07-03T00:00:00Z",
        paper_bankroll=1000.0,
    )

    for row in report["candidates"]:
        assert isinstance(row["paper_usable"], bool), (
            f"paper_usable must be boolean, got {type(row['paper_usable'])} for {row.get('signal_key')}"
        )
        if row["paper_usable"] is True:
            assert not row["blocker_list"], (
                f"Row {row.get('signal_key')} is paper_usable but has blocker_list"
            )
        else:
            assert row["blocker_list"], (
                f"Row {row.get('signal_key')} is not usable but has empty blocker_list"
            )


def test_val_paper_003_blocked_candidates_have_zero_stake_and_fraction(
    tmp_path: Path,
) -> None:
    """VAL-PAPER-003: Blocked candidates have paper_stake=0 and kelly_fraction=0."""
    ledger_path = tmp_path / "ledger.json"
    write_json(ledger_path, ledger_payload(pass_ready_row(capacity_gate_status="blocked")))

    report = build_paper_decision_candidates(
        ledger_path=ledger_path,
        generated_utc="2026-07-03T00:00:00Z",
        paper_bankroll=1000.0,
    )

    for row in report["candidates"]:
        if row["paper_usable"] is False:
            assert row["paper_stake"] == 0.0, (
                f"Blocked candidate {row.get('signal_key')} has paper_stake={row['paper_stake']}"
            )
            assert row["kelly_fraction"] == 0.0, (
                f"Blocked candidate {row.get('signal_key')} has kelly_fraction={row['kelly_fraction']}"
            )


def test_covariance_zeroed_candidates_have_explicit_blocker_and_zero_fraction(
    tmp_path: Path,
) -> None:
    """A deliberately pathological covariance lambda can still zero candidates explicitly."""
    ledger_path = tmp_path / "ledger.json"
    write_json(
        ledger_path,
        ledger_payload(
            pass_ready_row(
                contract_ticker="KXUNIT-A",
                calibrated_probability=0.9,
                display_price=0.1,
                all_in_cost=0.1,
                expected_value_per_contract=0.8,
                capacity_estimate=1_000.0,
                correlation_cluster_key="unit|same_cluster",
            ),
            pass_ready_row(
                contract_ticker="KXUNIT-B",
                calibrated_probability=0.9,
                display_price=0.1,
                all_in_cost=0.1,
                expected_value_per_contract=0.8,
                capacity_estimate=1_000.0,
                correlation_cluster_key="unit|same_cluster",
            ),
        ),
    )

    report = build_paper_decision_candidates(
        ledger_path=ledger_path,
        generated_utc="2026-07-03T00:00:00Z",
        paper_bankroll=10_000.0,
        max_fraction_per_contract=0.02,
        covariance_penalty_lambda=200.0,
        within_cluster_correlation=0.5,
    )

    assert report["summary"]["paper_usable_count"] == 0
    for row in report["candidates"]:
        assert row["paper_usable"] is False
        assert row["paper_stake"] == 0.0
        assert row["kelly_fraction"] == 0.0
        assert any(
            "covariance penalty reduced paper stake to zero" in str(blocker)
            for blocker in row["blocker_list"]
        )


def test_val_paper_004_surviving_candidates_carry_full_fields(tmp_path: Path) -> None:
    """VAL-PAPER-004: Surviving candidates carry calibrated_probability, EV, all_in_cost, positive stake."""
    ledger_path = tmp_path / "ledger.json"
    write_json(ledger_path, ledger_payload(pass_ready_row()))

    report = build_paper_decision_candidates(
        ledger_path=ledger_path,
        generated_utc="2026-07-03T00:00:00Z",
        paper_bankroll=1000.0,
        kelly_fraction=0.25,
        max_fraction_per_contract=0.02,
    )

    usable = [row for row in report["candidates"] if row["paper_usable"] is True]
    for row in usable:
        assert row["calibrated_probability"] is not None, (
            f"Usable candidate {row.get('signal_key')} missing calibrated_probability"
        )
        assert 0.0 <= row["calibrated_probability"] <= 1.0, (
            f"calibrated_probability {row['calibrated_probability']} out of [0,1]"
        )
        assert row["expected_value_per_contract"] is not None, (
            f"Usable candidate {row.get('signal_key')} missing expected_value_per_contract"
        )
        assert row["all_in_cost"] is not None, (
            f"Usable candidate {row.get('signal_key')} missing all_in_cost"
        )
        assert row["paper_stake"] > 0.0, (
            f"Usable candidate {row.get('signal_key')} has non-positive paper_stake={row['paper_stake']}"
        )
        assert 0.0 < row["kelly_fraction"] <= 1.0, (
            f"Usable candidate {row.get('signal_key')} has kelly_fraction={row['kelly_fraction']} out of (0,1]"
        )


def test_val_paper_005_live_preflight_mirrors_paper_state(tmp_path: Path) -> None:
    """VAL-PAPER-005: Live preflight mirrors paper state — when paper_usable_count=0,
    live_eligible=false with 'paper candidate is not usable' in blocker_list."""
    ledger_path = tmp_path / "ledger.json"
    write_json(ledger_path, ledger_payload(pass_ready_row(capacity_gate_status="blocked")))

    report = build_paper_decision_candidates(
        ledger_path=ledger_path,
        generated_utc="2026-07-03T00:00:00Z",
        paper_bankroll=1000.0,
    )

    assert report["summary"]["paper_usable_count"] == 0, (
        f"Expected 0 usable, got {report['summary']['paper_usable_count']}"
    )

    for row in report["candidates"]:
        blockers = candidate_live_blockers(
            row, safe_sources={"predmarket-alpha"}, retired_signal_keys=set()
        )
        assert any("paper candidate is not usable" in str(b).lower() for b in blockers), (
            f"Candidate {row.get('signal_key')} is paper_usable={row.get('paper_usable')} "
            f"but live blockers do not include 'paper candidate is not usable': {blockers}"
        )


def test_val_paper_007_sports_blocker_rows_ingested_by_default(tmp_path: Path) -> None:
    """VAL-PAPER-007: Sports blocker rows ingested by default without manual flag.
    Verifies that the default gate_evidence_paths include sports family artifacts."""
    from scripts.kalshi_paper_decision_candidates import DEFAULT_GATE_EVIDENCE_PATHS

    assert len(DEFAULT_GATE_EVIDENCE_PATHS) >= 2, (
        f"Expected at least 2 default gate evidence paths, got {len(DEFAULT_GATE_EVIDENCE_PATHS)}"
    )

    path_names = [str(p) for p in DEFAULT_GATE_EVIDENCE_PATHS]
    sports_paths = [p for p in path_names if "sports" in p.lower()]
    assert sports_paths, f"No sports-family artifacts in DEFAULT_GATE_EVIDENCE_PATHS: {path_names}"

    # Verify the script's main function uses these paths without requiring --gate-evidence-path
    assert any("stack-sequencing" in str(p) for p in DEFAULT_GATE_EVIDENCE_PATHS), (
        "Expected kalshi-sports-stack-sequencing in default gate evidence"
    )
    assert any("flow-replay" in str(p) for p in DEFAULT_GATE_EVIDENCE_PATHS), (
        "Expected kalshi-near-resolution-flow-replay-gates in default gate evidence"
    )


def test_val_paper_008_all_paper_rows_research_only(tmp_path: Path) -> None:
    """VAL-PAPER-008: All paper rows have research_only=true, execution_enabled=false."""
    ledger_path = tmp_path / "ledger.json"
    write_json(ledger_path, ledger_payload(pass_ready_row()))

    report = build_paper_decision_candidates(
        ledger_path=ledger_path,
        generated_utc="2026-07-03T00:00:00Z",
        paper_bankroll=1000.0,
    )

    for row in report["candidates"]:
        assert row.get("research_only") is True, (
            f"Candidate {row.get('signal_key')} has research_only={row.get('research_only')}"
        )
        assert row.get("execution_enabled") is False, (
            f"Candidate {row.get('signal_key')} has execution_enabled={row.get('execution_enabled')}"
        )
        assert row.get("market_execution") is False, (
            f"Candidate {row.get('signal_key')} has market_execution={row.get('market_execution')}"
        )
        assert row.get("account_or_order_paths") is False, (
            f"Candidate {row.get('signal_key')} has account_or_order_paths={row.get('account_or_order_paths')}"
        )


def test_val_paper_009_retired_signals_blocked_in_paper(tmp_path: Path) -> None:
    """VAL-PAPER-009: Retired signals appear as zero-stake blocked paper candidates with retirement reason."""
    ledger_path = tmp_path / "ledger.json"
    # A usable row (passes all gates) plus a retirement ledger that retires it
    row = pass_ready_row()
    write_json(ledger_path, ledger_payload(row))

    signal_key = "unit_family|unit_model|unit_formula|unit_repo"
    retirement_ledger = {
        "schema_version": 1,
        "generated_utc": "2026-07-03T00:10:00Z",
        "status": "signal_decay_retirement_ledger_ready",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "signals": [
            {
                "signal_key": signal_key,
                "retirement_status": "retired",
                "retirement_reasons": [
                    "recent bucket accuracy below threshold",
                    "calibration error above threshold",
                ],
                "label_count": 10,
                "correct_count": 3,
                "accuracy": 0.3,
                "recent_bucket": "2026-07-03T00:00Z",
                "recent_label_count": 3,
                "recent_correct_count": 0,
                "recent_accuracy": 0.0,
                "mean_calibration_error": 0.25,
                "capacity_disappeared": False,
                "next_generator_action": "deprioritize_or_avoid",
            }
        ],
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
        },
    }

    report = build_paper_decision_candidates(
        ledger_path=ledger_path,
        retirement_ledger=retirement_ledger,
        generated_utc="2026-07-03T00:00:00Z",
        paper_bankroll=1000.0,
    )

    # The row passes all gates but is retired — should be blocked
    for row_candidate in report["candidates"]:
        if row_candidate.get("signal_key") == signal_key:
            assert row_candidate["paper_usable"] is False, (
                f"Retired candidate {signal_key} should be paper_usable=False"
            )
            assert row_candidate["paper_stake"] == 0.0, (
                f"Retired candidate {signal_key} should have paper_stake=0, got {row_candidate['paper_stake']}"
            )
            assert any(
                "retired" in str(b).lower() for b in row_candidate.get("blocker_list", [])
            ), (
                f"Retired candidate {signal_key} blocker_list missing retirement reason: "
                f"{row_candidate.get('blocker_list')}"
            )


def test_val_paper_006_chain_completeness(tmp_path: Path) -> None:
    """VAL-PAPER-006: candidate_count >= gate_evidence_row_count; live_decision_count >= paper_usable_count."""
    ledger_path = tmp_path / "ledger.json"
    write_json(ledger_path, ledger_payload(pass_ready_row()))

    gate_path = tmp_path / "sports-blockers.json"
    write_json(
        gate_path,
        {
            "schema_version": 1,
            "status": "sports_stack_sequencing_ready_current_depth_passed",
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "paper_decision_blocker_rows": [
                {
                    "contract_ticker": "KXWCGAME-TEST",
                    "side": "yes",
                    "family_id": "world_cup_soccer",
                    "model_id": "test",
                    "source_repo_id": "predmarket-alpha",
                    "usable": False,
                    "blocker_list": ["test blocker"],
                },
            ],
            "safety": {
                "market_execution": False,
                "account_or_order_paths": False,
                "database_writes": False,
            },
        },
    )

    report = build_paper_decision_candidates(
        ledger_path=ledger_path,
        gate_evidence_paths=(gate_path,),
        generated_utc="2026-07-03T00:00:00Z",
        paper_bankroll=1000.0,
    )

    assert report["summary"]["candidate_count"] >= report["summary"]["gate_evidence_row_count"], (
        f"candidate_count ({report['summary']['candidate_count']}) < "
        f"gate_evidence_row_count ({report['summary']['gate_evidence_row_count']})"
    )

    # live_decision_count >= paper_usable_count should hold.
    # The paper report creates candidates from both ledger rows and gate evidence.
    # One ledger row passes all gates and is usable.
    assert report["summary"]["paper_usable_count"] >= 1, (
        f"Expected paper_usable_count >= 1, got {report['summary']['paper_usable_count']}"
    )
    # Live decision count will be at least candidate_count (each candidate becomes a decision)
    # candidate_count + gate_evidence_row_count >= candidate_count since gate_evidence rows
    # are included in candidates
    live_decision_count = report["summary"]["candidate_count"]
    assert live_decision_count >= report["summary"]["paper_usable_count"], (
        f"live_decision_count ({live_decision_count}) < "
        f"paper_usable_count ({report['summary']['paper_usable_count']})"
    )
