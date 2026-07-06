from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "codex_macro_router.py"


def load_router_module():
    spec = importlib.util.spec_from_file_location("codex_macro_router", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_active_universe_contains_five_macro_repos() -> None:
    router = load_router_module()

    configs = router.repo_configs()

    assert set(configs) == {
        "predmarket-alpha",
        "mlb-platform",
        "atp-oracle",
        "nba-analytics-platform",
        "nfl_quant_glm51_greenfield",
    }


def test_status_schema_file_loads_as_json() -> None:
    schema_path = (
        Path(__file__).resolve().parents[1] / "docs" / "codex" / "macro" / "status.schema.json"
    )

    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema["title"] == "MacroRepoStatusV1"
    assert "repo_id" in schema["required"]


def test_collect_status_shape_for_each_active_repo() -> None:
    router = load_router_module()

    for repo_id in router.repo_configs():
        status = router.collect_status(repo_id)
        json.dumps(status)

        assert status["schema_version"] == 1
        assert status["repo_id"] == repo_id
        assert status["mode"]["research_only"] is True
        assert status["mode"]["execution_enabled"] is False
        assert status["mode"]["live_calls_allowed"] is False
        assert isinstance(status["evidence"]["latest_artifacts"], list)
        assert isinstance(status["evidence"]["hashes"], dict)
        assert set(status["evidence"]["gate_counts"]) == {"pass", "warn", "blocked", "fail"}
        assert status["scheduling"]["recommended_next_tranche"]
        assert status["scheduling"]["stop_condition"]
        assert all(
            gate["status"] in {"pass", "warn", "blocked", "fail"} for gate in status["gates"]
        )


def test_decision_recommends_exactly_one_repo() -> None:
    router = load_router_module()
    statuses = router.collect_all_statuses()

    decision = router.decide(statuses)

    repo_ids = {status["repo_id"] for status in statuses}
    assert decision["recommended_repo_id"] in repo_ids
    assert len(decision["ranked_repos"]) == len(repo_ids)
    assert decision["recommended_next_tranche"]
    assert decision["stop_condition"]
    priorities = [repo["priority"] for repo in decision["ranked_repos"]]
    assert priorities == sorted(priorities, reverse=True)


def test_predmarket_missing_reference_is_a_blocked_macro_gate() -> None:
    router = load_router_module()

    status = router.collect_status("predmarket-alpha")

    if (
        status["evidence"]["status"]
        != "kalshi_type2_reference_preflight_blocked_missing_sportsbook_reference"
    ):
        return
    gates = {gate["name"]: gate for gate in status["gates"]}
    assert gates["mapped_sportsbook_reference_available"]["status"] == "blocked"
    assert status["evidence"]["blocker_count"] >= 1
    assert status["evidence"]["gate_counts"]["blocked"] >= 1


def test_predmarket_missing_reference_state_is_parked_by_scheduler() -> None:
    router = load_router_module()

    status = router.collect_status("predmarket-alpha")

    if (
        status["evidence"]["status"]
        != "kalshi_type2_reference_preflight_blocked_missing_sportsbook_reference"
    ):
        return
    assert status["scheduling"]["priority"] <= 0


def test_predmarket_watch_only_candidate_disposition_is_parked_by_scheduler() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "kalshi_type2_candidate_disposition_watch_only"},
        }
    )

    assert status["scheduling"]["priority"] <= 0


def test_predmarket_kalshi_ev_contract_mapping_work_order_is_command_center_status() -> None:
    router = load_router_module()

    status = router.collect_status("predmarket-alpha")

    if status["evidence"]["status"] != "kalshi_ev_contract_mapping_work_order_ready":
        return
    gates = {gate["name"]: gate for gate in status["gates"]}
    metrics = status["evidence"]["metrics"]
    assert gates["kalshi_ev_ledger_ready"]["status"] == "pass"
    assert gates["kalshi_ev_overlay_preflight_ready"]["status"] == "pass"
    assert gates["kalshi_ev_calibration_work_order_ready"]["status"] == "pass"
    assert gates["kalshi_ev_contract_mapping_work_order_ready"]["status"] == "pass"
    assert gates["kalshi_ev_usable_rows_present"]["status"] == "blocked"
    assert metrics["kalshi_ev_ledger_summary"]["row_count"] >= 1
    assert metrics["kalshi_ev_calibration_work_order_summary"]["selected_row_count"] >= 1
    assert (
        metrics["kalshi_ev_contract_mapping_work_order_summary"]["selected_contract_side_count"]
        >= 1
    )
    assert status["scheduling"]["priority"] > 0
    assert "contract-mapping work-order row" in status["scheduling"]["recommended_next_tranche"]


