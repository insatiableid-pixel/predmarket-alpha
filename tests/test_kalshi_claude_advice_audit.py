from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kalshi_claude_advice_audit.py"
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_module():
    spec = importlib.util.spec_from_file_location("kalshi_claude_advice_audit", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def safe_artifact(status: str, **summary):
    return {
        "schema_version": 1,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "summary": summary,
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }


def base_inputs(tmp_path: Path) -> dict[str, Path]:
    return {
        "flow_gate": write_json(
            tmp_path / "flow_gate.json",
            safe_artifact(
                "near_resolution_informed_flow_research_candidates_ready",
                research_candidate_count=1,
                testable_candidate_count=4,
                min_oos_labels=10,
                min_settled_contracts=30,
            ),
        ),
        "flow_replay": write_json(
            tmp_path / "flow_replay.json",
            safe_artifact(
                "near_resolution_flow_replay_gates_ready_for_ev_ledger_promotion",
                capacity_positive_row_count=10,
                positive_correlation_cluster_count=5,
                min_positive_correlation_clusters=3,
                decay_status="recent_bucket_not_worse_than_random",
            ),
        ),
        "ev": write_json(
            tmp_path / "ev.json",
            safe_artifact("kalshi_ev_ledger_ready_with_usable_contract_edges", usable_row_count=24),
        ),
        "paper": write_json(
            tmp_path / "paper.json",
            safe_artifact(
                "paper_decision_candidates_ready_with_paper_sized_rows",
                paper_usable_count=10,
            ),
        ),
        "passive": write_json(
            tmp_path / "passive.json",
            safe_artifact(
                "passive_liquidity_paper_fill_falsification_ready_no_research_candidates",
                valid_paper_fill_label_count=1826,
                paper_filled_count=597,
                min_independent_labels=30,
                min_oos_labels=10,
                min_oos_fills=3,
                tested_hypothesis_count=3,
                fdr_survivor_count=0,
                research_candidate_count=0,
                best_candidate_net_ev=-0.03,
            ),
        ),
        "atp": write_json(
            tmp_path / "atp.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_forward_oos",
                forward_oos_resolved=2,
                forward_oos_min_probe=10,
                next_expected_expiration_utc="2026-07-06T06:00:00Z",
            ),
        ),
        "world_cup": write_json(
            tmp_path / "world_cup.json",
            safe_artifact(
                "world_cup_outcome_independence_diagnostic_ready_parallel_outcome_clocks",
                outcome_level_parallel_clock_supported=True,
                current_candidate_independence_requires_review=False,
                recommended_portfolio_cluster_unit="world_cup_match",
                non_match_result_outcome_family_count=8,
            ),
        ),
        "prior": write_json(
            tmp_path / "prior.json",
            safe_artifact(
                "prior_only_donor_gate_ready",
                eligible_prior_context_count=797,
                settlement_label_credit_count=0,
                independent_label_credit_count=0,
                oos_label_credit_count=0,
                paper_usable_count=0,
                live_eligible_count=0,
                direct_probability_promotion_count=0,
            ),
        ),
        "velocity": write_json(
            tmp_path / "velocity.json",
            safe_artifact(
                "sports_event_velocity_eta_ready_with_label_deficits",
                total_label_deficit=119,
                total_oos_deficit=54,
                next_probe_surface={
                    "surface_id": "sports_consensus_rule_bucket_accumulation",
                    "next_probe_utc": "2026-07-06T03:00:00Z",
                },
            ),
        ),
        "live": write_json(
            tmp_path / "live.json",
            {
                **safe_artifact(
                    "kalshi_live_blocked",
                    live_eligible_count=0,
                    total_live_stake=0,
                ),
                "safety": {
                    "market_orders": False,
                    "execution_enabled": False,
                    "market_execution": False,
                },
            },
        ),
        "line_move": write_json(
            tmp_path / "line_move.json",
            safe_artifact(
                "kalshi_sports_line_move_delta_logger_ready_with_deltas",
                snapshot_count=4,
                event_count=99,
                delta_count=23,
                line_move_count=23,
                error_count=0,
            ),
        ),
        "tick_recorder": write_json(
            tmp_path / "tick_recorder.json",
            safe_artifact(
                "kalshi_tick_recorder_blocked_missing_or_invalid_auth",
                ticker_count=250,
                channel_counts={"ticker": 1, "orderbook_delta": 1},
                recorded_line_count=0,
                gap_count=0,
            ),
        ),
        "resolved_archive": write_json(
            tmp_path / "resolved_archive.json",
            safe_artifact(
                "kalshi_resolved_archive_backfill_ready_no_fdr_survivors",
                label_count=1184,
                distinct_contract_count=1184,
                observation_count=3552,
                tested_hypothesis_count=2,
                fdr_survivor_count=0,
            ),
        ),
        "historical_feasibility": write_json(
            tmp_path / "historical_feasibility.json",
            safe_artifact(
                "kalshi_sports_historical_consensus_feasibility_ready_paid_access_unverified",
                snapshot_interval_seconds=300,
                max_expected_absolute_skew_seconds=150.0,
                max_allowed_skew_seconds=180,
                skew_gate_pass=True,
                paid_access_verified=False,
            ),
        ),
        "historical_backfill": write_json(
            tmp_path / "historical_backfill.json",
            safe_artifact(
                "kalshi_sports_historical_consensus_backfill_blocked_missing_historical_archive",
                historical_consensus_row_count=0,
                valid_observation_count=0,
                tested_hypothesis_count=0,
                fdr_survivor_count=0,
            ),
        ),
    }


