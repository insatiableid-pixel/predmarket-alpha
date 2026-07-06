import json

from scripts.codex_macro_unlock_scout import (
    build_unlock_scout,
    render_unlock_scout_markdown,
    write_unlock_scout,
)


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_unlock_scout_reports_local_inputs_and_blockers(tmp_path):
    repo = tmp_path / "predmarket"
    manual = tmp_path / "manual_drops"
    _write_json(
        repo / "docs/codex/macro/latest-decision.json",
        {
            "all_lanes_parked": True,
            "recommended_repo_id": "predmarket-alpha",
            "blocker_summary": [
                {
                    "repo_id": "nba-analytics-platform",
                    "status": "macro_partial_truth_shrinkage_clipped_residual_market_parity",
                    "priority": -11,
                    "gate_counts": {"blocked": 3},
                    "unlock": "Supply a new source-backed NBA signal or market dataset.",
                },
                {
                    "repo_id": "nfl_quant_glm51_greenfield",
                    "status": "governance_macro_export_ready_fresh_snapshots_research_only",
                    "priority": -4,
                    "gate_counts": {"blocked": 0},
                    "unlock": "No immediate NFL work.",
                },
            ],
        },
    )
    _write_json(
        repo
        / "docs/codex/artifacts/type2-reference-builder-latest/type2-reference-builder-latest.json",
        {"status": "reference_built", "summary": {"market_count": 4}, "research_only": True},
    )
    _write_json(
        repo
        / "docs/codex/artifacts/type2-candidate-disposition-latest/type2-candidate-disposition-latest.json",
        {
            "status": "candidate_disposition_all_passes_downgraded",
            "summary": {"kept_review_candidate": 0},
        },
    )
    _write_json(manual / "odds_api/baseball_mlb.json", [])

    report = build_unlock_scout(
        control_repo=repo,
        manual_drops=manual,
        mlb_repo=tmp_path / "mlb",
        as_of_utc="2026-06-28T00:00:00Z",
    )

    assert report["research_only"] is True
    assert report["safety"]["provider_api_calls"] is False
    assert report["local_inputs"]["odds_api_json_count"] == 1
    assert report["local_inputs"]["kalshi_json_count"] == 0
    predmarket = next(lane for lane in report["lanes"] if lane["repo_id"] == "predmarket-alpha")
    mlb = next(lane for lane in report["lanes"] if lane["repo_id"] == "mlb-platform")
    assert predmarket["blocked"] is True
    assert "Timing-safe mapped sportsbook reference" in predmarket["missing_input"]
    assert mlb["blocked"] is True
    assert "Kalshi pregame drops" in mlb["missing_input"]


def test_unlock_scout_reports_predmarket_watch_only_reference(tmp_path):
    repo = tmp_path / "predmarket"
    manual = tmp_path / "manual_drops"
    _write_json(repo / "docs/codex/macro/latest-decision.json", {"all_lanes_parked": True})
    _write_json(
        repo
        / "docs/codex/artifacts/type2-reference-builder-latest/type2-reference-builder-latest.json",
        {"status": "reference_built", "summary": {"market_count": 24}, "research_only": True},
    )
    _write_json(
        repo
        / "docs/codex/artifacts/type2-candidate-disposition-latest/type2-candidate-disposition-latest.json",
        {
            "status": "candidate_disposition_watch_only",
            "summary": {
                "kept_review_candidate": 0,
                "watch_only": 24,
                "downgraded_temporal_mismatch": 0,
            },
        },
    )

    report = build_unlock_scout(
        control_repo=repo,
        manual_drops=manual,
        mlb_repo=tmp_path / "mlb",
        as_of_utc="2026-06-29T00:00:00Z",
    )

    predmarket = next(lane for lane in report["lanes"] if lane["repo_id"] == "predmarket-alpha")
    assert predmarket["blocked"] is True
    assert predmarket["status"] == "candidate_disposition_watch_only"
    assert "Timing-safe mapped reference exists" in predmarket["missing_input"]
    assert "watch_only_candidates=24" in predmarket["what_exists"]


