"""Research-only Kalshi public universe scanner.

The scanner pulls public market data, classifies markets, and writes candidate
inventory artifacts. It never calls authenticated account/order endpoints and
never claims that a market is usable EV.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import math
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from predmarket.config import load_config
from predmarket.kalshi_dataset import KalshiMarketDataClient
from predmarket.kalshi_execution_cost import normalize_kalshi_execution_cost

DEFAULT_MIN_CLOSE_HOURS = 0.0
DEFAULT_MAX_CLOSE_HOURS = 72.0
DEFAULT_LIMIT = 1000
DEFAULT_MAX_PAGES = 10
DEFAULT_RAW_OUTPUT_DIR = Path("/home/mrwatson/manual_drops/kalshi_universe")
DEFAULT_LATEST_RAW_PATH = DEFAULT_RAW_OUTPUT_DIR / "kalshi_universe_scan_latest.json"
DEFAULT_OUT_DIR = Path("docs/codex/macro/kalshi-universe-scan-latest")
MACRO_DIR = Path("docs/codex/macro")
DEFAULT_BROAD_MVE_FILTERS: tuple[str | None, ...] = ("exclude",)
DEFAULT_FOCUSED_SPORTS_FETCH_MAX_CLOSE_HOURS = 720.0
DEFAULT_WORLD_CUP_SOCCER_SERIES: tuple[str, ...] = (
    "KXWCGAME",
    "KXWCSPREAD",
    "KXWCTOTAL",
    "KXWCBTTS",
    "KXWC1H",
    "KXWC1HSPREAD",
    "KXWC1HTOTAL",
    "KXWC2H",
    "KXWC2HSPREAD",
    "KXWC2HTOTAL",
    "KXWCTEAMH2H",
    "KXWCTEAMGOALS",
    "KXWCTEAMSHOT",
    "KXWCTEAMSOG",
    "KXWCCORNERS",
    "KXWCTCORNERS",
    "KXFIFAGAME",
    "KXFIFASPREAD",
    "KXFIFATOTAL",
    "KXFIFAADVANCE",
)
DEFAULT_FOCUSED_SPORTS_SERIES: tuple[str, ...] = (
    "KXMLBGAME",
    "KXLMBGAME",
    "KXKBOGAME",
    "KXMLBASGAME",
    "KXMLBSTGAME",
    "KXATPMATCH",
    "KXATPGAME",
    "KXATPSETWINNER",
    "KXATPS3GWINNER",
    "KXWIMMEN",
    "KXWIMWOMEN",
    "KXWMENSINGLES",
    "KXWWOMENSINGLES",
    *DEFAULT_WORLD_CUP_SOCCER_SERIES,
)
CORE_MODEL_ROUTES = {
    "nfl": "nfl_quant_glm51_greenfield",
    "mlb": "mlb-platform",
    "nba": "nba-analytics-platform",
    "atp": "atp-oracle",
}
SPORTS_CLASSIFICATIONS = frozenset({"nfl", "mlb", "nba", "atp", "other_sports"})
MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}
SOFT_ROUTES = {
    "other_sports",
    "weather",
    "macro_econ",
    "politics_policy",
    "finance_crypto",
    "entertainment",
    "geopolitics",
    "unknown_soft_watch",
}
CSV_FIELDS = [
    "ticker",
    "event_ticker",
    "series_ticker",
    "classification",
    "model_route",
    "status",
    "time_to_close_hours",
    "time_to_settlement_hours",
    "settlement_time",
    "settlement_time_source",
    "horizon_time_basis",
    "yes_bid",
    "yes_ask",
    "yes_spread",
    "volume",
    "open_interest",
    "liquidity",
    "softness_score",
    "gate_status",
    "title",
]


@dataclass(frozen=True)
class KalshiUniverseScanArtifacts:
    snapshot_path: Path
    latest_raw_path: Path
    report_json_path: Path
    candidates_csv_path: Path
    routes_json_path: Path
    soft_watch_markdown_path: Path
    schedule_template_path: Path


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def iso_from_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


async def capture_kalshi_universe_snapshot(
    *,
    min_close_hours: float = DEFAULT_MIN_CLOSE_HOURS,
    max_close_hours: float = DEFAULT_MAX_CLOSE_HOURS,
    include_unopened: bool = False,
    limit: int = DEFAULT_LIMIT,
    max_pages: int = DEFAULT_MAX_PAGES,
    created_ts: float | None = None,
    client: KalshiMarketDataClient | None = None,
    broad_mve_filters: Sequence[str | None] = DEFAULT_BROAD_MVE_FILTERS,
    focused_sports_series: Sequence[str] = DEFAULT_FOCUSED_SPORTS_SERIES,
    focused_sports_fetch_max_close_hours: float = DEFAULT_FOCUSED_SPORTS_FETCH_MAX_CLOSE_HOURS,
) -> dict[str, Any]:
    ts = float(created_ts or time.time())
    min_close_ts = int(ts + min_close_hours * 3600)
    max_close_ts = int(ts + max_close_hours * 3600)
    statuses = ["open", "unopened"] if include_unopened else ["open"]

    if client is not None:
        return await _capture_with_client(
            client,
            created_ts=ts,
            statuses=statuses,
            limit=limit,
            max_pages=max_pages,
            min_close_ts=min_close_ts,
            max_close_ts=max_close_ts,
            min_close_hours=min_close_hours,
            max_close_hours=max_close_hours,
            include_unopened=include_unopened,
            broad_mve_filters=broad_mve_filters,
            focused_sports_series=focused_sports_series,
            focused_sports_fetch_max_close_hours=focused_sports_fetch_max_close_hours,
        )

    config = load_config()
    async with KalshiMarketDataClient(config) as live_client:
        return await _capture_with_client(
            live_client,
            created_ts=ts,
            statuses=statuses,
            limit=limit,
            max_pages=max_pages,
            min_close_ts=min_close_ts,
            max_close_ts=max_close_ts,
            min_close_hours=min_close_hours,
            max_close_hours=max_close_hours,
            include_unopened=include_unopened,
            broad_mve_filters=broad_mve_filters,
            focused_sports_series=focused_sports_series,
            focused_sports_fetch_max_close_hours=focused_sports_fetch_max_close_hours,
        )


async def _capture_with_client(
    client: KalshiMarketDataClient,
    *,
    created_ts: float,
    statuses: Sequence[str],
    limit: int,
    max_pages: int,
    min_close_ts: int,
    max_close_ts: int,
    min_close_hours: float,
    max_close_hours: float,
    include_unopened: bool,
    broad_mve_filters: Sequence[str | None],
    focused_sports_series: Sequence[str],
    focused_sports_fetch_max_close_hours: float,
) -> dict[str, Any]:
    series_index, series_error = await _series_index(client)
    markets_by_ticker: dict[str, dict[str, Any]] = {}
    status_counts: dict[str, int] = {}
    fetch_errors: dict[str, str] = {}

    for status in statuses:
        for mve_filter in broad_mve_filters:
            fetch_key = f"{status}:mve_{mve_label(mve_filter)}"
            try:
                markets = await client.fetch_markets(
                    status=status,
                    limit=limit,
                    max_pages=max_pages,
                    min_close_ts=min_close_ts,
                    max_close_ts=max_close_ts,
                    mve_filter=mve_filter,
                )
            except Exception as exc:
                markets = []
                fetch_errors[fetch_key] = str(exc)
            status_counts[fetch_key] = len(markets)
            merge_markets(
                markets_by_ticker,
                markets,
                series_index=series_index,
                discovery_source=f"public_markets_status_{status}_mve_{mve_label(mve_filter)}",
            )

    focused_counts: dict[str, int] = {}
    focused_max_close_ts = int(
        created_ts + max(max_close_hours, focused_sports_fetch_max_close_hours) * 3600
    )
    for status in statuses:
        for series_ticker in dedupe_nonempty(focused_sports_series):
            fetch_key = f"{status}:series_{series_ticker}:mve_default"
            try:
                markets = await client.fetch_markets(
                    status=status,
                    limit=limit,
                    max_pages=max_pages,
                    min_close_ts=min_close_ts,
                    max_close_ts=focused_max_close_ts,
                    series_ticker=series_ticker,
                    mve_filter=None,
                )
            except Exception as exc:
                markets = []
                fetch_errors[fetch_key] = str(exc)
            focused_counts[fetch_key] = len(markets)
            merge_markets(
                markets_by_ticker,
                markets,
                series_index=series_index,
                discovery_source=f"public_markets_series_{series_ticker}",
            )

    markets = sorted(markets_by_ticker.values(), key=lambda row: str(row.get("ticker") or ""))
    return {
        "schema_version": 1,
        "created_at_utc": iso_from_ts(created_ts),
        "status": "kalshi_universe_public_fetch_ok"
        if markets
        else "kalshi_universe_public_fetch_empty",
        "research_only": True,
        "execution_enabled": False,
        "safety": safety_flags(public_market_data_calls=True),
        "query": {
            "statuses": list(statuses),
            "limit": limit,
            "max_pages": max_pages,
            "broad_mve_filters": [mve_label(value) for value in broad_mve_filters],
            "focused_sports_series": list(dedupe_nonempty(focused_sports_series)),
            "focused_sports_fetch_max_close_hours": focused_sports_fetch_max_close_hours,
            "min_close_ts": min_close_ts,
            "max_close_ts": max_close_ts,
            "focused_sports_max_close_ts": focused_max_close_ts,
            "min_close_hours": min_close_hours,
            "max_close_hours": max_close_hours,
            "include_unopened": include_unopened,
        },
        "series": {
            "series_count": len(series_index),
            "series_error": series_error,
        },
        "summary": {
            "market_count": len(markets),
            "status_counts": status_counts,
            "focused_series_counts": focused_counts,
            "fetch_error_count": len(fetch_errors) + (1 if series_error else 0),
            "fetch_errors": fetch_errors,
        },
        "markets": markets,
    }


def merge_markets(
    markets_by_ticker: dict[str, dict[str, Any]],
    markets: Sequence[Any],
    *,
    series_index: Mapping[str, Mapping[str, Any]],
    discovery_source: str,
) -> None:
    for market in markets:
        if not isinstance(market, Mapping):
            continue
        ticker = str(market.get("ticker") or "").strip()
        if not ticker:
            continue
        enriched = dict(market)
        series_ticker = str(enriched.get("series_ticker") or infer_series_ticker(enriched) or "")
        if series_ticker:
            enriched["series_ticker"] = series_ticker
            series = series_index.get(series_ticker)
            if series:
                enriched.setdefault("category", series.get("category"))
                enriched.setdefault("tags", series.get("tags"))
                enriched.setdefault("series_title", series.get("title"))
                enriched.setdefault("settlement_sources", series.get("settlement_sources"))
        enriched.setdefault("discovery_source", discovery_source)
        existing = markets_by_ticker.get(ticker)
        if existing and existing.get("discovery_source"):
            enriched["discovery_source"] = f"{existing['discovery_source']},{discovery_source}"
        markets_by_ticker[ticker] = enriched


def mve_label(value: str | None) -> str:
    return value if value is not None else "default"


def dedupe_nonempty(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        cleaned = str(value or "").strip().upper()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            output.append(cleaned)
    return tuple(output)


async def _series_index(
    client: KalshiMarketDataClient,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    if not hasattr(client, "fetch_series_list"):
        return {}, None
    try:
        series = await client.fetch_series_list(include_product_metadata=False, include_volume=True)
    except Exception as exc:
        return {}, str(exc)
    return {
        str(item.get("ticker") or ""): dict(item)
        for item in series
        if isinstance(item, Mapping) and item.get("ticker")
    }, None


def build_universe_scan_report(
    snapshot: Mapping[str, Any],
    *,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    markets = [market for market in snapshot.get("markets", []) if isinstance(market, Mapping)]
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    created_ts = timestamp(snapshot.get("created_at_utc")) or time.time()
    query = snapshot.get("query") if isinstance(snapshot.get("query"), Mapping) else {}
    min_hours = optional_float(query.get("min_close_hours")) or DEFAULT_MIN_CLOSE_HOURS
    max_hours = optional_float(query.get("max_close_hours")) or DEFAULT_MAX_CLOSE_HOURS

    for market in markets:
        candidate = candidate_from_market(
            market,
            as_of_ts=created_ts,
            min_close_hours=min_hours,
            max_close_hours=max_hours,
        )
        if candidate is None:
            skipped.append(
                {
                    "ticker": market.get("ticker"),
                    "reason": "missing_or_outside_settlement_window",
                }
            )
            continue
        candidates.append(candidate)

    candidates.sort(
        key=lambda row: (
            -float(row.get("softness_score") or 0.0),
            float(
                row.get("time_to_settlement_hours") or row.get("time_to_close_hours") or 999999.0
            ),
            str(row.get("ticker") or ""),
        )
    )
    routes = route_groups(candidates)
    model_route_candidates = [
        row for row in candidates if row.get("classification") in CORE_MODEL_ROUTES
    ]
    soft_watch_candidates = [row for row in candidates if row.get("classification") in SOFT_ROUTES]
    if snapshot.get("status") == "kalshi_universe_public_fetch_empty" and not candidates:
        status = "universe_scan_blocked_public_fetch_failed"
    elif model_route_candidates:
        status = "universe_scan_ready_with_model_routes"
    elif soft_watch_candidates:
        status = "universe_scan_ready_soft_watch_only"
    else:
        status = "universe_scan_ready"

    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": True,
        "authenticated_api_calls": False,
        "provider_api_calls": True,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "summary": {
            "raw_market_count": len(markets),
            "candidate_count": len(candidates),
            "skipped_count": len(skipped),
            "model_route_candidate_count": len(model_route_candidates),
            "soft_watch_candidate_count": len(soft_watch_candidates),
            "settlement_window": {
                "min_hours": min_hours,
                "max_hours": max_hours,
                "basis": "sports settlement horizon when sports; close horizon otherwise",
                "legacy_min_close_hours": min_hours,
                "legacy_max_close_hours": max_hours,
            },
            "classification_counts": counts(row.get("classification") for row in candidates),
            "route_counts": {route: len(rows) for route, rows in routes.get("routes", {}).items()},
            "gate_counts": counts(row.get("gate_status") for row in candidates),
        },
        "contract_math": {
            "yes_preliminary_break_even": "YES ask plus official Kalshi fee estimate",
            "no_preliminary_break_even": "NO ask plus official Kalshi fee estimate",
            "edge_policy": "No EV is computed here. The EV ledger remains the only place that compares calibrated probability to break-even.",
        },
        "inputs": {
            "snapshot_created_at_utc": snapshot.get("created_at_utc"),
            "query": dict(query),
            "source_status": snapshot.get("status"),
        },
        "routes": routes,
        "candidates": candidates,
        "skipped": skipped[:100],
        "next_action": next_action(status, candidates),
        "safety": safety_flags(public_market_data_calls=True),
    }


def candidate_from_market(
    market: Mapping[str, Any],
    *,
    as_of_ts: float,
    min_close_hours: float,
    max_close_hours: float,
) -> dict[str, Any] | None:
    classification = classify_market(market)
    settlement = settlement_time_fields(market, classification=classification)
    settlement_ts = settlement["timestamp"]
    if settlement_ts is None:
        return None
    time_to_settlement_hours = (settlement_ts - as_of_ts) / 3600
    if time_to_settlement_hours < min_close_hours or time_to_settlement_hours > max_close_hours:
        return None

    close_ts = close_timestamp(market)
    if close_ts is None:
        close_ts = settlement_ts
    time_to_close_hours = (close_ts - as_of_ts) / 3600
    ticker = str(market.get("ticker") or "")
    series_ticker = str(market.get("series_ticker") or infer_series_ticker(market) or "")
    yes_bid = money(market.get("yes_bid_dollars"))
    yes_ask = money(market.get("yes_ask_dollars"))
    no_bid = money(market.get("no_bid_dollars"))
    no_ask = money(market.get("no_ask_dollars"))
    yes_cost = normalize_kalshi_execution_cost(
        display_price=yes_ask,
        executable_price=yes_ask,
        executable_price_source="public_kalshi_yes_ask",
        ticker=ticker,
    )
    no_cost = normalize_kalshi_execution_cost(
        display_price=no_ask,
        executable_price=no_ask,
        executable_price_source="public_kalshi_no_ask",
        ticker=ticker,
    )
    resolution_rule = official_rules(market)
    model_route = model_route_for(classification)
    event_start = event_start_time_fields(market, classification=classification)
    softness_score, softness_reasons = softness(
        market, classification=classification, as_of_ts=as_of_ts
    )
    gate_status, gate_reasons = candidate_gate(
        ticker=ticker,
        yes_ask=yes_ask,
        no_ask=no_ask,
        resolution_rule=resolution_rule,
    )
    return {
        "schema_version": "KalshiUniverseCandidateV1",
        "ticker": ticker,
        "event_ticker": market.get("event_ticker"),
        "series_ticker": series_ticker,
        "title": market.get("title"),
        "subtitle": market.get("subtitle"),
        "category": market.get("category"),
        "tags": list(market.get("tags") or []) if isinstance(market.get("tags"), list) else [],
        "status": market.get("status"),
        "close_time": market.get("close_time"),
        "expected_expiration_time": market.get("expected_expiration_time"),
        "expiration_time": market.get("expiration_time"),
        "close_ts": close_ts,
        "time_to_close_hours": round(time_to_close_hours, 4),
        "settlement_ts": settlement_ts,
        "settlement_time": settlement["iso"],
        "settlement_time_source": settlement["source"],
        "time_to_settlement_hours": round(time_to_settlement_hours, 4),
        "horizon_time_basis": settlement["basis"],
        "event_start_time": event_start["iso"],
        "event_start_time_source": event_start["source"],
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "no_bid": no_bid,
        "no_ask": no_ask,
        "yes_spread": round(yes_ask - yes_bid, 6)
        if yes_ask is not None and yes_bid is not None
        else None,
        "no_spread": round(no_ask - no_bid, 6)
        if no_ask is not None and no_bid is not None
        else None,
        "volume": number(market.get("volume_fp")) or number(market.get("volume")),
        "volume_24h": number(market.get("volume_24h_fp")) or number(market.get("volume_24h")),
        "open_interest": number(market.get("open_interest_fp"))
        or number(market.get("open_interest")),
        "liquidity": money(market.get("liquidity_dollars")),
        "official_rules_hash": sha256_text(resolution_rule) if resolution_rule else None,
        "official_rules_source": "public_kalshi_market_payload" if resolution_rule else None,
        "classification": classification,
        "model_route": model_route,
        "model_route_reason": model_route_reason(classification),
        "softness_score": softness_score,
        "softness_reasons": softness_reasons,
        "yes_preliminary_all_in_break_even": yes_cost.break_even_probability,
        "no_preliminary_all_in_break_even": no_cost.break_even_probability,
        "cost_quality": {
            "yes": yes_cost.cost_quality,
            "no": no_cost.cost_quality,
        },
        "gate_status": gate_status,
        "gates": gate_reasons,
        "calibrated_probability": None,
        "edge_probability": None,
        "expected_value_per_contract": None,
        "usable": False,
        "ev_status": "not_evaluated_universe_inventory_only",
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
        },
    }


def classify_market(market: Mapping[str, Any]) -> str:
    series = str(market.get("series_ticker") or infer_series_ticker(market) or "").upper()
    text = searchable_text(market)
    if series.startswith("KXNFL") or re.search(r"\b(nfl|pro football|super bowl)\b", text):
        return "nfl"
    if series.startswith(("KXMLB", "KXLMB", "KXKBO", "KXWBCGAME")) or re.search(
        r"\b(mlb|baseball|world series|mexican baseball|kbo)\b",
        text,
    ):
        return "mlb"
    if series.startswith("KXNBA") or re.search(r"\b(nba|basketball)\b", text):
        return "nba"
    if series.startswith(("KXATP", "KXTENNIS", "KXWIM")) or re.search(
        r"\b(atp|tennis|wimbledon|us open|australian open|french open)\b",
        text,
    ):
        return "atp"
    if re.search(r"\b(weather|temperature|rain|snow|hurricane|tornado|noaa|wind|heat)\b", text):
        return "weather"
    if re.search(
        r"\b(cpi|inflation|fomc|fed|interest rate|jobs report|unemployment|gdp|pce|treasury)\b",
        text,
    ):
        return "macro_econ"
    if re.search(
        r"\b(election|president|congress|senate|house|supreme court|bill|vote|tariff)\b", text
    ):
        return "politics_policy"
    if re.search(r"\b(bitcoin|btc|ethereum|crypto|nasdaq|s&p|stock|oil|gold|dollar|yield)\b", text):
        return "finance_crypto"
    if re.search(r"\b(oscar|grammy|movie|box office|album|song|tv|streaming)\b", text):
        return "entertainment"
    if re.search(
        r"\b(ukraine|russia|iran|israel|gaza|nato|war|ceasefire|hormuz|china|taiwan)\b", text
    ):
        return "geopolitics"
    if series in DEFAULT_WORLD_CUP_SOCCER_SERIES or re.search(
        r"\b(nhl|soccer|world cup|fifa|uefa|champions league|epl|golf|ufc|boxing|racing|cricket)\b",
        text,
    ):
        return "other_sports"
    return "unknown_soft_watch"


def model_route_for(classification: str) -> str:
    if classification in CORE_MODEL_ROUTES:
        return CORE_MODEL_ROUTES[classification]
    if classification in SOFT_ROUTES:
        return "soft_market_research_backlog"
    return "unrouted"


def model_route_reason(classification: str) -> str:
    if classification in CORE_MODEL_ROUTES:
        return f"direct deterministic route to {CORE_MODEL_ROUTES[classification]}"
    if classification in SOFT_ROUTES:
        return "non-core soft-watch route; requires a separate probability engine before EV"
    return "unrouted classification"


def settlement_time_fields(market: Mapping[str, Any], *, classification: str) -> dict[str, Any]:
    """Return the horizon timestamp used for inventory filtering.

    Sports contracts can retain an administrative ``close_time`` beyond the event
    horizon. For game/match discovery, the actionable horizon is expected
    expiration/settlement. Non-sports keep the historical close-time behavior.
    """
    if classification in SPORTS_CLASSIFICATIONS:
        keys = ("expected_expiration_time", "expiration_time", "settlement_time")
        basis = "sports_expected_expiration_time"
    else:
        keys = ("close_time", "expected_expiration_time", "expiration_time")
        basis = "close_time"
    for key in keys:
        ts = timestamp(market.get(key))
        if ts is not None:
            return {"timestamp": ts, "iso": iso_from_ts(ts), "source": key, "basis": basis}
    if classification == "atp":
        event_probe = event_ticker_probe_time(market)
        close_ts = timestamp(market.get("close_time"))
        if event_probe["timestamp"] is not None and (
            close_ts is None or event_probe["timestamp"] <= close_ts
        ):
            return {**event_probe, "basis": "sports_event_ticker_probe_schedule"}
        if close_ts is not None:
            return {
                "timestamp": close_ts,
                "iso": iso_from_ts(close_ts),
                "source": "close_time",
                "basis": "sports_close_time_fallback",
            }
    if classification in SPORTS_CLASSIFICATIONS:
        ts = timestamp(market.get("close_time"))
        if ts is not None:
            return {
                "timestamp": ts,
                "iso": iso_from_ts(ts),
                "source": "close_time",
                "basis": "sports_close_time_fallback",
            }
    return {"timestamp": None, "iso": None, "source": None, "basis": basis}


def event_start_time_fields(market: Mapping[str, Any], *, classification: str) -> dict[str, Any]:
    if classification not in SPORTS_CLASSIFICATIONS:
        return {"timestamp": None, "iso": None, "source": None}
    for key in ("event_start_time", "scheduled_start_time", "event_time", "game_start_time"):
        ts = timestamp(market.get(key))
        if ts is not None:
            return {"timestamp": ts, "iso": iso_from_ts(ts), "source": key}
    return {"timestamp": None, "iso": None, "source": None}


def event_ticker_probe_time(market: Mapping[str, Any]) -> dict[str, Any]:
    event_ticker = str(market.get("event_ticker") or market.get("ticker") or "")
    match = re.search(
        r"-(?P<year>\d{2})(?P<month>[A-Z]{3})(?P<day>\d{2})(?P<hour>\d{2})?(?P<minute>\d{2})?",
        event_ticker,
    )
    if not match:
        return {"timestamp": None, "iso": None, "source": None}
    month = MONTHS.get(match.group("month"))
    if month is None:
        return {"timestamp": None, "iso": None, "source": None}
    year = 2000 + int(match.group("year"))
    day = int(match.group("day"))
    hour_text = match.group("hour")
    minute_text = match.group("minute")
    if hour_text is not None and minute_text is not None:
        dt = datetime(year, month, day, int(hour_text), int(minute_text), tzinfo=UTC) + timedelta(
            hours=6
        )
        source = "event_ticker_datetime_plus_6h_probe_schedule"
    else:
        dt = datetime(year, month, day, tzinfo=UTC) + timedelta(days=1, hours=6)
        source = "event_ticker_date_next_morning_probe_schedule"
    return {"timestamp": dt.timestamp(), "iso": iso_from_ts(dt.timestamp()), "source": source}


def softness(  # noqa: C901
    market: Mapping[str, Any], *, classification: str, as_of_ts: float
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    yes_bid = money(market.get("yes_bid_dollars"))
    yes_ask = money(market.get("yes_ask_dollars"))
    spread = yes_ask - yes_bid if yes_ask is not None and yes_bid is not None else None
    if spread is None:
        score += 0.15
        reasons.append("missing quoted spread")
    elif spread >= 0.10:
        score += 0.25
        reasons.append("wide spread >= 10pp")
    elif spread >= 0.05:
        score += 0.15
        reasons.append("moderate spread >= 5pp")

    liquidity = money(market.get("liquidity_dollars"))
    if liquidity is None or liquidity <= 0:
        score += 0.20
        reasons.append("zero or missing displayed liquidity")
    elif liquidity < 1000:
        score += 0.12
        reasons.append("low displayed liquidity")

    volume = number(market.get("volume_fp")) or number(market.get("volume"))
    if volume is None or volume < 100:
        score += 0.08
        reasons.append("thin lifetime volume")

    settlement_ts = settlement_time_fields(market, classification=classification)["timestamp"]
    if settlement_ts is not None:
        hours = (settlement_ts - as_of_ts) / 3600
        if hours <= 6:
            score += 0.18
            reasons.append("settles within 6h")
        elif hours <= 24:
            score += 0.10
            reasons.append("settles within 24h")

    updated = timestamp(market.get("updated_time") or market.get("last_updated_ts"))
    if updated is not None:
        stale_hours = max((as_of_ts - updated) / 3600, 0.0)
        if stale_hours >= 24:
            score += 0.18
            reasons.append("metadata stale >= 24h")
        elif stale_hours >= 6:
            score += 0.10
            reasons.append("metadata stale >= 6h")

    rule = official_rules(market)
    if rule and len(rule) <= 500:
        score += 0.08
        reasons.append("simple official rule text")
    if classification not in CORE_MODEL_ROUTES:
        score += 0.12
        reasons.append("outside current core model routes")
    if classification in {"weather", "macro_econ", "finance_crypto"}:
        score += 0.08
        reasons.append("likely external reference data exists")

    return round(min(score, 1.0), 4), reasons


def candidate_gate(
    *,
    ticker: str,
    yes_ask: float | None,
    no_ask: float | None,
    resolution_rule: str,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if not ticker:
        reasons.append("ticker is missing")
    if yes_ask is None and no_ask is None:
        reasons.append("both YES and NO executable quotes are missing")
    if not resolution_rule:
        reasons.append("official rule text is missing")
    if any("missing" in reason for reason in reasons):
        return "blocked", reasons
    if yes_ask is None or no_ask is None:
        reasons.append("one side quote is missing")
        return "warn", reasons
    return "pass", ["candidate inventory only; EV not evaluated here"]


def route_groups(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    routes: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        route = str(candidate.get("model_route") or "unrouted")
        routes.setdefault(route, []).append(compact_candidate(candidate))
    for route, rows in routes.items():
        routes[route] = sorted(
            rows,
            key=lambda row: (
                -float(row.get("softness_score") or 0.0),
                float(
                    row.get("time_to_settlement_hours")
                    or row.get("time_to_close_hours")
                    or 999999.0
                ),
            ),
        )
    return {
        "schema_version": 1,
        "research_only": True,
        "execution_enabled": False,
        "routes": routes,
    }


def compact_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ticker": candidate.get("ticker"),
        "event_ticker": candidate.get("event_ticker"),
        "series_ticker": candidate.get("series_ticker"),
        "title": candidate.get("title"),
        "classification": candidate.get("classification"),
        "model_route": candidate.get("model_route"),
        "time_to_close_hours": candidate.get("time_to_close_hours"),
        "time_to_settlement_hours": candidate.get("time_to_settlement_hours"),
        "settlement_time": candidate.get("settlement_time"),
        "settlement_time_source": candidate.get("settlement_time_source"),
        "horizon_time_basis": candidate.get("horizon_time_basis"),
        "yes_ask": candidate.get("yes_ask"),
        "no_ask": candidate.get("no_ask"),
        "softness_score": candidate.get("softness_score"),
        "softness_reasons": candidate.get("softness_reasons"),
        "gate_status": candidate.get("gate_status"),
    }


def write_universe_scan_artifacts(
    snapshot: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    raw_output_dir: Path = DEFAULT_RAW_OUTPUT_DIR,
    latest_raw_path: Path = DEFAULT_LATEST_RAW_PATH,
    out_dir: Path = DEFAULT_OUT_DIR,
    macro_dir: Path = MACRO_DIR,
) -> KalshiUniverseScanArtifacts:
    raw_output_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = str(snapshot.get("created_at_utc") or utc_now()).replace("-", "").replace(":", "")
    snapshot_path = raw_output_dir / f"kalshi_universe_scan_{stamp}.json"
    snapshot_text = json.dumps(snapshot, indent=2, sort_keys=True, default=str) + "\n"
    snapshot_path.write_text(snapshot_text, encoding="utf-8")
    latest_raw_path.parent.mkdir(parents=True, exist_ok=True)
    latest_raw_path.write_text(snapshot_text, encoding="utf-8")

    report_with_paths = dict(report)
    report_with_paths["raw_outputs"] = {
        "snapshot_path": str(snapshot_path),
        "latest_raw_path": str(latest_raw_path),
    }
    report_json_path = out_dir / "kalshi-universe-scan.json"
    candidates_csv_path = out_dir / "kalshi-universe-candidates.csv"
    routes_json_path = out_dir / "kalshi-universe-routes.json"
    soft_watch_markdown_path = out_dir / "kalshi-soft-market-watch.md"
    schedule_template_path = out_dir / "kalshi-universe-scan.timer.example"

    report_text = json.dumps(report_with_paths, indent=2, sort_keys=True, default=str) + "\n"
    report_json_path.write_text(report_text, encoding="utf-8")
    write_candidates_csv(report.get("candidates", []), candidates_csv_path)
    routes_json_path.write_text(
        json.dumps(report.get("routes", {}), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    soft_watch_markdown_path.write_text(render_soft_watch(report), encoding="utf-8")
    schedule_template_path.write_text(render_timer_template(), encoding="utf-8")

    macro_dir.mkdir(parents=True, exist_ok=True)
    (macro_dir / "latest-kalshi-universe-scan.json").write_text(report_text, encoding="utf-8")
    write_candidates_csv(
        report.get("candidates", []), macro_dir / "latest-kalshi-universe-candidates.csv"
    )
    (macro_dir / "latest-kalshi-universe-routes.json").write_text(
        json.dumps(report.get("routes", {}), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (macro_dir / "latest-kalshi-soft-market-watch.md").write_text(
        render_soft_watch(report), encoding="utf-8"
    )

    return KalshiUniverseScanArtifacts(
        snapshot_path=snapshot_path,
        latest_raw_path=latest_raw_path,
        report_json_path=report_json_path,
        candidates_csv_path=candidates_csv_path,
        routes_json_path=routes_json_path,
        soft_watch_markdown_path=soft_watch_markdown_path,
        schedule_template_path=schedule_template_path,
    )


def write_candidates_csv(candidates: Any, path: Path) -> None:
    rows = [row for row in candidates if isinstance(row, Mapping)]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def render_soft_watch(report: Mapping[str, Any]) -> str:
    candidates = [
        row
        for row in report.get("candidates", [])
        if isinstance(row, Mapping) and row.get("classification") in SOFT_ROUTES
    ]
    candidates.sort(key=lambda row: -float(row.get("softness_score") or 0.0))
    lines = [
        "# Kalshi Soft Market Watch",
        "",
        f"- Status: `{report.get('status')}`",
        "- Mode: research-only public market inventory",
        "- Execution enabled: `false`",
        "- EV policy: not evaluated here; use the EV ledger after calibrated probabilities exist.",
        "",
        "| Rank | Ticker | Route | Settles (h) | Softness | Reason | Needed Evidence |",
        "| ---: | --- | --- | ---: | ---: | --- | --- |",
    ]
    for idx, row in enumerate(candidates[:25], start=1):
        reasons = "; ".join(str(reason) for reason in row.get("softness_reasons") or [])
        lines.append(
            f"| {idx} | `{row.get('ticker')}` | `{row.get('classification')}` | "
            f"{fmt(row.get('time_to_settlement_hours') or row.get('time_to_close_hours'))} | "
            f"{fmt(row.get('softness_score'))} | "
            f"{reasons or 'none'} | {needed_evidence(str(row.get('classification') or ''))} |"
        )
    lines.extend(
        [
            "",
            "## Guardrail",
            "",
            "This watchlist is not a list of bets. It is a routing inventory.",
            "",
        ]
    )
    return "\n".join(lines)


def render_timer_template() -> str:
    return """# Example systemd user timer. Do not enable automatically.
