"""FavoriteLongshotBiasFamily - the favorite-longshot bias signal family.

Hypothesis: low-price Kalshi contracts (below ~50c) underperform their
midpoint breakeven rate (they settle NO more often than the market implies),
while high-price contracts (above ~50c) overperform (they settle YES more
often than implied).  This is the classic favorite-longshot bias observed in
prediction markets - the crowd overprices longshots (low probability) and
underprices favorites (high probability).

Falsification: chronological OOS split, price-bucket grouping via
``DEFAULT_PRICE_BUCKETS`` from ``sports_consensus_falsification.py``,
binomial scoring against each bucket's midpoint null-rate, and BH-FDR control
across all buckets.

Acceptance criteria: a bucket evaluator graduates from
``testable_research_candidate`` to ``research_candidate_fdr_passed`` only
when (a) BH q-value ≤ 0.10 and (b) OOS directional accuracy exceeds the
bucket's null-rate midpoint.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from predmarket.shared_helpers import binomial_survival, outcome_value, wilson_lower_bound
from predmarket.signal_family import SignalFamily
from predmarket.sports_consensus_falsification import DEFAULT_PRICE_BUCKETS

FAMILY_ID = "favorite_longshot_bias"
STATUS_PREFIX = "favorite_longshot_bias"
FAVORITE_LONGSHOT_OFFICIAL_SETTLEMENT_SOURCE = "Kalshi public settlement"

# Price threshold separating "low" (NO-predict) from "high" (YES-predict).
MEDIAN_PRICE_THRESHOLD = 0.50

# Re-export for downstream consumers.
EVALUATOR_MODEL_ID_PREFIX = f"{FAMILY_ID}_bucket"


# ── Prediction rule ──────────────────────────────────────────────────────


def favorite_longshot_prediction_rule(
    row: Mapping[str, Any],
) -> tuple[int | None, float | None]:
    """Favorite-longshot bias prediction rule.

    Returns (0, None) — predict NO — for contracts whose price is below the
    median threshold (50c).  Returns (1, None) — predict YES — for contracts
    at or above the median threshold.  Returns (None, None) when the row
    has no ``kalshi_mid_for_side`` or it is non-numeric.
    """
    value = row.get("kalshi_mid_for_side")
    if value is None:
        return None, None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None, None
    if price < MEDIAN_PRICE_THRESHOLD:
        return 0, None
    return 1, None


# ── Bucket evaluator factory ─────────────────────────────────────────────


def _make_favorite_longshot_bucket_evaluate_fn(
    bucket_name: str,
    bucket_low: float,
    bucket_high: float,
) -> Callable[..., dict[str, Any]]:
    """Create an evaluate_fn for a single price bucket.

    The returned callable has the same signature as other family evaluators:
    ``evaluate_fn(*, rows, oos_rows, prediction_rule, min_independent_labels,
    min_oos_labels)``.
    """

    def _in_bucket(row: Mapping[str, Any]) -> bool:
        value = row.get("kalshi_mid_for_side")
        if value is None:
            return False
        try:
            return float(bucket_low) <= float(value) < float(bucket_high)
        except (TypeError, ValueError):
            return False

    def evaluate_fn(
        *,
        rows: Sequence[Mapping[str, Any]],
        oos_rows: Sequence[Mapping[str, Any]],
        prediction_rule: Callable[[Mapping[str, Any]], tuple[int | None, float | None]]
        | None = None,
        min_independent_labels: int = 30,
        min_oos_labels: int = 10,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Evaluate favorite-longshot bias for this price bucket on OOS rows."""
        n_independent = len(rows)
        applicable_oos = [row for row in oos_rows if _in_bucket(row)]
        n_oos = len(applicable_oos)

        # Apply prediction rule to each OOS row and count correct predictions.
        n_correct = 0
        for row in applicable_oos:
            if prediction_rule is None:
                continue
            pred, _ = prediction_rule(row)
            outcome = outcome_value(row.get("yes_outcome"))
            if pred is not None and outcome is not None and pred == outcome:
                n_correct += 1

        null_rate = (bucket_low + bucket_high) / 2.0
        oos_accuracy = n_correct / n_oos if n_oos else None

        p_value = (
            binomial_survival(n_correct, n_oos, null_rate)
            if n_independent >= min_independent_labels and n_oos >= min_oos_labels
            else None
        )

        wilson = wilson_lower_bound(n_correct, n_oos, 1.6448536269514722) if n_oos else None

        if n_independent < min_independent_labels:
            status = "blocked_insufficient_independent_labels"
        elif n_oos < min_oos_labels:
            status = "blocked_insufficient_oos_labels"
        else:
            status = "testable_research_candidate"

        return {
            "model_id": f"{EVALUATOR_MODEL_ID_PREFIX}_{bucket_name}",
            "candidate_rule": f"{FAMILY_ID}_price_bucket_bias",
            "signal_key": f"{FAMILY_ID}_price_bucket_bias",
            "price_bucket": bucket_name,
            "price_bucket_low": bucket_low,
            "price_bucket_high": bucket_high,
            "null_rate": null_rate,
            "independent_label_count": n_independent,
            "oos_count": n_oos,
            "oos_correct_count": n_correct,
            "oos_accuracy": oos_accuracy,
            "wilson_lower_bound": wilson,
            "p_value": p_value,
            "q_value": None,
            "status": status,
            "usable": False,
            "calibrated_probability": None,
            "expected_value_per_contract": None,
            "research_only": True,
            "execution_enabled": False,
        }

    return evaluate_fn


