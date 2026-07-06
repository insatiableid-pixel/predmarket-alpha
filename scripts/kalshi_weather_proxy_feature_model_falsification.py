#!/usr/bin/env python3
"""Falsify weather bracket-proxy feature models against settled labels via the engine.

This is the weather analog of ``scripts/kalshi_sports_proxy_feature_model_falsification.py``.
It runs the WeatherFamily descriptor's ``weather_prediction_rule`` and
``WEATHER_MODEL_EVALUATORS`` through the engine's ``build_falsification()`` generic
spine — demonstrating the spine is closed for modification (zero spine edits).

Weather-specific differences:
- Prediction rule: ``weather_prediction_rule`` from ``predmarket.weather_family``
  (bracket probability threshold rule: YES/NO based on |bracket_probability - yes_ask|).
- Model evaluators: ``weather_bracket_directional_accuracy`` +
  ``weather_market_yes_ask_probability_baseline`` (diagnostic only).
- Labels from ``/home/mrwatson/manual_drops/kalshi_weather_proxy_labels/``.
- Output artifacts under ``docs/codex/macro/latest-kalshi-weather-proxy-feature-model-falsification.*``.
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

from predmarket.engine import build_falsification  # noqa: E402
from predmarket.shared_helpers import (  # noqa: E402
    counts,
    gate,
    read_json_or_empty,
    safe_research_artifact,
    safety_flags,
    utc_now,
)
from predmarket.weather_family import (  # noqa: E402
    WEATHER_MODEL_EVALUATORS,
    resolve_weather_station_id_from_ticker,
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
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-weather-proxy-feature-model-falsification-latest"

# Binding constants (shared, do NOT change)
MIN_INDEPENDENT_LABELS = 30
MIN_OOS_LABELS = 10
TEST_FRACTION = 0.30
FDR_ALPHA = 0.10

# Status prefix used by the weather family
STATUS_PREFIX = "weather_proxy"

# CSV output fields
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


# ---------------------------------------------------------------------------
# Label loading (generic, mirrors kalshi_falsification_replay_shared)
# ---------------------------------------------------------------------------


def load_label_packets(label_dir: Path) -> dict[str, Any]:
    """Load label packets from *label_dir*, returning normalized rows."""
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


def extract_label_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Extract and normalize label rows for engine.build_falsification."""
    label_rows: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for row in rows:
        ticker = str(row.get("contract_ticker") or "").strip()
        outcome = row.get("yes_outcome")
        decision_time = row.get("decision_time")
        close_time = row.get("close_time")
        errors = []
        if not ticker:
            errors.append("missing_contract_ticker")
        if outcome is None:
            errors.append("missing_yes_outcome")
        if not decision_time:
            errors.append("missing_decision_time")
        if not close_time:
            errors.append("missing_close_time")
        expected_station_id = resolve_weather_station_id_from_ticker(
            row.get("series_ticker"),
            row.get("event_ticker"),
            ticker,
        )
        observed_station_id = str(row.get("station_id") or "").strip().upper()
        if (
            expected_station_id
            and observed_station_id
            and observed_station_id != expected_station_id
        ):
            errors.append("station_id_ticker_mismatch")
        if errors:
            invalid.append({"contract_ticker": ticker or None, "errors": errors})
            continue
        label_rows.append(
            {
                "contract_ticker": ticker,
                "event_ticker": row.get("event_ticker"),
                "series_ticker": row.get("series_ticker"),
                "weather_family": row.get("weather_family", row.get("series_ticker")),
                "station_id": expected_station_id or row.get("station_id"),
                "bracket_probability": row.get("bracket_probability"),
                "predicted_side": row.get("predicted_side"),
                "yes_ask": row.get("yes_ask"),
                "yes_bid": row.get("yes_bid"),
                "yes_outcome": outcome,
                "decision_time": decision_time,
                "close_time": close_time,
                "usable": False,
                "calibrated_probability": None,
                "expected_value_per_contract": None,
            }
        )
    label_rows.sort(key=lambda item: (str(item.get("decision_time") or ""), item["contract_ticker"]))
    return label_rows


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Weather Proxy Feature Model Falsification",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Raw label rows: `{summary.get('raw_label_row_count')}`",
        f"- Independent contract labels: `{summary.get('independent_contract_label_count')}`",
        f"- Research candidates: `{summary.get('research_candidate_count')}`",
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
            "## Evaluations",
            "",
            "| Model | Status | OOS Count | Accuracy | p | q |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in report.get("evaluations", []):
        if isinstance(item, Mapping):
            lines.append(
                f"| `{item.get('model_id')}` | `{item.get('status')}` | "
                f"{item.get('oos_count')} | {item.get('oos_accuracy')} | {item.get('p_value')} | {item.get('q_value')} |"
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
            "## Guardrail",
            "",
            "This report is not a betting recommendation. It does not produce calibrated probabilities, EV, sizing, or orders.",
            "",
        ]
    )
    return "\n".join(lines)


