from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from predmarket.kalshi_execution_cost import GENERAL_MAKER_FEE_RATE, kalshi_trade_fee

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kalshi_contract_ev_ledger.py"
SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "codex"
    / "macro"
    / "kalshi-contract-ev-ledger.schema.json"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_ledger_module():
    spec = importlib.util.spec_from_file_location("kalshi_contract_ev_ledger", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_example_ev_row(ledger_mod, **overrides):
    params = {
        "source_repo_id": "example",
        "source_artifact": SCRIPT_PATH,
        "source_row_index": 0,
        "contract_ticker": "EXAMPLE-YES",
        "event_ticker": "EXAMPLE",
        "market_ticker": "EXAMPLE",
        "side": "yes",
        "selection": "yes",
        "market_type": "example",
        "title": "Example",
        "resolution_rule": "YES resolves if the example contract settles yes under verified official terms.",
        "resolution_rule_source": "unit_test_official_terms",
        "resolution_rule_status": "verified_official_terms",
        "display_price": 0.71,
        "display_price_source": "screen_price",
        "executable_price_source": "screen_price",
        "fee_estimate": None,
        "slippage_buffer": None,
        "explicit_all_in_cost": None,
        "all_in_payout_multiple": None,
        "kalshi_payout_multiple": 1.34,
        "calibrated_probability": 0.76,
        "calibrated_probability_source": "unit_test_calibrated_probability",
        "calibration_status": "validated_calibrated_probability",
        "calibrated_probability_source_artifact": None,
        "calibrated_probability_source_sha256": None,
        "reference_probability": None,
        "reference_probability_source": "none",
        "probability_uncertainty": None,
        "kalshi_bid": None,
        "kalshi_ask": 0.71,
        "kalshi_midpoint": None,
        "gate_status": "pass",
        "gate_reasons": [],
        "review_status": "review_ready",
        "timing_status": "clean",
        "mapping_confidence": "high",
    }
    params.update(overrides)
    return ledger_mod.make_ev_row(**params)


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def safe_overlay(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "research_only": True,
        "execution_enabled": False,
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "provider_api_calls": False,
            "database_writes": False,
        },
        "rows": rows,
    }


def make_ev_ledger_fixture(tmp_path: Path) -> dict[str, Any]:
    repos_dir = tmp_path / "repos"
    predmarket_repo = repos_dir / "predmarket-alpha"
    mlb_repo = repos_dir / "mlb-platform"
    atp_repo = repos_dir / "atp-oracle"
    nba_repo = repos_dir / "nba-analytics-platform"
    nfl_repo = repos_dir / "nfl_quant_glm51_greenfield"
    repos = [
        ("predmarket-alpha", predmarket_repo),
        ("mlb-platform", mlb_repo),
        ("atp-oracle", atp_repo),
        ("nba-analytics-platform", nba_repo),
        ("nfl_quant_glm51_greenfield", nfl_repo),
    ]
    active_universe = write_json(
        tmp_path / "macro" / "active-universe.json",
        {
            "schema_version": 1,
            "as_of": "2026-07-01",
            "control_plane_repo_id": "predmarket-alpha",
            "phase": "research_paper_only",
            "repos": [
                {
                    "repo_id": repo_id,
                    "path": str(repo_path),
                    "role": "unit_test_fixture",
                    "default_tranche": "unit_test",
                }
                for repo_id, repo_path in repos
            ],
        },
    )

    predmarket_candidates: list[dict[str, Any]] = []
    predmarket_dispositions: list[dict[str, Any]] = []
    term_records: list[dict[str, Any]] = []
    for index in range(5):
        event_ticker = f"KXMLBGAME-26JUL0{index}AAA{index}BBB{index}"
        contract_ticker = f"{event_ticker}-AAA{index}"
        reference_id = f"fixture-reference-{index}"
        predmarket_candidates.append(
            {
                "event_ticker": event_ticker,
                "kalshi_ticker": contract_ticker,
                "kalshi_ask": 0.41 + index * 0.01,
                "kalshi_bid": 0.40 + index * 0.01,
                "kalshi_midpoint": 0.405 + index * 0.01,
                "reference_id": reference_id,
                "review_status": "REVIEW_READY",
                "sportsbook_no_vig_yes": 0.57 + index * 0.01,
                "sportsbook_no_vig_no": 0.43 - index * 0.01,
                "title": f"Fixture AAA{index} vs BBB{index} Winner?",
                "uncertainty_buffer": 0.01,
            }
        )
        predmarket_dispositions.append(
            {
                "kalshi_ticker": contract_ticker,
                "reference_id": reference_id,
                "disposition": "PREGAME_CLEAN",
            }
        )
        term_records.append(
            {
                "ticker": contract_ticker,
                "event_ticker": event_ticker,
                "rules_primary": (
                    f"{contract_ticker} market resolves to Yes if the fixture selection wins "
                    "under official Kalshi rules."
                ),
            }
        )
    write_json(
        predmarket_repo
        / "docs/codex/artifacts/type2-paper-matcher-latest/type2-paper-matcher-latest.json",
        {
            "research_only": True,
            "execution_enabled": False,
            "safety": {
                "market_execution": False,
                "account_or_order_paths": False,
                "database_writes": False,
            },
            "candidates": predmarket_candidates,
        },
    )
    write_json(
        predmarket_repo
        / "docs/codex/artifacts/type2-candidate-disposition-latest/type2-candidate-disposition-latest.json",
        {
            "research_only": True,
            "execution_enabled": False,
            "safety": {
                "market_execution": False,
                "account_or_order_paths": False,
                "database_writes": False,
            },
            "dispositions": predmarket_dispositions,
        },
    )
    write_json(
        predmarket_repo / "docs/codex/macro/latest-kalshi-sports-proxy-feature-packet.json",
        {
            "schema_version": 1,
            "status": "sports_proxy_feature_packet_ready",
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "safety": {
                "market_execution": False,
                "account_or_order_paths": False,
                "database_writes": False,
            },
            "feature_rows": [
                {
                    "contract_ticker": "KXMLBGAME-26JUL041910NYYBOS-NYY",
                    "event_ticker": "KXMLBGAME-26JUL041910NYYBOS",
                    "series_ticker": "KXMLBGAME",
                    "league": "MLB",
                    "selected_code": "NYY",
                    "title": "New York Yankees vs Boston Red Sox Winner?",
                    "feature_status": "sports_proxy_features_ready",
                    "yes_ask": 0.55,
                    "yes_bid": 0.54,
                    "win_probability": 0.57,
                }
            ],
        },
    )
    term_records.append(
        {
            "ticker": "KXMLBGAME-26JUL041910NYYBOS-NYY",
            "event_ticker": "KXMLBGAME-26JUL041910NYYBOS",
            "rules_primary": (
                "KXMLBGAME-26JUL041910NYYBOS-NYY market resolves to Yes if New York Yankees win "
                "under official Kalshi rules."
            ),
        }
    )

    mlb_ticker = "KXMLBGAME-26JUL04MLBHOMEAWAY-HOME"
    term_records.append(
        {
            "ticker": mlb_ticker,
            "event_ticker": "KXMLBGAME-26JUL04MLBHOMEAWAY",
            "rules_primary": (
                f"{mlb_ticker} market resolves to Yes if the home fixture side wins "
                "under official Kalshi rules."
            ),
        }
    )
    write_json(
        mlb_repo / "docs/codex/artifacts/type2-fixture/type2-evidence.json",
        {
            "research_only": True,
            "execution_enabled": False,
            "candidates": [
                {
                    "exchange_market_id": mlb_ticker,
                    "exchange_ask": 0.48,
                    "exchange_bid": 0.47,
                    "exchange_prob": 0.475,
                    "friction_prob": 0.01,
                    "game_id": "fixture-mlb-game",
                    "game_id_match_mode": "exact",
                    "market": "moneyline",
                    "selection": "HOME",
                    "source_snapshot_role": "pregame_clean",
                    "sportsbook_prob": 0.54,
                    "status": "review_ready",
                }
            ],
        },
    )

    terms_dir = tmp_path / "terms"
    write_json(terms_dir / "kalshi_scored_fixture.json", {"markets": term_records})

    nfl_ticker = "KXNFLGAME-26SEP10KCLAC-KC"
    mapping_dir = tmp_path / "contract-mappings"
    write_json(
        mapping_dir / "nfl-contract-mapping.json",
        safe_overlay(
            [
                {
                    "source_repo_id": "nfl_quant_glm51_greenfield",
                    "contract_ticker": nfl_ticker,
                    "event_ticker": "KXNFLGAME-26SEP10KCLAC",
                    "market_ticker": "KXNFLGAME-26SEP10KCLAC",
                    "side": "yes",
                    "selection": "KC",
                    "market_type": "nfl_game_winner",
                    "title": "Kansas City vs LA Chargers Winner?",
                    "mapping_status": "verified_contract_mapping",
                    "mapping_confidence": "high",
                    "resolution_rule": (
                        f"{nfl_ticker} market resolves to Yes if Kansas City wins "
                        "under verified official Kalshi terms."
                    ),
                    "resolution_rule_source": "local_kalshi_contract_evidence_scout",
                    "resolution_rule_status": "verified_official_terms",
                    "executable_price": 0.42,
                    "executable_price_source": "fixture_quote",
                    "display_price_source": "fixture_quote",
                    "kalshi_ask": 0.42,
                    "kalshi_bid": 0.41,
                    "kalshi_midpoint": 0.415,
                    "reference_probability": 0.55,
                    "reference_probability_source": "fixture_market_reference",
                    "timing_status": "pregame_clean",
                }
            ]
        ),
    )
    probability_dir = tmp_path / "probabilities"
    write_json(
        probability_dir / "nfl-probability.json",
        safe_overlay(
            [
                {
                    "contract_ticker": nfl_ticker,
                    "side": "yes",
                    "calibrated_probability": 0.72,
                    "calibrated_probability_source": "fixture_validated_model",
                    "calibration_status": "validated_calibrated_probability",
                    "probability_uncertainty": 0.03,
                }
            ]
        ),
    )
    write_json(
        atp_repo / "data/kalshi/matches-2026-07-03.json",
        {
            "captured_at": "2026-07-03T19:31:02Z",
            "source": "kalshi_public_api",
            "series_ticker": "KXATPMATCH",
            "status_filter": "open",
            "n_matches": 1,
            "matches": [
                {
                    "player_a": "Carlos Alcaraz",
                    "player_b": "Matteo Berrettini",
                    "kalshi_price_a": 0.62,
                    "kalshi_price_b": 0.39,
                    "kalshi_market_id_a": "KXATPMATCH-26JUL05ALCBER-ALC",
                    "kalshi_market_id_b": "KXATPMATCH-26JUL05ALCBER-BER",
                    "surface": "Grass",
                    "best_of": 5,
                    "tourney_name": "Wimbledon",
                    "tourney_level": "G",
                    "_kalshi_event_ticker": "KXATPMATCH-26JUL05ALCBER",
                    "_yes_bid_a": 0.61,
                    "_yes_bid_b": 0.38,
                    "_yes_ask_a": 0.62,
                    "_yes_ask_b": 0.39,
                    "_close_time_a": "2026-07-05T16:00:00Z",
                    "_close_time_b": "2026-07-05T16:00:00Z",
                }
            ],
        },
    )

    return {
        "active_universe_path": active_universe,
        "official_terms_paths": [terms_dir],
        "calibrated_probability_paths": [probability_dir],
        "contract_mapping_paths": [mapping_dir],
        "nfl_ticker": nfl_ticker,
    }