def test_predmarket_kalshi_ev_work_order_scheduler_is_active() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "kalshi_ev_calibration_work_order_ready"},
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert "validated calibrated probabilities" in status["scheduling"]["recommended_next_tranche"]
    assert "inventing model probabilities" in status["scheduling"]["stop_condition"]


def test_predmarket_kalshi_ev_contract_mapping_scheduler_is_active() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "kalshi_ev_contract_mapping_work_order_ready"},
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert "exact Kalshi ticker" in status["scheduling"]["recommended_next_tranche"]
    assert "guessing a ticker" in status["scheduling"]["stop_condition"]


def test_predmarket_kalshi_ev_queue_robustness_scheduler_is_active() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "kalshi_ev_queue_robustness_repeat_positive_cost_caveated"},
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert "queue robustness artifact" in status["scheduling"]["recommended_next_tranche"]
    assert "all-in ticket-cost confirmation" in status["scheduling"]["recommended_next_tranche"]
    assert "cost-caveated repeat-positive rows" in status["scheduling"]["stop_condition"]


def test_predmarket_kalshi_universe_scan_scheduler_is_active() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "universe_scan_ready_with_model_routes"},
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert "Kalshi universe command center" in status["scheduling"]["recommended_next_tranche"]
    assert "authenticated/account/order endpoints" in status["scheduling"]["stop_condition"]


def test_predmarket_signal_factory_scheduler_routes_to_falsification() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "signal_factory_foundation_ready_falsification_missing"},
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert "HypothesisCandidate registry" in status["scheduling"]["recommended_next_tranche"]
    assert "Stop before adding or enabling sizing" in status["scheduling"]["stop_condition"]


def test_predmarket_hypothesis_registry_scheduler_routes_to_labeled_oos_backtest() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {
                "status": "signal_factory_hypothesis_registry_ready_falsification_blocked_missing_labeled_oos_evidence"
            },
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert (
        "labeled out-of-sample replay/backtest harness"
        in status["scheduling"]["recommended_next_tranche"]
    )
    assert "OOS cost-aware FDR evidence" in status["scheduling"]["stop_condition"]


def test_predmarket_oos_harness_routes_to_label_packet_builder() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {
                "status": "signal_factory_oos_backtest_harness_ready_labeled_observations_missing"
            },
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert "safe labeled-observation packets" in status["scheduling"]["recommended_next_tranche"]
    assert "unlabeled, time-unsafe" in status["scheduling"]["stop_condition"]


def test_predmarket_pending_observations_routes_to_probability_breadth() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "signal_factory_oos_pending_observations_waiting_settlement"},
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert (
        "expand calibrated-probability coverage" in status["scheduling"]["recommended_next_tranche"]
    )
    assert "pending unresolved observations" in status["scheduling"]["stop_condition"]


def test_predmarket_probability_breadth_scout_routes_to_crypto_feature_packets() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {
                "status": "signal_factory_probability_breadth_scout_ready_crypto_proxy_route"
            },
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert "crypto proxy feature" in status["scheduling"]["recommended_next_tranche"]
    assert "CF Benchmarks RTI" in status["scheduling"]["recommended_next_tranche"]
    assert "proxy prices as official settlement labels" in status["scheduling"]["stop_condition"]


