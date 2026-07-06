"""Portfolio-level exposure diagnostics for paper Kalshi decisions."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from predmarket.shared_helpers import optional_float

DEFAULT_MAX_CLUSTER_SHARE = 0.35


def build_paper_portfolio_risk(
    rows: Sequence[Mapping[str, Any]],
    *,
    paper_bankroll: float | None = None,
    max_contract_stake: float | None = None,
    max_cluster_share: float = DEFAULT_MAX_CLUSTER_SHARE,
) -> dict[str, Any]:
    usable = [row for row in rows if row.get("paper_usable") is True]
    total_stake = stake_sum(usable)
    by_family = exposure_rows(usable, "family_id", total_stake)
    by_signal = exposure_rows(usable, "signal_key", total_stake)
    by_cluster = exposure_rows(usable, "cluster_key", total_stake)
    by_contract = exposure_rows(usable, "contract_ticker", total_stake)
    cap_breaches = cap_breach_rows(
        by_cluster=by_cluster,
        by_contract=by_contract,
        max_cluster_share=max_cluster_share,
        max_contract_stake=max_contract_stake,
    )
    return {
        "schema_version": 1,
        "paper_usable_count": len(usable),
        "total_paper_stake": round(total_stake, 6),
        "stake_share_of_bankroll": round(total_stake / paper_bankroll, 10)
        if paper_bankroll and paper_bankroll > 0
        else None,
        "settled_paper_stake": round(
            stake_sum(row for row in usable if row.get("settlement_status") == "settled"), 6
        ),
        "unresolved_paper_stake": round(
            stake_sum(row for row in usable if row.get("settlement_status") != "settled"), 6
        ),
        "due_unresolved_paper_stake": round(
            stake_sum(
                row for row in usable if row.get("settlement_status") == "pending_settlement_due"
            ),
            6,
        ),
        "realized_pnl": round(
            sum(optional_float(row.get("realized_pnl")) or 0.0 for row in usable), 10
        ),
        "largest_family": first_or_empty(by_family),
        "largest_signal": first_or_empty(by_signal),
        "largest_cluster": first_or_empty(by_cluster),
        "largest_contract": first_or_empty(by_contract),
        "cap_policy": {
            "paper_bankroll": paper_bankroll,
            "max_contract_stake": max_contract_stake,
            "max_cluster_share": max_cluster_share,
            "cap_scope": "diagnostic_report_only_not_live_authorization",
        },
        "cap_status": "paper_portfolio_cap_breaches_present"
        if cap_breaches
        else "paper_portfolio_caps_observed",
        "cap_breach_count": len(cap_breaches),
        "cap_breaches": cap_breaches,
        "exposure": {
            "by_family": by_family,
            "by_signal": by_signal,
            "by_cluster": by_cluster,
            "by_contract": by_contract[:50],
        },
    }


def stake_sum(rows: Sequence[Mapping[str, Any]] | Any) -> float:
    return sum(optional_float(row.get("paper_stake")) or 0.0 for row in rows)


def exposure_rows(
    rows: Sequence[Mapping[str, Any]],
    key: str,
    total_stake: float,
) -> list[dict[str, Any]]:
    stake_by_key: defaultdict[str, float] = defaultdict(float)
    count_by_key: Counter[str] = Counter()
    settled_by_key: defaultdict[str, float] = defaultdict(float)
    unresolved_by_key: defaultdict[str, float] = defaultdict(float)
    pnl_by_key: defaultdict[str, float] = defaultdict(float)
    for row in rows:
        value = str(row.get(key) or f"unknown_{key}")
        stake = optional_float(row.get("paper_stake")) or 0.0
        stake_by_key[value] += stake
        count_by_key[value] += 1
        if row.get("settlement_status") == "settled":
            settled_by_key[value] += stake
        else:
            unresolved_by_key[value] += stake
        pnl_by_key[value] += optional_float(row.get("realized_pnl")) or 0.0
    output = [
        {
            "key": value,
            "paper_stake": round(stake, 6),
            "stake_share": round(stake / total_stake, 10) if total_stake > 0 else 0.0,
            "row_count": count_by_key[value],
            "settled_paper_stake": round(settled_by_key[value], 6),
            "unresolved_paper_stake": round(unresolved_by_key[value], 6),
            "realized_pnl": round(pnl_by_key[value], 10),
        }
        for value, stake in stake_by_key.items()
    ]
    return sorted(output, key=lambda item: (-float(item["paper_stake"]), str(item["key"])))


def cap_breach_rows(
    *,
    by_cluster: Sequence[Mapping[str, Any]],
    by_contract: Sequence[Mapping[str, Any]],
    max_cluster_share: float,
    max_contract_stake: float | None,
) -> list[dict[str, Any]]:
    breaches: list[dict[str, Any]] = []
    for row in by_cluster:
        share = optional_float(row.get("stake_share")) or 0.0
        if share > max_cluster_share:
            breaches.append(
                {
                    "cap": "max_cluster_share",
                    "key": row.get("key"),
                    "value": share,
                    "limit": max_cluster_share,
                }
            )
    if max_contract_stake is not None:
        for row in by_contract:
            stake = optional_float(row.get("paper_stake")) or 0.0
            if stake > max_contract_stake:
                breaches.append(
                    {
                        "cap": "max_contract_stake",
                        "key": row.get("key"),
                        "value": round(stake, 6),
                        "limit": round(max_contract_stake, 6),
                    }
                )
    return breaches


def first_or_empty(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return dict(rows[0]) if rows else {}
