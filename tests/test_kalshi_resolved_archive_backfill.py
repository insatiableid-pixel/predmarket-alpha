from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_resolved_archive_backfill.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("kalshi_resolved_archive_backfill", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
        "created_time": f"2026-07-{day:02d}T00:{minute:02d}:00Z",
        "last_price_dollars": "0.60",
        "yes_bid_dollars": "0.58",
        "yes_ask_dollars": "0.62",
        "category": "sports",
    }


def candles(index: int, price: float) -> list[dict[str, object]]:
    day = ((index - 1) % 28) + 1
    minute = (index - 1) % 60
    return [
        {
            "end_period_ts": f"2026-07-{day:02d}T14:{minute:02d}:00Z",
            "price": {"close": price},
            "yes_bid": {"close": price - 0.01},
            "yes_ask": {"close": price + 0.01},
        }
    ]


def test_backfill_emits_bucket_only_observations_and_labels() -> None:
    module = load_module()
    markets = [market(i, result="yes" if i % 2 else "no") for i in range(1, 6)]
    candle_map = {row["ticker"]: candles(i, 0.62) for i, row in enumerate(markets, start=1)}

    report = module.build_resolved_archive_backfill(
        markets=markets,
        candlesticks_by_ticker=candle_map,
        generated_utc="2026-07-06T00:00:00Z",
    )

    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["account_or_order_paths"] is False
    assert report["summary"]["label_count"] == 5
    assert report["summary"]["observation_count"] == 5
    assert (
        report["observations"][0]["consensus_probability_for_side"]
        == (report["observations"][0]["kalshi_mid_for_side"])
    )
    assert all(row["divergence"] == 0.0 for row in report["observations"])
    assert all(
        row["label_source"] == "public_kalshi_settled_market_payload" for row in report["labels"]
    )


def test_backfill_reaches_existing_bucket_falsification_when_powered() -> None:
    module = load_module()
    markets = [market(i, result="yes") for i in range(1, 41)]
    candle_map = {row["ticker"]: candles(i, 0.62) for i, row in enumerate(markets, start=1)}

    report = module.build_resolved_archive_backfill(
        markets=markets,
        candlesticks_by_ticker=candle_map,
        generated_utc="2026-07-06T00:00:00Z",
    )
    summary = report["summary"]

    assert summary["tested_hypothesis_count"] >= 1
    assert summary["falsification_status"] in {
        "sports_consensus_falsification_ready_no_research_candidates",
        "sports_consensus_falsification_ready_with_research_candidates",
    }
    assert report["status"] in {
        "kalshi_resolved_archive_backfill_ready_no_fdr_survivors",
        "kalshi_resolved_archive_backfill_ready_with_fdr_survivors",
    }


def test_capture_public_archive_uses_series_and_candlestick_endpoints(tmp_path: Path) -> None:
    module = load_module()
    calls: list[str] = []

    def fake_fetch(url: str) -> dict[str, object]:
        calls.append(url)
        if "/candlesticks" in url:
            return {"candlesticks": candles(1, 0.55)}
        return {"markets": [market(1)], "cursor": ""}

    markets_path, candles_path = module.capture_public_archive(
        series_tickers=["KXMLBGAME"],
        raw_dir=tmp_path,
        limit=10,
        max_pages=1,
        days_back=10,
        period_interval=60,
        fetch_json=fake_fetch,
        generated_utc="2026-07-06T00:00:00Z",
    )

    assert markets_path.is_file()
    assert candles_path.is_file()
    assert any("series_ticker=KXMLBGAME" in url for url in calls)
    assert any("/candlesticks" in url for url in calls)


def test_capture_public_archive_skips_bad_candlestick_ticker(tmp_path: Path) -> None:
    module = load_module()

    def fake_fetch(url: str) -> dict[str, object]:
        if "/candlesticks" in url:
            raise module.HTTPError(url, 404, "Not Found", {}, None)
        return {"markets": [market(1)], "cursor": ""}

    markets_path, candles_path = module.capture_public_archive(
        series_tickers=["KXMLBGAME"],
        raw_dir=tmp_path,
        limit=10,
        max_pages=1,
        days_back=10,
        period_interval=60,
        fetch_json=fake_fetch,
        generated_utc="2026-07-06T00:00:00Z",
    )

    assert markets_path.is_file()
    assert candles_path.is_file()
    candles_payload = module.read_json_or_empty(candles_path)
    ticker = market(1)["ticker"]
    assert candles_payload["candlesticks_by_ticker"][ticker] == []


def test_capture_public_archive_reuses_existing_candlestick_cache(tmp_path: Path) -> None:
    module = load_module()
    calls: list[str] = []
    cached_market = market(1)

    def fake_fetch(url: str) -> dict[str, object]:
        calls.append(url)
        if "/candlesticks" in url:
            raise AssertionError("cached candlestick should not be fetched")
        return {"markets": [cached_market], "cursor": ""}

    _, candles_path = module.capture_public_archive(
        series_tickers=["KXMLBGAME"],
        raw_dir=tmp_path,
        limit=10,
        max_pages=1,
        days_back=10,
        period_interval=60,
        existing_candlesticks_by_ticker={cached_market["ticker"]: candles(1, 0.57)},
        fetch_json=fake_fetch,
        generated_utc="2026-07-06T00:00:00Z",
    )

    candles_payload = module.read_json_or_empty(candles_path)
    assert (
        candles_payload["candlesticks_by_ticker"][cached_market["ticker"]][0]["price"]["close"]
        == 0.57
    )
    assert not any("/candlesticks" in url for url in calls)
