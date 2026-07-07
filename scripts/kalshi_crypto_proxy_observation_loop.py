#!/usr/bin/env python3
"""Archive crypto proxy feature observations and attach settled Kalshi labels.

This is the first repeatability loop after contract-keyed crypto proxy features.
It records point-in-time features outside the repo, then labels only from public
settled Kalshi market payloads. Proxy prices remain features, never labels,
calibrated probabilities, EV, sizing, or execution evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.feature_flags import FeatureFlag, is_enabled  # noqa: E402
from predmarket.shared_helpers import manual_drop_path  # noqa: E402

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_FEATURE_PACKET_PATH = MACRO_DIR / "latest-kalshi-crypto-proxy-feature-packet.json"
DEFAULT_SETTLED_SNAPSHOT_PATH = manual_drop_path(
    "kalshi_oos_settlements", "kalshi_settled_markets_latest.json"
)
DEFAULT_SETTLED_RAW_DIR = manual_drop_path("kalshi_oos_settlements")
DEFAULT_OBSERVATION_DIR = manual_drop_path("kalshi_crypto_proxy_observations")
DEFAULT_LABEL_DIR = manual_drop_path("kalshi_crypto_proxy_labels")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-crypto-proxy-observation-loop-latest"
KALSHI_PUBLIC_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
CSV_FIELDS = [
    "observation_id",
    "contract_ticker",
    "asset_symbol",
    "contract_family",
    "decision_time",
    "close_time",
    "yes_ask",
    "proxy_price",
    "proxy_state",
    "label_status",
    "yes_outcome",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_float(value: Any) -> float | None:
    """Safely convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_crypto_proxy_observation_loop(
    *,
    feature_packet_path: Path = DEFAULT_FEATURE_PACKET_PATH,
    settled_snapshot_path: Path = DEFAULT_SETTLED_SNAPSHOT_PATH,
    observation_dir: Path = DEFAULT_OBSERVATION_DIR,
    label_dir: Path = DEFAULT_LABEL_DIR,
    generated_utc: str | None = None,
    public_market_data_calls: bool = False,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    feature_packet = read_json_or_empty(feature_packet_path)
    settled_snapshot = read_json_or_empty(settled_snapshot_path)
    feature_safe = safe_research_artifact(feature_packet)
    candidate_observations = (
        feature_observations(feature_packet, feature_packet_path=feature_packet_path)
        if feature_safe
        else []
    )
    existing = load_packets(observation_dir)
    existing_observation_ids = observation_ids(existing["rows"])
    new_observations = [
        row for row in candidate_observations if str(row.get("observation_id") or "") not in existing_observation_ids
    ]
    all_observations = dedupe_by_id([*existing["rows"], *candidate_observations])
    existing_labels = load_packets(label_dir)
    existing_label_ids = observation_ids(existing_labels["rows"])
    due_summary = observation_due_summary(all_observations, generated_utc=generated)
    settled_index = settled_market_index(settled_snapshot)
    computed_label_rows, label_blocked = label_observations(all_observations, settled_index)
    new_label_rows = [
        row for row in computed_label_rows if str(row.get("observation_id") or "") not in existing_label_ids
    ]
    all_label_rows = dedupe_by_id([*existing_labels["rows"], *computed_label_rows])
    status = loop_status(
        feature_safe=feature_safe,
        new_observation_count=len(new_observations),
        total_observation_count=len(all_observations),
        label_count=len(all_label_rows),
    )

    # Feature flag: crypto proxy orderbook depth enrichment. When enabled,
    # spread metrics are computed from the proxy ask vs. Kalshi yes_ask to
    # flag observations where the orderbook depth suggests low fill confidence.
    depth_enabled = is_enabled(FeatureFlag.CRYPTO_PROXY_ORDERBOOK_DEPTH)
    depth_metrics: dict[str, Any] = {}
    if depth_enabled and all_observations:
        spreads = []
        for row in all_observations:
            ask = _safe_float(row.get("yes_ask"))
            proxy = _safe_float(row.get("proxy_price"))
            if ask is not None and proxy is not None and ask > 0:
                spreads.append(abs(ask - proxy) / ask)
        if spreads:
            depth_metrics = {
                "enabled": True,
                "observed_spread_count": len(spreads),
                "median_spread": sorted(spreads)[len(spreads) // 2],
                "max_spread": max(spreads),
                "mean_spread": sum(spreads) / len(spreads),
            }
    gates = build_gates(
        feature_safe=feature_safe,
        observation_count=len(all_observations),
        new_observation_count=len(new_observations),
        settled_market_count=len(settled_index),
        label_count=len(all_label_rows),
        observation_dir=observation_dir,
        label_dir=label_dir,
        rows=[*all_observations, *all_label_rows],
    )
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": public_market_data_calls,
        "authenticated_api_calls": False,
        "provider_api_calls": public_market_data_calls,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "inputs": {
            "feature_packet_path": str(feature_packet_path),
            "feature_packet_sha256": sha256_or_none(feature_packet_path),
            "feature_packet_status": feature_packet.get("status") if isinstance(feature_packet, Mapping) else None,
            "settled_snapshot_path": str(settled_snapshot_path),
            "settled_snapshot_sha256": sha256_or_none(settled_snapshot_path),
            "observation_dir": str(observation_dir),
            "label_dir": str(label_dir),
        },
        "method": {
            "observation_rule": "Record ready crypto proxy feature rows keyed by exact Kalshi contract ticker and packet time.",
            "label_rule": "Attach outcomes only from public settled Kalshi market payloads matched by exact ticker.",
            "proxy_boundary": "Coinbase/public exchange data are model features only and never official settlement labels.",
            "ev_boundary": "This loop does not create calibrated probabilities, EV, usable rows, sizing, or orders.",
            "orderbook_depth_enrichment": depth_enabled,
        },
        "orderbook_depth": depth_metrics if depth_enabled else {"enabled": False},
        "summary": {
            "feature_packet_safe": feature_safe,
            "new_observation_row_count": len(new_observations),
            "existing_observation_packet_count": existing["packet_count"],
            "existing_observation_row_count": len(existing["rows"]),
            "total_observation_row_count": len(all_observations),
            "distinct_contract_count": len({row.get("contract_ticker") for row in all_observations}),
            "settled_market_count": len(settled_index),
            "existing_label_packet_count": existing_labels["packet_count"],
            "existing_label_row_count": len(existing_labels["rows"]),
            "new_label_row_count": len(new_label_rows),
            "label_row_count": len(all_label_rows),
            "blocked_label_row_count": len(label_blocked),
            "asset_counts": counts(row.get("asset_symbol") for row in all_observations),
            "contract_family_counts": counts(row.get("contract_family") for row in all_observations),
            "label_status_counts": counts(row.get("label_status") for row in [*all_label_rows, *label_blocked]),
            "due_observation_row_count": due_summary["due_observation_row_count"],
            "due_distinct_contract_count": due_summary["due_distinct_contract_count"],
            "not_due_distinct_contract_count": due_summary["not_due_distinct_contract_count"],
            "oldest_due_expected_expiration_utc": due_summary["oldest_due_expected_expiration_utc"],
            "next_expected_expiration_utc": due_summary["next_expected_expiration_utc"],
            "next_public_label_probe_utc": due_summary["next_public_label_probe_utc"],
            "expected_expiration_bucket_counts": due_summary["expected_expiration_bucket_counts"],
            "gate_counts": gate_counts(gates),
        },
        "observation_packet": safe_packet(
            generated_utc=generated,
            packet_type="kalshi_crypto_proxy_feature_observations",
            rows=new_observations,
            inputs={"feature_packet_path": str(feature_packet_path)},
        ),
        "label_packet": safe_packet(
            generated_utc=generated,
            packet_type="kalshi_crypto_proxy_feature_labels",
            rows=new_label_rows,
            inputs={
                "observation_dir": str(observation_dir),
                "settled_snapshot_path": str(settled_snapshot_path),
            },
        ),
        "gates": gates,
        "observation_rows_sample": all_observations[:20],
        "label_rows_sample": all_label_rows[:20],
        "blocked_label_rows_sample": label_blocked[:50],
        "next_action": next_action(status),
        "label_probe_schedule": due_summary,
        "safety": safety_flags(public_market_data_calls=public_market_data_calls),
    }


def capture_public_settled_snapshot(
    *,
    raw_dir: Path = DEFAULT_SETTLED_RAW_DIR,
    limit: int = 1000,
    max_pages: int = 1,
    generated_utc: str | None = None,
    fetch_json: Any | None = None,
) -> Path:
    generated = generated_utc or utc_now()
    fetch = fetch_json or fetch_json_url
    raw_dir.mkdir(parents=True, exist_ok=True)
    markets: list[Mapping[str, Any]] = []
    cursor = ""
    for _ in range(max(1, max_pages)):
        query = urllib.parse.urlencode(
            {
                "status": "settled",
                "limit": max(1, min(int(limit), 1000)),
                "mve_filter": "exclude",
                **({"cursor": cursor} if cursor else {}),
            }
        )
        payload = fetch(f"{KALSHI_PUBLIC_BASE_URL}/markets?{query}")
        if not isinstance(payload, Mapping):
            break
        markets.extend(row for row in payload.get("markets", []) if isinstance(row, Mapping))
        cursor = str(payload.get("cursor") or "")
        if not cursor:
            break
    snapshot = {
        "schema_version": 1,
        "created_at_utc": generated,
        "status": "kalshi_public_settled_fetch_ok" if markets else "kalshi_public_settled_fetch_empty",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "query": {
            "status": "settled",
            "limit": max(1, min(int(limit), 1000)),
            "max_pages": max_pages,
            "mve_filter": "exclude",
        },
        "summary": {"market_count": len(markets), "cursor_present": bool(cursor)},
        "safety": safety_flags(public_market_data_calls=True),
        "markets": markets,
    }
    stamp = safe_stamp(generated)
    snapshot_path = raw_dir / f"kalshi_settled_markets_{stamp}.json"
    latest_path = raw_dir / "kalshi_settled_markets_latest.json"
    text = json.dumps(snapshot, indent=2, sort_keys=True, default=str) + "\n"
    snapshot_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return latest_path


def capture_public_observed_markets_snapshot(
    *,
    tickers: Sequence[str],
    raw_dir: Path = DEFAULT_SETTLED_RAW_DIR,
    base_snapshot_path: Path | None = None,
    generated_utc: str | None = None,
    fetch_json: Any | None = None,
) -> Path:
    generated = generated_utc or utc_now()
    fetch = fetch_json or fetch_json_url
    raw_dir.mkdir(parents=True, exist_ok=True)
    base_snapshot = read_json_or_empty(base_snapshot_path) if base_snapshot_path else {}
    base_markets = base_snapshot.get("markets", []) if isinstance(base_snapshot.get("markets"), list) else []
    markets: list[Mapping[str, Any]] = [row for row in base_markets if isinstance(row, Mapping)]
    probe_errors: list[dict[str, str]] = []
    seen = {str(row.get("ticker") or "") for row in markets}
    for ticker in tickers:
        if not ticker or ticker in seen:
            continue
        try:
            payload = fetch(f"{KALSHI_PUBLIC_BASE_URL}/markets/{urllib.parse.quote(ticker, safe='')}")
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
        "status": "kalshi_public_observed_market_fetch_ok"
        if markets
        else "kalshi_public_observed_market_fetch_empty",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "query": {
            "mode": "exact_observed_ticker_probe",
            "observed_ticker_count": len(tickers),
            "base_snapshot_path": str(base_snapshot_path) if base_snapshot_path else None,
        },
        "summary": {
            "market_count": len(markets),
            "base_market_count": len(base_markets),
            "observed_ticker_count": len(tickers),
            "probe_error_count": len(probe_errors),
            "settled_label_ready_count": sum(1 for market in markets if settlement_outcome(market) is not None),
        },
        "probe_errors_sample": probe_errors[:50],
        "safety": safety_flags(public_market_data_calls=True),
        "markets": markets,
    }
    stamp = safe_stamp(generated)
    snapshot_path = raw_dir / f"kalshi_observed_markets_{stamp}.json"
    latest_path = raw_dir / "kalshi_observed_markets_latest.json"
    text = json.dumps(snapshot, indent=2, sort_keys=True, default=str) + "\n"
    snapshot_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return latest_path


