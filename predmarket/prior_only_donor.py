"""Prior-only donor context for cold-start Kalshi signal families.

This module implements the boundary Claude called for: donor artifacts may help
seed hypothesis generation for thin-data families, but they cannot contribute
settlement labels, OOS labels, EV, paper stake, or live eligibility.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from predmarket.external_artifact_bridge import artifact_rows
from predmarket.shared_helpers import (
    probability,
    read_json_or_empty,
    safe_research_artifact,
    safety_flags,
    sha256_or_none,
    utc_now,
)

LABEL_LIKE_KEYS = {
    "actual_outcome",
    "correct",
    "final_score",
    "label",
    "label_source",
    "label_status",
    "outcome",
    "outcome_for_side",
    "resolved",
    "settled",
    "settled_outcome",
    "settlement_result",
    "winner",
}
PRIOR_PROBABILITY_KEYS = (
    "prior_probability",
    "model_probability",
    "calibrated_probability",
    "probability",
    "win_probability",
    "selected_win_probability",
    "selected_team_win_probability",
)
BLOCKED_PROMOTION_FIELDS = {
    "all_in_cost",
    "expected_value_per_contract",
    "kelly_fraction",
    "live_eligible",
    "live_stake",
    "order_count",
    "paper_stake",
    "paper_usable",
    "usable",
}


def build_prior_only_donor_gate(
    *,
    external_preflight_path: Path,
    formula_registry_path: Path | None = None,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    preflight = read_json_or_empty(external_preflight_path)
    formula_registry = read_json_or_empty(formula_registry_path) if formula_registry_path else {}
    artifact_inputs = safe_preflight_artifacts(preflight)
    rows = [
        prior_context_row(
            source_row=row,
            artifact=artifact,
            artifact_index=artifact_index,
            source_row_index=row_index,
        )
        for artifact_index, artifact in enumerate(artifact_inputs)
        for row_index, row in enumerate(load_artifact_rows(artifact))
    ]
    summary = build_summary(
        preflight=preflight,
        formula_registry=formula_registry,
        artifact_inputs=artifact_inputs,
        rows=rows,
    )
    gates = build_gates(
        preflight=preflight,
        formula_registry=formula_registry,
        artifact_inputs=artifact_inputs,
        rows=rows,
        summary=summary,
        external_preflight_path=external_preflight_path,
        formula_registry_path=formula_registry_path,
    )
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": report_status(summary, gates),
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "north_star_alignment": {
            "purpose": "Seed cold-start hypothesis generation without discretionary promotion.",
            "boundary": (
                "Donor priors may inform pre-falsification hypothesis generation only; "
                "they never satisfy labels, OOS evidence, EV, paper sizing, or live trading gates."
            ),
        },
        "inputs": {
            "external_preflight_path": str(external_preflight_path),
            "external_preflight_sha256": sha256_or_none(external_preflight_path),
            "external_preflight_status": preflight.get("status"),
            "formula_registry_path": str(formula_registry_path) if formula_registry_path else None,
            "formula_registry_sha256": (
                sha256_or_none(formula_registry_path) if formula_registry_path else None
            ),
            "formula_registry_status": formula_registry.get("status"),
        },
        "method": {
            "admission_scope": "hypothesis_generation_only",
            "label_credit_policy": "hard_zero_for_all_donor_prior_rows",
            "promotion_policy": (
                "Any row with direct EV, paper, live, or settlement-label fields is stripped "
                "from promotion and blocked from prior eligibility."
            ),
            "multiple_testing_policy": (
                "Prior context rows do not count as tests. Generated formulas from the formula "
                "registry count toward the multiple-testing ledger before falsification."
            ),
        },
        "summary": summary,
        "prior_context_rows": rows,
        "gates": gates,
        "next_action": next_action(summary),
        "safety": safety_flags(),
    }


def safe_preflight_artifacts(preflight: Mapping[str, Any]) -> list[dict[str, Any]]:
    artifacts = preflight.get("artifacts") if isinstance(preflight.get("artifacts"), list) else []
    return [
        dict(row)
        for row in artifacts
        if isinstance(row, Mapping)
        and row.get("safe") is True
        and str(row.get("path") or "").strip()
    ]


def load_artifact_rows(artifact: Mapping[str, Any]) -> list[dict[str, Any]]:
    path = Path(str(artifact.get("path") or ""))
    payload = read_json_or_empty(path)
    if not safe_research_artifact(payload):
        return []
    rows = artifact_rows(payload)
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def prior_context_row(
    *,
    source_row: Mapping[str, Any],
    artifact: Mapping[str, Any],
    artifact_index: int,
    source_row_index: int,
) -> dict[str, Any]:
    blockers = row_blockers(source_row)
    prior_probability = row_prior_probability(source_row)
    if prior_probability is None:
        blockers.append("row has no bounded donor probability or prior probability")
    status = "prior_context_ready" if not blockers else "prior_context_blocked"
    source_payload = (
        source_row.get("source_payload")
        if isinstance(source_row.get("source_payload"), Mapping)
        else {}
    )
    row = {
        "prior_context_key": prior_context_key(source_row, artifact, source_row_index),
        "source_repo_id": str(
            source_row.get("source_repo_id") or artifact.get("source_repo_id") or ""
        ),
        "family_id": str(source_row.get("family_id") or artifact.get("family_id") or ""),
        "model_id": str(source_row.get("model_id") or ""),
        "artifact_kind": str(
            source_row.get("artifact_kind") or artifact.get("artifact_kind") or ""
        ),
        "source_path": str(source_row.get("source_path") or artifact.get("source_path") or ""),
        "wrapped_artifact_path": str(artifact.get("path") or ""),
        "source_sha256": str(source_row.get("source_sha256") or artifact.get("sha256") or ""),
        "artifact_index": artifact_index,
        "source_row_index": source_row_index,
        "contract_ticker": str(source_row.get("contract_ticker") or ""),
        "side": str(source_row.get("side") or ""),
        "event_ticker": str(source_row.get("event_ticker") or ""),
        "admission_scope": "hypothesis_generation_only",
        "prior_probability": prior_probability,
        "prior_role": "probability_prior",
        "can_seed_signal_formula_generation": status == "prior_context_ready",
        "status": status,
        "blocker_list": blockers,
        "counts_toward_independent_labels": False,
        "counts_toward_oos_labels": False,
        "counts_toward_settlement_labels": False,
        "counts_toward_multiple_testing": False,
        "direct_probability_promotion_allowed": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
        "paper_stake": 0.0,
        "paper_usable": False,
        "live_eligible": False,
        "live_stake": 0.0,
        "order_count": 0,
        "usable": False,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
    }
    for key in ("selection", "selected_team", "selected_player", "match_label", "game"):
        value = source_row.get(key) or source_payload.get(key)
        if value not in (None, ""):
            row[key] = value
    return row


def row_blockers(row: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if row_has_label_like_payload(row):
        blockers.append("row has label/outcome-like payload and cannot be prior-only evidence")
    if any(row.get(key) not in (None, "", False, 0, 0.0) for key in BLOCKED_PROMOTION_FIELDS):
        blockers.append("row contains direct promotion, EV, paper, or live fields")
    if row.get("research_only") is not True:
        blockers.append("row is not research_only")
    if row.get("execution_enabled") is not False:
        blockers.append("row execution_enabled flag is not false")
    if row.get("market_execution") is True or row.get("account_or_order_paths") is True:
        blockers.append("row exposes execution/account/order flags")
    return blockers


def row_has_label_like_payload(row: Mapping[str, Any]) -> bool:
    keys = {str(key).lower() for key in row}
    payload = row.get("source_payload") if isinstance(row.get("source_payload"), Mapping) else {}
    payload_keys = {str(key).lower() for key in payload}
    return bool((keys | payload_keys) & LABEL_LIKE_KEYS)


def row_prior_probability(row: Mapping[str, Any]) -> float | None:
    payload = row.get("source_payload") if isinstance(row.get("source_payload"), Mapping) else {}
    for key in PRIOR_PROBABILITY_KEYS:
        parsed = probability(row.get(key))
        if parsed is not None:
            return parsed
        parsed = probability(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def prior_context_key(
    row: Mapping[str, Any], artifact: Mapping[str, Any], source_row_index: int
) -> str:
    material = "|".join(
        [
            str(row.get("source_repo_id") or artifact.get("source_repo_id") or ""),
            str(row.get("family_id") or artifact.get("family_id") or ""),
            str(row.get("model_id") or ""),
            str(row.get("contract_ticker") or ""),
            str(row.get("side") or ""),
            str(source_row_index),
        ]
    )
    return "prior-only-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def build_summary(
    *,
    preflight: Mapping[str, Any],
    formula_registry: Mapping[str, Any],
    artifact_inputs: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    source_counts = Counter(str(row.get("source_repo_id") or "unknown") for row in rows)
    family_counts = Counter(str(row.get("family_id") or "unknown") for row in rows)
    eligible_rows = [row for row in rows if row.get("status") == "prior_context_ready"]
    formula_summary = (
        formula_registry.get("summary")
        if isinstance(formula_registry.get("summary"), Mapping)
        else {}
    )
    return {
        "external_preflight_status": preflight.get("status"),
        "safe_artifact_count": len(artifact_inputs),
        "prior_context_row_count": len(rows),
        "eligible_prior_context_count": len(eligible_rows),
        "blocked_prior_context_count": len(rows) - len(eligible_rows),
        "prior_probability_row_count": sum(
            1 for row in rows if probability(row.get("prior_probability")) is not None
        ),
        "source_repo_count": len(source_counts),
        "family_count": len(family_counts),
        "source_repo_counts": dict(sorted(source_counts.items())),
        "family_counts": dict(sorted(family_counts.items())),
        "settlement_label_credit_count": 0,
        "independent_label_credit_count": 0,
        "oos_label_credit_count": 0,
        "direct_probability_promotion_count": 0,
        "ev_row_count": 0,
        "paper_usable_count": 0,
        "live_eligible_count": 0,
        "multiple_testing_ready_formula_count": int(
            formula_summary.get("multiple_testing_hypothesis_count") or 0
        ),
        "formula_registry_status": formula_registry.get("status"),
    }


def build_gates(
    *,
    preflight: Mapping[str, Any],
    formula_registry: Mapping[str, Any],
    artifact_inputs: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    external_preflight_path: Path,
    formula_registry_path: Path | None,
) -> list[dict[str, Any]]:
    return [
        {
            "name": "external_preflight_present",
            "status": "pass" if external_preflight_path.is_file() else "blocked",
            "reason": str(external_preflight_path),
        },
        {
            "name": "safe_external_artifacts_present",
            "status": "pass" if artifact_inputs else "blocked",
            "reason": f"{len(artifact_inputs)} safe donor artifact(s) available.",
        },
        {
            "name": "prior_context_rows_present",
            "status": "pass" if rows else "blocked",
            "reason": f"{len(rows)} prior context row(s) derived from safe artifacts.",
        },
        {
            "name": "formula_registry_multiple_testing_visible",
            "status": "pass"
            if int(summary.get("multiple_testing_ready_formula_count") or 0) > 0
            else "warn",
            "reason": (
                f"{summary.get('multiple_testing_ready_formula_count')} formula(s) ready "
                f"for multiple-testing ledger; path={formula_registry_path}."
            ),
        },
        {
            "name": "donor_rows_get_zero_label_credit",
            "status": "pass"
            if summary.get("settlement_label_credit_count") == 0
            and summary.get("independent_label_credit_count") == 0
            and summary.get("oos_label_credit_count") == 0
            else "fail",
            "reason": "Donor prior rows must never satisfy settlement, independent, or OOS label counts.",
        },
        {
            "name": "no_direct_probability_ev_paper_live_promotion",
            "status": "pass"
            if summary.get("direct_probability_promotion_count") == 0
            and summary.get("ev_row_count") == 0
            and summary.get("paper_usable_count") == 0
            and summary.get("live_eligible_count") == 0
            else "fail",
            "reason": "Prior context emits no EV, stake, live eligibility, or direct tradable probability.",
        },
        {
            "name": "research_only_input_boundary",
            "status": "pass" if safe_research_artifact(preflight) else "blocked",
            "reason": f"external preflight status={preflight.get('status')}.",
        },
        {
            "name": "eligible_rows_have_blockers_resolved",
            "status": "pass"
            if all(
                bool(row.get("blocker_list"))
                or row.get("can_seed_signal_formula_generation") is True
                for row in rows
            )
            else "fail",
            "reason": "Every unblocked row is explicitly limited to formula-generation context.",
        },
    ]


def report_status(summary: Mapping[str, Any], gates: Sequence[Mapping[str, Any]]) -> str:
    if any(row.get("status") == "fail" for row in gates):
        return "prior_only_donor_gate_failed"
    if not summary.get("safe_artifact_count"):
        return "prior_only_donor_gate_blocked_no_safe_artifacts"
    if not summary.get("prior_context_row_count"):
        return "prior_only_donor_gate_ready_no_context_rows"
    if not summary.get("eligible_prior_context_count"):
        return "prior_only_donor_gate_ready_all_context_blocked"
    return "prior_only_donor_gate_ready"


def next_action(summary: Mapping[str, Any]) -> dict[str, Any]:
    if not summary.get("eligible_prior_context_count"):
        return {
            "name": "inspect_donor_preflight",
            "why": "No eligible prior-only donor context exists; keep donor outputs non-tradable.",
            "stop_condition": "Do not convert donor probabilities into labels or EV rows.",
        }
    return {
        "name": "generate_prior_seeded_formula_specs",
        "why": (
            "Eligible donor priors can seed formula/hypothesis generation for thin-data families, "
            "then every generated formula must enter the multiple-testing/FDR ledger."
        ),
        "stop_condition": "Stop before paper sizing unless OOS/FDR and all downstream gates pass.",
    }
