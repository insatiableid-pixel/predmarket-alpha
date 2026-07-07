#!/usr/bin/env python3
"""Audit implementation status against Claude's Kalshi sports advice."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import (  # noqa: E402
    path_is_within,
    read_json_or_empty,
    safe_research_artifact,
    safety_flags,
    sha256_or_none,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_FLOW_GATE_PATH = (
    MACRO_DIR / "latest-kalshi-near-resolution-informed-flow-evidence-gate.json"
)
DEFAULT_FLOW_REPLAY_PATH = MACRO_DIR / "latest-kalshi-near-resolution-flow-replay-gates.json"
DEFAULT_EV_LEDGER_PATH = MACRO_DIR / "latest-kalshi-contract-ev-ledger.json"
DEFAULT_PAPER_PATH = MACRO_DIR / "latest-paper-decision-candidates.json"
DEFAULT_PASSIVE_FILL_PATH = (
    MACRO_DIR / "latest-kalshi-passive-liquidity-paper-fill-falsification.json"
)
DEFAULT_ATP_PATH = MACRO_DIR / "latest-kalshi-atp-proxy-evidence-gate.json"
DEFAULT_WORLD_CUP_INDEPENDENCE_PATH = (
    MACRO_DIR / "latest-kalshi-world-cup-outcome-independence-diagnostic.json"
)
DEFAULT_PRIOR_ONLY_PATH = MACRO_DIR / "latest-prior-only-donor-gate.json"
DEFAULT_EVENT_VELOCITY_PATH = MACRO_DIR / "latest-kalshi-sports-event-velocity-eta.json"
DEFAULT_LIVE_PATH = MACRO_DIR / "latest-kalshi-live-preflight.json"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-claude-advice-audit-latest"

CSV_FIELDS = [
    "requirement_id",
    "advice_area",
    "status",
    "implementation_status",
    "evidence",
    "next_action",
    "blocker_type",
]

OPEN_STATUSES = {
    "blocked_clock",
    "blocked_external",
    "blocked_statistical_no_survivor",
    "pending_candidate",
    "warning",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_claude_advice_audit(
    *,
    flow_gate_path: Path = DEFAULT_FLOW_GATE_PATH,
    flow_replay_path: Path = DEFAULT_FLOW_REPLAY_PATH,
    ev_ledger_path: Path = DEFAULT_EV_LEDGER_PATH,
    paper_path: Path = DEFAULT_PAPER_PATH,
    passive_fill_path: Path = DEFAULT_PASSIVE_FILL_PATH,
    atp_path: Path = DEFAULT_ATP_PATH,
    world_cup_independence_path: Path = DEFAULT_WORLD_CUP_INDEPENDENCE_PATH,
    prior_only_path: Path = DEFAULT_PRIOR_ONLY_PATH,
    event_velocity_path: Path = DEFAULT_EVENT_VELOCITY_PATH,
    live_path: Path = DEFAULT_LIVE_PATH,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    artifacts = {
        "flow_gate": artifact(flow_gate_path),
        "flow_replay": artifact(flow_replay_path),
        "ev_ledger": artifact(ev_ledger_path),
        "paper": artifact(paper_path),
        "passive_fill": artifact(passive_fill_path),
        "atp": artifact(atp_path),
        "world_cup_independence": artifact(world_cup_independence_path),
        "prior_only": artifact(prior_only_path),
        "event_velocity": artifact(event_velocity_path),
        "live": artifact(live_path),
    }
    rows = advice_rows(artifacts)
    gates = build_gates(artifacts, rows)
    status = report_status(gates, rows)
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
        "north_star": "Extract and exploit mispricings in Kalshi event contracts before the crowd corrects them.",
        "method": {
            "purpose": "Map Claude's sports advice to current machine evidence and separate implementation gaps from clock/statistical blockers.",
            "boundary": "Audit only; it cannot promote candidates, size stake, lower thresholds, or authorize execution.",
        },
        "inputs": {
            key: {
                "path": item["path"],
                "sha256": item["sha256"],
                "exists": item["exists"],
                "safe": item["safe"],
                "status": item["status"],
            }
            for key, item in artifacts.items()
        },
        "summary": build_summary(artifacts, rows),
        "advice_rows": rows,
        "gates": gates,
        "next_action": next_action(rows),
        "safety": safety_flags(),
    }


def artifact(path: Path) -> dict[str, Any]:
    payload = read_json_or_empty(path)
    return {
        "path": str(path),
        "sha256": sha256_or_none(path),
        "exists": path.is_file(),
        "safe": safe_research_artifact(payload) or safe_blocked_live_artifact(payload),
        "status": payload.get("status"),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {},
        "payload": payload,
    }


def safe_blocked_live_artifact(payload: Mapping[str, Any]) -> bool:
    safety = payload.get("safety") if isinstance(payload.get("safety"), Mapping) else {}
    return (
        str(payload.get("status") or "").startswith("kalshi_live_")
        and payload.get("execution_enabled") is False
        and payload.get("market_execution") is False
        and safety.get("market_orders") is False
    )


def advice_rows(artifacts: Mapping[str, Mapping[str, Any]]) -> list[dict[str, str]]:
    return [
        flow_candidate_row(artifacts["flow_gate"]),
        flow_full_gate_row(artifacts["flow_replay"], artifacts["ev_ledger"], artifacts["paper"]),
        passive_real_fill_row(artifacts["passive_fill"]),
        passive_falsification_row(artifacts["passive_fill"]),
        atp_clock_row(artifacts["atp"]),
        world_cup_independence_row(artifacts["world_cup_independence"]),
        prior_only_row(artifacts["prior_only"]),
        event_velocity_row(artifacts["event_velocity"]),
        live_avoidance_row(artifacts["live"]),
        no_threshold_lowering_row(artifacts),
    ]


def flow_candidate_row(flow_gate: Mapping[str, Any]) -> dict[str, str]:
    summary = flow_gate.get("summary", {})
    candidates = int_value(summary.get("research_candidate_count"))
    testable = int_value(summary.get("testable_candidate_count"))
    gate_status = str(flow_gate.get("status") or "")
    statistically_rejected = (
        gate_status == "near_resolution_informed_flow_falsification_ready_no_research_candidate"
        and testable > 0
    )
    status = (
        "satisfied"
        if (candidates > 0 and testable > 0) or statistically_rejected
        else "pending_candidate"
    )
    implementation_ok = testable > 0 and (
        candidates > 0
        or statistically_rejected
        or gate_status == "near_resolution_informed_flow_research_candidates_ready"
    )
    return row(
        "CLAUDE-001",
        "near_resolution_informed_flow_candidate",
        status,
        f"research_candidates={candidates}; testable_candidates={testable}; status={flow_gate.get('status')}",
        "Keep replay/paper settlement running; do not force a survivor after price-implied-null rejection."
        if statistically_rejected
        else "Run informed-flow hypothesis generation/falsification until at least one candidate exists."
        if status != "satisfied"
        else "Keep replay/paper settlement running; do not add discretionary variants.",
        "compute",
        implementation_status="satisfied" if implementation_ok else status,
    )


def flow_full_gate_row(
    flow_replay: Mapping[str, Any],
    ev_ledger: Mapping[str, Any],
    paper: Mapping[str, Any],
) -> dict[str, str]:
    replay_summary = flow_replay.get("summary", {})
    ev_summary = ev_ledger.get("summary", {})
    paper_summary = paper.get("summary", {})
    ready_replay = str(flow_replay.get("status") or "").endswith("ready_for_ev_ledger_promotion")
    has_capacity = int_value(replay_summary.get("capacity_positive_row_count")) > 0
    has_clusters = int_value(replay_summary.get("positive_correlation_cluster_count")) >= int_value(
        replay_summary.get("min_positive_correlation_clusters")
    )
    decay_ok = (
        str(replay_summary.get("decay_status") or "") == "recent_bucket_not_worse_than_random"
    )
    ev_usable = int_value(ev_summary.get("usable_row_count")) > 0
    paper_usable = int_value(paper_summary.get("paper_usable_count")) > 0
    upstream_no_candidate = (
        str(flow_replay.get("status") or "")
        == "near_resolution_flow_replay_gates_blocked_missing_research_candidate"
    )
    passed = (
        ready_replay and has_capacity and has_clusters and decay_ok and ev_usable and paper_usable
    )
    implemented = (
        flow_replay.get("exists") is not False
        and ev_ledger.get("exists") is not False
        and paper.get("exists") is not False
        and bool(flow_replay.get("status"))
        and bool(ev_ledger.get("status"))
        and bool(paper.get("status"))
    )
    status = "satisfied" if passed or upstream_no_candidate else "warning"
    return row(
        "CLAUDE-002",
        "informed_flow_full_gate_chain",
        status,
        (
            f"replay={flow_replay.get('status')}; capacity_rows={replay_summary.get('capacity_positive_row_count')}; "
            f"clusters={replay_summary.get('positive_correlation_cluster_count')}/{replay_summary.get('min_positive_correlation_clusters')}; "
            f"decay={replay_summary.get('decay_status')}; ev_usable={ev_summary.get('usable_row_count')}; "
            f"paper_usable={paper_summary.get('paper_usable_count')}"
        ),
        "Keep all OOS/FDR/cost/capacity/correlation/decay/paper/live-preflight gates active."
        if passed or upstream_no_candidate
        else "Repair whichever replay, EV, paper, capacity, correlation, or decay gate is missing.",
        "gate_chain",
        implementation_status="satisfied" if implemented else "warning",
    )


def passive_real_fill_row(passive: Mapping[str, Any]) -> dict[str, str]:
    summary = passive.get("summary", {})
    labels = int_value(summary.get("valid_paper_fill_label_count"))
    fills = int_value(summary.get("paper_filled_count"))
    min_labels = int_value(summary.get("min_independent_labels"))
    min_fills = int_value(summary.get("min_oos_fills"))
    passed = labels >= min_labels and fills >= min_fills
    return row(
        "CLAUDE-003",
        "passive_liquidity_real_fill_labels",
        "satisfied" if passed else "blocked_clock",
        f"valid_paper_fill_labels={labels}/{min_labels}; paper_fills={fills}/{min_fills}; status={passive.get('status')}",
        "Continue passive paper-fill loop; only real paper fills/timeouts count.",
        "paper_fill_clock",
    )


def passive_falsification_row(passive: Mapping[str, Any]) -> dict[str, str]:
    summary = passive.get("summary", {})
    tested = int_value(summary.get("tested_hypothesis_count"))
    survivors = int_value(summary.get("fdr_survivor_count"))
    research = int_value(summary.get("research_candidate_count"))
    if tested <= 0:
        status = "pending_candidate"
    elif survivors <= 0 and research <= 0:
        status = "satisfied"
    else:
        status = "satisfied"
    return row(
        "CLAUDE-004",
        "passive_liquidity_fdr_gate",
        status,
        f"tested={tested}; fdr_survivors={survivors}; research_candidates={research}; best_net_ev={summary.get('best_candidate_net_ev')}",
        "Keep accumulating real fill labels; do not promote passive liquidity without an FDR survivor and net EV.",
        "statistical",
    )


def atp_clock_row(atp: Mapping[str, Any]) -> dict[str, str]:
    summary = atp.get("summary", {})
    resolved = int_value(summary.get("forward_oos_resolved"))
    minimum = int_value(summary.get("forward_oos_min_probe"))
    next_probe = summary.get("next_expected_expiration_utc") or summary.get(
        "next_public_label_probe_utc"
    )
    implementation_ok = minimum > 0 and bool(next_probe) and atp.get("exists") is not False
    status = "satisfied" if resolved >= minimum and minimum > 0 else "blocked_clock"
    return row(
        "CLAUDE-005",
        "atp_forward_oos_clock",
        status,
        f"forward_oos={resolved}/{minimum}; next_probe={next_probe}; status={atp.get('status')}",
        "Probe exact public Kalshi settlements at the next ATP clock; do not use sportsbook results as labels.",
        "calendar",
        implementation_status="satisfied" if implementation_ok else "warning",
    )


def world_cup_independence_row(world_cup: Mapping[str, Any]) -> dict[str, str]:
    summary = world_cup.get("summary", {})
    supported = summary.get("outcome_level_parallel_clock_supported") is True
    no_review = summary.get("current_candidate_independence_requires_review") is False
    clustered = summary.get("recommended_portfolio_cluster_unit") == "world_cup_match"
    families = int_value(summary.get("non_match_result_outcome_family_count"))
    passed = supported and no_review and clustered and families > 0
    return row(
        "CLAUDE-006",
        "world_cup_outcome_independence",
        "satisfied" if passed else "warning",
        (
            f"parallel_clocks={supported}; requires_review={summary.get('current_candidate_independence_requires_review')}; "
            f"non_match_families={families}; portfolio_cluster={summary.get('recommended_portfolio_cluster_unit')}"
        ),
        "Keep hypothesis labels at match/outcome-family level and portfolio risk clustered by match.",
        "correlation",
    )


def prior_only_row(prior: Mapping[str, Any]) -> dict[str, str]:
    summary = prior.get("summary", {})
    passed = (
        int_value(summary.get("eligible_prior_context_count")) > 0
        and int_value(summary.get("settlement_label_credit_count")) == 0
        and int_value(summary.get("independent_label_credit_count")) == 0
        and int_value(summary.get("oos_label_credit_count")) == 0
        and int_value(summary.get("paper_usable_count")) == 0
        and int_value(summary.get("live_eligible_count")) == 0
        and int_value(summary.get("direct_probability_promotion_count")) == 0
    )
    return row(
        "CLAUDE-007",
        "prior_only_donor_guardrail",
        "satisfied" if passed else "warning",
        (
            f"eligible_priors={summary.get('eligible_prior_context_count')}; label_credit="
            f"{summary.get('settlement_label_credit_count')}/{summary.get('independent_label_credit_count')}/{summary.get('oos_label_credit_count')}; "
            f"paper={summary.get('paper_usable_count')}; live={summary.get('live_eligible_count')}; direct_promotion={summary.get('direct_probability_promotion_count')}"
        ),
        "Keep donor priors pre-falsification only.",
        "donor_boundary",
    )


def event_velocity_row(event_velocity: Mapping[str, Any]) -> dict[str, str]:
    summary = event_velocity.get("summary", {})
    next_due = summary.get("next_due_surface")
    next_probe = summary.get("next_probe_surface")
    has_deficit = (
        int_value(summary.get("total_label_deficit")) > 0
        or int_value(summary.get("total_oos_deficit")) > 0
    )
    forecast_ready = (
        str(event_velocity.get("status") or "").startswith("sports_event_velocity_eta_ready")
        and "total_label_deficit" in summary
        and "total_oos_deficit" in summary
        and (not has_deficit or next_due or next_probe)
    )
    if has_deficit and (next_due or next_probe):
        status = "blocked_clock"
    elif not has_deficit:
        status = "satisfied"
    else:
        status = "warning"
    return row(
        "CLAUDE-008",
        "calendar_event_velocity_forecast",
        status,
        (
            f"next_due={next_due}; next_probe={next_probe}; label_deficit={summary.get('total_label_deficit')}; "
            f"oos_deficit={summary.get('total_oos_deficit')}"
        ),
        "Run the next due/probe action when its clock arrives.",
        "calendar",
        implementation_status="satisfied" if forecast_ready else "warning",
    )


def live_avoidance_row(live: Mapping[str, Any]) -> dict[str, str]:
    summary = live.get("summary", {})
    eligible = int_value(summary.get("live_eligible_count"))
    stake = float_value(summary.get("total_live_stake"))
    status = "satisfied" if eligible == 0 and stake == 0 else "warning"
    return row(
        "CLAUDE-009",
        "avoid_live_hardening_without_edges",
        status,
        f"live_status={live.get('status')}; eligible={eligible}; live_stake={stake}",
        "Do not spend engineering effort bypassing live gates while no validated live-eligible edge exists.",
        "policy",
    )


def no_threshold_lowering_row(artifacts: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    flow = artifacts["flow_gate"].get("summary", {})
    passive = artifacts["passive_fill"].get("summary", {})
    event_velocity = artifacts["event_velocity"].get("summary", {})
    suspicious = (
        int_value(flow.get("min_oos_labels")) < 10
        or int_value(flow.get("min_settled_contracts")) < 30
        or int_value(passive.get("min_oos_labels")) < 10
        or int_value(passive.get("min_independent_labels")) < 30
    )
    return row(
        "CLAUDE-010",
        "no_threshold_relaxation",
        "warning" if suspicious else "satisfied",
        (
            f"flow_min={flow.get('min_settled_contracts')}/{flow.get('min_oos_labels')}; "
            f"passive_min={passive.get('min_independent_labels')}/{passive.get('min_oos_labels')}; "
            f"event_velocity_status_counts={event_velocity.get('eta_status_counts')}"
        ),
        "Preserve independent-label, OOS, FDR, cost, capacity, correlation, and decay gates.",
        "gate_integrity",
    )


def row(
    requirement_id: str,
    advice_area: str,
    status: str,
    evidence: str,
    next_action_value: str,
    blocker_type: str,
    *,
    implementation_status: str | None = None,
) -> dict[str, str]:
    return {
        "requirement_id": requirement_id,
        "advice_area": advice_area,
        "status": status,
        "implementation_status": implementation_status or status,
        "evidence": evidence,
        "next_action": next_action_value,
        "blocker_type": blocker_type,
    }


def build_gates(
    artifacts: Mapping[str, Mapping[str, Any]], rows: Sequence[Mapping[str, str]]
) -> list[dict[str, str]]:
    unsafe = [
        key for key, value in artifacts.items() if value.get("exists") and not value.get("safe")
    ]
    missing = [key for key, value in artifacts.items() if not value.get("exists")]
    return [
        gate("all_existing_artifacts_safe", "pass" if not unsafe else "fail", str(unsafe)),
        gate("required_artifacts_exist", "pass" if not missing else "blocked", str(missing)),
        gate(
            "advice_rows_present",
            "pass" if len(rows) >= 10 else "blocked",
            f"{len(rows)} Claude-advice rows emitted.",
        ),
    ]


def report_status(gates: Sequence[Mapping[str, str]], rows: Sequence[Mapping[str, str]]) -> str:
    if any(item.get("status") == "fail" for item in gates):
        return "claude_advice_audit_failed_safety_gate"
    if any(item.get("status") == "blocked" for item in gates):
        return "claude_advice_audit_blocked_missing_artifacts"
    if any(row_item.get("status") == "warning" for row_item in rows):
        return "claude_advice_audit_ready_with_warnings"
    if any(row_item.get("status") in OPEN_STATUSES for row_item in rows):
        return "claude_advice_audit_ready_with_open_clock_or_statistical_items"
    return "claude_advice_audit_ready_all_items_satisfied"


def build_summary(
    artifacts: Mapping[str, Mapping[str, Any]], rows: Sequence[Mapping[str, str]]
) -> dict[str, Any]:
    counts = Counter(row.get("status", "unknown") for row in rows)
    implementation_counts = Counter(
        row.get("implementation_status", row.get("status", "unknown")) for row in rows
    )
    return {
        "safe_artifact_count": sum(1 for item in artifacts.values() if item.get("safe")),
        "artifact_count": len(artifacts),
        "unsafe_artifact_keys": [
            key for key, item in artifacts.items() if item.get("exists") and not item.get("safe")
        ],
        "missing_artifact_keys": [key for key, item in artifacts.items() if not item.get("exists")],
        "requirement_count": len(rows),
        "satisfied_count": counts.get("satisfied", 0),
        "open_clock_count": counts.get("blocked_clock", 0),
        "open_statistical_no_survivor_count": counts.get("blocked_statistical_no_survivor", 0),
        "warning_count": counts.get("warning", 0),
        "status_counts": dict(sorted(counts.items())),
        "open_requirement_ids": [
            row["requirement_id"] for row in rows if row.get("status") in OPEN_STATUSES
        ],
        "implementation_satisfied_count": implementation_counts.get("satisfied", 0),
        "implementation_warning_count": implementation_counts.get("warning", 0),
        "implementation_status_counts": dict(sorted(implementation_counts.items())),
        "implementation_open_requirement_ids": [
            row["requirement_id"]
            for row in rows
            if row.get("implementation_status", row.get("status")) != "satisfied"
        ],
    }


def next_action(rows: Sequence[Mapping[str, str]]) -> dict[str, str]:
    priority = [
        "CLAUDE-002",
        "CLAUDE-004",
        "CLAUDE-008",
        "CLAUDE-005",
    ]
    rows_by_id = {row["requirement_id"]: row for row in rows}
    for requirement_id in priority:
        candidate = rows_by_id.get(requirement_id)
        if candidate and candidate.get("status") in OPEN_STATUSES:
            return {
                "name": candidate["advice_area"],
                "why": candidate["evidence"],
                "stop_condition": candidate["next_action"],
            }
    open_rows = [row for row in rows if row.get("status") in OPEN_STATUSES]
    if open_rows:
        candidate = open_rows[0]
        return {
            "name": candidate["advice_area"],
            "why": candidate["evidence"],
            "stop_condition": candidate["next_action"],
        }
    return {
        "name": "claude_advice_completion_audit",
        "why": "All machine-audited Claude advice rows are satisfied.",
        "stop_condition": "Before marking complete, verify current tests and artifacts end to end.",
    }


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def float_value(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def write_outputs(report: Mapping[str, Any], *, out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-claude-advice-audit.json"
    md_path = out_dir / "kalshi-claude-advice-audit.md"
    csv_path = out_dir / "kalshi-claude-advice-audit.csv"
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("advice_rows", []), csv_path)
    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
    }
    if path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-claude-advice-audit.json"
        latest_md = MACRO_DIR / "latest-kalshi-claude-advice-audit.md"
        latest_csv = MACRO_DIR / "latest-kalshi-claude-advice-audit.csv"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        write_csv(report.get("advice_rows", []), latest_csv)
        paths.update(
            {
                "latest_json_path": str(latest_json),
                "latest_markdown_path": str(latest_md),
                "latest_csv_path": str(latest_csv),
            }
        )
    return paths


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Claude Advice Audit",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Requirements: `{summary.get('requirement_count')}`",
        f"- Satisfied: `{summary.get('satisfied_count')}`",
        f"- Implementation satisfied: `{summary.get('implementation_satisfied_count')}`",
        f"- Implementation open ids: `{summary.get('implementation_open_requirement_ids')}`",
        f"- Clock-bound: `{summary.get('open_clock_count')}`",
        f"- Statistical no-survivor: `{summary.get('open_statistical_no_survivor_count')}`",
        f"- Warnings: `{summary.get('warning_count')}`",
        f"- Open requirement ids: `{summary.get('open_requirement_ids')}`",
        "",
        "## Rows",
        "",
        "| Requirement | Area | Evidence Status | Implementation | Blocker | Evidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in report.get("advice_rows", []):
        if not isinstance(item, Mapping):
            continue
        lines.append(
            f"| `{item.get('requirement_id')}` | `{item.get('advice_area')}` | "
            f"`{item.get('status')}` | `{item.get('implementation_status')}` | "
            f"`{item.get('blocker_type')}` | {item.get('evidence')} |"
        )
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            f"- Name: `{report.get('next_action', {}).get('name')}`",
            f"- Why: {report.get('next_action', {}).get('why')}",
            f"- Stop condition: {report.get('next_action', {}).get('stop_condition')}",
            "",
            "> Control-plane audit only. It does not lower thresholds, compute EV, size stake, or touch live execution.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for item in rows:
            writer.writerow(dict(item))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_claude_advice_audit()
    paths = write_outputs(report, out_dir=args.out_dir)
    print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
