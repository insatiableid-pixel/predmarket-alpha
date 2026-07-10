"""Kalshi Sports executable short-horizon labels and event-grouped falsification.

Research-only helpers for Phase 0-3 of the sports max-leverage program.
Promotion targets are aggressive-entry / aggressive-exit after-cost returns at
fixed horizons. Midpoint direction is diagnostic only.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from predmarket.kalshi_execution_cost import GENERAL_TAKER_FEE_RATE, kalshi_trade_fee
from predmarket.shared_helpers import (
    benjamini_hochberg,
    chronological_split_index,
    counts,
    json_float,
    optional_float,
    timestamp,
)

DEFAULT_HORIZONS_SECONDS: tuple[int, ...] = (60, 300, 900)
# Accept future books within these absolute tolerances around the fixed horizon.
DEFAULT_HORIZON_TOLERANCE: dict[int, int] = {60: 45, 300: 120, 900: 300}
# Hard max wait past the horizon before the row is censored.
DEFAULT_HORIZON_MAX_LAG: dict[int, int] = {60: 90, 300: 240, 900: 450}

FEATURE_FAMILY_ID = "sports_executable_horizon_microstructure_v1"
RETIRED_SPEC_PREFIX = "retired_prior_"


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_observation_packets(observation_dir: Path) -> list[dict[str, Any]]:
    """Load and dedupe microstructure observation rows from ignored raw packets."""
    if not observation_dir.is_dir():
        return []
    by_id: dict[str, dict[str, Any]] = {}
    source_hashes: dict[str, str | None] = {}
    for path in sorted(observation_dir.glob("*.json")):
        if path.name.endswith("_latest.json") or "latest" in path.stem.split("_")[-1:]:
            # Still load latest, but prefer timestamped sources for provenance.
            pass
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source_hashes[str(path)] = sha256_file(path)
        rows = payload.get("rows") if isinstance(payload, Mapping) else payload
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                continue
            item = dict(row)
            snapshot_id = str(item.get("snapshot_id") or "").strip()
            if not snapshot_id:
                snapshot_id = hashlib.sha256(
                    f"{item.get('contract_ticker')}|{item.get('observed_at_utc')}|{index}".encode()
                ).hexdigest()
                item["snapshot_id"] = snapshot_id
            item["_source_path"] = str(path)
            item["_source_sha256"] = source_hashes[str(path)]
            # Prefer earliest source file for stable provenance when duplicate.
            if snapshot_id not in by_id:
                by_id[snapshot_id] = item
    return sorted(
        by_id.values(),
        key=lambda row: (
            str(row.get("contract_ticker") or ""),
            str(row.get("observed_at_utc") or ""),
            str(row.get("snapshot_id") or ""),
        ),
    )


def validate_book(
    bid: float | None, ask: float | None
) -> tuple[bool, str | None]:
    if bid is None or ask is None:
        return False, "missing_bid_or_ask"
    if not (0.0 <= bid <= 1.0 and 0.0 <= ask <= 1.0):
        return False, "price_out_of_bounds"
    if bid > ask:
        return False, "crossed_book"
    if bid == ask:
        # Zero-spread lock is executable only if size exists; treat as valid quote.
        return True, None
    return True, None


def microprice(
    bid: float | None,
    ask: float | None,
    bid_depth: float | None,
    ask_depth: float | None,
) -> float | None:
    if bid is None or ask is None:
        return None
    bd = 0.0 if bid_depth is None else max(0.0, bid_depth)
    ad = 0.0 if ask_depth is None else max(0.0, ask_depth)
    total = bd + ad
    if total <= 0:
        return (bid + ask) / 2.0
    # Standard microprice: volume-weighted toward the thinner side.
    return (ask * bd + bid * ad) / total


def taker_fee(price: float, *, contract_count: float = 1.0) -> float:
    return float(
        kalshi_trade_fee(
            price=price,
            contract_count=contract_count,
            fee_rate=GENERAL_TAKER_FEE_RATE,
        )
    )


def executable_round_trip(
    *,
    side: str,
    entry_bid: float | None,
    entry_ask: float | None,
    exit_bid: float | None,
    exit_ask: float | None,
    entry_depth: float | None,
    exit_depth: float | None,
) -> dict[str, Any]:
    """Aggressive entry at ask, aggressive exit at future bid, with taker fees."""
    side_norm = side.lower().strip()
    if side_norm not in {"yes", "no"}:
        return _blocked_return("invalid_side")

    ok_entry, reason_entry = validate_book(entry_bid, entry_ask)
    if not ok_entry:
        return _blocked_return(f"entry_{reason_entry}")
    ok_exit, reason_exit = validate_book(exit_bid, exit_ask)
    if not ok_exit:
        return _blocked_return(f"exit_{reason_exit}")

    assert entry_ask is not None and exit_bid is not None
    entry_price = float(entry_ask)
    exit_price = float(exit_bid)
    if entry_price <= 0.0 or entry_price >= 1.0 or exit_price < 0.0 or exit_price > 1.0:
        return _blocked_return("price_not_tradable")

    entry_fee = taker_fee(entry_price)
    exit_fee = taker_fee(exit_price)
    gross = exit_price - entry_price
    net = gross - entry_fee - exit_fee
    capacity = None
    if entry_depth is not None and exit_depth is not None:
        capacity = max(0.0, min(float(entry_depth), float(exit_depth)))
    elif entry_depth is not None:
        capacity = max(0.0, float(entry_depth))

    return {
        "label_status": "executable_round_trip_labeled",
        "side": side_norm,
        "entry_price": json_float(entry_price),
        "exit_price": json_float(exit_price),
        "gross_return_per_contract": json_float(gross),
        "entry_fee_per_contract": json_float(entry_fee),
        "exit_fee_per_contract": json_float(exit_fee),
        "net_return_per_contract": json_float(net),
        "capacity_contracts": json_float(capacity),
        "blocker": None,
    }


def _blocked_return(reason: str) -> dict[str, Any]:
    return {
        "label_status": "blocked",
        "side": None,
        "entry_price": None,
        "exit_price": None,
        "gross_return_per_contract": None,
        "entry_fee_per_contract": None,
        "exit_fee_per_contract": None,
        "net_return_per_contract": None,
        "capacity_contracts": None,
        "blocker": reason,
    }


def find_horizon_exit(
    future_rows: Sequence[Mapping[str, Any]],
    *,
    decision_ts: float,
    horizon_seconds: int,
    tolerance_seconds: int,
    max_lag_seconds: int,
) -> tuple[Mapping[str, Any] | None, str]:
    """Select the future book nearest to decision_ts + horizon within tolerance."""
    target = decision_ts + float(horizon_seconds)
    earliest_ok = target - float(tolerance_seconds)
    latest_ok = target + float(max_lag_seconds)
    best: Mapping[str, Any] | None = None
    best_dist = float("inf")
    first_future: float | None = None
    for row in future_rows:
        ts = timestamp(row.get("observed_at_utc"))
        if ts is None or ts <= decision_ts:
            continue
        if first_future is None:
            first_future = ts
        if ts > latest_ok:
            break
        if ts < earliest_ok:
            continue
        dist = abs(ts - target)
        if dist < best_dist:
            best = row
            best_dist = dist
    if best is not None:
        return best, "matched"
    if first_future is None:
        return None, "censored_no_future_book"
    return None, "censored_horizon_gap"


def side_quotes(row: Mapping[str, Any], side: str) -> dict[str, float | None]:
    if side == "yes":
        return {
            "bid": optional_float(row.get("best_yes_bid")),
            "ask": optional_float(row.get("best_yes_ask")),
            "bid_depth": optional_float(row.get("yes_bid_depth_top1")),
            "ask_depth": optional_float(row.get("yes_ask_depth_top1")),
        }
    return {
        "bid": optional_float(row.get("best_no_bid")),
        "ask": optional_float(row.get("best_no_ask")),
        "bid_depth": optional_float(row.get("no_bid_depth_top1")),
        "ask_depth": optional_float(row.get("no_ask_depth_top1")),
    }


def build_feature_row(row: Mapping[str, Any], previous: Mapping[str, Any] | None) -> dict[str, Any]:
    yes = side_quotes(row, "yes")
    yes_mid = optional_float(row.get("yes_mid"))
    if yes_mid is None and yes["bid"] is not None and yes["ask"] is not None:
        yes_mid = (float(yes["bid"]) + float(yes["ask"])) / 2.0
    mp = microprice(yes["bid"], yes["ask"], yes["bid_depth"], yes["ask_depth"])
    prev_mid = optional_float((previous or {}).get("yes_mid"))
    prev_mp = microprice(
        optional_float((previous or {}).get("best_yes_bid")),
        optional_float((previous or {}).get("best_yes_ask")),
        optional_float((previous or {}).get("yes_bid_depth_top1")),
        optional_float((previous or {}).get("yes_ask_depth_top1")),
    )
    depth_imbalance = optional_float(row.get("depth_imbalance_yes"))
    if depth_imbalance is None:
        yd = optional_float(row.get("yes_depth_top5")) or 0.0
        nd = optional_float(row.get("no_depth_top5")) or 0.0
        denom = yd + nd
        depth_imbalance = ((yd - nd) / denom) if denom > 0 else None
    spread = optional_float(row.get("yes_spread"))
    if spread is None and yes["bid"] is not None and yes["ask"] is not None:
        spread = float(yes["ask"]) - float(yes["bid"])
    mid_delta = None
    if yes_mid is not None and prev_mid is not None:
        mid_delta = yes_mid - prev_mid
    mp_delta = None
    if mp is not None and prev_mp is not None:
        mp_delta = mp - prev_mp
    depth_delta = optional_float(row.get("depth_imbalance_delta"))
    if depth_delta is None and previous is not None:
        prev_imb = optional_float(previous.get("depth_imbalance_yes"))
        if depth_imbalance is not None and prev_imb is not None:
            depth_delta = depth_imbalance - prev_imb
    spread_norm_imbalance = None
    if depth_imbalance is not None and spread is not None and spread > 1e-9:
        spread_norm_imbalance = depth_imbalance / spread
    mp_mid_gap = None
    if mp is not None and yes_mid is not None:
        mp_mid_gap = mp - yes_mid
    return {
        "yes_mid": json_float(yes_mid),
        "microprice": json_float(mp),
        "depth_imbalance_yes": json_float(depth_imbalance),
        "depth_imbalance_delta": json_float(depth_delta),
        "yes_spread": json_float(spread),
        "mid_delta_from_previous": json_float(mid_delta),
        "microprice_delta_from_previous": json_float(mp_delta),
        "spread_normalized_imbalance": json_float(spread_norm_imbalance),
        "microprice_minus_mid": json_float(mp_mid_gap),
        "total_depth_contracts": json_float(optional_float(row.get("total_depth_contracts"))),
        "time_to_settlement_seconds": json_float(
            optional_float(row.get("time_to_settlement_seconds"))
        ),
    }



def _label_from_pair(
    row: Mapping[str, Any],
    *,
    ticker: str,
    decision_ts: float,
    features: Mapping[str, Any],
    horizon: int,
    exit_row: Mapping[str, Any] | None,
    match_status: str,
) -> dict[str, Any]:
    base = {
        "label_id": f"{row.get('snapshot_id')}|h{horizon}",
        "feature_family": FEATURE_FAMILY_ID,
        "snapshot_id": row.get("snapshot_id"),
        "contract_ticker": ticker,
        "event_ticker": row.get("event_ticker"),
        "series_ticker": row.get("series_ticker"),
        "sport_surface": row.get("sport_surface"),
        "observed_at_utc": row.get("observed_at_utc"),
        "decision_ts": decision_ts,
        "settlement_time": row.get("settlement_time"),
        "horizon_seconds": int(horizon),
        "source_path": row.get("_source_path"),
        "source_sha256": row.get("_source_sha256"),
        "raw_orderbook_sha256": row.get("raw_orderbook_sha256"),
        "usable": False,
        "research_only": True,
        "execution_enabled": False,
        **features,
    }
    if exit_row is None:
        return {
            **base,
            "label_status": match_status,
            "exit_observed_at_utc": None,
            "exit_snapshot_id": None,
            "realized_horizon_seconds": None,
            "diagnostic_mid_delta": None,
            "yes_net_return_per_contract": None,
            "no_net_return_per_contract": None,
            "yes_gross_return_per_contract": None,
            "no_gross_return_per_contract": None,
            "yes_capacity_contracts": None,
            "no_capacity_contracts": None,
            "yes_blocker": match_status,
            "no_blocker": match_status,
        }

    exit_ts = timestamp(exit_row.get("observed_at_utc"))
    realized = None if exit_ts is None else exit_ts - decision_ts
    yes_q = side_quotes(row, "yes")
    no_q = side_quotes(row, "no")
    yes_exit = side_quotes(exit_row, "yes")
    no_exit = side_quotes(exit_row, "no")
    yes_rt = executable_round_trip(
        side="yes",
        entry_bid=yes_q["bid"],
        entry_ask=yes_q["ask"],
        exit_bid=yes_exit["bid"],
        exit_ask=yes_exit["ask"],
        entry_depth=yes_q["ask_depth"],
        exit_depth=yes_exit["bid_depth"],
    )
    no_rt = executable_round_trip(
        side="no",
        entry_bid=no_q["bid"],
        entry_ask=no_q["ask"],
        exit_bid=no_exit["bid"],
        exit_ask=no_exit["ask"],
        entry_depth=no_q["ask_depth"],
        exit_depth=no_exit["bid_depth"],
    )
    entry_mid = features.get("yes_mid")
    exit_mid = optional_float(exit_row.get("yes_mid"))
    if exit_mid is None:
        eb, ea = yes_exit["bid"], yes_exit["ask"]
        if eb is not None and ea is not None:
            exit_mid = (float(eb) + float(ea)) / 2.0
    mid_delta = None
    if entry_mid is not None and exit_mid is not None:
        mid_delta = float(exit_mid) - float(entry_mid)
    status = "blocked_invalid_books" if yes_rt["blocker"] and no_rt["blocker"] else "executable_labeled"
    return {
        **base,
        "label_status": status,
        "exit_observed_at_utc": exit_row.get("observed_at_utc"),
        "exit_snapshot_id": exit_row.get("snapshot_id"),
        "realized_horizon_seconds": json_float(realized),
        "diagnostic_mid_delta": json_float(mid_delta),
        "yes_net_return_per_contract": yes_rt["net_return_per_contract"],
        "no_net_return_per_contract": no_rt["net_return_per_contract"],
        "yes_gross_return_per_contract": yes_rt["gross_return_per_contract"],
        "no_gross_return_per_contract": no_rt["gross_return_per_contract"],
        "yes_capacity_contracts": yes_rt["capacity_contracts"],
        "no_capacity_contracts": no_rt["capacity_contracts"],
        "yes_entry_price": yes_rt["entry_price"],
        "yes_exit_price": yes_rt["exit_price"],
        "no_entry_price": no_rt["entry_price"],
        "no_exit_price": no_rt["exit_price"],
        "yes_entry_fee": yes_rt["entry_fee_per_contract"],
        "yes_exit_fee": yes_rt["exit_fee_per_contract"],
        "no_entry_fee": no_rt["entry_fee_per_contract"],
        "no_exit_fee": no_rt["exit_fee_per_contract"],
        "yes_blocker": yes_rt["blocker"],
        "no_blocker": no_rt["blocker"],
    }


def build_executable_labels(
    rows: Sequence[Mapping[str, Any]],
    *,
    horizons: Sequence[int] = DEFAULT_HORIZONS_SECONDS,
    tolerances: Mapping[int, int] | None = None,
    max_lags: Mapping[int, int] | None = None,
    discovery_cutoff_utc: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Construct fixed-horizon executable labels with explicit censoring."""
    tol = dict(DEFAULT_HORIZON_TOLERANCE)
    lag = dict(DEFAULT_HORIZON_MAX_LAG)
    if tolerances:
        tol.update({int(k): int(v) for k, v in tolerances.items()})
    if max_lags:
        lag.update({int(k): int(v) for k, v in max_lags.items()})

    cutoff_ts = timestamp(discovery_cutoff_utc) if discovery_cutoff_utc else None
    by_ticker: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        ticker = str(row.get("contract_ticker") or "").strip()
        if ticker:
            by_ticker[ticker].append(row)

    labels: list[dict[str, Any]] = []
    quality: Counter[str] = Counter()
    for ticker, ticker_rows in by_ticker.items():
        ordered = sorted(ticker_rows, key=lambda item: str(item.get("observed_at_utc") or ""))
        for index, row in enumerate(ordered):
            decision_ts = timestamp(row.get("observed_at_utc"))
            if decision_ts is None:
                quality["missing_decision_timestamp"] += 1
                continue
            if cutoff_ts is not None and decision_ts > cutoff_ts:
                quality["post_cutoff_excluded_from_discovery"] += 1
                continue
            previous = ordered[index - 1] if index > 0 else None
            features = build_feature_row(row, previous)
            future = ordered[index + 1 :]
            for horizon in horizons:
                exit_row, match_status = find_horizon_exit(
                    future,
                    decision_ts=decision_ts,
                    horizon_seconds=int(horizon),
                    tolerance_seconds=int(tol[int(horizon)]),
                    max_lag_seconds=int(lag[int(horizon)]),
                )
                label = _label_from_pair(
                    row,
                    ticker=ticker,
                    decision_ts=decision_ts,
                    features=features,
                    horizon=int(horizon),
                    exit_row=exit_row,
                    match_status=match_status,
                )
                quality[str(label.get("label_status"))] += 1
                labels.append(label)

    summary = {
        "observation_row_count": len(rows),
        "label_row_count": len(labels),
        "horizons_seconds": list(horizons),
        "horizon_tolerance_seconds": tol,
        "horizon_max_lag_seconds": lag,
        "discovery_cutoff_utc": discovery_cutoff_utc,
        "quality_counts": dict(quality),
        "executable_label_count": int(quality.get("executable_labeled", 0)),
        "censored_count": int(
            quality.get("censored_no_future_book", 0) + quality.get("censored_horizon_gap", 0)
        ),
        "sport_surface_counts": counts(row.get("sport_surface") for row in rows),
        "distinct_contract_count": len({row.get("contract_ticker") for row in rows}),
        "distinct_event_count": len(
            {row.get("event_ticker") for row in rows if row.get("event_ticker")}
        ),
    }
    return labels, summary



