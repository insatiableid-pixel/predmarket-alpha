#!/usr/bin/env python3
"""Phase 0-3 Kalshi Sports executable short-horizon research program.

Builds a truth/leakage audit, fixed-horizon after-cost labels, a finite
hypothesis registry, event-grouped walk-forward + FDR results, a negative
registry, and a ranked research frontier. Research-only: no paper stake,
sizing, accounts, or live execution.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import (  # noqa: E402
    gate,
    gate_counts,
    manual_drop_path,
    path_is_within,
    safe_research_artifact,
    safety_flags,
    utc_now,
)
from predmarket.sports_cross_contract_horizon import (  # noqa: E402
    CROSS_CONTRACT_FAMILY_ID,
    attach_cross_contract_features,
    cross_contract_hypothesis_registry,
)
from predmarket.sports_executable_horizon import (  # noqa: E402
    DEFAULT_HORIZONS_SECONDS,
    FEATURE_FAMILY_ID,
    apply_fdr,
    attach_leakage_features,
    audit_observation_inventory,
    build_executable_labels,
    evaluate_hypothesis,
    hard_gate_assessment,
    hypothesis_registry,
    load_observation_packets,
    research_frontier,
    retired_negative_registry,
    synthetic_leakage_tests,
)
from predmarket.sports_thin_book_horizon import (  # noqa: E402
    THIN_BOOK_FAMILY_ID,
    attach_thin_book_features,
    thin_book_hypothesis_registry,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-executable-horizon-research-latest"
DEFAULT_OBSERVATION_DIR = manual_drop_path(
    "kalshi_sports_microstructure_observations",
    env_vars=("KALSHI_SPORTS_MICROSTRUCTURE_OBSERVATION_DIR",),
)
DEFAULT_LABEL_DIR = manual_drop_path(
    "kalshi_sports_microstructure_labels",
    env_vars=("KALSHI_SPORTS_MICROSTRUCTURE_LABEL_DIR",),
)
DEFAULT_TICK_DIR = manual_drop_path(
    "kalshi_ticks",
    env_vars=("KALSHI_TICK_RECORDER_JSONL_DIR",),
)
FROZEN_STARTING_EVIDENCE = {
    "fable_audit_json": "e87745a7319f5495dc429032512700bc062711989a8cf53cc5f627a1b03a1a02",
    "historical_backfill_json": "5fc9c5d3f3bbc3e612a3b7fb4249ba4603a9e5b0a7a16e2ee5dcd8b75599e709",
    "historical_archive_report_json": "9ceb6c0cb7569e0a2abe189eb1fef09a4345687b1306dab3fde32767d38bd92c",
    "external_1108_row_archive_json": "8eff01f02aedc73c34c4455b91d57fceaa120f2049d47349f847adc0c6a11b8c",
}



def evaluate_family(
    labels: Sequence[Mapping[str, Any]],
    registry: Sequence[Mapping[str, Any]],
    *,
    family_id: str,
    min_oos_labels: int,
    min_events: int,
    fdr_alpha: float,
) -> list[dict[str, Any]]:
    evaluations = [
        evaluate_hypothesis(
            labels,
            spec,
            min_oos_labels=min_oos_labels,
            min_events=min_events,
        )
        for spec in registry
    ]
    evaluations = apply_fdr(evaluations, alpha=fdr_alpha)
    gated: list[dict[str, Any]] = []
    for row in evaluations:
        item = dict(row)
        item["feature_family"] = family_id
        assessment = hard_gate_assessment(item, min_oos=min_oos_labels, min_events=min_events)
        item["hard_gates"] = assessment
        if (
            item.get("status") == "research_candidate_fdr_passed"
            and not assessment["discovery_gates_pass"]
        ):
            item["status"] = "testable_fdr_pass_hard_gate_fail"
        if assessment["research_ready"]:
            item["status"] = "research_ready"
        gated.append(item)
    return gated


def program_family_status(family_statuses: Mapping[str, str]) -> str:
    if any(status == "research_ready" for status in family_statuses.values()):
        return "research_ready"
    if any(status == "confirmation_pending" for status in family_statuses.values()):
        return "confirmation_pending"
    if family_statuses and all(status == "falsified" for status in family_statuses.values()):
        return "falsified"
    return "discovery_pending"


def build_report(
    *,
    observation_dir: Path,
    label_dir: Path,
    tick_dir: Path,
    discovery_cutoff_utc: str | None,
    fdr_alpha: float,
    min_oos_labels: int,
    min_events: int,
) -> dict[str, Any]:
    generated = utc_now()
    cutoff = discovery_cutoff_utc or generated
    rows = load_observation_packets(observation_dir)
    audit = audit_observation_inventory(
        rows,
        observation_dir=observation_dir,
        label_dir=label_dir,
        tick_dir=tick_dir,
        frozen_checksums=FROZEN_STARTING_EVIDENCE,
    )
    audit["viewed_time_range_utc"] = audit.get("time_range_utc")
    audit["untouched_confirmation_cutoff_utc"] = cutoff
    audit["synthetic_tests"] = synthetic_leakage_tests()
    audit["synthetic_tests_passed"] = all(
        bool(item.get("passed")) for item in audit["synthetic_tests"]
    )

    labels, label_summary = build_executable_labels(
        rows,
        horizons=DEFAULT_HORIZONS_SECONDS,
        discovery_cutoff_utc=cutoff,
    )
    labels = attach_leakage_features(labels)
    labels = attach_cross_contract_features(labels)
    labels = attach_thin_book_features(labels)

    family_specs = {
        FEATURE_FAMILY_ID: hypothesis_registry(),
        CROSS_CONTRACT_FAMILY_ID: cross_contract_hypothesis_registry(),
        THIN_BOOK_FAMILY_ID: thin_book_hypothesis_registry(),
    }
    family_results = {
        family_id: evaluate_family(
            labels,
            registry,
            family_id=family_id,
            min_oos_labels=min_oos_labels,
            min_events=min_events,
            fdr_alpha=fdr_alpha,
        )
        for family_id, registry in family_specs.items()
    }
    gated = [row for rows in family_results.values() for row in rows]
    registry = [spec for specs in family_specs.values() for spec in specs]
    negative = list(retired_negative_registry())
    family_statuses = {
        family_id: resolve_family_status(rows) for family_id, rows in family_results.items()
    }
    for family_id, status_name in family_statuses.items():
        if status_name == "falsified":
            negative.append(
                {
                    "spec_id": family_id,
                    "family": family_id,
                    "status": "falsified",
                    "evidence": summarize_family_negative(
                        family_results[family_id], label_summary
                    ),
                    "do_not_repeat": (
                        "Same feature/threshold set without denser books or a distinct "
                        "mechanical family"
                    ),
                    "generated_utc": generated,
                }
            )
    family_status = program_family_status(family_statuses)

    frontier = research_frontier(
        label_summary=label_summary, evaluations=gated, audit=audit
    )
    # Update frontier lane statuses from measured family results.
    for lane in frontier:
        if lane.get("lane") == "executable_horizon_microstructure_v1":
            lane["status"] = family_statuses.get(FEATURE_FAMILY_ID, lane.get("status"))
        if lane.get("lane") == "cross_contract_within_event_coherence":
            lane["status"] = family_statuses.get(CROSS_CONTRACT_FAMILY_ID, lane.get("status"))
            if family_statuses.get(CROSS_CONTRACT_FAMILY_ID) == "falsified":
                lane["next_action"] = "Retired on discovery FDR; densify ticks or park"
        if lane.get("lane") == "thin_book_fade":
            lane["status"] = family_statuses.get(THIN_BOOK_FAMILY_ID, lane.get("status"))
            if family_statuses.get(THIN_BOOK_FAMILY_ID) == "falsified":
                lane["next_action"] = "Retired on discovery FDR; densify ticks or park"
    summary = build_summary(
        audit=audit,
        label_summary=label_summary,
        evaluations=gated,
        family_status=family_status,
        frontier=frontier,
        cutoff=cutoff,
        fdr_alpha=fdr_alpha,
        min_oos_labels=min_oos_labels,
        min_events=min_events,
    )
    summary["family_statuses"] = family_statuses
    gates = build_gates(summary, audit)
    status = resolve_status(summary, family_status, audit)

    # Keep artifact size bounded: full labels go to ignored manual_drops via write.
    sample_labels = [
        row
        for row in labels
        if row.get("label_status") == "executable_labeled"
    ][:100]
    sample_labels += [
        row for row in labels if str(row.get("label_status") or "").startswith("censored")
    ][:20]

    report: dict[str, Any] = {
        "schema_version": 1,
        "packet_type": "kalshi_sports_executable_horizon_research",
        "status": status,
        "generated_utc": generated,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "safety": safety_flags(public_market_data_calls=False),
        "directive_id": "kalshi-sports-max-leverage-20260710T043157Z",
        "feature_family": FEATURE_FAMILY_ID,
        "inputs": {
            "observation_dir": str(observation_dir),
            "label_dir": str(label_dir),
            "tick_dir": str(tick_dir),
            "discovery_cutoff_utc": cutoff,
            "fdr_alpha": fdr_alpha,
            "min_oos_labels": min_oos_labels,
            "min_events": min_events,
            "frozen_starting_evidence": FROZEN_STARTING_EVIDENCE,
        },
        "summary": summary,
        "gates": gates,
        "gate_counts": gate_counts(gates),
        "phase0_truth_leakage_audit": audit,
        "label_summary": label_summary,
        "hypothesis_registry": registry,
        "family_evaluations": family_results,
        "evaluations": gated,
        "negative_result_registry": negative,
        "research_frontier": frontier,
        "label_rows_sample": sample_labels,
        "multiple_testing_family": [row.get("model_id") for row in registry],
        "stop_condition": (
            "Stop before paper stake, sizing, accounts, orders, or live execution. "
            "Historical/discovery results cannot alone authorize promotion."
        ),
    }
    report["_labels_for_export"] = labels
    return report


def resolve_family_status(evaluations: Sequence[Mapping[str, Any]]) -> str:
    if any(row.get("status") == "research_ready" for row in evaluations):
        return "research_ready"
    if any(row.get("status") == "research_candidate_fdr_passed" for row in evaluations):
        return "confirmation_pending"
    if any(row.get("status") in {"testable", "testable_fdr_pass_hard_gate_fail"} for row in evaluations):
        # Testable but no FDR survivor => falsified for this declared family.
        if any(row.get("status") == "testable_fdr_pass_hard_gate_fail" for row in evaluations):
            return "falsified"
        # If any testable with q-values computed and none pass FDR:
        if any(row.get("q_value") is not None for row in evaluations):
            return "falsified"
        return "discovery_pending"
    if any(int(row.get("oos_event_count") or 0) > 0 for row in evaluations):
        return "falsified"
    return "discovery_pending"


def summarize_family_negative(
    evaluations: Sequence[Mapping[str, Any]], label_summary: Mapping[str, Any]
) -> str:
    best = min(
        (
            row
            for row in evaluations
            if row.get("q_value") is not None or row.get("p_value_mean_net_positive") is not None
        ),
        key=lambda row: float(row.get("q_value") or row.get("p_value_mean_net_positive") or 1.0),
        default={},
    )
    return (
        f"executable_labels={label_summary.get('executable_label_count')} "
        f"candidates={len(evaluations)} "
        f"best_model={best.get('model_id')} "
        f"best_q={best.get('q_value')} "
        f"best_mean_net={best.get('oos_mean_net_return')} "
        f"best_oos_events={best.get('oos_event_count')}"
    )


def build_summary(
    *,
    audit: Mapping[str, Any],
    label_summary: Mapping[str, Any],
    evaluations: Sequence[Mapping[str, Any]],
    family_status: str,
    frontier: Sequence[Mapping[str, Any]],
    cutoff: str,
    fdr_alpha: float,
    min_oos_labels: int,
    min_events: int,
) -> dict[str, Any]:
    survivors = [
        row
        for row in evaluations
        if row.get("status") in {"research_candidate_fdr_passed", "research_ready"}
    ]
    testable = [
        row
        for row in evaluations
        if row.get("status")
        in {"testable", "testable_fdr_pass_hard_gate_fail", "research_candidate_fdr_passed", "research_ready"}
    ]
    best = min(
        (
            row
            for row in evaluations
            if row.get("q_value") is not None or row.get("p_value_mean_net_positive") is not None
        ),
        key=lambda row: float(row.get("q_value") or row.get("p_value_mean_net_positive") or 1.0),
        default={},
    )
    return {
        "family_status": family_status,
        "feature_family": FEATURE_FAMILY_ID,
        "observation_rows": audit.get("unique_observation_rows"),
        "distinct_contracts": audit.get("unique_contracts"),
        "distinct_events": audit.get("unique_events"),
        "executable_label_count": label_summary.get("executable_label_count"),
        "censored_label_count": label_summary.get("censored_count"),
        "label_row_count": label_summary.get("label_row_count"),
        "pre_registered_candidate_count": len(evaluations),
        "testable_candidate_count": len(testable),
        "fdr_survivor_count": len(survivors),
        "research_ready_count": sum(1 for row in evaluations if row.get("status") == "research_ready"),
        "best_model_id": best.get("model_id"),
        "best_q_value": best.get("q_value"),
        "best_oos_mean_net_return": best.get("oos_mean_net_return"),
        "best_oos_event_count": best.get("oos_event_count"),
        "untouched_confirmation_cutoff_utc": cutoff,
        "fdr_alpha": fdr_alpha,
        "min_oos_labels": min_oos_labels,
        "min_events": min_events,
        "synthetic_tests_passed": audit.get("synthetic_tests_passed"),
        "unresolved_label_semantic_defect_count": len(
            audit.get("unresolved_label_semantic_defects") or []
        ),
        "frontier_top_lane": frontier[0].get("lane") if frontier else None,
        "usable_row_count": 0,
        "paper_stake": 0,
        "live_eligible": 0,
    }


def build_gates(summary: Mapping[str, Any], audit: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        gate(
            "synthetic_leakage_tests",
            "pass" if audit.get("synthetic_tests_passed") else "fail",
            "built-in positive/negative/leakage/censor tests",
        ),
        gate(
            "no_unresolved_label_semantic_defects",
            "pass" if int(summary.get("unresolved_label_semantic_defect_count") or 0) == 0 else "fail",
            f"unresolved={summary.get('unresolved_label_semantic_defect_count')}",
        ),
        gate(
            "frozen_cutoff_declared",
            "pass" if summary.get("untouched_confirmation_cutoff_utc") else "fail",
            f"cutoff={summary.get('untouched_confirmation_cutoff_utc')}",
        ),
        gate(
            "executable_labels_present",
            "pass" if int(summary.get("executable_label_count") or 0) > 0 else "fail",
            f"executable={summary.get('executable_label_count')}",
        ),
        gate(
            "finite_hypothesis_registry",
            "pass" if int(summary.get("pre_registered_candidate_count") or 0) > 0 else "fail",
            f"candidates={summary.get('pre_registered_candidate_count')}",
        ),
        gate(
            "complete_family_fdr",
            "pass",
            f"family_size={summary.get('pre_registered_candidate_count')} alpha={summary.get('fdr_alpha')}",
        ),
        gate(
            "research_ready_survivor",
            "pass" if int(summary.get("research_ready_count") or 0) > 0 else "fail",
            f"research_ready={summary.get('research_ready_count')}",
        ),
        gate(
            "research_only_boundaries",
            "pass",
            "usable_row_count=0 paper_stake=0 live_eligible=0",
        ),
    ]


def resolve_status(
    summary: Mapping[str, Any], family_status: str, audit: Mapping[str, Any]
) -> str:
    if not audit.get("synthetic_tests_passed"):
        return "executable_horizon_research_blocked_label_defects"
    if int(summary.get("unresolved_label_semantic_defect_count") or 0) > 0:
        return "executable_horizon_research_blocked_label_defects"
    if family_status == "research_ready":
        return "executable_horizon_research_ready_survivor"
    if family_status == "confirmation_pending":
        return "executable_horizon_research_confirmation_pending"
    if family_status == "falsified":
        return "executable_horizon_research_family_falsified"
    if int(summary.get("executable_label_count") or 0) <= 0:
        return "executable_horizon_research_blocked_no_executable_labels"
    return "executable_horizon_research_discovery_pending"


def write_outputs(
    report: Mapping[str, Any],
    *,
    out_dir: Path,
    export_label_dir: Path | None,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    labels = list(report.get("_labels_for_export") or [])
    clean = {key: value for key, value in report.items() if key != "_labels_for_export"}
    if not safe_research_artifact(clean):
        raise RuntimeError("refusing to write unsafe research artifact")

    json_path = out_dir / "kalshi-sports-executable-horizon-research.json"
    md_path = out_dir / "kalshi-sports-executable-horizon-research.md"
    csv_path = out_dir / "kalshi-sports-executable-horizon-research.csv"
    frontier_path = out_dir / "kalshi-sports-research-frontier.json"
    negative_path = out_dir / "kalshi-sports-negative-result-registry.json"
    audit_path = out_dir / "kalshi-sports-truth-leakage-audit.json"
    registry_path = out_dir / "kalshi-sports-executable-hypothesis-registry.json"

    text = json.dumps(clean, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(clean), encoding="utf-8")
    write_evaluations_csv(csv_path, clean.get("evaluations") or [])
    frontier_path.write_text(
        json.dumps(clean.get("research_frontier") or [], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    negative_path.write_text(
        json.dumps(clean.get("negative_result_registry") or [], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    audit_path.write_text(
        json.dumps(clean.get("phase0_truth_leakage_audit") or {}, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )
    registry_path.write_text(
        json.dumps(clean.get("hypothesis_registry") or [], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
        "frontier_path": str(frontier_path),
        "negative_registry_path": str(negative_path),
        "audit_path": str(audit_path),
        "registry_path": str(registry_path),
    }

    if export_label_dir is not None:
        export_label_dir.mkdir(parents=True, exist_ok=True)
        stamp = str(clean.get("generated_utc") or utc_now()).replace(":", "").replace("-", "")
        label_path = export_label_dir / f"sports_executable_horizon_labels_{stamp}.json"
        latest_labels = export_label_dir / "sports_executable_horizon_labels_latest.json"
        payload = {
            "schema_version": 1,
            "packet_type": "sports_executable_horizon_labels",
            "generated_utc": clean.get("generated_utc"),
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "summary": clean.get("label_summary"),
            "rows": labels,
        }
        body = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
        label_path.write_text(body, encoding="utf-8")
        latest_labels.write_text(body, encoding="utf-8")
        paths["label_export_path"] = str(label_path)
        paths["label_export_latest_path"] = str(latest_labels)

    if path_is_within(out_dir, MACRO_DIR):
        for name, source in {
            "latest-kalshi-sports-executable-horizon-research.json": json_path,
            "latest-kalshi-sports-executable-horizon-research.md": md_path,
            "latest-kalshi-sports-executable-horizon-research.csv": csv_path,
            "latest-kalshi-sports-research-frontier.json": frontier_path,
            "latest-kalshi-sports-negative-result-registry.json": negative_path,
            "latest-kalshi-sports-truth-leakage-audit.json": audit_path,
            "latest-kalshi-sports-executable-hypothesis-registry.json": registry_path,
        }.items():
            target = MACRO_DIR / name
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            paths[name] = str(target)
    return paths


def write_evaluations_csv(path: Path, evaluations: Sequence[Mapping[str, Any]]) -> None:
    fields = [
        "model_id",
        "status",
        "horizon_seconds",
        "side",
        "feature",
        "threshold",
        "negative_control",
        "oos_event_count",
        "oos_mean_net_return",
        "oos_mean_gross_return",
        "oos_positive_rate",
        "p_value_mean_net_positive",
        "q_value",
        "bootstrap_mean_net_lower_95",
        "positive_temporal_buckets",
        "recent_bucket_mean_net",
        "largest_series_cluster_share",
        "positive_capacity_event_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in evaluations:
            writer.writerow({field: row.get(field) for field in fields})


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Sports Executable Horizon Research",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Family status: `{summary.get('family_status')}`",
        f"- Observations: `{summary.get('observation_rows')}`",
        f"- Executable labels: `{summary.get('executable_label_count')}`",
        f"- Censored labels: `{summary.get('censored_label_count')}`",
        f"- Pre-registered candidates: `{summary.get('pre_registered_candidate_count')}`",
        f"- Testable candidates: `{summary.get('testable_candidate_count')}`",
        f"- FDR survivors: `{summary.get('fdr_survivor_count')}`",
        f"- Research-ready: `{summary.get('research_ready_count')}`",
        f"- Best model: `{summary.get('best_model_id')}` q=`{summary.get('best_q_value')}` "
        f"mean_net=`{summary.get('best_oos_mean_net_return')}` "
        f"oos_events=`{summary.get('best_oos_event_count')}`",
        f"- Untouched cutoff: `{summary.get('untouched_confirmation_cutoff_utc')}`",
        "",
        "## Decision",
        "",
    ]
    if int(summary.get("research_ready_count") or 0) > 0:
        lines.append("Research-ready survivor present. Confirmation and packet required before any sizing.")
    elif int(summary.get("fdr_survivor_count") or 0) > 0:
        lines.append("Discovery FDR survivor only. Untouched confirmation is still required.")
    elif summary.get("family_status") == "falsified":
        lines.append(
            "Declared executable-horizon family falsified on available discovery evidence. "
            "Advance to the next distinct sports family or densify labels; do not tune on holdout."
        )
    else:
        lines.append("Discovery still pending denser executable labels or more independent events.")
    lines.extend(["", "## Evaluations", ""])
    for row in report.get("evaluations") or []:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            f"- `{row.get('model_id')}` status=`{row.get('status')}` "
            f"oos=`{row.get('oos_event_count')}` mean_net=`{row.get('oos_mean_net_return')}` "
            f"q=`{row.get('q_value')}` negctrl=`{row.get('negative_control')}`"
        )
    lines.extend(["", "## Frontier", ""])
    for row in report.get("research_frontier") or []:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            f"- rank `{row.get('rank')}` `{row.get('lane')}` status=`{row.get('status')}` "
            f"next=`{row.get('next_action')}`"
        )
    lines.extend(
        [
            "",
            "Research-only. No paper stake, sizing, accounts, orders, or live execution.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--observation-dir", type=Path, default=DEFAULT_OBSERVATION_DIR)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument("--tick-dir", type=Path, default=DEFAULT_TICK_DIR)
    parser.add_argument(
        "--export-label-dir",
        type=Path,
        default=manual_drop_path("kalshi_sports_executable_horizon_labels"),
    )
    parser.add_argument("--discovery-cutoff-utc", default="")
    parser.add_argument("--fdr-alpha", type=float, default=0.05)
    parser.add_argument("--min-oos-labels", type=int, default=100)
    parser.add_argument("--min-events", type=int, default=20)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        observation_dir=args.observation_dir,
        label_dir=args.label_dir,
        tick_dir=args.tick_dir,
        discovery_cutoff_utc=args.discovery_cutoff_utc or None,
        fdr_alpha=float(args.fdr_alpha),
        min_oos_labels=int(args.min_oos_labels),
        min_events=int(args.min_events),
    )
    if args.write:
        paths = write_outputs(
            report,
            out_dir=args.out_dir,
            export_label_dir=args.export_label_dir,
        )
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "summary": report["summary"],
                    **paths,
                },
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
    else:
        clean = {key: value for key, value in report.items() if key != "_labels_for_export"}
        print(json.dumps(clean, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