def test_predmarket_crypto_proxy_feature_packet_routes_to_observation_loop() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "signal_factory_crypto_proxy_feature_packet_ready"},
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert (
        "repeated crypto proxy observation loop" in status["scheduling"]["recommended_next_tranche"]
    )
    assert "settled Kalshi outcomes" in status["scheduling"]["recommended_next_tranche"]
    assert "proxy states as official settlement labels" in status["scheduling"]["stop_condition"]


def test_predmarket_crypto_proxy_observations_waiting_routes_to_accumulation() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "signal_factory_crypto_proxy_observations_waiting_settlement"},
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert (
        "continue the crypto proxy observation loop"
        in status["scheduling"]["recommended_next_tranche"]
    )
    assert "proxy states as labels" in status["scheduling"]["stop_condition"]


def test_predmarket_crypto_proxy_labels_ready_routes_to_feature_model_falsification() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "signal_factory_crypto_proxy_labels_ready"},
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert (
        "train and falsify the first crypto proxy feature model"
        in status["scheduling"]["recommended_next_tranche"]
    )
    assert "FDR-controlled OOS survival" in status["scheduling"]["stop_condition"]


def test_predmarket_crypto_proxy_model_insufficient_labels_routes_to_accumulation() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "signal_factory_crypto_proxy_feature_model_insufficient_labels"},
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert (
        "continue the crypto proxy observation loop"
        in status["scheduling"]["recommended_next_tranche"]
    )
    assert "duplicate contract labels" in status["scheduling"]["stop_condition"]


def test_predmarket_crypto_proxy_research_candidate_routes_to_replay() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "signal_factory_crypto_proxy_feature_model_research_candidates"},
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert (
        "replay crypto proxy research candidates"
        in status["scheduling"]["recommended_next_tranche"]
    )
    assert "positive replay rows as deployable" in status["scheduling"]["stop_condition"]


def test_predmarket_crypto_proxy_replay_blocked_routes_to_capacity_correlation_decay() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {
                "status": "signal_factory_crypto_proxy_replay_blocked_predeployment_gates"
            },
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert "capacity-depth" in status["scheduling"]["recommended_next_tranche"]
    assert "correlation-cluster" in status["scheduling"]["recommended_next_tranche"]
    assert "replay rows as live edges" in status["scheduling"]["stop_condition"]


def test_predmarket_crypto_proxy_ccd_correlation_block_routes_to_cluster_control() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "signal_factory_crypto_proxy_correlation_concentration_blocked"},
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert (
        "correlation-cluster exposure controls" in status["scheduling"]["recommended_next_tranche"]
    )
    assert "cluster exposure limits" in status["scheduling"]["stop_condition"]


def test_predmarket_crypto_proxy_cluster_breadth_block_routes_to_breadth_accumulation() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "signal_factory_crypto_proxy_cluster_breadth_blocked"},
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert (
        "diversified current crypto proxy candidates"
        in status["scheduling"]["recommended_next_tranche"]
    )
    assert "reducing cluster breadth requirements" in status["scheduling"]["stop_condition"]


def test_missing_reference_route_moves_off_predmarket_when_other_work_exists() -> None:
    router = load_router_module()
    statuses = router.collect_all_statuses()
    decision = router.decide(statuses)
    predmarket_status = next(
        status for status in statuses if status["repo_id"] == "predmarket-alpha"
    )

    if (
        predmarket_status["evidence"]["status"]
        != "kalshi_type2_reference_preflight_blocked_missing_sportsbook_reference"
    ):
        return
    if decision.get("all_lanes_parked"):
        assert decision["recommended_repo_id"] == "predmarket-alpha"
        return
    assert decision["recommended_repo_id"] != "predmarket-alpha"


def test_atp_g1g2_diagnostic_state_is_parked_by_scheduler() -> None:
    router = load_router_module()

    status = router.collect_status("atp-oracle")

    if (
        status["evidence"]["status"]
        != "tennis_type2_g1g2_diagnostic_ready_blocked_fresh_validation_external_evidence"
    ):
        return
    gates = {gate["name"]: gate for gate in status["gates"]}
    assert gates["type2_g1g2_diagnostic_ready"]["status"] == "pass"
    assert (
        status["evidence"]["metrics"]["type2_g1g2_diagnostic_status"]
        == "blocked_g1g2_model_quality_evidence"
    )
    assert status["scheduling"]["priority"] <= 0