# Save as ~/.config/systemd/user/kalshi-universe-scan.timer after review.

[Unit]
Description=Run research-only Kalshi universe scan every 10 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
RandomizedDelaySec=45s
Persistent=true

[Install]
WantedBy=timers.target

# Matching service:
# [Unit]
# Description=Research-only Kalshi universe scan
# [Service]
# Type=oneshot
# WorkingDirectory=/home/mrwatson/projects/predmarket-alpha
# ExecStart=/usr/bin/make kalshi-universe-watch-once
"""


def next_action(status: str, candidates: Sequence[Mapping[str, Any]]) -> str:
    if status == "universe_scan_ready_with_model_routes":
        return "Route modelable candidates to the matching repo work-order layer; do not compute EV here."
    if status == "universe_scan_ready_soft_watch_only":
        return "Inspect soft-watch candidates and build a probability engine only for markets with available evidence."
    if status == "universe_scan_blocked_public_fetch_failed":
        return "Check public Kalshi market-data availability and rerun with a smaller page budget."
    if candidates:
        return "Keep inventory current and wait for model routes or soft-watch evidence."
    return "No candidate markets landed inside the configured settlement window."


def needed_evidence(classification: str) -> str:
    return {
        "weather": "NOAA/NWS reference and local forecast model",
        "macro_econ": "official release calendar and historical surprise model",
        "politics_policy": "source-backed event model and resolution monitor",
        "finance_crypto": "market reference feed and volatility model",
        "entertainment": "source-backed public data model",
        "geopolitics": "trusted source monitor and resolution-rule audit",
        "unknown_soft_watch": "manual classification and evidence source",
    }.get(classification, "route-specific calibrated probability")


def safety_flags(*, public_market_data_calls: bool) -> dict[str, Any]:
    return {
        "research_only": True,
        "public_market_data_calls": public_market_data_calls,
        "authenticated_api_calls": False,
        "account_or_order_paths": False,
        "market_execution": False,
        "database_writes": False,
        "paid_calls": False,
        "raw_secrets_copied": False,
        "raw_payloads_copied_to_repo": False,
        "staking_or_sizing_guidance": False,
    }


def close_timestamp(market: Mapping[str, Any]) -> float | None:
    for key in ("close_time", "expected_expiration_time", "expiration_time"):
        value = timestamp(market.get(key))
        if value is not None:
            return value
    return None


def timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def infer_series_ticker(market: Mapping[str, Any]) -> str:
    ticker = str(
        market.get("series_ticker") or market.get("event_ticker") or market.get("ticker") or ""
    )
    if "-" in ticker:
        return ticker.split("-", 1)[0]
    return ticker


def searchable_text(market: Mapping[str, Any]) -> str:
    tags = market.get("tags") if isinstance(market.get("tags"), list) else []
    parts = [
        market.get("series_ticker"),
        market.get("event_ticker"),
        market.get("ticker"),
        market.get("title"),
        market.get("subtitle"),
        market.get("category"),
        market.get("series_title"),
        market.get("rules_primary"),
        market.get("rules_secondary"),
        " ".join(str(tag) for tag in tags),
    ]
    return " ".join(str(part or "") for part in parts).lower()


def official_rules(market: Mapping[str, Any]) -> str:
    primary = str(market.get("rules_primary") or "").strip()
    secondary = str(market.get("rules_secondary") or "").strip()
    return " ".join(part for part in (primary, secondary) if part)


def money(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number_value = float(str(value).strip().replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number_value):
        return None
    return number_value


def number(value: Any) -> float | None:
    return money(value)


def optional_float(value: Any) -> float | None:
    return number(value)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def counts(values: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        key = str(value or "unknown")
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


def fmt(value: Any) -> str:
    number_value = optional_float(value)
    return "" if number_value is None else f"{number_value:.4f}"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan the public Kalshi market universe in research-only mode."
    )
    parser.add_argument("--min-close-hours", type=float, default=DEFAULT_MIN_CLOSE_HOURS)
    parser.add_argument("--max-close-hours", type=float, default=DEFAULT_MAX_CLOSE_HOURS)
    parser.add_argument(
        "--focused-sports-fetch-max-close-hours",
        type=float,
        default=DEFAULT_FOCUSED_SPORTS_FETCH_MAX_CLOSE_HOURS,
    )
    parser.add_argument("--include-unopened", action="store_true")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--raw-output-dir", type=Path, default=DEFAULT_RAW_OUTPUT_DIR)
    parser.add_argument("--latest-raw-path", type=Path, default=DEFAULT_LATEST_RAW_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


async def _async_main(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], KalshiUniverseScanArtifacts | None]:
    snapshot = await capture_kalshi_universe_snapshot(
        min_close_hours=args.min_close_hours,
        max_close_hours=args.max_close_hours,
        focused_sports_fetch_max_close_hours=args.focused_sports_fetch_max_close_hours,
        include_unopened=args.include_unopened,
        limit=args.limit,
        max_pages=args.max_pages,
    )
    report = build_universe_scan_report(snapshot)
    artifacts = None
    if args.write:
        artifacts = write_universe_scan_artifacts(
            snapshot,
            report,
            raw_output_dir=args.raw_output_dir,
            latest_raw_path=args.latest_raw_path,
            out_dir=args.out_dir,
        )
    return report, artifacts


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report, artifacts = asyncio.run(_async_main(args))
    payload: dict[str, Any]
    if artifacts is None:
        payload = report
    else:
        payload = {
            "status": report["status"],
            "summary": report["summary"],
            "snapshot_path": str(artifacts.snapshot_path),
            "latest_raw_path": str(artifacts.latest_raw_path),
            "report_json_path": str(artifacts.report_json_path),
            "candidates_csv_path": str(artifacts.candidates_csv_path),
            "routes_json_path": str(artifacts.routes_json_path),
            "soft_watch_markdown_path": str(artifacts.soft_watch_markdown_path),
            "schedule_template_path": str(artifacts.schedule_template_path),
        }
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
