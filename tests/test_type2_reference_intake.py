import json

from predmarket.type2_reference_intake import (
    build_type2_reference_preflight,
    run_type2_reference_preflight,
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


def test_missing_sportsbook_reference_blocks_safely():
    report = build_type2_reference_preflight(
        _kalshi_payload(),
        None,
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "blocked_missing_sportsbook_reference"
    assert report["ready"] is False
    assert report["safety"]["provider_api_calls"] is False
    assert report["safety"]["account_or_order_paths"] is False
    assert report["summary"]["blocker_count"] == 1
    assert report["blockers"][0]["reason"] == "missing_sportsbook_reference"


def test_valid_explicit_mapping_passes_preflight():
    report = build_type2_reference_preflight(
        _kalshi_payload(),
        _sportsbook_payload(),
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "reference_ready"
    assert report["ready"] is True
    assert report["summary"]["valid_reference_count"] == 1
    assert report["references"][0]["kalshi_ticker"] == "KXMLBPROP-26JUN27-JUDGEHIT"
    assert report["references"][0]["valid"] is True
    assert all(gate["status"] == "pass" for gate in report["gates"])


def test_missing_kalshi_ticker_blocks_without_title_matching():
    report = build_type2_reference_preflight(
        _kalshi_payload(),
        _sportsbook_payload(kalshi_ticker="", title="Aaron Judge over 0.5 hits?"),
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "blocked_invalid_reference"
    assert report["ready"] is False
    assert report["summary"]["missing_ticker_count"] == 1
    assert report["references"][0]["blocker_reasons"] == ["missing_explicit_kalshi_ticker"]


def test_unknown_kalshi_ticker_blocks():
    report = build_type2_reference_preflight(
        _kalshi_payload(),
        _sportsbook_payload(kalshi_ticker="KXMLBPROP-26JUN27-NOTREAL"),
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "blocked_invalid_reference"
    assert report["summary"]["unknown_ticker_count"] == 1
    assert report["references"][0]["blocker_reasons"] == ["kalshi_ticker_not_found"]


def test_invalid_odds_block():
    report = build_type2_reference_preflight(
        _kalshi_payload(),
        _sportsbook_payload(yes={"american": -110}, no=None),
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "blocked_invalid_reference"
    assert report["summary"]["invalid_odds_count"] == 1
    assert "invalid_sportsbook_reference" in report["references"][0]["blocker_reasons"]


def test_cli_runner_writes_json_and_markdown(tmp_path):
    kalshi_path = tmp_path / "kalshi.json"
    sportsbook_path = tmp_path / "sportsbook.json"
    out_dir = tmp_path / "out"
    kalshi_path.write_text(json.dumps(_kalshi_payload()))
    sportsbook_path.write_text(json.dumps(_sportsbook_payload()))

    artifacts = run_type2_reference_preflight(
        kalshi_json=kalshi_path,
        sportsbook_json=sportsbook_path,
        output_dir=out_dir,
        run_id="unit-preflight",
    )

    loaded = json.loads(artifacts.json_path.read_text())
    markdown = artifacts.markdown_path.read_text()
    assert loaded["status"] == "reference_ready"
    assert loaded["ready"] is True
    assert artifacts.markdown_path.exists()
    assert "Mode: review-only" in markdown
    assert "manual review" in markdown
    forbidden = ["Kelly", "bankroll", "stake", "place a bet", "wager"]
    assert not any(term in markdown for term in forbidden)
