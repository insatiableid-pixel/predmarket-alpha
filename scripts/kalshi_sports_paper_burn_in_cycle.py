#!/usr/bin/env python3
# ruff: noqa: E402
"""Run the sports paper settlement burn-in loop.

This is an orchestration wrapper over existing research-only builders.  It
decides whether paper rows are due for exact public Kalshi settlement probing,
refreshes the paper settlement artifact, feeds that enriched artifact into the
retirement ledger, refreshes sports evidence summaries, and emits one compact
audit for the next machine action.
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

from predmarket.shared_helpers import (
    iso_time,
    safety_flags,
    sha256_or_none,
    timestamp,
    utc_now,
)
from predmarket.signal_decay_retirement import (
    build_signal_decay_retirement_ledger,
)
from scripts.kalshi_paper_settlement_reconcile import (
    DEFAULT_OUT_DIR as DEFAULT_SETTLEMENT_OUT_DIR,
)
from scripts.kalshi_paper_settlement_reconcile import (
    DEFAULT_PAPER_DECISIONS_PATH,
    DEFAULT_SETTLED_RAW_DIR,
    DEFAULT_SETTLED_SNAPSHOT_PATH,
    build_paper_settlement_reconciliation,
    capture_public_paper_settlement_snapshot,
    due_paper_tickers,
)
from scripts.kalshi_paper_settlement_reconcile import (
    write_outputs as write_settlement_outputs,
)
from scripts.kalshi_signal_decay_retirement import (
    DEFAULT_OUT_DIR as DEFAULT_RETIREMENT_OUT_DIR,
)
from scripts.kalshi_signal_decay_retirement import (
    write_ledger,
)
from scripts.kalshi_sports_evidence_cycle_report import (
    DEFAULT_OUT_DIR as DEFAULT_EVIDENCE_OUT_DIR,
)
from scripts.kalshi_sports_evidence_cycle_report import (
    build_sports_evidence_cycle_report,
)
from scripts.kalshi_sports_evidence_cycle_report import (
    write_outputs as write_evidence_outputs,
)
from scripts.kalshi_sports_label_accumulation_cycle import (
    DEFAULT_OUT_DIR as DEFAULT_LABEL_OUT_DIR,
)
from scripts.kalshi_sports_label_accumulation_cycle import (
    build_sports_label_accumulation_cycle,
)
from scripts.kalshi_sports_label_accumulation_cycle import (
    write_outputs as write_label_outputs,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-paper-burn-in-cycle-latest"
DEFAULT_LATEST_SETTLEMENT_PATH = MACRO_DIR / "latest-paper-settlement-reconciliation.json"
DEFAULT_LATEST_RETIREMENT_PATH = MACRO_DIR / "latest-signal-decay-retirement-ledger.json"
DEFAULT_LATEST_EVIDENCE_PATH = MACRO_DIR / "latest-kalshi-sports-evidence-cycle.json"
DEFAULT_LATEST_LABEL_PATH = MACRO_DIR / "latest-kalshi-sports-label-accumulation-cycle.json"

CSV_FIELDS = [
    "status",
    "paper_usable_count",
    "due_before_fetch_count",
    "due_after_fetch_count",
    "settled_paper_usable_count",
    "unresolved_paper_usable_count",
    "paper_portfolio_cap_status",
    "paper_portfolio_cap_breach_count",
    "paper_portfolio_unresolved_stake",
    "next_paper_close_time_utc",
    "total_label_deficit",
    "live_eligible_count",
    "next_action_name",
]


def execute_sports_paper_burn_in_cycle(
    *,
    paper_decisions_path: Path = DEFAULT_PAPER_DECISIONS_PATH,
    settled_snapshot_path: Path = DEFAULT_SETTLED_SNAPSHOT_PATH,
    settled_raw_dir: Path = DEFAULT_SETTLED_RAW_DIR,
    max_fetch_tickers: int = 100,
    fetch_due_settlements: bool = False,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    due_before = due_paper_tickers(
        paper_decisions_path,
        generated_utc=generated,
        max_tickers=max_fetch_tickers,
    )
    active_settlement_path = settled_snapshot_path
    fetched_snapshot_path: Path | None = None
    if fetch_due_settlements and due_before:
        active_settlement_path = capture_public_paper_settlement_snapshot(
            tickers=due_before,
            raw_dir=settled_raw_dir,
            base_snapshot_path=settled_snapshot_path if settled_snapshot_path.exists() else None,
            generated_utc=generated,
        )
        fetched_snapshot_path = active_settlement_path

    settlement = build_paper_settlement_reconciliation(
        paper_decisions_path=paper_decisions_path,
        settled_snapshot_path=active_settlement_path,
        generated_utc=generated,
    )
    write_settlement_outputs(settlement, out_dir=DEFAULT_SETTLEMENT_OUT_DIR)

    retirement = build_signal_decay_retirement_ledger(
        paper_decisions_path=DEFAULT_LATEST_SETTLEMENT_PATH
    )
    write_ledger(retirement, DEFAULT_RETIREMENT_OUT_DIR)

    evidence = build_sports_evidence_cycle_report(generated_utc=generated)
    write_evidence_outputs(evidence, out_dir=DEFAULT_EVIDENCE_OUT_DIR)

    label = build_sports_label_accumulation_cycle(generated_utc=generated)
    write_label_outputs(label, out_dir=DEFAULT_LABEL_OUT_DIR)

    return build_sports_paper_burn_in_report(
        generated_utc=generated,
        paper_decisions_path=paper_decisions_path,
        settlement_snapshot_path=active_settlement_path,
        fetched_snapshot_path=fetched_snapshot_path,
        due_tickers_before_fetch=due_before,
        settlement=settlement,
        retirement=retirement,
        evidence=evidence,
        label=label,
    )


def build_sports_paper_burn_in_report(
    *,
    generated_utc: str,
    paper_decisions_path: Path,
    settlement_snapshot_path: Path,
    fetched_snapshot_path: Path | None,
    due_tickers_before_fetch: Sequence[str],
    settlement: Mapping[str, Any],
    retirement: Mapping[str, Any],
    evidence: Mapping[str, Any],
    label: Mapping[str, Any],
) -> dict[str, Any]:
    summary = build_summary(
        generated_utc=generated_utc,
        due_tickers_before_fetch=due_tickers_before_fetch,
        settlement=settlement,
        retirement=retirement,
        evidence=evidence,
        label=label,
    )
    gates = build_gates(summary, settlement=settlement, evidence=evidence, label=label)
    status = report_status(summary, gates)
    next_action = next_action_for_status(status, summary, label)
    return {
        "schema_version": 1,
        "generated_utc": generated_utc,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": bool(fetched_snapshot_path),
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "paper_sizing_only": True,
        "inputs": {
            "paper_decisions_path": str(paper_decisions_path),
            "paper_decisions_sha256": sha256_or_none(paper_decisions_path),
            "settlement_snapshot_path": str(settlement_snapshot_path),
            "settlement_snapshot_sha256": sha256_or_none(settlement_snapshot_path),
            "fetched_snapshot_path": str(fetched_snapshot_path) if fetched_snapshot_path else None,
            "fetched_snapshot_sha256": sha256_or_none(fetched_snapshot_path)
            if fetched_snapshot_path
            else None,
        },
        "method": {
            "purpose": "Advance sports paper decisions through exact public Kalshi settlement, retirement, and evidence-cycle reporting.",
            "due_rule": "Only paper-usable rows with close_time <= generated_utc are eligible for public settlement probing.",
            "label_rule": "Family exact-label readiness is summarized separately and keeps duplicate contracts from counting as independent evidence.",
            "execution_boundary": "No account, order, approval queue, or live execution path is reached by this cycle.",
        },
        "summary": summary,
        "gates": gates,
        "next_action": next_action,
        "family_rows": label.get("family_rows")
        if isinstance(label.get("family_rows"), list)
        else [],
        "safety": safety_flags(public_market_data_calls=bool(fetched_snapshot_path)),
    }


def build_summary(
    *,
    generated_utc: str,
    due_tickers_before_fetch: Sequence[str],
    settlement: Mapping[str, Any],
    retirement: Mapping[str, Any],
    evidence: Mapping[str, Any],
    label: Mapping[str, Any],
) -> dict[str, Any]:
    settlement_summary = mapping(settlement.get("summary"))
    retirement_summary = mapping(retirement.get("summary"))
    evidence_summary = mapping(evidence.get("summary"))
    label_summary = mapping(label.get("summary"))
    candidates = (
        settlement.get("candidates") if isinstance(settlement.get("candidates"), list) else []
    )
    due_after = int_value(settlement_summary.get("due_unresolved_paper_usable_count"))
    next_close = settlement_summary.get("next_unresolved_close_time_utc") or next_paper_close_time(
        candidates, generated_utc=generated_utc
    )
    label_deficits = [
        {
            "family_id": row.get("family_id"),
            "label_deficit": row.get("label_deficit"),
            "next_public_label_probe_utc": row.get("next_public_label_probe_utc"),
            "status": row.get("status"),
        }
        for row in label.get("family_rows", [])
        if isinstance(row, Mapping) and int_value(row.get("label_deficit")) > 0
    ]
    return {
        "paper_usable_count": int_value(settlement_summary.get("paper_usable_count")),
        "due_before_fetch_count": len(due_tickers_before_fetch),
        "due_tickers_before_fetch_sample": list(due_tickers_before_fetch[:25]),
        "due_after_fetch_count": due_after,
        "settled_paper_usable_count": int_value(
            settlement_summary.get("settled_paper_usable_count")
        ),
        "unresolved_paper_usable_count": int_value(
            settlement_summary.get("unresolved_paper_usable_count")
        ),
        "total_paper_stake": settlement_summary.get("total_paper_stake"),
        "paper_portfolio_cap_status": settlement_summary.get("paper_portfolio_cap_status"),
        "paper_portfolio_cap_breach_count": int_value(
            settlement_summary.get("paper_portfolio_cap_breach_count")
        ),
        "paper_portfolio_largest_family": settlement_summary.get("paper_portfolio_largest_family"),
        "paper_portfolio_largest_signal": settlement_summary.get("paper_portfolio_largest_signal"),
        "paper_portfolio_largest_cluster": settlement_summary.get(
            "paper_portfolio_largest_cluster"
        ),
        "paper_portfolio_largest_contract": settlement_summary.get(
            "paper_portfolio_largest_contract"
        ),
        "paper_portfolio_unresolved_stake": settlement_summary.get(
            "paper_portfolio_unresolved_stake"
        ),
        "paper_portfolio_settled_stake": settlement_summary.get("paper_portfolio_settled_stake"),
        "next_paper_close_time_utc": next_close,
        "paper_realized_pnl": settlement_summary.get("realized_pnl"),
        "paper_hit_rate": settlement_summary.get("hit_rate"),
        "retired_signal_count": int_value(retirement_summary.get("retired_signal_count")),
        "active_signal_count": int_value(retirement_summary.get("active_signal_count")),
        "sports_evidence_status": evidence.get("status"),
        "sports_label_status": label.get("status"),
        "total_exact_label_count": int_value(label_summary.get("total_exact_label_count")),
        "total_independent_label_count": int_value(
            label_summary.get("total_independent_label_count")
        ),
        "total_label_deficit": int_value(label_summary.get("total_label_deficit")),
        "label_deficits": label_deficits,
        "oos_fdr_candidate_family_count": int_value(
            label_summary.get("oos_fdr_candidate_family_count")
        ),
        "live_eligible_count": int_value(evidence_summary.get("live_eligible_count")),
        "settlement_status": settlement.get("status"),
        "retirement_status": retirement.get("status"),
        "generated_utc": generated_utc,
    }


def build_gates(
    summary: Mapping[str, Any],
    *,
    settlement: Mapping[str, Any],
    evidence: Mapping[str, Any],
    label: Mapping[str, Any],
) -> list[dict[str, str]]:
    return [
        gate(
            "paper_settlement_artifact_safe",
            "pass"
            if settlement.get("research_only") is True
            and settlement.get("market_execution") is False
            else "fail",
            f"Settlement status={settlement.get('status')}.",
        ),
        gate(
            "retirement_refreshed_from_paper_settlement",
            "pass"
            if summary.get("retirement_status") == "signal_decay_retirement_ledger_ready"
            else "blocked",
            f"Retirement status={summary.get('retirement_status')}.",
        ),
        gate(
            "sports_evidence_refreshed",
            "pass"
            if str(evidence.get("status") or "").startswith("sports_evidence_cycle_")
            else "blocked",
            f"Evidence status={evidence.get('status')}.",
        ),
        gate(
            "label_accumulation_refreshed",
            "pass"
            if str(label.get("status") or "").startswith("sports_label_accumulation_")
            else "blocked",
            f"Label status={label.get('status')}.",
        ),
        gate(
            "due_rows_have_explicit_state",
            "pass"
            if int_value(summary.get("due_after_fetch_count")) == 0
            or str(summary.get("settlement_status") or "")
            == "paper_settlement_reconciliation_waiting_for_due_settlements"
            else "blocked",
            f"Due after fetch={summary.get('due_after_fetch_count')}.",
        ),
        gate(
            "live_execution_remains_blocked",
            "pass" if int_value(summary.get("live_eligible_count")) == 0 else "warn",
            f"Live eligible={summary.get('live_eligible_count')}.",
        ),
    ]


def report_status(summary: Mapping[str, Any], gates: Sequence[Mapping[str, Any]]) -> str:
    if any(item.get("status") == "fail" for item in gates):
        return "sports_paper_burn_in_failed_safety_gate"
    if any(item.get("status") == "blocked" for item in gates):
        return "sports_paper_burn_in_blocked_missing_refresh"
    if int_value(summary.get("settled_paper_usable_count")) > 0:
        return "sports_paper_burn_in_ready_with_realized_paper_rows"
    if int_value(summary.get("due_after_fetch_count")) > 0:
        return "sports_paper_burn_in_waiting_for_public_settlement"
    if int_value(summary.get("paper_usable_count")) > 0:
        return "sports_paper_burn_in_waiting_for_next_close"
    return "sports_paper_burn_in_ready_no_paper_usable_rows"


def next_action_for_status(
    status: str, summary: Mapping[str, Any], label: Mapping[str, Any]
) -> dict[str, Any]:
    if status == "sports_paper_burn_in_ready_with_realized_paper_rows":
        return {
            "name": "kalshi_sports_paper_outcome_audit",
            "why": "Resolved paper rows are now available for realized PnL, calibration, and retirement review.",
            "command": "make kalshi-sports-paper-burn-in-cycle",
            "stop_condition": "Stop before live execution unless live mode is explicitly armed and risk gates pass.",
        }
    if status == "sports_paper_burn_in_waiting_for_public_settlement":
        return {
            "name": "kalshi_paper_settlement_exact_ticker_probe",
            "why": f"{summary.get('due_after_fetch_count')} due paper row(s) still lack public settlement outcomes.",
            "command": "make kalshi-sports-paper-burn-in-cycle KALSHI_SPORTS_PAPER_BURN_IN_FETCH=1",
            "stop_condition": "Use only exact public Kalshi market payloads; do not infer outcomes from scoreboards.",
        }
    if status == "sports_paper_burn_in_waiting_for_next_close":
        return {
            "name": "kalshi_paper_lifecycle_wait",
            "why": "Paper rows are frozen but not yet past close.",
            "next_paper_close_time_utc": summary.get("next_paper_close_time_utc"),
            "command": "make kalshi-sports-paper-burn-in-cycle KALSHI_SPORTS_PAPER_BURN_IN_FETCH=1",
            "stop_condition": "Do not rewrite decision-time probabilities or stakes after outcomes are known.",
        }
    if int_value(summary.get("oos_fdr_candidate_family_count")) > 0:
        return {
            "name": "kalshi_sports_replay_capacity_decay",
            "why": "At least one sports family has an OOS/FDR research candidate ready for replay/capacity/decay gates.",
            "label_status": label.get("status"),
            "stop_condition": "Stop before paper stake if any downstream gate blocks.",
        }
    return {
        "name": "kalshi_sports_exact_label_accumulation",
        "why": "Exact public Kalshi settlement labels remain below thresholds for at least one family.",
        "label_deficits": summary.get("label_deficits"),
        "stop_condition": "Stop before lowering thresholds or counting duplicate contracts as independent labels.",
    }


def next_paper_close_time(rows: Sequence[Any], *, generated_utc: str) -> str | None:
    generated_ts = timestamp(generated_utc)
    future: list[tuple[float, str]] = []
    for row in rows:
        if not isinstance(row, Mapping) or row.get("paper_usable") is not True:
            continue
        close = iso_time(row.get("close_time"))
        close_ts = timestamp(close)
        if close and close_ts is not None and (generated_ts is None or close_ts > generated_ts):
            future.append((close_ts, close))
    return min(future)[1] if future else None


def mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def write_outputs(report: Mapping[str, Any], *, out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-paper-burn-in-cycle.json"
    md_path = out_dir / "kalshi-sports-paper-burn-in-cycle.md"
    csv_path = out_dir / "kalshi-sports-paper-burn-in-cycle.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, csv_path)

    latest_json = MACRO_DIR / "latest-kalshi-sports-paper-burn-in-cycle.json"
    latest_md = MACRO_DIR / "latest-kalshi-sports-paper-burn-in-cycle.md"
    latest_csv = MACRO_DIR / "latest-kalshi-sports-paper-burn-in-cycle.csv"
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
    summary = mapping(report.get("summary"))
    lines = [
        "# Kalshi Sports Paper Burn-In Cycle",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Paper usable: `{summary.get('paper_usable_count')}`",
        f"- Total paper stake: `{summary.get('total_paper_stake')}`",
        f"- Settled paper usable: `{summary.get('settled_paper_usable_count')}`",
        f"- Due before fetch: `{summary.get('due_before_fetch_count')}`",
        f"- Due after fetch: `{summary.get('due_after_fetch_count')}`",
        f"- Next paper close: `{summary.get('next_paper_close_time_utc')}`",
        f"- Realized PnL: `{summary.get('paper_realized_pnl')}`",
        f"- Portfolio cap status: `{summary.get('paper_portfolio_cap_status')}`",
        f"- Largest cluster: `{summary.get('paper_portfolio_largest_cluster')}`",
        f"- Total label deficit: `{summary.get('total_label_deficit')}`",
        f"- Live eligible: `{summary.get('live_eligible_count')}`",
        f"- Next action: `{mapping(report.get('next_action')).get('name')}`",
        "",
        "| Family | Status | Deficit | Next Probe |",
        "| --- | --- | ---: | --- |",
    ]
    family_rows = report.get("family_rows") if isinstance(report.get("family_rows"), list) else []
    for row in family_rows:
        if isinstance(row, Mapping):
            lines.append(
                f"| `{row.get('family_id')}` | `{row.get('status')}` | "
                f"`{row.get('label_deficit')}` | `{row.get('next_public_label_probe_utc')}` |"
            )
    lines.extend(
        [
            "",
            "Research-only burn-in. No account, order, approval queue, or live execution path.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(report: Mapping[str, Any], path: Path) -> None:
    summary = mapping(report.get("summary"))
    row = {
        "status": report.get("status"),
        "paper_usable_count": summary.get("paper_usable_count"),
        "due_before_fetch_count": summary.get("due_before_fetch_count"),
        "due_after_fetch_count": summary.get("due_after_fetch_count"),
        "settled_paper_usable_count": summary.get("settled_paper_usable_count"),
        "unresolved_paper_usable_count": summary.get("unresolved_paper_usable_count"),
        "paper_portfolio_cap_status": summary.get("paper_portfolio_cap_status"),
        "paper_portfolio_cap_breach_count": summary.get("paper_portfolio_cap_breach_count"),
        "paper_portfolio_unresolved_stake": summary.get("paper_portfolio_unresolved_stake"),
        "next_paper_close_time_utc": summary.get("next_paper_close_time_utc"),
        "total_label_deficit": summary.get("total_label_deficit"),
        "live_eligible_count": summary.get("live_eligible_count"),
        "next_action_name": mapping(report.get("next_action")).get("name"),
    }
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerow(row)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-decisions-path", type=Path, default=DEFAULT_PAPER_DECISIONS_PATH)
    parser.add_argument("--settled-snapshot-path", type=Path, default=DEFAULT_SETTLED_SNAPSHOT_PATH)
    parser.add_argument("--settled-raw-dir", type=Path, default=DEFAULT_SETTLED_RAW_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-fetch-tickers", type=int, default=100)
    parser.add_argument("--fetch-due-settlements", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = execute_sports_paper_burn_in_cycle(
        paper_decisions_path=args.paper_decisions_path,
        settled_snapshot_path=args.settled_snapshot_path,
        settled_raw_dir=args.settled_raw_dir,
        max_fetch_tickers=args.max_fetch_tickers,
        fetch_due_settlements=args.fetch_due_settlements,
    )
    if args.write:
        paths = write_outputs(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
