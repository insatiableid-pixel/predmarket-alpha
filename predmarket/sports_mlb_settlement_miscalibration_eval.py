"""Walk-forward evaluation and synthetic suite for MLB settlement miscalibration."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
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
    DEFAULT_CLOCKS_SECONDS,
    DEFAULT_STALENESS_SECONDS,
    FAMILY_ID,
    FDR_ALPHA,
    MIN_CONFIRMATION_EVENTS,
    MIN_DISCOVERY_EVENTS,
    MIN_OOS_EVENTS,
    PRIOR_NEGATIVE_SPECS,
    build_fixed_clock_labels,
    normalize_observation_row,
    sha256_file,
    validate_book,
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


def cluster_bootstrap_lower_bound(
    event_returns: Sequence[float],
    *,
    n_bootstrap: int = 400,
    seed: int = 11,
    alpha: float = 0.05,
) -> float | None:
    if not event_returns:
        return None
    state = seed % 2147483647
    if state <= 0:
        state = 1
    samples: list[float] = []
    n = len(event_returns)
    for _ in range(n_bootstrap):
        draws: list[float] = []
        for _ in range(n):
            state = (1103515245 * state + 12345) % (2**31)
            draws.append(event_returns[state % n])
        samples.append(sum(draws) / n)
    samples.sort()
    index = max(0, min(len(samples) - 1, math.floor(alpha * len(samples))))
    return samples[index]


def _binomial_gte(successes: int, trials: int, p_null: float) -> float:
    if trials <= 0:
        return 1.0
    total = 0.0
    for k in range(successes, trials + 1):
        total += math.comb(trials, k) * (p_null**k) * ((1.0 - p_null) ** (trials - k))
    return min(max(total, 0.0), 1.0)


def evaluate_hypothesis(
    labels: Sequence[Mapping[str, Any]],
    spec: Mapping[str, Any],
    *,
    min_oos_labels: int = MIN_OOS_EVENTS,
    min_events: int = MIN_OOS_EVENTS,
    n_folds: int = 4,
    require_orderbook_entry: bool = True,
) -> dict[str, Any]:
    # Promotion economics require orderbook entry truth. Candlestick rows remain in
    # calibration/coverage diagnostics but do not enter the economic FDR family.
    fired = eligible_signal_rows(
        labels, spec, require_orderbook_entry=require_orderbook_entry
    )
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
    p_value = _binomial_gte(wins, len(nets), 0.5) if nets else 1.0
    bootstrap_lb = cluster_bootstrap_lower_bound(nets)
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

    # Single-series MLB moneyline always has series share 1.0; concentration is
    # measured across chronological slate buckets (UTC date of game/decision).
    def _slate_key(row: Mapping[str, Any]) -> str:
        ts = optional_float(row.get("game_start_ts")) or optional_float(row.get("decision_ts"))
        if ts is None:
            return "unknown"

        return datetime.fromtimestamp(float(ts), tz=UTC).strftime("%Y-%m-%d")

    slate_counts = counts(_slate_key(row) for row in oos_rows)
    series_counts = counts(row.get("series_ticker") for row in oos_rows)
    largest_share = 0.0
    if oos_rows and slate_counts:
        largest_share = max(slate_counts.values()) / len(oos_rows)

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
    n_events = len({row.get("event_ticker") for row in oos_rows})
    if len(oos_rows) >= min_oos_labels and n_events >= min_events:
        status = "testable"

    return {
        "model_id": spec["model_id"],
        "feature_family": FAMILY_ID,
        "clock_name": spec["clock_name"],
        "side": spec["side"],
        "feature": spec["feature"],
        "direction": spec["direction"],
        "threshold": spec.get("threshold"),
        "range": spec.get("range"),
        "negative_control": bool(spec.get("negative_control")),
        "baseline_only": bool(spec.get("baseline_only")),
        "mechanism": spec.get("mechanism"),
        "fired_row_count": len(fired),
        "independent_event_count": len(independent),
        "oos_event_count": len(oos_rows),
        "oos_positive_event_count": wins,
        "oos_mean_net_return": json_float(mean_net),
        "oos_mean_gross_return": json_float(
            mean_or_none([float(row["selected_gross_return"]) for row in oos_rows])
        ),
        "oos_mean_calibration_residual": json_float(mean_residual),
        "oos_positive_rate": json_float(wins / len(oos_rows) if oos_rows else None),
        "p_value_mean_net_positive": json_float(p_value),
        "bootstrap_mean_net_lower_95": json_float(bootstrap_lb),
        "fold_stats": fold_stats,
        "temporal_bucket_mean_net": [json_float(value) for value in bucket_means],
        "positive_temporal_buckets": positive_buckets,
        "recent_bucket_mean_net": json_float(recent_bucket),
        "positive_capacity_event_count": len(capacity_values),
        "mean_capacity_contracts": json_float(mean_or_none(capacity_values)),
        "orderbook_entry_share": json_float(orderbook_share),
        "series_cluster_counts": series_counts,
        "slate_cluster_counts": slate_counts,
        "largest_series_cluster_share": json_float(largest_share),
        "largest_slate_cluster_share": json_float(largest_share),
        "status": status,
        "usable": False,
        "research_only": True,
        "execution_enabled": False,
    }


def apply_fdr(
    evaluations: Sequence[Mapping[str, Any]], *, alpha: float = FDR_ALPHA
) -> list[dict[str, Any]]:
    indexed: list[tuple[int, float]] = []
    for index, row in enumerate(evaluations):
        # Complete family includes baselines and negative controls for FDR accounting,
        # but only non-control non-baseline can become survivors.
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
                and not item.get("baseline_only")
            ):
                item["status"] = "research_candidate_fdr_passed"
        else:
            item["q_value"] = None
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
    mean_net = optional_float(evaluation.get("oos_mean_net_return"))
    gates.append(
        _gate("positive_mean_net", mean_net is not None and mean_net > 0, f"mean_net={mean_net}")
    )
    mean_resid = optional_float(evaluation.get("oos_mean_calibration_residual"))
    # Calibration evidence in the selected-side residual direction (mean residual > 0
    # means outcomes beat selected-side probability).
    gates.append(
        _gate(
            "calibration_direction",
            mean_resid is not None and mean_resid > 0,
            f"mean_selected_residual={mean_resid}",
        )
    )
    q_value = optional_float(evaluation.get("q_value"))
    gates.append(_gate("fdr_q_le_0_05", q_value is not None and q_value <= 0.05, f"q={q_value}"))
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
    # Depth may be missing on proxy/candle quotes; require capacity when available.
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
    share = optional_float(
        evaluation.get(
            "largest_slate_cluster_share", evaluation.get("largest_series_cluster_share")
        )
    )
    gates.append(
        _gate(
            "cluster_share_le_0_35",
            share is not None and share <= 0.35,
            f"largest_slate_share={share}",
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
        conf_mean = optional_float(confirmation.get("mean_net_return"))
        conf_ok = conf_events >= MIN_CONFIRMATION_EVENTS and conf_mean is not None and conf_mean > 0
        conf_reason = (
            f"events={conf_events} mean_net={conf_mean} min_events={MIN_CONFIRMATION_EVENTS}"
        )
    gates.append(_gate("untouched_confirmation", conf_ok, conf_reason))
    discovery_pass = all(
        gate["status"] == "pass" for gate in gates if gate["name"] != "untouched_confirmation"
    )
    research_ready = all(gate["status"] == "pass" for gate in gates)
    return {
        "gates": gates,
        "discovery_gates_pass": discovery_pass,
        "research_ready": research_ready,
    }


def _gate(name: str, passed: bool, reason: str) -> dict[str, str]:
    return {"name": name, "status": "pass" if passed else "fail", "reason": reason}


def evaluate_confirmation(
    labels: Sequence[Mapping[str, Any]],
    spec: Mapping[str, Any],
    *,
    cutoff_utc: str,
    require_orderbook_entry: bool = True,
) -> dict[str, Any]:
    cutoff_ts = timestamp(cutoff_utc)
    fired = eligible_signal_rows(
        labels, spec, require_orderbook_entry=require_orderbook_entry
    )
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
    return {
        "model_id": spec["model_id"],
        "cutoff_utc": cutoff_utc,
        "event_count": len(independent),
        "mean_net_return": json_float(mean_or_none(nets)),
        "mean_calibration_residual": json_float(mean_or_none(residuals)),
        "positive_rate": json_float(mean_or_none([1.0 if value > 0 else 0.0 for value in nets])),
        "status": (
            "confirmation_ready"
            if len(independent) >= MIN_CONFIRMATION_EVENTS
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


def power_analysis(label_summary: Mapping[str, Any]) -> dict[str, Any]:
    events_by_clock = dict(label_summary.get("events_by_clock") or {})
    max_events = max(events_by_clock.values()) if events_by_clock else 0
    return {
        "independence_unit": "event_ticker",
        "min_discovery_events": MIN_DISCOVERY_EVENTS,
        "min_oos_events": MIN_OOS_EVENTS,
        "min_confirmation_events": MIN_CONFIRMATION_EVENTS,
        "events_by_clock": events_by_clock,
        "max_clock_events": max_events,
        "discovery_power_met": max_events >= MIN_DISCOVERY_EVENTS,
        "notes": (
            "Power is event-level. Complementary contracts and multiple clocks from one "
            "game are not independent evidence."
        ),
    }


def phase0_audit(
    *,
    observations: Sequence[Mapping[str, Any]],
    settlements: Mapping[str, Mapping[str, Any]],
    observation_dirs: Sequence[Path],
    settlement_paths: Sequence[Path],
) -> dict[str, Any]:
    missing_book = 0
    crossed = 0
    future_settle = 0
    for row in observations:
        ok, reason = validate_book(
            optional_float(row.get("best_yes_bid")),
            optional_float(row.get("best_yes_ask")),
        )
        if not ok and reason == "missing_bid_or_ask":
            missing_book += 1
        if not ok and reason == "crossed_book":
            crossed += 1
        obs_ts = optional_float(row.get("observed_ts"))
        settle_ts = timestamp(row.get("settlement_time"))
        if obs_ts is not None and settle_ts is not None and settle_ts < obs_ts:
            future_settle += 1

    obs_hashes = {}
    for directory in observation_dirs:
        if directory.is_dir():
            for path in sorted(directory.glob("*.json"))[:30]:
                obs_hashes[str(path)] = sha256_file(path)
    sett_hashes = {str(path): sha256_file(path) for path in settlement_paths if path.is_file()}

    return {
        "family_id": FAMILY_ID,
        "prior_negative_specs": list(PRIOR_NEGATIVE_SPECS),
        "novelty_map": {
            "closed_families": [row["spec_id"] for row in PRIOR_NEGATIVE_SPECS],
            "this_family": FAMILY_ID,
            "distinct_mechanisms": [
                "fixed pregame clocks vs short-horizon microstructure",
                "hold-to-settlement economics vs next-mid / round-trip",
                "calibration residual surface separate from executable EV",
                "listing-age cold-start and clock-geometry path features",
            ],
            "baseline_only": ["static price buckets"],
        },
        "timestamp_semantics": {
            "market_observation_time": "observed_at_utc / quote_time of book snapshot",
            "orderbook_receipt_time": "same as observation time for stored packets",
            "scheduled_game_start": "occurrence_datetime preferred; ticker parse fallback",
            "market_close": "close_time from public market payload",
            "settlement_time": "public Kalshi settlement/result on contract ticker",
            "join_rule": "strict as-of: latest book with observed_ts <= clock_ts",
            "staleness": DEFAULT_STALENESS_SECONDS,
            "no_nearest_absolute_future_match": True,
        },
        "book_orientation": {
            "yes_ask": "executable entry for YES",
            "no_ask": "executable entry for NO; never inferred from invalid complement for economics",
            "complementary_contracts": "same event_ticker collapsed for independence",
        },
        "observation_row_count": len(observations),
        "settlement_ticker_count": len(settlements),
        "missing_yes_book_count": missing_book,
        "crossed_yes_book_count": crossed,
        "settlement_before_observation_count": future_settle,
        "observation_source_hashes_sample": obs_hashes,
        "settlement_source_hashes": sett_hashes,
        "synthetic_tests": synthetic_tests(),
        "clocks_frozen_before_outcomes": list(DEFAULT_CLOCKS_SECONDS.keys()),
        "staleness_frozen_before_outcomes": DEFAULT_STALENESS_SECONDS,
    }


def synthetic_tests() -> list[dict[str, Any]]:
    """Positive/negative/leakage/fee/staleness synthetic suite."""

    def iso(ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=UTC).isoformat().replace("+00:00", "Z")

    game_start = datetime(2026, 7, 8, 23, 5, tzinfo=UTC).timestamp()
    ticker = "KXMLBGAME-26JUL081805BOSNYY-BOS"
    event = "KXMLBGAME-26JUL081805BOSNYY"
    # Books: T-60m exact, future book after clock, stale book.
    t_60 = game_start - 3600
    observations = [
        {
            "snapshot_id": "past",
            "contract_ticker": ticker,
            "event_ticker": event,
            "series_ticker": "KXMLBGAME",
            "observed_at_utc": iso(t_60 - 120),
            "best_yes_bid": 0.54,
            "best_yes_ask": 0.56,
            "best_no_bid": 0.44,
            "best_no_ask": 0.46,
            "yes_bid_depth_top1": 10,
            "yes_ask_depth_top1": 12,
            "no_bid_depth_top1": 8,
            "no_ask_depth_top1": 9,
            "yes_mid": 0.55,
            "yes_spread": 0.02,
            "entry_source": "synthetic",
        },
        {
            "snapshot_id": "future_leak",
            "contract_ticker": ticker,
            "event_ticker": event,
            "series_ticker": "KXMLBGAME",
            "observed_at_utc": iso(t_60 + 30),
            "best_yes_bid": 0.80,
            "best_yes_ask": 0.82,
            "best_no_bid": 0.18,
            "best_no_ask": 0.20,
            "yes_bid_depth_top1": 10,
            "yes_ask_depth_top1": 12,
            "no_bid_depth_top1": 8,
            "no_ask_depth_top1": 9,
            "yes_mid": 0.81,
            "yes_spread": 0.02,
            "entry_source": "synthetic",
        },
    ]
    # Normalize.
    norm = []
    for index, row in enumerate(observations):
        item = normalize_observation_row(
            row, source_path="synthetic", source_sha256="synthetic", index=index
        )
        assert item is not None
        norm.append(item)
    settlements = {
        ticker: {
            "ticker": ticker,
            "event_ticker": event,
            "result": "yes",
            "occurrence_datetime": iso(game_start),
            "open_time": iso(game_start - 3 * 86400),
            "yes_outcome": 1,
        }
    }
    labels, _summary = build_fixed_clock_labels(
        norm,
        settlements,
        clocks={"T-60m": 3600},
        staleness={"T-60m": 15 * 60},
    )
    labeled = [row for row in labels if row.get("label_status") == "labeled"]
    tests: list[dict[str, Any]] = []
    tests.append(
        {
            "name": "asof_never_selects_future_book",
            "passed": bool(labeled)
            and labeled[0].get("snapshot_id") == "past"
            and float(labeled[0]["p_hat"]) < 0.7,
            "detail": labeled[0] if labeled else None,
        }
    )
    if labeled:
        fee = float(labeled[0]["yes_entry_fee"] or 0)
        gross = float(labeled[0]["yes_gross_payoff"] or 0)
        net = float(labeled[0]["yes_net_payoff"] or 0)
        tests.append(
            {
                "name": "hold_to_settlement_fee_is_entry_only",
                "passed": abs((gross - fee) - net) < 1e-9 and fee > 0,
                "detail": {"gross": gross, "fee": fee, "net": net},
            }
        )
        tests.append(
            {
                "name": "positive_path_yes_settlement_payoff",
                "passed": labeled[0]["yes_settlement_payoff"] == 1.0,
                "detail": labeled[0]["yes_settlement_payoff"],
            }
        )
    else:
        tests.append({"name": "hold_to_settlement_fee_is_entry_only", "passed": False})
        tests.append({"name": "positive_path_yes_settlement_payoff", "passed": False})

    # Stale book censoring.
    stale_only = [
        normalize_observation_row(
            {
                "snapshot_id": "stale",
                "contract_ticker": ticker,
                "event_ticker": event,
                "series_ticker": "KXMLBGAME",
                "observed_at_utc": iso(t_60 - 3600),
                "best_yes_bid": 0.5,
                "best_yes_ask": 0.52,
                "best_no_bid": 0.48,
                "best_no_ask": 0.5,
                "yes_mid": 0.51,
                "yes_spread": 0.02,
            },
            source_path="synthetic",
            source_sha256="synthetic",
            index=0,
        )
    ]
    assert stale_only[0] is not None
    stale_labels, _ = build_fixed_clock_labels(
        stale_only,
        settlements,
        clocks={"T-60m": 3600},
        staleness={"T-60m": 15 * 60},
    )
    tests.append(
        {
            "name": "stale_book_censored",
            "passed": all(row.get("label_status") == "censored_stale_book" for row in stale_labels),
            "detail": [row.get("label_status") for row in stale_labels],
        }
    )

    # Missing book.
    empty_labels, _ = build_fixed_clock_labels(
        [],
        settlements,
        clocks={"T-60m": 3600},
        staleness={"T-60m": 15 * 60},
    )
    tests.append(
        {
            "name": "missing_book_no_phantom_labels",
            "passed": empty_labels == [],
            "detail": len(empty_labels),
        }
    )

    # Complementary independence collapse.
    complementary = []
    for team, _outcome in (("BOS", 1), ("NYY", 0)):
        t = f"KXMLBGAME-26JUL081805BOSNYY-{team}"
        complementary.append(
            normalize_observation_row(
                {
                    "snapshot_id": f"c-{team}",
                    "contract_ticker": t,
                    "event_ticker": event,
                    "series_ticker": "KXMLBGAME",
                    "observed_at_utc": iso(t_60 - 60),
                    "best_yes_bid": 0.54,
                    "best_yes_ask": 0.56,
                    "best_no_bid": 0.44,
                    "best_no_ask": 0.46,
                    "yes_mid": 0.55,
                    "yes_spread": 0.02,
                },
                source_path="synthetic",
                source_sha256="synthetic",
                index=0,
            )
        )
    sett2 = {
        "KXMLBGAME-26JUL081805BOSNYY-BOS": {
            "ticker": "KXMLBGAME-26JUL081805BOSNYY-BOS",
            "event_ticker": event,
            "result": "yes",
            "occurrence_datetime": iso(game_start),
            "open_time": iso(game_start - 86400),
        },
        "KXMLBGAME-26JUL081805BOSNYY-NYY": {
            "ticker": "KXMLBGAME-26JUL081805BOSNYY-NYY",
            "event_ticker": event,
            "result": "no",
            "occurrence_datetime": iso(game_start),
            "open_time": iso(game_start - 86400),
        },
    }
    comp_labels, _ = build_fixed_clock_labels(
        [row for row in complementary if row is not None],
        sett2,
        clocks={"T-60m": 3600},
        staleness={"T-60m": 15 * 60},
    )
    fired = eligible_signal_rows(
        comp_labels,
        {
            "clock_name": "T-60m",
            "side": "yes",
            "feature": "p_hat",
            "direction": "gt",
            "threshold": 0.01,
        },
    )
    collapsed = collapse_event_independence(fired)
    tests.append(
        {
            "name": "event_independence_collapses_complementary_contracts",
            "passed": len(fired) == 2 and len(collapsed) == 1,
            "detail": {"fired": len(fired), "collapsed": len(collapsed)},
        }
    )

    # Duplicate snapshot stability.
    dup = norm + norm
    labels_dup, _ = build_fixed_clock_labels(
        dup,
        settlements,
        clocks={"T-60m": 3600},
        staleness={"T-60m": 15 * 60},
    )
    tests.append(
        {
            "name": "duplicate_books_do_not_double_count_clock_rows",
            "passed": sum(1 for row in labels_dup if row.get("label_status") == "labeled") == 1,
            "detail": len(labels_dup),
        }
    )
    return tests


def lifecycle_status(evaluations: Sequence[Mapping[str, Any]]) -> str:
    if any(row.get("status") == "research_ready" for row in evaluations):
        return "research_ready"
    if any(row.get("status") == "confirmation_pending" for row in evaluations):
        return "confirmation_pending"
    if any(row.get("status") == "confirmation_failed" for row in evaluations):
        return "confirmation_failed"
    testable = [
        row
        for row in evaluations
        if row.get("status")
        in {
            "testable",
            "research_candidate_fdr_passed",
            "testable_fdr_pass_hard_gate_fail",
            "falsified",
        }
    ]
    novel = [
        row
        for row in evaluations
        if not row.get("negative_control") and not row.get("baseline_only")
    ]
    if novel and all(
        row.get("status")
        in {"falsified", "insufficient_sample", "testable", "testable_fdr_pass_hard_gate_fail"}
        and row.get("status") != "research_candidate_fdr_passed"
        for row in novel
    ):
        # Family falsified only when power met and no FDR survivors among novel specs.
        powered = [row for row in novel if int(row.get("oos_event_count") or 0) >= MIN_OOS_EVENTS]
        survivors = [row for row in novel if row.get("status") == "research_candidate_fdr_passed"]
        if powered and not survivors:
            return "falsified"
    if testable:
        return "discovery_pending"
    return "discovery_pending"


def research_frontier(family_status: str, label_summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "rank": 1,
            "lane": FAMILY_ID,
            "status": family_status,
            "decision_value": "Fixed-clock MLB moneyline settlement miscalibration",
            "independent_labels_now": label_summary.get("distinct_event_count"),
            "events_by_clock": label_summary.get("events_by_clock"),
            "next_action": (
                "Produce readiness packet"
                if family_status == "research_ready"
                else (
                    "Retired: do not retune thresholds/buckets; require multi-week dense "
                    "orderbook panel as a new pre-registered evidence surface before reopening"
                    if family_status == "falsified"
                    else "Accumulate dense fixed-clock books and settled labels; do not retune"
                )
            ),
        },
        {
            "rank": 2,
            "lane": "mlb_multiweek_dense_fixed_clock_panel_v2",
            "status": "discovery_pending",
            "decision_value": (
                "Next distinct surface: multi-week dense orderbook fixed-clock panel with "
                "pre-registered slate-breadth power (not cosmetic retune of v1 thresholds)"
            ),
            "next_action": (
                "Run scripts/kalshi_sports_mlb_dense_book_capture.py on a cadence covering "
                "T-24h/T-6h/T-60m/T-15m across >=4 chronological slates before re-registering"
            ),
        },
        {
            "rank": 3,
            "lane": "sports_exact_cross_contract_moneyline_coherence",
            "status": "parked",
            "decision_value": (
                "Distinct settlement-miscalibration mechanism only where market terms prove "
                "complementary moneyline identity within event"
            ),
            "next_action": "Park until multi-week dense panel exists; do not mix with retired v1",
        },
        {
            "rank": 4,
            "lane": "retired_short_horizon_microstructure",
            "status": "falsified",
            "decision_value": "Do not resurrect short-horizon next-mid families",
            "next_action": "Parked permanently under negative registry",
        },
    ]


def negative_registry_update(
    evaluations: Sequence[Mapping[str, Any]], *, family_status: str
) -> list[dict[str, Any]]:
    rows = [dict(item) for item in PRIOR_NEGATIVE_SPECS]
    if family_status == "falsified":
        rows.append(
            {
                "family": FAMILY_ID,
                "spec_id": FAMILY_ID,
                "status": "falsified",
                "do_not_repeat": (
                    "Do not retune fixed-clock thresholds/buckets cosmetically; require a "
                    "genuinely new settlement-miscalibration mechanism or mapped sports surface"
                ),
                "evidence": {
                    "evaluations": [
                        {
                            "model_id": row.get("model_id"),
                            "status": row.get("status"),
                            "oos_event_count": row.get("oos_event_count"),
                            "oos_mean_net_return": row.get("oos_mean_net_return"),
                            "q_value": row.get("q_value"),
                        }
                        for row in evaluations
                    ]
                },
            }
        )
    for row in evaluations:
        if row.get("status") in {"falsified", "confirmation_failed"} or (
            row.get("status") == "testable"
            and optional_float(row.get("oos_mean_net_return")) is not None
            and float(row["oos_mean_net_return"]) <= 0
        ):
            rows.append(
                {
                    "family": FAMILY_ID,
                    "spec_id": row.get("model_id"),
                    "status": row.get("status") if row.get("status") != "testable" else "falsified",
                    "do_not_repeat": f"Failed or non-positive OOS economics for {row.get('model_id')}",
                    "evidence": {
                        "oos_event_count": row.get("oos_event_count"),
                        "oos_mean_net_return": row.get("oos_mean_net_return"),
                        "q_value": row.get("q_value"),
                        "oos_mean_calibration_residual": row.get("oos_mean_calibration_residual"),
                    },
                }
            )
    return rows
