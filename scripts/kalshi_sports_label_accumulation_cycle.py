#!/usr/bin/env python3
"""Summarize exact-label accumulation and OOS/FDR readiness for Kalshi sports.

Hardened with:
- Stronger dedup by (contract_ticker, close_time, family_id, cluster_key, source_artifact_sha256)
- Provenance on every label row (source_snapshot_sha256, probe_time_utc, settlement_payload_reference)
- Stale-observation detection with clear observation_status (waiting/blocked indicators)
- Idempotent output (running twice with unchanged inputs produces identical counts)
- Explicit blocker rows when labels/snapshots are missing or stale
"""

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
DEFAULT_MLB_OBSERVATION_PATH = MACRO_DIR / "latest-kalshi-sports-proxy-observation-loop.json"
DEFAULT_MLB_MODEL_PATH = MACRO_DIR / "latest-kalshi-sports-proxy-feature-model-falsification.json"
DEFAULT_WORLD_CUP_OBSERVATION_PATH = (
    MACRO_DIR / "latest-kalshi-world-cup-proxy-observation-loop.json"
)
DEFAULT_WORLD_CUP_MODEL_PATH = (
    MACRO_DIR / "latest-kalshi-world-cup-proxy-feature-model-falsification.json"
)
DEFAULT_ATP_OBSERVATION_PATH = MACRO_DIR / "latest-kalshi-atp-proxy-observation-loop.json"
DEFAULT_ATP_EVIDENCE_PATH = MACRO_DIR / "latest-kalshi-atp-proxy-evidence-gate.json"
DEFAULT_PAPER_PATH = MACRO_DIR / "latest-paper-decision-candidates.json"
DEFAULT_LIVE_PATH = MACRO_DIR / "latest-kalshi-live-preflight.json"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-label-accumulation-cycle-latest"

# Composite dedup key fields used to collapse duplicate label rows.
DEDUP_KEY_FIELDS = [
    "contract_ticker",
    "close_time",
    "family_id",
    "cluster_key",
    "source_artifact_sha256",
]