def due_observed_tickers(
    *,
    feature_packet_path: Path,
    observation_dir: Path,
    generated_utc: str,
    max_tickers: int,
) -> list[str]:
    rows: list[Mapping[str, Any]] = []
    feature_packet = read_json_or_empty(feature_packet_path)
    if safe_research_artifact(feature_packet):
        rows.extend(feature_observations(feature_packet, feature_packet_path=feature_packet_path))
    rows.extend(load_packets(observation_dir)["rows"])
    cutoff = timestamp(generated_utc) or datetime.now(UTC).timestamp()
    output: list[str] = []
    seen: set[str] = set()
    for row in rows:
        due_at = timestamp(first_present(row, ["expected_expiration_time", "expiration_time", "close_time"]))
        ticker = str(row.get("contract_ticker") or "").strip()
        if not ticker or ticker in seen or due_at is None or due_at > cutoff:
            continue
        seen.add(ticker)
        output.append(ticker)
        if len(output) >= max(0, max_tickers):
            break
    return output


def observation_due_summary(rows: Sequence[Mapping[str, Any]], *, generated_utc: str) -> dict[str, Any]:
    cutoff = timestamp(generated_utc) or datetime.now(UTC).timestamp()
    due_rows = 0
    due_contracts: set[str] = set()
    not_due_contracts: set[str] = set()
    due_times: list[float] = []
    future_times: list[float] = []
    bucket_counter: Counter[str] = Counter()
    for row in rows:
        ticker = str(row.get("contract_ticker") or "").strip()
        due_at = timestamp(first_present(row, ["expected_expiration_time", "expiration_time", "close_time"]))
        if not ticker or due_at is None:
            continue
        bucket_counter[bucket_time(due_at)] += 1
        if due_at <= cutoff:
            due_rows += 1
            due_contracts.add(ticker)
            due_times.append(due_at)
        else:
            not_due_contracts.add(ticker)
            future_times.append(due_at)
    next_expiration = min(future_times) if future_times else None
    oldest_due = min(due_times) if due_times else None
    return {
        "generated_utc": generated_utc,
        "due_observation_row_count": due_rows,
        "due_distinct_contract_count": len(due_contracts),
        "not_due_distinct_contract_count": len(not_due_contracts - due_contracts),
        "oldest_due_expected_expiration_utc": iso_from_timestamp(oldest_due),
        "next_expected_expiration_utc": iso_from_timestamp(next_expiration),
        "next_public_label_probe_utc": generated_utc if due_contracts else iso_from_timestamp(next_expiration),
        "expected_expiration_bucket_counts": dict(sorted(bucket_counter.items(), key=lambda item: item[0])[:12]),
    }


