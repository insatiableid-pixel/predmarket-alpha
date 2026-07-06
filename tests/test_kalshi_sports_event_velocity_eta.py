from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_event_velocity_eta.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_module():
    spec = importlib.util.spec_from_file_location("kalshi_sports_event_velocity_eta", SCRIPT_PATH)
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


def base_inputs(tmp_path: Path) -> dict[str, Path]:
    universe = safe_artifact("universe_scan_ready_with_model_routes")
    universe["candidates"] = [
        {
            "ticker": "KXMLBGAME-26JUL05TEAM-AAA",
            "series_ticker": "KXMLBGAME",
            "classification": "mlb",
            "gate_status": "pass",
            "settlement_time": "2026-07-06T02:00:00Z",
        },
        {
            "ticker": "KXATPMATCH-26JUL05AAABBB-AAA",
            "series_ticker": "KXATPMATCH",
            "classification": "atp",
            "gate_status": "pass",
            "settlement_time": "2026-07-05T22:00:00Z",
        },
    ]
    preflight = safe_artifact("sports_consensus_preflight_ready", valid_candidate_count=2)
    preflight["candidates"] = [
        {
            "valid": True,
            "kalshi_ticker": "KXMLBGAME-26JUL05TEAM-AAA",
            "side": "yes",
        },
        {
            "valid": True,
            "kalshi_ticker": "KXATPMATCH-26JUL05AAABBB-AAA",
            "side": "yes",
        },
    ]
    falsification = safe_artifact(
        "sports_consensus_falsification_blocked_insufficient_labels",
        joined_label_count=2,
        independent_label_count=2,
        oos_label_count=1,
        min_independent_labels=30,
        min_oos_labels=10,
        fdr_survivor_count=0,
    )
    falsification["rows"] = [
        {
            "contract_ticker": "KXMLBGAME-26JUL04TEAM-AAA",
            "sport_key": "baseball_mlb",
            "observed_utc": "2026-07-04T20:00:00Z",
            "settlement_outcome": 1,
        },
        {
            "contract_ticker": "KXATPMATCH-26JUL04AAABBB-AAA",
            "sport_key": "tennis_atp",
            "observed_utc": "2026-07-04T21:00:00Z",
            "settlement_outcome": 0,
        },
    ]
    return {
        "universe": write_json(tmp_path / "universe.json", universe),
        "sports_model": write_json(
            tmp_path / "sports_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=8,
                independent_contract_label_count=8,
                min_independent_labels=30,
                min_oos_labels=10,
            ),
        ),
        "atp": write_json(
            tmp_path / "atp.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=2,
                forward_oos_resolved=2,
                min_settled_labels=10,
                forward_oos_min_probe=10,
                next_public_label_probe_utc="2026-07-05T22:30:00Z",
            ),
        ),
        "world_cup": write_json(
            tmp_path / "world_cup.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_ready_with_research_candidates",
                valid_label_row_count=93,
                independent_contract_label_count=93,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=2,
            ),
        ),
        "world_cup_independence": write_json(
            tmp_path / "world_cup_independence.json",
            safe_artifact(
                "world_cup_outcome_independence_diagnostic_ready_candidate_independence_review",
                exact_contract_label_count=93,
                outcome_family_label_count=23,
                match_cluster_count=3,
                min_independent_labels=30,
                min_oos_labels=10,
                current_candidate_independence_requires_review=True,
                recommended_portfolio_cluster_unit="world_cup_match",
            ),
        ),
        "preflight": write_json(tmp_path / "preflight.json", preflight),
        "observation": write_json(
            tmp_path / "observation.json",
            safe_artifact(
                "sports_consensus_observation_loop_label_rows_ready",
                due_distinct_contract_count=2,
                next_public_label_probe_utc="2026-07-05T20:30:00Z",
            ),
        ),
        "falsification": write_json(tmp_path / "falsification.json", falsification),
        "nba_adapter": write_json(
            tmp_path / "nba_adapter.json",
            safe_artifact(
                "sports_consensus_nba_adapter_blocked_no_nba_rows",
                nba_reference_row_count=0,
                nba_unique_kalshi_ticker_count=0,
            ),
        ),
        "flow": write_json(
            tmp_path / "flow.json",
            safe_artifact(
                "near_resolution_informed_flow_research_candidates_ready",
                settled_contract_label_count=199,
                min_settled_contracts=30,
                min_oos_labels=10,
                distinct_contract_count=1454,
                research_candidate_count=2,
            ),
        ),
        "passive": write_json(
            tmp_path / "passive.json",
            safe_artifact(
                "passive_liquidity_paper_fill_falsification_blocked_no_paper_fills",
                valid_paper_fill_label_count=226,
                paper_filled_count=0,
                paper_intent_count=462,
                min_independent_labels=30,
                min_oos_labels=10,
                min_oos_fills=3,
            ),
        ),
    }