def build_fixture_ledger(ledger_mod, tmp_path: Path) -> dict[str, Any]:
    fixture = make_ev_ledger_fixture(tmp_path)
    return ledger_mod.build_ledger(
        active_universe_path=fixture["active_universe_path"],
        max_rows_per_repo=10,
        generated_utc="2026-07-01T00:00:00Z",
        official_terms_paths=fixture["official_terms_paths"],
        calibrated_probability_paths=fixture["calibrated_probability_paths"],
        contract_mapping_paths=fixture["contract_mapping_paths"],
    )


def test_kalshi_contract_ev_schema_loads() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["title"] == "KalshiContractEVLedgerV1"
    assert "rows" in schema["required"]
    assert schema["properties"]["research_only"]["const"] is True
    assert schema["properties"]["execution_enabled"]["const"] is False


def test_ledger_collects_all_macro_repos_with_research_only_usable_rows(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()

    ledger = build_fixture_ledger(ledger_mod, tmp_path)

    repo_ids = {feed["repo_id"] for feed in ledger["repo_feeds"]}
    assert repo_ids == {
        "predmarket-alpha",
        "mlb-platform",
        "atp-oracle",
        "nba-analytics-platform",
        "nfl_quant_glm51_greenfield",
    }
    assert ledger["research_only"] is True
    assert ledger["execution_enabled"] is False
    assert ledger["provider_api_calls"] is False
    assert ledger["summary"]["repo_count"] == 5
    assert ledger["summary"]["usable_row_count"] >= 1
    assert ledger["status"] in {
        "kalshi_ev_ledger_ready_with_usable_contract_edges",
        "kalshi_ev_ledger_candidates_present_but_not_usable",
        "kalshi_ev_ledger_blocked_no_contract_rows",
    }
    for feed in ledger["repo_feeds"]:
        readiness = feed["ev_readiness"]
        assert readiness["contract_mapping_status"]
        assert readiness["official_terms_status"]
        assert readiness["execution_cost_status"]
        assert readiness["calibrated_probability_status"]
        assert readiness["row_gate_status"]
        assert readiness["exact_next_input"]
        assert readiness["next_local_command"]


def test_ledger_rows_use_contract_break_even_math(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()

    ledger = build_fixture_ledger(ledger_mod, tmp_path)

    assert ledger["rows"], "fixture artifacts should produce review rows"
    assert ledger["summary"]["positive_edge_row_count"] >= 1
    assert (
        ledger["summary"]["verified_resolution_rule_row_count"]
        + ledger["summary"]["inferred_resolution_rule_row_count"]
        == ledger["summary"]["row_count"]
    )
    assert ledger["summary"]["missing_calibrated_probability_row_count"] == (
        ledger["summary"]["row_count"]
        - ledger["summary"]["calibrated_probability_overlay_row_count"]
    )
    assert (
        ledger["summary"]["blocked_row_reason_counts"]["calibrated contract probability is missing"]
        == ledger["summary"]["missing_calibrated_probability_row_count"]
    )
    assert ledger["summary"]["calibrated_probability_overlay_row_count"] >= 1
    assert ledger["summary"]["contract_mapping_overlay_row_count"] >= 1
    assert {
        "reason": "calibrated contract probability is missing",
        "count": ledger["summary"]["missing_calibrated_probability_row_count"],
    } in ledger["summary"]["top_blocked_row_reasons"]
    usable_rows = [row for row in ledger["rows"] if row["usable"] is True]
    assert usable_rows
    usable = usable_rows[0]
    assert usable["source_repo_id"] == "nfl_quant_glm51_greenfield"
    assert usable["contract_ticker"].startswith("KXNFLGAME-")
    assert usable["resolution_rule_status"] == "verified_official_terms"
    assert usable["resolution_rule_source"] == "local_kalshi_contract_evidence_scout"
    assert usable["calibration_status"] == "validated_calibrated_probability"
    assert usable["calibrated_probability"] is not None
    assert usable["all_in_break_even_probability"] is not None
    assert usable["margin_probability"] is not None
    assert usable["margin_probability"] > 0
    assert usable["gate_status"] == "pass"
    assert usable["timing_status"] == "pregame_clean"
    for row in ledger["rows"]:
        if row["usable"] is True:
            continue
        assert row["display_price"] is not None
        assert row["resolution_rule"]
        if row["resolution_rule_status"] == "verified_official_terms":
            assert row["resolution_rule_source"] in {
                "official_kalshi_local_market_snapshot",
                "local_kalshi_contract_evidence_scout",
            }
            assert row["resolution_rule_source_artifact"]
            assert row["resolution_rule_source_sha256"]
            assert "market resolves to Yes" in row["resolution_rule"]
            assert not any(
                "resolution rule is not independently verified" in reason
                for reason in row["gate_reasons"]
            )
        else:
            assert row["resolution_rule_source"] in {
                "inferred_from_kalshi_ticker_and_title",
                "inferred_from_mlb_type2_evidence",
                "inferred_from_atp_kalshi_match_snapshot",
                "inferred_from_current_sports_feature_packet",
            }
            assert row["resolution_rule_status"] == "inferred_unverified_official_terms"
            assert row["resolution_rule_source_artifact"] is None
            assert row["resolution_rule_source_sha256"] is None
            assert any(
                "resolution rule is not independently verified" in reason
                for reason in row["gate_reasons"]
            )
        assert row["kalshi_payout_multiple"] is None
        assert row["payout_multiple"] is None
        expected_fee = kalshi_trade_fee(price=row["display_price"], fee_rate=GENERAL_MAKER_FEE_RATE)
        assert abs(row["fee_estimate"] - expected_fee) < 1e-12
        assert abs(row["all_in_cost"] - (row["display_price"] + expected_fee)) < 1e-12
        assert row["cost_basis_source"] is not None
        assert row["contract_price_break_even_probability"] == row["display_price"]
        assert row["displayed_price_break_even_probability"] == row["display_price"]
        assert abs(row["all_in_break_even_probability"] - row["all_in_cost"]) < 1e-12
        assert row["payout_implied_break_even_probability"] is None
        assert row["break_even_probability"] == row["all_in_cost"]
        assert row["break_even_source"] == "executable_contract_price_plus_fee_estimate"
        assert abs(row["effective_hold_probability"] - expected_fee) < 1e-12
        assert row["usable"] is False
        if row["calibrated_probability"] is None:
            assert row["reference_probability"] is not None
            assert row["estimated_probability"] is None
            assert row["edge_probability"] is None
            assert row["margin_probability"] is None
            assert row["gate_status"] == "blocked"
            assert any("calibrated" in reason for reason in row["gate_reasons"])
        else:
            assert row["estimated_probability"] == row["calibrated_probability"]
            assert row["edge_probability"] == row["margin_probability"]
            assert row["margin_probability"] <= 0
            assert row["gate_status"] == "warn"
            assert any(
                "does not clear execution cost basis" in reason for reason in row["gate_reasons"]
            )


def test_ev_readiness_distinguishes_contract_vs_probability_gaps(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()

    ledger = build_fixture_ledger(ledger_mod, tmp_path)
    feeds = {feed["repo_id"]: feed for feed in ledger["repo_feeds"]}

    predmarket = feeds["predmarket-alpha"]["ev_readiness"]
    assert predmarket["contract_mapping_status"] == "exact_kalshi_contract_rows_present"
    assert predmarket["official_terms_status"] == "verified_official_terms"
    assert predmarket["execution_cost_status"] == "fee_aware_all_in_cost_present"
    assert predmarket["calibrated_probability_status"] == "missing_calibrated_contract_probability"
    assert "not a sportsbook no-vig reference" in predmarket["exact_next_input"]

    mlb = feeds["mlb-platform"]["ev_readiness"]
    assert mlb["contract_mapping_status"] == "exact_kalshi_contract_rows_present"
    assert mlb["calibrated_probability_status"] == "missing_calibrated_contract_probability"

    nfl = feeds["nfl_quant_glm51_greenfield"]["ev_readiness"]
    assert nfl["contract_mapping_status"] == "exact_kalshi_contract_rows_present"
    assert nfl["official_terms_status"] == "verified_official_terms"
    assert nfl["execution_cost_status"] == "fee_aware_all_in_cost_present"
    assert nfl["calibrated_probability_status"] == "calibrated_contract_probabilities_present"
    assert nfl["row_gate_status"] == "usable_rows_present"


def test_ticket_payout_multiple_controls_gross_execution_break_even_and_hold_when_fee_known() -> (
    None
):
    ledger_mod = load_ledger_module()

    row = make_example_ev_row(ledger_mod, fee_estimate=0.0)

    expected_break_even = 1.0 / 1.34
    assert abs(row["break_even_probability"] - expected_break_even) < 1e-12
    assert abs(row["all_in_break_even_probability"] - expected_break_even) < 1e-12
    assert row["contract_price_break_even_probability"] == 0.71
    assert row["displayed_price_break_even_probability"] == 0.71
    assert abs(row["payout_implied_break_even_probability"] - expected_break_even) < 1e-12
    assert (
        abs(row["payout_multiplier_discrepancy_probability"] - (expected_break_even - 0.71)) < 1e-12
    )
    assert abs(row["all_in_cost"] - expected_break_even) < 1e-12
    assert abs(row["effective_hold_probability"] - (expected_break_even - 0.71)) < 1e-12
    assert abs(row["margin_probability"] - (0.76 - expected_break_even)) < 1e-12
    assert abs(row["expected_value_per_contract"] - (0.76 - expected_break_even)) < 1e-12
    assert row["break_even_source"] == "kalshi_payout_multiple_plus_fee_estimate"
    assert row["cost_basis_source"] == "kalshi_payout_multiple_plus_fee_estimate"
    assert row["payout_multiple_source"] == "kalshi_ticket_payout_gross"
    assert row["source_gate_status"] == "pass"
    assert row["gate_status"] == "pass"
    assert row["usable"] is True


def test_ticket_payout_multiplier_blocks_probability_that_only_beats_display_price() -> None:
    ledger_mod = load_ledger_module()

    row = make_example_ev_row(ledger_mod, calibrated_probability=0.74, fee_estimate=0.0)

    assert row["display_price"] == 0.71
    assert row["displayed_price_break_even_probability"] == 0.71
    assert abs(row["all_in_break_even_probability"] - (1.0 / 1.34)) < 1e-12
    assert row["payout_implied_break_even_probability"] > 0.74
    assert row["margin_probability"] < 0.0
    assert row["expected_value_per_contract"] < 0.0
    assert row["gate_status"] == "warn"
    assert row["usable"] is False
    assert any("does not clear execution cost basis" in reason for reason in row["gate_reasons"])


def test_sports_ccd_projection_row_is_blocked_by_consensus_doctrine(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()
    source = write_json(tmp_path / "cluster.json", {"status": "unit"})

    row = ledger_mod.sports_ccd_paper_overlay_ev_row(
        repo_id="predmarket-alpha",
        source_artifact=source,
        source_row_index=0,
        capacity={
            "contract_ticker": "KXMLBGAME-26JUL031605STLCHC-STL",
            "event_ticker": "KXMLBGAME-26JUL031605STLCHC",
            "league": "MLB",
            "predicted_side": "yes",
            "best_all_in_break_even_probability": 0.40,
            "conservative_calibrated_side_probability": 0.60,
            "controlled_depth_cost": 12.0,
            "controlled_depth_contracts": 30.0,
            "correlation_cluster_key": "MLB|KXMLBGAME-26JUL031605STLCHC|2026-07-03T23:05Z",
            "close_time": "2026-07-03T23:05:00Z",
        },
        official_terms={
            "KXMLBGAME-26JUL031605STLCHC-STL": {
                "resolution_rule": "Official Kalshi MLB game-winner terms.",
                "source_artifact": str(source),
                "source_sha256": "abc",
            }
        },
    )

    assert row["usable"] is False
    assert row["family_id"] == "mlb"
    assert row["capacity_gate_status"] == "pass"
    assert row["correlation_cluster_gate_status"] == "pass"
    assert row["decay_gate_status"] == "decay_survival_pass"
    assert row["source_gate_status"] == "blocked"
    assert row["sports_probability_source_gate_status"] == (
        "blocked_projection_model_not_consensus"
    )
    assert any(
        "timestamp-matched multi-book no-vig consensus" in reason for reason in row["gate_reasons"]
    )
    assert row["capacity_estimate"] == 12.0
    assert abs(row["expected_value_per_contract"] - 0.2) < 1e-12


def test_near_resolution_flow_replay_ready_promotes_usable_ev_row(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()
    predmarket_repo = tmp_path / "repos" / "predmarket-alpha"
    active_universe = write_json(
        tmp_path / "macro" / "active-universe.json",
        {
            "repos": [
                {
                    "repo_id": "predmarket-alpha",
                    "path": str(predmarket_repo),
                }
            ]
        },
    )
    write_json(
        predmarket_repo
        / "docs/codex/artifacts/type2-paper-matcher-latest/type2-paper-matcher-latest.json",
        {
            "research_only": True,
            "execution_enabled": False,
            "safety": {
                "market_execution": False,
                "account_or_order_paths": False,
                "database_writes": False,
            },
            "candidates": [],
        },
    )
    write_json(
        predmarket_repo
        / "docs/codex/artifacts/type2-candidate-disposition-latest/type2-candidate-disposition-latest.json",
        {
            "research_only": True,
            "execution_enabled": False,
            "safety": {
                "market_execution": False,
                "account_or_order_paths": False,
                "database_writes": False,
            },
            "dispositions": [],
        },
    )
    contract_ticker = "KXFLOWGAME-26JUL04AAA-BBB-BBB"
    flow_path = (
        predmarket_repo / "docs/codex/macro/latest-kalshi-near-resolution-flow-replay-gates.json"
    )
    write_json(
        flow_path,
        {
            "schema_version": 1,
            "status": "near_resolution_flow_replay_gates_ready_for_ev_ledger_promotion",
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "summary": {
                "evidence_status": "near_resolution_informed_flow_research_candidates_ready",
                "selected_replay_model_id": "flow_depth_imbalance_settlement_directional",
                "conservative_calibrated_side_probability": 0.72,
                "candidate_oos_label_count": 60,
                "candidate_oos_correct_count": 51,
                "candidate_q_value": 0.0000000308,
                "decay_status": "recent_bucket_not_worse_than_random",
                "decay_bucket_count": 4,
                "controlled_cluster_costs": {
                    "flow|cluster|2026-07-04T20:00Z": 25.0,
                },
            },
            "capacity_rows": [
                {
                    "contract_ticker": contract_ticker,
                    "event_ticker": "KXFLOWGAME-26JUL04AAA-BBB",
                    "series_ticker": "KXFLOWGAME",
                    "sport_surface": "unit_sport",
                    "side": "yes",
                    "gate_status": "pass",
                    "selected_side_executable_price": 0.40,
                    "all_in_cost": 0.42,
                    "fee_estimate": 0.02,
                    "conservative_calibrated_side_probability": 0.72,
                    "expected_value_per_contract": 0.30,
                    "positive_depth_cost": 50.0,
                    "positive_depth_contracts": 125.0,
                    "correlation_cluster_key": "flow|cluster|2026-07-04T20:00Z",
                    "close_time": "2026-07-04T20:00:00Z",
                    "decision_time": "2026-07-04T19:55:00Z",
                    "predicted_outcome": 1,
                }
            ],
            "safety": {
                "research_only": True,
                "execution_enabled": False,
                "provider_api_calls": False,
                "paid_calls": False,
                "database_writes": False,
                "market_execution": False,
                "account_or_order_paths": False,
            },
        },
    )
    terms_dir = tmp_path / "terms"
    write_json(
        terms_dir / "kalshi_scored_flow.json",
        {
            "markets": [
                {
                    "ticker": contract_ticker,
                    "event_ticker": "KXFLOWGAME-26JUL04AAA-BBB",
                    "rules_primary": "If BBB wins, this market resolves to Yes.",
                }
            ]
        },
    )

    ledger = ledger_mod.build_ledger(
        active_universe_path=active_universe,
        official_terms_paths=[terms_dir],
        calibrated_probability_paths=[],
        contract_mapping_paths=[],
        generated_utc="2026-07-04T20:01:00Z",
    )

    flow_rows = [
        row
        for row in ledger["rows"]
        if row.get("market_type") == "sports_microstructure_near_resolution_flow"
    ]
    assert len(flow_rows) == 1
    row = flow_rows[0]
    assert row["usable"] is True
    assert row["family_id"] == "microstructure_informed_flow"
    assert row["model_id"] == "flow_depth_imbalance_settlement_directional"
    assert row["capacity_gate_status"] == "pass"
    assert row["correlation_cluster_gate_status"] == "pass"
    assert row["decay_gate_status"] == "decay_survival_pass"
    assert row["capacity_estimate"] == 25.0
    assert row["controlled_capacity_contracts"] == 62.5
    assert row["expected_value_per_contract"] == 0.3
    assert row["gate_status"] == "pass"


def test_near_resolution_flow_replay_not_ready_does_not_promote_ev_rows(
    tmp_path: Path,
) -> None:
    ledger_mod = load_ledger_module()
    predmarket_repo = tmp_path / "repos" / "predmarket-alpha"
    active_universe = write_json(
        tmp_path / "macro" / "active-universe.json",
        {"repos": [{"repo_id": "predmarket-alpha", "path": str(predmarket_repo)}]},
    )
    write_json(
        predmarket_repo
        / "docs/codex/artifacts/type2-paper-matcher-latest/type2-paper-matcher-latest.json",
        {
            "research_only": True,
            "execution_enabled": False,
            "safety": {
                "market_execution": False,
                "account_or_order_paths": False,
                "database_writes": False,
            },
            "candidates": [],
        },
    )
    write_json(
        predmarket_repo / "docs/codex/macro/latest-kalshi-near-resolution-flow-replay-gates.json",
        {
            "status": "near_resolution_flow_replay_gates_blocked_decay_survival",
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "capacity_rows": [
                {
                    "contract_ticker": "KXFLOWGAME-26JUL04AAA-BBB-BBB",
                    "side": "yes",
                    "gate_status": "pass",
                }
            ],
            "safety": {
                "research_only": True,
                "execution_enabled": False,
                "provider_api_calls": False,
                "paid_calls": False,
                "database_writes": False,
                "market_execution": False,
                "account_or_order_paths": False,
            },
        },
    )

    ledger = ledger_mod.build_ledger(
        active_universe_path=active_universe,
        official_terms_paths=[],
        calibrated_probability_paths=[],
        contract_mapping_paths=[],
        generated_utc="2026-07-04T20:01:00Z",
    )

    assert not [
        row
        for row in ledger["rows"]
        if row.get("market_type") == "sports_microstructure_near_resolution_flow"
    ]


def test_gross_ticket_payout_uses_official_fee_estimate_when_fee_missing() -> None:
    ledger_mod = load_ledger_module()

    row = make_example_ev_row(ledger_mod, calibrated_probability=0.76)

    gross = 1.0 / 1.34
    fee = kalshi_trade_fee(price=gross, fee_rate=GENERAL_MAKER_FEE_RATE)
    assert abs(row["break_even_probability"] - (gross + fee)) < 1e-12
    assert row["fee_source"] == "kalshi_official_maker_fee_estimate"
    assert row["gate_status"] == "pass"
    assert row["usable"] is True


def test_missing_payout_multiple_does_not_block_executable_price_ev() -> None:
    ledger_mod = load_ledger_module()

    row = make_example_ev_row(
        ledger_mod,
        kalshi_payout_multiple=None,
        calibrated_probability=0.80,
    )

    assert row["display_price"] == 0.71
    assert row["displayed_price_break_even_probability"] == 0.71
    expected_fee = kalshi_trade_fee(price=0.71, fee_rate=GENERAL_MAKER_FEE_RATE)
    assert abs(row["all_in_break_even_probability"] - (0.71 + expected_fee)) < 1e-12
    assert row["payout_implied_break_even_probability"] is None
    assert abs(row["break_even_probability"] - (0.71 + expected_fee)) < 1e-12
    assert row["break_even_source"] == "executable_contract_price_plus_fee_estimate"
    assert row["cost_basis_source"] == "screen_price"
    assert abs(row["margin_probability"] - (0.80 - 0.71 - expected_fee)) < 1e-12
    assert abs(row["expected_value_per_contract"] - (0.80 - 0.71 - expected_fee)) < 1e-12
    assert row["source_gate_status"] == "pass"
    assert row["gate_status"] == "pass"
    assert row["usable"] is True


def test_known_fee_and_slippage_raise_the_break_even_hurdle() -> None:
    ledger_mod = load_ledger_module()

    row = make_example_ev_row(
        ledger_mod,
        kalshi_payout_multiple=None,
        fee_estimate=0.01,
        slippage_buffer=0.005,
        calibrated_probability=0.72,
    )

    assert row["display_price"] == 0.71
    assert abs(row["all_in_cost"] - 0.725) < 1e-12
    assert abs(row["all_in_break_even_probability"] - 0.725) < 1e-12
    assert row["margin_probability"] < 0.0
    assert row["gate_status"] == "warn"
    assert row["usable"] is False
    assert any("does not clear execution cost basis" in reason for reason in row["gate_reasons"])


def test_ticket_payout_multiple_adds_known_fee_and_slippage() -> None:
    ledger_mod = load_ledger_module()

    row = make_example_ev_row(
        ledger_mod,
        fee_estimate=0.01,
        slippage_buffer=0.005,
        calibrated_probability=0.755,
    )

    expected_break_even = (1.0 / 1.34) + 0.015
    assert abs(row["all_in_cost"] - expected_break_even) < 1e-12
    assert abs(row["break_even_probability"] - expected_break_even) < 1e-12
    assert row["cost_basis_source"] == "kalshi_payout_multiple_plus_fee_estimate"
    assert row["margin_probability"] < 0.0
    assert row["gate_status"] == "warn"
    assert row["usable"] is False


def test_explicit_all_in_cost_overrides_ticket_payout_when_present() -> None:
    ledger_mod = load_ledger_module()

    row = make_example_ev_row(
        ledger_mod,
        display_price=0.89,
        explicit_all_in_cost=0.90,
        kalshi_payout_multiple=1.11,
        calibrated_probability=0.895,
    )

    assert row["display_price"] == 0.89
    assert abs(row["payout_implied_break_even_probability"] - (1.0 / 1.11)) < 1e-12
    assert row["all_in_break_even_probability"] == 0.90
    assert row["break_even_probability"] == 0.90
    assert row["break_even_source"] == "explicit_all_in_cost"
    assert row["cost_basis_source"] == "explicit_all_in_cost"
    assert row["margin_probability"] < 0.0
    assert row["gate_status"] == "warn"
    assert row["usable"] is False


def test_fee_inclusive_payout_multiple_does_not_require_extra_fee() -> None:
    ledger_mod = load_ledger_module()

    row = make_example_ev_row(
        ledger_mod,
        kalshi_payout_multiple=None,
        all_in_payout_multiple=1.34,
        calibrated_probability=0.76,
    )

    expected_break_even = 1.0 / 1.34
    assert abs(row["break_even_probability"] - expected_break_even) < 1e-12
    assert row["cost_basis_source"] == "fee_inclusive_payout_multiple"
    assert row["break_even_source"] == "fee_inclusive_payout_multiple"
    assert row["payout_multiple_source"] == "kalshi_fee_inclusive_payout"
    assert row["gate_status"] == "pass"
    assert row["usable"] is True


def test_unverified_resolution_rule_blocks_otherwise_positive_row() -> None:
    ledger_mod = load_ledger_module()

    row = make_example_ev_row(
        ledger_mod,
        fee_estimate=0.0,
        calibrated_probability=0.90,
        resolution_rule_status="inferred_unverified_official_terms",
    )

    assert row["margin_probability"] > 0.0
    assert row["source_gate_status"] == "pass"
    assert row["gate_status"] == "blocked"
    assert row["usable"] is False
    assert any(
        "resolution rule is not independently verified" in reason for reason in row["gate_reasons"]
    )


def test_official_terms_index_extracts_local_kalshi_rules(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()
    source = tmp_path / "kalshi_mlb_game_series_test.json"
    source.write_text(
        json.dumps(
            {
                "all_scored": [
                    {
                        "ticker": "KXMLBGAME-26JUN291835CWSBAL-CWS",
                        "event_ticker": "KXMLBGAME-26JUN291835CWSBAL",
                        "rules_primary": "If Chicago WS wins, then the market resolves to Yes.",
                        "rules_secondary": "If the game is cancelled, the market resolves by the official rules.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    terms = ledger_mod.load_official_terms_index(paths=[tmp_path])

    assert set(terms) == {"KXMLBGAME-26JUN291835CWSBAL-CWS"}
    row_terms = terms["KXMLBGAME-26JUN291835CWSBAL-CWS"]
    assert row_terms["event_ticker"] == "KXMLBGAME-26JUN291835CWSBAL"
    assert row_terms["source_artifact"] == str(source.resolve())
    assert row_terms["source_sha256"] == ledger_mod.sha256_file(source)
    assert row_terms["resolution_rule"] == (
        "If Chicago WS wins, then the market resolves to Yes. "
        "If the game is cancelled, the market resolves by the official rules."
    )


def test_resolution_rule_fields_upgrade_exact_ticker_to_verified_terms(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()
    source = tmp_path / "kalshi_mlb_game_series_test.json"
    source.write_text(
        json.dumps(
            {
                "all_scored": [
                    {
                        "ticker": "EXAMPLE-YES",
                        "rules_primary": "If the example happens, then the market resolves to Yes.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    terms = ledger_mod.load_official_terms_index(paths=[tmp_path])

    verified = ledger_mod.resolution_rule_fields(
        contract_ticker="EXAMPLE-YES",
        inferred_rule="inferred",
        inferred_source="inferred_test",
        official_terms=terms,
    )
    inferred = ledger_mod.resolution_rule_fields(
        contract_ticker="MISSING-YES",
        inferred_rule="inferred",
        inferred_source="inferred_test",
        official_terms=terms,
    )

    assert verified["resolution_rule_status"] == "verified_official_terms"
    assert verified["resolution_rule_source"] == "official_kalshi_local_market_snapshot"
    assert verified["resolution_rule_source_artifact"] == str(source.resolve())
    assert verified["resolution_rule_source_sha256"] == ledger_mod.sha256_file(source)
    assert verified["resolution_rule"] == "If the example happens, then the market resolves to Yes."
    assert inferred == {
        "resolution_rule": "inferred",
        "resolution_rule_source": "inferred_test",
        "resolution_rule_status": "inferred_unverified_official_terms",
        "resolution_rule_source_artifact": None,
        "resolution_rule_source_sha256": None,
    }


def test_calibrated_probability_overlay_requires_safe_research_only_file(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()
    safe = tmp_path / "safe.json"
    unsafe = tmp_path / "unsafe.json"
    safe.write_text(
        json.dumps(
            {
                "research_only": True,
                "execution_enabled": False,
                "safety": {
                    "market_execution": False,
                    "account_or_order_paths": False,
                },
                "rows": [
                    {
                        "contract_ticker": "EXAMPLE-YES",
                        "side": "YES",
                        "calibrated_probability": 0.62,
                        "calibrated_probability_source": "unit_test_model",
                        "calibration_status": "validated_calibrated_probability",
                        "probability_uncertainty": 0.03,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    unsafe.write_text(
        json.dumps(
            {
                "research_only": True,
                "execution_enabled": True,
                "safety": {
                    "market_execution": False,
                    "account_or_order_paths": False,
                },
                "rows": [
                    {
                        "contract_ticker": "UNSAFE-YES",
                        "side": "yes",
                        "calibrated_probability": 0.99,
                        "calibration_status": "validated_calibrated_probability",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    overlays = ledger_mod.load_calibrated_probability_index(paths=[tmp_path])

    assert set(overlays) == {("EXAMPLE-YES", "yes")}
    overlay = overlays[("EXAMPLE-YES", "yes")]
    assert overlay["calibrated_probability"] == 0.62
    assert overlay["calibrated_probability_source"] == "unit_test_model"
    assert overlay["calibration_status"] == "validated_calibrated_probability"
    assert overlay["probability_uncertainty"] == 0.03
    assert overlay["source_artifact"] == str(safe.resolve())
    assert overlay["source_sha256"] == ledger_mod.sha256_file(safe)


def test_calibrated_probability_fields_and_gate_reason_adjustment(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()
    source = tmp_path / "probabilities.json"
    source.write_text(
        json.dumps(
            {
                "research_only": True,
                "execution_enabled": False,
                "safety": {
                    "market_execution": False,
                    "account_or_order_paths": False,
                },
                "rows": [
                    {
                        "contract_ticker": "EXAMPLE-YES",
                        "side": "yes",
                        "calibrated_probability": 0.62,
                        "model_name": "review_model",
                        "calibration_status": "review_only_calibrated_probability",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    overlays = ledger_mod.load_calibrated_probability_index(paths=[tmp_path])

    fields = ledger_mod.calibrated_probability_fields(
        contract_ticker="EXAMPLE-YES",
        side="yes",
        calibrated_probabilities=overlays,
    )
    reasons = ledger_mod.probability_adjusted_gate_reasons(
        [
            "probability source is sportsbook no-vig reference, not a calibrated platform model",
            "calibrated contract probability is missing",
            "other blocker",
        ],
        fields,
    )
    missing = ledger_mod.calibrated_probability_fields(
        contract_ticker="MISSING-YES",
        side="yes",
        calibrated_probabilities=overlays,
    )

    assert fields["calibrated_probability"] == 0.62
    assert fields["calibrated_probability_source"] == "local_overlay:review_model"
    assert fields["calibration_status"] == "review_only_calibrated_probability"
    assert fields["source_artifact"] == str(source.resolve())
    assert reasons == [
        "other blocker",
        "calibrated probability status is review_only_calibrated_probability",
    ]
    assert missing["calibrated_probability"] is None
    assert missing["calibrated_probability_source"] == "missing_calibrated_contract_probability"


def test_contract_mapping_overlay_requires_safe_exact_verified_rows(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()
    safe = tmp_path / "safe-mapping.json"
    unsafe = tmp_path / "unsafe-mapping.json"
    safe.write_text(
        json.dumps(
            {
                "research_only": True,
                "execution_enabled": False,
                "safety": {
                    "market_execution": False,
                    "account_or_order_paths": False,
                },
                "rows": [
                    {
                        "source_repo_id": "nfl_quant_glm51_greenfield",
                        "contract_ticker": "KXNFLGAME-26SEP09NESEA-SEA",
                        "side": "yes",
                        "mapping_status": "verified_contract_mapping",
                        "resolution_rule_status": "verified_official_terms",
                        "resolution_rule": "If Seattle wins, then the market resolves to Yes.",
                        "executable_price": 0.4,
                        "timing_status": "clean",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    unsafe.write_text(
        json.dumps(
            {
                "research_only": True,
                "execution_enabled": True,
                "safety": {
                    "market_execution": False,
                    "account_or_order_paths": False,
                },
                "rows": [
                    {
                        "source_repo_id": "nfl_quant_glm51_greenfield",
                        "contract_ticker": "UNSAFE-YES",
                        "side": "yes",
                        "mapping_status": "verified_contract_mapping",
                        "resolution_rule_status": "verified_official_terms",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    mappings = ledger_mod.load_contract_mapping_index(paths=[tmp_path])

    assert set(mappings) == {"nfl_quant_glm51_greenfield"}
    row = mappings["nfl_quant_glm51_greenfield"][0]
    assert row["contract_ticker"] == "KXNFLGAME-26SEP09NESEA-SEA"
    assert row["side"] == "yes"
    assert row["source_artifact"] == str(safe.resolve())
    assert row["source_sha256"] == ledger_mod.sha256_file(safe)
    assert "UNSAFE-YES" not in json.dumps(mappings)


def test_contract_mapping_overlay_dedupes_same_repo_ticker_side(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()
    ticker = "KXNFLGAME-26SEP09NESEA-SEA"
    safety = {
        "market_execution": False,
        "account_or_order_paths": False,
    }
    for name, price in (("a-first.json", 0.4), ("b-latest.json", 0.42)):
        (tmp_path / name).write_text(
            json.dumps(
                {
                    "research_only": True,
                    "execution_enabled": False,
                    "safety": safety,
                    "rows": [
                        {
                            "source_repo_id": "nfl_quant_glm51_greenfield",
                            "contract_ticker": ticker,
                            "event_ticker": "KXNFLGAME-26SEP09NESEA",
                            "side": "yes",
                            "mapping_status": "verified_contract_mapping",
                            "resolution_rule_status": "verified_official_terms",
                            "resolution_rule": "If Seattle wins, then the market resolves to Yes.",
                            "executable_price": price,
                            "timing_status": "clean",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    mappings = ledger_mod.load_contract_mapping_index(paths=[tmp_path])

    assert len(mappings["nfl_quant_glm51_greenfield"]) == 1
    assert mappings["nfl_quant_glm51_greenfield"][0]["contract_ticker"] == ticker
    assert mappings["nfl_quant_glm51_greenfield"][0]["executable_price"] == 0.42
    assert mappings["nfl_quant_glm51_greenfield"][0]["source_artifact"].endswith("b-latest.json")


def test_contract_mapping_and_probability_overlays_can_create_usable_row(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()
    mapping = tmp_path / "mapping.json"
    probability = tmp_path / "probability.json"
    ticker = "KXNFLGAME-26SEP09NESEA-SEA"
    safety = {
        "market_execution": False,
        "account_or_order_paths": False,
    }
    mapping.write_text(
        json.dumps(
            {
                "research_only": True,
                "execution_enabled": False,
                "safety": safety,
                "rows": [
                    {
                        "source_repo_id": "nfl_quant_glm51_greenfield",
                        "contract_ticker": ticker,
                        "event_ticker": "KXNFLGAME-26SEP09NESEA",
                        "side": "yes",
                        "selection": "SEA",
                        "market_type": "nfl_game_moneyline",
                        "title": "Seattle to beat New England",
                        "mapping_status": "verified_contract_mapping",
                        "mapping_confidence": "operator_verified",
                        "resolution_rule_status": "verified_official_terms",
                        "resolution_rule": "If Seattle wins, then the market resolves to Yes.",
                        "resolution_rule_source": "operator_verified_local_kalshi_snapshot",
                        "executable_price": 0.4,
                        "timing_status": "clean",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    probability.write_text(
        json.dumps(
            {
                "research_only": True,
                "execution_enabled": False,
                "safety": safety,
                "rows": [
                    {
                        "contract_ticker": ticker,
                        "side": "yes",
                        "calibrated_probability": 0.6,
                        "calibrated_probability_source": "unit_test_platt_model",
                        "calibration_status": "validated_calibrated_probability",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    ledger = ledger_mod.build_ledger(
        max_rows_per_repo=1,
        generated_utc="2026-07-01T00:00:00Z",
        calibrated_probability_paths=[tmp_path],
        contract_mapping_paths=[tmp_path],
    )
    row = next(item for item in ledger["rows"] if item["contract_ticker"] == ticker)
    nfl_feed = next(
        feed for feed in ledger["repo_feeds"] if feed["repo_id"] == "nfl_quant_glm51_greenfield"
    )

    assert ledger["summary"]["contract_mapping_overlay_row_count"] == 1
    assert ledger["summary"]["calibrated_probability_overlay_row_count"] == 1
    assert row["source_repo_id"] == "nfl_quant_glm51_greenfield"
    assert row["resolution_rule_status"] == "verified_official_terms"
    assert row["calibration_status"] == "validated_calibrated_probability"
    assert row["calibrated_probability"] == 0.6
    assert row["all_in_break_even_probability"] < 0.6
    assert row["margin_probability"] > 0.0
    assert row["gate_status"] == "pass"
    assert row["usable"] is True
    assert (
        nfl_feed["ev_readiness"]["contract_mapping_status"] == "exact_kalshi_contract_rows_present"
    )
    assert nfl_feed["ev_readiness"]["calibrated_probability_status"] == (
        "calibrated_contract_probabilities_present"
    )


def test_overlay_preflight_reports_missing_inputs(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()

    report = ledger_mod.build_overlay_preflight(
        generated_utc="2026-07-01T00:00:00Z",
        calibrated_probability_paths=[tmp_path / "probabilities"],
        contract_mapping_paths=[tmp_path / "mappings"],
    )

    assert report["status"] == "overlay_preflight_blocked_missing_or_unjoined_inputs"
    assert report["summary"]["contract_mapping_file_count"] == 0
    assert report["summary"]["calibrated_probability_file_count"] == 0
    assert report["summary"]["exact_join_row_count"] == 0
    assert report["summary"]["usable_overlay_ev_row_count"] == 0
    assert report["safety"]["market_execution"] is False
    assert "contract-mapping overlay" in report["next_action"]


def test_overlay_preflight_reports_joined_usable_rows(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()
    mapping_dir = tmp_path / "mappings"
    probability_dir = tmp_path / "probabilities"
    mapping_dir.mkdir()
    probability_dir.mkdir()
    ticker = "KXNFLGAME-26SEP09NESEA-SEA"
    safety = {
        "market_execution": False,
        "account_or_order_paths": False,
    }
    (mapping_dir / "mapping.json").write_text(
        json.dumps(
            {
                "research_only": True,
                "execution_enabled": False,
                "safety": safety,
                "rows": [
                    {
                        "source_repo_id": "nfl_quant_glm51_greenfield",
                        "contract_ticker": ticker,
                        "side": "yes",
                        "mapping_status": "verified_contract_mapping",
                        "resolution_rule_status": "verified_official_terms",
                        "resolution_rule": "If Seattle wins, then the market resolves to Yes.",
                        "executable_price": 0.4,
                        "timing_status": "clean",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (probability_dir / "probability.json").write_text(
        json.dumps(
            {
                "research_only": True,
                "execution_enabled": False,
                "safety": safety,
                "rows": [
                    {
                        "contract_ticker": ticker,
                        "side": "yes",
                        "calibrated_probability": 0.6,
                        "calibration_status": "validated_calibrated_probability",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = ledger_mod.build_overlay_preflight(
        generated_utc="2026-07-01T00:00:00Z",
        calibrated_probability_paths=[probability_dir],
        contract_mapping_paths=[mapping_dir],
    )

    assert report["status"] == "overlay_preflight_usable_ev_rows_present"
    assert report["summary"]["contract_mapping_file_count"] == 1
    assert report["summary"]["calibrated_probability_file_count"] == 1
    assert report["summary"]["exact_join_row_count"] == 1
    assert report["summary"]["usable_overlay_ev_row_count"] == 1
    assert report["joined_keys"] == [{"contract_ticker": ticker, "side": "yes"}]
    assert "Review the usable overlay EV rows" in report["next_action"]


def test_calibration_work_order_queues_safe_probability_assignments(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()
    fixture = make_ev_ledger_fixture(tmp_path)
    ledger_mod.OFFICIAL_TERMS_SNAPSHOT_PATHS = tuple(fixture["official_terms_paths"])

    report = ledger_mod.build_calibration_work_order(
        generated_utc="2026-07-01T00:00:00Z",
        active_universe_path=fixture["active_universe_path"],
        max_rows_per_repo=500,
        limit=5,
        calibrated_probability_paths=fixture["calibrated_probability_paths"],
        contract_mapping_paths=fixture["contract_mapping_paths"],
    )

    assert report["status"] == "calibration_work_order_ready_source_gated"
    assert report["summary"]["selected_row_count"] == 5
    assert report["summary"]["candidate_row_count"] >= 5
    assert report["summary"]["direct_pass_ready_candidate_count"] == 0
    assert report["summary"]["source_gated_candidate_count"] >= 5
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["safety"]["market_execution"] is False
    assert report["probability_overlay_template"]["research_only"] is True
    assert report["probability_overlay_template"]["execution_enabled"] is False
    assert len(report["probability_overlay_template"]["rows"]) == 5
    for row, template in zip(
        report["rows"], report["probability_overlay_template"]["rows"], strict=True
    ):
        assert row["contract_ticker"]
        assert row["side"] == "yes"
        assert row["resolution_rule_status"] == "verified_official_terms"
        assert row["all_in_break_even_probability"] is not None
        assert row["source_gate_status"] == "blocked"
        assert "temporal_mismatch" not in str(row["timing_status"]).lower()
        assert (
            "calibrated contract probability is missing" not in row["non_probability_gate_reasons"]
        )
        assert template["contract_ticker"] == row["contract_ticker"]
        assert template["side"] == row["side"]
        assert template["calibrated_probability"] is None
        assert template["calibration_status"] == "validated_calibrated_probability"
    assert "probabilities alone will not create usable EV rows" in report["next_action"]


def test_calibration_work_order_writer_emits_template(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()
    ledger_mod.MACRO_DIR = tmp_path / "macro"
    report = ledger_mod.build_calibration_work_order(
        generated_utc="2026-07-01T00:00:00Z",
        max_rows_per_repo=10,
        limit=2,
    )

    paths = ledger_mod.write_calibration_work_order(report, out_dir=tmp_path)
    template = json.loads(Path(paths["template_path"]).read_text(encoding="utf-8"))
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["template_path"]).exists()
    assert template == report["probability_overlay_template"]
    assert "Kalshi EV Calibration Work Order" in markdown
    assert "Selected Contracts" in markdown


def test_contract_mapping_work_order_queues_nfl_model_rows(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()
    fair_line = tmp_path / "fair-line-review.json"
    fair_line.write_text(
        json.dumps(
            {
                "research_only": True,
                "safety": {
                    "research_only": True,
                    "provider_api_calls": False,
                    "paid_calls": False,
                    "database_writes": False,
                    "market_execution": False,
                    "account_or_order_paths": False,
                },
                "rows": [
                    {
                        "season": 2026,
                        "week": 1,
                        "game": "NE@SEA",
                        "home_team": "SEA",
                        "away_team": "NE",
                        "model_prob_home": 0.69,
                        "model_prob_away": 0.31,
                        "market_prob_home": 0.64,
                        "model_prob_source": "profile:selection_proposal_elo",
                        "model_prob_detail": "profile_elo_only",
                        "model_calibration_active": True,
                        "model_calibration_source": "platt_logit",
                        "model_calibration_detail": "train_rows=749",
                    },
                    {
                        "season": 2026,
                        "week": 1,
                        "game": "CHI@CAR",
                        "home_team": "CAR",
                        "away_team": "CHI",
                        "model_prob_home": 0.40,
                        "model_prob_away": 0.60,
                        "market_prob_home": 0.44,
                        "model_prob_source": "profile:selection_proposal_elo",
                        "model_prob_detail": "profile_elo_only",
                        "model_calibration_active": True,
                        "model_calibration_source": "platt_logit",
                        "model_calibration_detail": "train_rows=749",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    report = ledger_mod.build_contract_mapping_work_order(
        generated_utc="2026-07-01T00:00:00Z",
        limit=3,
        nfl_fair_line_path=fair_line,
        nfl_validation_paths=[],
    )

    assert report["status"] == "contract_mapping_work_order_ready"
    assert report["summary"]["model_row_count"] == 2
    assert report["summary"]["selected_contract_side_count"] == 3
    assert report["summary"]["source_repo_id"] == "nfl_quant_glm51_greenfield"
    assert report["safety"]["market_execution"] is False
    assert report["contract_mapping_overlay_template"]["template_only"] is True
    assert report["calibrated_probability_overlay_template"]["template_only"] is True
    assert len(report["contract_mapping_overlay_template"]["rows"]) == 3
    assert len(report["calibrated_probability_overlay_template"]["rows"]) == 3
    first_mapping = report["contract_mapping_overlay_template"]["rows"][0]
    first_probability = report["calibrated_probability_overlay_template"]["rows"][0]
    assert first_mapping["mapping_status"].startswith("TODO:")
    assert first_probability["calibration_status"].startswith("TODO:")
    assert first_probability["calibrated_probability"] is not None
    assert "exact Kalshi ticker" in report["next_action"]


def test_contract_mapping_work_order_writer_emits_templates(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()
    ledger_mod.MACRO_DIR = tmp_path / "macro"
    fair_line = tmp_path / "fair-line-review.json"
    fair_line.write_text(
        json.dumps(
            {
                "research_only": True,
                "safety": {
                    "research_only": True,
                    "provider_api_calls": False,
                    "paid_calls": False,
                    "database_writes": False,
                    "market_execution": False,
                    "account_or_order_paths": False,
                },
                "rows": [
                    {
                        "season": 2026,
                        "week": 1,
                        "game": "NE@SEA",
                        "home_team": "SEA",
                        "away_team": "NE",
                        "model_prob_home": 0.69,
                        "model_prob_away": 0.31,
                        "market_prob_home": 0.64,
                        "model_prob_source": "profile:selection_proposal_elo",
                        "model_calibration_active": True,
                        "model_calibration_source": "platt_logit",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report = ledger_mod.build_contract_mapping_work_order(
        generated_utc="2026-07-01T00:00:00Z",
        limit=2,
        nfl_fair_line_path=fair_line,
        nfl_validation_paths=[],
    )

    paths = ledger_mod.write_contract_mapping_work_order(report, out_dir=tmp_path)
    mapping_template = json.loads(Path(paths["mapping_template_path"]).read_text(encoding="utf-8"))
    probability_template = json.loads(
        Path(paths["probability_template_path"]).read_text(encoding="utf-8")
    )
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")

    assert Path(paths["json_path"]).exists()
    assert mapping_template == report["contract_mapping_overlay_template"]
    assert probability_template == report["calibrated_probability_overlay_template"]
    assert "Kalshi EV Contract Mapping Work Order" in markdown
    assert "Selected NFL Rows" in markdown


def test_payout_multiple_parser_accepts_ticket_formats() -> None:
    ledger_mod = load_ledger_module()

    assert ledger_mod.extract_kalshi_payout_multiple({"ticket_payout_multiple": "1.34x"}) == 1.34
    assert ledger_mod.extract_kalshi_payout_multiple({"displayed_payout_multiple": "134%"}) == 1.34
    assert ledger_mod.extract_kalshi_payout_multiple({"kalshi_payout_multiple": 1.34}) == 1.34
    assert (
        ledger_mod.extract_all_in_payout_multiple({"fee_inclusive_payout_multiple": "1.34x"})
        == 1.34
    )
    assert ledger_mod.extract_kalshi_payout_multiple({"displayed_payout_multiple": "71%"}) is None
    assert ledger_mod.extract_kalshi_payout_multiple({"payout_multiple": 0.71}) is None


def test_atp_match_snapshot_routes_exact_contract_rows_but_blocks_usability(tmp_path: Path) -> None:
    ledger_mod = load_ledger_module()

    ledger = build_fixture_ledger(ledger_mod, tmp_path)
    atp = next(feed for feed in ledger["repo_feeds"] if feed["repo_id"] == "atp-oracle")
    rows = [row for row in ledger["rows"] if row["source_repo_id"] == "atp-oracle"]

    assert atp["status"] == "atp_kalshi_match_snapshot_rows_blocked_not_usable"
    assert atp["row_count"] == 2
    assert {row["contract_ticker"] for row in rows} == {
        "KXATPMATCH-26JUL05ALCBER-ALC",
        "KXATPMATCH-26JUL05ALCBER-BER",
    }
    assert all(row["market_type"] == "sports_tennis_kalshi_match_snapshot" for row in rows)
    assert all(row["side"] == "yes" for row in rows)
    assert all(row["usable"] is False for row in rows)
    assert all(row["gate_status"] == "blocked" for row in rows)
    assert all(
        "ATP match snapshot is market observation input, not a model probability"
        in row["gate_reasons"]
        for row in rows
    )
    assert atp["ev_readiness"]["contract_mapping_status"] == "exact_kalshi_contract_rows_present"
    assert (
        atp["ev_readiness"]["calibrated_probability_status"]
        == "missing_calibrated_contract_probability"
    )


def test_current_sports_feature_packet_routes_mlb_game_rows_but_blocks_usability(
    tmp_path: Path,
) -> None:
    ledger_mod = load_ledger_module()

    ledger = build_fixture_ledger(ledger_mod, tmp_path)
    rows = [
        row
        for row in ledger["rows"]
        if row["market_type"] == "sports_baseball_current_game_feature_packet"
    ]

    assert len(rows) == 1
    row = rows[0]
    assert row["source_repo_id"] == "predmarket-alpha"
    assert row["contract_ticker"] == "KXMLBGAME-26JUL041910NYYBOS-NYY"
    assert row["side"] == "yes"
    assert row["display_price"] == 0.55
    assert row["reference_probability"] == 0.57
    assert (
        row["reference_probability_source"]
        == "sports_proxy_strength_reference_not_calibrated_probability"
    )
    assert row["gate_status"] == "blocked"
    assert row["usable"] is False
    assert (
        "sports feature packet is feature-only and not a validated probability overlay"
        in row["gate_reasons"]
    )


def test_makefile_exposes_kalshi_ev_ledger_target() -> None:
    content = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-ev-ledger" in content
    assert "scripts/kalshi_contract_ev_ledger.py" in content
    assert "KALSHI_EV_LEDGER_MAX_ROWS_PER_REPO" in content
    assert "kalshi-ev-calibration-work-order" in content
    assert "kalshi-ev-contract-mapping-work-order" in content