CSV_FIELDS = [
    "family_id",
    "status",
    "observation_count",
    "exact_label_count",
    "independent_label_count",
    "min_independent_labels",
    "label_deficit",
    "next_public_label_probe_utc",
    "oos_fdr_status",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_sports_label_accumulation_cycle(
    *,
    mlb_observation_path: Path = DEFAULT_MLB_OBSERVATION_PATH,
    mlb_model_path: Path = DEFAULT_MLB_MODEL_PATH,
    world_cup_observation_path: Path = DEFAULT_WORLD_CUP_OBSERVATION_PATH,
    world_cup_model_path: Path = DEFAULT_WORLD_CUP_MODEL_PATH,
    atp_observation_path: Path = DEFAULT_ATP_OBSERVATION_PATH,
    atp_evidence_path: Path = DEFAULT_ATP_EVIDENCE_PATH,
    paper_path: Path = DEFAULT_PAPER_PATH,
    live_path: Path = DEFAULT_LIVE_PATH,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    artifacts = {
        "mlb_observation": artifact(mlb_observation_path),
        "mlb_model": artifact(mlb_model_path),
        "world_cup_observation": artifact(world_cup_observation_path),
        "world_cup_model": artifact(world_cup_model_path),
        "atp_observation": artifact(atp_observation_path),
        "atp_evidence": artifact(atp_evidence_path),
        "paper": artifact(paper_path),
        "live": artifact(live_path, allow_blocked_live=True),
    }

    # Collect label rows from observation artifacts and assign family_id
    mlb_label_rows = collect_label_rows_from_observation(
        artifacts["mlb_observation"], family_id="mlb"
    )
    world_cup_label_rows = collect_label_rows_from_observation(
        artifacts["world_cup_observation"], family_id="world_cup_soccer"
    )
    atp_label_rows = collect_label_rows_from_observation(
        artifacts["atp_observation"], family_id="atp"
    )

    # Deduplicate label rows using strong composite key
    all_deduped = deduplicate_label_rows(
        [*mlb_label_rows, *world_cup_label_rows, *atp_label_rows]
    )

    # Group deduplicated rows by family for counting
    deduped_by_family: dict[str, list[dict[str, Any]]] = {}
    for row in all_deduped:
        fid = str(row.get("family_id") or "")
        if fid not in deduped_by_family:
            deduped_by_family[fid] = []
        deduped_by_family[fid].append(row)

    families = [
        model_family_row(
            "mlb",
            observation=artifacts["mlb_observation"],
            model=artifacts["mlb_model"],
            deduped_labels=deduped_by_family.get("mlb", []),
            generated_utc=generated,
        ),
        model_family_row(
            "world_cup_soccer",
            observation=artifacts["world_cup_observation"],
            model=artifacts["world_cup_model"],
            deduped_labels=deduped_by_family.get("world_cup_soccer", []),
            generated_utc=generated,
        ),
        atp_family_row(
            observation=artifacts["atp_observation"],
            evidence=artifacts["atp_evidence"],
            deduped_labels=deduped_by_family.get("atp", []),
            generated_utc=generated,
        ),
    ]

    # Count raw label rows from upstream (before dedup) for duplicate tracking
    all_raw_rows = [*mlb_label_rows, *world_cup_label_rows, *atp_label_rows]
    summary = build_summary(artifacts, families, all_raw_rows, all_deduped)
    gates = build_gates(artifacts, families, summary)
    status = report_status(gates, summary)

    # Build label_rows with provenance for the report
    label_rows_with_provenance = add_provenance_to_label_rows(
        all_deduped,
        observation_artifacts={
            "mlb": artifacts["mlb_observation"],
            "world_cup_soccer": artifacts["world_cup_observation"],
            "atp": artifacts["atp_observation"],
        },
    )

    report: dict[str, Any] = {
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
        "method": {
            "purpose": "Determine whether exact Kalshi settlement labels are sufficient for OOS/FDR to promote any sports family into paper sizing.",
            "exact_label_rule": "Only label rows sourced from public Kalshi settlement artifacts count as exact labels.",
            "proxy_label_boundary": "Forward quote labels and counterfactual fill proxy labels are excluded from exact-label thresholds.",
            "paper_boundary": "The report never changes thresholds, probabilities, stakes, orders, or account state.",
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
        "summary": summary,
        "family_rows": families,
        "gates": gates,
        "next_action": next_action(status, families, summary),
        "safety": safety_flags(),
        "label_rows": label_rows_with_provenance,
    }
    return report


def collect_label_rows_from_observation(
    obs_artifact: Mapping[str, Any], *, family_id: str
) -> list[dict[str, Any]]:
    """Extract label rows from an observation artifact's payload.

    Reads ``label_rows_sample`` from the payload and assigns ``family_id``
    to each row. Returns an empty list if no label rows are found.
    """
    payload = obs_artifact.get("payload", {})
    if not isinstance(payload, Mapping):
        return []
    label_rows_raw = payload.get("label_rows_sample", [])
    if not isinstance(label_rows_raw, list):
        return []
    rows: list[dict[str, Any]] = []
    for row in label_rows_raw:
        if not isinstance(row, Mapping):
            continue
        r = dict(row)
        r["family_id"] = family_id
        rows.append(r)
    return rows


def deduplicate_label_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate label rows by composite key.

    The dedup key is ``(contract_ticker, close_time, family_id, cluster_key,
    source_artifact_sha256)``.  Within each group the earliest
    ``settled_time`` (or decision_time) is kept.
    """
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        parts: list[str] = []
        for field in DEDUP_KEY_FIELDS:
            val = str(row.get(field) or "")
            parts.append(val)
        key = "|".join(parts)
        if key not in seen:
            seen[key] = dict(row)
        else:
            # Keep the one with the earlier settled_time
            existing_ts = str(seen[key].get("settled_time") or seen[key].get("decision_time") or "")
            new_ts = str(row.get("settled_time") or row.get("decision_time") or "")
            if new_ts < existing_ts:
                seen[key] = dict(row)
    return list(seen.values())


def add_provenance_to_label_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    observation_artifacts: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Add provenance fields to each deduplicated label row.

    Provenance fields added:
    - ``source_snapshot_sha256``: SHA-256 of the source observation artifact
    - ``probe_time_utc``: generated_utc of the source observation artifact
    - ``settlement_payload_reference``: reference to the settlement payload
    - ``settlement_time``: alias of ``settled_time`` if not already present
    """
    result: list[dict[str, Any]] = []
    for row in rows:
        r = dict(row)
        fid = str(row.get("family_id") or "")
        obs = observation_artifacts.get(fid, {})
        obs_payload = obs.get("payload", {}) if isinstance(obs, Mapping) else {}
        obs_gen = str(obs_payload.get("generated_utc") or obs.get("generated_utc") or "")
        obs_sha = (
            str(row.get("source_artifact_sha256") or "")
            or str(obs.get("sha256") or "")
        )
        r["source_snapshot_sha256"] = obs_sha or None
        r["probe_time_utc"] = obs_gen or r.get("decision_time") or None
        r["settlement_payload_reference"] = row.get(
            "label_source",
            row.get("settlement_result", "public_kalshi_settled_market_payload"),
        )
        # Ensure settlement_time alias from settled_time
        if r.get("settlement_time") is None and r.get("settled_time") is not None:
            r["settlement_time"] = r["settled_time"]
        result.append(r)
    return result


def detect_stale_observations(
    obs_artifact: Mapping[str, Any],
    *,
    exact_label_count: int,
    generated_utc: str,
    family_id: str,
) -> str:
    """Determine observation status with staleness detection.

    Returns one of:
    - ``"labeled"`` if exact_label_count > 0
    - ``"waiting_settlement"`` if next probe is in the future
    - ``"blocked_stale_observations"`` if probe time has passed but no labels
    - The observation artifact's status as fallback
    """
    if exact_label_count > 0:
        return "labeled"

    summary = obs_artifact.get("summary", {})
    if not isinstance(summary, Mapping):
        summary = {}

    next_probe = str(summary.get("next_public_label_probe_utc") or "")
    if not next_probe:
        # Fall back to observation status
        return str(obs_artifact.get("status") or "waiting_settlement")

    # Parse the timestamps for staleness check
    now_ts = _parse_timestamp(generated_utc)
    probe_ts = _parse_timestamp(next_probe)

    if probe_ts is not None and now_ts is not None and probe_ts <= now_ts:
        # Probe time is in the past but no labels → stale
        return "blocked_stale_observations"

    return "waiting_settlement"


def _parse_timestamp(value: str | None) -> float | None:
    """Parse an ISO-8601 timestamp to Unix timestamp."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.timestamp()
    except (ValueError, TypeError):
        return None


def artifact(path: Path, *, allow_blocked_live: bool = False) -> dict[str, Any]:
    payload = read_json_or_empty(path)
    safe = safe_research_artifact(payload)
    if allow_blocked_live:
        safe = safe or safe_blocked_live_artifact(payload)
    return {
        "path": str(path),
        "sha256": sha256_or_none(path),
        "exists": path.is_file(),
        "safe": safe,
        "status": payload.get("status"),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {},
        "generated_utc": payload.get("generated_utc") if isinstance(payload, Mapping) else None,
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


def model_family_row(
    family_id: str,
    *,
    observation: Mapping[str, Any],
    model: Mapping[str, Any],
    deduped_labels: Sequence[Mapping[str, Any]] | None = None,
    generated_utc: str = "",
) -> dict[str, Any]:
    obs = summary_of(observation)
    model_summary = summary_of(model)

    # Extract label counts from upstream model/observation summaries
    exact_labels = int_value(model_summary.get("valid_label_row_count")) or int_value(
        obs.get("label_row_count")
    )
    independent = int_value(model_summary.get("independent_contract_label_count"))
    min_independent = int_value(model_summary.get("min_independent_labels"))
    min_oos = int_value(model_summary.get("min_oos_labels"))
    research_candidates = int_value(model_summary.get("research_candidate_count"))

    # Label counts come from the model artifact which computes them from the
    # full dataset using independent_contract_rows() by contract_ticker.
    # These are authoritative.  The label_rows_sample is a subset (up to 20
    # rows) used only for display/provenance and must NOT override the model's
    # comprehensive counts.
    raw_count = int_value(model_summary.get("raw_label_row_count")) or exact_labels
    duplicate_count = int_value(model_summary.get("duplicate_label_row_count"))
    invalid_count = int_value(model_summary.get("invalid_label_row_count"))

    # Compute observation_status with staleness detection
    obs_status = detect_stale_observations(
        observation,
        exact_label_count=exact_labels,
        generated_utc=generated_utc,
        family_id=family_id,
    )

    return {
        "family_id": family_id,
        "status": family_status(
            exact_label_count=exact_labels,
            independent_label_count=independent,
            min_independent_labels=min_independent,
            research_candidate_count=research_candidates,
            model_status=str(model.get("status") or ""),
        ),
        "observation_status": obs_status,
        "oos_fdr_status": model.get("status"),
        "observation_count": int_value(obs.get("total_observation_row_count")),
        "distinct_contract_count": int_value(obs.get("distinct_contract_count")),
        "exact_label_count": exact_labels,
        "independent_label_count": independent,
        "min_independent_labels": min_independent,
        "min_oos_labels": min_oos,
        "label_deficit": max(0, min_independent - independent),
        "raw_label_count": raw_count,
        "invalid_label_count": invalid_count,
        "duplicate_label_count": duplicate_count,
        "research_candidate_count": research_candidates,
        "next_public_label_probe_utc": obs.get("next_public_label_probe_utc"),
        # Provenance fields at family row level
        "source_snapshot_sha256": observation.get("sha256"),
        "probe_time_utc": observation.get("generated_utc"),
        "settlement_payload_reference": (
            str(obs.get("label_row_count"))
            if int_value(obs.get("label_row_count")) > 0
            else "pending_kalshi_settlement"
        ),
    }


def atp_family_row(
    *,
    observation: Mapping[str, Any],
    evidence: Mapping[str, Any],
    deduped_labels: Sequence[Mapping[str, Any]] | None = None,
    generated_utc: str = "",
) -> dict[str, Any]:
    obs = summary_of(observation)
    evidence_summary = summary_of(evidence)
    exact_labels = int_value(evidence_summary.get("settled_label_count")) or int_value(
        obs.get("label_row_count")
    )
    min_labels = int_value(evidence_summary.get("min_settled_labels")) or 10

    # Note: deduped_labels (from label_rows_sample) is NOT used to override
    # counts here because the evidence/observation summaries are authoritative.
    # The sample is only used for display/provenance.

    # Compute observation_status with staleness detection
    obs_status = detect_stale_observations(
        observation,
        exact_label_count=exact_labels,
        generated_utc=generated_utc,
        family_id="atp",
    )

    return {
        "family_id": "atp",
        "status": (
            "oos_fdr_candidate_ready"
            if int_value(evidence_summary.get("research_candidate_count")) > 0
            else (
                "label_threshold_met"
                if exact_labels >= min_labels
                else "waiting_exact_labels"
            )
        ),
        "observation_status": obs_status,
        "oos_fdr_status": evidence.get("status"),
        "observation_count": int_value(obs.get("total_observation_row_count"))
        or int_value(evidence_summary.get("observation_count")),
        "distinct_contract_count": int_value(obs.get("distinct_contract_count")),
        "exact_label_count": exact_labels,
        "independent_label_count": exact_labels,
        "min_independent_labels": min_labels,
        "min_oos_labels": min_labels,
        "label_deficit": max(0, min_labels - exact_labels),
        "raw_label_count": exact_labels,
        "invalid_label_count": 0,
        "duplicate_label_count": 0,
        "research_candidate_count": int_value(
            evidence_summary.get("research_candidate_count")
        ),
        "next_public_label_probe_utc": obs.get("next_public_label_probe_utc")
        or evidence_summary.get("next_public_label_probe_utc"),
        # Provenance fields at family row level
        "source_snapshot_sha256": observation.get("sha256"),
        "probe_time_utc": observation.get("generated_utc"),
        "settlement_payload_reference": (
            str(obs.get("label_row_count"))
            if int_value(obs.get("label_row_count")) > 0
            else "pending_kalshi_settlement"
        ),
    }


def family_status(
    *,
    exact_label_count: int,
    independent_label_count: int,
    min_independent_labels: int,
    research_candidate_count: int,
    model_status: str,
) -> str:
    if research_candidate_count > 0:
        return "oos_fdr_candidate_ready"
    if independent_label_count >= min_independent_labels and min_independent_labels > 0:
        return "label_threshold_met_oos_fdr_no_candidate"
    if exact_label_count > 0:
        return "waiting_more_independent_exact_labels"
    if "missing_labels" in model_status:
        return "waiting_exact_labels"
    return "waiting_exact_labels"


def build_summary(
    artifacts: Mapping[str, Mapping[str, Any]],
    families: Sequence[Mapping[str, Any]],
    raw_label_rows: Sequence[Mapping[str, Any]] | None = None,
    deduped_label_rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    paper_summary = summary_of(artifacts["paper"])
    live_summary = summary_of(artifacts["live"])

    missing_keys = [
        key for key, item in artifacts.items() if not item.get("exists")
    ]
    unsafe_keys = [
        key for key, item in artifacts.items() if item.get("exists") and not item.get("safe")
    ]

    return {
        "safe_artifact_count": sum(1 for item in artifacts.values() if item.get("safe")),
        "artifact_count": len(artifacts),
        "missing_artifact_keys": missing_keys,
        "unsafe_artifact_keys": unsafe_keys,
        "family_count": len(families),
        "total_observation_count": sum(int(row.get("observation_count") or 0) for row in families),
        "total_exact_label_count": sum(int(row.get("exact_label_count") or 0) for row in families),
        "total_independent_label_count": sum(
            int(row.get("independent_label_count") or 0) for row in families
        ),
        "total_label_deficit": sum(int(row.get("label_deficit") or 0) for row in families),
        "total_raw_label_count": len(raw_label_rows) if raw_label_rows else None,
        "total_deduped_label_count": len(deduped_label_rows) if deduped_label_rows else None,
        "families_at_label_threshold": sum(
            1 for row in families if int(row.get("label_deficit") or 0) == 0
        ),
        "oos_fdr_candidate_family_count": sum(
            1 for row in families if int(row.get("research_candidate_count") or 0) > 0
        ),
        "paper_candidate_count": int_value(paper_summary.get("candidate_count")),
        "paper_usable_count": int_value(paper_summary.get("paper_usable_count")),
        "live_decision_count": int_value(live_summary.get("live_decision_count")),
        "live_eligible_count": int_value(live_summary.get("live_eligible_count")),
    }


def build_gates(
    artifacts: Mapping[str, Mapping[str, Any]],
    families: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> list[dict[str, str]]:
    missing = list(summary.get("missing_artifact_keys") or [])
    unsafe = list(summary.get("unsafe_artifact_keys") or [])
    return [
        gate("required_artifacts_exist", "pass" if not missing else "blocked", str(missing)),
        gate("all_existing_artifacts_safe", "pass" if not unsafe else "fail", str(unsafe)),
        gate(
            "exact_labels_present",
            "pass" if int_value(summary.get("total_exact_label_count")) > 0 else "blocked",
            f"{summary.get('total_exact_label_count')} exact public Kalshi label(s).",
        ),
        gate(
            "family_label_thresholds",
            "pass" if int_value(summary.get("total_label_deficit")) == 0 else "blocked",
            "; ".join(
                f"{row.get('family_id')} deficit={row.get('label_deficit')}"
                for row in families
            ),
        ),
        gate(
            "paper_usable_only_after_oos_fdr",
            "pass"
            if int_value(summary.get("paper_usable_count")) == 0
            or int_value(summary.get("oos_fdr_candidate_family_count")) > 0
            else "fail",
            f"{summary.get('paper_usable_count')} paper-usable row(s), {summary.get('oos_fdr_candidate_family_count')} candidate family/families.",
        ),
        gate(
            "live_eligibility_remains_blocked",
            "pass" if int_value(summary.get("live_eligible_count")) == 0 else "warn",
            f"{summary.get('live_eligible_count')} live-eligible row(s).",
        ),
    ]


def report_status(gates: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> str:
    if any(gate.get("status") == "fail" for gate in gates):
        return "sports_label_accumulation_failed_safety_gate"
    if int_value(summary.get("paper_usable_count")) > 0:
        return "sports_label_accumulation_oos_fdr_paper_candidates_ready"
    if int_value(summary.get("oos_fdr_candidate_family_count")) > 0:
        return "sports_label_accumulation_oos_fdr_research_candidates_ready"
    if int_value(summary.get("total_label_deficit")) > 0:
        return "sports_label_accumulation_waiting_more_exact_labels"
    return "sports_label_accumulation_exact_labels_ready_oos_fdr_no_candidate"


def next_action(
    status: str, families: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]
) -> dict[str, Any]:
    if status == "sports_label_accumulation_oos_fdr_paper_candidates_ready":
        return {
            "name": "kalshi_paper_sizing_audit",
            "why": "At least one OOS/FDR survivor reached paper usability; audit cost/capacity/correlation/decay before live promotion.",
            "stop_condition": "Stop before live execution unless live risk and arming gates also pass.",
        }
    if status == "sports_label_accumulation_oos_fdr_research_candidates_ready":
        return {
            "name": "kalshi_sports_replay_capacity_decay",
            "why": "OOS/FDR found a research candidate; run all-in cost replay, capacity, correlation, and decay gates.",
            "stop_condition": "Stop before paper stake if any downstream gate blocks.",
        }
    deficits = [
        {
            "family_id": row.get("family_id"),
            "label_deficit": row.get("label_deficit"),
            "next_public_label_probe_utc": row.get("next_public_label_probe_utc"),
        }
        for row in families
        if int(row.get("label_deficit") or 0) > 0
    ]
    return {
        "name": "kalshi_sports_exact_label_accumulation",
        "why": "Exact public Kalshi settlement labels remain below OOS/FDR thresholds.",
        "deficits": deficits,
        "total_label_deficit": summary.get("total_label_deficit"),
        "stop_condition": "Stop before lowering thresholds, counting duplicate contracts as independent labels, or using proxy labels as outcomes.",
    }


def summary_of(artifact: Mapping[str, Any]) -> Mapping[str, Any]:
    summary = artifact.get("summary")
    return summary if isinstance(summary, Mapping) else {}


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def write_outputs(report: Mapping[str, Any], *, out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-label-accumulation-cycle.json"
    md_path = out_dir / "kalshi-sports-label-accumulation-cycle.md"
    csv_path = out_dir / "kalshi-sports-label-accumulation-cycle.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("family_rows", []), csv_path)
    latest_json = MACRO_DIR / "latest-kalshi-sports-label-accumulation-cycle.json"
    latest_md = MACRO_DIR / "latest-kalshi-sports-label-accumulation-cycle.md"
    latest_csv = MACRO_DIR / "latest-kalshi-sports-label-accumulation-cycle.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("family_rows", []), latest_csv)
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
        "# Kalshi Sports Label Accumulation Cycle",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Exact labels: `{summary.get('total_exact_label_count')}`",
        f"- Independent labels: `{summary.get('total_independent_label_count')}`",
        f"- Total label deficit: `{summary.get('total_label_deficit')}`",
        f"- Paper usable: `{summary.get('paper_usable_count')}`",
        f"- Live eligible: `{summary.get('live_eligible_count')}`",
        f"- Missing artifacts: `{summary.get('missing_artifact_keys')}`",
        f"- Unsafe artifacts: `{summary.get('unsafe_artifact_keys')}`",
        "",
        "| Family | Status | Observations | Exact Labels | Independent | Deficit | Next Probe | OOS/FDR |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in report.get("family_rows", []):
        if isinstance(row, Mapping):
            lines.append(
                "| "
                f"`{row.get('family_id')}` | "
                f"`{row.get('status')}` | "
                f"`{row.get('observation_count')}` | "
                f"`{row.get('exact_label_count')}` | "
                f"`{row.get('independent_label_count')}` | "
                f"`{row.get('label_deficit')}` | "
                f"`{row.get('next_public_label_probe_utc')}` | "
                f"`{row.get('oos_fdr_status')}` |"
            )
    lines.extend(
        [
            "",
            "Exact labels mean public Kalshi settlement labels only. Proxy quote labels are excluded.",
            "Research-only report. No probability, paper stake, live order, or account action.",
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
    report = build_sports_label_accumulation_cycle()
    if args.write:
        paths = write_outputs(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
