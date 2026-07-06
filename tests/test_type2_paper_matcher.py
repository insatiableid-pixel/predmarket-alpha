import json

from predmarket.type2_paper_matcher import (
    build_type2_paper_match_report,
    implied_probability_from_odds,
    no_vig_midpoint_from_reference,
    run_type2_paper_matcher,
)


def _kalshi_payload():
    return {
        "all_scored": [
            {
                "ticker": "KXMLBPROP-26JUN27-JUDGEHIT",
                "event_ticker": "KXMLBPROP-26JUN27",
                "title": "Aaron Judge over 0.5 hits?",
                "bid": 0.39,
                "ask": 0.45,
            }
        ]
    }


def _sportsbook_payload(**reference_overrides):
    reference = {
        "reference_id": "judge-hit-reference",
        "kalshi_ticker": "KXMLBPROP-26JUN27-JUDGEHIT",
        "yes": {"american": -165},
        "no": {"american": 145},
    }
    reference.update(reference_overrides)
    return {"schema_version": 1, "markets": [reference]}


def test_american_odds_to_implied_probability():
    assert round(implied_probability_from_odds({"american": -110}), 6) == 0.52381
    assert round(implied_probability_from_odds({"american": 130}), 6) == 0.434783


def test_decimal_odds_no_vig_midpoint():
    midpoint = no_vig_midpoint_from_reference(
        {
            "yes": {"decimal": 1.80},
            "no": {"decimal": 2.10},
        }
    )

    assert round(midpoint["raw_yes_implied"], 6) == 0.555556
    assert round(midpoint["raw_no_implied"], 6) == 0.47619
    assert round(midpoint["no_vig_yes"] + midpoint["no_vig_no"], 6) == 1.0


def test_probability_no_vig_midpoint():
    midpoint = no_vig_midpoint_from_reference(
        {
            "yes_implied_probability": 0.58,
            "no_implied_probability": 0.47,
        }
    )

    assert round(midpoint["overround"], 6) == 0.05
    assert round(midpoint["no_vig_yes"], 6) == 0.555
    assert round(midpoint["no_vig_no"], 6) == 0.445


def test_explicit_ticker_match_produces_review_only_candidate():
    report = build_type2_paper_match_report(
        _kalshi_payload(),
        _sportsbook_payload(),
        run_id="unit",
        created_ts=1_800_000_000.0,
        min_net_divergence=0.08,
    )

    candidate = report["candidates"][0]
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["status"] == "review_candidates_present"
    assert candidate["kalshi_ticker"] == "KXMLBPROP-26JUN27-JUDGEHIT"
    assert candidate["review_status"] == "REVIEW_ONLY_PASS"
    assert round(candidate["kalshi_midpoint"], 6) == 0.42
    assert candidate["review_only_net_divergence"] > 0.08


def test_missing_sportsbook_reference_blocks_without_guessing():
    report = build_type2_paper_match_report(
        _kalshi_payload(),
        None,
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "blocked_missing_sportsbook_reference"
    assert report["candidates"] == []
    assert report["blockers"][0]["reason"] == "missing_sportsbook_reference"


def test_unmapped_reference_does_not_fuzzy_match_title():
    sportsbook = _sportsbook_payload(kalshi_ticker="KXMLBPROP-26JUN27-NOTREAL")
    report = build_type2_paper_match_report(
        _kalshi_payload(),
        sportsbook,
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "blocked_no_matched_references"
    assert report["candidates"] == []
    assert report["blockers"][0]["reason"] == "kalshi_ticker_not_found"


def test_cli_runner_writes_review_only_reports(tmp_path):
    kalshi_path = tmp_path / "kalshi.json"
    sportsbook_path = tmp_path / "sportsbook.json"
    out_dir = tmp_path / "out"
    kalshi_path.write_text(json.dumps(_kalshi_payload()))
    sportsbook_path.write_text(json.dumps(_sportsbook_payload()))

    artifacts = run_type2_paper_matcher(
        kalshi_json=kalshi_path,
        sportsbook_json=sportsbook_path,
        output_dir=out_dir,
        run_id="unit-type2",
        min_net_divergence=0.08,
    )

    assert artifacts.json_path.exists()
    assert artifacts.markdown_path.exists()
    loaded = json.loads(artifacts.json_path.read_text())
    markdown = artifacts.markdown_path.read_text()
    assert loaded["safety"]["provider_api_calls"] is False
    assert loaded["safety"]["account_or_order_paths"] is False
    assert "Mode: review-only" in markdown
    assert (
        "`REVIEW_ONLY_PASS` means the row is eligible for manual research review only" in markdown
    )
    forbidden = ["Kelly", "bankroll", "stake", "place a bet", "wager"]
    assert not any(term in markdown for term in forbidden)
