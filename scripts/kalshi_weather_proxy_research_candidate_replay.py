#!/usr/bin/env python3
"""Replay weather research candidates against all-in Kalshi costs via the engine.

This is the weather analog of ``scripts/kalshi_sports_proxy_research_candidate_replay.py``.
It reuses the engine's ``build_replay_calibration()`` for Wilson lower-bound calibration
and ``kalshi_execution_cost`` for all-in cost math — demonstrating the spine is closed
for modification (zero spine edits).

Weather-specific differences:
- Prediction rule: ``weather_prediction_rule`` (bracket probability threshold rule).
- Cluster key: ``station|bracket|date`` (each station-bracket-day is an independent cluster).
- Labels from ``/home/mrwatson/manual_drops/kalshi_weather_proxy_labels/``.
- Falsification report from ``latest-kalshi-weather-proxy-feature-model-falsification.json``.
- Output artifacts under ``docs/codex/macro/latest-kalshi-weather-proxy-research-candidate-replay.*``.
- Every row ``usable=false``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = CONTROL_REPO / "scripts"
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from predmarket.engine import (  # noqa: E402
    build_decay_summary,
    build_replay_calibration,
    chronological_split_index,
    independent_contract_rows,
)
from predmarket.kalshi_execution_cost import normalize_kalshi_execution_cost  # noqa: E402
from predmarket.shared_helpers import (  # noqa: E402
    counts,
    gate,
    iso_from_timestamp,
    json_float,
    mean,
    median,
    outcome_value,
    positive_number,
    probability,
    read_json_or_empty,
    safe_research_artifact,
    safety_flags,
    timestamp,
    utc_now,
)
from predmarket.weather_family import (  # noqa: E402
    weather_cluster_key_composer,
    weather_prediction_rule,
)


def outside_repo(path: Path) -> bool:
    """Check if path is outside the repository working tree."""
    try:
        path.expanduser().resolve().relative_to(CONTROL_REPO.resolve())
    except (ValueError, OSError):
        return True
    return False


MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_LABEL_DIR = Path("/home/mrwatson/manual_drops/kalshi_weather_proxy_labels")
DEFAULT_MODEL_FALSIFICATION_PATH = (
    MACRO_DIR / "latest-kalshi-weather-proxy-feature-model-falsification.json"
)
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-weather-proxy-research-candidate-replay-latest"

# Binding constants
CONFIDENCE_Z = 1.6448536269514722
MIN_SIDE_OOS_LABELS = 30
MIN_DECAY_BUCKETS = 3
MIN_DECAY_LABELS = 100

# Status prefix
STATUS_PREFIX = "weather_proxy"

# CSV output fields
REPLAY_CSV_FIELDS = [
    "contract_ticker",
    "event_ticker",
    "decision_time",
    "close_time",
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


# ---------------------------------------------------------------------------
# Label loading (generic)
# ---------------------------------------------------------------------------


def load_label_packets(label_dir: Path) -> dict[str, Any]:
    """Load label packets from *label_dir*."""
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


def normalize_label_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Normalize label rows for replay processing."""
    normalized: list[dict[str, Any]] = []
    for row in rows:
        ticker = str(row.get("contract_ticker") or "").strip()
        outcome = outcome_value(row.get("yes_outcome"))
        decision_time = row.get("decision_time")
        close_time = row.get("close_time")
        decision_ts = timestamp(decision_time)
        close_ts = timestamp(close_time)
        if not ticker or outcome is None or decision_ts is None or close_ts is None:
            continue
        normalized.append(
            {
                "contract_ticker": ticker,
                "event_ticker": row.get("event_ticker"),
                "series_ticker": row.get("series_ticker"),
                "weather_family": row.get("weather_family", row.get("series_ticker")),
                "station_id": row.get("station_id"),
                "bracket_probability": row.get("bracket_probability"),
                "predicted_side": row.get("predicted_side"),
                "yes_ask": row.get("yes_ask"),
                "yes_bid": row.get("yes_bid"),
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
    return normalized


# ---------------------------------------------------------------------------
# Replay row construction (weather-specific: uses weather prediction & cluster key)
# ---------------------------------------------------------------------------


def selected_side_price(row: Mapping[str, Any], side: str) -> float | None:
    if side == "yes":
        return probability(row.get("yes_ask"))
    yes_bid = probability(row.get("yes_bid"))
    return 1.0 - yes_bid if yes_bid is not None else None


def selected_side_outcome_fn(row: Mapping[str, Any]) -> int | None:
    prediction = weather_prediction_rule(row)[0]
    yes_outcome = outcome_value(row.get("yes_outcome"))
    if prediction is None or yes_outcome is None:
        return None
    return yes_outcome if prediction == 1 else 1 - yes_outcome


def build_replay_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    calibration: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Build replay rows with all-in cost math."""
    calibrated = probability(calibration.get("conservative_calibrated_side_probability"))
    replay_rows: list[dict[str, Any]] = []
    for row in rows:
        prediction = weather_prediction_rule(row)[0]
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
        outcome = selected_side_outcome_fn(row)
        paper_result = (
            outcome - all_in_cost if outcome is not None and all_in_cost is not None else None
        )
        cluster_key = weather_cluster_key_composer(row)
        replay_rows.append(
            {
                "contract_ticker": row.get("contract_ticker"),
                "event_ticker": row.get("event_ticker"),
                "series_ticker": row.get("series_ticker"),
                "weather_family": row.get("weather_family"),
                "station_id": row.get("station_id"),
                "decision_time": row.get("decision_time"),
                "close_time": row.get("close_time"),
                "bracket_probability": json_float(row.get("bracket_probability")),
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


def research_candidate_evaluation(
    model_report: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Find the first research_candidate_fdr_passed evaluation."""
    for item in model_report.get("evaluations", []):
        if isinstance(item, Mapping) and item.get("status") == "research_candidate_fdr_passed":
            return dict(item)
    return None


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------


def build_summary(
    *,
    label_load: Mapping[str, Any],
    normalized_rows: Sequence[Mapping[str, Any]],
    independent_rows: Sequence[Mapping[str, Any]],
    selected_rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    replay_rows: Sequence[Mapping[str, Any]],
    calibration: Mapping[str, Any],
    candidate_eval: Mapping[str, Any] | None,
    model_falsification_status: str,
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
    decay = build_decay_summary(oos_rows, weather_prediction_rule)

    return {
        "model_falsification_status": model_falsification_status,
        "label_packet_count": label_load.get("packet_count", 0),
        "unsafe_label_packet_count": len(label_load.get("unsafe_packets", [])),
        "raw_label_row_count": len(label_load.get("rows", [])),
        "normalized_label_row_count": len(normalized_rows),
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
        "station_counts": counts(row.get("station_id") for row in replay_rows),
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
        "min_side_oos_labels": MIN_SIDE_OOS_LABELS,
        "min_decay_buckets": MIN_DECAY_BUCKETS,
        "min_decay_labels": MIN_DECAY_LABELS,
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
        int(summary.get("independent_contract_label_count") or 0) >= MIN_DECAY_LABELS
        and int(summary.get("decay_bucket_count") or 0) >= MIN_DECAY_BUCKETS
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
            "Weather proxy label packets must stay outside the repo.",
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
                f"requires {MIN_DECAY_BUCKETS} bucket(s) and {MIN_DECAY_LABELS} independent labels. "
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


def report_status(summary: Mapping[str, Any], gates: Sequence[Mapping[str, Any]]) -> str:
    prefix = STATUS_PREFIX
    if not summary.get("candidate_research_model_present"):
        return f"{prefix}_research_candidate_replay_blocked_missing_research_candidate"
    if int(summary.get("replay_row_count") or 0) == 0:
        return f"{prefix}_research_candidate_replay_blocked_missing_replay_rows"
    if any(item.get("status") == "fail" for item in gates):
        return f"{prefix}_research_candidate_replay_failed_safety_gate"
    hard_blockers = {
        "capacity_depth_available",
        "correlation_control_available",
        "decay_survival_available",
    }
    if any(item.get("name") in hard_blockers and item.get("status") != "pass" for item in gates):
        return f"{prefix}_research_candidate_replay_blocked_predeployment_gates"
    if int(summary.get("positive_expected_value_row_count") or 0) > 0:
        return f"{prefix}_research_candidate_replay_ready_for_paper_probability_overlay"
    return f"{prefix}_research_candidate_replay_ready_no_positive_cost_adjusted_rows"


def next_action(status: str) -> dict[str, str]:
    prefix_mapping = STATUS_PREFIX
    blocked_prefix = f"{prefix_mapping}_research_candidate_replay"
    if status == f"{blocked_prefix}_blocked_predeployment_gates":
        return {
            "name": "kalshi_weather_proxy_capacity_correlation_decay",
            "why": "A research candidate has conservative cost-adjusted replay rows, but capacity, correlation, and decay gates block any usable edge.",
            "stop_condition": "Stop before sizing, execution, account/order paths, or treating positive replay rows as deployable.",
        }
    if status == f"{blocked_prefix}_ready_for_paper_probability_overlay":
        return {
            "name": "kalshi_weather_proxy_paper_probability_overlay",
            "why": "Replay gates are research-ready; next work is a paper-only probability overlay with live decay monitoring.",
            "stop_condition": "Stop before real positions, execution, or account/order paths.",
        }
    return {
        "name": "kalshi_weather_proxy_signal_family_rotation",
        "why": "The current candidate is missing, uncosted, or not positive after conservative cost replay.",
        "stop_condition": "Stop before discretionary feature selection; register and falsify new feature families.",
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    calibration = (
        report.get("calibration") if isinstance(report.get("calibration"), Mapping) else {}
    )
    lines = [
        "# Kalshi Weather Proxy Research Candidate Replay",
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
            lines.append(
                f"| `{item.get('name')}` | `{item.get('status')}` | {item.get('reason')} |"
            )
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


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_weather_proxy_research_candidate_replay(
    *,
    label_dir: Path = DEFAULT_LABEL_DIR,
    model_falsification_path: Path = DEFAULT_MODEL_FALSIFICATION_PATH,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    """Build the weather proxy replay report via the engine's generic calibration."""
    generated = generated_utc or utc_now()

    # Load upstream artifacts
    model_report = read_json_or_empty(model_falsification_path)
    label_load = load_label_packets(label_dir)

    # Normalize and deduplicate labels
    normalized_rows = normalize_label_rows(label_load.get("rows", []))
    independent_rows = independent_contract_rows(normalized_rows)

    # Find research candidate
    candidate_eval = research_candidate_evaluation(model_report)

    # Select rows with predictions
    selected_rows = [row for row in independent_rows if weather_prediction_rule(row)[0] is not None]

    # Chronological OOS split (using model's test_fraction)
    test_fraction = float(model_report.get("method", {}).get("test_fraction", 0.30))
    split_index = chronological_split_index(len(independent_rows), test_fraction)
    oos_rows = [
        row for row in independent_rows[split_index:] if weather_prediction_rule(row)[0] is not None
    ]

    # Run calibration through the engine's generic spine
    calibration = build_replay_calibration(
        oos_rows=oos_rows,
        prediction_rule=weather_prediction_rule,
        confidence_z=CONFIDENCE_Z,
        min_side_oos_labels=MIN_SIDE_OOS_LABELS,
        candidate_eval=candidate_eval,
    )

    # Build replay rows with all-in cost
    replay_rows = build_replay_rows(
        selected_rows,
        calibration=calibration,
    )

    summary = build_summary(
        label_load=label_load,
        normalized_rows=normalized_rows,
        independent_rows=independent_rows,
        selected_rows=selected_rows,
        oos_rows=oos_rows,
        replay_rows=replay_rows,
        calibration=calibration,
        candidate_eval=candidate_eval,
        model_falsification_status=str(model_report.get("status", "")),
    )
    gates = build_gates(
        summary=summary,
        label_dir=label_dir,
        replay_rows=replay_rows,
    )
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
            "label_packet_count": label_load.get("packet_count"),
            "unsafe_packet_count": len(label_load.get("unsafe_packets", [])),
            "model_falsification_status": model_report.get("status"),
        },
        "method": {
            "engine_stage": "build_replay_calibration from predmarket.engine",
            "calibration_rule": (
                "Use the Wilson lower confidence bound of OOS directional accuracy as the conservative "
                "selected-side probability. This is a preflight calibration, not a deployed model."
            ),
            "cost_rule": (
                "YES cost uses yes_ask; NO cost uses 1 - yes_bid; both pass through the Kalshi "
                "execution-cost normalizer with official fee estimates."
            ),
            "prediction_rule": "weather_prediction_rule (bracket probability threshold rule)",
            "cluster_key": "station | bracket | date via weather_cluster_key_composer",
            "replay_boundary": "Historical paper replay only; no live orders, positions, staking, sizing, or usable edge flags.",
        },
        "calibration": calibration,
        "summary": summary,
        "gates": gates,
        "replay_rows": replay_rows,
        "next_action": next_action(status),
        "safety": safety_flags(),
    }


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def write_weather_proxy_research_candidate_replay(
    report: Mapping[str, Any],
    out_dir: Path = DEFAULT_OUT_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-weather-proxy-research-candidate-replay.json"
    markdown_path = out_dir / "kalshi-weather-proxy-research-candidate-replay.md"
    csv_path = out_dir / "kalshi-weather-proxy-research-candidate-replay.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    _write_csv(report, csv_path)
    # Write latest-* pointers
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-weather-proxy-research-candidate-replay.json"
    latest_md = MACRO_DIR / "latest-kalshi-weather-proxy-research-candidate-replay.md"
    latest_csv = MACRO_DIR / "latest-kalshi-weather-proxy-research-candidate-replay.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    _write_csv(report, latest_csv)
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "csv_path": str(csv_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
        "latest_csv_path": str(latest_csv),
    }


def _write_csv(report: Mapping[str, Any], path: Path) -> None:
    import csv as _csv

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = _csv.DictWriter(handle, fieldnames=REPLAY_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in report.get("replay_rows", []):
            if isinstance(row, Mapping):
                writer.writerow({field: row.get(field) for field in REPLAY_CSV_FIELDS})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument(
        "--model-falsification-path", type=Path, default=DEFAULT_MODEL_FALSIFICATION_PATH
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_weather_proxy_research_candidate_replay(
        label_dir=args.label_dir,
        model_falsification_path=args.model_falsification_path,
    )
    if args.write:
        paths = write_weather_proxy_research_candidate_replay(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], "paths": paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
