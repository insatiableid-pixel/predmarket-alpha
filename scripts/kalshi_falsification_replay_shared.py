"""Shared generic helpers for Kalshi signal-factory falsification and replay.

This module contains generic label-loading, replay-math, and scaffolding
helpers that are family-agnostic.  Shared statistical helpers have been
single-sourced to ``predmarket.shared_helpers`` — this module imports them
from there rather than defining them locally (strangler-fig).

The functions here are parameterized by:
- model_evaluators: a list of callables(rows, oos_rows, min_independent_labels, min_oos_labels) -> dict
- prediction_rule: a callable(row) -> int | None (1=YES, 0=NO, None=no prediction)
- cluster_key_composer: a callable(row) -> str
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = CONTROL_REPO / "scripts"
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Single-sourced shared helpers from the engine.
from predmarket.kalshi_execution_cost import normalize_kalshi_execution_cost  # noqa: E402
from predmarket.shared_helpers import (  # noqa: E402
    benjamini_hochberg,
    binomial_survival,
    chronological_split_index,
    counts,
    gate,
    independent_contract_rows,
    iso_from_timestamp,
    json_float,
    mean,
    median,
    optional_float,
    outcome_value,
    positive_number,
    probability,
    read_json_or_empty,
    safe_research_artifact,
    safety_flags,
    timestamp,
    wilson_lower_bound,
)
from predmarket.shared_helpers import (
    bucket_time as _shared_bucket_time,
)
from predmarket.shared_helpers import (
    outside_repo as _shared_outside_repo,
)

# ---------------------------------------------------------------------------
# Binding threshold constants (shared, do NOT change)
# ---------------------------------------------------------------------------
DEFAULT_MIN_INDEPENDENT_LABELS = 30
DEFAULT_MIN_OOS_LABELS = 10
DEFAULT_TEST_FRACTION = 0.30
DEFAULT_FDR_ALPHA = 0.10
DEFAULT_CONFIDENCE_Z = 1.6448536269514722
DEFAULT_MIN_SIDE_OOS_LABELS = 30
DEFAULT_MIN_DECAY_BUCKETS = 3
DEFAULT_MIN_DECAY_LABELS = 100

# ---------------------------------------------------------------------------
# Compatibility wrappers (where shared_helpers signatures differ)
# ---------------------------------------------------------------------------


def bucket_time(value: Any) -> str | None:
    """Wrapper matching the legacy single-arg signature."""
    return _shared_bucket_time(value)


def outside_repo(path: Path) -> bool:
    """Wrapper that passes the module-level CONTROL_REPO to the single-sourced helper."""
    return _shared_outside_repo(path, CONTROL_REPO)


# ---------------------------------------------------------------------------
# Label loading and normalization (generic)
# ---------------------------------------------------------------------------


def load_label_packets(label_dir: Path) -> dict[str, Any]:
    rows: list[Mapping[str, Any]] = []
    packet_paths: list[str] = []
    unsafe_packets: list[dict[str, str]] = []
    if not label_dir.exists():
        return {"packet_count": 0, "packet_paths": [], "rows": [], "unsafe_packets": []}
    for path in sorted(label_dir.glob("*.json")):
        payload = read_json_or_empty(path)
        if not safe_research_artifact(payload):
            unsafe_packets.append({"path": str(path), "reason": "unsafe_or_missing_research_flags"})
            continue
        packet_rows = payload.get("rows", [])
        if not isinstance(packet_rows, list):
            unsafe_packets.append({"path": str(path), "reason": "missing_rows_list"})
            continue
        packet_paths.append(str(path))
        rows.extend(row for row in packet_rows if isinstance(row, Mapping))
    return {
        "packet_count": len(packet_paths),
        "packet_paths": packet_paths,
        "rows": rows,
        "unsafe_packets": unsafe_packets,
    }


def normalize_label_rows(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for row in rows:
        errors: list[str] = []
        ticker = str(row.get("contract_ticker") or "").strip()
        outcome = outcome_value(row.get("yes_outcome", row.get("side_outcome")))
        decision_ts = timestamp(row.get("decision_time"))
        close_ts = timestamp(row.get("close_time"))
        yes_ask = probability(row.get("yes_ask"))
        if not ticker:
            errors.append("missing_contract_ticker")
        if outcome is None:
            errors.append("missing_yes_outcome")
        if decision_ts is None:
            errors.append("missing_decision_time")
        if close_ts is None:
            errors.append("missing_close_time")
        if decision_ts is not None and close_ts is not None and decision_ts >= close_ts:
            errors.append("decision_not_before_close")
        if errors:
            invalid.append({"contract_ticker": ticker or None, "errors": errors})
            continue
        assert outcome is not None
        assert decision_ts is not None
        assert close_ts is not None
        normalized.append(
            {
                "contract_ticker": ticker,
                "event_ticker": row.get("event_ticker"),
                "series_ticker": row.get("series_ticker"),
                "league": row.get("league"),
                "home_code": row.get("home_code"),
                "away_code": row.get("away_code"),
                "selected_code": row.get("selected_code"),
                "win_probability": optional_float(row.get("win_probability")),
                "predicted_side": row.get("predicted_side"),
                "mlb_platform_model_probability": optional_float(
                    row.get("mlb_platform_model_probability")
                ),
                "mlb_platform_predicted_side": row.get("mlb_platform_predicted_side"),
                "mlb_platform_model_status": row.get("mlb_platform_model_status"),
                "mlb_platform_model_id": row.get("mlb_platform_model_id"),
                "mlb_platform_match_key": row.get("mlb_platform_match_key"),
                "yes_ask": yes_ask,
                "yes_bid": probability(row.get("yes_bid")),
                "yes_outcome": outcome,
                "decision_ts": decision_ts,
                "close_ts": close_ts,
                "decision_time": iso_from_timestamp(decision_ts),
                "close_time": iso_from_timestamp(close_ts),
                "usable": False,
                "calibrated_probability": None,
                "expected_value_per_contract": None,
            }
        )
    normalized.sort(key=lambda item: (item["decision_ts"], item["contract_ticker"]))
    return normalized, invalid


# ---------------------------------------------------------------------------
# Generic model evaluation (parameterized by model_evaluators list)
# ---------------------------------------------------------------------------


def evaluate_models(
    rows: Sequence[Mapping[str, Any]],
    *,
    model_evaluators: Sequence[Callable[..., dict[str, Any]]],
    min_independent_labels: int,
    min_oos_labels: int,
    test_fraction: float,
    fdr_alpha: float,
) -> list[dict[str, Any]]:
    sorted_rows = list(rows)
    split_index = chronological_split_index(len(sorted_rows), test_fraction)
    oos_rows = sorted_rows[split_index:]
    evaluations = [
        evaluator(
            rows=sorted_rows,
            oos_rows=oos_rows,
            min_independent_labels=min_independent_labels,
            min_oos_labels=min_oos_labels,
        )
        for evaluator in model_evaluators
    ]
    p_values = [
        (index, row["p_value"])
        for index, row in enumerate(evaluations)
        if isinstance(row.get("p_value"), (int, float))
    ]
    q_by_index = benjamini_hochberg(p_values)
    for index, q_value in q_by_index.items():
        evaluations[index]["q_value"] = q_value
        if (
            evaluations[index]["status"] == "testable_research_candidate"
            and q_value <= fdr_alpha
            and float(evaluations[index].get("oos_accuracy") or 0.0) > 0.5
        ):
            evaluations[index]["status"] = "research_candidate_fdr_passed"
    return evaluations


# ---------------------------------------------------------------------------
# Selected-side price/outcome (parameterized by prediction_rule)
# ---------------------------------------------------------------------------


def selected_side_price(row: Mapping[str, Any], side: str) -> float | None:
    if side == "yes":
        return probability(row.get("yes_ask"))
    yes_bid = probability(row.get("yes_bid"))
    return 1.0 - yes_bid if yes_bid is not None else None


def selected_side_outcome(
    row: Mapping[str, Any], prediction_rule: Callable[[Mapping[str, Any]], int | None]
) -> int | None:
    prediction = prediction_rule(row)
    yes_outcome = outcome_value(row.get("yes_outcome"))
    if prediction is None or yes_outcome is None:
        return None
    return yes_outcome if prediction == 1 else 1 - yes_outcome


# ---------------------------------------------------------------------------
# Generic replay calibration
# ---------------------------------------------------------------------------


def conservative_side_probability(
    *,
    oos_rows: Sequence[Mapping[str, Any]],
    prediction_rule: Callable[[Mapping[str, Any]], int | None],
    confidence_z: float,
    min_side_oos_labels: int,
    candidate_eval: Mapping[str, Any] | None,
    model_id: str = "strength_win_prob_directional_accuracy",
) -> dict[str, Any]:
    scored = [row for row in oos_rows if prediction_rule(row) is not None]
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
        "model_id": model_id,
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


# ---------------------------------------------------------------------------
# Generic replay row construction (parameterized by prediction_rule + cluster_key_composer)
# ---------------------------------------------------------------------------


def replay_contract_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    calibration: Mapping[str, Any],
    prediction_rule: Callable[[Mapping[str, Any]], int | None],
    cluster_key_composer: Callable[[Mapping[str, Any]], str],
) -> list[dict[str, Any]]:
    calibrated = probability(calibration.get("conservative_calibrated_side_probability"))
    replay_rows: list[dict[str, Any]] = []
    for row in rows:
        prediction = prediction_rule(row)
        if prediction is None:
            continue
        side = "yes" if prediction == 1 else "no"
        executable_price = selected_side_price(row, side)
        cost = normalize_kalshi_execution_cost(
            display_price=executable_price,
            executable_price=executable_price,
            executable_price_source=f"{side}_ask_derived_from_public_quote",
            payout_if_correct=1.0,
            ticker=str(row.get("contract_ticker") or ""),
        )
        all_in_cost = cost.all_in_cost
        break_even = cost.break_even_probability
        expected_value = (
            calibrated - all_in_cost if calibrated is not None and all_in_cost is not None else None
        )
        margin = (
            calibrated - break_even if calibrated is not None and break_even is not None else None
        )
        outcome = selected_side_outcome(row, prediction_rule)
        paper_result = (
            outcome - all_in_cost if outcome is not None and all_in_cost is not None else None
        )
        cluster_key = cluster_key_composer(row)
        replay_rows.append(
            {
                "contract_ticker": row.get("contract_ticker"),
                "event_ticker": row.get("event_ticker"),
                "series_ticker": row.get("series_ticker"),
                "league": row.get("league"),
                "home_code": row.get("home_code"),
                "away_code": row.get("away_code"),
                "selected_code": row.get("selected_code"),
                "decision_time": row.get("decision_time"),
                "close_time": row.get("close_time"),
                "win_probability": json_float(row.get("win_probability")),
                "predicted_side": side,
                "yes_outcome": row.get("yes_outcome"),
                "selected_side_outcome": outcome,
                "yes_bid": json_float(row.get("yes_bid")),
                "yes_ask": json_float(row.get("yes_ask")),
                "selected_side_executable_price": json_float(executable_price),
                "fee_estimate": json_float(cost.fee_estimate),
                "fee_source": cost.fee_source,
                "all_in_cost": json_float(all_in_cost),
                "all_in_break_even_probability": json_float(break_even),
                "conservative_calibrated_side_probability": json_float(calibrated),
                "margin_probability": json_float(margin),
                "expected_value_per_contract": json_float(expected_value),
                "paper_result_per_contract": json_float(paper_result),
                "cost_quality": cost.cost_quality,
                "cost_gate_status": cost.gate_status,
                "cost_gate_reasons": list(cost.gate_reasons),
                "correlation_cluster_key": cluster_key,
                "usable": False,
                "research_only": True,
                "execution_enabled": False,
            }
        )
    return replay_rows


def decay_summary(
    oos_rows: Sequence[Mapping[str, Any]],
    prediction_rule: Callable[[Mapping[str, Any]], int | None],
) -> dict[str, Any]:
    buckets: dict[str, list[int]] = defaultdict(list)
    for row in oos_rows:
        bucket = bucket_time(row.get("close_time"))
        outcome_val = selected_side_outcome(row, prediction_rule)
        if bucket and outcome_val is not None:
            buckets[bucket].append(outcome_val)
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
    accuracy = sum(recent) / len(recent) if recent else None
    status = (
        "recent_bucket_not_worse_than_random"
        if accuracy is not None and accuracy >= 0.5
        else "recent_bucket_below_random"
    )
    all_outcomes = [o for outcomes in buckets.values() for o in outcomes]
    total_labels = len(all_outcomes)
    cumulative = sum(all_outcomes) / total_labels if total_labels else None
    passing = sum(1 for b in decay_buckets if b["pass_threshold"])
    return {
        "bucket_count": len(buckets),
        "recent_bucket_accuracy": json_float(accuracy),
        "recent_bucket_key": recent_key,
        "recent_bucket_label_count": len(recent),
        "status": status,
        "decay_buckets": decay_buckets,
        "total_decay_labels": total_labels,
        "passing_bucket_count": passing,
        "cumulative_accuracy": json_float(cumulative),
    }


# ---------------------------------------------------------------------------
# Research-candidate lookup (generic)
# ---------------------------------------------------------------------------


def research_candidate_evaluation(
    model_report: Mapping[str, Any],
    model_id: str = "strength_win_prob_directional_accuracy",
) -> dict[str, Any] | None:
    for item in model_report.get("evaluations", []):
        if (
            isinstance(item, Mapping)
            and item.get("model_id") == model_id
            and item.get("status") == "research_candidate_fdr_passed"
        ):
            return dict(item)
    return None


def outside_repo(path: Path) -> bool:
    try:
        path.expanduser().resolve().relative_to(CONTROL_REPO.resolve())
    except ValueError:
        return True
    return False


# ---------------------------------------------------------------------------
# CSV writers (generic)
# ---------------------------------------------------------------------------

FALSIFICATION_CSV_FIELDS = [
    "model_id",
    "status",
    "independent_label_count",
    "oos_count",
    "oos_accuracy",
    "p_value",
    "q_value",
    "mean_market_brier",
]

REPLAY_CSV_FIELDS = [
    "contract_ticker",
    "event_ticker",
    "decision_time",
    "close_time",
    "league",
    "source_model_id",
    "source_model_probability",
    "predicted_side",
    "selected_side_outcome",
    "selected_side_executable_price",
    "all_in_break_even_probability",
    "conservative_calibrated_side_probability",
    "margin_probability",
    "expected_value_per_contract",
    "paper_result_per_contract",
    "cost_quality",
    "correlation_cluster_key",
    "usable",
]


def write_csv_generic(
    report: Mapping[str, Any], path: Path, fieldnames: list[str], rows_key: str = "evaluations"
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in report.get(rows_key, []):
            if isinstance(row, Mapping):
                writer.writerow({field: row.get(field) for field in fieldnames})


# ---------------------------------------------------------------------------
# Falsification summary builder (generic)
# ---------------------------------------------------------------------------


def build_falsification_summary(
    *,
    label_load: Mapping[str, Any],
    normalized_rows: Sequence[Mapping[str, Any]],
    independent_rows: Sequence[Mapping[str, Any]],
    invalid_rows: Sequence[Mapping[str, Any]],
    evaluations: Sequence[Mapping[str, Any]],
    min_independent_labels: int,
    min_oos_labels: int,
    family_label: str = "sports",
) -> dict[str, Any]:
    return {
        "label_packet_count": label_load.get("packet_count", 0),
        "unsafe_label_packet_count": len(label_load.get("unsafe_packets", [])),
        "raw_label_row_count": len(label_load.get("rows", [])),
        "valid_label_row_count": len(normalized_rows),
        "invalid_label_row_count": len(invalid_rows),
        "independent_contract_label_count": len(independent_rows),
        "duplicate_label_row_count": max(0, len(normalized_rows) - len(independent_rows)),
        "min_independent_labels": min_independent_labels,
        "min_oos_labels": min_oos_labels,
        "testable_model_count": sum(
            1 for item in evaluations if item.get("status") == "testable_research_candidate"
        ),
        "research_candidate_count": sum(
            1 for item in evaluations if item.get("status") == "research_candidate_fdr_passed"
        ),
        "label_outcome_counts": counts(row.get("yes_outcome") for row in independent_rows),
        "league_counts": counts(row.get("league") for row in independent_rows),
    }


# ---------------------------------------------------------------------------
# Falsification gates (generic)
# ---------------------------------------------------------------------------


def build_falsification_gates(
    *,
    summary: Mapping[str, Any],
    evaluations: Sequence[Mapping[str, Any]],
    label_dir: Path,
    family_label: str = "sports",
) -> list[dict[str, Any]]:
    return [
        gate(
            "label_packets_safe",
            "pass" if int(summary.get("unsafe_label_packet_count") or 0) == 0 else "blocked",
            f"{summary.get('label_packet_count')} safe packet(s), {summary.get('unsafe_label_packet_count')} unsafe packet(s).",
        ),
        gate(
            "label_dir_outside_repo",
            "pass" if outside_repo(label_dir) else "blocked",
            f"{family_label.capitalize()} proxy label packets must stay outside the repo.",
        ),
        gate(
            "independent_label_minimum",
            "pass"
            if int(summary.get("independent_contract_label_count") or 0)
            >= int(summary.get("min_independent_labels") or 0)
            else "blocked",
            f"{summary.get('independent_contract_label_count')} independent label(s); minimum is {summary.get('min_independent_labels')}.",
        ),
        gate(
            "oos_label_minimum",
            "pass"
            if any(
                str(item.get("status"))
                in {"testable_research_candidate", "research_candidate_fdr_passed"}
                for item in evaluations
            )
            else "blocked",
            f"{summary.get('testable_model_count')} testable model(s); minimum OOS labels is {summary.get('min_oos_labels')}.",
        ),
        gate(
            "no_probability_ev_or_execution_claims",
            "pass"
            if all(
                item.get("usable") is False
                and item.get("calibrated_probability") is None
                and item.get("expected_value_per_contract") is None
                for item in evaluations
            )
            else "fail",
            "Falsification output remains research-only and does not produce usable EV.",
        ),
    ]


# ---------------------------------------------------------------------------
# Replay summary builder (generic)
# ---------------------------------------------------------------------------


def build_replay_summary(
    *,
    label_load: Mapping[str, Any],
    invalid_rows: Sequence[Mapping[str, Any]],
    independent_rows: Sequence[Mapping[str, Any]],
    selected_rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    replay_rows: Sequence[Mapping[str, Any]],
    calibration: Mapping[str, Any],
    candidate_eval: Mapping[str, Any] | None,
    prediction_rule: Callable[[Mapping[str, Any]], int | None],
    cluster_key_composer: Callable[[Mapping[str, Any]], str],
    min_side_oos_labels: int,
    min_decay_buckets: int,
    min_decay_labels: int,
) -> dict[str, Any]:
    positive = [
        row for row in replay_rows if positive_number(row.get("expected_value_per_contract"))
    ]
    costed = [row for row in replay_rows if row.get("all_in_cost") is not None]
    cluster_counts = counts(row.get("correlation_cluster_key") for row in replay_rows)
    paper_results = [
        float(row["paper_result_per_contract"])
        for row in replay_rows
        if row.get("paper_result_per_contract") is not None
    ]
    margins = [
        float(row["margin_probability"])
        for row in replay_rows
        if row.get("margin_probability") is not None
    ]
    decay = decay_summary(oos_rows, prediction_rule)
    return {
        "label_packet_count": label_load.get("packet_count", 0),
        "unsafe_label_packet_count": len(label_load.get("unsafe_packets", [])),
        "raw_label_row_count": len(label_load.get("rows", [])),
        "invalid_label_row_count": len(invalid_rows),
        "independent_contract_label_count": len(independent_rows),
        "selected_rule_row_count": len(selected_rows),
        "oos_selected_row_count": len(oos_rows),
        "replay_row_count": len(replay_rows),
        "costed_replay_row_count": len(costed),
        "positive_expected_value_row_count": len(positive),
        "positive_expected_value_rate": json_float(
            len(positive) / len(replay_rows) if replay_rows else None
        ),
        "candidate_research_model_present": candidate_eval is not None,
        "calibration_status": calibration.get("status"),
        "conservative_calibrated_side_probability": calibration.get(
            "conservative_calibrated_side_probability"
        ),
        "raw_oos_accuracy": calibration.get("raw_oos_accuracy"),
        "source_model_q_value": calibration.get("source_model_q_value"),
        "mean_margin_probability": json_float(mean(margins)),
        "median_margin_probability": json_float(median(margins)),
        "mean_expected_value_per_contract": json_float(
            mean(
                [
                    float(row["expected_value_per_contract"])
                    for row in replay_rows
                    if row.get("expected_value_per_contract") is not None
                ]
            )
        ),
        "historical_paper_result_sum": json_float(sum(paper_results) if paper_results else None),
        "historical_paper_result_mean": json_float(mean(paper_results)),
        "league_counts": counts(row.get("league") for row in independent_rows),
        "predicted_side_counts": counts(row.get("predicted_side") for row in replay_rows),
        "cost_quality_counts": counts(row.get("cost_quality") for row in replay_rows),
        "correlation_cluster_count": len(cluster_counts),
        "largest_correlation_cluster_key": next(iter(cluster_counts), None),
        "largest_correlation_cluster_count": next(iter(cluster_counts.values()), 0)
        if cluster_counts
        else 0,
        "decay_bucket_count": decay["bucket_count"],
        "recent_bucket_accuracy": decay["recent_bucket_accuracy"],
        "recent_bucket_key": decay.get("recent_bucket_key"),
        "recent_bucket_label_count": decay.get("recent_bucket_label_count"),
        "decay_status": decay["status"],
        "decay_buckets": decay.get("decay_buckets", []),
        "total_decay_labels": decay.get("total_decay_labels", 0),
        "passing_bucket_count": decay.get("passing_bucket_count", 0),
        "cumulative_decay_accuracy": decay.get("cumulative_accuracy"),
        "min_side_oos_labels": min_side_oos_labels,
        "min_decay_buckets": min_decay_buckets,
        "min_decay_labels": min_decay_labels,
        "capacity_depth_row_count": 0,
        "usable_row_count": 0,
    }


# ---------------------------------------------------------------------------
# Replay gates (generic)
# ---------------------------------------------------------------------------


def build_replay_gates(
    *,
    summary: Mapping[str, Any],
    label_dir: Path,
    replay_rows: Sequence[Mapping[str, Any]],
    min_decay_labels: int,
    min_decay_buckets: int,
) -> list[dict[str, Any]]:
    decay_pass = (
        int(summary.get("independent_contract_label_count") or 0) >= min_decay_labels
        and int(summary.get("decay_bucket_count") or 0) >= min_decay_buckets
        and str(summary.get("decay_status")) == "recent_bucket_not_worse_than_random"
    )
    return [
        gate(
            "label_packets_safe",
            "pass" if int(summary.get("unsafe_label_packet_count") or 0) == 0 else "blocked",
            f"{summary.get('label_packet_count')} safe packet(s), {summary.get('unsafe_label_packet_count')} unsafe packet(s).",
        ),
        gate(
            "label_dir_outside_repo",
            "pass" if outside_repo(label_dir) else "blocked",
            "Sports proxy label packets must stay outside the repo.",
        ),
        gate(
            "research_candidate_present",
            "pass" if summary.get("candidate_research_model_present") is True else "blocked",
            "Feature-model falsification must have a research_candidate_fdr_passed row.",
        ),
        gate(
            "conservative_probability_preflight",
            "pass"
            if summary.get("calibration_status") == "research_only_conservative_probability_ready"
            else "blocked",
            f"Calibration status is {summary.get('calibration_status')}; OOS selected rows: {summary.get('oos_selected_row_count')}.",
        ),
        gate(
            "all_in_cost_replay",
            "pass"
            if replay_rows
            and int(summary.get("costed_replay_row_count") or 0)
            == int(summary.get("replay_row_count") or 0)
            else "blocked",
            f"{summary.get('costed_replay_row_count')} of {summary.get('replay_row_count')} replay rows have all-in cost.",
        ),
        gate(
            "positive_cost_adjusted_replay_rows",
            "warn" if int(summary.get("positive_expected_value_row_count") or 0) > 0 else "blocked",
            f"{summary.get('positive_expected_value_row_count')} replay row(s) are positive after conservative probability and all-in cost.",
        ),
        gate(
            "capacity_depth_available",
            "blocked",
            "No public depth or validated local order-book depth is attached, so capacity and price impact are unknown.",
        ),
        gate(
            "correlation_control_available",
            "blocked",
            (
                f"{summary.get('correlation_cluster_count')} cluster(s); largest cluster "
                f"{summary.get('largest_correlation_cluster_key')} has {summary.get('largest_correlation_cluster_count')} row(s). "
                "Cluster counts are measured, but covariance/exposure controls are not implemented."
            ),
        ),
        gate(
            "decay_survival_available",
            "pass" if decay_pass else "blocked",
            (
                f"Decay status is {summary.get('decay_status')} across {summary.get('decay_bucket_count')} bucket(s); "
                f"requires {min_decay_buckets} bucket(s) and {min_decay_labels} independent labels. "
                f"Recent bucket {summary.get('recent_bucket_key')} accuracy {summary.get('recent_bucket_accuracy')} "
                f"({summary.get('recent_bucket_label_count')} labels); "
                f"cumulative accuracy {summary.get('cumulative_decay_accuracy')} across {summary.get('total_decay_labels')} labels; "
                f"{summary.get('passing_bucket_count')}/{summary.get('decay_bucket_count')} bucket(s) pass >= 0.5."
            ),
        ),
        gate(
            "no_usable_ev_sizing_or_execution",
            "pass"
            if int(summary.get("usable_row_count") or 0) == 0
            and all(row.get("usable") is False for row in replay_rows)
            else "fail",
            "Replay remains research-only with zero usable rows and no sizing or execution.",
        ),
    ]


# ---------------------------------------------------------------------------
# Replay status determination (generic)
# ---------------------------------------------------------------------------


def replay_status(
    summary: Mapping[str, Any], gates: Sequence[Mapping[str, Any]], family_prefix: str = "sports"
) -> str:
    if not summary.get("candidate_research_model_present"):
        return f"{family_prefix}_proxy_research_candidate_replay_blocked_missing_research_candidate"
    if int(summary.get("replay_row_count") or 0) == 0:
        return f"{family_prefix}_proxy_research_candidate_replay_blocked_missing_replay_rows"
    if any(item.get("status") == "fail" for item in gates):
        return f"{family_prefix}_proxy_research_candidate_replay_failed_safety_gate"
    hard_blockers = {
        "capacity_depth_available",
        "correlation_control_available",
        "decay_survival_available",
    }
    if any(item.get("name") in hard_blockers and item.get("status") != "pass" for item in gates):
        return f"{family_prefix}_proxy_research_candidate_replay_blocked_predeployment_gates"
    if int(summary.get("positive_expected_value_row_count") or 0) > 0:
        return (
            f"{family_prefix}_proxy_research_candidate_replay_ready_for_paper_probability_overlay"
        )
    return f"{family_prefix}_proxy_research_candidate_replay_ready_no_positive_cost_adjusted_rows"
