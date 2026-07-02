#!/usr/bin/env python3
"""Replay crypto proxy research candidates against all-in Kalshi costs.

This is the bridge between "a feature survived first falsification" and "is
there anything worth continuing to paper-calibrate?" It remains research-only:
no sizing, no account/order paths, no execution, and no usable edge flags.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.kalshi_execution_cost import normalize_kalshi_execution_cost  # noqa: E402

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_LABEL_DIR = Path("/home/mrwatson/manual_drops/kalshi_crypto_proxy_labels")
DEFAULT_MODEL_FALSIFICATION_PATH = MACRO_DIR / "latest-kalshi-crypto-proxy-feature-model-falsification.json"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-crypto-proxy-research-candidate-replay-latest"
DEFAULT_CONFIDENCE_Z = 1.6448536269514722
DEFAULT_MIN_SIDE_OOS_LABELS = 30
DEFAULT_MIN_DECAY_BUCKETS = 3
DEFAULT_MIN_DECAY_LABELS = 100

CSV_FIELDS = [
    "contract_ticker",
    "event_ticker",
    "decision_time",
    "close_time",
    "asset_symbol",
    "contract_family",
    "proxy_state",
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


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_crypto_proxy_research_candidate_replay(
    *,
    label_dir: Path = DEFAULT_LABEL_DIR,
    model_falsification_path: Path = DEFAULT_MODEL_FALSIFICATION_PATH,
    generated_utc: str | None = None,
    confidence_z: float = DEFAULT_CONFIDENCE_Z,
    min_side_oos_labels: int = DEFAULT_MIN_SIDE_OOS_LABELS,
    min_decay_buckets: int = DEFAULT_MIN_DECAY_BUCKETS,
    min_decay_labels: int = DEFAULT_MIN_DECAY_LABELS,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    model_report = read_json_or_empty(model_falsification_path)
    label_load = load_label_packets(label_dir)
    rows, invalid_rows = normalize_label_rows(label_load["rows"])
    independent_rows = independent_contract_rows(rows)
    candidate_eval = research_candidate_evaluation(model_report)
    selected_rows = [row for row in independent_rows if proxy_state_prediction(row.get("proxy_state")) is not None]
    split_index = chronological_split_index(len(independent_rows), model_report)
    oos_rows = [
        row
        for row in independent_rows[split_index:]
        if proxy_state_prediction(row.get("proxy_state")) is not None
    ]
    calibration = conservative_side_probability(
        oos_rows=oos_rows,
        confidence_z=confidence_z,
        min_side_oos_labels=min_side_oos_labels,
        candidate_eval=candidate_eval,
    )
    replay_rows = replay_contract_rows(selected_rows, calibration)
    summary = build_summary(
        label_load=label_load,
        invalid_rows=invalid_rows,
        independent_rows=independent_rows,
        selected_rows=selected_rows,
        oos_rows=oos_rows,
        replay_rows=replay_rows,
        calibration=calibration,
        candidate_eval=candidate_eval,
        min_side_oos_labels=min_side_oos_labels,
        min_decay_buckets=min_decay_buckets,
        min_decay_labels=min_decay_labels,
    )
    gates = build_gates(summary=summary, label_dir=label_dir, replay_rows=replay_rows)
    status = report_status(summary, gates)
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
        "inputs": {
            "label_dir": str(label_dir),
            "model_falsification_path": str(model_falsification_path),
            "label_packet_count": label_load["packet_count"],
            "unsafe_packet_count": len(label_load["unsafe_packets"]),
            "model_falsification_status": model_report.get("status"),
        },
        "method": {
            "replay_boundary": "Historical paper replay only; no live orders, positions, staking, sizing, or usable edge flags.",
            "independence_rule": "Collapse repeated observations by exact contract_ticker; keep earliest decision_time.",
            "model_rule": "proxy_state_directional_accuracy: above => buy YES, below => buy NO.",
            "calibration_rule": (
                "Use the Wilson lower confidence bound of OOS directional accuracy as the conservative "
                "selected-side probability. This is a preflight calibration, not a deployed model."
            ),
            "cost_rule": (
                "YES cost uses yes_ask; NO cost uses 1 - yes_bid; both pass through the Kalshi "
                "execution-cost normalizer with official fee estimates."
            ),
            "capacity_rule": "Blocked until public depth or validated local order-book depth exists.",
            "correlation_rule": "Blocked until within-venue covariance or cluster exposure controls exist.",
            "decay_rule": "Blocked until recurring time buckets/regimes show stable OOS survival.",
        },
        "calibration": calibration,
        "summary": summary,
        "gates": gates,
        "replay_rows": replay_rows,
        "invalid_label_rows_sample": invalid_rows[:50],
        "next_action": next_action(status),
        "safety": safety_flags(),
    }


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


def normalize_label_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for row in rows:
        errors: list[str] = []
        ticker = str(row.get("contract_ticker") or "").strip()
        outcome = outcome_value(row.get("yes_outcome", row.get("side_outcome")))
        decision_ts = timestamp(row.get("decision_time"))
        close_ts = timestamp(row.get("close_time"))
        yes_bid = probability(row.get("yes_bid"))
        yes_ask = probability(row.get("yes_ask"))
        yes_spread = optional_float(row.get("yes_spread"))
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
                "asset_symbol": row.get("asset_symbol"),
                "contract_family": row.get("contract_family"),
                "proxy_state": row.get("proxy_state"),
                "yes_bid": yes_bid,
                "yes_ask": yes_ask,
                "yes_spread": yes_spread,
                "yes_outcome": outcome,
                "decision_ts": decision_ts,
                "close_ts": close_ts,
                "decision_time": iso_from_timestamp(decision_ts),
                "close_time": iso_from_timestamp(close_ts),
            }
        )
    normalized.sort(key=lambda item: (item["decision_ts"], item["contract_ticker"]))
    return normalized, invalid


def independent_contract_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_ticker: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("contract_ticker") or "")
        if not ticker:
            continue
        if ticker not in by_ticker or float(row.get("decision_ts") or 0) < float(by_ticker[ticker].get("decision_ts") or 0):
            by_ticker[ticker] = dict(row)
    return sorted(by_ticker.values(), key=lambda item: (item["decision_ts"], item["contract_ticker"]))


def research_candidate_evaluation(model_report: Mapping[str, Any]) -> dict[str, Any] | None:
    for item in model_report.get("evaluations", []):
        if (
            isinstance(item, Mapping)
            and item.get("model_id") == "proxy_state_directional_accuracy"
            and item.get("status") == "research_candidate_fdr_passed"
        ):
            return dict(item)
    return None


def conservative_side_probability(
    *,
    oos_rows: Sequence[Mapping[str, Any]],
    confidence_z: float,
    min_side_oos_labels: int,
    candidate_eval: Mapping[str, Any] | None,
) -> dict[str, Any]:
    wins = sum(1 for row in oos_rows if selected_side_outcome(row) == 1)
    count = len(oos_rows)
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
        "model_id": "proxy_state_directional_accuracy",
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


def replay_contract_rows(
    rows: Sequence[Mapping[str, Any]],
    calibration: Mapping[str, Any],
) -> list[dict[str, Any]]:
    calibrated = probability(calibration.get("conservative_calibrated_side_probability"))
    replay_rows: list[dict[str, Any]] = []
    for row in rows:
        prediction = proxy_state_prediction(row.get("proxy_state"))
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
        expected_value = calibrated - all_in_cost if calibrated is not None and all_in_cost is not None else None
        margin = calibrated - break_even if calibrated is not None and break_even is not None else None
        outcome = selected_side_outcome(row)
        paper_result = outcome - all_in_cost if outcome is not None and all_in_cost is not None else None
        cluster_key = correlation_cluster_key(row)
        replay_rows.append(
            {
                "contract_ticker": row.get("contract_ticker"),
                "event_ticker": row.get("event_ticker"),
                "series_ticker": row.get("series_ticker"),
                "decision_time": row.get("decision_time"),
                "close_time": row.get("close_time"),
                "asset_symbol": row.get("asset_symbol"),
                "contract_family": row.get("contract_family"),
                "proxy_state": row.get("proxy_state"),
                "predicted_side": side,
                "yes_outcome": row.get("yes_outcome"),
                "selected_side_outcome": outcome,
                "yes_bid": json_float(row.get("yes_bid")),
                "yes_ask": json_float(row.get("yes_ask")),
                "yes_spread": json_float(row.get("yes_spread")),
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


def build_summary(
    *,
    label_load: Mapping[str, Any],
    invalid_rows: Sequence[Mapping[str, Any]],
    independent_rows: Sequence[Mapping[str, Any]],
    selected_rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    replay_rows: Sequence[Mapping[str, Any]],
    calibration: Mapping[str, Any],
    candidate_eval: Mapping[str, Any] | None,
    min_side_oos_labels: int,
    min_decay_buckets: int,
    min_decay_labels: int,
) -> dict[str, Any]:
    positive = [row for row in replay_rows if positive_number(row.get("expected_value_per_contract"))]
    costed = [row for row in replay_rows if row.get("all_in_cost") is not None]
    cluster_counts = counts(row.get("correlation_cluster_key") for row in replay_rows)
    close_bucket_counts = counts(bucket_time(row.get("close_time")) for row in selected_rows)
    paper_results = [float(row["paper_result_per_contract"]) for row in replay_rows if row.get("paper_result_per_contract") is not None]
    margins = [float(row["margin_probability"]) for row in replay_rows if row.get("margin_probability") is not None]
    decay = decay_summary(oos_rows)
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
        "positive_expected_value_rate": json_float(len(positive) / len(replay_rows) if replay_rows else None),
        "candidate_research_model_present": candidate_eval is not None,
        "calibration_status": calibration.get("status"),
        "conservative_calibrated_side_probability": calibration.get("conservative_calibrated_side_probability"),
        "raw_oos_accuracy": calibration.get("raw_oos_accuracy"),
        "source_model_q_value": calibration.get("source_model_q_value"),
        "mean_margin_probability": json_float(mean(margins)),
        "median_margin_probability": json_float(median(margins)),
        "mean_expected_value_per_contract": json_float(mean([float(row["expected_value_per_contract"]) for row in replay_rows if row.get("expected_value_per_contract") is not None])),
        "historical_paper_result_sum": json_float(sum(paper_results) if paper_results else None),
        "historical_paper_result_mean": json_float(mean(paper_results)),
        "asset_counts": counts(row.get("asset_symbol") for row in independent_rows),
        "contract_family_counts": counts(row.get("contract_family") for row in independent_rows),
        "predicted_side_counts": counts(row.get("predicted_side") for row in replay_rows),
        "cost_quality_counts": counts(row.get("cost_quality") for row in replay_rows),
        "correlation_cluster_count": len(cluster_counts),
        "largest_correlation_cluster_key": next(iter(cluster_counts), None),
        "largest_correlation_cluster_count": next(iter(cluster_counts.values()), 0) if cluster_counts else 0,
        "close_bucket_count": len(close_bucket_counts),
        "close_bucket_counts": close_bucket_counts,
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


def build_gates(
    *,
    summary: Mapping[str, Any],
    label_dir: Path,
    replay_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    decay_pass = (
        int(summary.get("independent_contract_label_count") or 0) >= int(summary.get("min_decay_labels") or 0)
        and int(summary.get("decay_bucket_count") or 0) >= int(summary.get("min_decay_buckets") or 0)
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
            "Crypto proxy label packets must stay outside the repo.",
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
            if replay_rows and int(summary.get("costed_replay_row_count") or 0) == int(summary.get("replay_row_count") or 0)
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
                f"requires {summary.get('min_decay_buckets')} bucket(s) and {summary.get('min_decay_labels')} independent labels. "
                f"Recent bucket {summary.get('recent_bucket_key')} accuracy {summary.get('recent_bucket_accuracy')} "
                f"({summary.get('recent_bucket_label_count')} labels); "
                f"cumulative accuracy {summary.get('cumulative_decay_accuracy')} across {summary.get('total_decay_labels')} labels; "
                f"{summary.get('passing_bucket_count')}/{summary.get('decay_bucket_count')} bucket(s) pass >= 0.5."
            ),
        ),
        gate(
            "no_usable_ev_sizing_or_execution",
            "pass"
            if int(summary.get("usable_row_count") or 0) == 0 and all(row.get("usable") is False for row in replay_rows)
            else "fail",
            "Replay remains research-only with zero usable rows and no sizing or execution.",
        ),
    ]


def report_status(summary: Mapping[str, Any], gates: Sequence[Mapping[str, Any]]) -> str:
    if not summary.get("candidate_research_model_present"):
        return "crypto_proxy_research_candidate_replay_blocked_missing_research_candidate"
    if int(summary.get("replay_row_count") or 0) == 0:
        return "crypto_proxy_research_candidate_replay_blocked_missing_replay_rows"
    if any(item.get("status") == "fail" for item in gates):
        return "crypto_proxy_research_candidate_replay_failed_safety_gate"
    hard_blockers = {
        "capacity_depth_available",
        "correlation_control_available",
        "decay_survival_available",
    }
    if any(item.get("name") in hard_blockers and item.get("status") != "pass" for item in gates):
        return "crypto_proxy_research_candidate_replay_blocked_predeployment_gates"
    if int(summary.get("positive_expected_value_row_count") or 0) > 0:
        return "crypto_proxy_research_candidate_replay_ready_for_paper_probability_overlay"
    return "crypto_proxy_research_candidate_replay_ready_no_positive_cost_adjusted_rows"


def next_action(status: str) -> dict[str, str]:
    if status == "crypto_proxy_research_candidate_replay_blocked_predeployment_gates":
        return {
            "name": "kalshi_crypto_proxy_capacity_correlation_decay",
            "why": (
                "A research candidate has conservative cost-adjusted replay rows, but capacity, correlation, "
                "and decay gates block any usable edge."
            ),
            "stop_condition": "Stop before sizing, execution, account/order paths, or treating positive replay rows as deployable.",
        }
    if status == "crypto_proxy_research_candidate_replay_ready_for_paper_probability_overlay":
        return {
            "name": "kalshi_crypto_proxy_paper_probability_overlay",
            "why": "Replay gates are research-ready; next work is a paper-only probability overlay with live decay monitoring.",
            "stop_condition": "Stop before real positions, execution, or account/order paths.",
        }
    return {
        "name": "kalshi_crypto_proxy_signal_family_rotation",
        "why": "The current candidate is missing, uncosted, or not positive after conservative cost replay.",
        "stop_condition": "Stop before discretionary feature selection; register and falsify new feature families.",
    }


def write_crypto_proxy_research_candidate_replay(
    report: Mapping[str, Any],
    out_dir: Path = DEFAULT_OUT_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-crypto-proxy-research-candidate-replay.json"
    markdown_path = out_dir / "kalshi-crypto-proxy-research-candidate-replay.md"
    csv_path = out_dir / "kalshi-crypto-proxy-research-candidate-replay.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, csv_path)
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-crypto-proxy-research-candidate-replay.json"
    latest_md = MACRO_DIR / "latest-kalshi-crypto-proxy-research-candidate-replay.md"
    latest_csv = MACRO_DIR / "latest-kalshi-crypto-proxy-research-candidate-replay.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, latest_csv)
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "csv_path": str(csv_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
        "latest_csv_path": str(latest_csv),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = mapping(report.get("summary"))
    calibration = mapping(report.get("calibration"))
    lines = [
        "# Kalshi Crypto Proxy Research Candidate Replay",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Independent labels: `{summary.get('independent_contract_label_count')}`",
        f"- OOS selected rows: `{summary.get('oos_selected_row_count')}`",
        f"- Conservative selected-side probability: `{calibration.get('conservative_calibrated_side_probability')}`",
        f"- Positive cost-adjusted replay rows: `{summary.get('positive_expected_value_row_count')}`",
        f"- Usable rows: `{summary.get('usable_row_count')}`",
        "",
        "## Gates",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for item in report.get("gates", []):
        if isinstance(item, Mapping):
            lines.append(f"| `{item.get('name')}` | `{item.get('status')}` | {item.get('reason')} |")
    lines.extend(
        [
            "",
            "## Replay Summary",
            "",
            f"- Mean margin probability: `{summary.get('mean_margin_probability')}`",
            f"- Median margin probability: `{summary.get('median_margin_probability')}`",
            f"- Mean expected value per contract: `{summary.get('mean_expected_value_per_contract')}`",
            f"- Historical paper result sum: `{summary.get('historical_paper_result_sum')}`",
            f"- Largest correlation cluster: `{summary.get('largest_correlation_cluster_key')}` "
            f"({summary.get('largest_correlation_cluster_count')} rows)",
            "",
            "## Guardrail",
            "",
            "This report is not a betting recommendation. It never marks rows usable and does not size or execute.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(report: Mapping[str, Any], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in report.get("replay_rows", []):
            if isinstance(row, Mapping):
                writer.writerow({field: row.get(field) for field in CSV_FIELDS})


def selected_side_price(row: Mapping[str, Any], side: str) -> float | None:
    if side == "yes":
        return probability(row.get("yes_ask"))
    yes_bid = probability(row.get("yes_bid"))
    return 1.0 - yes_bid if yes_bid is not None else None


def selected_side_outcome(row: Mapping[str, Any]) -> int | None:
    prediction = proxy_state_prediction(row.get("proxy_state"))
    yes_outcome = outcome_value(row.get("yes_outcome"))
    if prediction is None or yes_outcome is None:
        return None
    return yes_outcome if prediction == 1 else 1 - yes_outcome


def proxy_state_prediction(value: Any) -> int | None:
    text = str(value or "").lower()
    if "above" in text:
        return 1
    if "below" in text:
        return 0
    return None


def chronological_split_index(count: int, model_report: Mapping[str, Any]) -> int:
    method = model_report.get("method") if isinstance(model_report.get("method"), Mapping) else {}
    test_fraction = optional_float(method.get("test_fraction"))
    if test_fraction is None:
        test_fraction = 0.30
    if count <= 0:
        return 0
    test_count = max(1, math.ceil(count * min(max(test_fraction, 0.0), 1.0)))
    return max(0, count - test_count)


def wilson_lower_bound(wins: int, count: int, z: float) -> float:
    if count <= 0:
        return 0.0
    p_hat = wins / count
    z2 = z * z
    denominator = 1 + z2 / count
    center = p_hat + z2 / (2 * count)
    margin = z * math.sqrt((p_hat * (1 - p_hat) + z2 / (4 * count)) / count)
    return max(0.0, min(1.0, (center - margin) / denominator))


def decay_summary(oos_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compute per-close-bucket decay evidence from OOS rows.

    The gate threshold is unchanged: the single most-recent bucket must have
    accuracy >= 0.5 (not worse than random).  The returned dict now also
    carries full per-bucket detail so the evidence is auditable across
    repeated settled-bucket snapshots without lowering any threshold.
    """
    buckets: dict[str, list[int]] = defaultdict(list)
    for row in oos_rows:
        bucket = bucket_time(row.get("close_time"))
        outcome = selected_side_outcome(row)
        if bucket and outcome is not None:
            buckets[bucket].append(outcome)
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
        decay_buckets.append({
            "bucket": key,
            "label_count": n,
            "correct_count": sum(outcomes),
            "accuracy": json_float(acc),
            "pass_threshold": acc is not None and acc >= 0.5,
        })
    recent_key = sorted_keys[-1]
    recent = buckets[recent_key]
    accuracy = sum(recent) / len(recent) if recent else None
    status = "recent_bucket_not_worse_than_random" if accuracy is not None and accuracy >= 0.5 else "recent_bucket_below_random"
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


