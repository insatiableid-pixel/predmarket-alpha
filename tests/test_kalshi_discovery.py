import json

import pytest

from predmarket.kalshi_dataset import KalshiResolvedDatasetBuilder, persist_rows
from predmarket.kalshi_discovery import (
    KalshiDiscoveryRunnerConfig,
    load_rows_for_discovery,
    render_markdown_report,
    run_kalshi_discovery,
    summarize_rows,
)
from predmarket.store import PointInTimeStore


def _market(ticker, event_ticker, outcome, month="06"):
    return {
        "ticker": ticker,
        "event_ticker": event_ticker,
        "series_ticker": "KXFED",
        "title": f"Will the Federal Reserve cut rates in month {month}?",
        "subtitle": "Fed target rate decision",
        "created_time": f"2026-{month}-01T00:00:00Z",
        "updated_time": f"2026-{month}-10T00:00:00Z",
        "open_time": f"2026-{month}-01T00:00:00Z",
        "close_time": f"2026-{month}-12T16:00:00Z",
        "expiration_time": f"2026-{month}-12T18:00:00Z",
        "settlement_ts": f"2026-{month}-12T19:00:00Z",
        "settlement_value_dollars": "1.0000" if outcome else "0.0000",
        "yes_bid_dollars": "0.5600",
        "yes_ask_dollars": "0.5800",
        "last_price_dollars": "0.5700",
        "previous_price_dollars": "0.5400",
        "volume_fp": "10000.00",
        "volume_24h_fp": "800.00",
        "open_interest_fp": "120000.00",
        "liquidity_dollars": "125000.0000",
        "settlement_timer_seconds": 3600,
        "can_close_early": True,
        "fractional_trading_enabled": True,
        "rules_primary": "This market resolves according to the Federal Reserve FOMC target rate announcement.",
        "rules_secondary": "Kalshi will use the official Federal Reserve statement.",
    }


def _candles(month, high_signal):
    return [
        {
            "end_period_ts": f"2026-{month}-10T00:00:00Z",
            "yes_bid": {"close_dollars": "0.4100" if high_signal else "0.2100"},
            "yes_ask": {"close_dollars": "0.4500" if high_signal else "0.2500"},
            "price": {
                "close_dollars": "0.4300" if high_signal else "0.2300",
                "previous_dollars": "0.4000" if high_signal else "0.3000",
            },
            "volume_fp": "800.00",
            "open_interest_fp": "120000.00",
        },
        {
            "end_period_ts": f"2026-{month}-11T00:00:00Z",
            "yes_bid": {"close_dollars": "0.7600" if high_signal else "0.1200"},
            "yes_ask": {"close_dollars": "0.8000" if high_signal else "0.1600"},
            "price": {
                "close_dollars": "0.7800" if high_signal else "0.1400",
                "previous_dollars": "0.4300" if high_signal else "0.2300",
            },
            "volume_fp": "1200.00",
            "open_interest_fp": "150000.00",
        },
    ]


def _rows():
    builder = KalshiResolvedDatasetBuilder()
    markets = []
    candles = {}
    for idx, month in enumerate(["06", "07", "08", "09", "10", "11"]):
        outcome = idx % 2 == 0
        ticker = f"KXFED-26{month}-TARGET"
        markets.append(_market(ticker, f"KXFED-26{month}", outcome, month))
        candles[ticker] = _candles(month, high_signal=outcome)
    return builder.build_rows(markets, candlesticks_by_ticker=candles).rows


def test_summarize_rows_counts_kalshi_panel():
    rows = _rows()
    summary = summarize_rows(rows)

    assert summary["n_rows"] == 12
    assert summary["n_markets"] == 6
    assert summary["n_events"] == 6
    assert summary["outcome_yes_rate"] == 0.5
    assert summary["domains"]["federal_reserve"] == 12


def test_kalshi_discovery_runner_writes_json_and_markdown(tmp_path):
    store = PointInTimeStore(tmp_path)
    try:
        persist_rows(store, _rows())
        artifacts = run_kalshi_discovery(
            store,
            config=KalshiDiscoveryRunnerConfig(
                n_trajectories=1,
                iterations_per_trajectory=3,
                top_k=2,
                min_support=4,
                evolution_interval=0,
                backtest_min_train_size=4,
                backtest_test_size=2,
                backtest_step_size=2,
            ),
        )
    finally:
        store.close()

    assert artifacts.json_path.exists()
    assert artifacts.markdown_path.exists()
    assert artifacts.report["row_summary"]["n_rows"] == 12
    assert artifacts.report["top_hypotheses"]
    loaded = json.loads(artifacts.json_path.read_text())
    assert loaded["run_id"] == artifacts.report["run_id"]
    assert "# Kalshi Discovery Report" in artifacts.markdown_path.read_text()


def test_kalshi_discovery_filters_non_kalshi_rows(tmp_path):
    rows = _rows()
    rows.append({**rows[0], "row_id": "pm-row", "venue": "Polymarket", "market_id": "PM-1"})
    store = PointInTimeStore(tmp_path)
    try:
        persist_rows(store, rows)
        loaded = load_rows_for_discovery(store, KalshiDiscoveryRunnerConfig())
    finally:
        store.close()

    assert len(loaded) == len(rows) - 1
    assert all(row["venue"] == "Kalshi" for row in loaded)


def test_kalshi_discovery_requires_rows(tmp_path):
    store = PointInTimeStore(tmp_path)
    try:
        with pytest.raises(ValueError, match="No stored Kalshi resolved rows"):
            run_kalshi_discovery(store)
    finally:
        store.close()


def test_render_markdown_report_handles_empty_top_hypotheses():
    md = render_markdown_report(
        {
            "run_id": "unit",
            "row_summary": {"n_rows": 0, "n_markets": 0, "n_events": 0, "outcome_yes_rate": 0.0},
            "top_hypotheses": [],
        }
    )

    assert "No hypotheses evaluated" in md