def test_event_velocity_eta_surfaces_label_deficits_and_bottlenecks(tmp_path: Path) -> None:
    module = load_module()
    files = base_inputs(tmp_path)

    report = module.build_sports_event_velocity_eta(
        universe_path=files["universe"],
        sports_model_path=files["sports_model"],
        atp_evidence_path=files["atp"],
        world_cup_model_path=files["world_cup"],
        world_cup_outcome_independence_path=files["world_cup_independence"],
        consensus_preflight_path=files["preflight"],
        consensus_observation_path=files["observation"],
        consensus_falsification_path=files["falsification"],
        consensus_nba_adapter_path=files["nba_adapter"],
        flow_path=files["flow"],
        passive_fill_falsification_path=files["passive"],
        generated_utc="2026-07-05T20:00:00Z",
    )

    assert report["status"] == "sports_event_velocity_eta_ready_with_paper_fill_deficits"
    assert report["execution_enabled"] is False
    assert report["market_execution"] is False
    assert report["summary"]["safe_artifact_count"] == 11

    rows = {row["surface_id"]: row for row in report["eta_rows"]}
    assert rows["sports_consensus_all"]["label_deficit"] == 28
    assert rows["sports_consensus_all"]["oos_deficit"] == 9
    assert rows["sports_consensus_all"]["candidate_count"] == 2
    assert rows["sports_consensus_all"]["active_candidate_count"] == 2
    assert rows["sports_consensus_all"]["eta_status"] == ("waiting_for_next_probe_or_settlement")
    assert rows["sports_consensus_mlb"]["active_candidate_count"] == 1
    assert rows["sports_consensus_atp"]["active_candidate_count"] == 1
    assert rows["sports_consensus_nba"]["eta_status"] == "blocked_no_current_nba_consensus_rows"
    assert rows["sports_consensus_nba"]["bottleneck_type"] == (
        "calendar_or_offseason_no_current_markets"
    )
    assert rows["sports_consensus_nba"]["next_probe_utc"] is None
    assert rows["world_cup_proxy_directional"]["label_deficit"] == 7
    assert rows["world_cup_proxy_directional"]["eta_status"] == (
        "blocked_world_cup_independence_review"
    )
    assert rows["world_cup_proxy_directional"]["bottleneck_type"] == (
        "independence_definition_review"
    )
    assert rows["world_cup_proxy_directional"]["portfolio_cluster_unit"] == "world_cup_match"
    assert rows["near_resolution_informed_flow"]["eta_status"] == (
        "label_threshold_met_downstream_gates_active"
    )


def test_event_velocity_eta_keeps_passive_fills_separate_from_labels(tmp_path: Path) -> None:
    module = load_module()
    files = base_inputs(tmp_path)

    report = module.build_sports_event_velocity_eta(
        universe_path=files["universe"],
        sports_model_path=files["sports_model"],
        atp_evidence_path=files["atp"],
        world_cup_model_path=files["world_cup"],
        world_cup_outcome_independence_path=files["world_cup_independence"],
        consensus_preflight_path=files["preflight"],
        consensus_observation_path=files["observation"],
        consensus_falsification_path=files["falsification"],
        consensus_nba_adapter_path=files["nba_adapter"],
        flow_path=files["flow"],
        passive_fill_falsification_path=files["passive"],
        generated_utc="2026-07-05T20:00:00Z",
    )

    passive = next(
        row for row in report["eta_rows"] if row["surface_id"] == "passive_liquidity_paper_fill"
    )
    assert passive["bottleneck_type"] == "paper_fill_clock"
    assert passive["current_label_count"] == 226
    assert passive["paper_fill_count"] == 0
    assert passive["paper_fill_deficit"] == 3
    assert passive["eta_status"] == "blocked_waiting_for_paper_maker_fills"


