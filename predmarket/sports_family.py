"""SportsBaseballFamily — the sports (baseball) signal family descriptor.

Aggregates the sports lane's family-specific elements: statsapi/ESPN fetcher,
strength-model prediction rule, league|game_winner|date cluster key, and
sports model evaluators.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from predmarket.shared_helpers import bucket_time, outcome_value
from predmarket.signal_family import SignalFamily

SPORTS_OFFICIAL_SETTLEMENT_SOURCE = "official game result (league box score)"

# ── Classification tags ──────────────────────────────────────────────────

SPORTS_CLASSIFICATION_TAGS = ("KXMLBGAME", "KXKBOGAME", "KXLMBGAME")


# ── Prediction rule ──────────────────────────────────────────────────────
# (Placeholder — the full strength-model sigmoid rule lives in the sports
#  scripts and is wired into the descriptor at construction time.)


def sports_default_prediction_rule(row: Mapping[str, Any]) -> tuple[int | None, float | None]:
    """Default sports prediction rule (placeholder).

    The full strength-model sigmoid rule with frozen coefficients is injected
    by the sports scripts at ``SignalFamily`` construction time.
    """
    side = row.get("predicted_side")
    if side == "yes":
        return 1, row.get("win_probability")
    if side == "no":
        return 0, row.get("win_probability")
    return None, None


def mlb_platform_prediction_rule(row: Mapping[str, Any]) -> tuple[int | None, float | None]:
    """Prediction rule for optional MLB-platform model bridge rows."""
    side = row.get("mlb_platform_predicted_side")
    probability = row.get("mlb_platform_model_probability")
    if side == "yes":
        return 1, probability
    if side == "no":
        return 0, probability
    return None, probability


# ── Cluster-key composer ─────────────────────────────────────────────────


def sports_cluster_key_composer(row: Mapping[str, Any]) -> str:
    """Compose correlation cluster key: league|game_winner|date."""
    return "|".join(
        str(part or "unknown")
        for part in (
            row.get("league", row.get("series_ticker", "unknown")),
            row.get("game_winner", row.get("contract_ticker", "unknown")),
            bucket_time(row.get("close_time")),
        )
    )


# ── Model evaluator ──────────────────────────────────────────────────────


def evaluate_strength_win_prob(
    *,
    rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    prediction_rule: Any = None,
    min_independent_labels: int = 30,
    min_oos_labels: int = 10,
) -> dict[str, Any]:
    """Evaluate sports strength-model directional accuracy on OOS rows."""
    from predmarket.shared_helpers import binomial_survival

    scored = [
        row
        for row in oos_rows
        if prediction_rule is not None and prediction_rule(row)[0] is not None
    ]
    wins = 0
    for row in scored:
        pred, _ = prediction_rule(row) if prediction_rule else (None, None)
        outcome = outcome_value(row.get("yes_outcome"))
        if pred is not None and outcome is not None:
            if pred == outcome:
                wins += 1
    p_value = (
        binomial_survival(wins, len(scored), 0.5)
        if len(rows) >= min_independent_labels and len(scored) >= min_oos_labels
        else None
    )
    if len(rows) < min_independent_labels:
        status = "blocked_insufficient_independent_labels"
    elif len(scored) < min_oos_labels:
        status = "blocked_insufficient_oos_labels"
    else:
        status = "testable_research_candidate"
    return {
        "model_id": "strength_win_prob_directional_accuracy",
        "status": status,
        "independent_label_count": len(rows),
        "oos_count": len(scored),
        "oos_correct_count": wins,
        "oos_accuracy": wins / len(scored) if scored else None,
        "p_value": p_value,
        "q_value": None,
        "feature_rule": "Predict YES when strength-model win_prob - yes_ask >= +tau; NO when <= -tau.",
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


def evaluate_mlb_platform_model(
    *,
    rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    prediction_rule: Any = None,
    min_independent_labels: int = 30,
    min_oos_labels: int = 10,
) -> dict[str, Any]:
    """Evaluate optional MLB-platform model bridge directional accuracy."""
    from predmarket.shared_helpers import binomial_survival

    scored = [row for row in oos_rows if mlb_platform_prediction_rule(row)[0] is not None]
    wins = 0
    for row in scored:
        pred, _ = mlb_platform_prediction_rule(row)
        outcome = outcome_value(row.get("yes_outcome"))
        if pred is not None and outcome is not None and pred == outcome:
            wins += 1
    p_value = (
        binomial_survival(wins, len(scored), 0.5)
        if len(rows) >= min_independent_labels and len(scored) >= min_oos_labels
        else None
    )
    if len(rows) < min_independent_labels:
        status = "blocked_insufficient_independent_labels"
    elif len(scored) < min_oos_labels:
        status = "blocked_insufficient_oos_labels"
    else:
        status = "testable_research_candidate"
    return {
        "model_id": "mlb_platform_model_directional_accuracy",
        "status": status,
        "independent_label_count": len(rows),
        "oos_count": len(scored),
        "oos_correct_count": wins,
        "oos_accuracy": wins / len(scored) if scored else None,
        "p_value": p_value,
        "q_value": None,
        "feature_rule": "Optional MLB-platform model artifact probability; predict YES/NO from its contract-keyed selected-team probability.",
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


SPORTS_MODEL_EVALUATORS: list[dict[str, Any]] = [
    {
        "model_id": "strength_win_prob_directional_accuracy",
        "evaluate_fn": evaluate_strength_win_prob,
    },
    {
        "model_id": "mlb_platform_model_directional_accuracy",
        "evaluate_fn": evaluate_mlb_platform_model,
    },
]


# ── SportsBaseballFamily factory ─────────────────────────────────────────


def make_sports_family(**overrides: Any) -> SignalFamily:
    """Factory that returns the canonical SportsBaseballFamily descriptor.

    Accepts optional overrides (e.g. for tests to inject a prediction_rule).
    """
    import dataclasses

    base = SignalFamily(
        family_id="sports_baseball",
        status_prefix="sports_proxy",
        classification_tag=list(SPORTS_CLASSIFICATION_TAGS),
        official_settlement_source=SPORTS_OFFICIAL_SETTLEMENT_SOURCE,
        reference_source_registry={},
        fetcher=None,
        feature_definitions={},
        prediction_rule=sports_default_prediction_rule,
        model_evaluators=list(SPORTS_MODEL_EVALUATORS),
        cluster_key_composer=sports_cluster_key_composer,
    )
    if overrides:
        return dataclasses.replace(base, **overrides)
    return base
