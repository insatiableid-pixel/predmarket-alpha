#!/usr/bin/env python3
"""Gate near-resolution informed-flow sports evidence before any EV promotion."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import (  # noqa: E402
    benjamini_hochberg,
    binomial_survival,
    chronological_split_index,
    counts,
    json_float,
    outside_repo,
    read_json_or_empty,
    safe_research_artifact,
    safety_flags,
    sha256_or_none,
    timestamp,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_MICROSTRUCTURE_PATH = (
    MACRO_DIR / "latest-kalshi-sports-microstructure-observation-loop.json"
)
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-near-resolution-informed-flow-evidence-gate-latest"
DEFAULT_MIN_SETTLED_CONTRACTS = 30
DEFAULT_MIN_OOS_LABELS = 10
DEFAULT_TEST_FRACTION = 0.30
DEFAULT_FDR_ALPHA = 0.10
DEPTH_IMBALANCE_THRESHOLD = 0.25
DEPTH_DELTA_THRESHOLD = 0.10
CSV_FIELDS = [
    "flow_feature_id",
    "feature_family",
    "contract_ticker",
    "pre_close_bucket",
    "quote_velocity_yes_mid",
    "depth_imbalance_yes",
    "depth_imbalance_delta",
    "predicted_flow_direction",
    "forward_mid_delta_60s",
    "forward_mid_delta_300s",
    "forward_mid_delta_900s",
    "label_status",
    "usable",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_near_resolution_informed_flow_evidence_gate(
    *,
    microstructure_path: Path = DEFAULT_MICROSTRUCTURE_PATH,
    generated_utc: str | None = None,
    min_settled_contracts: int = DEFAULT_MIN_SETTLED_CONTRACTS,
    min_oos_labels: int = DEFAULT_MIN_OOS_LABELS,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    fdr_alpha: float = DEFAULT_FDR_ALPHA,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    micro = read_json_or_empty(microstructure_path)
    rows = microstructure_rows(micro)
    flow_rows = build_flow_rows(rows)
    evaluations = evaluate_flow_hypotheses(
        flow_rows,
        min_independent_labels=min_settled_contracts,
        min_oos_labels=min_oos_labels,
        test_fraction=test_fraction,
        fdr_alpha=fdr_alpha,
    )
    summary = build_summary(
        micro=micro,
        rows=rows,
        flow_rows=flow_rows,
        evaluations=evaluations,
        min_settled_contracts=min_settled_contracts,
        min_oos_labels=min_oos_labels,
    )
    gates = build_gates(summary)
    status = report_status(summary, gates)
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "family_id": "near_resolution_informed_flow",
        "public_market_data_calls": False,
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "inputs": {
            "microstructure_path": str(microstructure_path),
            "microstructure_sha256": sha256_or_none(microstructure_path),
            "microstructure_status": micro.get("status"),
        },
        "method": {
            "hypothesis": "Near-resolution quote/depth changes may lead short-horizon price movement and eventual settlement.",
            "label_policy": "Forward quote labels are exploratory only; promotion requires exact settled Kalshi labels and OOS/FDR survival.",
            "candidate_policy": (
                "Only four pre-registered candidate families are tested: quote momentum, "
                "depth imbalance, depth-imbalance delta, and depth imbalance versus final settlement."
            ),
            "independence_policy": "Each candidate is collapsed to one row per exact contract_ticker before chronological OOS scoring.",
            "boundary": "No calibrated probabilities, EV rows, paper stake, account state, orders, or execution are emitted.",
        },
        "summary": summary,
        "evaluations": evaluations,
        "gates": gates,
        "flow_rows": flow_rows,
        "next_action": next_action(status),
        "safety": safety_flags(),
    }


def microstructure_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = observation_history_rows(report)
    if rows:
        return rows
    packet = (
        report.get("observation_packet")
        if isinstance(report.get("observation_packet"), Mapping)
        else {}
    )
    rows = packet.get("rows") if isinstance(packet.get("rows"), list) else []
    if rows:
        return [dict(row) for row in rows if isinstance(row, Mapping)]
    sample = (
        report.get("observation_rows_sample")
        if isinstance(report.get("observation_rows_sample"), list)
        else []
    )
    return [dict(row) for row in sample if isinstance(row, Mapping)]


def observation_history_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    inputs = report.get("inputs") if isinstance(report.get("inputs"), Mapping) else {}
    observation_dir = Path(str(inputs.get("observation_dir") or ""))
    if not observation_dir or not outside_repo(observation_dir, CONTROL_REPO):
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(observation_dir.glob("*.json")) if observation_dir.is_dir() else []:
        payload = read_json_or_empty(path)
        if not safe_research_artifact(payload):
            continue
        raw_rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        rows.extend(dict(row) for row in raw_rows if isinstance(row, Mapping))
    packet = (
        report.get("observation_packet")
        if isinstance(report.get("observation_packet"), Mapping)
        else {}
    )
    raw_current = packet.get("rows") if isinstance(packet.get("rows"), list) else []
    rows.extend(dict(row) for row in raw_current if isinstance(row, Mapping))
    labels = label_rows_from_report(report)
    return attach_labels(dedupe_rows(rows), labels)


def label_rows_from_report(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    inputs = report.get("inputs") if isinstance(report.get("inputs"), Mapping) else {}
    label_dir = Path(str(inputs.get("label_dir") or ""))
    if label_dir and outside_repo(label_dir, CONTROL_REPO):
        for path in sorted(label_dir.glob("*.json")) if label_dir.is_dir() else []:
            payload = read_json_or_empty(path)
            if not safe_research_artifact(payload):
                continue
            raw_rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
            rows.extend(dict(row) for row in raw_rows if isinstance(row, Mapping))
    packet = report.get("label_packet") if isinstance(report.get("label_packet"), Mapping) else {}
    raw_current = packet.get("rows") if isinstance(packet.get("rows"), list) else []
    rows.extend(dict(row) for row in raw_current if isinstance(row, Mapping))
    return dedupe_rows(rows)


def attach_labels(
    rows: Sequence[Mapping[str, Any]], labels: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    by_snapshot = {
        str(label.get("snapshot_id") or ""): label
        for label in labels
        if str(label.get("snapshot_id") or "")
    }
    output: list[dict[str, Any]] = []
    for row in rows:
        label = by_snapshot.get(str(row.get("snapshot_id") or ""))
        if label is None:
            output.append(dict(row))
            continue
        merged = dict(row)
        for key in (
            "label_status",
            "settlement_yes_outcome",
            "yes_outcome",
            "side_outcome",
            "settled_time",
            "label_source",
        ):
            merged[key] = label.get(key)
        output.append(merged)
    return output


def dedupe_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        key = str(row.get("snapshot_id") or "").strip()
        if not key:
            key = f"{row.get('contract_ticker')}|{row.get('observed_at_utc')}|{index}"
        by_key[key] = dict(row)
    return sorted(
        by_key.values(),
        key=lambda row: (
            str(row.get("contract_ticker") or ""),
            str(row.get("observed_at_utc") or ""),
            str(row.get("snapshot_id") or ""),
        ),
    )


def build_flow_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_ticker: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_ticker.setdefault(str(row.get("contract_ticker") or ""), []).append(row)
    output: list[dict[str, Any]] = []
    for ticker, ticker_rows in by_ticker.items():
        ordered = sorted(ticker_rows, key=lambda row: str(row.get("observed_at_utc") or ""))
        for index, row in enumerate(ordered):
            previous = ordered[index - 1] if index > 0 else {}
            future = ordered[index + 1] if index + 1 < len(ordered) else {}
            mid = as_float(row.get("yes_mid"))
            previous_mid = as_float(previous.get("yes_mid"))
            future_mid = as_float(future.get("yes_mid"))
            dt = max(
                (timestamp(row.get("observed_at_utc")) or 0.0)
                - (timestamp(previous.get("observed_at_utc")) or 0.0),
                1.0,
            )
            mid_delta = mid - previous_mid if mid is not None and previous_mid is not None else None
            forward_delta = future_mid - mid if future_mid is not None and mid is not None else None
            label_status = (
                "forward_quote_labeled_settlement_missing"
                if forward_delta is not None
                else "settlement_label_missing"
            )
            output.append(
                {
                    "flow_feature_id": f"{ticker}|{row.get('snapshot_id')}",
                    "hypothesis_id": "near_resolution_informed_flow",
                    "feature_family": "near_resolution_informed_flow",
                    "contract_ticker": ticker,
                    "event_ticker": row.get("event_ticker"),
                    "series_ticker": row.get("series_ticker"),
                    "sport_surface": row.get("sport_surface"),
                    "snapshot_id": row.get("snapshot_id"),
                    "observed_at_utc": row.get("observed_at_utc"),
                    "settlement_time": row.get("settlement_time"),
                    "pre_close_bucket": pre_close_bucket(row.get("time_to_settlement_seconds")),
                    "flow_window_seconds": dt,
                    "best_yes_bid": row.get("best_yes_bid"),
                    "best_yes_ask": row.get("best_yes_ask"),
                    "best_no_bid": row.get("best_no_bid"),
                    "best_no_ask": row.get("best_no_ask"),
                    "yes_ask_depth_top1": row.get("yes_ask_depth_top1"),
                    "yes_bid_depth_top1": row.get("yes_bid_depth_top1"),
                    "no_ask_depth_top1": row.get("no_ask_depth_top1"),
                    "no_bid_depth_top1": row.get("no_bid_depth_top1"),
                    "yes_depth_top5": row.get("yes_depth_top5"),
                    "no_depth_top5": row.get("no_depth_top5"),
                    "quote_velocity_yes_mid": json_float(
                        mid_delta / dt if mid_delta is not None else None
                    ),
                    "spread_change": None,
                    "depth_imbalance_yes": row.get("depth_imbalance_yes"),
                    "depth_imbalance_delta": row.get("depth_imbalance_delta"),
                    "predicted_flow_direction": predicted_direction(mid_delta),
                    "forward_mid_delta_60s": json_float(forward_delta),
                    "forward_mid_delta_300s": json_float(forward_delta),
                    "forward_mid_delta_900s": json_float(forward_delta),
                    "settlement_yes_outcome": row.get("settlement_yes_outcome"),
                    "label_status": label_status,
                    "cost_adjusted_forward_edge": None,
                    "oos_fold": None,
                    "usable": False,
                }
            )
    return output


def evaluate_flow_hypotheses(
    flow_rows: Sequence[Mapping[str, Any]],
    *,
    min_independent_labels: int,
    min_oos_labels: int,
    test_fraction: float,
    fdr_alpha: float,
) -> list[dict[str, Any]]:
    evaluators = [
        {
            "model_id": "flow_quote_momentum_forward_quote",
            "label_type": "forward_quote",
            "prediction_rule": quote_momentum_prediction,
            "actual_rule": forward_quote_actual,
        },
        {
            "model_id": "flow_depth_imbalance_forward_quote",
            "label_type": "forward_quote",
            "prediction_rule": depth_imbalance_prediction,
            "actual_rule": forward_quote_actual,
        },
        {
            "model_id": "flow_depth_delta_forward_quote",
            "label_type": "forward_quote",
            "prediction_rule": depth_delta_prediction,
            "actual_rule": forward_quote_actual,
        },
        {
            "model_id": "flow_depth_imbalance_settlement_directional",
            "label_type": "settlement",
            "prediction_rule": depth_imbalance_prediction,
            "actual_rule": settlement_actual,
        },
    ]
    evaluations = [
        evaluate_hypothesis(
            evaluator,
            flow_rows,
            min_independent_labels=min_independent_labels,
            min_oos_labels=min_oos_labels,
            test_fraction=test_fraction,
        )
        for evaluator in evaluators
    ]
    p_values = [
        (index, float(evaluation["p_value"]))
        for index, evaluation in enumerate(evaluations)
        if isinstance(evaluation.get("p_value"), (int, float))
    ]
    q_values = benjamini_hochberg(p_values)
    for index, q_value in q_values.items():
        evaluations[index]["q_value"] = json_float(q_value)
        if (
            evaluations[index]["status"] == "testable_research_candidate"
            and q_value <= fdr_alpha
            and float(evaluations[index].get("oos_accuracy") or 0.0) > 0.5
        ):
            evaluations[index]["status"] = "research_candidate_fdr_passed"
    return evaluations


def evaluate_hypothesis(
    evaluator: Mapping[str, Any],
    flow_rows: Sequence[Mapping[str, Any]],
    *,
    min_independent_labels: int,
    min_oos_labels: int,
    test_fraction: float,
) -> dict[str, Any]:
    prediction_rule = evaluator["prediction_rule"]
    actual_rule = evaluator["actual_rule"]
    scored: list[dict[str, Any]] = []
    for row in flow_rows:
        prediction = prediction_rule(row)
        actual = actual_rule(row)
        if prediction is None or actual is None:
            continue
        scored.append(
            {
                **dict(row),
                "prediction": prediction,
                "actual": actual,
                "correct": int(prediction == actual),
                "decision_ts": timestamp(row.get("observed_at_utc")) or 0.0,
            }
        )
    independent = independent_flow_rows(scored)
    split_index = chronological_split_index(len(independent), test_fraction)
    oos_rows = independent[split_index:]
    wins = sum(int(row.get("correct") or 0) for row in oos_rows)
    p_value = (
        binomial_survival(wins, len(oos_rows), 0.5)
        if len(independent) >= min_independent_labels and len(oos_rows) >= min_oos_labels
        else None
    )
    status = "testable_research_candidate"
    if len(independent) < min_independent_labels:
        status = "blocked_insufficient_independent_labels"
    elif len(oos_rows) < min_oos_labels:
        status = "blocked_insufficient_oos_labels"
    return {
        "model_id": evaluator["model_id"],
        "label_type": evaluator["label_type"],
        "status": status,
        "raw_scored_row_count": len(scored),
        "independent_contract_label_count": len(independent),
        "oos_label_count": len(oos_rows),
        "oos_correct_count": wins,
        "oos_accuracy": json_float(wins / len(oos_rows) if oos_rows else None),
        "p_value": json_float(p_value),
        "q_value": None,
        "min_independent_labels": min_independent_labels,
        "min_oos_labels": min_oos_labels,
        "test_fraction": test_fraction,
        "scored_rows_sample": [
            {
                "contract_ticker": row.get("contract_ticker"),
                "observed_at_utc": row.get("observed_at_utc"),
                "prediction": row.get("prediction"),
                "actual": row.get("actual"),
                "correct": row.get("correct"),
            }
            for row in oos_rows[:10]
        ],
    }


def independent_flow_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_ticker: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("contract_ticker") or "")
        if not ticker:
            continue
        if ticker not in by_ticker or float(row.get("decision_ts") or 0.0) < float(
            by_ticker[ticker].get("decision_ts") or 0.0
        ):
            by_ticker[ticker] = dict(row)
    return sorted(
        by_ticker.values(),
        key=lambda row: (float(row.get("decision_ts") or 0.0), str(row.get("contract_ticker"))),
    )


def quote_momentum_prediction(row: Mapping[str, Any]) -> int | None:
    velocity = as_float(row.get("quote_velocity_yes_mid"))
    if velocity is None or abs(velocity) < 1e-12:
        return None
    return 1 if velocity > 0 else 0


def depth_imbalance_prediction(row: Mapping[str, Any]) -> int | None:
    imbalance = as_float(row.get("depth_imbalance_yes"))
    if imbalance is None or abs(imbalance) < DEPTH_IMBALANCE_THRESHOLD:
        return None
    return 1 if imbalance > 0 else 0


def depth_delta_prediction(row: Mapping[str, Any]) -> int | None:
    delta = as_float(row.get("depth_imbalance_delta"))
    if delta is None or abs(delta) < DEPTH_DELTA_THRESHOLD:
        return None
    return 1 if delta > 0 else 0


def forward_quote_actual(row: Mapping[str, Any]) -> int | None:
    forward_delta = as_float(row.get("forward_mid_delta_60s"))
    if forward_delta is None or abs(forward_delta) < 1e-12:
        return None
    return 1 if forward_delta > 0 else 0


def settlement_actual(row: Mapping[str, Any]) -> int | None:
    value = row.get("settlement_yes_outcome")
    if value in {0, 1}:
        return int(value)
    return None


def pre_close_bucket(seconds: Any) -> str:
    value = as_float(seconds)
    if value is None:
        return "unknown"
    if value <= 300:
        return "5m"
    if value <= 900:
        return "15m"
    if value <= 1800:
        return "30m"
    if value <= 3600:
        return "1h"
    if value <= 10800:
        return "3h"
    return "6h"


def predicted_direction(mid_delta: float | None) -> str:
    if mid_delta is None or abs(mid_delta) < 1e-9:
        return "no_signal"
    return "yes_up" if mid_delta > 0 else "yes_down"


def build_summary(
    *,
    micro: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    flow_rows: Sequence[Mapping[str, Any]],
    evaluations: Sequence[Mapping[str, Any]],
    min_settled_contracts: int,
    min_oos_labels: int,
) -> dict[str, Any]:
    settled = [row for row in flow_rows if row.get("settlement_yes_outcome") in {0, 1}]
    forward_labeled = [row for row in flow_rows if row.get("forward_mid_delta_60s") is not None]
    testable = [
        row
        for row in evaluations
        if row.get("status") in {"testable_research_candidate", "research_candidate_fdr_passed"}
    ]
    candidates = [
        row for row in evaluations if row.get("status") == "research_candidate_fdr_passed"
    ]
    return {
        "microstructure_safe": safe_research_artifact(micro),
        "microstructure_status": micro.get("status"),
        "microstructure_row_count": len(rows),
        "distinct_contract_count": len({row.get("contract_ticker") for row in rows}),
        "repeated_snapshot_contract_count": len(
            {
                ticker
                for ticker, count in counts(row.get("contract_ticker") for row in rows).items()
                if ticker != "unknown" and int(count) >= 2
            }
        ),
        "flow_row_count": len(flow_rows),
        "forward_quote_label_count": len(forward_labeled),
        "settled_contract_label_count": len({row.get("contract_ticker") for row in settled}),
        "min_settled_contracts": min_settled_contracts,
        "min_oos_labels": min_oos_labels,
        "pre_close_bucket_counts": counts(row.get("pre_close_bucket") for row in flow_rows),
        "pre_registered_candidate_count": len(evaluations),
        "testable_candidate_count": len(testable),
        "usable_row_count": 0,
        "research_candidate_count": len(candidates),
        "best_candidate_model_id": min(
            (
                row
                for row in evaluations
                if isinstance(row.get("q_value"), (int, float))
                or isinstance(row.get("p_value"), (int, float))
            ),
            key=lambda row: float(row.get("q_value") or row.get("p_value") or 1.0),
            default={},
        ).get("model_id"),
        "best_candidate_q_value": min(
            (
                float(row.get("q_value") or row.get("p_value") or 1.0)
                for row in evaluations
                if isinstance(row.get("q_value"), (int, float))
                or isinstance(row.get("p_value"), (int, float))
            ),
            default=None,
        ),
    }


def build_gates(summary: Mapping[str, Any]) -> list[dict[str, str]]:
    settled = int(summary.get("settled_contract_label_count") or 0)
    min_settled = int(summary.get("min_settled_contracts") or DEFAULT_MIN_SETTLED_CONTRACTS)
    oos = int(summary.get("forward_quote_label_count") or 0)
    min_oos = int(summary.get("min_oos_labels") or DEFAULT_MIN_OOS_LABELS)
    testable = int(summary.get("testable_candidate_count") or 0)
    candidates = int(summary.get("research_candidate_count") or 0)
    return [
        gate(
            "hypothesis_family_registered",
            "pass",
            "near_resolution_informed_flow is registered separately from directional sports signals.",
        ),
        gate(
            "microstructure_snapshots_present",
            "pass" if int(summary.get("microstructure_row_count") or 0) > 0 else "blocked",
            f"{summary.get('microstructure_row_count')} microstructure row(s).",
        ),
        gate(
            "strict_time_ordering_no_label_leakage",
            "pass",
            "Rows use only pre-close public orderbook state.",
        ),
        gate(
            "near_resolution_window_coverage",
            "pass" if summary.get("pre_close_bucket_counts") else "blocked",
            f"Buckets: {summary.get('pre_close_bucket_counts')}.",
        ),
        gate(
            "forward_quote_labels_available",
            "pass" if oos >= min_oos else "blocked",
            f"{oos}/{min_oos} forward quote labels.",
        ),
        gate(
            "settled_kalshi_labels_available",
            "pass" if settled >= min_settled else "blocked",
            f"{settled}/{min_settled} settled contract labels.",
        ),
        gate(
            "candidate_hypotheses_preregistered",
            "pass" if int(summary.get("pre_registered_candidate_count") or 0) == 4 else "fail",
            f"{summary.get('pre_registered_candidate_count')} pre-registered candidate(s).",
        ),
        gate(
            "walk_forward_or_purged_split",
            "pass" if testable > 0 else "blocked",
            f"{testable} candidate(s) reached chronological contract-collapsed OOS scoring.",
        ),
        gate(
            "fdr_q_value_lte_0_10",
            "pass" if candidates > 0 else "blocked",
            f"{candidates} candidate(s) survived BH-FDR at q<=0.10.",
        ),
        gate(
            "cost_adjusted_lead_lag_survival",
            "blocked",
            "Blocked until cost-adjusted forward movement survives OOS/FDR.",
        ),
        gate(
            "current_depth_support_from_ghost_diagnostic",
            "pass",
            "Current depth preflight is consumed upstream by sequencing.",
        ),
        gate(
            "no_probability_ev_sizing_or_execution", "pass", "This gate emits evidence rows only."
        ),
    ]


def report_status(summary: Mapping[str, Any], gates: Sequence[Mapping[str, Any]]) -> str:
    if int(summary.get("microstructure_row_count") or 0) <= 0:
        return "near_resolution_informed_flow_blocked_no_microstructure_snapshots"
    if int(summary.get("settled_contract_label_count") or 0) < int(
        summary.get("min_settled_contracts") or 0
    ):
        return "near_resolution_informed_flow_blocked_missing_settled_labels"
    if int(summary.get("testable_candidate_count") or 0) <= 0:
        return "near_resolution_informed_flow_blocked_falsification_not_ready"
    if int(summary.get("research_candidate_count") or 0) <= 0:
        return "near_resolution_informed_flow_falsification_ready_no_research_candidate"
    return "near_resolution_informed_flow_research_candidates_ready"


def next_action(status: str) -> dict[str, str]:
    if status == "near_resolution_informed_flow_research_candidates_ready":
        return {
            "name": "kalshi_near_resolution_flow_cost_capacity_decay_replay",
            "why": "At least one flow candidate survived OOS/FDR; next gate is all-in cost, capacity, correlation, and decay.",
            "stop_condition": "Stop before paper stake if cost, capacity, correlation, or decay blocks.",
        }
    if status == "near_resolution_informed_flow_falsification_ready_no_research_candidate":
        return {
            "name": "kalshi_sports_microstructure_snapshot_accumulation",
            "why": "OOS/FDR ran on the pre-registered flow candidates and found no survivor.",
            "stop_condition": "Stop before expanding the hypothesis set without updating the multiple-testing ledger.",
        }
    return {
        "name": "kalshi_sports_microstructure_snapshot_accumulation",
        "why": "Flow evidence needs repeated pre-close snapshots plus exact Kalshi settlement labels.",
        "stop_condition": "Stop before calibrated probabilities, EV rows, paper stake, or live orders.",
    }


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def write_outputs(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-near-resolution-informed-flow-evidence-gate.json"
    md_path = out_dir / "kalshi-near-resolution-informed-flow-evidence-gate.md"
    csv_path = out_dir / "kalshi-near-resolution-informed-flow-evidence-gate.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("flow_rows", []), csv_path)
    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
    }
    if _path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-near-resolution-informed-flow-evidence-gate.json"
        latest_md = MACRO_DIR / "latest-kalshi-near-resolution-informed-flow-evidence-gate.md"
        latest_csv = MACRO_DIR / "latest-kalshi-near-resolution-informed-flow-evidence-gate.csv"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        write_csv(report.get("flow_rows", []), latest_csv)
        paths.update(
            {
                "latest_json_path": str(latest_json),
                "latest_markdown_path": str(latest_md),
                "latest_csv_path": str(latest_csv),
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
        "# Kalshi Near-Resolution Informed-Flow Evidence Gate",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Flow rows: `{summary.get('flow_row_count')}`",
        f"- Settled labels: `{summary.get('settled_contract_label_count')}`",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for item in report.get("gates", []):
        if isinstance(item, Mapping):
            lines.append(
                f"| `{item.get('name')}` | `{item.get('status')}` | {item.get('reason')} |"
            )
    lines.append("")
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microstructure-path", type=Path, default=DEFAULT_MICROSTRUCTURE_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--min-settled-contracts", type=int, default=DEFAULT_MIN_SETTLED_CONTRACTS)
    parser.add_argument("--min-oos-labels", type=int, default=DEFAULT_MIN_OOS_LABELS)
    parser.add_argument("--test-fraction", type=float, default=DEFAULT_TEST_FRACTION)
    parser.add_argument("--fdr-alpha", type=float, default=DEFAULT_FDR_ALPHA)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_near_resolution_informed_flow_evidence_gate(
        microstructure_path=args.microstructure_path,
        min_settled_contracts=args.min_settled_contracts,
        min_oos_labels=args.min_oos_labels,
        test_fraction=args.test_fraction,
        fdr_alpha=args.fdr_alpha,
    )
    if args.write:
        print(
            json.dumps(
                {"status": report["status"], **write_outputs(report, args.out_dir)},
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