def correlation_cluster_key(row: Mapping[str, Any]) -> str:
    return "|".join(
        str(part or "unknown")
        for part in (
            row.get("asset_symbol"),
            row.get("contract_family"),
            bucket_time(row.get("close_time")),
        )
    )


def bucket_time(value: Any) -> str | None:
    ts = timestamp(value)
    if ts is None:
        return None
    parsed = datetime.fromtimestamp(ts, UTC)
    return parsed.strftime("%Y-%m-%dT%H:%MZ")


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def read_json_or_empty(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return raw if isinstance(raw, dict) else {}


def safe_research_artifact(payload: Mapping[str, Any]) -> bool:
    safety = payload.get("safety") if isinstance(payload.get("safety"), Mapping) else {}
    return (
        payload.get("research_only") is True
        and payload.get("execution_enabled") is False
        and payload.get("market_execution") is False
        and payload.get("account_or_order_paths") is False
        and payload.get("database_writes") is False
        and safety.get("market_execution") is False
        and safety.get("account_or_order_paths") is False
        and safety.get("database_writes") is False
    )


def outside_repo(path: Path) -> bool:
    try:
        resolved = path.resolve()
        CONTROL_REPO.resolve()
    except OSError:
        return False
    return CONTROL_REPO.resolve() not in (resolved, *resolved.parents)


def outcome_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    number = probability(value)
    if number is not None:
        if number >= 0.999:
            return 1
        if number <= 0.001:
            return 0
    text = str(value or "").strip().lower()
    if text in {"yes", "true", "win", "1"}:
        return 1
    if text in {"no", "false", "loss", "0"}:
        return 0
    return None


def probability(value: Any) -> float | None:
    number = optional_float(value)
    return number if number is not None and 0.0 <= number <= 1.0 else None


def optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip().rstrip("%")
            if not value:
                return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def positive_number(value: Any) -> bool:
    number = optional_float(value)
    return number is not None and number > 0


def timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        number = None
    if number is not None:
        return number if math.isfinite(number) else None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def iso_from_timestamp(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def counts(values: Sequence[Any]) -> dict[str, int]:
    counter = Counter(str(value if value is not None else "unknown") for value in values)
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


def json_float(value: Any) -> float | None:
    number = optional_float(value)
    return round(number, 10) if number is not None else None


def mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def safety_flags() -> dict[str, bool]:
    return {
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": False,
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "raw_payloads_copied_to_repo": False,
        "staking_or_sizing_guidance": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument("--model-falsification-path", type=Path, default=DEFAULT_MODEL_FALSIFICATION_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--confidence-z", type=float, default=DEFAULT_CONFIDENCE_Z)
    parser.add_argument("--min-side-oos-labels", type=int, default=DEFAULT_MIN_SIDE_OOS_LABELS)
    parser.add_argument("--min-decay-buckets", type=int, default=DEFAULT_MIN_DECAY_BUCKETS)
    parser.add_argument("--min-decay-labels", type=int, default=DEFAULT_MIN_DECAY_LABELS)
    parser.add_argument("--write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_crypto_proxy_research_candidate_replay(
        label_dir=args.label_dir,
        model_falsification_path=args.model_falsification_path,
        confidence_z=args.confidence_z,
        min_side_oos_labels=args.min_side_oos_labels,
        min_decay_buckets=args.min_decay_buckets,
        min_decay_labels=args.min_decay_labels,
    )
    if args.write:
        paths = write_crypto_proxy_research_candidate_replay(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], "paths": paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