def test_unlock_scout_prefers_kalshi_ev_work_order_when_present(tmp_path):
    repo = tmp_path / "predmarket"
    manual = tmp_path / "manual_drops"
    _write_json(repo / "docs/codex/macro/latest-decision.json", {"all_lanes_parked": True})
    safety = {
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
    }
    _write_json(
        repo / "docs/codex/macro/latest-kalshi-contract-ev-ledger.json",
        {
            "status": "kalshi_ev_ledger_candidates_present_but_not_usable",
            "research_only": True,
            "execution_enabled": False,
            "safety": safety,
            "summary": {
                "row_count": 3,
                "usable_row_count": 0,
                "missing_calibrated_probability_row_count": 3,
            },
        },
    )
    _write_json(
        repo / "docs/codex/macro/latest-kalshi-ev-overlay-preflight.json",
        {
            "status": "overlay_preflight_blocked_missing_or_unjoined_inputs",
            "research_only": True,
            "execution_enabled": False,
            "safety": safety,
            "summary": {"exact_join_row_count": 0},
        },
    )
    _write_json(
        repo / "docs/codex/macro/latest-kalshi-ev-calibration-work-order.json",
        {
            "status": "calibration_work_order_ready",
            "research_only": True,
            "execution_enabled": False,
            "safety": safety,
            "summary": {"selected_row_count": 2},
        },
    )

    report = build_unlock_scout(
        control_repo=repo,
        manual_drops=manual,
        mlb_repo=tmp_path / "mlb",
        as_of_utc="2026-07-01T00:00:00Z",
    )

    predmarket = next(lane for lane in report["lanes"] if lane["repo_id"] == "predmarket-alpha")
    assert report["kalshi_ev"]["calibration_work_order_status"] == "calibration_work_order_ready"
    assert predmarket["status"] == "calibration_work_order_ready"
    assert predmarket["blocked"] is True
    assert "validated calibrated-probability overlay" in predmarket["missing_input"]
    assert "make kalshi-ev-calibration-work-order" in predmarket["next_local_command"]


def test_unlock_scout_prefers_contract_mapping_work_order_over_probability_queue(tmp_path):
    repo = tmp_path / "predmarket"
    manual = tmp_path / "manual_drops"
    _write_json(repo / "docs/codex/macro/latest-decision.json", {"all_lanes_parked": False})
    safety = {
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
    }
    _write_json(
        repo / "docs/codex/macro/latest-kalshi-contract-ev-ledger.json",
        {
            "status": "kalshi_ev_ledger_candidates_present_but_not_usable",
            "research_only": True,
            "execution_enabled": False,
            "safety": safety,
            "summary": {"row_count": 316, "usable_row_count": 0},
        },
    )
    _write_json(
        repo / "docs/codex/macro/latest-kalshi-ev-contract-mapping-work-order.json",
        {
            "status": "contract_mapping_work_order_ready",
            "research_only": True,
            "execution_enabled": False,
            "safety": safety,
            "summary": {"selected_contract_side_count": 32, "model_row_count": 16},
        },
    )
    _write_json(
        repo / "docs/codex/macro/latest-kalshi-ev-calibration-work-order.json",
        {
            "status": "calibration_work_order_ready_source_gated",
            "research_only": True,
            "execution_enabled": False,
            "safety": safety,
            "summary": {"selected_row_count": 25},
        },
    )

    report = build_unlock_scout(
        control_repo=repo,
        manual_drops=manual,
        mlb_repo=tmp_path / "mlb",
        as_of_utc="2026-07-01T00:00:00Z",
    )

    predmarket = next(lane for lane in report["lanes"] if lane["repo_id"] == "predmarket-alpha")
    assert (
        report["kalshi_ev"]["contract_mapping_work_order_status"]
        == "contract_mapping_work_order_ready"
    )
    assert predmarket["status"] == "contract_mapping_work_order_ready"
    assert "Exact Kalshi ticker" in predmarket["missing_input"]
    assert "make kalshi-ev-contract-mapping-work-order" in predmarket["next_local_command"]


def test_unlock_scout_writes_json_and_markdown(tmp_path):
    repo = tmp_path / "predmarket"
    manual = tmp_path / "manual_drops"
    _write_json(repo / "docs/codex/macro/latest-decision.json", {"all_lanes_parked": True})
    report = build_unlock_scout(
        control_repo=repo,
        manual_drops=manual,
        mlb_repo=tmp_path / "mlb",
        as_of_utc="2026-06-28T00:00:00Z",
    )

    json_path, md_path = write_unlock_scout(report, output_dir=repo / "docs/codex/macro")

    assert json_path.exists()
    assert md_path.exists()
    markdown = md_path.read_text(encoding="utf-8")
    assert "Macro Unlock Scout" in markdown
    assert "Provider/API calls: false" in markdown
    assert "does not authorize execution or account activity" in markdown
    forbidden = ["Kelly", "bankroll", "stake", "place a bet", "wager"]
    assert not any(term in markdown for term in forbidden)


