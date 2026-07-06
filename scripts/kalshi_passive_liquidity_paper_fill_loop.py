#!/usr/bin/env python3
"""Persist passive-liquidity paper maker intents and label them on later snapshots."""

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
    iso_from_timestamp,
    json_float,
    outside_repo,
    path_is_within,
    read_json_or_empty,
    safe_research_artifact,
    safety_flags,
    sha256_or_none,
    timestamp,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_PASSIVE_PATH = MACRO_DIR / "latest-kalshi-passive-liquidity-provision-evidence-gate.json"
DEFAULT_MICROSTRUCTURE_PATH = (
    MACRO_DIR / "latest-kalshi-sports-microstructure-observation-loop.json"
)
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-passive-liquidity-paper-fill-loop-latest"
DEFAULT_STATE_DIR = Path("/home/mrwatson/manual_drops/kalshi_passive_liquidity_paper_fills")

INTENT_FIELDS = [
    "paper_intent_id",
    "virtual_order_id",
    "contract_ticker",
    "side",
    "quote_price",
    "quote_size_contracts",
    "entry_snapshot_id",
    "entry_observed_at_utc",
    "order_expires_at_utc",
    "ttl_seconds",
    "created_at_utc",
    "status",
    "research_only",
    "execution_enabled",
]
LABEL_FIELDS = [
    "paper_intent_id",
    "virtual_order_id",
    "contract_ticker",
    "side",
    "quote_price",
    "entry_observed_at_utc",
    "order_expires_at_utc",
    "paper_fill_status",
    "paper_fill_label_utc",
    "label_snapshot_id",
    "label_observed_at_utc",
    "label_source",
    "research_only",
    "execution_enabled",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_passive_liquidity_paper_fill_loop(
    *,
    passive_path: Path = DEFAULT_PASSIVE_PATH,
    microstructure_path: Path = DEFAULT_MICROSTRUCTURE_PATH,
    state_dir: Path = DEFAULT_STATE_DIR,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    passive = read_json_or_empty(passive_path)
    micro = read_json_or_empty(microstructure_path)
    current_snapshot_ids = current_packet_snapshot_ids(micro)
    micro_rows = microstructure_rows(micro)
    existing_intents, existing_labels = load_state(state_dir)
    existing_intent_ids = {str(row.get("paper_intent_id") or "") for row in existing_intents}
    current_intents = build_current_intents(
        passive,
        current_snapshot_ids=current_snapshot_ids,
        generated_utc=generated,
    )
    new_intents = [
        row
        for row in current_intents
        if str(row.get("paper_intent_id") or "") not in existing_intent_ids
    ]
    labeled_ids = {str(row.get("paper_intent_id") or "") for row in existing_labels}
    new_labels = label_prior_intents(
        existing_intents,
        micro_rows,
        generated_utc=generated,
        already_labeled_ids=labeled_ids,
    )
    all_intents = merge_rows(existing_intents, new_intents, key_field="paper_intent_id")
    all_labels = merge_rows(existing_labels, new_labels, key_field="paper_intent_id")
    summary = build_summary(
        passive=passive,
        micro=micro,
        state_dir=state_dir,
        current_snapshot_ids=current_snapshot_ids,
        current_intents=current_intents,
        new_intents=new_intents,
        existing_intents=existing_intents,
        all_intents=all_intents,
        existing_labels=existing_labels,
        new_labels=new_labels,
        all_labels=all_labels,
    )
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
            "passive_path": str(passive_path),
            "passive_sha256": sha256_or_none(passive_path),
            "passive_status": passive.get("status"),
            "microstructure_path": str(microstructure_path),
            "microstructure_sha256": sha256_or_none(microstructure_path),
            "microstructure_status": micro.get("status"),
            "state_dir": str(state_dir),
        },
        "method": {
            "purpose": "Start the passive maker evidence clock by persisting paper quote intents and labeling only previously persisted intents from later public snapshots.",
            "fill_label_boundary": "Labels are paper fill/timeout observations from later public orderbook snapshots, not real exchange maker fills.",
            "same_run_guard": "New intents created in this run are excluded from label generation in this run.",
            "execution_boundary": "This loop never submits quotes, creates orders, reads accounts, sizes stakes, or emits tradable probabilities.",
        },
        "summary": summary,
        "gates": gates,
        "paper_intent_rows": all_intents,
        "paper_fill_label_rows": all_labels,
        "new_paper_intent_rows": new_intents,
        "new_paper_fill_label_rows": new_labels,
        "next_action": next_action(status),
        "safety": safety_flags(),
    }


