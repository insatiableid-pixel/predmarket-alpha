from __future__ import annotations

import json
from pathlib import Path

from predmarket.sports_consensus import build_sports_consensus_preflight
from predmarket.sports_consensus_reference_builder import (
    HttpResponse,
    build_sports_consensus_reference,
    capture_the_odds_api_current,
)

MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def _kalshi_payload() -> dict:
    return {
        "generated_utc": "2026-07-04T20:18:30Z",
        "candidates": [
            {
                "ticker": "KXMLBGAME-26JUL041605DETTEX-DET",
                "event_ticker": "KXMLBGAME-26JUL041605DETTEX",
                "title": "Detroit vs Texas Winner?",
            },
            {
                "ticker": "KXMLBGAME-26JUL041605DETTEX-TEX",
                "event_ticker": "KXMLBGAME-26JUL041605DETTEX",
                "title": "Detroit vs Texas Winner?",
            },
        ],
    }


def _odds_payload(*, lowvig_update: str = "2026-07-04T20:17:45Z") -> list[dict]:
    return [
        {
            "id": "evt-det-tex",
            "sport_key": "baseball_mlb",
            "commence_time": "2026-07-04T20:06:00Z",
            "away_team": "Detroit Tigers",
            "home_team": "Texas Rangers",
            "bookmakers": [
                _book("lowvig", lowvig_update, -119, 108),
                _book("betonlineag", "2026-07-04T20:17:40Z", -118, 107),
                _book("draftkings", "2026-07-04T20:17:30Z", -237, 177),
            ],
        }
    ]


def _book(book_id: str, update: str, away_price: int, home_price: int) -> dict:
    return {
        "key": book_id,
        "title": book_id,
        "last_update": update,
        "markets": [
            {
                "key": "h2h",
                "last_update": update,
                "outcomes": [
                    {"name": "Detroit Tigers", "price": away_price},
                    {"name": "Texas Rangers", "price": home_price},
                ],
            }
        ],
    }


def test_reference_builder_creates_required_book_rows_that_pass_preflight() -> None:
    reference, report = build_sports_consensus_reference(
        kalshi_payload=_kalshi_payload(),
        odds_captures=[
            (
                _odds_payload(),
                {"sport_key": "baseball_mlb", "created_at_utc": "2026-07-04T20:18:06Z"},
                Path("/tmp/baseball_mlb_current.json"),
            )
        ],
        created_ts=1_800_000_000.0,
        required_books=("lowvig", "betonlineag"),
    )

    assert report["status"] == "sports_consensus_reference_built"
    assert reference["quality"]["reference_row_count"] == 4
    assert reference["quality"]["unique_kalshi_ticker_count"] == 2
    assert {row["book_id"] for row in reference["rows"]} == {"lowvig", "betonlineag"}

    preflight = build_sports_consensus_preflight(
        _kalshi_payload(),
        reference,
        run_id="unit",
        created_ts=1_800_000_000.0,
    )
    assert preflight["status"] == "sports_consensus_preflight_ready"
    assert preflight["summary"]["valid_candidate_count"] == 2


def test_reference_builder_applies_source_age_filter() -> None:
    reference, report = build_sports_consensus_reference(
        kalshi_payload=_kalshi_payload(),
        odds_captures=[
            (
                _odds_payload(lowvig_update="2026-07-04T19:00:00Z"),
                {"sport_key": "baseball_mlb", "created_at_utc": "2026-07-04T20:18:06Z"},
                None,
            )
        ],
        created_ts=1_800_000_000.0,
        required_books=("lowvig", "betonlineag"),
        max_source_age_seconds=900.0,
    )

    assert report["status"] == "sports_consensus_reference_built_with_warnings"
    assert reference["quality"]["reference_row_count"] == 2
    assert report["skipped"][0]["reason"] == "required_books_incomplete"


def test_capture_current_writes_raw_without_printing_key(tmp_path: Path) -> None:
    def transport(url: str, timeout: float) -> HttpResponse:
        assert "secret-key" in url
        assert timeout == 2.0
        return HttpResponse(
            status_code=200,
            headers={"x-requests-used": "1"},
            body=json.dumps(_odds_payload()).encode("utf-8"),
        )

    rows, meta, raw_path = capture_the_odds_api_current(
        api_key="secret-key",
        sport_key="baseball_mlb",
        output_dir=tmp_path,
        timeout_seconds=2.0,
        created_at_utc="2026-07-04T20:18:06Z",
        transport=transport,
    )

    assert len(rows) == 1
    assert raw_path.is_file()
    assert meta["api_key_printed"] is False
    assert "secret-key" not in json.dumps(meta)
    assert meta["quota_headers"]["x-requests-used"] == "1"


def test_capture_current_can_target_bookmakers_without_regions(tmp_path: Path) -> None:
    seen_url = ""

    def transport(url: str, timeout: float) -> HttpResponse:
        nonlocal seen_url
        seen_url = url
        return HttpResponse(
            status_code=200,
            headers={},
            body=json.dumps(_odds_payload()).encode("utf-8"),
        )

    _, meta, _ = capture_the_odds_api_current(
        api_key="secret-key",
        sport_key="baseball_mlb",
        output_dir=tmp_path,
        bookmakers=("pinnacle", "matchbook"),
        timeout_seconds=2.0,
        created_at_utc="2026-07-04T20:18:06Z",
        transport=transport,
    )

    assert "bookmakers=pinnacle%2Cmatchbook" in seen_url
    assert "regions=" not in seen_url
    assert meta["bookmakers"] == ["pinnacle", "matchbook"]
    assert meta["request"]["params"]["bookmakers"] == "pinnacle,matchbook"
    assert "regions" not in meta["request"]["params"]


def test_makefile_consensus_refresh_target_exists() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-consensus-reference-build" in text
    assert "kalshi-sports-consensus-sharp-provider-capture" in text
    assert "kalshi-sports-consensus-refresh" in text
    assert "KALSHI_SPORTS_CONSENSUS_SHARP_BOOKMAKERS" in text
    assert "KALSHI_SPORTS_CONSENSUS_REQUIRED_BOOKS ?= pinnacle,betfair_ex_uk,matchbook,smarkets" in text
    assert "scripts/kalshi_sports_consensus_reference_build.py" in text
