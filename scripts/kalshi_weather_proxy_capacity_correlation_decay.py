#!/usr/bin/env python3
"""Measure capacity, correlation, and decay gates for weather proxy candidates via the engine.

This is the weather analog of ``scripts/kalshi_sports_proxy_capacity_correlation_decay.py``.
It reuses the engine's generic ``ask_levels`` and ``capacity_row`` for public Kalshi orderbook
depth on weather contracts, and ``build_decay_summary`` for decay — demonstrating the spine
is closed for modification (zero spine edits).

Weather-specific differences:
- Prediction rule: ``weather_prediction_rule`` (bracket probability threshold rule).
- Cluster key: ``station|bracket|date`` via ``weather_cluster_key_composer``.
- Inputs: ``latest-kalshi-weather-proxy-feature-packet.json`` and
  ``latest-kalshi-weather-proxy-research-candidate-replay.json``.
- Raw orderbook payloads outside the repo under
  ``/home/mrwatson/manual_drops/kalshi_weather_proxy_orderbooks/``.
- Every row ``usable=false``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.engine import ask_levels  # noqa: E402
from predmarket.kalshi_execution_cost import normalize_kalshi_execution_cost  # noqa: E402
from predmarket.shared_helpers import (  # noqa: E402
    counts,
    gate,
    json_float,
    path_is_within,
    probability,
    read_json_or_empty,
    safety_flags,
    timestamp,
    utc_now,
)
from predmarket.weather_family import (  # noqa: E402
    weather_cluster_key_composer,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
KALSHI_PUBLIC_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"


def outside_repo(path: Path) -> bool:
    """Check if path is outside the repository working tree."""
    try:
        path.expanduser().resolve().relative_to(CONTROL_REPO.resolve())
    except (ValueError, OSError):
        return True
    return False

DEFAULT_FEATURE_PACKET_PATH = MACRO_DIR / "latest-kalshi-weather-proxy-feature-packet.json"
DEFAULT_REPLAY_PATH = MACRO_DIR / "latest-kalshi-weather-proxy-research-candidate-replay.json"
DEFAULT_RAW_ORDERBOOK_DIR = Path("/home/mrwatson/manual_drops/kalshi_weather_proxy_orderbooks")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-weather-proxy-capacity-correlation-decay-latest"
DEFAULT_MAX_CLOSE_HOURS = 48.0  # Weather contracts settle at end of day
DEFAULT_MAX_TICKERS = 60
DEFAULT_DEPTH = 0
DEFAULT_DELAY_SECONDS = 0.05
DEFAULT_MAX_CLUSTER_SHARE = 0.35
DEFAULT_MIN_POSITIVE_CAPACITY_CONTRACTS = 1.0
DEFAULT_MIN_DECAY_BUCKETS = 3
DEFAULT_MIN_DECAY_LABELS = 100

STATUS_PREFIX = "weather_proxy"

CSV_FIELDS = [
    "contract_ticker",
    "event_ticker",
    "series_ticker",
    "close_time",
    "predicted_side",
    "best_all_in_break_even_probability",
    "conservative_calibrated_side_probability",
    "best_margin_probability",
    "positive_depth_contracts",
    "positive_depth_cost",
    "level_count",
    "correlation_cluster_key",
    "gate_status",
    "usable",
]


def build_weather_proxy_capacity_correlation_decay(
    *,
    feature_packet_path: Path = DEFAULT_FEATURE_PACKET_PATH,
    replay_path: Path = DEFAULT_REPLAY_PATH,
    raw_orderbook_dir: Path = DEFAULT_RAW_ORDERBOOK_DIR,
    generated_utc: str | None = None,
    max_close_hours: float = DEFAULT_MAX_CLOSE_HOURS,
    max_tickers: int = DEFAULT_MAX_TICKERS,
    depth: int = DEFAULT_DEPTH,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    capture_orderbooks: bool = False,
    fetch_json: Callable[[str], Any] | None = None,
    max_cluster_share: float = DEFAULT_MAX_CLUSTER_SHARE,
    min_positive_capacity_contracts: float = DEFAULT_MIN_POSITIVE_CAPACITY_CONTRACTS,
    min_decay_buckets: int = DEFAULT_MIN_DECAY_BUCKETS,
    min_decay_labels: int = DEFAULT_MIN_DECAY_LABELS,
) -> dict[str, Any]:
    """Build the weather proxy CCD report.

    Args:
        feature_packet_path: Path to the latest weather feature packet.
        replay_path: Path to the latest weather replay report.
        raw_orderbook_dir: Directory for raw orderbook payloads.
        generated_utc: Override timestamp (ISO format).
        max_close_hours: Maximum hours to close for a contract to be included.
        max_tickers: Maximum number of tickers to probe.
        depth: Orderbook depth.
        delay_seconds: Delay between orderbook fetches.
        capture_orderbooks: If True, fetch orderbooks live.
        fetch_json: Injectable fetch function (for tests).
        max_cluster_share: Max share per correlation cluster.
        min_positive_capacity_contracts: Minimum positive depth contracts threshold.
        min_decay_buckets: Minimum decay buckets for survival pass.
        min_decay_labels: Minimum decay labels for survival pass.

    Returns:
        The CCD report dict.
    """
    generated = generated_utc or utc_now()
    generated_ts = timestamp(generated) or time.time()
    feature_packet = read_json_or_empty(feature_packet_path)
    replay = read_json_or_empty(replay_path)

    calibrated_probability = _get_calibrated_probability(replay)

    # Select current candidates using weather prediction + cluster key
    selected = select_current_candidates(
        feature_packet=feature_packet,
        generated_ts=generated_ts,
        max_close_hours=max_close_hours,
        max_tickers=max_tickers,
    )

    # Capture or load orderbooks
    capture = (
        capture_public_orderbooks(
            tickers=[str(row["contract_ticker"]) for row in selected],
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

    # Build capacity rows using engine's ask_levels + capacity_row approach
    capacity_rows = [
        build_capacity_row(
            row,
            orderbook=orderbooks.get(str(row.get("contract_ticker"))),
            calibrated_probability=calibrated_probability,
        )
        for row in selected
    ]

    summary_data = build_summary(
        feature_packet=feature_packet,
        replay=replay,
        selected=selected,
        capacity_rows=capacity_rows,
        capture=capture,
        calibrated_probability=calibrated_probability,
        max_cluster_share=max_cluster_share,
        min_positive_capacity_contracts=min_positive_capacity_contracts,
        min_decay_buckets=min_decay_buckets,
        min_decay_labels=min_decay_labels,
    )
    gates = build_gates(summary_data, raw_orderbook_dir=raw_orderbook_dir)
    status = report_status(summary_data, gates)

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
            "feature_packet_path": str(feature_packet_path),
            "feature_packet_status": feature_packet.get("status"),
            "replay_path": str(replay_path),
            "replay_status": replay.get("status"),
            "raw_orderbook_dir": str(raw_orderbook_dir),
            "raw_orderbook_dir_outside_repo": outside_repo(raw_orderbook_dir),
            "max_close_hours": max_close_hours,
            "max_tickers": max_tickers,
            "depth": depth,
        },
        "method": {
            "engine_stage": "ask_levels + capacity_row + build_decay_summary from predmarket.engine",
            "orderbook_source": "Kalshi public market-data orderbook endpoint; unauthenticated.",
            "ask_derivation": "Orderbooks return YES/NO bids only; opposing bids are reciprocal asks.",
            "yes_capacity_rule": "YES buy-side levels are derived from NO bids as yes_ask = 1 - no_bid.",
            "no_capacity_rule": "NO buy-side levels are derived from YES bids as no_ask = 1 - yes_bid.",
            "positive_capacity_rule": (
                "A level has positive capacity only if its fee-aware all-in break-even is below the "
                "conservative selected-side probability from the replay artifact."
            ),
            "correlation_rule": "Cluster current exposure by station + bracket + close-time bucket.",
            "candidate_selection_rule": (
                "Eligible current candidates are sorted inside each correlation cluster, then selected "
                "round-robin across clusters before truncating to the ticker cap."
            ),
            "boundary": "This report never emits usable rows, staking, sizing, execution, or account/order paths.",
        },
        "capture": _capture_brief(capture),
        "summary": summary_data,
        "gates": gates,
        "capacity_rows": capacity_rows,
        "next_action": _next_action(status),
        "safety": safety_flags(public_market_data_calls=capture_orderbooks),
    }


# ---------------------------------------------------------------------------
# Weather prediction rule (mirroring weather_prediction_rule from the family)
# ---------------------------------------------------------------------------


def weather_proxy_prediction(row: Mapping[str, Any]) -> int | None:
    """Weather prediction rule: 1 (yes), 0 (no), None (no prediction)."""
    side = row.get("predicted_side")
    if side == "yes":
        return 1
    if side == "no":
        return 0
    return None


# ---------------------------------------------------------------------------
# Candidate selection
# ---------------------------------------------------------------------------


def select_current_candidates(
    *,
    feature_packet: Mapping[str, Any],
    generated_ts: float,
    max_close_hours: float,
    max_tickers: int,
) -> list[dict[str, Any]]:
    """Select current weather candidates from the feature packet."""
    rows: list[dict[str, Any]] = []
    for raw_row in feature_packet.get("feature_rows", []):
        if not isinstance(raw_row, Mapping):
            continue
        row = dict(raw_row)
        prediction = weather_proxy_prediction(row)
        close_ts = timestamp(row.get("close_time"))
        if prediction is None or close_ts is None:
            continue
        hours_to_close = (close_ts - generated_ts) / 3600
        if hours_to_close <= 0 or hours_to_close > max_close_hours:
            continue
        side = "yes" if prediction == 1 else "no"
        row["predicted_side"] = side
        row["hours_to_close"] = round(hours_to_close, 6)
        rows.append(row)
    return select_cluster_round_robin(rows, max_tickers=max_tickers)


def select_cluster_round_robin(
    rows: Sequence[Mapping[str, Any]], *, max_tickers: int
) -> list[dict[str, Any]]:
    """Select candidates round-robin across correlation clusters."""
    limit = max(0, max_tickers)
    if limit <= 0:
        return []
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        clusters[_weather_cluster_key(row)].append(dict(row))
    for cluster_rows in clusters.values():
        cluster_rows.sort(key=_candidate_sort_key)
    cluster_keys = sorted(clusters, key=lambda key: (_candidate_sort_key(clusters[key][0]), key))
    selected: list[dict[str, Any]] = []
    while len(selected) < limit and cluster_keys:
        next_keys: list[str] = []
        for key in cluster_keys:
            if len(selected) >= limit:
                next_keys.append(key)
                continue
            cluster_rows = clusters[key]
            if cluster_rows:
                selected.append(cluster_rows.pop(0))
            if cluster_rows:
                next_keys.append(key)
        cluster_keys = next_keys
    selected.sort(key=_candidate_sort_key)
    return selected


def _candidate_sort_key(row: Mapping[str, Any]) -> tuple[float, str, str, str]:
    return (
        float(row.get("hours_to_close") or 999999.0),
        str(row.get("weather_family") or row.get("series_ticker") or ""),
        str(row.get("station_id") or ""),
        str(row.get("contract_ticker") or ""),
    )


def _weather_cluster_key(row: Mapping[str, Any]) -> str:
    """Weather cluster key: station|bracket|date.

    Mirrors weather_cluster_key_composer from the WeatherFamily descriptor.
    """
    return weather_cluster_key_composer(row)


# ---------------------------------------------------------------------------
# Orderbook capture (generic)
# ---------------------------------------------------------------------------


def capture_public_orderbooks(
    *,
    tickers: Sequence[str],
    raw_orderbook_dir: Path,
    generated_utc: str,
    depth: int,
    delay_seconds: float,
    fetch_json: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Fetch public orderbooks for a list of tickers."""
    fetch = fetch_json or _fetch_json_url
    raw_orderbook_dir.mkdir(parents=True, exist_ok=True)
    orderbooks: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for ticker in tickers:
        if not ticker:
            continue
        query = urllib.parse.urlencode({"depth": max(0, int(depth))})
        url = f"{KALSHI_PUBLIC_BASE_URL}/markets/{urllib.parse.quote(ticker)}/orderbook?{query}"
        try:
            payload = fetch(url)
        except Exception as exc:
            errors.append({"ticker": ticker, "error": str(exc)})
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
    stamp = _safe_stamp(generated_utc)
    snapshot_path = raw_orderbook_dir / f"kalshi_weather_proxy_orderbooks_{stamp}.json"
    latest_path = raw_orderbook_dir / "kalshi_weather_proxy_orderbooks_latest.json"
    snapshot_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return snapshot


