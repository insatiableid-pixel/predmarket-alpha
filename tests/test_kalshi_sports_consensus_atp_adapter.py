from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from predmarket.sports_consensus import build_sports_consensus_preflight
from predmarket.sports_consensus_atp_adapter import (
    build_atp_book_rows_from_odds_api,
    build_atp_donor_consensus_adapter,
    build_atp_kalshi_rows_from_payload,
)

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_consensus_atp_donor_adapter.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_script():
    spec = importlib.util.spec_from_file_location(
        "kalshi_sports_consensus_atp_donor_adapter", SCRIPT_PATH
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def atp_book_rows() -> list[dict]:
    return [
        quote("Betfair Exchange UK", "betfair_ex_uk", "Alex de Minaur", 1.28),
        quote("Betfair Exchange UK", "betfair_ex_uk", "Flavio Cobolli", 4.5),
        quote("Matchbook Exchange", "matchbook", "Alex de Minaur", 1.29),
        quote("Matchbook Exchange", "matchbook", "Flavio Cobolli", 4.4),
    ]


def quote(provider: str, key: str, side: str, decimal: float) -> dict:
    return {
        "away_team": "Flavio Cobolli",
        "commence_time": "2026-07-05T09:00:00Z",
        "decimal_odds": decimal,
        "event_id": "KXATPMATCH-26JUL06DECOB",
        "home_team": "Alex de Minaur",
        "market_type": "match_winner",
        "observed_at": "2026-07-04T23:43:56Z",
        "provider": provider,
        "provider_implied_sum": 1.003472,
        "provider_key": key,
        "side": side,
        "source": "the_odds_api",
        "sport": "tennis",
    }


def atp_kalshi_rows() -> list[dict]:
    return [
        kalshi("Alex de Minaur", "KXATPMATCH-26JUL06DECOB-DE", 0.76, 0.77),
        kalshi("Flavio Cobolli", "KXATPMATCH-26JUL06DECOB-COB", 0.24, 0.25),
    ]


def atp_universe_payload() -> dict:
    return {
        "generated_utc": "2026-07-05T20:40:00Z",
        "candidates": [
            {
                "event_ticker": "KXATPMATCH-26JUL06DECOB",
                "expected_expiration_time": "2026-07-06T13:00:00Z",
                "open_interest": 1000.0,
                "series_ticker": "KXATPMATCH",
                "ticker": "KXATPMATCH-26JUL06DECOB-DE",
                "title": "Will Alex de Minaur win the de Minaur vs Cobolli: Round Of 16 match?",
                "volume": 1000.0,
                "yes_ask": 0.78,
                "yes_bid": 0.77,
            },
            {
                "event_ticker": "KXATPMATCH-26JUL06DECOB",
                "expected_expiration_time": "2026-07-06T13:00:00Z",
                "open_interest": 1000.0,
                "series_ticker": "KXATPMATCH",
                "ticker": "KXATPMATCH-26JUL06DECOB-COB",
                "title": "Will Flavio Cobolli win the de Minaur vs Cobolli: Round Of 16 match?",
                "volume": 1000.0,
                "yes_ask": 0.23,
                "yes_bid": 0.22,
            },
            {
                "event_ticker": "KXATPSETWINNER-26JUL06DECOB-1",
                "series_ticker": "KXATPSETWINNER",
                "ticker": "KXATPSETWINNER-26JUL06DECOB-1-DE",
                "title": "Will Alex de Minaur win set 1 in the Alex de Minaur vs Flavio Cobolli match",
            },
        ],
    }


def raw_odds_api_payload() -> list[dict]:
    return [
        {
            "away_team": "Flavio Cobolli",
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "title": "Pinnacle",
                    "markets": [
                        {
                            "key": "h2h",
                            "last_update": "2026-07-05T20:39:10Z",
                            "outcomes": [
                                {"name": "Alex de Minaur", "price": -360},
                                {"name": "Flavio Cobolli", "price": 290},
                            ],
                        }
                    ],
                },
                {
                    "key": "matchbook",
                    "title": "Matchbook Exchange",
                    "markets": [
                        {
                            "key": "h2h",
                            "last_update": "2026-07-05T20:39:20Z",
                            "outcomes": [
                                {"name": "Alex de Minaur", "price": -350},
                                {"name": "Flavio Cobolli", "price": 285},
                            ],
                        }
                    ],
                },
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "markets": [
                        {
                            "key": "h2h",
                            "last_update": "2026-07-05T20:39:20Z",
                            "outcomes": [
                                {"name": "Alex de Minaur", "price": -380},
                                {"name": "Flavio Cobolli", "price": 300},
                            ],
                        }
                    ],
                },
            ],
            "commence_time": "2026-07-06T13:00:00Z",
            "home_team": "Alex de Minaur",
            "id": "odds-event-1",
            "sport_key": "tennis_atp_wimbledon",
        }
    ]


