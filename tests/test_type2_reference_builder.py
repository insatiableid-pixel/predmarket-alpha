from predmarket.type2_reference_builder import (
    build_type2_reference,
    parse_kalshi_game_start_utc,
    render_type2_reference_builder_markdown,
)


def _odds_event(commence, away="San Francisco Giants", home="Miami Marlins"):
    return {
        "sport_key": "baseball_mlb",
        "commence_time": commence,
        "away_team": away,
        "home_team": home,
        "bookmakers": [
            {
                "key": "fanduel",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": away, "price": -144},
                            {"name": home, "price": 122},
                        ],
                    }
                ],
            }
        ],
    }


def _kalshi_payload():
    return {
        "created_at_utc": "2026-06-20T23:02:03Z",
        "research_only": True,
        "execution_enabled": False,
        "all_scored": [
            {
                "ticker": "KXMLBGAME-26JUN201610SFMIA-SF",
                "event_ticker": "KXMLBGAME-26JUN201610SFMIA",
                "title": "San Francisco vs Miami Winner?",
            },
            {
                "ticker": "KXMLBGAME-26JUN201610SFMIA-MIA",
                "event_ticker": "KXMLBGAME-26JUN201610SFMIA",
                "title": "San Francisco vs Miami Winner?",
            },
            {
                "ticker": "KXMLBGAME-26JUN211340SFMIA-SF",
                "event_ticker": "KXMLBGAME-26JUN211340SFMIA",
                "title": "San Francisco vs Miami Winner?",
            },
            {
                "ticker": "KXMLBGAME-26JUN211340SFMIA-MIA",
                "event_ticker": "KXMLBGAME-26JUN211340SFMIA",
                "title": "San Francisco vs Miami Winner?",
            },
        ],
    }


def _meta():
    return {
        "created_at_utc": "2026-06-20T22:59:34Z",
        "raw_path": "/home/mrwatson/manual_drops/odds_api/baseball_mlb_current_20260620T225933Z.json",
        "sport_key": "baseball_mlb",
        "api_key_printed": False,
    }


def test_parse_kalshi_game_start_utc_uses_eastern_time():
    parsed = parse_kalshi_game_start_utc("KXMLBGAME-26JUN201610SFMIA")

    assert parsed is not None
    assert parsed.isoformat().replace("+00:00", "Z") == "2026-06-20T20:10:00Z"


def test_repeated_team_matchups_use_event_time_without_duplicate_tickers():
    reference, report = build_type2_reference(
        [
            _odds_event("2026-06-20T20:11:00Z"),
            _odds_event("2026-06-21T17:41:00Z"),
        ],
        _meta(),
        _kalshi_payload(),
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    tickers = [row["kalshi_ticker"] for row in reference["markets"]]
    assert report["status"] == "reference_built"
    assert len(tickers) == 4
    assert len(set(tickers)) == 4
    assert "KXMLBGAME-26JUN201610SFMIA-SF" in tickers
    assert "KXMLBGAME-26JUN211340SFMIA-SF" in tickers
    assert reference["quality"]["duplicate_kalshi_ticker_count"] == 0
    assert reference["quality"]["max_event_match_delta_seconds"] == 60.0
    assert report["safety"]["provider_api_calls"] is False


def test_out_of_tolerance_event_is_skipped():
    reference, report = build_type2_reference(
        [_odds_event("2026-06-22T20:11:00Z")],
        _meta(),
        _kalshi_payload(),
        run_id="unit",
        created_ts=1_800_000_000.0,
        max_event_delta_seconds=180.0,
    )

    assert reference["markets"] == []
    assert report["status"] == "reference_build_blocked_no_rows"
    assert report["skipped_events"][0]["reason"] == "kalshi_event_not_matched"


def test_missing_h2h_market_is_reported():
    event = _odds_event("2026-06-20T20:11:00Z")
    event["bookmakers"] = []
    reference, report = build_type2_reference(
        [event],
        _meta(),
        _kalshi_payload(),
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert reference["markets"] == []
    assert report["skipped_events"][0]["reason"] == "h2h_market_not_found"


def test_markdown_preserves_research_only_guardrails():
    _, report = build_type2_reference(
        [_odds_event("2026-06-20T20:11:00Z")],
        _meta(),
        _kalshi_payload(),
        run_id="unit",
        created_ts=1_800_000_000.0,
    )
    markdown = render_type2_reference_builder_markdown(report)

    assert "Mode: review-only" in markdown
    assert "does not authorize execution or account activity" in markdown
    forbidden = ["Kelly", "bankroll", "stake", "place a bet", "wager"]
    assert not any(term in markdown for term in forbidden)
