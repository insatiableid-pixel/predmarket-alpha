#!/usr/bin/env python3
"""Replay sports (baseball) research candidates against all-in Kalshi costs.

This is the sports analog of ``scripts/kalshi_crypto_proxy_research_candidate_replay.py``.
It reuses the GENERIC replay machinery from the shared companion module
``kalshi_falsification_replay_shared``: Wilson lower-bound calibration, all-in
cost via ``predmarket.kalshi_execution_cost``, contract-key independence collapse,
decay bucketing.

Sports-specific differences:
- Prediction rule: ``predicted_side`` from the strength-mechanical model.
- Cluster key: ``league|game_winner_ticker|date`` (each game is an independent cluster).
- Labels from the configurable manual-drop ``kalshi_sports_proxy_labels/`` directory.
- Falsification report from ``latest-kalshi-sports-proxy-feature-model-falsification.json``.
- Output artifacts under ``docs/codex/macro/latest-kalshi-sports-proxy-research-candidate-replay.*``.
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

from kalshi_falsification_replay_shared import (  # noqa: E402, F401
    DEFAULT_CONFIDENCE_Z,
    DEFAULT_MIN_DECAY_BUCKETS,
    DEFAULT_MIN_DECAY_LABELS,
    DEFAULT_MIN_SIDE_OOS_LABELS,
    REPLAY_CSV_FIELDS,
    bucket_time,
    chronological_split_index,
    conservative_side_probability,
    independent_contract_rows,
    load_label_packets,
    normalize_kalshi_execution_cost,
    normalize_label_rows,
    outside_repo,
    read_json_or_empty,
    replay_contract_rows,
    safety_flags,
    write_csv_generic,
)

from predmarket.shared_helpers import manual_drop_path  # noqa: E402

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_LABEL_DIR = manual_drop_path("kalshi_sports_proxy_labels")
DEFAULT_MODEL_FALSIFICATION_PATH = (
    MACRO_DIR / "latest-kalshi-sports-proxy-feature-model-falsification.json"
)
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-proxy-research-candidate-replay-latest"


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Sports prediction rule
# ---------------------------------------------------------------------------


def sports_strength_win_prob_prediction(row: Mapping[str, Any]) -> int | None:
    """Mechanical prediction rule: predicted_side -> 1 (yes), 0 (no), None (no prediction)."""
    side = row.get("predicted_side")
    if side == "yes":
        return 1
    if side == "no":
        return 0
    return None


def sports_mlb_platform_model_prediction(row: Mapping[str, Any]) -> int | None:
    """Optional MLB-platform bridge prediction rule."""
    side = row.get("mlb_platform_predicted_side")
    if side == "yes":
        return 1
    if side == "no":
        return 0
    return None


def side_prediction(value: Any) -> int | None:
    side = str(value or "").strip().lower()
    if side == "yes":
        return 1
    if side == "no":
        return 0
    return None


def world_cup_market_consensus_prediction(row: Mapping[str, Any]) -> int | None:
    """World Cup proxy rule: follow the side implied by the captured Kalshi quote."""
    return side_prediction(row.get("market_consensus_prediction"))


def world_cup_longshot_fade_prediction(row: Mapping[str, Any]) -> int | None:
    """World Cup proxy rule: fade low-priced YES or follow high-priced YES buckets."""
    return side_prediction(row.get("longshot_fade_prediction"))


PREDICTION_RULES: dict[str, Any] = {
    "strength_win_prob_directional_accuracy": sports_strength_win_prob_prediction,
    "mlb_platform_model_directional_accuracy": sports_mlb_platform_model_prediction,
    "world_cup_market_consensus_directional_accuracy": world_cup_market_consensus_prediction,
    "world_cup_longshot_fade_directional_accuracy": world_cup_longshot_fade_prediction,
}


def select_research_candidate(
    model_report: Mapping[str, Any],
    *,
    preferred_model_id: str | None = None,
) -> dict[str, Any] | None:
    """Pick a passed research candidate; lowest q wins unless a preferred id passes."""
    candidates = [
        dict(item)
        for item in model_report.get("evaluations", [])
        if isinstance(item, Mapping) and item.get("status") == "research_candidate_fdr_passed"
    ]
    if preferred_model_id:
        for item in candidates:
            if item.get("model_id") == preferred_model_id:
                return item
    candidates.sort(
        key=lambda item: (
            float(item.get("q_value") if item.get("q_value") is not None else 999.0),
            -float(item.get("oos_accuracy") or 0.0),
            -int(item.get("oos_count") or 0),
            str(item.get("model_id") or ""),
        )
    )
    return candidates[0] if candidates else None


# ---------------------------------------------------------------------------
# Sports cluster key composer
# ---------------------------------------------------------------------------


def sports_cluster_key_composer(row: Mapping[str, Any]) -> str:
    """Compose a cluster key: league|game_winner_ticker|date.

    Each distinct game is an independent cluster (unlike crypto's asset-based clusters).
    """
    ticker = str(row.get("contract_ticker") or "unknown")
    league = str(row.get("league") or "unknown")
    date_bucket = (
        bucket_time(row.get("expected_expiration_time") or row.get("close_time")) or "unknown"
    )
    return f"{league}|{ticker}|{date_bucket}"


# ---------------------------------------------------------------------------
# Build replay summary (sports-specific)
# ---------------------------------------------------------------------------


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
    selected_model_id: str | None,
    prediction_rule: Any,
    min_side_oos_labels: int,
    min_decay_buckets: int,
    min_decay_labels: int,
) -> dict[str, Any]:
    positive = [
        row
        for row in replay_rows
        if row.get("expected_value_per_contract") is not None
        and row["expected_value_per_contract"] > 0
    ]
    costed = [row for row in replay_rows if row.get("all_in_cost") is not None]
    cluster_counts: dict[str, int] = {}
    for row in replay_rows:
        key = str(row.get("correlation_cluster_key") or "unknown")
        cluster_counts[key] = cluster_counts.get(key, 0) + 1
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

    # Decay summary using sports prediction rule
    from kalshi_falsification_replay_shared import decay_summary as _decay_summary

    decay = _decay_summary(oos_rows, prediction_rule)

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
        "positive_expected_value_rate": len(positive) / len(replay_rows) if replay_rows else None,
        "candidate_research_model_present": candidate_eval is not None,
        "selected_replay_model_id": selected_model_id,
        "calibration_status": calibration.get("status"),
        "conservative_calibrated_side_probability": calibration.get(
            "conservative_calibrated_side_probability"
        ),
        "raw_oos_accuracy": calibration.get("raw_oos_accuracy"),
        "source_model_q_value": calibration.get("source_model_q_value"),
        "mean_margin_probability": sum(margins) / len(margins) if margins else None,
        "median_margin_probability": sorted(margins)[len(margins) // 2] if margins else None,
        "mean_expected_value_per_contract": sum(
            float(row["expected_value_per_contract"])
            for row in replay_rows
            if row.get("expected_value_per_contract") is not None
        )
        / max(
            1, sum(1 for row in replay_rows if row.get("expected_value_per_contract") is not None)
        ),
        "historical_paper_result_sum": sum(paper_results) if paper_results else None,
        "historical_paper_result_mean": sum(paper_results) / len(paper_results)
        if paper_results
        else None,
        "league_counts": {},
        "predicted_side_counts": {},
        "cost_quality_counts": {},
        "correlation_cluster_count": len(cluster_counts),
        "largest_correlation_cluster_key": max(cluster_counts, key=cluster_counts.get)
        if cluster_counts
        else None,
        "largest_correlation_cluster_count": max(cluster_counts.values()) if cluster_counts else 0,
        "decay_bucket_count": decay["bucket_count"],
        "recent_bucket_accuracy": decay["recent_bucket_accuracy"],
        "recent_bucket_key": decay.get("recent_bucket_key"),
        "recent_bucket_label_count": decay.get("recent_bucket_label_count"),
        "decay_status": decay["status"],
        "min_side_oos_labels": min_side_oos_labels,
        "min_decay_buckets": min_decay_buckets,
        "min_decay_labels": min_decay_labels,
        "capacity_depth_row_count": 0,
        "usable_row_count": 0,
    }


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


def build_gates(
    *,
    summary: Mapping[str, Any],
    label_dir: Path,
    replay_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    decay_pass = (
        int(summary.get("independent_contract_label_count") or 0)
        >= int(summary.get("min_decay_labels") or 0)
        and int(summary.get("decay_bucket_count") or 0)
        >= int(summary.get("min_decay_buckets") or 0)
        and str(summary.get("decay_status")) == "recent_bucket_not_worse_than_random"
    )
    return [
        {
            "name": "label_packets_safe",
            "status": "pass"
            if int(summary.get("unsafe_label_packet_count") or 0) == 0
            else "blocked",
            "reason": f"{summary.get('label_packet_count')} safe packet(s), {summary.get('unsafe_label_packet_count')} unsafe packet(s).",
        },
        {
            "name": "label_dir_outside_repo",
            "status": "pass" if outside_repo(label_dir) else "blocked",
            "reason": "Sports proxy label packets must stay outside the repo.",
        },
        {
            "name": "research_candidate_present",
            "status": "pass"
            if summary.get("candidate_research_model_present") is True
            else "blocked",
            "reason": "Feature-model falsification must have a research_candidate_fdr_passed row.",
        },
        {
            "name": "conservative_probability_preflight",
            "status": "pass"
            if summary.get("calibration_status") == "research_only_conservative_probability_ready"
            else "blocked",
            "reason": f"Calibration status is {summary.get('calibration_status')}; OOS selected rows: {summary.get('oos_selected_row_count')}.",
        },
        {
            "name": "all_in_cost_replay",
            "status": "pass"
            if replay_rows
            and int(summary.get("costed_replay_row_count") or 0)
            == int(summary.get("replay_row_count") or 0)
            else "blocked",
            "reason": f"{summary.get('costed_replay_row_count')} of {summary.get('replay_row_count')} replay rows have all-in cost.",
        },
        {
            "name": "positive_cost_adjusted_replay_rows",
            "status": "warn"
            if int(summary.get("positive_expected_value_row_count") or 0) > 0
            else "blocked",
            "reason": f"{summary.get('positive_expected_value_row_count')} replay row(s) are positive after conservative probability and all-in cost.",
        },
        {
            "name": "capacity_depth_available",
            "status": "blocked",
            "reason": "No public depth or validated local order-book depth is attached, so capacity and price impact are unknown.",
        },
        {
            "name": "correlation_control_available",
            "status": "blocked",
            "reason": (
                f"{summary.get('correlation_cluster_count')} cluster(s); largest cluster "
                f"{summary.get('largest_correlation_cluster_key')} has {summary.get('largest_correlation_cluster_count')} row(s). "
                "Cluster counts are measured, but covariance/exposure controls are not implemented."
            ),
        },
        {
            "name": "decay_survival_available",
            "status": "pass" if decay_pass else "blocked",
            "reason": (
                f"Decay status is {summary.get('decay_status')} across {summary.get('decay_bucket_count')} bucket(s); "
                f"requires {summary.get('min_decay_buckets')} bucket(s) and {summary.get('min_decay_labels')} independent labels. "
                f"Recent bucket {summary.get('recent_bucket_key')} accuracy {summary.get('recent_bucket_accuracy')}"
            ),
        },
        {
            "name": "no_usable_ev_sizing_or_execution",
            "status": "pass"
            if int(summary.get("usable_row_count") or 0) == 0
            and all(row.get("usable") is False for row in replay_rows)
            else "fail",
            "reason": "Replay remains research-only with zero usable rows and no sizing or execution.",
        },
    ]


def report_status(summary: Mapping[str, Any], gates: Sequence[Mapping[str, Any]]) -> str:
    if not summary.get("candidate_research_model_present"):
        return "sports_proxy_research_candidate_replay_blocked_missing_research_candidate"
    if int(summary.get("replay_row_count") or 0) == 0:
        return "sports_proxy_research_candidate_replay_blocked_missing_replay_rows"
    if any(item.get("status") == "fail" for item in gates):
        return "sports_proxy_research_candidate_replay_failed_safety_gate"
    hard_blockers = {
        "capacity_depth_available",
        "correlation_control_available",
        "decay_survival_available",
    }
    if any(item.get("name") in hard_blockers and item.get("status") != "pass" for item in gates):
        return "sports_proxy_research_candidate_replay_blocked_predeployment_gates"
    if int(summary.get("positive_expected_value_row_count") or 0) > 0:
        return "sports_proxy_research_candidate_replay_ready_for_paper_probability_overlay"
    return "sports_proxy_research_candidate_replay_ready_no_positive_cost_adjusted_rows"


def next_action(status: str) -> dict[str, str]:
    if status == "sports_proxy_research_candidate_replay_blocked_predeployment_gates":
        return {
            "name": "kalshi_sports_proxy_capacity_correlation_decay",
            "why": "A research candidate has conservative cost-adjusted replay rows, but capacity, correlation, and decay gates block any usable edge.",
            "stop_condition": "Stop before sizing, execution, account/order paths, or treating positive replay rows as deployable.",
        }
    if status == "sports_proxy_research_candidate_replay_ready_for_paper_probability_overlay":
        return {
            "name": "kalshi_sports_proxy_paper_probability_overlay",
            "why": "Replay gates are research-ready; next work is a paper-only probability overlay with live decay monitoring.",
            "stop_condition": "Stop before real positions, execution, or account/order paths.",
        }
    return {
        "name": "kalshi_sports_proxy_signal_family_rotation",
        "why": "The current candidate is missing, uncosted, or not positive after conservative cost replay.",
        "stop_condition": "Stop before discretionary feature selection; register and falsify new feature families.",
    }


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_sports_proxy_research_candidate_replay(
    *,
    label_dir: Path = DEFAULT_LABEL_DIR,
    model_falsification_path: Path = DEFAULT_MODEL_FALSIFICATION_PATH,
    generated_utc: str | None = None,
    confidence_z: float = DEFAULT_CONFIDENCE_Z,
    min_side_oos_labels: int = DEFAULT_MIN_SIDE_OOS_LABELS,
    min_decay_buckets: int = DEFAULT_MIN_DECAY_BUCKETS,
    min_decay_labels: int = DEFAULT_MIN_DECAY_LABELS,
    preferred_model_id: str | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    model_report = read_json_or_empty(model_falsification_path)
    label_load = load_label_packets(label_dir)
    rows, invalid_rows = normalize_label_rows(label_load["rows"])
    independent_rows = independent_contract_rows(rows)
    candidate_eval = select_research_candidate(model_report, preferred_model_id=preferred_model_id)
    selected_model_id = str(candidate_eval.get("model_id")) if candidate_eval else None
    prediction_rule = PREDICTION_RULES.get(
        selected_model_id or "",
        sports_strength_win_prob_prediction,
    )
    selected_rows = [row for row in independent_rows if prediction_rule(row) is not None]
    split_index = chronological_split_index(
        len(independent_rows),
        float(model_report.get("method", {}).get("test_fraction", 0.30)),
    )
    oos_rows = [row for row in independent_rows[split_index:] if prediction_rule(row) is not None]
    calibration = conservative_side_probability(
        oos_rows=oos_rows,
        prediction_rule=prediction_rule,
        confidence_z=confidence_z,
        min_side_oos_labels=min_side_oos_labels,
        candidate_eval=candidate_eval,
        model_id=selected_model_id or "strength_win_prob_directional_accuracy",
    )
    replay_rows = replay_contract_rows(
        selected_rows,
        calibration=calibration,
        prediction_rule=prediction_rule,
        cluster_key_composer=sports_cluster_key_composer,
    )
    selected_by_ticker = {str(row.get("contract_ticker") or ""): row for row in selected_rows}
    for row in replay_rows:
        row["source_model_id"] = selected_model_id
        if selected_model_id == "mlb_platform_model_directional_accuracy":
            source = selected_by_ticker.get(str(row.get("contract_ticker") or ""), {})
            row["source_model_probability"] = source.get("mlb_platform_model_probability")
            row["source_model_match_key"] = source.get("mlb_platform_match_key")
    summary = build_summary(
        label_load=label_load,
        invalid_rows=invalid_rows,
        independent_rows=independent_rows,
        selected_rows=selected_rows,
        oos_rows=oos_rows,
        replay_rows=replay_rows,
        calibration=calibration,
        candidate_eval=candidate_eval,
        selected_model_id=selected_model_id,
        prediction_rule=prediction_rule,
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
            "selected_replay_model_id": selected_model_id,
        },
        "method": {
            "replay_boundary": "Historical paper replay only; no live orders, positions, staking, sizing, or usable edge flags.",
            "independence_rule": "Collapse repeated observations by exact contract_ticker; keep earliest decision_time.",
            "model_rule": (
                "Auto-select the best FDR-passed sports evaluator by q-value; strength and optional "
                "MLB-platform bridge models compete under the same OOS/FDR gate."
            ),
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


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def write_sports_proxy_research_candidate_replay(
    report: Mapping[str, Any],
    out_dir: Path = DEFAULT_OUT_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-proxy-research-candidate-replay.json"
    markdown_path = out_dir / "kalshi-sports-proxy-research-candidate-replay.md"
    csv_path = out_dir / "kalshi-sports-proxy-research-candidate-replay.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv_generic(report, csv_path, REPLAY_CSV_FIELDS, rows_key="replay_rows")
    # Write latest-* pointers
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-sports-proxy-research-candidate-replay.json"
    latest_md = MACRO_DIR / "latest-kalshi-sports-proxy-research-candidate-replay.md"
    latest_csv = MACRO_DIR / "latest-kalshi-sports-proxy-research-candidate-replay.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv_generic(report, latest_csv, REPLAY_CSV_FIELDS, rows_key="replay_rows")
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
    calibration = (
        report.get("calibration") if isinstance(report.get("calibration"), Mapping) else {}
    )
    lines = [
        "# Kalshi Sports Proxy Research Candidate Replay",
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
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument(
        "--model-falsification-path", type=Path, default=DEFAULT_MODEL_FALSIFICATION_PATH
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--confidence-z", type=float, default=DEFAULT_CONFIDENCE_Z)
    parser.add_argument("--min-side-oos-labels", type=int, default=DEFAULT_MIN_SIDE_OOS_LABELS)
    parser.add_argument("--min-decay-buckets", type=int, default=DEFAULT_MIN_DECAY_BUCKETS)
    parser.add_argument("--min-decay-labels", type=int, default=DEFAULT_MIN_DECAY_LABELS)
    parser.add_argument("--preferred-model-id", default=None)
    parser.add_argument("--write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_sports_proxy_research_candidate_replay(
        label_dir=args.label_dir,
        model_falsification_path=args.model_falsification_path,
        confidence_z=args.confidence_z,
        min_side_oos_labels=args.min_side_oos_labels,
        min_decay_buckets=args.min_decay_buckets,
        min_decay_labels=args.min_decay_labels,
        preferred_model_id=args.preferred_model_id,
    )
    if args.write:
        paths = write_sports_proxy_research_candidate_replay(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], "paths": paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