# ── Model evaluators (one per price bucket) ──────────────────────────────

FAVORITE_LONGSHOT_MODEL_EVALUATORS: list[dict[str, Any]] = [
    {
        "model_id": f"{EVALUATOR_MODEL_ID_PREFIX}_{name}",
        "evaluate_fn": _make_favorite_longshot_bucket_evaluate_fn(name, low, high),
    }
    for name, low, high in DEFAULT_PRICE_BUCKETS
]


# ── Cluster-key composer ─────────────────────────────────────────────────


def favorite_longshot_cluster_key_composer(row: Mapping[str, Any]) -> str:
    """Compose correlation cluster key: price_bucket | event_ticker.

    Groups contracts that share a price bucket AND the same event/market,
    controlling within-bucket correlation since multiple contracts in the
    same bucket for the same event will have highly correlated outcomes.
    """
    price = row.get("kalshi_mid_for_side")
    bucket = _resolve_price_bucket(price)
    event = str(row.get("event_ticker") or row.get("series_ticker") or "unknown")
    return f"{bucket}|{event}"


def _resolve_price_bucket(price: Any) -> str:
    """Resolve a price to its bucket name, or 'unknown' if out of range."""
    if price is None:
        return "unknown"
    try:
        p = float(price)
    except (TypeError, ValueError):
        return "unknown"
    for name, low, high in DEFAULT_PRICE_BUCKETS:
        if low <= p < high:
            return name
    return "unknown"


# ── FavoriteLongshotBiasFamily factory ───────────────────────────────────


def make_favorite_longshot_family(**overrides: Any) -> SignalFamily:
    """Factory that returns the canonical FavoriteLongshotBiasFamily descriptor.

    Accepts optional overrides (e.g. for tests to inject a custom
    ``prediction_rule`` or ``model_evaluators``).
    """
    import dataclasses

    base = SignalFamily(
        family_id=FAMILY_ID,
        status_prefix=STATUS_PREFIX,
        classification_tag="",
        official_settlement_source=FAVORITE_LONGSHOT_OFFICIAL_SETTLEMENT_SOURCE,
        reference_source_registry={},
        fetcher=None,
        feature_definitions={},
        prediction_rule=favorite_longshot_prediction_rule,
        model_evaluators=list(FAVORITE_LONGSHOT_MODEL_EVALUATORS),
        cluster_key_composer=favorite_longshot_cluster_key_composer,
    )
    if overrides:
        return dataclasses.replace(base, **overrides)
    return base
