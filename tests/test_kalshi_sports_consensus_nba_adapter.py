from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from predmarket.sports_consensus import build_sports_consensus_preflight
from predmarket.sports_consensus_nba_adapter import build_nba_consensus_adapter

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_consensus_nba_adapter.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_script():
    spec = importlib.util.spec_from_file_location(
        "kalshi_sports_consensus_nba_adapter", SCRIPT_PATH
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def nba_kalshi_payload() -> dict:
    return {
        "created_at_utc": "2026-10-21T23:58:00Z",
        "all_scored": [
            nba_kalshi_row("KXNBA-26OCT21BOSNYK-BOS", "BOS", "Boston Celtics", 0.58, 0.60),
            nba_kalshi_row("KXNBA-26OCT21BOSNYK-NYK", "NYK", "New York Knicks", 0.41, 0.43),
        ],
    }


def nba_kalshi_row(ticker: str, suffix: str, team: str, bid: float, ask: float) -> dict:
    return {
        "ticker": ticker,
        "event_ticker": "KXNBA-26OCT21BOSNYK",
        "title": f"Will {team} win the Boston vs New York Pro Basketball game?",
        "yes_sub_title": team,
        "yes_bid_dollars": f"{bid:.4f}",
        "yes_ask_dollars": f"{ask:.4f}",
        "last_price_dollars": f"{bid:.4f}",
        "volume_fp": "1000.0",
        "open_interest_fp": "2000.0",
        "expected_expiration_time": "2026-10-22T00:00:00Z",
        "close_time": "2026-10-22T03:00:00Z",
        "status": "active",
        "suffix": suffix,
    }


def nba_odds_payload() -> list[dict]:
    return [
        {
            "id": "bosnyk",
            "sport_key": "basketball_nba",
            "commence_time": "2026-10-22T00:00:00Z",
            "away_team": "Boston Celtics",
            "home_team": "New York Knicks",
            "bookmakers": [
                bookmaker("pinnacle", -150, 130),
                bookmaker("circa", -145, 125),
            ],
        }
    ]


def bookmaker(key: str, away_price: int, home_price: int) -> dict:
    return {
        "key": key,
        "title": key,
        "last_update": "2026-10-21T23:58:20Z",
        "markets": [
            {
                "key": "h2h",
                "last_update": "2026-10-21T23:58:20Z",
                "outcomes": [
                    {"name": "Boston Celtics", "price": away_price},
                    {"name": "New York Knicks", "price": home_price},
                ],
            }
        ],
    }


def test_nba_adapter_emits_strict_rows_that_pass_preflight() -> None:
    reference, combined_kalshi, report = build_nba_consensus_adapter(
        existing_reference={"rows": []},
        base_kalshi_payload={"generated_utc": "2026-10-21T23:58:00Z", "candidates": []},
        nba_kalshi_payload=nba_kalshi_payload(),
        nba_odds_payload=nba_odds_payload(),
        nba_odds_meta={"created_at_utc": "2026-10-21T23:58:20Z"},
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "sports_consensus_nba_adapter_ready"
    assert reference["quality"]["nba_reference_row_count"] == 4
    assert reference["quality"]["nba_unique_kalshi_ticker_count"] == 2
    assert reference["quality"]["nba_matched_event_count"] == 1
    assert {row["book_id"] for row in reference["rows"]} == {"circa", "pinnacle"}
    assert len(combined_kalshi["candidates"]) == 2

    preflight = build_sports_consensus_preflight(
        combined_kalshi,
        reference,
        run_id="unit",
        max_timestamp_skew_seconds=180.0,
        created_ts=1_800_000_000.0,
    )
    assert preflight["status"] == "sports_consensus_preflight_ready"
    assert preflight["summary"]["valid_candidate_count"] == 2
    candidate = next(
        row for row in preflight["candidates"] if row["kalshi_ticker"].endswith("-BOS")
    )
    assert candidate["distinct_books"] == ["circa", "pinnacle"]
    assert candidate["consensus_no_vig_probability_for_side"] is not None


def test_nba_adapter_requires_exact_team_pair_and_time_window() -> None:
    payload = nba_odds_payload()
    payload[0] = {**payload[0], "home_team": "Brooklyn Nets"}

    reference, _combined_kalshi, report = build_nba_consensus_adapter(
        existing_reference={"rows": []},
        base_kalshi_payload={"candidates": []},
        nba_kalshi_payload=nba_kalshi_payload(),
        nba_odds_payload=payload,
        nba_odds_meta={"created_at_utc": "2026-10-21T23:58:20Z"},
        created_ts=1_800_000_000.0,
    )

    assert reference["quality"]["nba_reference_row_count"] == 0
    assert report["status"] == "sports_consensus_nba_adapter_blocked_no_nba_rows"
    assert any(row["reason"] == "kalshi_event_not_matched" for row in report["skipped"])


def test_script_writes_reference_and_combined_kalshi(tmp_path: Path) -> None:
    module = load_script()
    reference = tmp_path / "sports-no-vig-consensus.json"
    combined = tmp_path / "combined-kalshi.json"
    base = tmp_path / "base-kalshi.json"
    kalshi_path = tmp_path / "nba-kalshi.json"
    odds = tmp_path / "basketball_nba_current_20261021T235820Z.json"
    meta = tmp_path / "basketball_nba_current_20261021T235820Z.meta.json"
    out_dir = tmp_path / "out"
    reference.write_text(json.dumps({"rows": []}), encoding="utf-8")
    base.write_text(json.dumps({"candidates": []}), encoding="utf-8")
    kalshi_path.write_text(json.dumps(nba_kalshi_payload()), encoding="utf-8")
    odds.write_text(json.dumps(nba_odds_payload()), encoding="utf-8")
    meta.write_text(json.dumps({"created_at_utc": "2026-10-21T23:58:20Z"}), encoding="utf-8")

    report = module.run_nba_consensus_adapter(
        reference_json=reference,
        combined_kalshi_json=combined,
        base_kalshi_json=base,
        nba_kalshi_json=kalshi_path,
        nba_odds_json=odds,
        nba_odds_meta_json=meta,
        out_dir=out_dir,
        run_id="unit",
        write=True,
    )

    assert report["status"] == "sports_consensus_nba_adapter_ready"
    assert (
        json.loads(reference.read_text(encoding="utf-8"))["quality"]["nba_reference_row_count"] == 4
    )
    assert json.loads(combined.read_text(encoding="utf-8"))["candidates"][0]["ticker"]
    assert (out_dir / "kalshi-sports-consensus-nba-adapter.json").is_file()


def test_makefile_wires_nba_adapter_before_consensus_preflight() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-consensus-nba-adapter" in text
    assert "scripts/kalshi_sports_consensus_nba_adapter.py" in text
    assert "--nba-kalshi-json $(KALSHI_SPORTS_CONSENSUS_NBA_KALSHI_JSON)" in text