def test_event_velocity_eta_marks_passive_fdr_no_survivor_as_downstream(
    tmp_path: Path,
) -> None:
    module = load_module()
    files = base_inputs(tmp_path)
    write_json(
        files["passive"],
        safe_artifact(
            "passive_liquidity_paper_fill_falsification_ready_no_research_candidates",
            valid_paper_fill_label_count=951,
            paper_filled_count=17,
            paper_intent_count=1652,
            min_independent_labels=30,
            min_oos_labels=10,
            min_oos_fills=3,
            tested_hypothesis_count=3,
            fdr_survivor_count=0,
            research_candidate_count=0,
        ),
    )

    report = module.build_sports_event_velocity_eta(
        universe_path=files["universe"],
        sports_model_path=files["sports_model"],
        atp_evidence_path=files["atp"],
        world_cup_model_path=files["world_cup"],
        world_cup_outcome_independence_path=files["world_cup_independence"],
        consensus_preflight_path=files["preflight"],
        consensus_observation_path=files["observation"],
        consensus_falsification_path=files["falsification"],
        consensus_nba_adapter_path=files["nba_adapter"],
        flow_path=files["flow"],
        passive_fill_falsification_path=files["passive"],
        generated_utc="2026-07-05T20:00:00Z",
    )

    passive = next(
        row for row in report["eta_rows"] if row["surface_id"] == "passive_liquidity_paper_fill"
    )
    assert passive["bottleneck_type"] == "compute_or_downstream_gates"
    assert passive["eta_status"] == "label_threshold_met_no_fdr_survivor"
    assert passive["paper_fill_deficit"] == 0
    assert passive["label_deficit"] == 0
    assert passive["oos_deficit"] == 0
    assert passive["fdr_survivor_count"] == 0
    assert passive["research_candidate_count"] == 0


