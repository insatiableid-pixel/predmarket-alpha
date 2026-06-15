import json

from predmarket.kalshi_live_rank import (
    KalshiLiveRankConfig,
    build_live_row,
    orderbook_to_yes_bids_and_asks,
    persist_live_snapshot,
    rank_live_rows,
    run_kalshi_live_rank,
    write_live_rank_report,
)
from predmarket.store import PointInTimeStore


AS_OF_TS = 1781550000.0


def _market(**overrides):
    base = {
        "ticker": "KXFED-26JUN-TARGET",
        "event_ticker": "KXFED-26JUN",
        "series_ticker": "KXFED",
        "title": "Will the Federal Reserve cut rates above 25 bps in June 2026?",
        "subtitle": "Fed target rate decision",
        "created_time": "2026-06-01T00:00:00Z",
        "updated_time": "2026-06-15T12:00:00Z",
        "open_time": "2026-06-01T00:00:00Z",
        "close_time": "2026-06-20T16:00:00Z",
        "expiration_time": "2026-06-20T18:00:00Z",
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
        "rules_primary": "This market resolves according to the official Federal Reserve FOMC statement.",
        "rules_secondary": "Kalshi will use the official target range announcement.",
    }
    base.update(overrides)
    return base


def _orderbook():
    return {
        "orderbook_fp": {
            "yes_dollars": [["0.4200", "100.00"], ["0.3900", "200.00"]],
            "no_dollars": [["0.5500", "80.00"], ["0.5200", "120.00"]],
        }
    }


def _candles():
    return [
        {
            "end_period_ts": AS_OF_TS - 3600,
            "yes_bid": {"close_dollars": "0.4100"},
            "yes_ask": {"close_dollars": "0.4600"},
            "price": {"close_dollars": "0.4400", "previous_dollars": "0.4000"},
            "volume_fp": "1200.00",
            "open_interest_fp": "120000.00",
        }
    ]


def _discovery_report(expression="clip(market_implied + 0.20, 0.01, 0.99)"):
    return {
        "run_id": "discovery-unit",
        "top_hypotheses": [
            {
                "hypothesis_id": "hyp-unit",
                "name": "unit-edge",
                "expression": expression,
                "reward": 0.25,
            }
        ],
    }


def test_build_live_row_uses_orderbook_and_excludes_labels():
    row = build_live_row(
        _market(),
        orderbook=_orderbook(),
        candlesticks=_candles(),
        as_of_ts=AS_OF_TS,
    )

    assert row["venue"] == "Kalshi"
    assert row["market_id"] == "KXFED-26JUN-TARGET"
    assert row["orderbook_available"] == 1.0
    assert row["yes_bid"] == 0.42
    assert row["yes_ask"] == 0.45
    assert round(row["bid_ask_spread"], 4) == 0.03
    assert row["market_implied"] == 0.44
    assert row["rules_has_threshold_terms"] == 1.0
    assert row["square_money_vulnerability"] > 0.0
    assert "outcome" not in row
    assert "resolved_ts" not in row


def test_orderbook_converts_no_bids_to_yes_asks():
    bids, asks = orderbook_to_yes_bids_and_asks(_orderbook())

    assert bids[0]["price"] == 0.42
    assert asks[0]["price"] == 0.45
    assert asks[0]["size"] == 80.0


def test_rank_live_rows_applies_discovery_hypotheses():
    row = build_live_row(
        _market(),
        orderbook=_orderbook(),
        candlesticks=_candles(),
        as_of_ts=AS_OF_TS,
    )
    report = rank_live_rows(
        [row],
        config=KalshiLiveRankConfig(
            min_liquidity_usd=1.0,
            max_spread=0.10,
            min_fill_probability=0.10,
            min_liquidity_adjusted_edge=0.005,
        ),
        discovery_report=_discovery_report(),
    )

    top = report["top_opportunities"][0]
    assert top["side"] == "YES"
    assert top["venue"] == "Kalshi"
    assert top["model_probability"] > top["market_probability"]
    assert top["used_hypotheses"]
    assert "watchlist_only_no_usable_discovery_hypothesis" not in top["blocking_reasons"]
    assert report["research_only"] is True
    assert report["execution_enabled"] is False


def test_rank_live_rows_falls_back_to_watchlist_vulnerability():
    row = build_live_row(
        _market(),
        orderbook={},
        candlesticks=[],
        as_of_ts=AS_OF_TS,
    )
    report = rank_live_rows([row], discovery_report=None)

    top = report["top_opportunities"][0]
    assert top["scoring_mode"] == "watchlist_vulnerability"
    assert "watchlist_only_no_usable_discovery_hypothesis" in top["blocking_reasons"]
    assert "orderbook_not_available" in top["blocking_reasons"]


def test_live_rank_report_writes_json_and_markdown(tmp_path):
    row = build_live_row(
        _market(),
        orderbook=_orderbook(),
        candlesticks=_candles(),
        as_of_ts=AS_OF_TS,
    )
    report = rank_live_rows([row], discovery_report=_discovery_report())
    artifacts = write_live_rank_report(report, reports_dir=tmp_path)

    assert artifacts.json_path.exists()
    assert artifacts.markdown_path.exists()
    loaded = json.loads(artifacts.json_path.read_text())
    assert loaded["run_id"] == report["run_id"]
    assert "# Live Kalshi Rank Report" in artifacts.markdown_path.read_text()


def test_run_kalshi_live_rank_loads_latest_discovery_report(tmp_path, mock_config):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "discovery-unit.json").write_text(json.dumps(_discovery_report()))
    row = build_live_row(
        _market(),
        orderbook=_orderbook(),
        candlesticks=_candles(),
        as_of_ts=AS_OF_TS,
    )
    store = PointInTimeStore(tmp_path / "data")
    try:
        artifacts = run_kalshi_live_rank(
            store,
            app_config=mock_config,
            rows=[row],
            reports_dir=reports_dir,
        )
    finally:
        store.close()

    assert artifacts.report["discovery_report_ref"]["run_id"] == "discovery-unit"
    assert artifacts.report["top_opportunities"][0]["used_hypotheses"]


def test_persist_live_snapshot_writes_point_in_time_context(tmp_path):
    row = build_live_row(
        _market(),
        orderbook=_orderbook(),
        candlesticks=_candles(),
        as_of_ts=AS_OF_TS,
    )
    store = PointInTimeStore(tmp_path)
    try:
        persist_live_snapshot(store, row, market=_market(), orderbook=_orderbook())
        context = store.load_context(row["event_id"], row["market_id"], AS_OF_TS)
    finally:
        store.close()

    assert context["snapshot"]["contract_id"] == row["market_id"]
    assert context["orderbook"]["bids"][0]["price"] == 0.42
    assert context["orderbook"]["asks"][0]["price"] == 0.45