def test_completed_atp_diagnostic_route_moves_off_atp() -> None:
    router = load_router_module()
    statuses = router.collect_all_statuses()
    decision = router.decide(statuses)
    atp_status = next(status for status in statuses if status["repo_id"] == "atp-oracle")

    if (
        atp_status["evidence"]["status"]
        != "tennis_type2_g1g2_diagnostic_ready_blocked_fresh_validation_external_evidence"
    ):
        return
    if decision.get("all_lanes_parked"):
        assert decision["recommended_repo_id"] == "predmarket-alpha"
        return
    assert decision["recommended_repo_id"] != "atp-oracle"


def test_mlb_missing_pregame_drop_is_a_blocked_macro_gate() -> None:
    router = load_router_module()

    status = router.collect_status("mlb-platform")

    if status["evidence"]["status"] != "primary_type2_pregame_intake_blocked_missing_operator_drop":
        return
    gates = {gate["name"]: gate for gate in status["gates"]}
    assert gates["pregame_operator_drop_available"]["status"] == "blocked"
    assert status["evidence"]["blocker_count"] >= 1
    assert status["evidence"]["gate_counts"]["blocked"] >= 1


def test_mlb_missing_pregame_drop_state_is_parked_by_scheduler() -> None:
    router = load_router_module()

    status = router.collect_status("mlb-platform")

    if status["evidence"]["status"] != "primary_type2_pregame_intake_blocked_missing_operator_drop":
        return
    assert status["scheduling"]["priority"] <= 0


def test_missing_pregame_drop_route_moves_off_mlb() -> None:
    router = load_router_module()
    statuses = router.collect_all_statuses()
    decision = router.decide(statuses)
    mlb_status = next(status for status in statuses if status["repo_id"] == "mlb-platform")

    if (
        mlb_status["evidence"]["status"]
        != "primary_type2_pregame_intake_blocked_missing_operator_drop"
    ):
        return
    if decision.get("all_lanes_parked"):
        assert decision["recommended_repo_id"] == "predmarket-alpha"
        return
    assert decision["recommended_repo_id"] != "mlb-platform"


def test_mlb_review_adjudication_ready_gate_is_reported() -> None:
    router = load_router_module()

    status = router.collect_status("mlb-platform")

    if status["evidence"]["status"] != "primary_type2_review_adjudication_ready":
        return
    gates = {gate["name"]: gate for gate in status["gates"]}
    assert gates["review_adjudication_ready"]["status"] == "pass"
    review = status["evidence"]["metrics"]["review_adjudication"]
    assert review["ready"] is True
    assert review["summary"]["review_ready_cluster_count"] >= 1


def test_mlb_repeatability_observed_gate_is_reported_and_parked() -> None:
    router = load_router_module()

    status = router.collect_status("mlb-platform")

    if status["evidence"]["status"] != "primary_type2_repeatability_observed":
        return
    gates = {gate["name"]: gate for gate in status["gates"]}
    ledger = status["evidence"]["metrics"]["repeatability_ledger"]
    assert gates["repeatability_ledger_present"]["status"] == "pass"
    assert ledger["status"] == "repeatability_observed_two_clean_packets"
    assert ledger["summary"]["clean_packet_count"] >= 2
    assert status["scheduling"]["priority"] <= 0


def test_mlb_repeatability_ready_routes_to_research_review_synthesis() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "mlb-platform",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "primary_type2_repeatability_ready_for_research_review"},
        }
    )

    assert "research review" in status["scheduling"]["recommended_next_tranche"]
    assert "another provider/API capture" in status["scheduling"]["stop_condition"]
    assert "repeatability ledger" not in status["scheduling"]["recommended_next_tranche"]
    assert status["scheduling"]["priority"] > 0


