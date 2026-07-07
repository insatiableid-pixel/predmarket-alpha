#!/usr/bin/env python3
"""Build contract-keyed proxy feature packets for Kalshi crypto contracts.

This report creates features, not probabilities. It joins open Kalshi crypto
contract inventory to public exchange proxy data and preserves the boundary:
CF Benchmarks RTI is the official settlement source; Coinbase/Kraken-style
prices are proxy feature inputs only.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import manual_drop_path  # noqa: E402

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_UNIVERSE_SCAN_PATH = MACRO_DIR / "latest-kalshi-universe-scan.json"
DEFAULT_BREADTH_SCOUT_PATH = MACRO_DIR / "latest-kalshi-probability-breadth-scout.json"
DEFAULT_RAW_UNIVERSE_PATH = manual_drop_path(
    "kalshi_universe", "kalshi_universe_scan_latest.json"
)
DEFAULT_RAW_PROXY_DIR = manual_drop_path("kalshi_crypto_proxy_features")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-crypto-proxy-feature-packet-latest"
DEFAULT_MAX_CLOSE_HOURS = 6.0
DEFAULT_MAX_CONTRACTS = 1500
DEFAULT_COINBASE_GRANULARITY_SECONDS = 60
CSV_FIELDS = [
    "contract_ticker",
    "event_ticker",
    "series_ticker",
    "asset_symbol",
    "contract_family",
    "contract_side",
    "close_time",
    "fresh_time_to_close_minutes",
    "yes_bid",
    "yes_ask",
    "yes_spread",
    "strike_type",
    "floor_strike",
    "cap_strike",
    "proxy_source",
    "proxy_product_id",
    "proxy_price",
    "proxy_return_5m",
    "proxy_return_15m",
    "proxy_return_60m",
    "proxy_realized_vol_15m",
    "proxy_realized_vol_60m",
    "proxy_distance_to_floor",
    "proxy_distance_to_cap",
    "proxy_state",
    "feature_status",
    "label_status",
    "ev_status",
    "usable",
]
ASSET_CONFIG: dict[str, dict[str, str]] = {
    "BTC": {"coinbase_product": "BTC-USD", "official_index": "BRTI"},
    "ETH": {"coinbase_product": "ETH-USD", "official_index": "ETHUSDRTI"},
    "SOL": {"coinbase_product": "SOL-USD", "official_index": "SOLUSDRTI"},
    "DOGE": {"coinbase_product": "DOGE-USD", "official_index": "DOGEUSDRTI"},
    "XRP": {"coinbase_product": "XRP-USD", "official_index": "XRPUSDRTI"},
    "ZEC": {"coinbase_product": "ZEC-USD", "official_index": "ZECUSDRTI"},
    "NEAR": {"coinbase_product": "NEAR-USD", "official_index": "NEARUSDRTI"},
    "BNB": {"coinbase_product": "BNB-USD", "official_index": "BNBUSDRTI"},
    "HYPE": {"coinbase_product": "HYPE-USD", "official_index": "HYPEUSDRTI"},
}
ASSET_ORDER = tuple(ASSET_CONFIG)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_crypto_proxy_feature_packet(
    *,
    universe_scan_path: Path = DEFAULT_UNIVERSE_SCAN_PATH,
    probability_breadth_scout_path: Path = DEFAULT_BREADTH_SCOUT_PATH,
    raw_universe_path: Path = DEFAULT_RAW_UNIVERSE_PATH,
    raw_proxy_dir: Path = DEFAULT_RAW_PROXY_DIR,
    max_close_hours: float = DEFAULT_MAX_CLOSE_HOURS,
    max_contracts: int = DEFAULT_MAX_CONTRACTS,
    generated_utc: str | None = None,
    capture_public_proxy: bool = False,
    fetch_json: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    generated_ts = parse_ts(generated) or time.time()
    universe = read_json_or_empty(universe_scan_path)
    breadth = read_json_or_empty(probability_breadth_scout_path)
    raw_universe = read_json_or_empty(raw_universe_path)
    universe_safe = safe_research_artifact(universe)
    breadth_safe = safe_research_artifact(breadth)
    raw_index = raw_market_index(raw_universe)
    selected = select_crypto_candidates(
        universe.get("candidates", []),
        raw_index=raw_index,
        generated_ts=generated_ts,
        max_close_hours=max_close_hours,
        max_contracts=max_contracts,
    )
    assets = sorted({row["asset_symbol"] for row in selected if row.get("asset_symbol") in ASSET_CONFIG})
    proxy_capture = (
        capture_proxy_sources(assets, raw_proxy_dir=raw_proxy_dir, fetch_json=fetch_json)
        if capture_public_proxy
        else no_proxy_capture(assets, raw_proxy_dir=raw_proxy_dir)
    )
    proxy_features = proxy_feature_index(proxy_capture)
    feature_rows = [
        feature_row(candidate, proxy_features=proxy_features, generated_ts=generated_ts)
        for candidate in selected
    ]
    feature_ready_count = sum(1 for row in feature_rows if row["feature_status"] == "proxy_features_ready")
    partial_count = sum(1 for row in feature_rows if row["feature_status"] != "proxy_features_ready")
    status = feature_packet_status(
        universe_safe=universe_safe,
        breadth_safe=breadth_safe,
        row_count=len(feature_rows),
        feature_ready_count=feature_ready_count,
        capture_public_proxy=capture_public_proxy,
    )
    gates = build_gates(
        universe_safe=universe_safe,
        breadth_safe=breadth_safe,
        raw_universe_present=bool(raw_index),
        proxy_capture=proxy_capture,
        feature_rows=feature_rows,
    )
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": capture_public_proxy,
        "authenticated_api_calls": False,
        "provider_api_calls": capture_public_proxy,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "summary": {
            "candidate_row_count": len(selected),
            "feature_row_count": len(feature_rows),
            "feature_ready_count": feature_ready_count,
            "feature_partial_count": partial_count,
            "asset_counts": counts(row.get("asset_symbol") for row in feature_rows),
            "contract_family_counts": counts(row.get("contract_family") for row in feature_rows),
            "feature_status_counts": counts(row.get("feature_status") for row in feature_rows),
            "max_close_hours": max_close_hours,
            "max_contracts": max_contracts,
            "proxy_asset_count": len(assets),
            "proxy_available_asset_count": sum(
                1 for row in proxy_capture.get("assets", []) if row.get("status") == "available"
            ),
            "gate_counts": gate_counts(gates),
        },
        "source_policy": {
            "official_settlement_source": "CF Benchmarks RTI",
            "official_settlement_source_status": "not_captured_by_this_report",
            "proxy_source_role": "model_feature_only_not_official_settlement",
            "label_policy": "settled Kalshi outcomes or authenticated CF Benchmarks data are required for labels",
            "ev_policy": "This packet does not compute calibrated probability, EV, usable status, sizing, or orders.",
        },
        "inputs": {
            "universe_scan_path": str(universe_scan_path),
            "universe_scan_status": universe.get("status") if isinstance(universe, Mapping) else None,
            "probability_breadth_scout_path": str(probability_breadth_scout_path),
            "probability_breadth_scout_status": breadth.get("status") if isinstance(breadth, Mapping) else None,
            "raw_universe_path": str(raw_universe_path),
            "raw_universe_outside_repo": is_outside_repo(raw_universe_path),
        },
        "proxy_capture": proxy_capture,
        "gates": gates,
        "feature_rows": feature_rows,
        "next_action": next_action(status),
        "safety": safety_flags(public_market_data_calls=capture_public_proxy),
    }


def select_crypto_candidates(
    candidates: Any,
    *,
    raw_index: Mapping[str, Mapping[str, Any]],
    generated_ts: float,
    max_close_hours: float,
    max_contracts: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in candidates if isinstance(candidates, list) else []:
        if not isinstance(row, Mapping) or row.get("classification") != "finance_crypto":
            continue
        ticker = str(row.get("ticker") or "")
        raw = raw_index.get(ticker, {})
        close_ts = close_timestamp(row, raw)
        if close_ts is None:
            continue
        fresh_hours = (close_ts - generated_ts) / 3600
        if fresh_hours <= 0 or fresh_hours > max_close_hours:
            continue
        asset = asset_symbol(row, raw)
        if asset not in ASSET_CONFIG:
            continue
        parsed = parse_contract(row, raw, asset=asset)
        enriched = {
            "contract_ticker": ticker,
            "event_ticker": row.get("event_ticker") or raw.get("event_ticker"),
            "series_ticker": row.get("series_ticker") or raw.get("series_ticker"),
            "title": row.get("title") or raw.get("title"),
            "subtitle": row.get("subtitle") or raw.get("subtitle"),
            "asset_symbol": asset,
            "contract_side": "YES",
            "close_time": row.get("close_time") or raw.get("close_time"),
            "expected_expiration_time": row.get("expected_expiration_time") or raw.get("expected_expiration_time"),
            "fresh_time_to_close_hours": round(fresh_hours, 6),
            "yes_bid": row.get("yes_bid"),
            "yes_ask": row.get("yes_ask"),
            "no_bid": row.get("no_bid"),
            "no_ask": row.get("no_ask"),
            "yes_spread": row.get("yes_spread"),
            "softness_score": row.get("softness_score"),
            "official_rules_hash": row.get("official_rules_hash"),
            "official_rules_source": row.get("official_rules_source"),
            **parsed,
        }
        rows.append(enriched)
    rows.sort(
        key=lambda item: (
            float(item.get("fresh_time_to_close_hours") or 999999.0),
            str(item.get("asset_symbol") or ""),
            str(item.get("contract_ticker") or ""),
        )
    )
    return rows[:max_contracts]


def parse_contract(row: Mapping[str, Any], raw: Mapping[str, Any], *, asset: str | None) -> dict[str, Any]:
    strike_type = str(raw.get("strike_type") or "")
    tags = [str(tag).lower() for tag in raw.get("tags", []) if isinstance(tag, str)]
    series = str(row.get("series_ticker") or raw.get("series_ticker") or "")
    title = str(row.get("title") or raw.get("title") or "").lower()
    if "15 min" in tags or series.endswith("15M") or "next 15 mins" in title:
        family = "fifteen_minute_up_down"
    elif strike_type == "between" or raw.get("cap_strike") is not None:
        family = "range"
    elif strike_type in {"greater_or_equal", "greater"}:
        family = "above"
    elif strike_type in {"less_or_equal", "less"}:
        family = "below"
    else:
        family = "unknown_crypto_contract"
    return {
        "contract_family": family,
        "strike_type": strike_type or None,
        "floor_strike": optional_float(raw.get("floor_strike")),
        "cap_strike": optional_float(raw.get("cap_strike")),
        "official_index": ASSET_CONFIG.get(asset or "", {}).get("official_index"),
        "official_settlement_source": "CF Benchmarks RTI",
        "official_label_status": "not_captured_proxy_feature_packet_only",
    }


def asset_symbol(row: Mapping[str, Any], raw: Mapping[str, Any]) -> str | None:
    for source in (raw.get("tags"), row.get("tags")):
        if isinstance(source, list):
            for tag in source:
                text = str(tag).upper()
                if text in ASSET_CONFIG:
                    return text
    text = " ".join(
        str(value or "")
        for value in [
            row.get("series_ticker"),
            raw.get("series_ticker"),
            row.get("title"),
            raw.get("title"),
            raw.get("series_title"),
        ]
    ).upper()
    for asset in ASSET_ORDER:
        if re.search(rf"\b{re.escape(asset)}\b", text) or f"KX{asset}" in text:
            return asset
    if "BITCOIN" in text:
        return "BTC"
    if "ETHEREUM" in text:
        return "ETH"
    if "SOLANA" in text:
        return "SOL"
    if "DOGECOIN" in text:
        return "DOGE"
    return None


def capture_proxy_sources(
    assets: Sequence[str],
    *,
    raw_proxy_dir: Path,
    fetch_json: Callable[[str], Any] | None,
) -> dict[str, Any]:
    raw_proxy_dir.mkdir(parents=True, exist_ok=True)
    fetched_at = utc_now()
    getter = fetch_json or fetch_public_json
    asset_rows: list[dict[str, Any]] = []
    raw_payloads: dict[str, Any] = {}
    for asset in assets:
        config = ASSET_CONFIG.get(asset)
        if not config:
            asset_rows.append(proxy_asset_unavailable(asset, "asset_not_configured"))
            continue
        product = config["coinbase_product"]
        ticker_url = f"https://api.exchange.coinbase.com/products/{product}/ticker"
        candles_url = "https://api.exchange.coinbase.com/products/" + product + "/candles?" + urllib.parse.urlencode(
            {"granularity": DEFAULT_COINBASE_GRANULARITY_SECONDS}
        )
        started = time.time()
        try:
            ticker_payload = getter(ticker_url)
            candles_payload = getter(candles_url)
            raw_payloads[asset] = {
                "product": product,
                "ticker_url": ticker_url,
                "candles_url": candles_url,
                "ticker_payload": ticker_payload,
                "candles_payload": candles_payload,
            }
            features = summarize_proxy_payloads(ticker_payload, candles_payload)
            asset_rows.append(
                {
                    "asset_symbol": asset,
                    "status": "available",
                    "proxy_source": "coinbase_exchange_public",
                    "proxy_product_id": product,
                    "latency_ms": round((time.time() - started) * 1000, 2),
                    "error": None,
                    "role": "proxy_feature_source_not_official_settlement",
                    **features,
                }
            )
        except Exception as exc:
            asset_rows.append(proxy_asset_unavailable(asset, f"{type(exc).__name__}: {str(exc)[:240]}"))
    raw_snapshot = {
        "schema_version": 1,
        "fetched_at_utc": fetched_at,
        "research_only": True,
        "execution_enabled": False,
        "source_role": "crypto_proxy_feature_source_not_official_settlement",
        "payloads": raw_payloads,
        "safety": safety_flags(public_market_data_calls=True),
    }
    stamp = fetched_at.replace("-", "").replace(":", "")
    raw_snapshot_path = raw_proxy_dir / f"crypto_proxy_feature_capture_{stamp}.json"
    raw_text = json.dumps(raw_snapshot, indent=2, sort_keys=True, default=str) + "\n"
    raw_snapshot_path.write_text(raw_text, encoding="utf-8")
    latest_path = raw_proxy_dir / "crypto_proxy_feature_capture_latest.json"
    latest_path.write_text(raw_text, encoding="utf-8")
    return {
        "status": "public_proxy_feature_capture_completed",
        "fetched_at_utc": fetched_at,
        "raw_snapshot_path": str(raw_snapshot_path),
        "latest_raw_snapshot_path": str(latest_path),
        "raw_snapshot_outside_repo": is_outside_repo(raw_snapshot_path),
        "assets": asset_rows,
    }


def no_proxy_capture(assets: Sequence[str], *, raw_proxy_dir: Path) -> dict[str, Any]:
    return {
        "status": "public_proxy_feature_capture_not_run",
        "raw_proxy_dir": str(raw_proxy_dir),
        "raw_snapshot_outside_repo": is_outside_repo(raw_proxy_dir),
        "assets": [
            {
                "asset_symbol": asset,
                "status": "not_captured",
                "proxy_source": "coinbase_exchange_public",
                "role": "proxy_feature_source_not_official_settlement",
            }
            for asset in assets
        ],
    }


def proxy_asset_unavailable(asset: str, error: str) -> dict[str, Any]:
    config = ASSET_CONFIG.get(asset, {})
    return {
        "asset_symbol": asset,
        "status": "unavailable",
        "proxy_source": "coinbase_exchange_public",
        "proxy_product_id": config.get("coinbase_product"),
        "error": error,
        "role": "proxy_feature_source_not_official_settlement",
    }


def summarize_proxy_payloads(ticker_payload: Any, candles_payload: Any) -> dict[str, Any]:
    price = optional_float(ticker_payload.get("price")) if isinstance(ticker_payload, Mapping) else None
    observed_at = ticker_payload.get("time") if isinstance(ticker_payload, Mapping) else None
    candles = parse_coinbase_candles(candles_payload)
    return {
        "proxy_price": price,
        "proxy_observed_at_utc": observed_at,
        "candle_count": len(candles),
        "latest_candle_close": candles[-1]["close"] if candles else None,
        "proxy_return_5m": trailing_return(candles, 5),
        "proxy_return_15m": trailing_return(candles, 15),
        "proxy_return_60m": trailing_return(candles, 60),
        "proxy_realized_vol_15m": realized_vol(candles, 15),
        "proxy_realized_vol_60m": realized_vol(candles, 60),
    }


def parse_coinbase_candles(value: Any) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    if not isinstance(value, list):
        return rows
    for item in value:
        if not isinstance(item, list) or len(item) < 6:
            continue
        ts, low, high, open_, close, volume = item[:6]
        parsed = {
            "ts": optional_float(ts),
            "low": optional_float(low),
            "high": optional_float(high),
            "open": optional_float(open_),
            "close": optional_float(close),
            "volume": optional_float(volume),
        }
        if all(parsed[key] is not None for key in ("ts", "open", "close")):
            rows.append(parsed)  # type: ignore[arg-type]
    return sorted(rows, key=lambda row: row["ts"])


def trailing_return(candles: Sequence[Mapping[str, float]], minutes: int) -> float | None:
    if len(candles) <= minutes:
        return None
    latest = optional_float(candles[-1].get("close"))
    prior = optional_float(candles[-(minutes + 1)].get("close"))
    if latest is None or prior is None or prior <= 0:
        return None
    return round((latest / prior) - 1.0, 8)


def realized_vol(candles: Sequence[Mapping[str, float]], minutes: int) -> float | None:
    if len(candles) <= minutes:
        return None
    closes = [optional_float(row.get("close")) for row in candles[-(minutes + 1) :]]
    valid = [value for value in closes if value is not None and value > 0]
    if len(valid) < 3:
        return None
    returns = [math.log(valid[idx] / valid[idx - 1]) for idx in range(1, len(valid))]
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / max(len(returns) - 1, 1)
    return round(math.sqrt(variance), 8)


def proxy_feature_index(proxy_capture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row.get("asset_symbol")): row
        for row in proxy_capture.get("assets", [])
        if isinstance(row, Mapping) and row.get("asset_symbol")
    }


def feature_row(candidate: Mapping[str, Any], *, proxy_features: Mapping[str, Mapping[str, Any]], generated_ts: float) -> dict[str, Any]:
    asset = str(candidate.get("asset_symbol") or "")
    proxy = proxy_features.get(asset, {})
    proxy_price = optional_float(proxy.get("proxy_price"))
    floor = optional_float(candidate.get("floor_strike"))
    cap = optional_float(candidate.get("cap_strike"))
    feature_status = "proxy_features_ready" if proxy.get("status") == "available" and proxy_price is not None else "proxy_source_missing"
    return {
        **dict(candidate),
        "fresh_time_to_close_minutes": round(float(candidate.get("fresh_time_to_close_hours") or 0.0) * 60, 4),
        "proxy_source": proxy.get("proxy_source"),
        "proxy_product_id": proxy.get("proxy_product_id"),
        "proxy_price": proxy_price,
        "proxy_observed_at_utc": proxy.get("proxy_observed_at_utc"),
        "proxy_return_5m": proxy.get("proxy_return_5m"),
        "proxy_return_15m": proxy.get("proxy_return_15m"),
        "proxy_return_60m": proxy.get("proxy_return_60m"),
        "proxy_realized_vol_15m": proxy.get("proxy_realized_vol_15m"),
        "proxy_realized_vol_60m": proxy.get("proxy_realized_vol_60m"),
        "proxy_distance_to_floor": round(proxy_price - floor, 8) if proxy_price is not None and floor is not None else None,
        "proxy_distance_to_cap": round(cap - proxy_price, 8) if proxy_price is not None and cap is not None else None,
        "proxy_state": proxy_state(proxy_price=proxy_price, floor=floor, cap=cap, family=str(candidate.get("contract_family") or "")),
        "feature_status": feature_status,
        "feature_policy": "proxy_feature_only_not_official_settlement_label",
        "label_status": "not_labeled_proxy_feature_packet_only",
        "calibrated_probability": None,
        "edge_probability": None,
        "expected_value_per_contract": None,
        "ev_status": "not_evaluated_proxy_feature_packet_only",
        "usable": False,
        "generated_ts": generated_ts,
    }


def proxy_state(*, proxy_price: float | None, floor: float | None, cap: float | None, family: str) -> str | None:
    if proxy_price is None:
        return None
    if family == "range" and floor is not None and cap is not None:
        if proxy_price < floor:
            return "proxy_below_range_not_label"
        if proxy_price > cap:
            return "proxy_above_range_not_label"
        return "proxy_inside_range_not_label"
    if floor is not None:
        return "proxy_above_floor_not_label" if proxy_price >= floor else "proxy_below_floor_not_label"
    return "proxy_observed_not_label"


def feature_packet_status(
    *,
    universe_safe: bool,
    breadth_safe: bool,
    row_count: int,
    feature_ready_count: int,
    capture_public_proxy: bool,
) -> str:
    if not universe_safe:
        return "crypto_proxy_feature_packet_blocked_missing_safe_universe_scan"
    if not breadth_safe:
        return "crypto_proxy_feature_packet_blocked_missing_probability_breadth_scout"
    if row_count == 0:
        return "crypto_proxy_feature_packet_blocked_no_open_fast_crypto_contracts"
    if capture_public_proxy and feature_ready_count == row_count:
        return "crypto_proxy_feature_packet_ready"
    if capture_public_proxy and feature_ready_count > 0:
        return "crypto_proxy_feature_packet_partial_proxy_coverage"
    return "crypto_proxy_feature_packet_blocked_proxy_capture_missing"


def build_gates(
    *,
    universe_safe: bool,
    breadth_safe: bool,
    raw_universe_present: bool,
    proxy_capture: Mapping[str, Any],
    feature_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        gate("safe_universe_scan_present", "pass" if universe_safe else "blocked", "Safe universe scan is required."),
        gate("probability_breadth_scout_present", "pass" if breadth_safe else "blocked", "Probability breadth scout is required."),
        gate("raw_universe_snapshot_available", "pass" if raw_universe_present else "warn", "Raw Kalshi snapshot enriches contract parsing."),
        gate(
            "raw_proxy_snapshot_outside_repo",
            "pass" if proxy_capture.get("raw_snapshot_outside_repo") is True else "blocked",
            "Raw public proxy payloads must stay outside the repo.",
        ),
        gate("feature_rows_keyed", "pass" if feature_rows else "blocked", "Feature rows must be keyed to exact contract tickers."),
        gate(
            "no_ev_or_label_claims",
            "pass"
            if all(row.get("usable") is False and row.get("calibrated_probability") is None for row in feature_rows)
            else "fail",
            "Feature packet must not compute EV, labels, sizing, or usable rows.",
        ),
    ]


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def next_action(status: str) -> dict[str, str]:
    if status == "crypto_proxy_feature_packet_ready":
        return {
            "name": "kalshi_crypto_proxy_observation_loop",
            "why": (
                "Contract-keyed crypto proxy features are available. The next useful step is repeated "
                "feature snapshots plus settled Kalshi outcome matching for OOS falsification."
            ),
            "stop_condition": (
                "Stop before treating proxy states as settlement labels, computing usable EV, sizing, "
                "execution, or account/order paths."
            ),
        }
    if status == "crypto_proxy_feature_packet_partial_proxy_coverage":
        return {
            "name": "kalshi_crypto_proxy_coverage_hardening",
            "why": "Some feature rows are ready, but proxy-source coverage is incomplete.",
            "stop_condition": "Stop before filling missing proxy prices by hand or treating proxy data as labels.",
        }
    return {
        "name": "kalshi_crypto_proxy_feature_packet_blocker_review",
        "why": "The crypto feature packet is blocked or empty.",
        "stop_condition": "Stop before inventing proxy data, labels, calibrated probabilities, EV, or execution evidence.",
    }


def write_crypto_proxy_feature_packet(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-crypto-proxy-feature-packet.json"
    md_path = out_dir / "kalshi-crypto-proxy-feature-packet.md"
    csv_path = out_dir / "kalshi-crypto-proxy-feature-packet.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_feature_csv(report.get("feature_rows", []), csv_path)
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-crypto-proxy-feature-packet.json"
    latest_md = MACRO_DIR / "latest-kalshi-crypto-proxy-feature-packet.md"
    latest_csv = MACRO_DIR / "latest-kalshi-crypto-proxy-feature-packet.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_feature_csv(report.get("feature_rows", []), latest_csv)
    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
        "latest_csv_path": str(latest_csv),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    next_step = report.get("next_action") if isinstance(report.get("next_action"), Mapping) else {}
    lines = [
        "# Kalshi Crypto Proxy Feature Packet",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Research only: `{str(report.get('research_only')).lower()}`",
        f"- Execution enabled: `{str(report.get('execution_enabled')).lower()}`",
        f"- Feature rows: `{summary.get('feature_row_count')}`",
        f"- Feature-ready rows: `{summary.get('feature_ready_count')}`",
        f"- Assets: `{summary.get('asset_counts')}`",
        "",
        "## Source Policy",
        "",
        "- Official settlement source: `CF Benchmarks RTI`",
        "- Public exchange data role: `proxy feature only`",
        "- Labels require settled Kalshi outcomes or authenticated official settlement data.",
        "- This packet does not compute probability, EV, sizing, or execution instructions.",
        "",
        "## Gates",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for item in report.get("gates", []):
        if isinstance(item, Mapping):
            lines.append(f"| `{item.get('name')}` | `{item.get('status')}` | {item.get('reason')} |")
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            f"- Name: `{next_step.get('name')}`",
            f"- Why: {next_step.get('why')}",
            f"- Stop condition: {next_step.get('stop_condition')}",
            "",
        ]
    )
    return "\n".join(lines)


def write_feature_csv(rows: Any, path: Path) -> None:
    feature_rows = [row for row in rows if isinstance(row, Mapping)]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in feature_rows:
            writer.writerow(dict(row))


def raw_market_index(raw_universe: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row.get("ticker")): row
        for row in raw_universe.get("markets", [])
        if isinstance(row, Mapping) and row.get("ticker")
    }


def close_timestamp(candidate: Mapping[str, Any], raw: Mapping[str, Any]) -> float | None:
    for source in (candidate, raw):
        for key in ("close_time", "expected_expiration_time", "expiration_time"):
            value = parse_ts(source.get(key))
            if value is not None:
                return value
    value = optional_float(candidate.get("close_ts"))
    return value


def parse_ts(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def fetch_public_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "predmarket-alpha research-only"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


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


def safe_research_artifact(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    safety = value.get("safety") if isinstance(value.get("safety"), Mapping) else {}
    return (
        value.get("research_only") is True
        and value.get("execution_enabled") is False
        and safety.get("market_execution") is False
        and safety.get("account_or_order_paths") is False
        and safety.get("database_writes") is False
    )


def is_outside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(CONTROL_REPO.resolve())
    except ValueError:
        return True
    return False


def gate_counts(gates: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counter = Counter(str(item.get("status") or "blocked") for item in gates)
    return {"pass": counter["pass"], "warn": counter["warn"], "blocked": counter["blocked"], "fail": counter["fail"]}


def counts(values: Sequence[Any]) -> dict[str, int]:
    counter = Counter(str(value or "unknown") for value in values)
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_json_or_empty(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-scan-path", type=Path, default=DEFAULT_UNIVERSE_SCAN_PATH)
    parser.add_argument("--probability-breadth-scout-path", type=Path, default=DEFAULT_BREADTH_SCOUT_PATH)
    parser.add_argument("--raw-universe-path", type=Path, default=DEFAULT_RAW_UNIVERSE_PATH)
    parser.add_argument("--raw-proxy-dir", type=Path, default=DEFAULT_RAW_PROXY_DIR)
    parser.add_argument("--max-close-hours", type=float, default=DEFAULT_MAX_CLOSE_HOURS)
    parser.add_argument("--max-contracts", type=int, default=DEFAULT_MAX_CONTRACTS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--capture-public-proxy", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_crypto_proxy_feature_packet(
        universe_scan_path=args.universe_scan_path,
        probability_breadth_scout_path=args.probability_breadth_scout_path,
        raw_universe_path=args.raw_universe_path,
        raw_proxy_dir=args.raw_proxy_dir,
        max_close_hours=args.max_close_hours,
        max_contracts=args.max_contracts,
        capture_public_proxy=args.capture_public_proxy,
    )
    if args.write:
        paths = write_crypto_proxy_feature_packet(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
