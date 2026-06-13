from predmarket.discovery import AgenticDiscoveryConfig, AgenticSignalDiscoveryEngine
from predmarket.kalshi_dataset import (
    KalshiResolvedDatasetBuilder,
    infer_resolution_source,
    persist_rows,
)
from predmarket.store import PointInTimeStore


def _market(**overrides):
    base = {
        "ticker": "KXFED-26JUN-TARGET",
        "event_ticker": "KXFED-26JUN",
        "series_ticker": "KXFED",
        "title": "Will the Federal Reserve cut rates in June 2026?",
        "subtitle": "Fed target rate decision",
        "created_time": "2026-05-01T00:00:00Z",
        "updated_time": "2026-06-10T00:00:00Z",
        "open_time": "2026-05-01T00:00:00Z",
        "close_time": "2026-06-12T16:00:00Z",
        "expiration_time": "2026-06-12T18:00:00Z",
        "settlement_ts": "2026-06-12T19:00:00Z",
        "settlement_value_dollars": "1.0000",
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
    base.update(overrides)
    return base


def _candles():
    return [
        {
            "end_period_ts": 1781049600,
            "yes_bid": {"close_dollars": "0.4300"},
            "yes_ask": {"close_dollars": "0.4700"},
            "price": {"close_dollars": "0.4500", "previous_dollars": "0.4400"},
            "volume_fp": "100.00",
            "open_interest_fp": "10000.00",
        },
        {
            "end_period_ts": 1781136000,
            "yes_bid": {"close_dollars": "0.5200"},
            "yes_ask": {"close_dollars": "0.5600"},
            "price": {"close_dollars": "0.5400", "previous_dollars": "0.4500"},
            "volume_fp": "500.00",
            "open_interest_fp": "120000.00",
        },
        {
            # After settlement: must be excluded to avoid leakage.
            "end_period_ts": 1781294400,
            "yes_bid": {"close_dollars": "0.9900"},
            "yes_ask": {"close_dollars": "1.0000"},
            "price": {"close_dollars": "1.0000", "previous_dollars": "0.5400"},
            "volume_fp": "5000.00",
            "open_interest_fp": "120000.00",
        },
    ]


def test_kalshi_dataset_builds_point_in_time_resolved_rows():
    builder = KalshiResolvedDatasetBuilder()
    result = builder.build_rows(
        [_market()],
        candlesticks_by_ticker={"KXFED-26JUN-TARGET": _candles()},
        retrieved_ts=1781300000,
    )

    assert len(result.rows) == 2
    first, second = result.rows
    assert first["venue"] == "Kalshi"
    assert first["market_id"] == "KXFED-26JUN-TARGET"
    assert first["event_id"] == "KXFED-26JUN"
    assert first["outcome"] == 1
    assert first["market_implied"] == 0.45
    assert second["market_implied"] == 0.54
    assert second["price_momentum_1"] > 0
    assert first["as_of_ts"] < first["resolved_ts"]
    assert first["resolution_source"] == "federal_reserve"
    assert first["resolution_source_confidence"] > 0.8
    assert first["liquidity_bucket"] == "liquid"
    assert first["rules_has_specific_source"] == 1.0


def test_kalshi_dataset_feature_catalog_excludes_labels_and_ids():
    result = KalshiResolvedDatasetBuilder().build_rows(
        [_market()],
        candlesticks_by_ticker={"KXFED-26JUN-TARGET": _candles()},
    )

    features = result.feature_catalog

    assert "market_implied" in features
    assert "bid_ask_spread" in features
    assert "rules_word_count" in features
    assert "resolution_source_confidence" in features
    assert "outcome" not in features
    assert "resolved_ts" not in features
    assert "as_of_ts" not in features
    assert "row_id" not in features


def test_kalshi_dataset_skips_non_kalshi_and_unresolved_markets():
    builder = KalshiResolvedDatasetBuilder()
    result = builder.build_rows(
        [
            _market(venue="Polymarket"),
            _market(ticker="KXFED-UNRESOLVED", settlement_value_dollars=None, expiration_value=""),
        ]
    )

    reasons = {item["reason"] for item in result.skipped_markets}
    assert result.rows == []
    assert "non_kalshi_market" in reasons
    assert "unresolved_market" in reasons


def test_kalshi_dataset_store_roundtrip(tmp_path):
    result = KalshiResolvedDatasetBuilder().build_rows(
        [_market()],
        candlesticks_by_ticker={"KXFED-26JUN-TARGET": _candles()},
    )
    store = PointInTimeStore(tmp_path)
    try:
        persist_rows(store, result.rows)
        loaded = store.load_kalshi_resolved_rows(market_id="KXFED-26JUN-TARGET")
    finally:
        store.close()

    assert [row["row_id"] for row in loaded] == [row["row_id"] for row in result.rows]
    assert loaded[0]["market_implied"] == result.rows[0]["market_implied"]


def test_kalshi_dataset_rows_feed_discovery_engine(tmp_path):
    result = KalshiResolvedDatasetBuilder().build_rows(
        [_market()],
        candlesticks_by_ticker={"KXFED-26JUN-TARGET": _candles()},
    )
    # Duplicate with the opposite outcome to give the discovery loop a minimal
    # resolved panel instead of a single-market toy row.
    no_result = KalshiResolvedDatasetBuilder().build_rows(
        [
            _market(
                ticker="KXFED-26JUL-TARGET",
                event_ticker="KXFED-26JUL",
                settlement_value_dollars="0.0000",
                settlement_ts="2026-07-12T19:00:00Z",
                close_time="2026-07-12T16:00:00Z",
                expiration_time="2026-07-12T18:00:00Z",
            )
        ],
        candlesticks_by_ticker={"KXFED-26JUL-TARGET": _candles()},
    )
    rows = result.rows + no_result.rows
    store = PointInTimeStore(tmp_path)
    try:
        engine = AgenticSignalDiscoveryEngine(store=store)
        report = engine.run(
            AgenticDiscoveryConfig(
                n_trajectories=1,
                iterations_per_trajectory=2,
                top_k=1,
                min_support=2,
                evolution_interval=0,
                backtest_min_train_size=2,
                backtest_test_size=1,
                backtest_step_size=1,
            ),
            rows,
            feature_catalog=KalshiResolvedDatasetBuilder.feature_catalog(rows),
        )
    finally:
        store.close()

    assert report.top_hypotheses
    assert report.promotion_decisions


def test_resolution_source_mapper_uses_rules_and_title():
    source = infer_resolution_source(
        _market(
            title="Will CPI be above 3 percent?",
            subtitle="Inflation print",
            rules_primary="Resolved by the Bureau of Labor Statistics CPI release.",
            rules_secondary="",
        )
    )

    assert source.family == "bls_inflation"
    assert source.code == 2
