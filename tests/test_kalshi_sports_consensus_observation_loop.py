from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_consensus_observation_loop.py"
)
FALSIFICATION_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_consensus_falsification.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_module(path: Path = SCRIPT_PATH, name: str = "kalshi_sports_consensus_observation_loop"):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def preflight_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "sports_consensus_preflight_ready",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "created_at_utc": "2026-07-04T18:00:00Z",
        "inputs": {"consensus_sha256": "abc123"},
        "summary": {
            "valid_candidate_count": 1,
            "reference_row_count": 2,
            "distinct_book_count": 2,
        },
        "candidates": [
            {
                "valid": True,
                "kalshi_ticker": "KXMLBGAME-26JUL041910NYYTOR-NYY",
                "side": "yes",
                "kalshi_observed_utc": "2026-07-04T18:00:00Z",
                "consensus_no_vig_probability_for_side": 0.57,
                "book_count": 2,
                "distinct_books": ["betonlineag", "lowvig"],
                "timestamp_skew_seconds": 25.0,
            }
        ],
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }


def universe_payload(*, include_mid: bool = True) -> dict:
    row = {
        "ticker": "KXMLBGAME-26JUL041910NYYTOR-NYY",
        "event_ticker": "KXMLBGAME-26JUL041910NYYTOR",
        "series_ticker": "KXMLBGAME",
        "classification": "mlb",
        "close_time": "2026-07-04T23:00:00Z",
        "expected_expiration_time": "2026-07-04T23:05:00Z",
        "research_only": True,
        "execution_enabled": False,
    }
    if include_mid:
        row.update({"yes_bid": 0.51, "yes_ask": 0.53, "no_bid": 0.47, "no_ask": 0.49})
    return {
        "schema_version": 1,
        "status": "universe_scan_ready_with_model_routes",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "all_scored": [row],
        "summary": {"candidate_count": 1},
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }


def settled_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "kalshi_sports_consensus_observed_market_fetch_ok",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "markets": [
            {
                "ticker": "KXMLBGAME-26JUL041910NYYTOR-NYY",
                "result": "yes",
                "settlement_value_dollars": 1.0,
                "close_time": "2026-07-04T23:00:00Z",
                "expiration_time": "2026-07-04T23:05:00Z",
            }
        ],
        "summary": {"market_count": 1},
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }


def test_missing_preflight_blocks(tmp_path: Path) -> None:
    module = load_module()
    universe = write_json(tmp_path / "universe.json", universe_payload())

    report = module.build_sports_consensus_observation_loop(
        preflight_path=tmp_path / "missing.json",
        universe_path=universe,
        observation_dir=tmp_path / "obs",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-04T18:00:00Z",
    )

    assert report["status"] == "sports_consensus_observation_loop_blocked_missing_preflight"
    assert report["summary"]["total_observation_row_count"] == 0
    assert report["summary"]["label_row_count"] == 0


def test_valid_preflight_archives_consensus_observation(tmp_path: Path) -> None:
    module = load_module()
    preflight = write_json(tmp_path / "preflight.json", preflight_payload())
    universe = write_json(tmp_path / "universe.json", universe_payload())

    report = module.build_sports_consensus_observation_loop(
        preflight_path=preflight,
        universe_path=universe,
        observation_dir=tmp_path / "obs",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-04T18:00:00Z",
    )

    row = report["observation_packet"]["rows"][0]
    assert report["status"] == "sports_consensus_observation_loop_ready_waiting_settlement"
    assert report["summary"]["new_observation_row_count"] == 1
    assert row["contract_ticker"] == "KXMLBGAME-26JUL041910NYYTOR-NYY"
    assert row["kalshi_mid_for_side"] == 0.52
    assert row["consensus_probability_for_side"] == 0.57
    assert round(row["divergence"], 4) == 0.05
    assert row["usable"] is False
    assert row["expected_value_per_contract"] is None


def test_missing_mid_blocks_observation_creation(tmp_path: Path) -> None:
    module = load_module()
    preflight = write_json(tmp_path / "preflight.json", preflight_payload())
    universe = write_json(tmp_path / "universe.json", universe_payload(include_mid=False))

    report = module.build_sports_consensus_observation_loop(
        preflight_path=preflight,
        universe_path=universe,
        observation_dir=tmp_path / "obs",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-04T18:00:00Z",
    )

    assert report["status"] == "sports_consensus_observation_loop_blocked_no_observations"
    assert report["summary"]["total_observation_row_count"] == 0


