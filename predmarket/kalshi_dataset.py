"""Kalshi resolved-row dataset builder for alpha discovery.

This module converts Kalshi market payloads plus price history into the row
shape consumed by the discovery engine. It deliberately does not create alpha;
it creates point-in-time, resolved rows with conservative execution assumptions
so the existing research and promotion gates can test alpha candidates.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import urlencode

from predmarket.config import Config, load_config
from predmarket.store import PointInTimeStore

logger = logging.getLogger("predmarket.kalshi_dataset")


NON_FEATURE_FIELDS = {
    "as_of_ts",
    "created_ts",
    "resolved_ts",
    "settlement_value",
    "outcome",
    "event_id",
    "market_id",
    "ticker",
    "title",
    "subtitle",
    "rules_primary",
    "rules_secondary",
    "resolution_source",
    "resolution_source_url",
    "venue",
    "domain",
    "horizon",
    "liquidity_bucket",
    "calibration_bucket",
    "raw_market_json",
    "raw_candlestick_json",
    "retrieved_ts",
    "row_id",
    "row_schema_version",
}


SOURCE_PATTERNS: tuple[tuple[str, str, int, str], ...] = (
    ("federal_reserve", r"\b(federal reserve|fomc|fed funds|target rate)\b", 1, "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"),
    ("bls_inflation", r"\b(cpi|inflation|consumer price index|bureau of labor statistics)\b", 2, "https://www.bls.gov/cpi/"),
    ("bls_labor", r"\b(nonfarm|payroll|unemployment|jobs report|employment situation)\b", 3, "https://www.bls.gov/ces/"),
    ("bea_macro", r"\b(gdp|gross domestic product|bea|personal consumption expenditures|pce)\b", 4, "https://www.bea.gov/"),
    ("noaa_weather", r"\b(weather|temperature|rain|snow|hurricane|noaa|national weather service)\b", 5, "https://www.weather.gov/"),
    ("congress", r"\b(congress|senate|house of representatives|bill|resolution|vote)\b", 6, "https://www.congress.gov/"),
    ("sports", r"\b(nfl|nba|mlb|nhl|soccer|world cup|game|match|championship)\b", 7, ""),
    ("crypto", r"\b(bitcoin|btc|ethereum|eth|crypto)\b", 8, ""),
)


@dataclass(frozen=True)
class ResolutionSource:
    family: str
    code: int
    confidence: float
    url: str = ""


@dataclass
class KalshiDatasetBuildResult:
    rows: List[Dict[str, Any]]
    skipped_markets: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def feature_catalog(self) -> List[str]:
        return KalshiResolvedDatasetBuilder.feature_catalog(self.rows)


class KalshiMarketDataClient:
    """Small public Kalshi market-data client.

    The endpoints used here are public market-data endpoints. Authenticated
    orderbook and execution paths stay outside the dataset builder.
    """

    def __init__(self, config: Config, session: Any = None):
        self.config = config
        self.base_url = config.venues.kalshi.effective_api_url.rstrip("/")
        self.session = session
        self._owns_session = False

    async def __aenter__(self) -> "KalshiMarketDataClient":
        if self.session is None:
            import aiohttp

            self.session = aiohttp.ClientSession()
            self._owns_session = True
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._owns_session and self.session is not None:
            await self.session.close()
        self.session = None
        self._owns_session = False

    async def get_json(self, path: str, params: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        if self.session is None:
            raise RuntimeError("KalshiMarketDataClient must be used as an async context manager")
        query = f"?{urlencode({k: v for k, v in (params or {}).items() if v is not None})}" if params else ""
        url = f"{self.base_url}{path}{query}"
        async with self.session.get(url) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"Kalshi market data request failed {resp.status}: {text[:240]}")
            return await resp.json()

    async def fetch_markets(
        self,
        *,
        status: str = "settled",
        limit: int = 100,
        max_pages: int = 1,
        series_ticker: Optional[str] = None,
        min_settled_ts: Optional[int] = None,
        max_settled_ts: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        markets: List[Dict[str, Any]] = []
        cursor = ""
        for _ in range(max_pages):
            payload = await self.get_json(
                "/markets",
                {
                    "status": status,
                    "limit": limit,
                    "cursor": cursor or None,
                    "series_ticker": series_ticker,
                    "min_settled_ts": min_settled_ts,
                    "max_settled_ts": max_settled_ts,
                    "mve_filter": "exclude",
                },
            )
            markets.extend(payload.get("markets", []))
            cursor = payload.get("cursor") or ""
            if not cursor:
                break
        return markets

    async def fetch_candlesticks(
        self,
        market: Mapping[str, Any],
        *,
        start_ts: int,
        end_ts: int,
        period_interval: int = 1440,
        historical: bool = False,
    ) -> List[Dict[str, Any]]:
        ticker = str(market.get("ticker") or "")
        if not ticker:
            return []
        if historical:
            path = f"/historical/markets/{ticker}/candlesticks"
        else:
            series_ticker = infer_series_ticker(market)
            path = f"/series/{series_ticker}/markets/{ticker}/candlesticks"
        payload = await self.get_json(
            path,
            {
                "start_ts": int(start_ts),
                "end_ts": int(end_ts),
                "period_interval": int(period_interval),
            },
        )
        return payload.get("candlesticks", [])

    async def fetch_orderbook(
        self,
        market: Mapping[str, Any],
        *,
        depth: int = 10,
    ) -> Dict[str, Any]:
        ticker = str(market.get("ticker") or "")
        if not ticker:
            return {}
        return await self.get_json(
            f"/markets/{ticker}/orderbook",
            {"depth": int(depth)},
        )


class KalshiResolvedDatasetBuilder:
    """Build discovery-ready resolved rows from Kalshi markets."""

    def __init__(self, *, min_settlement_confidence: float = 0.99):
        self.min_settlement_confidence = float(min_settlement_confidence)

    def build_rows(
        self,
        markets: Sequence[Mapping[str, Any]],
        *,
        candlesticks_by_ticker: Optional[Mapping[str, Sequence[Mapping[str, Any]]]] = None,
        retrieved_ts: Optional[float] = None,
    ) -> KalshiDatasetBuildResult:
        rows: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        retrieved = float(retrieved_ts or time.time())
        candles = candlesticks_by_ticker or {}

        for market in markets:
            ticker = str(market.get("ticker") or market.get("market_id") or "")
            if not ticker:
                skipped.append({"reason": "missing_ticker", "market": dict(market)})
                continue
            if str(market.get("venue", "Kalshi")).lower() != "kalshi":
                skipped.append({"reason": "non_kalshi_market", "ticker": ticker})
                continue

            settlement_value = _money(market.get("settlement_value_dollars", market.get("settlement_value")))
            expiration_value = str(market.get("expiration_value") or "").lower()
            if settlement_value is None and expiration_value in {"yes", "true", "1"}:
                settlement_value = 1.0
            elif settlement_value is None and expiration_value in {"no", "false", "0"}:
                settlement_value = 0.0
            if settlement_value is None:
                skipped.append({"reason": "unresolved_market", "ticker": ticker})
                continue
            if not self._is_binary_settlement(settlement_value):
                skipped.append({"reason": "non_binary_settlement", "ticker": ticker, "settlement_value": settlement_value})
                continue

            outcome = 1 if settlement_value >= 0.5 else 0
            resolved_ts = _timestamp(
                market.get("settlement_ts")
                or market.get("settled_time")
                or market.get("close_time")
                or market.get("expiration_time")
            )
            if resolved_ts is None:
                skipped.append({"reason": "missing_resolved_ts", "ticker": ticker})
                continue

            market_rows = self._rows_for_market(
                dict(market),
                list(candles.get(ticker, [])),
                outcome=outcome,
                resolved_ts=resolved_ts,
                settlement_value=settlement_value,
                retrieved_ts=retrieved,
            )
            if not market_rows:
                skipped.append({"reason": "no_point_in_time_rows", "ticker": ticker})
            rows.extend(market_rows)

        rows.sort(key=lambda row: (float(row["as_of_ts"]), row["market_id"]))
        return KalshiDatasetBuildResult(rows=rows, skipped_markets=skipped)

    def _rows_for_market(
        self,
        market: Dict[str, Any],
        candlesticks: Sequence[Mapping[str, Any]],
        *,
        outcome: int,
        resolved_ts: float,
        settlement_value: float,
        retrieved_ts: float,
    ) -> List[Dict[str, Any]]:
        ticker = str(market["ticker"])
        event_id = str(market.get("event_ticker") or ticker)
        title = str(market.get("title") or market.get("yes_sub_title") or ticker)
        rules_primary = str(market.get("rules_primary") or "")
        rules_secondary = str(market.get("rules_secondary") or "")
        source = infer_resolution_source(market)
        base = self._base_features(
            market,
            event_id=event_id,
            title=title,
            rules_primary=rules_primary,
            rules_secondary=rules_secondary,
            source=source,
            outcome=outcome,
            resolved_ts=resolved_ts,
            settlement_value=settlement_value,
            retrieved_ts=retrieved_ts,
        )

        rows: List[Dict[str, Any]] = []
        ordered_candles = sorted(
            [dict(c) for c in candlesticks if _timestamp(c.get("end_period_ts")) is not None],
            key=lambda c: float(_timestamp(c.get("end_period_ts")) or 0.0),
        )
        previous_price: Optional[float] = None
        for candle in ordered_candles:
            as_of_ts = float(_timestamp(candle.get("end_period_ts")) or 0.0)
            if as_of_ts <= 0 or as_of_ts >= resolved_ts:
                continue
            row = {**base, **self._candlestick_features(candle, previous_price)}
            row["as_of_ts"] = as_of_ts
            row["horizon"] = horizon_bucket(max(resolved_ts - as_of_ts, 0.0))
            row["time_to_resolution_hours"] = max((resolved_ts - as_of_ts) / 3600.0, 0.0)
            row["time_to_close_hours"] = self._time_until(market.get("close_time"), as_of_ts)
            row["time_to_expiration_hours"] = self._time_until(market.get("expiration_time"), as_of_ts)
            row["row_id"] = stable_row_id(row)
            rows.append(row)
            previous_price = row.get("market_implied", previous_price)

        if rows:
            return rows

        as_of_ts = _timestamp(market.get("updated_time") or market.get("close_time") or market.get("created_time"))
        if as_of_ts is None or as_of_ts >= resolved_ts:
            created_ts = _timestamp(market.get("created_time"))
            as_of_ts = min(float(created_ts or (resolved_ts - 1.0)), resolved_ts - 1.0)
        row = {**base, **self._market_quote_features(market)}
        row["as_of_ts"] = float(as_of_ts)
        row["horizon"] = horizon_bucket(max(resolved_ts - float(as_of_ts), 0.0))
        row["time_to_resolution_hours"] = max((resolved_ts - float(as_of_ts)) / 3600.0, 0.0)
        row["time_to_close_hours"] = self._time_until(market.get("close_time"), float(as_of_ts))
        row["time_to_expiration_hours"] = self._time_until(market.get("expiration_time"), float(as_of_ts))
        row["row_id"] = stable_row_id(row)
        return [row]

    def _base_features(
        self,
        market: Mapping[str, Any],
        *,
        event_id: str,
        title: str,
        rules_primary: str,
        rules_secondary: str,
        source: ResolutionSource,
        outcome: int,
        resolved_ts: float,
        settlement_value: float,
        retrieved_ts: float,
    ) -> Dict[str, Any]:
        rules_text = " ".join(part for part in (rules_primary, rules_secondary) if part)
        created_ts = _timestamp(market.get("created_time")) or 0.0
        close_ts = _timestamp(market.get("close_time")) or 0.0
        liquidity = _money(market.get("liquidity_dollars")) or 0.0
        open_interest = _fp(market.get("open_interest_fp", market.get("open_interest"))) or 0.0
        volume_24h = _fp(market.get("volume_24h_fp", market.get("volume_24h"))) or 0.0
        volume_lifetime = _fp(market.get("volume_fp", market.get("volume"))) or 0.0
        series_ticker = infer_series_ticker(market)
        return {
            "row_schema_version": 1,
            "venue": "Kalshi",
            "event_id": event_id,
            "market_id": str(market.get("ticker") or ""),
            "ticker": str(market.get("ticker") or ""),
            "series_ticker": series_ticker,
            "domain": str(market.get("category") or source.family or "unknown"),
            "title": title,
            "subtitle": str(market.get("subtitle") or ""),
            "rules_primary": rules_primary,
            "rules_secondary": rules_secondary,
            "rules_hash": _stable_hash({"primary": rules_primary, "secondary": rules_secondary}),
            "rules_word_count": float(len(re.findall(r"\w+", rules_text))),
            "rules_char_count": float(len(rules_text)),
            "rules_has_primary": 1.0 if rules_primary.strip() else 0.0,
            "rules_has_secondary": 1.0 if rules_secondary.strip() else 0.0,
            "rules_has_specific_source": 1.0 if re.search(r"\b(according to|reported by|source|official|bureau|noaa|federal reserve|congress)\b", rules_text.lower()) else 0.0,
            "rules_has_discretionary_terms": 1.0 if re.search(r"\b(determined by kalshi|sole discretion|may be amended|ambiguous)\b", rules_text.lower()) else 0.0,
            "title_word_count": float(len(re.findall(r"\w+", title))),
            "resolution_source": source.family,
            "resolution_source_code": float(source.code),
            "resolution_source_confidence": float(source.confidence),
            "resolution_source_url": source.url,
            "created_ts": float(created_ts),
            "market_age_hours_at_close": max((close_ts - created_ts) / 3600.0, 0.0) if close_ts and created_ts else 0.0,
            "settlement_timer_hours": float(market.get("settlement_timer_seconds") or 0.0) / 3600.0,
            "can_close_early": 1.0 if bool(market.get("can_close_early")) else 0.0,
            "has_early_close_condition": 1.0 if str(market.get("early_close_condition") or "").strip() else 0.0,
            "fractional_trading_enabled": 1.0 if bool(market.get("fractional_trading_enabled")) else 0.0,
            "liquidity_dollars": liquidity,
            "open_interest": open_interest,
            "volume_24h": volume_24h,
            "volume_lifetime": volume_lifetime,
            "liquidity_bucket": liquidity_bucket(liquidity, open_interest),
            "settlement_value": float(settlement_value),
            "resolved_ts": float(resolved_ts),
            "outcome": int(outcome),
            "p_baseline": 0.5,
            "filled": 1.0,
            "retrieved_ts": float(retrieved_ts),
            "raw_market_json": json.dumps(dict(market), sort_keys=True, default=str),
        }

    def _candlestick_features(
        self, candle: Mapping[str, Any], previous_price: Optional[float]
    ) -> Dict[str, Any]:
        price = candle.get("price") or {}
        yes_bid = candle.get("yes_bid") or {}
        yes_ask = candle.get("yes_ask") or {}
        implied = _nested_money(price, "close") or _nested_money(price, "close_dollars")
        previous = (
            previous_price
            if previous_price is not None
            else _nested_money(price, "previous")
            or _nested_money(price, "previous_dollars")
            or implied
        )
        bid = _nested_money(yes_bid, "close") or _nested_money(yes_bid, "close_dollars")
        ask = _nested_money(yes_ask, "close") or _nested_money(yes_ask, "close_dollars")
        if implied is None and bid is not None and ask is not None:
            implied = (bid + ask) / 2.0
        implied = _bounded_probability(implied, fallback=0.5)
        bid = _bounded_probability(bid, fallback=max(implied - 0.01, 0.01))
        ask = _bounded_probability(ask, fallback=min(implied + 0.01, 0.99))
        spread = max(ask - bid, 0.0)
        volume = _fp(candle.get("volume_fp", candle.get("volume"))) or 0.0
        open_interest = _fp(candle.get("open_interest_fp", candle.get("open_interest"))) or 0.0
        return {
            "market_implied": implied,
            "execution_price": min(ask, 0.99),
            "yes_bid": bid,
            "yes_ask": ask,
            "bid_ask_spread": spread,
            "mid_price": (bid + ask) / 2.0,
            "last_price": implied,
            "previous_price": _bounded_probability(previous, fallback=implied),
            "price_momentum_1": implied - _bounded_probability(previous, fallback=implied),
            "candle_volume": volume,
            "candle_open_interest": open_interest,
            "fees": 0.0015,
            "slippage": min(max(spread * 0.25, 0.0), 0.05),
            "fill_probability": fill_probability(spread, volume, open_interest),
            "raw_candlestick_json": json.dumps(dict(candle), sort_keys=True, default=str),
        }

    def _market_quote_features(self, market: Mapping[str, Any]) -> Dict[str, Any]:
        bid = _money(market.get("yes_bid_dollars"))
        ask = _money(market.get("yes_ask_dollars"))
        last = _money(market.get("last_price_dollars")) or _money(market.get("previous_price_dollars"))
        if last is None and bid is not None and ask is not None:
            last = (bid + ask) / 2.0
        implied = _bounded_probability(last, fallback=0.5)
        bid = _bounded_probability(bid, fallback=max(implied - 0.01, 0.01))
        ask = _bounded_probability(ask, fallback=min(implied + 0.01, 0.99))
        spread = max(ask - bid, 0.0)
        volume = _fp(market.get("volume_24h_fp", market.get("volume_24h"))) or 0.0
        open_interest = _fp(market.get("open_interest_fp", market.get("open_interest"))) or 0.0
        return {
            "market_implied": implied,
            "execution_price": min(ask, 0.99),
            "yes_bid": bid,
            "yes_ask": ask,
            "bid_ask_spread": spread,
            "mid_price": (bid + ask) / 2.0,
            "last_price": implied,
            "previous_price": _bounded_probability(_money(market.get("previous_price_dollars")), fallback=implied),
            "price_momentum_1": implied - _bounded_probability(_money(market.get("previous_price_dollars")), fallback=implied),
            "candle_volume": volume,
            "candle_open_interest": open_interest,
            "fees": 0.0015,
            "slippage": min(max(spread * 0.25, 0.0), 0.05),
            "fill_probability": fill_probability(spread, volume, open_interest),
            "raw_candlestick_json": "{}",
        }

    def _is_binary_settlement(self, settlement_value: float) -> bool:
        return (
            settlement_value <= (1.0 - self.min_settlement_confidence)
            or settlement_value >= self.min_settlement_confidence
        )

    @staticmethod
    def _time_until(value: Any, as_of_ts: float) -> float:
        ts = _timestamp(value)
        if ts is None:
            return 0.0
        return max((ts - as_of_ts) / 3600.0, 0.0)

    @staticmethod
    def feature_catalog(rows: Sequence[Mapping[str, Any]]) -> List[str]:
        features = set()
        for row in rows:
            for key, value in row.items():
                if key in NON_FEATURE_FIELDS or key.endswith("_json") or key.endswith("_hash"):
                    continue
                if isinstance(value, bool) or isinstance(value, (int, float)):
                    if math.isfinite(float(value)):
                        features.add(str(key))
        return sorted(features)


def infer_resolution_source(market: Mapping[str, Any]) -> ResolutionSource:
    text = " ".join(
        str(market.get(key) or "")
        for key in ("title", "subtitle", "yes_sub_title", "no_sub_title", "rules_primary", "rules_secondary")
    ).lower()
    for family, pattern, code, url in SOURCE_PATTERNS:
        if re.search(pattern, text):
            return ResolutionSource(family=family, code=code, confidence=0.85, url=url)
    return ResolutionSource(family="unknown", code=0, confidence=0.10, url="")


def infer_series_ticker(market: Mapping[str, Any]) -> str:
    explicit = market.get("series_ticker")
    if explicit:
        return str(explicit)
    event_ticker = str(market.get("event_ticker") or "")
    if "-" in event_ticker:
        return event_ticker.split("-", 1)[0]
    if event_ticker:
        return event_ticker
    ticker = str(market.get("ticker") or "")
    return ticker.split("-", 1)[0] if "-" in ticker else ticker


def stable_row_id(row: Mapping[str, Any]) -> str:
    payload = {
        "market_id": row.get("market_id"),
        "as_of_ts": row.get("as_of_ts"),
        "outcome": row.get("outcome"),
        "schema": row.get("row_schema_version", 1),
    }
    return "kalshi-row-" + _stable_hash(payload)[:20]


def liquidity_bucket(liquidity_dollars: float, open_interest: float) -> str:
    score = max(float(liquidity_dollars or 0.0), float(open_interest or 0.0))
    if score >= 250_000:
        return "deep"
    if score >= 50_000:
        return "liquid"
    if score >= 10_000:
        return "thin"
    return "illiquid"


def horizon_bucket(seconds: float) -> str:
    days = float(seconds) / 86400.0
    if days <= 1:
        return "1d"
    if days <= 7:
        return "7d"
    if days <= 30:
        return "30d"
    if days <= 90:
        return "90d"
    return "long"


def fill_probability(spread: float, volume: float, open_interest: float) -> float:
    liquidity_score = min(math.log1p(max(volume, open_interest, 0.0)) / math.log1p(250_000.0), 1.0)
    spread_penalty = min(max(spread, 0.0) / 0.20, 1.0)
    return float(max(0.05, min(0.98, 0.15 + 0.80 * liquidity_score - 0.35 * spread_penalty)))


def _timestamp(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value) / 1000.0 if float(value) > 10_000_000_000 else float(value)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return _timestamp(float(text))
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc).timestamp()
    except ValueError:
        return None


def _money(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _fp(value: Any) -> Optional[float]:
    return _money(value)


def _nested_money(obj: Mapping[str, Any], key: str) -> Optional[float]:
    if not isinstance(obj, Mapping):
        return None
    return _money(obj.get(key))


def _bounded_probability(value: Any, *, fallback: float) -> float:
    parsed = _money(value)
    if parsed is None:
        parsed = float(fallback)
    return float(min(max(parsed, 0.01), 0.99))


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


async def build_dataset_from_kalshi_api(
    config: Config,
    *,
    limit: int = 100,
    max_pages: int = 1,
    days_back: int = 90,
    series_ticker: Optional[str] = None,
    period_interval: int = 1440,
) -> KalshiDatasetBuildResult:
    now = int(time.time())
    min_settled_ts = now - int(days_back * 86400)
    async with KalshiMarketDataClient(config) as client:
        markets = await client.fetch_markets(
            status="settled",
            limit=limit,
            max_pages=max_pages,
            series_ticker=series_ticker,
            min_settled_ts=min_settled_ts,
        )
        candles: Dict[str, List[Dict[str, Any]]] = {}
        for market in markets:
            ticker = str(market.get("ticker") or "")
            if not ticker:
                continue
            start_ts = int(_timestamp(market.get("open_time") or market.get("created_time")) or min_settled_ts)
            end_ts = int(_timestamp(market.get("settlement_ts") or market.get("close_time")) or now)
            try:
                candles[ticker] = await client.fetch_candlesticks(
                    market,
                    start_ts=start_ts,
                    end_ts=end_ts,
                    period_interval=period_interval,
                    historical=False,
                )
            except Exception as exc:
                logger.warning("Kalshi candlestick fetch failed for %s: %s", ticker, exc)
                candles[ticker] = []
    return KalshiResolvedDatasetBuilder().build_rows(markets, candlesticks_by_ticker=candles)


def persist_rows(store: PointInTimeStore, rows: Sequence[Mapping[str, Any]]) -> None:
    store.write_kalshi_resolved_rows([dict(row) for row in rows])


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build Kalshi resolved rows for alpha discovery")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--days-back", type=int, default=90)
    parser.add_argument("--series-ticker", default=None)
    parser.add_argument("--period-interval", type=int, default=1440, choices=[1, 60, 1440])
    parser.add_argument("--write", action="store_true", help="Persist rows to the research store")
    args = parser.parse_args(argv)

    config = load_config()
    result = asyncio.run(
        build_dataset_from_kalshi_api(
            config,
            limit=args.limit,
            max_pages=args.max_pages,
            days_back=args.days_back,
            series_ticker=args.series_ticker,
            period_interval=args.period_interval,
        )
    )
    if args.write:
        store = PointInTimeStore(config.global_cfg.data_dir)
        try:
            persist_rows(store, result.rows)
        finally:
            store.close()
    print(
        json.dumps(
            {
                "rows": len(result.rows),
                "skipped_markets": len(result.skipped_markets),
                "features": result.feature_catalog,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI smoke path
    raise SystemExit(main())