def test_mlb_research_review_same_slate_caveat_is_parked() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "mlb-platform",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {
                "status": "primary_type2_repeatability_research_review_ready_same_slate_caveat"
            },
        }
    )

    assert status["scheduling"]["priority"] <= 0
    assert "cross-slate" in status["scheduling"]["recommended_next_tranche"]
    assert "new calendar-slate" in status["scheduling"]["stop_condition"]


def test_mlb_repeatability_blocked_no_clean_packets_is_parked() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "mlb-platform",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "primary_type2_repeatability_blocked_no_clean_packets"},
        }
    )

    assert status["scheduling"]["priority"] <= 0
    assert "zero clean adjudicated packets" in status["scheduling"]["recommended_next_tranche"]
    assert "superseded run-line pattern" in status["scheduling"]["stop_condition"]


def test_mlb_repeatability_no_signal_clean_packets_is_parked() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "mlb-platform",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "primary_type2_repeatability_no_signal_clean_packets"},
        }
    )

    assert status["scheduling"]["priority"] <= 0
    assert "zero review-ready rows" in status["scheduling"]["recommended_next_tranche"]
    assert "threshold-policy directive" in status["scheduling"]["stop_condition"]


def test_mlb_threshold_policy_hold_current_is_parked() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "mlb-platform",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "primary_type2_threshold_policy_hold_current"},
        }
    )

    assert status["scheduling"]["priority"] <= 0
    assert "hold the current threshold" in status["scheduling"]["recommended_next_tranche"]
    assert "new clean slate" in status["scheduling"]["stop_condition"]


def test_mlb_threshold_policy_review_candidate_routes_to_manual_review() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "mlb-platform",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "primary_type2_threshold_policy_review_candidate"},
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert "threshold-policy candidate" in status["scheduling"]["recommended_next_tranche"]
    assert "before changing thresholds" in status["scheduling"]["stop_condition"]


def test_mlb_settled_validation_no_policy_change_is_parked() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "mlb-platform",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "primary_type2_settled_validation_no_policy_change_same_slate"},
        }
    )

    assert status["scheduling"]["priority"] <= 0
    assert "does not support a threshold change" in status["scheduling"]["recommended_next_tranche"]
    assert "cross-slate settled validation" in status["scheduling"]["stop_condition"]


def test_mlb_settled_validation_candidate_routes_to_manual_review() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "mlb-platform",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "primary_type2_settled_validation_review_candidate"},
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert (
        "settled-outcome validation candidate" in status["scheduling"]["recommended_next_tranche"]
    )
    assert "before changing thresholds" in status["scheduling"]["stop_condition"]


def test_mlb_closing_proxy_same_slate_support_is_parked() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "mlb-platform",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "primary_type2_closing_proxy_same_slate_support_insufficient"},
        }
    )

    assert status["scheduling"]["priority"] <= 0
    assert (
        "same-slate later snapshots moved favorably"
        in status["scheduling"]["recommended_next_tranche"]
    )
    assert "true closing-line validation" in status["scheduling"]["stop_condition"]


def test_mlb_closing_proxy_candidate_routes_to_manual_review() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "mlb-platform",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": "primary_type2_closing_proxy_review_candidate"},
        }
    )

    assert status["scheduling"]["priority"] > 0
    assert "closing-proxy candidate" in status["scheduling"]["recommended_next_tranche"]
    assert "before changing thresholds" in status["scheduling"]["stop_condition"]


def test_mlb_betexplorer_moneyline_no_policy_change_is_parked() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "mlb-platform",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {
                "status": "primary_type2_betexplorer_moneyline_closing_comparison_no_policy_change"
            },
        }
    )

    assert status["scheduling"]["priority"] <= 0
    assert (
        "public BetExplorer moneyline comparison exists"
        in status["scheduling"]["recommended_next_tranche"]
    )
    assert "full closing-line validation" in status["scheduling"]["stop_condition"]


