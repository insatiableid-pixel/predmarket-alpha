from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "kalshi_sports_historical_consensus_backfill.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_sports_historical_consensus_backfill", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def feasibility() -> dict[str, object]:
    return {
        "status": "kalshi_sports_historical_consensus_feasibility_ready_paid_access_unverified",
        "summary": {
            "skew_gate_pass": True,
            "max_allowed_skew_seconds": 180,
            "paid_access_verified": False,
        },
    }


def market(index: int, *, result: str = "yes") -> dict[str, object]:
    day = ((index - 1) % 28) + 1
    minute = (index - 1) % 60
    return {
        "ticker": f"KXMLBGAME-26JUL{day:02d}{index:03d}AAA-BBB-BBB",
        "event_ticker": f"KXMLBGAME-26JUL{day:02d}{index:03d}AAA-BBB",
        "series_ticker": "KXMLBGAME",
        "result": result,
        "settlement_value_dollars": "1.0000" if result == "yes" else "0.0000",
        "settlement_ts": f"2026-07-{day:02d}T20:{minute:02d}:00Z",
        "close_time": f"2026-07-{day:02d}T20:{minute:02d}:00Z",
    }


def candle(index: int, price: float = 0.60) -> dict[str, object]:
    day = ((index - 1) % 28) + 1
    minute = (index - 1) % 60
    return {
        "end_period_ts": f"2026-07-{day:02d}T12:{minute:02d}:00Z",
        "price": {"close": price},
        "yes_bid": {"close": price - 0.01},
        "yes_ask": {"close": price + 0.01},
    }


def historical_row(index: int, *, skew_seconds: int = 0) -> dict[str, object]:
    day = ((index - 1) % 28) + 1
    minute = (index - 1) % 60
    observed = f"2026-07-{day:02d}T12:{minute:02d}:00Z"
    return {
        "contract_ticker": market(index)["ticker"],
        "event_ticker": market(index)["event_ticker"],
        "series_ticker": "KXMLBGAME",
        "side": "yes",
        "observed_utc": observed,
        "provider_snapshot_utc": observed,
        "timestamp_skew_seconds": skew_seconds,
        "consensus_probability_for_side": 0.72,
        "book_count": 4,
        "distinct_books": ["pinnacle", "betfair_ex_uk", "matchbook", "smarkets"],
    }


def test_historical_consensus_backfill_reaches_divergence_fdr_grid(tmp_path: Path) -> None:
    module = load_module()
    markets = [market(i, result="yes") for i in range(1, 41)]
    rows = [historical_row(i) for i in range(1, 41)]
    candle_map = {str(row["ticker"]): [candle(i, 0.60)] for i, row in enumerate(markets, start=1)}
    source_path = tmp_path / "historical.json"
    source_path.write_text(json.dumps({"rows": rows}), encoding="utf-8")

    report = module.build_historical_consensus_backfill(
        feasibility_report=feasibility(),
        historical_consensus_rows=rows,
        markets=markets,
        candlesticks_by_ticker=candle_map,
        generated_utc="2026-07-07T00:00:00Z",
        historical_consensus_path=source_path,
    )

    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["account_or_order_paths"] is False
    assert report["summary"]["valid_observation_count"] == 40
    assert report["summary"]["settlement_label_count"] == 40
    assert report["summary"]["tested_hypothesis_count"] > 0
    assert report["summary"]["fdr_survivor_count"] > 0
    assert (
        report["status"]
        == "kalshi_sports_historical_consensus_backfill_ready_with_research_candidates"
    )
    assert all(row["usable"] is False for row in report["observations"])


def test_historical_consensus_backfill_blocks_missing_archive() -> None:
    module = load_module()

    report = module.build_historical_consensus_backfill(
        feasibility_report=feasibility(),
        historical_consensus_rows=[],
        markets=[market(1)],
        candlesticks_by_ticker={market(1)["ticker"]: [candle(1)]},
        generated_utc="2026-07-07T00:00:00Z",
    )

    assert (
        report["status"]
        == "kalshi_sports_historical_consensus_backfill_blocked_missing_historical_archive"
    )
    assert report["summary"]["valid_observation_count"] == 0
    assert report["summary"]["tested_hypothesis_count"] == 0


def test_historical_consensus_backfill_rejects_provider_skew() -> None:
    module = load_module()
    rows = [historical_row(1, skew_seconds=181)]

    report = module.build_historical_consensus_backfill(
        feasibility_report=feasibility(),
        historical_consensus_rows=rows,
        markets=[market(1)],
        candlesticks_by_ticker={market(1)["ticker"]: [candle(1)]},
        generated_utc="2026-07-07T00:00:00Z",
    )

    assert (
        report["status"] == "kalshi_sports_historical_consensus_backfill_blocked_no_valid_join"
    )
    assert report["summary"]["join_blocker_count"] == 1
    assert report["join_blockers"][0]["reason"] == "provider_snapshot_skew_exceeds_policy"


def test_historical_consensus_backfill_rejects_kalshi_quote_skew() -> None:
    module = load_module()
    bad_candle = candle(1)
    bad_candle["end_period_ts"] = "2026-07-01T00:00:00Z"

    report = module.build_historical_consensus_backfill(
        feasibility_report=feasibility(),
        historical_consensus_rows=[historical_row(1)],
        markets=[market(1)],
        candlesticks_by_ticker={market(1)["ticker"]: [bad_candle]},
        generated_utc="2026-07-07T00:00:00Z",
    )

    assert (
        report["status"] == "kalshi_sports_historical_consensus_backfill_blocked_no_valid_join"
    )
    assert report["join_blockers"][0]["reason"] == "missing_kalshi_historical_quote"


def test_makefile_exposes_historical_consensus_backfill_target() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-historical-consensus-backfill:" in text
    assert "scripts/kalshi_sports_historical_consensus_backfill.py" in text
