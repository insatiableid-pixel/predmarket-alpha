#!/usr/bin/env python3
"""Build a ranked research-only Kalshi EV review queue.

The EV ledger answers whether a row is mathematically usable. This queue adds
the next layer of judgment for research work: rank positive rows, label thin
versus more robust margins, and preserve rejected-row counts so a human can see
why most candidates did not make the queue.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


CONTROL_REPO = Path(__file__).resolve().parents[1]
MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_LEDGER_PATH = MACRO_DIR / "latest-kalshi-contract-ev-ledger.json"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-ev-review-queue-latest"
DEFAULT_MIN_ROBUST_MARGIN = 0.02
CLEAN_TIMING_STATUSES = {"clean", "pregame_clean", "not_applicable"}
CSV_FIELDS = [
    "queue_rank",
    "disposition",
    "contract_ticker",
    "side",
    "selection",
    "source_repo_id",
    "market_type",
    "all_in_break_even_probability",
    "calibrated_probability",
    "margin_probability",
    "expected_roi",
    "executable_price",
    "fee_estimate",
    "gate_status",
    "timing_status",
    "resolution_rule_status",
    "robustness_reasons",
    "rejection_reasons",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_review_queue(
    *,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    generated_utc: str | None = None,
    min_robust_margin: float = DEFAULT_MIN_ROBUST_MARGIN,
    max_rows: int = 100,
) -> dict[str, Any]:
    ledger = read_json_or_empty(ledger_path)
    ledger_rows = ledger.get("rows") if isinstance(ledger.get("rows"), list) else []
    rows = [row for row in ledger_rows if isinstance(row, Mapping)]
    queued_rows = [
        queue_row(row, ledger=ledger, min_robust_margin=min_robust_margin)
        for row in rows
        if is_positive_usable(row)
    ]
    queued_rows.sort(
        key=lambda row: (
            row["disposition"] != "robust_positive_ev_review",
            row["disposition"] != "positive_ev_watch",
            -float(row.get("margin_probability") or 0.0),
            -float(row.get("expected_roi") or 0.0),
            str(row.get("contract_ticker") or ""),
        )
    )
    queued_rows = queued_rows[: max(0, max_rows)]
    for index, row in enumerate(queued_rows, start=1):
        row["queue_rank"] = index

    robust_count = sum(1 for row in queued_rows if row["disposition"] == "robust_positive_ev_review")
    positive_watch_count = sum(1 for row in queued_rows if row["disposition"] == "positive_ev_watch")
    thin_count = sum(1 for row in queued_rows if row["disposition"] == "thin_positive_ev_watch")
    rejected_reason_counts = rejected_reason_counts_for(rows)
    if robust_count:
        status = "kalshi_ev_review_queue_ready_with_robust_candidates"
    elif queued_rows:
        status = "kalshi_ev_review_queue_positive_candidates_need_robustness"
    else:
        status = "kalshi_ev_review_queue_blocked_no_positive_usable_rows"

    return {
        "schema_version": 1,
        "generated_utc": generated_utc or utc_now(),
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "live_calls_made": False,
        "provider_api_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "inputs": {
            "ledger_path": str(ledger_path),
            "ledger_status": ledger.get("status"),
            "ledger_generated_utc": ledger.get("generated_utc"),
        },
        "policy": {
            "min_positive_margin": 0.0,
            "min_robust_margin": min_robust_margin,
            "break_even_hurdle": "all_in_break_even_probability",
            "candidate_rule": "usable=true and margin_probability > 0",
            "robust_rule": (
                "candidate rule plus margin_probability >= min_robust_margin, "
                "verified official terms, clean timing, and pass gate"
            ),
        },
        "summary": {
            "ledger_row_count": len(rows),
            "queued_row_count": len(queued_rows),
            "robust_candidate_count": robust_count,
            "positive_watch_count": positive_watch_count,
            "thin_positive_watch_count": thin_count,
            "usable_positive_row_count": len(queued_rows),
            "rejected_row_count": max(0, len(rows) - len(queued_rows)),
            "rejected_reason_counts": rejected_reason_counts,
        },
        "rows": queued_rows,
        "next_action": next_action(status, queued_rows),
        "safety": {
            "research_only": True,
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "raw_payloads_copied_to_repo": False,
        },
    }


def is_positive_usable(row: Mapping[str, Any]) -> bool:
    margin = optional_float(row.get("margin_probability"))
    return row.get("usable") is True and margin is not None and margin > 0.0


def queue_row(row: Mapping[str, Any], *, ledger: Mapping[str, Any], min_robust_margin: float) -> dict[str, Any]:
    margin = optional_float(row.get("margin_probability")) or 0.0
    robustness_reasons = robustness_reasons_for(row, min_robust_margin=min_robust_margin)
    if not robustness_reasons:
        disposition = "robust_positive_ev_review"
    elif margin < min_robust_margin:
        disposition = "thin_positive_ev_watch"
    else:
        disposition = "positive_ev_watch"
    return {
        "queue_rank": None,
        "disposition": disposition,
        "contract_ticker": row.get("contract_ticker"),
        "event_ticker": row.get("event_ticker"),
        "side": row.get("side"),
        "selection": row.get("selection"),
        "source_repo_id": row.get("source_repo_id"),
        "market_type": row.get("market_type"),
        "evidence_timestamp": ledger.get("generated_utc"),
        "resolution_rule": row.get("resolution_rule"),
        "resolution_rule_source": row.get("resolution_rule_source"),
        "resolution_rule_status": row.get("resolution_rule_status"),
        "resolution_rule_source_artifact": row.get("resolution_rule_source_artifact"),
        "executable_price": row.get("executable_price"),
        "fee_estimate": row.get("fee_estimate"),
        "all_in_break_even_probability": row.get("all_in_break_even_probability"),
        "calibrated_probability": row.get("calibrated_probability"),
        "calibrated_probability_source": row.get("calibrated_probability_source"),
        "calibrated_probability_source_artifact": row.get("calibrated_probability_source_artifact"),
        "margin_probability": margin,
        "expected_value_per_contract": row.get("expected_value_per_contract"),
        "expected_roi": row.get("expected_roi"),
        "gate_status": row.get("gate_status"),
        "gate_reasons": row.get("gate_reasons") or [],
        "rejection_reasons": [],
        "timing_status": row.get("timing_status"),
        "usable": row.get("usable"),
        "robustness_reasons": robustness_reasons,
    }


def robustness_reasons_for(row: Mapping[str, Any], *, min_robust_margin: float) -> list[str]:
    reasons: list[str] = []
    margin = optional_float(row.get("margin_probability"))
    if margin is None or margin < min_robust_margin:
        reasons.append(f"margin below robust review threshold {min_robust_margin:.4f}")
    if row.get("gate_status") != "pass":
        reasons.append(f"row gate status is {row.get('gate_status')}")
    if row.get("resolution_rule_status") != "verified_official_terms":
        reasons.append("resolution rule is not verified official terms")
    if str(row.get("timing_status") or "") not in CLEAN_TIMING_STATUSES:
        reasons.append("timing status is not clean")
    if optional_float(row.get("probability_uncertainty")) is not None:
        reasons.append("probability uncertainty is present and must be reviewed")
    if row.get("cost_quality") == "estimated_fee_from_executable_price":
        reasons.append("fee is estimated from executable price")
    return reasons


def rejected_reason_counts_for(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if is_positive_usable(row):
            continue
        reasons = row.get("gate_reasons") if isinstance(row.get("gate_reasons"), list) else []
        if not reasons:
            margin = optional_float(row.get("margin_probability"))
            if row.get("usable") is not True:
                reasons = ["row is not usable"]
            elif margin is None:
                reasons = ["margin is missing"]
            elif margin <= 0:
                reasons = ["margin is not positive"]
            else:
                reasons = ["not queued"]
        for reason in reasons:
            text = str(reason)
            counts[text] = counts.get(text, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20])


def next_action(status: str, rows: Sequence[Mapping[str, Any]]) -> str:
    if status == "kalshi_ev_review_queue_ready_with_robust_candidates":
        return (
            "Review the robust research candidates manually; execution remains disabled. "
            "Next engineering work is independent snapshot repeatability and forward-context validation."
        )
    if rows:
        return (
            "Positive candidates exist, but current margins are thin or have robustness caveats. "
            "Next work: assemble the full available contract set, repeat snapshots, and require forward-context "
            "or independent validation before treating any row as stronger than watch-only research."
        )
    return (
        "No positive usable rows are queued. Refresh the ledger after exact contract mappings and calibrated "
        "probabilities exist, then rerun the review queue."
    )


def write_review_queue(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-ev-review-queue.json"
    md_path = out_dir / "kalshi-ev-review-queue.md"
    csv_path = out_dir / "kalshi-ev-review-queue.csv"
    json_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("rows") if isinstance(report.get("rows"), list) else [], csv_path)
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-ev-review-queue.json"
    latest_md = MACRO_DIR / "latest-kalshi-ev-review-queue.md"
    latest_csv = MACRO_DIR / "latest-kalshi-ev-review-queue.csv"
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("rows") if isinstance(report.get("rows"), list) else [], latest_csv)
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
    policy = report.get("policy") if isinstance(report.get("policy"), Mapping) else {}
    lines = [
        "# Kalshi EV Review Queue",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Research only: `{str(report.get('research_only')).lower()}`",
        f"- Execution enabled: `{str(report.get('execution_enabled')).lower()}`",
        f"- Ledger rows: `{summary.get('ledger_row_count')}`",
        f"- Queued rows: `{summary.get('queued_row_count')}`",
        f"- Robust candidates: `{summary.get('robust_candidate_count')}`",
        f"- Positive watch rows: `{summary.get('positive_watch_count')}`",
        f"- Thin positive watch rows: `{summary.get('thin_positive_watch_count')}`",
        f"- Robust margin threshold: `{policy.get('min_robust_margin')}`",
        "",
        "## Queue",
        "",
        "| Rank | Disposition | Contract | Selection | Break-even | Probability | Margin | ROI | Caveats |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    for row in rows[:25]:
        caveats = "; ".join(str(reason) for reason in row.get("robustness_reasons") or [])
        lines.append(
            f"| {row.get('queue_rank')} | `{row.get('disposition')}` | `{row.get('contract_ticker')}` | "
            f"`{row.get('selection')}` | {format_number(row.get('all_in_break_even_probability'))} | "
            f"{format_number(row.get('calibrated_probability'))} | {format_number(row.get('margin_probability'))} | "
            f"{format_number(row.get('expected_roi'))} | {caveats or 'none'} |"
        )
    if not rows:
        lines.append("|  |  |  |  |  |  |  |  | No queued rows |")
    lines.extend(["", "## Next Action", "", str(report.get("next_action") or ""), ""])
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            output = dict(row)
            output["robustness_reasons"] = "; ".join(str(reason) for reason in row.get("robustness_reasons") or [])
            writer.writerow(output)


def format_number(value: Any) -> str:
    number = optional_float(value)
    return "" if number is None else f"{number:.6f}"


def optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-path", type=Path, default=DEFAULT_LEDGER_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--min-robust-margin", type=float, default=DEFAULT_MIN_ROBUST_MARGIN)
    parser.add_argument("--max-rows", type=int, default=100)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_review_queue(
        ledger_path=args.ledger_path,
        min_robust_margin=args.min_robust_margin,
        max_rows=args.max_rows,
    )
    if args.write:
        paths = write_review_queue(report, args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
