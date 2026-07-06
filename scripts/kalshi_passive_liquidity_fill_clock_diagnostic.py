#!/usr/bin/env python3
"""Diagnose why passive-liquidity paper maker intents are not filling.

This is a control-plane artifact for Claude's passive-liquidity requirement.
It explains whether the paper fill clock is blocked by sparse snapshots, short
TTL, conservative quote prices, missing side books, or actual lack of touches.

It does not treat public touches as real exchange fills, and it never emits EV,
stake, live eligibility, account access, or orders.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = CONTROL_REPO / "scripts"
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kalshi_passive_liquidity_paper_fill_falsification import (  # noqa: E402
    microstructure_rows,
)

from predmarket.shared_helpers import (  # noqa: E402
    json_float,
    path_is_within,
    read_json_or_empty,
    safe_research_artifact,
    safety_flags,
    sha256_or_none,
    timestamp,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_PAPER_FILL_PATH = MACRO_DIR / "latest-kalshi-passive-liquidity-paper-fill-loop.json"
DEFAULT_MICROSTRUCTURE_PATH = (
    MACRO_DIR / "latest-kalshi-sports-microstructure-observation-loop.json"
)
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-passive-liquidity-fill-clock-diagnostic-latest"

CSV_FIELDS = [
    "paper_intent_id",
    "contract_ticker",
    "side",
    "quote_price",
    "ttl_seconds",
    "entry_observed_at_utc",
    "order_expires_at_utc",
    "paper_fill_status",
    "future_snapshot_within_ttl_count",
    "future_snapshot_after_expiry_count",
    "seconds_to_first_later_snapshot",
    "min_ask_distance_to_touch",
    "first_touch_utc",
    "diagnostic_reason",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_passive_liquidity_fill_clock_diagnostic(
    *,
    paper_fill_path: Path = DEFAULT_PAPER_FILL_PATH,
    microstructure_path: Path = DEFAULT_MICROSTRUCTURE_PATH,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    paper_fill = read_json_or_empty(paper_fill_path)
    micro = read_json_or_empty(microstructure_path)
    rows = microstructure_rows(micro)
    diagnostic_rows = build_diagnostic_rows(paper_fill, rows)
    summary = build_summary(paper_fill=paper_fill, micro=micro, rows=diagnostic_rows)
    gates = build_gates(summary)
    status = report_status(summary)
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "family_id": "passive_liquidity_provision",
        "public_market_data_calls": False,
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "usable": False,
        "inputs": {
            "paper_fill_path": str(paper_fill_path),
            "paper_fill_sha256": sha256_or_none(paper_fill_path),
            "paper_fill_status": paper_fill.get("status"),
            "microstructure_path": str(microstructure_path),
            "microstructure_sha256": sha256_or_none(microstructure_path),
            "microstructure_status": micro.get("status"),
        },
        "method": {
            "purpose": "Explain why persisted passive maker paper intents have not generated paper fill labels.",
            "fill_boundary": "Public orderbook touches are paper labels only; real exchange fills remain zero unless account/order reconciliation exists.",
            "ttl_cadence_rule": "A paper intent cannot observe a touch if no later public snapshot lands before its TTL expires.",
            "execution_boundary": "This diagnostic never submits quotes, reads accounts, sizes stakes, or emits tradable probabilities.",
        },
        "summary": summary,
        "gates": gates,
        "diagnostic_rows": diagnostic_rows,
        "next_action": next_action(status, summary),
        "safety": safety_flags(),
    }


def build_diagnostic_rows(
    paper_fill: Mapping[str, Any],
    micro_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    intents = [row for row in paper_fill.get("paper_intent_rows", []) if isinstance(row, Mapping)]
    labels = {
        str(row.get("paper_intent_id") or ""): row
        for row in paper_fill.get("paper_fill_label_rows", [])
        if isinstance(row, Mapping) and str(row.get("paper_intent_id") or "")
    }
    by_ticker: dict[str, list[Mapping[str, Any]]] = {}
    for row in micro_rows:
        ticker = str(row.get("contract_ticker") or "")
        if ticker:
            by_ticker.setdefault(ticker, []).append(row)
    for ticker_rows in by_ticker.values():
        ticker_rows.sort(key=lambda row: timestamp(row.get("observed_at_utc")) or -1.0)

    output = [
        diagnose_intent(intent, labels.get(str(intent.get("paper_intent_id") or "")), by_ticker)
        for intent in intents
    ]
    return sorted(output, key=lambda row: str(row.get("paper_intent_id") or ""))


def diagnose_intent(
    intent: Mapping[str, Any],
    label: Mapping[str, Any] | None,
    by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    ticker = str(intent.get("contract_ticker") or "")
    side = str(intent.get("side") or "").lower()
    quote_price = as_float(intent.get("quote_price"))
    ttl_seconds = int_value(intent.get("ttl_seconds"))
    entry_ts = timestamp(intent.get("entry_observed_at_utc"))
    expiry_ts = timestamp(intent.get("order_expires_at_utc"))
    rows = list(by_ticker.get(ticker, []))
    later_rows = [
        row
        for row in rows
        if entry_ts is not None and (timestamp(row.get("observed_at_utc")) or -1.0) > entry_ts
    ]
    within_ttl = [
        row
        for row in later_rows
        if expiry_ts is not None
        and (timestamp(row.get("observed_at_utc")) or math.inf) <= expiry_ts
    ]
    after_expiry = [
        row
        for row in later_rows
        if expiry_ts is not None and (timestamp(row.get("observed_at_utc")) or -1.0) > expiry_ts
    ]
    first_later_ts = (
        min(timestamp(row.get("observed_at_utc")) or math.inf for row in later_rows)
        if later_rows
        else None
    )
    distances = ask_distances(within_ttl, side=side, quote_price=quote_price)
    first_touch = first_touch_utc(within_ttl, side=side, quote_price=quote_price)
    paper_status = (
        str(label.get("paper_fill_status") or "") if label is not None else "paper_intent_open"
    )
    reason = diagnostic_reason(
        paper_status=paper_status,
        side=side,
        quote_price=quote_price,
        entry_ts=entry_ts,
        expiry_ts=expiry_ts,
        later_rows=later_rows,
        within_ttl=within_ttl,
        distances=distances,
    )
    return {
        "paper_intent_id": intent.get("paper_intent_id"),
        "virtual_order_id": intent.get("virtual_order_id"),
        "contract_ticker": ticker,
        "side": side,
        "quote_price": json_float(quote_price),
        "ttl_seconds": ttl_seconds,
        "entry_observed_at_utc": intent.get("entry_observed_at_utc"),
        "order_expires_at_utc": intent.get("order_expires_at_utc"),
        "paper_fill_status": paper_status,
        "future_snapshot_within_ttl_count": len(within_ttl),
        "future_snapshot_after_expiry_count": len(after_expiry),
        "seconds_to_first_later_snapshot": json_float(
            first_later_ts - entry_ts
            if first_later_ts is not None and entry_ts is not None and math.isfinite(first_later_ts)
            else None
        ),
        "min_ask_distance_to_touch": json_float(min(distances) if distances else None),
        "first_touch_utc": first_touch,
        "diagnostic_reason": reason,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "usable": False,
    }


def ask_distances(
    rows: Sequence[Mapping[str, Any]], *, side: str, quote_price: float | None
) -> list[float]:
    if side not in {"yes", "no"} or quote_price is None:
        return []
    distances: list[float] = []
    for row in rows:
        ask = as_float(row.get(f"best_{side}_ask"))
        if ask is not None:
            distances.append(ask - quote_price)
    return distances


def first_touch_utc(
    rows: Sequence[Mapping[str, Any]], *, side: str, quote_price: float | None
) -> str | None:
    if side not in {"yes", "no"} or quote_price is None:
        return None
    for row in rows:
        ask = as_float(row.get(f"best_{side}_ask"))
        if ask is not None and ask <= quote_price:
            return str(row.get("observed_at_utc") or "") or None
    return None


def diagnostic_reason(
    *,
    paper_status: str,
    side: str,
    quote_price: float | None,
    entry_ts: float | None,
    expiry_ts: float | None,
    later_rows: Sequence[Mapping[str, Any]],
    within_ttl: Sequence[Mapping[str, Any]],
    distances: Sequence[float],
) -> str:
    if paper_status == "paper_filled_from_later_public_touch":
        return "paper_touch_fill_observed"
    if side not in {"yes", "no"} or quote_price is None:
        return "invalid_side_or_quote_price"
    if entry_ts is None or expiry_ts is None:
        return "missing_entry_or_expiry_time"
    if not later_rows:
        return "awaiting_later_public_snapshot"
    if not within_ttl:
        return "ttl_shorter_than_snapshot_cadence"
    if not distances:
        return "side_ask_missing_within_ttl"
    if min(distances) <= 0:
        return "touch_seen_but_label_not_filled"
    if paper_status == "paper_expired_unfilled_no_public_touch":
        return "quote_not_reached_within_ttl"
    return "awaiting_expiry_or_later_label"


def build_summary(
    *,
    paper_fill: Mapping[str, Any],
    micro: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    reason_counts = Counter(str(row.get("diagnostic_reason") or "unknown") for row in rows)
    ttl_values = [
        int_value(row.get("ttl_seconds")) for row in rows if int_value(row.get("ttl_seconds")) > 0
    ]
    first_later_seconds = [
        float(row["seconds_to_first_later_snapshot"])
        for row in rows
        if isinstance(row.get("seconds_to_first_later_snapshot"), (int, float))
    ]
    labeled = [row for row in rows if row.get("paper_fill_status") != "paper_intent_open"]
    fills = [
        row
        for row in rows
        if row.get("paper_fill_status") == "paper_filled_from_later_public_touch"
    ]
    timeouts = [
        row
        for row in rows
        if row.get("paper_fill_status") == "paper_expired_unfilled_no_public_touch"
    ]
    mismatch_count = reason_counts["ttl_shorter_than_snapshot_cadence"]
    recommended_ttl = recommended_ttl_seconds(first_later_seconds, ttl_values)
    max_ttl = max(ttl_values) if ttl_values else None
    current_ttl_aligned = (
        recommended_ttl is not None and max_ttl is not None and max_ttl >= recommended_ttl
    )
    active_reason_counts = Counter(reason_counts)
    if current_ttl_aligned:
        active_reason_counts.pop("ttl_shorter_than_snapshot_cadence", None)
    return {
        "paper_fill_safe": safe_research_artifact(paper_fill),
        "paper_fill_status": paper_fill.get("status"),
        "microstructure_safe": safe_research_artifact(micro),
        "microstructure_status": micro.get("status"),
        "paper_intent_count": len(rows),
        "paper_fill_label_count": len(labeled),
        "paper_filled_count": len(fills),
        "paper_timeout_count": len(timeouts),
        "open_paper_intent_count": len(rows) - len(labeled),
        "paper_fill_rate": json_float(len(fills) / len(labeled) if labeled else None),
        "future_snapshot_within_ttl_intent_count": sum(
            1 for row in rows if int_value(row.get("future_snapshot_within_ttl_count")) > 0
        ),
        "ttl_cadence_mismatch_count": mismatch_count,
        "active_ttl_cadence_mismatch_count": 0 if current_ttl_aligned else mismatch_count,
        "current_ttl_cadence_aligned": current_ttl_aligned,
        "quote_not_reached_count": reason_counts["quote_not_reached_within_ttl"],
        "awaiting_later_snapshot_count": reason_counts["awaiting_later_public_snapshot"],
        "side_ask_missing_count": reason_counts["side_ask_missing_within_ttl"],
        "diagnostic_reason_counts": dict(sorted(reason_counts.items())),
        "min_ttl_seconds": min(ttl_values) if ttl_values else None,
        "median_ttl_seconds": median(ttl_values),
        "max_ttl_seconds": max_ttl,
        "median_seconds_to_first_later_snapshot": json_float(median(first_later_seconds)),
        "p90_seconds_to_first_later_snapshot": json_float(percentile(first_later_seconds, 0.90)),
        "recommended_ttl_seconds": recommended_ttl,
        "fill_clock_primary_bottleneck": primary_bottleneck(active_reason_counts),
        "real_exchange_fill_label_count": 0,
        "usable_row_count": 0,
    }


def recommended_ttl_seconds(
    first_later_seconds: Sequence[float], ttl_values: Sequence[int]
) -> int | None:
    if not first_later_seconds:
        return max(ttl_values, default=600) if ttl_values else 600
    p90 = percentile(first_later_seconds, 0.90)
    if p90 is None:
        return max(ttl_values, default=600) if ttl_values else 600
    return int(max(600, math.ceil((p90 + 60.0) / 60.0) * 60))


def primary_bottleneck(reason_counts: Counter[str]) -> str:
    non_fill = Counter(
        {
            key: value
            for key, value in reason_counts.items()
            if key != "paper_touch_fill_observed" and value > 0
        }
    )
    if not non_fill:
        return "paper_touch_fills_observed"
    return sorted(non_fill.items(), key=lambda item: (-item[1], item[0]))[0][0]


def build_gates(summary: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        gate(
            "paper_fill_loop_safe",
            "pass" if summary.get("paper_fill_safe") is True else "blocked",
            f"Paper fill loop status: {summary.get('paper_fill_status')}.",
        ),
        gate(
            "microstructure_artifact_safe",
            "pass" if summary.get("microstructure_safe") is True else "blocked",
            f"Microstructure status: {summary.get('microstructure_status')}.",
        ),
        gate(
            "paper_intents_available",
            "pass" if int_value(summary.get("paper_intent_count")) > 0 else "blocked",
            f"{summary.get('paper_intent_count')} paper intent(s).",
        ),
        gate(
            "paper_labels_available",
            "pass" if int_value(summary.get("paper_fill_label_count")) > 0 else "warn",
            f"{summary.get('paper_fill_label_count')} paper fill/timeout label(s).",
        ),
        gate(
            "future_snapshots_inside_ttl",
            "pass"
            if int_value(summary.get("future_snapshot_within_ttl_intent_count")) > 0
            else "warn",
            f"{summary.get('future_snapshot_within_ttl_intent_count')} intent(s) had a later snapshot before TTL expiry.",
        ),
        gate(
            "paper_fills_observed",
            "pass" if int_value(summary.get("paper_filled_count")) > 0 else "blocked",
            f"{summary.get('paper_filled_count')} paper touch fill(s).",
        ),
        gate(
            "no_real_exchange_fill_claim",
            "pass" if int_value(summary.get("real_exchange_fill_label_count")) == 0 else "fail",
            "Diagnostic keeps public-snapshot paper labels separate from real exchange fills.",
        ),
        gate(
            "no_account_order_execution_paths",
            "pass",
            "This diagnostic never touches account or order endpoints.",
        ),
    ]


def report_status(summary: Mapping[str, Any]) -> str:
    if summary.get("paper_fill_safe") is not True or summary.get("microstructure_safe") is not True:
        return "passive_liquidity_fill_clock_diagnostic_blocked_unsafe_inputs"
    if int_value(summary.get("paper_intent_count")) <= 0:
        return "passive_liquidity_fill_clock_diagnostic_blocked_no_paper_intents"
    if int_value(summary.get("paper_filled_count")) > 0:
        return "passive_liquidity_fill_clock_diagnostic_ready_with_paper_fills"
    if int_value(summary.get("ttl_cadence_mismatch_count")) > 0:
        return "passive_liquidity_fill_clock_diagnostic_ready_ttl_cadence_mismatch"
    return "passive_liquidity_fill_clock_diagnostic_ready_no_paper_fills"


def next_action(status: str, summary: Mapping[str, Any]) -> dict[str, str]:
    if status.endswith("ttl_cadence_mismatch"):
        return {
            "name": "kalshi_passive_liquidity_ttl_cadence_alignment",
            "why": (
                "Paper maker intents are expiring before the next public snapshot can observe a touch. "
                f"Recommended minimum TTL: {summary.get('recommended_ttl_seconds')} seconds."
            ),
            "stop_condition": "Stop before treating timeout-only paper labels as evidence against passive fills.",
        }
    if status.endswith("ready_with_paper_fills"):
        return {
            "name": "kalshi_passive_liquidity_paper_fill_falsification",
            "why": "Paper touch fills exist; keep routing them through OOS/FDR and adverse-selection checks.",
            "stop_condition": "Stop before calling public-snapshot paper fills real exchange fills.",
        }
    return {
        "name": "kalshi_passive_liquidity_paper_fill_accumulation",
        "why": "Passive liquidity still needs paper fill labels before FDR can test maker-fill EV.",
        "stop_condition": "Stop before lowering fill/OOS/FDR gates.",
    }


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def median(values: Sequence[float | int]) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(max(math.ceil(len(ordered) * q) - 1, 0), len(ordered) - 1)
    return ordered[index]


def write_outputs(report: Mapping[str, Any], *, out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-passive-liquidity-fill-clock-diagnostic.json"
    md_path = out_dir / "kalshi-passive-liquidity-fill-clock-diagnostic.md"
    csv_path = out_dir / "kalshi-passive-liquidity-fill-clock-diagnostic.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("diagnostic_rows", []), csv_path)

    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
    }
    if path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-passive-liquidity-fill-clock-diagnostic.json"
        latest_md = MACRO_DIR / "latest-kalshi-passive-liquidity-fill-clock-diagnostic.md"
        latest_csv = MACRO_DIR / "latest-kalshi-passive-liquidity-fill-clock-diagnostic.csv"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        write_csv(report.get("diagnostic_rows", []), latest_csv)
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
        "# Kalshi Passive-Liquidity Fill Clock Diagnostic",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Paper intents: `{summary.get('paper_intent_count')}`",
        f"- Paper labels: `{summary.get('paper_fill_label_count')}`",
        f"- Paper fills: `{summary.get('paper_filled_count')}`",
        f"- Future snapshots inside TTL: `{summary.get('future_snapshot_within_ttl_intent_count')}`",
        f"- TTL/cadence mismatches: `{summary.get('ttl_cadence_mismatch_count')}`",
        f"- Active TTL/cadence mismatches: `{summary.get('active_ttl_cadence_mismatch_count')}`",
        f"- Current TTL cadence aligned: `{summary.get('current_ttl_cadence_aligned')}`",
        f"- Median seconds to first later snapshot: `{summary.get('median_seconds_to_first_later_snapshot')}`",
        f"- Recommended TTL seconds: `{summary.get('recommended_ttl_seconds')}`",
        f"- Primary bottleneck: `{summary.get('fill_clock_primary_bottleneck')}`",
        "",
        "## Gates",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for item in report.get("gates", []):
        if isinstance(item, Mapping):
            lines.append(
                f"| `{item.get('name')}` | `{item.get('status')}` | {item.get('reason')} |"
            )
    lines.extend(
        [
            "",
            "## Reason Counts",
            "",
            "| Reason | Count |",
            "| --- | ---: |",
        ]
    )
    for reason, count in dict(summary.get("diagnostic_reason_counts") or {}).items():
        lines.append(f"| `{reason}` | {count} |")
    next_step = report.get("next_action") if isinstance(report.get("next_action"), Mapping) else {}
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            f"- Name: `{next_step.get('name')}`",
            f"- Why: {next_step.get('why')}",
            f"- Stop condition: {next_step.get('stop_condition')}",
            "",
            "## Guardrail",
            "",
            "This diagnostic is research-only and separates public-snapshot paper fills from real exchange fills.",
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
    parser.add_argument("--paper-fill-path", type=Path, default=DEFAULT_PAPER_FILL_PATH)
    parser.add_argument("--microstructure-path", type=Path, default=DEFAULT_MICROSTRUCTURE_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_passive_liquidity_fill_clock_diagnostic(
        paper_fill_path=args.paper_fill_path,
        microstructure_path=args.microstructure_path,
    )
    if args.write:
        paths = write_outputs(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