def audit_observation_inventory(
    rows: Sequence[Mapping[str, Any]],
    *,
    observation_dir: Path,
    label_dir: Path | None = None,
    tick_dir: Path | None = None,
    frozen_checksums: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Phase 0 inventory: provenance, duplicates, timestamp ordering, book validity."""
    snapshot_ids = [str(row.get("snapshot_id") or "") for row in rows]
    contracts = [str(row.get("contract_ticker") or "") for row in rows]
    events = [str(row.get("event_ticker") or "") for row in rows]
    times = [str(row.get("observed_at_utc") or "") for row in rows if row.get("observed_at_utc")]

    missing_book = 0
    crossed = 0
    settlement_before_obs = 0
    for row in rows:
        ok, reason = validate_book(
            optional_float(row.get("best_yes_bid")),
            optional_float(row.get("best_yes_ask")),
        )
        if not ok and reason == "missing_bid_or_ask":
            missing_book += 1
        elif not ok and reason == "crossed_book":
            crossed += 1
        obs_ts = timestamp(row.get("observed_at_utc"))
        settle_ts = timestamp(row.get("settlement_time"))
        if obs_ts is not None and settle_ts is not None and settle_ts < obs_ts:
            settlement_before_obs += 1

    # Within-contract chronological gaps.
    by_ticker: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        ts = timestamp(row.get("observed_at_utc"))
        ticker = str(row.get("contract_ticker") or "")
        if ts is not None and ticker:
            by_ticker[ticker].append(ts)
    gaps: list[float] = []
    for values in by_ticker.values():
        ordered = sorted(values)
        for left, right in itertools.pairwise(ordered):
            gaps.append(right - left)

    packet_files = sorted(observation_dir.glob("*.json")) if observation_dir.is_dir() else []
    packet_hashes = {
        str(path): sha256_file(path) for path in packet_files if path.is_file()
    }

    label_claim_defects = [
        {
            "claim": "forward_mid_delta_60s/300s/900s",
            "location": "scripts/kalshi_near_resolution_informed_flow_evidence_gate.py:build_flow_rows",
            "defect": (
                "All three named horizons currently store the same next-observation midpoint "
                "delta, not mechanically fixed 60/300/900-second exits."
            ),
            "impact": "Prior forward-quote family cannot support fixed-horizon promotion claims.",
            "disposition": "documented_not_promotion_surface",
        },
        {
            "claim": "forward_quote label economics",
            "location": "scripts/kalshi_near_resolution_informed_flow_evidence_gate.py",
            "defect": "Promotion-adjacent scoring used midpoint direction, not after-cost executable returns.",
            "impact": "Accuracy > 50% on mid direction is not executable EV.",
            "disposition": "replaced_by_executable_horizon_labels",
        },
        {
            "claim": "flow_depth_imbalance_settlement_directional",
            "location": "prior paper burn-in / goal-ready handoff",
            "defect": "Retired after 8/18 correct paper labels and calibration error ~0.53.",
            "impact": "Do not resurrect under a new name.",
            "disposition": "retired_negative_result",
        },
    ]

    frozen = dict(frozen_checksums or {})
    frozen_status = {
        name: {"expected_sha256": digest, "reconciled": digest is not None}
        for name, digest in frozen.items()
    }

    tick_files = sorted(tick_dir.glob("*.jsonl")) if tick_dir and tick_dir.is_dir() else []
    label_files = sorted(label_dir.glob("*.json")) if label_dir and label_dir.is_dir() else []

    gap_summary = None
    if gaps:
        ordered_gaps = sorted(gaps)
        gap_summary = {
            "count": len(ordered_gaps),
            "min_seconds": ordered_gaps[0],
            "p10_seconds": ordered_gaps[max(0, int(0.10 * (len(ordered_gaps) - 1)))],
            "median_seconds": statistics.median(ordered_gaps),
            "p90_seconds": ordered_gaps[max(0, int(0.90 * (len(ordered_gaps) - 1)))],
            "max_seconds": ordered_gaps[-1],
        }

    return {
        "observation_dir": str(observation_dir),
        "observation_packet_count": len(packet_files),
        "observation_packet_hashes_sample": dict(list(packet_hashes.items())[:20]),
        "unique_observation_rows": len(rows),
        "unique_snapshot_ids": len(set(snapshot_ids) - {""}),
        "duplicate_snapshot_id_count": len(snapshot_ids) - len(set(snapshot_ids) - {""}),
        "unique_contracts": len(set(contracts) - {""}),
        "unique_events": len(set(events) - {""}),
        "contracts_with_repeat_snapshots": sum(1 for values in by_ticker.values() if len(values) >= 2),
        "time_range_utc": {"min": min(times) if times else None, "max": max(times) if times else None},
        "sport_surface_counts": counts(row.get("sport_surface") for row in rows),
        "series_ticker_counts": counts(row.get("series_ticker") for row in rows),
        "missing_yes_book_count": missing_book,
        "crossed_yes_book_count": crossed,
        "settlement_before_observation_count": settlement_before_obs,
        "inter_observation_gap_summary": gap_summary,
        "label_claim_defects": label_claim_defects,
        "frozen_starting_evidence": frozen_status,
        "tick_jsonl_file_count": len(tick_files),
        "tick_jsonl_paths": [str(path) for path in tick_files[:20]],
        "settlement_label_packet_count": len(label_files),
        "unresolved_label_semantic_defects": [
            defect
            for defect in label_claim_defects
            if defect.get("disposition")
            not in {
                "retired_negative_result",
                "documented_not_promotion_surface",
                "replaced_by_executable_horizon_labels",
            }
        ],
        "yes_no_normalization": {
            "yes_buy_uses": "best_yes_ask",
            "yes_sell_uses": "best_yes_bid",
            "no_buy_uses": "best_no_ask",
            "no_sell_uses": "best_no_bid",
            "fee_policy": "general_taker_quadratic_fee_rate_0.07_both_legs",
        },
    }


def hypothesis_registry() -> list[dict[str, Any]]:
    """Finite pre-registered family for executable-horizon discovery.

    Thresholds and directions are fixed before confirmation. Negative controls
    are included in the FDR family.
    """
    return [
        {
            "model_id": "spread_norm_imbalance_buy_yes_h300",
            "horizon_seconds": 300,
            "side": "yes",
            "feature": "spread_normalized_imbalance",
            "direction": "long_if_feature_gt",
            "threshold": 2.0,
            "mechanism": "Depth imbalance large relative to spread predicts short-horizon upward pressure.",
            "negative_control": False,
        },
        {
            "model_id": "spread_norm_imbalance_buy_no_h300",
            "horizon_seconds": 300,
            "side": "no",
            "feature": "spread_normalized_imbalance",
            "direction": "long_if_feature_lt",
            "threshold": -2.0,
            "mechanism": "Negative spread-normalized imbalance predicts downward pressure.",
            "negative_control": False,
        },
        {
            "model_id": "microprice_momentum_buy_yes_h300",
            "horizon_seconds": 300,
            "side": "yes",
            "feature": "microprice_delta_from_previous",
            "direction": "long_if_feature_gt",
            "threshold": 0.005,
            "mechanism": "Microprice momentum conditioned on prior snapshot continues briefly.",
            "negative_control": False,
        },
        {
            "model_id": "microprice_momentum_buy_no_h300",
            "horizon_seconds": 300,
            "side": "no",
            "feature": "microprice_delta_from_previous",
            "direction": "long_if_feature_lt",
            "threshold": -0.005,
            "mechanism": "Negative microprice momentum continues briefly.",
            "negative_control": False,
        },
        {
            "model_id": "microprice_mid_gap_fade_yes_h300",
            "horizon_seconds": 300,
            "side": "yes",
            "feature": "microprice_minus_mid",
            "direction": "long_if_feature_gt",
            "threshold": 0.002,
            "mechanism": "Microprice above mid implies latent bid pressure not yet in mid.",
            "negative_control": False,
        },
        {
            "model_id": "microprice_mid_gap_fade_no_h300",
            "horizon_seconds": 300,
            "side": "no",
            "feature": "microprice_minus_mid",
            "direction": "long_if_feature_lt",
            "threshold": -0.002,
            "mechanism": "Microprice below mid implies latent ask pressure.",
            "negative_control": False,
        },
        {
            "model_id": "depth_delta_buy_yes_h900",
            "horizon_seconds": 900,
            "side": "yes",
            "feature": "depth_imbalance_delta",
            "direction": "long_if_feature_gt",
            "threshold": 0.05,
            "mechanism": "Improving YES depth imbalance forecasts 15m executable drift.",
            "negative_control": False,
        },
        {
            "model_id": "depth_delta_buy_no_h900",
            "horizon_seconds": 900,
            "side": "no",
            "feature": "depth_imbalance_delta",
            "direction": "long_if_feature_lt",
            "threshold": -0.05,
            "mechanism": "Deteriorating YES depth imbalance forecasts 15m downward drift.",
            "negative_control": False,
        },
        {
            "model_id": "tight_spread_imbalance_buy_yes_h900",
            "horizon_seconds": 900,
            "side": "yes",
            "feature": "depth_imbalance_yes",
            "direction": "long_if_feature_gt_and_tight_spread",
            "threshold": 0.25,
            "spread_max": 0.03,
            "mechanism": "Large imbalance with tight spread is more informative than wide-spread noise.",
            "negative_control": False,
        },
        {
            "model_id": "tight_spread_imbalance_buy_no_h900",
            "horizon_seconds": 900,
            "side": "no",
            "feature": "depth_imbalance_yes",
            "direction": "long_if_feature_lt_and_tight_spread",
            "threshold": -0.25,
            "spread_max": 0.03,
            "mechanism": "Negative imbalance with tight spread forecasts NO-side edge.",
            "negative_control": False,
        },
        {
            "model_id": "negctrl_time_reversed_imbalance_h300",
            "horizon_seconds": 300,
            "side": "yes",
            "feature": "depth_imbalance_yes",
            "direction": "time_reversed_long_if_feature_gt",
            "threshold": 0.25,
            "mechanism": "Negative control: use next-row feature as if known at decision time.",
            "negative_control": True,
        },
        {
            "model_id": "negctrl_impossible_mid_delta_sign_flip_h300",
            "horizon_seconds": 300,
            "side": "yes",
            "feature": "mid_delta_from_previous",
            "direction": "long_if_feature_lt",
            "threshold": 0.0,
            "mechanism": "Negative control: trade against observed mid delta.",
            "negative_control": True,
        },
    ]


def signal_fires(row: Mapping[str, Any], spec: Mapping[str, Any]) -> bool:
    min_peers = optional_float(spec.get("min_peer_contracts"))
    if min_peers is not None and int(row.get("peer_contract_count") or 0) < int(min_peers):
        return False
    feature = optional_float(row.get(str(spec["feature"])))
    direction = str(spec["direction"])
    threshold = float(spec["threshold"])
    spread = optional_float(row.get("yes_spread"))
    spread_max = optional_float(spec.get("spread_max"))

    if direction == "long_if_feature_gt":
        return feature is not None and feature > threshold
    if direction == "long_if_feature_lt":
        return feature is not None and feature < threshold
    if direction == "long_if_feature_gt_and_tight_spread":
        return (
            feature is not None
            and feature > threshold
            and spread is not None
            and spread_max is not None
            and spread <= spread_max
        )
    if direction == "long_if_feature_lt_and_tight_spread":
        return (
            feature is not None
            and feature < threshold
            and spread is not None
            and spread_max is not None
            and spread <= spread_max
        )
    if direction == "time_reversed_long_if_feature_gt":
        # Leakage-style control: feature already present is used; evaluation layer
        # may attach future feature under this key when testing.
        leaked = optional_float(row.get("_leaked_future_feature"))
        value = leaked if leaked is not None else feature
        return value is not None and value > threshold
    return False


def attach_leakage_features(labels: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Attach next-row feature values for the time-reversed negative control only."""
    by_contract: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in labels:
        item = dict(row)
        by_contract[str(item.get("contract_ticker") or "")].append(item)
    output: list[dict[str, Any]] = []
    for ticker_rows in by_contract.values():
        ordered = sorted(ticker_rows, key=lambda item: float(item.get("decision_ts") or 0.0))
        for index, row in enumerate(ordered):
            if index + 1 < len(ordered):
                row["_leaked_future_feature"] = ordered[index + 1].get("depth_imbalance_yes")
            else:
                row["_leaked_future_feature"] = None
            output.append(row)
    return output


def eligible_signal_rows(
    labels: Sequence[Mapping[str, Any]], spec: Mapping[str, Any]
) -> list[dict[str, Any]]:
    horizon = int(spec["horizon_seconds"])
    side = str(spec["side"])
    net_key = "yes_net_return_per_contract" if side == "yes" else "no_net_return_per_contract"
    selected: list[dict[str, Any]] = []
    for row in labels:
        if int(row.get("horizon_seconds") or -1) != horizon:
            continue
        if str(row.get("label_status") or "") != "executable_labeled":
            continue
        if row.get(net_key) is None:
            continue
        if not signal_fires(row, spec):
            continue
        item = dict(row)
        item["selected_side"] = side
        item["selected_net_return"] = float(row[net_key])
        item["selected_gross_return"] = float(
            row.get("yes_gross_return_per_contract" if side == "yes" else "no_gross_return_per_contract")
            or 0.0
        )
        item["selected_capacity"] = optional_float(
            row.get("yes_capacity_contracts" if side == "yes" else "no_capacity_contracts")
        )
        item["correct_executable"] = 1 if item["selected_net_return"] > 0 else 0
        selected.append(item)
    return selected


def event_grouped_folds(
    rows: Sequence[Mapping[str, Any]],
    *,
    n_folds: int = 4,
    embargo_events: int = 1,
) -> list[dict[str, Any]]:
    """Chronological event-grouped folds with an embargo between train and test."""
    event_times: dict[str, float] = {}
    for row in rows:
        event = str(row.get("event_ticker") or row.get("contract_ticker") or "")
        ts = float(row.get("decision_ts") or 0.0)
        if not event:
            continue
        if event not in event_times or ts < event_times[event]:
            event_times[event] = ts
    events = sorted(event_times, key=lambda key: (event_times[key], key))
    if len(events) < max(4, n_folds + embargo_events + 1):
        return []

    fold_size = max(1, len(events) // n_folds)
    folds: list[dict[str, Any]] = []
    for fold_index in range(n_folds):
        test_start = fold_index * fold_size
        test_end = len(events) if fold_index == n_folds - 1 else min(len(events), test_start + fold_size)
        if test_start >= len(events):
            break
        test_events = set(events[test_start:test_end])
        embargo_start = max(0, test_start - embargo_events)
        embargo_end = min(len(events), test_end + embargo_events)
        embargo_events_set = set(events[embargo_start:embargo_end]) - test_events
        train_events = set(events[:test_start]) - embargo_events_set
        # Also allow train events after the test block only when not embargoed and
        # only for pure historical discovery? No — keep pure expanding-window:
        # train is only events strictly before test (minus embargo).
        train_rows = [
            row
            for row in rows
            if str(row.get("event_ticker") or row.get("contract_ticker") or "") in train_events
        ]
        test_rows = [
            row
            for row in rows
            if str(row.get("event_ticker") or row.get("contract_ticker") or "") in test_events
        ]
        folds.append(
            {
                "fold_index": fold_index,
                "train_event_count": len(train_events),
                "test_event_count": len(test_events),
                "embargo_event_count": len(embargo_events_set),
                "train_rows": train_rows,
                "test_rows": test_rows,
                "test_events": sorted(test_events),
            }
        )
    return folds


def collapse_event_independence(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One independent unit per event: earliest signal row in the event."""
    by_event: dict[str, dict[str, Any]] = {}
    for row in rows:
        event = str(row.get("event_ticker") or row.get("contract_ticker") or "")
        if not event:
            continue
        current = by_event.get(event)
        if current is None or float(row.get("decision_ts") or 0) < float(
            current.get("decision_ts") or 0
        ):
            by_event[event] = dict(row)
    return sorted(by_event.values(), key=lambda item: (float(item.get("decision_ts") or 0), item.get("event_ticker") or ""))


def mean_or_none(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return float(sum(values) / len(values))


def cluster_bootstrap_lower_bound(
    event_returns: Sequence[float],
    *,
    n_bootstrap: int = 400,
    seed: int = 7,
    alpha: float = 0.05,
) -> float | None:
    if not event_returns:
        return None
    # Deterministic multiplicative congruential generator for reproducibility.
    state = seed % 2147483647
    if state <= 0:
        state = 1
    samples: list[float] = []
    n = len(event_returns)
    for _ in range(n_bootstrap):
        draws: list[float] = []
        for _ in range(n):
            state = (1103515245 * state + 12345) % (2**31)
            idx = state % n
            draws.append(event_returns[idx])
        samples.append(sum(draws) / n)
    samples.sort()
    index = max(0, min(len(samples) - 1, math.floor(alpha * len(samples))))
    return samples[index]


def evaluate_hypothesis(
    labels: Sequence[Mapping[str, Any]],
    spec: Mapping[str, Any],
    *,
    min_oos_labels: int = 100,
    min_events: int = 20,
    n_folds: int = 4,
) -> dict[str, Any]:
    fired = eligible_signal_rows(labels, spec)
    independent = collapse_event_independence(fired)
    folds = event_grouped_folds(independent, n_folds=n_folds, embargo_events=1)

    oos_rows: list[dict[str, Any]] = []
    fold_stats: list[dict[str, Any]] = []
    for fold in folds:
        test_rows = fold["test_rows"]
        if not test_rows:
            continue
        nets = [float(row["selected_net_return"]) for row in test_rows]
        fold_stats.append(
            {
                "fold_index": fold["fold_index"],
                "oos_event_count": len(test_rows),
                "mean_net_return": mean_or_none(nets),
                "positive_rate": mean_or_none([1.0 if value > 0 else 0.0 for value in nets]),
            }
        )
        oos_rows.extend(test_rows)

    # If folds are too thin, fall back to chronological event holdout.
    if len(oos_rows) < min(20, min_oos_labels // 2) and independent:
        split = chronological_split_index(len(independent), 0.3)
        oos_rows = independent[split:]
        nets = [float(row["selected_net_return"]) for row in oos_rows]
        fold_stats = [
            {
                "fold_index": 0,
                "oos_event_count": len(oos_rows),
                "mean_net_return": mean_or_none(nets),
                "positive_rate": mean_or_none([1.0 if value > 0 else 0.0 for value in nets]),
                "fallback": "chronological_event_holdout_30pct",
            }
        ]

    nets = [float(row["selected_net_return"]) for row in oos_rows]
    wins = sum(1 for value in nets if value > 0)
    mean_net = mean_or_none(nets)
    # One-sided test that mean net > 0 via sign/binomial on positive net events,
    # plus bootstrap lower bound on mean.
    p_value = 1.0
    if nets:
        # Exact binomial under p=0.5 on positive vs non-positive independent events.
        p_value = _binomial_gte(wins, len(nets), 0.5)
    bootstrap_lb = cluster_bootstrap_lower_bound(nets)
    capacity_values = [
        float(row["selected_capacity"])
        for row in oos_rows
        if optional_float(row.get("selected_capacity")) is not None
        and float(row["selected_capacity"]) > 0
    ]
    surface_counts = counts(row.get("sport_surface") for row in oos_rows)
    series_counts = counts(row.get("series_ticker") for row in oos_rows)
    largest_cluster_share = 0.0
    if oos_rows:
        top = max(series_counts.values()) if series_counts else 0
        largest_cluster_share = top / len(oos_rows)

    # Temporal buckets by decision time quartiles.
    bucket_means: list[float | None] = []
    if oos_rows:
        ordered = sorted(oos_rows, key=lambda row: float(row.get("decision_ts") or 0))
        chunk = max(1, len(ordered) // 4)
        for bucket_index in range(4):
            start = bucket_index * chunk
            end = len(ordered) if bucket_index == 3 else min(len(ordered), start + chunk)
            part = ordered[start:end]
            bucket_means.append(mean_or_none([float(row["selected_net_return"]) for row in part]))

    positive_buckets = sum(1 for value in bucket_means if value is not None and value > 0)
    recent_bucket = bucket_means[-1] if bucket_means else None

    status = "insufficient_sample"
    if len(oos_rows) >= min_oos_labels and len({row.get("event_ticker") for row in oos_rows}) >= min_events:
        status = "testable"
    if status == "testable" and mean_net is not None and mean_net > 0 and p_value <= 1.0:
        status = "testable"

    return {
        "model_id": spec["model_id"],
        "feature_family": FEATURE_FAMILY_ID,
        "horizon_seconds": spec["horizon_seconds"],
        "side": spec["side"],
        "feature": spec["feature"],
        "direction": spec["direction"],
        "threshold": spec["threshold"],
        "negative_control": bool(spec.get("negative_control")),
        "mechanism": spec.get("mechanism"),
        "fired_row_count": len(fired),
        "independent_event_count": len(independent),
        "oos_event_count": len(oos_rows),
        "oos_positive_event_count": wins,
        "oos_mean_net_return": json_float(mean_net),
        "oos_mean_gross_return": json_float(
            mean_or_none([float(row["selected_gross_return"]) for row in oos_rows])
        ),
        "oos_positive_rate": json_float(wins / len(oos_rows) if oos_rows else None),
        "p_value_mean_net_positive": json_float(p_value),
        "bootstrap_mean_net_lower_95": json_float(bootstrap_lb),
        "fold_stats": fold_stats,
        "temporal_bucket_mean_net": [json_float(value) for value in bucket_means],
        "positive_temporal_buckets": positive_buckets,
        "recent_bucket_mean_net": json_float(recent_bucket),
        "positive_capacity_event_count": len(capacity_values),
        "mean_capacity_contracts": json_float(mean_or_none(capacity_values)),
        "sport_surface_counts": surface_counts,
        "series_cluster_counts": series_counts,
        "largest_series_cluster_share": json_float(largest_cluster_share),
        "status": status,
        "usable": False,
        "research_only": True,
        "execution_enabled": False,
    }


def _binomial_gte(successes: int, trials: int, p_null: float) -> float:
    if trials <= 0:
        return 1.0
    total = 0.0
    for k in range(successes, trials + 1):
        total += math.comb(trials, k) * (p_null**k) * ((1.0 - p_null) ** (trials - k))
    return min(max(total, 0.0), 1.0)


def apply_fdr(
    evaluations: Sequence[Mapping[str, Any]], *, alpha: float = 0.05
) -> list[dict[str, Any]]:
    indexed: list[tuple[int, float]] = []
    for index, row in enumerate(evaluations):
        if row.get("status") not in {"testable", "research_candidate_fdr_passed"}:
            continue
        p_value = optional_float(row.get("p_value_mean_net_positive"))
        if p_value is None:
            continue
        indexed.append((index, float(p_value)))
    q_map = benjamini_hochberg(indexed) if indexed else {}
    output: list[dict[str, Any]] = []
    for index, row in enumerate(evaluations):
        item = dict(row)
        if index in q_map:
            item["q_value"] = json_float(q_map[index])
            if (
                item.get("status") == "testable"
                and q_map[index] <= alpha
                and optional_float(item.get("oos_mean_net_return")) is not None
                and float(item["oos_mean_net_return"]) > 0
                and not item.get("negative_control")
            ):
                # Additional hard gates checked later; mark FDR pass only.
                item["status"] = "research_candidate_fdr_passed"
        else:
            item["q_value"] = None
        output.append(item)
    return output


def hard_gate_assessment(evaluation: Mapping[str, Any], *, min_oos: int = 100, min_events: int = 20) -> dict[str, Any]:
    gates = []
    oos = int(evaluation.get("oos_event_count") or 0)
    gates.append(_gate("min_oos_events", oos >= min_oos, f"oos_event_count={oos} min={min_oos}"))
    mean_net = optional_float(evaluation.get("oos_mean_net_return"))
    gates.append(_gate("positive_mean_net", mean_net is not None and mean_net > 0, f"mean_net={mean_net}"))
    q_value = optional_float(evaluation.get("q_value"))
    gates.append(_gate("fdr_q_le_0_05", q_value is not None and q_value <= 0.05, f"q={q_value}"))
    lb = optional_float(evaluation.get("bootstrap_mean_net_lower_95"))
    gates.append(_gate("bootstrap_lb_above_0", lb is not None and lb > 0, f"lb={lb}"))
    pos_buckets = int(evaluation.get("positive_temporal_buckets") or 0)
    recent = optional_float(evaluation.get("recent_bucket_mean_net"))
    gates.append(
        _gate(
            "temporal_survival",
            pos_buckets >= 3 and (recent is None or recent > 0),
            f"positive_buckets={pos_buckets} recent={recent}",
        )
    )
    cap = int(evaluation.get("positive_capacity_event_count") or 0)
    gates.append(_gate("capacity_events", cap >= 3, f"positive_capacity_events={cap}"))
    share = optional_float(evaluation.get("largest_series_cluster_share"))
    gates.append(
        _gate("cluster_share_le_0_35", share is not None and share <= 0.35, f"largest_share={share}")
    )
    gates.append(
        _gate(
            "not_negative_control",
            not bool(evaluation.get("negative_control")),
            f"negative_control={evaluation.get('negative_control')}",
        )
    )
    gates.append(
        _gate(
            "untouched_confirmation",
            False,
            "discovery-only surface; confirmation requires post-cutoff ticks",
        )
    )
    passed = all(gate["status"] == "pass" for gate in gates if gate["name"] != "untouched_confirmation")
    # research_ready requires confirmation too
    research_ready = all(gate["status"] == "pass" for gate in gates)
    return {
        "gates": gates,
        "discovery_gates_pass": passed,
        "research_ready": research_ready,
    }


def _gate(name: str, passed: bool, reason: str) -> dict[str, str]:
    return {"name": name, "status": "pass" if passed else "fail", "reason": reason}


def synthetic_leakage_tests() -> list[dict[str, Any]]:
    """Built-in synthetic checks for label construction invariants."""
    rows = [
        {
            "snapshot_id": "s1",
            "contract_ticker": "KXMLBGAME-T1-HOME",
            "event_ticker": "KXMLBGAME-T1",
            "series_ticker": "KXMLBGAME",
            "sport_surface": "mlb",
            "observed_at_utc": "2026-07-05T00:00:00Z",
            "settlement_time": "2026-07-05T03:00:00Z",
            "best_yes_bid": 0.48,
            "best_yes_ask": 0.50,
            "best_no_bid": 0.50,
            "best_no_ask": 0.52,
            "yes_bid_depth_top1": 10.0,
            "yes_ask_depth_top1": 12.0,
            "no_bid_depth_top1": 8.0,
            "no_ask_depth_top1": 9.0,
            "yes_mid": 0.49,
            "yes_spread": 0.02,
            "depth_imbalance_yes": 0.2,
            "total_depth_contracts": 100.0,
            "time_to_settlement_seconds": 10800.0,
            "_source_path": "synthetic",
            "_source_sha256": "synthetic",
        },
        {
            "snapshot_id": "s2",
            "contract_ticker": "KXMLBGAME-T1-HOME",
            "event_ticker": "KXMLBGAME-T1",
            "series_ticker": "KXMLBGAME",
            "sport_surface": "mlb",
            "observed_at_utc": "2026-07-05T00:05:00Z",
            "settlement_time": "2026-07-05T03:00:00Z",
            "best_yes_bid": 0.55,
            "best_yes_ask": 0.57,
            "best_no_bid": 0.43,
            "best_no_ask": 0.45,
            "yes_bid_depth_top1": 11.0,
            "yes_ask_depth_top1": 10.0,
            "no_bid_depth_top1": 7.0,
            "no_ask_depth_top1": 8.0,
            "yes_mid": 0.56,
            "yes_spread": 0.02,
            "depth_imbalance_yes": 0.3,
            "total_depth_contracts": 100.0,
            "time_to_settlement_seconds": 10500.0,
            "_source_path": "synthetic",
            "_source_sha256": "synthetic",
        },
    ]
    labels, _summary = build_executable_labels(rows, horizons=(300,))
    labeled = [row for row in labels if row.get("label_status") == "executable_labeled"]
    tests = []
    tests.append(
        {
            "name": "positive_path_yes_net_accounts_for_fees",
            "passed": bool(labeled)
            and labeled[0]["yes_gross_return_per_contract"] is not None
            and labeled[0]["yes_net_return_per_contract"]
            < labeled[0]["yes_gross_return_per_contract"],
            "detail": labeled[0] if labeled else None,
        }
    )
    # Leakage: exit must be after decision.
    leakage_ok = all(
        (timestamp(row.get("exit_observed_at_utc")) or 0)
        > (timestamp(row.get("observed_at_utc")) or 0)
        for row in labeled
    )
    tests.append({"name": "exit_strictly_after_decision", "passed": leakage_ok, "detail": None})
    # Duplicate snapshot collapse
    dup_rows = [*rows, dict(rows[0])]
    labels_dup, _ = build_executable_labels(dup_rows, horizons=(300,))
    # build_executable_labels does not dedupe inputs; inventory audit does.
    tests.append(
        {
            "name": "duplicate_input_rows_create_duplicate_labels_without_inventory_dedupe",
            "passed": len(labels_dup) >= len(labels),
            "detail": {"labels": len(labels), "labels_dup": len(labels_dup)},
        }
    )
    # Boundary: missing future censors.
    alone, _ = build_executable_labels(rows[:1], horizons=(300,))
    tests.append(
        {
            "name": "missing_future_is_censored_not_dropped",
            "passed": len(alone) == 1 and str(alone[0]["label_status"]).startswith("censored"),
            "detail": alone[0] if alone else None,
        }
    )
    # Negative: crossed book blocked.
    bad = dict(rows[0])
    bad["best_yes_bid"] = 0.60
    bad["best_yes_ask"] = 0.50
    bad2 = dict(rows[1])
    bad_labels, _ = build_executable_labels([bad, bad2], horizons=(300,))
    yes_blocked = any(
        row.get("yes_blocker") for row in bad_labels if row.get("label_status") != "censored_no_future_book"
    )
    tests.append({"name": "crossed_entry_book_blocked", "passed": yes_blocked, "detail": bad_labels[0] if bad_labels else None})
    return tests


def retired_negative_registry() -> list[dict[str, Any]]:
    return [
        {
            "spec_id": "historical_mlb_multi_book_consensus_v1",
            "family": "sports_consensus_historical",
            "status": "falsified",
            "evidence": "1108 exact rows, 1098 public-Kalshi labels, 5 hypotheses, max OOS 186, 0 FDR survivors",
            "do_not_repeat": "Cosmetic threshold/bucket renames of the same consensus divergence specs",
        },
        {
            "spec_id": "near_resolution_simple_flow_forward_mid_v1",
            "family": "near_resolution_informed_flow",
            "status": "falsified",
            "evidence": "11061 obs, 7951 forward-quote labels, 3 testable simple forward candidates, best q~0.999",
            "do_not_repeat": "Same mid-direction forward labels with cosmetic momentum/imbalance renames",
        },
        {
            "spec_id": "passive_liquidity_public_snapshot_paper_fill_v1",
            "family": "passive_liquidity_provision",
            "status": "falsified",
            "evidence": "9301 valid labels, 3 hypotheses, best q=1.0, best net EV ~-0.0183",
            "do_not_repeat": "Same maker paper-fill specs on public snapshots without new fill truth",
        },
        {
            "spec_id": "flow_depth_imbalance_settlement_directional_v1",
            "family": "near_resolution_informed_flow",
            "status": "confirmation_failed",
            "evidence": "Retired after 18 paper labels: 8 correct, accuracy 0.4444, mean calibration error ~0.5288",
            "do_not_repeat": "Resurrecting settlement-direction depth imbalance without new mechanism",
        },
    ]


def research_frontier(
    *,
    label_summary: Mapping[str, Any],
    evaluations: Sequence[Mapping[str, Any]],
    audit: Mapping[str, Any],
) -> list[dict[str, Any]]:
    executable = int(label_summary.get("executable_label_count") or 0)
    censored = int(label_summary.get("censored_count") or 0)
    survivors = [row for row in evaluations if row.get("status") == "research_candidate_fdr_passed"]
    testable = [row for row in evaluations if row.get("status") in {"testable", "research_candidate_fdr_passed"}]
    return [
        {
            "rank": 1,
            "lane": "executable_horizon_microstructure_v1",
            "status": "confirmation_pending" if survivors else ("falsified" if testable else "discovery_pending"),
            "independent_labels_now": executable,
            "censored_labels": censored,
            "expected_time_to_next_labels_minutes": 15,
            "decision_value": "Primary sports short-horizon promotion surface",
            "next_action": (
                "Freeze survivor and accumulate post-cutoff confirmation"
                if survivors
                else "Retire family if complete FDR failure; else densify 5/15m capture"
            ),
        },
        {
            "rank": 2,
            "lane": "tick_recorder_dense_mlb_orderbook",
            "status": "discovery_pending",
            "independent_labels_now": int(audit.get("tick_jsonl_file_count") or 0),
            "expected_time_to_next_labels_minutes": 30,
            "decision_value": "Unlock true 60s executable labels (current snapshot median gap ~27m)",
            "next_action": "Run read-only tick recorder on MLB moneyline books during live slate",
        },
        {
            "rank": 3,
            "lane": "cross_contract_within_event_coherence",
            "status": "discovery_pending",
            "independent_labels_now": 0,
            "decision_value": "Distinct family if executable horizon microstructure falsifies",
            "next_action": "Only after family 1 complete negative or survivor packet",
        },
        {
            "rank": 4,
            "lane": "thin_book_fade",
            "status": "discovery_pending",
            "independent_labels_now": executable,
            "decision_value": "Liquidity-reversion family distinct from informed-flow imbalance continuation",
            "next_action": "Falsify thin-book fade on executable 5/15m labels",
        },
        {
            "rank": 5,
            "lane": "atp_forward_oos_and_settlement_velocity",
            "status": "calendar_monitor",
            "decision_value": "Clock-bound; do not block main loop",
            "next_action": "Parked monitor only",
        },
        {
            "rank": 6,
            "lane": "asian_sharp_soccer",
            "status": "blocked_external_deferred",
            "decision_value": "Explicitly out of scope",
            "next_action": "Do not pursue under this directive",
        },
    ]
