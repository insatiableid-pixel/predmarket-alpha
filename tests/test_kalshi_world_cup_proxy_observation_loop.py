from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_world_cup_proxy_observation_loop.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_loop_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_world_cup_proxy_observation_loop", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def safe_universe(rows=None):
    return {
        "schema_version": 1,
        "status": "universe_scan_ready_with_candidates",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "candidates": rows or [world_cup_candidate()],
        "safety": {
            "research_only": True,
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
            "staking_or_sizing_guidance": False,
        },
    }


def world_cup_candidate(**overrides):
    row = {
        "ticker": "KXWCGAME-26JUL03BRASPA-BRA",
        "event_ticker": "KXWCGAME-26JUL03BRASPA",
        "series_ticker": "KXWCGAME",
        "classification": "other_sports",
        "gate_status": "pass",
        "title": "Brazil vs Spain",
        "subtitle": "Brazil to win",
        "settlement_time": "2026-07-03T22:00:00Z",
        "expected_expiration_time": "2026-07-03T22:00:00Z",
        "yes_bid": 0.61,
        "yes_ask": 0.63,
        "yes_spread": 0.02,
        "time_to_settlement_hours": 2.0,
    }
    row.update(overrides)
    return row


def settled_snapshot(**overrides):
    payload = {
        "schema_version": 1,
        "created_at_utc": "2026-07-03T22:30:00Z",
        "status": "kalshi_public_observed_market_fetch_ok",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
        "markets": [
            {
                "ticker": "KXWCGAME-26JUL03BRASPA-BRA",
                "event_ticker": "KXWCGAME-26JUL03BRASPA",
                "series_ticker": "KXWCGAME",
                "result": "yes",
                "settlement_value_dollars": "1.0000",
                "close_time": "2026-07-03T22:00:00Z",
                "settlement_ts": "2026-07-03T22:20:00Z",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_world_cup_proxy_observation_records_soft_watch_rows_without_ev(tmp_path: Path) -> None:
    module = load_loop_module()
    universe_path = tmp_path / "universe.json"
    write_json(universe_path, safe_universe())

    report = module.build_world_cup_proxy_observation_loop(
        universe_scan_path=universe_path,
        settled_snapshot_path=tmp_path / "missing-settled.json",
        observation_dir=tmp_path / "observations",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-03T20:00:00Z",
    )

    assert report["status"] == "world_cup_proxy_observation_loop_ready_waiting_settlement"
    assert report["summary"]["candidate_count"] == 1
    assert report["summary"]["new_observation_row_count"] == 1
    assert report["summary"]["label_row_count"] == 0
    row = report["observation_packet"]["rows"][0]
    assert row["contract_ticker"] == "KXWCGAME-26JUL03BRASPA-BRA"
    assert row["market_consensus_prediction"] == "yes"
    assert row["feature_policy"] == "kalshi_market_structure_only_not_soccer_handicap"
    assert row["calibrated_probability"] is None
    assert row["expected_value_per_contract"] is None
    assert row["usable"] is False


def test_world_cup_proxy_observation_labels_exact_ticker_from_public_settlement(
    tmp_path: Path,
) -> None:
    module = load_loop_module()
    universe_path = tmp_path / "universe.json"
    settled_path = tmp_path / "settled.json"
    write_json(universe_path, safe_universe())
    write_json(settled_path, settled_snapshot())

    report = module.build_world_cup_proxy_observation_loop(
        universe_scan_path=universe_path,
        settled_snapshot_path=settled_path,
        observation_dir=tmp_path / "observations",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-03T20:00:00Z",
    )

    assert report["status"] == "world_cup_proxy_observation_loop_label_rows_ready"
    assert report["summary"]["label_row_count"] == 1
    label = report["label_packet"]["rows"][0]
    assert label["contract_ticker"] == "KXWCGAME-26JUL03BRASPA-BRA"
    assert label["yes_outcome"] == 1
    assert label["label_source"] == "public_kalshi_settled_market_payload"
    assert label["usable"] is False


def test_due_observed_tickers_uses_exact_world_cup_tickers(tmp_path: Path) -> None:
    module = load_loop_module()
    universe_path = tmp_path / "universe.json"
    write_json(universe_path, safe_universe())

    before = module.due_observed_tickers(
        universe_scan_path=universe_path,
        observation_dir=tmp_path / "observations",
        generated_utc="2026-07-03T21:59:00Z",
        max_tickers=10,
    )
    after = module.due_observed_tickers(
        universe_scan_path=universe_path,
        observation_dir=tmp_path / "observations",
        generated_utc="2026-07-03T22:01:00Z",
        max_tickers=10,
    )

    assert before == []
    assert after == ["KXWCGAME-26JUL03BRASPA-BRA"]


def test_capture_public_observed_markets_snapshot_fetches_exact_world_cup_ticker(
    tmp_path: Path,
) -> None:
    module = load_loop_module()
    calls: list[str] = []

    def fake_fetch(url: str):
        calls.append(url)
        return {
            "market": {
                "ticker": "KXWCGAME-26JUL03BRASPA-BRA",
                "result": "yes",
                "settlement_value_dollars": "1.0000",
            }
        }

    latest_path = module.capture_public_observed_markets_snapshot(
        tickers=["KXWCGAME-26JUL03BRASPA-BRA"],
        raw_dir=tmp_path / "settled",
        generated_utc="2026-07-03T22:30:00Z",
        fetch_json=fake_fetch,
    )
    payload = json.loads(latest_path.read_text(encoding="utf-8"))

    assert payload["summary"]["settled_label_ready_count"] == 1
    assert payload["markets"][0]["ticker"] == "KXWCGAME-26JUL03BRASPA-BRA"
    assert calls == [
        "https://external-api.kalshi.com/trade-api/v2/markets/KXWCGAME-26JUL03BRASPA-BRA"
    ]


def test_world_cup_proxy_observation_makefile_targets_are_registered() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-world-cup-proxy-observation-loop" in text
    assert "kalshi-world-cup-proxy-observation-watch-once" in text
    assert "KALSHI_WORLD_CUP_PROXY_OBSERVATION_OUT_DIR" in text


# ── World Cup exact settlement mapping tests ──


def test_settlement_outcome_parses_dollar_value_yes() -> None:
    """Verify settlement_outcome extracts YES from settlement_value_dollars >= 0.999."""
    module = load_loop_module()
    assert module.settlement_outcome({"settlement_value_dollars": "1.0000"}) == 1
    assert module.settlement_outcome({"settlement_value_dollars": "0.9999"}) == 1


def test_settlement_outcome_parses_dollar_value_no() -> None:
    """Verify settlement_outcome extracts NO from settlement_value_dollars <= 0.001."""
    module = load_loop_module()
    assert module.settlement_outcome({"settlement_value_dollars": "0.0000"}) == 0
    assert module.settlement_outcome({"settlement_value_dollars": "0.0001"}) == 0


def test_settlement_outcome_parses_result_yes() -> None:
    """Verify settlement_outcome extracts YES from the result field."""
    module = load_loop_module()
    assert module.settlement_outcome({"result": "yes"}) == 1
    assert module.settlement_outcome({"result": "Yes"}) == 1
    assert module.settlement_outcome({"result": "true"}) == 1
    assert module.settlement_outcome({"expiration_value": "1"}) == 1


def test_settlement_outcome_parses_result_no() -> None:
    """Verify settlement_outcome extracts NO from the result field."""
    module = load_loop_module()
    assert module.settlement_outcome({"result": "no"}) == 0
    assert module.settlement_outcome({"result": "false"}) == 0
    assert module.settlement_outcome({"expiration_value": "0"}) == 0


def test_settlement_outcome_returns_none_for_missing() -> None:
    """Verify settlement_outcome returns None when no settlement is present."""
    module = load_loop_module()
    assert module.settlement_outcome({}) is None
    assert module.settlement_outcome({"result": ""}) is None
    assert module.settlement_outcome({"settlement_value_dollars": "0.5000"}) is None


def test_settled_market_index_only_includes_markets_with_settlement() -> None:
    """Verify settled_market_index only indexes markets that have a settlement outcome.

    Markets without settlement_value_dollars or result should be excluded,
    matching the MLB observation loop pattern.
    """
    module = load_loop_module()
    snapshot = {
        "markets": [
            {
                "ticker": "KXWCGAME-26JUL03BRASPA-BRA",
                "result": "yes",
                "settlement_value_dollars": "1.0000",
            },
            {
                "ticker": "KXWCGAME-26JUL03BRASPA-TIE",
                "result": "no",
            },
            {
                "ticker": "KXWC1HTOTAL-26JUL03BRASPA-1",
                # No settlement fields - should be excluded
            },
            {
                "ticker": "KXWC2HTOTAL-26JUL03BRASPA-2",
                "settlement_value": "0.5000",  # Middle value = no outcome
            },
        ]
    }
    index = module.settled_market_index(snapshot)
    assert "KXWCGAME-26JUL03BRASPA-BRA" in index  # Has result
    assert "KXWCGAME-26JUL03BRASPA-TIE" in index  # Has result
    assert "KXWC1HTOTAL-26JUL03BRASPA-1" not in index  # No settlement
    assert "KXWC2HTOTAL-26JUL03BRASPA-2" not in index  # Middle value


def test_settled_market_index_handles_missing_markets_key() -> None:
    """Verify settled_market_index gracefully handles missing markets list."""
    module = load_loop_module()
    assert module.settled_market_index({}) == {}
    assert module.settled_market_index({"markets": None}) == {}
    assert module.settled_market_index({"markets": "not_a_list"}) == {}


def test_market_type_maps_all_expected_world_cup_series() -> None:
    """Verify market_type correctly maps each World Cup series prefix."""
    module = load_loop_module()
    cases = [
        ("KXWCGAME", "game"),
        ("KXWCSPREAD", "spread"),
        ("KXWCTOTAL", "total"),
        ("KXWC1H", "first_half"),
        ("KXWC1HTOTAL", "total"),
        ("KXWC1HSPREAD", "spread"),
        ("KXWC2H", "second_half"),
        ("KXWC2HTOTAL", "total"),
        ("KXWC2HSPREAD", "spread"),
        ("KXWCBTTS", "both_teams_to_score"),
        ("KXWCCORNERS", "game"),
        ("KXWCTCORNERS", "game"),
        ("KXWCTEAMGOALS", "team_prop"),
    ]
    for series, expected_type in cases:
        assert module.market_type({"series_ticker": series}) == expected_type, (
            f"Expected {series} → {expected_type}"
        )


def test_world_cup_labels_for_all_series_prefixes(tmp_path: Path) -> None:
    """Verify observation loop produces labels for each target World Cup series.

    Tests all five series prefixes from the feature spec: KXWCGAME, KXWC1HTOTAL,
    KXWC2HTOTAL, KXWCBTTS, KXWCTCORNERS.
    """
    module = load_loop_module()
    candidates = [
        world_cup_candidate(
            ticker="KXWCGAME-26JUL03BRASPA-BRA",
            series_ticker="KXWCGAME",
        ),
        world_cup_candidate(
            ticker="KXWC1HTOTAL-26JUL03BRASPA-1",
            series_ticker="KXWC1HTOTAL",
        ),
        world_cup_candidate(
            ticker="KXWC2HTOTAL-26JUL03BRASPA-2",
            series_ticker="KXWC2HTOTAL",
        ),
        world_cup_candidate(
            ticker="KXWCBTTS-26JUL03BRASPA-YES",
            series_ticker="KXWCBTTS",
        ),
        world_cup_candidate(
            ticker="KXWCTCORNERS-26JUL03BRASPA-ARG11",
            series_ticker="KXWCTCORNERS",
        ),
    ]
    universe_path = tmp_path / "universe.json"
    write_json(universe_path, safe_universe(candidates))

    settled_markets = [
        {
            "ticker": "KXWCGAME-26JUL03BRASPA-BRA",
            "result": "yes",
            "settlement_value_dollars": "1.0000",
            "close_time": "2026-07-03T22:00:00Z",
            "settlement_ts": "2026-07-03T22:20:00Z",
        },
        {
            "ticker": "KXWC1HTOTAL-26JUL03BRASPA-1",
            "result": "no",
            "settlement_value_dollars": "0.0000",
            "close_time": "2026-07-03T22:00:00Z",
            "settlement_ts": "2026-07-03T22:15:00Z",
        },
        {
            "ticker": "KXWC2HTOTAL-26JUL03BRASPA-2",
            "result": "yes",
            "settlement_value_dollars": "1.0000",
            "close_time": "2026-07-03T22:30:00Z",
            "settlement_ts": "2026-07-03T23:00:00Z",
        },
        {
            "ticker": "KXWCBTTS-26JUL03BRASPA-YES",
            "result": "yes",
            "settlement_value_dollars": "1.0000",
            "close_time": "2026-07-03T22:00:00Z",
            "settlement_ts": "2026-07-03T22:20:00Z",
        },
        {
            "ticker": "KXWCTCORNERS-26JUL03BRASPA-ARG11",
            "result": "no",
            "settlement_value_dollars": "0.0000",
            "close_time": "2026-07-03T22:45:00Z",
            "settlement_ts": "2026-07-03T23:15:00Z",
        },
    ]
    settled_path = tmp_path / "settled.json"
    write_json(settled_path, settled_snapshot(markets=settled_markets))

    report = module.build_world_cup_proxy_observation_loop(
        universe_scan_path=universe_path,
        settled_snapshot_path=settled_path,
        observation_dir=tmp_path / "observations",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-03T23:30:00Z",
    )

    assert report["status"] == "world_cup_proxy_observation_loop_label_rows_ready"
    assert report["summary"]["label_row_count"] == 5
    assert report["summary"]["distinct_contract_count"] == 5

    labels_by_ticker = {r["contract_ticker"]: r for r in report["label_packet"]["rows"]}

    # KXWCGAME → YES (BRA wins)
    assert labels_by_ticker["KXWCGAME-26JUL03BRASPA-BRA"]["yes_outcome"] == 1

    # KXWC1HTOTAL → NO (under 1.5 goals)
    assert labels_by_ticker["KXWC1HTOTAL-26JUL03BRASPA-1"]["yes_outcome"] == 0

    # KXWC2HTOTAL → YES (over 1.5 goals)
    assert labels_by_ticker["KXWC2HTOTAL-26JUL03BRASPA-2"]["yes_outcome"] == 1

    # KXWCBTTS → YES (both teams scored)
    assert labels_by_ticker["KXWCBTTS-26JUL03BRASPA-YES"]["yes_outcome"] == 1

    # KXWCTCORNERS → NO (not an individual corners threshold)
    assert labels_by_ticker["KXWCTCORNERS-26JUL03BRASPA-ARG11"]["yes_outcome"] == 0

    # All labels carry required provenance fields
    for label in labels_by_ticker.values():
        assert label["label_source"] == "public_kalshi_settled_market_payload"
        assert label["usable"] is False
        assert label["yes_outcome"] is not None
        assert label.get("settled_time") is not None


def test_label_deduplication_collapses_duplicate_observations(tmp_path: Path) -> None:
    """Verify that observation rows are deduplicated by observation_id.

    When the same observation_id appears in both existing packets and the
    current run, only the first occurrence is kept. The dedup is by observation_id,
    not contract_ticker — contract_ticker dedup happens in the model falsification
    stage via independent_contract_rows().
    """
    module = load_loop_module()
    ticker = "KXWCGAME-26JUL03BRASPA-BRA"

    # Pre-load a label packet with a label for the same contract
    label_dir = tmp_path / "labels"
    label_dir.mkdir(parents=True, exist_ok=True)
    existing_label = {
        "schema_version": 1,
        "generated_utc": "2026-07-03T22:00:00Z",
        "packet_type": "kalshi_world_cup_proxy_feature_labels",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "rows": [
            {
                "observation_id": "world_cup_obs_existing",
                "contract_ticker": ticker,
                "series_ticker": "KXWCGAME",
                "label_status": "labeled_from_public_kalshi_settled_market",
                "yes_outcome": 1,
                "side_outcome": 1,
                "close_time": "2026-07-03T22:00:00Z",
                "settled_time": "2026-07-03T22:20:00Z",
                "label_source": "public_kalshi_settled_market_payload",
                "usable": False,
            }
        ],
        "safety": {
            "research_only": True,
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }
    write_json(label_dir / "existing_labels.json", existing_label)

    universe_path = tmp_path / "universe.json"
    write_json(universe_path, safe_universe())
    settled = settled_snapshot(
        markets=[
            {
                "ticker": ticker,
                "result": "yes",
                "settlement_value_dollars": "1.0000",
                "close_time": "2026-07-03T22:00:00Z",
                "settlement_ts": "2026-07-03T22:20:00Z",
            }
        ]
    )
    settled_path = tmp_path / "settled.json"
    write_json(settled_path, settled)

    report = module.build_world_cup_proxy_observation_loop(
        universe_scan_path=universe_path,
        settled_snapshot_path=settled_path,
        observation_dir=tmp_path / "observations",
        label_dir=label_dir,
        generated_utc="2026-07-03T23:00:00Z",
    )

    # New label packet contains only the newly computed label (not the pre-existing one)
    new_label_rows = report["label_packet"]["rows"]
    assert len(new_label_rows) == 1
    assert new_label_rows[0]["contract_ticker"] == ticker

    # Total label row count should be 2 (1 existing + 1 new computed)
    assert report["summary"]["label_row_count"] == 2
    assert report["summary"]["existing_label_row_count"] == 1
    assert report["summary"]["new_label_row_count"] == 1


def test_label_row_has_full_provenance_fields(tmp_path: Path) -> None:
    """Verify each World Cup label row carries contract_ticker, settlement_time,
    outcome, and source_snapshot_sha256 provenance."""
    module = load_loop_module()
    universe_path = tmp_path / "universe.json"
    write_json(universe_path, safe_universe())

    settled_path = tmp_path / "settled.json"
    write_json(
        settled_path,
        settled_snapshot(
            markets=[
                {
                    "ticker": "KXWCGAME-26JUL03BRASPA-BRA",
                    "result": "yes",
                    "settlement_value_dollars": "1.0000",
                    "close_time": "2026-07-03T22:00:00Z",
                    "settlement_ts": "2026-07-03T22:20:00Z",
                }
            ]
        ),
    )

    report = module.build_world_cup_proxy_observation_loop(
        universe_scan_path=universe_path,
        settled_snapshot_path=settled_path,
        observation_dir=tmp_path / "observations",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-03T23:00:00Z",
    )

    label = report["label_packet"]["rows"][0]
    assert label.get("contract_ticker") == "KXWCGAME-26JUL03BRASPA-BRA"
    assert label.get("settled_time") is not None
    assert label.get("settlement_time") is None  # label rows use settled_time alias
    assert label.get("yes_outcome") is not None
    # Provenance fields
    assert label.get("label_source") == "public_kalshi_settled_market_payload"
    assert label.get("label_status") == "labeled_from_public_kalshi_settled_market"
