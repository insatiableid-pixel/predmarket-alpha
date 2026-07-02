#!/usr/bin/env python3
"""Build safe Kalshi OOS observation packets for hypothesis falsification.

The builder records point-in-time pending observations from model-backed EV
rows, then converts those pending rows into settled label packets only when a
public Kalshi settlement payload provides the outcome. It never fetches by
default, never uses account/order paths, and never promotes a hypothesis.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_REGISTRY_PATH = MACRO_DIR / "latest-kalshi-hypothesis-registry.json"
DEFAULT_EV_LEDGER_PATH = MACRO_DIR / "latest-kalshi-contract-ev-ledger.json"
DEFAULT_UNIVERSE_SCAN_PATH = MACRO_DIR / "latest-kalshi-universe-scan.json"
DEFAULT_SETTLED_SNAPSHOT_PATH = Path(
    "/home/mrwatson/manual_drops/kalshi_oos_settlements/kalshi_settled_markets_latest.json"
)
DEFAULT_SETTLED_RAW_DIR = Path("/home/mrwatson/manual_drops/kalshi_oos_settlements")
DEFAULT_PENDING_DIR = Path("/home/mrwatson/manual_drops/kalshi_oos_pending")
DEFAULT_LABEL_DIR = Path("/home/mrwatson/manual_drops/kalshi_oos_labels")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-labeled-observation-builder-latest"
KALSHI_PUBLIC_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
CSV_FIELDS = [
    "hypothesis_id",
    "contract_ticker",
    "side",
    "source_repo_id",
    "market_type",
    "status",
    "decision_time",
    "model_probability",
    "all_in_break_even_probability",
    "blocker",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_labeled_observation_report(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    ev_ledger_path: Path = DEFAULT_EV_LEDGER_PATH,
    universe_scan_path: Path = DEFAULT_UNIVERSE_SCAN_PATH,
    settled_snapshot_path: Path = DEFAULT_SETTLED_SNAPSHOT_PATH,
    pending_dir: Path = DEFAULT_PENDING_DIR,
    label_dir: Path = DEFAULT_LABEL_DIR,
    generated_utc: str | None = None,
    public_market_data_calls: bool = False,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    registry = read_json_or_empty(registry_path)
    ledger = read_json_or_empty(ev_ledger_path)
    universe = read_json_or_empty(universe_scan_path)
    settled_snapshot = read_json_or_empty(settled_snapshot_path)
    hypotheses = [row for row in registry.get("hypotheses", []) if isinstance(row, Mapping)]
    ledger_rows = [row for row in ledger.get("rows", []) if isinstance(row, Mapping)]
    universe_rows = [row for row in universe.get("candidates", []) if isinstance(row, Mapping)]

    hypothesis_index = contract_ev_hypotheses(hypotheses)
    pending_from_ledger, blocked = pending_rows_from_ledger(
        ledger_rows,
        hypotheses=hypothesis_index,
        ledger_generated_utc=str(ledger.get("generated_utc") or generated),
        ev_ledger_path=ev_ledger_path,
    )
    universe_blocked = blocked_universe_rows(universe_rows, hypotheses)
    existing_pending = load_pending_packets(pending_dir)
    all_pending = dedupe_pending([*existing_pending["rows"], *pending_from_ledger])
    settled_index = settled_market_index(settled_snapshot)
    label_rows, label_blocked = label_rows_from_pending(all_pending, settled_index)

    pending_packet = safe_packet(
        generated_utc=generated,
        packet_type="kalshi_oos_pending_observations",
        rows=pending_from_ledger,
        inputs={
            "registry_path": str(registry_path),
            "ev_ledger_path": str(ev_ledger_path),
            "universe_scan_path": str(universe_scan_path),
            "settled_snapshot_path": str(settled_snapshot_path),
        },
    )
    label_packet = safe_packet(
        generated_utc=generated,
        packet_type="kalshi_oos_labeled_observations",
        rows=label_rows,
        inputs={
            "pending_dir": str(pending_dir),
            "settled_snapshot_path": str(settled_snapshot_path),
        },
    )
    status = builder_status(
        registry_safe=safe_research_artifact(registry),
        ledger_safe=safe_research_artifact(ledger),
        pending_count=len(all_pending),
        new_pending_count=len(pending_from_ledger),
        label_count=len(label_rows),
    )
    summary = {
        "hypothesis_count": len(hypotheses),
        "ev_ledger_row_count": len(ledger_rows),
        "universe_candidate_count": len(universe_rows),
        "eligible_pending_row_count": len(pending_from_ledger),
        "existing_pending_packet_count": existing_pending["packet_count"],
        "existing_pending_row_count": len(existing_pending["rows"]),
        "total_pending_row_count": len(all_pending),
        "settled_market_count": len(settled_index),
        "label_row_count": len(label_rows),
        "blocked_source_row_count": len(blocked) + len(universe_blocked),
        "blocked_label_row_count": len(label_blocked),
        "blocked_reason_counts": blocked_reason_counts([*blocked, *universe_blocked, *label_blocked]),
    }
    gates = build_gates(
        registry=registry,
        ledger=ledger,
        pending_count=len(all_pending),
        label_count=len(label_rows),
        settled_market_count=len(settled_index),
        pending_dir=pending_dir,
        label_dir=label_dir,
    )
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": public_market_data_calls,
        "authenticated_api_calls": False,
        "provider_api_calls": public_market_data_calls,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "inputs": {
            "registry_path": str(registry_path),
            "registry_sha256": sha256_or_none(registry_path),
            "ev_ledger_path": str(ev_ledger_path),
            "ev_ledger_sha256": sha256_or_none(ev_ledger_path),
            "universe_scan_path": str(universe_scan_path),
            "universe_scan_sha256": sha256_or_none(universe_scan_path),
            "settled_snapshot_path": str(settled_snapshot_path),
            "settled_snapshot_sha256": sha256_or_none(settled_snapshot_path),
            "pending_dir": str(pending_dir),
            "label_dir": str(label_dir),
        },
        "method": {
            "pending_rule": "Only rows with registered HypothesisCandidate IDs, calibrated model probabilities, all-in costs, and point-in-time decision/model/quote times become pending observations.",
            "label_rule": "Only pending rows with public settled Kalshi outcomes become labeled OOS observations.",
            "time_safety": "The downstream OOS harness rejects rows unless quote_time <= decision_time, model_time <= decision_time, and decision_time < close_time <= settled_time.",
            "edge_boundary": "This builder never tests, promotes, sizes, or executes. It only prepares observations for falsification.",
        },
        "summary": summary,
        "gates": gates,
        "pending_packet": pending_packet,
        "label_packet": label_packet,
        "pending_rows_sample": pending_from_ledger[:20],
        "label_rows_sample": label_rows[:20],
        "blocked_source_rows_sample": [*blocked, *universe_blocked][:50],
        "blocked_label_rows_sample": label_blocked[:50],
        "next_action": next_action(status),
        "safety": safety_flags(public_market_data_calls=public_market_data_calls),
    }


def capture_public_settled_snapshot(
    *,
    raw_dir: Path = DEFAULT_SETTLED_RAW_DIR,
    limit: int = 1000,
    max_pages: int = 1,
    status: str = "settled",
    generated_utc: str | None = None,
) -> Path:
    generated = generated_utc or utc_now()
    raw_dir.mkdir(parents=True, exist_ok=True)
    markets: list[Mapping[str, Any]] = []
    cursor = ""
    for _ in range(max(1, max_pages)):
        params = {
            "status": status,
            "limit": max(1, min(int(limit), 1000)),
            "mve_filter": "exclude",
            "cursor": cursor or None,
        }
        query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
        with urllib.request.urlopen(f"{KALSHI_PUBLIC_BASE_URL}/markets?{query}", timeout=30) as response:
            payload = json.load(response)
        if not isinstance(payload, Mapping):
            break
        markets.extend(row for row in payload.get("markets", []) if isinstance(row, Mapping))
        cursor = str(payload.get("cursor") or "")
        if not cursor:
            break
    snapshot = {
        "schema_version": 1,
        "created_at_utc": generated,
        "status": "kalshi_public_settled_fetch_ok" if markets else "kalshi_public_settled_fetch_empty",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "query": {
            "status": status,
            "limit": max(1, min(int(limit), 1000)),
            "max_pages": max_pages,
            "mve_filter": "exclude",
        },
        "summary": {"market_count": len(markets), "cursor_present": bool(cursor)},
        "safety": safety_flags(public_market_data_calls=True),
        "markets": markets,
    }
    stamp = generated.replace("-", "").replace(":", "")
    snapshot_path = raw_dir / f"kalshi_settled_markets_{stamp}.json"
    latest_path = raw_dir / "kalshi_settled_markets_latest.json"
    text = json.dumps(snapshot, indent=2, sort_keys=True, default=str) + "\n"
    snapshot_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return latest_path


def contract_ev_hypotheses(hypotheses: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    indexed: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for hypothesis in hypotheses:
        filt = hypothesis.get("market_universe_filter")
        if not isinstance(filt, Mapping):
            continue
        if hypothesis.get("source") != "contract_ev_ledger" and not filt.get("source_repo_id"):
            continue
        source_repo_id = str(filt.get("source_repo_id") or "").strip()
        market_type = str(filt.get("market_type") or "").strip()
        if source_repo_id and market_type:
            indexed.setdefault((source_repo_id, market_type), []).append(hypothesis)
    return indexed


def pending_rows_from_ledger(
    rows: Sequence[Mapping[str, Any]],
    *,
    hypotheses: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
    ledger_generated_utc: str,
    ev_ledger_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pending: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    source_sha = sha256_or_none(ev_ledger_path)
    for index, row in enumerate(rows):
        source_repo_id = str(row.get("source_repo_id") or "").strip()
        market_type = str(row.get("market_type") or "").strip()
        candidate_hypotheses = list(hypotheses.get((source_repo_id, market_type), []))
        matched_hypotheses = [
            hypothesis
            for hypothesis in candidate_hypotheses
            if row_matches_hypothesis(row, hypothesis)
        ]
        base = {
            "contract_ticker": row.get("contract_ticker"),
            "side": row.get("side"),
            "source_repo_id": source_repo_id,
            "market_type": market_type,
            "source_row_index": index,
        }
        common_errors = pending_row_errors(row, ledger_generated_utc=ledger_generated_utc)
        if not matched_hypotheses and common_errors and candidate_hypotheses:
            blocked.extend(
                {**base, "hypothesis_id": hypothesis.get("hypothesis_id"), "blocker": err}
                for hypothesis in candidate_hypotheses
                for err in common_errors
            )
            continue
        if not matched_hypotheses:
            blocked.append({**base, "blocker": "no_registered_contract_ev_hypothesis_match"})
            continue
        if common_errors:
            blocked.extend({**base, "hypothesis_id": hypothesis.get("hypothesis_id"), "blocker": err} for hypothesis in matched_hypotheses for err in common_errors)
            continue
        for hypothesis in matched_hypotheses:
            pending.append(
                pending_observation(
                    row,
                    hypothesis=hypothesis,
                    source_row_index=index,
                    source_artifact=str(ev_ledger_path),
                    source_sha256=source_sha,
                    ledger_generated_utc=ledger_generated_utc,
                )
            )
    return pending, blocked


def row_matches_hypothesis(row: Mapping[str, Any], hypothesis: Mapping[str, Any]) -> bool:
    family = str(hypothesis.get("feature_family") or "")
    if family == "calibrated_probability_decay":
        return probability(row.get("calibrated_probability")) is not None
    if family == "legacy_positive_margin_survival":
        edge = optional_float(row.get("expected_value_per_contract", row.get("margin_probability")))
        return row.get("usable") is True or (str(row.get("gate_status")) == "pass" and edge is not None and edge > 0.0)
    return False


def pending_row_errors(row: Mapping[str, Any], *, ledger_generated_utc: str) -> list[str]:
    errors: list[str] = []
    if not str(row.get("contract_ticker") or "").strip():
        errors.append("missing_contract_ticker")
    if normalize_side(row.get("side")) not in {"yes", "no"}:
        errors.append("missing_or_invalid_side")
    if probability(row.get("calibrated_probability")) is None:
        errors.append("missing_calibrated_model_probability")
    if probability(row.get("all_in_break_even_probability", row.get("all_in_cost"))) is None:
        errors.append("missing_all_in_break_even_probability")
    if timestamp(first_present(row, ["decision_time", "decision_ts", "as_of_utc", "generated_utc"], ledger_generated_utc)) is None:
        errors.append("missing_decision_time")
    if timestamp(first_present(row, ["quote_time", "quote_ts", "as_of_utc", "generated_utc"], ledger_generated_utc)) is None:
        errors.append("missing_quote_time")
    if timestamp(first_present(row, ["model_time", "model_ts", "as_of_utc", "generated_utc"], ledger_generated_utc)) is None:
        errors.append("missing_model_time")
    return errors


def pending_observation(
    row: Mapping[str, Any],
    *,
    hypothesis: Mapping[str, Any],
    source_row_index: int,
    source_artifact: str,
    source_sha256: str | None,
    ledger_generated_utc: str,
) -> dict[str, Any]:
    decision_time = iso_time(first_present(row, ["decision_time", "decision_ts", "as_of_utc", "generated_utc"], ledger_generated_utc))
    quote_time = iso_time(first_present(row, ["quote_time", "quote_ts", "as_of_utc", "generated_utc"], ledger_generated_utc))
    model_time = iso_time(first_present(row, ["model_time", "model_ts", "as_of_utc", "generated_utc"], ledger_generated_utc))
    return {
        "schema_version": "KalshiPendingOosObservationV1",
        "hypothesis_id": hypothesis.get("hypothesis_id"),
        "contract_ticker": str(row.get("contract_ticker") or "").strip(),
        "event_ticker": row.get("event_ticker"),
        "side": normalize_side(row.get("side")),
        "source_repo_id": row.get("source_repo_id"),
        "market_type": row.get("market_type"),
        "feature_family": hypothesis.get("feature_family"),
        "decision_time": decision_time,
        "quote_time": quote_time,
        "model_time": model_time,
        "timestamp_source": "ev_ledger_row_or_report_generated_utc",
        "model_probability": probability(row.get("calibrated_probability")),
        "all_in_break_even_probability": probability(row.get("all_in_break_even_probability", row.get("all_in_cost"))),
        "model_probability_source": row.get("calibrated_probability_source"),
        "cost_source": row.get("break_even_source") or row.get("cost_basis_source"),
        "source_artifact": source_artifact,
        "source_artifact_sha256": source_sha256,
        "source_row_index": source_row_index,
        "calibrated_probability_source_artifact": row.get("calibrated_probability_source_artifact"),
        "calibrated_probability_source_sha256": row.get("calibrated_probability_source_sha256"),
        "resolution_rule_source_artifact": row.get("resolution_rule_source_artifact"),
        "resolution_rule_source_sha256": row.get("resolution_rule_source_sha256"),
        "research_only": True,
        "execution_enabled": False,
    }


def blocked_universe_rows(
    universe_rows: Sequence[Mapping[str, Any]],
    hypotheses: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    universe_hypotheses = [
        hypothesis for hypothesis in hypotheses if hypothesis.get("source") == "universe_scan"
    ]
    if not universe_hypotheses:
        return []
    counts: Counter[str] = Counter()
    for row in universe_rows:
        if probability(row.get("calibrated_probability")) is None:
            counts["universe_candidate_missing_model_probability"] += 1
        elif probability(row.get("yes_preliminary_all_in_break_even")) is None:
            counts["universe_candidate_missing_all_in_cost"] += 1
    return [{"blocker": key, "count": count} for key, count in sorted(counts.items())]


def blocked_reason_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        reason = str(row.get("blocker") or "unknown_blocker")
        try:
            amount = int(row.get("count") or 1)
        except (TypeError, ValueError):
            amount = 1
        counts[reason] += max(amount, 1)
    return dict(sorted(counts.items()))


def load_pending_packets(pending_dir: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    paths: list[str] = []
    if not pending_dir.exists():
        return {"packet_count": 0, "paths": [], "rows": []}
    for path in sorted(pending_dir.glob("*.json")):
        payload = read_json_or_empty(path)
        if not safe_research_artifact(payload):
            continue
        packet_rows = payload.get("rows", [])
        if not isinstance(packet_rows, list):
            continue
        paths.append(str(path))
        rows.extend(dict(row) for row in packet_rows if isinstance(row, Mapping))
    return {"packet_count": len(paths), "paths": paths, "rows": rows}


def dedupe_pending(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    output: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("hypothesis_id") or ""),
            str(row.get("contract_ticker") or ""),
            normalize_side(row.get("side")),
            str(row.get("decision_time") or ""),
        )
        if "" in key or key in seen:
            continue
        seen.add(key)
        output.append(dict(row))
    output.sort(key=lambda item: (str(item.get("decision_time") or ""), str(item.get("contract_ticker") or "")))
    return output


def settled_market_index(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    markets = snapshot.get("markets")
    if not isinstance(markets, list):
        return {}
    indexed: dict[str, Mapping[str, Any]] = {}
    for market in markets:
        if not isinstance(market, Mapping):
            continue
        ticker = str(market.get("ticker") or "").strip()
        if ticker and settlement_outcome(market) is not None:
            indexed[ticker] = market
    return indexed


def label_rows_from_pending(
    pending_rows: Sequence[Mapping[str, Any]],
    settled_index: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    label_rows: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for row in pending_rows:
        ticker = str(row.get("contract_ticker") or "").strip()
        side = normalize_side(row.get("side"))
        market = settled_index.get(ticker)
        if market is None:
            blocked.append({"contract_ticker": ticker, "hypothesis_id": row.get("hypothesis_id"), "blocker": "pending_contract_not_settled_in_snapshot"})
            continue
        yes_outcome = settlement_outcome(market)
        close_time = iso_time(first_present(market, ["close_time", "expected_expiration_time", "expiration_time"]))
        settled_time = iso_time(first_present(market, ["settlement_ts", "settled_time", "close_time", "expiration_time"]))
        if yes_outcome is None:
            blocked.append({"contract_ticker": ticker, "hypothesis_id": row.get("hypothesis_id"), "blocker": "settlement_outcome_missing"})
            continue
        if close_time is None or settled_time is None:
            blocked.append({"contract_ticker": ticker, "hypothesis_id": row.get("hypothesis_id"), "blocker": "settlement_timestamps_missing"})
            continue
        side_outcome = yes_outcome if side == "yes" else 1 - yes_outcome
        label_rows.append(
            {
                "hypothesis_id": row.get("hypothesis_id"),
                "contract_ticker": ticker,
                "event_ticker": row.get("event_ticker") or market.get("event_ticker"),
                "side": side,
                "quote_time": row.get("quote_time"),
                "model_time": row.get("model_time"),
                "decision_time": row.get("decision_time"),
                "close_time": close_time,
                "settled_time": settled_time,
                "model_probability": row.get("model_probability"),
                "all_in_break_even_probability": row.get("all_in_break_even_probability"),
                "side_outcome": side_outcome,
                "label_source": "public_kalshi_settled_market_payload",
                "cost_source": row.get("cost_source") or "pending_observation_cost_basis",
                "source_artifact": row.get("source_artifact"),
                "settlement_result": market.get("result"),
                "settlement_value_dollars": market.get("settlement_value_dollars"),
            }
        )
    return label_rows, blocked


def build_gates(
    *,
    registry: Mapping[str, Any],
    ledger: Mapping[str, Any],
    pending_count: int,
    label_count: int,
    settled_market_count: int,
    pending_dir: Path,
    label_dir: Path,
) -> list[dict[str, Any]]:
    return [
        gate("registry_safe", "pass" if safe_research_artifact(registry) else "blocked", "Hypothesis registry is research-only." if safe_research_artifact(registry) else "Hypothesis registry missing or unsafe."),
        gate("ev_ledger_safe", "pass" if safe_research_artifact(ledger) else "blocked", "EV ledger is research-only." if safe_research_artifact(ledger) else "EV ledger missing or unsafe."),
        gate("pending_observations_available", "pass" if pending_count else "blocked", f"{pending_count} pending OOS observation(s) available."),
        gate("settled_markets_available", "pass" if settled_market_count else "warn", f"{settled_market_count} settled public market(s) loaded."),
        gate("label_rows_available", "pass" if label_count else "blocked", f"{label_count} settled label row(s) emitted."),
        gate("manual_drop_dirs_outside_repo", "pass" if outside_repo(pending_dir) and outside_repo(label_dir) else "blocked", "Pending and label directories are outside the repo."),
        gate("no_execution_boundary", "pass", "Builder emits research-only observation packets and no account/order fields."),
    ]


def builder_status(
    *,
    registry_safe: bool,
    ledger_safe: bool,
    pending_count: int,
    new_pending_count: int,
    label_count: int,
) -> str:
    if not registry_safe:
        return "labeled_observation_builder_blocked_missing_hypothesis_registry"
    if not ledger_safe:
        return "labeled_observation_builder_blocked_missing_ev_ledger"
    if label_count:
        return "labeled_observation_builder_label_packet_ready"
    if pending_count:
        return "labeled_observation_builder_pending_observations_waiting_settlement"
    if new_pending_count:
        return "labeled_observation_builder_pending_observations_recorded"
    return "labeled_observation_builder_blocked_no_eligible_model_rows"


def next_action(status: str) -> dict[str, str]:
    if status == "labeled_observation_builder_label_packet_ready":
        return {
            "name": "run_labeled_oos_backtest",
            "why": "A settled label packet exists; the OOS falsification harness can now score registered hypotheses.",
            "stop_condition": "Stop before sizing/execution; research promotion still requires FDR-controlled OOS survival.",
        }
    if status == "labeled_observation_builder_pending_observations_waiting_settlement":
        return {
            "name": "wait_for_settlement_or_expand_calibrated_probability_coverage",
            "why": "Pending model-backed observations exist, but none have settled labels yet.",
            "stop_condition": "Stop before using unresolved contracts as OOS proof.",
        }
    return {
        "name": "build_more_model_backed_ev_rows",
        "why": "No eligible pending OOS observations can be formed without registered hypotheses, calibrated probabilities, and all-in costs.",
        "stop_condition": "Stop before relabeling universe inventory or market prices as model probabilities.",
    }


def write_labeled_observation_outputs(
    report: Mapping[str, Any],
    *,
    out_dir: Path = DEFAULT_OUT_DIR,
    pending_dir: Path = DEFAULT_PENDING_DIR,
    label_dir: Path = DEFAULT_LABEL_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-labeled-observation-builder.json"
    md_path = out_dir / "kalshi-labeled-observation-builder.md"
    csv_path = out_dir / "kalshi-labeled-observation-builder.csv"
    report_text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(report_text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, csv_path)

    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
    }
    pending_rows = report.get("pending_packet", {}).get("rows", []) if isinstance(report.get("pending_packet"), Mapping) else []
    label_rows = report.get("label_packet", {}).get("rows", []) if isinstance(report.get("label_packet"), Mapping) else []
    stamp = safe_stamp(str(report.get("generated_utc") or utc_now()))
    if pending_rows:
        pending_dir.mkdir(parents=True, exist_ok=True)
        pending_path = pending_dir / f"kalshi_oos_pending_{stamp}.json"
        pending_latest = pending_dir / "kalshi_oos_pending_latest.json"
        pending_text = json.dumps(report["pending_packet"], indent=2, sort_keys=True, default=str) + "\n"
        pending_path.write_text(pending_text, encoding="utf-8")
        pending_latest.write_text(pending_text, encoding="utf-8")
        paths["pending_packet_path"] = str(pending_path)
        paths["pending_packet_latest_path"] = str(pending_latest)
    if label_rows:
        label_dir.mkdir(parents=True, exist_ok=True)
        label_path = label_dir / f"kalshi_oos_label_packet_{stamp}.json"
        label_latest = label_dir / "kalshi_oos_label_packet_latest.json"
        label_text = json.dumps(report["label_packet"], indent=2, sort_keys=True, default=str) + "\n"
        label_path.write_text(label_text, encoding="utf-8")
        label_latest.write_text(label_text, encoding="utf-8")
        paths["label_packet_path"] = str(label_path)
        paths["label_packet_latest_path"] = str(label_latest)

    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-labeled-observation-builder.json"
    latest_md = MACRO_DIR / "latest-kalshi-labeled-observation-builder.md"
    latest_csv = MACRO_DIR / "latest-kalshi-labeled-observation-builder.csv"
    latest_json.write_text(report_text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, latest_csv)
    paths["latest_json_path"] = str(latest_json)
    paths["latest_markdown_path"] = str(latest_md)
    paths["latest_csv_path"] = str(latest_csv)
    return paths


def write_csv(report: Mapping[str, Any], path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for row in report.get("pending_rows_sample", []):
        if isinstance(row, Mapping):
            rows.append({**{field: row.get(field) for field in CSV_FIELDS}, "status": "pending", "blocker": ""})
    for row in report.get("blocked_source_rows_sample", []):
        if isinstance(row, Mapping):
            rows.append({**{field: row.get(field) for field in CSV_FIELDS}, "status": "blocked"})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in CSV_FIELDS})


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Labeled Observation Builder",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Pending observations: `{summary.get('total_pending_row_count', 0)}`",
        f"- New pending observations: `{summary.get('eligible_pending_row_count', 0)}`",
        f"- Settled markets loaded: `{summary.get('settled_market_count', 0)}`",
        f"- Label rows: `{summary.get('label_row_count', 0)}`",
        "",
        "## Gates",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for item in report.get("gates", []):
        if isinstance(item, Mapping):
            lines.append(f"| `{item.get('name')}` | `{item.get('status')}` | {item.get('reason')} |")
    blocked = summary.get("blocked_reason_counts") if isinstance(summary.get("blocked_reason_counts"), Mapping) else {}
    lines.extend(["", "## Blocked Reasons", ""])
    if blocked:
        for reason, count in blocked.items():
            lines.append(f"- `{reason}`: `{count}`")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Guardrail",
            "",
            "This builder creates falsification inputs only. It does not test, promote, size, or execute contracts.",
            "",
        ]
    )
    return "\n".join(lines)


def safe_packet(*, generated_utc: str, packet_type: str, rows: Sequence[Mapping[str, Any]], inputs: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_utc": generated_utc,
        "packet_type": packet_type,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "staking_or_sizing_guidance": False,
        "inputs": dict(inputs),
        "rows": list(rows),
        "safety": safety_flags(),
    }


def settlement_outcome(market: Mapping[str, Any]) -> int | None:
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


def first_present(row: Mapping[str, Any], keys: Sequence[str], fallback: Any = None) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in {None, ""}:
            return value
    return fallback


def normalize_side(value: Any) -> str:
    text = str(value or "yes").strip().lower()
    return text if text in {"yes", "no"} else ""


def probability(value: Any) -> float | None:
    number = optional_float(value)
    return number if number is not None and 0.0 <= number <= 1.0 else None


def optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip().rstrip("%")
            if not value:
                return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        number = None
    if number is not None:
        return number if math.isfinite(number) else None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def iso_time(value: Any) -> str | None:
    ts = timestamp(value)
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_research_artifact(value: Mapping[str, Any]) -> bool:
    safety = value.get("safety") if isinstance(value.get("safety"), Mapping) else {}
    return (
        value.get("research_only") is True
        and value.get("execution_enabled") is False
        and value.get("market_execution") is not True
        and value.get("account_or_order_paths") is not True
        and safety.get("market_execution") is False
        and safety.get("account_or_order_paths") is False
        and safety.get("database_writes") is False
    )


def safety_flags(*, public_market_data_calls: bool = False) -> dict[str, bool]:
    return {
        "research_only": True,
        "public_market_data_calls": public_market_data_calls,
        "authenticated_api_calls": False,
        "provider_api_calls": public_market_data_calls,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "raw_payloads_copied_to_repo": False,
        "staking_or_sizing_guidance": False,
    }


def outside_repo(path: Path) -> bool:
    try:
        path.expanduser().resolve().relative_to(CONTROL_REPO.resolve())
    except ValueError:
        return True
    return False


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def read_json_or_empty(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def sha256_or_none(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_stamp(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum()) or "latest"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--ev-ledger-path", type=Path, default=DEFAULT_EV_LEDGER_PATH)
    parser.add_argument("--universe-scan-path", type=Path, default=DEFAULT_UNIVERSE_SCAN_PATH)
    parser.add_argument("--settled-snapshot-path", type=Path, default=DEFAULT_SETTLED_SNAPSHOT_PATH)
    parser.add_argument("--settled-raw-dir", type=Path, default=DEFAULT_SETTLED_RAW_DIR)
    parser.add_argument("--capture-settled-public", action="store_true")
    parser.add_argument("--settled-limit", type=int, default=1000)
    parser.add_argument("--settled-max-pages", type=int, default=1)
    parser.add_argument("--pending-dir", type=Path, default=DEFAULT_PENDING_DIR)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settled_snapshot_path = args.settled_snapshot_path
    if args.capture_settled_public:
        settled_snapshot_path = capture_public_settled_snapshot(
            raw_dir=args.settled_raw_dir,
            limit=args.settled_limit,
            max_pages=args.settled_max_pages,
        )
    report = build_labeled_observation_report(
        registry_path=args.registry_path,
        ev_ledger_path=args.ev_ledger_path,
        universe_scan_path=args.universe_scan_path,
        settled_snapshot_path=settled_snapshot_path,
        pending_dir=args.pending_dir,
        label_dir=args.label_dir,
        public_market_data_calls=args.capture_settled_public,
    )
    if args.write:
        paths = write_labeled_observation_outputs(
            report,
            out_dir=args.out_dir,
            pending_dir=args.pending_dir,
            label_dir=args.label_dir,
        )
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
