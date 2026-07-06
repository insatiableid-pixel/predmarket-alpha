"""Generic signal-factory engine spine — parameterized by SignalFamily.

Every stage is a public function that takes a ``SignalFamily`` descriptor and
dispatches all family-specific behavior through its fields (``fetcher``,
``prediction_rule``, ``model_evaluators``, ``cluster_key_composer``, …).

The spine NEVER branches on ``family_id`` — it is closed for modification.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from typing import Any

# Re-export shared helpers so consumers can ``from predmarket.engine import …``
from predmarket.shared_helpers import (
    benjamini_hochberg,
    binomial_survival,
    bucket_time,
    chronological_split_index,
    controlled_cluster_costs,
    counts,
    gate,
    gate_counts,
    independent_contract_rows,
    iso_from_timestamp,
    iso_time,
    json_float,
    mapping,
    nonnegative_float,
    optional_float,
    outcome_value,
    outside_repo,
    path_is_within,
    positive_number,
    probability,
    read_json_or_empty,
    required_cluster_count,
    safe_research_artifact,
    safety_flags,
    select_cluster_round_robin,
    sha256_or_none,
    timestamp,
    utc_now,
    wilson_lower_bound,
)
from predmarket.signal_family import SignalFamily

__all__ = [
    # Re-exported helpers
    "ask_levels",
    "benjamini_hochberg",
    "binomial_survival",
    "bucket_time",
    "build_decay_summary",
    "build_falsification",
    "build_feature_packet",
    "build_replay_calibration",
    "capacity_row",
    "chronological_split_index",
    "controlled_capacity_rows",
    "controlled_cluster_costs",
    "counts",
    "gate",
    "gate_counts",
    "independent_contract_rows",
    "iso_from_timestamp",
    "iso_time",
    "json_float",
    "mapping",
    "nonnegative_float",
    "optional_float",
    "outcome_value",
    "outside_repo",
    "path_is_within",
    "positive_number",
    "probability",
    "read_json_or_empty",
    "required_cluster_count",
    "safe_research_artifact",
    "safety_flags",
    "select_cluster_round_robin",
    "sha256_or_none",
    "timestamp",
    "utc_now",
    "wilson_lower_bound",
]


# ── Shared defaults (binding threshold constants) ─────────────────────────

MIN_INDEPENDENT_LABELS = 30
MIN_OOS_LABELS = 10
TEST_FRACTION = 0.30
FDR_ALPHA = 0.10
CONFIDENCE_Z = 1.6448536269514722
MIN_SIDE_OOS_LABELS = 30
MIN_DECAY_BUCKETS = 3
MIN_DECAY_LABELS = 100
MAX_CLUSTER_SHARE = 0.35
MIN_POSITIVE_CAPACITY_CONTRACTS = 1.0
MAX_CLOSE_HOURS = 6.0
MAX_CONTRACTS = 1500
MAX_TICKERS = 60


# ═══════════════════════════════════════════════════════════════════════════
# Stage 1 — Feature packet
# ═══════════════════════════════════════════════════════════════════════════


def build_feature_packet(
    *,
    family: SignalFamily,
    candidates: Sequence[Mapping[str, Any]],
    raw_index: Mapping[str, Mapping[str, Any]],
    generated_ts: float,
    max_close_hours: float = MAX_CLOSE_HOURS,
    max_contracts: int = MAX_CONTRACTS,
    feature_row_fn: Callable[
        [Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], float], dict[str, Any]
    ],
    gates_fn: Callable[..., list[dict[str, Any]]],
    status_fn: Callable[..., str],
    next_action_fn: Callable[[str], dict[str, str]],
    **kwargs: Any,
) -> dict[str, Any]:
    """Build a feature-packet report from universe candidates.  (Generic spine.)

    ``family`` is used for identity fields; the actual family-specific logic
    (feature computation, gates, status) is injected via ``feature_row_fn``,
    ``gates_fn``, ``status_fn``, ``next_action_fn``.
    """
    generated = kwargs.get("generated_utc") or utc_now()
    selected = _select_candidates(
        candidates=candidates,
        raw_index=raw_index,
        generated_ts=generated_ts,
        max_close_hours=max_close_hours,
        max_contracts=max_contracts,
        filter_fn=lambda row: True,
        sort_key_fn=lambda row: (
            float(row.get("fresh_time_to_close_hours") or 999999.0),
            str(row.get("asset_symbol") or row.get("contract_ticker") or ""),
        ),
    )
    enriched = _enrich_candidates(selected, raw_index)
    feature_rows = [feature_row_fn(row, {}, {}, generated_ts) for row in enriched]
    feature_ready_count = sum(
        1 for row in feature_rows if row.get("feature_status") == "proxy_features_ready"
    )
    has_capture = kwargs.get("capture_public_proxy", False)
    status = status_fn(
        row_count=len(feature_rows),
        feature_ready_count=feature_ready_count,
        capture_public_proxy=has_capture,
    )
    gates = gates_fn(
        feature_rows=feature_rows,
        proxy_capture=kwargs.get("proxy_capture", {}),
        **kwargs,
    )
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": has_capture,
        "authenticated_api_calls": False,
        "provider_api_calls": has_capture,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "summary": {
            "candidate_row_count": len(selected),
            "feature_row_count": len(feature_rows),
            "feature_ready_count": feature_ready_count,
            "feature_partial_count": max(0, len(feature_rows) - feature_ready_count),
        },
        "source_policy": {
            "official_settlement_source": str(family.official_settlement_source),
            "official_settlement_source_status": "not_captured_by_this_report",
            "proxy_source_role": "model_feature_only_not_official_settlement",
        },
        "gates": gates,
        "feature_rows": feature_rows,
        "next_action": next_action_fn(status),
        "safety": safety_flags(public_market_data_calls=has_capture),
    }


def _select_candidates(
    *,
    candidates: Sequence[Mapping[str, Any]],
    raw_index: Mapping[str, Mapping[str, Any]],
    generated_ts: float,
    max_close_hours: float,
    max_contracts: int,
    filter_fn: Callable[[Mapping[str, Any]], bool],
    sort_key_fn: Callable[[Mapping[str, Any]], Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in candidates if isinstance(candidates, list) else []:
        if not isinstance(row, Mapping) or not filter_fn(row):
            continue
        ticker = str(row.get("ticker") or "")
        raw = raw_index.get(ticker, {})
        close_ts = _close_timestamp(row, raw)
        if close_ts is None:
            continue
        fresh_hours = (close_ts - generated_ts) / 3600
        if fresh_hours <= 0 or fresh_hours > max_close_hours:
            continue
        enriched = {
            "contract_ticker": ticker,
            "event_ticker": row.get("event_ticker") or raw.get("event_ticker"),
            "series_ticker": row.get("series_ticker") or raw.get("series_ticker"),
            "close_time": row.get("close_time") or raw.get("close_time"),
            "expected_expiration_time": row.get("expected_expiration_time")
            or raw.get("expected_expiration_time"),
            "fresh_time_to_close_hours": round(fresh_hours, 6),
            "yes_bid": row.get("yes_bid"),
            "yes_ask": row.get("yes_ask"),
            "no_bid": row.get("no_bid"),
            "no_ask": row.get("no_ask"),
            "yes_spread": row.get("yes_spread"),
        }
        rows.append(enriched)
    rows.sort(key=sort_key_fn)
    return rows[:max_contracts]


def _close_timestamp(candidate: Mapping[str, Any], raw: Mapping[str, Any]) -> float | None:
    for source in (candidate, raw):
        for key in ("close_time", "expected_expiration_time", "expiration_time"):
            value = timestamp(source.get(key))
            if value is not None:
                return value
    return optional_float(candidate.get("close_ts"))


def _enrich_candidates(
    rows: Sequence[Mapping[str, Any]], raw_index: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        ticker = str(row.get("contract_ticker") or "")
        raw = raw_index.get(ticker, {})
        row_copy = dict(row)
        for key in (
            "title",
            "subtitle",
            "strike_type",
            "floor_strike",
            "cap_strike",
            "tags",
            "series_title",
        ):
            value = raw.get(key)
            if value is not None and row_copy.get(key) is None:
                row_copy[key] = value
        enriched.append(row_copy)
    return enriched


# ═══════════════════════════════════════════════════════════════════════════
# Stage 2 — Falsification (generic evaluator loop)
# ═══════════════════════════════════════════════════════════════════════════


def build_falsification(
    *,
    label_rows: Sequence[Mapping[str, Any]],
    prediction_rule: Callable[[Mapping[str, Any]], tuple[int | None, float | None]],
    model_evaluators: Sequence[Mapping[str, Any]],
    family: SignalFamily | None = None,
    status_prefix: str = "",
    min_independent_labels: int = MIN_INDEPENDENT_LABELS,
    min_oos_labels: int = MIN_OOS_LABELS,
    test_fraction: float = TEST_FRACTION,
    fdr_alpha: float = FDR_ALPHA,
    **kwargs: Any,
) -> dict[str, Any]:
    """Falsification harness — generic evaluator loop parameterized by family.

    ``prediction_rule``: callable(row) → (side_int {0, 1} | None, confidence).
    ``model_evaluators``: list of descriptors, each with a ``model_id`` and
        ``evaluate_fn(rows, oos_rows, prediction_rule, …)`` callable.
    ``family``: optional SignalFamily to derive ``status_prefix`` from.
    ``status_prefix``: explicit prefix override (takes precedence when non-empty).
    """
    # Derive status_prefix from family or explicit arg or fallback
    derived_prefix = (
        status_prefix
        or (family.status_prefix if family else "")
        or (family.family_id if family else kwargs.get("family_id", ""))
    )
    normalized = _normalize_label_rows(label_rows)
    invalid_count = normalized["invalid_count"]
    independent = independent_contract_rows(normalized["rows"])
    evaluations = []
    split_index = chronological_split_index(len(independent), test_fraction)
    oos_rows = independent[split_index:]
    for evaluator in model_evaluators:
        eval_result = _run_evaluator(
            evaluator=evaluator,
            rows=independent,
            oos_rows=oos_rows,
            prediction_rule=prediction_rule,
            min_independent_labels=min_independent_labels,
            min_oos_labels=min_oos_labels,
            fdr_alpha=fdr_alpha,
        )
        evaluations.append(eval_result)
    # BH correction across testable evaluators
    p_values = [
        (i, e["p_value"])
        for i, e in enumerate(evaluations)
        if isinstance(e.get("p_value"), (int, float))
    ]
    q_by_index = benjamini_hochberg(p_values)
    for idx, q_val in q_by_index.items():
        evaluations[idx]["q_value"] = q_val
        if (
            evaluations[idx]["status"] == "testable_research_candidate"
            and q_val <= fdr_alpha
            and float(evaluations[idx].get("oos_accuracy") or 0.0) > 0.5
        ):
            evaluations[idx]["status"] = "research_candidate_fdr_passed"
    summary = _falsification_summary(
        independent=independent,
        evaluations=evaluations,
        invalid_count=invalid_count,
        min_independent_labels=min_independent_labels,
        min_oos_labels=min_oos_labels,
    )
    status = _falsification_status(summary, evaluations, derived_prefix)
    return {
        "evaluations": evaluations,
        "summary": summary,
        "status": status,
    }


def _run_evaluator(
    *,
    evaluator: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    prediction_rule: Callable[[Mapping[str, Any]], tuple[int | None, float | None]],
    min_independent_labels: int,
    min_oos_labels: int,
    fdr_alpha: float,
) -> dict[str, Any]:
    """Run a single model evaluator and return its result dict."""
    evaluate_fn = evaluator.get("evaluate_fn")
    if evaluate_fn:
        return evaluate_fn(
            rows=rows,
            oos_rows=oos_rows,
            prediction_rule=prediction_rule,
            min_independent_labels=min_independent_labels,
            min_oos_labels=min_oos_labels,
        )
    # Default: directional evaluator pattern
    scored = [row for row in oos_rows if prediction_rule(row)[0] is not None]
    wins = sum(1 for row in scored if prediction_rule(row)[0] == row.get("yes_outcome"))
    model_id = str(evaluator.get("model_id", "unknown"))
    if len(rows) < min_independent_labels:
        status = "blocked_insufficient_independent_labels"
    elif len(scored) < min_oos_labels:
        status = "blocked_insufficient_oos_labels"
    else:
        status = "testable_research_candidate"
    p_val = (
        binomial_survival(wins, len(scored), 0.5)
        if len(rows) >= min_independent_labels and len(scored) >= min_oos_labels
        else None
    )
    return {
        "model_id": model_id,
        "status": status,
        "independent_label_count": len(rows),
        "oos_count": len(scored),
        "oos_correct_count": wins,
        "oos_accuracy": wins / len(scored) if scored else None,
        "p_value": p_val,
        "q_value": None,
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


def _normalize_label_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    invalid_count = 0
    for row in rows:
        ticker = str(row.get("contract_ticker") or "").strip()
        outcome = outcome_value(row.get("yes_outcome", row.get("side_outcome")))
        decision_ts = timestamp(row.get("decision_time"))
        close_ts = timestamp(row.get("close_time"))
        errors = []
        if not ticker:
            errors.append("missing_contract_ticker")
        if outcome is None:
            errors.append("missing_yes_outcome")
        if decision_ts is None:
            errors.append("missing_decision_time")
        if close_ts is None:
            errors.append("missing_close_time")
        if errors:
            invalid_count += 1
            continue
        normalized.append(
            {
                "contract_ticker": ticker,
                "yes_outcome": outcome,
                "decision_ts": decision_ts,
                "close_ts": close_ts,
                "decision_time": iso_from_timestamp(decision_ts),
                "close_time": iso_from_timestamp(close_ts),
                **{
                    k: row.get(k)
                    for k in row
                    if k
                    not in (
                        "contract_ticker",
                        "yes_outcome",
                        "decision_ts",
                        "close_ts",
                        "decision_time",
                        "close_time",
                    )
                },
            }
        )
    normalized.sort(key=lambda item: (item["decision_ts"], item["contract_ticker"]))
    return {"rows": normalized, "invalid_count": invalid_count}


def _falsification_summary(
    *,
    independent: Sequence[Mapping[str, Any]],
    evaluations: Sequence[Mapping[str, Any]],
    invalid_count: int,
    min_independent_labels: int,
    min_oos_labels: int,
) -> dict[str, Any]:
    return {
        "independent_contract_label_count": len(independent),
        "duplicate_label_row_count": 0,
        "min_independent_labels": min_independent_labels,
        "min_oos_labels": min_oos_labels,
        "testable_model_count": sum(
            1 for e in evaluations if e.get("status") == "testable_research_candidate"
        ),
        "research_candidate_count": sum(
            1 for e in evaluations if e.get("status") == "research_candidate_fdr_passed"
        ),
    }


def _falsification_status(
    summary: Mapping[str, Any], evaluations: Sequence[Mapping[str, Any]], family_id: str
) -> str:
    # The caller passes the family's status_prefix or falls back to family_id.
    # This avoids substring matching on family_id which would misroute weather
    # (e.g. "crypto" in "weather_proxy" is False, "sports" in "weather_proxy" is False).
    prefix = family_id if family_id else "unknown"
    if summary.get("independent_contract_label_count", 0) == 0:
        return f"{prefix}_feature_model_falsification_blocked_missing_labels"
    if summary.get("independent_contract_label_count", 0) < summary.get(
        "min_independent_labels", 30
    ):
        return f"{prefix}_feature_model_falsification_blocked_insufficient_independent_labels"
    if not any(
        e.get("status") in {"testable_research_candidate", "research_candidate_fdr_passed"}
        for e in evaluations
    ):
        return f"{prefix}_feature_model_falsification_blocked_insufficient_oos_labels"
    if summary.get("research_candidate_count", 0) > 0:
        return f"{prefix}_feature_model_falsification_ready_with_research_candidates"
    return f"{prefix}_feature_model_falsification_ready_no_research_candidates"


# ═══════════════════════════════════════════════════════════════════════════
# Stage 3 — Replay calibration
# ═══════════════════════════════════════════════════════════════════════════


def build_replay_calibration(
    *,
    oos_rows: Sequence[Mapping[str, Any]],
    prediction_rule: Callable[[Mapping[str, Any]], tuple[int | None, float | None]],
    confidence_z: float = CONFIDENCE_Z,
    min_side_oos_labels: int = MIN_SIDE_OOS_LABELS,
    candidate_eval: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute conservative calibrated side probability from OOS rows."""
    scored = [row for row in oos_rows if prediction_rule(row)[0] is not None]
    wins = sum(1 for row in scored if selected_side_outcome(row, prediction_rule) == 1)
    count = len(scored)
    raw_accuracy = wins / count if count else None
    posterior_mean = (wins + 1.0) / (count + 2.0) if count else None
    lower_bound = wilson_lower_bound(wins, count, confidence_z) if count else None
    status = "blocked_missing_research_candidate"
    if candidate_eval is not None and count < min_side_oos_labels:
        status = "blocked_insufficient_side_oos_labels"
    elif candidate_eval is not None and lower_bound is not None and lower_bound <= 0.5:
        status = "blocked_conservative_probability_not_above_random"
    elif candidate_eval is not None:
        status = "research_only_conservative_probability_ready"
    return {
        "status": status,
        "oos_count": count,
        "oos_correct_count": wins,
        "raw_oos_accuracy": json_float(raw_accuracy),
        "posterior_mean_selected_side_probability": json_float(posterior_mean),
        "conservative_calibrated_side_probability": json_float(lower_bound),
        "confidence_z": confidence_z,
        "min_side_oos_labels": min_side_oos_labels,
        "source_model_q_value": candidate_eval.get("q_value") if candidate_eval else None,
        "usable": False,
    }