def test_event_velocity_eta_surfaces_consensus_rule_bucket_accumulation(
    tmp_path: Path,
) -> None:
    module = load_module()
    files = base_inputs(tmp_path)
    write_json(
        files["falsification"],
        safe_artifact(
            "sports_consensus_falsification_blocked_no_testable_hypotheses",
            joined_label_count=185,
            independent_label_count=31,
            oos_label_count=10,
            min_independent_labels=30,
            min_oos_labels=10,
            max_hypothesis_oos_count=5,
            nearest_hypothesis_oos_deficit=5,
            nearest_hypothesis_model_id="sports_consensus_price_bucket_bias_bucket_0.50_0.70",
            hypothesis_accumulation_opportunity_count=239,
            hypothesis_accumulation_opportunity_distinct_contract_count=101,
            nearest_hypothesis_current_opportunity_count=32,
            tested_hypothesis_count=0,
            fdr_survivor_count=0,
        ),
    )
    observation = json.loads(files["observation"].read_text(encoding="utf-8"))
    observation["summary"]["due_distinct_contract_count"] = 0
    observation["summary"]["next_public_label_probe_utc"] = "2026-07-06T02:20:00Z"
    files["observation"].write_text(json.dumps(observation), encoding="utf-8")

    report = module.build_sports_event_velocity_eta(
        universe_path=files["universe"],
        sports_model_path=files["sports_model"],
        atp_evidence_path=files["atp"],
        world_cup_model_path=files["world_cup"],
        world_cup_outcome_independence_path=files["world_cup_independence"],
        consensus_preflight_path=files["preflight"],
        consensus_observation_path=files["observation"],
        consensus_falsification_path=files["falsification"],
        consensus_nba_adapter_path=files["nba_adapter"],
        flow_path=files["flow"],
        passive_fill_falsification_path=files["passive"],
        generated_utc="2026-07-06T01:40:00Z",
    )

    rows = {row["surface_id"]: row for row in report["eta_rows"]}
    rollup = rows["sports_consensus_all"]
    rule_bucket = rows["sports_consensus_rule_bucket_accumulation"]
    assert rollup["label_deficit"] == 0
    assert rollup["oos_deficit"] == 0
    assert rule_bucket["model_id"] == "sports_consensus_price_bucket_bias_bucket_0.50_0.70"
    assert rule_bucket["current_label_count"] == 5
    assert rule_bucket["oos_label_count"] == 5
    assert rule_bucket["oos_deficit"] == 5
    assert rule_bucket["active_candidate_count"] == 32
    assert rule_bucket["hypothesis_accumulation_opportunity_count"] == 239
    assert rule_bucket["hypothesis_accumulation_opportunity_distinct_contract_count"] == 101
    assert rule_bucket["nearest_hypothesis_current_opportunity_count"] == 32
    assert rule_bucket["eta_status"] == "waiting_for_next_probe_or_settlement"
    assert rule_bucket["next_probe_utc"] == "2026-07-06T02:20:00Z"
    assert report["summary"]["next_probe_surface"] == {
        "surface_id": "sports_consensus_rule_bucket_accumulation",
        "next_probe_utc": "2026-07-06T02:20:00Z",
        "eta_days": 0.0278,
        "due_count": 0,
        "label_deficit": 0,
        "oos_deficit": 5,
        "paper_fill_deficit": 0,
        "bottleneck_type": "calendar_settlement_labels",
        "eta_status": "waiting_for_next_probe_or_settlement",
        "model_id": "sports_consensus_price_bucket_bias_bucket_0.50_0.70",
    }
    assert report["next_action"]["name"] == "kalshi_sports_wait_for_next_settlement_clock"
    assert "sports_consensus_rule_bucket_accumulation" in report["next_action"]["why"]
    assert report["summary"]["actionable_calendar_label_blocked_surface_count"] >= 1
    assert report["summary"]["actionable_calendar_oos_deficit"] >= 5


def test_event_velocity_eta_marks_stale_unmatched_consensus_reference(
    tmp_path: Path,
) -> None:
    module = load_module()
    files = base_inputs(tmp_path)
    preflight = json.loads(files["preflight"].read_text(encoding="utf-8"))
    preflight["candidates"][1].update(
        {
            "valid": False,
            "blocker_reasons": [
                "kalshi_ticker_not_found",
                "timestamp_skew_exceeds_policy",
            ],
        }
    )
    files["preflight"].write_text(json.dumps(preflight), encoding="utf-8")

    report = module.build_sports_event_velocity_eta(
        universe_path=files["universe"],
        sports_model_path=files["sports_model"],
        atp_evidence_path=files["atp"],
        world_cup_model_path=files["world_cup"],
        world_cup_outcome_independence_path=files["world_cup_independence"],
        consensus_preflight_path=files["preflight"],
        consensus_observation_path=files["observation"],
        consensus_falsification_path=files["falsification"],
        consensus_nba_adapter_path=files["nba_adapter"],
        flow_path=files["flow"],
        passive_fill_falsification_path=files["passive"],
        generated_utc="2026-07-05T20:00:00Z",
    )

    rows = {row["surface_id"]: row for row in report["eta_rows"]}
    atp = rows["sports_consensus_atp"]
    assert atp["candidate_count"] == 1
    assert atp["active_candidate_count"] == 0
    assert atp["rejected_candidate_count"] == 1
    assert atp["timestamp_skew_blocker_count"] == 1
    assert atp["kalshi_ticker_not_found_blocker_count"] == 1
    assert atp["bottleneck_type"] == "stale_or_unmatched_strict_consensus_reference"
    assert atp["eta_status"] == "blocked_stale_or_unmatched_strict_consensus_reference"
    assert atp["next_probe_utc"] is None
    assert report["summary"]["external_or_source_blocked_surface_count"] >= 1
    assert report["next_action"]["name"] == "kalshi_sports_stale_or_source_blocker_refresh"


