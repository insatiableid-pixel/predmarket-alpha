from predmarket.type2_candidate_disposition import (
    build_type2_candidate_disposition,
    render_type2_candidate_disposition_markdown,
)


def _paper_report(status="REVIEW_ONLY_PASS"):
    return {
        "status": "review_candidates_present",
        "research_only": True,
        "execution_enabled": False,
        "candidates": [
            {
                "reference_id": "ref-1",
                "kalshi_ticker": "KXMLBGAME-26JUN201605SDTEX-SD",
                "event_ticker": "KXMLBGAME-26JUN201605SDTEX",
                "title": "San Diego vs Texas Winner?",
                "review_status": status,
                "kalshi_midpoint": 0.62,
                "sportsbook_no_vig_yes": 0.49,
                "review_only_net_divergence": 0.12,
                "blockers": [],
            }
        ],
    }


def _sportsbook_reference(capture="2026-06-20T19:55:00Z", commence="2026-06-20T20:06:00Z"):
    return {
        "schema_version": 1,
        "markets": [
            {
                "reference_id": "ref-1",
                "kalshi_ticker": "KXMLBGAME-26JUN201605SDTEX-SD",
                "sportsbook": "manual-reference",
                "team": "San Diego Padres",
                "opponent": "Texas Rangers",
                "capture_time_utc": capture,
                "commence_time_utc": commence,
                "yes": {"american": -110},
                "no": {"american": -110},
            }
        ],
    }


def _kalshi_payload(capture="2026-06-20T19:56:00Z"):
    return {
        "created_at_utc": capture,
        "research_only": True,
        "execution_enabled": False,
        "all_scored": [],
    }


def test_pregame_pass_is_kept_as_review_candidate():
    report = build_type2_candidate_disposition(
        _paper_report(),
        _sportsbook_reference(),
        _kalshi_payload(),
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "candidate_disposition_review_candidates_present"
    assert report["summary"]["kept_review_candidate"] == 1
    assert report["dispositions"][0]["disposition"] == "KEPT_REVIEW_CANDIDATE"
    assert report["safety"]["provider_api_calls"] is False
    assert report["safety"]["account_or_order_paths"] is False


def test_after_start_sportsbook_capture_is_downgraded():
    report = build_type2_candidate_disposition(
        _paper_report(),
        _sportsbook_reference(capture="2026-06-20T20:06:00Z"),
        _kalshi_payload(),
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "candidate_disposition_all_passes_downgraded"
    assert report["summary"]["downgraded_temporal_mismatch"] == 1
    assert report["dispositions"][0]["disposition"] == "DOWNGRADED_TEMPORAL_MISMATCH"


def test_after_start_kalshi_capture_is_downgraded():
    report = build_type2_candidate_disposition(
        _paper_report(),
        _sportsbook_reference(),
        _kalshi_payload(capture="2026-06-20T20:07:00Z"),
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert report["summary"]["downgraded_temporal_mismatch"] == 1
    assert report["dispositions"][0]["reason"] == "At least one snapshot was captured at or after first pitch."


def test_missing_timing_requires_manual_review():
    report = build_type2_candidate_disposition(
        _paper_report(),
        _sportsbook_reference(capture=None),
        _kalshi_payload(),
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "candidate_disposition_manual_timing_review"
    assert report["summary"]["manual_review_timing_unknown"] == 1


def test_duplicate_reference_tickers_require_manual_review():
    sportsbook = _sportsbook_reference()
    sportsbook["markets"].append(dict(sportsbook["markets"][0], reference_id="ref-duplicate"))
    report = build_type2_candidate_disposition(
        _paper_report(),
        sportsbook,
        _kalshi_payload(),
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "candidate_disposition_manual_timing_review"
    assert report["summary"]["duplicate_reference_ticker_count"] == 1
    assert report["dispositions"][0]["reason"] == "Multiple sportsbook reference rows were found for this explicit ticker."


def test_watch_only_remains_watch_only_when_timing_passes():
    report = build_type2_candidate_disposition(
        _paper_report(status="REVIEW_ONLY_WATCH"),
        _sportsbook_reference(),
        _kalshi_payload(),
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "candidate_disposition_watch_only"
    assert report["summary"]["watch_only"] == 1


def test_watch_only_temporal_downgrade_does_not_claim_passes_downgraded():
    report = build_type2_candidate_disposition(
        _paper_report(status="REVIEW_ONLY_WATCH"),
        _sportsbook_reference(capture="2026-06-20T20:06:00Z"),
        _kalshi_payload(),
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "candidate_disposition_watch_only"
    assert report["summary"]["original_review_only_pass"] == 0
    assert report["summary"]["downgraded_temporal_mismatch"] == 1


def test_markdown_preserves_review_only_guardrails():
    report = build_type2_candidate_disposition(
        _paper_report(),
        _sportsbook_reference(),
        _kalshi_payload(),
        run_id="unit",
        created_ts=1_800_000_000.0,
    )
    markdown = render_type2_candidate_disposition_markdown(report)

    assert "Mode: review-only" in markdown
    assert "does not authorize execution or account activity" in markdown
    forbidden = ["Kelly", "bankroll", "stake", "place a bet", "wager"]
    assert not any(term in markdown for term in forbidden)