def test_mlb_betexplorer_market_no_policy_change_is_parked() -> None:
    router = load_router_module()

    status = router.apply_scheduling(
        {
            "repo_id": "mlb-platform",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {
                "status": "primary_type2_betexplorer_market_closing_comparison_no_policy_change"
            },
        }
    )

    assert status["scheduling"]["priority"] <= 0
    assert (
        "public BetExplorer multi-market comparison"
        in status["scheduling"]["recommended_next_tranche"]
    )
    assert "full closing-line validation" in status["scheduling"]["stop_condition"]


def test_nfl_fresh_governance_state_is_parked_by_scheduler() -> None:
    router = load_router_module()

    status = router.collect_status("nfl_quant_glm51_greenfield")

    if (
        status["evidence"]["status"]
        != "governance_macro_export_ready_fresh_snapshots_research_only"
    ):
        return
    assert status["scheduling"]["priority"] <= 0


def test_nfl_line_readiness_context_state_is_active_by_scheduler() -> None:
    router = load_router_module()

    for evidence_status in [
        "line_readiness_profiled_slate_forward_context_partial_research_only",
        "line_readiness_profiled_slate_forward_context_manual_drop_blocked_research_only",
        "line_readiness_profiled_slate_forward_context_manual_drop_ready_research_only",
    ]:
        status = {
            "repo_id": "nfl_quant_glm51_greenfield",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": evidence_status},
        }

        scheduled = router.apply_scheduling(status)

        assert scheduled["scheduling"]["priority"] > 0
        assert "Advance NFL line-readiness" in scheduled["scheduling"]["recommended_next_tranche"]
        assert "readiness gates" in scheduled["scheduling"]["stop_condition"]


def test_nfl_forward_context_not_yet_due_state_is_parked_by_scheduler() -> None:
    router = load_router_module()

    status = {
        "repo_id": "nfl_quant_glm51_greenfield",
        "git": {
            "dirty_counts": {"total": 0},
            "risk_flags": {
                "staged_changes": False,
                "deleted_paths": False,
                "ide_or_temp_paths": False,
            },
        },
        "evidence": {
            "status": "line_readiness_profiled_slate_forward_context_not_yet_due_research_only"
        },
    }

    scheduled = router.apply_scheduling(status)

    assert scheduled["scheduling"]["priority"] <= 0
    assert (
        "Park NFL forward-context collection" in scheduled["scheduling"]["recommended_next_tranche"]
    )
    assert (
        "forward-context availability artifact reports due_now"
        in scheduled["scheduling"]["stop_condition"]
    )


def test_nfl_manual_drop_gate_is_reported_when_packet_exists() -> None:
    router = load_router_module()

    status = router.collect_status("nfl_quant_glm51_greenfield")

    gates = {gate["name"]: gate for gate in status["gates"]}
    if "forward_context_manual_drop_readiness" not in gates:
        return
    manual_drop = status["evidence"]["metrics"]["forward_context_manual_drop"]
    assert gates["forward_context_manual_drop_readiness"]["status"] in {"pass", "warn", "blocked"}
    if manual_drop.get("missing") is True:
        assert status["evidence"]["metrics"]["forward_context_manual_drop_status"] is None
        return
    assert manual_drop["json_type"] == "object"
    assert status["evidence"]["metrics"]["forward_context_manual_drop_status"]


def test_nfl_market_snapshot_ledger_gate_is_reported_when_packet_exists() -> None:
    router = load_router_module()

    status = router.collect_status("nfl_quant_glm51_greenfield")

    gates = {gate["name"]: gate for gate in status["gates"]}
    if "market_snapshot_ledger_ready" not in gates:
        return
    metrics = status["evidence"]["metrics"]
    assert gates["market_snapshot_ledger_ready"]["status"] in {"pass", "warn", "blocked"}
    if metrics["market_snapshot_ledger_status"] is not None:
        assert metrics["market_snapshot_ledger"]["json_type"] == "object"


def test_nfl_historical_line_backtest_gate_is_reported_when_packet_exists() -> None:
    router = load_router_module()

    status = router.collect_status("nfl_quant_glm51_greenfield")

    gates = {gate["name"]: gate for gate in status["gates"]}
    if "historical_line_backtest_ready" not in gates:
        return
    metrics = status["evidence"]["metrics"]
    assert gates["historical_line_backtest_ready"]["status"] in {"pass", "warn"}
    if metrics["historical_line_backtest_status"] is not None:
        assert metrics["historical_line_backtest"]["json_type"] == "object"
        assert metrics["historical_line_backtest_row_count"] is not None