def current_packet_snapshot_ids(report: Mapping[str, Any]) -> set[str]:
    packet = (
        report.get("observation_packet")
        if isinstance(report.get("observation_packet"), Mapping)
        else {}
    )
    rows = packet.get("rows") if isinstance(packet.get("rows"), list) else []
    return {
        str(row.get("snapshot_id") or "")
        for row in rows
        if isinstance(row, Mapping) and str(row.get("snapshot_id") or "")
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
    raw_rows = packet.get("rows") if isinstance(packet.get("rows"), list) else []
    return dedupe_rows([dict(row) for row in raw_rows if isinstance(row, Mapping)])


def observation_history_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    inputs = report.get("inputs") if isinstance(report.get("inputs"), Mapping) else {}
    observation_dir = Path(str(inputs.get("observation_dir") or ""))
    rows: list[dict[str, Any]] = []
    if observation_dir and outside_repo(observation_dir, CONTROL_REPO) and observation_dir.is_dir():
        for path in sorted(observation_dir.glob("*.json")):
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
    return dedupe_rows(rows)


def build_current_intents(
    passive: Mapping[str, Any],
    *,
    current_snapshot_ids: set[str],
    generated_utc: str,
) -> list[dict[str, Any]]:
    if not current_snapshot_ids:
        return []
    raw_rows = (
        passive.get("virtual_order_rows")
        if isinstance(passive.get("virtual_order_rows"), list)
        else []
    )
    intents: list[dict[str, Any]] = []
    for row in raw_rows:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("snapshot_id") or "") not in current_snapshot_ids:
            continue
        intent = paper_intent_from_virtual_order(row, generated_utc=generated_utc)
        if intent:
            intents.append(intent)
    return sorted(intents, key=lambda item: str(item.get("paper_intent_id") or ""))


def paper_intent_from_virtual_order(
    row: Mapping[str, Any], *, generated_utc: str
) -> dict[str, Any]:
    virtual_id = str(row.get("virtual_order_id") or "")
    ticker = str(row.get("contract_ticker") or "")
    side = str(row.get("side") or "").lower()
    quote_price = as_float(row.get("quote_price"))
    expires_at = str(row.get("order_expires_at_utc") or "")
    ttl_seconds = int_value(row.get("ttl_seconds"))
    expires_ts = timestamp(expires_at)
    if (
        not virtual_id
        or not ticker
        or side not in {"yes", "no"}
        or quote_price is None
        or not (0.0 < quote_price < 1.0)
        or ttl_seconds <= 0
        or expires_ts is None
    ):
        return {}
    entry_ts = expires_ts - ttl_seconds
    paper_intent_id = f"paper-passive-{virtual_id}"
    return {
        "paper_intent_id": paper_intent_id,
        "virtual_order_id": virtual_id,
        "contract_ticker": ticker,
        "side": side,
        "quote_price": json_float(quote_price),
        "quote_size_contracts": int_value(row.get("quote_size_contracts")) or 1,
        "quote_rule": row.get("quote_rule"),
        "entry_snapshot_id": row.get("snapshot_id"),
        "entry_observed_at_utc": iso_from_timestamp(entry_ts),
        "order_expires_at_utc": expires_at,
        "ttl_seconds": ttl_seconds,
        "created_at_utc": generated_utc,
        "status": "paper_resting_intent_open",
        "label_status": "awaiting_later_public_snapshot",
        "post_only_assumed": True,
        "real_exchange_order": False,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
    }


def label_prior_intents(
    intents: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    *,
    generated_utc: str,
    already_labeled_ids: set[str],
) -> list[dict[str, Any]]:
    rows_by_ticker: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        ticker = str(row.get("contract_ticker") or "")
        if not ticker:
            continue
        rows_by_ticker.setdefault(ticker, []).append(row)
    for ticker_rows in rows_by_ticker.values():
        ticker_rows.sort(key=lambda item: timestamp(item.get("observed_at_utc")) or -1.0)
    labels: list[dict[str, Any]] = []
    for intent in intents:
        intent_id = str(intent.get("paper_intent_id") or "")
        if not intent_id or intent_id in already_labeled_ids:
            continue
        label = label_for_intent(
            intent, rows_by_ticker.get(str(intent.get("contract_ticker") or ""), []), generated_utc
        )
        if label:
            labels.append(label)
    return sorted(labels, key=lambda item: str(item.get("paper_intent_id") or ""))


