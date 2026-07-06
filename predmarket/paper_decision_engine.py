"""Paper-autonomous decision candidates for Kalshi EV rows."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from predmarket.kalshi_execution_cost import kalshi_net_fee
from predmarket.paper_portfolio_risk import DEFAULT_MAX_CLUSTER_SHARE, build_paper_portfolio_risk
from predmarket.shared_helpers import (
    bucket_time,
    controlled_cluster_costs,
    optional_float,
    probability,
    read_json_or_empty,
    required_cluster_count,
    safe_research_artifact,
    utc_now,
)

PASS_VALUES = {"pass", "ready", "decay_survival_pass", "cluster_control_pass"}
CLEAN_TIMING = {"clean", "pregame_clean", "not_applicable"}
GENERAL_MAKER_FEE_RATE = 0.0175
GENERAL_TAKER_FEE_RATE = 0.07
DEFAULT_PAPER_BANKROLL = 10_000.0
DEFAULT_COVARIANCE_LAMBDA = 0.1
DEFAULT_WITHIN_CLUSTER_CORRELATION = 0.5
GHOST_LISTING_MAX_STALENESS_SECONDS = 3600
PORTFOLIO_CAP_CLIP_BUFFER = 0.999999


def load_ghost_listing_diagnostic(path: Path | str | None) -> dict[str, Any]:
    """Load ghost-listing depth diagnostic and return its depth row index.

    Returns empty dict if diagnostic is missing. The caller determines how
    to handle missing data (fail-open for paper research).
    """
    if path is None:
        return {}
    return read_json_or_empty(Path(path))


def build_ghost_listing_index(
    diagnostic: Mapping[str, Any],
) -> dict[str, bool]:
    """Build a {contract_ticker: ghost_listing_flag} index from the diagnostic.

    Returns empty dict if diagnostic is missing or invalid.
    """
    rows = diagnostic.get("depth_rows") if isinstance(diagnostic.get("depth_rows"), list) else []
    if not safe_research_artifact(diagnostic):
        return {}
    return {
        str(row.get("contract_ticker", "")).strip(): bool(row.get("ghost_listing_flag"))
        for row in rows
        if isinstance(row, Mapping) and str(row.get("contract_ticker", "")).strip()
    }


def check_ghost_listing_stale(diagnostic: Mapping[str, Any]) -> bool:
    """Check whether the ghost-listing diagnostic is stale.

    Returns True if stale (should block capacity locking).
    Returns False if diagnostic is missing (fail-open for paper research).
    """
    freshness = (
        diagnostic.get("freshness") if isinstance(diagnostic.get("freshness"), Mapping) else {}
    )
    generated_utc = str(freshness.get("generated_utc") or diagnostic.get("generated_utc") or "")
    if not generated_utc:
        return False
    return _diagnostic_is_stale(generated_utc)


def _diagnostic_is_stale(generated_utc: str) -> bool:
    try:
        generated_dt = datetime.fromisoformat(generated_utc.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return True
    return (datetime.now(UTC) - generated_dt).total_seconds() > GHOST_LISTING_MAX_STALENESS_SECONDS


def apply_ghost_listing_capacity_override(
    candidates: list[dict[str, Any]],
    ghost_listing_index: dict[str, bool],
) -> list[dict[str, Any]]:
    """Apply ghost-listing capacity override to paper candidates.

    Ghost-listed contracts (flagged True in index) get capacity_estimate forced
    to zero, paper_stake set to zero, and paper_usable set to False.
    Non-ghost-listed contracts keep their existing capacity_estimate.
    Missing from index (ticker not in diagnostic) → no change (fail-open).
    Capacity cap floor is 0.0.
    """
    updated: list[dict[str, Any]] = []
    for candidate in candidates:
        ticker = str(candidate.get("contract_ticker", "")).strip()
        if not ticker:
            updated.append(candidate)
            continue
        is_ghost = ghost_listing_index.get(ticker)
        candidate = dict(candidate)
        candidate["ghost_listing_flag"] = bool(is_ghost) if is_ghost is not None else False
        candidate["ghost_listing_applied"] = True
        if is_ghost is True:
            candidate["capacity_estimate"] = 0.0
            candidate["paper_stake"] = 0.0
            candidate["paper_usable"] = False
        updated.append(candidate)
    return updated


@dataclass(frozen=True, slots=True)
class PaperDecisionCandidate:
    contract_ticker: str
    side: str
    family_id: str
    model_id: str
    signal_key: str
    signal_formula_key: str
    calibrated_probability: float | None
    market_probability: float | None
    all_in_cost: float | None
    expected_value_per_contract: float | None
    capacity_estimate: float | None
    cluster_key: str
    decay_status: str
    kelly_fraction: float
    paper_stake: float
    blocker_list: tuple[str, ...]
    net_fee: float | None = None
    fee_mode: str = "maker"
    source_repo_id: str | None = None
    decision_time: str | None = None
    close_time: str | None = None
    close_bucket: str | None = None
    predicted_outcome: int | None = None
    settled_outcome: object | None = None

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["blocker_list"] = list(self.blocker_list)
        row["paper_usable"] = not self.blocker_list and self.paper_stake > 0
        row["research_only"] = True
        row["execution_enabled"] = False
        row["market_execution"] = False
        row["account_or_order_paths"] = False
        return row


def compute_covariance_penalty(
    stakes: Sequence[float],
    cluster_keys: Sequence[str],
    *,
    lambda_penalty: float = DEFAULT_COVARIANCE_LAMBDA,
    within_cluster_correlation: float = DEFAULT_WITHIN_CLUSTER_CORRELATION,
    normalization_base: float | None = DEFAULT_PAPER_BANKROLL,
) -> list[float]:
    """Compute per-position covariance penalty from cluster correlation data.

    Penalty reduces allocation for positions sharing a correlation cluster.
    Stakes are dollar costs, so the correlation term must use exposure fractions:
    penalty_i = lambda x rho x stake_i x (sum_{j!=i, same cluster} stake_j / bankroll)

    Single-position portfolios, missing cluster_keys, and clusters with
    only one member get zero penalty. No penalties produce negative stakes.
    """
    if lambda_penalty <= 0.0 or within_cluster_correlation <= 0.0:
        return [0.0] * len(stakes)

    n = len(stakes)
    if n <= 1:
        return [0.0] * n
    base = float(normalization_base or 0.0)
    if base <= 0.0:
        base = max(sum(max(0.0, float(stake)) for stake in stakes), 1.0)

    # Build cluster sums: total stake per non-empty cluster_key
    cluster_sums: defaultdict[str, float] = defaultdict(float)
    for stake, ck in zip(stakes, cluster_keys, strict=False):
        ck = ck.strip()
        if ck:
            cluster_sums[ck] += stake

    penalties: list[float] = []
    for stake, ck in zip(stakes, cluster_keys, strict=False):
        ck = ck.strip()
        if not ck:
            penalties.append(0.0)
            continue
        total = cluster_sums.get(ck, 0.0)
        other_stakes = total - stake
        if other_stakes <= 0.0:
            penalties.append(0.0)
        else:
            penalty = lambda_penalty * within_cluster_correlation * stake * (other_stakes / base)
            penalties.append(max(0.0, penalty))

    return penalties


def build_paper_decision_candidates(
    *,
    ledger_path: Path,
    retirement_ledger: Mapping[str, Any] | None = None,
    gate_evidence_paths: Sequence[Path] | None = None,
    ghost_depth_path: Path | str | None = None,
    generated_utc: str | None = None,
    paper_bankroll: float = 10_000.0,
    kelly_fraction: float = 0.25,
    max_fraction_per_contract: float = 0.02,
    max_cluster_share: float = DEFAULT_MAX_CLUSTER_SHARE,
    enforce_portfolio_caps: bool = False,
    covariance_penalty_lambda: float = DEFAULT_COVARIANCE_LAMBDA,
    within_cluster_correlation: float = DEFAULT_WITHIN_CLUSTER_CORRELATION,
) -> dict[str, Any]:
    ledger = read_json_or_empty(Path(ledger_path))
    rows = ledger.get("rows") if isinstance(ledger.get("rows"), list) else []
    retired = retired_signal_keys(retirement_ledger or {})

    # ── Load ghost-listing diagnostic ─────────────────────────────────
    ghost_diagnostic = load_ghost_listing_diagnostic(ghost_depth_path)
    ghost_index = build_ghost_listing_index(ghost_diagnostic)
    ghost_stale = check_ghost_listing_stale(ghost_diagnostic) if ghost_index else False
    ghost_diagnostic_version = ghost_diagnostic.get("schema_version") if ghost_diagnostic else None
    ghost_diagnostic_generated_utc = (
        ghost_diagnostic.get("generated_utc") if ghost_diagnostic else None
    )

    candidates = [
        candidate_from_ledger_row(
            row,
            retired_signal_keys=retired,
            paper_bankroll=paper_bankroll,
            kelly_fraction=kelly_fraction,
            max_fraction_per_contract=max_fraction_per_contract,
        ).to_row()
        for row in rows
        if isinstance(row, Mapping)
    ]
    gate_evidence_rows = load_gate_evidence_rows(gate_evidence_paths or ())
    candidates.extend(
        candidate_from_gate_evidence_row(row, retired_signal_keys=retired).to_row()
        for row in gate_evidence_rows
    )

    # ── Apply ghost-listing capacity override ─────────────────────────
    if ghost_index:
        candidates = apply_ghost_listing_capacity_override(candidates, ghost_index)

    # Add ghost-listing provenance to all candidates (don't overwrite override flags)
    for candidate in candidates:
        if "ghost_listing_applied" not in candidate or not candidate.get("ghost_listing_applied"):
            ticker = str(candidate.get("contract_ticker", "")).strip()
            candidate["ghost_listing_flag"] = (
                ghost_index.get(ticker, False) if ghost_index else False
            )
            candidate["ghost_listing_applied"] = bool(ghost_index)
        candidate["ghost_listing_diagnostic_version"] = ghost_diagnostic_version
        candidate["ghost_listing_diagnostic_generated_utc"] = ghost_diagnostic_generated_utc

    paper_usable_count = sum(1 for row in candidates if row["paper_usable"])
    max_contract_stake = paper_bankroll * max(0.0, max_fraction_per_contract)

    # ── Apply covariance penalty ──────────────────────────────────────
    if (
        covariance_penalty_lambda > 0.0
        and within_cluster_correlation > 0.0
        and paper_usable_count > 0
    ):
        usable_indices = [i for i, row in enumerate(candidates) if row["paper_usable"]]
        usable_stakes = [candidates[i]["paper_stake"] for i in usable_indices]
        usable_cluster_keys = [str(candidates[i].get("cluster_key", "")) for i in usable_indices]
        penalties = compute_covariance_penalty(
            usable_stakes,
            usable_cluster_keys,
            lambda_penalty=covariance_penalty_lambda,
            within_cluster_correlation=within_cluster_correlation,
            normalization_base=paper_bankroll,
        )
        for idx, penalty in zip(usable_indices, penalties, strict=False):
            old_stake = candidates[idx]["paper_stake"]
            new_stake = max(0.0, old_stake - penalty)
            candidates[idx]["paper_stake"] = round(new_stake, 6)
            candidates[idx]["covariance_penalty"] = round(penalty, 6)
            if new_stake <= 0.0:
                existing = [
                    str(item)
                    for item in candidates[idx].get("blocker_list") or []
                    if str(item).strip()
                ]
                candidates[idx]["blocker_list"] = list(
                    dict.fromkeys(
                        [
                            *existing,
                            (
                                "covariance penalty reduced paper stake to zero: "
                                f"old_stake={old_stake} penalty={round(penalty, 6)}"
                            ),
                        ]
                    )
                )
                candidates[idx]["kelly_fraction"] = 0.0
                candidates[idx]["paper_usable"] = False

    # Recompute paper_usable_count after ghost-listing + covariance penalty
    paper_usable_count = sum(1 for row in candidates if row["paper_usable"])

    pre_enforcement_portfolio_risk = build_paper_portfolio_risk(
        candidates,
        paper_bankroll=paper_bankroll,
        max_contract_stake=max_contract_stake,
        max_cluster_share=max_cluster_share,
    )
    portfolio_cap_enforcement_result = {
        "blocked_candidate_count": 0,
        "adjusted_candidate_count": 0,
    }
    if enforce_portfolio_caps:
        portfolio_cap_enforcement_result = enforce_paper_portfolio_caps(
            candidates,
            paper_bankroll=paper_bankroll,
            max_contract_stake=max_contract_stake,
            max_cluster_share=max_cluster_share,
        )

    paper_usable_count = sum(1 for row in candidates if row["paper_usable"])
    portfolio_risk = build_paper_portfolio_risk(
        candidates,
        paper_bankroll=paper_bankroll,
        max_contract_stake=max_contract_stake,
        max_cluster_share=max_cluster_share,
    )
    status = (
        "paper_decision_candidates_ready_with_paper_sized_rows"
        if paper_usable_count
        else "paper_decision_candidates_ready_all_rows_blocked"
        if candidates
        else "paper_decision_candidates_blocked_no_ledger_rows"
    )
    return {
        "schema_version": 1,
        "generated_utc": generated_utc or utc_now(),
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "paper_sizing_enabled": True,
        "live_staking_or_sizing_guidance": False,
        "inputs": {
            "ledger_path": str(ledger_path),
            "ledger_status": ledger.get("status"),
            "retired_signal_count": len(retired),
            "gate_evidence_paths": [str(path) for path in gate_evidence_paths or ()],
            "gate_evidence_row_count": len(gate_evidence_rows),
            "ghost_depth_path": str(ghost_depth_path) if ghost_depth_path else None,
            "ghost_diagnostic_version": ghost_diagnostic_version,
            "ghost_diagnostic_generated_utc": ghost_diagnostic_generated_utc,
        },
        "policy": {
            "paper_bankroll": paper_bankroll,
            "kelly_fraction": kelly_fraction,
            "max_fraction_per_contract": max_fraction_per_contract,
            "max_cluster_share": max_cluster_share,
            "portfolio_cap_enforcement": "clip_to_caps_block_infeasible_rows"
            if enforce_portfolio_caps
            else "diagnostic_only",
            "ghost_listing_policy": "Ghost-listed contracts get capacity_estimate forced to 0. Stale diagnostic blocks capacity lock.",
            "nonzero_paper_stake_requires": [
                "usable ledger row",
                "positive calibrated EV",
                "verified official terms",
                "pass row gate",
                "clean timing",
                "capacity gate pass",
                "correlation cluster gate pass",
                "decay gate pass",
                "paper portfolio caps pass",
                "not retired",
            ],
        },
        "summary": {
            "ledger_row_count": len(rows),
            "gate_evidence_row_count": len(gate_evidence_rows),
            "candidate_count": len(candidates),
            "paper_usable_count": paper_usable_count,
            "ghost_listing_stale": ghost_stale,
            "ghost_listing_diagnostic_version": ghost_diagnostic_version,
            "ghost_listing_diagnostic_generated_utc": ghost_diagnostic_generated_utc,
            "blocked_candidate_count": len(candidates) - paper_usable_count,
            "total_paper_stake": round(
                sum(float(row.get("paper_stake") or 0.0) for row in candidates), 6
            ),
            "paper_portfolio_cap_enforcement_enabled": enforce_portfolio_caps,
            "paper_portfolio_pre_enforcement_cap_status": pre_enforcement_portfolio_risk[
                "cap_status"
            ],
            "paper_portfolio_pre_enforcement_cap_breach_count": pre_enforcement_portfolio_risk[
                "cap_breach_count"
            ],
            "paper_portfolio_cap_blocked_candidate_count": portfolio_cap_enforcement_result[
                "blocked_candidate_count"
            ],
            "paper_portfolio_cap_adjusted_candidate_count": portfolio_cap_enforcement_result[
                "adjusted_candidate_count"
            ],
            "paper_portfolio_cap_status": portfolio_risk["cap_status"],
            "paper_portfolio_cap_breach_count": portfolio_risk["cap_breach_count"],
            "paper_portfolio_largest_cluster": portfolio_risk["largest_cluster"],
            "paper_portfolio_largest_contract": portfolio_risk["largest_contract"],
            "paper_portfolio_largest_signal": portfolio_risk["largest_signal"],
        },
        "pre_enforcement_portfolio_risk": pre_enforcement_portfolio_risk,
        "portfolio_risk": portfolio_risk,
        "candidates": candidates,
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "paper_sizing_only": True,
        },
    }


def enforce_paper_portfolio_caps(
    candidates: list[dict[str, Any]],
    *,
    paper_bankroll: float | None,
    max_contract_stake: float | None,
    max_cluster_share: float,
) -> dict[str, int]:
    """Clip feasible paper stakes to portfolio caps and block infeasible rows.

    Portfolio caps are hard constraints, not advisory diagnostics. A feasible
    multi-cluster basket should be resized into compliance; an infeasible
    basket, such as a single cluster under a 35% max-cluster-share rule, remains
    zero-stake with explicit blockers.
    """
    contract_blocked, contract_adjusted = _enforce_contract_stake_caps(
        candidates, max_contract_stake=max_contract_stake
    )
    cluster_blocked, cluster_adjusted = _enforce_cluster_share_caps(
        candidates, max_cluster_share=max_cluster_share
    )
    residual_blocked = _block_remaining_portfolio_breaches(
        candidates,
        paper_bankroll=paper_bankroll,
        max_contract_stake=max_contract_stake,
        max_cluster_share=max_cluster_share,
    )
    blocked_ids = contract_blocked | cluster_blocked | residual_blocked
    adjusted_ids = (contract_adjusted | cluster_adjusted) - blocked_ids

    return {
        "blocked_candidate_count": len(blocked_ids),
        "adjusted_candidate_count": len(adjusted_ids),
    }


def _enforce_contract_stake_caps(
    candidates: list[dict[str, Any]], *, max_contract_stake: float | None
) -> tuple[set[int], set[int]]:
    blocked_ids: set[int] = set()
    adjusted_ids: set[int] = set()
    if max_contract_stake is not None:
        for row in candidates:
            if row.get("paper_usable") is not True:
                continue
            stake = optional_float(row.get("paper_stake")) or 0.0
            if stake <= max_contract_stake:
                continue
            if max_contract_stake <= 0.0:
                _block_candidate_for_portfolio_caps(
                    row,
                    (
                        "paper portfolio max_contract_stake cap infeasible: "
                        f"{row.get('contract_ticker')} limit={max_contract_stake}",
                    ),
                )
                blocked_ids.add(id(row))
                continue
            _clip_candidate_for_portfolio_caps(
                row,
                new_stake=max_contract_stake,
                reason=(
                    "paper portfolio max_contract_stake cap clip: "
                    f"{row.get('contract_ticker')} value={stake} limit={max_contract_stake}"
                ),
            )
            adjusted_ids.add(id(row))
    return blocked_ids, adjusted_ids


def _enforce_cluster_share_caps(
    candidates: list[dict[str, Any]], *, max_cluster_share: float
) -> tuple[set[int], set[int]]:
    cluster_stakes, rows_by_cluster = _usable_cluster_stakes(candidates)
    if not cluster_stakes:
        return set(), set()
    if len(cluster_stakes) < required_cluster_count(max_cluster_share, 1):
        return _block_infeasible_cluster_share_rows(
            candidates,
            positive_cluster_count=len(cluster_stakes),
            max_cluster_share=max_cluster_share,
        ), set()
    controlled_stakes = controlled_cluster_costs(cluster_stakes, max_cluster_share)
    if not controlled_stakes:
        return _block_infeasible_cluster_share_rows(
            candidates,
            positive_cluster_count=len(cluster_stakes),
            max_cluster_share=max_cluster_share,
        ), set()
    return _clip_rows_to_controlled_cluster_stakes(
        cluster_stakes=cluster_stakes,
        rows_by_cluster=rows_by_cluster,
        controlled_stakes=controlled_stakes,
    )


def _usable_cluster_stakes(
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, float], dict[str, list[dict[str, Any]]]]:
    cluster_stakes: defaultdict[str, float] = defaultdict(float)
    rows_by_cluster: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        if row.get("paper_usable") is not True:
            continue
        cluster_key = _portfolio_cluster_key(row)
        stake = optional_float(row.get("paper_stake")) or 0.0
        if stake <= 0.0:
            continue
        cluster_stakes[cluster_key] += stake
        if isinstance(row, dict):
            rows_by_cluster[cluster_key].append(row)
    return dict(cluster_stakes), dict(rows_by_cluster)


def _block_infeasible_cluster_share_rows(
    candidates: list[dict[str, Any]],
    *,
    positive_cluster_count: int,
    max_cluster_share: float,
) -> set[int]:
    blocked_ids: set[int] = set()
    for row in candidates:
        if row.get("paper_usable") is not True:
            continue
        _block_candidate_for_portfolio_caps(
            row,
            (
                "paper portfolio max_cluster_share cap infeasible: "
                f"positive_clusters={positive_cluster_count} limit={max_cluster_share}",
            ),
        )
        blocked_ids.add(id(row))
    return blocked_ids


def _clip_rows_to_controlled_cluster_stakes(
    *,
    cluster_stakes: Mapping[str, float],
    rows_by_cluster: Mapping[str, Sequence[dict[str, Any]]],
    controlled_stakes: Mapping[str, float],
) -> tuple[set[int], set[int]]:
    blocked_ids: set[int] = set()
    adjusted_ids: set[int] = set()
    for cluster_key, original_cluster_stake in cluster_stakes.items():
        target_cluster_stake = controlled_stakes.get(cluster_key, 0.0)
        if original_cluster_stake <= 0.0:
            continue
        if target_cluster_stake >= original_cluster_stake:
            continue
        target_cluster_stake *= PORTFOLIO_CAP_CLIP_BUFFER
        ratio = max(0.0, min(1.0, target_cluster_stake / original_cluster_stake))
        for row in rows_by_cluster.get(cluster_key, []):
            old_stake = optional_float(row.get("paper_stake")) or 0.0
            new_stake = round(old_stake * ratio, 6)
            if new_stake <= 0.0:
                _block_candidate_for_portfolio_caps(
                    row,
                    (
                        "paper portfolio max_cluster_share cap clipped stake to zero: "
                        f"{cluster_key} ratio={round(ratio, 10)}",
                    ),
                )
                blocked_ids.add(id(row))
                continue
            _clip_candidate_for_portfolio_caps(
                row,
                new_stake=new_stake,
                reason=(
                    "paper portfolio max_cluster_share cap clip: "
                    f"{cluster_key} ratio={round(ratio, 10)}"
                ),
            )
            adjusted_ids.add(id(row))
    return blocked_ids, adjusted_ids


def _block_remaining_portfolio_breaches(
    candidates: list[dict[str, Any]],
    *,
    paper_bankroll: float | None,
    max_contract_stake: float | None,
    max_cluster_share: float,
) -> set[int]:
    """Defensive final pass: no cap breach may survive enforcement."""
    blocked_ids: set[int] = set()
    risk = build_paper_portfolio_risk(
        candidates,
        paper_bankroll=paper_bankroll,
        max_contract_stake=max_contract_stake,
        max_cluster_share=max_cluster_share,
    )
    breaches = risk.get("cap_breaches") if isinstance(risk.get("cap_breaches"), list) else []
    if breaches:
        for row in candidates:
            if row.get("paper_usable") is not True:
                continue
            blockers = _portfolio_cap_blockers_for_row(row, breaches)
            if not blockers:
                continue
            _block_candidate_for_portfolio_caps(row, blockers)
            blocked_ids.add(id(row))
    return blocked_ids


def _portfolio_cluster_key(row: Mapping[str, Any]) -> str:
    return str(row.get("cluster_key") or "unknown_cluster_key")


def _clip_candidate_for_portfolio_caps(
    row: dict[str, Any],
    *,
    new_stake: float,
    reason: str,
) -> None:
    old_stake = optional_float(row.get("paper_stake")) or 0.0
    if old_stake <= 0.0:
        _block_candidate_for_portfolio_caps(row, (reason,))
        return
    if new_stake >= old_stake:
        return
    ratio = max(0.0, new_stake / old_stake)
    row["portfolio_cap_adjusted"] = True
    row.setdefault("paper_stake_before_portfolio_cap_clip", old_stake)
    row["paper_stake"] = round(new_stake, 6)
    row["portfolio_cap_clip_ratio"] = round(ratio, 10)
    row["portfolio_cap_clip_reason"] = reason
    kelly = optional_float(row.get("kelly_fraction"))
    if kelly is not None:
        row.setdefault("kelly_fraction_before_portfolio_cap_clip", kelly)
        row["kelly_fraction"] = round(max(0.0, kelly * ratio), 10)


def _legacy_hard_block_paper_portfolio_caps(
    candidates: list[dict[str, Any]],
    *,
    paper_bankroll: float | None,
    max_contract_stake: float | None,
    max_cluster_share: float,
) -> int:
    """Historical hard-block implementation retained for audit/debug reference."""
    blocked_ids: set[int] = set()
    for _ in range(max(1, len(candidates))):
        risk = build_paper_portfolio_risk(
            candidates,
            paper_bankroll=paper_bankroll,
            max_contract_stake=max_contract_stake,
            max_cluster_share=max_cluster_share,
        )
        breaches = risk.get("cap_breaches") if isinstance(risk.get("cap_breaches"), list) else []
        if not breaches:
            break
        changed = False
        for row in candidates:
            if row.get("paper_usable") is not True:
                continue
            blockers = _portfolio_cap_blockers_for_row(row, breaches)
            if not blockers:
                continue
            _block_candidate_for_portfolio_caps(row, blockers)
            blocked_ids.add(id(row))
            changed = True
        if not changed:
            break
    return len(blocked_ids)


def _portfolio_cap_blockers_for_row(
    row: Mapping[str, Any], breaches: Sequence[Mapping[str, Any]]
) -> list[str]:
    blockers: list[str] = []
    cluster_key = str(row.get("cluster_key") or "")
    contract_ticker = str(row.get("contract_ticker") or "")
    for breach in breaches:
        cap = str(breach.get("cap") or "")
        key = str(breach.get("key") or "")
        value = breach.get("value")
        limit = breach.get("limit")
        if cap == "max_cluster_share" and key == cluster_key:
            blockers.append(
                f"paper portfolio max_cluster_share cap breach: {key} value={value} limit={limit}"
            )
        elif cap == "max_contract_stake" and key == contract_ticker:
            blockers.append(
                f"paper portfolio max_contract_stake cap breach: {key} value={value} limit={limit}"
            )
    return blockers


def _block_candidate_for_portfolio_caps(row: dict[str, Any], blockers: Sequence[str]) -> None:
    existing = [str(item) for item in row.get("blocker_list") or [] if str(item).strip()]
    row["portfolio_cap_blocked"] = True
    row["paper_stake_before_portfolio_cap_block"] = row.get("paper_stake")
    row["portfolio_cap_blockers"] = list(dict.fromkeys(str(item) for item in blockers))
    row["blocker_list"] = list(dict.fromkeys([*existing, *row["portfolio_cap_blockers"]]))
    row["kelly_fraction"] = 0.0
    row["paper_stake"] = 0.0
    row["paper_usable"] = False


def _resolve_paper_fee(
    *,
    market_probability: float | None,
    fee_mode: str | None,
    decay_rate: float | None,
    time_to_fill: float | None,
) -> tuple[str, float]:
    """Resolve effective fee_mode and compute net_fee for paper sizing.

    Maker-first is the default. Switch to taker only when
    decay_rate * time_to_fill > (taker_net_fee - maker_net_fee).
    Missing decay_rate or time_to_fill defaults to maker with no taker switch.
    """
    if market_probability is None or market_probability <= 0.0 or market_probability >= 1.0:
        return "maker", 0.0

    maker_fee = kalshi_net_fee(price=market_probability, fee_mode="maker")
    resolved_mode = "maker"
    net_fee = maker_fee

    # Check if decay justifies switching to taker
    if decay_rate is not None and time_to_fill is not None:
        if decay_rate > 0 and time_to_fill > 0:
            decay_cost = decay_rate * time_to_fill
            taker_fee = kalshi_net_fee(price=market_probability, fee_mode="taker")
            fee_diff = taker_fee - maker_fee
            if decay_cost > fee_diff:
                net_fee = taker_fee
                resolved_mode = "taker"

    # An explicit fee_mode on the row that is "taker" overrides the default
    if fee_mode is not None and fee_mode.lower().strip() == "taker":
        if resolved_mode != "taker":
            net_fee = maker_fee
            resolved_mode = "maker"

    return resolved_mode, net_fee


def candidate_from_ledger_row(
    row: Mapping[str, Any],
    *,
    retired_signal_keys: set[str],
    paper_bankroll: float,
    kelly_fraction: float,
    max_fraction_per_contract: float,
) -> PaperDecisionCandidate:
    calibrated = probability(row.get("calibrated_probability"))
    all_in_cost = probability(row.get("all_in_cost")) or probability(
        row.get("all_in_break_even_probability")
    )
    market_probability = probability(row.get("display_price")) or probability(
        row.get("executable_price")
    )
    expected_value = optional_float(row.get("expected_value_per_contract"))
    capacity = optional_float(row.get("capacity_estimate")) or optional_float(
        row.get("controlled_capacity_cost")
    )
    model_id = str(
        row.get("model_id") or row.get("calibrated_probability_source") or "unknown_model"
    )
    family_id = str(row.get("family_id") or row.get("market_type") or "unknown_family")
    signal_key = signal_key_for_row(row, family_id=family_id, model_id=model_id)

    # Fee-aware edge computation with maker/taker branching
    row_fee_mode = str(row.get("fee_mode") or "").lower().strip() or None
    raw_decay_rate = optional_float(row.get("decay_rate"))
    raw_time_to_fill = optional_float(row.get("time_to_fill"))
    resolved_fee_mode, net_fee = _resolve_paper_fee(
        market_probability=market_probability,
        fee_mode=row_fee_mode,
        decay_rate=raw_decay_rate,
        time_to_fill=raw_time_to_fill,
    )
    edge_after_fee = (
        calibrated - market_probability - net_fee
        if calibrated is not None and market_probability is not None and net_fee is not None
        else None
    )

    blockers = blockers_for_row(
        row,
        calibrated=calibrated,
        all_in_cost=all_in_cost,
        expected_value=expected_value,
        capacity=capacity,
        retired=signal_key in retired_signal_keys,
        edge_after_fee=edge_after_fee,
    )
    kelly = 0.0 if blockers else binary_contract_kelly(calibrated, all_in_cost, kelly_fraction)
    stake_cap = paper_bankroll * max(0.0, max_fraction_per_contract)
    capacity_cap = capacity if capacity is not None else stake_cap
    paper_stake = 0.0 if blockers else min(paper_bankroll * kelly, stake_cap, capacity_cap)
    close_time = (
        str(
            row.get("close_time")
            or row.get("expected_expiration_time")
            or row.get("close_time_utc")
            or ""
        )
        or None
    )
    side = str(row.get("side") or "")
    return PaperDecisionCandidate(
        contract_ticker=str(row.get("contract_ticker") or ""),
        side=side,
        family_id=family_id,
        model_id=model_id,
        signal_key=signal_key,
        signal_formula_key=str(row.get("signal_formula_key") or row.get("feature_rule") or ""),
        calibrated_probability=calibrated,
        market_probability=market_probability,
        all_in_cost=all_in_cost,
        expected_value_per_contract=expected_value,
        capacity_estimate=capacity,
        cluster_key=str(row.get("correlation_cluster_key") or row.get("cluster_key") or ""),
        decay_status=str(row.get("decay_gate_status") or row.get("decay_status") or "missing"),
        kelly_fraction=round(kelly, 10),
        paper_stake=round(paper_stake, 6),
        blocker_list=tuple(blockers),
        net_fee=net_fee,
        fee_mode=resolved_fee_mode,
        source_repo_id=str(row.get("source_repo_id") or "") or None,
        decision_time=str(row.get("decision_time") or "") or None,
        close_time=close_time,
        close_bucket=str(row.get("close_bucket") or bucket_time(close_time) or "") or None,
        predicted_outcome=(
            int(row["predicted_outcome"])
            if isinstance(row.get("predicted_outcome"), bool | int)
            else 1
            if side.lower() == "yes"
            else 0
            if side.lower() == "no"
            else None
        ),
        settled_outcome=row.get("settled_outcome")
        if "settled_outcome" in row
        else row.get("outcome"),
    )


def load_gate_evidence_rows(paths: Sequence[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        payload = read_json_or_empty(Path(path))
        if not safe_research_artifact(payload):
            continue
        if (
            payload.get("status")
            == "near_resolution_flow_replay_gates_ready_for_ev_ledger_promotion"
        ):
            continue
        raw_rows = payload.get("paper_decision_blocker_rows")
        if not isinstance(raw_rows, list):
            continue
        for index, row in enumerate(raw_rows):
            if not isinstance(row, Mapping):
                continue
            item = dict(row)
            item.setdefault("source_artifact_path", str(path))
            item.setdefault("source_artifact_row_index", index)
            rows.append(item)
    return rows


def candidate_from_gate_evidence_row(
    row: Mapping[str, Any], *, retired_signal_keys: set[str]
) -> PaperDecisionCandidate:
    family_id = str(row.get("family_id") or row.get("surface_id") or "unknown_family")
    model_id = str(row.get("model_id") or "gate_evidence_blocker")
    signal_key = signal_key_for_row(row, family_id=family_id, model_id=model_id)
    blockers = gate_evidence_blockers(row, retired=signal_key in retired_signal_keys)
    close_time = (
        str(
            row.get("close_time")
            or row.get("settlement_time")
            or row.get("expected_expiration_time")
            or ""
        )
        or None
    )
    return PaperDecisionCandidate(
        contract_ticker=str(row.get("contract_ticker") or row.get("ticker") or ""),
        side=str(row.get("side") or row.get("predicted_side") or ""),
        family_id=family_id,
        model_id=model_id,
        signal_key=signal_key,
        signal_formula_key=str(row.get("signal_formula_key") or row.get("feature_rule") or ""),
        calibrated_probability=probability(row.get("calibrated_probability")),
        market_probability=probability(row.get("market_probability")),
        all_in_cost=probability(row.get("all_in_cost")),
        expected_value_per_contract=optional_float(row.get("expected_value_per_contract")),
        capacity_estimate=optional_float(row.get("capacity_estimate")),
        cluster_key=str(row.get("correlation_cluster_key") or row.get("cluster_key") or ""),
        decay_status=str(row.get("decay_gate_status") or row.get("decay_status") or "blocked"),
        kelly_fraction=0.0,
        paper_stake=0.0,
        blocker_list=tuple(blockers),
        source_repo_id=str(row.get("source_repo_id") or "") or None,
        decision_time=str(row.get("decision_time") or "") or None,
        close_time=close_time,
        close_bucket=str(row.get("close_bucket") or bucket_time(close_time) or "") or None,
        predicted_outcome=(
            int(row["predicted_outcome"])
            if isinstance(row.get("predicted_outcome"), bool | int)
            else None
        ),
        settled_outcome=row.get("settled_outcome")
        if "settled_outcome" in row
        else row.get("outcome"),
    )


def gate_evidence_blockers(row: Mapping[str, Any], *, retired: bool) -> list[str]:
    blockers = (
        [str(item) for item in row.get("blocker_list", []) if str(item).strip()]
        if isinstance(row.get("blocker_list"), list)
        else []
    )
    if not blockers:
        blockers.append("gate evidence row has not passed EV ledger promotion")
    if row.get("usable") is True:
        blockers.append("gate evidence row cannot be paper-usable outside the EV ledger")
    if not str(row.get("contract_ticker") or row.get("ticker") or ""):
        blockers.append("exact Kalshi contract ticker missing")
    if str(row.get("side") or row.get("predicted_side") or "").lower() not in {"yes", "no"}:
        blockers.append("tradable side missing")
    if retired:
        blockers.append("signal is retired")
    return list(dict.fromkeys(blockers))


def blockers_for_row(
    row: Mapping[str, Any],
    *,
    calibrated: float | None,
    all_in_cost: float | None,
    expected_value: float | None,
    capacity: float | None,
    retired: bool,
    edge_after_fee: float | None = None,
) -> list[str]:
    blockers: list[str] = []
    checks = (
        (row.get("usable") is True, "ledger row is not usable"),
        (calibrated is not None, "calibrated probability missing"),
        (all_in_cost is not None, "all-in cost missing"),
        (expected_value is not None and expected_value > 0, "expected value is not positive"),
        (
            row.get("resolution_rule_status") == "verified_official_terms",
            "resolution rule is not verified official terms",
        ),
        (str(row.get("gate_status") or "") == "pass", "ledger gate status is not pass"),
        (str(row.get("timing_status") or "") in CLEAN_TIMING, "timing status is not clean"),
        (
            str(row.get("capacity_gate_status") or "") in PASS_VALUES,
            "capacity gate has not passed",
        ),
        (
            str(row.get("correlation_cluster_gate_status") or "") in PASS_VALUES,
            "correlation cluster gate has not passed",
        ),
        (
            str(row.get("decay_gate_status") or row.get("decay_status") or "") in PASS_VALUES,
            "decay gate has not passed",
        ),
        (capacity is not None and capacity > 0, "positive capacity estimate missing"),
        (not retired, "signal is retired"),
        (
            edge_after_fee is not None and edge_after_fee > 0,
            "edge after fees is not positive",
        ),
    )
    blockers.extend(reason for passed, reason in checks if not passed)
    return blockers


def binary_contract_kelly(
    calibrated_probability: float | None,
    all_in_cost: float | None,
    fraction: float,
) -> float:
    if calibrated_probability is None or all_in_cost is None:
        return 0.0
    if not (0.0 < all_in_cost < 1.0):
        return 0.0
    b = (1.0 - all_in_cost) / all_in_cost
    edge = calibrated_probability * (1.0 + b) - 1.0
    if edge <= 0 or b <= 0:
        return 0.0
    return max(0.0, min(1.0, edge / b * max(0.0, min(1.0, fraction))))


def retired_signal_keys(retirement_ledger: Mapping[str, Any]) -> set[str]:
    rows = (
        retirement_ledger.get("signals")
        if isinstance(retirement_ledger.get("signals"), list)
        else []
    )
    return {
        str(row.get("signal_key"))
        for row in rows
        if isinstance(row, Mapping) and row.get("retirement_status") == "retired"
    }


def signal_key_for_row(row: Mapping[str, Any], *, family_id: str, model_id: str) -> str:
    formula = str(row.get("signal_formula_key") or row.get("feature_rule") or "")
    source = str(row.get("source_repo_id") or "")
    return "|".join([family_id, model_id, formula, source])
