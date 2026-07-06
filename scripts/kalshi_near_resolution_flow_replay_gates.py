#!/usr/bin/env python3
"""Replay near-resolution informed-flow candidates through cost/depth/decay gates."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = CONTROL_REPO / "scripts"
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import kalshi_near_resolution_informed_flow_evidence_gate as flow_gate  # noqa: E402

from predmarket.kalshi_execution_cost import normalize_kalshi_execution_cost  # noqa: E402
from predmarket.shared_helpers import (  # noqa: E402
    bucket_time,
    controlled_cluster_costs,
    counts,
    json_float,
    probability,
    read_json_or_empty,
    required_cluster_count,
    safe_research_artifact,
    safety_flags,
    sha256_or_none,
    timestamp,
    wilson_lower_bound,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_EVIDENCE_PATH = MACRO_DIR / "latest-kalshi-near-resolution-informed-flow-evidence-gate.json"
DEFAULT_MICROSTRUCTURE_PATH = (
    MACRO_DIR / "latest-kalshi-sports-microstructure-observation-loop.json"
)
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-near-resolution-flow-replay-gates-latest"
DEFAULT_MODEL_ID = "flow_depth_imbalance_settlement_directional"
DEFAULT_CONFIDENCE_Z = 1.6448536269514722
DEFAULT_MIN_SIDE_OOS_LABELS = 30
DEFAULT_MIN_DECAY_BUCKETS = 3
DEFAULT_MIN_DECAY_LABELS = 100
DEFAULT_MAX_CLOSE_HOURS = 6.0
DEFAULT_MAX_CURRENT_CANDIDATES = 60
DEFAULT_MAX_OBSERVATION_AGE_SECONDS = 900.0
DEFAULT_MAX_CLUSTER_SHARE = 0.35
DEFAULT_MIN_POSITIVE_CAPACITY_CONTRACTS = 1.0

CSV_FIELDS = [
    "contract_ticker",
    "side",
    "decision_time",
    "close_time",
    "selected_side_executable_price",
    "all_in_cost",
    "conservative_calibrated_side_probability",
    "expected_value_per_contract",
    "selected_side_outcome",
    "correlation_cluster_key",
    "usable",
]

CAPACITY_CSV_FIELDS = [
    "contract_ticker",
    "side",
    "decision_time",
    "close_time",
    "current_observation_age_seconds",
    "selected_side_executable_price",
    "all_in_cost",
    "positive_depth_contracts",
    "positive_depth_cost",
    "correlation_cluster_key",
    "gate_status",
    "usable",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_near_resolution_flow_replay_gates(
    *,
    evidence_path: Path = DEFAULT_EVIDENCE_PATH,
    microstructure_path: Path = DEFAULT_MICROSTRUCTURE_PATH,
    generated_utc: str | None = None,
    model_id: str = DEFAULT_MODEL_ID,
    confidence_z: float = DEFAULT_CONFIDENCE_Z,
    min_side_oos_labels: int = DEFAULT_MIN_SIDE_OOS_LABELS,
    min_decay_buckets: int = DEFAULT_MIN_DECAY_BUCKETS,
    min_decay_labels: int = DEFAULT_MIN_DECAY_LABELS,
    max_close_hours: float = DEFAULT_MAX_CLOSE_HOURS,
    max_current_candidates: int = DEFAULT_MAX_CURRENT_CANDIDATES,
    max_observation_age_seconds: float = DEFAULT_MAX_OBSERVATION_AGE_SECONDS,
    max_cluster_share: float = DEFAULT_MAX_CLUSTER_SHARE,
    min_positive_capacity_contracts: float = DEFAULT_MIN_POSITIVE_CAPACITY_CONTRACTS,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    generated_ts = timestamp(generated) or 0.0
    evidence = read_json_or_empty(evidence_path)
    micro = read_json_or_empty(microstructure_path)
    micro_rows = replay_source_rows(evidence=evidence, micro=micro)
    candidate_eval = research_candidate(evidence, model_id=model_id)
    scored_rows = scored_depth_imbalance_rows(micro_rows)
    independent_rows = independent_rows_by_contract(scored_rows, keep="earliest")
    replay_rows = replay_rows_for_candidate(
        independent_rows,
        calibration=calibration_from_candidate(
            candidate_eval,
            confidence_z=confidence_z,
            min_side_oos_labels=min_side_oos_labels,
        ),
    )
    calibration = calibration_from_candidate(
        candidate_eval,
        confidence_z=confidence_z,
        min_side_oos_labels=min_side_oos_labels,
    )
    current_rows = select_current_rows(
        scored_rows,
        generated_ts=generated_ts,
        max_close_hours=max_close_hours,
        max_observation_age_seconds=max_observation_age_seconds,
        max_current_candidates=max_current_candidates,
    )
    capacity_rows = capacity_rows_for_current_candidates(
        current_rows,
        calibrated_probability=probability(
            calibration.get("conservative_calibrated_side_probability")
        ),
    )
    summary = build_summary(
        evidence=evidence,
        micro=micro,
        micro_rows=micro_rows,
        scored_rows=scored_rows,
        independent_rows=independent_rows,
        replay_rows=replay_rows,
        current_rows=current_rows,
        capacity_rows=capacity_rows,
        candidate_eval=candidate_eval,
        calibration=calibration,
        min_side_oos_labels=min_side_oos_labels,
        min_decay_buckets=min_decay_buckets,
        min_decay_labels=min_decay_labels,
        max_cluster_share=max_cluster_share,
        min_positive_capacity_contracts=min_positive_capacity_contracts,
    )
    gates = build_gates(summary)
    status = report_status(summary, gates)
    blocker_rows = paper_decision_blocker_rows(capacity_rows, summary=summary, gates=gates)
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
        "family_id": "near_resolution_informed_flow",
        "inputs": {
            "evidence_path": str(evidence_path),
            "evidence_sha256": sha256_or_none(evidence_path),
            "evidence_status": evidence.get("status"),
            "microstructure_path": str(microstructure_path),
            "microstructure_sha256": sha256_or_none(microstructure_path),
            "microstructure_status": micro.get("status"),
            "model_id": model_id,
            "max_close_hours": max_close_hours,
            "max_current_candidates": max_current_candidates,
            "max_observation_age_seconds": max_observation_age_seconds,
        },
        "method": {
            "candidate_policy": "Only the FDR-surviving pre-registered flow candidate is replayed.",
            "replay_policy": "Historical rows are collapsed by exact contract_ticker and costed from public quotes.",
            "calibration_policy": "Conservative selected-side probability is Wilson lower bound of OOS candidate accuracy.",
            "capacity_policy": "Current candidates must still have fresh public quote/depth support after fees.",
            "correlation_policy": "Positive-depth cost is clustered by sport surface, event ticker, and close-date bucket.",
            "decay_policy": "Selected-side OOS settlement survival must hold across recent close-date buckets.",
            "boundary": "This artifact emits research blockers only; it never authorizes stake, order, or account actions.",
        },
        "calibration": calibration,
        "summary": summary,
        "gates": gates,
        "replay_rows": replay_rows,
        "capacity_rows": capacity_rows,
        "paper_decision_blocker_rows": blocker_rows,
        "next_action": next_action(status),
        "safety": safety_flags(),
    }


def research_candidate(evidence: Mapping[str, Any], *, model_id: str) -> dict[str, Any] | None:
    rows = evidence.get("evaluations") if isinstance(evidence.get("evaluations"), list) else []
    for row in rows:
        if (
            isinstance(row, Mapping)
            and row.get("model_id") == model_id
            and row.get("status") == "research_candidate_fdr_passed"
        ):
            return dict(row)
    return None


def replay_source_rows(
    *, evidence: Mapping[str, Any], micro: Mapping[str, Any]
) -> list[dict[str, Any]]:
    micro_rows = flow_gate.microstructure_rows(micro)
    evidence_rows = evidence.get("flow_rows") if isinstance(evidence.get("flow_rows"), list) else []
    usable_evidence_rows = [
        dict(row)
        for row in evidence_rows
        if isinstance(row, Mapping)
        and row.get("best_yes_ask") is not None
        and row.get("settlement_time") is not None
    ]
    if len(usable_evidence_rows) > len(micro_rows):
        return usable_evidence_rows
    return [dict(row) for row in micro_rows if isinstance(row, Mapping)]


def calibration_from_candidate(
    candidate_eval: Mapping[str, Any] | None,
    *,
    confidence_z: float,
    min_side_oos_labels: int,
) -> dict[str, Any]:
    count = int(candidate_eval.get("oos_label_count") or 0) if candidate_eval else 0
    wins = int(candidate_eval.get("oos_correct_count") or 0) if candidate_eval else 0
    lower = wilson_lower_bound(wins, count, confidence_z) if count else None
    raw_accuracy = wins / count if count else None
    status = "blocked_missing_research_candidate"
    if candidate_eval and count < min_side_oos_labels:
        status = "blocked_insufficient_side_oos_labels"
    elif candidate_eval and lower is not None and lower <= 0.5:
        status = "blocked_conservative_probability_not_above_random"
    elif candidate_eval:
        status = "research_only_conservative_probability_ready"
    return {
        "model_id": candidate_eval.get("model_id") if candidate_eval else DEFAULT_MODEL_ID,
        "status": status,
        "oos_count": count,
        "oos_correct_count": wins,
        "raw_oos_accuracy": json_float(raw_accuracy),
        "conservative_calibrated_side_probability": json_float(lower),
        "confidence_z": confidence_z,
        "min_side_oos_labels": min_side_oos_labels,
        "source_model_p_value": candidate_eval.get("p_value") if candidate_eval else None,
        "source_model_q_value": candidate_eval.get("q_value") if candidate_eval else None,
        "usable": False,
    }


def scored_depth_imbalance_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        prediction = flow_gate.depth_imbalance_prediction(row)
        if prediction is None:
            continue
        decision_ts = timestamp(row.get("observed_at_utc"))
        close_time = (
            row.get("settlement_time")
            or row.get("close_time")
            or row.get("expected_expiration_time")
        )
        close_ts = timestamp(close_time)
        if decision_ts is None or close_ts is None:
            continue
        yes_outcome = outcome(row.get("settlement_yes_outcome"))
        side = "yes" if prediction == 1 else "no"
        executable = selected_side_executable_price(row, side)
        selected_outcome = (
            yes_outcome if prediction == 1 else 1 - yes_outcome if yes_outcome in {0, 1} else None
        )
        output.append(
            {
                **dict(row),
                "decision_ts": decision_ts,
                "close_ts": close_ts,
                "decision_time": iso_from_ts(decision_ts),
                "close_time": str(close_time),
                "model_id": DEFAULT_MODEL_ID,
                "side": side,
                "predicted_outcome": prediction,
                "yes_outcome": yes_outcome,
                "selected_side_outcome": selected_outcome,
                "selected_side_executable_price": executable,
                "correlation_cluster_key": correlation_cluster_key(row, close_time=close_time),
                "usable": False,
                "research_only": True,
                "execution_enabled": False,
            }
        )
    return sorted(output, key=lambda item: (item["decision_ts"], item["contract_ticker"]))


def independent_rows_by_contract(
    rows: Sequence[Mapping[str, Any]], *, keep: str
) -> list[dict[str, Any]]:
    by_ticker: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("contract_ticker") or "")
        if not ticker:
            continue
        if ticker not in by_ticker:
            by_ticker[ticker] = dict(row)
            continue
        current = float(row.get("decision_ts") or 0.0)
        previous = float(by_ticker[ticker].get("decision_ts") or 0.0)
        if (keep == "latest" and current > previous) or (keep != "latest" and current < previous):
            by_ticker[ticker] = dict(row)
    return sorted(
        by_ticker.values(),
        key=lambda item: (float(item.get("decision_ts") or 0.0), str(item.get("contract_ticker"))),
    )


def replay_rows_for_candidate(
    rows: Sequence[Mapping[str, Any]], *, calibration: Mapping[str, Any]
) -> list[dict[str, Any]]:
    calibrated = probability(calibration.get("conservative_calibrated_side_probability"))
    output: list[dict[str, Any]] = []
    for row in rows:
        if row.get("selected_side_outcome") not in {0, 1}:
            continue
        cost = cost_for_row(row)
        all_in_cost = cost.all_in_cost
        expected_value = (
            calibrated - all_in_cost if calibrated is not None and all_in_cost is not None else None
        )
        paper_result = (
            int(row["selected_side_outcome"]) - all_in_cost if all_in_cost is not None else None
        )
        output.append(
            {
                "contract_ticker": row.get("contract_ticker"),
                "event_ticker": row.get("event_ticker"),
                "series_ticker": row.get("series_ticker"),
                "sport_surface": row.get("sport_surface"),
                "decision_time": row.get("decision_time"),
                "close_time": row.get("close_time"),
                "model_id": DEFAULT_MODEL_ID,
                "side": row.get("side"),
                "predicted_outcome": row.get("predicted_outcome"),
                "yes_outcome": row.get("yes_outcome"),
                "selected_side_outcome": row.get("selected_side_outcome"),
                "depth_imbalance_yes": json_float(row.get("depth_imbalance_yes")),
                "selected_side_executable_price": json_float(
                    row.get("selected_side_executable_price")
                ),
                "fee_estimate": json_float(cost.fee_estimate),
                "fee_source": cost.fee_source,
                "all_in_cost": json_float(all_in_cost),
                "all_in_break_even_probability": json_float(cost.break_even_probability),
                "conservative_calibrated_side_probability": json_float(calibrated),
                "expected_value_per_contract": json_float(expected_value),
                "paper_result_per_contract": json_float(paper_result),
                "cost_quality": cost.cost_quality,
                "cost_gate_status": cost.gate_status,
                "cost_gate_reasons": list(cost.gate_reasons),
                "correlation_cluster_key": row.get("correlation_cluster_key"),
                "usable": False,
                "research_only": True,
                "execution_enabled": False,
            }
        )
    return output


def select_current_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    generated_ts: float,
    max_close_hours: float,
    max_observation_age_seconds: float,
    max_current_candidates: int,
) -> list[dict[str, Any]]:
    current: list[dict[str, Any]] = []
    for row in independent_rows_by_contract(rows, keep="latest"):
        decision_ts = float(row.get("decision_ts") or 0.0)
        close_ts = float(row.get("close_ts") or 0.0)
        if close_ts <= generated_ts:
            continue
        hours_to_close = (close_ts - generated_ts) / 3600.0
        age = max(0.0, generated_ts - decision_ts)
        if hours_to_close > max_close_hours or age > max_observation_age_seconds:
            continue
        item = dict(row)
        item["hours_to_close"] = json_float(hours_to_close)
        item["current_observation_age_seconds"] = json_float(age)
        current.append(item)
    current.sort(
        key=lambda row: (
            str(row.get("correlation_cluster_key") or ""),
            float(row.get("hours_to_close") or 999999.0),
            str(row.get("contract_ticker") or ""),
        )
    )
    return select_cluster_round_robin(current, max_rows=max_current_candidates)


def select_cluster_round_robin(
    rows: Sequence[Mapping[str, Any]], *, max_rows: int
) -> list[dict[str, Any]]:
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        clusters[str(row.get("correlation_cluster_key") or "unknown")].append(dict(row))
    for cluster_rows in clusters.values():
        cluster_rows.sort(
            key=lambda row: (
                float(row.get("hours_to_close") or 999999.0),
                str(row.get("contract_ticker") or ""),
            )
        )
    selected: list[dict[str, Any]] = []
    keys = sorted(clusters)
    while keys and len(selected) < max_rows:
        next_keys: list[str] = []
        for key in keys:
            if len(selected) >= max_rows:
                break
            cluster_rows = clusters[key]
            if cluster_rows:
                selected.append(cluster_rows.pop(0))
            if cluster_rows:
                next_keys.append(key)
        keys = next_keys
    return selected


def capacity_rows_for_current_candidates(
    rows: Sequence[Mapping[str, Any]], *, calibrated_probability: float | None
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        cost = cost_for_row(row)
        all_in_cost = cost.all_in_cost
        depth = selected_side_depth(row, str(row.get("side") or ""))
        positive = (
            depth
            if calibrated_probability is not None
            and all_in_cost is not None
            and calibrated_probability > all_in_cost
            else 0.0
        )
        output.append(
            {
                "contract_ticker": row.get("contract_ticker"),
                "event_ticker": row.get("event_ticker"),
                "series_ticker": row.get("series_ticker"),
                "sport_surface": row.get("sport_surface"),
                "decision_time": row.get("decision_time"),
                "close_time": row.get("close_time"),
                "current_observation_age_seconds": row.get("current_observation_age_seconds"),
                "model_id": DEFAULT_MODEL_ID,
                "side": row.get("side"),
                "predicted_outcome": row.get("predicted_outcome"),
                "depth_imbalance_yes": json_float(row.get("depth_imbalance_yes")),
                "selected_side_executable_price": json_float(
                    row.get("selected_side_executable_price")
                ),
                "selected_side_depth_top1": json_float(depth),
                "fee_estimate": json_float(cost.fee_estimate),
                "fee_source": cost.fee_source,
                "all_in_cost": json_float(all_in_cost),
                "all_in_break_even_probability": json_float(cost.break_even_probability),
                "conservative_calibrated_side_probability": json_float(calibrated_probability),
                "expected_value_per_contract": json_float(
                    calibrated_probability - all_in_cost
                    if calibrated_probability is not None and all_in_cost is not None
                    else None
                ),
                "positive_depth_contracts": json_float(positive),
                "positive_depth_cost": json_float((all_in_cost or 0.0) * positive),
                "correlation_cluster_key": row.get("correlation_cluster_key"),
                "gate_status": "pass" if positive > 0 else "blocked",
                "usable": False,
                "research_only": True,
                "execution_enabled": False,
            }
        )
    return output


def build_summary(
    *,
    evidence: Mapping[str, Any],
    micro: Mapping[str, Any],
    micro_rows: Sequence[Mapping[str, Any]],
    scored_rows: Sequence[Mapping[str, Any]],
    independent_rows: Sequence[Mapping[str, Any]],
    replay_rows: Sequence[Mapping[str, Any]],
    current_rows: Sequence[Mapping[str, Any]],
    capacity_rows: Sequence[Mapping[str, Any]],
    candidate_eval: Mapping[str, Any] | None,
    calibration: Mapping[str, Any],
    min_side_oos_labels: int,
    min_decay_buckets: int,
    min_decay_labels: int,
    max_cluster_share: float,
    min_positive_capacity_contracts: float,
) -> dict[str, Any]:
    costed = [row for row in replay_rows if row.get("all_in_cost") is not None]
    positive_replay = [
        row for row in replay_rows if float(row.get("expected_value_per_contract") or 0.0) > 0.0
    ]
    positive_capacity = [
        row for row in capacity_rows if float(row.get("positive_depth_contracts") or 0.0) > 0.0
    ]
    positive_depth_contracts = sum(
        float(row.get("positive_depth_contracts") or 0.0) for row in capacity_rows
    )
    positive_depth_cost = sum(float(row.get("positive_depth_cost") or 0.0) for row in capacity_rows)
    cluster_costs: dict[str, float] = defaultdict(float)
    for row in capacity_rows:
        cluster_costs[str(row.get("correlation_cluster_key") or "unknown")] += float(
            row.get("positive_depth_cost") or 0.0
        )
    positive_cluster_costs = {key: value for key, value in cluster_costs.items() if value > 0.0}
    controlled_costs = controlled_cluster_costs(positive_cluster_costs, max_cluster_share)
    controlled_total = sum(controlled_costs.values())
    controlled_largest = max(controlled_costs.values()) if controlled_costs else 0.0
    controlled_largest_share = (
        controlled_largest / controlled_total if controlled_total > 0.0 else None
    )
    min_positive_clusters = required_cluster_count(max_cluster_share, 0)
    largest_cluster_key = (
        max(positive_cluster_costs, key=positive_cluster_costs.get)
        if positive_cluster_costs
        else None
    )
    largest_cluster_cost = positive_cluster_costs.get(largest_cluster_key, 0.0)
    largest_share = (
        largest_cluster_cost / positive_depth_cost if positive_depth_cost > 0.0 else None
    )
    decay = decay_summary(replay_rows)
    return {
        "evidence_safe": safe_research_artifact(evidence),
        "microstructure_safe": safe_research_artifact(micro),
        "evidence_status": evidence.get("status"),
        "microstructure_status": micro.get("status"),
        "microstructure_row_count": len(micro_rows),
        "scored_depth_imbalance_row_count": len(scored_rows),
        "independent_contract_label_count": len(
            [row for row in independent_rows if row.get("yes_outcome") in {0, 1}]
        ),
        "replay_row_count": len(replay_rows),
        "costed_replay_row_count": len(costed),
        "costed_replay_coverage": json_float(
            len(costed) / len(replay_rows) if replay_rows else None
        ),
        "positive_expected_value_row_count": len(positive_replay),
        "current_candidate_row_count": len(current_rows),
        "capacity_row_count": len(capacity_rows),
        "capacity_positive_row_count": len(positive_capacity),
        "positive_depth_contracts": json_float(positive_depth_contracts),
        "positive_depth_cost": json_float(positive_depth_cost),
        "min_positive_capacity_contracts": min_positive_capacity_contracts,
        "candidate_research_model_present": candidate_eval is not None,
        "selected_replay_model_id": candidate_eval.get("model_id") if candidate_eval else None,
        "candidate_oos_label_count": candidate_eval.get("oos_label_count")
        if candidate_eval
        else None,
        "candidate_oos_correct_count": candidate_eval.get("oos_correct_count")
        if candidate_eval
        else None,
        "candidate_q_value": candidate_eval.get("q_value") if candidate_eval else None,
        "calibration_status": calibration.get("status"),
        "conservative_calibrated_side_probability": calibration.get(
            "conservative_calibrated_side_probability"
        ),
        "min_side_oos_labels": min_side_oos_labels,
        "correlation_cluster_count": len(cluster_costs),
        "positive_correlation_cluster_count": len(positive_cluster_costs),
        "controlled_correlation_cluster_count": len(controlled_costs),
        "controlled_positive_depth_cost": json_float(controlled_total),
        "controlled_largest_correlation_cluster_share": json_float(controlled_largest_share),
        "min_positive_correlation_clusters": min_positive_clusters,
        "controlled_cluster_costs": {
            key: json_float(value) for key, value in controlled_costs.items()
        },
        "largest_correlation_cluster_key": largest_cluster_key,
        "largest_correlation_cluster_cost": json_float(largest_cluster_cost),
        "largest_correlation_cluster_share": json_float(largest_share),
        "max_cluster_share": max_cluster_share,
        "correlation_status": "correlation_cluster_within_limit"
        if controlled_total > 0.0 and len(controlled_costs) >= min_positive_clusters
        else "correlation_cluster_concentrated_or_missing",
        "decay_status": decay["status"],
        "decay_bucket_count": decay["bucket_count"],
        "recent_bucket_key": decay["recent_bucket_key"],
        "recent_bucket_accuracy": decay["recent_bucket_accuracy"],
        "recent_bucket_label_count": decay["recent_bucket_label_count"],
        "total_decay_labels": decay["total_decay_labels"],
        "passing_bucket_count": decay["passing_bucket_count"],
        "cumulative_decay_accuracy": decay["cumulative_accuracy"],
        "decay_buckets": decay["decay_buckets"],
        "min_decay_buckets": min_decay_buckets,
        "min_decay_labels": min_decay_labels,
        "side_counts": counts(row.get("side") for row in scored_rows),
        "current_side_counts": counts(row.get("side") for row in current_rows),
        "usable_row_count": 0,
    }


def decay_summary(replay_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[int]] = defaultdict(list)
    for row in replay_rows:
        bucket = bucket_time(row.get("close_time"))
        outcome_value = row.get("selected_side_outcome")
        if bucket and outcome_value in {0, 1}:
            buckets[bucket].append(int(outcome_value))
    if not buckets:
        return {
            "bucket_count": 0,
            "recent_bucket_accuracy": None,
            "recent_bucket_key": None,
            "recent_bucket_label_count": 0,
            "status": "blocked_missing_decay_buckets",
            "decay_buckets": [],
            "total_decay_labels": 0,
            "passing_bucket_count": 0,
            "cumulative_accuracy": None,
        }
    sorted_keys = sorted(buckets)
    rows: list[dict[str, Any]] = []
    for key in sorted_keys:
        labels = buckets[key]
        accuracy = sum(labels) / len(labels) if labels else None
        rows.append(
            {
                "bucket": key,
                "label_count": len(labels),
                "correct_count": sum(labels),
                "accuracy": json_float(accuracy),
                "pass_threshold": accuracy is not None and accuracy >= 0.5,
            }
        )
    recent_key = sorted_keys[-1]
    recent = buckets[recent_key]
    recent_accuracy = sum(recent) / len(recent) if recent else None
    all_labels = [label for labels in buckets.values() for label in labels]
    cumulative = sum(all_labels) / len(all_labels) if all_labels else None
    return {
        "bucket_count": len(buckets),
        "recent_bucket_accuracy": json_float(recent_accuracy),
        "recent_bucket_key": recent_key,
        "recent_bucket_label_count": len(recent),
        "status": "recent_bucket_not_worse_than_random"
        if recent_accuracy is not None and recent_accuracy >= 0.5
        else "recent_bucket_below_random",
        "decay_buckets": rows,
        "total_decay_labels": len(all_labels),
        "passing_bucket_count": sum(1 for row in rows if row["pass_threshold"]),
        "cumulative_accuracy": json_float(cumulative),
    }


def build_gates(summary: Mapping[str, Any]) -> list[dict[str, str]]:
    decay_pass = (
        str(summary.get("decay_status")) == "recent_bucket_not_worse_than_random"
        and int(summary.get("decay_bucket_count") or 0)
        >= int(summary.get("min_decay_buckets") or 0)
        and int(summary.get("total_decay_labels") or 0) >= int(summary.get("min_decay_labels") or 0)
    )
    return [
        gate(
            "evidence_artifact_safe",
            "pass"
            if summary.get("evidence_safe") and summary.get("microstructure_safe")
            else "fail",
            f"Evidence safe={summary.get('evidence_safe')}; microstructure safe={summary.get('microstructure_safe')}.",
        ),
        gate(
            "research_candidate_present",
            "pass" if summary.get("candidate_research_model_present") else "blocked",
            f"Selected model: {summary.get('selected_replay_model_id')}.",
        ),
        gate(
            "conservative_probability_ready",
            "pass"
            if summary.get("calibration_status") == "research_only_conservative_probability_ready"
            else "blocked",
            f"Calibration status {summary.get('calibration_status')}; OOS labels {summary.get('candidate_oos_label_count')}.",
        ),
        gate(
            "historical_all_in_cost_replay",
            "pass"
            if int(summary.get("costed_replay_row_count") or 0)
            >= int(summary.get("min_side_oos_labels") or 0)
            else "blocked",
            (
                f"{summary.get('costed_replay_row_count')}/{summary.get('replay_row_count')} replay rows costed "
                f"(coverage {summary.get('costed_replay_coverage')}); minimum costed rows is "
                f"{summary.get('min_side_oos_labels')}."
            ),
        ),
        gate(
            "positive_cost_adjusted_replay_rows",
            "pass" if int(summary.get("positive_expected_value_row_count") or 0) > 0 else "blocked",
            f"{summary.get('positive_expected_value_row_count')} historical replay row(s) positive after cost.",
        ),
        gate(
            "current_candidates_present",
            "pass" if int(summary.get("current_candidate_row_count") or 0) > 0 else "blocked",
            f"{summary.get('current_candidate_row_count')} fresh current candidate row(s).",
        ),
        gate(
            "positive_capacity_depth",
            "pass"
            if float(summary.get("positive_depth_contracts") or 0.0)
            >= float(summary.get("min_positive_capacity_contracts") or 0.0)
            else "blocked",
            f"{summary.get('positive_depth_contracts')} positive-depth contract(s), {summary.get('positive_depth_cost')} notional cost.",
        ),
        gate(
            "correlation_cluster_limit",
            "pass"
            if summary.get("correlation_status") == "correlation_cluster_within_limit"
            else "blocked",
            (
                f"Raw largest cluster share {summary.get('largest_correlation_cluster_share')}; "
                f"controlled largest share {summary.get('controlled_largest_correlation_cluster_share')}; "
                f"controlled clusters {summary.get('controlled_correlation_cluster_count')}/"
                f"{summary.get('min_positive_correlation_clusters')}."
            ),
        ),
        gate(
            "decay_survival",
            "pass" if decay_pass else "blocked",
            (
                f"Decay {summary.get('decay_status')} across {summary.get('decay_bucket_count')} bucket(s), "
                f"{summary.get('total_decay_labels')} label(s); recent {summary.get('recent_bucket_key')} "
                f"accuracy {summary.get('recent_bucket_accuracy')}."
            ),
        ),
        gate(
            "no_usable_sizing_or_execution",
            "pass" if int(summary.get("usable_row_count") or 0) == 0 else "fail",
            "Replay gate remains research-only with zero usable rows.",
        ),
    ]


def report_status(summary: Mapping[str, Any], gates: Sequence[Mapping[str, Any]]) -> str:
    if any(row.get("status") == "fail" for row in gates):
        return "near_resolution_flow_replay_gates_failed_safety_gate"
    if gate_status(gates, "research_candidate_present") != "pass":
        return "near_resolution_flow_replay_gates_blocked_missing_research_candidate"
    if gate_status(gates, "conservative_probability_ready") != "pass":
        return "near_resolution_flow_replay_gates_blocked_calibration"
    if gate_status(gates, "historical_all_in_cost_replay") != "pass":
        return "near_resolution_flow_replay_gates_blocked_cost_replay"
    if gate_status(gates, "current_candidates_present") != "pass":
        return "near_resolution_flow_replay_gates_blocked_no_current_candidates"
    if gate_status(gates, "positive_capacity_depth") != "pass":
        return "near_resolution_flow_replay_gates_blocked_capacity_depth"
    if gate_status(gates, "correlation_cluster_limit") != "pass":
        return "near_resolution_flow_replay_gates_blocked_correlation_concentration"
    if gate_status(gates, "decay_survival") != "pass":
        return "near_resolution_flow_replay_gates_blocked_decay_survival"
    if gate_status(gates, "positive_cost_adjusted_replay_rows") != "pass":
        return "near_resolution_flow_replay_gates_ready_no_positive_replay_edge"
    return "near_resolution_flow_replay_gates_ready_for_ev_ledger_promotion"


def paper_decision_blocker_rows(
    capacity_rows: Sequence[Mapping[str, Any]],
    *,
    summary: Mapping[str, Any],
    gates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    blockers = blockers_from_gates(gates)
    rows: list[dict[str, Any]] = []
    for row in capacity_rows:
        row_blockers = list(blockers)
        if row.get("gate_status") != "pass":
            row_blockers.append("current row has no positive cost-adjusted depth")
        rows.append(
            {
                "contract_ticker": row.get("contract_ticker"),
                "side": row.get("side"),
                "family_id": "microstructure_informed_flow",
                "model_id": DEFAULT_MODEL_ID,
                "signal_formula_key": "depth_imbalance_yes_abs_gt_0_25",  # gitleaks:allow
                "source_repo_id": "predmarket-alpha",
                "decision_time": row.get("decision_time"),
                "close_time": row.get("close_time"),
                "calibrated_probability": summary.get("conservative_calibrated_side_probability"),
                "market_probability": row.get("selected_side_executable_price"),
                "all_in_cost": row.get("all_in_cost"),
                "expected_value_per_contract": row.get("expected_value_per_contract"),
                "capacity_estimate": row.get("positive_depth_cost"),
                "correlation_cluster_key": row.get("correlation_cluster_key"),
                "decay_status": summary.get("decay_status"),
                "decay_gate_status": "pass"
                if not any("decay" in item for item in row_blockers)
                else "blocked",
                "predicted_outcome": row.get("predicted_outcome"),
                "usable": False,
                "execution_enabled": False,
                "blocker_list": list(dict.fromkeys(row_blockers)),
            }
        )
    return rows


def blockers_from_gates(gates: Sequence[Mapping[str, Any]]) -> list[str]:
    """Only report the first upstream-blocked gate to avoid downstream noise.

    Gates are ordered by dependency from upstream (evidence_artifact_safe)
    to downstream (decay_survival).  If an upstream gate is blocked the
    downstream gates cannot be independently evaluated, so they are excluded
    from the blocker list.
    """
    for item in gates:
        name = str(item.get("name") or "")
        if name == "no_usable_sizing_or_execution":
            continue
        if item.get("status") not in {"pass", "warn"}:
            return [f"{name} not passing"]
    return ["flow replay gate has not been promoted through EV ledger"]


def next_action(status: str) -> dict[str, str]:
    if status == "near_resolution_flow_replay_gates_ready_for_ev_ledger_promotion":
        return {
            "name": "kalshi_near_resolution_flow_ev_ledger_promotion",
            "why": "FDR, calibration, cost, current depth, correlation, and decay gates are all passing.",
            "stop_condition": "Stop before live eligibility until EV ledger and paper sizing produce audited rows.",
        }
    if status == "near_resolution_flow_replay_gates_blocked_no_current_candidates":
        return {
            "name": "kalshi_sports_microstructure_current_snapshot_accumulation",
            "why": "Historical flow candidate survived, but no fresh current candidates remain in the entry window.",
            "stop_condition": "Stop before inferring capacity from stale orderbooks.",
        }
    if status == "near_resolution_flow_replay_gates_blocked_decay_survival":
        return {
            "name": "kalshi_near_resolution_flow_decay_accumulation",
            "why": "Flow candidate needs stable recent-bucket survival before any paper promotion.",
            "stop_condition": "Stop before lowering decay/sample thresholds.",
        }
    if status == "near_resolution_flow_replay_gates_blocked_correlation_concentration":
        return {
            "name": "kalshi_near_resolution_flow_cluster_breadth_accumulation",
            "why": "Positive current flow capacity is too concentrated after cluster control.",
            "stop_condition": "Stop before raising max cluster share or bypassing correlation controls.",
        }
    return {
        "name": "kalshi_near_resolution_flow_gate_repair_or_accumulation",
        "why": "At least one downstream replay gate is still blocking the FDR survivor.",
        "stop_condition": "Stop before paper stake, live eligibility, account paths, or orders.",
    }


def selected_side_executable_price(row: Mapping[str, Any], side: str) -> float | None:
    if side == "yes":
        return probability(row.get("best_yes_ask"))
    no_ask = probability(row.get("best_no_ask"))
    if no_ask is not None:
        return no_ask
    yes_bid = probability(row.get("best_yes_bid"))
    return 1.0 - yes_bid if yes_bid is not None else None


def selected_side_depth(row: Mapping[str, Any], side: str) -> float:
    key = "yes_ask_depth_top1" if side == "yes" else "no_ask_depth_top1"
    try:
        return max(0.0, float(row.get(key) or 0.0))
    except (TypeError, ValueError):
        return 0.0


def cost_for_row(row: Mapping[str, Any]):
    price = probability(row.get("selected_side_executable_price"))
    return normalize_kalshi_execution_cost(
        display_price=price,
        executable_price=price,
        executable_price_source=f"{row.get('side')}_ask_from_public_microstructure_quote",
        payout_if_correct=1.0,
        ticker=str(row.get("contract_ticker") or ""),
    )


def correlation_cluster_key(row: Mapping[str, Any], *, close_time: Any) -> str:
    surface = str(row.get("sport_surface") or "sports_microstructure")
    event = str(row.get("event_ticker") or event_from_ticker(row.get("contract_ticker")) or "")
    bucket = bucket_time(close_time) or "unknown"
    return f"{surface}|{event}|{bucket}"


def event_from_ticker(ticker: Any) -> str:
    text = str(ticker or "")
    parts = text.split("-")
    if len(parts) >= 3:
        return "-".join(parts[:3])
    return text


def outcome(value: Any) -> int | None:
    if value in {0, 1}:
        return int(value)
    prob = probability(value)
    if prob is None:
        return None
    if prob >= 0.999:
        return 1
    if prob <= 0.001:
        return 0
    return None


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def gate_status(gates: Sequence[Mapping[str, Any]], name: str) -> str | None:
    for row in gates:
        if row.get("name") == name:
            return str(row.get("status") or "")
    return None


def iso_from_ts(value: float) -> str:
    return datetime.fromtimestamp(value, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_outputs(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-near-resolution-flow-replay-gates.json"
    md_path = out_dir / "kalshi-near-resolution-flow-replay-gates.md"
    csv_path = out_dir / "kalshi-near-resolution-flow-replay-gates.csv"
    capacity_csv_path = out_dir / "kalshi-near-resolution-flow-capacity-rows.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("replay_rows", []), csv_path, CSV_FIELDS)
    write_csv(report.get("capacity_rows", []), capacity_csv_path, CAPACITY_CSV_FIELDS)

    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
        "capacity_csv_path": str(capacity_csv_path),
    }
    if _path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-near-resolution-flow-replay-gates.json"
        latest_md = MACRO_DIR / "latest-kalshi-near-resolution-flow-replay-gates.md"
        latest_csv = MACRO_DIR / "latest-kalshi-near-resolution-flow-replay-gates.csv"
        latest_capacity_csv = MACRO_DIR / "latest-kalshi-near-resolution-flow-capacity-rows.csv"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        write_csv(report.get("replay_rows", []), latest_csv, CSV_FIELDS)
        write_csv(report.get("capacity_rows", []), latest_capacity_csv, CAPACITY_CSV_FIELDS)
        paths.update(
            {
                "latest_json_path": str(latest_json),
                "latest_markdown_path": str(latest_md),
                "latest_csv_path": str(latest_csv),
                "latest_capacity_csv_path": str(latest_capacity_csv),
            }
        )
    return paths


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Near-Resolution Flow Replay Gates",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Model: `{summary.get('selected_replay_model_id')}`",
        f"- Conservative probability: `{summary.get('conservative_calibrated_side_probability')}`",
        f"- Replay rows: `{summary.get('replay_row_count')}`",
        f"- Positive replay rows: `{summary.get('positive_expected_value_row_count')}`",
        f"- Current candidates: `{summary.get('current_candidate_row_count')}`",
        f"- Positive depth contracts: `{summary.get('positive_depth_contracts')}`",
        f"- Largest cluster share: `{summary.get('largest_correlation_cluster_share')}`",
        f"- Decay: `{summary.get('decay_status')}`",
        f"- Paper blocker rows: `{len(report.get('paper_decision_blocker_rows', []))}`",
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
            "Research-only artifact. No stake, order, account path, or live eligibility.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(rows: Any, path: Path, fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, Mapping):
                writer.writerow({field: row.get(field) for field in fieldnames})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-path", type=Path, default=DEFAULT_EVIDENCE_PATH)
    parser.add_argument("--microstructure-path", type=Path, default=DEFAULT_MICROSTRUCTURE_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--confidence-z", type=float, default=DEFAULT_CONFIDENCE_Z)
    parser.add_argument("--min-side-oos-labels", type=int, default=DEFAULT_MIN_SIDE_OOS_LABELS)
    parser.add_argument("--min-decay-buckets", type=int, default=DEFAULT_MIN_DECAY_BUCKETS)
    parser.add_argument("--min-decay-labels", type=int, default=DEFAULT_MIN_DECAY_LABELS)
    parser.add_argument("--max-close-hours", type=float, default=DEFAULT_MAX_CLOSE_HOURS)
    parser.add_argument(
        "--max-current-candidates", type=int, default=DEFAULT_MAX_CURRENT_CANDIDATES
    )
    parser.add_argument(
        "--max-observation-age-seconds",
        type=float,
        default=DEFAULT_MAX_OBSERVATION_AGE_SECONDS,
    )
    parser.add_argument("--max-cluster-share", type=float, default=DEFAULT_MAX_CLUSTER_SHARE)
    parser.add_argument(
        "--min-positive-capacity-contracts",
        type=float,
        default=DEFAULT_MIN_POSITIVE_CAPACITY_CONTRACTS,
    )
    parser.add_argument("--write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_near_resolution_flow_replay_gates(
        evidence_path=args.evidence_path,
        microstructure_path=args.microstructure_path,
        model_id=args.model_id,
        confidence_z=args.confidence_z,
        min_side_oos_labels=args.min_side_oos_labels,
        min_decay_buckets=args.min_decay_buckets,
        min_decay_labels=args.min_decay_labels,
        max_close_hours=args.max_close_hours,
        max_current_candidates=args.max_current_candidates,
        max_observation_age_seconds=args.max_observation_age_seconds,
        max_cluster_share=args.max_cluster_share,
        min_positive_capacity_contracts=args.min_positive_capacity_contracts,
    )
    if args.write:
        paths = write_outputs(report, args.out_dir)
        print(json.dumps({"status": report["status"], "paths": paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
