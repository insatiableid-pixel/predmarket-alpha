from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from predmarket.sports_consensus import build_sports_consensus_preflight
from predmarket.sports_consensus_nfl_adapter import build_nfl_consensus_adapter

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_consensus_nfl_adapter.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_script():
    spec = importlib.util.spec_from_file_location(
        "kalshi_sports_consensus_nfl_adapter", SCRIPT_PATH
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def nfl_kalshi_payload() -> dict:
    return {
        "created_at_utc": "2026-07-05T03:47:29Z",
        "all_scored": [
            nfl_kalshi_row("KXNFLGAME-26SEP09NESEA-NE", "NE", "New England", 0.35, 0.38),
            nfl_kalshi_row("KXNFLGAME-26SEP09NESEA-SEA", "SEA", "Seattle", 0.65, 0.66),
        ],
    }


def nfl_kalshi_row(ticker: str, suffix: str, team: str, bid: float, ask: float) -> dict:
    return {
        "ticker": ticker,
        "event_ticker": "KXNFLGAME-26SEP09NESEA",
        "title": f"Will {team} win the New England vs Seattle Pro Football game?",
        "yes_sub_title": team,
        "yes_bid_dollars": f"{bid:.4f}",
        "yes_ask_dollars": f"{ask:.4f}",
        "last_price_dollars": f"{bid:.4f}",
        "volume_fp": "1000.0",
        "open_interest_fp": "2000.0",
        "expected_expiration_time": "2026-09-10T03:20:00Z",
        "close_time": "2026-09-12T00:20:00Z",
        "status": "active",
        "suffix": suffix,
    }


def nfl_odds_payload() -> list[dict]:
    return [
        {
            "id": "nesea",
            "sport_key": "americanfootball_nfl",
            "commence_time": "2026-09-10T00:15:00Z",
            "away_team": "New England Patriots",
            "home_team": "Seattle Seahawks",
            "bookmakers": [
                bookmaker("smarkets", 156, -222),
                bookmaker("pinnacle", 178, -206),
            ],
        }
    ]


def bookmaker(key: str, away_price: int, home_price: int) -> dict:
    return {
        "key": key,
        "title": key,
        "last_update": "2026-07-05T03:47:50Z",
        "markets": [
            {
                "key": "h2h",
                "last_update": "2026-07-05T03:47:50Z",
                "outcomes": [
                    {"name": "New England Patriots", "price": away_price},
                    {"name": "Seattle Seahawks", "price": home_price},
                ],
            }
        ],
    }


def test_nfl_adapter_emits_strict_rows_that_pass_preflight() -> None:
    reference, combined_kalshi, report = build_nfl_consensus_adapter(
        existing_reference={"rows": []},
        base_kalshi_payload={"generated_utc": "2026-07-05T03:47:29Z", "candidates": []},
        nfl_kalshi_payload=nfl_kalshi_payload(),
        nfl_odds_payload=nfl_odds_payload(),
        nfl_odds_meta={"created_at_utc": "2026-07-05T03:47:50Z"},
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "sports_consensus_nfl_adapter_ready"
    assert reference["quality"]["nfl_reference_row_count"] == 4
    assert reference["quality"]["nfl_unique_kalshi_ticker_count"] == 2
    assert reference["quality"]["nfl_matched_event_count"] == 1
    assert {row["book_id"] for row in reference["rows"]} == {"pinnacle", "smarkets"}
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
        row for row in preflight["candidates"] if row["kalshi_ticker"].endswith("-SEA")
    )
    assert candidate["distinct_books"] == ["pinnacle", "smarkets"]
    assert candidate["consensus_no_vig_probability_for_side"] is not None


def test_nfl_adapter_requires_exact_local_date_and_team_pair() -> None:
    payload = nfl_odds_payload()
    payload[0] = {**payload[0], "home_team": "San Francisco 49ers"}

    reference, _combined_kalshi, report = build_nfl_consensus_adapter(
        existing_reference={"rows": []},
        base_kalshi_payload={"candidates": []},
        nfl_kalshi_payload=nfl_kalshi_payload(),
        nfl_odds_payload=payload,
        nfl_odds_meta={"created_at_utc": "2026-07-05T03:47:50Z"},
        created_ts=1_800_000_000.0,
    )

    assert reference["quality"]["nfl_reference_row_count"] == 0
    assert report["status"] == "sports_consensus_nfl_adapter_blocked_no_nfl_rows"
    assert any(row["reason"] == "kalshi_event_not_matched" for row in report["skipped"])


def test_script_writes_reference_and_combined_kalshi(tmp_path: Path) -> None:
    module = load_script()
    reference = tmp_path / "sports-no-vig-consensus.json"
    combined = tmp_path / "combined-kalshi.json"
    base = tmp_path / "base-kalshi.json"
    kalshi_path = tmp_path / "nfl-kalshi.json"
    odds = tmp_path / "americanfootball_nfl_current_20260705T034750Z.json"
    meta = tmp_path / "americanfootball_nfl_current_20260705T034750Z.meta.json"
    out_dir = tmp_path / "out"
    reference.write_text(json.dumps({"rows": []}))
    base.write_text(json.dumps({"candidates": []}))
    kalshi_path.write_text(json.dumps(nfl_kalshi_payload()))
    odds.write_text(json.dumps(nfl_odds_payload()))
    meta.write_text(json.dumps({"created_at_utc": "2026-07-05T03:47:50Z"}))

    report = module.run_nfl_consensus_adapter(
        reference_json=reference,
        combined_kalshi_json=combined,
        base_kalshi_json=base,
        nfl_kalshi_json=kalshi_path,
        nfl_odds_json=odds,
        nfl_odds_meta_json=meta,
        out_dir=out_dir,
        run_id="unit",
        write=True,
    )

    assert report["status"] == "sports_consensus_nfl_adapter_ready"
    assert json.loads(reference.read_text())["quality"]["nfl_reference_row_count"] == 4
    assert json.loads(combined.read_text())["candidates"][0]["ticker"]
    assert (out_dir / "kalshi-sports-consensus-nfl-adapter.json").is_file()


def test_makefile_wires_nfl_adapter_before_consensus_preflight() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-consensus-nfl-adapter" in text
    assert "scripts/kalshi_sports_consensus_nfl_adapter.py" in text
    assert "--nfl-kalshi-json $(KALSHI_SPORTS_CONSENSUS_NFL_KALSHI_JSON)" in text
