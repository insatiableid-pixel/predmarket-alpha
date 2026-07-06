from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_evidence_cycle_report.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_sports_evidence_cycle_report", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def safe_artifact(status: str = "ready", **summary):
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
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }


def live_artifact(**summary):
    return {
        "schema_version": 1,
        "status": "kalshi_live_blocked",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "summary": summary,
        "safety": {
            "manual_approval_queue": False,
            "market_orders": False,
            "production_requires_env_arm": True,
        },
    }


def test_sports_evidence_cycle_report_summarizes_safe_label_progress(tmp_path: Path) -> None:
    module = load_module()
    files = {
        "universe": write_json(tmp_path / "universe.json", safe_artifact()),
        "sports_obs": write_json(
            tmp_path / "sports_obs.json",
            safe_artifact(
                total_observation_row_count=10, distinct_contract_count=8, label_row_count=2
            ),
        ),
        "sports_model": write_json(
            tmp_path / "sports_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=2,
                independent_contract_label_count=1,
            ),
        ),
        "sports_replay": write_json(tmp_path / "sports_replay.json", safe_artifact()),
        "sports_ccd": write_json(tmp_path / "sports_ccd.json", safe_artifact()),
        "sports_cluster": write_json(
            tmp_path / "sports_cluster.json",
            safe_artifact(positive_cluster_count=3),
        ),
        "atp_obs": write_json(tmp_path / "atp_obs.json", safe_artifact()),
        "atp_evidence": write_json(tmp_path / "atp_evidence.json", safe_artifact()),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=12, label_row_count=3),
        ),
        "wc_model": write_json(tmp_path / "wc_model.json", safe_artifact(valid_label_row_count=3)),
        "wc_outcome_independence": write_json(
            tmp_path / "wc_outcome_independence.json",
            safe_artifact(
                "world_cup_outcome_independence_diagnostic_ready_candidate_independence_review",
                exact_contract_label_count=93,
                outcome_family_label_count=22,
                match_cluster_count=3,
                current_candidate_independence_requires_review=True,
                recommended_portfolio_cluster_unit="world_cup_match",
            ),
        ),
        "stack": write_json(
            tmp_path / "stack.json",
            {
                **safe_artifact(candidate_count=200),
                "paper_decision_blocker_rows": [{"contract_ticker": f"KX-{i}"} for i in range(90)],
            },
        ),
        "consensus": write_json(
            tmp_path / "consensus.json",
            safe_artifact(
                "sports_consensus_preflight_ready",
                reference_row_count=4,
                candidate_count=2,
                valid_candidate_count=2,
                blocker_count=0,
            ),
        ),
        "consensus_observation": write_json(
            tmp_path / "consensus_observation.json",
            safe_artifact(
                "sports_consensus_observation_loop_ready_waiting_settlement",
                total_observation_row_count=2,
                new_observation_row_count=2,
                label_row_count=0,
                new_label_row_count=0,
                due_distinct_contract_count=0,
            ),
        ),
        "consensus_falsification": write_json(
            tmp_path / "consensus_falsification.json",
            safe_artifact(
                "sports_consensus_falsification_blocked_insufficient_labels",
                joined_label_count=0,
                independent_label_count=0,
                tested_hypothesis_count=0,
                max_hypothesis_oos_count=0,
                hypothesis_accumulation_plan_count=30,
                nearest_hypothesis_oos_deficit=10,
                nearest_hypothesis_model_id=(
                    "sports_consensus_price_bucket_bias_bucket_0.50_0.70"
                ),
                hypothesis_accumulation_opportunity_count=4,
                hypothesis_accumulation_opportunity_distinct_contract_count=2,
                nearest_hypothesis_current_opportunity_count=2,
                fdr_survivor_count=0,
            ),
        ),
        "consensus_provider_audit": write_json(
            tmp_path / "consensus_provider_audit.json",
            safe_artifact(
                "sports_consensus_provider_audit_ready_with_per_sport_gaps",
                sport_target_count=5,
                sport_covered_count=1,
                sport_deferred_count=1,
                sport_gap_count=3,
                strict_consensus_sport_count=2,
                strict_consensus_sports=["tennis", "soccer"],
                covered_sports=["tennis"],
                deferred_sports=["nba"],
                actionable_gap_sports=["mlb", "soccer", "nfl"],
            ),
        ),
        "soccer_asian_provider": write_json(
            tmp_path / "soccer_asian_provider.json",
            safe_artifact(
                "soccer_asian_provider_diagnostic_blocked_target_books_unavailable_in_feed",
                requested_target_provider_count=3,
                observed_target_provider_count=0,
                missing_target_providers=["ibc", "sbobet", "singbet"],
                latest_capture_utc="2026-07-05T23:50:33Z",
            ),
        ),
        "event_velocity": write_json(
            tmp_path / "event_velocity.json",
            {
                **safe_artifact(
                    "sports_event_velocity_eta_ready_with_label_deficits",
                    label_blocked_surface_count=4,
                    paper_fill_blocked_surface_count=1,
                    total_label_deficit=44,
                    total_oos_deficit=17,
                    eta_status_counts={
                        "next_probe_due_now": 2,
                        "waiting_for_next_probe_or_settlement": 1,
                    },
                    bottleneck_type_counts={
                        "calendar_settlement_labels": 3,
                        "paper_fill_clock": 1,
                    },
                    next_due_surface={"surface_id": "sports_consensus_all", "due_count": 2},
                    next_probe_surface={
                        "surface_id": "sports_consensus_rule_bucket_accumulation",
                        "next_probe_utc": "2026-07-06T02:20:00Z",
                        "oos_deficit": 5,
                    },
                ),
                "eta_rows": [
                    {
                        "surface_id": "sports_consensus_rule_bucket_accumulation",
                        "model_id": "sports_consensus_price_bucket_bias_bucket_0.50_0.70",
                        "oos_label_count": 5,
                        "oos_deficit": 5,
                        "hypothesis_accumulation_opportunity_count": 239,
                        "nearest_hypothesis_current_opportunity_count": 32,
                        "next_probe_utc": "2026-07-06T02:20:00Z",
                        "eta_days": 0.0251,
                    }
                ],
            },
        ),
        "micro": write_json(
            tmp_path / "micro.json",
            safe_artifact(historical_observation_row_count=20, repeated_snapshot_contract_count=5),
        ),
        "flow": write_json(
            tmp_path / "flow.json",
            safe_artifact(forward_quote_label_count=4, repeated_snapshot_contract_count=5),
        ),
        "flow_replay": write_json(
            tmp_path / "flow_replay.json",
            safe_artifact(current_candidate_row_count=2, research_candidate_count=1),
        ),
        "flow_terms": write_json(
            tmp_path / "flow_terms.json",
            safe_artifact(official_rules_market_count=2, captured_target_count=2),
        ),
        "passive": write_json(
            tmp_path / "passive.json",
            safe_artifact(counterfactual_fill_proxy_label_count=2, would_touch_proxy_count=1),
        ),
        "passive_paper_fill": write_json(
            tmp_path / "passive_paper_fill.json",
            safe_artifact(
                "passive_liquidity_paper_fill_loop_accumulating_intents",
                paper_intent_count=3,
                new_paper_intent_count=2,
                open_paper_intent_count=3,
                paper_fill_label_count=0,
                new_paper_fill_label_count=0,
                real_exchange_fill_label_count=0,
            ),
        ),
        "passive_paper_fill_falsification": write_json(
            tmp_path / "passive_paper_fill_falsification.json",
            safe_artifact(
                "passive_liquidity_paper_fill_falsification_blocked_no_paper_fill_labels",
                valid_paper_fill_label_count=0,
                paper_filled_count=0,
                tested_hypothesis_count=0,
                fdr_survivor_count=0,
            ),
        ),
        "passive_fill_clock_diagnostic": write_json(
            tmp_path / "passive_fill_clock_diagnostic.json",
            safe_artifact(
                "passive_liquidity_fill_clock_diagnostic_ready_ttl_cadence_mismatch",
                fill_clock_primary_bottleneck="ttl_shorter_than_snapshot_cadence",
                ttl_cadence_mismatch_count=3,
                active_ttl_cadence_mismatch_count=3,
                current_ttl_cadence_aligned=False,
                future_snapshot_within_ttl_intent_count=0,
                recommended_ttl_seconds=600,
            ),
        ),
        "paper": write_json(
            tmp_path / "paper.json",
            safe_artifact(
                candidate_count=90,
                gate_evidence_row_count=90,
                paper_usable_count=0,
                total_paper_stake=0.0,
                paper_portfolio_cap_status="paper_portfolio_caps_observed",
            ),
        ),
        "paper_settlement": write_json(
            tmp_path / "paper_settlement.json",
            safe_artifact(
                "paper_settlement_reconciliation_waiting_for_close",
                paper_usable_count=0,
                settled_paper_usable_count=0,
                next_unresolved_close_time_utc="2026-07-04T19:30:00Z",
                total_paper_stake=0.0,
                paper_portfolio_cap_status="paper_portfolio_caps_observed",
                paper_portfolio_largest_cluster={},
                realized_pnl=0.0,
            ),
        ),
        "live": write_json(
            tmp_path / "live.json",
            live_artifact(live_decision_count=90, live_eligible_count=0),
        ),
        "retirement": write_json(tmp_path / "retirement.json", safe_artifact()),
    }

    report = module.build_sports_evidence_cycle_report(
        universe_path=files["universe"],
        sports_observation_path=files["sports_obs"],
        sports_model_path=files["sports_model"],
        sports_replay_path=files["sports_replay"],
        sports_ccd_path=files["sports_ccd"],
        sports_cluster_path=files["sports_cluster"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        world_cup_outcome_independence_path=files["wc_outcome_independence"],
        stack_path=files["stack"],
        consensus_path=files["consensus"],
        consensus_observation_path=files["consensus_observation"],
        consensus_falsification_path=files["consensus_falsification"],
        consensus_provider_audit_path=files["consensus_provider_audit"],
        soccer_asian_provider_path=files["soccer_asian_provider"],
        event_velocity_path=files["event_velocity"],
        microstructure_path=files["micro"],
        flow_path=files["flow"],
        flow_replay_path=files["flow_replay"],
        flow_terms_path=files["flow_terms"],
        passive_path=files["passive"],
        passive_paper_fill_path=files["passive_paper_fill"],
        passive_paper_fill_falsification_path=files["passive_paper_fill_falsification"],
        passive_fill_clock_diagnostic_path=files["passive_fill_clock_diagnostic"],
        paper_path=files["paper"],
        paper_settlement_path=files["paper_settlement"],
        live_path=files["live"],
        retirement_path=files["retirement"],
        generated_utc="2026-07-04T01:00:00Z",
    )

    assert report["status"] == "sports_evidence_cycle_ready_with_label_progress"
    assert report["summary"]["safe_artifact_count"] == 30
    assert report["summary"]["total_label_count"] == 9
    assert report["summary"]["total_paper_fill_label_count"] == 0
    assert report["summary"]["flow_terms_official_rules_market_count"] == 2
    assert report["summary"]["sports_consensus_valid_candidate_count"] == 2
    assert report["summary"]["sports_consensus_observation_count"] == 2
    assert report["summary"]["sports_consensus_new_observation_count"] == 2
    assert report["summary"]["sports_consensus_label_count"] == 0
    assert report["summary"]["sports_consensus_new_label_count"] == 0
    assert report["summary"]["sports_consensus_observation_status"] == (
        "sports_consensus_observation_loop_ready_waiting_settlement"
    )
    assert (
        report["summary"]["sports_consensus_falsification_status"]
        == "sports_consensus_falsification_blocked_insufficient_labels"
    )
    assert report["summary"]["sports_consensus_falsification_joined_label_count"] == 0
    assert report["summary"]["sports_consensus_falsification_tested_hypothesis_count"] == 0
    assert report["summary"]["sports_consensus_falsification_max_hypothesis_oos_count"] == 0
    assert (
        report["summary"]["sports_consensus_falsification_hypothesis_accumulation_plan_count"]
        == 30
    )
    assert report["summary"]["sports_consensus_falsification_nearest_hypothesis_oos_deficit"] == 10
    assert report["summary"]["sports_consensus_falsification_nearest_hypothesis_model_id"] == (
        "sports_consensus_price_bucket_bias_bucket_0.50_0.70"
    )
    assert (
        report["summary"]["sports_consensus_falsification_accumulation_opportunity_count"]
        == 4
    )
    assert (
        report["summary"][
            "sports_consensus_falsification_accumulation_opportunity_distinct_contract_count"
        ]
        == 2
    )
    assert (
        report["summary"][
            "sports_consensus_falsification_nearest_hypothesis_current_opportunity_count"
        ]
        == 2
    )
    assert report["summary"]["sports_consensus_falsification_fdr_survivor_count"] == 0
    assert report["summary"]["sports_consensus_falsification_research_candidate_count"] == 0
    assert report["summary"]["sports_consensus_provider_audit_status"] == (
        "sports_consensus_provider_audit_ready_with_per_sport_gaps"
    )
    assert report["summary"]["sports_consensus_provider_sport_covered_count"] == 1
    assert report["summary"]["sports_consensus_provider_sport_target_count"] == 5
    assert report["summary"]["sports_consensus_provider_sport_gap_count"] == 3
    assert report["summary"]["sports_consensus_provider_sport_deferred_count"] == 1
    assert report["summary"]["sports_consensus_provider_deferred_sports"] == ["nba"]
    assert report["summary"]["sports_consensus_provider_actionable_gap_sports"] == [
        "mlb",
        "soccer",
        "nfl",
    ]
    assert report["summary"]["soccer_asian_provider_status"] == (
        "soccer_asian_provider_diagnostic_blocked_target_books_unavailable_in_feed"
    )
    assert report["summary"]["soccer_asian_provider_requested_target_provider_count"] == 3
    assert report["summary"]["soccer_asian_provider_observed_target_provider_count"] == 0
    assert report["summary"]["soccer_asian_provider_missing_target_providers"] == [
        "ibc",
        "sbobet",
        "singbet",
    ]
    assert report["summary"]["sports_consensus_provider_strict_consensus_sport_count"] == 2
    assert report["summary"]["sports_consensus_provider_strict_consensus_sports"] == [
        "tennis",
        "soccer",
    ]
    assert report["summary"]["sports_event_velocity_status"] == (
        "sports_event_velocity_eta_ready_with_label_deficits"
    )
    assert report["summary"]["sports_event_velocity_label_blocked_surface_count"] == 4
    assert (
        report["summary"]["sports_event_velocity_actionable_calendar_label_blocked_surface_count"]
        == 0
    )
    assert report["summary"]["sports_event_velocity_external_or_source_blocked_surface_count"] == 0
    assert report["summary"]["sports_event_velocity_paper_fill_blocked_surface_count"] == 1
    assert report["summary"]["sports_event_velocity_total_label_deficit"] == 44
    assert report["summary"]["sports_event_velocity_total_oos_deficit"] == 17
    assert report["summary"]["sports_event_velocity_next_due_surface"] == {
        "surface_id": "sports_consensus_all",
        "due_count": 2,
    }
    assert report["summary"]["sports_event_velocity_next_probe_surface"] == {
        "surface_id": "sports_consensus_rule_bucket_accumulation",
        "next_probe_utc": "2026-07-06T02:20:00Z",
        "oos_deficit": 5,
    }
    assert report["summary"]["sports_event_velocity_eta_status_counts"] == {
        "next_probe_due_now": 2,
        "waiting_for_next_probe_or_settlement": 1,
    }
    assert report["summary"]["sports_event_velocity_bottleneck_type_counts"] == {
        "calendar_settlement_labels": 3,
        "paper_fill_clock": 1,
    }
    assert report["summary"]["sports_event_velocity_consensus_rule_bucket_model_id"] == (
        "sports_consensus_price_bucket_bias_bucket_0.50_0.70"
    )
    assert report["summary"]["sports_event_velocity_consensus_rule_bucket_oos_label_count"] == 5
    assert report["summary"]["sports_event_velocity_consensus_rule_bucket_oos_deficit"] == 5
    assert report["summary"]["sports_event_velocity_consensus_rule_bucket_opportunity_count"] == 239
    assert (
        report["summary"][
            "sports_event_velocity_consensus_rule_bucket_nearest_opportunity_count"
        ]
        == 32
    )
    assert report["summary"]["sports_event_velocity_consensus_rule_bucket_next_probe_utc"] == (
        "2026-07-06T02:20:00Z"
    )
    assert report["summary"]["sports_event_velocity_consensus_rule_bucket_eta_days"] == 0.0251
    assert report["summary"]["world_cup_outcome_independence_status"] == (
        "world_cup_outcome_independence_diagnostic_ready_candidate_independence_review"
    )
    assert report["summary"]["world_cup_outcome_exact_contract_label_count"] == 93
    assert report["summary"]["world_cup_outcome_family_label_count"] == 22
    assert report["summary"]["world_cup_outcome_match_cluster_count"] == 3
    assert report["summary"]["world_cup_outcome_candidate_independence_requires_review"] is True
    assert (
        report["summary"]["world_cup_outcome_recommended_portfolio_cluster_unit"]
        == "world_cup_match"
    )
    assert report["summary"]["passive_paper_fill_status"] == (
        "passive_liquidity_paper_fill_loop_accumulating_intents"
    )
    assert report["summary"]["passive_paper_intent_count"] == 3
    assert report["summary"]["passive_new_paper_intent_count"] == 2
    assert report["summary"]["passive_open_paper_intent_count"] == 3
    assert report["summary"]["passive_paper_fill_label_count"] == 0
    assert report["summary"]["passive_paper_fill_falsification_status"] == (
        "passive_liquidity_paper_fill_falsification_blocked_no_paper_fill_labels"
    )
    assert report["summary"]["passive_paper_fill_falsification_label_count"] == 0
    assert report["summary"]["passive_paper_fill_falsification_fill_count"] == 0
    assert report["summary"]["passive_paper_fill_falsification_tested_hypothesis_count"] == 0
    assert report["summary"]["passive_paper_fill_falsification_fdr_survivor_count"] == 0
    assert report["summary"]["passive_fill_clock_diagnostic_status"] == (
        "passive_liquidity_fill_clock_diagnostic_ready_ttl_cadence_mismatch"
    )
    assert report["summary"]["passive_fill_clock_primary_bottleneck"] == (
        "ttl_shorter_than_snapshot_cadence"
    )
    assert report["summary"]["passive_fill_clock_ttl_cadence_mismatch_count"] == 3
    assert report["summary"]["passive_fill_clock_active_ttl_cadence_mismatch_count"] == 3
    assert report["summary"]["passive_fill_clock_current_ttl_cadence_aligned"] is False
    assert report["summary"]["passive_fill_clock_future_snapshot_within_ttl_count"] == 0
    assert report["summary"]["passive_fill_clock_recommended_ttl_seconds"] == 600
    assert report["summary"]["passive_real_exchange_fill_label_count"] == 0
    assert report["summary"]["paper_settlement_status"] == (
        "paper_settlement_reconciliation_waiting_for_close"
    )
    assert report["summary"]["paper_realized_pnl"] == 0.0
    assert report["summary"]["paper_next_unresolved_close_time_utc"] == "2026-07-04T19:30:00Z"
    assert report["summary"]["paper_total_stake"] == 0.0
    assert report["summary"]["paper_portfolio_cap_status"] == "paper_portfolio_caps_observed"
    assert report["summary"]["sports_stack_blocker_row_count"] == 90
    assert report["summary"]["live_eligible_count"] == 0
    assert report["summary"]["independent_cluster_count"] == 3

    # Verify surface_rows has exactly 5 entries with correct surface_ids
    assert len(report["surface_rows"]) == 5
    surface_ids = [row["surface_id"] for row in report["surface_rows"]]
    assert surface_ids == [
        "mlb",
        "atp",
        "world_cup_soccer",
        "sports_no_vig_consensus",
        "sports_microstructure",
    ]

    # Verify proxy_label_count on each surface
    for row in report["surface_rows"]:
        assert "proxy_label_count" in row
        assert isinstance(row["proxy_label_count"], int)
        assert "paper_fill_label_count" in row
        assert isinstance(row["paper_fill_label_count"], int)
    assert report["summary"]["total_proxy_label_count"] == 2  # only microstructure has proxy labels

    # Verify CSV fields include proxy_label_count
    assert "proxy_label_count" in module.CSV_FIELDS
    assert "paper_fill_label_count" in module.CSV_FIELDS

    # Verify next_action has required fields
    assert "name" in report["next_action"]
    assert "why" in report["next_action"]
    assert "stop_condition" in report["next_action"]
    assert all(report["next_action"].get(k) for k in ("name", "why", "stop_condition"))
    assert report["next_action"]["name"] == "kalshi_sports_exact_settlement_probe"


def test_sports_evidence_cycle_next_action_defers_to_eta_clock() -> None:
    module = load_module()
    status = "sports_evidence_cycle_ready_with_label_progress"

    assert (
        module.next_action(
            status,
            {
                "total_due_count": 28,
                "sports_event_velocity_next_due_surface": None,
                "sports_event_velocity_external_or_source_blocked_surface_count": 3,
                "sports_event_velocity_actionable_calendar_label_blocked_surface_count": 3,
            },
        )["name"]
        == "kalshi_sports_stale_or_source_blocker_refresh"
    )
    assert (
        module.next_action(
            status,
            {
                "total_due_count": 28,
                "sports_event_velocity_next_due_surface": None,
                "sports_event_velocity_next_probe_surface": {
                    "surface_id": "sports_consensus_rule_bucket_accumulation",
                    "next_probe_utc": "2026-07-06T02:20:00Z",
                },
                "sports_event_velocity_external_or_source_blocked_surface_count": 0,
                "sports_event_velocity_actionable_calendar_label_blocked_surface_count": 3,
            },
        )["name"]
        == "kalshi_sports_wait_for_next_settlement_clock"
    )
    action = module.next_action(
        status,
        {
            "total_due_count": 28,
            "sports_event_velocity_next_due_surface": None,
            "sports_event_velocity_next_probe_surface": {
                "surface_id": "sports_consensus_rule_bucket_accumulation",
                "next_probe_utc": "2026-07-06T02:20:00Z",
            },
            "sports_event_velocity_external_or_source_blocked_surface_count": 0,
            "sports_event_velocity_actionable_calendar_label_blocked_surface_count": 3,
        },
    )
    assert "sports_consensus_rule_bucket_accumulation" in action["why"]
    assert (
        module.next_action(
            status,
            {
                "total_due_count": 0,
                "sports_event_velocity_next_due_surface": {
                    "surface_id": "sports_consensus_all",
                    "due_count": 2,
                },
                "sports_event_velocity_external_or_source_blocked_surface_count": 0,
                "sports_event_velocity_actionable_calendar_label_blocked_surface_count": 0,
            },
        )["name"]
        == "kalshi_sports_exact_settlement_probe"
    )


def test_microstructure_blockers_ignore_superseded_proxy_only_passive_gate() -> None:
    module = load_module()
    legacy_proxy_blocker = {
        "status": "passive_liquidity_provision_blocked_proxy_only_no_real_fill_labels"
    }
    ready_paper_fill_falsification = {
        "status": "passive_liquidity_paper_fill_falsification_ready_no_research_candidates"
    }

    assert module.microstructure_blockers(
        flow={},
        flow_replay={},
        passive=legacy_proxy_blocker,
        passive_paper_fill={},
        passive_paper_fill_falsification=ready_paper_fill_falsification,
        paper_fill_label_count=10,
    ) == []

    assert module.microstructure_blockers(
        flow={},
        flow_replay={},
        passive=legacy_proxy_blocker,
        passive_paper_fill={},
        passive_paper_fill_falsification=ready_paper_fill_falsification,
        paper_fill_label_count=0,
    ) == ["passive_liquidity_provision_blocked_proxy_only_no_real_fill_labels"]


def test_sports_evidence_cycle_safety_failure_next_action(tmp_path: Path) -> None:
    """When status starts with sports_evidence_cycle_failed, next_action must reference safety failure."""
    module = load_module()
    # Create an unsafe universe artifact (research_only is False, execution_enabled is True)
    unsafe_universe = {
        "schema_version": 1,
        "status": "ready",
        "research_only": False,
        "execution_enabled": True,
        "market_execution": True,
        "account_or_order_paths": True,
        "database_writes": True,
        "summary": {},
        "safety": {
            "market_execution": True,
            "account_or_order_paths": True,
            "database_writes": False,
        },
    }
    files = {
        "universe": write_json(tmp_path / "universe.json", unsafe_universe),
        "sports_obs": write_json(tmp_path / "sports_obs.json", safe_artifact()),
        "sports_model": write_json(tmp_path / "sports_model.json", safe_artifact()),
        "sports_replay": write_json(tmp_path / "sports_replay.json", safe_artifact()),
        "sports_ccd": write_json(tmp_path / "sports_ccd.json", safe_artifact()),
        "sports_cluster": write_json(tmp_path / "sports_cluster.json", safe_artifact()),
        "atp_obs": write_json(tmp_path / "atp_obs.json", safe_artifact()),
        "atp_evidence": write_json(tmp_path / "atp_evidence.json", safe_artifact()),
        "wc_obs": write_json(tmp_path / "wc_obs.json", safe_artifact()),
        "wc_model": write_json(tmp_path / "wc_model.json", safe_artifact()),
        "wc_outcome_independence": write_json(
            tmp_path / "wc_outcome_independence.json", safe_artifact()
        ),
        "stack": write_json(
            tmp_path / "stack.json",
            {
                **safe_artifact(candidate_count=0),
                "paper_decision_blocker_rows": [],
            },
        ),
        "consensus": write_json(tmp_path / "consensus.json", safe_artifact()),
        "consensus_observation": write_json(
            tmp_path / "consensus_observation.json", safe_artifact()
        ),
        "consensus_falsification": write_json(
            tmp_path / "consensus_falsification.json", safe_artifact()
        ),
        "consensus_provider_audit": write_json(
            tmp_path / "consensus_provider_audit.json", safe_artifact()
        ),
        "soccer_asian_provider": write_json(
            tmp_path / "soccer_asian_provider.json", safe_artifact()
        ),
        "micro": write_json(tmp_path / "micro.json", safe_artifact()),
        "flow": write_json(tmp_path / "flow.json", safe_artifact()),
        "flow_replay": write_json(tmp_path / "flow_replay.json", safe_artifact()),
        "flow_terms": write_json(tmp_path / "flow_terms.json", safe_artifact()),
        "passive": write_json(tmp_path / "passive.json", safe_artifact()),
        "passive_paper_fill": write_json(tmp_path / "passive_paper_fill.json", safe_artifact()),
        "passive_paper_fill_falsification": write_json(
            tmp_path / "passive_paper_fill_falsification.json",
            safe_artifact(),
        ),
        "passive_fill_clock_diagnostic": write_json(
            tmp_path / "passive_fill_clock_diagnostic.json",
            safe_artifact(),
        ),
        "event_velocity": write_json(tmp_path / "event_velocity.json", safe_artifact()),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(candidate_count=0)),
        "paper_settlement": write_json(
            tmp_path / "paper_settlement.json", safe_artifact(candidate_count=0)
        ),
        "live": write_json(tmp_path / "live.json", live_artifact()),
        "retirement": write_json(tmp_path / "retirement.json", safe_artifact()),
    }

    report = module.build_sports_evidence_cycle_report(
        universe_path=files["universe"],
        sports_observation_path=files["sports_obs"],
        sports_model_path=files["sports_model"],
        sports_replay_path=files["sports_replay"],
        sports_ccd_path=files["sports_ccd"],
        sports_cluster_path=files["sports_cluster"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        world_cup_outcome_independence_path=files["wc_outcome_independence"],
        stack_path=files["stack"],
        consensus_path=files["consensus"],
        consensus_observation_path=files["consensus_observation"],
        consensus_falsification_path=files["consensus_falsification"],
        consensus_provider_audit_path=files["consensus_provider_audit"],
        soccer_asian_provider_path=files["soccer_asian_provider"],
        microstructure_path=files["micro"],
        flow_path=files["flow"],
        flow_replay_path=files["flow_replay"],
        flow_terms_path=files["flow_terms"],
        passive_path=files["passive"],
        passive_paper_fill_path=files["passive_paper_fill"],
        passive_paper_fill_falsification_path=files["passive_paper_fill_falsification"],
        passive_fill_clock_diagnostic_path=files["passive_fill_clock_diagnostic"],
        event_velocity_path=files["event_velocity"],
        paper_path=files["paper"],
        paper_settlement_path=files["paper_settlement"],
        live_path=files["live"],
        retirement_path=files["retirement"],
        generated_utc="2026-07-04T01:00:00Z",
    )

    assert report["status"].startswith("sports_evidence_cycle_failed")
    action = report["next_action"]
    assert action["name"] == "kalshi_artifact_safety_audit"
    assert "safety" in action["why"].lower() or "unsafe" in action["why"].lower()
    assert (
        "safety" in action["stop_condition"].lower() or "unsafe" in action["stop_condition"].lower()
    )


def test_sports_evidence_cycle_makefile_target_exists() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-evidence-cycle" in text
    assert "scripts/kalshi_sports_evidence_cycle_report.py" in text
    assert "kalshi-sports-consensus-preflight" in text
    assert "kalshi-sports-consensus-observation-loop" in text
    assert "kalshi-sports-consensus-soccer-asian-provider-diagnostic" in text
    assert "kalshi-world-cup-outcome-independence-diagnostic" in text
    assert "kalshi-sports-event-velocity-eta" in text
    assert "kalshi-passive-liquidity-paper-fill-loop" in text
    assert "kalshi-passive-liquidity-fill-clock-diagnostic" in text
    assert "kalshi-paper-settlement-reconcile" in text
