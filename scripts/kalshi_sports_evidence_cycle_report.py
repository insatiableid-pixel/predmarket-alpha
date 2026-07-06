#!/usr/bin/env python3
"""Summarize one full Kalshi sports evidence-velocity cycle."""

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
    read_json_or_empty,
    safe_research_artifact,
    safety_flags,
    sha256_or_none,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_UNIVERSE_PATH = MACRO_DIR / "latest-kalshi-universe-scan.json"
DEFAULT_SPORTS_OBSERVATION_PATH = MACRO_DIR / "latest-kalshi-sports-proxy-observation-loop.json"
DEFAULT_SPORTS_MODEL_PATH = (
    MACRO_DIR / "latest-kalshi-sports-proxy-feature-model-falsification.json"
)
DEFAULT_SPORTS_REPLAY_PATH = MACRO_DIR / "latest-kalshi-sports-proxy-research-candidate-replay.json"
DEFAULT_SPORTS_CCD_PATH = MACRO_DIR / "latest-kalshi-sports-proxy-capacity-correlation-decay.json"
DEFAULT_SPORTS_CLUSTER_PATH = (
    MACRO_DIR / "latest-kalshi-sports-proxy-correlation-cluster-control.json"
)
DEFAULT_ATP_OBSERVATION_PATH = MACRO_DIR / "latest-kalshi-atp-proxy-observation-loop.json"
DEFAULT_ATP_EVIDENCE_PATH = MACRO_DIR / "latest-kalshi-atp-proxy-evidence-gate.json"
DEFAULT_WORLD_CUP_OBSERVATION_PATH = (
    MACRO_DIR / "latest-kalshi-world-cup-proxy-observation-loop.json"
)
DEFAULT_WORLD_CUP_MODEL_PATH = (
    MACRO_DIR / "latest-kalshi-world-cup-proxy-feature-model-falsification.json"
)
DEFAULT_WORLD_CUP_OUTCOME_INDEPENDENCE_PATH = (
    MACRO_DIR / "latest-kalshi-world-cup-outcome-independence-diagnostic.json"
)
DEFAULT_STACK_PATH = MACRO_DIR / "latest-kalshi-sports-stack-sequencing.json"
DEFAULT_CONSENSUS_PATH = MACRO_DIR / "latest-kalshi-sports-consensus-preflight.json"
DEFAULT_CONSENSUS_OBSERVATION_PATH = (
    MACRO_DIR / "latest-kalshi-sports-consensus-observation-loop.json"
)
DEFAULT_CONSENSUS_FALSIFICATION_PATH = (
    MACRO_DIR / "latest-kalshi-sports-consensus-falsification.json"
)
DEFAULT_CONSENSUS_PROVIDER_AUDIT_PATH = (
    MACRO_DIR / "latest-kalshi-sports-consensus-provider-audit.json"
)
DEFAULT_SOCCER_ASIAN_PROVIDER_PATH = (
    MACRO_DIR / "latest-kalshi-sports-consensus-soccer-asian-provider-diagnostic.json"
)
DEFAULT_EVENT_VELOCITY_PATH = MACRO_DIR / "latest-kalshi-sports-event-velocity-eta.json"
DEFAULT_MICROSTRUCTURE_PATH = (
    MACRO_DIR / "latest-kalshi-sports-microstructure-observation-loop.json"
)
DEFAULT_FLOW_PATH = MACRO_DIR / "latest-kalshi-near-resolution-informed-flow-evidence-gate.json"
DEFAULT_FLOW_REPLAY_PATH = MACRO_DIR / "latest-kalshi-near-resolution-flow-replay-gates.json"
DEFAULT_FLOW_TERMS_PATH = MACRO_DIR / "latest-kalshi-near-resolution-flow-terms-capture.json"
DEFAULT_PASSIVE_PATH = MACRO_DIR / "latest-kalshi-passive-liquidity-provision-evidence-gate.json"
DEFAULT_PASSIVE_PAPER_FILL_PATH = MACRO_DIR / "latest-kalshi-passive-liquidity-paper-fill-loop.json"
DEFAULT_PASSIVE_PAPER_FILL_FALSIFICATION_PATH = (
    MACRO_DIR / "latest-kalshi-passive-liquidity-paper-fill-falsification.json"
)
DEFAULT_PASSIVE_FILL_CLOCK_DIAGNOSTIC_PATH = (
    MACRO_DIR / "latest-kalshi-passive-liquidity-fill-clock-diagnostic.json"
)
DEFAULT_PAPER_PATH = MACRO_DIR / "latest-paper-decision-candidates.json"
DEFAULT_PAPER_SETTLEMENT_PATH = MACRO_DIR / "latest-paper-settlement-reconciliation.json"
DEFAULT_LIVE_PATH = MACRO_DIR / "latest-kalshi-live-preflight.json"
DEFAULT_RETIREMENT_PATH = MACRO_DIR / "latest-signal-decay-retirement-ledger.json"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-evidence-cycle-latest"

