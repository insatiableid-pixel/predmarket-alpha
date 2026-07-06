#!/usr/bin/env python3
"""Sequence sports and adjacent Kalshi lanes by current evidence leverage.

This is a control-plane artifact. It does not merge sports into one feature
bucket. It ranks which already-specific family pipelines should be run first
and records that adaptation is at the output/gate layer, not the feature layer.
"""

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

from predmarket.kalshi_universe_scan import DEFAULT_WORLD_CUP_SOCCER_SERIES  # noqa: E402
from predmarket.shared_helpers import (  # noqa: E402
    counts,
    read_json_or_empty,
    safe_research_artifact,
    safety_flags,
    sha256_or_none,
    timestamp,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_UNIVERSE_SCAN_PATH = MACRO_DIR / "latest-kalshi-universe-scan.json"
DEFAULT_WORLD_CUP_OBSERVATION_PATH = (
    MACRO_DIR / "latest-kalshi-world-cup-proxy-observation-loop.json"
)
DEFAULT_WORLD_CUP_MODEL_PATH = (
    MACRO_DIR / "latest-kalshi-world-cup-proxy-feature-model-falsification.json"
)
DEFAULT_MLB_OBSERVATION_PATH = MACRO_DIR / "latest-kalshi-sports-proxy-observation-loop.json"
DEFAULT_MLB_MODEL_PATH = MACRO_DIR / "latest-kalshi-sports-proxy-feature-model-falsification.json"
DEFAULT_MLB_REPLAY_PATH = MACRO_DIR / "latest-kalshi-sports-proxy-research-candidate-replay.json"
DEFAULT_MLB_CCD_PATH = MACRO_DIR / "latest-kalshi-sports-proxy-capacity-correlation-decay.json"
DEFAULT_MLB_CLUSTER_PATH = MACRO_DIR / "latest-kalshi-sports-proxy-correlation-cluster-control.json"
DEFAULT_ATP_OBSERVATION_PATH = MACRO_DIR / "latest-kalshi-atp-proxy-observation-loop.json"
DEFAULT_ATP_EVIDENCE_PATH = MACRO_DIR / "latest-kalshi-atp-proxy-evidence-gate.json"
DEFAULT_GHOST_DEPTH_PATH = MACRO_DIR / "latest-kalshi-ghost-listing-depth-diagnostic.json"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-stack-sequencing-latest"
DEFAULT_MAX_PAPER_BLOCKER_ROWS_PER_SURFACE = 30
WORLD_CUP_SERIES = frozenset(DEFAULT_WORLD_CUP_SOCCER_SERIES)

CSV_FIELDS = [
    "surface_id",
    "priority",
    "timeframe",
    "active_candidate_count",
    "recommended_target",
    "sequence_status",
    "adaptation_layer",
    "feature_layer_action",
    "cap_i_lock_state",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_sports_stack_sequencing(
    *,
    universe_scan_path: Path = DEFAULT_UNIVERSE_SCAN_PATH,
    world_cup_observation_path: Path = DEFAULT_WORLD_CUP_OBSERVATION_PATH,
    world_cup_model_path: Path = DEFAULT_WORLD_CUP_MODEL_PATH,
    mlb_observation_path: Path = DEFAULT_MLB_OBSERVATION_PATH,
    mlb_model_path: Path = DEFAULT_MLB_MODEL_PATH,
    mlb_replay_path: Path = DEFAULT_MLB_REPLAY_PATH,
    mlb_ccd_path: Path = DEFAULT_MLB_CCD_PATH,
    mlb_cluster_path: Path = DEFAULT_MLB_CLUSTER_PATH,
    atp_observation_path: Path = DEFAULT_ATP_OBSERVATION_PATH,
    atp_evidence_path: Path = DEFAULT_ATP_EVIDENCE_PATH,
    ghost_depth_path: Path = DEFAULT_GHOST_DEPTH_PATH,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    generated_ts = timestamp(generated) or 0.0
    universe = read_json_or_empty(universe_scan_path)
    artifacts = {
        "world_cup_observation": load_artifact(world_cup_observation_path),
        "world_cup_model": load_artifact(world_cup_model_path),
        "mlb_observation": load_artifact(mlb_observation_path),
        "mlb_model": load_artifact(mlb_model_path),
        "mlb_replay": load_artifact(mlb_replay_path),
        "mlb_ccd": load_artifact(mlb_ccd_path),
        "mlb_cluster": load_artifact(mlb_cluster_path),
        "atp_observation": load_artifact(atp_observation_path),
        "atp_evidence": load_artifact(atp_evidence_path),
        "ghost_depth": load_artifact(ghost_depth_path),
    }
    candidates = current_candidates(universe, generated_ts=generated_ts)
    candidate_counts = surface_candidate_counts(candidates)
    ghost = artifacts["ghost_depth"]["payload"]
    ghost_safe = safe_research_artifact(ghost)
    ghost_ready = (
        ghost_safe
        and ghost.get("status") == "ghost_listing_depth_diagnostic_current_depth_ready"
        and ghost.get("summary", {}).get("cap_i_lock_allowed") is True
    )
    cap_i_lock_state = (
        "current_depth_passed"
        if ghost_ready
        else "blocked_until_ghost_listing_depth_diagnostic_passes"
    )
    rows = sequence_rows(
        candidate_counts=candidate_counts,
        artifacts=artifacts,
        cap_i_lock_state=cap_i_lock_state,
    )
    gates = build_gates(
        rows=rows,
        candidate_counts=candidate_counts,
        ghost_safe=ghost_safe,
        ghost_ready=ghost_ready,
    )
    status = report_status(rows=rows, ghost_ready=ghost_ready)
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
        "policy": {
            "sequencing": "Current World Cup/FIFA and MLB lanes first, then ATP/NFL/NBA by season and evidence readiness.",
            "adaptation_boundary": "Sports share output-layer gates; feature layers remain family-specific.",
            "cap_i_boundary": "Do not lock cap_i until the current ghost-listing depth diagnostic passes.",
            "medium_term": "Near-resolution informed flow and passive liquidity provision are separate falsification-gated families.",
            "long_term": "Economics and politics stay in accumulation mode until resolved base rates are large enough.",
        },
        "inputs": artifact_inputs(
            universe_scan_path=universe_scan_path,
            world_cup_observation_path=world_cup_observation_path,
            world_cup_model_path=world_cup_model_path,
            mlb_observation_path=mlb_observation_path,
            mlb_model_path=mlb_model_path,
            mlb_replay_path=mlb_replay_path,
            mlb_ccd_path=mlb_ccd_path,
            mlb_cluster_path=mlb_cluster_path,
            atp_observation_path=atp_observation_path,
            atp_evidence_path=atp_evidence_path,
            ghost_depth_path=ghost_depth_path,
            artifacts=artifacts,
        ),
        "summary": build_summary(
            rows=rows,
            candidates=candidates,
            candidate_counts=candidate_counts,
            ghost=ghost,
            ghost_safe=ghost_safe,
            ghost_ready=ghost_ready,
        ),
        "sequence_rows": rows,
        "paper_decision_blocker_rows": paper_decision_blocker_rows(
            candidates=candidates,
            sequence_rows=rows,
            artifacts=artifacts,
            generated_utc=generated,
        ),
        "medium_term_families": medium_term_families(),
        "long_term_accumulation": long_term_accumulation(candidate_counts),
        "gates": gates,
        "next_action": next_action(status),
        "safety": safety_flags(),
    }


def load_artifact(path: Path) -> dict[str, Any]:
    payload = read_json_or_empty(path)
    return {
        "path": str(path),
        "sha256": sha256_or_none(path),
        "exists": path.is_file(),
        "safe": safe_research_artifact(payload),
        "status": payload.get("status"),
        "payload": payload,
    }


def current_candidates(universe: Mapping[str, Any], *, generated_ts: float) -> list[dict[str, Any]]:
    raw = universe.get("candidates", []) if isinstance(universe.get("candidates"), list) else []
    output: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("gate_status") or "") not in {"pass", "warn"}:
            continue
        due_ts = timestamp(row.get("settlement_time") or row.get("close_time"))
        if due_ts is not None and due_ts <= generated_ts:
            continue
        output.append(dict(row))
    return output


def surface_candidate_counts(candidates: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in candidates:
        surface = candidate_surface_id(row)
        if surface:
            counter[surface] += 1
        elif str(row.get("classification") or "") == "other_sports":
            counter["other_sports_non_world_cup"] += 1
    return dict(sorted(counter.items(), key=lambda item: item[0]))


def candidate_surface_id(row: Mapping[str, Any]) -> str | None:
    classification = str(row.get("classification") or "unknown")
    series = str(row.get("series_ticker") or "").upper()
    if classification == "other_sports" and series in WORLD_CUP_SERIES:
        return "world_cup_soccer"
    if classification in {"mlb", "atp", "nfl", "nba", "macro_econ", "politics_policy"}:
        return classification
    return None


def sequence_rows(
    *,
    candidate_counts: Mapping[str, int],
    artifacts: Mapping[str, Mapping[str, Any]],
    cap_i_lock_state: str,
) -> list[dict[str, Any]]:
    rows = [
        sports_row(
            surface_id="world_cup_soccer",
            priority=100 if candidate_counts.get("world_cup_soccer", 0) else 60,
            timeframe="near_term",
            active_candidate_count=candidate_counts.get("world_cup_soccer", 0),
            recommended_target="kalshi-world-cup-proxy-observation-watch-once",
            evidence_artifacts=("world_cup_observation", "world_cup_model"),
            artifacts=artifacts,
            sequence_status="active_live_volume_first",
            feature_layer_action="Use World Cup/FIFA market-structure evidence; do not borrow MLB/ATP/NFL/NBA features.",
            cap_i_lock_state=cap_i_lock_state,
        ),
        sports_row(
            surface_id="mlb",
            priority=90 if candidate_counts.get("mlb", 0) else 50,
            timeframe="near_term",
            active_candidate_count=candidate_counts.get("mlb", 0),
            recommended_target="kalshi-sports-proxy-observation-watch-once",
            evidence_artifacts=(
                "mlb_observation",
                "mlb_model",
                "mlb_replay",
                "mlb_ccd",
                "mlb_cluster",
            ),
            artifacts=artifacts,
            sequence_status="mid_season_second",
            feature_layer_action="Use MLB/baseball feature model and settlement evidence only.",
            cap_i_lock_state=cap_i_lock_state,
        ),
        sports_row(
            surface_id="atp",
            priority=78 if candidate_counts.get("atp", 0) else 45,
            timeframe="near_term",
            active_candidate_count=candidate_counts.get("atp", 0),
            recommended_target="kalshi-atp-proxy-observation-watch-once",
            evidence_artifacts=("atp_observation", "atp_evidence"),
            artifacts=artifacts,
            sequence_status="active_if_tennis_markets_present",
            feature_layer_action="Use ATP-oracle donor/evidence outputs only; no generic sports feature reuse.",
            cap_i_lock_state=cap_i_lock_state,
        ),
        sports_row(
            surface_id="nfl",
            priority=55 if candidate_counts.get("nfl", 0) else 40,
            timeframe="near_term_preseason_watch",
            active_candidate_count=candidate_counts.get("nfl", 0),
            recommended_target="kalshi-ev-nfl-overlay-assembler",
            evidence_artifacts=(),
            artifacts=artifacts,
            sequence_status="preseason_soon_bridge_ready",
            feature_layer_action="Prepare NFL feature donor bridge now; wait for preseason liquidity.",
            cap_i_lock_state=cap_i_lock_state,
        ),
        sports_row(
            surface_id="nba",
            priority=25,
            timeframe="offseason_low_liquidity",
            active_candidate_count=candidate_counts.get("nba", 0),
            recommended_target="kalshi-external-artifact-preflight",
            evidence_artifacts=(),
            artifacts=artifacts,
            sequence_status="deprioritized_until_fall_liquidity",
            feature_layer_action="Keep NBA feature donor bridge/output mapping warm; avoid offseason props as core flow.",
            cap_i_lock_state=cap_i_lock_state,
        ),
    ]
    rows.sort(key=lambda row: (-int(row["priority"]), row["surface_id"]))
    return rows


def sports_row(
    *,
    surface_id: str,
    priority: int,
    timeframe: str,
    active_candidate_count: int,
    recommended_target: str,
    evidence_artifacts: Sequence[str],
    artifacts: Mapping[str, Mapping[str, Any]],
    sequence_status: str,
    feature_layer_action: str,
    cap_i_lock_state: str,
) -> dict[str, Any]:
    evidence = [dict(artifacts[key]) for key in evidence_artifacts if key in artifacts]
    return {
        "surface_id": surface_id,
        "priority": priority,
        "timeframe": timeframe,
        "active_candidate_count": active_candidate_count,
        "recommended_target": recommended_target,
        "sequence_status": sequence_status,
        "adaptation_layer": "output_layer_only",
        "feature_layer_action": feature_layer_action,
        "evidence_artifacts": evidence,
        "evidence_statuses": [item.get("status") for item in evidence],
        "cap_i_lock_state": cap_i_lock_state,
        "research_only": True,
        "execution_enabled": False,
        "usable": False,
    }


def paper_decision_blocker_rows(
    *,
    candidates: Sequence[Mapping[str, Any]],
    sequence_rows: Sequence[Mapping[str, Any]],
    artifacts: Mapping[str, Mapping[str, Any]],
    generated_utc: str,
    max_per_surface: int = DEFAULT_MAX_PAPER_BLOCKER_ROWS_PER_SURFACE,
) -> list[dict[str, Any]]:
    ordered_surfaces = [
        str(row.get("surface_id") or "")
        for row in sequence_rows
        if str(row.get("timeframe") or "").startswith("near_term")
    ]
    sequence_by_surface = {
        str(row.get("surface_id") or ""): row
        for row in sequence_rows
        if str(row.get("surface_id") or "")
    }
    grouped: dict[str, list[dict[str, Any]]] = {surface: [] for surface in ordered_surfaces}
    for row in candidates:
        surface = candidate_surface_id(row)
        if surface in grouped:
            grouped[surface].append(dict(row))
    output: list[dict[str, Any]] = []
    for surface in ordered_surfaces:
        surface_rows = sorted(grouped.get(surface, []), key=paper_blocker_sort_key)
        for index, row in enumerate(surface_rows[: max(0, max_per_surface)]):
            output.append(
                paper_blocker_row(
                    row,
                    surface_id=surface,
                    sequence_row=sequence_by_surface.get(surface, {}),
                    artifacts=artifacts,
                    generated_utc=generated_utc,
                    source_row_index=index,
                )
            )
    return output


def paper_blocker_family_id(surface_id: str) -> str:
    """Map surface_id to paper-usable family_id for VAL-PAPER-001 prefix compliance."""
    return {"mlb": "mlb_sports", "atp": "atp_tennis"}.get(surface_id, surface_id)


def paper_blocker_row(
    row: Mapping[str, Any],
    *,
    surface_id: str,
    sequence_row: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
    generated_utc: str,
    source_row_index: int,
) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "")
    close_time = str(
        row.get("settlement_time")
        or row.get("expected_expiration_time")
        or row.get("close_time")
        or ""
    )
    return {
        "contract_ticker": ticker,
        "event_ticker": row.get("event_ticker"),
        "side": "yes",
        "family_id": paper_blocker_family_id(surface_id),
        "surface_id": surface_id,
        "source_repo_id": "predmarket-alpha",
        "source_artifact": "kalshi-sports-stack-sequencing",
        "source_row_index": source_row_index,
        "model_id": f"{surface_id}_sports_gate_chain",
        "signal_formula_key": f"{surface_id}_mechanical_gate_evidence",
        "cluster_key": sports_cluster_key(row, surface_id=surface_id),
        "correlation_cluster_key": sports_cluster_key(row, surface_id=surface_id),
        "decision_time": generated_utc,
        "close_time": close_time or None,
        "close_bucket": close_bucket(close_time),
        "market_probability": probability_from_quotes(row),
        "calibrated_probability": None,
        "all_in_cost": None,
        "expected_value_per_contract": None,
        "capacity_estimate": None,
        "decay_status": "blocked",
        "gate_status": "blocked",
        "usable": False,
        "research_only": True,
        "execution_enabled": False,
        "blocker_list": surface_blockers(
            surface_id=surface_id,
            sequence_row=sequence_row,
            artifacts=artifacts,
        ),
    }


def surface_blockers(
    *,
    surface_id: str,
    sequence_row: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    if sequence_row.get("cap_i_lock_state") != "current_depth_passed":
        blockers.append("current-depth cap_i preflight has not passed")
    if surface_id == "world_cup_soccer":
        blockers.extend(artifact_blockers(("world_cup_observation", "world_cup_model"), artifacts))
        blockers.append("World Cup replay/capacity/cluster/decay adapters have not passed")
    elif surface_id == "mlb":
        blockers.extend(
            artifact_blockers(
                ("mlb_observation", "mlb_model", "mlb_replay", "mlb_ccd", "mlb_cluster"),
                artifacts,
            )
        )
    elif surface_id == "atp":
        blockers.extend(artifact_blockers(("atp_observation", "atp_evidence"), artifacts))
        blockers.append("ATP falsification/replay/capacity/cluster/decay adapters have not passed")
    elif surface_id == "nfl":
        blockers.append("NFL is preseason watch-only until current markets and labels are due")
    elif surface_id == "nba":
        blockers.append("NBA is offseason low-liquidity watch-only")
    else:
        blockers.append("sports surface has not passed the full paper promotion chain")
    blockers.append("sports gate evidence has not passed EV ledger promotion")
    return list(dict.fromkeys(blockers))


def artifact_blockers(keys: Sequence[str], artifacts: Mapping[str, Mapping[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for key in keys:
        artifact = artifacts.get(key, {})
        status = str(artifact.get("status") or "missing")
        safe = artifact.get("safe") is True
        if not safe:
            blockers.append(f"{key} artifact is missing or unsafe")
        if not status_ready(status):
            blockers.append(f"{key} status is {status}")
    return blockers


def status_ready(status: str) -> bool:
    text = status.lower()
    return (
        text.endswith("_ready_for_paper_overlay")
        or text.endswith("_ready_with_research_candidates")
        or text.endswith("_ready_for_falsification")
        or text == "ready"
    )


def paper_blocker_sort_key(row: Mapping[str, Any]) -> tuple[float, str]:
    return (
        float(row.get("time_to_settlement_hours") or row.get("time_to_close_hours") or 999999.0),
        str(row.get("ticker") or ""),
    )


def sports_cluster_key(row: Mapping[str, Any], *, surface_id: str) -> str:
    event = str(row.get("event_ticker") or str(row.get("ticker") or "").rsplit("-", maxsplit=1)[0])
    return "|".join([surface_id, event, close_bucket(str(row.get("settlement_time") or ""))])


def close_bucket(value: str) -> str:
    return value[:16] + "Z" if len(value) >= 16 else ""


def probability_from_quotes(row: Mapping[str, Any]) -> float | None:
    bid = as_probability(row.get("yes_bid"))
    ask = as_probability(row.get("yes_ask"))
    if bid is not None and ask is not None:
        return round((bid + ask) / 2.0, 6)
    return ask if ask is not None else bid


def as_probability(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0.0 <= number <= 1.0 else None


def medium_term_families() -> list[dict[str, Any]]:
    return [
        {
            "family_id": "near_resolution_informed_flow",
            "timeframe": "medium_term",
            "acceptance_metric": "pre_close_flow_lead_lag_survival",
            "acceptance_criteria": (
                "OOS/FDR evidence that near-resolution order flow or quote imbalance predicts "
                "subsequent price movement or settlement after fees and stale-source filters."
            ),
            "graded_against": "flow_specific_acceptance_criteria_not_directional_signal_bar",
            "required_artifacts": [
                "time-safe pre-close quote/orderbook snapshots",
                "subsequent price movement labels",
                "settlement labels",
                "cost and stale-source filters",
            ],
        },
        {
            "family_id": "passive_liquidity_provision",
            "timeframe": "medium_term",
            "acceptance_metric": "maker_fill_net_ev_after_adverse_selection",
            "acceptance_criteria": (
                "OOS/FDR evidence that passive quotes have positive net maker-fill EV after "
                "non-fill, timeout, fees, and adverse-selection costs."
            ),
            "graded_against": "maker_specific_acceptance_criteria_not_directional_signal_bar",
            "required_artifacts": [
                "queue/fill observations",
                "orderbook depth and spread snapshots",
                "timeout and non-fill labels",
                "adverse-selection cost replay",
            ],
        },
    ]


def long_term_accumulation(candidate_counts: Mapping[str, int]) -> list[dict[str, Any]]:
    return [
        {
            "surface_id": "macro_econ",
            "timeframe": "long_term",
            "active_candidate_count": candidate_counts.get("macro_econ", 0),
            "status": "base_rate_accumulation",
            "reason": "Economic releases resolve more slowly; wait for enough labeled OOS base rates.",
        },
        {
            "surface_id": "politics_policy",
            "timeframe": "long_term",
            "active_candidate_count": candidate_counts.get("politics_policy", 0),
            "status": "base_rate_accumulation",
            "reason": "Political markets resolve in quarters; do not promote before sample size exists.",
        },
    ]


def build_summary(
    *,
    rows: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    candidate_counts: Mapping[str, int],
    ghost: Mapping[str, Any],
    ghost_safe: bool,
    ghost_ready: bool,
) -> dict[str, Any]:
    near_term_count = sum(
        int(row.get("active_candidate_count") or 0)
        for row in rows
        if str(row.get("timeframe") or "").startswith("near_term")
    )
    return {
        "sports_surface_count": len(rows),
        "near_term_active_candidate_count": near_term_count,
        "candidate_count": len(candidates),
        "candidate_counts": dict(candidate_counts),
        "classification_counts": counts(row.get("classification") for row in candidates),
        "recommended_order": [row.get("surface_id") for row in rows],
        "top_surface": rows[0].get("surface_id") if rows else None,
        "all_sports_adaptation_layer": "output_layer_only",
        "ghost_depth_status": ghost.get("status"),
        "ghost_depth_safe": ghost_safe,
        "ghost_depth_ready": ghost_ready,
        "cap_i_lock_allowed": ghost_ready,
        "cap_i_lock_state": "current_depth_passed"
        if ghost_ready
        else "blocked_until_ghost_listing_depth_diagnostic_passes",
        "usable_row_count": 0,
    }


def build_gates(
    *,
    rows: Sequence[Mapping[str, Any]],
    candidate_counts: Mapping[str, int],
    ghost_safe: bool,
    ghost_ready: bool,
) -> list[dict[str, str]]:
    active_sports = sum(candidate_counts.get(key, 0) for key in ("world_cup_soccer", "mlb", "atp"))
    return [
        gate(
            "sports_surfaces_separated",
            "pass"
            if {row.get("surface_id") for row in rows}
            >= {"world_cup_soccer", "mlb", "atp", "nfl", "nba"}
            else "blocked",
            "World Cup, MLB, ATP, NFL, and NBA are separate sequencing rows.",
        ),
        gate(
            "current_sports_candidates_present",
            "pass" if active_sports > 0 else "blocked",
            f"{active_sports} active near-term World Cup/MLB/ATP candidate(s) found.",
        ),
        gate(
            "world_cup_first_when_live",
            "pass" if rows and rows[0].get("surface_id") == "world_cup_soccer" else "warn",
            "World Cup/FIFA volume is ranked first while current rows exist.",
        ),
        gate(
            "output_layer_only_adaptation",
            "pass"
            if all(row.get("adaptation_layer") == "output_layer_only" for row in rows)
            else "fail",
            "Sports adaptation is restricted to output/gate sequencing, not shared feature reuse.",
        ),
        gate(
            "ghost_listing_depth_before_cap_i",
            "pass" if ghost_ready else "blocked",
            "Current ghost-listing depth diagnostic must pass before cap_i is locked.",
        ),
        gate(
            "ghost_depth_artifact_safe",
            "pass" if ghost_safe else "blocked",
            "Ghost-depth diagnostic artifact is research-only and safe."
            if ghost_safe
            else "No safe ghost-depth diagnostic artifact is available.",
        ),
        gate(
            "medium_term_families_registered",
            "pass",
            "Near-resolution informed flow and passive liquidity provision are registered separately.",
        ),
        gate(
            "no_execution_boundary",
            "pass",
            "Sequencing artifact emits no EV, stake, account, order, or execution fields.",
        ),
    ]


def report_status(*, rows: Sequence[Mapping[str, Any]], ghost_ready: bool) -> str:
    active = sum(int(row.get("active_candidate_count") or 0) for row in rows)
    if active <= 0:
        return "sports_stack_sequencing_blocked_no_current_sports_candidates"
    if ghost_ready:
        return "sports_stack_sequencing_ready_current_depth_passed"
    return "sports_stack_sequencing_ready_cap_i_lock_blocked"


def next_action(status: str) -> dict[str, str]:
    if status == "sports_stack_sequencing_ready_current_depth_passed":
        return {
            "name": "run_world_cup_then_mlb_then_atp_gate_chain",
            "why": "Current-depth evidence is available; run family-specific evidence loops in ranked order.",
            "stop_condition": "Stop before live sizing or execution; this remains research sequencing.",
        }
    return {
        "name": "run_ghost_listing_depth_diagnostic_then_world_cup_mlb_atp",
        "why": "Sports rows exist, but capacity cannot be locked until current depth passes.",
        "stop_condition": "Stop before locking cap_i from stale or inventory-only depth.",
    }


def artifact_inputs(
    *,
    universe_scan_path: Path,
    world_cup_observation_path: Path,
    world_cup_model_path: Path,
    mlb_observation_path: Path,
    mlb_model_path: Path,
    mlb_replay_path: Path,
    mlb_ccd_path: Path,
    mlb_cluster_path: Path,
    atp_observation_path: Path,
    atp_evidence_path: Path,
    ghost_depth_path: Path,
    artifacts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    paths = {
        "universe_scan_path": universe_scan_path,
        "world_cup_observation_path": world_cup_observation_path,
        "world_cup_model_path": world_cup_model_path,
        "mlb_observation_path": mlb_observation_path,
        "mlb_model_path": mlb_model_path,
        "mlb_replay_path": mlb_replay_path,
        "mlb_ccd_path": mlb_ccd_path,
        "mlb_cluster_path": mlb_cluster_path,
        "atp_observation_path": atp_observation_path,
        "atp_evidence_path": atp_evidence_path,
        "ghost_depth_path": ghost_depth_path,
    }
    return (
        {key: str(path) for key, path in paths.items()}
        | {f"{key}_sha256": sha256_or_none(path) for key, path in paths.items()}
        | {
            "artifact_statuses": {key: value.get("status") for key, value in artifacts.items()},
            "artifact_safety": {key: value.get("safe") for key, value in artifacts.items()},
        }
    )


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def write_outputs(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-stack-sequencing.json"
    md_path = out_dir / "kalshi-sports-stack-sequencing.md"
    csv_path = out_dir / "kalshi-sports-stack-sequencing.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, csv_path)
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-sports-stack-sequencing.json"
    latest_md = MACRO_DIR / "latest-kalshi-sports-stack-sequencing.md"
    latest_csv = MACRO_DIR / "latest-kalshi-sports-stack-sequencing.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, latest_csv)
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
        "# Kalshi Sports Stack Sequencing",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Top surface: `{summary.get('top_surface')}`",
        f"- Current sports candidates: `{summary.get('near_term_active_candidate_count')}`",
        f"- cap_i lock state: `{summary.get('cap_i_lock_state')}`",
        "",
        "## Sequence",
        "",
        "| Priority | Surface | Timeframe | Active | Target | cap_i |",
        "| ---: | --- | --- | ---: | --- | --- |",
    ]
    for row in report.get("sequence_rows", []):
        if isinstance(row, Mapping):
            lines.append(
                "| "
                f"{row.get('priority')} | `{row.get('surface_id')}` | "
                f"{row.get('timeframe')} | {row.get('active_candidate_count')} | "
                f"`{row.get('recommended_target')}` | `{row.get('cap_i_lock_state')}` |"
            )
    lines.extend(
        [
            "",
            "## Medium-Term Families",
            "",
            "| Family | Metric | Grading |",
            "| --- | --- | --- |",
        ]
    )
    for family in report.get("medium_term_families", []):
        if isinstance(family, Mapping):
            lines.append(
                f"| `{family.get('family_id')}` | `{family.get('acceptance_metric')}` | "
                f"{family.get('graded_against')} |"
            )
    lines.extend(["", "## Gates", "", "| Gate | Status | Reason |", "| --- | --- | --- |"])
    for item in report.get("gates", []):
        if isinstance(item, Mapping):
            lines.append(
                f"| `{item.get('name')}` | `{item.get('status')}` | {item.get('reason')} |"
            )
    lines.extend(["", "This artifact is research-only and emits no trade instructions.", ""])
    return "\n".join(lines)


def write_csv(report: Mapping[str, Any], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in report.get("sequence_rows", []):
            if isinstance(row, Mapping):
                writer.writerow(dict(row))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-scan-path", type=Path, default=DEFAULT_UNIVERSE_SCAN_PATH)
    parser.add_argument(
        "--world-cup-observation-path", type=Path, default=DEFAULT_WORLD_CUP_OBSERVATION_PATH
    )
    parser.add_argument("--world-cup-model-path", type=Path, default=DEFAULT_WORLD_CUP_MODEL_PATH)
    parser.add_argument("--mlb-observation-path", type=Path, default=DEFAULT_MLB_OBSERVATION_PATH)
    parser.add_argument("--mlb-model-path", type=Path, default=DEFAULT_MLB_MODEL_PATH)
    parser.add_argument("--mlb-replay-path", type=Path, default=DEFAULT_MLB_REPLAY_PATH)
    parser.add_argument("--mlb-ccd-path", type=Path, default=DEFAULT_MLB_CCD_PATH)
    parser.add_argument("--mlb-cluster-path", type=Path, default=DEFAULT_MLB_CLUSTER_PATH)
    parser.add_argument("--atp-observation-path", type=Path, default=DEFAULT_ATP_OBSERVATION_PATH)
    parser.add_argument("--atp-evidence-path", type=Path, default=DEFAULT_ATP_EVIDENCE_PATH)
    parser.add_argument("--ghost-depth-path", type=Path, default=DEFAULT_GHOST_DEPTH_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_sports_stack_sequencing(
        universe_scan_path=args.universe_scan_path,
        world_cup_observation_path=args.world_cup_observation_path,
        world_cup_model_path=args.world_cup_model_path,
        mlb_observation_path=args.mlb_observation_path,
        mlb_model_path=args.mlb_model_path,
        mlb_replay_path=args.mlb_replay_path,
        mlb_ccd_path=args.mlb_ccd_path,
        mlb_cluster_path=args.mlb_cluster_path,
        atp_observation_path=args.atp_observation_path,
        atp_evidence_path=args.atp_evidence_path,
        ghost_depth_path=args.ghost_depth_path,
    )
    if args.write:
        paths = write_outputs(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
