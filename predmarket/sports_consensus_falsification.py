"""Sports no-vig consensus falsification ledger.

This module turns valid sports consensus preflight candidates plus exact
Kalshi settlement labels into a multiple-testing-controlled read on whether
Kalshi-vs-consensus divergence has non-random, out-of-sample predictive
value. It is the statistical gate before any EV-ledger promotion.

Inputs are already-joined observation rows (consensus probability + Kalshi
mid at observation time) paired with exact Kalshi settlement outcomes. The
join itself happens upstream (CLI / future accumulator); the helper stays
focused on deterministic falsification math.

Output is research-only. No EV, sizing, or execution.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from predmarket.shared_helpers import (
    benjamini_hochberg,
    binomial_survival,
    chronological_split_index,
    outcome_value,
    safety_flags,
    wilson_lower_bound,
)

FAMILY_ID = "sports_no_vig_consensus"

DEFAULT_THRESHOLDS: tuple[float, ...] = (
    0.005,
    0.01,
    0.015,
    0.02,
    0.025,
    0.03,
    0.04,
    0.05,
)
DEFAULT_PRICE_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("0.05_0.15", 0.05, 0.15),
    ("0.15_0.30", 0.15, 0.30),
    ("0.30_0.50", 0.30, 0.50),
    ("0.50_0.70", 0.50, 0.70),
    ("0.70_0.85", 0.70, 0.85),
    ("0.85_0.95", 0.85, 0.95),
)
DEFAULT_MIN_INDEPENDENT_LABELS = 30
DEFAULT_MIN_OOS_LABELS = 10
DEFAULT_TEST_FRACTION = 0.30
DEFAULT_FDR_ALPHA = 0.10
DEFAULT_CONFIDENCE_Z = 1.6448536269514722

CANDIDATE_RULES: tuple[str, ...] = (
    "kalshi_vs_consensus_favorite_underpriced",
    "kalshi_vs_consensus_underdog_underpriced",
    "kalshi_vs_consensus_fade_overpriced",
    "sports_consensus_price_bucket_bias",
)


# ---------------------------------------------------------------------------
# Doctrine
# ---------------------------------------------------------------------------


def falsification_doctrine(
    *,
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
    price_buckets: Sequence[tuple[str, float, float]] = DEFAULT_PRICE_BUCKETS,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "family_id": FAMILY_ID,
        "primary_probability_source": "timestamp_matched_multi_book_no_vig_consensus",
        "candidate_rules": list(CANDIDATE_RULES),
        "threshold_grid": [float(t) for t in thresholds],
        "price_buckets": [
            {"name": name, "low": low, "high": high} for name, low, high in price_buckets
        ],
        "independence_rule": "exact contract_ticker (each contract settles once)",
        "cluster_key_rule": "sport_key|market_key|event_ticker",
        "split_rule": "chronological holdout by observed_utc",
        "multiple_testing_family": (
            "Every (candidate_rule, threshold) for divergence rules plus every "
            "(candidate_rule, price_bucket) for the bucket bias rule increments "
            "the family and is routed through Benjamini-Hochberg FDR."
        ),
        "promotion_boundary": (
            "FDR survivor only signals a research candidate; no EV, sizing, or "
            "execution is implied."
        ),
    }


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def build_sports_consensus_falsification(
    *,
    preflight_report: Mapping[str, Any] | None,
    consensus_observations: Sequence[Mapping[str, Any]],
    settlement_labels: Sequence[Mapping[str, Any]],
    generated_utc: str | None = None,
    min_independent_labels: int = DEFAULT_MIN_INDEPENDENT_LABELS,
    min_oos_labels: int = DEFAULT_MIN_OOS_LABELS,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    fdr_alpha: float = DEFAULT_FDR_ALPHA,
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
    price_buckets: Sequence[tuple[str, float, float]] = DEFAULT_PRICE_BUCKETS,
    confidence_z: float = DEFAULT_CONFIDENCE_Z,
    preflight_path: Path | None = None,
    observation_dir: Path | None = None,
    label_dir: Path | None = None,
) -> dict[str, Any]:
    """Build the sports consensus falsification artifact.

    ``consensus_observations`` are already-joined rows produced upstream
    (one per contract_ticker+side+observed_utc) carrying the no-vig
    consensus probability and the timestamp-matched Kalshi mid.

    ``settlement_labels`` are rows that carry an exact Kalshi settlement
    outcome for the same contract_ticker+side.

    The helper joins them by exact contract_ticker+side, collapses repeated
    observations of the same contract to its earliest observation, performs
    a chronological in-sample/OOS split, evaluates every pre-registered
    candidate rule, applies BH-FDR, and emits a research-only artifact.
    """
    generated = generated_utc or _utc_now()
    preflight_present = isinstance(preflight_report, Mapping) and bool(preflight_report)
    preflight_summary: Mapping[str, Any] = (
        preflight_report.get("summary") if preflight_present else {}
    )
    preflight_status = preflight_report.get("status") if preflight_present else None
    preflight_valid = int(preflight_summary.get("valid_candidate_count") or 0)

    joined_rows, join_blockers = _join_observations_to_labels(
        consensus_observations, settlement_labels
    )
    independent_rows = _collapse_independent(joined_rows)
    independent_rows.sort(key=lambda r: (r["observed_ts"], r["contract_ticker"]))

    split_index = chronological_split_index(len(independent_rows), test_fraction)
    in_sample_rows = independent_rows[:split_index]
    oos_rows = independent_rows[split_index:]

    evaluations = _evaluate_candidate_rules(
        independent_rows=independent_rows,
        in_sample_rows=in_sample_rows,
        oos_rows=oos_rows,
        thresholds=thresholds,
        price_buckets=price_buckets,
        min_independent_labels=min_independent_labels,
        min_oos_labels=min_oos_labels,
        confidence_z=confidence_z,
    )
    _apply_fdr(evaluations, fdr_alpha=fdr_alpha)
    hypothesis_accumulation_plan = _build_hypothesis_accumulation_plan(
        evaluations=evaluations,
        min_independent_labels=min_independent_labels,
        min_oos_labels=min_oos_labels,
    )
    hypothesis_accumulation_opportunities = _build_hypothesis_accumulation_opportunities(
        accumulation_plan=hypothesis_accumulation_plan,
        consensus_observations=consensus_observations,
        settlement_labels=settlement_labels,
    )

    summary = _build_summary(
        preflight_summary=preflight_summary,
        preflight_valid=preflight_valid,
        consensus_observations=consensus_observations,
        settlement_labels=settlement_labels,
        joined_rows=joined_rows,
        independent_rows=independent_rows,
        in_sample_rows=in_sample_rows,
        oos_rows=oos_rows,
        join_blockers=join_blockers,
        evaluations=evaluations,
        min_independent_labels=min_independent_labels,
        min_oos_labels=min_oos_labels,
        test_fraction=test_fraction,
        fdr_alpha=fdr_alpha,
        hypothesis_accumulation_plan=hypothesis_accumulation_plan,
        hypothesis_accumulation_opportunities=hypothesis_accumulation_opportunities,
    )
    gates = _build_gates(
        preflight_present=preflight_present,
        preflight_valid=preflight_valid,
        summary=summary,
        evaluations=evaluations,
        observation_dir=observation_dir,
        label_dir=label_dir,
    )
    status = _status(
        preflight_present=preflight_present,
        preflight_valid=preflight_valid,
        gates=gates,
        summary=summary,
        evaluations=evaluations,
    )
    survivor = _best_survivor(evaluations)
    rows = _emit_evaluation_rows(
        independent_rows=independent_rows,
        oos_rows=oos_rows,
        thresholds=thresholds,
        price_buckets=price_buckets,
    )
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": False,
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "family_id": FAMILY_ID,
        "doctrine": falsification_doctrine(thresholds=thresholds, price_buckets=price_buckets),
        "inputs": {
            "preflight_path": str(preflight_path) if preflight_path else None,
            "preflight_present": preflight_present,
            "preflight_status": preflight_status,
            "preflight_valid_candidate_count": preflight_valid,
            "observation_dir": str(observation_dir) if observation_dir else None,
            "label_dir": str(label_dir) if label_dir else None,
            "consensus_observation_count": len(consensus_observations),
            "settlement_label_count": len(settlement_labels),
        },
        "method": {
            "independence_rule": ("Collapse by exact contract_ticker; each contract settles once."),
            "cluster_key_rule": "sport_key|market_key|event_ticker",
            "split": "chronological holdout by observed_utc",
            "test_fraction": test_fraction,
            "min_independent_labels": min_independent_labels,
            "min_oos_labels": min_oos_labels,
            "p_value": ("one-sided exact binomial survival under the rule-specific null"),
            "fdr": "Benjamini-Hochberg q-values across all testable hypotheses",
            "fdr_alpha": fdr_alpha,
            "threshold_grid": [float(t) for t in thresholds],
            "price_buckets": [
                {"name": name, "low": low, "high": high} for name, low, high in price_buckets
            ],
            "promotion_boundary": ("Research candidate only; no EV, sizing, or execution."),
        },
        "summary": summary,
        "gates": gates,
        "evaluations": evaluations,
        "hypothesis_accumulation_plan": hypothesis_accumulation_plan,
        "hypothesis_accumulation_opportunities": hypothesis_accumulation_opportunities,
        "best_survivor": survivor,
        "rows": rows,
        "join_blockers": join_blockers,
        "next_action": _next_action(status),
        "safety": safety_flags(),
    }


# ---------------------------------------------------------------------------
# Join / normalize / collapse
# ---------------------------------------------------------------------------


def _join_observations_to_labels(
    observations: Sequence[Mapping[str, Any]],
    labels: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Join observations to settlement labels by exact contract_ticker+side."""
    label_lookup: dict[tuple[str, str], Mapping[str, Any]] = {}
    for label in labels:
        ticker = str(label.get("contract_ticker") or "").strip()
        side = _normalize_side(label.get("side"))
        if not ticker or side is None:
            continue
        outcome = outcome_value(
            label.get("yes_outcome", label.get("settlement_outcome", label.get("side_outcome")))
        )
        if outcome is None:
            continue
        key = (ticker, side)
        if key not in label_lookup:
            label_lookup[key] = label

    joined: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for obs in observations:
        ticker = str(obs.get("contract_ticker") or "").strip()
        side = _normalize_side(obs.get("side"))
        if not ticker or side is None:
            blockers.append(
                {
                    "reason": "observation_missing_contract_or_side",
                    "contract_ticker": ticker or None,
                    "side": side,
                }
            )
            continue
        consensus_probability = _finite_float(
            obs.get(
                "consensus_probability_for_side", obs.get("consensus_no_vig_probability_for_side")
            )
        )
        kalshi_mid = _finite_float(obs.get("kalshi_mid_for_side"))
        observed_utc = _format_utc(_parse_utc(obs.get("observed_utc")))
        if consensus_probability is None or kalshi_mid is None or observed_utc is None:
            blockers.append(
                {
                    "reason": "observation_missing_required_field",
                    "contract_ticker": ticker,
                    "side": side,
                    "missing": [
                        field
                        for field, value in (
                            ("consensus_probability_for_side", consensus_probability),
                            ("kalshi_mid_for_side", kalshi_mid),
                            ("observed_utc", observed_utc),
                        )
                        if value is None
                    ],
                }
            )
            continue
        key = (ticker, side, observed_utc)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        label = label_lookup.get((ticker, side))
        if label is None:
            continue
        yes_outcome = outcome_value(
            label.get("yes_outcome", label.get("settlement_outcome", label.get("side_outcome")))
        )
        if yes_outcome is None:
            continue
        settlement_outcome_for_side = yes_outcome if side == "yes" else 1 - yes_outcome
        settlement_time_utc = _format_utc(
            _parse_utc(
                label.get("settled_time")
                or label.get("settlement_time_utc")
                or label.get("close_time")
            )
        )
        joined.append(
            {
                "contract_ticker": ticker,
                "event_ticker": (
                    obs.get("event_ticker")
                    or label.get("event_ticker")
                    or _derive_event_ticker(ticker)
                ),
                "side": side,
                "consensus_probability_for_side": consensus_probability,
                "kalshi_mid_for_side": kalshi_mid,
                "divergence": consensus_probability - kalshi_mid,
                "observed_utc": observed_utc,
                "observed_ts": _parse_utc(observed_utc).timestamp()
                if _parse_utc(observed_utc)
                else 0.0,
                "settlement_outcome_for_side": settlement_outcome_for_side,
                "settlement_time_utc": settlement_time_utc,
                "settlement_result": label.get("settlement_result"),
                "sport_key": obs.get("sport_key") or _derive_sport_key(ticker),
                "market_key": obs.get("market_key")
                or label.get("series_ticker")
                or _derive_market_key(ticker),
                "cluster_key": obs.get("cluster_key") or _build_cluster_key(ticker, obs, label),
                "book_count": int(obs.get("book_count") or 0),
                "distinct_books": list(obs.get("distinct_books") or []),
                "source_reference_sha256": obs.get("source_reference_sha256"),
            }
        )
    return joined, blockers