def test_claude_advice_audit_classifies_current_goal_state(tmp_path: Path) -> None:
    module = load_module()
    files = base_inputs(tmp_path)

    report = module.build_claude_advice_audit(
        flow_gate_path=files["flow_gate"],
        flow_replay_path=files["flow_replay"],
        ev_ledger_path=files["ev"],
        paper_path=files["paper"],
        passive_fill_path=files["passive"],
        atp_path=files["atp"],
        world_cup_independence_path=files["world_cup"],
        prior_only_path=files["prior"],
        event_velocity_path=files["velocity"],
        live_path=files["live"],
        line_move_path=files["line_move"],
        tick_recorder_path=files["tick_recorder"],
        resolved_archive_path=files["resolved_archive"],
        historical_feasibility_path=files["historical_feasibility"],
        historical_backfill_path=files["historical_backfill"],
        generated_utc="2026-07-06T02:40:00Z",
    )

    rows = {row["requirement_id"]: row for row in report["advice_rows"]}
    assert report["status"] == "claude_advice_audit_ready_with_open_clock_or_statistical_items"
    assert report["summary"]["requirement_count"] == 14
    assert rows["CLAUDE-001"]["status"] == "satisfied"
    assert rows["CLAUDE-002"]["status"] == "satisfied"
    assert rows["CLAUDE-003"]["status"] == "satisfied"
    assert rows["CLAUDE-004"]["status"] == "satisfied"
    assert rows["CLAUDE-005"]["status"] == "blocked_clock"
    assert rows["CLAUDE-005"]["implementation_status"] == "satisfied"
    assert rows["CLAUDE-006"]["status"] == "satisfied"
    assert rows["CLAUDE-007"]["status"] == "satisfied"
    assert rows["CLAUDE-008"]["status"] == "blocked_clock"
    assert rows["CLAUDE-008"]["implementation_status"] == "satisfied"
    assert rows["CLAUDE-009"]["status"] == "satisfied"
    assert rows["CLAUDE-010"]["status"] == "satisfied"
    assert rows["CLAUDE-011"]["status"] == "satisfied"
    assert rows["CLAUDE-011"]["implementation_status"] == "satisfied"
    assert rows["CLAUDE-012"]["status"] == "blocked_external"
    assert rows["CLAUDE-012"]["implementation_status"] == "satisfied"
    assert rows["CLAUDE-013"]["status"] == "satisfied"
    assert rows["CLAUDE-013"]["implementation_status"] == "satisfied"
    assert rows["CLAUDE-014"]["status"] == "blocked_external"
    assert rows["CLAUDE-014"]["implementation_status"] == "satisfied"
    assert report["summary"]["implementation_satisfied_count"] == 14
    assert report["summary"]["implementation_open_requirement_ids"] == []
    assert report["next_action"]["name"] == "kalshi_tick_orderbook_delta_capture"
    assert report["execution_enabled"] is False
    assert report["market_execution"] is False