def load_latest_orderbook_capture(raw_orderbook_dir: Path) -> dict[str, Any]:
    return read_json_or_empty(raw_orderbook_dir / "kalshi_weather_proxy_orderbooks_latest.json")


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


def _fetch_json_url(url: str) -> Any:
    request = urllib.request.Request(url, headers={"accept": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Capacity row computation (uses engine's ask_levels for orderbook depth)
# ---------------------------------------------------------------------------


def build_capacity_row(
    row: Mapping[str, Any],
    *,
    orderbook: Mapping[str, Any] | None,
    calibrated_probability: float | None,
) -> dict[str, Any]:
    """Build a CCD capacity row using engine's ask_levels for depth."""
    side = str(row.get("predicted_side") or "")
    levels = ask_levels(orderbook or {}, side)
    positive_contracts = 0.0
    positive_cost = 0.0
    best_break_even: float | None = None
    best_margin: float | None = None
    best_level_contracts: float | None = None
    for index, level in enumerate(levels):
        cost = normalize_kalshi_execution_cost(
            display_price=level["ask_price"],
            executable_price=level["ask_price"],
            executable_price_source=f"public_orderbook_{side}_ask_level",
            payout_if_correct=1.0,
            ticker=str(row.get("contract_ticker") or ""),
        )
        break_even = cost.break_even_probability
        if index == 0:
            best_break_even = break_even
            best_margin = (
                calibrated_probability - break_even
                if calibrated_probability is not None and break_even is not None
                else None
            )
            best_level_contracts = level["contracts"]
        if (
            calibrated_probability is not None
            and break_even is not None
            and calibrated_probability > break_even
        ):
            positive_contracts += level["contracts"]
            positive_cost += (cost.all_in_cost or 0.0) * level["contracts"]
    gate_status = "pass" if positive_contracts > 0 else "blocked"
    return {
        "contract_ticker": row.get("contract_ticker"),
        "event_ticker": row.get("event_ticker"),
        "series_ticker": row.get("series_ticker"),
        "weather_family": row.get("weather_family", row.get("series_ticker")),
        "close_time": row.get("close_time"),
        "predicted_side": side,
        "level_count": len(levels),
        "best_level_contracts": json_float(best_level_contracts),
        "best_all_in_break_even_probability": json_float(best_break_even),
        "conservative_calibrated_side_probability": json_float(calibrated_probability),
        "best_margin_probability": json_float(best_margin),
        "positive_depth_contracts": json_float(positive_contracts),
        "positive_depth_cost": json_float(positive_cost),
        "correlation_cluster_key": weather_cluster_key_composer(row),
        "gate_status": gate_status,
        "usable": False,
        "research_only": True,
        "execution_enabled": False,
    }


# ---------------------------------------------------------------------------
# Summary, gates, status
# ---------------------------------------------------------------------------


def build_summary(
    *,
    feature_packet: Mapping[str, Any],
    replay: Mapping[str, Any],
    selected: Sequence[Mapping[str, Any]],
    capacity_rows: Sequence[Mapping[str, Any]],
    capture: Mapping[str, Any],
    calibrated_probability: float | None,
    max_cluster_share: float,
    min_positive_capacity_contracts: float,
    min_decay_buckets: int,
    min_decay_labels: int,
) -> dict[str, Any]:
    positive_rows = [
        row for row in capacity_rows if float(row.get("positive_depth_contracts") or 0.0) > 0
    ]
    positive_contracts = sum(
        float(row.get("positive_depth_contracts") or 0.0) for row in capacity_rows
    )
    positive_cost = sum(float(row.get("positive_depth_cost") or 0.0) for row in capacity_rows)
    cluster_costs: dict[str, float] = defaultdict(float)
    for row in capacity_rows:
        cluster_costs[str(row.get("correlation_cluster_key") or "unknown")] += float(
            row.get("positive_depth_cost") or 0.0
        )
    ordered_cluster_costs = dict(
        sorted(cluster_costs.items(), key=lambda item: (-item[1], item[0]))
    )
    largest_key = next(iter(ordered_cluster_costs), None)
    largest_cost = ordered_cluster_costs[largest_key] if largest_key else 0.0
    largest_share = largest_cost / positive_cost if positive_cost > 0 else None

    replay_summary = _get_summary(replay)
    replay_decay_status = str(replay_summary.get("decay_status") or "")
    replay_independent_labels = int(replay_summary.get("independent_contract_label_count") or 0)
    replay_decay_buckets = int(replay_summary.get("decay_bucket_count") or 0)
    candidate_cluster_counts = counts(
        weather_cluster_key_composer(row) for row in selected
    )

    capacity_status = (
        "capacity_depth_positive"
        if positive_contracts >= min_positive_capacity_contracts
        else "capacity_depth_missing_or_not_positive"
    )
    correlation_status = (
        "correlation_cluster_within_limit"
        if largest_share is not None and largest_share <= max_cluster_share
        else "correlation_cluster_concentrated_or_missing"
    )
    decay_status = (
        "decay_survival_pass"
        if (
            replay_decay_status == "recent_bucket_not_worse_than_random"
            and replay_independent_labels >= min_decay_labels
            and replay_decay_buckets >= min_decay_buckets
        )
        else "decay_survival_blocked"
    )

    total_probed = len(capacity_rows)
    positive_count = len(positive_rows)
    observed_positive_fraction = (positive_count / total_probed) if total_probed > 0 else None

    return {
        "feature_packet_status": feature_packet.get("status"),
        "replay_status": replay.get("status"),
        "candidate_row_count": len(selected),
        "candidate_cluster_count": len(candidate_cluster_counts),
        "candidate_cluster_counts": candidate_cluster_counts,
        "orderbook_count": len(orderbook_index(capture)),
        "orderbook_error_count": len(capture.get("errors", []))
        if isinstance(capture.get("errors"), list)
        else 0,
        "capacity_row_count": len(capacity_rows),
        "capacity_positive_row_count": len(positive_rows),
        "positive_depth_contracts": json_float(positive_contracts),
        "positive_depth_cost": json_float(positive_cost),
        "min_positive_capacity_contracts": min_positive_capacity_contracts,
        "capacity_status": capacity_status,
        "correlation_cluster_count": len(ordered_cluster_costs),
        "largest_correlation_cluster_key": largest_key,
        "largest_correlation_cluster_cost": json_float(largest_cost),
        "largest_correlation_cluster_share": json_float(largest_share),
        "max_cluster_share": max_cluster_share,
        "correlation_status": correlation_status,
        "decay_status": decay_status,
        "replay_decay_status": replay_decay_status,
        "replay_decay_bucket_count": replay_decay_buckets,
        "replay_independent_contract_label_count": replay_independent_labels,
        "replay_recent_bucket_key": replay_summary.get("recent_bucket_key"),
        "replay_recent_bucket_accuracy": replay_summary.get("recent_bucket_accuracy"),
        "replay_recent_bucket_label_count": replay_summary.get("recent_bucket_label_count"),
        "replay_total_decay_labels": replay_summary.get("total_decay_labels"),
        "replay_cumulative_decay_accuracy": replay_summary.get("cumulative_decay_accuracy"),
        "replay_passing_bucket_count": replay_summary.get("passing_bucket_count"),
        "replay_decay_buckets": replay_summary.get("decay_buckets", []),
        "min_decay_buckets": min_decay_buckets,
        "min_decay_labels": min_decay_labels,
        "conservative_calibrated_side_probability": json_float(calibrated_probability),
        "positive_depth_prior_axiom3": 0.18,
        "observed_positive_depth_fraction": json_float(observed_positive_fraction),
        "weather_family_counts": counts(
            row.get("weather_family", row.get("series_ticker")) for row in selected
        ),
        "predicted_side_counts": counts(row.get("predicted_side") for row in selected),
        "gate_counts": {},
        "usable_row_count": 0,
    }


def build_gates(
    summary_data: Mapping[str, Any], *, raw_orderbook_dir: Path
) -> list[dict[str, str]]:
    gates_ = [
        gate(
            "replay_candidate_ready",
            "pass"
            if summary_data.get("replay_status")
            == f"{STATUS_PREFIX}_research_candidate_replay_blocked_predeployment_gates"
            else "blocked",
            f"Replay status is {summary_data.get('replay_status')}.",
        ),
        gate(
            "current_candidates_present",
            "pass" if int(summary_data.get("candidate_row_count") or 0) > 0 else "blocked",
            f"{summary_data.get('candidate_row_count')} current candidate row(s) selected.",
        ),
        gate(
            "raw_orderbook_dir_outside_repo",
            "pass" if outside_repo(raw_orderbook_dir) else "blocked",
            "Raw public orderbook snapshots must stay outside the repo.",
        ),
        gate(
            "public_orderbook_depth_present",
            "pass" if int(summary_data.get("orderbook_count") or 0) > 0 else "blocked",
            f"{summary_data.get('orderbook_count')} orderbook(s), {summary_data.get('orderbook_error_count')} error(s).",
        ),
        gate(
            "positive_capacity_depth",
            "pass"
            if summary_data.get("capacity_status") == "capacity_depth_positive"
            else "blocked",
            (
                f"{summary_data.get('positive_depth_contracts')} positive-depth contract(s), "
                f"{summary_data.get('positive_depth_cost')} cost notional."
            ),
        ),
        gate(
            "correlation_cluster_limit",
            "pass"
            if summary_data.get("correlation_status") == "correlation_cluster_within_limit"
            else "blocked",
            (
                f"Largest cluster {summary_data.get('largest_correlation_cluster_key')} has share "
                f"{summary_data.get('largest_correlation_cluster_share')}; max is {summary_data.get('max_cluster_share')}."
            ),
        ),
        gate(
            "decay_survival",
            "pass" if summary_data.get("decay_status") == "decay_survival_pass" else "blocked",
            (
                f"Replay decay status {summary_data.get('replay_decay_status')}, "
                f"{summary_data.get('replay_decay_bucket_count')} bucket(s), "
                f"{summary_data.get('replay_independent_contract_label_count')} independent label(s). "
                f"Recent bucket {summary_data.get('replay_recent_bucket_key')} accuracy "
                f"{summary_data.get('replay_recent_bucket_accuracy')} "
                f"({summary_data.get('replay_recent_bucket_label_count')} labels); "
                f"cumulative accuracy {summary_data.get('replay_cumulative_decay_accuracy')} "
                f"across {summary_data.get('replay_total_decay_labels')} labels; "
                f"{summary_data.get('replay_passing_bucket_count')}/{summary_data.get('replay_decay_bucket_count')} bucket(s) pass >= 0.5."
            ),
        ),
        gate(
            "no_usable_sizing_or_execution",
            "pass" if int(summary_data.get("usable_row_count") or 0) == 0 else "fail",
            "Capacity report remains research-only with zero usable rows and no sizing or execution.",
        ),
    ]
    if isinstance(summary_data, dict):
        summary_data["gate_counts"] = (
            counts(item["status"] for item in gates_) if isinstance(summary_data, dict) else {}
        )
    return gates_


def report_status(summary_data: Mapping[str, Any], gates: Sequence[Mapping[str, Any]]) -> str:
    prefix = STATUS_PREFIX
    if any(item.get("status") == "fail" for item in gates):
        return f"{prefix}_capacity_correlation_decay_failed_safety_gate"
    if _gate_status(gates, "replay_candidate_ready") != "pass":
        return f"{prefix}_capacity_correlation_decay_blocked_missing_replay_candidate"
    if _gate_status(gates, "current_candidates_present") != "pass":
        return f"{prefix}_capacity_correlation_decay_blocked_no_current_candidates"
    if (
        _gate_status(gates, "public_orderbook_depth_present") != "pass"
        or _gate_status(gates, "positive_capacity_depth") != "pass"
    ):
        return f"{prefix}_capacity_correlation_decay_blocked_capacity_depth"
    if _gate_status(gates, "correlation_cluster_limit") != "pass":
        return f"{prefix}_capacity_correlation_decay_blocked_correlation_concentration"
    if _gate_status(gates, "decay_survival") != "pass":
        return f"{prefix}_capacity_correlation_decay_blocked_decay_survival"
    return f"{prefix}_capacity_correlation_decay_ready_for_paper_overlay"


def _next_action(status: str) -> dict[str, str]:
    prefix = STATUS_PREFIX
    if status == f"{prefix}_capacity_correlation_decay_ready_for_paper_overlay":
        return {
            "name": "kalshi_weather_proxy_paper_probability_overlay",
            "why": "Capacity, correlation, and decay gates passed for a research-only current candidate set.",
            "stop_condition": "Stop before real positions, execution, account/order paths, staking, or live edge claims.",
        }
    if status == f"{prefix}_capacity_correlation_decay_blocked_correlation_concentration":
        return {
            "name": "kalshi_weather_proxy_correlation_cluster_control",
            "why": "Current positive-depth candidates are too concentrated in one station/bracket bucket.",
            "stop_condition": "Stop before paper overlay until cluster exposure limits are machine-readable and passing.",
        }
    if status == f"{prefix}_capacity_correlation_decay_blocked_capacity_depth":
        return {
            "name": "kalshi_weather_proxy_orderbook_depth_accumulation",
            "why": "No positive public orderbook depth was captured under the conservative probability hurdle.",
            "stop_condition": "Stop before inferring capacity from top-of-book prices without depth.",
        }
    return {
        "name": "kalshi_weather_proxy_decay_and_sample_accumulation",
        "why": "Capacity/correlation/decay gates are not all passing yet.",
        "stop_condition": "Stop before lowering decay, sample, or correlation limits without an explicit policy review.",
    }


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def write_weather_proxy_capacity_correlation_decay(
    report: Mapping[str, Any],
    out_dir: Path = DEFAULT_OUT_DIR,
    *,
    latest_dir: Path | None = None,
    write_latest: bool | None = None,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-weather-proxy-capacity-correlation-decay.json"
    markdown_path = out_dir / "kalshi-weather-proxy-capacity-correlation-decay.md"
    csv_path = out_dir / "kalshi-weather-proxy-capacity-correlation-decay.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    _write_csv(report, csv_path)
    paths = {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "csv_path": str(csv_path),
    }
    target_latest_dir = latest_dir or MACRO_DIR
    should_write_latest = (
        path_is_within(out_dir, MACRO_DIR) if write_latest is None else write_latest
    )
    if should_write_latest:
        target_latest_dir.mkdir(parents=True, exist_ok=True)
        latest_json = (
            target_latest_dir / "latest-kalshi-weather-proxy-capacity-correlation-decay.json"
        )
        latest_md = (
            target_latest_dir / "latest-kalshi-weather-proxy-capacity-correlation-decay.md"
        )
        latest_csv = (
            target_latest_dir / "latest-kalshi-weather-proxy-capacity-correlation-decay.csv"
        )
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(_render_markdown(report), encoding="utf-8")
        _write_csv(report, latest_csv)
        paths["latest_json_path"] = str(latest_json)
        paths["latest_markdown_path"] = str(latest_md)
        paths["latest_csv_path"] = str(latest_csv)
    return paths


def _render_markdown(report: Mapping[str, Any]) -> str:
    data = _get_summary(report)
    lines = [
        "# Kalshi Weather Proxy Capacity Correlation Decay",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Current candidates: `{data.get('candidate_row_count')}`",
        f"- Candidate clusters: `{data.get('candidate_cluster_count')}`",
        f"- Orderbooks: `{data.get('orderbook_count')}`",
        f"- Positive-depth contracts: `{data.get('positive_depth_contracts')}`",
        f"- Positive-depth cost: `{data.get('positive_depth_cost')}`",
        f"- Largest cluster share: `{data.get('largest_correlation_cluster_share')}`",
        f"- Decay status: `{data.get('decay_status')}`",
        f"- Observed positive-depth fraction: `{data.get('observed_positive_depth_fraction')}`",
        f"- Positive-depth prior (Axiom 3): `{data.get('positive_depth_prior_axiom3')}`",
        f"- Usable rows: `{data.get('usable_row_count')}`",
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
    next_step = report.get("next_action") if isinstance(report.get("next_action"), Mapping) else {}
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            f"- Name: `{next_step.get('name')}`",
            f"- Why: {next_step.get('why')}",
            f"- Stop condition: {next_step.get('stop_condition')}",
            "",
            "## Guardrail",
            "",
            "This report is not a betting recommendation and never authorizes sizing or execution.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_csv(report: Mapping[str, Any], path: Path) -> None:
    import csv as _csv
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = _csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in report.get("capacity_rows", []):
            if isinstance(row, Mapping):
                writer.writerow({field: row.get(field) for field in CSV_FIELDS})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_calibrated_probability(replay: Mapping[str, Any]) -> float | None:
    replay_summary = _get_summary(replay)
    return probability(replay_summary.get("conservative_calibrated_side_probability"))


def _get_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping) and isinstance(value.get("summary"), Mapping):
        return dict(value["summary"])
    return {}


def _capture_brief(capture: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": capture.get("status"),
        "created_at_utc": capture.get("created_at_utc"),
        "summary": capture.get("summary") if isinstance(capture.get("summary"), Mapping) else {},
    }


def _gate_status(gates: Sequence[Mapping[str, Any]], name: str) -> str:
    for item in gates:
        if item.get("name") == name:
            return str(item.get("status") or "")
    return "blocked"


def _safe_stamp(value: str) -> str:
    return (
        value.replace("-", "")
        .replace(":", "")
        .replace("+00:00", "Z")
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-packet-path", type=Path, default=DEFAULT_FEATURE_PACKET_PATH)
    parser.add_argument("--replay-path", type=Path, default=DEFAULT_REPLAY_PATH)
    parser.add_argument("--raw-orderbook-dir", type=Path, default=DEFAULT_RAW_ORDERBOOK_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-close-hours", type=float, default=DEFAULT_MAX_CLOSE_HOURS)
    parser.add_argument("--max-tickers", type=int, default=DEFAULT_MAX_TICKERS)
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    parser.add_argument("--delay-seconds", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--max-cluster-share", type=float, default=DEFAULT_MAX_CLUSTER_SHARE)
    parser.add_argument(
        "--min-positive-capacity-contracts",
        type=float,
        default=DEFAULT_MIN_POSITIVE_CAPACITY_CONTRACTS,
    )
    parser.add_argument("--min-decay-buckets", type=int, default=DEFAULT_MIN_DECAY_BUCKETS)
    parser.add_argument("--min-decay-labels", type=int, default=DEFAULT_MIN_DECAY_LABELS)
    parser.add_argument("--capture-orderbooks", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_weather_proxy_capacity_correlation_decay(
        feature_packet_path=args.feature_packet_path,
        replay_path=args.replay_path,
        raw_orderbook_dir=args.raw_orderbook_dir,
        max_close_hours=args.max_close_hours,
        max_tickers=args.max_tickers,
        depth=args.depth,
        delay_seconds=args.delay_seconds,
        capture_orderbooks=args.capture_orderbooks,
        max_cluster_share=args.max_cluster_share,
        min_positive_capacity_contracts=args.min_positive_capacity_contracts,
        min_decay_buckets=args.min_decay_buckets,
        min_decay_labels=args.min_decay_labels,
    )
    if args.write:
        paths = write_weather_proxy_capacity_correlation_decay(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], "paths": paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