def test_event_velocity_eta_uses_consensus_expected_expiration_clock(
    tmp_path: Path,
) -> None:
    module = load_module()
    files = base_inputs(tmp_path)
    observation = json.loads(files["observation"].read_text(encoding="utf-8"))
    observation["summary"]["due_distinct_contract_count"] = 0
    observation["summary"]["next_public_label_probe_utc"] = "2026-07-05T20:00:00Z"
    observation["summary"]["next_expected_expiration_utc"] = "2026-07-05T20:35:00Z"
    files["observation"].write_text(json.dumps(observation), encoding="utf-8")

    report = module.build_sports_event_velocity_eta(
        universe_path=files["universe"],
        sports_model_path=files["sports_model"],
        atp_evidence_path=files["atp"],
        world_cup_model_path=files["world_cup"],
        world_cup_outcome_independence_path=files["world_cup_independence"],
        consensus_preflight_path=files["preflight"],
        consensus_observation_path=files["observation"],
        consensus_falsification_path=files["falsification"],
        consensus_nba_adapter_path=files["nba_adapter"],
        flow_path=files["flow"],
        passive_fill_falsification_path=files["passive"],
        generated_utc="2026-07-05T20:10:00Z",
    )

    rows = {row["surface_id"]: row for row in report["eta_rows"]}
    assert rows["sports_consensus_all"]["due_count"] == 0
    assert rows["sports_consensus_all"]["eta_status"] == ("waiting_for_next_probe_or_settlement")
    assert rows["sports_consensus_all"]["next_probe_utc"] == "2026-07-05T20:35:00Z"


def test_event_velocity_eta_keeps_due_consensus_backlog_visible(
    tmp_path: Path,
) -> None:
    module = load_module()
    files = base_inputs(tmp_path)
    observation = json.loads(files["observation"].read_text(encoding="utf-8"))
    observation["summary"]["due_distinct_contract_count"] = 7
    observation["summary"]["next_public_label_probe_utc"] = "2026-07-05T20:00:00Z"
    observation["summary"]["next_expected_expiration_utc"] = "2026-07-05T20:35:00Z"
    files["observation"].write_text(json.dumps(observation), encoding="utf-8")

    report = module.build_sports_event_velocity_eta(
        universe_path=files["universe"],
        sports_model_path=files["sports_model"],
        atp_evidence_path=files["atp"],
        world_cup_model_path=files["world_cup"],
        world_cup_outcome_independence_path=files["world_cup_independence"],
        consensus_preflight_path=files["preflight"],
        consensus_observation_path=files["observation"],
        consensus_falsification_path=files["falsification"],
        consensus_nba_adapter_path=files["nba_adapter"],
        flow_path=files["flow"],
        passive_fill_falsification_path=files["passive"],
        generated_utc="2026-07-05T20:10:00Z",
    )

    rows = {row["surface_id"]: row for row in report["eta_rows"]}
    assert rows["sports_consensus_all"]["due_count"] == 7
    assert rows["sports_consensus_all"]["eta_status"] == "next_probe_due_now"
    assert rows["sports_consensus_all"]["next_probe_utc"] == "2026-07-05T20:00:00Z"
    assert report["summary"]["next_due_surface"] == {
        "surface_id": "sports_consensus_all",
        "due_count": 7,
        "next_probe_utc": "2026-07-05T20:00:00Z",
    }
    assert report["next_action"]["name"] == "kalshi_sports_exact_settlement_probe"