def kalshi(side: str, ticker: str, bid: float, ask: float) -> dict:
    return {
        "close_time": "2026-07-05T09:00:00Z",
        "event_id": "KXATPMATCH-26JUL06DECOB",
        "last_price": bid,
        "market_ticker": ticker,
        "market_type": "match_winner",
        "observed_at": "2026-07-04T23:45:00Z",
        "open_interest": 1000.0,
        "side": side,
        "source": "kalshi_public_api",
        "sport": "tennis",
        "volume": 1000.0,
        "yes_ask": ask,
        "yes_bid": bid,
    }


def test_atp_adapter_emits_strict_rows_that_pass_preflight() -> None:
    reference, combined_kalshi, report = build_atp_donor_consensus_adapter(
        existing_reference={"rows": []},
        base_kalshi_payload={"generated_utc": "2026-07-04T23:45:00Z", "candidates": []},
        atp_book_rows=atp_book_rows(),
        atp_kalshi_rows=atp_kalshi_rows(),
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "sports_consensus_atp_donor_adapter_ready"
    assert reference["quality"]["atp_reference_row_count"] == 4
    assert reference["quality"]["atp_unique_kalshi_ticker_count"] == 2
    assert {row["book_id"] for row in reference["rows"]} == {
        "betfair_exchange",
        "matchbook",
    }
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
    candidate = next(row for row in preflight["candidates"] if row["kalshi_ticker"].endswith("-DE"))
    assert candidate["distinct_books"] == ["betfair_exchange", "matchbook"]
    assert candidate["consensus_no_vig_probability_for_side"] is not None


def test_atp_adapter_skips_missing_exact_kalshi_side() -> None:
    reference, _combined_kalshi, report = build_atp_donor_consensus_adapter(
        existing_reference={"rows": []},
        base_kalshi_payload={"candidates": []},
        atp_book_rows=atp_book_rows(),
        atp_kalshi_rows=atp_kalshi_rows()[:1],
        created_ts=1_800_000_000.0,
    )

    assert reference["quality"]["atp_reference_row_count"] == 2
    assert report["status"] == "sports_consensus_atp_donor_adapter_ready_with_warnings"
    assert any(row["reason"] == "missing_exact_atp_kalshi_ticker" for row in report["skipped"])


def test_current_odds_api_payload_converts_to_strict_atp_rows() -> None:
    kalshi_rows = build_atp_kalshi_rows_from_payload(atp_universe_payload())
    book_rows, skipped = build_atp_book_rows_from_odds_api(
        raw_odds_api_payload(),
        atp_kalshi_rows=kalshi_rows,
        odds_meta={
            "created_at_utc": "2026-07-05T20:40:00Z",
            "odds_format": "american",
            "provider_api_calls": True,
        },
        allowed_books=("pinnacle", "matchbook"),
    )

    assert not skipped
    assert {row["event_id"] for row in book_rows} == {"KXATPMATCH-26JUL06DECOB"}
    assert {row["provider_key"] for row in book_rows} == {"pinnacle", "matchbook"}
    assert {row["side"] for row in book_rows} == {"Alex de Minaur", "Flavio Cobolli"}
    assert all(row["decimal_odds"] > 1.0 for row in book_rows)

    reference, combined_kalshi, report = build_atp_donor_consensus_adapter(
        existing_reference={"rows": []},
        base_kalshi_payload=atp_universe_payload(),
        atp_book_rows=book_rows,
        atp_kalshi_rows=kalshi_rows,
        created_ts=1_800_000_000.0,
        provider_api_calls=True,
    )
    assert report["status"] == "sports_consensus_atp_donor_adapter_ready"
    assert report["provider_api_calls"] is True

    preflight = build_sports_consensus_preflight(
        combined_kalshi,
        reference,
        run_id="unit",
        max_timestamp_skew_seconds=180.0,
        created_ts=1_800_000_000.0,
    )
    assert preflight["summary"]["valid_candidate_count"] == 2


def test_script_marks_set_winner_only_tennis_as_incompatible_market(tmp_path: Path) -> None:
    module = load_script()
    reference = tmp_path / "sports-no-vig-consensus.json"
    combined = tmp_path / "combined-kalshi.json"
    base = tmp_path / "base-kalshi.json"
    odds = tmp_path / "odds.json"
    meta = tmp_path / "odds.meta.json"
    out_dir = tmp_path / "out"
    reference.write_text(json.dumps({"rows": []}))
    base.write_text(
        json.dumps(
            {
                "generated_utc": "2026-07-05T20:40:00Z",
                "candidates": [
                    {
                        "event_ticker": "KXATPSETWINNER-26JUL06DECOB-1",
                        "series_ticker": "KXATPSETWINNER",
                        "ticker": "KXATPSETWINNER-26JUL06DECOB-1-DE",
                        "title": (
                            "Will Alex de Minaur win set 1 in the "
                            "Alex de Minaur vs Flavio Cobolli match"
                        ),
                    }
                ],
            }
        )
    )
    odds.write_text(json.dumps(raw_odds_api_payload()))
    meta.write_text(
        json.dumps(
            {
                "created_at_utc": "2026-07-05T20:40:00Z",
                "odds_format": "american",
                "provider_api_calls": False,
            }
        )
    )

    report = module.run_atp_donor_adapter(
        reference_json=reference,
        combined_kalshi_json=combined,
        base_kalshi_json=base,
        atp_odds_json=odds,
        atp_odds_meta_json=meta,
        out_dir=out_dir,
        run_id="unit",
        write=True,
    )

    assert (
        report["status"]
        == "sports_consensus_atp_donor_adapter_blocked_no_compatible_atp_match_markets"
    )
    assert report["summary"]["atp_reference_row_count"] == 0
    assert {row["reason"] for row in report["conversion_skipped"]} == {
        "missing_exact_atp_kalshi_event"
    }


def test_script_writes_reference_and_combined_kalshi(tmp_path: Path) -> None:
    module = load_script()
    reference = tmp_path / "sports-no-vig-consensus.json"
    combined = tmp_path / "combined-kalshi.json"
    base = tmp_path / "base-kalshi.json"
    book = tmp_path / "atp-books.jsonl"
    kalshi_path = tmp_path / "atp-kalshi.jsonl"
    out_dir = tmp_path / "out"
    reference.write_text(json.dumps({"rows": []}))
    base.write_text(json.dumps({"candidates": []}))
    book.write_text("\n".join(json.dumps(row) for row in atp_book_rows()) + "\n")
    kalshi_path.write_text("\n".join(json.dumps(row) for row in atp_kalshi_rows()) + "\n")

    report = module.run_atp_donor_adapter(
        reference_json=reference,
        combined_kalshi_json=combined,
        base_kalshi_json=base,
        atp_book_jsonl=book,
        atp_kalshi_jsonl=kalshi_path,
        out_dir=out_dir,
        run_id="unit",
        write=True,
    )

    assert report["status"] == "sports_consensus_atp_donor_adapter_ready"
    assert json.loads(reference.read_text())["quality"]["atp_reference_row_count"] == 4
    assert json.loads(combined.read_text())["candidates"][0]["ticker"]
    assert (out_dir / "kalshi-sports-consensus-atp-donor-adapter.json").is_file()


def test_makefile_wires_atp_adapter_before_consensus_preflight() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-consensus-atp-donor-adapter" in text
    assert "scripts/kalshi_sports_consensus_atp_donor_adapter.py" in text
    assert "--kalshi-json $(KALSHI_SPORTS_CONSENSUS_KALSHI_JSON)" in text
    assert "KALSHI_SPORTS_CONSENSUS_ATP_CAPTURE" in text