def test_claude_advice_audit_treats_price_null_rejection_as_implemented(
    tmp_path: Path,
) -> None:
    module = load_module()
    files = base_inputs(tmp_path)
    files["flow_gate"] = write_json(
        tmp_path / "flow_gate_rejected.json",
        safe_artifact(
            "near_resolution_informed_flow_falsification_ready_no_research_candidate",
            research_candidate_count=0,
            testable_candidate_count=3,
            min_oos_labels=10,
            min_settled_contracts=30,
        ),
    )
    files["flow_replay"] = write_json(
        tmp_path / "flow_replay_rejected.json",
        safe_artifact(
            "near_resolution_flow_replay_gates_blocked_missing_research_candidate",
            capacity_positive_row_count=0,
            positive_correlation_cluster_count=0,
            min_positive_correlation_clusters=3,
            decay_status="recent_bucket_not_worse_than_random",
        ),
    )

    report = module.build_claude_advice_audit(
        flow_gate_path=files["flow_gate"],
        flow_replay_path=files["flow_replay"],
        ev_ledger_path=files["ev"],
        paper_path=files["paper"],
        passive_fill_path=files["passive"],
        atp_path=files["atp"],
        world_cup_independence_path=files["world_cup"],
        prior_only_path=files["prior"],
        event_velocity_path=files["velocity"],
        live_path=files["live"],
        line_move_path=files["line_move"],
        tick_recorder_path=files["tick_recorder"],
        resolved_archive_path=files["resolved_archive"],
        historical_feasibility_path=files["historical_feasibility"],
        historical_backfill_path=files["historical_backfill"],
        generated_utc="2026-07-07T05:00:00Z",
    )

    rows = {row["requirement_id"]: row for row in report["advice_rows"]}
    assert rows["CLAUDE-001"]["status"] == "satisfied"
    assert rows["CLAUDE-001"]["implementation_status"] == "satisfied"
    assert rows["CLAUDE-002"]["status"] == "satisfied"
    assert rows["CLAUDE-002"]["implementation_status"] == "satisfied"
    assert report["summary"]["implementation_satisfied_count"] == 14
    assert report["summary"]["implementation_open_requirement_ids"] == []


def test_claude_advice_audit_satisfies_tick_capture_after_recording(tmp_path: Path) -> None:
    module = load_module()
    files = base_inputs(tmp_path)
    files["tick_recorder"] = write_json(
        tmp_path / "tick_recorder_ready.json",
        safe_artifact(
            "kalshi_tick_recorder_ready",
            ticker_count=250,
            channel_counts={"ticker": 1, "orderbook_delta": 1},
            recorded_line_count=42,
            gap_count=0,
        ),
    )

    report = module.build_claude_advice_audit(
        flow_gate_path=files["flow_gate"],
        flow_replay_path=files["flow_replay"],
        ev_ledger_path=files["ev"],
        paper_path=files["paper"],
        passive_fill_path=files["passive"],
        atp_path=files["atp"],
        world_cup_independence_path=files["world_cup"],
        prior_only_path=files["prior"],
        event_velocity_path=files["velocity"],
        live_path=files["live"],
        line_move_path=files["line_move"],
        tick_recorder_path=files["tick_recorder"],
        resolved_archive_path=files["resolved_archive"],
        historical_feasibility_path=files["historical_feasibility"],
        historical_backfill_path=files["historical_backfill"],
        generated_utc="2026-07-07T05:00:00Z",
    )

    rows = {row["requirement_id"]: row for row in report["advice_rows"]}
    assert rows["CLAUDE-012"]["status"] == "satisfied"
    assert rows["CLAUDE-012"]["implementation_status"] == "satisfied"


