from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from predmarket.sports_consensus import build_sports_consensus_preflight
from predmarket.sports_consensus_soccer_adapter import build_soccer_consensus_adapter

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_consensus_soccer_adapter.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_script():
    spec = importlib.util.spec_from_file_location(
        "kalshi_sports_consensus_soccer_adapter", SCRIPT_PATH
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def soccer_kalshi_payload() -> dict:
    return {
        "created_at_utc": "2026-07-05T03:59:13Z",
        "all_scored": [
            soccer_kalshi_row("KXWCGAME-26JUL05BRANOR-BRA", "Brazil", 0.53, 0.54),
            soccer_kalshi_row("KXWCGAME-26JUL05BRANOR-NOR", "Norway", 0.20, 0.21),
            soccer_kalshi_row("KXWCGAME-26JUL05BRANOR-TIE", "Tie", 0.26, 0.27),
        ],
    }


def soccer_kalshi_row(ticker: str, side: str, bid: float, ask: float) -> dict:
    return {
        "ticker": ticker,
        "event_ticker": "KXWCGAME-26JUL05BRANOR",
        "title": "Brazil vs Norway Winner?",
        "yes_sub_title": f"Reg Time: {side}",
        "no_sub_title": f"Reg Time: {side}",
        "yes_bid_dollars": f"{bid:.4f}",
        "yes_ask_dollars": f"{ask:.4f}",
        "last_price_dollars": f"{bid:.4f}",
        "volume_fp": "1000.0",
        "open_interest_fp": "2000.0",
        "expected_expiration_time": "2026-07-05T23:00:00Z",
        "close_time": "2026-07-19T20:00:00Z",
        "status": "active",
    }


def soccer_odds_payload() -> list[dict]:
    return [
        {
            "id": "branor",
            "sport_key": "soccer_fifa_world_cup",
            "commence_time": "2026-07-05T20:00:00Z",
            "home_team": "Brazil",
            "away_team": "Norway",
            "bookmakers": [
                bookmaker("pinnacle", -120, 390, 280),
                bookmaker("smarkets", -116, 390, 280),
            ],
        }
    ]


def bookmaker(key: str, home_price: int, away_price: int, draw_price: int) -> dict:
    return {
        "key": key,
        "title": key,
        "last_update": "2026-07-05T03:59:30Z",
        "markets": [
            {
                "key": "h2h",
                "last_update": "2026-07-05T03:59:30Z",
                "outcomes": [
                    {"name": "Brazil", "price": home_price},
                    {"name": "Norway", "price": away_price},
                    {"name": "Draw", "price": draw_price},
                ],
            }
        ],
    }


def test_soccer_adapter_emits_three_way_strict_rows_that_pass_preflight() -> None:
    reference, combined_kalshi, report = build_soccer_consensus_adapter(
        existing_reference={"rows": []},
        base_kalshi_payload={"generated_utc": "2026-07-05T03:59:13Z", "candidates": []},
        soccer_kalshi_payload=soccer_kalshi_payload(),
        soccer_odds_payload=soccer_odds_payload(),
        soccer_odds_meta={"created_at_utc": "2026-07-05T03:59:30Z"},
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "sports_consensus_soccer_adapter_ready"
    assert reference["quality"]["soccer_reference_row_count"] == 6
    assert reference["quality"]["soccer_unique_kalshi_ticker_count"] == 3
    assert reference["quality"]["soccer_matched_event_count"] == 1
    assert {row["book_id"] for row in reference["rows"]} == {"pinnacle", "smarkets"}
    assert all(row["three_way_no_vig"] is True for row in reference["rows"])
    assert len(combined_kalshi["candidates"]) == 3

    preflight = build_sports_consensus_preflight(
        combined_kalshi,
        reference,
        run_id="unit",
        max_timestamp_skew_seconds=180.0,
        created_ts=1_800_000_000.0,
    )
    assert preflight["status"] == "sports_consensus_preflight_ready"
    assert preflight["summary"]["valid_candidate_count"] == 3
    candidate = next(
        row for row in preflight["candidates"] if row["kalshi_ticker"].endswith("-TIE")
    )
    assert candidate["distinct_books"] == ["pinnacle", "smarkets"]
    assert candidate["consensus_no_vig_probability_for_side"] is not None


def test_soccer_adapter_requires_exact_home_away_event_ticker() -> None:
    payload = soccer_odds_payload()
    payload[0] = {**payload[0], "home_team": "France"}

    reference, _combined_kalshi, report = build_soccer_consensus_adapter(
        existing_reference={"rows": []},
        base_kalshi_payload={"candidates": []},
        soccer_kalshi_payload=soccer_kalshi_payload(),
        soccer_odds_payload=payload,
        soccer_odds_meta={"created_at_utc": "2026-07-05T03:59:30Z"},
        created_ts=1_800_000_000.0,
    )

    assert reference["quality"]["soccer_reference_row_count"] == 0
    assert report["status"] == "sports_consensus_soccer_adapter_blocked_no_soccer_rows"
    assert any(row["reason"] == "kalshi_event_not_matched" for row in report["skipped"])


def test_script_writes_reference_and_combined_kalshi(tmp_path: Path) -> None:
    module = load_script()
    reference = tmp_path / "sports-no-vig-consensus.json"
    combined = tmp_path / "combined-kalshi.json"
    base = tmp_path / "base-kalshi.json"
    kalshi_path = tmp_path / "soccer-kalshi.json"
    odds = tmp_path / "soccer_fifa_world_cup_current_20260705T035930Z.json"
    meta = tmp_path / "soccer_fifa_world_cup_current_20260705T035930Z.meta.json"
    out_dir = tmp_path / "out"
    reference.write_text(json.dumps({"rows": []}))
    base.write_text(json.dumps({"candidates": []}))
    kalshi_path.write_text(json.dumps(soccer_kalshi_payload()))
    odds.write_text(json.dumps(soccer_odds_payload()))
    meta.write_text(json.dumps({"created_at_utc": "2026-07-05T03:59:30Z"}))

    report = module.run_soccer_consensus_adapter(
        reference_json=reference,
        combined_kalshi_json=combined,
        base_kalshi_json=base,
        soccer_kalshi_json=kalshi_path,
        soccer_odds_json=odds,
        soccer_odds_meta_json=meta,
        out_dir=out_dir,
        run_id="unit",
        write=True,
    )

    assert report["status"] == "sports_consensus_soccer_adapter_ready"
    assert json.loads(reference.read_text())["quality"]["soccer_reference_row_count"] == 6
    assert json.loads(combined.read_text())["candidates"][0]["ticker"]
    assert (out_dir / "kalshi-sports-consensus-soccer-adapter.json").is_file()


def test_makefile_wires_soccer_adapter_before_consensus_preflight() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-consensus-soccer-adapter" in text
    assert "scripts/kalshi_sports_consensus_soccer_adapter.py" in text
    assert "--soccer-kalshi-json $(KALSHI_SPORTS_CONSENSUS_SOCCER_KALSHI_JSON)" in text
