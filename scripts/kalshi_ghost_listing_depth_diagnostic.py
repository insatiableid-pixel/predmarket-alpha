#!/usr/bin/env python3
"""Probe current Kalshi orderbook depth before treating capacity as real.

This diagnostic is intentionally pre-signal and research-only. It measures
whether current universe rows have executable public orderbook depth at all,
so downstream ``cap_i`` estimates cannot be locked from stale top-of-book or
inventory-only artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.kalshi_universe_scan import DEFAULT_WORLD_CUP_SOCCER_SERIES  # noqa: E402
from predmarket.shared_helpers import (  # noqa: E402
    counts,
    json_float,
    manual_drop_path,
    optional_float,
    outside_repo,
    price_probability,
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
DEFAULT_RAW_ORDERBOOK_DIR = manual_drop_path("kalshi_ghost_listing_depth")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-ghost-listing-depth-diagnostic-latest"
DEFAULT_CLASSIFICATIONS = (
    "other_sports",
    "mlb",
    "atp",
    "nfl",
    "nba",
    "weather",
    "finance_crypto",
    "macro_econ",
    "politics_policy",
)
DEFAULT_MAX_CONTRACTS = 120
DEFAULT_DEPTH = 0
DEFAULT_DELAY_SECONDS = 0.03
DEFAULT_MIN_PROBE_COVERAGE = 0.80
DEFAULT_MIN_POSITIVE_DEPTH_FRACTION = 0.18
WORLD_CUP_SERIES = frozenset(DEFAULT_WORLD_CUP_SOCCER_SERIES)
CSV_FIELDS = [
    "contract_ticker",
    "classification",
    "series_ticker",
    "event_ticker",
    "settlement_time",
    "time_to_settlement_hours",
    "yes_level_count",
    "no_level_count",
    "best_yes_ask",
    "best_no_ask",
    "total_depth_contracts",
    "total_depth_notional",
    "ghost_listing_flag",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_ghost_listing_depth_diagnostic(
    *,
    universe_scan_path: Path = DEFAULT_UNIVERSE_SCAN_PATH,
    raw_orderbook_dir: Path = DEFAULT_RAW_ORDERBOOK_DIR,
    generated_utc: str | None = None,
    max_contracts: int = DEFAULT_MAX_CONTRACTS,
    depth: int = DEFAULT_DEPTH,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    classifications: Sequence[str] = DEFAULT_CLASSIFICATIONS,
    min_probe_coverage: float = DEFAULT_MIN_PROBE_COVERAGE,
    min_positive_depth_fraction: float = DEFAULT_MIN_POSITIVE_DEPTH_FRACTION,
    capture_orderbooks: bool = False,
    fetch_json: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    generated_ts = timestamp(generated) or time.time()
    universe = read_json_or_empty(universe_scan_path)
    selected = stratified_select_candidates(
        universe,
        generated_ts=generated_ts,
        classifications=classifications,
        max_contracts=max_contracts,
    )
    capture = (
        capture_public_orderbooks(
            tickers=[str(row["ticker"]) for row in selected],
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
    rows = [depth_row(row, orderbook=orderbooks.get(str(row.get("ticker")))) for row in selected]
    summary = build_summary(
        universe=universe,
        selected=selected,
        rows=rows,
        capture=capture,
        min_probe_coverage=min_probe_coverage,
        min_positive_depth_fraction=min_positive_depth_fraction,
    )
    gates = build_gates(
        summary,
        raw_orderbook_dir=raw_orderbook_dir,
        generated_utc=generated,
        max_staleness_seconds=3600,
    )
    status = report_status(summary, gates, generated_utc=generated)
    cap_i_lock_allowed = status == "ghost_listing_depth_diagnostic_current_depth_ready"
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
        "freshness": {
            "generated_utc": generated,
            "max_staleness_seconds": 3600,
            "stale_as_of_utc": utc_now() if _is_stale(generated, 3600) else generated,
        },
        "inputs": {
            "universe_scan_path": str(universe_scan_path),
            "universe_scan_sha256": sha256_or_none(universe_scan_path),
            "universe_scan_status": universe.get("status"),
            "raw_orderbook_dir": str(raw_orderbook_dir),
            "raw_orderbook_dir_outside_repo": outside_repo(raw_orderbook_dir, CONTROL_REPO),
            "max_contracts": max_contracts,
            "depth": depth,
            "classifications": list(classifications),
            "min_probe_coverage": min_probe_coverage,
            "min_positive_depth_fraction": min_positive_depth_fraction,
        },
        "method": {
            "purpose": "Measure current public depth before any capacity cap is treated as real.",
            "selection": "Stratified sampling across all active classifications: probe budget allocated proportionally to each classification's share of eligible universe candidates. Within each classification, candidates are sorted by time-to-settlement for earliest-expiring first.",
            "ghost_listing_rule": "A ticker is ghost-listed for this diagnostic when the current public orderbook has no executable YES or NO derived ask levels.",
            "cap_i_policy": "cap_i_lock_allowed is false unless current public orderbook probe coverage and positive-depth fraction pass and ghost-listing diagnostic is not stale.",
            "boundary": "This report never emits EV, sizing, account, order, or execution instructions.",
        },
        "summary": summary,
        "gates": gates,
        "depth_rows": rows,
        "next_action": next_action(status),
        "cap_i_policy": {
            "cap_i_lock_allowed": cap_i_lock_allowed,
            "reason": "current_depth_probe_passed"
            if cap_i_lock_allowed
            else "cap_i_lock_blocked_until_current_depth_probe_passes",
        },
        "safety": safety_flags(public_market_data_calls=capture_orderbooks),
    }


def _is_stale(generated_utc: str, max_staleness_seconds: int) -> bool:
    """Check whether the ghost-listing diagnostic is stale."""
    try:
        generated_dt = datetime.fromisoformat(generated_utc.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return True
    return (datetime.now(UTC) - generated_dt).total_seconds() > max_staleness_seconds


def stratified_select_candidates(
    universe: Mapping[str, Any],
    *,
    generated_ts: float,
    classifications: Sequence[str],
    max_contracts: int,
) -> list[dict[str, Any]]:
    """Stratified sampling across all classifications.

    Allocates the probe budget proportionally to each classification's share
    of eligible candidates, ensuring representative coverage. Within each
    stratum, candidates are sorted by time-to-settlement (earliest first).
    """
    allowed = {str(item).strip() for item in classifications if str(item).strip()}
    candidates = (
        universe.get("candidates", []) if isinstance(universe.get("candidates"), list) else []
    )
    by_classification: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        if not eligible_candidate(row, allowed=allowed, generated_ts=generated_ts):
            continue
        item = dict(row)
        classification = str(item.get("classification") or "unknown")
        by_classification[classification].append(item)

    for rows in by_classification.values():
        rows.sort(key=_stratum_sort_key)

    total_eligible = sum(len(rows) for rows in by_classification.values())
    limit = max(0, max_contracts)

    if total_eligible <= 0:
        return []

    return _allocate_strata(by_classification, limit)


def _allocate_strata(
    by_classification: dict[str, list[dict[str, Any]]],
    limit: int,
) -> list[dict[str, Any]]:
    """Allocate probe budget proportionally across strata, then select candidates."""
    total_eligible = sum(len(rows) for rows in by_classification.values())

    # Phase 1: Proportional allocation (no floor yet)
    raw_allocations: dict[str, int] = {}
    for classification in sorted(by_classification):
        count = len(by_classification[classification])
        raw_allocations[classification] = max(0, min(count, round(limit * count / total_eligible)))

    # Phase 2: Ensure every stratum with candidates gets at least 1 if budget allows
    allocations = dict(raw_allocations)
    total_raw = sum(allocations.values())
    if total_raw < limit:
        remaining = limit - total_raw
        for classification in sorted(by_classification):
            if remaining <= 0:
                break
            count = len(by_classification[classification])
            if allocations[classification] < count:
                allocations[classification] += 1
                remaining -= 1
    elif total_raw > limit:
        surplus = total_raw - limit
        for classification in sorted(by_classification, key=lambda c: -allocations[c]):
            if surplus <= 0:
                break
            if allocations[classification] > 1 and len(by_classification[classification]) > 0:
                reduction = min(surplus, allocations[classification] - 1)
                allocations[classification] -= reduction
                surplus -= reduction

    selected: list[dict[str, Any]] = []
    for classification in sorted(by_classification):
        pool = list(by_classification[classification])
        take = min(allocations.get(classification, 0), len(pool))
        selected.extend(pool[:take])

    return selected


def _stratum_sort_key(row: Mapping[str, Any]) -> tuple[float, str, str]:
    return (
        float(row.get("time_to_settlement_hours") or row.get("time_to_close_hours") or 999999.0),
        str(row.get("series_ticker") or ""),
        str(row.get("ticker") or ""),
    )


def eligible_candidate(row: Any, *, allowed: set[str], generated_ts: float) -> bool:
    if not isinstance(row, Mapping):
        return False
    classification = str(row.get("classification") or "")
    if classification not in allowed:
        return False
    if str(row.get("gate_status") or "") not in {"pass", "warn"}:
        return False
    if not str(row.get("ticker") or "").strip():
        return False
    due_ts = timestamp(
        row.get("settlement_time") or row.get("expected_expiration_time") or row.get("close_time")
    )
    return due_ts is None or due_ts > generated_ts


def capture_public_orderbooks(
    *,
    tickers: Sequence[str],
    raw_orderbook_dir: Path,
    generated_utc: str,
    depth: int,
    delay_seconds: float,
    fetch_json: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    fetch = fetch_json or fetch_json_url
    raw_orderbook_dir.mkdir(parents=True, exist_ok=True)
    orderbooks: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for ticker in tickers:
        query = urllib.parse.urlencode({"depth": max(0, int(depth))})
        url = f"{KALSHI_PUBLIC_BASE_URL}/markets/{urllib.parse.quote(ticker, safe='')}/orderbook?{query}"
        try:
            payload = fetch(url)
        except Exception as exc:  # pragma: no cover - public network defensive path
            errors.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})
            continue
        if isinstance(payload, Mapping):
            orderbooks.append({"ticker": ticker, "payload": dict(payload)})
        else:
            errors.append({"ticker": ticker, "error": "non_mapping_payload"})
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    snapshot = {
        "schema_version": 1,
        "created_at_utc": generated_utc,
        "status": "kalshi_public_orderbook_fetch_ok"
        if orderbooks
        else "kalshi_public_orderbook_fetch_empty",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "query": {"ticker_count": len(tickers), "depth": depth},
        "summary": {"orderbook_count": len(orderbooks), "error_count": len(errors)},
        "orderbooks": orderbooks,
        "errors": errors,
        "safety": safety_flags(public_market_data_calls=True),
    }
    text = json.dumps(snapshot, indent=2, sort_keys=True, default=str) + "\n"
    stamp = safe_stamp(generated_utc)
    (raw_orderbook_dir / f"kalshi_ghost_listing_orderbooks_{stamp}.json").write_text(
        text, encoding="utf-8"
    )
    (raw_orderbook_dir / "kalshi_ghost_listing_orderbooks_latest.json").write_text(
        text, encoding="utf-8"
    )
    return snapshot


def load_latest_orderbook_capture(raw_orderbook_dir: Path) -> dict[str, Any]:
    return read_json_or_empty(raw_orderbook_dir / "kalshi_ghost_listing_orderbooks_latest.json")


def orderbook_index(capture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    for item in capture.get("orderbooks", []):
        if not isinstance(item, Mapping):
            continue
        ticker = str(item.get("ticker") or "").strip()
        payload = item.get("payload")
        if ticker and isinstance(payload, Mapping):
            output[ticker] = payload
    return output


def depth_row(row: Mapping[str, Any], *, orderbook: Mapping[str, Any] | None) -> dict[str, Any]:
    yes_levels = ask_levels(orderbook or {}, "yes")
    no_levels = ask_levels(orderbook or {}, "no")
    yes_contracts = sum(level["contracts"] for level in yes_levels)
    no_contracts = sum(level["contracts"] for level in no_levels)
    yes_notional = sum(level["ask_price"] * level["contracts"] for level in yes_levels)
    no_notional = sum(level["ask_price"] * level["contracts"] for level in no_levels)
    total_contracts = yes_contracts + no_contracts
    total_notional = yes_notional + no_notional
    return {
        "contract_ticker": row.get("ticker"),
        "classification": row.get("classification"),
        "series_ticker": row.get("series_ticker"),
        "event_ticker": row.get("event_ticker"),
        "settlement_time": row.get("settlement_time"),
        "time_to_settlement_hours": row.get("time_to_settlement_hours"),
        "yes_level_count": len(yes_levels),
        "no_level_count": len(no_levels),
        "best_yes_ask": json_float(yes_levels[0]["ask_price"] if yes_levels else None),
        "best_no_ask": json_float(no_levels[0]["ask_price"] if no_levels else None),
        "yes_depth_contracts": json_float(yes_contracts),
        "no_depth_contracts": json_float(no_contracts),
        "total_depth_contracts": json_float(total_contracts),
        "total_depth_notional": json_float(total_notional),
        "ghost_listing_flag": total_contracts <= 0,
        "cap_i_lock_allowed_for_row": False,
        "usable": False,
        "research_only": True,
        "execution_enabled": False,
    }


def ask_levels(orderbook: Mapping[str, Any], side: str) -> list[dict[str, float]]:
    book = (
        orderbook.get("orderbook_fp") if isinstance(orderbook.get("orderbook_fp"), Mapping) else {}
    )
    if not book:
        book = orderbook.get("orderbook") if isinstance(orderbook.get("orderbook"), Mapping) else {}
    bid_key = "no_dollars" if side == "yes" else "yes_dollars"
    legacy_key = "no" if side == "yes" else "yes"
    raw_levels = book.get(bid_key) or book.get(f"{bid_key}_fp") or book.get(legacy_key) or []
    levels: list[dict[str, float]] = []
    for level in raw_levels if isinstance(raw_levels, list) else []:
        if not isinstance(level, (list, tuple)) or len(level) < 2:
            continue
        bid_price = price_probability(level[0])
        contracts = optional_float(level[1])
        if bid_price is None or contracts is None or contracts <= 0:
            continue
        ask_price = 1.0 - bid_price
        if 0.0 < ask_price <= 1.0:
            levels.append({"ask_price": ask_price, "contracts": contracts})
    levels.sort(key=lambda item: item["ask_price"])
    return levels


def build_summary(
    *,
    universe: Mapping[str, Any],
    selected: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    capture: Mapping[str, Any],
    min_probe_coverage: float,
    min_positive_depth_fraction: float,
) -> dict[str, Any]:
    orderbook_count = len(orderbook_index(capture))
    selected_count = len(selected)
    positive_depth_rows = [
        row for row in rows if float(row.get("total_depth_contracts") or 0.0) > 0
    ]
    ghost_rows = [row for row in rows if row.get("ghost_listing_flag") is True]
    probe_coverage = orderbook_count / selected_count if selected_count else None
    positive_fraction = len(positive_depth_rows) / selected_count if selected_count else None
    by_classification = {
        key: classification_summary(key, rows)
        for key in sorted({str(row.get("classification") or "unknown") for row in rows})
    }
    # Stratification metadata
    classification_counts = counts(row.get("classification") for row in selected)
    return {
        "universe_status": universe.get("status"),
        "universe_safe": safe_research_artifact(universe),
        "selected_candidate_count": selected_count,
        "orderbook_count": orderbook_count,
        "orderbook_error_count": len(capture.get("errors", []))
        if isinstance(capture.get("errors"), list)
        else 0,
        "probe_coverage": json_float(probe_coverage),
        "min_probe_coverage": min_probe_coverage,
        "positive_depth_row_count": len(positive_depth_rows),
        "ghost_listing_row_count": len(ghost_rows),
        "positive_depth_fraction": json_float(positive_fraction),
        "ghost_listing_fraction": json_float(
            len(ghost_rows) / selected_count if selected_count else None
        ),
        "min_positive_depth_fraction": min_positive_depth_fraction,
        "total_depth_contracts": json_float(
            sum(float(row.get("total_depth_contracts") or 0.0) for row in rows)
        ),
        "total_depth_notional": json_float(
            sum(float(row.get("total_depth_notional") or 0.0) for row in rows)
        ),
        "classification_counts": classification_counts,
        "stratification_allocation": classification_counts,
        "series_counts": counts(row.get("series_ticker") for row in selected),
        "depth_by_classification": by_classification,
        "cap_i_lock_allowed": bool(
            selected_count
            and probe_coverage is not None
            and probe_coverage >= min_probe_coverage
            and positive_fraction is not None
            and positive_fraction >= min_positive_depth_fraction
        ),
        "usable_row_count": 0,
    }


def classification_summary(
    classification: str, rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    subset = [row for row in rows if str(row.get("classification") or "unknown") == classification]
    positive = [row for row in subset if float(row.get("total_depth_contracts") or 0.0) > 0]
    return {
        "row_count": len(subset),
        "positive_depth_row_count": len(positive),
        "positive_depth_fraction": json_float(len(positive) / len(subset) if subset else None),
        "ghost_listing_row_count": len(subset) - len(positive),
        "total_depth_contracts": json_float(
            sum(float(row.get("total_depth_contracts") or 0.0) for row in subset)
        ),
        "total_depth_notional": json_float(
            sum(float(row.get("total_depth_notional") or 0.0) for row in subset)
        ),
    }


def build_gates(
    summary: Mapping[str, Any],
    *,
    raw_orderbook_dir: Path,
    generated_utc: str | None = None,
    max_staleness_seconds: int = 3600,
) -> list[dict[str, str]]:
    is_stale = generated_utc is not None and _is_stale(generated_utc, max_staleness_seconds)
    return [
        gate(
            "universe_scan_safe",
            "pass" if summary.get("universe_safe") is True else "blocked",
            f"Universe status is {summary.get('universe_status')}.",
        ),
        gate(
            "current_candidates_selected",
            "pass" if int(summary.get("selected_candidate_count") or 0) > 0 else "blocked",
            f"{summary.get('selected_candidate_count')} current candidate(s) selected.",
        ),
        gate(
            "raw_orderbook_dir_outside_repo",
            "pass" if outside_repo(raw_orderbook_dir, CONTROL_REPO) else "blocked",
            "Raw public orderbook snapshots must stay outside the repo.",
        ),
        gate(
            "public_orderbooks_present",
            "pass" if int(summary.get("orderbook_count") or 0) > 0 else "blocked",
            f"{summary.get('orderbook_count')} orderbook(s), {summary.get('orderbook_error_count')} error(s).",
        ),
        gate(
            "probe_coverage_minimum",
            "pass"
            if float(summary.get("probe_coverage") or 0.0)
            >= float(summary.get("min_probe_coverage") or 0.0)
            else "blocked",
            f"Probe coverage {summary.get('probe_coverage')}; minimum {summary.get('min_probe_coverage')}.",
        ),
        gate(
            "positive_depth_fraction_minimum",
            "pass"
            if float(summary.get("positive_depth_fraction") or 0.0)
            >= float(summary.get("min_positive_depth_fraction") or 0.0)
            else "blocked",
            (
                f"Positive-depth fraction {summary.get('positive_depth_fraction')}; "
                f"minimum {summary.get('min_positive_depth_fraction')}."
            ),
        ),
        gate(
            "ghost_listing_diagnostic_freshness",
            "blocked" if is_stale else "pass",
            "Stale ghost-listing diagnostic: must be refreshed before downstream consumers may use it."
            if is_stale
            else f"Fresh diagnostic (max_staleness_seconds={max_staleness_seconds}).",
        ),
        gate(
            "cap_i_lock_boundary",
            "pass" if summary.get("cap_i_lock_allowed") is True else "blocked",
            "cap_i may not be locked until current public depth probe passes.",
        ),
        gate(
            "no_ev_sizing_or_execution",
            "pass" if int(summary.get("usable_row_count") or 0) == 0 else "fail",
            "Diagnostic emits no usable rows, EV, sizing, account, order, or execution output.",
        ),
    ]


def report_status(
    summary: Mapping[str, Any],
    gates: Sequence[Mapping[str, Any]],
    *,
    generated_utc: str | None = None,
) -> str:
    if any(gate.get("status") == "fail" for gate in gates):
        return "ghost_listing_depth_diagnostic_failed_safety_gate"
    if not summary.get("universe_safe"):
        return "ghost_listing_depth_diagnostic_blocked_missing_universe_scan"
    if int(summary.get("selected_candidate_count") or 0) <= 0:
        return "ghost_listing_depth_diagnostic_blocked_no_current_candidates"
    if int(summary.get("orderbook_count") or 0) <= 0:
        return "ghost_listing_depth_diagnostic_blocked_no_current_orderbooks"
    # If the diagnostic itself is stale, block cap_i lock
    if generated_utc and _is_stale(generated_utc, 3600):
        return "ghost_listing_depth_diagnostic_stale_blocks_cap_i_lock"
    if summary.get("cap_i_lock_allowed") is True:
        return "ghost_listing_depth_diagnostic_current_depth_ready"
    return "ghost_listing_depth_diagnostic_blocks_cap_i_lock"


def next_action(status: str) -> dict[str, str]:
    if status == "ghost_listing_depth_diagnostic_current_depth_ready":
        return {
            "name": "kalshi_capacity_gate_can_consume_current_depth",
            "why": "Current public orderbook probe coverage and positive-depth fraction passed.",
            "stop_condition": "Stop before live sizing; this only unblocks cap_i estimation inputs.",
        }
    if status == "ghost_listing_depth_diagnostic_stale_blocks_cap_i_lock":
        return {
            "name": "kalshi_ghost_listing_depth_diagnostic_refresh_required",
            "why": "Ghost-listing diagnostic is stale; refresh before downstream consumers can use it.",
            "stop_condition": "Stop before locking cap_i from stale depth data.",
        }
    return {
        "name": "kalshi_current_depth_accumulation",
        "why": "Current public depth is absent, sparse, or too ghost-listed to lock capacity caps.",
        "stop_condition": "Stop before locking cap_i or inferring capacity from inventory/top-of-book alone.",
    }


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def fetch_json_url(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.load(response)
    return payload if isinstance(payload, dict) else {}


def write_outputs(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-ghost-listing-depth-diagnostic.json"
    md_path = out_dir / "kalshi-ghost-listing-depth-diagnostic.md"
    csv_path = out_dir / "kalshi-ghost-listing-depth-diagnostic.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, csv_path)
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-ghost-listing-depth-diagnostic.json"
    latest_md = MACRO_DIR / "latest-kalshi-ghost-listing-depth-diagnostic.md"
    latest_csv = MACRO_DIR / "latest-kalshi-ghost-listing-depth-diagnostic.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, latest_csv)
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
    lines = [
        "# Kalshi Ghost-Listing Depth Diagnostic",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Selected candidates: `{summary.get('selected_candidate_count')}`",
        f"- Orderbooks: `{summary.get('orderbook_count')}`",
        f"- Positive-depth fraction: `{summary.get('positive_depth_fraction')}`",
        f"- Ghost-listing fraction: `{summary.get('ghost_listing_fraction')}`",
        f"- cap_i lock allowed: `{summary.get('cap_i_lock_allowed')}`",
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
        ["", "## Guardrail", "", "This is a current-depth diagnostic, not a betting surface.", ""]
    )
    return "\n".join(lines)


def write_csv(report: Mapping[str, Any], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in report.get("depth_rows", []):
            if isinstance(row, Mapping):
                writer.writerow(dict(row))


def parse_classifications(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-scan-path", type=Path, default=DEFAULT_UNIVERSE_SCAN_PATH)
    parser.add_argument("--raw-orderbook-dir", type=Path, default=DEFAULT_RAW_ORDERBOOK_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-contracts", type=int, default=DEFAULT_MAX_CONTRACTS)
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    parser.add_argument("--delay-seconds", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--classifications", default=",".join(DEFAULT_CLASSIFICATIONS))
    parser.add_argument("--min-probe-coverage", type=float, default=DEFAULT_MIN_PROBE_COVERAGE)
    parser.add_argument(
        "--min-positive-depth-fraction", type=float, default=DEFAULT_MIN_POSITIVE_DEPTH_FRACTION
    )
    parser.add_argument("--capture-orderbooks", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_ghost_listing_depth_diagnostic(
        universe_scan_path=args.universe_scan_path,
        raw_orderbook_dir=args.raw_orderbook_dir,
        max_contracts=args.max_contracts,
        depth=args.depth,
        delay_seconds=args.delay_seconds,
        classifications=parse_classifications(args.classifications),
        min_probe_coverage=args.min_probe_coverage,
        min_positive_depth_fraction=args.min_positive_depth_fraction,
        capture_orderbooks=args.capture_orderbooks,
    )
    if args.write:
        paths = write_outputs(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