def test_unlock_scout_marks_mlb_blocked_after_invalid_intake(tmp_path):
    repo = tmp_path / "predmarket"
    manual = tmp_path / "manual_drops"
    mlb = tmp_path / "mlb"
    _write_json(repo / "docs/codex/macro/latest-decision.json", {"all_lanes_parked": True})
    _write_json(manual / "odds_api/baseball_mlb_current.json", [])
    _write_json(manual / "kalshi/kalshi_mlb_game_series_latest.json", {"all_scored": []})
    _write_json(
        mlb / "docs/codex/artifacts/invalid-run/pregame-drop-intake-status.json",
        {
            "status": "blocked_invalid_operator_drop",
            "ready": False,
            "blockers": ["Local step failed: type2-audit returned 2."],
        },
    )

    report = build_unlock_scout(
        control_repo=repo,
        manual_drops=manual,
        mlb_repo=mlb,
        as_of_utc="2026-06-28T00:00:00Z",
    )

    mlb_lane = next(lane for lane in report["lanes"] if lane["repo_id"] == "mlb-platform")
    assert mlb_lane["blocked"] is True
    assert mlb_lane["status"] == "blocked_invalid_operator_drop"
    assert "current local pair failed intake" in mlb_lane["missing_input"]
    assert "latest_intake_blockers=1" in mlb_lane["what_exists"]


def test_unlock_scout_reports_mlb_repeatability_observed(tmp_path):
    repo = tmp_path / "predmarket"
    manual = tmp_path / "manual_drops"
    mlb = tmp_path / "mlb"
    _write_json(repo / "docs/codex/macro/latest-decision.json", {"all_lanes_parked": False})
    _write_json(manual / "odds_api/baseball_mlb_current.json", [])
    _write_json(manual / "kalshi/kalshi_mlb_game_series_latest.json", {"all_scored": []})
    _write_json(
        mlb / "docs/codex/artifacts/clean/pregame-drop-intake-status.json",
        {"status": "ready_pregame_pair", "ready": True, "blockers": []},
    )
    _write_json(
        mlb / "docs/codex/artifacts/clean/review-adjudication.json",
        {
            "status": "review_adjudication_ready",
            "ready_for_human_review": True,
            "summary": {"review_ready_cluster_count": 8, "review_ready_row_count": 58},
        },
    )
    _write_json(
        mlb
        / "docs/codex/artifacts/type2-repeatability-ledger-latest/type2-repeatability-ledger.json",
        {
            "status": "repeatability_observed_two_clean_packets",
            "review_only": True,
            "summary": {"clean_packet_count": 2, "repeated_descriptor_count": 2},
        },
    )

    report = build_unlock_scout(
        control_repo=repo,
        manual_drops=manual,
        mlb_repo=mlb,
        as_of_utc="2026-06-29T00:00:00Z",
    )

    mlb_lane = next(lane for lane in report["lanes"] if lane["repo_id"] == "mlb-platform")
    assert mlb_lane["blocked"] is True
    assert mlb_lane["status"] == "repeatability_observed_two_clean_packets"
    assert "Explicitly authorize another bounded clean current capture" in mlb_lane["missing_input"]
    assert "make type2-repeatability-ledger" in mlb_lane["next_local_command"]