def fetch_json_url(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.load(response)
    return payload if isinstance(payload, dict) else {}


def feature_observations(feature_packet: Mapping[str, Any], *, feature_packet_path: Path) -> list[dict[str, Any]]:
    rows = feature_packet.get("feature_rows", [])
    if not isinstance(rows, list):
        return []
    generated = str(feature_packet.get("generated_utc") or utc_now())
    source_sha = sha256_or_none(feature_packet_path)
    observations: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        if row.get("feature_status") != "proxy_features_ready":
            continue
        ticker = str(row.get("contract_ticker") or "").strip()
        if not ticker:
            continue
        observation = {
            "schema_version": "KalshiCryptoProxyFeatureObservationV1",
            "observation_id": observation_id(ticker=ticker, decision_time=generated, source_row_index=index),
            "contract_ticker": ticker,
            "event_ticker": row.get("event_ticker"),
            "series_ticker": row.get("series_ticker"),
            "side": "yes",
            "asset_symbol": row.get("asset_symbol"),
            "contract_family": row.get("contract_family"),
            "contract_side": row.get("contract_side"),
            "decision_time": generated,
            "quote_time": generated,
            "model_time": generated,
            "timestamp_source": "crypto_proxy_feature_packet_generated_utc",
            "close_time": row.get("close_time"),
            "expected_expiration_time": row.get("expected_expiration_time"),
            "yes_bid": probability(row.get("yes_bid")),
            "yes_ask": probability(row.get("yes_ask")),
            "yes_spread": optional_float(row.get("yes_spread")),
            "proxy_source": row.get("proxy_source"),
            "proxy_product_id": row.get("proxy_product_id"),
            "proxy_price": optional_float(row.get("proxy_price")),
            "proxy_observed_at_utc": row.get("proxy_observed_at_utc"),
            "proxy_return_5m": optional_float(row.get("proxy_return_5m")),
            "proxy_return_15m": optional_float(row.get("proxy_return_15m")),
            "proxy_return_60m": optional_float(row.get("proxy_return_60m")),
            "proxy_realized_vol_15m": optional_float(row.get("proxy_realized_vol_15m")),
            "proxy_realized_vol_60m": optional_float(row.get("proxy_realized_vol_60m")),
            "proxy_distance_to_floor": optional_float(row.get("proxy_distance_to_floor")),
            "proxy_distance_to_cap": optional_float(row.get("proxy_distance_to_cap")),
            "proxy_state": row.get("proxy_state"),
            "feature_policy": "proxy_feature_only_not_official_settlement_label",
            "label_status": "pending_settled_kalshi_outcome",
            "calibrated_probability": None,
            "expected_value_per_contract": None,
            "usable": False,
            "source_artifact": str(feature_packet_path),
            "source_artifact_sha256": source_sha,
            "source_row_index": index,
            "research_only": True,
            "execution_enabled": False,
        }
        observations.append(observation)
    return observations


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
        close_time = iso_time(first_present(market, ["close_time", "expected_expiration_time", "expiration_time"], row.get("close_time")))
        settled_time = iso_time(first_present(market, ["settlement_ts", "settled_time", "expiration_time", "close_time"]))
        if close_time is None or settled_time is None:
            blocked.append(blocked_label(row, "settlement_timestamps_missing"))
            continue
        labels.append(
            {
                **dict(row),
                "label_status": "labeled_from_public_kalshi_settled_market",
                "yes_outcome": yes_outcome,
                "side_outcome": yes_outcome,
                "close_time": close_time,
                "settled_time": settled_time,
                "label_source": "public_kalshi_settled_market_payload",
                "settlement_result": market.get("result"),
                "settlement_value_dollars": market.get("settlement_value_dollars"),
                "calibrated_probability": None,
                "expected_value_per_contract": None,
                "usable": False,
            }
        )
    return labels, blocked


def blocked_label(row: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "observation_id": row.get("observation_id"),
        "contract_ticker": row.get("contract_ticker"),
        "asset_symbol": row.get("asset_symbol"),
        "decision_time": row.get("decision_time"),
        "label_status": reason,
    }


def settled_market_index(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    markets = snapshot.get("markets", [])
    if not isinstance(markets, list):
        return {}
    output: dict[str, Mapping[str, Any]] = {}
    for market in markets:
        if not isinstance(market, Mapping):
            continue
        ticker = str(market.get("ticker") or "").strip()
        if ticker and settlement_outcome(market) is not None:
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


def build_gates(
    *,
    feature_safe: bool,
    observation_count: int,
    new_observation_count: int,
    settled_market_count: int,
    label_count: int,
    observation_dir: Path,
    label_dir: Path,
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        gate("crypto_proxy_feature_packet_safe", "pass" if feature_safe else "blocked", "Ready, research-only crypto proxy feature packet is required."),
        gate("new_observations_recorded", "pass" if new_observation_count else "warn", f"{new_observation_count} new observation row(s) from latest feature packet."),
        gate("observations_available", "pass" if observation_count else "blocked", f"{observation_count} total crypto proxy observation row(s)."),
        gate("settled_markets_available", "pass" if settled_market_count else "warn", f"{settled_market_count} public settled market row(s) loaded."),
        gate("label_rows_available", "pass" if label_count else "warn", f"{label_count} crypto proxy label row(s) emitted."),
        gate("manual_drop_dirs_outside_repo", "pass" if outside_repo(observation_dir) and outside_repo(label_dir) else "blocked", "Observation and label packets must stay outside the repo."),
        gate(
            "no_probability_ev_or_execution_claims",
            "pass"
            if all(
                row.get("usable") is False
                and row.get("calibrated_probability") is None
                and row.get("expected_value_per_contract") is None
                for row in rows
            )
            else "fail",
            "Observations and labels remain feature/outcome data only.",
        ),
    ]


def loop_status(
    *,
    feature_safe: bool,
    new_observation_count: int,
    total_observation_count: int,
    label_count: int,
) -> str:
    if not feature_safe:
        return "crypto_proxy_observation_loop_blocked_missing_feature_packet"
    if label_count:
        return "crypto_proxy_observation_loop_label_rows_ready"
    if total_observation_count:
        return "crypto_proxy_observation_loop_ready_waiting_settlement"
    if new_observation_count:
        return "crypto_proxy_observation_loop_observations_recorded_waiting_settlement"
    return "crypto_proxy_observation_loop_blocked_no_observations"


def next_action(status: str) -> dict[str, str]:
    if status == "crypto_proxy_observation_loop_label_rows_ready":
        return {
            "name": "kalshi_crypto_proxy_feature_model_falsification",
            "why": "Feature observations now have real Kalshi settled outcomes; next work is a cost-aware feature model and OOS falsification.",
            "stop_condition": "Stop before promoting, sizing, or executing without calibrated probabilities and FDR-controlled OOS survival.",
        }
    if status == "crypto_proxy_observation_loop_ready_waiting_settlement":
        return {
            "name": "kalshi_crypto_proxy_observation_accumulation",
            "why": "Feature observations are archived; keep collecting snapshots and settled outcomes until labels exist.",
            "stop_condition": "Stop before using proxy states as labels, model probabilities, EV, sizing, or execution evidence.",
        }
    return {
        "name": "kalshi_crypto_proxy_observation_blocker_review",
        "why": "The observation loop lacks safe feature observations.",
        "stop_condition": "Stop before inventing observations, labels, probabilities, EV, sizing, or execution evidence.",
    }


def write_crypto_proxy_observation_outputs(
    report: Mapping[str, Any],
    *,
    out_dir: Path = DEFAULT_OUT_DIR,
    observation_dir: Path = DEFAULT_OBSERVATION_DIR,
    label_dir: Path = DEFAULT_LABEL_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-crypto-proxy-observation-loop.json"
    md_path = out_dir / "kalshi-crypto-proxy-observation-loop.md"
    csv_path = out_dir / "kalshi-crypto-proxy-observation-loop.csv"
    timer_path = out_dir / "kalshi-crypto-proxy-observation-loop.timer.example"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, csv_path)
    timer_path.write_text(render_timer_template(), encoding="utf-8")
    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
        "schedule_template_path": str(timer_path),
    }
    stamp = safe_stamp(str(report.get("generated_utc") or utc_now()))

    observation_rows = packet_rows(report.get("observation_packet"))
    if observation_rows:
        observation_dir.mkdir(parents=True, exist_ok=True)
        obs_path = observation_dir / f"crypto_proxy_observations_{stamp}.json"
        obs_latest = observation_dir / "crypto_proxy_observations_latest.json"
        obs_text = json.dumps(report["observation_packet"], indent=2, sort_keys=True, default=str) + "\n"
        obs_path.write_text(obs_text, encoding="utf-8")
        obs_latest.write_text(obs_text, encoding="utf-8")
        paths["observation_packet_path"] = str(obs_path)
        paths["observation_packet_latest_path"] = str(obs_latest)

    label_rows = packet_rows(report.get("label_packet"))
    if label_rows:
        label_dir.mkdir(parents=True, exist_ok=True)
        label_path = label_dir / f"crypto_proxy_labels_{stamp}.json"
        label_latest = label_dir / "crypto_proxy_labels_latest.json"
        label_text = json.dumps(report["label_packet"], indent=2, sort_keys=True, default=str) + "\n"
        label_path.write_text(label_text, encoding="utf-8")
        label_latest.write_text(label_text, encoding="utf-8")
        paths["label_packet_path"] = str(label_path)
        paths["label_packet_latest_path"] = str(label_latest)

    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-crypto-proxy-observation-loop.json"
    latest_md = MACRO_DIR / "latest-kalshi-crypto-proxy-observation-loop.md"
    latest_csv = MACRO_DIR / "latest-kalshi-crypto-proxy-observation-loop.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, latest_csv)
    paths["latest_json_path"] = str(latest_json)
    paths["latest_markdown_path"] = str(latest_md)
    paths["latest_csv_path"] = str(latest_csv)
    return paths


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    next_step = report.get("next_action") if isinstance(report.get("next_action"), Mapping) else {}
    lines = [
        "# Kalshi Crypto Proxy Observation Loop",
        "",
        f"- Status: `{report.get('status')}`",
        f"- New observations: `{summary.get('new_observation_row_count')}`",
        f"- Total observations: `{summary.get('total_observation_row_count')}`",
        f"- Due observations: `{summary.get('due_observation_row_count')}`",
        f"- Due contracts: `{summary.get('due_distinct_contract_count')}`",
        f"- Next expected expiration: `{summary.get('next_expected_expiration_utc')}`",
        f"- Next public label probe: `{summary.get('next_public_label_probe_utc')}`",
        f"- Label rows: `{summary.get('label_row_count')}`",
        f"- Assets: `{summary.get('asset_counts')}`",
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
            "## Guardrail",
            "",
            "This loop archives features and settled outcomes only. It does not produce model probabilities, EV, sizing, or orders.",
            "",
        ]
    )
    return "\n".join(lines)


