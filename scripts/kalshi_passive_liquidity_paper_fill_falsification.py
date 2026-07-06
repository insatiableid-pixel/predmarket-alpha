#!/usr/bin/env python3
"""Falsify passive-liquidity paper fill labels before any promotion."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.kalshi_execution_cost import (  # noqa: E402
    GENERAL_MAKER_FEE_RATE,
    GENERAL_TAKER_FEE_RATE,
    kalshi_trade_fee,
)
from predmarket.shared_helpers import (  # noqa: E402
    benjamini_hochberg,
    chronological_split_index,
    json_float,
    outside_repo,
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
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-passive-liquidity-paper-fill-falsification-latest"
DEFAULT_MIN_INDEPENDENT_LABELS = 30
DEFAULT_MIN_OOS_LABELS = 10
DEFAULT_MIN_OOS_FILLS = 3
DEFAULT_TEST_FRACTION = 0.30
DEFAULT_FDR_ALPHA = 0.10

CSV_FIELDS = [
    "model_id",
    "status",
    "maker_side",
    "independent_label_count",
    "oos_label_count",
    "oos_fill_count",
    "oos_timeout_count",
    "oos_net_ev_count",
    "fill_rate",
    "maker_fill_net_ev_after_adverse_selection",
    "p_value",
    "q_value",
    "usable",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_passive_liquidity_paper_fill_falsification(
    *,
    paper_fill_path: Path = DEFAULT_PAPER_FILL_PATH,
    microstructure_path: Path = DEFAULT_MICROSTRUCTURE_PATH,
    generated_utc: str | None = None,
    min_independent_labels: int = DEFAULT_MIN_INDEPENDENT_LABELS,
    min_oos_labels: int = DEFAULT_MIN_OOS_LABELS,
    min_oos_fills: int = DEFAULT_MIN_OOS_FILLS,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    fdr_alpha: float = DEFAULT_FDR_ALPHA,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    paper_fill = read_json_or_empty(paper_fill_path)
    micro = read_json_or_empty(microstructure_path)
    micro_index = microstructure_index(micro)
    trials, invalid_trials = build_trials(paper_fill, micro_index)
    evaluations = evaluate_models(
        trials,
        min_independent_labels=min_independent_labels,
        min_oos_labels=min_oos_labels,
        min_oos_fills=min_oos_fills,
        test_fraction=test_fraction,
        fdr_alpha=fdr_alpha,
    )
    summary = build_summary(
        paper_fill=paper_fill,
        micro=micro,
        trials=trials,
        invalid_trials=invalid_trials,
        evaluations=evaluations,
        min_independent_labels=min_independent_labels,
        min_oos_labels=min_oos_labels,
        min_oos_fills=min_oos_fills,
    )
    gates = build_gates(summary, evaluations)
    status = report_status(summary, evaluations)
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
            "purpose": "Test passive maker paper fill/timeout labels without treating them as real exchange fills.",
            "label_boundary": "paper_fill_status values are derived from later public orderbook snapshots, not account/order fills.",
            "acceptance_metric": "maker_fill_net_ev_after_adverse_selection on OOS filled paper trials",
            "split": "chronological holdout by paper intent entry time",
            "fdr": "Benjamini-Hochberg q-values across all/yes/no maker-side evaluators",
            "promotion_boundary": "Research candidate only; no calibrated probability, EV ledger row, stake, or order.",
        },
        "summary": summary,
        "gates": gates,
        "evaluations": evaluations,
        "paper_trial_rows_sample": trials[:50],
        "invalid_trial_rows_sample": invalid_trials[:50],
        "next_action": next_action(status),
        "safety": safety_flags(),
    }


def microstructure_index(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = microstructure_rows(report)
    return {
        str(row.get("snapshot_id") or ""): dict(row)
        for row in rows
        if str(row.get("snapshot_id") or "")
    }


def microstructure_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    inputs = report.get("inputs") if isinstance(report.get("inputs"), Mapping) else {}
    observation_dir = Path(str(inputs.get("observation_dir") or ""))
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
    sample = (
        report.get("observation_rows_sample")
        if isinstance(report.get("observation_rows_sample"), list)
        else []
    )
    rows.extend(dict(row) for row in sample if isinstance(row, Mapping))
    deduped: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        key = str(row.get("snapshot_id") or "")
        if not key:
            key = f"{row.get('contract_ticker')}|{row.get('observed_at_utc')}|{index}"
        deduped[key] = row
    return sorted(deduped.values(), key=lambda row: str(row.get("observed_at_utc") or ""))


def build_trials(
    paper_fill: Mapping[str, Any],
    micro_index: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    intents = {
        str(row.get("paper_intent_id") or ""): row
        for row in paper_fill.get("paper_intent_rows", [])
        if isinstance(row, Mapping) and str(row.get("paper_intent_id") or "")
    }
    labels = [
        row
        for row in paper_fill.get("paper_fill_label_rows", [])
        if isinstance(row, Mapping) and str(row.get("paper_intent_id") or "")
    ]
    trials: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for label in sorted(labels, key=lambda row: str(row.get("entry_observed_at_utc") or "")):
        intent = intents.get(str(label.get("paper_intent_id") or ""))
        trial = trial_from_label(label, intent=intent, micro_index=micro_index)
        if trial.get("valid_trial") is True:
            trials.append(trial)
        else:
            invalid.append(trial)
    return trials, invalid


def trial_from_label(
    label: Mapping[str, Any],
    *,
    intent: Mapping[str, Any] | None,
    micro_index: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    side = str(label.get("side") or (intent or {}).get("side") or "").lower()
    fill_status = str(label.get("paper_fill_status") or "")
    quote_price = as_float(label.get("quote_price") or (intent or {}).get("quote_price"))
    entry_snapshot_id = str((intent or {}).get("entry_snapshot_id") or "")
    label_snapshot_id = str(label.get("label_snapshot_id") or "")
    entry_row = micro_index.get(entry_snapshot_id, {})
    label_row = micro_index.get(label_snapshot_id, {})
    blockers: list[str] = []
    if intent is None:
        blockers.append("matching paper intent missing")
    if side not in {"yes", "no"}:
        blockers.append("maker side missing")
    if quote_price is None or not (0.0 < quote_price < 1.0):
        blockers.append("valid quote price missing")
    if fill_status not in {
        "paper_filled_from_later_public_touch",
        "paper_expired_unfilled_no_public_touch",
    }:
        blockers.append("recognized paper fill status missing")
    if bool(label.get("real_exchange_fill")) is True:
        blockers.append("real exchange fill label unexpectedly present")

    filled = fill_status == "paper_filled_from_later_public_touch"
    mid_at_entry = side_mid(entry_row, side) if side in {"yes", "no"} else None
    mid_after_touch = side_mid(label_row, side) if side in {"yes", "no"} and filled else None
    maker_fee = (
        kalshi_trade_fee(price=quote_price, fee_rate=GENERAL_MAKER_FEE_RATE)
        if quote_price is not None
        else None
    )
    taker_fee = (
        kalshi_trade_fee(price=quote_price, fee_rate=GENERAL_TAKER_FEE_RATE)
        if quote_price is not None
        else None
    )
    net_ev = None
    if filled:
        if mid_at_entry is None or mid_after_touch is None:
            blockers.append("filled paper label missing entry/touch midpoint")
        elif maker_fee is not None and taker_fee is not None:
            maker_fee_savings = taker_fee - maker_fee
            adverse_cost = adverse_selection_cost(
                side=side,
                mid_at_entry=mid_at_entry,
                mid_after_touch=mid_after_touch,
            )
            net_ev = maker_fee_savings - adverse_cost
    else:
        net_ev = 0.0

    return {
        "paper_intent_id": label.get("paper_intent_id"),
        "virtual_order_id": label.get("virtual_order_id"),
        "contract_ticker": label.get("contract_ticker"),
        "side": side,
        "quote_price": json_float(quote_price),
        "entry_observed_at_utc": label.get("entry_observed_at_utc"),
        "order_expires_at_utc": label.get("order_expires_at_utc"),
        "paper_fill_status": fill_status,
        "filled": filled,
        "label_source": label.get("label_source"),
        "real_exchange_fill": bool(label.get("real_exchange_fill")),
        "entry_snapshot_id": entry_snapshot_id,
        "label_snapshot_id": label_snapshot_id,
        "mid_at_entry": json_float(mid_at_entry),
        "mid_after_touch": json_float(mid_after_touch),
        "maker_fee_estimate": json_float(maker_fee),
        "taker_fee_estimate": json_float(taker_fee),
        "maker_fee_savings": json_float(
            taker_fee - maker_fee if maker_fee is not None and taker_fee is not None else None
        ),
        "maker_fill_net_ev_after_adverse_selection": json_float(net_ev),
        "decision_ts": timestamp(label.get("entry_observed_at_utc")) or 0.0,
        "valid_trial": not blockers,
        "blocker_list": blockers,
        "research_only": True,
        "execution_enabled": False,
        "usable": False,
    }


def adverse_selection_cost(*, side: str, mid_at_entry: float, mid_after_touch: float) -> float:
    delta = mid_after_touch - mid_at_entry
    if side == "yes":
        return abs(delta) if delta < 0 else 0.0
    return abs(delta) if delta < 0 else 0.0


def side_mid(row: Mapping[str, Any], side: str) -> float | None:
    if side == "yes":
        value = as_float(row.get("yes_mid"))
        if value is not None:
            return value
    bid = as_float(row.get(f"best_{side}_bid"))
    ask = as_float(row.get(f"best_{side}_ask"))
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    return None


def evaluate_models(
    trials: Sequence[Mapping[str, Any]],
    *,
    min_independent_labels: int,
    min_oos_labels: int,
    min_oos_fills: int,
    test_fraction: float,
    fdr_alpha: float,
) -> list[dict[str, Any]]:
    evaluations = [
        evaluate_side(
            trials,
            maker_side=None,
            min_independent_labels=min_independent_labels,
            min_oos_labels=min_oos_labels,
            min_oos_fills=min_oos_fills,
            test_fraction=test_fraction,
        ),
        evaluate_side(
            trials,
            maker_side="yes",
            min_independent_labels=min_independent_labels,
            min_oos_labels=min_oos_labels,
            min_oos_fills=min_oos_fills,
            test_fraction=test_fraction,
        ),
        evaluate_side(
            trials,
            maker_side="no",
            min_independent_labels=min_independent_labels,
            min_oos_labels=min_oos_labels,
            min_oos_fills=min_oos_fills,
            test_fraction=test_fraction,
        ),
    ]
    p_values = [
        (index, float(row["p_value"]))
        for index, row in enumerate(evaluations)
        if isinstance(row.get("p_value"), (int, float))
    ]
    q_values = benjamini_hochberg(p_values)
    for index, q_value in q_values.items():
        evaluations[index]["q_value"] = json_float(q_value)
        if (
            evaluations[index]["status"] == "testable_paper_fill_candidate"
            and q_value <= fdr_alpha
            and float(evaluations[index].get("maker_fill_net_ev_after_adverse_selection") or 0.0)
            > 0.0
        ):
            evaluations[index]["status"] = "research_candidate_fdr_passed"
    return evaluations


def evaluate_side(
    trials: Sequence[Mapping[str, Any]],
    *,
    maker_side: str | None,
    min_independent_labels: int,
    min_oos_labels: int,
    min_oos_fills: int,
    test_fraction: float,
) -> dict[str, Any]:
    side_trials = [row for row in trials if maker_side is None or row.get("side") == maker_side]
    independent = independent_trials(side_trials)
    split_index = chronological_split_index(len(independent), test_fraction)
    oos = independent[split_index:]
    oos_filled = [row for row in oos if row.get("filled") is True]
    net_evs = [
        float(row["maker_fill_net_ev_after_adverse_selection"])
        for row in oos_filled
        if isinstance(row.get("maker_fill_net_ev_after_adverse_selection"), (int, float))
    ]
    mean_net_ev = sum(net_evs) / len(net_evs) if net_evs else None
    p_value = net_ev_one_sided_p(net_evs) if len(net_evs) >= min_oos_fills else None
    status = "testable_paper_fill_candidate"
    if len(independent) < min_independent_labels:
        status = "blocked_insufficient_independent_paper_labels"
    elif len(oos) < min_oos_labels:
        status = "blocked_insufficient_oos_paper_labels"
    elif len(oos_filled) < min_oos_fills:
        status = "blocked_insufficient_oos_paper_fills"
    elif len(net_evs) < len(oos_filled):
        status = "blocked_missing_adverse_selection_midpoints"
    elif mean_net_ev is None or mean_net_ev <= 0.0:
        status = "testable_paper_fill_candidate_non_positive_net_ev"
    return {
        "model_id": f"passive_liquidity_paper_fill_{maker_side or 'all'}",
        "candidate_rule": "paper_maker_fill_net_ev_after_adverse_selection",
        "maker_side": maker_side or "all",
        "status": status,
        "independent_label_count": len(independent),
        "oos_label_count": len(oos),
        "oos_fill_count": len(oos_filled),
        "oos_timeout_count": len(oos) - len(oos_filled),
        "oos_net_ev_count": len(net_evs),
        "fill_rate": json_float(len(oos_filled) / len(oos) if oos else None),
        "maker_fill_net_ev_after_adverse_selection": json_float(mean_net_ev),
        "p_value": json_float(p_value),
        "q_value": None,
        "min_independent_labels": min_independent_labels,
        "min_oos_labels": min_oos_labels,
        "min_oos_fills": min_oos_fills,
        "test_fraction": test_fraction,
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
        "research_only": True,
        "execution_enabled": False,
    }


def independent_trials(trials: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(
        sorted(trials, key=lambda item: float(item.get("decision_ts") or 0.0))
    ):
        key = str(row.get("paper_intent_id") or "")
        if not key:
            key = f"{row.get('contract_ticker')}|{row.get('side')}|{row.get('entry_observed_at_utc')}|{index}"
        by_id.setdefault(key, dict(row))
    return sorted(by_id.values(), key=lambda item: float(item.get("decision_ts") or 0.0))


def net_ev_one_sided_p(net_evs: Sequence[float]) -> float | None:
    if len(net_evs) < 3:
        return None
    n = len(net_evs)
    mean = sum(net_evs) / n
    if mean <= 0:
        return 1.0
    variance = sum((value - mean) ** 2 for value in net_evs) / (n - 1)
    if variance <= 0:
        return 0.0
    se = math.sqrt(variance / n)
    if se <= 0:
        return 0.0
    t_stat = mean / se
    return 1.0 / (1.0 + math.exp(1.702 * t_stat))


def build_summary(
    *,
    paper_fill: Mapping[str, Any],
    micro: Mapping[str, Any],
    trials: Sequence[Mapping[str, Any]],
    invalid_trials: Sequence[Mapping[str, Any]],
    evaluations: Sequence[Mapping[str, Any]],
    min_independent_labels: int,
    min_oos_labels: int,
    min_oos_fills: int,
) -> dict[str, Any]:
    fdr_survivors = [
        row for row in evaluations if row.get("status") == "research_candidate_fdr_passed"
    ]
    testable = [
        row
        for row in evaluations
        if str(row.get("status") or "").startswith("testable_")
        or row.get("status") == "research_candidate_fdr_passed"
    ]
    fill_count = sum(1 for row in trials if row.get("filled") is True)
    return {
        "paper_fill_safe": safe_research_artifact(paper_fill),
        "paper_fill_status": paper_fill.get("status"),
        "microstructure_safe": safe_research_artifact(micro),
        "microstructure_status": micro.get("status"),
        "paper_intent_count": int_value(
            (
                paper_fill.get("summary") if isinstance(paper_fill.get("summary"), Mapping) else {}
            ).get("paper_intent_count")
        ),
        "paper_fill_label_count": len(trials) + len(invalid_trials),
        "valid_paper_fill_label_count": len(trials),
        "invalid_paper_fill_label_count": len(invalid_trials),
        "paper_filled_count": fill_count,
        "paper_timeout_count": len(trials) - fill_count,
        "real_exchange_fill_label_count": 0,
        "tested_hypothesis_count": len(testable),
        "fdr_survivor_count": len(fdr_survivors),
        "research_candidate_count": len(fdr_survivors),
        "min_independent_labels": min_independent_labels,
        "min_oos_labels": min_oos_labels,
        "min_oos_fills": min_oos_fills,
        "best_candidate_q_value": min(
            (
                float(row.get("q_value"))
                for row in evaluations
                if isinstance(row.get("q_value"), (int, float))
            ),
            default=None,
        ),
        "best_candidate_net_ev": max(
            (
                float(row.get("maker_fill_net_ev_after_adverse_selection"))
                for row in evaluations
                if isinstance(row.get("maker_fill_net_ev_after_adverse_selection"), (int, float))
            ),
            default=None,
        ),
    }


def build_gates(
    summary: Mapping[str, Any], evaluations: Sequence[Mapping[str, Any]]
) -> list[dict[str, str]]:
    max_independent = max(
        (int_value(row.get("independent_label_count")) for row in evaluations), default=0
    )
    max_oos = max((int_value(row.get("oos_label_count")) for row in evaluations), default=0)
    max_fills = max((int_value(row.get("oos_fill_count")) for row in evaluations), default=0)
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
            "paper_fill_labels_available",
            "pass" if int_value(summary.get("valid_paper_fill_label_count")) > 0 else "blocked",
            f"{summary.get('valid_paper_fill_label_count')} valid paper fill/timeout label(s).",
        ),
        gate(
            "paper_fills_available",
            "pass" if int_value(summary.get("paper_filled_count")) > 0 else "blocked",
            f"{summary.get('paper_filled_count')} paper touch fill label(s).",
        ),
        gate(
            "independent_paper_label_minimum",
            "pass"
            if max_independent >= int_value(summary.get("min_independent_labels"))
            else "blocked",
            f"Max independent labels: {max_independent}; required {summary.get('min_independent_labels')}.",
        ),
        gate(
            "oos_paper_label_minimum",
            "pass" if max_oos >= int_value(summary.get("min_oos_labels")) else "blocked",
            f"Max OOS labels: {max_oos}; required {summary.get('min_oos_labels')}.",
        ),
        gate(
            "oos_paper_fill_minimum",
            "pass" if max_fills >= int_value(summary.get("min_oos_fills")) else "blocked",
            f"Max OOS fills: {max_fills}; required {summary.get('min_oos_fills')}.",
        ),
        gate(
            "fdr_q_value_lte_0_10",
            "pass" if int_value(summary.get("fdr_survivor_count")) > 0 else "blocked",
            f"{summary.get('fdr_survivor_count')} FDR survivor(s).",
        ),
        gate(
            "no_real_exchange_fill_claim",
            "pass" if int_value(summary.get("real_exchange_fill_label_count")) == 0 else "fail",
            "Paper fill labels remain explicitly distinct from real exchange fills.",
        ),
        gate(
            "no_account_order_execution_paths",
            "pass",
            "This falsification artifact never touches account or order endpoints.",
        ),
    ]


def report_status(summary: Mapping[str, Any], evaluations: Sequence[Mapping[str, Any]]) -> str:
    if summary.get("paper_fill_safe") is not True or summary.get("microstructure_safe") is not True:
        return "passive_liquidity_paper_fill_falsification_blocked_unsafe_inputs"
    if int_value(summary.get("valid_paper_fill_label_count")) <= 0:
        return "passive_liquidity_paper_fill_falsification_blocked_no_paper_fill_labels"
    if int_value(summary.get("paper_filled_count")) <= 0:
        return "passive_liquidity_paper_fill_falsification_blocked_no_paper_fills"
    if int_value(summary.get("fdr_survivor_count")) > 0:
        return "passive_liquidity_paper_fill_falsification_ready_with_research_candidates"
    if any(str(row.get("status") or "").startswith("testable_") for row in evaluations):
        return "passive_liquidity_paper_fill_falsification_ready_no_research_candidates"
    return "passive_liquidity_paper_fill_falsification_blocked_insufficient_paper_fill_evidence"


def next_action(status: str) -> dict[str, str]:
    if status.endswith("ready_with_research_candidates"):
        return {
            "name": "kalshi_passive_liquidity_paper_fill_replay_gates",
            "why": "A paper-fill evaluator survived FDR; route through cost/capacity/correlation/decay before any paper stake.",
            "stop_condition": "Stop before treating paper labels as live fills or emitting an order.",
        }
    return {
        "name": "kalshi_passive_liquidity_paper_fill_label_accumulation",
        "why": "Passive liquidity needs enough paper touch fills and adverse-selection evidence before FDR can promote anything.",
        "stop_condition": "Stop before lowering fill/OOS/FDR gates or calling paper labels real fills.",
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


def write_outputs(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-passive-liquidity-paper-fill-falsification.json"
    md_path = out_dir / "kalshi-passive-liquidity-paper-fill-falsification.md"
    csv_path = out_dir / "kalshi-passive-liquidity-paper-fill-falsification.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("evaluations", []), csv_path)
    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
    }
    if path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-passive-liquidity-paper-fill-falsification.json"
        latest_md = MACRO_DIR / "latest-kalshi-passive-liquidity-paper-fill-falsification.md"
        latest_csv = MACRO_DIR / "latest-kalshi-passive-liquidity-paper-fill-falsification.csv"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        write_csv(report.get("evaluations", []), latest_csv)
        paths.update(
            {
                "latest_json_path": str(latest_json),
                "latest_markdown_path": str(latest_md),
                "latest_csv_path": str(latest_csv),
            }
        )
    return paths


def path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Passive-Liquidity Paper Fill Falsification",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Paper fill labels: `{summary.get('valid_paper_fill_label_count')}`",
        f"- Paper fills: `{summary.get('paper_filled_count')}`",
        f"- FDR survivors: `{summary.get('fdr_survivor_count')}`",
        f"- Real exchange fills claimed: `{summary.get('real_exchange_fill_label_count')}`",
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
            "| Model | Status | OOS labels | OOS fills | Mean net EV | q |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report.get("evaluations", []):
        if isinstance(row, Mapping):
            lines.append(
                f"| `{row.get('model_id')}` | `{row.get('status')}` | {row.get('oos_label_count')} | {row.get('oos_fill_count')} | {row.get('maker_fill_net_ev_after_adverse_selection')} | {row.get('q_value')} |"
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
    parser.add_argument("--paper-fill-path", type=Path, default=DEFAULT_PAPER_FILL_PATH)
    parser.add_argument("--microstructure-path", type=Path, default=DEFAULT_MICROSTRUCTURE_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--min-independent-labels", type=int, default=DEFAULT_MIN_INDEPENDENT_LABELS
    )
    parser.add_argument("--min-oos-labels", type=int, default=DEFAULT_MIN_OOS_LABELS)
    parser.add_argument("--min-oos-fills", type=int, default=DEFAULT_MIN_OOS_FILLS)
    parser.add_argument("--test-fraction", type=float, default=DEFAULT_TEST_FRACTION)
    parser.add_argument("--fdr-alpha", type=float, default=DEFAULT_FDR_ALPHA)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_passive_liquidity_paper_fill_falsification(
        paper_fill_path=args.paper_fill_path,
        microstructure_path=args.microstructure_path,
        min_independent_labels=args.min_independent_labels,
        min_oos_labels=args.min_oos_labels,
        min_oos_fills=args.min_oos_fills,
        test_fraction=args.test_fraction,
        fdr_alpha=args.fdr_alpha,
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