def label_for_intent(
    intent: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], generated_utc: str
) -> dict[str, Any]:
    entry_ts = timestamp(intent.get("entry_observed_at_utc"))
    expiry_ts = timestamp(intent.get("order_expires_at_utc"))
    quote_price = as_float(intent.get("quote_price"))
    side = str(intent.get("side") or "").lower()
    if entry_ts is None or expiry_ts is None or quote_price is None or side not in {"yes", "no"}:
        return {}
    after_entry = [
        row for row in rows if (timestamp(row.get("observed_at_utc")) or -1.0) > entry_ts
    ]
    if not after_entry:
        return {}
    within_ttl = [
        row
        for row in after_entry
        if (timestamp(row.get("observed_at_utc")) or float("inf")) <= expiry_ts
    ]
    for row in within_ttl:
        best_ask = as_float(row.get(f"best_{side}_ask"))
        if best_ask is not None and best_ask <= quote_price:
            return paper_label(
                intent,
                row,
                status="paper_filled_from_later_public_touch",
                generated_utc=generated_utc,
            )
    if max((timestamp(row.get("observed_at_utc")) or -1.0) for row in after_entry) >= expiry_ts:
        expiry_row = first_row_at_or_after(after_entry, expiry_ts) or after_entry[-1]
        return paper_label(
            intent,
            expiry_row,
            status="paper_expired_unfilled_no_public_touch",
            generated_utc=generated_utc,
        )
    return {}


def paper_label(
    intent: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    status: str,
    generated_utc: str,
) -> dict[str, Any]:
    return {
        "paper_intent_id": intent.get("paper_intent_id"),
        "virtual_order_id": intent.get("virtual_order_id"),
        "contract_ticker": intent.get("contract_ticker"),
        "side": intent.get("side"),
        "quote_price": intent.get("quote_price"),
        "entry_observed_at_utc": intent.get("entry_observed_at_utc"),
        "order_expires_at_utc": intent.get("order_expires_at_utc"),
        "paper_fill_status": status,
        "paper_fill_label_utc": generated_utc,
        "label_snapshot_id": row.get("snapshot_id"),
        "label_observed_at_utc": row.get("observed_at_utc"),
        "label_source": "later_public_orderbook_snapshot",
        "real_exchange_fill": False,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
    }


def first_row_at_or_after(rows: Sequence[Mapping[str, Any]], ts: float) -> Mapping[str, Any] | None:
    for row in rows:
        row_ts = timestamp(row.get("observed_at_utc"))
        if row_ts is not None and row_ts >= ts:
            return row
    return None