def test_unlock_scout_reports_mlb_repeatability_ready_for_review(tmp_path):
    repo = tmp_path / "predmarket"
    manual = tmp_path / "manual_drops"
    mlb = tmp_path / "mlb"
    _write_json(repo / "docs/codex/macro/latest-decision.json", {"all_lanes_parked": False})
    _write_json(manual / "odds_api/baseball_mlb_current.json", [])
    _write_json(manual / "kalshi/kalshi_mlb_game_series_latest.json", {"all_scored": []})
    _write_json(
        mlb / "docs/codex/artifacts/clean/pregame-drop-intake-status.json",
        {"status": "ready_pregame_pair", "ready": True, "blockers": []},
    )
    _write_json(
        mlb / "docs/codex/artifacts/clean/review-adjudication.json",
        {
            "status": "review_adjudication_ready",
            "ready_for_human_review": True,
            "summary": {"review_ready_cluster_count": 10, "review_ready_row_count": 81},
        },
    )
    _write_json(
        mlb
        / "docs/codex/artifacts/type2-repeatability-ledger-latest/type2-repeatability-ledger.json",
        {
            "status": "repeatability_ready_for_research_review",
            "review_only": True,
            "summary": {"clean_packet_count": 3, "repeated_descriptor_count": 3},
        },
    )

    report = build_unlock_scout(
        control_repo=repo,
        manual_drops=manual,
        mlb_repo=mlb,
        as_of_utc="2026-06-29T00:00:00Z",
    )

    mlb_lane = next(lane for lane in report["lanes"] if lane["repo_id"] == "mlb-platform")
    assert mlb_lane["blocked"] is False
    assert mlb_lane["status"] == "repeatability_ready_for_research_review"
    assert "No missing local input" in mlb_lane["missing_input"]
    assert "make macro-status" in mlb_lane["next_local_command"]


def test_unlock_scout_reports_mlb_research_review_same_slate_caveat(tmp_path):
    repo = tmp_path / "predmarket"
    manual = tmp_path / "manual_drops"
    mlb = tmp_path / "mlb"
    _write_json(repo / "docs/codex/macro/latest-decision.json", {"all_lanes_parked": True})
    _write_json(manual / "odds_api/baseball_mlb_current.json", [])
    _write_json(manual / "kalshi/kalshi_mlb_game_series_latest.json", {"all_scored": []})
    _write_json(
        mlb / "docs/codex/artifacts/clean/pregame-drop-intake-status.json",
        {"status": "ready_pregame_pair", "ready": True, "blockers": []},
    )
    _write_json(
        mlb / "docs/codex/artifacts/clean/review-adjudication.json",
        {
            "status": "review_adjudication_ready",
            "ready_for_human_review": True,
            "summary": {"review_ready_cluster_count": 10, "review_ready_row_count": 81},
        },
    )
    _write_json(
        mlb
        / "docs/codex/artifacts/type2-repeatability-ledger-latest/type2-repeatability-ledger.json",
        {
            "status": "repeatability_ready_for_research_review",
            "review_only": True,
            "summary": {"clean_packet_count": 3, "repeated_descriptor_count": 3},
        },
    )
    _write_json(
        mlb
        / "docs/codex/artifacts/type2-repeatability-research-review-latest/type2-repeatability-research-review.json",
        {
            "status": "repeatability_research_review_ready",
            "review_only": True,
            "summary": {
                "stable_recurring_descriptor_count": 2,
                "same_slate_dates": ["2026-06-29"],
            },
        },
    )

    report = build_unlock_scout(
        control_repo=repo,
        manual_drops=manual,
        mlb_repo=mlb,
        as_of_utc="2026-06-29T00:00:00Z",
    )

    mlb_lane = next(lane for lane in report["lanes"] if lane["repo_id"] == "mlb-platform")
    assert mlb_lane["blocked"] is True
    assert mlb_lane["status"] == "repeatability_research_review_ready"
    assert "Cross-slate clean packet" in mlb_lane["missing_input"]
    assert "same-slate caveated" in mlb_lane["missing_input"]


def test_unlock_scout_reports_mlb_repeatability_blocked_no_clean_packets(tmp_path):
    repo = tmp_path / "predmarket"
    manual = tmp_path / "manual_drops"
    mlb = tmp_path / "mlb"
    _write_json(repo / "docs/codex/macro/latest-decision.json", {"all_lanes_parked": True})
    _write_json(manual / "odds_api/baseball_mlb_current.json", [])
    _write_json(manual / "kalshi/kalshi_mlb_game_series_latest.json", {"all_scored": []})
    _write_json(
        mlb / "docs/codex/artifacts/clean/pregame-drop-intake-status.json",
        {"status": "ready_pregame_pair", "ready": True, "blockers": []},
    )
    _write_json(
        mlb
        / "docs/codex/artifacts/type2-repeatability-ledger-latest/type2-repeatability-ledger.json",
        {
            "status": "repeatability_blocked_no_clean_packets",
            "review_only": True,
            "summary": {"clean_packet_count": 0, "repeated_descriptor_count": 0},
        },
    )
    _write_json(
        mlb
        / "docs/codex/artifacts/type2-repeatability-research-review-latest/type2-repeatability-research-review.json",
        {
            "status": "repeatability_research_review_blocked_threshold_not_met",
            "review_only": True,
            "summary": {
                "stable_recurring_descriptor_count": 0,
                "same_slate_dates": [],
            },
        },
    )

    report = build_unlock_scout(
        control_repo=repo,
        manual_drops=manual,
        mlb_repo=mlb,
        as_of_utc="2026-06-29T00:00:00Z",
    )

    mlb_lane = next(lane for lane in report["lanes"] if lane["repo_id"] == "mlb-platform")
    assert mlb_lane["blocked"] is True
    assert mlb_lane["status"] == "repeatability_research_review_blocked_threshold_not_met"
    assert "Corrected contract mapping invalidated" in mlb_lane["missing_input"]
    assert "make macro-status" in mlb_lane["next_local_command"]


