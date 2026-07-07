#!/usr/bin/env python3
"""Backfill settled Kalshi sports prices into bucket-bias falsification.

This collector is Kalshi-only. It uses settled public market payloads and
historical candlesticks to create replayable observations for the
price-bucket bias family without pretending to have no-vig consensus evidence.
Sportsbook labels, projection outputs, EV, paper stake, and live paths are out
of scope.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import (  # noqa: E402
    counts,
    gate,
    gate_counts,
    iso_from_timestamp,
    iso_time,
    json_float,
    manual_drop_path,
    probability,
    read_json_or_empty,
    safe_stamp,
    safety_flags,
    sha256_or_none,
    timestamp,
)
from predmarket.sports_consensus_falsification import (  # noqa: E402
    build_sports_consensus_falsification,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-resolved-archive-backfill-latest"
DEFAULT_RAW_DIR = manual_drop_path(
    "kalshi_resolved_archive_backfill",
    env_vars=("KALSHI_RESOLVED_ARCHIVE_RAW_DIR",),
)
KALSHI_PUBLIC_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
DEFAULT_SERIES_TICKERS = (
    "KXMLBGAME",
    "KXMLBTOTAL",
    "KXMLBSPREAD",
    "KXWCGAME",
    "KXATPMATCH",
    "KXNFLGAME",
    "KXNBA",
)
ENTRY_HORIZON_SECONDS = (24 * 3600, 6 * 3600, 3600)
CSV_FIELDS = [
    "contract_ticker",
    "event_ticker",
    "series_ticker",
    "sport_key",
    "side",
    "observed_utc",
    "entry_horizon_seconds",
    "kalshi_mid_for_side",
    "yes_outcome",
    "settlement_time_utc",
    "usable",
]
FetchJson = Callable[[str], dict[str, Any]]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_resolved_archive_backfill(
    *,
    markets: Sequence[Mapping[str, Any]],
    candlesticks_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    generated_utc: str | None = None,
    public_market_data_calls: bool = False,
    raw_markets_path: Path | None = None,
    raw_candlesticks_path: Path | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    candles = candlesticks_by_ticker or {}
    eligible_markets = [dict(row) for row in markets if settlement_outcome(row) is not None]
    observations, labels, skipped = archive_observation_rows(
        eligible_markets,
        candlesticks_by_ticker=candles,
    )
    falsification = build_sports_consensus_falsification(
        preflight_report={
            "status": "resolved_archive_backfill_bucket_bias_only",
            "summary": {"valid_candidate_count": len(observations)},
        },
        consensus_observations=observations,
        settlement_labels=labels,
        generated_utc=generated,
        preflight_path=raw_markets_path,
    )
    gates = build_gates(observations=observations, labels=labels, falsification=falsification)
    status = report_status(gates, falsification)
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "family_id": "resolved_archive_price_bucket_bias",
        "public_market_data_calls": public_market_data_calls,
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "inputs": {
            "raw_markets_path": str(raw_markets_path) if raw_markets_path else None,
            "raw_markets_sha256": sha256_or_none(raw_markets_path) if raw_markets_path else None,
            "raw_candlesticks_path": str(raw_candlesticks_path) if raw_candlesticks_path else None,
            "raw_candlesticks_sha256": sha256_or_none(raw_candlesticks_path)
            if raw_candlesticks_path
            else None,
        },
        "method": {
            "source": "Kalshi public settled markets plus Kalshi public candlesticks only.",
            "label_rule": "Exact public Kalshi settlement outcome matched by contract_ticker.",
            "observation_rule": (
                "For each settled contract, select historical candlesticks closest to "
                "pre-registered horizons before settlement."
            ),
            "consensus_boundary": (
                "consensus_probability_for_side is set equal to kalshi_mid_for_side, "
                "so divergence rules cannot create evidence from this artifact."
            ),
            "promotion_boundary": "Research-only falsification input; no EV, paper, or live output.",
        },
        "summary": {
            "raw_market_count": len(markets),
            "eligible_settled_market_count": len(eligible_markets),
            "observation_count": len(observations),
            "label_count": len(labels),
            "distinct_contract_count": len({row["contract_ticker"] for row in labels}),
            "candlestick_market_count": len(candles),
            "skipped_market_count": len(skipped),
            "sport_key_counts": counts([row.get("sport_key") for row in observations]),
            "series_ticker_counts": counts([row.get("series_ticker") for row in labels]),
            "falsification_status": falsification.get("status"),
            "tested_hypothesis_count": falsification.get("summary", {}).get(
                "tested_hypothesis_count"
            ),
            "fdr_survivor_count": falsification.get("summary", {}).get("fdr_survivor_count"),
            "max_hypothesis_oos_count": falsification.get("summary", {}).get(
                "max_hypothesis_oos_count"
            ),
            "gate_counts": gate_counts(gates),
        },
        "gates": gates,
        "observations": observations,
        "labels": labels,
        "skipped_markets_sample": skipped[:50],
        "falsification": falsification,
        "next_action": next_action(status),
        "safety": safety_flags(public_market_data_calls=public_market_data_calls),
    }


def archive_observation_rows(
    markets: Sequence[Mapping[str, Any]],
    *,
    candlesticks_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    observations: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for market in markets:
        ticker = str(market.get("ticker") or market.get("contract_ticker") or "").strip()
        yes_outcome = settlement_outcome(market)
        settled_ts = settlement_timestamp(market)
        if not ticker or yes_outcome is None or settled_ts is None:
            skipped.append({"ticker": ticker or None, "reason": "missing_ticker_or_settlement"})
            continue
        selected = select_entry_candles(
            candlesticks_by_ticker.get(ticker, []),
            settlement_ts=settled_ts,
        )
        if not selected:
            selected = [fallback_market_candle(market, settled_ts=settled_ts)]
        label = label_row(market, ticker=ticker, yes_outcome=yes_outcome, settled_ts=settled_ts)
        labels.append(label)
        for candle, horizon in selected:
            row = observation_row(
                market,
                candle,
                ticker=ticker,
                yes_outcome=yes_outcome,
                settled_ts=settled_ts,
                entry_horizon_seconds=horizon,
            )
            if row is None:
                skipped.append({"ticker": ticker, "reason": "missing_price_for_selected_candle"})
                continue
            observations.append(row)
    observations.sort(key=lambda row: (str(row["observed_utc"]), str(row["contract_ticker"])))
    labels.sort(key=lambda row: str(row["contract_ticker"]))
    return observations, labels, skipped


def select_entry_candles(
    candles: Sequence[Mapping[str, Any]], *, settlement_ts: float
) -> list[tuple[Mapping[str, Any], int]]:
    parsed = [
        (timestamp(candle.get("end_period_ts") or candle.get("ts") or candle.get("time")), candle)
        for candle in candles
        if isinstance(candle, Mapping)
    ]
    valid = [(ts, candle) for ts, candle in parsed if ts is not None and ts < settlement_ts]
    if not valid:
        return []
    selected: list[tuple[Mapping[str, Any], int]] = []
    used_times: set[float] = set()
    for horizon in ENTRY_HORIZON_SECONDS:
        target = settlement_ts - horizon
        before = [
            (abs(float(ts) - target), float(ts), candle) for ts, candle in valid if ts <= target
        ]
        if not before:
            continue
        _, ts, candle = min(before, key=lambda item: (item[0], -item[1]))
        if ts in used_times:
            continue
        used_times.add(ts)
        selected.append((candle, horizon))
    return selected


def observation_row(
    market: Mapping[str, Any],
    candle: Mapping[str, Any],
    *,
    ticker: str,
    yes_outcome: int,
    settled_ts: float,
    entry_horizon_seconds: int,
) -> dict[str, Any] | None:
    mid = candle_mid(candle)
    observed = iso_time(candle.get("end_period_ts") or candle.get("ts") or candle.get("time"))
    if mid is None or observed is None:
        return None
    series = series_ticker(market, ticker)
    event = str(market.get("event_ticker") or derive_event_ticker(ticker) or ticker)
    sport = sport_key(series, ticker)
    return {
        "schema_version": "KalshiResolvedArchiveObservationV1",
        "observation_id": f"resolved_archive_{ticker}_{entry_horizon_seconds}",
        "contract_ticker": ticker,
        "event_ticker": event,
        "series_ticker": series,
        "side": "yes",
        "family_id": "resolved_archive_price_bucket_bias",
        "sport_key": sport,
        "market_key": series,
        "cluster_key": f"{sport}|{series}|{event}",
        "observed_utc": observed,
        "decision_time": observed,
        "quote_time": observed,
        "entry_horizon_seconds": int(entry_horizon_seconds),
        "close_time": iso_time(market.get("close_time")),
        "expected_expiration_time": iso_from_timestamp(settled_ts),
        "kalshi_mid_for_side": json_float(mid),
        "consensus_probability_for_side": json_float(mid),
        "consensus_no_vig_probability_for_side": json_float(mid),
        "divergence": 0.0,
        "book_count": 0,
        "distinct_books": [],
        "timestamp_skew_seconds": 0.0,
        "consensus_method": "none_kalshi_resolved_archive_bucket_bias_only",
        "yes_outcome": int(yes_outcome),
        "side_outcome": int(yes_outcome),
        "label_status": "labeled_from_public_kalshi_resolved_archive",
        "label_source": "public_kalshi_settled_market_payload",
        "settlement_time_utc": iso_from_timestamp(settled_ts),
        "calibrated_probability": None,
        "expected_value_per_contract": None,
        "usable": False,
        "research_only": True,
        "execution_enabled": False,
    }


def label_row(
    market: Mapping[str, Any], *, ticker: str, yes_outcome: int, settled_ts: float
) -> dict[str, Any]:
    return {
        "contract_ticker": ticker,
        "event_ticker": market.get("event_ticker") or derive_event_ticker(ticker),
        "series_ticker": series_ticker(market, ticker),
        "side": "yes",
        "yes_outcome": int(yes_outcome),
        "side_outcome": int(yes_outcome),
        "settled_time": iso_from_timestamp(settled_ts),
        "settlement_time_utc": iso_from_timestamp(settled_ts),
        "settlement_result": market.get("result") or market.get("expiration_value"),
        "settlement_value_dollars": market.get("settlement_value_dollars"),
        "label_source": "public_kalshi_settled_market_payload",
        "label_status": "labeled_from_public_kalshi_resolved_archive",
        "usable": False,
        "research_only": True,
        "execution_enabled": False,
    }


def build_gates(
    *,
    observations: Sequence[Mapping[str, Any]],
    labels: Sequence[Mapping[str, Any]],
    falsification: Mapping[str, Any],
) -> list[dict[str, str]]:
    tested = int(falsification.get("summary", {}).get("tested_hypothesis_count") or 0)
    return [
        gate(
            "resolved_markets_available",
            "pass" if labels else "blocked",
            f"{len(labels)} exact settled Kalshi contract label(s).",
        ),
        gate(
            "historical_prices_available",
            "pass" if observations else "blocked",
            f"{len(observations)} resolved archive price observation(s).",
        ),
        gate(
            "bucket_falsification_reached",
            "pass" if tested else "blocked",
            f"{tested} hypothesis cell(s) reached OOS/FDR testing.",
        ),
        gate(
            "no_consensus_or_ev_claim",
            "pass"
            if all(float(row.get("divergence") or 0.0) == 0.0 for row in observations)
            else "fail",
            "Backfill can only feed price-bucket bias; divergence rules stay neutral.",
        ),
        gate("no_live_or_paper_paths", "pass", "No EV, paper stake, account state, or orders."),
    ]


def report_status(gates: Sequence[Mapping[str, Any]], falsification: Mapping[str, Any]) -> str:
    if any(item.get("status") == "fail" for item in gates):
        return "kalshi_resolved_archive_backfill_failed_safety_gate"
    if not falsification.get("summary", {}).get("tested_hypothesis_count"):
        return "kalshi_resolved_archive_backfill_ready_insufficient_test_power"
    if falsification.get("summary", {}).get("fdr_survivor_count"):
        return "kalshi_resolved_archive_backfill_ready_with_fdr_survivors"
    return "kalshi_resolved_archive_backfill_ready_no_fdr_survivors"


def next_action(status: str) -> dict[str, str]:
    if status == "kalshi_resolved_archive_backfill_ready_with_fdr_survivors":
        return {
            "name": "kalshi_resolved_archive_bucket_bias_downstream_gate_chain",
            "why": "At least one bucket-bias cell survived OOS/FDR; let existing cost/capacity/correlation/decay gates decide.",
            "stop_condition": "Stop before paper stake unless every downstream gate passes.",
        }
    return {
        "name": "kalshi_resolved_archive_backfill_scale",
        "why": "Resolved archive evidence exists but has not produced an FDR survivor at current gates.",
        "stop_condition": "Stop before lowering thresholds or adding post-hoc buckets.",
    }


def capture_public_archive(
    *,
    series_tickers: Sequence[str],
    raw_dir: Path,
    limit: int,
    max_pages: int,
    days_back: int,
    period_interval: int,
    request_delay_seconds: float = 0.0,
    existing_candlesticks_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    fetch_json: FetchJson = None,
    generated_utc: str | None = None,
) -> tuple[Path, Path]:
    generated = generated_utc or utc_now()
    fetch = fetch_json or fetch_json_url
    raw_dir.mkdir(parents=True, exist_ok=True)
    min_settled_ts = int(time.time()) - int(days_back * 86400)
    markets = fetch_settled_markets(
        series_tickers=series_tickers,
        limit=limit,
        max_pages=max_pages,
        min_settled_ts=min_settled_ts,
        fetch_json=fetch,
    )
    candles = fetch_candlesticks_for_markets(
        markets,
        period_interval=period_interval,
        min_settled_ts=min_settled_ts,
        request_delay_seconds=request_delay_seconds,
        existing_candlesticks_by_ticker=existing_candlesticks_by_ticker,
        fetch_json=fetch,
    )
    stamp = safe_stamp(generated)
    markets_path = raw_dir / f"kalshi_resolved_archive_markets_{stamp}.json"
    candles_path = raw_dir / f"kalshi_resolved_archive_candlesticks_{stamp}.json"
    write_json(markets_path, raw_payload(generated, "settled_markets", markets))
    write_json(candles_path, raw_payload(generated, "candlesticks_by_ticker", candles))
    write_json(
        raw_dir / "kalshi_resolved_archive_markets_latest.json", read_json_or_empty(markets_path)
    )
    write_json(
        raw_dir / "kalshi_resolved_archive_candlesticks_latest.json",
        read_json_or_empty(candles_path),
    )
    return markets_path, candles_path


def fetch_settled_markets(
    *,
    series_tickers: Sequence[str],
    limit: int,
    max_pages: int,
    min_settled_ts: int,
    fetch_json: FetchJson,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for series in series_tickers:
        cursor = ""
        for _page in range(max(0, max_pages)):
            params = {
                "status": "settled",
                "series_ticker": series,
                "limit": str(limit),
                "cursor": cursor or None,
                "min_settled_ts": str(min_settled_ts),
            }
            payload = fetch_json(f"{KALSHI_PUBLIC_BASE_URL}/markets?{urlencode_clean(params)}")
            output.extend(
                dict(row) for row in payload.get("markets", []) if isinstance(row, Mapping)
            )
            cursor = str(payload.get("cursor") or "")
            if not cursor:
                break
    return output


def fetch_candlesticks_for_markets(
    markets: Sequence[Mapping[str, Any]],
    *,
    period_interval: int,
    min_settled_ts: int,
    request_delay_seconds: float = 0.0,
    existing_candlesticks_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    fetch_json: FetchJson,
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    existing = existing_candlesticks_by_ticker or {}
    for market in markets:
        ticker = str(market.get("ticker") or "").strip()
        if not ticker:
            continue
        cached = existing.get(ticker)
        if isinstance(cached, Sequence) and cached:
            output[ticker] = [dict(row) for row in cached if isinstance(row, Mapping)]
            continue
        series = series_ticker(market, ticker)
        start_ts = int(
            timestamp(market.get("open_time") or market.get("created_time")) or min_settled_ts
        )
        end_ts = int(settlement_timestamp(market) or time.time())
        path = f"/series/{urllib.parse.quote(series, safe='')}/markets/{urllib.parse.quote(ticker, safe='')}/candlesticks"
        params = urlencode_clean(
            {
                "start_ts": str(start_ts),
                "end_ts": str(end_ts),
                "period_interval": str(period_interval),
            }
        )
        payload: dict[str, Any] = {}
        try:
            payload = fetch_json(f"{KALSHI_PUBLIC_BASE_URL}{path}?{params}")
        except HTTPError as exc:
            if exc.code not in {404, 422}:
                output[ticker] = []
                if request_delay_seconds > 0:
                    time.sleep(request_delay_seconds)
                continue
            try:
                payload = fetch_json(
                    f"{KALSHI_PUBLIC_BASE_URL}/historical/markets/{urllib.parse.quote(ticker, safe='')}/candlesticks?{params}"
                )
            except Exception:
                payload = {}
        except Exception:
            try:
                payload = fetch_json(
                    f"{KALSHI_PUBLIC_BASE_URL}/historical/markets/{urllib.parse.quote(ticker, safe='')}/candlesticks?{params}"
                )
            except Exception:
                payload = {}
        rows = payload.get("candlesticks", [])
        output[ticker] = [dict(row) for row in rows if isinstance(row, Mapping)]
        if request_delay_seconds > 0:
            time.sleep(request_delay_seconds)
    return output


def fetch_json_url(url: str, *, max_retries: int = 3) -> dict[str, Any]:
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                payload = json.load(response)
            return payload if isinstance(payload, dict) else {}
        except HTTPError as exc:
            if exc.code != 429 or attempt >= max_retries:
                raise
            retry_after = exc.headers.get("Retry-After")
            delay = min(float(retry_after or 2**attempt), 30.0)
            time.sleep(max(delay, 0.0))
    return {}


def load_raw_markets(path: Path | None) -> list[dict[str, Any]]:
    payload = read_json_or_empty(path) if path and path.is_file() else {}
    rows = payload.get("settled_markets") or payload.get("markets") or payload.get("rows") or []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def load_raw_candlesticks(path: Path | None) -> dict[str, list[dict[str, Any]]]:
    payload = read_json_or_empty(path) if path and path.is_file() else {}
    raw = payload.get("candlesticks_by_ticker") or payload.get("candles") or {}
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(ticker): [dict(row) for row in rows if isinstance(row, Mapping)]
        for ticker, rows in raw.items()
        if isinstance(rows, list)
    }


def settlement_outcome(market: Mapping[str, Any]) -> int | None:
    settlement = probability(market.get("settlement_value_dollars", market.get("settlement_value")))
    if settlement is not None:
        if settlement >= 0.999:
            return 1
        if settlement <= 0.001:
            return 0
    result = str(market.get("result") or market.get("expiration_value") or "").strip().lower()
    if result in {"yes", "true", "1"}:
        return 1
    if result in {"no", "false", "0"}:
        return 0
    return None


def settlement_timestamp(market: Mapping[str, Any]) -> float | None:
    return timestamp(
        market.get("settlement_ts")
        or market.get("settled_time")
        or market.get("expiration_time")
        or market.get("close_time")
    )


def candle_mid(candle: Mapping[str, Any]) -> float | None:
    price = nested_probability(candle.get("price"), "close")
    bid = nested_probability(candle.get("yes_bid"), "close")
    ask = nested_probability(candle.get("yes_ask"), "close")
    if price is not None:
        return price
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    return probability(candle.get("price") or candle.get("close") or candle.get("last_price"))


def nested_probability(value: Any, key: str) -> float | None:
    if not isinstance(value, Mapping):
        return None
    return probability(value.get(key) or value.get(f"{key}_dollars"))


def fallback_market_candle(
    market: Mapping[str, Any], *, settled_ts: float
) -> tuple[dict[str, Any], int]:
    observed_ts = timestamp(market.get("updated_time") or market.get("created_time")) or (
        settled_ts - 1
    )
    price = probability(market.get("last_price_dollars") or market.get("previous_price_dollars"))
    bid = probability(market.get("yes_bid_dollars"))
    ask = probability(market.get("yes_ask_dollars"))
    if price is None and bid is not None and ask is not None:
        price = (bid + ask) / 2.0
    return (
        {
            "end_period_ts": iso_from_timestamp(min(observed_ts, settled_ts - 1)),
            "price": {"close": price if price is not None else 0.5},
            "yes_bid": {"close": bid},
            "yes_ask": {"close": ask},
        },
        0,
    )


def series_ticker(market: Mapping[str, Any], ticker: str) -> str:
    explicit = str(market.get("series_ticker") or "").strip()
    if explicit:
        return explicit
    event = str(market.get("event_ticker") or "").strip()
    if "-" in event:
        return event.split("-", 1)[0]
    return ticker.split("-", 1)[0]


def derive_event_ticker(ticker: str) -> str | None:
    pieces = ticker.split("-")
    return "-".join(pieces[:2]) if len(pieces) >= 2 else (pieces[0] if pieces else None)


def sport_key(series: str, ticker: str) -> str:
    text = f"{series} {ticker}".upper()
    if "MLB" in text:
        return "baseball_mlb"
    if "ATP" in text or "WIM" in text:
        return "tennis_atp"
    if "WC" in text or "FIFA" in text:
        return "soccer_world_cup"
    if "NFL" in text:
        return "football_nfl"
    if "NBA" in text:
        return "basketball_nba"
    return "other_sports"


def raw_payload(generated_utc: str, key: str, rows: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_utc": generated_utc,
        "status": f"kalshi_resolved_archive_raw_{key}_ready",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        key: rows,
        "safety": safety_flags(public_market_data_calls=True),
    }


def write_outputs(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-resolved-archive-backfill.json"
    md_path = out_dir / "kalshi-resolved-archive-backfill.md"
    csv_path = out_dir / "kalshi-resolved-archive-backfill.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("observations", []), csv_path)
    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
    }
    if path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-resolved-archive-backfill.json"
        latest_md = MACRO_DIR / "latest-kalshi-resolved-archive-backfill.md"
        latest_csv = MACRO_DIR / "latest-kalshi-resolved-archive-backfill.csv"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        write_csv(report.get("observations", []), latest_csv)
        paths.update(
            {
                "latest_json_path": str(latest_json),
                "latest_markdown_path": str(latest_md),
                "latest_csv_path": str(latest_csv),
            }
        )
    return paths


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Resolved Archive Backfill",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Settled labels: `{summary.get('label_count')}`",
        f"- Observations: `{summary.get('observation_count')}`",
        f"- Tested hypotheses: `{summary.get('tested_hypothesis_count')}`",
        f"- FDR survivors: `{summary.get('fdr_survivor_count')}`",
        "",
        "## Gates",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for item in report.get("gates", []):
        if isinstance(item, Mapping):
            lines.append(
                f"| `{item.get('name')}` | `{item.get('status')}` | {item.get('reason')} |"
            )
    lines.extend(
        [
            "",
            "Research-only Kalshi archive evidence. No sportsbook labels, no EV, no paper stake, and no live execution.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in CSV_FIELDS})


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )


def path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def urlencode_clean(params: Mapping[str, Any]) -> str:
    return urllib.parse.urlencode(
        {key: value for key, value in params.items() if value is not None}
    )


def parse_series(value: str) -> list[str]:
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--markets-raw-path", type=Path)
    parser.add_argument("--candlesticks-raw-path", type=Path)
    parser.add_argument("--series-tickers", default=",".join(DEFAULT_SERIES_TICKERS))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--days-back", type=int, default=120)
    parser.add_argument("--period-interval", type=int, default=60)
    parser.add_argument("--request-delay-seconds", type=float, default=0.0)
    parser.add_argument("--capture-public", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    generated = utc_now()
    markets_path = args.markets_raw_path
    candles_path = args.candlesticks_raw_path
    public_calls = False
    if args.capture_public:
        existing_candles = load_raw_candlesticks(candles_path)
        markets_path, candles_path = capture_public_archive(
            series_tickers=parse_series(args.series_tickers),
            raw_dir=args.raw_dir,
            limit=args.limit,
            max_pages=args.max_pages,
            days_back=args.days_back,
            period_interval=args.period_interval,
            request_delay_seconds=float(args.request_delay_seconds),
            existing_candlesticks_by_ticker=existing_candles,
            generated_utc=generated,
        )
        public_calls = True
    report = build_resolved_archive_backfill(
        markets=load_raw_markets(markets_path),
        candlesticks_by_ticker=load_raw_candlesticks(candles_path),
        generated_utc=generated,
        public_market_data_calls=public_calls,
        raw_markets_path=markets_path,
        raw_candlesticks_path=candles_path,
    )
    if args.write:
        paths = write_outputs(report, args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
