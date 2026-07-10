"""Walk-forward evaluation and synthetic suite for MLB settlement miscalibration."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from predmarket.shared_helpers import (
    benjamini_hochberg,
    chronological_split_index,
    counts,
    json_float,
    optional_float,
    timestamp,
)
from predmarket.sports_mlb_settlement_miscalibration import (
    ANALYSIS_CONTRACT_VERSION,
    FAMILY_ID,
    FDR_ALPHA,
    INFERENCE_RESAMPLES,
    INFERENCE_SEED,
    MAX_SLATE_SHARE,
    MIN_CONFIRMATION_EVENTS,
    MIN_CONFIRMATION_SLATES,
    MIN_DISCOVERY_EVENTS,
    MIN_INFERENCE_SLATES,
    MIN_OOS_EVENTS,
    MIN_OOS_SLATES,
    sha256_text,
)


def signal_fires(row: Mapping[str, Any], spec: Mapping[str, Any]) -> bool:
    if str(row.get("clock_name")) != str(spec.get("clock_name")):
        return False
    if str(row.get("label_status")) != "labeled":
        return False
    feature = optional_float(row.get(str(spec["feature"])))
    direction = str(spec["direction"])
    p_hat = optional_float(row.get("p_hat"))
    spread = optional_float(row.get("yes_spread"))

    if direction == "gt":
        thr = float(spec["threshold"])
        return feature is not None and feature > thr
    if direction == "lt":
        thr = float(spec["threshold"])
        return feature is not None and feature < thr
    if direction == "in_range":
        low, high = spec["range"]
        return feature is not None and float(low) <= feature < float(high)
    if direction == "lt_and_p_gt":
        thr = float(spec["threshold"])
        p_thr = float(spec["p_threshold"])
        return feature is not None and feature < thr and p_hat is not None and p_hat > p_thr
    if direction == "gt_and_spread_le":
        thr = float(spec["threshold"])
        spread_max = float(spec["spread_max"])
        return feature is not None and feature > thr and spread is not None and spread <= spread_max
    return False


def eligible_signal_rows(
    labels: Sequence[Mapping[str, Any]],
    spec: Mapping[str, Any],
    *,
    require_orderbook_entry: bool = False,
) -> list[dict[str, Any]]:
    side = str(spec["side"]).lower()
    net_key = "yes_net_payoff" if side == "yes" else "no_net_payoff"
    gross_key = "yes_gross_payoff" if side == "yes" else "no_gross_payoff"
    cap_key = "yes_capacity" if side == "yes" else "no_capacity"
    selected: list[dict[str, Any]] = []
    for row in labels:
        if not signal_fires(row, spec):
            continue
        if row.get(net_key) is None:
            continue
        entry_source = str(row.get("entry_source") or "")
        if require_orderbook_entry and "candle" in entry_source.lower():
            continue
        item = dict(row)
        residual = optional_float(row.get("calibration_residual"))
        # For NO side, calibration residual vs selected-side probability:
        # selected p = 1-p_hat, Y_side = 1-yes_outcome => residual_side = -residual_yes
        side_residual = (
            residual if side == "yes" else (None if residual is None else -float(residual))
        )
        item["selected_side"] = side
        item["selected_net_return"] = float(row[net_key])
        item["selected_gross_return"] = float(row.get(gross_key) or 0.0)
        item["selected_capacity"] = optional_float(row.get(cap_key))
        item["selected_calibration_residual"] = json_float(side_residual)
        selected.append(item)
    return selected


def collapse_event_independence(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
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
    return sorted(
        by_event.values(),
        key=lambda item: (float(item.get("decision_ts") or 0), item.get("event_ticker") or ""),
    )


def event_grouped_folds(
    rows: Sequence[Mapping[str, Any]],
    *,
    n_folds: int = 4,
    embargo_events: int = 1,
) -> list[dict[str, Any]]:
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
        test_end = (
            len(events) if fold_index == n_folds - 1 else min(len(events), test_start + fold_size)
        )
        if test_start >= len(events):
            break
        test_events = set(events[test_start:test_end])
        embargo_start = max(0, test_start - embargo_events)
        embargo_end = min(len(events), test_end + embargo_events)
        embargo_set = set(events[embargo_start:embargo_end]) - test_events
        train_events = set(events[:test_start]) - embargo_set
        folds.append(
            {
                "fold_index": fold_index,
                "train_event_count": len(train_events),
                "test_event_count": len(test_events),
                "embargo_event_count": len(embargo_set),
                "train_rows": [
                    row
                    for row in rows
                    if str(row.get("event_ticker") or row.get("contract_ticker") or "")
                    in train_events
                ],
                "test_rows": [
                    row
                    for row in rows
                    if str(row.get("event_ticker") or row.get("contract_ticker") or "")
                    in test_events
                ],
            }
        )
    return folds


def mean_or_none(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return float(sum(values) / len(values))


def slate_date_key(row: Mapping[str, Any]) -> str:
    ts = optional_float(row.get("game_start_ts")) or optional_float(row.get("decision_ts"))
    if ts is None:
        return "unknown"
    return datetime.fromtimestamp(float(ts), tz=UTC).strftime("%Y-%m-%d")


def _lcg_next(state: int) -> int:
    return (1103515245 * state + 12345) % (2**31)


def slate_cluster_sign_flip_test(
    event_rows: Sequence[Mapping[str, Any]],
    value_key: str,
    *,
    n_resamples: int = INFERENCE_RESAMPLES,
    seed: int = INFERENCE_SEED,
    min_clusters: int = MIN_INFERENCE_SLATES,
    alternative: str = "greater",
) -> dict[str, Any]:
    """One-sided slate-clustered sign-flip test for E[value] > 0.

    Independence unit for outcomes is event; clusters are MLB slate dates.
    Sign flips are applied to whole slate clusters so same-day dependence is preserved.
    """
    pairs: list[tuple[str, float]] = []
    for row in event_rows:
        value = optional_float(row.get(value_key))
        if value is None:
            continue
        pairs.append((slate_date_key(row), float(value)))
    if not pairs:
        return {
            "method": "slate_cluster_sign_flip",
            "null": "E[value] <= 0",
            "alternative": "E[value] > 0",
            "cluster_unit": "mlb_slate_date_utc",
            "n_events": 0,
            "n_clusters": 0,
            "seed": seed,
            "n_resamples": n_resamples,
            "observed_mean": None,
            "p_value": 1.0,
            "underpowered": True,
            "underpowered_reason": "no_event_values",
        }

    by_slate: dict[str, list[float]] = defaultdict(list)
    for slate, value in pairs:
        by_slate[slate].append(value)
    slates = sorted(by_slate)
    n_events = len(pairs)
    n_clusters = len(slates)
    observed_mean = sum(value for _, value in pairs) / n_events
    underpowered = n_clusters < min_clusters
    underpowered_reason = (
        f"n_clusters={n_clusters} < min_inference_slates={min_clusters}" if underpowered else None
    )

    # Cluster totals and sizes for efficient flips.
    cluster_totals = [sum(by_slate[slate]) for slate in slates]
    state = seed % 2147483647
    if state <= 0:
        state = 1
    extreme = 0
    for _ in range(n_resamples):
        flipped_sum = 0.0
        for total in cluster_totals:
            state = _lcg_next(state)
            sign = 1.0 if (state % 2) == 0 else -1.0
            flipped_sum += sign * total
        flipped_mean = flipped_sum / n_events
        if alternative == "greater":
            if flipped_mean >= observed_mean - 1e-15:
                extreme += 1
        else:
            if flipped_mean <= observed_mean + 1e-15:
                extreme += 1
    # Add-one correction for discrete randomization tests.
    p_value = (extreme + 1) / (n_resamples + 1)
    return {
        "method": "slate_cluster_sign_flip",
        "null": "E[value] <= 0",
        "alternative": "E[value] > 0" if alternative == "greater" else "E[value] < 0",
        "cluster_unit": "mlb_slate_date_utc",
        "n_events": n_events,
        "n_clusters": n_clusters,
        "seed": seed,
        "n_resamples": n_resamples,
        "observed_mean": json_float(observed_mean),
        "p_value": json_float(p_value),
        "underpowered": underpowered,
        "underpowered_reason": underpowered_reason,
        "slate_ids": slates,
    }


def cluster_bootstrap_lower_bound(
    event_rows: Sequence[Mapping[str, Any]],
    value_key: str,
    *,
    n_bootstrap: int = 400,
    seed: int = INFERENCE_SEED,
    alpha: float = 0.05,
    min_clusters: int = MIN_INFERENCE_SLATES,
) -> dict[str, Any]:
    """Cluster bootstrap lower CI for mean using slate resampling."""
    by_slate: dict[str, list[float]] = defaultdict(list)
    for row in event_rows:
        value = optional_float(row.get(value_key))
        if value is None:
            continue
        by_slate[slate_date_key(row)].append(float(value))
    slates = sorted(by_slate)
    if not slates:
        return {
            "lower_bound": None,
            "method": "slate_cluster_bootstrap",
            "n_clusters": 0,
            "n_events": 0,
            "underpowered": True,
            "seed": seed,
            "n_bootstrap": n_bootstrap,
        }
    n_clusters = len(slates)
    n_events = sum(len(by_slate[s]) for s in slates)
    state = seed % 2147483647
    if state <= 0:
        state = 1
    samples: list[float] = []
    for _ in range(n_bootstrap):
        draws: list[float] = []
        for _c in range(n_clusters):
            state = _lcg_next(state)
            chosen = slates[state % n_clusters]
            draws.extend(by_slate[chosen])
        if draws:
            samples.append(sum(draws) / len(draws))
    samples.sort()
    if not samples:
        lower = None
    else:
        index = max(0, min(len(samples) - 1, math.floor(alpha * len(samples))))
        lower = samples[index]
    return {
        "lower_bound": json_float(lower),
        "method": "slate_cluster_bootstrap",
        "n_clusters": n_clusters,
        "n_events": n_events,
        "underpowered": n_clusters < min_clusters,
        "seed": seed,
        "n_bootstrap": n_bootstrap,
        "alpha": alpha,
    }


def chronological_slate_bucket_means(
    event_rows: Sequence[Mapping[str, Any]],
    value_key: str,
    *,
    n_buckets: int = 4,
) -> dict[str, Any]:
    """Real chronological slate-date buckets (not row-chunk pseudo-buckets)."""
    by_slate: dict[str, list[float]] = defaultdict(list)
    for row in event_rows:
        value = optional_float(row.get(value_key))
        if value is None:
            continue
        by_slate[slate_date_key(row)].append(float(value))
    ordered_slates = sorted(s for s in by_slate if s != "unknown")
    if not ordered_slates:
        return {
            "bucket_means": [],
            "positive_buckets": 0,
            "recent_bucket_mean": None,
            "bucket_slate_counts": [],
            "method": "chronological_slate_date_buckets",
        }
    chunk = max(1, math.ceil(len(ordered_slates) / n_buckets))
    bucket_means: list[float | None] = []
    bucket_slate_counts: list[int] = []
    for bucket_index in range(n_buckets):
        start = bucket_index * chunk
        end = min(len(ordered_slates), start + chunk)
        if start >= len(ordered_slates):
            break
        part_slates = ordered_slates[start:end]
        values = [value for slate in part_slates for value in by_slate[slate]]
        bucket_means.append(mean_or_none(values))
        bucket_slate_counts.append(len(part_slates))
    positive_buckets = sum(1 for value in bucket_means if value is not None and value > 0)
    recent = bucket_means[-1] if bucket_means else None
    return {
        "bucket_means": [json_float(value) for value in bucket_means],
        "positive_buckets": positive_buckets,
        "recent_bucket_mean": json_float(recent),
        "bucket_slate_counts": bucket_slate_counts,
        "method": "chronological_slate_date_buckets",
        "n_slates": len(ordered_slates),
    }


def evaluate_hypothesis(
    labels: Sequence[Mapping[str, Any]],
    spec: Mapping[str, Any],
    *,
    min_oos_labels: int = MIN_OOS_EVENTS,
    min_events: int = MIN_OOS_EVENTS,
    min_oos_slates: int = MIN_OOS_SLATES,
    n_folds: int = 4,
    require_orderbook_entry: bool = True,
    inference_seed: int = INFERENCE_SEED,
    inference_resamples: int = INFERENCE_RESAMPLES,
) -> dict[str, Any]:
    # Promotion economics require orderbook entry truth. Candlestick rows remain in
    # calibration/coverage diagnostics but do not enter the economic FDR family.
    fired = eligible_signal_rows(labels, spec, require_orderbook_entry=require_orderbook_entry)
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
                "mean_calibration_residual": mean_or_none(
                    [
                        float(row["selected_calibration_residual"])
                        for row in test_rows
                        if row.get("selected_calibration_residual") is not None
                    ]
                ),
            }
        )
        oos_rows.extend(test_rows)

    if len(oos_rows) < min(12, min_oos_labels // 2) and independent:
        split = chronological_split_index(len(independent), 0.3)
        oos_rows = independent[split:]
        nets = [float(row["selected_net_return"]) for row in oos_rows]
        fold_stats = [
            {
                "fold_index": 0,
                "oos_event_count": len(oos_rows),
                "mean_net_return": mean_or_none(nets),
                "fallback": "chronological_event_holdout_30pct",
            }
        ]

    nets = [float(row["selected_net_return"]) for row in oos_rows]
    residuals = [
        float(row["selected_calibration_residual"])
        for row in oos_rows
        if row.get("selected_calibration_residual") is not None
    ]
    wins = sum(1 for value in nets if value > 0)
    mean_net = mean_or_none(nets)
    mean_residual = mean_or_none(residuals)

    # Descriptive only — never labeled as mean-net p-value.
    win_rate = wins / len(oos_rows) if oos_rows else None

    economic_inference = slate_cluster_sign_flip_test(
        oos_rows,
        "selected_net_return",
        n_resamples=inference_resamples,
        seed=inference_seed,
    )
    calibration_inference = slate_cluster_sign_flip_test(
        oos_rows,
        "selected_calibration_residual",
        n_resamples=inference_resamples,
        seed=inference_seed + 17,
    )
    p_economic = float(economic_inference.get("p_value") or 1.0)
    p_calibration = float(calibration_inference.get("p_value") or 1.0)
    p_joint = max(p_economic, p_calibration)

    bootstrap = cluster_bootstrap_lower_bound(
        oos_rows,
        "selected_net_return",
        seed=inference_seed,
    )
    bootstrap_lb = optional_float(bootstrap.get("lower_bound"))
    capacity_values = [
        float(row["selected_capacity"])
        for row in oos_rows
        if optional_float(row.get("selected_capacity")) is not None
        and float(row["selected_capacity"]) > 0
    ]
    orderbook_n = sum(
        1 for row in oos_rows if "candle" not in str(row.get("entry_source") or "").lower()
    )
    orderbook_share = (orderbook_n / len(oos_rows)) if oos_rows else None

    slate_counts = counts(slate_date_key(row) for row in oos_rows)
    series_counts = counts(row.get("series_ticker") for row in oos_rows)
    n_slates = len(slate_counts)
    largest_share = 0.0
    if oos_rows and slate_counts:
        largest_share = max(slate_counts.values()) / len(oos_rows)

    # Discovery-side slate diagnostics (all independent fired events).
    discovery_slate_counts = counts(slate_date_key(row) for row in independent)

    temporal = chronological_slate_bucket_means(oos_rows, "selected_net_return")
    positive_buckets = int(temporal.get("positive_buckets") or 0)
    recent_bucket = optional_float(temporal.get("recent_bucket_mean"))
    bucket_means = list(temporal.get("bucket_means") or [])

    n_events = len({row.get("event_ticker") for row in oos_rows})
    power_met = (
        len(oos_rows) >= min_oos_labels and n_events >= min_events and n_slates >= min_oos_slates
    )
    inference_underpowered = bool(
        economic_inference.get("underpowered") or calibration_inference.get("underpowered")
    )
    if not power_met:
        status = "underpowered"
        power_reason = (
            f"oos_events={len(oos_rows)} min_events={min_oos_labels}; "
            f"oos_slates={n_slates} min_slates={min_oos_slates}"
        )
    elif inference_underpowered:
        status = "underpowered"
        power_reason = (
            economic_inference.get("underpowered_reason")
            or calibration_inference.get("underpowered_reason")
            or "inference_clusters_insufficient"
        )
    else:
        status = "testable"
        power_reason = "per_spec_event_and_slate_power_met"

    formula = {
        "model_id": spec["model_id"],
        "clock_name": spec["clock_name"],
        "side": spec["side"],
        "feature": spec["feature"],
        "direction": spec["direction"],
        "threshold": spec.get("threshold"),
        "range": spec.get("range"),
        "p_threshold": spec.get("p_threshold"),
        "spread_max": spec.get("spread_max"),
        "mechanism": spec.get("mechanism"),
    }
    formula_hash = sha256_text(str(sorted(formula.items())))

    return {
        "model_id": spec["model_id"],
        "feature_family": FAMILY_ID,
        "analysis_contract_version": ANALYSIS_CONTRACT_VERSION,
        "formula_hash": formula_hash,
        "clock_name": spec["clock_name"],
        "side": spec["side"],
        "feature": spec["feature"],
        "direction": spec["direction"],
        "threshold": spec.get("threshold"),
        "range": spec.get("range"),
        "negative_control": bool(spec.get("negative_control")),
        "baseline_only": bool(spec.get("baseline_only")),
        "mechanism": spec.get("mechanism"),
        "testing_family_role": (
            "descriptive_control"
            if spec.get("negative_control") or spec.get("baseline_only")
            else "novel_discovery"
        ),
        "fired_row_count": len(fired),
        "independent_event_count": len(independent),
        "effective_n_events": n_events,
        "oos_event_count": len(oos_rows),
        "oos_slate_count": n_slates,
        "discovery_event_count": len(independent),
        "discovery_slate_count": len(discovery_slate_counts),
        "oos_positive_event_count": wins,
        "oos_mean_net_return": json_float(mean_net),
        "oos_mean_gross_return": json_float(
            mean_or_none([float(row["selected_gross_return"]) for row in oos_rows])
        ),
        "oos_mean_calibration_residual": json_float(mean_residual),
        "oos_positive_rate": json_float(win_rate),
        "win_rate_descriptive_only": json_float(win_rate),
        "p_economic": json_float(p_economic),
        "p_calibration": json_float(p_calibration),
        "p_joint": json_float(p_joint),
        # Backward-compatible alias — NOT a win-rate binomial.
        "p_value_mean_net_positive": json_float(p_economic),
        "economic_inference": economic_inference,
        "calibration_inference": calibration_inference,
        "bootstrap_mean_net_lower_95": json_float(bootstrap_lb),
        "bootstrap_inference": bootstrap,
        "fold_stats": fold_stats,
        "temporal_bucket_mean_net": bucket_means,
        "temporal_bucket_method": temporal.get("method"),
        "temporal_bucket_slate_counts": temporal.get("bucket_slate_counts"),
        "positive_temporal_buckets": positive_buckets,
        "recent_bucket_mean_net": json_float(recent_bucket),
        "positive_capacity_event_count": len(capacity_values),
        "mean_capacity_contracts": json_float(mean_or_none(capacity_values)),
        "orderbook_entry_share": json_float(orderbook_share),
        "series_cluster_counts": series_counts,
        "slate_cluster_counts": slate_counts,
        "discovery_slate_cluster_counts": discovery_slate_counts,
        "largest_series_cluster_share": json_float(largest_share),
        "largest_slate_cluster_share": json_float(largest_share),
        "power_met": power_met and not inference_underpowered,
        "power_reason": power_reason,
        "power_state": "powered" if status == "testable" else "underpowered",
        "status": status,
        "usable": False,
        "research_only": True,
        "execution_enabled": False,
    }


def apply_fdr(
    evaluations: Sequence[Mapping[str, Any]], *, alpha: float = FDR_ALPHA
) -> list[dict[str, Any]]:
    """BH-FDR on p_joint for powered novel discovery members only.

    Baselines and negative controls are descriptive; they are not mixed into the
    novel discovery testing family.
    """
    indexed: list[tuple[int, float]] = []
    family_member_ids: list[str] = []
    excluded: list[dict[str, Any]] = []
    for index, row in enumerate(evaluations):
        model_id = str(row.get("model_id"))
        if row.get("negative_control") or row.get("baseline_only"):
            excluded.append(
                {
                    "model_id": model_id,
                    "reason": "descriptive_control_not_in_novel_fdr_family",
                    "role": row.get("testing_family_role"),
                }
            )
            continue
        if row.get("status") not in {"testable", "research_candidate_fdr_passed"}:
            excluded.append(
                {
                    "model_id": model_id,
                    "reason": f"not_eligible_status={row.get('status')}",
                    "power_state": row.get("power_state"),
                }
            )
            continue
        p_joint = optional_float(row.get("p_joint"))
        if p_joint is None:
            excluded.append({"model_id": model_id, "reason": "missing_p_joint"})
            continue
        indexed.append((index, float(p_joint)))
        family_member_ids.append(model_id)

    q_map = benjamini_hochberg(indexed) if indexed else {}
    # Rank map for artifact transparency.
    ordered = sorted(indexed, key=lambda item: item[1])
    rank_map = {index: rank for rank, (index, _) in enumerate(ordered, start=1)}
    family_size = len(indexed)

    output: list[dict[str, Any]] = []
    for index, row in enumerate(evaluations):
        item = dict(row)
        item["fdr_family"] = "novel_discovery"
        item["fdr_alpha"] = alpha
        item["fdr_family_size"] = family_size
        item["fdr_family_member_ids"] = list(family_member_ids)
        item["fdr_excluded_members"] = excluded
        if index in q_map:
            q_value = float(q_map[index])
            rank = rank_map[index]
            threshold = alpha * rank / family_size if family_size else None
            item["q_value"] = json_float(q_value)
            item["bh_rank"] = rank
            item["bh_threshold"] = json_float(threshold)
            item["p_economic"] = json_float(item.get("p_economic"))
            item["p_calibration"] = json_float(item.get("p_calibration"))
            item["p_joint"] = json_float(item.get("p_joint"))
            if (
                item.get("status") == "testable"
                and q_value <= alpha
                and optional_float(item.get("oos_mean_net_return")) is not None
                and float(item["oos_mean_net_return"]) > 0
                and optional_float(item.get("oos_mean_calibration_residual")) is not None
                and float(item["oos_mean_calibration_residual"]) > 0
                and not item.get("negative_control")
                and not item.get("baseline_only")
            ):
                item["status"] = "research_candidate_fdr_passed"
        else:
            item["q_value"] = None
            item["bh_rank"] = None
            item["bh_threshold"] = None
        output.append(item)
    return output


def hard_gate_assessment(
    evaluation: Mapping[str, Any],
    *,
    min_oos: int = MIN_OOS_EVENTS,
    confirmation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    gates = []
    oos = int(evaluation.get("oos_event_count") or 0)
    gates.append(_gate("min_oos_events", oos >= min_oos, f"oos_event_count={oos} min={min_oos}"))
    oos_slates = int(evaluation.get("oos_slate_count") or 0)
    gates.append(
        _gate(
            "min_oos_slates",
            oos_slates >= MIN_OOS_SLATES,
            f"oos_slate_count={oos_slates} min={MIN_OOS_SLATES}",
        )
    )
    mean_net = optional_float(evaluation.get("oos_mean_net_return"))
    gates.append(
        _gate("positive_mean_net", mean_net is not None and mean_net > 0, f"mean_net={mean_net}")
    )
    mean_resid = optional_float(evaluation.get("oos_mean_calibration_residual"))
    gates.append(
        _gate(
            "calibration_direction",
            mean_resid is not None and mean_resid > 0,
            f"mean_selected_residual={mean_resid}",
        )
    )
    p_economic = optional_float(evaluation.get("p_economic"))
    p_calibration = optional_float(evaluation.get("p_calibration"))
    p_joint = optional_float(evaluation.get("p_joint"))
    gates.append(
        _gate(
            "economic_inference",
            p_economic is not None and p_economic <= FDR_ALPHA,
            f"p_economic={p_economic}",
        )
    )
    gates.append(
        _gate(
            "calibration_inference",
            p_calibration is not None and p_calibration <= FDR_ALPHA,
            f"p_calibration={p_calibration}",
        )
    )
    q_value = optional_float(evaluation.get("q_value"))
    gates.append(
        _gate(
            "fdr_q_le_alpha_on_p_joint",
            q_value is not None and q_value <= FDR_ALPHA,
            f"q={q_value} p_joint={p_joint} alpha={FDR_ALPHA}",
        )
    )
    lb = optional_float(evaluation.get("bootstrap_mean_net_lower_95"))
    gates.append(_gate("bootstrap_lb_above_0", lb is not None and lb > 0, f"lb={lb}"))
    pos_buckets = int(evaluation.get("positive_temporal_buckets") or 0)
    recent = optional_float(evaluation.get("recent_bucket_mean_net"))
    gates.append(
        _gate(
            "temporal_survival",
            pos_buckets >= 3 and (recent is None or recent >= 0),
            f"positive_buckets={pos_buckets} recent={recent}",
        )
    )
    cap = int(evaluation.get("positive_capacity_event_count") or 0)
    if evaluation.get("mean_capacity_contracts") is None and cap == 0:
        gates.append(
            _gate(
                "capacity_events",
                False,
                "capacity_unavailable_or_zero; dense books required for research_ready",
            )
        )
    else:
        gates.append(_gate("capacity_events", cap >= 3, f"positive_capacity_events={cap}"))
    orderbook_share = optional_float(evaluation.get("orderbook_entry_share"))
    gates.append(
        _gate(
            "orderbook_entry_truth",
            orderbook_share is not None and orderbook_share >= 0.5,
            f"orderbook_entry_share={orderbook_share} (candlestick rows are discovery-only)",
        )
    )
    share = optional_float(evaluation.get("largest_slate_cluster_share"))
    gates.append(
        _gate(
            "cluster_share_le_max",
            share is not None and share <= MAX_SLATE_SHARE,
            f"largest_slate_share={share} max={MAX_SLATE_SHARE}",
        )
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
            "not_baseline_only",
            not bool(evaluation.get("baseline_only")),
            f"baseline_only={evaluation.get('baseline_only')}",
        )
    )
    conf_ok = False
    conf_reason = "confirmation_not_run"
    if confirmation is not None:
        conf_events = int(confirmation.get("event_count") or 0)
        conf_slates = int(confirmation.get("slate_count") or 0)
        conf_mean = optional_float(confirmation.get("mean_net_return"))
        conf_ok = (
            conf_events >= MIN_CONFIRMATION_EVENTS
            and conf_slates >= MIN_CONFIRMATION_SLATES
            and conf_mean is not None
            and conf_mean > 0
        )
        conf_reason = (
            f"events={conf_events} slates={conf_slates} mean_net={conf_mean} "
            f"min_events={MIN_CONFIRMATION_EVENTS} min_slates={MIN_CONFIRMATION_SLATES}"
        )
    gates.append(_gate("untouched_confirmation", conf_ok, conf_reason))

    non_conf = [gate for gate in gates if gate["name"] != "untouched_confirmation"]
    failed_non_conf = [gate for gate in non_conf if gate["status"] != "pass"]
    breadth_only = bool(failed_non_conf) and all(
        gate["name"] in {"cluster_share_le_max", "min_oos_slates"} for gate in failed_non_conf
    )
    discovery_pass = not failed_non_conf
    research_ready = all(gate["status"] == "pass" for gate in gates)
    return {
        "gates": gates,
        "discovery_gates_pass": discovery_pass,
        "research_ready": research_ready,
        "breadth_only_failure": breadth_only,
        "failed_non_confirmation_gates": [gate["name"] for gate in failed_non_conf],
    }


def _gate(name: str, passed: bool, reason: str) -> dict[str, str]:
    return {"name": name, "status": "pass" if passed else "fail", "reason": reason}


def evaluate_confirmation(
    labels: Sequence[Mapping[str, Any]],
    spec: Mapping[str, Any],
    *,
    cutoff_utc: str,
    registration_utc: str | None = None,
    require_orderbook_entry: bool = True,
) -> dict[str, Any]:
    # Confirmation must be strictly post-registration when a freeze timestamp exists.
    boundary = registration_utc or cutoff_utc
    cutoff_ts = timestamp(boundary)
    fired = eligible_signal_rows(labels, spec, require_orderbook_entry=require_orderbook_entry)
    post = [
        row
        for row in fired
        if cutoff_ts is not None and float(row.get("decision_ts") or 0) > cutoff_ts
    ]
    independent = collapse_event_independence(post)
    nets = [float(row["selected_net_return"]) for row in independent]
    residuals = [
        float(row["selected_calibration_residual"])
        for row in independent
        if row.get("selected_calibration_residual") is not None
    ]
    slate_counts = counts(slate_date_key(row) for row in independent)
    return {
        "model_id": spec["model_id"],
        "historical_discovery_data_cutoff_utc": cutoff_utc,
        "forward_confirmation_registered_at_utc": registration_utc,
        "confirmation_boundary_utc": boundary,
        "event_count": len(independent),
        "slate_count": len(slate_counts),
        "mean_net_return": json_float(mean_or_none(nets)),
        "mean_calibration_residual": json_float(mean_or_none(residuals)),
        "positive_rate": json_float(mean_or_none([1.0 if value > 0 else 0.0 for value in nets])),
        "status": (
            "confirmation_ready"
            if (
                len(independent) >= MIN_CONFIRMATION_EVENTS
                and len(slate_counts) >= MIN_CONFIRMATION_SLATES
            )
            else "confirmation_insufficient_sample"
        ),
    }


def calibration_summary(labels: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [
        row
        for row in labels
        if row.get("label_status") == "labeled" and optional_float(row.get("p_hat")) is not None
    ]
    by_clock: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_clock[str(row.get("clock_name"))].append(row)
    clock_reports = {}
    for clock_name, clock_rows in by_clock.items():
        residuals = [
            float(row["calibration_residual"])
            for row in clock_rows
            if row.get("calibration_residual") is not None
        ]
        briers = [float(row["brier"]) for row in clock_rows if row.get("brier") is not None]
        # Reliability curve buckets.
        buckets = []
        for low, high in (
            (0.05, 0.20),
            (0.20, 0.35),
            (0.35, 0.50),
            (0.50, 0.65),
            (0.65, 0.80),
            (0.80, 0.95),
        ):
            part = [
                row
                for row in clock_rows
                if optional_float(row.get("p_hat")) is not None
                and low <= float(row["p_hat"]) < high
            ]
            if not part:
                continue
            mean_p = mean_or_none([float(row["p_hat"]) for row in part])
            mean_y = mean_or_none([float(row["yes_outcome"]) for row in part])
            buckets.append(
                {
                    "bucket": f"{low:.2f}_{high:.2f}",
                    "n": len(part),
                    "mean_p": json_float(mean_p),
                    "mean_y": json_float(mean_y),
                    "mean_residual": json_float(
                        None if mean_p is None or mean_y is None else mean_y - mean_p
                    ),
                }
            )
        clock_reports[clock_name] = {
            "n": len(clock_rows),
            "mean_residual": json_float(mean_or_none(residuals)),
            "mean_brier": json_float(mean_or_none(briers)),
            "reliability_buckets": buckets,
            "distinct_events": len({row.get("event_ticker") for row in clock_rows}),
        }
    return {
        "labeled_rows": len(rows),
        "by_clock": clock_reports,
    }


def power_analysis(
    label_summary: Mapping[str, Any],
    evaluations: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    events_by_clock = dict(label_summary.get("events_by_clock") or {})
    slates_by_clock = dict(label_summary.get("slates_by_clock") or {})
    max_events = max(events_by_clock.values()) if events_by_clock else 0
    max_slates = max(slates_by_clock.values()) if slates_by_clock else 0
    per_spec: list[dict[str, Any]] = []
    if evaluations is not None:
        for row in evaluations:
            if row.get("negative_control") or row.get("baseline_only"):
                continue
            per_spec.append(
                {
                    "model_id": row.get("model_id"),
                    "formula_hash": row.get("formula_hash"),
                    "clock_name": row.get("clock_name"),
                    "oos_event_count": row.get("oos_event_count"),
                    "oos_slate_count": row.get("oos_slate_count"),
                    "discovery_event_count": row.get("discovery_event_count"),
                    "discovery_slate_count": row.get("discovery_slate_count"),
                    "largest_slate_cluster_share": row.get("largest_slate_cluster_share"),
                    "power_state": row.get("power_state"),
                    "power_reason": row.get("power_reason"),
                    "status": row.get("status"),
                    "power_met": row.get("power_met"),
                }
            )
    powered = [row for row in per_spec if row.get("power_met")]
    underpowered = [row for row in per_spec if not row.get("power_met")]
    return {
        "independence_unit": "event_ticker",
        "cluster_unit": "mlb_slate_date_utc",
        "min_discovery_events": MIN_DISCOVERY_EVENTS,
        "min_oos_events": MIN_OOS_EVENTS,
        "min_oos_slates": MIN_OOS_SLATES,
        "min_inference_slates": MIN_INFERENCE_SLATES,
        "min_confirmation_events": MIN_CONFIRMATION_EVENTS,
        "min_confirmation_slates": MIN_CONFIRMATION_SLATES,
        "events_by_clock": events_by_clock,
        "slates_by_clock": slates_by_clock,
        "max_clock_events": max_events,
        "max_clock_slates": max_slates,
        # Family-level panel coverage only; per-spec power is authoritative.
        "panel_event_coverage_met": max_events >= MIN_DISCOVERY_EVENTS,
        "discovery_power_met": bool(powered)
        and not underpowered
        and max_events >= MIN_DISCOVERY_EVENTS,
        "per_spec_power": per_spec,
        "powered_novel_count": len(powered),
        "underpowered_novel_count": len(underpowered),
        "notes": (
            "Power is per-specification at the event level with slate-cluster inference. "
            "Complementary contracts and multiple clocks from one game are not independent. "
            "Do not pool clocks or take max-clock events as a surrogate for per-spec power."
        ),
    }


# Re-export lifecycle helpers so existing imports from *_eval keep working.
from predmarket.sports_mlb_settlement_miscalibration_lifecycle import (  # noqa: E402
    family_resolution_counts,
    lifecycle_status,
    negative_registry_update,
    phase0_audit,
    research_frontier,
    resolve_spec_status,
    synthetic_tests,
)

__all__ = [
    "apply_fdr",
    "calibration_summary",
    "chronological_slate_bucket_means",
    "cluster_bootstrap_lower_bound",
    "collapse_event_independence",
    "eligible_signal_rows",
    "evaluate_confirmation",
    "evaluate_hypothesis",
    "event_grouped_folds",
    "family_resolution_counts",
    "hard_gate_assessment",
    "lifecycle_status",
    "mean_or_none",
    "negative_registry_update",
    "phase0_audit",
    "power_analysis",
    "research_frontier",
    "resolve_spec_status",
    "signal_fires",
    "slate_cluster_sign_flip_test",
    "slate_date_key",
    "synthetic_tests",
]