def test_nba_market_parity_state_is_parked_by_scheduler() -> None:
    router = load_router_module()

    status = router.collect_status("nba-analytics-platform")

    if (
        status["evidence"]["status"]
        != "macro_partial_truth_shrinkage_clipped_residual_market_parity"
    ):
        return
    assert status["scheduling"]["priority"] <= 0


def test_all_parked_decision_routes_to_predmarket_command_center() -> None:
    router = load_router_module()
    statuses = [
        _status_for_decision(
            router, "mlb-platform", -4, "primary_type2_pregame_intake_blocked_missing_operator_drop"
        ),
        _status_for_decision(
            router,
            "nfl_quant_glm51_greenfield",
            -4,
            "governance_macro_export_ready_fresh_snapshots_research_only",
        ),
        _status_for_decision(
            router,
            "predmarket-alpha",
            -3,
            "kalshi_type2_reference_preflight_blocked_missing_sportsbook_reference",
        ),
    ]

    decision = router.decide(statuses)

    assert decision["all_lanes_parked"] is True
    assert decision["recommended_repo_id"] == "predmarket-alpha"
    assert len(decision["blocker_summary"]) == 3
    assert decision["recommended_next_tranche"] == router.PARKED_COMMAND_CENTER_TRANCHE


def _status_for_decision(router, repo_id: str, priority: int, evidence_status: str) -> dict:
    return {
        "repo_id": repo_id,
        "repo_path": str(router.repo_path(repo_id)),
        "evidence": {
            "status": evidence_status,
            "gate_counts": {"pass": 0, "warn": 0, "blocked": 1, "fail": 0},
        },
        "git": {"dirty_counts": {"total": 0}},
        "scheduling": {
            "priority": priority,
            "recommended_next_tranche": f"{repo_id} tranche",
            "stop_condition": f"{repo_id} stop",
        },
    }


# ---------------------------------------------------------------------------
# Family-aware sports router entries (VAL-ORCH-015..018, 025)
# ---------------------------------------------------------------------------

SPORTS_SIGNAL_STATUSES = [
    "signal_factory_sports_stack_sequencing_ready_current_depth_passed",
    "signal_factory_sports_stack_sequencing_ready_cap_i_lock_blocked",
    "signal_factory_sports_baseball_feature_packet_ready",
    "signal_factory_sports_baseball_observations_waiting_settlement",
    "signal_factory_sports_baseball_labels_ready",
    "signal_factory_probability_breadth_scout_ready_sports_baseball_route",
]

SPORTS_BLOCKED_STATUSES = [
    "signal_factory_sports_baseball_blocked_missing_feature_packet",
]


def _apply_scheduling_for(router, evidence_status: str) -> dict:
    return router.apply_scheduling(
        {
            "repo_id": "predmarket-alpha",
            "git": {
                "dirty_counts": {"total": 0},
                "risk_flags": {
                    "staged_changes": False,
                    "deleted_paths": False,
                    "ide_or_temp_paths": False,
                },
            },
            "evidence": {"status": evidence_status},
        }
    )


def test_sports_signal_factory_status_routes_to_positive_priority() -> None:
    """VAL-ORCH-015: sports statuses get priority >= 0, tier parity with crypto."""
    router = load_router_module()
    for sports_status in SPORTS_SIGNAL_STATUSES:
        status = _apply_scheduling_for(router, sports_status)
        assert status["scheduling"]["priority"] >= 0, f"{sports_status} priority < 0"
        # Tier parity: compare with a comparable crypto status.
        crypto_status = _apply_scheduling_for(
            router, "signal_factory_crypto_proxy_feature_packet_ready"
        )
        assert (
            status["scheduling"]["score_components"]["architecture_leverage"]
            == crypto_status["scheduling"]["score_components"]["architecture_leverage"]
        )


