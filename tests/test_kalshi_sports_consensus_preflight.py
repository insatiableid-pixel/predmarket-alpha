from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from predmarket.sports_consensus import build_sports_consensus_preflight

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_consensus_preflight.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_script_module():
    spec = importlib.util.spec_from_file_location("kalshi_sports_consensus_preflight", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _kalshi_payload():
    return {
        "created_at_utc": "2026-07-04T18:00:00Z",
        "all_scored": [
            {
                "ticker": "KXMLBGAME-26JUL041910NYYTOR-NYY",
                "event_ticker": "KXMLBGAME-26JUL041910NYYTOR",
                "title": "Yankees beat Blue Jays?",
                "bid": 0.48,
                "ask": 0.52,
            }
        ],
    }


def _book_row(
    book_id: str, *, source_type: str = "sportsbook", captured: str = "2026-07-04T18:01:00Z"
):
    return {
        "reference_id": f"nyy-{book_id}",
        "kalshi_ticker": "KXMLBGAME-26JUL041910NYYTOR-NYY",
        "side": "yes",
        "book_id": book_id,
        "source_type": source_type,
        "capture_time_utc": captured,
        "yes": {"american": -120},
        "no": {"american": 110},
    }


def test_multi_book_timestamp_matched_no_vig_consensus_passes() -> None:
    report = build_sports_consensus_preflight(
        _kalshi_payload(),
        {"rows": [_book_row("pinnacle"), _book_row("circa")]},
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "sports_consensus_preflight_ready"
    assert report["ready"] is True
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["summary"]["valid_candidate_count"] == 1
    candidate = report["candidates"][0]
    assert candidate["valid"] is True
    assert candidate["distinct_books"] == ["circa", "pinnacle"]
    assert round(candidate["consensus_no_vig_yes_probability"], 6) == 0.534632
    assert all(gate["status"] == "pass" for gate in report["gates"])


def test_single_book_reference_blocks_as_not_consensus() -> None:
    report = build_sports_consensus_preflight(
        _kalshi_payload(),
        {"rows": [_book_row("pinnacle")]},
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert report["status"] == "sports_consensus_preflight_blocked_no_valid_consensus_rows"
    assert report["ready"] is False
    assert report["summary"]["single_book_blocker_count"] == 1
    assert "insufficient_distinct_books" in report["candidates"][0]["blocker_reasons"]


def test_projection_model_rows_are_rejected_as_primary_sports_probability_source() -> None:
    report = build_sports_consensus_preflight(
        _kalshi_payload(),
        {"rows": [_book_row("projection-a", source_type="elo"), _book_row("circa")]},
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    assert report["ready"] is False
    assert report["summary"]["projection_source_blocker_count"] == 1
    assert "forbidden_projection_primary_source" in report["candidates"][0]["blocker_reasons"]


def test_missing_timestamp_or_exact_mapping_blocks() -> None:
    bad_timestamp = _book_row("pinnacle", captured="")
    unknown_ticker = _book_row("circa")
    unknown_ticker["kalshi_ticker"] = "KXMLBGAME-26JUL041910NYYTOR-NOTREAL"

    report = build_sports_consensus_preflight(
        _kalshi_payload(),
        {"rows": [bad_timestamp, unknown_ticker]},
        run_id="unit",
        created_ts=1_800_000_000.0,
    )

    reasons = {blocker["reason"] for blocker in report["blockers"]}
    assert report["ready"] is False
    assert "missing_reference_timestamp" in reasons
    assert "kalshi_ticker_not_found" in reasons


def test_cli_writes_latest_research_only_artifacts(tmp_path: Path) -> None:
    module = load_script_module()
    kalshi_path = tmp_path / "kalshi.json"
    consensus_path = tmp_path / "consensus.json"
    out_dir = tmp_path / "out"
    latest_json = module.MACRO_DIR / "latest-kalshi-sports-consensus-preflight.json"
    latest_before = latest_json.read_text(encoding="utf-8") if latest_json.exists() else None
    kalshi_path.write_text(json.dumps(_kalshi_payload()), encoding="utf-8")
    consensus_path.write_text(
        json.dumps({"rows": [_book_row("pinnacle"), _book_row("circa")]}),
        encoding="utf-8",
    )

    report = module.run_sports_consensus_preflight(
        kalshi_json=kalshi_path,
        consensus_json=consensus_path,
        output_dir=out_dir,
        run_id="unit",
        write=True,
    )

    paths = report["output_paths"]
    loaded = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert loaded["status"] == "sports_consensus_preflight_ready"
    assert loaded["safety"]["account_or_order_paths"] is False
    assert "sharp timestamp-matched no-vig consensus" in markdown
    forbidden = ["Kelly", "bankroll", "place a bet", "wager"]
    assert not any(term in markdown for term in forbidden)
    assert "latest_json_path" not in paths
    latest_after = latest_json.read_text(encoding="utf-8") if latest_json.exists() else None
    assert latest_after == latest_before


def test_makefile_target_exists() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-consensus-preflight" in text
    assert "scripts/kalshi_sports_consensus_preflight.py" in text