def test_unlock_scout_reports_mlb_repeatability_no_signal_clean_packets(tmp_path):
    repo = tmp_path / "predmarket"
    manual = tmp_path / "manual_drops"
    mlb = tmp_path / "mlb"
    _write_json(repo / "docs/codex/macro/latest-decision.json", {"all_lanes_parked": True})
    _write_json(manual / "odds_api/baseball_mlb_current.json", [])
    _write_json(manual / "kalshi/kalshi_mlb_game_series_latest.json", {"all_scored": []})
    _write_json(
        mlb / "docs/codex/artifacts/clean/pregame-drop-intake-status.json",
        {"status": "ready_pregame_pair", "ready": True, "blockers": []},
    )
    _write_json(
        mlb
        / "docs/codex/artifacts/type2-repeatability-ledger-latest/type2-repeatability-ledger.json",
        {
            "status": "repeatability_no_signal_clean_packets",
            "review_only": True,
            "summary": {
                "clean_packet_count": 0,
                "clean_no_signal_packet_count": 4,
                "repeated_descriptor_count": 0,
            },
        },
    )
    _write_json(
        mlb
        / "docs/codex/artifacts/type2-repeatability-research-review-latest/type2-repeatability-research-review.json",
        {
            "status": "repeatability_research_review_blocked_threshold_not_met",
            "review_only": True,
            "summary": {
                "stable_recurring_descriptor_count": 0,
                "same_slate_dates": [],
            },
        },
    )

    report = build_unlock_scout(
        control_repo=repo,
        manual_drops=manual,
        mlb_repo=mlb,
        as_of_utc="2026-06-29T00:00:00Z",
    )

    mlb_lane = next(lane for lane in report["lanes"] if lane["repo_id"] == "mlb-platform")
    assert mlb_lane["blocked"] is True
    assert mlb_lane["status"] == "repeatability_research_review_blocked_threshold_not_met"
    assert "zero rows cleared the current review threshold" in mlb_lane["missing_input"]
    assert "clean_no_signal_packets=4" in mlb_lane["what_exists"]
    assert "make macro-status" in mlb_lane["next_local_command"]


def test_unlock_scout_reports_mlb_threshold_policy_hold_current(tmp_path):
    repo = tmp_path / "predmarket"
    manual = tmp_path / "manual_drops"
    mlb = tmp_path / "mlb"
    _write_json(repo / "docs/codex/macro/latest-decision.json", {"all_lanes_parked": True})
    _write_json(manual / "odds_api/baseball_mlb_current.json", [])
    _write_json(manual / "kalshi/kalshi_mlb_game_series_latest.json", {"all_scored": []})
    _write_json(
        mlb / "docs/codex/artifacts/clean/pregame-drop-intake-status.json",
        {"status": "ready_pregame_pair", "ready": True, "blockers": []},
    )
    _write_json(
        mlb
        / "docs/codex/artifacts/type2-repeatability-ledger-latest/type2-repeatability-ledger.json",
        {
            "status": "repeatability_no_signal_clean_packets",
            "review_only": True,
            "summary": {
                "clean_packet_count": 0,
                "clean_no_signal_packet_count": 4,
                "repeated_descriptor_count": 0,
            },
        },
    )
    _write_json(
        mlb
        / "docs/codex/artifacts/type2-threshold-policy-review-latest/type2-threshold-policy-review.json",
        {
            "status": "threshold_policy_hold_current",
            "review_only": True,
            "summary": {
                "current_threshold_count": 0,
                "max_abs_net_edge": 0.0277,
                "same_slate_date_count": 1,
                "best_lower_threshold_candidate": {"threshold": 0.02},
            },
        },
    )

    report = build_unlock_scout(
        control_repo=repo,
        manual_drops=manual,
        mlb_repo=mlb,
        as_of_utc="2026-06-30T00:00:00Z",
    )

    mlb_lane = next(lane for lane in report["lanes"] if lane["repo_id"] == "mlb-platform")
    assert mlb_lane["blocked"] is True
    assert mlb_lane["status"] == "threshold_policy_hold_current"
    assert "hold the current threshold" in mlb_lane["missing_input"]
    assert "same_slate_date_count=1" in mlb_lane["what_exists"]
    assert "best_lower_threshold=0.02" in mlb_lane["what_exists"]


