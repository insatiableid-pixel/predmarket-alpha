#!/usr/bin/env python3
"""Gate passive-liquidity sports evidence using counterfactual public snapshots."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.kalshi_execution_cost import GENERAL_MAKER_FEE_RATE, kalshi_trade_fee  # noqa: E402
from predmarket.shared_helpers import (  # noqa: E402
    json_float,
    outside_repo,
    read_json_or_empty,
    safe_research_artifact,
    safety_flags,
    sha256_or_none,
    timestamp,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_MICROSTRUCTURE_PATH = (
    MACRO_DIR / "latest-kalshi-sports-microstructure-observation-loop.json"
)
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-passive-liquidity-provision-evidence-gate-latest"
DEFAULT_TTL_SECONDS = 180
CSV_FIELDS = [
    "virtual_order_id",
    "feature_family",
    "snapshot_id",
    "contract_ticker",
    "side",
    "quote_rule",
    "quote_price",
    "quote_size_contracts",
    "post_only_assumed",
    "ttl_seconds",
    "order_expires_at_utc",
    "best_ask_at_entry",
    "spread_at_entry",
    "maker_fee_estimate",
    "taker_fee_estimate",
    "maker_fee_savings",
    "fill_proxy_status",
    "label_status",
    "usable",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_passive_liquidity_provision_evidence_gate(
    *,
    microstructure_path: Path = DEFAULT_MICROSTRUCTURE_PATH,
    generated_utc: str | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    micro = read_json_or_empty(microstructure_path)
    rows = microstructure_rows(micro)
    virtual_orders = build_virtual_orders(rows, ttl_seconds=ttl_seconds)
    summary = build_summary(micro=micro, rows=rows, virtual_orders=virtual_orders)
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
        "inputs": {
            "microstructure_path": str(microstructure_path),
            "microstructure_sha256": sha256_or_none(microstructure_path),
            "microstructure_status": micro.get("status"),
            "ttl_seconds": ttl_seconds,
        },
        "method": {
            "hypothesis": "Passive sports quotes may earn positive maker EV after timeout and adverse selection.",
            "fill_policy": "Public orderbooks can provide would-touch proxies only; real maker fills remain unavailable here.",
            "boundary": "This gate never submits quotes, creates orders, reads accounts, sizes stakes, or emits EV rows.",
        },
        "summary": summary,
        "gates": gates,
        "virtual_order_rows": virtual_orders,
        "next_action": next_action(status),
        "safety": safety_flags(),
    }


def microstructure_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = observation_history_rows(report)
    if rows:
        return rows
    packet = (
        report.get("observation_packet")
        if isinstance(report.get("observation_packet"), Mapping)
        else {}
    )
    rows = packet.get("rows") if isinstance(packet.get("rows"), list) else []
    if rows:
        return [dict(row) for row in rows if isinstance(row, Mapping)]
    sample = (
        report.get("observation_rows_sample")
        if isinstance(report.get("observation_rows_sample"), list)
        else []
    )
    return [dict(row) for row in sample if isinstance(row, Mapping)]


def observation_history_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    inputs = report.get("inputs") if isinstance(report.get("inputs"), Mapping) else {}
    observation_dir = Path(str(inputs.get("observation_dir") or ""))
    if not observation_dir or not outside_repo(observation_dir, CONTROL_REPO):
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(observation_dir.glob("*.json")) if observation_dir.is_dir() else []:
        payload = read_json_or_empty(path)
        if not safe_research_artifact(payload):
            continue
        raw_rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        rows.extend(dict(row) for row in raw_rows if isinstance(row, Mapping))
    packet = (
        report.get("observation_packet")
        if isinstance(report.get("observation_packet"), Mapping)
        else {}
    )
    raw_current = packet.get("rows") if isinstance(packet.get("rows"), list) else []
    rows.extend(dict(row) for row in raw_current if isinstance(row, Mapping))
    labels = label_rows_from_report(report)
    return attach_labels(dedupe_rows(rows), labels)


def label_rows_from_report(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    inputs = report.get("inputs") if isinstance(report.get("inputs"), Mapping) else {}
    label_dir = Path(str(inputs.get("label_dir") or ""))
    if label_dir and outside_repo(label_dir, CONTROL_REPO):
        for path in sorted(label_dir.glob("*.json")) if label_dir.is_dir() else []:
            payload = read_json_or_empty(path)
            if not safe_research_artifact(payload):
                continue
            raw_rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
            rows.extend(dict(row) for row in raw_rows if isinstance(row, Mapping))
    packet = report.get("label_packet") if isinstance(report.get("label_packet"), Mapping) else {}
    raw_current = packet.get("rows") if isinstance(packet.get("rows"), list) else []
    rows.extend(dict(row) for row in raw_current if isinstance(row, Mapping))
    return dedupe_rows(rows)


def attach_labels(
    rows: Sequence[Mapping[str, Any]], labels: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    by_snapshot = {
        str(label.get("snapshot_id") or ""): label
        for label in labels
        if str(label.get("snapshot_id") or "")
    }
    output: list[dict[str, Any]] = []
    for row in rows:
        label = by_snapshot.get(str(row.get("snapshot_id") or ""))
        if label is None:
            output.append(dict(row))
            continue
        merged = dict(row)
        for key in (
            "label_status",
            "settlement_yes_outcome",
            "yes_outcome",
            "side_outcome",
            "settled_time",
            "label_source",
        ):
            merged[key] = label.get(key)
        output.append(merged)
    return output


def dedupe_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        key = str(row.get("snapshot_id") or "").strip()
        if not key:
            key = f"{row.get('contract_ticker')}|{row.get('observed_at_utc')}|{index}"
        by_key[key] = dict(row)
    return sorted(
        by_key.values(),
        key=lambda row: (
            str(row.get("contract_ticker") or ""),
            str(row.get("observed_at_utc") or ""),
            str(row.get("snapshot_id") or ""),
        ),
    )


def build_virtual_orders(
    rows: Sequence[Mapping[str, Any]], *, ttl_seconds: int
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    by_ticker: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_ticker.setdefault(str(row.get("contract_ticker") or ""), []).append(row)
    for ticker_rows in by_ticker.values():
        ordered = sorted(ticker_rows, key=lambda row: str(row.get("observed_at_utc") or ""))
        for index, row in enumerate(ordered):
            future_rows = ordered[index + 1 :]
            for side in ("yes", "no"):
                output.append(
                    virtual_order_row(
                        row,
                        side=side,
                        ttl_seconds=ttl_seconds,
                        future_rows=future_rows,
                    )
                )
    return [row for row in output if row]


def virtual_order_row(
    row: Mapping[str, Any],
    *,
    side: str,
    ttl_seconds: int,
    future_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    quote_price = quote_price_for_side(row, side)
    if quote_price is None:
        return {}
    best_ask = as_float(row.get(f"best_{side}_ask"))
    spread = as_float(row.get(f"{side}_spread"))
    maker_fee = kalshi_trade_fee(price=quote_price, fee_rate=GENERAL_MAKER_FEE_RATE)
    taker_fee = kalshi_trade_fee(price=quote_price)
    observed = str(row.get("observed_at_utc") or "")
    order_expires = expiry(observed, ttl_seconds)
    fill_proxy = fill_proxy_for_virtual_bid(
        future_rows,
        side=side,
        quote_price=quote_price,
        observed_at=observed,
        ttl_seconds=ttl_seconds,
    )
    mid_at_entry = side_mid(row, side)
    mid_after_touch = side_mid(fill_proxy.get("touch_row", {}), side)
    mid_at_expiry = side_mid(fill_proxy.get("expiry_row", {}), side)
    virtual_id = hashlib.sha256(
        f"{row.get('snapshot_id')}|{side}|{quote_price}|{ttl_seconds}".encode()
    ).hexdigest()
    return {
        "virtual_order_id": virtual_id,
        "hypothesis_id": "passive_liquidity_provision",
        "feature_family": "passive_liquidity_provision",
        "snapshot_id": row.get("snapshot_id"),
        "contract_ticker": row.get("contract_ticker"),
        "side": side,
        "quote_rule": "improve_best_bid_one_tick",
        "quote_price": json_float(quote_price),
        "quote_size_contracts": 1,
        "post_only_assumed": True,
        "ttl_seconds": ttl_seconds,
        "order_expires_at_utc": order_expires,
        "best_ask_at_entry": json_float(best_ask),
        "spread_at_entry": json_float(spread),
        "maker_fee_estimate": json_float(maker_fee),
        "taker_fee_estimate": json_float(taker_fee),
        "maker_fee_savings": json_float(taker_fee - maker_fee),
        "fill_proxy_status": fill_proxy["status"],
        "first_touch_utc": fill_proxy.get("first_touch_utc"),
        "fill_proxy_latency_seconds": json_float(fill_proxy.get("fill_proxy_latency_seconds")),
        "mid_at_entry": json_float(mid_at_entry),
        "mid_after_touch": json_float(mid_after_touch),
        "mid_at_expiry": json_float(mid_at_expiry),
        "settlement_yes_outcome": None,
        "adverse_selection_mid_delta": json_float(
            mid_after_touch - mid_at_entry
            if mid_after_touch is not None and mid_at_entry is not None
            else None
        ),
        "counterfactual_net_ev_if_filled": None,
        "counterfactual_net_ev_with_timeout": None,
        "label_status": "proxy_only_no_real_fill_label",
        "usable": False,
    }


def fill_proxy_for_virtual_bid(
    rows: Sequence[Mapping[str, Any]],
    *,
    side: str,
    quote_price: float,
    observed_at: str,
    ttl_seconds: int,
) -> dict[str, Any]:
    observed_ts = timestamp(observed_at)
    if observed_ts is None:
        return {"status": "insufficient_future_snapshots"}
    expiry_ts = observed_ts + max(1, int(ttl_seconds))
    candidates: list[Mapping[str, Any]] = []
    for row in rows:
        row_ts = timestamp(row.get("observed_at_utc"))
        if row_ts is None or row_ts <= observed_ts or row_ts > expiry_ts:
            continue
        candidates.append(row)
    if not candidates:
        return {"status": "insufficient_future_snapshots"}
    for row in candidates:
        best_ask = as_float(row.get(f"best_{side}_ask"))
        if best_ask is not None and best_ask <= quote_price:
            return {
                "status": "would_touch_within_ttl",
                "touch_row": row,
                "expiry_row": candidates[-1],
                "first_touch_utc": row.get("observed_at_utc"),
                "fill_proxy_latency_seconds": (timestamp(row.get("observed_at_utc")) or 0.0)
                - observed_ts,
            }
    return {"status": "not_touched_within_observed_ttl", "expiry_row": candidates[-1]}


def side_mid(row: Mapping[str, Any], side: str) -> float | None:
    if side == "yes":
        return as_float(row.get("yes_mid"))
    bid = as_float(row.get("best_no_bid"))
    ask = as_float(row.get("best_no_ask"))
    return (bid + ask) / 2.0 if bid is not None and ask is not None else None


def quote_price_for_side(row: Mapping[str, Any], side: str) -> float | None:
    bid = as_float(row.get(f"best_{side}_bid"))
    ask = as_float(row.get(f"best_{side}_ask"))
    if bid is None or ask is None:
        return None
    price = min(ask - 0.01, bid + 0.01)
    return round(price, 4) if 0.0 < price < ask and price < 1.0 else None


def expiry(observed_at: str, ttl_seconds: int) -> str | None:
    ts = timestamp(observed_at)
    if ts is None:
        return None
    return (
        (datetime.fromtimestamp(ts, UTC) + timedelta(seconds=max(1, int(ttl_seconds))))
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def build_summary(
    *,
    micro: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    virtual_orders: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    proxy_labeled = [
        row
        for row in virtual_orders
        if row.get("fill_proxy_status")
        in {"would_touch_within_ttl", "not_touched_within_observed_ttl"}
    ]
    adverse_selection_windows = [
        row
        for row in virtual_orders
        if row.get("mid_at_entry") is not None and row.get("mid_at_expiry") is not None
    ]
    return {
        "microstructure_safe": safe_research_artifact(micro),
        "microstructure_status": micro.get("status"),
        "microstructure_row_count": len(rows),
        "distinct_contract_count": len({row.get("contract_ticker") for row in rows}),
        "virtual_order_count": len(virtual_orders),
        "counterfactual_fill_proxy_label_count": len(proxy_labeled),
        "would_touch_proxy_count": sum(
            1 for row in virtual_orders if row.get("fill_proxy_status") == "would_touch_within_ttl"
        ),
        "adverse_selection_window_count": len(adverse_selection_windows),
        "real_fill_label_count": 0,
        "usable_row_count": 0,
    }


def build_gates(summary: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        gate(
            "hypothesis_family_registered",
            "pass",
            "passive_liquidity_provision is registered separately from directional signals.",
        ),
        gate(
            "virtual_quote_plan_safe",
            "pass",
            "Rows are counterfactual and post-only-assumed; no order path exists.",
        ),
        gate(
            "public_orderbook_sequence_sufficient",
            "pass" if int(summary.get("microstructure_row_count") or 0) > 0 else "blocked",
            f"{summary.get('microstructure_row_count')} microstructure row(s).",
        ),
        gate(
            "counterfactual_fill_proxy_labels_available",
            "pass"
            if int(summary.get("counterfactual_fill_proxy_label_count") or 0) > 0
            else "blocked",
            f"{summary.get('counterfactual_fill_proxy_label_count')} counterfactual touch/timeout labels.",
        ),
        gate(
            "maker_fee_model_available",
            "pass",
            "Kalshi maker/taker fee model is available locally.",
        ),
        gate(
            "adverse_selection_window_available",
            "pass" if int(summary.get("adverse_selection_window_count") or 0) > 0 else "blocked",
            f"{summary.get('adverse_selection_window_count')} adverse-selection window(s).",
        ),
        gate(
            "net_ev_after_adverse_selection_positive",
            "blocked",
            "Cannot evaluate without proxy or real fill labels.",
        ),
        gate("fdr_q_value_lte_0_10", "blocked", "Cannot run FDR without labeled trials."),
        gate(
            "current_depth_support_from_ghost_diagnostic",
            "pass",
            "Current depth preflight is consumed upstream by sequencing.",
        ),
        gate(
            "real_fill_labels_available",
            "blocked",
            "Public orderbooks do not prove real maker queue fills.",
        ),
        gate(
            "no_account_order_execution_paths",
            "pass",
            "This report never touches account or order endpoints.",
        ),
    ]


def report_status(summary: Mapping[str, Any]) -> str:
    if int(summary.get("microstructure_row_count") or 0) <= 0:
        return "passive_liquidity_provision_blocked_no_microstructure_snapshots"
    return "passive_liquidity_provision_blocked_proxy_only_no_real_fill_labels"


def next_action(status: str) -> dict[str, str]:
    return {
        "name": "kalshi_passive_liquidity_touch_sequence_accumulation",
        "why": "Maker evidence needs repeated post-entry public snapshots and eventually real fill labels.",
        "stop_condition": "Stop before submitting quotes, simulating account fills as facts, or emitting EV rows.",
    }


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def write_outputs(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-passive-liquidity-provision-evidence-gate.json"
    md_path = out_dir / "kalshi-passive-liquidity-provision-evidence-gate.md"
    csv_path = out_dir / "kalshi-passive-liquidity-provision-evidence-gate.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("virtual_order_rows", []), csv_path)
    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
    }
    if _path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-passive-liquidity-provision-evidence-gate.json"
        latest_md = MACRO_DIR / "latest-kalshi-passive-liquidity-provision-evidence-gate.md"
        latest_csv = MACRO_DIR / "latest-kalshi-passive-liquidity-provision-evidence-gate.csv"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        write_csv(report.get("virtual_order_rows", []), latest_csv)
        paths.update(
            {
                "latest_json_path": str(latest_json),
                "latest_markdown_path": str(latest_md),
                "latest_csv_path": str(latest_csv),
            }
        )
    return paths


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Passive-Liquidity Provision Evidence Gate",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Virtual orders: `{summary.get('virtual_order_count')}`",
        f"- Real fill labels: `{summary.get('real_fill_label_count')}`",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for item in report.get("gates", []):
        if isinstance(item, Mapping):
            lines.append(
                f"| `{item.get('name')}` | `{item.get('status')}` | {item.get('reason')} |"
            )
    lines.append("")
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microstructure-path", type=Path, default=DEFAULT_MICROSTRUCTURE_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--ttl-seconds", type=int, default=DEFAULT_TTL_SECONDS)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_passive_liquidity_provision_evidence_gate(
        microstructure_path=args.microstructure_path,
        ttl_seconds=args.ttl_seconds,
    )
    if args.write:
        print(
            json.dumps(
                {"status": report["status"], **write_outputs(report, args.out_dir)},
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