def test_settled_public_market_payload_creates_label(tmp_path: Path) -> None:
    module = load_module()
    preflight = write_json(tmp_path / "preflight.json", preflight_payload())
    universe = write_json(tmp_path / "universe.json", universe_payload())
    settled = write_json(tmp_path / "settled.json", settled_payload())

    report = module.build_sports_consensus_observation_loop(
        preflight_path=preflight,
        universe_path=universe,
        settled_snapshot_path=settled,
        observation_dir=tmp_path / "obs",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-05T01:00:00Z",
    )

    label = report["label_packet"]["rows"][0]
    assert report["status"] == "sports_consensus_observation_loop_label_rows_ready"
    assert report["summary"]["new_label_row_count"] == 1
    assert label["yes_outcome"] == 1
    assert label["side_outcome"] == 1
    assert label["label_status"] == "labeled_from_public_kalshi_settled_market"


def test_write_outputs_uses_external_packets_without_temp_latest_leak(tmp_path: Path) -> None:
    module = load_module()
    preflight = write_json(tmp_path / "preflight.json", preflight_payload())
    universe = write_json(tmp_path / "universe.json", universe_payload())
    report = module.build_sports_consensus_observation_loop(
        preflight_path=preflight,
        universe_path=universe,
        observation_dir=tmp_path / "manual_obs",
        label_dir=tmp_path / "manual_labels",
        generated_utc="2026-07-04T18:00:00Z",
    )

    paths = module.write_sports_consensus_observation_outputs(
        report,
        out_dir=tmp_path / "out",
        observation_dir=tmp_path / "manual_obs",
        label_dir=tmp_path / "manual_labels",
    )

    assert Path(paths["json_path"]).is_file()
    assert "latest_json_path" not in paths
    assert Path(paths["observation_packet_path"]).is_file()
    packet = json.loads(Path(paths["observation_packet_path"]).read_text(encoding="utf-8"))
    assert packet["research_only"] is True
    assert packet["rows"][0]["usable"] is False


def test_existing_observation_is_deduped(tmp_path: Path) -> None:
    module = load_module()
    preflight = write_json(tmp_path / "preflight.json", preflight_payload())
    universe = write_json(tmp_path / "universe.json", universe_payload())
    first = module.build_sports_consensus_observation_loop(
        preflight_path=preflight,
        universe_path=universe,
        observation_dir=tmp_path / "obs",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-04T18:00:00Z",
    )
    module.write_sports_consensus_observation_outputs(
        first,
        out_dir=tmp_path / "out",
        observation_dir=tmp_path / "obs",
        label_dir=tmp_path / "labels",
    )

    second = module.build_sports_consensus_observation_loop(
        preflight_path=preflight,
        universe_path=universe,
        observation_dir=tmp_path / "obs",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-04T18:01:00Z",
    )

    assert second["summary"]["existing_observation_row_count"] == 1
    assert second["summary"]["new_observation_row_count"] == 0
    assert second["summary"]["total_observation_row_count"] == 1


def test_due_summary_reports_due_contracts_by_sport() -> None:
    module = load_module()

    summary = module.due_summary(
        [
            {
                "contract_ticker": "KXMLBGAME-26JUL041910NYYTOR-NYY",
                "sport_key": "baseball_mlb",
                "expected_expiration_time": "2026-07-04T23:05:00Z",
            },
            {
                "contract_ticker": "KXATPMATCH-26JUL06DECOB-DE",
                "sport_key": "tennis_atp",
                "expected_expiration_time": "2026-07-06T13:00:00Z",
            },
            {
                "contract_ticker": "KXMLBGAME-26JUL042010BOSNYY-NYY",
                "sport_key": "baseball_mlb",
                "expected_expiration_time": "2026-07-06T13:30:00Z",
            },
        ],
        generated_utc="2026-07-05T01:00:00Z",
    )

    assert summary["due_distinct_contract_count"] == 1
    assert summary["due_distinct_contract_count_by_sport"] == {"baseball_mlb": 1}
    assert summary["due_observation_row_count_by_sport"] == {"baseball_mlb": 1}
    assert summary["not_due_distinct_contract_count_by_sport"] == {
        "baseball_mlb": 1,
        "tennis_atp": 1,
    }