def _collapse_independent(
    joined_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse repeated observations by exact contract_ticker; keep earliest observed_utc."""
    by_ticker: dict[str, dict[str, Any]] = {}
    for row in joined_rows:
        ticker = row["contract_ticker"]
        existing = by_ticker.get(ticker)
        if existing is None or row["observed_ts"] < existing["observed_ts"]:
            by_ticker[ticker] = dict(row)
    return list(by_ticker.values())


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------


def _rule_applies(rule_name: str, row: Mapping[str, Any]) -> bool:
    consensus = row.get("consensus_probability_for_side")
    if consensus is None:
        return False
    if rule_name == "kalshi_vs_consensus_favorite_underpriced":
        return float(consensus) > 0.5
    if rule_name == "kalshi_vs_consensus_underdog_underpriced":
        return float(consensus) <= 0.5
    if rule_name == "kalshi_vs_consensus_fade_overpriced":
        return True
    return False


def _divergence_prediction(rule_name: str, row: Mapping[str, Any], threshold: float) -> int | None:
    divergence = float(row.get("divergence") or 0.0)
    if rule_name in {
        "kalshi_vs_consensus_favorite_underpriced",
        "kalshi_vs_consensus_underdog_underpriced",
    }:
        return 1 if divergence >= threshold else None
    if rule_name == "kalshi_vs_consensus_fade_overpriced":
        return 0 if -divergence >= threshold else None
    return None


def _evaluate_divergence_rule(
    *,
    rule_name: str,
    independent_rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    threshold: float,
    min_independent_labels: int,
    min_oos_labels: int,
    confidence_z: float,
) -> dict[str, Any]:
    n_independent = len(independent_rows)
    oos_scored = [
        row
        for row in oos_rows
        if _rule_applies(rule_name, row)
        and _divergence_prediction(rule_name, row, threshold) is not None
    ]
    n_oos = len(oos_scored)
    n_correct = sum(
        1
        for row in oos_scored
        if _divergence_prediction(rule_name, row, threshold) == row["settlement_outcome_for_side"]
    )
    null_rate = 0.5
    oos_accuracy = (n_correct / n_oos) if n_oos else None
    p_value = (
        binomial_survival(n_correct, n_oos, null_rate)
        if n_independent >= min_independent_labels and n_oos >= min_oos_labels
        else None
    )
    wilson = wilson_lower_bound(n_correct, n_oos, confidence_z) if n_oos else None
    if n_independent < min_independent_labels:
        status = "blocked_insufficient_independent_labels"
    elif n_oos < min_oos_labels:
        status = "blocked_insufficient_oos_labels"
    else:
        status = "testable_research_candidate"
    return {
        "candidate_rule": rule_name,
        "signal_key": rule_name,
        "model_id": f"{rule_name}_threshold_{threshold}",
        "threshold": float(threshold),
        "price_bucket": None,
        "null_rate": null_rate,
        "independent_label_count": n_independent,
        "oos_count": n_oos,
        "oos_correct_count": n_correct,
        "oos_accuracy": _json_float(oos_accuracy),
        "wilson_lower_bound": _json_float(wilson),
        "p_value": p_value,
        "q_value": None,
        "status": status,
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
        "research_only": True,
        "execution_enabled": False,
    }


def _evaluate_bucket_rule(
    *,
    bucket_name: str,
    bucket_low: float,
    bucket_high: float,
    independent_rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    min_independent_labels: int,
    min_oos_labels: int,
    confidence_z: float,
) -> dict[str, Any]:
    n_independent = len(independent_rows)

    def in_bucket(row: Mapping[str, Any]) -> bool:
        value = row.get("kalshi_mid_for_side")
        if value is None:
            return False
        return float(bucket_low) <= float(value) < float(bucket_high)

    applicable_oos = [row for row in oos_rows if in_bucket(row)]
    n_oos = len(applicable_oos)
    # Directional rule: predict YES for every contract in this bucket.
    n_correct = sum(1 for row in applicable_oos if row["settlement_outcome_for_side"] == 1)
    null_rate = (float(bucket_low) + float(bucket_high)) / 2.0
    oos_accuracy = (n_correct / n_oos) if n_oos else None
    p_value = (
        binomial_survival(n_correct, n_oos, null_rate)
        if n_independent >= min_independent_labels and n_oos >= min_oos_labels
        else None
    )
    wilson = wilson_lower_bound(n_correct, n_oos, confidence_z) if n_oos else None
    if n_independent < min_independent_labels:
        status = "blocked_insufficient_independent_labels"
    elif n_oos < min_oos_labels:
        status = "blocked_insufficient_oos_labels"
    else:
        status = "testable_research_candidate"
    return {
        "candidate_rule": "sports_consensus_price_bucket_bias",
        "signal_key": "sports_consensus_price_bucket_bias",
        "model_id": f"sports_consensus_price_bucket_bias_bucket_{bucket_name}",
        "threshold": None,
        "price_bucket": bucket_name,
        "price_bucket_low": float(bucket_low),
        "price_bucket_high": float(bucket_high),
        "null_rate": null_rate,
        "independent_label_count": n_independent,
        "oos_count": n_oos,
        "oos_correct_count": n_correct,
        "oos_accuracy": _json_float(oos_accuracy),
        "wilson_lower_bound": _json_float(wilson),
        "p_value": p_value,
        "q_value": None,
        "status": status,
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
        "research_only": True,
        "execution_enabled": False,
    }


def _evaluate_candidate_rules(
    *,
    independent_rows: Sequence[Mapping[str, Any]],
    in_sample_rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    thresholds: Sequence[float],
    price_buckets: Sequence[tuple[str, float, float]],
    min_independent_labels: int,
    min_oos_labels: int,
    confidence_z: float,
) -> list[dict[str, Any]]:
    evaluations: list[dict[str, Any]] = []
    divergence_rules = (
        "kalshi_vs_consensus_favorite_underpriced",
        "kalshi_vs_consensus_underdog_underpriced",
        "kalshi_vs_consensus_fade_overpriced",
    )
    for rule_name in divergence_rules:
        for threshold in thresholds:
            evaluations.append(
                _evaluate_divergence_rule(
                    rule_name=rule_name,
                    independent_rows=independent_rows,
                    oos_rows=oos_rows,
                    threshold=float(threshold),
                    min_independent_labels=min_independent_labels,
                    min_oos_labels=min_oos_labels,
                    confidence_z=confidence_z,
                )
            )
    for bucket_name, bucket_low, bucket_high in price_buckets:
        evaluations.append(
            _evaluate_bucket_rule(
                bucket_name=bucket_name,
                bucket_low=float(bucket_low),
                bucket_high=float(bucket_high),
                independent_rows=independent_rows,
                oos_rows=oos_rows,
                min_independent_labels=min_independent_labels,
                min_oos_labels=min_oos_labels,
                confidence_z=confidence_z,
            )
        )
    return evaluations


def _apply_fdr(evaluations: list[dict[str, Any]], *, fdr_alpha: float) -> None:
    testable_indices = [
        (idx, float(item["p_value"]))
        for idx, item in enumerate(evaluations)
        if item.get("p_value") is not None and item.get("status") == "testable_research_candidate"
    ]
    q_by_index = benjamini_hochberg(testable_indices)
    for idx, q_value in q_by_index.items():
        item = evaluations[idx]
        item["q_value"] = float(q_value)
        null_rate = float(item["null_rate"])
        oos_accuracy = item.get("oos_accuracy")
        if (
            oos_accuracy is not None
            and float(oos_accuracy) > null_rate
            and float(q_value) <= fdr_alpha
        ):
            item["status"] = "research_candidate_fdr_passed"


def _build_hypothesis_accumulation_plan(
    *,
    evaluations: Sequence[Mapping[str, Any]],
    min_independent_labels: int,
    min_oos_labels: int,
) -> list[dict[str, Any]]:
    """Name the pre-registered cells that need future exact labels.

    This is deliberately descriptive only. It does not add hypotheses, lower
    thresholds, or make current rows testable; it gives the collector a stable
    target list for the next settlement clocks.
    """
    rows: list[dict[str, Any]] = []
    for item in evaluations:
        independent_count = int(item.get("independent_label_count") or 0)
        oos_count = int(item.get("oos_count") or 0)
        independent_deficit = max(0, int(min_independent_labels) - independent_count)
        oos_deficit = max(0, int(min_oos_labels) - oos_count)
        if independent_deficit == 0 and oos_deficit == 0:
            continue
        rows.append(
            {
                "model_id": item.get("model_id"),
                "candidate_rule": item.get("candidate_rule"),
                "threshold": item.get("threshold"),
                "price_bucket": item.get("price_bucket"),
                "status": item.get("status"),
                "current_independent_label_count": independent_count,
                "required_independent_label_count": int(min_independent_labels),
                "independent_label_deficit": independent_deficit,
                "current_oos_label_count": oos_count,
                "required_oos_label_count": int(min_oos_labels),
                "oos_label_deficit": oos_deficit,
                "accumulation_target": (
                    "future exact Kalshi settlement labels matching this "
                    "pre-registered rule/threshold or price-bucket cell"
                ),
                "research_only": True,
                "usable": False,
            }
        )
    rows.sort(
        key=lambda row: (
            int(row["independent_label_deficit"]),
            int(row["oos_label_deficit"]),
            str(row.get("candidate_rule") or ""),
            float(row.get("threshold") or -1.0),
            str(row.get("price_bucket") or ""),
        )
    )
    return rows


def _build_hypothesis_accumulation_opportunities(
    *,
    accumulation_plan: Sequence[Mapping[str, Any]],
    consensus_observations: Sequence[Mapping[str, Any]],
    settlement_labels: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Map current pending observations to deficient pre-registered cells.

    These rows are not evidence yet. They are a routing surface for the
    collector: if the exact Kalshi contract later settles, the label will fill
    the named rule/threshold or bucket cell.
    """
    plan_rows = [
        item
        for item in accumulation_plan
        if int(item.get("independent_label_deficit") or 0) > 0
        or int(item.get("oos_label_deficit") or 0) > 0
    ]
    if not plan_rows:
        return []

    labeled_keys = {
        (str(label.get("contract_ticker") or "").strip(), _normalize_side(label.get("side")))
        for label in settlement_labels
        if str(label.get("contract_ticker") or "").strip()
    }
    latest_pending = _latest_pending_observations(
        consensus_observations=consensus_observations,
        labeled_keys=labeled_keys,
    )

    opportunities: list[dict[str, Any]] = []
    for plan_index, plan in enumerate(plan_rows):
        for row in latest_pending:
            if not _observation_matches_plan(row, plan):
                continue
            opportunities.append(
                {
                    "model_id": plan.get("model_id"),
                    "candidate_rule": plan.get("candidate_rule"),
                    "threshold": plan.get("threshold"),
                    "price_bucket": plan.get("price_bucket"),
                    "contract_ticker": row.get("contract_ticker"),
                    "event_ticker": row.get("event_ticker"),
                    "side": row.get("side"),
                    "sport_key": row.get("sport_key"),
                    "market_key": row.get("market_key"),
                    "cluster_key": row.get("cluster_key"),
                    "observed_utc": row.get("observed_utc"),
                    "close_time": row.get("close_time"),
                    "expected_expiration_time": row.get("expected_expiration_time"),
                    "kalshi_mid_for_side": _json_float(row.get("kalshi_mid_for_side")),
                    "consensus_probability_for_side": _json_float(
                        row.get(
                            "consensus_probability_for_side",
                            row.get("consensus_no_vig_probability_for_side"),
                        )
                    ),
                    "divergence": _json_float(
                        _finite_float(row.get("divergence"))
                        if row.get("divergence") is not None
                        else _opportunity_divergence(row)
                    ),
                    "book_count": row.get("book_count"),
                    "distinct_books": list(row.get("distinct_books") or []),
                    "current_oos_label_count": plan.get("current_oos_label_count"),
                    "oos_label_deficit": plan.get("oos_label_deficit"),
                    "opportunity_status": "pending_exact_kalshi_settlement_label",
                    "research_only": True,
                    "usable": False,
                    "_plan_index": plan_index,
                }
            )
    opportunities.sort(
        key=lambda item: (
            int(item.get("_plan_index") or 0),
            str(item.get("close_time") or item.get("expected_expiration_time") or ""),
            str(item.get("contract_ticker") or ""),
        )
    )
    for item in opportunities:
        item.pop("_plan_index", None)
    return opportunities


def _latest_pending_observations(
    *,
    consensus_observations: Sequence[Mapping[str, Any]],
    labeled_keys: set[tuple[str, str | None]],
) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in consensus_observations:
        ticker = str(row.get("contract_ticker") or "").strip()
        side = _normalize_side(row.get("side"))
        if not ticker or side is None or (ticker, side) in labeled_keys:
            continue
        consensus = _finite_float(
            row.get(
                "consensus_probability_for_side",
                row.get("consensus_no_vig_probability_for_side"),
            )
        )
        kalshi_mid = _finite_float(row.get("kalshi_mid_for_side"))
        observed_utc = _format_utc(_parse_utc(row.get("observed_utc")))
        if consensus is None or kalshi_mid is None or observed_utc is None:
            continue
        normalized = dict(row)
        normalized["contract_ticker"] = ticker
        normalized["side"] = side
        normalized["consensus_probability_for_side"] = consensus
        normalized["kalshi_mid_for_side"] = kalshi_mid
        normalized["observed_utc"] = observed_utc
        normalized["observed_ts"] = _parse_utc(observed_utc).timestamp()
        normalized["divergence"] = consensus - kalshi_mid
        key = (ticker, side)
        existing = latest.get(key)
        if existing is None or normalized["observed_ts"] > existing["observed_ts"]:
            latest[key] = normalized
    return list(latest.values())


def _observation_matches_plan(row: Mapping[str, Any], plan: Mapping[str, Any]) -> bool:
    rule = str(plan.get("candidate_rule") or "")
    if rule == "sports_consensus_price_bucket_bias":
        bucket = str(plan.get("price_bucket") or "")
        for bucket_name, low, high in DEFAULT_PRICE_BUCKETS:
            if bucket_name != bucket:
                continue
            mid = _finite_float(row.get("kalshi_mid_for_side"))
            return mid is not None and float(low) <= mid < float(high)
        return False
    threshold = _finite_float(plan.get("threshold"))
    return (
        threshold is not None
        and _rule_applies(rule, row)
        and _divergence_prediction(rule, row, threshold) is not None
    )


def _opportunity_divergence(row: Mapping[str, Any]) -> float | None:
    consensus = _finite_float(
        row.get("consensus_probability_for_side", row.get("consensus_no_vig_probability_for_side"))
    )
    kalshi_mid = _finite_float(row.get("kalshi_mid_for_side"))
    if consensus is None or kalshi_mid is None:
        return None
    return consensus - kalshi_mid


# ---------------------------------------------------------------------------
# Long-format evaluation rows (one per contract x hypothesis)
# ---------------------------------------------------------------------------


def _emit_evaluation_rows(
    *,
    independent_rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    thresholds: Sequence[float],
    price_buckets: Sequence[tuple[str, float, float]],
) -> list[dict[str, Any]]:
    """Emit one row per (independent contract, applicable hypothesis)."""
    oos_keys = {(row["contract_ticker"], row["side"]) for row in oos_rows}
    output: list[dict[str, Any]] = []
    divergence_rules = (
        "kalshi_vs_consensus_favorite_underpriced",
        "kalshi_vs_consensus_underdog_underpriced",
        "kalshi_vs_consensus_fade_overpriced",
    )
    for row in independent_rows:
        in_oos = (row["contract_ticker"], row["side"]) in oos_keys
        for rule_name in divergence_rules:
            if not _rule_applies(rule_name, row):
                continue
            for threshold in thresholds:
                prediction = _divergence_prediction(rule_name, row, float(threshold))
                correct = (
                    None
                    if prediction is None or not in_oos
                    else int(prediction == row["settlement_outcome_for_side"])
                )
                output.append(
                    _evaluation_row(
                        row=row,
                        candidate_rule=rule_name,
                        threshold=float(threshold),
                        price_bucket=None,
                        selected_side_prediction=prediction if in_oos else None,
                        correct=correct,
                    )
                )
        for bucket_name, bucket_low, bucket_high in price_buckets:
            kalshi_mid = row.get("kalshi_mid_for_side")
            if kalshi_mid is None or not (
                float(bucket_low) <= float(kalshi_mid) < float(bucket_high)
            ):
                continue
            prediction = 1  # bucket rule always predicts YES for side in bucket
            correct = int(prediction == row["settlement_outcome_for_side"]) if in_oos else None
            output.append(
                _evaluation_row(
                    row=row,
                    candidate_rule="sports_consensus_price_bucket_bias",
                    threshold=None,
                    price_bucket=bucket_name,
                    selected_side_prediction=prediction if in_oos else None,
                    correct=correct,
                )
            )
    output.sort(
        key=lambda r: (
            r["contract_ticker"],
            r["candidate_rule"],
            r["threshold"] if r["threshold"] is not None else -1.0,
            r["price_bucket"] or "",
        )
    )
    return output


def _evaluation_row(
    *,
    row: Mapping[str, Any],
    candidate_rule: str,
    threshold: float | None,
    price_bucket: str | None,
    selected_side_prediction: int | None,
    correct: int | None,
) -> dict[str, Any]:
    return {
        "contract_ticker": row["contract_ticker"],
        "event_ticker": row.get("event_ticker"),
        "family_id": FAMILY_ID,
        "model_id": (
            f"{candidate_rule}_threshold_{threshold}"
            if threshold is not None
            else f"{candidate_rule}_bucket_{price_bucket}"
        ),
        "signal_key": candidate_rule,
        "candidate_rule": candidate_rule,
        "threshold": threshold,
        "price_bucket": price_bucket,
        "side": row["side"],
        "kalshi_mid_for_side": _json_float(row.get("kalshi_mid_for_side")),
        "consensus_probability_for_side": _json_float(row.get("consensus_probability_for_side")),
        "divergence": _json_float(row.get("divergence")),
        "selected_side_prediction": selected_side_prediction,
        "settlement_outcome": row["settlement_outcome_for_side"],
        "correct": correct,
        "observed_utc": row.get("observed_utc"),
        "settlement_time_utc": row.get("settlement_time_utc"),
        "sport_key": row.get("sport_key"),
        "market_key": row.get("market_key"),
        "cluster_key": row.get("cluster_key"),
        "book_count": row.get("book_count"),
        "distinct_books": row.get("distinct_books"),
        "source_reference_sha256": row.get("source_reference_sha256"),
        "research_only": True,
        "usable": False,
    }


# ---------------------------------------------------------------------------
# Summary / gates / status
# ---------------------------------------------------------------------------


def _build_summary(
    *,
    preflight_summary: Mapping[str, Any],
    preflight_valid: int,
    consensus_observations: Sequence[Mapping[str, Any]],
    settlement_labels: Sequence[Mapping[str, Any]],
    joined_rows: Sequence[Mapping[str, Any]],
    independent_rows: Sequence[Mapping[str, Any]],
    in_sample_rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    join_blockers: Sequence[Mapping[str, Any]],
    evaluations: Sequence[Mapping[str, Any]],
    min_independent_labels: int,
    min_oos_labels: int,
    test_fraction: float,
    fdr_alpha: float,
    hypothesis_accumulation_plan: Sequence[Mapping[str, Any]],
    hypothesis_accumulation_opportunities: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    testable_count = sum(
        1 for item in evaluations if item.get("status") == "testable_research_candidate"
    )
    survivor_count = sum(
        1 for item in evaluations if item.get("status") == "research_candidate_fdr_passed"
    )
    tested_hypothesis_count = sum(1 for item in evaluations if item.get("p_value") is not None)
    status_counts = Counter(str(item.get("status") or "unknown") for item in evaluations)
    max_hypothesis_oos_count = max(
        (int(item.get("oos_count") or 0) for item in evaluations),
        default=0,
    )
    nearest_oos_deficit = min(
        (
            int(item.get("oos_label_deficit") or 0)
            for item in hypothesis_accumulation_plan
            if int(item.get("oos_label_deficit") or 0) > 0
        ),
        default=0,
    )
    nearest_model_id = None
    nearest_deficit = None
    for item in hypothesis_accumulation_plan:
        deficit = int(item.get("oos_label_deficit") or 0)
        if deficit <= 0:
            continue
        if nearest_deficit is None or deficit < nearest_deficit:
            nearest_deficit = deficit
            nearest_model_id = str(item.get("model_id") or "")
    opportunities_by_model = Counter(
        str(item.get("model_id") or "") for item in hypothesis_accumulation_opportunities
    )
    return {
        "preflight_valid_candidate_count": preflight_valid,
        "preflight_reference_row_count": int(preflight_summary.get("reference_row_count") or 0),
        "preflight_distinct_book_count": int(preflight_summary.get("distinct_book_count") or 0),
        "consensus_observation_count": len(consensus_observations),
        "settlement_label_count": len(settlement_labels),
        "joined_label_count": len(joined_rows),
        "independent_label_count": len(independent_rows),
        "in_sample_label_count": len(in_sample_rows),
        "oos_label_count": len(oos_rows),
        "join_blocker_count": len(join_blockers),
        "candidate_rule_count": len(CANDIDATE_RULES),
        "tested_hypothesis_count": tested_hypothesis_count,
        "testable_candidate_count": testable_count,
        "fdr_survivor_count": survivor_count,
        "evaluation_status_counts": dict(sorted(status_counts.items())),
        "max_hypothesis_oos_count": max_hypothesis_oos_count,
        "hypothesis_accumulation_plan_count": len(hypothesis_accumulation_plan),
        "nearest_hypothesis_oos_deficit": nearest_oos_deficit,
        "nearest_hypothesis_model_id": nearest_model_id,
        "hypothesis_accumulation_opportunity_count": len(
            hypothesis_accumulation_opportunities
        ),
        "hypothesis_accumulation_opportunity_distinct_contract_count": len(
            {
                str(item.get("contract_ticker") or "")
                for item in hypothesis_accumulation_opportunities
                if item.get("contract_ticker")
            }
        ),
        "nearest_hypothesis_current_opportunity_count": int(
            opportunities_by_model.get(str(nearest_model_id or ""), 0)
        ),
        "fdr_alpha": float(fdr_alpha),
        "min_independent_labels": int(min_independent_labels),
        "min_oos_labels": int(min_oos_labels),
        "test_fraction": float(test_fraction),
    }


def _build_gates(
    *,
    preflight_present: bool,
    preflight_valid: int,
    summary: Mapping[str, Any],
    evaluations: Sequence[Mapping[str, Any]],
    observation_dir: Path | None,
    label_dir: Path | None,
) -> list[dict[str, str]]:
    joined = int(summary.get("joined_label_count") or 0)
    independent = int(summary.get("independent_label_count") or 0)
    min_independent = int(summary.get("min_independent_labels") or 0)
    min_oos = int(summary.get("min_oos_labels") or 0)
    oos = int(summary.get("oos_label_count") or 0)
    testable = int(summary.get("testable_candidate_count") or 0)
    survivor = int(summary.get("fdr_survivor_count") or 0)
    return [
        _gate(
            "preflight_artifact_present",
            "pass" if preflight_present else "blocked",
            "Sports consensus preflight artifact is present."
            if preflight_present
            else "Sports consensus preflight artifact is missing.",
        ),
        _gate(
            "preflight_valid_candidates",
            "pass" if preflight_valid > 0 else "blocked",
            f"Preflight reports {preflight_valid} valid candidate(s).",
        ),
        _gate(
            "consensus_observations_with_settlement_labels",
            "pass" if joined > 0 else "blocked",
            f"{joined} joined observation+settlement row(s).",
        ),
        _gate(
            "independent_label_minimum",
            "pass" if independent >= min_independent else "blocked",
            f"{independent} independent contract label(s); minimum is {min_independent}.",
        ),
        _gate(
            "oos_label_minimum",
            "pass" if oos >= min_oos else "blocked",
            f"{oos} OOS label(s); minimum is {min_oos}.",
        ),
        _gate(
            "testable_candidate_present",
            "pass" if testable > 0 else "blocked",
            f"{testable} testable candidate(s) reached the binomial scoring step.",
        ),
        _gate(
            "fdr_control_applied",
            "pass" if survivor >= 0 else "blocked",
            "Benjamini-Hochberg FDR applied across all testable hypotheses.",
        ),
        _gate(
            "no_usable_ev_sizing_or_execution",
            "pass"
            if all(
                item.get("usable") is False
                and item.get("calibrated_probability") is None
                and item.get("expected_value_per_contract") is None
                for item in evaluations
            )
            else "fail",
            "Falsification output remains research-only with no EV, sizing, or execution.",
        ),
        _gate(
            "observation_dir_outside_repo",
            "pass" if observation_dir is None or _outside_repo(observation_dir) else "blocked",
            "Consensus observation packets must stay outside the repo.",
        ),
        _gate(
            "label_dir_outside_repo",
            "pass" if label_dir is None or _outside_repo(label_dir) else "blocked",
            "Settlement label packets must stay outside the repo.",
        ),
    ]


def _status(
    *,
    preflight_present: bool,
    preflight_valid: int,
    gates: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    evaluations: Sequence[Mapping[str, Any]],
) -> str:
    if any(item.get("status") == "fail" for item in gates):
        return "sports_consensus_falsification_failed_safety_gate"
    if not preflight_present:
        return "sports_consensus_falsification_blocked_missing_inputs"
    if preflight_valid <= 0:
        return "sports_consensus_falsification_blocked_no_valid_consensus_rows"
    independent = int(summary.get("independent_label_count") or 0)
    min_independent = int(summary.get("min_independent_labels") or 0)
    oos = int(summary.get("oos_label_count") or 0)
    min_oos = int(summary.get("min_oos_labels") or 0)
    if independent < min_independent:
        return "sports_consensus_falsification_blocked_insufficient_labels"
    if oos < min_oos:
        return "sports_consensus_falsification_blocked_insufficient_labels"
    if not any(
        item.get("status") in {"testable_research_candidate", "research_candidate_fdr_passed"}
        for item in evaluations
    ):
        return "sports_consensus_falsification_blocked_no_testable_hypotheses"
    if int(summary.get("fdr_survivor_count") or 0) > 0:
        return "sports_consensus_falsification_ready_with_research_candidates"
    return "sports_consensus_falsification_ready_no_research_candidates"


def _best_survivor(
    evaluations: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    survivors = [
        item for item in evaluations if item.get("status") == "research_candidate_fdr_passed"
    ]
    if not survivors:
        return None
    survivors.sort(
        key=lambda item: (
            float(item.get("q_value") or 1.0),
            -float(item.get("oos_accuracy") or 0.0),
            str(item.get("candidate_rule")),
            float(item.get("threshold") or -1.0),
        )
    )
    return dict(survivors[0])


def _next_action(status: str) -> dict[str, str]:
    if status.startswith("sports_consensus_falsification_failed"):
        return {
            "name": "kalshi_sports_consensus_falsification_safety_audit",
            "why": "Safety gate failure detected: at least one evaluation produced a non-research flag.",
            "stop_condition": "Stop before continuing accumulation while safety flags are violated.",
        }
    if status == "sports_consensus_falsification_blocked_missing_inputs":
        return {
            "name": "kalshi_sports_consensus_preflight_refresh",
            "why": "Preflight artifact is missing; rebuild the no-vig consensus reference and preflight before falsification.",
            "stop_condition": "Stop before lowering consensus admission gates or accepting a single-book reference.",
        }
    if status == "sports_consensus_falsification_blocked_no_valid_consensus_rows":
        return {
            "name": "kalshi_sports_consensus_reference_rebuild",
            "why": "Preflight is present but admits zero valid consensus rows.",
            "stop_condition": "Stop before treating any sportsbook row as a tradable probability.",
        }
    if status == "sports_consensus_falsification_blocked_insufficient_labels":
        return {
            "name": "kalshi_sports_consensus_label_accumulation",
            "why": "Exact Kalshi settlement labels are still insufficient for OOS/FDR falsification.",
            "stop_condition": "Stop before treating duplicate contract labels as independent evidence or using non-Kalshi labels.",
        }
    if status == "sports_consensus_falsification_blocked_no_testable_hypotheses":
        return {
            "name": "kalshi_sports_consensus_rule_bucket_label_accumulation",
            "why": (
                "Global independent/OOS label floors are met, but no pre-registered "
                "rule or price bucket has enough applicable OOS labels to enter FDR."
            ),
            "stop_condition": "Stop before lowering per-hypothesis OOS floors or adding post-hoc rules.",
        }
    if status == "sports_consensus_falsification_ready_with_research_candidates":
        return {
            "name": "kalshi_sports_consensus_ev_ledger_promotion_audit",
            "why": "At least one candidate survived OOS/FDR. The next step is a separate EV ledger promotion gate with its own tests.",
            "stop_condition": "Stop before paper sizing, capacity/correlation/cluster control, or live execution until those gates are added.",
        }
    return {
        "name": "kalshi_sports_consensus_label_accumulation",
        "why": "Rules are testable but no candidate survived FDR; continue accumulating exact settlement labels.",
        "stop_condition": "Stop before lowering thresholds to force a survivor.",
    }


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def render_sports_consensus_falsification_markdown(
    report: Mapping[str, Any],
) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    inputs = report.get("inputs", {}) if isinstance(report.get("inputs"), Mapping) else {}
    survivor = (
        report.get("best_survivor") if isinstance(report.get("best_survivor"), Mapping) else {}
    )
    accumulation_plan = [
        item
        for item in report.get("hypothesis_accumulation_plan", [])
        if isinstance(item, Mapping)
    ]
    accumulation_opportunities = [
        item
        for item in report.get("hypothesis_accumulation_opportunities", [])
        if isinstance(item, Mapping)
    ]
    lines = [
        "# Kalshi Sports Consensus Falsification Ledger",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Family: `{report.get('family_id')}`",
        "- Mode: research-only",
        "- Execution enabled: `false`",
        "",
        "## Doctrine",
        "",
        "- The sharp timestamp-matched multi-book no-vig consensus line is the primary sports probability source.",
        "- This ledger does NOT promote any row to EV/paper/live; it only emits FDR-controlled research candidates.",
        "- Internal projection/Elo/simulation probabilities are not the primary sports model and are not assessed here.",
        "",
        "## Inputs",
        "",
        f"- Preflight valid candidates: `{inputs.get('preflight_valid_candidate_count')}`",
        f"- Consensus observations: `{inputs.get('consensus_observation_count')}`",
        f"- Settlement labels: `{inputs.get('settlement_label_count')}`",
        f"- Joined label rows: `{summary.get('joined_label_count')}`",
        f"- Independent contract labels: `{summary.get('independent_label_count')}`",
        f"- In-sample labels: `{summary.get('in_sample_label_count')}`",
        f"- OOS labels: `{summary.get('oos_label_count')}`",
        "",
        "## Summary",
        "",
        f"- Candidate rules: `{summary.get('candidate_rule_count')}`",
        f"- Tested hypotheses: `{summary.get('tested_hypothesis_count')}`",
        f"- Testable candidates: `{summary.get('testable_candidate_count')}`",
        f"- Max hypothesis OOS labels: `{summary.get('max_hypothesis_oos_count')}`",
        f"- Hypothesis accumulation plan rows: `{summary.get('hypothesis_accumulation_plan_count')}`",
        f"- Nearest hypothesis OOS deficit: `{summary.get('nearest_hypothesis_oos_deficit')}`",
        f"- Nearest hypothesis model: `{summary.get('nearest_hypothesis_model_id')}`",
        f"- Current accumulation opportunities: `{summary.get('hypothesis_accumulation_opportunity_count')}`",
        f"- Current opportunity contracts: `{summary.get('hypothesis_accumulation_opportunity_distinct_contract_count')}`",
        f"- Nearest hypothesis current opportunities: `{summary.get('nearest_hypothesis_current_opportunity_count')}`",
        f"- Evaluation status counts: `{summary.get('evaluation_status_counts')}`",
        f"- FDR survivors: `{summary.get('fdr_survivor_count')}`",
        f"- FDR alpha: `{summary.get('fdr_alpha')}`",
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
            "## Best Survivor",
            "",
        ]
    )
    if survivor:
        lines.extend(
            [
                f"- Candidate rule: `{survivor.get('candidate_rule')}`",
                f"- Threshold: `{survivor.get('threshold')}`",
                f"- Price bucket: `{survivor.get('price_bucket')}`",
                f"- OOS accuracy: `{survivor.get('oos_accuracy')}`",
                f"- p-value: `{survivor.get('p_value')}`",
                f"- q-value: `{survivor.get('q_value')}`",
            ]
        )
    else:
        lines.append("- _No FDR survivor identified._")
    lines.extend(
        [
            "",
            "## Accumulation Plan",
            "",
        ]
    )
    if accumulation_plan:
        lines.extend(
            [
                "| Candidate Rule | Threshold | Price Bucket | Current OOS | OOS Deficit |",
                "| --- | ---: | --- | ---: | ---: |",
            ]
        )
        for item in accumulation_plan[:10]:
            lines.append(
                "| "
                f"`{item.get('candidate_rule')}` | "
                f"`{item.get('threshold')}` | "
                f"`{item.get('price_bucket')}` | "
                f"`{item.get('current_oos_label_count')}` | "
                f"`{item.get('oos_label_deficit')}` |"
            )
    else:
        lines.append("- _No accumulation deficit for pre-registered hypotheses._")
    lines.extend(
        [
            "",
            "## Current Accumulation Opportunities",
            "",
        ]
    )
    if accumulation_opportunities:
        lines.extend(
            [
                "| Model | Contract | Side | Sport | Close | Kalshi Mid | Consensus |",
                "| --- | --- | --- | --- | --- | ---: | ---: |",
            ]
        )
        for row in accumulation_opportunities[:20]:
            lines.append(
                "| "
                f"`{row.get('model_id')}` | "
                f"`{row.get('contract_ticker')}` | "
                f"`{row.get('side')}` | "
                f"`{row.get('sport_key')}` | "
                f"`{row.get('close_time') or row.get('expected_expiration_time')}` | "
                f"`{row.get('kalshi_mid_for_side')}` | "
                f"`{row.get('consensus_probability_for_side')}` |"
            )
    else:
        lines.append("- _No current pending observations match deficient pre-registered cells._")
    next_action = (
        report.get("next_action") if isinstance(report.get("next_action"), Mapping) else {}
    )
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            f"- Name: `{next_action.get('name')}`",
            f"- Why: {next_action.get('why')}",
            f"- Stop condition: {next_action.get('stop_condition')}",
            "",
            "> Research-only falsification ledger. No stake, order, account, or execution path is authorized by this artifact.",
            "",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_side(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text not in {"yes", "no"}:
        return None
    return text


def _finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _json_float(value: Any) -> float | None:
    number = _finite_float(value)
    return None if number is None else float(number)


def _parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_now() -> str:
    return _format_utc(datetime.now(UTC)) or ""


def _derive_event_ticker(ticker: str) -> str | None:
    if not ticker:
        return None
    parts = ticker.split("-")
    if len(parts) >= 2:
        return parts[0] + "-" + parts[1]
    return parts[0] if parts else None


def _derive_sport_key(ticker: str) -> str:
    text = (ticker or "").upper()
    if text.startswith("KXMLB") or text.startswith("KXLMB") or text.startswith("KXKBO"):
        return "mlb"
    if text.startswith("KXATP") or text.startswith("KXWIM"):
        return "atp"
    if text.startswith("KXWC") or text.startswith("KXFIFA"):
        return "world_cup"
    if text.startswith("KXNFL"):
        return "nfl"
    if text.startswith("KXNBA"):
        return "nba"
    if text.startswith("KNFL"):
        return "nfl"
    return "other"


def _derive_market_key(ticker: str) -> str | None:
    if not ticker:
        return None
    head = ticker.split("-", 1)[0]
    return head or None


def _build_cluster_key(
    ticker: str,
    obs: Mapping[str, Any],
    label: Mapping[str, Any],
) -> str:
    sport_key = obs.get("sport_key") or _derive_sport_key(ticker)
    market_key = obs.get("market_key") or label.get("series_ticker") or _derive_market_key(ticker)
    event_ticker = (
        obs.get("event_ticker") or label.get("event_ticker") or _derive_event_ticker(ticker)
    )
    return f"{sport_key}|{market_key}|{event_ticker}"


def _outside_repo(path: Path) -> bool:
    try:
        path.expanduser().resolve().relative_to(Path(__file__).resolve().parents[1])
    except ValueError:
        return True
    return False


def _gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}
