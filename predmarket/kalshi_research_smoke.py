"""Offline smoke runner for the Kalshi research desk."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from predmarket.config import Config, GlobalConfig, VenuesConfig
from predmarket.kalshi_live_rank import KalshiLiveRankConfig, build_live_row, rank_live_rows
from predmarket.kalshi_paper_ledger import run_paper_ledger_audit
from predmarket.kalshi_research_cycle import (
    KalshiPaperConfig,
    KalshiResearchCycleConfig,
    run_kalshi_research_cycle,
)
from predmarket.store import PointInTimeStore


def build_smoke_rank_report(*, as_of_ts: Optional[float] = None) -> Dict[str, Any]:
    ts = float(as_of_ts or time.time())
    row = build_live_row(
        _smoke_market(ts),
        orderbook=_smoke_orderbook(),
        candlesticks=[],
        as_of_ts=ts,
    )
    return rank_live_rows(
        [row],
        config=KalshiLiveRankConfig(
            min_liquidity_usd=1.0,
            max_spread=0.10,
            min_fill_probability=0.10,
            min_liquidity_adjusted_edge=0.005,
            top_k=5,
        ),
        discovery_report={
            "run_id": "kalshi-smoke-discovery",
            "top_hypotheses": [
                {
                    "hypothesis_id": "kalshi-smoke-hypothesis",
                    "name": "synthetic-rules-edge",
                    "expression": "clip(market_implied + 0.20, 0.01, 0.99)",
                    "reward": 0.25,
                }
            ],
        },
    )


def run_kalshi_research_smoke(
    *,
    data_dir: Optional[Path] = None,
    reports_dir: Optional[Path] = None,
    as_of_ts: Optional[float] = None,
) -> Dict[str, Any]:
    root = Path(data_dir) if data_dir else Path(tempfile.mkdtemp(prefix="kalshi-research-smoke-"))
    out_dir = Path(reports_dir) if reports_dir else root / "reports"
    venues = VenuesConfig()
    venues.polymarket.enabled = False
    venues.kalshi.enabled = False
    venues.kalshi.execution_enabled = False
    app_config = Config(global_cfg=GlobalConfig(data_dir=root), venues=venues)
    rank_report = build_smoke_rank_report(as_of_ts=as_of_ts)
    store = PointInTimeStore(root)
    try:
        cycle_artifacts = run_kalshi_research_cycle(
            store,
            app_config=app_config,
            rank_report=rank_report,
            outcomes={"KXSMOKE-26JUN-TARGET": 1},
            config=KalshiResearchCycleConfig(
                paper=KalshiPaperConfig(
                    min_liquidity_adjusted_edge=0.005,
                    min_directional_edge=0.02,
                    settle_existing=True,
                )
            ),
            reports_dir=out_dir,
        )
        ledger_artifacts = run_paper_ledger_audit(store, reports_dir=out_dir)
    finally:
        store.close()

    return {
        "data_dir": str(root),
        "reports_dir": str(out_dir),
        "research_only": True,
        "execution_enabled": False,
        "rank_run_id": rank_report["run_id"],
        "cycle": {
            "run_id": cycle_artifacts.report["run_id"],
            "paper_intents": cycle_artifacts.report["paper"]["intended_count"],
            "settled": cycle_artifacts.report["settlement"]["settled_count"],
            "events": cycle_artifacts.report["events"]["count"],
            "json_path": str(cycle_artifacts.json_path),
            "markdown_path": str(cycle_artifacts.markdown_path),
        },
        "ledger": {
            "run_id": ledger_artifacts.report["run_id"],
            "count": ledger_artifacts.report["ledger"]["count"],
            "events": ledger_artifacts.report["events"]["count"],
            "readiness": ledger_artifacts.report["promotion_readiness"]["status"],
            "json_path": str(ledger_artifacts.json_path),
            "markdown_path": str(ledger_artifacts.markdown_path),
        },
    }


def _smoke_market(ts: float) -> Dict[str, Any]:
    close_ts = ts + 5 * 24 * 3600
    return {
        "ticker": "KXSMOKE-26JUN-TARGET",
        "event_ticker": "KXSMOKE-26JUN",
        "series_ticker": "KXSMOKE",
        "title": "Will the synthetic Kalshi smoke event resolve yes?",
        "subtitle": "Offline smoke market",
        "created_time": _iso_ts(ts - 14 * 24 * 3600),
        "updated_time": _iso_ts(ts),
        "open_time": _iso_ts(ts - 14 * 24 * 3600),
        "close_time": _iso_ts(close_ts),
        "expiration_time": _iso_ts(close_ts + 3600),
        "yes_bid_dollars": "0.4100",
        "yes_ask_dollars": "0.4600",
        "last_price_dollars": "0.4400",
        "previous_price_dollars": "0.4000",
        "volume_fp": "100000.00",
        "volume_24h_fp": "25000.00",
        "open_interest_fp": "120000.00",
        "liquidity_dollars": "125000.0000",
        "settlement_timer_seconds": 3600,
        "can_close_early": True,
        "fractional_trading_enabled": True,
        "rules_primary": "This smoke market resolves from a deterministic synthetic outcome.",
        "rules_secondary": "The smoke runner supplies the outcome locally and never submits orders.",
    }


def _smoke_orderbook() -> Dict[str, Any]:
    return {
        "orderbook_fp": {
            "yes_dollars": [["0.4200", "100.00"], ["0.3900", "200.00"]],
            "no_dollars": [["0.5500", "80.00"], ["0.5200", "120.00"]],
        }
    }


def _iso_ts(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run an offline Kalshi research desk smoke test")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--reports-dir", default=None)
    args = parser.parse_args(argv)
    report = run_kalshi_research_smoke(
        data_dir=Path(args.data_dir) if args.data_dir else None,
        reports_dir=Path(args.reports_dir) if args.reports_dir else None,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI smoke path
    raise SystemExit(main())
