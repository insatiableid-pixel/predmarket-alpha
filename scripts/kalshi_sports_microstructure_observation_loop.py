#!/usr/bin/env python3
"""Capture sports orderbook microstructure evidence for non-directional gates."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = CONTROL_REPO / "scripts"
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kalshi_ghost_listing_depth_diagnostic import (  # noqa: E402
    ask_levels,
    capture_public_orderbooks,
    load_latest_orderbook_capture,
    orderbook_index,
)

from predmarket.kalshi_universe_scan import DEFAULT_WORLD_CUP_SOCCER_SERIES  # noqa: E402
from predmarket.shared_helpers import (  # noqa: E402
    counts,
    iso_from_timestamp,
    json_float,
    manual_drop_path,
    outside_repo,
    probability,
    read_json_or_empty,
    safe_research_artifact,
    safe_stamp,
    safety_flags,
    sha256_or_none,
    timestamp,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
KALSHI_PUBLIC_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
DEFAULT_UNIVERSE_SCAN_PATH = MACRO_DIR / "latest-kalshi-universe-scan.json"
DEFAULT_RAW_ORDERBOOK_DIR = manual_drop_path("kalshi_sports_microstructure_orderbooks")
DEFAULT_OBSERVATION_DIR = manual_drop_path("kalshi_sports_microstructure_observations")
DEFAULT_SETTLED_RAW_DIR = manual_drop_path("kalshi_sports_microstructure_settlements")
DEFAULT_SETTLED_SNAPSHOT_PATH = (
    DEFAULT_SETTLED_RAW_DIR / "kalshi_sports_microstructure_observed_markets_latest.json"
)
DEFAULT_LABEL_DIR = manual_drop_path("kalshi_sports_microstructure_labels")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-microstructure-observation-loop-latest"
DEFAULT_MAX_TICKERS = 120
DEFAULT_MAX_CLOSE_HOURS = 48.0
DEFAULT_DEPTH = 0
DEFAULT_DELAY_SECONDS = 0.03
DEFAULT_OBSERVED_PROBE_MAX_TICKERS = 300
WORLD_CUP_SERIES = frozenset(DEFAULT_WORLD_CUP_SOCCER_SERIES)
SURFACE_QUOTA_WEIGHTS = {
    "world_cup_soccer": 2,
    "mlb": 3,
    "atp": 2,
    "nfl": 1,
}
PREFERRED_SERIES_RANKS = {
    "KXWCGAME": 0,
    "KXWC2H": 1,
    "KXWCSPREAD": 2,
    "KXWCSTART": 4,
    "KXATPMATCH": 0,
    "KXMLBGAME": 0,
    "KXKBOGAME": 1,
    "KXLMBGAME": 1,
    "KXNPBGAME": 1,
    "KXMLBSPREAD": 2,
    "KXMLBTOTAL": 3,
    "KXMLBEXTRAS": 4,
}

CSV_FIELDS = [
    "snapshot_id",
    "contract_ticker",
    "sport_surface",
    "observed_at_utc",
    "settlement_time",
    "time_to_settlement_seconds",
    "best_yes_bid",
    "best_yes_ask",
    "best_no_bid",
    "best_no_ask",
    "yes_mid",
    "yes_spread",
    "no_spread",
    "yes_bid_depth_top1",
    "no_bid_depth_top1",
    "yes_ask_depth_top1",
    "no_ask_depth_top1",
    "yes_depth_top5",
    "no_depth_top5",
    "total_depth_contracts",
    "depth_imbalance_yes",
    "depth_imbalance_delta",
    "mid_delta_from_previous_snapshot",
    "raw_orderbook_sha256",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_sports_microstructure_observation_loop(
    *,
    universe_scan_path: Path = DEFAULT_UNIVERSE_SCAN_PATH,
    raw_orderbook_dir: Path = DEFAULT_RAW_ORDERBOOK_DIR,
    observation_dir: Path = DEFAULT_OBSERVATION_DIR,
    settled_snapshot_path: Path = DEFAULT_SETTLED_SNAPSHOT_PATH,
    settled_raw_dir: Path = DEFAULT_SETTLED_RAW_DIR,
    label_dir: Path = DEFAULT_LABEL_DIR,
    generated_utc: str | None = None,
    max_tickers: int = DEFAULT_MAX_TICKERS,
    max_close_hours: float = DEFAULT_MAX_CLOSE_HOURS,
    depth: int = DEFAULT_DEPTH,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    observed_probe_max_tickers: int = DEFAULT_OBSERVED_PROBE_MAX_TICKERS,
    capture_orderbooks: bool = False,
    probe_observed_public: bool = False,
    fetch_json: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    universe = read_json_or_empty(universe_scan_path)
    candidates = select_current_sports_candidates(
        universe,
        generated_utc=generated,
        max_tickers=max_tickers,
        max_close_hours=max_close_hours,
    )
    capture = (
        capture_public_orderbooks(
            tickers=[str(row["ticker"]) for row in candidates],
            raw_orderbook_dir=raw_orderbook_dir,
            generated_utc=generated,
            depth=depth,
            delay_seconds=delay_seconds,
            fetch_json=fetch_json,
        )
        if capture_orderbooks
        else load_latest_orderbook_capture(raw_orderbook_dir)
    )
    orderbooks = orderbook_index(capture)
    previous_rows = load_observation_rows(observation_dir)
    previous = previous_observation_index(previous_rows)
    rows = [
        microstructure_row(
            candidate,
            orderbook=orderbooks.get(str(candidate.get("ticker"))),
            previous=previous.get(str(candidate.get("ticker"))),
            generated_utc=generated,
            raw_orderbook_dir=raw_orderbook_dir,
        )
        for candidate in candidates
        if orderbooks.get(str(candidate.get("ticker"))) is not None
    ]
    history_rows = dedupe_observation_rows([*previous_rows, *rows])
    due_tickers = due_observed_tickers(
        history_rows, generated_utc=generated, max_tickers=observed_probe_max_tickers
    )
    if probe_observed_public and due_tickers:
        settled_snapshot_path = capture_public_observed_markets_snapshot(
            tickers=due_tickers,
            raw_dir=settled_raw_dir,
            base_snapshot_path=settled_snapshot_path,
            generated_utc=generated,
            fetch_json=fetch_json,
        )
    settled_snapshot = read_json_or_empty(settled_snapshot_path)
    existing_labels = load_label_rows(label_dir)
    computed_labels, blocked_labels = label_observations(
        history_rows, settled_market_index(settled_snapshot)
    )
    existing_label_ids = {str(row.get("snapshot_id") or "") for row in existing_labels}
    new_labels = [
        row
        for row in computed_labels
        if str(row.get("snapshot_id") or "") not in existing_label_ids
    ]
    all_labels = dedupe_observation_rows([*existing_labels, *computed_labels])
    labeled_history_rows = attach_settlement_labels(history_rows, all_labels)
    packet = safe_packet(generated_utc=generated, rows=rows, universe_scan_path=universe_scan_path)
    label_packet = safe_label_packet(
        generated_utc=generated,
        rows=new_labels,
        observation_dir=observation_dir,
        settled_snapshot_path=settled_snapshot_path,
    )
    summary = build_summary(
        universe=universe,
        candidates=candidates,
        rows=rows,
        history_rows=labeled_history_rows,
        label_rows=all_labels,
        blocked_label_rows=blocked_labels,
        due_tickers=due_tickers,
        settled_snapshot=settled_snapshot,
        capture=capture,
        raw_orderbook_dir=raw_orderbook_dir,
        observation_dir=observation_dir,
        label_dir=label_dir,
    )
    gates = build_gates(summary)
    status = report_status(summary, gates)
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": capture_orderbooks,
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "inputs": {
            "universe_scan_path": str(universe_scan_path),
            "universe_scan_sha256": sha256_or_none(universe_scan_path),
            "raw_orderbook_dir": str(raw_orderbook_dir),
            "observation_dir": str(observation_dir),
            "settled_snapshot_path": str(settled_snapshot_path),
            "settled_snapshot_sha256": sha256_or_none(settled_snapshot_path),
            "settled_raw_dir": str(settled_raw_dir),
            "label_dir": str(label_dir),
            "max_tickers": max_tickers,
            "max_close_hours": max_close_hours,
            "depth": depth,
            "observed_probe_max_tickers": observed_probe_max_tickers,
        },
        "method": {
            "purpose": "Create replayable pre-close sports microstructure evidence for flow and passive-liquidity falsification.",
            "selection": "Diversified current World Cup/FIFA, MLB, ATP, then NFL rows within the configured close-time window, preferring quote-hinted game/match markets before thin prop clutter.",
            "orderbook_source": "Unauthenticated Kalshi public orderbook endpoint or latest saved public capture.",
            "boundary": "No calibrated probabilities, EV rows, paper stake, account state, orders, or execution are emitted.",
        },
        "summary": summary,
        "gates": gates,
        "observation_packet": packet,
        "label_packet": label_packet,
        "observation_rows_sample": rows[:50],
        "label_rows_sample": all_labels[:50],
        "blocked_label_rows_sample": blocked_labels[:50],
        "historical_observation_rows_sample": labeled_history_rows[-50:],
        "next_action": next_action(status),
        "safety": safety_flags(
            public_market_data_calls=capture_orderbooks or probe_observed_public
        ),
    }


def select_current_sports_candidates(
    universe: Mapping[str, Any],
    *,
    generated_utc: str,
    max_tickers: int,
    max_close_hours: float,
) -> list[dict[str, Any]]:
    generated_ts = timestamp(generated_utc) or 0.0
    rows = universe.get("candidates", []) if isinstance(universe.get("candidates"), list) else []
    eligible: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        surface = sport_surface(row)
        if surface is None:
            continue
        if str(row.get("gate_status") or "") not in {"pass", "warn"}:
            continue
        ticker = str(row.get("ticker") or "")
        if not ticker:
            continue
        due_ts = timestamp(
            row.get("settlement_time")
            or row.get("expected_expiration_time")
            or row.get("close_time")
        )
        if due_ts is None or due_ts <= generated_ts:
            continue
        hours = (due_ts - generated_ts) / 3600.0
        if hours > max_close_hours:
            continue
        item = dict(row)
        item["_sport_surface"] = surface
        item["_hours_to_settlement"] = hours
        item["_quote_hint_score"] = quote_hint_score(item)
        item["_series_priority"] = series_priority(item)
        eligible.append(item)
    return diversified_candidate_selection(eligible, max_tickers=max_tickers)


def diversified_candidate_selection(
    eligible: Sequence[Mapping[str, Any]], *, max_tickers: int
) -> list[dict[str, Any]]:
    limit = max(0, int(max_tickers))
    if limit <= 0:
        return []
    by_surface: dict[str, list[dict[str, Any]]] = {}
    for row in eligible:
        surface = str(row.get("_sport_surface") or "")
        if not surface:
            continue
        by_surface.setdefault(surface, []).append(dict(row))
    for rows in by_surface.values():
        rows.sort(key=sports_candidate_sort_key)
    surfaces = sorted(by_surface, key=surface_priority)
    quotas = surface_quotas(surfaces, limit)
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for surface in surfaces:
        quota = quotas.get(surface, 0)
        for row in by_surface[surface][:quota]:
            ticker = str(row.get("ticker") or "")
            if ticker and ticker not in seen:
                selected.append(row)
                seen.add(ticker)
    if len(selected) < limit:
        remaining = [
            dict(row)
            for row in eligible
            if str(row.get("ticker") or "") and str(row.get("ticker") or "") not in seen
        ]
        remaining.sort(
            key=lambda item: (
                sports_candidate_sort_key(item),
                surface_priority(str(item.get("_sport_surface") or "")),
            )
        )
        for row in remaining:
            if len(selected) >= limit:
                break
            ticker = str(row.get("ticker") or "")
            if ticker and ticker not in seen:
                selected.append(row)
                seen.add(ticker)
    selected.sort(
        key=lambda item: (
            surface_priority(str(item.get("_sport_surface") or "")),
            sports_candidate_sort_key(item),
        )
    )
    return selected[:limit]


def surface_quotas(surfaces: Sequence[str], limit: int) -> dict[str, int]:
    active = [surface for surface in surfaces if surface]
    if not active or limit <= 0:
        return {}
    total_weight = sum(SURFACE_QUOTA_WEIGHTS.get(surface, 1) for surface in active)
    quotas = {
        surface: max(1, round(limit * SURFACE_QUOTA_WEIGHTS.get(surface, 1) / total_weight))
        for surface in active
    }
    while sum(quotas.values()) > limit:
        surface = max(active, key=lambda item: (quotas[item], -surface_priority(item), item))
        quotas[surface] -= 1
    while sum(quotas.values()) < limit:
        surface = max(
            active,
            key=lambda item: (SURFACE_QUOTA_WEIGHTS.get(item, 1), -surface_priority(item), item),
        )
        quotas[surface] += 1
    return quotas


def sports_candidate_sort_key(row: Mapping[str, Any]) -> tuple[int, int, float, float, str]:
    quote_score = float(row.get("_quote_hint_score") or quote_hint_score(row))
    return (
        0 if quote_score > 0 else 1,
        int(row.get("_series_priority") or series_priority(row)),
        -quote_score,
        float(row.get("_hours_to_settlement") or 999999.0),
        str(row.get("ticker") or ""),
    )


def quote_hint_score(row: Mapping[str, Any]) -> float:
    bid = as_float(row.get("yes_bid"))
    ask = as_float(row.get("yes_ask"))
    if bid is None or ask is None or not (0.0 <= bid < ask <= 1.0):
        return 0.0
    spread = max(0.0, ask - bid)
    volume = max(0.0, as_float(row.get("volume")) or 0.0)
    open_interest = max(0.0, as_float(row.get("open_interest")) or 0.0)
    liquidity = min(1_000_000.0, volume + open_interest) / 1_000_000.0
    spread_bonus = max(0.0, 0.25 - spread)
    return round(1.0 + spread_bonus + liquidity, 10)


def series_priority(row: Mapping[str, Any]) -> int:
    series = str(row.get("series_ticker") or "").upper()
    return PREFERRED_SERIES_RANKS.get(series, 9)


def sport_surface(row: Mapping[str, Any]) -> str | None:
    classification = str(row.get("classification") or "")
    series = str(row.get("series_ticker") or "").upper()
    if classification == "other_sports" and series in WORLD_CUP_SERIES:
        return "world_cup_soccer"
    if classification in {"mlb", "atp", "nfl"}:
        return classification
    return None


def surface_priority(surface: str) -> int:
    return {"world_cup_soccer": 0, "mlb": 1, "atp": 2, "nfl": 3}.get(surface, 9)


def microstructure_row(
    candidate: Mapping[str, Any],
    *,
    orderbook: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    generated_utc: str,
    raw_orderbook_dir: Path,
) -> dict[str, Any]:
    ticker = str(candidate.get("ticker") or "")
    yes_bids = bid_levels(orderbook, "yes")
    no_bids = bid_levels(orderbook, "no")
    yes_asks = ask_levels(orderbook, "yes")
    no_asks = ask_levels(orderbook, "no")
    best_yes_bid = level_price(yes_bids)
    best_no_bid = level_price(no_bids)
    best_yes_ask = level_price(yes_asks)
    best_no_ask = level_price(no_asks)
    yes_mid = midpoint(best_yes_bid, best_yes_ask)
    depth_imbalance = imbalance(depth(yes_bids, 5), depth(no_bids, 5))
    previous_mid = as_float((previous or {}).get("yes_mid"))
    previous_imbalance = as_float((previous or {}).get("depth_imbalance_yes"))
    close_time = str(
        candidate.get("settlement_time")
        or candidate.get("expected_expiration_time")
        or candidate.get("close_time")
        or ""
    )
    observed_ts = timestamp(generated_utc) or 0.0
    close_ts = timestamp(close_time) or observed_ts
    raw_payload = json.dumps(orderbook, sort_keys=True, default=str).encode()
    raw_sha = hashlib.sha256(raw_payload).hexdigest()
    # Clamp depth metrics to enforce invariants
    clamped_yes_mid = json_float(clamp_depth_metric(yes_mid, min_val=0.0, max_val=1.0))
    clamped_spread = json_float(spread(best_yes_bid, best_yes_ask))
    clamped_no_spread = json_float(spread(best_no_bid, best_no_ask))
    # Ensure spreads are non-negative - if negative, set to 0
    if clamped_spread is not None and clamped_spread < 0:
        clamped_spread = 0.0
    if clamped_no_spread is not None and clamped_no_spread < 0:
        clamped_no_spread = 0.0
    clamped_depth_imbalance = json_float(
        clamp_depth_metric(depth_imbalance, min_val=-1.0, max_val=1.0)
    )
    clamped_imbalance_delta = json_float(
        clamp_depth_metric(
            depth_imbalance - previous_imbalance
            if depth_imbalance is not None and previous_imbalance is not None
            else None,
            min_val=-1.0,
            max_val=1.0,
        )
    )
    total_depth = depth(yes_bids, 5) + depth(no_bids, 5) + depth(yes_asks, 5) + depth(no_asks, 5)
    clamped_total_depth = json_float(max(0.0, total_depth))
    # mid_delta is null for first observation (no previous) - this is naturally handled
    # by the None check, which produces None when previous_mid is None
    return {
        "snapshot_id": hashlib.sha256(f"{ticker}|{generated_utc}|{raw_sha}".encode()).hexdigest(),
        "contract_ticker": ticker,
        "event_ticker": candidate.get("event_ticker"),
        "series_ticker": candidate.get("series_ticker"),
        "sport_surface": candidate.get("_sport_surface") or sport_surface(candidate),
        "observed_at_utc": generated_utc,
        "settlement_time": close_time or None,
        "time_to_settlement_seconds": json_float(close_ts - observed_ts),
        "best_yes_bid": json_float(best_yes_bid),
        "best_yes_ask": json_float(best_yes_ask),
        "best_no_bid": json_float(best_no_bid),
        "best_no_ask": json_float(best_no_ask),
        "yes_mid": clamped_yes_mid,
        "yes_spread": clamped_spread,
        "no_spread": clamped_no_spread,
        "yes_bid_depth_top1": json_float(depth(yes_bids, 1)),
        "no_bid_depth_top1": json_float(depth(no_bids, 1)),
        "yes_ask_depth_top1": json_float(depth(yes_asks, 1)),
        "no_ask_depth_top1": json_float(depth(no_asks, 1)),
        "yes_depth_top5": json_float(depth(yes_bids, 5)),
        "no_depth_top5": json_float(depth(no_bids, 5)),
        "total_depth_contracts": clamped_total_depth,
        "depth_imbalance_yes": clamped_depth_imbalance,
        "depth_imbalance_delta": clamped_imbalance_delta,
        "mid_delta_from_previous_snapshot": json_float(
            yes_mid - previous_mid if yes_mid is not None and previous_mid is not None else None
        ),
        "raw_orderbook_sha256": raw_sha,
        "raw_orderbook_path": str(
            raw_orderbook_dir / "kalshi_ghost_listing_orderbooks_latest.json"
        ),
        "usable": False,
        "research_only": True,
        "execution_enabled": False,
    }


def bid_levels(orderbook: Mapping[str, Any], side: str) -> list[dict[str, float]]:
    book = (
        orderbook.get("orderbook_fp") if isinstance(orderbook.get("orderbook_fp"), Mapping) else {}
    )
    if not book:
        book = orderbook.get("orderbook") if isinstance(orderbook.get("orderbook"), Mapping) else {}
    key = "yes_dollars" if side == "yes" else "no_dollars"
    legacy = "yes" if side == "yes" else "no"
    raw_levels = book.get(key) or book.get(f"{key}_fp") or book.get(legacy) or []
    output: list[dict[str, float]] = []
    for level in raw_levels if isinstance(raw_levels, list) else []:
        if not isinstance(level, list | tuple) or len(level) < 2:
            continue
        price = as_float(level[0])
        contracts = as_float(level[1])
        if price is None or contracts is None or contracts <= 0:
            continue
        if price > 1.0:
            price = price / 100.0
        if 0.0 <= price <= 1.0:
            output.append({"ask_price": price, "contracts": contracts})
    output.sort(key=lambda item: item["ask_price"], reverse=True)
    return output


def level_price(levels: Sequence[Mapping[str, float]]) -> float | None:
    return float(levels[0]["ask_price"]) if levels else None


def depth(levels: Sequence[Mapping[str, float]], count: int) -> float:
    return sum(float(row.get("contracts") or 0.0) for row in levels[:count])


def midpoint(bid: float | None, ask: float | None) -> float | None:
    return (bid + ask) / 2.0 if bid is not None and ask is not None else None


def spread(bid: float | None, ask: float | None) -> float | None:
    return ask - bid if bid is not None and ask is not None else None


def imbalance(yes_depth: float, no_depth: float) -> float | None:
    total = yes_depth + no_depth
    return (yes_depth - no_depth) / total if total > 0 else None


def clamp_depth_metric(value: float | None, *, min_val: float, max_val: float) -> float | None:
    """Clamp a depth metric to [min_val, max_val] if non-None."""
    if value is None:
        return None
    return max(min_val, min(max_val, value))


def load_observation_rows(observation_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(observation_dir.glob("*.json")) if observation_dir.is_dir() else []:
        payload = read_json_or_empty(path)
        if not safe_research_artifact(payload):
            continue
        raw_rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        rows.extend(dict(row) for row in raw_rows if isinstance(row, Mapping))
    return dedupe_observation_rows(rows)


def load_label_rows(label_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(label_dir.glob("*.json")) if label_dir.is_dir() else []:
        payload = read_json_or_empty(path)
        if not safe_research_artifact(payload):
            continue
        raw_rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        rows.extend(dict(row) for row in raw_rows if isinstance(row, Mapping))
    return dedupe_observation_rows(rows)


def dedupe_observation_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        contract_ticker = str(row.get("contract_ticker") or "").strip()
        observed_at = str(row.get("observed_at_utc") or "").strip()
        snapshot_id = str(row.get("snapshot_id") or "").strip()
        if not snapshot_id:
            snapshot_id = hashlib.sha256(
                json.dumps(
                    {
                        "ticker": contract_ticker,
                        "observed": observed_at,
                        "index": index,
                    },
                    sort_keys=True,
                    default=str,
                ).encode()
            ).hexdigest()
        # Dedup by composite key: (contract_ticker, observed_at_utc, snapshot_id)
        composite_key = f"{contract_ticker}|{observed_at}|{snapshot_id}"
        if composite_key not in by_key:
            by_key[composite_key] = dict(row)
    return sorted(
        by_key.values(),
        key=lambda row: (
            str(row.get("contract_ticker") or ""),
            str(row.get("observed_at_utc") or ""),
            str(row.get("snapshot_id") or ""),
        ),
    )


def previous_observation_index(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: str(row.get("observed_at_utc") or ""))
    return {str(row.get("contract_ticker") or ""): dict(row) for row in ordered}


def due_observed_tickers(
    rows: Sequence[Mapping[str, Any]], *, generated_utc: str, max_tickers: int
) -> list[str]:
    cutoff = timestamp(generated_utc) or datetime.now(UTC).timestamp()
    output: list[str] = []
    seen: set[str] = set()
    for row in sorted(rows, key=lambda item: str(item.get("settlement_time") or "")):
        ticker = str(row.get("contract_ticker") or "").strip()
        due_at = timestamp(row.get("settlement_time"))
        if not ticker or ticker in seen or due_at is None or due_at > cutoff:
            continue
        seen.add(ticker)
        output.append(ticker)
        if len(output) >= max(0, int(max_tickers)):
            break
    return output


def capture_public_observed_markets_snapshot(
    *,
    tickers: Sequence[str],
    raw_dir: Path,
    base_snapshot_path: Path | None = None,
    generated_utc: str | None = None,
    fetch_json: Callable[[str], Any] | None = None,
) -> Path:
    generated = generated_utc or utc_now()
    fetch = fetch_json or fetch_json_url
    raw_dir.mkdir(parents=True, exist_ok=True)
    base_snapshot = read_json_or_empty(base_snapshot_path) if base_snapshot_path else {}
    base_markets = (
        base_snapshot.get("markets", []) if isinstance(base_snapshot.get("markets"), list) else []
    )
    markets: list[Mapping[str, Any]] = [row for row in base_markets if isinstance(row, Mapping)]
    seen = {str(row.get("ticker") or "") for row in markets}
    probe_errors: list[dict[str, str]] = []
    for ticker in tickers:
        if not ticker or ticker in seen:
            continue
        try:
            payload = fetch(
                f"{KALSHI_PUBLIC_BASE_URL}/markets/{urllib.parse.quote(ticker, safe='')}"
            )
        except Exception as exc:
            probe_errors.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})
            continue
        market = payload.get("market") if isinstance(payload, Mapping) else None
        if isinstance(market, Mapping):
            markets.append(market)
            seen.add(ticker)
    snapshot = {
        "schema_version": 1,
        "created_at_utc": generated,
        "status": "kalshi_public_microstructure_observed_market_fetch_ok"
        if markets
        else "kalshi_public_microstructure_observed_market_fetch_empty",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "query": {
            "mode": "sports_microstructure_exact_observed_ticker_probe",
            "observed_ticker_count": len(tickers),
            "base_snapshot_path": str(base_snapshot_path) if base_snapshot_path else None,
        },
        "summary": {
            "market_count": len(markets),
            "base_market_count": len(base_markets),
            "observed_ticker_count": len(tickers),
            "probe_error_count": len(probe_errors),
            "settled_label_ready_count": sum(
                1 for market in markets if settlement_outcome(market) is not None
            ),
        },
        "probe_errors_sample": probe_errors[:50],
        "safety": safety_flags(public_market_data_calls=True),
        "markets": markets,
    }
    text = json.dumps(snapshot, indent=2, sort_keys=True, default=str) + "\n"
    stamp = safe_stamp(generated)
    latest_path = raw_dir / "kalshi_sports_microstructure_observed_markets_latest.json"
    (raw_dir / f"kalshi_sports_microstructure_observed_markets_{stamp}.json").write_text(
        text, encoding="utf-8"
    )
    latest_path.write_text(text, encoding="utf-8")
    return latest_path


def fetch_json_url(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.load(response)
    return payload if isinstance(payload, dict) else {}


def label_observations(
    observations: Sequence[Mapping[str, Any]],
    settled_index: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    labels: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for row in observations:
        ticker = str(row.get("contract_ticker") or "").strip()
        market = settled_index.get(ticker)
        if market is None:
            blocked.append(blocked_label(row, "pending_contract_not_settled_in_snapshot"))
            continue
        yes_outcome = settlement_outcome(market)
        if yes_outcome is None:
            blocked.append(blocked_label(row, "settlement_outcome_missing"))
            continue
        labels.append(
            {
                **dict(row),
                "label_status": "labeled_from_public_kalshi_settled_market",
                "settlement_yes_outcome": yes_outcome,
                "yes_outcome": yes_outcome,
                "side_outcome": yes_outcome,
                "settled_time": iso_time(
                    market.get("settlement_ts")
                    or market.get("settled_time")
                    or market.get("expiration_time")
                    or market.get("close_time")
                ),
                "label_source": "public_kalshi_settled_market_payload",
                "settlement_result": market.get("result"),
                "settlement_value_dollars": market.get("settlement_value_dollars"),
                "usable": False,
                "research_only": True,
                "execution_enabled": False,
            }
        )
    return labels, blocked


def blocked_label(row: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "snapshot_id": row.get("snapshot_id"),
        "contract_ticker": row.get("contract_ticker"),
        "sport_surface": row.get("sport_surface"),
        "observed_at_utc": row.get("observed_at_utc"),
        "label_status": reason,
    }


def settled_market_index(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = snapshot.get("markets", []) if isinstance(snapshot.get("markets"), list) else []
    output: dict[str, Mapping[str, Any]] = {}
    for market in rows:
        if not isinstance(market, Mapping):
            continue
        ticker = str(market.get("ticker") or "").strip()
        if ticker:
            output[ticker] = market
    return output


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


def attach_settlement_labels(
    rows: Sequence[Mapping[str, Any]], labels: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    by_snapshot = {
        str(label.get("snapshot_id") or ""): label
        for label in labels
        if str(label.get("snapshot_id") or "")
    }
    output: list[dict[str, Any]] = []
    for row in rows:
        label = by_snapshot.get(str(row.get("snapshot_id") or ""))
        if label is None:
            output.append(dict(row))
            continue
        merged = dict(row)
        for key in (
            "label_status",
            "settlement_yes_outcome",
            "yes_outcome",
            "side_outcome",
            "settled_time",
            "label_source",
            "settlement_result",
            "settlement_value_dollars",
        ):
            merged[key] = label.get(key)
        output.append(merged)
    return output


def iso_time(value: Any) -> str | None:
    parsed = timestamp(value)
    return iso_from_timestamp(parsed)


def safe_packet(
    *, generated_utc: str, rows: Sequence[Mapping[str, Any]], universe_scan_path: Path
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "packet_type": "kalshi_sports_microstructure_observations",
        "generated_utc": generated_utc,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "inputs": {"universe_scan_path": str(universe_scan_path)},
        "rows": list(rows),
        "safety": safety_flags(),
    }


def safe_label_packet(
    *,
    generated_utc: str,
    rows: Sequence[Mapping[str, Any]],
    observation_dir: Path,
    settled_snapshot_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "packet_type": "kalshi_sports_microstructure_settlement_labels",
        "generated_utc": generated_utc,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "inputs": {
            "observation_dir": str(observation_dir),
            "settled_snapshot_path": str(settled_snapshot_path),
        },
        "rows": list(rows),
        "safety": safety_flags(),
    }


def build_summary(
    *,
    universe: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    history_rows: Sequence[Mapping[str, Any]],
    label_rows: Sequence[Mapping[str, Any]],
    blocked_label_rows: Sequence[Mapping[str, Any]],
    due_tickers: Sequence[str],
    settled_snapshot: Mapping[str, Any],
    capture: Mapping[str, Any],
    raw_orderbook_dir: Path,
    observation_dir: Path,
    label_dir: Path,
) -> dict[str, Any]:
    snapshot_counts = counts(row.get("contract_ticker") for row in history_rows)
    repeated = {
        ticker: count
        for ticker, count in snapshot_counts.items()
        if ticker != "unknown" and int(count) >= 2
    }
    max_snapshots = max((int(count) for count in snapshot_counts.values()), default=0)
    # Collect orderbook capture errors for descriptive gate reasons
    capture_errors = capture.get("errors", []) if isinstance(capture, Mapping) else []
    error_sample = [str(e.get("error", "")) for e in capture_errors if isinstance(e, Mapping)][:3]
    return {
        "universe_status": universe.get("status"),
        "universe_safe": safe_research_artifact(universe),
        "selected_candidate_count": len(candidates),
        "selected_quote_hint_count": sum(
            1 for row in candidates if float(row.get("_quote_hint_score") or 0.0) > 0.0
        ),
        "selected_preferred_series_count": sum(
            1 for row in candidates if int(row.get("_series_priority") or 9) <= 2
        ),
        "selected_surface_counts": counts(row.get("_sport_surface") for row in candidates),
        "selected_series_counts": counts(row.get("series_ticker") for row in candidates),
        "orderbook_count": len(orderbook_index(capture)),
        "orderbook_error_count": len(capture_errors),
        "orderbook_error_sample": error_sample,
        "observation_row_count": len(rows),
        "quoteable_observation_row_count": sum(1 for row in rows if quoteable_row(row)),
        "historical_observation_row_count": len(history_rows),
        "historical_distinct_contract_count": len(snapshot_counts),
        "repeated_snapshot_contract_count": len(repeated),
        "max_snapshots_per_contract": max_snapshots,
        "forward_quote_pair_count": sum(
            max(0, int(count) - 1) for count in snapshot_counts.values()
        ),
        "due_distinct_contract_count": len(set(due_tickers)),
        "settled_market_count": len(settled_market_index(settled_snapshot)),
        "label_row_count": len(label_rows),
        "blocked_label_row_count": len(blocked_label_rows),
        "settled_label_contract_count": len(
            {row.get("contract_ticker") for row in label_rows if row.get("contract_ticker")}
        ),
        "surface_counts": counts(row.get("sport_surface") for row in rows),
        "historical_surface_counts": counts(row.get("sport_surface") for row in history_rows),
        "raw_orderbook_dir_outside_repo": outside_repo(raw_orderbook_dir, CONTROL_REPO),
        "observation_dir_outside_repo": outside_repo(observation_dir, CONTROL_REPO),
        "label_dir_outside_repo": outside_repo(label_dir, CONTROL_REPO),
        "usable_row_count": 0,
    }


def _orderbook_gate_reason(summary: Mapping[str, Any]) -> str:
    """Build a descriptive reason for the public_orderbooks_present gate."""
    count = int(summary.get("orderbook_count") or 0)
    error_count = int(summary.get("orderbook_error_count") or 0)
    if count > 0:
        return f"{count} orderbook(s) loaded."
    if error_count > 0:
        error_sample = summary.get("orderbook_error_sample", [])
        sample_text = "; ".join(error_sample[:2]) if error_sample else "unknown errors"
        return f"0 orderbooks loaded, {error_count} error(s): {sample_text}"
    return "0 orderbooks loaded — no orderbook data available."


def quoteable_row(row: Mapping[str, Any]) -> bool:
    return (
        as_float(row.get("best_yes_bid")) is not None
        and as_float(row.get("best_yes_ask")) is not None
        and as_float(row.get("best_yes_bid")) < as_float(row.get("best_yes_ask"))
    ) or (
        as_float(row.get("best_no_bid")) is not None
        and as_float(row.get("best_no_ask")) is not None
        and as_float(row.get("best_no_bid")) < as_float(row.get("best_no_ask"))
    )


def build_gates(summary: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        gate(
            "universe_scan_safe",
            "pass" if summary.get("universe_safe") else "blocked",
            f"Universe status {summary.get('universe_status')}.",
        ),
        gate(
            "current_sports_candidates_present",
            "pass" if int(summary.get("selected_candidate_count") or 0) > 0 else "blocked",
            f"{summary.get('selected_candidate_count')} candidate(s) selected.",
        ),
        gate(
            "public_orderbooks_present",
            "pass" if int(summary.get("orderbook_count") or 0) > 0 else "blocked",
            _orderbook_gate_reason(summary),
        ),
        gate(
            "microstructure_rows_emitted",
            "pass" if int(summary.get("observation_row_count") or 0) > 0 else "blocked",
            f"{summary.get('observation_row_count')} observation row(s).",
        ),
        gate(
            "raw_payloads_outside_repo",
            "pass"
            if summary.get("raw_orderbook_dir_outside_repo")
            and summary.get("observation_dir_outside_repo")
            and summary.get("label_dir_outside_repo")
            else "blocked",
            "Raw orderbooks, observation packets, and label packets must stay outside the repo.",
        ),
        gate(
            "no_probability_ev_sizing_or_execution",
            "pass" if int(summary.get("usable_row_count") or 0) == 0 else "fail",
            "Microstructure observations are evidence only.",
        ),
    ]


def report_status(summary: Mapping[str, Any], gates: Sequence[Mapping[str, Any]]) -> str:
    if any(gate.get("status") == "fail" for gate in gates):
        return "sports_microstructure_observation_loop_failed_safety_gate"
    if int(summary.get("label_row_count") or 0) > 0:
        return "sports_microstructure_observation_loop_ready_with_settlement_labels"
    if all(gate.get("status") == "pass" for gate in gates):
        return "sports_microstructure_observation_loop_ready"
    if int(summary.get("selected_candidate_count") or 0) <= 0:
        return "sports_microstructure_observation_loop_blocked_no_near_resolution_sports"
    if int(summary.get("orderbook_count") or 0) <= 0:
        return "sports_microstructure_observation_loop_blocked_no_orderbooks"
    return "sports_microstructure_observation_loop_blocked"


def next_action(status: str) -> dict[str, str]:
    if status == "sports_microstructure_observation_loop_ready":
        return {
            "name": "kalshi_sports_nondirectional_evidence_gates",
            "why": "Replayable pre-close sports orderbook observations exist for flow and passive-liquidity gates.",
            "stop_condition": "Stop before EV, paper stake, live orders, or account/order paths.",
        }
    return {
        "name": "kalshi_sports_microstructure_snapshot_accumulation",
        "why": "Near-resolution sports orderbook snapshots are still missing or sparse.",
        "stop_condition": "Stop before inferring fills or settlement labels from missing snapshots.",
    }


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def write_outputs(
    report: Mapping[str, Any],
    *,
    out_dir: Path = DEFAULT_OUT_DIR,
    observation_dir: Path = DEFAULT_OBSERVATION_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-microstructure-observation-loop.json"
    md_path = out_dir / "kalshi-sports-microstructure-observation-loop.md"
    csv_path = out_dir / "kalshi-sports-microstructure-observation-loop.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("observation_rows_sample", []), csv_path)
    paths = {"json_path": str(json_path), "markdown_path": str(md_path), "csv_path": str(csv_path)}

    rows = (
        report.get("observation_packet", {}).get("rows")
        if isinstance(report.get("observation_packet"), Mapping)
        else []
    )
    if rows:
        observation_dir.mkdir(parents=True, exist_ok=True)
        stamp = safe_stamp(str(report.get("generated_utc") or utc_now()))
        packet_text = (
            json.dumps(report["observation_packet"], indent=2, sort_keys=True, default=str) + "\n"
        )
        packet_path = observation_dir / f"sports_microstructure_observations_{stamp}.json"
        latest_packet = observation_dir / "sports_microstructure_observations_latest.json"
        packet_path.write_text(packet_text, encoding="utf-8")
        latest_packet.write_text(packet_text, encoding="utf-8")
        paths["observation_packet_path"] = str(packet_path)
        paths["observation_packet_latest_path"] = str(latest_packet)

    label_rows = (
        report.get("label_packet", {}).get("rows")
        if isinstance(report.get("label_packet"), Mapping)
        else []
    )
    if label_rows:
        label_dir = Path(str(report.get("inputs", {}).get("label_dir") or DEFAULT_LABEL_DIR))
        label_dir.mkdir(parents=True, exist_ok=True)
        stamp = safe_stamp(str(report.get("generated_utc") or utc_now()))
        label_text = (
            json.dumps(report["label_packet"], indent=2, sort_keys=True, default=str) + "\n"
        )
        label_path = label_dir / f"sports_microstructure_labels_{stamp}.json"
        latest_label = label_dir / "sports_microstructure_labels_latest.json"
        label_path.write_text(label_text, encoding="utf-8")
        latest_label.write_text(label_text, encoding="utf-8")
        paths["label_packet_path"] = str(label_path)
        paths["label_packet_latest_path"] = str(latest_label)

    if _path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-sports-microstructure-observation-loop.json"
        latest_md = MACRO_DIR / "latest-kalshi-sports-microstructure-observation-loop.md"
        latest_csv = MACRO_DIR / "latest-kalshi-sports-microstructure-observation-loop.csv"
        MACRO_DIR.mkdir(parents=True, exist_ok=True)
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        write_csv(report.get("observation_rows_sample", []), latest_csv)
        paths["latest_json_path"] = str(latest_json)
        paths["latest_markdown_path"] = str(latest_md)
        paths["latest_csv_path"] = str(latest_csv)
    return paths


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Sports Microstructure Observation Loop",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Selected candidates: `{summary.get('selected_candidate_count')}`",
        f"- Selected quote hints: `{summary.get('selected_quote_hint_count')}`",
        f"- Quoteable observation rows: `{summary.get('quoteable_observation_row_count')}`",
        f"- Observation rows: `{summary.get('observation_row_count')}`",
        f"- Historical rows: `{summary.get('historical_observation_row_count')}`",
        f"- Repeated contracts: `{summary.get('repeated_snapshot_contract_count')}`",
        f"- Due contracts: `{summary.get('due_distinct_contract_count')}`",
        f"- Label rows: `{summary.get('label_row_count')}`",
        f"- Surface counts: `{summary.get('surface_counts')}`",
        f"- Selected surface counts: `{summary.get('selected_surface_counts')}`",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for item in report.get("gates", []):
        if isinstance(item, Mapping):
            lines.append(
                f"| `{item.get('name')}` | `{item.get('status')}` | {item.get('reason')} |"
            )
    lines.extend(["", "This artifact is research-only microstructure evidence.", ""])
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-scan-path", type=Path, default=DEFAULT_UNIVERSE_SCAN_PATH)
    parser.add_argument("--raw-orderbook-dir", type=Path, default=DEFAULT_RAW_ORDERBOOK_DIR)
    parser.add_argument("--observation-dir", type=Path, default=DEFAULT_OBSERVATION_DIR)
    parser.add_argument("--settled-snapshot-path", type=Path, default=DEFAULT_SETTLED_SNAPSHOT_PATH)
    parser.add_argument("--settled-raw-dir", type=Path, default=DEFAULT_SETTLED_RAW_DIR)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-tickers", type=int, default=DEFAULT_MAX_TICKERS)
    parser.add_argument("--max-close-hours", type=float, default=DEFAULT_MAX_CLOSE_HOURS)
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    parser.add_argument("--delay-seconds", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument(
        "--observed-probe-max-tickers", type=int, default=DEFAULT_OBSERVED_PROBE_MAX_TICKERS
    )
    parser.add_argument("--capture-orderbooks", action="store_true")
    parser.add_argument("--probe-observed-public", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_sports_microstructure_observation_loop(
        universe_scan_path=args.universe_scan_path,
        raw_orderbook_dir=args.raw_orderbook_dir,
        observation_dir=args.observation_dir,
        settled_snapshot_path=args.settled_snapshot_path,
        settled_raw_dir=args.settled_raw_dir,
        label_dir=args.label_dir,
        max_tickers=args.max_tickers,
        max_close_hours=args.max_close_hours,
        depth=args.depth,
        delay_seconds=args.delay_seconds,
        observed_probe_max_tickers=args.observed_probe_max_tickers,
        capture_orderbooks=args.capture_orderbooks,
        probe_observed_public=args.probe_observed_public,
    )
    if args.write:
        paths = write_outputs(report, out_dir=args.out_dir, observation_dir=args.observation_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