def test_event_velocity_eta_uses_consensus_due_counts_by_sport(
    tmp_path: Path,
) -> None:
    module = load_module()
    files = base_inputs(tmp_path)
    observation = json.loads(files["observation"].read_text(encoding="utf-8"))
    observation["summary"]["due_distinct_contract_count"] = 7
    observation["summary"]["due_distinct_contract_count_by_sport"] = {
        "baseball_mlb": 2,
        "tennis_atp": 5,
    }
    observation["summary"]["next_public_label_probe_utc"] = "2026-07-05T20:00:00Z"
    files["observation"].write_text(json.dumps(observation), encoding="utf-8")

    report = module.build_sports_event_velocity_eta(
        universe_path=files["universe"],
        sports_model_path=files["sports_model"],
        atp_evidence_path=files["atp"],
        world_cup_model_path=files["world_cup"],
        world_cup_outcome_independence_path=files["world_cup_independence"],
        consensus_preflight_path=files["preflight"],
        consensus_observation_path=files["observation"],
        consensus_falsification_path=files["falsification"],
        consensus_nba_adapter_path=files["nba_adapter"],
        flow_path=files["flow"],
        passive_fill_falsification_path=files["passive"],
        generated_utc="2026-07-05T20:10:00Z",
    )

    rows = {row["surface_id"]: row for row in report["eta_rows"]}
    assert rows["sports_consensus_all"]["due_count"] == 7
    assert rows["sports_consensus_mlb"]["due_count"] == 2
    assert rows["sports_consensus_atp"]["due_count"] == 5
    assert rows["sports_consensus_world_cup_soccer"]["due_count"] == 0
    assert rows["sports_consensus_nfl"]["due_count"] == 0
    assert report["summary"]["next_due_surface"] == {
        "surface_id": "sports_consensus_atp",
        "due_count": 5,
        "next_probe_utc": "2026-07-05T20:00:00Z",
    }


def test_event_velocity_eta_marks_atp_forward_oos_after_settlement_labels(
    tmp_path: Path,
) -> None:
    module = load_module()
    files = base_inputs(tmp_path)
    write_json(
        files["atp"],
        safe_artifact(
            "atp_proxy_evidence_gate_blocked_forward_oos",
            settled_label_count=382,
            forward_oos_resolved=2,
            min_settled_labels=10,
            forward_oos_min_probe=10,
            next_public_label_probe_utc="2026-07-05T20:14:09Z",
            next_expected_expiration_utc="2026-07-06T06:00:00Z",
        ),
    )

    report = module.build_sports_event_velocity_eta(
        universe_path=files["universe"],
        sports_model_path=files["sports_model"],
        atp_evidence_path=files["atp"],
        world_cup_model_path=files["world_cup"],
        world_cup_outcome_independence_path=files["world_cup_independence"],
        consensus_preflight_path=files["preflight"],
        consensus_observation_path=files["observation"],
        consensus_falsification_path=files["falsification"],
        consensus_nba_adapter_path=files["nba_adapter"],
        flow_path=files["flow"],
        passive_fill_falsification_path=files["passive"],
        generated_utc="2026-07-05T20:20:00Z",
    )

    rows = {row["surface_id"]: row for row in report["eta_rows"]}
    assert rows["atp_proxy_settlement_window"]["label_deficit"] == 0
    assert rows["atp_proxy_settlement_window"]["oos_deficit"] == 8
    assert rows["atp_proxy_settlement_window"]["bottleneck_type"] == "external_forward_oos"
    assert rows["atp_proxy_settlement_window"]["eta_status"] == "blocked_atp_forward_oos"
    assert rows["atp_proxy_settlement_window"]["next_probe_utc"] == "2026-07-06T06:00:00Z"


def test_event_velocity_temp_out_dir_does_not_mutate_macro_latest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    macro_dir = tmp_path / "macro"
    monkeypatch.setattr(module, "MACRO_DIR", macro_dir)
    files = base_inputs(tmp_path)
    report = module.build_sports_event_velocity_eta(
        universe_path=files["universe"],
        sports_model_path=files["sports_model"],
        atp_evidence_path=files["atp"],
        world_cup_model_path=files["world_cup"],
        world_cup_outcome_independence_path=files["world_cup_independence"],
        consensus_preflight_path=files["preflight"],
        consensus_observation_path=files["observation"],
        consensus_falsification_path=files["falsification"],
        consensus_nba_adapter_path=files["nba_adapter"],
        flow_path=files["flow"],
        passive_fill_falsification_path=files["passive"],
        generated_utc="2026-07-05T20:00:00Z",
    )
    paths = module.write_outputs(report, out_dir=tmp_path / "out")

    assert "latest_json_path" not in paths
    assert not (macro_dir / "latest-kalshi-sports-event-velocity-eta.json").exists()


def test_event_velocity_makefile_target_exists() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-event-velocity-eta" in text
    assert "scripts/kalshi_sports_event_velocity_eta.py" in text