def test_due_summary_excludes_already_labeled_due_contracts() -> None:
    module = load_module()

    summary = module.due_summary(
        [
            {
                "contract_ticker": "KXMLBGAME-26JUL041910NYYTOR-NYY",
                "sport_key": "baseball_mlb",
                "expected_expiration_time": "2026-07-04T23:05:00Z",
            },
            {
                "contract_ticker": "KXMLBGAME-26JUL042010BOSNYY-NYY",
                "sport_key": "baseball_mlb",
                "expected_expiration_time": "2026-07-04T23:30:00Z",
            },
        ],
        generated_utc="2026-07-05T01:00:00Z",
        labeled_contract_tickers={"KXMLBGAME-26JUL041910NYYTOR-NYY"},
    )

    assert summary["due_distinct_contract_count"] == 1
    assert summary["due_distinct_contract_count_by_sport"] == {"baseball_mlb": 1}
    assert summary["labeled_due_distinct_contract_count"] == 1
    assert summary["labeled_due_distinct_contract_count_by_sport"] == {"baseball_mlb": 1}


def test_due_summary_defers_to_current_active_market_clock() -> None:
    module = load_module()
    ticker = "KXMLBGAME-26JUL042008NYMATL-ATL"

    summary = module.due_summary(
        [
            {
                "contract_ticker": ticker,
                "sport_key": "baseball_mlb",
                "expected_expiration_time": "2026-07-05T03:08:00Z",
            },
        ],
        generated_utc="2026-07-06T01:00:00Z",
        market_index={
            ticker: {
                "ticker": ticker,
                "status": "active",
                "close_time": "2026-07-08T00:08:00Z",
                "expected_expiration_time": "2026-07-05T03:08:00Z",
            }
        },
    )

    assert summary["due_distinct_contract_count"] == 0
    assert summary["not_due_distinct_contract_count"] == 1
    assert summary["not_due_distinct_contract_count_by_sport"] == {"baseball_mlb": 1}
    assert summary["next_public_label_probe_utc"] == "2026-07-08T00:08:00Z"


def test_build_loop_does_not_report_labeled_contract_as_due(tmp_path: Path) -> None:
    module = load_module()
    preflight = write_json(tmp_path / "preflight.json", preflight_payload())
    universe = write_json(tmp_path / "universe.json", universe_payload())
    settled = write_json(tmp_path / "settled.json", settled_payload())

    report = module.build_sports_consensus_observation_loop(
        preflight_path=preflight,
        universe_path=universe,
        settled_snapshot_path=settled,
        observation_dir=tmp_path / "obs",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-05T01:00:00Z",
    )

    assert report["summary"]["new_label_row_count"] == 1
    assert report["summary"]["due_distinct_contract_count"] == 0
    assert report["summary"]["labeled_due_distinct_contract_count"] == 1


def test_falsification_reads_observation_and_label_packets(tmp_path: Path) -> None:
    module = load_module()
    falsification = load_module(FALSIFICATION_SCRIPT_PATH, "kalshi_sports_consensus_falsification")
    preflight = write_json(tmp_path / "preflight.json", preflight_payload())
    universe = write_json(tmp_path / "universe.json", universe_payload())
    settled = write_json(tmp_path / "settled.json", settled_payload())
    report = module.build_sports_consensus_observation_loop(
        preflight_path=preflight,
        universe_path=universe,
        settled_snapshot_path=settled,
        observation_dir=tmp_path / "obs",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-05T01:00:00Z",
    )
    module.write_sports_consensus_observation_outputs(
        report,
        out_dir=tmp_path / "out",
        observation_dir=tmp_path / "obs",
        label_dir=tmp_path / "labels",
    )

    falsification_report = falsification.run_sports_consensus_falsification(
        preflight_path=preflight,
        observation_dir=tmp_path / "obs",
        label_dir=tmp_path / "labels",
        min_independent_labels=1,
        min_oos_labels=1,
    )

    assert falsification_report["summary"]["consensus_observation_count"] == 1
    assert falsification_report["summary"]["settlement_label_count"] == 1
    assert falsification_report["summary"]["joined_label_count"] == 1


def test_makefile_targets_exist() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-consensus-observation-loop" in text
    assert "kalshi-sports-consensus-observation-watch-once" in text
    assert "kalshi-sports-consensus-public-kalshi-refresh" in text
    assert "scripts/kalshi_sports_consensus_observation_loop.py" in text
    assert "KALSHI_SPORTS_CONSENSUS_PROBE_OBSERVED ?= 1" in text
    assert "KALSHI_MANUAL_DROP_SERIES=KXNFLGAME" in text
    assert "KALSHI_MANUAL_DROP_SERIES=KXWCGAME" in text
    assert "KALSHI_SPORTS_CONSENSUS_NFL_CAPTURE=1" in text
    assert "KALSHI_SPORTS_CONSENSUS_SOCCER_CAPTURE=1" in text
