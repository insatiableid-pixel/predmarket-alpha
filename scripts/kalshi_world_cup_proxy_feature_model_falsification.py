#!/usr/bin/env python3
"""Falsify World Cup/FIFA market-structure proxy signals against settled labels.

This lane exists to move World Cup/FIFA sports rows out of soft-watch inventory
and into the same OOS/FDR evidence discipline as the rest of the factory. It
does not handicap soccer. Candidate rules are pre-registered quote/market
structure rules captured before settlement.
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
    outcome_value,
    probability,
    safety_flags,
    timestamp,
    write_csv_generic,
)

from predmarket.shared_helpers import counts, iso_from_timestamp  # noqa: E402

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_LABEL_DIR = Path("/home/mrwatson/manual_drops/kalshi_world_cup_proxy_labels")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-world-cup-proxy-feature-model-falsification-latest"


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def side_prediction(value: Any) -> int | None:
    text = str(value or "").strip().lower()
    if text == "yes":
        return 1
    if text == "no":
        return 0
    return None


def market_consensus_prediction(row: Mapping[str, Any]) -> int | None:
    return side_prediction(row.get("market_consensus_prediction"))


def longshot_fade_prediction(row: Mapping[str, Any]) -> int | None:
    return side_prediction(row.get("longshot_fade_prediction"))


def evaluate_market_consensus_directional_accuracy(
    *,
    rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    min_independent_labels: int,
    min_oos_labels: int,
) -> dict[str, Any]:
    return directional_evaluation(
        rows=rows,
        oos_rows=oos_rows,
        min_independent_labels=min_independent_labels,
        min_oos_labels=min_oos_labels,
        model_id="world_cup_market_consensus_directional_accuracy",
        prediction_rule=market_consensus_prediction,
        feature_rule="Predict the side implied by yes_mid > 0.5 or yes_mid < 0.5.",
    )


def evaluate_longshot_fade_directional_accuracy(
    *,
    rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    min_independent_labels: int,
    min_oos_labels: int,
) -> dict[str, Any]:
    return directional_evaluation(
        rows=rows,
        oos_rows=oos_rows,
        min_independent_labels=min_independent_labels,
        min_oos_labels=min_oos_labels,
        model_id="world_cup_longshot_fade_directional_accuracy",
        prediction_rule=longshot_fade_prediction,
        feature_rule=(
            "Fade low-priced YES asks <= 0.25 as NO; follow high YES bids >= 0.75 as YES."
        ),
    )


def directional_evaluation(
    *,
    rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    min_independent_labels: int,
    min_oos_labels: int,
    model_id: str,
    prediction_rule: Any,
    feature_rule: str,
) -> dict[str, Any]:
    scored = [row for row in oos_rows if prediction_rule(row) is not None]
    wins = sum(1 for row in scored if prediction_rule(row) == row.get("yes_outcome"))
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
        "model_id": model_id,
        "status": status,
        "independent_label_count": len(rows),
        "oos_count": len(scored),
        "oos_correct_count": wins,
        "oos_accuracy": wins / len(scored) if scored else None,
        "p_value": p_value,
        "q_value": None,
        "feature_rule": feature_rule,
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


WORLD_CUP_MODEL_EVALUATORS = [
    evaluate_market_consensus_directional_accuracy,
    evaluate_longshot_fade_directional_accuracy,
]


def normalize_world_cup_label_rows(
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
        consensus = side_prediction(row.get("market_consensus_prediction"))
        fade = side_prediction(row.get("longshot_fade_prediction"))
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
        if consensus is None and fade is None:
            errors.append("missing_world_cup_proxy_prediction")
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
                "league": "WORLD_CUP",
                "market_type": row.get("market_type"),
                "selection_token": row.get("selection_token"),
                "market_consensus_prediction": "yes"
                if consensus == 1
                else "no"
                if consensus == 0
                else None,
                "longshot_fade_prediction": "yes" if fade == 1 else "no" if fade == 0 else None,
                "yes_bid": probability(row.get("yes_bid")),
                "yes_ask": probability(row.get("yes_ask")),
                "yes_mid": probability(row.get("yes_mid")),
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


def report_status(summary: Mapping[str, Any], evaluations: Sequence[Mapping[str, Any]]) -> str:
    if int(summary.get("valid_label_row_count") or 0) == 0:
        return "world_cup_proxy_feature_model_falsification_blocked_missing_labels"
    if int(summary.get("independent_contract_label_count") or 0) < int(
        summary.get("min_independent_labels") or 0
    ):
        return "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels"
    if not any(
        str(item.get("status")) in {"testable_research_candidate", "research_candidate_fdr_passed"}
        for item in evaluations
    ):
        return "world_cup_proxy_feature_model_falsification_blocked_insufficient_oos_labels"
    if int(summary.get("research_candidate_count") or 0) > 0:
        return "world_cup_proxy_feature_model_falsification_ready_with_research_candidates"
    return "world_cup_proxy_feature_model_falsification_ready_no_research_candidates"


def next_action(status: str) -> dict[str, str]:
    if status == "world_cup_proxy_feature_model_falsification_ready_with_research_candidates":
        return {
            "name": "kalshi_world_cup_proxy_probability_calibration",
            "why": "A World Cup market-structure rule survived OOS/FDR; next is conservative calibration and cost replay.",
            "stop_condition": "Stop before paper stake or live order until cost, depth, cluster, and decay gates pass.",
        }
    return {
        "name": "kalshi_world_cup_proxy_observation_accumulation",
        "why": "World Cup labels are not yet enough for independent OOS/FDR promotion.",
        "stop_condition": "Stop before lowering thresholds or using unsettled contracts as labels.",
    }


def build_world_cup_proxy_feature_model_falsification(
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
    normalized_rows, invalid_rows = normalize_world_cup_label_rows(label_load["rows"])
    independent_rows = independent_contract_rows(normalized_rows)
    evaluations = evaluate_models(
        independent_rows,
        model_evaluators=WORLD_CUP_MODEL_EVALUATORS,
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
        family_label="world_cup",
    )
    summary.update(
        {
            "series_counts": counts(row.get("series_ticker") for row in independent_rows),
            "market_type_counts": counts(row.get("market_type") for row in independent_rows),
            "market_consensus_prediction_count": sum(
                1 for row in independent_rows if market_consensus_prediction(row) is not None
            ),
            "longshot_fade_prediction_count": sum(
                1 for row in independent_rows if longshot_fade_prediction(row) is not None
            ),
        }
    )
    gates = build_falsification_gates(
        summary=summary,
        evaluations=evaluations,
        label_dir=label_dir,
        family_label="world_cup",
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
            "independence_rule": "Collapse repeated labels by exact contract_ticker; keep earliest decision_time.",
            "candidate_feature_families": [
                "world_cup_market_consensus_directional_accuracy",
                "world_cup_longshot_fade_directional_accuracy",
            ],
            "model_boundary": "No soccer handicap, team-strength model, or sportsbook probability is used.",
            "split": "chronological holdout by decision_time",
            "test_fraction": test_fraction,
            "min_independent_labels": min_independent_labels,
            "min_oos_labels": min_oos_labels,
            "p_value": "one-sided binomial survival versus 50% directional accuracy on OOS rows",
            "fdr": "Benjamini-Hochberg q-values across World Cup proxy rules",
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


def write_world_cup_proxy_feature_model_falsification(
    report: Mapping[str, Any],
    out_dir: Path = DEFAULT_OUT_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-world-cup-proxy-feature-model-falsification.json"
    markdown_path = out_dir / "kalshi-world-cup-proxy-feature-model-falsification.md"
    csv_path = out_dir / "kalshi-world-cup-proxy-feature-model-falsification.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv_generic(report, csv_path, FALSIFICATION_CSV_FIELDS, rows_key="evaluations")

    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-world-cup-proxy-feature-model-falsification.json"
    latest_md = MACRO_DIR / "latest-kalshi-world-cup-proxy-feature-model-falsification.md"
    latest_csv = MACRO_DIR / "latest-kalshi-world-cup-proxy-feature-model-falsification.csv"
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
        "# Kalshi World Cup Proxy Feature Model Falsification",
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
                f"{item.get('oos_count')} | {item.get('oos_accuracy')} | "
                f"{item.get('p_value')} | {item.get('q_value')} |"
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
    report = build_world_cup_proxy_feature_model_falsification(
        label_dir=args.label_dir,
        min_independent_labels=args.min_independent_labels,
        min_oos_labels=args.min_oos_labels,
        test_fraction=args.test_fraction,
        fdr_alpha=args.fdr_alpha,
    )
    if args.write:
        paths = write_world_cup_proxy_feature_model_falsification(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