def test_unlock_scout_reports_mlb_settled_validation_no_policy_change(tmp_path):
    repo = tmp_path / "predmarket"
    manual = tmp_path / "manual_drops"
    mlb = tmp_path / "mlb"
    _write_json(repo / "docs/codex/macro/latest-decision.json", {"all_lanes_parked": True})
    _write_json(manual / "odds_api/baseball_mlb_current.json", [])
    _write_json(manual / "kalshi/kalshi_mlb_game_series_latest.json", {"all_scored": []})
    _write_json(
        mlb
        / "docs/codex/artifacts/type2-settled-outcome-validation-latest/type2-settled-outcome-validation.json",
        {
            "status": "settled_validation_no_policy_change_same_slate",
            "review_only": True,
            "summary": {
                "valid_directional_row_count": 1239,
                "directional_correct_rate": 0.4503,
                "current_threshold_count": 0,
                "same_slate_date_count": 1,
            },
        },
    )

    report = build_unlock_scout(
        control_repo=repo,
        manual_drops=manual,
        mlb_repo=mlb,
        as_of_utc="2026-06-30T00:00:00Z",
    )

    mlb_lane = next(lane for lane in report["lanes"] if lane["repo_id"] == "mlb-platform")
    assert mlb_lane["blocked"] is True
    assert mlb_lane["status"] == "settled_validation_no_policy_change_same_slate"
    assert "does not support a threshold change" in mlb_lane["missing_input"]
    assert "directional_correct_rate=45.0%" in mlb_lane["what_exists"]
    assert "zero current-threshold rows" in mlb_lane["missing_input"]


def test_unlock_scout_reports_mlb_closing_proxy_insufficient(tmp_path):
    repo = tmp_path / "predmarket"
    manual = tmp_path / "manual_drops"
    mlb = tmp_path / "mlb"
    _write_json(repo / "docs/codex/macro/latest-decision.json", {"all_lanes_parked": True})
    _write_json(manual / "odds_api/baseball_mlb_current.json", [])
    _write_json(manual / "kalshi/kalshi_mlb_game_series_latest.json", {"all_scored": []})
    _write_json(
        mlb
        / "docs/codex/artifacts/type2-settled-outcome-validation-latest/type2-settled-outcome-validation.json",
        {
            "status": "settled_validation_no_policy_change_same_slate",
            "review_only": True,
            "summary": {
                "valid_directional_row_count": 1239,
                "directional_correct_rate": 0.4503,
                "current_threshold_count": 0,
                "same_slate_date_count": 1,
            },
        },
    )
    _write_json(
        mlb
        / "docs/codex/artifacts/type2-closing-proxy-validation-latest/type2-closing-proxy-validation.json",
        {
            "status": "closing_proxy_same_slate_support_insufficient",
            "review_only": True,
            "summary": {
                "paired_row_count": 819,
                "current_threshold_count": 0,
                "same_slate_date_count": 1,
                "best_lower_threshold_candidate": {
                    "threshold": 0.025,
                    "exchange_support_count": 6,
                    "exchange_against_count": 0,
                },
            },
        },
    )

    report = build_unlock_scout(
        control_repo=repo,
        manual_drops=manual,
        mlb_repo=mlb,
        as_of_utc="2026-06-30T00:00:00Z",
    )

    mlb_lane = next(lane for lane in report["lanes"] if lane["repo_id"] == "mlb-platform")
    assert mlb_lane["blocked"] is True
    assert mlb_lane["status"] == "closing_proxy_same_slate_support_insufficient"
    assert "only same-slate later-snapshot evidence" in mlb_lane["missing_input"]
    assert "best_lower_threshold=0.025" in mlb_lane["what_exists"]
    assert "best_lower_support=6" in mlb_lane["what_exists"]


