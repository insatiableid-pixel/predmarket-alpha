from __future__ import annotations

from pathlib import Path

from scripts.kalshi_sports_historical_consensus_archive import (
    acquire_snapshots,
    assemble_archive,
    build_snapshot_plan,
)

MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def markets() -> list[dict[str, object]]:
    base = {
        "event_ticker": "KXMLBGAME-26JUL011900NYYBOS",
        "occurrence_datetime": "2026-07-01T23:00:00Z",
        "status": "finalized",
    }
    return [
        {**base, "ticker": "KXMLBGAME-26JUL011900NYYBOS-NYY"},
        {**base, "ticker": "KXMLBGAME-26JUL011900NYYBOS-BOS"},
    ]


def candles() -> dict[str, list[dict[str, object]]]:
    return {
        str(row["ticker"]): [
            {"end_period_ts": "2026-07-01T21:00:00Z"},
            {"end_period_ts": "2026-07-01T22:00:00Z"},
        ]
        for row in markets()
    }


def historical_payload() -> dict[str, object]:
    books = []
    for key, nyy, bos in (("pinnacle", -120, 110), ("matchbook", -118, 108)):
        books.append(
            {
                "key": key,
                "last_update": "2026-07-01T22:00:20Z",
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": "2026-07-01T22:00:20Z",
                        "outcomes": [
                            {"name": "New York Yankees", "price": nyy},
                            {"name": "Boston Red Sox", "price": bos},
                        ],
                    }
                ],
            }
        )
    return {
        "timestamp": "2026-07-01T22:00:37Z",
        "data": [
            {
                "id": "event-1",
                "sport_key": "baseball_mlb",
                "commence_time": "2026-07-01T23:00:00Z",
                "away_team": "New York Yankees",
                "home_team": "Boston Red Sox",
                "bookmakers": books,
            }
        ],
    }


def test_plan_uses_latest_shared_candle_at_least_one_hour_pregame() -> None:
    plan, blockers = build_snapshot_plan(markets(), candles(), pregame_lead_seconds=3600)

    assert blockers == []
    assert len(plan) == 1
    assert plan[0]["target_time_utc"] == "2026-07-01T22:00:00Z"
    assert len(plan[0]["contract_tickers"]) == 2


def test_plan_anchors_to_exact_ticker_start_when_archive_time_is_drifted() -> None:
    drifted_markets = [{**row, "occurrence_datetime": "2026-07-01T20:00:00Z"} for row in markets()]
    drifted_candles = {
        str(row["ticker"]): [
            {"end_period_ts": "2026-07-01T19:00:00Z"},
            {"end_period_ts": "2026-07-01T22:00:00Z"},
        ]
        for row in drifted_markets
    }

    plan, blockers = build_snapshot_plan(
        drifted_markets, drifted_candles, pregame_lead_seconds=3600
    )

    assert blockers == []
    assert plan[0]["target_time_utc"] == "2026-07-01T22:00:00Z"


def test_archive_uses_exact_mapping_multibook_no_vig_and_skew(tmp_path: Path) -> None:
    plan, blockers = build_snapshot_plan(markets(), candles(), pregame_lead_seconds=3600)

    def fake_fetch(url: str, timeout: float):
        assert "api-key-value" in url
        assert timeout == 20.0
        return historical_payload(), {"x-requests-last": "10", "x-requests-remaining": "990"}

    snapshots, errors = acquire_snapshots(
        plan,
        api_key="api-key-value",
        raw_dir=tmp_path / "raw",
        bookmakers=("pinnacle", "matchbook"),
        capture_paid=True,
        max_paid_credits=10,
        fetch_fn=fake_fetch,
    )
    archive, report = assemble_archive(
        plan,
        blockers,
        snapshots,
        errors,
        markets=markets(),
        min_distinct_books=2,
        max_skew_seconds=180,
    )

    assert report["status"] == "kalshi_sports_historical_consensus_archive_ready"
    assert report["summary"]["historical_consensus_row_count"] == 2
    assert report["summary"]["distinct_event_count"] == 1
    assert report["summary"]["max_provider_snapshot_skew_seconds"] == 37.0
    assert report["summary"]["quota_headers"]["x-requests-last"] == "10"
    assert all(row["book_count"] == 2 for row in archive["rows"])
    assert all(row["execution_enabled"] is False for row in archive["rows"])


def test_paid_credit_cap_blocks_before_transport(tmp_path: Path) -> None:
    plan, _ = build_snapshot_plan(markets(), candles(), pregame_lead_seconds=3600)

    def should_not_run(url: str, timeout: float):
        raise AssertionError((url, timeout))

    snapshots, errors = acquire_snapshots(
        plan,
        api_key="api-key-value",
        raw_dir=tmp_path / "raw",
        bookmakers=("pinnacle",),
        capture_paid=True,
        max_paid_credits=0,
        fetch_fn=should_not_run,
    )

    assert snapshots == []
    assert errors[0]["reason"] == "paid_credit_cap_exceeded"


def test_makefile_exposes_historical_archive_target() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-historical-consensus-archive:" in text
    assert "scripts/kalshi_sports_historical_consensus_archive.py" in text