def test_sports_signal_factory_status_routes_to_sports_tranche() -> None:
    """VAL-ORCH-016: sports status -> sports tranche, not generic fallback."""
    router = load_router_module()
    for sports_status in SPORTS_SIGNAL_STATUSES:
        status = _apply_scheduling_for(router, sports_status)
        tranche = status["scheduling"]["recommended_next_tranche"]
        assert "sports" in tranche.lower() or "baseball" in tranche.lower(), (
            f"{sports_status} tranche does not mention sports: {tranche}"
        )
        assert tranche != router.KALSHI_SIGNAL_FACTORY_TRANCHE, (
            f"{sports_status} fell through to generic KALSHI_SIGNAL_FACTORY_TRANCHE"
        )
        stop = status["scheduling"]["stop_condition"]
        assert "execution" in stop.lower() or "account" in stop.lower() or "order" in stop.lower()


def test_every_sports_status_has_parked_unlock_entry() -> None:
    """VAL-ORCH-017: every signal_factory_sports_* status has a PARKED_UNLOCKS entry."""
    router = load_router_module()
    all_sports_statuses = SPORTS_SIGNAL_STATUSES + SPORTS_BLOCKED_STATUSES
    for sports_status in all_sports_statuses:
        assert sports_status in router.PARKED_UNLOCKS, (
            f"{sports_status} missing from PARKED_UNLOCKS"
        )
        unlock = router.PARKED_UNLOCKS[sports_status]
        assert unlock, f"{sports_status} has empty PARKED_UNLOCKS value"
        assert "sport" in unlock.lower() or "baseball" in unlock.lower(), (
            f"{sports_status} unlock does not mention sports: {unlock}"
        )


def test_sports_parked_state_routes_to_command_center() -> None:
    """VAL-ORCH-018: sports-led predmarket parked -> command center + blocker summary."""
    router = load_router_module()
    statuses = [
        _status_for_decision(
            router, "mlb-platform", -4, "primary_type2_pregame_intake_blocked_missing_operator_drop"
        ),
        _status_for_decision(
            router,
            "nfl_quant_glm51_greenfield",
            -4,
            "governance_macro_export_ready_fresh_snapshots_research_only",
        ),
        _status_for_decision(
            router,
            "predmarket-alpha",
            -3,
            "signal_factory_sports_baseball_blocked_missing_feature_packet",
        ),
    ]

    decision = router.decide(statuses)

    assert decision["all_lanes_parked"] is True
    assert decision["recommended_repo_id"] == "predmarket-alpha"
    assert decision["recommended_next_tranche"] == router.PARKED_COMMAND_CENTER_TRANCHE
    assert len(decision["blocker_summary"]) >= 1
    blocker_statuses = [item.get("status") for item in decision["blocker_summary"]]
    assert "signal_factory_sports_baseball_blocked_missing_feature_packet" in blocker_statuses


def test_crypto_router_priority_unchanged_after_sports_additions() -> None:
    """VAL-ORCH-025: crypto statuses keep the same priority and tranche."""
    router = load_router_module()
    crypto_statuses = [
        "signal_factory_crypto_proxy_feature_packet_ready",
        "signal_factory_foundation_ready",
        "signal_factory_probability_breadth_scout_ready_crypto_proxy_route",
        "signal_factory_crypto_proxy_labels_ready",
    ]
    for crypto_status in crypto_statuses:
        status = _apply_scheduling_for(router, crypto_status)
        assert status["scheduling"]["priority"] > 0
        assert (
            "Kalshi signal-factory command center"
            in status["scheduling"]["recommended_next_tranche"]
        )


def test_sports_blocked_status_has_lower_priority_tier() -> None:
    """Sports blocked statuses get lower priority like crypto blocked."""
    router = load_router_module()
    for blocked_status in SPORTS_BLOCKED_STATUSES:
        status = _apply_scheduling_for(router, blocked_status)
        # Should still be recognized (not base fallback) but lower priority.
        components = status["scheduling"]["score_components"]
        assert components["architecture_leverage"] == 5
