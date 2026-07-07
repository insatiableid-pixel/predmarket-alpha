#!/usr/bin/env python3
"""Reconcile paper Kalshi decisions against public settled market outcomes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.paper_portfolio_risk import build_paper_portfolio_risk  # noqa: E402
from predmarket.shared_helpers import (  # noqa: E402
    bucket_time,
    gate,
    gate_counts,
    iso_time,
    manual_drop_path,
    optional_float,
    probability,
    read_json_or_empty,
    safe_research_artifact,
    safe_stamp,
    safety_flags,
    sha256_or_none,
    timestamp,
    utc_now,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_PAPER_DECISIONS_PATH = MACRO_DIR / "latest-paper-decision-candidates.json"
DEFAULT_SETTLED_SNAPSHOT_PATH = manual_drop_path(
    "kalshi_paper_settlements", "kalshi_paper_observed_markets_latest.json"
)
DEFAULT_SETTLED_RAW_DIR = manual_drop_path("kalshi_paper_settlements")
DEFAULT_OUT_DIR = MACRO_DIR / "paper-settlement-reconciliation-latest"
KALSHI_PUBLIC_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"

CSV_FIELDS = [
    "paper_decision_id",
    "contract_ticker",
    "side",
    "family_id",
    "model_id",
    "signal_key",
    "cluster_key",
    "decision_time",
    "close_time",
    "close_bucket",
    "paper_usable",
    "paper_stake",
    "paper_contract_count",
    "calibrated_probability",
    "all_in_cost",
    "predicted_outcome",
    "settled_outcome",
    "selected_side_outcome",
    "settlement_status",
    "realized_pnl",
    "realized_roi",
    "blocker_list",
]


def build_paper_settlement_reconciliation(
    *,
    paper_decisions_path: Path = DEFAULT_PAPER_DECISIONS_PATH,
    settled_snapshot_path: Path = DEFAULT_SETTLED_SNAPSHOT_PATH,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    paper = read_json_or_empty(paper_decisions_path)
    settled_snapshot = read_json_or_empty(settled_snapshot_path)
    paper_safe = safe_research_artifact(paper)
    settled_index = settled_market_index(settled_snapshot)
    rows = paper.get("candidates") if isinstance(paper.get("candidates"), list) else []
    reconciled = [
        reconcile_row(row, settled_index=settled_index, generated_utc=generated, row_index=index)
        for index, row in enumerate(rows)
        if isinstance(row, Mapping)
    ]
    policy = paper.get("policy") if isinstance(paper.get("policy"), Mapping) else {}
    paper_bankroll = optional_float(policy.get("paper_bankroll"))
    max_fraction_per_contract = optional_float(policy.get("max_fraction_per_contract"))
    portfolio_risk = build_paper_portfolio_risk(
        reconciled,
        paper_bankroll=paper_bankroll,
        max_contract_stake=paper_bankroll * max_fraction_per_contract
        if paper_bankroll is not None and max_fraction_per_contract is not None
        else None,
    )
    summary = build_summary(
        reconciled,
        paper_safe=paper_safe,
        settled_market_count=len(settled_index),
        generated_utc=generated,
        portfolio_risk=portfolio_risk,
    )
    gates = build_gates(
        paper_safe=paper_safe,
        paper_decision_count=len(rows),
        reconciled_count=len(reconciled),
        settled_market_count=len(settled_index),
        summary=summary,
    )
    status = report_status(summary, gates)
    return {
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
        "paper_sizing_only": True,
        "inputs": {
            "paper_decisions_path": str(paper_decisions_path),
            "paper_decisions_sha256": sha256_or_none(paper_decisions_path),
            "paper_decisions_status": paper.get("status"),
            "settled_snapshot_path": str(settled_snapshot_path),
            "settled_snapshot_sha256": sha256_or_none(settled_snapshot_path),
            "settled_snapshot_status": settled_snapshot.get("status"),
        },
        "method": {
            "decision_freeze_rule": "Paper rows are copied from the paper-decision artifact and keyed by a stable hash of decision fields.",
            "settlement_rule": "Outcomes come only from public Kalshi market payloads matched by exact contract ticker.",
            "pnl_rule": "Paper PnL treats paper_stake as selected-side cost: contracts = stake / all_in_cost; pnl = contracts * selected_side_outcome - stake.",
            "calibration_rule": "calibrated_probability is treated as selected-side probability, not unconditional YES probability.",
            "execution_boundary": "This artifact never submits, cancels, or approves orders and never reads account state.",
        },
        "summary": summary,
        "portfolio_risk": portfolio_risk,
        "gates": gates,
        "gate_counts": gate_counts(gates),
        "candidates": reconciled,
        "resolved_rows": [row for row in reconciled if row.get("settlement_status") == "settled"],
        "unresolved_rows": [
            row
            for row in reconciled
            if row.get("paper_usable") is True and row.get("settlement_status") != "settled"
        ],
        "next_action": next_action(status, summary),
        "safety": safety_flags(),
    }


def reconcile_row(
    row: Mapping[str, Any],
    *,
    settled_index: Mapping[str, Mapping[str, Any]],
    generated_utc: str,
    row_index: int,
) -> dict[str, Any]:
    output = dict(row)
    ticker = str(row.get("contract_ticker") or "").strip()
    side = str(row.get("side") or "").strip().lower()
    paper_usable = row.get("paper_usable") is True
    close_time = iso_time(row.get("close_time"))
    market = settled_index.get(ticker)
    yes_outcome = settlement_outcome(market) if market is not None else None
    selected_outcome = selected_side_outcome(side=side, yes_outcome=yes_outcome)
    all_in_cost = probability(row.get("all_in_cost"))
    stake = optional_float(row.get("paper_stake")) or 0.0
    contract_count = (
        stake / all_in_cost if paper_usable and all_in_cost and all_in_cost > 0 else 0.0
    )
    realized_pnl = (
        contract_count * float(selected_outcome) - stake
        if paper_usable and selected_outcome is not None and contract_count > 0
        else None
    )
    output.update(
        {
            "paper_decision_id": paper_decision_id(row, row_index=row_index),
            "side": side,
            "close_time": close_time,
            "close_bucket": str(row.get("close_bucket") or bucket_time(close_time) or "") or None,
            "predicted_outcome": predicted_yes_outcome(row),
            "settled_outcome": yes_outcome,
            "yes_outcome": yes_outcome,
            "selected_side_outcome": selected_outcome,
            "paper_contract_count": round(contract_count, 10),
            "settlement_status": settlement_status(
                row,
                generated_utc=generated_utc,
                market=market,
                yes_outcome=yes_outcome,
            ),
            "settlement_source": "public_kalshi_market_payload" if market else None,
            "settled_time": settled_time(market) if market is not None else None,
            "settlement_result": market.get("result") if market is not None else None,
            "settlement_value_dollars": market.get("settlement_value_dollars")
            if market is not None
            else None,
            "realized_pnl": round(realized_pnl, 10) if realized_pnl is not None else None,
            "realized_roi": round(realized_pnl / stake, 10)
            if realized_pnl is not None and stake > 0
            else None,
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
        }
    )
    return output


def build_summary(
    rows: Sequence[Mapping[str, Any]],
    *,
    paper_safe: bool,
    settled_market_count: int,
    generated_utc: str,
    portfolio_risk: Mapping[str, Any],
) -> dict[str, Any]:
    usable = [row for row in rows if row.get("paper_usable") is True]
    settled = [row for row in usable if row.get("settlement_status") == "settled"]
    unresolved = [row for row in usable if row.get("settlement_status") != "settled"]
    due_unresolved = [
        row for row in unresolved if is_due(row.get("close_time"), generated_utc=generated_utc)
    ]
    next_close = next_unresolved_close_time(unresolved, generated_utc=generated_utc)
    wins = sum(1 for row in settled if row.get("selected_side_outcome") == 1)
    total_stake = sum(optional_float(row.get("paper_stake")) or 0.0 for row in usable)
    settled_stake = sum(optional_float(row.get("paper_stake")) or 0.0 for row in settled)
    realized_pnl = sum(optional_float(row.get("realized_pnl")) or 0.0 for row in settled)
    by_signal = Counter(str(row.get("signal_key") or "unknown") for row in usable)
    settled_by_signal = Counter(str(row.get("signal_key") or "unknown") for row in settled)
    return {
        "paper_decisions_safe": paper_safe,
        "settled_market_count": settled_market_count,
        "candidate_count": len(rows),
        "paper_usable_count": len(usable),
        "settled_paper_usable_count": len(settled),
        "unresolved_paper_usable_count": len(unresolved),
        "due_unresolved_paper_usable_count": len(due_unresolved),
        "next_unresolved_close_time_utc": next_close,
        "winning_paper_usable_count": wins,
        "hit_rate": round(wins / len(settled), 10) if settled else None,
        "total_paper_stake": round(total_stake, 6),
        "settled_paper_stake": round(settled_stake, 6),
        "realized_pnl": round(realized_pnl, 10),
        "realized_roi": round(realized_pnl / settled_stake, 10) if settled_stake > 0 else None,
        "mean_calibration_error": mean_calibration_error(settled),
        "status_counts": dict(
            Counter(str(row.get("settlement_status") or "unknown") for row in rows)
        ),
        "usable_signal_counts": dict(sorted(by_signal.items())),
        "settled_signal_counts": dict(sorted(settled_by_signal.items())),
        "paper_portfolio_cap_status": portfolio_risk.get("cap_status"),
        "paper_portfolio_cap_breach_count": portfolio_risk.get("cap_breach_count"),
        "paper_portfolio_largest_family": portfolio_risk.get("largest_family"),
        "paper_portfolio_largest_signal": portfolio_risk.get("largest_signal"),
        "paper_portfolio_largest_cluster": portfolio_risk.get("largest_cluster"),
        "paper_portfolio_largest_contract": portfolio_risk.get("largest_contract"),
        "paper_portfolio_unresolved_stake": portfolio_risk.get("unresolved_paper_stake"),
        "paper_portfolio_settled_stake": portfolio_risk.get("settled_paper_stake"),
    }


def build_gates(
    *,
    paper_safe: bool,
    paper_decision_count: int,
    reconciled_count: int,
    settled_market_count: int,
    summary: Mapping[str, Any],
) -> list[dict[str, str]]:
    return [
        gate(
            "paper_decision_artifact_safe",
            "pass" if paper_safe else "blocked",
            "Input paper decision artifact must preserve research-only safety flags.",
        ),
        gate(
            "paper_decision_rows_available",
            "pass" if paper_decision_count else "blocked",
            f"{paper_decision_count} paper decision row(s) loaded.",
        ),
        gate(
            "reconciliation_rows_emitted",
            "pass"
            if reconciled_count == paper_decision_count and paper_decision_count
            else "blocked",
            f"{reconciled_count}/{paper_decision_count} paper decision row(s) reconciled.",
        ),
        gate(
            "settlement_snapshot_loaded",
            "pass" if settled_market_count else "warn",
            f"{settled_market_count} exact public Kalshi market payload(s) loaded.",
        ),
        gate(
            "live_execution_remains_disabled",
            "pass",
            "Reconciliation emits paper-only PnL and never calls account/order paths.",
        ),
        gate(
            "resolved_rows_ready_for_retirement",
            "pass" if int(summary.get("settled_paper_usable_count") or 0) else "warn",
            f"{summary.get('settled_paper_usable_count')} settled paper-usable row(s).",
        ),
    ]


def report_status(summary: Mapping[str, Any], gates: Sequence[Mapping[str, Any]]) -> str:
    if any(item.get("status") == "blocked" for item in gates):
        return "paper_settlement_reconciliation_blocked_missing_inputs"
    if int(summary.get("settled_paper_usable_count") or 0) > 0:
        return "paper_settlement_reconciliation_ready_with_realized_rows"
    if int(summary.get("paper_usable_count") or 0) == 0:
        return "paper_settlement_reconciliation_ready_no_paper_usable_rows"
    if int(summary.get("due_unresolved_paper_usable_count") or 0) > 0:
        return "paper_settlement_reconciliation_waiting_for_due_settlements"
    return "paper_settlement_reconciliation_waiting_for_close"


def next_action(status: str, summary: Mapping[str, Any]) -> dict[str, str]:
    if status == "paper_settlement_reconciliation_ready_with_realized_rows":
        return {
            "name": "kalshi_signal_decay_retirement",
            "why": "Resolved paper rows are available for calibration, survival, and retirement updates.",
            "stop_condition": "Stop before live execution unless live preflight and risk gates are explicitly armed.",
        }
    if status == "paper_settlement_reconciliation_waiting_for_due_settlements":
        return {
            "name": "kalshi_paper_settlement_exact_ticker_probe",
            "why": f"{summary.get('due_unresolved_paper_usable_count')} due paper row(s) still lack public settlement outcomes.",
            "stop_condition": "Use only exact public Kalshi market payloads; do not infer outcomes from non-Kalshi sources.",
        }
    return {
        "name": "kalshi_paper_lifecycle_wait",
        "why": (
            "Paper decisions are frozen; wait for close/settlement before judging the signal."
            if not summary.get("next_unresolved_close_time_utc")
            else "Paper decisions are frozen; next unresolved paper close is "
            f"{summary.get('next_unresolved_close_time_utc')}."
        ),
        "stop_condition": "Do not rewrite decision-time probabilities or stakes after outcomes are known.",
    }


def capture_public_paper_settlement_snapshot(
    *,
    tickers: Sequence[str],
    raw_dir: Path = DEFAULT_SETTLED_RAW_DIR,
    base_snapshot_path: Path | None = None,
    generated_utc: str | None = None,
    fetch_json: Any | None = None,
) -> Path:
    generated = generated_utc or utc_now()
    fetch = fetch_json or fetch_json_url
    raw_dir.mkdir(parents=True, exist_ok=True)
    base_snapshot = read_json_or_empty(base_snapshot_path) if base_snapshot_path else {}
    base_markets = (
        base_snapshot.get("markets") if isinstance(base_snapshot.get("markets"), list) else []
    )
    markets: list[Mapping[str, Any]] = [row for row in base_markets if isinstance(row, Mapping)]
    seen = {str(row.get("ticker") or "") for row in markets}
    probe_errors: list[dict[str, str]] = []
    for ticker in tickers:
        if not ticker or ticker in seen:
            continue
        try:
            payload = fetch(
                f"{KALSHI_PUBLIC_BASE_URL}/markets/{urllib.parse.quote(ticker, safe='')}"
            )
        except Exception as exc:
            probe_errors.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})
            continue
        market = payload.get("market") if isinstance(payload, Mapping) else None
        if isinstance(market, Mapping):
            markets.append(market)
            seen.add(ticker)
    snapshot = {
        "schema_version": 1,
        "created_at_utc": generated,
        "status": "kalshi_public_paper_settlement_probe_ok"
        if markets
        else "kalshi_public_paper_settlement_probe_empty",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "query": {
            "mode": "exact_paper_decision_ticker_probe",
            "observed_ticker_count": len(tickers),
            "base_snapshot_path": str(base_snapshot_path) if base_snapshot_path else None,
        },
        "summary": {
            "market_count": len(markets),
            "probe_error_count": len(probe_errors),
            "settled_label_ready_count": sum(
                1 for market in markets if settlement_outcome(market) is not None
            ),
        },
        "probe_errors_sample": probe_errors[:50],
        "safety": safety_flags(public_market_data_calls=True),
        "markets": markets,
    }
    text = json.dumps(snapshot, indent=2, sort_keys=True, default=str) + "\n"
    stamp = safe_stamp(generated)
    snapshot_path = raw_dir / f"kalshi_paper_observed_markets_{stamp}.json"
    latest_path = raw_dir / "kalshi_paper_observed_markets_latest.json"
    snapshot_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return latest_path


def due_paper_tickers(
    paper_decisions_path: Path,
    *,
    generated_utc: str,
    max_tickers: int,
) -> list[str]:
    payload = read_json_or_empty(paper_decisions_path)
    rows = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    output: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or row.get("paper_usable") is not True:
            continue
        ticker = str(row.get("contract_ticker") or "").strip()
        if not ticker or ticker in seen:
            continue
        if not is_due(row.get("close_time"), generated_utc=generated_utc):
            continue
        seen.add(ticker)
        output.append(ticker)
        if len(output) >= max(0, max_tickers):
            break
    return output


def settlement_status(
    row: Mapping[str, Any],
    *,
    generated_utc: str,
    market: Mapping[str, Any] | None,
    yes_outcome: int | None,
) -> str:
    if row.get("paper_usable") is not True:
        return "blocked_not_paper_usable"
    if market is None:
        return (
            "pending_settlement_due"
            if is_due(row.get("close_time"), generated_utc=generated_utc)
            else "waiting_for_close"
        )
    if yes_outcome is None:
        return "settlement_outcome_missing"
    return "settled"


def settlement_outcome(market: Mapping[str, Any] | None) -> int | None:
    if market is None:
        return None
    settlement = probability(market.get("settlement_value_dollars", market.get("settlement_value")))
    if settlement is not None:
        if settlement >= 0.999:
            return 1
        if settlement <= 0.001:
            return 0
    result = str(market.get("result") or market.get("expiration_value") or "").strip().lower()
    if result in {"yes", "true", "1"}:
        return 1
    if result in {"no", "false", "0"}:
        return 0
    return None


def settled_market_index(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    markets = snapshot.get("markets") if isinstance(snapshot.get("markets"), list) else []
    output: dict[str, Mapping[str, Any]] = {}
    for market in markets:
        if not isinstance(market, Mapping):
            continue
        ticker = str(market.get("ticker") or "").strip()
        if ticker:
            output[ticker] = market
    return output


def selected_side_outcome(*, side: str, yes_outcome: int | None) -> int | None:
    if yes_outcome is None:
        return None
    if side == "yes":
        return yes_outcome
    if side == "no":
        return 1 - yes_outcome
    return None


def predicted_yes_outcome(row: Mapping[str, Any]) -> int | None:
    value = row.get("predicted_outcome")
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int) and value in {0, 1}:
        return value
    side = str(row.get("side") or "").strip().lower()
    if side == "yes":
        return 1
    if side == "no":
        return 0
    return None


def paper_decision_id(row: Mapping[str, Any], *, row_index: int) -> str:
    payload = {
        "row_index": row_index,
        "contract_ticker": row.get("contract_ticker"),
        "side": row.get("side"),
        "signal_key": row.get("signal_key"),
        "decision_time": row.get("decision_time"),
        "close_time": row.get("close_time"),
        "paper_stake": row.get("paper_stake"),
        "all_in_cost": row.get("all_in_cost"),
    }
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def settled_time(market: Mapping[str, Any]) -> str | None:
    return iso_time(
        market.get("settlement_ts")
        or market.get("settled_time")
        or market.get("expiration_time")
        or market.get("close_time")
    )


def is_due(value: Any, *, generated_utc: str) -> bool:
    close_ts = timestamp(value)
    generated_ts = timestamp(generated_utc)
    return close_ts is not None and generated_ts is not None and close_ts <= generated_ts


def next_unresolved_close_time(
    rows: Sequence[Mapping[str, Any]], *, generated_utc: str
) -> str | None:
    generated_ts = timestamp(generated_utc)
    future_closes: list[tuple[float, str]] = []
    for row in rows:
        close_time = iso_time(row.get("close_time"))
        close_ts = timestamp(close_time)
        if close_time and close_ts is not None and (
            generated_ts is None or close_ts > generated_ts
        ):
            future_closes.append((close_ts, close_time))
    if not future_closes:
        return None
    return min(future_closes, key=lambda item: item[0])[1]


def mean_calibration_error(rows: Sequence[Mapping[str, Any]]) -> float | None:
    errors: list[float] = []
    for row in rows:
        p = probability(row.get("calibrated_probability"))
        selected = row.get("selected_side_outcome")
        if p is None or selected not in {0, 1}:
            continue
        errors.append(abs(p - int(selected)))
    return round(sum(errors) / len(errors), 10) if errors else None


def fetch_json_url(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.load(response)
    return payload if isinstance(payload, dict) else {}


def write_outputs(report: Mapping[str, Any], *, out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "paper-settlement-reconciliation.json"
    md_path = out_dir / "paper-settlement-reconciliation.md"
    csv_path = out_dir / "paper-settlement-reconciliation.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("candidates", []), csv_path)

    latest_json = MACRO_DIR / "latest-paper-settlement-reconciliation.json"
    latest_md = MACRO_DIR / "latest-paper-settlement-reconciliation.md"
    latest_csv = MACRO_DIR / "latest-paper-settlement-reconciliation.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("candidates", []), latest_csv)
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
        "# Paper Settlement Reconciliation",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Paper usable: `{summary.get('paper_usable_count')}`",
        f"- Settled usable: `{summary.get('settled_paper_usable_count')}`",
        f"- Due unresolved usable: `{summary.get('due_unresolved_paper_usable_count')}`",
        f"- Next unresolved close: `{summary.get('next_unresolved_close_time_utc')}`",
        f"- Realized PnL: `{summary.get('realized_pnl')}`",
        f"- Hit rate: `{summary.get('hit_rate')}`",
        f"- Portfolio cap status: `{summary.get('paper_portfolio_cap_status')}`",
        f"- Largest cluster: `{summary.get('paper_portfolio_largest_cluster')}`",
        f"- Largest contract: `{summary.get('paper_portfolio_largest_contract')}`",
        "",
        "| Contract | Side | Stake | Status | PnL |",
        "| --- | --- | ---: | --- | ---: |",
    ]
    rows = report.get("candidates") if isinstance(report.get("candidates"), list) else []
    for row in [item for item in rows if item.get("paper_usable") is True][:50]:
        lines.append(
            f"| `{row.get('contract_ticker')}` | `{row.get('side')}` | "
            f"{row.get('paper_stake')} | `{row.get('settlement_status')}` | "
            f"{row.get('realized_pnl')} |"
        )
    if not rows:
        lines.append("|  |  |  | No candidates |  |")
    lines.append("")
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            output = dict(row)
            output["blocker_list"] = "; ".join(str(item) for item in row.get("blocker_list") or [])
            writer.writerow(output)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-decisions-path", type=Path, default=DEFAULT_PAPER_DECISIONS_PATH)
    parser.add_argument("--settled-snapshot-path", type=Path, default=DEFAULT_SETTLED_SNAPSHOT_PATH)
    parser.add_argument("--settled-raw-dir", type=Path, default=DEFAULT_SETTLED_RAW_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--fetch-settled", action="store_true")
    parser.add_argument("--max-fetch-tickers", type=int, default=100)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    generated = utc_now()
    settled_snapshot_path = args.settled_snapshot_path
    if args.fetch_settled:
        tickers = due_paper_tickers(
            args.paper_decisions_path,
            generated_utc=generated,
            max_tickers=args.max_fetch_tickers,
        )
        settled_snapshot_path = capture_public_paper_settlement_snapshot(
            tickers=tickers,
            raw_dir=args.settled_raw_dir,
            base_snapshot_path=args.settled_snapshot_path
            if args.settled_snapshot_path.exists()
            else None,
            generated_utc=generated,
        )
    report = build_paper_settlement_reconciliation(
        paper_decisions_path=args.paper_decisions_path,
        settled_snapshot_path=settled_snapshot_path,
        generated_utc=generated,
    )
    if args.write:
        paths = write_outputs(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
