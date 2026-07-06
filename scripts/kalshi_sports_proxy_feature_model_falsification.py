#!/usr/bin/env python3
"""Falsify sports (baseball) strength-win-probability feature models against settled labels.

This is the sports analog of ``scripts/kalshi_crypto_proxy_feature_model_falsification.py``.
It reuses the GENERIC statistical core (Benjamini-Hochberg FDR, exact binomial survival,
chronological OOS split, contract-key independence collapse) from the shared companion
module ``kalshi_falsification_replay_shared``.

Sports-specific differences:
- Prediction rule: ``predicted_side`` from the strength-mechanical model (yes/no/None).
- Model evaluator: ``strength_win_prob_directional_accuracy``.
- Labels from ``/home/mrwatson/manual_drops/kalshi_sports_proxy_labels/``.
- Output artifacts under ``docs/codex/macro/latest-kalshi-sports-proxy-feature-model-falsification.*``.
- Every row ``usable=false``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = CONTROL_REPO / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kalshi_falsification_replay_shared import (  # noqa: E402
    DEFAULT_FDR_ALPHA,
    DEFAULT_MIN_INDEPENDENT_LABELS,
    DEFAULT_MIN_OOS_LABELS,
    DEFAULT_TEST_FRACTION,
    FALSIFICATION_CSV_FIELDS,
    binomial_survival,
    build_falsification_gates,
    build_falsification_summary,
    evaluate_models,
    independent_contract_rows,
    load_label_packets,
    normalize_label_rows,
    safety_flags,
    write_csv_generic,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_LABEL_DIR = Path("/home/mrwatson/manual_drops/kalshi_sports_proxy_labels")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-proxy-feature-model-falsification-latest"


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Sports prediction rule
# ---------------------------------------------------------------------------


def sports_strength_win_prob_prediction(row: Mapping[str, Any]) -> int | None:
    """Mechanical prediction rule: predicted_side -> 1 (yes), 0 (no), None (no prediction).

    This is the sports analog of ``proxy_state_prediction``.
    """
    side = row.get("predicted_side")
    if side == "yes":
        return 1
    if side == "no":
        return 0
    return None


def sports_mlb_platform_model_prediction(row: Mapping[str, Any]) -> int | None:
    """Optional MLB-platform bridge prediction rule: predicted_side -> 1/0/None."""
    side = row.get("mlb_platform_predicted_side")
    if side == "yes":
        return 1
    if side == "no":
        return 0
    return None


# ---------------------------------------------------------------------------
# Sports model evaluator
# ---------------------------------------------------------------------------


def evaluate_sports_strength_win_prob(
    *,
    rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    min_independent_labels: int,
    min_oos_labels: int,
) -> dict[str, Any]:
    scored = [row for row in oos_rows if sports_strength_win_prob_prediction(row) is not None]
    wins = sum(
        1 for row in scored if sports_strength_win_prob_prediction(row) == row.get("yes_outcome")
    )
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
        "feature_rule": "Predict YES when predicted_side='yes'; predict NO when predicted_side='no'.",
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


def evaluate_sports_mlb_platform_model(
    *,
    rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    min_independent_labels: int,
    min_oos_labels: int,
) -> dict[str, Any]:
    scored = [row for row in oos_rows if sports_mlb_platform_model_prediction(row) is not None]
    wins = sum(
        1 for row in scored if sports_mlb_platform_model_prediction(row) == row.get("yes_outcome")
    )
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
        "feature_rule": "Optional MLB-platform model bridge: predict YES when mlb_platform_predicted_side='yes'; NO when 'no'.",
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


# ---------------------------------------------------------------------------
# Model evaluators list (the sports family descriptor's model_evaluators)
# ---------------------------------------------------------------------------

SPORTS_MODEL_EVALUATORS = [evaluate_sports_strength_win_prob, evaluate_sports_mlb_platform_model]


# ---------------------------------------------------------------------------
# Report status helpers
# ---------------------------------------------------------------------------


def report_status(summary: Mapping[str, Any], evaluations: Sequence[Mapping[str, Any]]) -> str:
    if int(summary.get("valid_label_row_count") or 0) == 0:
        return "sports_proxy_feature_model_falsification_blocked_missing_labels"
    if int(summary.get("independent_contract_label_count") or 0) < int(
        summary.get("min_independent_labels") or 0
    ):
        return "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels"
    if not any(
        str(item.get("status")) in {"testable_research_candidate", "research_candidate_fdr_passed"}
        for item in evaluations
    ):
        return "sports_proxy_feature_model_falsification_blocked_insufficient_oos_labels"
    if int(summary.get("research_candidate_count") or 0) > 0:
        return "sports_proxy_feature_model_falsification_ready_with_research_candidates"
    return "sports_proxy_feature_model_falsification_ready_no_research_candidates"


def next_action(status: str) -> dict[str, str]:
    if status == "sports_proxy_feature_model_falsification_ready_with_research_candidates":
        return {
            "name": "kalshi_sports_proxy_probability_calibration",
            "why": "At least one feature family survived OOS/FDR as a research candidate; next work is calibrated probability modeling and cost replay.",
            "stop_condition": "Stop before sizing or execution until calibrated probabilities, all-in costs, capacity, correlation, and kill-switch gates exist.",
        }
    return {
        "name": "kalshi_sports_proxy_observation_accumulation",
        "why": "True labels exist but are not enough for independent OOS/FDR falsification.",
        "stop_condition": "Stop before lowering sample thresholds, using duplicate contract labels as independent evidence, or creating EV/sizing/execution claims.",
    }


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_sports_proxy_feature_model_falsification(
    *,
    label_dir: Path = DEFAULT_LABEL_DIR,
    generated_utc: str | None = None,
    min_independent_labels: int = DEFAULT_MIN_INDEPENDENT_LABELS,
    min_oos_labels: int = DEFAULT_MIN_OOS_LABELS,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    fdr_alpha: float = DEFAULT_FDR_ALPHA,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    label_load = load_label_packets(label_dir)
    normalized_rows, invalid_rows = normalize_label_rows(label_load["rows"])
    independent_rows = independent_contract_rows(normalized_rows)
    evaluations = evaluate_models(
        independent_rows,
        model_evaluators=SPORTS_MODEL_EVALUATORS,
        min_independent_labels=min_independent_labels,
        min_oos_labels=min_oos_labels,
        test_fraction=test_fraction,
        fdr_alpha=fdr_alpha,
    )
    summary = build_falsification_summary(
        label_load=label_load,
        normalized_rows=normalized_rows,
        independent_rows=independent_rows,
        invalid_rows=invalid_rows,
        evaluations=evaluations,
        min_independent_labels=min_independent_labels,
        min_oos_labels=min_oos_labels,
        family_label="sports",
    )
    gates = build_falsification_gates(
        summary=summary,
        evaluations=evaluations,
        label_dir=label_dir,
        family_label="sports",
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
            "label_packet_paths": label_load["packet_paths"],
            "unsafe_packet_count": len(label_load["unsafe_packets"]),
        },
        "method": {
            "independence_rule": "Collapse repeated observations by exact contract_ticker; keep earliest decision_time.",
            "candidate_feature_families": [
                "strength_win_prob_directional_accuracy",
                "mlb_platform_model_directional_accuracy",
            ],
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
        "independent_label_rows_sample": independent_rows[:25],
        "invalid_label_rows_sample": invalid_rows[:50],
        "next_action": next_action(status),
        "safety": safety_flags(),
    }


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def write_sports_proxy_feature_model_falsification(
    report: Mapping[str, Any],
    out_dir: Path = DEFAULT_OUT_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-proxy-feature-model-falsification.json"
    markdown_path = out_dir / "kalshi-sports-proxy-feature-model-falsification.md"
    csv_path = out_dir / "kalshi-sports-proxy-feature-model-falsification.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv_generic(report, csv_path, FALSIFICATION_CSV_FIELDS, rows_key="evaluations")
    # Write latest-* pointers
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-sports-proxy-feature-model-falsification.json"
    latest_md = MACRO_DIR / "latest-kalshi-sports-proxy-feature-model-falsification.md"
    latest_csv = MACRO_DIR / "latest-kalshi-sports-proxy-feature-model-falsification.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv_generic(report, latest_csv, FALSIFICATION_CSV_FIELDS, rows_key="evaluations")
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "csv_path": str(csv_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
        "latest_csv_path": str(latest_csv),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Sports Proxy Feature Model Falsification",
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--min-independent-labels", type=int, default=DEFAULT_MIN_INDEPENDENT_LABELS
    )
    parser.add_argument("--min-oos-labels", type=int, default=DEFAULT_MIN_OOS_LABELS)
    parser.add_argument("--test-fraction", type=float, default=DEFAULT_TEST_FRACTION)
    parser.add_argument("--fdr-alpha", type=float, default=DEFAULT_FDR_ALPHA)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_sports_proxy_feature_model_falsification(
        label_dir=args.label_dir,
        min_independent_labels=args.min_independent_labels,
        min_oos_labels=args.min_oos_labels,
        test_fraction=args.test_fraction,
        fdr_alpha=args.fdr_alpha,
    )
    if args.write:
        paths = write_sports_proxy_feature_model_falsification(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