def selected_side_outcome(
    row: Mapping[str, Any],
    prediction_rule: Callable[[Mapping[str, Any]], tuple[int | None, float | None]],
) -> int | None:
    """Return 1 if the predicted side matches the actual outcome, 0 otherwise."""
    prediction, _ = prediction_rule(row)
    yes_outcome = outcome_value(row.get("yes_outcome"))
    if prediction is None or yes_outcome is None:
        return None
    return yes_outcome if prediction == 1 else 1 - yes_outcome


# ═══════════════════════════════════════════════════════════════════════════
# Stage 3b — Decay summary (generic)
# ═══════════════════════════════════════════════════════════════════════════


def build_decay_summary(
    oos_rows: Sequence[Mapping[str, Any]],
    prediction_rule: Callable[[Mapping[str, Any]], tuple[int | None, float | None]],
) -> dict[str, Any]:
    """Per-close-bucket decay evidence from OOS rows."""
    buckets: dict[str, list[int]] = defaultdict(list)
    for row in oos_rows:
        bk = bucket_time(row.get("close_time"))
        outcome = selected_side_outcome(row, prediction_rule)
        if bk and outcome is not None:
            buckets[bk].append(outcome)
    if not buckets:
        return {
            "bucket_count": 0,
            "recent_bucket_accuracy": None,
            "recent_bucket_key": None,
            "status": "blocked_missing_decay_buckets",
            "decay_buckets": [],
            "total_decay_labels": 0,
            "passing_bucket_count": 0,
            "cumulative_accuracy": None,
        }
    sorted_keys = sorted(buckets)
    decay_buckets: list[dict[str, Any]] = []
    for key in sorted_keys:
        outcomes = buckets[key]
        n = len(outcomes)
        acc = sum(outcomes) / n if n else None
        decay_buckets.append(
            {
                "bucket": key,
                "label_count": n,
                "correct_count": sum(outcomes),
                "accuracy": json_float(acc),
                "pass_threshold": acc is not None and acc >= 0.5,
            }
        )
    recent_key = sorted_keys[-1]
    recent = buckets[recent_key]
    recent_accuracy = sum(recent) / len(recent) if recent else None
    status = (
        "recent_bucket_not_worse_than_random"
        if recent_accuracy is not None and recent_accuracy >= 0.5
        else "recent_bucket_below_random"
    )
    all_outcomes = [o for outs in buckets.values() for o in outs]
    total_labels = len(all_outcomes)
    cumulative = sum(all_outcomes) / total_labels if total_labels else None
    passing = sum(1 for b in decay_buckets if b["pass_threshold"])
    return {
        "bucket_count": len(buckets),
        "recent_bucket_accuracy": json_float(recent_accuracy),
        "recent_bucket_key": recent_key,
        "recent_bucket_label_count": len(recent),
        "status": status,
        "decay_buckets": decay_buckets,
        "total_decay_labels": total_labels,
        "passing_bucket_count": passing,
        "cumulative_accuracy": json_float(cumulative),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Stage 4 — CCD (capacity correlation decay) generic helpers
# ═══════════════════════════════════════════════════════════════════════════


def ask_levels(orderbook: Mapping[str, Any], side: str) -> list[dict[str, float]]:
    """Derive YES/NO reciprocal-ask levels from a Kalshi orderbook.

    Kalshi orderbooks return bids only.  To buy a YES contract you trade
    against NO bids (and vice versa), so the ask price is 1 - opposing bid.
    """
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
        bid_price = _price_probability(level[0])
        contracts = nonnegative_float(level[1])
        if bid_price is None or contracts is None or contracts <= 0:
            continue
        ask_price = 1.0 - bid_price
        if 0.0 < ask_price <= 1.0:
            levels.append({"ask_price": ask_price, "contracts": contracts})
    levels.sort(key=lambda item: item["ask_price"])
    return levels


def _price_probability(value: Any) -> float | None:
    """Parse a price that may be a probability (0-1) or a percentage (0-100)."""
    number = probability(value)
    if number is not None:
        return number
    raw = nonnegative_float(value)
    if raw is not None and raw > 1.0 and raw <= 100.0:
        return raw / 100.0
    return None


def capacity_row(
    row: Mapping[str, Any],
    *,
    orderbook: Mapping[str, Any] | None,
    calibrated_probability: float | None,
    normalize_cost_fn: Callable[..., Any] | None = None,
    ticker: str | None = None,
) -> dict[str, Any]:
    """Build a CCD capacity row from a candidate + orderbook."""
    from predmarket.kalshi_execution_cost import normalize_kalshi_execution_cost as _norm

    normalize = normalize_cost_fn or _norm
    side = str(row.get("predicted_side") or "")
    levels = ask_levels(orderbook or {}, side)
    positive_contracts = 0.0
    positive_cost = 0.0
    best_break_even: float | None = None
    best_margin: float | None = None
    for i, level in enumerate(levels):
        cost = normalize(
            display_price=level["ask_price"],
            executable_price=level["ask_price"],
            executable_price_source=f"public_orderbook_{side}_ask_level",
            payout_if_correct=1.0,
            ticker=ticker or str(row.get("contract_ticker") or ""),
        )
        break_even = cost.break_even_probability
        if i == 0:
            best_break_even = break_even
            best_margin = (
                calibrated_probability - break_even
                if calibrated_probability is not None and break_even is not None
                else None
            )
        if (
            calibrated_probability is not None
            and break_even is not None
            and calibrated_probability > break_even
        ):
            positive_contracts += level["contracts"]
            positive_cost += (cost.all_in_cost or 0.0) * level["contracts"]
    return {
        "contract_ticker": row.get("contract_ticker"),
        "event_ticker": row.get("event_ticker"),
        "close_time": row.get("close_time"),
        "predicted_side": side,
        "level_count": len(levels),
        "best_all_in_break_even_probability": json_float(best_break_even),
        "conservative_calibrated_side_probability": json_float(calibrated_probability),
        "best_margin_probability": json_float(best_margin),
        "positive_depth_contracts": json_float(positive_contracts),
        "positive_depth_cost": json_float(positive_cost),
        "gate_status": "pass" if positive_contracts > 0 else "blocked",
        "usable": False,
        "research_only": True,
        "execution_enabled": False,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Stage 5 — Cluster control (fully generic)
# ═══════════════════════════════════════════════════════════════════════════


def controlled_capacity_rows(
    rows: Sequence[Mapping[str, Any]],
    controlled_clusters: Mapping[str, float],
) -> list[dict[str, Any]]:
    """Apply cluster-controlled allocation to capacity rows."""
    remaining = dict(controlled_clusters)
    cluster_totals = dict(controlled_clusters)
    output: list[dict[str, Any]] = []
    ordered = sorted(
        rows,
        key=lambda row: (
            str(row.get("correlation_cluster_key") or "unknown"),
            -float(row.get("best_margin_probability") or 0.0),
            str(row.get("contract_ticker") or ""),
        ),
    )
    for row in ordered:
        key = str(row.get("correlation_cluster_key") or "unknown")
        available = remaining.get(key, 0.0)
        source_cost = float(row.get("positive_depth_cost") or 0.0)
        if available <= 1e-9 or source_cost <= 0:
            controlled_cost = 0.0
        else:
            controlled_cost = min(source_cost, available)
            remaining[key] = available - controlled_cost
        source_contracts = float(row.get("positive_depth_contracts") or 0.0)
        ratio = controlled_cost / source_cost if source_cost > 0 else 0.0
        controlled_contracts = source_contracts * ratio
        row_copy = dict(row)
        row_copy["controlled_depth_cost"] = json_float(controlled_cost)
        row_copy["controlled_depth_contracts"] = json_float(controlled_contracts)
        row_copy["controlled_cluster_share"] = None
        row_copy["gate_status"] = "pass" if controlled_cost > 0 else "blocked"
        row_copy["usable"] = False
        if cluster_totals.get(key) and sum(cluster_totals.values()) > 0:
            row_copy["controlled_cluster_share"] = json_float(
                cluster_totals[key] / sum(cluster_totals.values())
            )
        output.append(row_copy)
    return output