def test_claude_advice_audit_blocks_underpowered_resolved_archive(tmp_path: Path) -> None:
    module = load_module()
    files = base_inputs(tmp_path)
    files["resolved_archive"] = write_json(
        tmp_path / "resolved_archive_underpowered.json",
        safe_artifact(
            "kalshi_resolved_archive_backfill_ready_insufficient_test_power",
            label_count=999,
            distinct_contract_count=999,
            observation_count=2997,
            tested_hypothesis_count=0,
            fdr_survivor_count=0,
        ),
    )

    report = module.build_claude_advice_audit(
        flow_gate_path=files["flow_gate"],
        flow_replay_path=files["flow_replay"],
        ev_ledger_path=files["ev"],
        paper_path=files["paper"],
        passive_fill_path=files["passive"],
        atp_path=files["atp"],
        world_cup_independence_path=files["world_cup"],
        prior_only_path=files["prior"],
        event_velocity_path=files["velocity"],
        live_path=files["live"],
        line_move_path=files["line_move"],
        tick_recorder_path=files["tick_recorder"],
        resolved_archive_path=files["resolved_archive"],
        historical_feasibility_path=files["historical_feasibility"],
        historical_backfill_path=files["historical_backfill"],
        generated_utc="2026-07-07T05:00:00Z",
    )

    rows = {row["requirement_id"]: row for row in report["advice_rows"]}
    assert rows["CLAUDE-013"]["status"] == "blocked_clock"
    assert rows["CLAUDE-013"]["implementation_status"] == "satisfied"


def test_claude_advice_audit_satisfies_historical_consensus_backfill(
    tmp_path: Path,
) -> None:
    module = load_module()
    files = base_inputs(tmp_path)
    files["historical_feasibility"] = write_json(
        tmp_path / "historical_feasibility_ready.json",
        safe_artifact(
            "kalshi_sports_historical_consensus_feasibility_ready_for_backfill",
            snapshot_interval_seconds=300,
            max_expected_absolute_skew_seconds=150.0,
            max_allowed_skew_seconds=180,
            skew_gate_pass=True,
            paid_access_verified=True,
        ),
    )
    files["historical_backfill"] = write_json(
        tmp_path / "historical_backfill_ready.json",
        safe_artifact(
            "kalshi_sports_historical_consensus_backfill_ready_no_research_candidates",
            historical_consensus_row_count=1200,
            valid_observation_count=1200,
            tested_hypothesis_count=4,
            fdr_survivor_count=0,
        ),
    )

    report = module.build_claude_advice_audit(
        flow_gate_path=files["flow_gate"],
        flow_replay_path=files["flow_replay"],
        ev_ledger_path=files["ev"],
        paper_path=files["paper"],
        passive_fill_path=files["passive"],
        atp_path=files["atp"],
        world_cup_independence_path=files["world_cup"],
        prior_only_path=files["prior"],
        event_velocity_path=files["velocity"],
        live_path=files["live"],
        line_move_path=files["line_move"],
        tick_recorder_path=files["tick_recorder"],
        resolved_archive_path=files["resolved_archive"],
        historical_feasibility_path=files["historical_feasibility"],
        historical_backfill_path=files["historical_backfill"],
        generated_utc="2026-07-07T05:00:00Z",
    )

    rows = {row["requirement_id"]: row for row in report["advice_rows"]}
    assert rows["CLAUDE-014"]["status"] == "satisfied"
    assert rows["CLAUDE-014"]["implementation_status"] == "satisfied"


def test_claude_advice_audit_temp_out_dir_does_not_write_latest(
    tmp_path: Path, monkeypatch
) -> None:
    module = load_module()
    macro_dir = tmp_path / "macro"
    monkeypatch.setattr(module, "MACRO_DIR", macro_dir)
    report = {
        "status": "claude_advice_audit_ready_all_items_satisfied",
        "summary": {"requirement_count": 0},
        "advice_rows": [],
        "next_action": {"name": "done", "why": "done", "stop_condition": "done"},
    }
    paths = module.write_outputs(report, out_dir=tmp_path / "out")

    assert "latest_json_path" not in paths
    assert not (macro_dir / "latest-kalshi-claude-advice-audit.json").exists()


def test_claude_advice_audit_makefile_target_exists() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-claude-advice-audit" in text
    assert "scripts/kalshi_claude_advice_audit.py" in text