CSV_FIELDS = [
    "surface_id",
    "artifact_status",
    "observation_count",
    "label_count",
    "due_count",
    "proxy_label_count",
    "paper_fill_label_count",
    "research_candidate_count",
    "blocked_reason",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_sports_evidence_cycle_report(
    *,
    universe_path: Path = DEFAULT_UNIVERSE_PATH,
    sports_observation_path: Path = DEFAULT_SPORTS_OBSERVATION_PATH,
    sports_model_path: Path = DEFAULT_SPORTS_MODEL_PATH,
    sports_replay_path: Path = DEFAULT_SPORTS_REPLAY_PATH,
    sports_ccd_path: Path = DEFAULT_SPORTS_CCD_PATH,
    sports_cluster_path: Path = DEFAULT_SPORTS_CLUSTER_PATH,
    atp_observation_path: Path = DEFAULT_ATP_OBSERVATION_PATH,
    atp_evidence_path: Path = DEFAULT_ATP_EVIDENCE_PATH,
    world_cup_observation_path: Path = DEFAULT_WORLD_CUP_OBSERVATION_PATH,
    world_cup_model_path: Path = DEFAULT_WORLD_CUP_MODEL_PATH,
    world_cup_outcome_independence_path: Path = DEFAULT_WORLD_CUP_OUTCOME_INDEPENDENCE_PATH,
    stack_path: Path = DEFAULT_STACK_PATH,
    consensus_path: Path = DEFAULT_CONSENSUS_PATH,
    consensus_observation_path: Path = DEFAULT_CONSENSUS_OBSERVATION_PATH,
    consensus_falsification_path: Path = DEFAULT_CONSENSUS_FALSIFICATION_PATH,
    consensus_provider_audit_path: Path = DEFAULT_CONSENSUS_PROVIDER_AUDIT_PATH,
    soccer_asian_provider_path: Path = DEFAULT_SOCCER_ASIAN_PROVIDER_PATH,
    event_velocity_path: Path = DEFAULT_EVENT_VELOCITY_PATH,
    microstructure_path: Path = DEFAULT_MICROSTRUCTURE_PATH,
    flow_path: Path = DEFAULT_FLOW_PATH,
    flow_replay_path: Path = DEFAULT_FLOW_REPLAY_PATH,
    flow_terms_path: Path = DEFAULT_FLOW_TERMS_PATH,
    passive_path: Path = DEFAULT_PASSIVE_PATH,
    passive_paper_fill_path: Path = DEFAULT_PASSIVE_PAPER_FILL_PATH,
    passive_paper_fill_falsification_path: Path = DEFAULT_PASSIVE_PAPER_FILL_FALSIFICATION_PATH,
    passive_fill_clock_diagnostic_path: Path = DEFAULT_PASSIVE_FILL_CLOCK_DIAGNOSTIC_PATH,
    paper_path: Path = DEFAULT_PAPER_PATH,
    paper_settlement_path: Path = DEFAULT_PAPER_SETTLEMENT_PATH,
    live_path: Path = DEFAULT_LIVE_PATH,
    retirement_path: Path = DEFAULT_RETIREMENT_PATH,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    artifacts = {
        "universe": artifact(universe_path),
        "sports_observation": artifact(sports_observation_path),
        "sports_model": artifact(sports_model_path),
        "sports_replay": artifact(sports_replay_path),
        "sports_ccd": artifact(sports_ccd_path),
        "sports_cluster": artifact(sports_cluster_path),
        "atp_observation": artifact(atp_observation_path),
        "atp_evidence": artifact(atp_evidence_path),
        "world_cup_observation": artifact(world_cup_observation_path),
        "world_cup_model": artifact(world_cup_model_path),
        "world_cup_outcome_independence": artifact(world_cup_outcome_independence_path),
        "stack": artifact(stack_path),
        "sports_consensus": artifact(consensus_path),
        "sports_consensus_observation": artifact(consensus_observation_path),
        "sports_consensus_falsification": artifact(consensus_falsification_path),
        "sports_consensus_provider_audit": artifact(consensus_provider_audit_path),
        "soccer_asian_provider": artifact(soccer_asian_provider_path),
        "sports_event_velocity": artifact(event_velocity_path),
        "microstructure": artifact(microstructure_path),
        "flow": artifact(flow_path),
        "flow_replay": artifact(flow_replay_path),
        "flow_terms": artifact(flow_terms_path),
        "passive": artifact(passive_path),
        "passive_paper_fill": artifact(passive_paper_fill_path),
        "passive_paper_fill_falsification": artifact(passive_paper_fill_falsification_path),
        "passive_fill_clock_diagnostic": artifact(passive_fill_clock_diagnostic_path),
        "paper": artifact(paper_path),
        "paper_settlement": artifact(paper_settlement_path),
        "live": artifact(live_path),
        "retirement": artifact(retirement_path),
    }
    rows = surface_rows(artifacts)
    summary = build_summary(artifacts, rows)
    gates = build_gates(artifacts, summary)
    status = report_status(gates, summary)
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
        "north_star": "Extract and exploit mispricings in Kalshi sports contracts before the crowd corrects them.",
        "method": {
            "purpose": "Audit whether the latest sports evidence cycle has increased labels, repeated snapshots, gate-ready rows, or exact blockers.",
            "boundary": "This report only summarizes research artifacts; it never computes a new probability, stake, or order.",
        },
        "inputs": {
            key: {
                "path": item["path"],
                "sha256": item["sha256"],
                "exists": item["exists"],
                "status": item["status"],
                "safe": item["safe"],
            }
            for key, item in artifacts.items()
        },
        "summary": summary,
        "surface_rows": rows,
        "gates": gates,
        "next_action": next_action(status, summary),
        "safety": safety_flags(),
    }


def artifact(path: Path) -> dict[str, Any]:
    payload = read_json_or_empty(path)
    safe = safe_research_artifact(payload) or safe_blocked_live_artifact(payload)
    return {
        "path": str(path),
        "sha256": sha256_or_none(path),
        "exists": path.is_file(),
        "safe": safe,
        "status": payload.get("status"),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {},
        "payload": payload,
    }


def safe_blocked_live_artifact(payload: Mapping[str, Any]) -> bool:
    safety = payload.get("safety") if isinstance(payload.get("safety"), Mapping) else {}
    return (
        str(payload.get("status") or "").startswith("kalshi_live_")
        and payload.get("research_only") is True
        and payload.get("execution_enabled") is False
        and payload.get("market_execution") is False
        and safety.get("manual_approval_queue") is False
        and safety.get("market_orders") is False
        and safety.get("production_requires_env_arm") is True
    )


def surface_rows(artifacts: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        family_row(
            "mlb",
            observation=artifacts["sports_observation"],
            model=artifacts["sports_model"],
            replay=artifacts["sports_replay"],
            ccd=artifacts["sports_ccd"],
            cluster=artifacts["sports_cluster"],
        ),
        family_row(
            "atp",
            observation=artifacts["atp_observation"],
            model=artifacts["atp_evidence"],
        ),
        family_row(
            "world_cup_soccer",
            observation=artifacts["world_cup_observation"],
            model=artifacts["world_cup_model"],
        ),
        consensus_row(
            artifacts["sports_consensus"],
            artifacts["sports_consensus_observation"],
        ),
        microstructure_row(
            artifacts["microstructure"],
            artifacts["flow"],
            artifacts["flow_replay"],
            artifacts["passive"],
            artifacts["passive_paper_fill"],
            artifacts["passive_paper_fill_falsification"],
        ),
    ]


def family_row(
    surface_id: str,
    *,
    observation: Mapping[str, Any],
    model: Mapping[str, Any],
    replay: Mapping[str, Any] | None = None,
    ccd: Mapping[str, Any] | None = None,
    cluster: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    obs = observation.get("summary") if isinstance(observation.get("summary"), Mapping) else {}
    model_summary = model.get("summary") if isinstance(model.get("summary"), Mapping) else {}
    blockers = [
        str(item.get("status") or "")
        for item in (model, replay or {}, ccd or {}, cluster or {})
        if str(item.get("status") or "").endswith("blocked_missing_labels")
        or "blocked" in str(item.get("status") or "")
    ]
    return {
        "surface_id": surface_id,
        "artifact_status": observation.get("status"),
        "model_status": model.get("status"),
        "replay_status": (replay or {}).get("status"),
        "ccd_status": (ccd or {}).get("status"),
        "cluster_status": (cluster or {}).get("status"),
        "observation_count": int_value(obs.get("total_observation_row_count")),
        "distinct_contract_count": int_value(obs.get("distinct_contract_count")),
        "label_count": int_value(obs.get("label_row_count"))
        or int_value(model_summary.get("valid_label_row_count")),
        "proxy_label_count": 0,
        "paper_fill_label_count": 0,
        "due_count": int_value(obs.get("due_distinct_contract_count")),
        "research_candidate_count": int_value(model_summary.get("research_candidate_count")),
        "blocked_reason": "; ".join(blockers[:4]) if blockers else "waiting_for_gate_evidence",
    }


def consensus_row(
    consensus: Mapping[str, Any],
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    summary = consensus.get("summary") if isinstance(consensus.get("summary"), Mapping) else {}
    obs_summary = (
        observation.get("summary") if isinstance(observation.get("summary"), Mapping) else {}
    )
    observation_count = int_value(obs_summary.get("total_observation_row_count"))
    label_count = int_value(obs_summary.get("label_row_count"))
    due_count = int_value(obs_summary.get("due_distinct_contract_count"))
    return {
        "surface_id": "sports_no_vig_consensus",
        "artifact_status": observation.get("status") or consensus.get("status"),
        "model_status": consensus.get("status"),
        "replay_status": None,
        "ccd_status": None,
        "cluster_status": None,
        "observation_count": observation_count or int_value(summary.get("reference_row_count")),
        "distinct_contract_count": int_value(summary.get("candidate_count")),
        "label_count": label_count,
        "proxy_label_count": 0,
        "paper_fill_label_count": 0,
        "due_count": due_count or int_value(summary.get("valid_candidate_count")),
        "research_candidate_count": int_value(summary.get("valid_candidate_count")),
        "blocked_reason": (
            "timestamp_matched_no_vig_consensus_observation_archive_ready"
            if observation_count > 0
            else "timestamp_matched_no_vig_consensus_ready"
            if int_value(summary.get("valid_candidate_count")) > 0
            else str(consensus.get("status") or "waiting_for_multi_book_consensus_reference")
        ),
    }


def consensus_falsification_status(
    falsification: Mapping[str, Any],
) -> dict[str, Any]:
    payload = falsification.get("payload") if isinstance(falsification, Mapping) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    return {
        "status": payload.get("status"),
        "joined_label_count": int_value(summary.get("joined_label_count")),
        "independent_label_count": int_value(summary.get("independent_label_count")),
        "tested_hypothesis_count": int_value(summary.get("tested_hypothesis_count")),
        "fdr_survivor_count": int_value(summary.get("fdr_survivor_count")),
        "research_candidate_count": int_value(summary.get("fdr_survivor_count")),
    }


def microstructure_row(
    microstructure: Mapping[str, Any],
    flow: Mapping[str, Any],
    flow_replay: Mapping[str, Any],
    passive: Mapping[str, Any],
    passive_paper_fill: Mapping[str, Any],
    passive_paper_fill_falsification: Mapping[str, Any],
) -> dict[str, Any]:
    micro_summary = (
        microstructure.get("summary") if isinstance(microstructure.get("summary"), Mapping) else {}
    )
    flow_summary = flow.get("summary") if isinstance(flow.get("summary"), Mapping) else {}
    replay_summary = (
        flow_replay.get("summary") if isinstance(flow_replay.get("summary"), Mapping) else {}
    )
    passive_summary = passive.get("summary") if isinstance(passive.get("summary"), Mapping) else {}
    paper_fill_summary = (
        passive_paper_fill.get("summary")
        if isinstance(passive_paper_fill.get("summary"), Mapping)
        else {}
    )
    paper_fill_falsification_summary = (
        passive_paper_fill_falsification.get("summary")
        if isinstance(passive_paper_fill_falsification.get("summary"), Mapping)
        else {}
    )
    blockers = microstructure_blockers(
        flow=flow,
        flow_replay=flow_replay,
        passive=passive,
        passive_paper_fill=passive_paper_fill,
        passive_paper_fill_falsification=passive_paper_fill_falsification,
        paper_fill_label_count=int_value(paper_fill_summary.get("paper_fill_label_count")),
    )
    falsification_status = str(passive_paper_fill_falsification.get("status") or "")
    blocked_reason = "; ".join(blockers)
    if not blocked_reason:
        blocked_reason = (
            falsification_status
            if falsification_status
            == "passive_liquidity_paper_fill_falsification_ready_no_research_candidates"
            else "waiting_for_repeated_snapshot_evidence"
        )
    return {
        "surface_id": "sports_microstructure",
        "artifact_status": microstructure.get("status"),
        "model_status": flow.get("status"),
        "replay_status": flow_replay.get("status"),
        "ccd_status": passive.get("status"),
        "cluster_status": None,
        "observation_count": int_value(micro_summary.get("historical_observation_row_count"))
        or int_value(micro_summary.get("observation_row_count")),
        "distinct_contract_count": int_value(
            micro_summary.get("historical_distinct_contract_count")
        )
        or int_value(flow_summary.get("distinct_contract_count")),
        "label_count": int_value(flow_summary.get("forward_quote_label_count")),
        "proxy_label_count": int_value(
            passive_summary.get("counterfactual_fill_proxy_label_count")
        ),
        "paper_fill_label_count": int_value(paper_fill_summary.get("paper_fill_label_count")),
        "due_count": int_value(replay_summary.get("current_candidate_row_count"))
        or int_value(passive_summary.get("counterfactual_fill_proxy_label_count")),
        "research_candidate_count": int_value(flow_summary.get("research_candidate_count")),
        "blocked_reason": blocked_reason,
        "repeated_snapshot_contract_count": int_value(
            micro_summary.get("repeated_snapshot_contract_count")
        )
        or int_value(flow_summary.get("repeated_snapshot_contract_count")),
        "passive_would_touch_proxy_count": int_value(
            passive_summary.get("would_touch_proxy_count")
        ),
        "passive_paper_fill_status": passive_paper_fill.get("status"),
        "passive_paper_fill_falsification_status": passive_paper_fill_falsification.get("status"),
        "passive_paper_intent_count": int_value(paper_fill_summary.get("paper_intent_count")),
        "passive_open_paper_intent_count": int_value(
            paper_fill_summary.get("open_paper_intent_count")
        ),
        "passive_paper_fill_fdr_survivor_count": int_value(
            paper_fill_falsification_summary.get("fdr_survivor_count")
        ),
    }


def microstructure_blockers(
    *,
    flow: Mapping[str, Any],
    flow_replay: Mapping[str, Any],
    passive: Mapping[str, Any],
    passive_paper_fill: Mapping[str, Any],
    passive_paper_fill_falsification: Mapping[str, Any],
    paper_fill_label_count: int,
) -> list[str]:
    blockers: list[str] = []
    paper_fill_falsification_status = str(passive_paper_fill_falsification.get("status") or "")
    paper_fill_supersedes_proxy_only = (
        paper_fill_label_count > 0
        and paper_fill_falsification_status.startswith(
            "passive_liquidity_paper_fill_falsification_ready"
        )
    )
    for item in (
        flow,
        flow_replay,
        passive,
        passive_paper_fill,
        passive_paper_fill_falsification,
    ):
        status = str(item.get("status") or "")
        if "blocked" not in status:
            continue
        if (
            paper_fill_supersedes_proxy_only
            and status == "passive_liquidity_provision_blocked_proxy_only_no_real_fill_labels"
        ):
            continue
        blockers.append(status)
    return blockers


def build_summary(
    artifacts: Mapping[str, Mapping[str, Any]], rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    paper_summary = artifacts["paper"].get("summary", {})
    paper_settlement_summary = artifacts["paper_settlement"].get("summary", {})
    live_summary = artifacts["live"].get("summary", {})
    stack_summary = artifacts["stack"].get("summary", {})
    stack_payload = artifacts["stack"].get("payload", {})
    cluster_summary = artifacts["sports_cluster"].get("summary", {})
    flow_terms_summary = artifacts["flow_terms"].get("summary", {})
    consensus_summary = artifacts["sports_consensus"].get("summary", {})
    consensus_observation_summary = artifacts["sports_consensus_observation"].get("summary", {})
    consensus_falsification_summary = artifacts["sports_consensus_falsification"].get("summary", {})
    consensus_provider_summary = artifacts["sports_consensus_provider_audit"].get("summary", {})
    soccer_asian_summary = artifacts["soccer_asian_provider"].get("summary", {})
    event_velocity_summary = artifacts["sports_event_velocity"].get("summary", {})
    event_velocity_payload = artifacts["sports_event_velocity"].get("payload", {})
    consensus_rule_bucket_eta = eta_row_by_surface(
        event_velocity_payload, "sports_consensus_rule_bucket_accumulation"
    )
    world_cup_outcome_summary = artifacts["world_cup_outcome_independence"].get("summary", {})
    passive_paper_fill_summary = artifacts["passive_paper_fill"].get("summary", {})
    passive_paper_fill_falsification_summary = artifacts["passive_paper_fill_falsification"].get(
        "summary", {}
    )
    passive_fill_clock_summary = artifacts["passive_fill_clock_diagnostic"].get("summary", {})
    stack_blocker_rows = (
        stack_payload.get("paper_decision_blocker_rows")
        if isinstance(stack_payload.get("paper_decision_blocker_rows"), list)
        else []
    )
    return {
        "safe_artifact_count": sum(1 for item in artifacts.values() if item.get("safe")),
        "artifact_count": len(artifacts),
        "unsafe_artifact_keys": [
            key for key, item in artifacts.items() if item.get("exists") and not item.get("safe")
        ],
        "missing_artifact_keys": [key for key, item in artifacts.items() if not item.get("exists")],
        "sports_surface_count": len(rows),
        "total_observation_count": sum(int(row.get("observation_count") or 0) for row in rows),
        "total_label_count": sum(int(row.get("label_count") or 0) for row in rows),
        "total_proxy_label_count": sum(int(row.get("proxy_label_count") or 0) for row in rows),
        "total_paper_fill_label_count": sum(
            int(row.get("paper_fill_label_count") or 0) for row in rows
        ),
        "total_due_count": sum(int(row.get("due_count") or 0) for row in rows),
        "total_research_candidate_count": sum(
            int(row.get("research_candidate_count") or 0) for row in rows
        ),
        "independent_cluster_count": int_value(cluster_summary.get("positive_cluster_count")),
        "paper_candidate_count": int_value(paper_summary.get("candidate_count")),
        "paper_gate_evidence_row_count": int_value(paper_summary.get("gate_evidence_row_count")),
        "paper_usable_count": int_value(paper_summary.get("paper_usable_count")),
        "paper_settlement_status": artifacts["paper_settlement"].get("status"),
        "paper_settled_usable_count": int_value(
            paper_settlement_summary.get("settled_paper_usable_count")
        ),
        "paper_unresolved_usable_count": int_value(
            paper_settlement_summary.get("unresolved_paper_usable_count")
        ),
        "paper_due_unresolved_usable_count": int_value(
            paper_settlement_summary.get("due_unresolved_paper_usable_count")
        ),
        "paper_next_unresolved_close_time_utc": paper_settlement_summary.get(
            "next_unresolved_close_time_utc"
        ),
        "paper_realized_pnl": paper_settlement_summary.get("realized_pnl"),
        "paper_hit_rate": paper_settlement_summary.get("hit_rate"),
        "paper_total_stake": paper_settlement_summary.get(
            "total_paper_stake", paper_summary.get("total_paper_stake")
        ),
        "paper_portfolio_cap_status": paper_settlement_summary.get(
            "paper_portfolio_cap_status",
            paper_summary.get("paper_portfolio_cap_status"),
        ),
        "paper_portfolio_cap_breach_count": int_value(
            paper_settlement_summary.get(
                "paper_portfolio_cap_breach_count",
                paper_summary.get("paper_portfolio_cap_breach_count"),
            )
        ),
        "paper_portfolio_largest_cluster": paper_settlement_summary.get(
            "paper_portfolio_largest_cluster",
            paper_summary.get("paper_portfolio_largest_cluster"),
        ),
        "paper_portfolio_largest_signal": paper_settlement_summary.get(
            "paper_portfolio_largest_signal",
            paper_summary.get("paper_portfolio_largest_signal"),
        ),
        "flow_terms_official_rules_market_count": int_value(
            flow_terms_summary.get("official_rules_market_count")
        ),
        "flow_terms_captured_target_count": int_value(
            flow_terms_summary.get("captured_target_count")
        ),
        "sports_consensus_valid_candidate_count": int_value(
            consensus_summary.get("valid_candidate_count")
        ),
        "sports_consensus_blocker_count": int_value(consensus_summary.get("blocker_count")),
        "sports_consensus_observation_status": artifacts["sports_consensus_observation"].get(
            "status"
        ),
        "sports_consensus_observation_count": int_value(
            consensus_observation_summary.get("total_observation_row_count")
        ),
        "sports_consensus_new_observation_count": int_value(
            consensus_observation_summary.get("new_observation_row_count")
        ),
        "sports_consensus_label_count": int_value(
            consensus_observation_summary.get("label_row_count")
        ),
        "sports_consensus_new_label_count": int_value(
            consensus_observation_summary.get("new_label_row_count")
        ),
        "sports_consensus_falsification_status": artifacts["sports_consensus_falsification"].get(
            "status"
        ),
        "sports_consensus_falsification_joined_label_count": int_value(
            consensus_falsification_summary.get("joined_label_count")
        ),
        "sports_consensus_falsification_tested_hypothesis_count": int_value(
            consensus_falsification_summary.get("tested_hypothesis_count")
        ),
        "sports_consensus_falsification_max_hypothesis_oos_count": int_value(
            consensus_falsification_summary.get("max_hypothesis_oos_count")
        ),
        "sports_consensus_falsification_hypothesis_accumulation_plan_count": int_value(
            consensus_falsification_summary.get("hypothesis_accumulation_plan_count")
        ),
        "sports_consensus_falsification_nearest_hypothesis_oos_deficit": int_value(
            consensus_falsification_summary.get("nearest_hypothesis_oos_deficit")
        ),
        "sports_consensus_falsification_nearest_hypothesis_model_id": (
            consensus_falsification_summary.get("nearest_hypothesis_model_id")
        ),
        "sports_consensus_falsification_accumulation_opportunity_count": int_value(
            consensus_falsification_summary.get("hypothesis_accumulation_opportunity_count")
        ),
        "sports_consensus_falsification_accumulation_opportunity_distinct_contract_count": (
            int_value(
                consensus_falsification_summary.get(
                    "hypothesis_accumulation_opportunity_distinct_contract_count"
                )
            )
        ),
        "sports_consensus_falsification_nearest_hypothesis_current_opportunity_count": (
            int_value(
                consensus_falsification_summary.get(
                    "nearest_hypothesis_current_opportunity_count"
                )
            )
        ),
        "sports_consensus_falsification_fdr_survivor_count": int_value(
            consensus_falsification_summary.get("fdr_survivor_count")
        ),
        "sports_consensus_falsification_research_candidate_count": int_value(
            consensus_falsification_summary.get("fdr_survivor_count")
        ),
        "sports_consensus_provider_audit_status": artifacts["sports_consensus_provider_audit"].get(
            "status"
        ),
        "sports_consensus_provider_sport_target_count": int_value(
            consensus_provider_summary.get("sport_target_count")
        ),
        "sports_consensus_provider_sport_covered_count": int_value(
            consensus_provider_summary.get("sport_covered_count")
        ),
        "sports_consensus_provider_sport_gap_count": int_value(
            consensus_provider_summary.get("sport_gap_count")
        ),
        "sports_consensus_provider_sport_deferred_count": int_value(
            consensus_provider_summary.get("sport_deferred_count")
        ),
        "sports_consensus_provider_deferred_sports": consensus_provider_summary.get(
            "deferred_sports", []
        ),
        "sports_consensus_provider_actionable_gap_sports": consensus_provider_summary.get(
            "actionable_gap_sports", []
        ),
        "sports_consensus_provider_strict_consensus_sport_count": int_value(
            consensus_provider_summary.get("strict_consensus_sport_count")
        ),
        "sports_consensus_provider_strict_consensus_sports": consensus_provider_summary.get(
            "strict_consensus_sports", []
        ),
        "sports_consensus_provider_covered_sports": consensus_provider_summary.get(
            "covered_sports", []
        ),
        "soccer_asian_provider_status": artifacts["soccer_asian_provider"].get("status"),
        "soccer_asian_provider_requested_target_provider_count": int_value(
            soccer_asian_summary.get("requested_target_provider_count")
        ),
        "soccer_asian_provider_observed_target_provider_count": int_value(
            soccer_asian_summary.get("observed_target_provider_count")
        ),
        "soccer_asian_provider_missing_target_providers": soccer_asian_summary.get(
            "missing_target_providers", []
        ),
        "soccer_asian_provider_latest_capture_utc": soccer_asian_summary.get(
            "latest_capture_utc"
        ),
        "sports_event_velocity_status": artifacts["sports_event_velocity"].get("status"),
        "sports_event_velocity_label_blocked_surface_count": int_value(
            event_velocity_summary.get("label_blocked_surface_count")
        ),
        "sports_event_velocity_actionable_calendar_label_blocked_surface_count": int_value(
            event_velocity_summary.get("actionable_calendar_label_blocked_surface_count")
        ),
        "sports_event_velocity_external_or_source_blocked_surface_count": int_value(
            event_velocity_summary.get("external_or_source_blocked_surface_count")
        ),
        "sports_event_velocity_waiting_evidence_blocked_surface_count": int_value(
            event_velocity_summary.get("waiting_evidence_blocked_surface_count")
        ),
        "sports_event_velocity_statistical_no_survivor_surface_count": int_value(
            event_velocity_summary.get("statistical_no_survivor_surface_count")
        ),
        "sports_event_velocity_paper_fill_blocked_surface_count": int_value(
            event_velocity_summary.get("paper_fill_blocked_surface_count")
        ),
        "sports_event_velocity_total_label_deficit": int_value(
            event_velocity_summary.get("total_label_deficit")
        ),
        "sports_event_velocity_total_oos_deficit": int_value(
            event_velocity_summary.get("total_oos_deficit")
        ),
        "sports_event_velocity_actionable_calendar_label_deficit": int_value(
            event_velocity_summary.get("actionable_calendar_label_deficit")
        ),
        "sports_event_velocity_actionable_calendar_oos_deficit": int_value(
            event_velocity_summary.get("actionable_calendar_oos_deficit")
        ),
        "sports_event_velocity_external_or_source_label_deficit": int_value(
            event_velocity_summary.get("external_or_source_label_deficit")
        ),
        "sports_event_velocity_external_or_source_oos_deficit": int_value(
            event_velocity_summary.get("external_or_source_oos_deficit")
        ),
        "sports_event_velocity_waiting_evidence_label_deficit": int_value(
            event_velocity_summary.get("waiting_evidence_label_deficit")
        ),
        "sports_event_velocity_waiting_evidence_oos_deficit": int_value(
            event_velocity_summary.get("waiting_evidence_oos_deficit")
        ),
        "sports_event_velocity_eta_status_counts": event_velocity_summary.get(
            "eta_status_counts", {}
        ),
        "sports_event_velocity_bottleneck_type_counts": event_velocity_summary.get(
            "bottleneck_type_counts", {}
        ),
        "sports_event_velocity_next_due_surface": event_velocity_summary.get("next_due_surface"),
        "sports_event_velocity_next_probe_surface": event_velocity_summary.get(
            "next_probe_surface"
        ),
        "sports_event_velocity_consensus_rule_bucket_model_id": consensus_rule_bucket_eta.get(
            "model_id"
        ),
        "sports_event_velocity_consensus_rule_bucket_oos_label_count": int_value(
            consensus_rule_bucket_eta.get("oos_label_count")
        ),
        "sports_event_velocity_consensus_rule_bucket_oos_deficit": int_value(
            consensus_rule_bucket_eta.get("oos_deficit")
        ),
        "sports_event_velocity_consensus_rule_bucket_opportunity_count": int_value(
            consensus_rule_bucket_eta.get("hypothesis_accumulation_opportunity_count")
        ),
        "sports_event_velocity_consensus_rule_bucket_nearest_opportunity_count": int_value(
            consensus_rule_bucket_eta.get("nearest_hypothesis_current_opportunity_count")
        ),
        "sports_event_velocity_consensus_rule_bucket_next_probe_utc": (
            consensus_rule_bucket_eta.get("next_probe_utc")
        ),
        "sports_event_velocity_consensus_rule_bucket_eta_days": consensus_rule_bucket_eta.get(
            "eta_days"
        ),
        "world_cup_outcome_independence_status": artifacts["world_cup_outcome_independence"].get(
            "status"
        ),
        "world_cup_outcome_exact_contract_label_count": int_value(
            world_cup_outcome_summary.get("exact_contract_label_count")
        ),
        "world_cup_outcome_family_label_count": int_value(
            world_cup_outcome_summary.get("outcome_family_label_count")
        ),
        "world_cup_outcome_match_cluster_count": int_value(
            world_cup_outcome_summary.get("match_cluster_count")
        ),
        "world_cup_outcome_candidate_independence_requires_review": bool(
            world_cup_outcome_summary.get("current_candidate_independence_requires_review")
        ),
        "world_cup_outcome_recommended_portfolio_cluster_unit": world_cup_outcome_summary.get(
            "recommended_portfolio_cluster_unit"
        ),
        "passive_paper_fill_status": artifacts["passive_paper_fill"].get("status"),
        "passive_paper_fill_falsification_status": artifacts[
            "passive_paper_fill_falsification"
        ].get("status"),
        "passive_paper_intent_count": int_value(
            passive_paper_fill_summary.get("paper_intent_count")
        ),
        "passive_new_paper_intent_count": int_value(
            passive_paper_fill_summary.get("new_paper_intent_count")
        ),
        "passive_open_paper_intent_count": int_value(
            passive_paper_fill_summary.get("open_paper_intent_count")
        ),
        "passive_paper_fill_label_count": int_value(
            passive_paper_fill_summary.get("paper_fill_label_count")
        ),
        "passive_new_paper_fill_label_count": int_value(
            passive_paper_fill_summary.get("new_paper_fill_label_count")
        ),
        "passive_real_exchange_fill_label_count": int_value(
            passive_paper_fill_summary.get("real_exchange_fill_label_count")
        ),
        "passive_paper_fill_falsification_label_count": int_value(
            passive_paper_fill_falsification_summary.get("valid_paper_fill_label_count")
        ),
        "passive_paper_fill_falsification_fill_count": int_value(
            passive_paper_fill_falsification_summary.get("paper_filled_count")
        ),
        "passive_paper_fill_falsification_tested_hypothesis_count": int_value(
            passive_paper_fill_falsification_summary.get("tested_hypothesis_count")
        ),
        "passive_paper_fill_falsification_fdr_survivor_count": int_value(
            passive_paper_fill_falsification_summary.get("fdr_survivor_count")
        ),
        "passive_fill_clock_diagnostic_status": artifacts["passive_fill_clock_diagnostic"].get(
            "status"
        ),
        "passive_fill_clock_primary_bottleneck": passive_fill_clock_summary.get(
            "fill_clock_primary_bottleneck"
        ),
        "passive_fill_clock_ttl_cadence_mismatch_count": int_value(
            passive_fill_clock_summary.get("ttl_cadence_mismatch_count")
        ),
        "passive_fill_clock_active_ttl_cadence_mismatch_count": int_value(
            passive_fill_clock_summary.get("active_ttl_cadence_mismatch_count")
        ),
        "passive_fill_clock_current_ttl_cadence_aligned": bool(
            passive_fill_clock_summary.get("current_ttl_cadence_aligned")
        ),
        "passive_fill_clock_future_snapshot_within_ttl_count": int_value(
            passive_fill_clock_summary.get("future_snapshot_within_ttl_intent_count")
        ),
        "passive_fill_clock_recommended_ttl_seconds": int_value(
            passive_fill_clock_summary.get("recommended_ttl_seconds")
        ),
        "live_decision_count": int_value(live_summary.get("live_decision_count")),
        "live_eligible_count": int_value(live_summary.get("live_eligible_count")),
        "sports_stack_candidate_count": int_value(stack_summary.get("candidate_count")),
        "sports_stack_blocker_row_count": len(stack_blocker_rows),
    }


def build_gates(
    artifacts: Mapping[str, Mapping[str, Any]], summary: Mapping[str, Any]
) -> list[dict[str, str]]:
    unsafe = [key for key, item in artifacts.items() if item.get("exists") and not item.get("safe")]
    missing = [key for key, item in artifacts.items() if not item.get("exists")]
    paper_gate_rows = int_value(summary.get("paper_gate_evidence_row_count"))
    stack_rows = int_value(summary.get("sports_stack_blocker_row_count"))
    live_eligible = int_value(summary.get("live_eligible_count"))
    return [
        gate(
            "all_existing_artifacts_safe",
            "pass" if not unsafe else "fail",
            f"Unsafe artifacts: {unsafe or []}.",
        ),
        gate(
            "required_cycle_artifacts_exist",
            "pass" if not missing else "blocked",
            f"Missing artifacts: {missing or []}.",
        ),
        gate(
            "sports_rows_enter_paper_chain",
            "pass" if paper_gate_rows >= stack_rows and stack_rows > 0 else "blocked",
            (
                f"{paper_gate_rows} gate-evidence sports row(s) in paper chain; "
                f"{stack_rows} sports-stack blocker row(s)."
            ),
        ),
        gate(
            "live_promotion_remains_blocked_until_all_gates_pass",
            "pass" if live_eligible == 0 else "warn",
            f"{live_eligible} live-eligible row(s).",
        ),
        gate(
            "sports_consensus_provider_coverage_audited",
            "pass" if artifacts["sports_consensus_provider_audit"].get("safe") else "blocked",
            (
                "Provider coverage audit loaded; "
                f"{summary.get('sports_consensus_provider_sport_covered_count')}/"
                f"{summary.get('sports_consensus_provider_sport_target_count')} target sport(s) covered."
            ),
        ),
        gate(
            "sports_event_velocity_eta_ready",
            "pass" if artifacts["sports_event_velocity"].get("safe") else "blocked",
            f"Event-velocity ETA status: {summary.get('sports_event_velocity_status')}.",
        ),
        gate(
            "passive_fill_clock_diagnostic_ready",
            "pass" if artifacts["passive_fill_clock_diagnostic"].get("safe") else "blocked",
            (
                "Passive fill-clock diagnostic status: "
                f"{summary.get('passive_fill_clock_diagnostic_status')}."
            ),
        ),
        gate(
            "world_cup_outcome_independence_diagnostic_ready",
            "pass" if artifacts["world_cup_outcome_independence"].get("safe") else "blocked",
            (
                "World Cup outcome-independence diagnostic status: "
                f"{summary.get('world_cup_outcome_independence_status')}."
            ),
        ),
        gate(
            "world_cup_candidate_independence_review_visible",
            "warn"
            if summary.get("world_cup_outcome_candidate_independence_requires_review")
            else "pass",
            (
                "World Cup candidate independence review required: "
                f"{summary.get('world_cup_outcome_candidate_independence_requires_review')}."
            ),
        ),
        gate(
            "sports_consensus_all_target_sports_have_sharp_coverage",
            "pass"
            if int_value(summary.get("sports_consensus_provider_sport_gap_count")) == 0
            else "warn",
            f"{summary.get('sports_consensus_provider_sport_gap_count')} sport coverage gap(s).",
        ),
    ]


def report_status(gates: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> str:
    if any(item.get("status") == "fail" for item in gates):
        return "sports_evidence_cycle_failed_safety_gate"
    if any(item.get("status") == "blocked" for item in gates):
        return "sports_evidence_cycle_blocked_missing_required_artifacts"
    if int_value(summary.get("live_eligible_count")) > 0:
        return "sports_evidence_cycle_ready_with_live_eligible_rows"
    if int_value(summary.get("total_label_count")) > 0:
        return "sports_evidence_cycle_ready_with_label_progress"
    return "sports_evidence_cycle_ready_all_rows_blocked"


def next_action(status: str, summary: Mapping[str, Any]) -> dict[str, str]:
    if status.startswith("sports_evidence_cycle_failed"):
        return {
            "name": "kalshi_artifact_safety_audit",
            "why": "Safety gate failure detected: unsafe artifacts exist. Resolve artifact safety issues before continuing label or gate processing.",
            "stop_condition": "Stop before overriding safety flags or continuing accumulation while unsafe artifacts are present.",
        }
    if status == "sports_evidence_cycle_ready_with_live_eligible_rows":
        return {
            "name": "kalshi_live_preflight_audit",
            "why": "Live-eligible rows exist; audit strict live arming and risk caps before any execution mode change.",
            "stop_condition": "Stop before manual trade approval or bypassing live-risk gates.",
        }
    eta_due = summary.get("sports_event_velocity_next_due_surface")
    if isinstance(eta_due, Mapping):
        return {
            "name": "kalshi_sports_exact_settlement_probe",
            "why": (
                "Event-velocity ETA says observed sports contracts are due; probe exact "
                "public Kalshi tickers for settled labels."
            ),
            "stop_condition": "Stop before using non-Kalshi labels or unsettled rows as evidence.",
        }
    eta_probe = summary.get("sports_event_velocity_next_probe_surface")
    if int_value(summary.get("sports_event_velocity_external_or_source_blocked_surface_count")) > 0:
        return {
            "name": "kalshi_sports_stale_or_source_blocker_refresh",
            "why": "At least one sports surface is blocked by stale, unmatched, or externally missing consensus evidence.",
            "stop_condition": "Stop before treating stale donor/reference rows as current sharp consensus.",
        }
    if (
        int_value(
            summary.get("sports_event_velocity_actionable_calendar_label_blocked_surface_count")
        )
        > 0
    ):
        return {
            "name": "kalshi_sports_wait_for_next_settlement_clock",
            "why": (
                "Sports label blockers remain; next deficient probe surface is "
                f"{eta_probe.get('surface_id')} at {eta_probe.get('next_probe_utc')}."
                if isinstance(eta_probe, Mapping)
                else "Sports label blockers remain, but event-velocity ETA reports no due surface yet."
            ),
            "stop_condition": "Stop before repeat-probing early or lowering label/FDR thresholds.",
        }
    return {
        "name": "kalshi_sports_evidence_accumulation",
        "why": "Rows are flowing through the gate chain, but labels/repeated snapshots are still insufficient.",
        "stop_condition": "Stop before threshold lowering or discretionary candidate promotion.",
    }


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def eta_row_by_surface(payload: Mapping[str, Any], surface_id: str) -> Mapping[str, Any]:
    rows = payload.get("eta_rows")
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if isinstance(row, Mapping) and row.get("surface_id") == surface_id:
            return row
    return {}


def write_outputs(report: Mapping[str, Any], *, out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-evidence-cycle.json"
    md_path = out_dir / "kalshi-sports-evidence-cycle.md"
    csv_path = out_dir / "kalshi-sports-evidence-cycle.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("surface_rows", []), csv_path)

    latest_json = MACRO_DIR / "latest-kalshi-sports-evidence-cycle.json"
    latest_md = MACRO_DIR / "latest-kalshi-sports-evidence-cycle.md"
    latest_csv = MACRO_DIR / "latest-kalshi-sports-evidence-cycle.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("surface_rows", []), latest_csv)
    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
        "latest_csv_path": str(latest_csv),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Sports Evidence Cycle",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Total observations: `{summary.get('total_observation_count')}`",
        f"- Total labels: `{summary.get('total_label_count')}`",
        f"- Total proxy labels: `{summary.get('total_proxy_label_count')}`",
        f"- Passive paper fill/timeout labels: `{summary.get('passive_paper_fill_label_count')}`",
        f"- Passive paper intents: `{summary.get('passive_paper_intent_count')}`",
        f"- Passive open paper intents: `{summary.get('passive_open_paper_intent_count')}`",
        f"- Passive paper fill loop: `{summary.get('passive_paper_fill_status')}`",
        f"- Passive paper fill falsification: `{summary.get('passive_paper_fill_falsification_status')}`",
        f"- Passive paper fill FDR survivors: `{summary.get('passive_paper_fill_falsification_fdr_survivor_count')}`",
        f"- Passive fill-clock diagnostic: `{summary.get('passive_fill_clock_diagnostic_status')}`",
        f"- Passive fill-clock bottleneck: `{summary.get('passive_fill_clock_primary_bottleneck')}`",
        f"- Passive TTL/cadence mismatches: `{summary.get('passive_fill_clock_ttl_cadence_mismatch_count')}`",
        f"- Passive active TTL/cadence mismatches: `{summary.get('passive_fill_clock_active_ttl_cadence_mismatch_count')}`",
        f"- Passive current TTL cadence aligned: `{summary.get('passive_fill_clock_current_ttl_cadence_aligned')}`",
        f"- Passive recommended TTL seconds: `{summary.get('passive_fill_clock_recommended_ttl_seconds')}`",
        f"- Independent clusters: `{summary.get('independent_cluster_count')}`",
        f"- Paper candidates: `{summary.get('paper_candidate_count')}`",
        f"- Paper usable: `{summary.get('paper_usable_count')}`",
        f"- Paper settlement: `{summary.get('paper_settlement_status')}`",
        f"- Paper settled usable: `{summary.get('paper_settled_usable_count')}`",
        f"- Paper due unresolved usable: `{summary.get('paper_due_unresolved_usable_count')}`",
        f"- Paper next unresolved close: `{summary.get('paper_next_unresolved_close_time_utc')}`",
        f"- Paper total stake: `{summary.get('paper_total_stake')}`",
        f"- Paper realized PnL: `{summary.get('paper_realized_pnl')}`",
        f"- Paper portfolio cap status: `{summary.get('paper_portfolio_cap_status')}`",
        f"- Largest paper cluster: `{summary.get('paper_portfolio_largest_cluster')}`",
        f"- Sports no-vig consensus rows: `{summary.get('sports_consensus_valid_candidate_count')}`",
        f"- Sports consensus observations: `{summary.get('sports_consensus_observation_count')}`",
        f"- Sports consensus labels: `{summary.get('sports_consensus_label_count')}`",
        f"- Sports consensus observation loop: `{summary.get('sports_consensus_observation_status')}`",
        f"- Sports consensus falsification: `{summary.get('sports_consensus_falsification_status')}`",
        f"- Sports consensus joined labels: `{summary.get('sports_consensus_falsification_joined_label_count')}`",
        f"- Sports consensus tested hypotheses: `{summary.get('sports_consensus_falsification_tested_hypothesis_count')}`",
        f"- Sports consensus max hypothesis OOS labels: `{summary.get('sports_consensus_falsification_max_hypothesis_oos_count')}`",
        f"- Sports consensus hypothesis accumulation rows: `{summary.get('sports_consensus_falsification_hypothesis_accumulation_plan_count')}`",
        f"- Sports consensus nearest hypothesis OOS deficit: `{summary.get('sports_consensus_falsification_nearest_hypothesis_oos_deficit')}`",
        f"- Sports consensus nearest hypothesis model: `{summary.get('sports_consensus_falsification_nearest_hypothesis_model_id')}`",
        f"- Sports consensus accumulation opportunities: `{summary.get('sports_consensus_falsification_accumulation_opportunity_count')}`",
        f"- Sports consensus opportunity contracts: `{summary.get('sports_consensus_falsification_accumulation_opportunity_distinct_contract_count')}`",
        f"- Sports consensus nearest hypothesis opportunities: `{summary.get('sports_consensus_falsification_nearest_hypothesis_current_opportunity_count')}`",
        f"- Sports consensus FDR survivors: `{summary.get('sports_consensus_falsification_fdr_survivor_count')}`",
        f"- Sports consensus provider audit: `{summary.get('sports_consensus_provider_audit_status')}`",
        f"- Sports consensus target sports with strict rows: `{summary.get('sports_consensus_provider_strict_consensus_sport_count')}/{summary.get('sports_consensus_provider_sport_target_count')}`",
        f"- Sports consensus target sports covered: `{summary.get('sports_consensus_provider_sport_covered_count')}/{summary.get('sports_consensus_provider_sport_target_count')}`",
        f"- Sports consensus provider gaps: `{summary.get('sports_consensus_provider_sport_gap_count')}`",
        f"- Sports consensus actionable provider gaps: `{summary.get('sports_consensus_provider_actionable_gap_sports')}`",
        f"- Sports consensus deferred target sports: `{summary.get('sports_consensus_provider_deferred_sports')}`",
        f"- Soccer Asian provider diagnostic: `{summary.get('soccer_asian_provider_status')}`",
        f"- Soccer Asian providers observed: `{summary.get('soccer_asian_provider_observed_target_provider_count')}`",
        f"- Soccer Asian providers missing: `{summary.get('soccer_asian_provider_missing_target_providers')}`",
        f"- Sports event-velocity ETA: `{summary.get('sports_event_velocity_status')}`",
        f"- Sports event-velocity label-blocked surfaces: `{summary.get('sports_event_velocity_label_blocked_surface_count')}`",
        f"- Sports event-velocity actionable calendar blockers: `{summary.get('sports_event_velocity_actionable_calendar_label_blocked_surface_count')}`",
        f"- Sports event-velocity external/source blockers: `{summary.get('sports_event_velocity_external_or_source_blocked_surface_count')}`",
        f"- Sports event-velocity waiting-evidence blockers: `{summary.get('sports_event_velocity_waiting_evidence_blocked_surface_count')}`",
        f"- Sports event-velocity total label deficit: `{summary.get('sports_event_velocity_total_label_deficit')}`",
        f"- Sports event-velocity total OOS deficit: `{summary.get('sports_event_velocity_total_oos_deficit')}`",
        f"- Sports event-velocity actionable label deficit: `{summary.get('sports_event_velocity_actionable_calendar_label_deficit')}`",
        f"- Sports event-velocity actionable OOS deficit: `{summary.get('sports_event_velocity_actionable_calendar_oos_deficit')}`",
        f"- Sports event-velocity ETA status counts: `{summary.get('sports_event_velocity_eta_status_counts')}`",
        f"- Sports event-velocity bottleneck counts: `{summary.get('sports_event_velocity_bottleneck_type_counts')}`",
        f"- Sports event-velocity next due surface: `{summary.get('sports_event_velocity_next_due_surface')}`",
        f"- Sports event-velocity next probe surface: `{summary.get('sports_event_velocity_next_probe_surface')}`",
        f"- Sports consensus rule/bucket ETA model: `{summary.get('sports_event_velocity_consensus_rule_bucket_model_id')}`",
        f"- Sports consensus rule/bucket OOS: `{summary.get('sports_event_velocity_consensus_rule_bucket_oos_label_count')}`",
        f"- Sports consensus rule/bucket OOS deficit: `{summary.get('sports_event_velocity_consensus_rule_bucket_oos_deficit')}`",
        f"- Sports consensus rule/bucket opportunities: `{summary.get('sports_event_velocity_consensus_rule_bucket_opportunity_count')}`",
        f"- Sports consensus rule/bucket nearest opportunities: `{summary.get('sports_event_velocity_consensus_rule_bucket_nearest_opportunity_count')}`",
        f"- Sports consensus rule/bucket next probe: `{summary.get('sports_event_velocity_consensus_rule_bucket_next_probe_utc')}`",
        f"- Sports consensus rule/bucket ETA days: `{summary.get('sports_event_velocity_consensus_rule_bucket_eta_days')}`",
        f"- World Cup outcome independence: `{summary.get('world_cup_outcome_independence_status')}`",
        f"- World Cup exact-contract labels: `{summary.get('world_cup_outcome_exact_contract_label_count')}`",
        f"- World Cup outcome-family clocks: `{summary.get('world_cup_outcome_family_label_count')}`",
        f"- World Cup match clusters: `{summary.get('world_cup_outcome_match_cluster_count')}`",
        f"- World Cup candidate independence review: `{summary.get('world_cup_outcome_candidate_independence_requires_review')}`",
        f"- Live eligible: `{summary.get('live_eligible_count')}`",
        "",
        "| Surface | Status | Observations | Labels | Proxy | Paper fills | Due | Blocker |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("surface_rows", []):
        if isinstance(row, Mapping):
            lines.append(
                "| "
                f"`{row.get('surface_id')}` | "
                f"`{row.get('artifact_status')}` | "
                f"`{row.get('observation_count')}` | "
                f"`{row.get('label_count')}` | "
                f"`{row.get('proxy_label_count')}` | "
                f"`{row.get('paper_fill_label_count')}` | "
                f"`{row.get('due_count')}` | "
                f"{row.get('blocked_reason')} |"
            )
    lines.extend(
        [
            "",
            "> **Research-only summary.** No probability, stake, order, or account action is computed or implied by this report.",
            "> All safety flags are disabled: `execution_enabled=false`, `market_execution=false`, `account_or_order_paths=false`.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_sports_evidence_cycle_report()
    if args.write:
        paths = write_outputs(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