def render_timer_template() -> str:
    return """# Example systemd user timer. Do not enable automatically.
# Save as ~/.config/systemd/user/kalshi-crypto-proxy-observation-loop.timer after review.

[Unit]
Description=Run research-only Kalshi crypto proxy observation loop every 10 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
RandomizedDelaySec=45s
Persistent=true

[Install]
WantedBy=timers.target

# Matching service:
# Save as ~/.config/systemd/user/kalshi-crypto-proxy-observation-loop.service after review.
# [Unit]
# Description=Research-only Kalshi crypto proxy observation loop
# [Service]
# Type=oneshot
# WorkingDirectory=/path/to/predmarket-alpha
# ExecStart=/usr/bin/make kalshi-crypto-proxy-observation-watch-once
"""


def write_csv(report: Mapping[str, Any], path: Path) -> None:
    rows: list[Mapping[str, Any]] = []
    rows.extend(row for row in report.get("label_rows_sample", []) if isinstance(row, Mapping))
    rows.extend(row for row in report.get("observation_rows_sample", []) if isinstance(row, Mapping))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in CSV_FIELDS})


def load_packets(directory: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    paths: list[str] = []
    if not directory.exists():
        return {"packet_count": 0, "paths": [], "rows": []}
    for path in sorted(directory.glob("*.json")):
        payload = read_json_or_empty(path)
        if not safe_research_artifact(payload):
            continue
        packet_rows = payload.get("rows", [])
        if not isinstance(packet_rows, list):
            continue
        paths.append(str(path))
        rows.extend(dict(row) for row in packet_rows if isinstance(row, Mapping))
    return {"packet_count": len(paths), "paths": paths, "rows": rows}


def dedupe_by_id(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.get("observation_id") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(dict(row))
    output.sort(key=lambda item: (str(item.get("decision_time") or ""), str(item.get("contract_ticker") or "")))
    return output


def observation_ids(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    return {str(row.get("observation_id") or "") for row in rows if row.get("observation_id")}


def safe_packet(*, generated_utc: str, packet_type: str, rows: Sequence[Mapping[str, Any]], inputs: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_utc": generated_utc,
        "packet_type": packet_type,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "staking_or_sizing_guidance": False,
        "inputs": dict(inputs),
        "rows": list(rows),
        "safety": safety_flags(public_market_data_calls=False),
    }


def packet_rows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        return []
    rows = value.get("rows", [])
    return [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


def observation_id(*, ticker: str, decision_time: str, source_row_index: int) -> str:
    material = f"{ticker}|{decision_time}|{source_row_index}".encode()
    return "crypto_obs_" + hashlib.sha256(material).hexdigest()[:20]


def first_present(row: Mapping[str, Any], keys: Sequence[str], fallback: Any = None) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in {None, ""}:
            return value
    return fallback


def probability(value: Any) -> float | None:
    number = optional_float(value)
    return number if number is not None and 0.0 <= number <= 1.0 else None


def optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip().rstrip("%")
            if not value:
                return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        number = None
    if number is not None:
        return number if math.isfinite(number) else None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def iso_from_timestamp(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def bucket_time(value: float) -> str:
    parsed = datetime.fromtimestamp(value, UTC).replace(second=0, microsecond=0)
    minute = (parsed.minute // 15) * 15
    return parsed.replace(minute=minute).isoformat(timespec="minutes").replace("+00:00", "Z")


def iso_time(value: Any) -> str | None:
    ts = timestamp(value)
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def counts(values: Sequence[Any]) -> dict[str, int]:
    counter = Counter(str(value or "unknown") for value in values)
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def gate_counts(gates: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counter = Counter(str(item.get("status") or "blocked") for item in gates)
    return {"pass": counter["pass"], "warn": counter["warn"], "blocked": counter["blocked"], "fail": counter["fail"]}


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def safe_research_artifact(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    safety = value.get("safety") if isinstance(value.get("safety"), Mapping) else {}
    return (
        value.get("research_only") is True
        and value.get("execution_enabled") is False
        and value.get("market_execution") is not True
        and value.get("account_or_order_paths") is not True
        and safety.get("market_execution") is False
        and safety.get("account_or_order_paths") is False
        and safety.get("database_writes") is False
    )


def safety_flags(*, public_market_data_calls: bool) -> dict[str, bool]:
    return {
        "research_only": True,
        "public_market_data_calls": public_market_data_calls,
        "authenticated_api_calls": False,
        "provider_api_calls": public_market_data_calls,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "raw_payloads_copied_to_repo": False,
        "staking_or_sizing_guidance": False,
    }


def outside_repo(path: Path) -> bool:
    try:
        path.expanduser().resolve().relative_to(CONTROL_REPO.resolve())
    except ValueError:
        return True
    return False


def read_json_or_empty(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def sha256_or_none(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_stamp(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum()) or "latest"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-packet-path", type=Path, default=DEFAULT_FEATURE_PACKET_PATH)
    parser.add_argument("--settled-snapshot-path", type=Path, default=DEFAULT_SETTLED_SNAPSHOT_PATH)
    parser.add_argument("--settled-raw-dir", type=Path, default=DEFAULT_SETTLED_RAW_DIR)
    parser.add_argument("--capture-settled-public", action="store_true")
    parser.add_argument("--probe-observed-public", action="store_true")
    parser.add_argument("--observed-probe-max-tickers", type=int, default=300)
    parser.add_argument("--settled-limit", type=int, default=1000)
    parser.add_argument("--settled-max-pages", type=int, default=1)
    parser.add_argument("--observation-dir", type=Path, default=DEFAULT_OBSERVATION_DIR)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    generated = utc_now()
    settled_snapshot_path = args.settled_snapshot_path
    public_calls = False
    if args.capture_settled_public:
        settled_snapshot_path = capture_public_settled_snapshot(
            raw_dir=args.settled_raw_dir,
            limit=args.settled_limit,
            max_pages=args.settled_max_pages,
            generated_utc=generated,
        )
        public_calls = True
    if args.probe_observed_public:
        due_tickers = due_observed_tickers(
            feature_packet_path=args.feature_packet_path,
            observation_dir=args.observation_dir,
            generated_utc=generated,
            max_tickers=args.observed_probe_max_tickers,
        )
        if due_tickers:
            settled_snapshot_path = capture_public_observed_markets_snapshot(
                tickers=due_tickers,
                raw_dir=args.settled_raw_dir,
                base_snapshot_path=settled_snapshot_path if settled_snapshot_path.exists() else None,
                generated_utc=generated,
            )
            public_calls = True
    report = build_crypto_proxy_observation_loop(
        feature_packet_path=args.feature_packet_path,
        settled_snapshot_path=settled_snapshot_path,
        observation_dir=args.observation_dir,
        label_dir=args.label_dir,
        generated_utc=generated,
        public_market_data_calls=public_calls,
    )
    if args.write:
        paths = write_crypto_proxy_observation_outputs(
            report,
            out_dir=args.out_dir,
            observation_dir=args.observation_dir,
            label_dir=args.label_dir,
        )
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