def next_action(status: str) -> dict[str, str]:
    if status == "weather_proxy_feature_model_falsification_ready_with_research_candidates":
        return {
            "name": "kalshi_weather_proxy_probability_calibration",
            "why": "At least one feature family survived OOS/FDR as a research candidate; next work is calibrated probability modeling and cost replay.",
            "stop_condition": "Stop before sizing or execution until calibrated probabilities, all-in costs, capacity, correlation, and kill-switch gates exist.",
        }
    return {
        "name": "kalshi_weather_proxy_observation_accumulation",
        "why": "True labels exist but are not enough for independent OOS/FDR falsification.",
        "stop_condition": "Stop before lowering sample thresholds, using duplicate contract labels as independent evidence, or creating EV/sizing/execution claims.",
    }


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


def build_gates(
    *,
    label_load: Mapping[str, Any],
    summary: Mapping[str, Any],
    evaluations: Sequence[Mapping[str, Any]],
    label_dir: Path,
) -> list[dict[str, Any]]:
    unsafe_count = len(label_load.get("unsafe_packets", []))
    return [
        gate(
            "label_packets_safe",
            "pass" if unsafe_count == 0 else "blocked",
            f"{label_load.get('packet_count')} safe packet(s), {unsafe_count} unsafe packet(s).",
        ),
        gate(
            "label_dir_outside_repo",
            "pass" if outside_repo(label_dir) else "blocked",
            "Weather proxy label packets must stay outside the repo.",
        ),
        gate(
            "station_provenance_matches_ticker",
            "pass" if int(summary.get("station_mismatch_label_row_count") or 0) == 0 else "blocked",
            (
                f"{summary.get('station_mismatch_label_row_count')} weather label row(s) have "
                "station provenance that conflicts with the contract ticker."
            ),
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


def report_status(summary: Mapping[str, Any], evaluations: Sequence[Mapping[str, Any]]) -> str:
    prefix = STATUS_PREFIX
    if int(summary.get("independent_contract_label_count") or 0) == 0:
        return f"{prefix}_feature_model_falsification_blocked_missing_labels"
    if int(summary.get("independent_contract_label_count") or 0) < int(
        summary.get("min_independent_labels") or 0
    ):
        return f"{prefix}_feature_model_falsification_blocked_insufficient_independent_labels"
    if not any(
        str(item.get("status")) in {"testable_research_candidate", "research_candidate_fdr_passed"}
        for item in evaluations
    ):
        return f"{prefix}_feature_model_falsification_blocked_insufficient_oos_labels"
    if int(summary.get("research_candidate_count") or 0) > 0:
        return f"{prefix}_feature_model_falsification_ready_with_research_candidates"
    return f"{prefix}_feature_model_falsification_ready_no_research_candidates"


def count_station_mismatch_label_rows(rows: Sequence[Mapping[str, Any]]) -> int:
    mismatch_count = 0
    for row in rows:
        ticker = str(row.get("contract_ticker") or "").strip()
        expected_station_id = resolve_weather_station_id_from_ticker(
            row.get("series_ticker"),
            row.get("event_ticker"),
            ticker,
        )
        observed_station_id = str(row.get("station_id") or "").strip().upper()
        if expected_station_id and observed_station_id and observed_station_id != expected_station_id:
            mismatch_count += 1
    return mismatch_count


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_weather_proxy_feature_model_falsification(
    *,
    label_dir: Path = DEFAULT_LABEL_DIR,
    generated_utc: str | None = None,
    min_independent_labels: int = MIN_INDEPENDENT_LABELS,
    min_oos_labels: int = MIN_OOS_LABELS,
    test_fraction: float = TEST_FRACTION,
    fdr_alpha: float = FDR_ALPHA,
) -> dict[str, Any]:
    """Build the weather proxy falsification report via the engine's generic spine.

    Args:
        label_dir: Path to directory with label packet JSON files.
        generated_utc: Override timestamp (ISO format).
        min_independent_labels: Minimum independent labels for a testable evaluation.
        min_oos_labels: Minimum OOS labels for a testable evaluation.
        test_fraction: Fraction of (latest) labels held out for OOS.
        fdr_alpha: FDR alpha threshold for BH q-value.

    Returns:
        The falsification report dict with evaluations, summary, gates, and safety flags.
    """
    generated = generated_utc or utc_now()

    # Load labels
    label_load = load_label_packets(label_dir)
    raw_rows = label_load.get("rows", [])
    label_rows = extract_label_rows(raw_rows)
    invalid_count = len(raw_rows) - len(label_rows)

    # Run through the engine's generic falsification spine
    engine_result = build_falsification(
        label_rows=label_rows,
        prediction_rule=weather_prediction_rule,
        model_evaluators=WEATHER_MODEL_EVALUATORS,
        status_prefix=STATUS_PREFIX,
        min_independent_labels=min_independent_labels,
        min_oos_labels=min_oos_labels,
        test_fraction=test_fraction,
        fdr_alpha=fdr_alpha,
    )

    evaluations = engine_result.get("evaluations", [])
    engine_summary = engine_result.get("summary", {})

    # Build the full report envelope
    summary = {
        "label_packet_count": label_load.get("packet_count", 0),
        "unsafe_label_packet_count": len(label_load.get("unsafe_packets", [])),
        "raw_label_row_count": len(raw_rows),
        "valid_label_row_count": len(label_rows),
        "invalid_label_row_count": invalid_count,
        "station_mismatch_label_row_count": count_station_mismatch_label_rows(raw_rows),
        "independent_contract_label_count": engine_summary.get(
            "independent_contract_label_count", 0
        ),
        "testable_model_count": engine_summary.get("testable_model_count", 0),
        "research_candidate_count": engine_summary.get("research_candidate_count", 0),
        "min_independent_labels": min_independent_labels,
        "min_oos_labels": min_oos_labels,
        "label_outcome_counts": counts(row.get("yes_outcome") for row in label_rows),
        "station_counts": counts(row.get("station_id") for row in label_rows),
    }

    gates = build_gates(
        label_load=label_load,
        summary=summary,
        evaluations=evaluations,
        label_dir=label_dir,
    )
    status = report_status(summary, evaluations)

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
            "label_packet_count": label_load["packet_count"],
            "label_packet_paths": label_load.get("packet_paths", []),
            "unsafe_packet_count": len(label_load.get("unsafe_packets", [])),
        },
        "method": {
            "engine_stage": "build_falsification from predmarket.engine",
            "prediction_rule": "weather_prediction_rule (bracket probability threshold rule)",
            "model_evaluators": [m.get("model_id") for m in WEATHER_MODEL_EVALUATORS],
            "independence_rule": "Collapse repeated observations by exact contract_ticker; keep earliest decision_time.",
            "split": "chronological holdout by decision_time",
            "test_fraction": test_fraction,
            "min_independent_labels": min_independent_labels,
            "min_oos_labels": min_oos_labels,
            "p_value": "one-sided binomial survival versus 50% directional accuracy on OOS rows",
            "fdr": "Benjamini-Hochberg q-values across testable directional feature families",
            "promotion_boundary": "Research candidate only; no calibrated probability, EV, sizing, or execution.",
        },
        "summary": summary,
        "gates": gates,
        "evaluations": evaluations,
        "next_action": next_action(status),
        "safety": safety_flags(),
    }


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def write_weather_proxy_feature_model_falsification(
    report: Mapping[str, Any],
    out_dir: Path = DEFAULT_OUT_DIR,
) -> dict[str, str]:
    """Write the falsification report to disk and refresh latest-* pointers."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-weather-proxy-feature-model-falsification.json"
    markdown_path = out_dir / "kalshi-weather-proxy-feature-model-falsification.md"
    csv_path = out_dir / "kalshi-weather-proxy-feature-model-falsification.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    _write_csv(report, csv_path)
    # Write latest-* pointers
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-weather-proxy-feature-model-falsification.json"
    latest_md = MACRO_DIR / "latest-kalshi-weather-proxy-feature-model-falsification.md"
    latest_csv = MACRO_DIR / "latest-kalshi-weather-proxy-feature-model-falsification.csv"
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
        writer = _csv.DictWriter(handle, fieldnames=FALSIFICATION_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in report.get("evaluations", []):
            if isinstance(row, Mapping):
                writer.writerow({field: row.get(field) for field in FALSIFICATION_CSV_FIELDS})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--min-independent-labels", type=int, default=MIN_INDEPENDENT_LABELS
    )
    parser.add_argument("--min-oos-labels", type=int, default=MIN_OOS_LABELS)
    parser.add_argument("--test-fraction", type=float, default=TEST_FRACTION)
    parser.add_argument("--fdr-alpha", type=float, default=FDR_ALPHA)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_weather_proxy_feature_model_falsification(
        label_dir=args.label_dir,
        min_independent_labels=args.min_independent_labels,
        min_oos_labels=args.min_oos_labels,
        test_fraction=args.test_fraction,
        fdr_alpha=args.fdr_alpha,
    )
    if args.write:
        paths = write_weather_proxy_feature_model_falsification(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