def test_unlock_scout_reports_mlb_betexplorer_moneyline_no_policy_change(tmp_path):
    repo = tmp_path / "predmarket"
    manual = tmp_path / "manual_drops"
    mlb = tmp_path / "mlb"
    _write_json(repo / "docs/codex/macro/latest-decision.json", {"all_lanes_parked": True})
    _write_json(
        mlb
        / "docs/codex/artifacts/type2-betexplorer-moneyline-closing-comparison-latest/type2-betexplorer-moneyline-closing-comparison.json",
        {
            "status": "betexplorer_moneyline_closing_comparison_ready_no_policy_change",
            "review_only": True,
            "summary": {
                "matched_row_count": 22,
                "current_threshold_count": 0,
                "converged_count": 16,
                "diverged_count": 6,
                "direction_support_count": 17,
                "direction_against_count": 5,
            },
        },
    )

    report = build_unlock_scout(
        control_repo=repo,
        manual_drops=manual,
        mlb_repo=mlb,
        as_of_utc="2026-06-30T00:00:00Z",
    )

    mlb_lane = next(lane for lane in report["lanes"] if lane["repo_id"] == "mlb-platform")
    assert mlb_lane["blocked"] is True
    assert mlb_lane["status"] == "betexplorer_moneyline_closing_comparison_ready_no_policy_change"
    assert "Public BetExplorer moneyline comparison is present" in mlb_lane["missing_input"]
    assert "matched_rows=22" in mlb_lane["what_exists"]
    assert "current_threshold_count=0" in mlb_lane["what_exists"]


def test_unlock_scout_reports_mlb_betexplorer_market_no_policy_change(tmp_path):
    repo = tmp_path / "predmarket"
    manual = tmp_path / "manual_drops"
    mlb = tmp_path / "mlb"
    _write_json(repo / "docs/codex/macro/latest-decision.json", {"all_lanes_parked": True})
    _write_json(
        mlb
        / "docs/codex/artifacts/type2-betexplorer-market-closing-comparison-latest/type2-betexplorer-market-closing-comparison.json",
        {
            "status": "betexplorer_market_closing_comparison_ready_no_policy_change",
            "review_only": True,
            "summary": {
                "matched_row_count": 24,
                "matched_by_market": {"ml": 22, "run_line": 2},
                "current_threshold_count": 0,
                "converged_count": 16,
                "diverged_count": 8,
                "direction_support_count": 18,
                "direction_against_count": 6,
            },
        },
    )

    report = build_unlock_scout(
        control_repo=repo,
        manual_drops=manual,
        mlb_repo=mlb,
        as_of_utc="2026-06-30T00:00:00Z",
    )

    mlb_lane = next(lane for lane in report["lanes"] if lane["repo_id"] == "mlb-platform")
    assert mlb_lane["blocked"] is True
    assert mlb_lane["status"] == "betexplorer_market_closing_comparison_ready_no_policy_change"
    assert "Public BetExplorer multi-market comparison is present" in mlb_lane["missing_input"]
    assert "matched_rows=24" in mlb_lane["what_exists"]
    assert "matched_by_market={'ml': 22, 'run_line': 2}" in mlb_lane["what_exists"]
    assert "current_threshold_count=0" in mlb_lane["what_exists"]


def test_render_unlock_scout_markdown_lists_lanes():
    markdown = render_unlock_scout_markdown(
        {
            "as_of_utc": "2026-06-28T00:00:00Z",
            "router": {"all_lanes_parked": True},
            "local_inputs": {
                "manual_drops": "/tmp/manual",
                "odds_api_json_count": 0,
                "kalshi_json_count": 0,
                "predmarket_reference_exists": False,
            },
            "lanes": [
                {
                    "repo_id": "predmarket-alpha",
                    "status": "blocked",
                    "blocked": True,
                    "what_exists": "nothing",
                    "missing_input": "timing-safe reference",
                    "next_local_command": "make type2-reference-build",
                }
            ],
        }
    )

    assert "predmarket-alpha" in markdown
    assert "make type2-reference-build" in markdown
