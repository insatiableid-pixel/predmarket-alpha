import json

from predmarket.type2_threshold_sensitivity import (
    build_type2_threshold_sensitivity,
    run_type2_threshold_sensitivity,
)


def _paper_report():
    return {
        "status": "watch_only_no_review_candidates",
        "config": {"min_net_divergence": 0.10},
        "research_only": True,
        "execution_enabled": False,
        "candidates": [
            {
                "reference_id": "a",
                "kalshi_ticker": "KXMLBGAME-A",
                "title": "A wins?",
                "review_status": "REVIEW_ONLY_WATCH",
                "kalshi_midpoint": 0.60,
                "sportsbook_no_vig_yes": 0.58,
                "raw_divergence": 0.02,
                "review_only_net_divergence": 0.015,
                "threshold": 0.10,
            },
            {
                "reference_id": "b",
                "kalshi_ticker": "KXMLBGAME-B",
                "title": "B wins?",
                "review_status": "REVIEW_ONLY_WATCH",
                "kalshi_midpoint": 0.51,
                "sportsbook_no_vig_yes": 0.50,
                "raw_divergence": 0.01,
                "review_only_net_divergence": 0.005,
                "threshold": 0.10,
            },
            {
                "reference_id": "c",
                "kalshi_ticker": "KXMLBGAME-C",
                "title": "C wins?",
                "review_status": "REVIEW_ONLY_WATCH",
                "kalshi_midpoint": 0.50,
                "sportsbook_no_vig_yes": 0.50,
                "raw_divergence": 0.0,
                "review_only_net_divergence": -0.005,
                "threshold": 0.10,
            },
        ],
    }


def _disposition_report():
    return {
        "status": "candidate_disposition_watch_only",
        "dispositions": [
            {"kalshi_ticker": "KXMLBGAME-A", "disposition": "WATCH_ONLY"},
            {"kalshi_ticker": "KXMLBGAME-B", "disposition": "WATCH_ONLY"},
            {"kalshi_ticker": "KXMLBGAME-C", "disposition": "DOWNGRADED_TEMPORAL_MISMATCH"},
        ],
    }


def test_threshold_sensitivity_summarizes_clean_watch_only_gap():
    report = build_type2_threshold_sensitivity(
        _paper_report(),
        _disposition_report(),
        thresholds=[0.10, 0.015, 0.005, 0.0],
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["status"] == "threshold_sensitivity_no_current_threshold_candidates"
    assert report["summary"]["timing_clean_candidate_count"] == 2
    assert report["summary"]["temporal_downgrade_count"] == 1
    assert report["summary"]["current_threshold_would_pass_count"] == 0
    assert report["summary"]["max_positive_review_only_net_divergence"] == 0.015
    assert report["summary"]["gap_to_current_threshold"] == 0.085
    grid = {row["threshold"]: row["would_pass_count"] for row in report["threshold_grid"]}
    assert grid[0.1] == 0
    assert grid[0.015] == 1
    assert grid[0.005] == 2
    assert report["top_candidates"][0]["kalshi_ticker"] == "KXMLBGAME-A"


def test_threshold_sensitivity_runner_writes_review_only_artifacts(tmp_path):
    paper_path = tmp_path / "paper.json"
    disposition_path = tmp_path / "disposition.json"
    out_dir = tmp_path / "out"
    paper_path.write_text(json.dumps(_paper_report()), encoding="utf-8")
    disposition_path.write_text(json.dumps(_disposition_report()), encoding="utf-8")

    artifacts = run_type2_threshold_sensitivity(
        paper_matcher_json=paper_path,
        disposition_json=disposition_path,
        output_dir=out_dir,
        run_id="unit-threshold",
        thresholds=[0.10, 0.005],
    )

    loaded = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    markdown = artifacts.markdown_path.read_text(encoding="utf-8")
    assert loaded["safety"]["provider_api_calls"] is False
    assert loaded["safety"]["account_or_order_paths"] is False
    assert "Threshold rows are hypothetical diagnostics only." in markdown
    assert "does not change thresholds" in markdown
    forbidden = ["Kelly", "bankroll", "stake", "place a bet", "wager"]
    assert not any(term in markdown for term in forbidden)