def load_state(state_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    intents: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    if not state_dir.is_dir():
        return [], []
    for path in sorted(state_dir.glob("passive_liquidity_paper_fill_state_*.json")):
        if path.name.endswith("_latest.json"):
            continue
        payload = read_json_or_empty(path)
        if not safe_research_artifact(payload):
            continue
        raw_intents = payload.get("paper_intent_rows")
        if isinstance(raw_intents, list):
            intents.extend(dict(row) for row in raw_intents if isinstance(row, Mapping))
        raw_labels = payload.get("paper_fill_label_rows")
        if isinstance(raw_labels, list):
            labels.extend(dict(row) for row in raw_labels if isinstance(row, Mapping))
    return (
        merge_rows(intents, key_field="paper_intent_id"),
        merge_rows(labels, key_field="paper_intent_id"),
    )


def merge_rows(*row_groups: Sequence[Mapping[str, Any]], key_field: str) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for rows in row_groups:
        for row in rows:
            key = str(row.get(key_field) or "")
            if not key:
                continue
            if key not in merged:
                merged[key] = dict(row)
    return sorted(merged.values(), key=lambda item: str(item.get(key_field) or ""))


def dedupe_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        key = str(row.get("snapshot_id") or "")
        if not key:
            key = f"{row.get('contract_ticker')}|{row.get('observed_at_utc')}|{index}"
        merged[key] = dict(row)
    return sorted(
        merged.values(),
        key=lambda item: (
            str(item.get("contract_ticker") or ""),
            str(item.get("observed_at_utc") or ""),
            str(item.get("snapshot_id") or ""),
        ),
    )


def build_summary(
    *,
    passive: Mapping[str, Any],
    micro: Mapping[str, Any],
    state_dir: Path,
    current_snapshot_ids: set[str],
    current_intents: Sequence[Mapping[str, Any]],
    new_intents: Sequence[Mapping[str, Any]],
    existing_intents: Sequence[Mapping[str, Any]],
    all_intents: Sequence[Mapping[str, Any]],
    existing_labels: Sequence[Mapping[str, Any]],
    new_labels: Sequence[Mapping[str, Any]],
    all_labels: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    labeled_ids = {str(row.get("paper_intent_id") or "") for row in all_labels}
    new_intent_ids = {str(row.get("paper_intent_id") or "") for row in new_intents}
    fill_statuses = [str(row.get("paper_fill_status") or "") for row in all_labels]
    return {
        "passive_safe": safe_research_artifact(passive),
        "passive_status": passive.get("status"),
        "microstructure_safe": safe_research_artifact(micro),
        "microstructure_status": micro.get("status"),
        "state_dir_outside_repo": outside_repo(state_dir, CONTROL_REPO),
        "current_snapshot_id_count": len(current_snapshot_ids),
        "candidate_virtual_order_count": len(current_intents),
        "persisted_prior_intent_count": len(existing_intents),
        "new_paper_intent_count": len(new_intents),
        "paper_intent_count": len(all_intents),
        "open_paper_intent_count": len(
            [row for row in all_intents if str(row.get("paper_intent_id") or "") not in labeled_ids]
        ),
        "existing_paper_fill_label_count": len(existing_labels),
        "new_paper_fill_label_count": len(new_labels),
        "paper_fill_label_count": len(all_labels),
        "paper_filled_count": fill_statuses.count("paper_filled_from_later_public_touch"),
        "paper_expired_unfilled_count": fill_statuses.count(
            "paper_expired_unfilled_no_public_touch"
        ),
        "new_intent_same_run_label_count": len(labeled_ids & new_intent_ids),
        "real_exchange_fill_label_count": 0,
        "usable_row_count": 0,
    }


def build_gates(summary: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        gate(
            "passive_evidence_gate_safe",
            "pass" if summary.get("passive_safe") is True else "blocked",
            f"Passive gate status: {summary.get('passive_status')}.",
        ),
        gate(
            "microstructure_artifact_safe",
            "pass" if summary.get("microstructure_safe") is True else "blocked",
            f"Microstructure status: {summary.get('microstructure_status')}.",
        ),
        gate(
            "current_paper_quote_intents_created",
            "pass" if int_value(summary.get("new_paper_intent_count")) > 0 else "blocked",
            f"{summary.get('new_paper_intent_count')} new paper intent(s).",
        ),
        gate(
            "persisted_paper_intents_available",
            "pass" if int_value(summary.get("paper_intent_count")) > 0 else "blocked",
            f"{summary.get('paper_intent_count')} total paper intent(s).",
        ),
        gate(
            "later_snapshot_paper_fill_labels_available",
            "pass" if int_value(summary.get("paper_fill_label_count")) > 0 else "blocked",
            f"{summary.get('paper_fill_label_count')} paper fill/timeout label(s).",
        ),
        gate(
            "same_run_future_leak_prevented",
            "pass" if int_value(summary.get("new_intent_same_run_label_count")) == 0 else "fail",
            f"{summary.get('new_intent_same_run_label_count')} new intent(s) labeled in same run.",
        ),
        gate(
            "no_real_exchange_fill_claim",
            "pass" if int_value(summary.get("real_exchange_fill_label_count")) == 0 else "fail",
            "Paper labels are public-snapshot labels, not real Kalshi maker fills.",
        ),
        gate(
            "no_account_order_execution_paths",
            "pass",
            "This loop never touches account or order endpoints.",
        ),
    ]


def report_status(summary: Mapping[str, Any]) -> str:
    if summary.get("passive_safe") is not True or summary.get("microstructure_safe") is not True:
        return "passive_liquidity_paper_fill_loop_blocked_unsafe_inputs"
    if int_value(summary.get("paper_intent_count")) <= 0:
        return "passive_liquidity_paper_fill_loop_blocked_no_paper_intents"
    if int_value(summary.get("paper_fill_label_count")) > 0:
        return "passive_liquidity_paper_fill_loop_ready_with_paper_fill_labels"
    return "passive_liquidity_paper_fill_loop_accumulating_intents"


def next_action(status: str) -> dict[str, str]:
    if status.endswith("ready_with_paper_fill_labels"):
        return {
            "name": "kalshi_passive_liquidity_falsification_from_paper_fill_labels",
            "why": "Paper maker labels now exist; the passive-liquidity family can start acceptance testing without proxy labels pretending to be fills.",
            "stop_condition": "Stop before treating public-snapshot paper labels as exchange fills or promoting without FDR.",
        }
    return {
        "name": "kalshi_passive_liquidity_paper_resting_accumulation",
        "why": "The passive-liquidity clock is running, but later snapshots have not labeled enough persisted paper intents.",
        "stop_condition": "Stop before submitting live quotes, using same-run future snapshots, or lowering gates.",
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


def write_outputs(
    report: Mapping[str, Any],
    *,
    out_dir: Path = DEFAULT_OUT_DIR,
    state_dir: Path = DEFAULT_STATE_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-passive-liquidity-paper-fill-loop.json"
    md_path = out_dir / "kalshi-passive-liquidity-paper-fill-loop.md"
    intents_csv_path = out_dir / "kalshi-passive-liquidity-paper-fill-intents.csv"
    labels_csv_path = out_dir / "kalshi-passive-liquidity-paper-fill-labels.csv"
    state_stamp = str(report.get("generated_utc") or utc_now()).replace("-", "").replace(":", "")
    state_stamp = state_stamp.replace("+0000", "Z").replace("Z", "Z")
    state_path = state_dir / f"passive_liquidity_paper_fill_state_{state_stamp}.json"
    latest_state_path = state_dir / "passive_liquidity_paper_fill_state_latest.json"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("paper_intent_rows", []), intents_csv_path, INTENT_FIELDS)
    write_csv(report.get("paper_fill_label_rows", []), labels_csv_path, LABEL_FIELDS)
    state_path.write_text(text, encoding="utf-8")
    latest_state_path.write_text(text, encoding="utf-8")
    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "intent_csv_path": str(intents_csv_path),
        "label_csv_path": str(labels_csv_path),
        "state_path": str(state_path),
        "latest_state_path": str(latest_state_path),
    }
    if path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-passive-liquidity-paper-fill-loop.json"
        latest_md = MACRO_DIR / "latest-kalshi-passive-liquidity-paper-fill-loop.md"
        latest_intents_csv = MACRO_DIR / "latest-kalshi-passive-liquidity-paper-fill-intents.csv"
        latest_labels_csv = MACRO_DIR / "latest-kalshi-passive-liquidity-paper-fill-labels.csv"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        write_csv(report.get("paper_intent_rows", []), latest_intents_csv, INTENT_FIELDS)
        write_csv(report.get("paper_fill_label_rows", []), latest_labels_csv, LABEL_FIELDS)
        paths.update(
            {
                "latest_json_path": str(latest_json),
                "latest_markdown_path": str(latest_md),
                "latest_intent_csv_path": str(latest_intents_csv),
                "latest_label_csv_path": str(latest_labels_csv),
            }
        )
    return paths


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Passive-Liquidity Paper Fill Loop",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Paper intents: `{summary.get('paper_intent_count')}`",
        f"- New intents: `{summary.get('new_paper_intent_count')}`",
        f"- Open intents: `{summary.get('open_paper_intent_count')}`",
        f"- Paper fill/timeout labels: `{summary.get('paper_fill_label_count')}`",
        f"- Real exchange fill labels: `{summary.get('real_exchange_fill_label_count')}`",
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
            "> Paper labels are public-snapshot touch/timeout labels only. No Kalshi account, order, or live quote path is touched.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path, fields: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--passive-path", type=Path, default=DEFAULT_PASSIVE_PATH)
    parser.add_argument("--microstructure-path", type=Path, default=DEFAULT_MICROSTRUCTURE_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_passive_liquidity_paper_fill_loop(
        passive_path=args.passive_path,
        microstructure_path=args.microstructure_path,
        state_dir=args.state_dir,
    )
    if args.write:
        paths = write_outputs(report, out_dir=args.out_dir, state_dir=args.state_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
