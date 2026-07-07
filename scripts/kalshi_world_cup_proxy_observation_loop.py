#!/usr/bin/env python3
"""Archive World Cup/FIFA soccer Kalshi observations and attach settled labels.

This lane turns the universe scanner's ``other_sports`` World Cup rows into
research evidence. It intentionally does not handicap soccer. The only
candidate "features" are market-structure facts visible at observation time
(quote, spread, series/market type, and exact ticker). Labels come only from
Kalshi's public settled market payload matched by exact ticker.
"""

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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.kalshi_universe_scan import DEFAULT_WORLD_CUP_SOCCER_SERIES  # noqa: E402
from predmarket.shared_helpers import (  # noqa: E402
    iso_from_timestamp,
    manual_drop_path,
    optional_float,
    outside_repo,
    probability,
    read_json_or_empty,
    safe_research_artifact,
    sha256_or_none,
    timestamp,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
KALSHI_PUBLIC_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
DEFAULT_UNIVERSE_SCAN_PATH = MACRO_DIR / "latest-kalshi-universe-scan.json"
DEFAULT_SETTLED_SNAPSHOT_PATH = manual_drop_path(
    "kalshi_world_cup_settlements", "kalshi_observed_markets_latest.json"
)
DEFAULT_SETTLED_RAW_DIR = manual_drop_path("kalshi_world_cup_settlements")
DEFAULT_OBSERVATION_DIR = manual_drop_path("kalshi_world_cup_proxy_observations")
DEFAULT_LABEL_DIR = manual_drop_path("kalshi_world_cup_proxy_labels")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-world-cup-proxy-observation-loop-latest"
DEFAULT_MAX_CONTRACTS = 300

WORLD_CUP_SERIES = frozenset(DEFAULT_WORLD_CUP_SOCCER_SERIES)
CSV_FIELDS = [
    "observation_id",
    "contract_ticker",
    "series_ticker",
    "market_type",
    "selection_token",
    "decision_time",
    "close_time",
    "expected_expiration_time",
    "yes_bid",
    "yes_ask",
    "yes_mid",
    "yes_spread",
    "market_consensus_prediction",
    "longshot_fade_prediction",
    "label_status",
    "yes_outcome",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_world_cup_proxy_observation_loop(
    *,
    universe_scan_path: Path = DEFAULT_UNIVERSE_SCAN_PATH,
    settled_snapshot_path: Path = DEFAULT_SETTLED_SNAPSHOT_PATH,
    observation_dir: Path = DEFAULT_OBSERVATION_DIR,
    label_dir: Path = DEFAULT_LABEL_DIR,
    generated_utc: str | None = None,
    max_contracts: int = DEFAULT_MAX_CONTRACTS,
    public_market_data_calls: bool = False,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    universe = read_json_or_empty(universe_scan_path)
    settled_snapshot = read_json_or_empty(settled_snapshot_path)
    candidates = world_cup_candidates(universe, max_contracts=max_contracts)
    candidate_observations = [
        observation_from_candidate(
            row,
            decision_time=generated,
            source_path=universe_scan_path,
            source_index=index,
        )
        for index, row in enumerate(candidates)
    ]
    existing_observations = load_packets(observation_dir)
    existing_ids = observation_ids(existing_observations["rows"])
    new_observations = [
        row
        for row in candidate_observations
        if str(row.get("observation_id") or "") not in existing_ids
    ]
    all_observations = dedupe_by_id([*existing_observations["rows"], *candidate_observations])
    existing_labels = load_packets(label_dir)
    existing_label_ids = observation_ids(existing_labels["rows"])
    settled_index = settled_market_index(settled_snapshot)
    label_rows, blocked_labels = label_observations(all_observations, settled_index)
    new_label_rows = [
        row for row in label_rows if str(row.get("observation_id") or "") not in existing_label_ids
    ]
    all_label_rows = dedupe_by_id([*existing_labels["rows"], *label_rows])
    due = observation_due_summary(all_observations, generated_utc=generated)
    gates = build_gates(
        universe_safe=safe_research_artifact(universe),
        candidate_count=len(candidates),
        observation_count=len(all_observations),
        new_observation_count=len(new_observations),
        settled_market_count=len(settled_index),
        label_count=len(all_label_rows),
        observation_dir=observation_dir,
        label_dir=label_dir,
        rows=[*all_observations, *all_label_rows],
    )
    status = loop_status(
        universe_safe=safe_research_artifact(universe),
        candidate_count=len(candidates),
        observation_count=len(all_observations),
        label_count=len(all_label_rows),
    )
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "family_id": "world_cup_proxy",
        "public_market_data_calls": public_market_data_calls,
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "inputs": {
            "universe_scan_path": str(universe_scan_path),
            "universe_scan_sha256": sha256_or_none(universe_scan_path),
            "universe_scan_status": universe.get("status")
            if isinstance(universe, Mapping)
            else None,
            "settled_snapshot_path": str(settled_snapshot_path),
            "settled_snapshot_sha256": sha256_or_none(settled_snapshot_path),
            "observation_dir": str(observation_dir),
            "label_dir": str(label_dir),
            "max_contracts": max_contracts,
            "world_cup_series": sorted(WORLD_CUP_SERIES),
        },
        "method": {
            "candidate_rule": "Use universe-scan candidates classified other_sports whose series_ticker is in the explicit World Cup/FIFA soccer allowlist.",
            "observation_rule": "Archive exact Kalshi ticker, quote, series type, and pre-registered market-structure predictions at decision time.",
            "label_rule": "Attach outcomes only from public Kalshi market payloads matched by exact contract_ticker.",
            "model_boundary": "No soccer handicapping model, sportsbook line, or donor probability is used in this loop.",
            "ev_boundary": "This loop emits observations and labels only; no calibrated probabilities, EV, sizing, or orders.",
        },
        "summary": {
            "universe_safe": safe_research_artifact(universe),
            "candidate_count": len(candidates),
            "new_observation_row_count": len(new_observations),
            "existing_observation_packet_count": existing_observations["packet_count"],
            "existing_observation_row_count": len(existing_observations["rows"]),
            "total_observation_row_count": len(all_observations),
            "distinct_contract_count": len(
                {row.get("contract_ticker") for row in all_observations}
            ),
            "settled_market_count": len(settled_index),
            "existing_label_packet_count": existing_labels["packet_count"],
            "existing_label_row_count": len(existing_labels["rows"]),
            "new_label_row_count": len(new_label_rows),
            "label_row_count": len(all_label_rows),
            "blocked_label_row_count": len(blocked_labels),
            "series_counts": counts(row.get("series_ticker") for row in all_observations),
            "market_type_counts": counts(row.get("market_type") for row in all_observations),
            "label_status_counts": counts(
                row.get("label_status") for row in [*all_label_rows, *blocked_labels]
            ),
            "gate_counts": gate_counts(gates),
            **due,
        },
        "observation_packet": safe_packet(
            generated_utc=generated,
            packet_type="kalshi_world_cup_proxy_feature_observations",
            rows=new_observations,
            inputs={"universe_scan_path": str(universe_scan_path)},
        ),
        "label_packet": safe_packet(
            generated_utc=generated,
            packet_type="kalshi_world_cup_proxy_feature_labels",
            rows=new_label_rows,
            inputs={
                "observation_dir": str(observation_dir),
                "settled_snapshot_path": str(settled_snapshot_path),
            },
        ),
        "gates": gates,
        "observation_rows_sample": all_observations[:25],
        "label_rows_sample": all_label_rows[:25],
        "blocked_label_rows_sample": blocked_labels[:50],
        "next_action": next_action(status),
        "safety": safety_flags(public_market_data_calls=public_market_data_calls),
    }


def world_cup_candidates(
    universe: Mapping[str, Any], *, max_contracts: int
) -> list[dict[str, Any]]:
    rows = universe.get("candidates", []) if isinstance(universe.get("candidates"), list) else []
    selected: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        series = str(row.get("series_ticker") or "").upper()
        if row.get("classification") != "other_sports" or series not in WORLD_CUP_SERIES:
            continue
        if row.get("gate_status") not in {"pass", "warn"}:
            continue
        if not str(row.get("ticker") or ""):
            continue
        selected.append(dict(row))
    selected.sort(
        key=lambda item: (
            float(item.get("time_to_settlement_hours") or item.get("time_to_close_hours") or 9e9),
            str(item.get("ticker") or ""),
        )
    )
    return selected[: max(0, int(max_contracts))]


def observation_from_candidate(
    row: Mapping[str, Any],
    *,
    decision_time: str,
    source_path: Path,
    source_index: int,
) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "")
    yes_bid = probability(row.get("yes_bid"))
    yes_ask = probability(row.get("yes_ask"))
    yes_mid = midpoint(yes_bid, yes_ask)
    close_time = (
        row.get("settlement_time")
        or row.get("expected_expiration_time")
        or row.get("expiration_time")
        or row.get("close_time")
    )
    return {
        "schema_version": "KalshiWorldCupProxyFeatureObservationV1",
        "observation_id": observation_id(
            ticker=ticker, decision_time=decision_time, source_row_index=source_index
        ),
        "contract_ticker": ticker,
        "event_ticker": row.get("event_ticker"),
        "series_ticker": row.get("series_ticker"),
        "market_type": market_type(row),
        "title": row.get("title"),
        "subtitle": row.get("subtitle"),
        "selection_token": selection_token(ticker),
        "decision_time": decision_time,
        "quote_time": decision_time,
        "close_time": close_time,
        "expected_expiration_time": close_time,
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "yes_mid": yes_mid,
        "yes_spread": optional_float(row.get("yes_spread")),
        "market_consensus_prediction": prediction_side(consensus_prediction(yes_mid)),
        "longshot_fade_prediction": prediction_side(longshot_fade_prediction(yes_bid, yes_ask)),
        "feature_status": "world_cup_proxy_features_ready",
        "feature_policy": "kalshi_market_structure_only_not_soccer_handicap",
        "label_status": "pending_settled_kalshi_outcome",
        "calibrated_probability": None,
        "expected_value_per_contract": None,
        "usable": False,
        "source_artifact": str(source_path),
        "source_artifact_sha256": sha256_or_none(source_path),
        "source_row_index": source_index,
        "research_only": True,
        "execution_enabled": False,
    }


def consensus_prediction(yes_mid: float | None) -> int | None:
    if yes_mid is None or abs(yes_mid - 0.5) < 1e-9:
        return None
    return 1 if yes_mid > 0.5 else 0


def longshot_fade_prediction(yes_bid: float | None, yes_ask: float | None) -> int | None:
    if yes_ask is not None and yes_ask <= 0.25:
        return 0
    if yes_bid is not None and yes_bid >= 0.75:
        return 1
    return None


def prediction_side(value: int | None) -> str | None:
    if value == 1:
        return "yes"
    if value == 0:
        return "no"
    return None


def midpoint(left: float | None, right: float | None) -> float | None:
    if left is not None and right is not None:
        return round((left + right) / 2.0, 6)
    return right if right is not None else left


def selection_token(ticker: str) -> str | None:
    if "-" not in ticker:
        return None
    token = ticker.rsplit("-", maxsplit=1)[-1].strip().upper()
    return token or None


def market_type(row: Mapping[str, Any]) -> str:
    series = str(row.get("series_ticker") or "").upper()
    if "SPREAD" in series:
        return "spread"
    if "TOTAL" in series:
        return "total"
    if "BTTS" in series:
        return "both_teams_to_score"
    if "1H" in series:
        return "first_half"
    if "2H" in series:
        return "second_half"
    if "TEAM" in series:
        return "team_prop"
    return "game"


def capture_public_observed_markets_snapshot(
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
        base_snapshot.get("markets", []) if isinstance(base_snapshot.get("markets"), list) else []
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
        "status": "kalshi_public_observed_market_fetch_ok"
        if markets
        else "kalshi_public_observed_market_fetch_empty",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "query": {
            "mode": "world_cup_exact_observed_ticker_probe",
            "observed_ticker_count": len(tickers),
            "base_snapshot_path": str(base_snapshot_path) if base_snapshot_path else None,
        },
        "summary": {
            "market_count": len(markets),
            "base_market_count": len(base_markets),
            "observed_ticker_count": len(tickers),
            "probe_error_count": len(probe_errors),
            "settled_label_ready_count": sum(
                1 for market in markets if settlement_outcome(market) is not None
            ),
        },
        "probe_errors_sample": probe_errors[:50],
        "safety": safety_flags(public_market_data_calls=True),
        "markets": markets,
    }
    latest_path = raw_dir / "kalshi_observed_markets_latest.json"
    text = json.dumps(snapshot, indent=2, sort_keys=True, default=str) + "\n"
    (raw_dir / f"kalshi_observed_markets_{safe_stamp(generated)}.json").write_text(
        text, encoding="utf-8"
    )
    latest_path.write_text(text, encoding="utf-8")
    return latest_path


def due_observed_tickers(
    *,
    universe_scan_path: Path,
    observation_dir: Path,
    generated_utc: str,
    max_tickers: int,
) -> list[str]:
    rows: list[Mapping[str, Any]] = []
    universe = read_json_or_empty(universe_scan_path)
    if safe_research_artifact(universe):
        rows.extend(
            observation_from_candidate(
                row, decision_time=generated_utc, source_path=universe_scan_path, source_index=index
            )
            for index, row in enumerate(world_cup_candidates(universe, max_contracts=max_tickers))
        )
    rows.extend(load_packets(observation_dir)["rows"])
    cutoff = timestamp(generated_utc) or datetime.now(UTC).timestamp()
    output: list[str] = []
    seen: set[str] = set()
    for row in rows:
        due_at = timestamp(row.get("expected_expiration_time") or row.get("close_time"))
        ticker = str(row.get("contract_ticker") or "").strip()
        if not ticker or ticker in seen or due_at is None or due_at > cutoff:
            continue
        seen.add(ticker)
        output.append(ticker)
        if len(output) >= max(0, max_tickers):
            break
    return output


def label_observations(
    observations: Sequence[Mapping[str, Any]],
    settled_index: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    labels: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for row in observations:
        ticker = str(row.get("contract_ticker") or "").strip()
        market = settled_index.get(ticker)
        if market is None:
            blocked.append(blocked_label(row, "pending_contract_not_settled_in_snapshot"))
            continue
        yes_outcome = settlement_outcome(market)
        if yes_outcome is None:
            blocked.append(blocked_label(row, "settlement_outcome_missing"))
            continue
        close_time = iso_time(
            first_present(
                market,
                ["close_time", "expected_expiration_time", "expiration_time"],
                row.get("close_time"),
            )
        )
        settled_time = iso_time(
            first_present(
                market, ["settlement_ts", "settled_time", "expiration_time", "close_time"]
            )
        )
        if close_time is None or settled_time is None:
            blocked.append(blocked_label(row, "settlement_timestamps_missing"))
            continue
        labels.append(
            {
                **dict(row),
                "label_status": "labeled_from_public_kalshi_settled_market",
                "yes_outcome": yes_outcome,
                "side_outcome": yes_outcome,
                "close_time": close_time,
                "settled_time": settled_time,
                "label_source": "public_kalshi_settled_market_payload",
                "settlement_result": market.get("result"),
                "settlement_value_dollars": market.get("settlement_value_dollars"),
                "calibrated_probability": None,
                "expected_value_per_contract": None,
                "usable": False,
            }
        )
    return labels, blocked


def settled_market_index(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    markets = snapshot.get("markets", [])
    if not isinstance(markets, list):
        return {}
    output: dict[str, Mapping[str, Any]] = {}
    for market in markets:
        if not isinstance(market, Mapping):
            continue
        ticker = str(market.get("ticker") or "").strip()
        if ticker and settlement_outcome(market) is not None:
            output[ticker] = market
    return output


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


def observation_due_summary(
    rows: Sequence[Mapping[str, Any]], *, generated_utc: str
) -> dict[str, Any]:
    cutoff = timestamp(generated_utc) or datetime.now(UTC).timestamp()
    due_contracts: set[str] = set()
    future_times: list[float] = []
    due_times: list[float] = []
    for row in rows:
        ticker = str(row.get("contract_ticker") or "").strip()
        due_at = timestamp(row.get("expected_expiration_time") or row.get("close_time"))
        if not ticker or due_at is None:
            continue
        if due_at <= cutoff:
            due_contracts.add(ticker)
            due_times.append(due_at)
        else:
            future_times.append(due_at)
    next_expiration = min(future_times) if future_times else None
    oldest_due = min(due_times) if due_times else None
    return {
        "due_distinct_contract_count": len(due_contracts),
        "oldest_due_expected_expiration_utc": iso_from_timestamp(oldest_due),
        "next_expected_expiration_utc": iso_from_timestamp(next_expiration),
        "next_public_label_probe_utc": generated_utc
        if due_contracts
        else iso_from_timestamp(next_expiration),
    }


def build_gates(
    *,
    universe_safe: bool,
    candidate_count: int,
    observation_count: int,
    new_observation_count: int,
    settled_market_count: int,
    label_count: int,
    observation_dir: Path,
    label_dir: Path,
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        gate(
            "world_cup_universe_safe",
            "pass" if universe_safe else "blocked",
            "Safe universe scan required.",
        ),
        gate(
            "world_cup_candidates_present",
            "pass" if candidate_count else "blocked",
            f"{candidate_count} World Cup/FIFA candidate(s).",
        ),
        gate(
            "new_observations_recorded",
            "pass" if new_observation_count else "warn",
            f"{new_observation_count} new observation row(s).",
        ),
        gate(
            "observations_available",
            "pass" if observation_count else "blocked",
            f"{observation_count} total observation row(s).",
        ),
        gate(
            "settled_markets_available",
            "pass" if settled_market_count else "warn",
            f"{settled_market_count} public market row(s) loaded.",
        ),
        gate(
            "label_rows_available",
            "pass" if label_count else "warn",
            f"{label_count} label row(s) emitted.",
        ),
        gate(
            "manual_drop_dirs_outside_repo",
            "pass"
            if outside_repo(observation_dir, CONTROL_REPO) and outside_repo(label_dir, CONTROL_REPO)
            else "blocked",
            "Observation and label packets must stay outside the repo.",
        ),
        gate(
            "no_probability_ev_or_execution_claims",
            "pass"
            if all(
                row.get("usable") is False
                and row.get("calibrated_probability") is None
                and row.get("expected_value_per_contract") is None
                for row in rows
            )
            else "fail",
            "Rows remain observation/label evidence only.",
        ),
    ]


def loop_status(
    *,
    universe_safe: bool,
    candidate_count: int,
    observation_count: int,
    label_count: int,
) -> str:
    if not universe_safe:
        return "world_cup_proxy_observation_loop_blocked_missing_universe_scan"
    if candidate_count <= 0:
        return "world_cup_proxy_observation_loop_blocked_no_world_cup_candidates"
    if label_count > 0:
        return "world_cup_proxy_observation_loop_label_rows_ready"
    if observation_count > 0:
        return "world_cup_proxy_observation_loop_ready_waiting_settlement"
    return "world_cup_proxy_observation_loop_blocked_no_observations"


def next_action(status: str) -> dict[str, str]:
    if status == "world_cup_proxy_observation_loop_label_rows_ready":
        return {
            "name": "kalshi_world_cup_proxy_feature_model_falsification",
            "why": "Exact World Cup Kalshi observations have settled labels; test pre-registered market-structure signals with OOS/FDR.",
            "stop_condition": "Stop before calibrated probability, EV, paper stake, or live orders.",
        }
    if status == "world_cup_proxy_observation_loop_ready_waiting_settlement":
        return {
            "name": "kalshi_world_cup_proxy_observation_accumulation",
            "why": "World Cup observations are archived; keep probing exact tickers after settlement.",
            "stop_condition": "Stop before using non-settled contracts as labels.",
        }
    return {
        "name": "kalshi_world_cup_proxy_observation_blocker_review",
        "why": "No safe World Cup observation set is available.",
        "stop_condition": "Stop before inventing labels or model probabilities.",
    }


def write_world_cup_proxy_observation_outputs(
    report: Mapping[str, Any],
    *,
    out_dir: Path = DEFAULT_OUT_DIR,
    observation_dir: Path = DEFAULT_OBSERVATION_DIR,
    label_dir: Path = DEFAULT_LABEL_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-world-cup-proxy-observation-loop.json"
    md_path = out_dir / "kalshi-world-cup-proxy-observation-loop.md"
    csv_path = out_dir / "kalshi-world-cup-proxy-observation-loop.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, csv_path)
    paths = {"json_path": str(json_path), "markdown_path": str(md_path), "csv_path": str(csv_path)}

    stamp = safe_stamp(str(report.get("generated_utc") or utc_now()))
    observation_rows = packet_rows(report.get("observation_packet"))
    if observation_rows:
        observation_dir.mkdir(parents=True, exist_ok=True)
        obs_path = observation_dir / f"world_cup_proxy_observations_{stamp}.json"
        obs_latest = observation_dir / "world_cup_proxy_observations_latest.json"
        obs_text = (
            json.dumps(report["observation_packet"], indent=2, sort_keys=True, default=str) + "\n"
        )
        obs_path.write_text(obs_text, encoding="utf-8")
        obs_latest.write_text(obs_text, encoding="utf-8")
        paths["observation_packet_path"] = str(obs_path)
        paths["observation_packet_latest_path"] = str(obs_latest)

    label_rows = packet_rows(report.get("label_packet"))
    if label_rows:
        label_dir.mkdir(parents=True, exist_ok=True)
        label_path = label_dir / f"world_cup_proxy_labels_{stamp}.json"
        label_latest = label_dir / "world_cup_proxy_labels_latest.json"
        label_text = (
            json.dumps(report["label_packet"], indent=2, sort_keys=True, default=str) + "\n"
        )
        label_path.write_text(label_text, encoding="utf-8")
        label_latest.write_text(label_text, encoding="utf-8")
        paths["label_packet_path"] = str(label_path)
        paths["label_packet_latest_path"] = str(label_latest)

    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-world-cup-proxy-observation-loop.json"
    latest_md = MACRO_DIR / "latest-kalshi-world-cup-proxy-observation-loop.md"
    latest_csv = MACRO_DIR / "latest-kalshi-world-cup-proxy-observation-loop.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, latest_csv)
    paths["latest_json_path"] = str(latest_json)
    paths["latest_markdown_path"] = str(latest_md)
    paths["latest_csv_path"] = str(latest_csv)
    return paths


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi World Cup Proxy Observation Loop",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Candidates: `{summary.get('candidate_count')}`",
        f"- Observations: `{summary.get('total_observation_row_count')}`",
        f"- Labels: `{summary.get('label_row_count')}`",
        f"- Due contracts: `{summary.get('due_distinct_contract_count')}`",
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
            "This report emits research observations and labels only. It is not a list of bets.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(report: Mapping[str, Any], path: Path) -> None:
    rows = [
        *packet_rows(report.get("observation_packet")),
        *packet_rows(report.get("label_packet")),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def load_packets(directory: Path) -> dict[str, Any]:
    rows: list[Mapping[str, Any]] = []
    packet_paths: list[str] = []
    unsafe_packets: list[dict[str, str]] = []
    if not directory.exists():
        return {"packet_count": 0, "packet_paths": [], "rows": [], "unsafe_packets": []}
    for path in sorted(directory.glob("*.json")):
        payload = read_json_or_empty(path)
        if not safe_research_artifact(payload):
            unsafe_packets.append({"path": str(path), "reason": "unsafe_or_missing_research_flags"})
            continue
        packet_rows = payload.get("rows", [])
        if not isinstance(packet_rows, list):
            unsafe_packets.append({"path": str(path), "reason": "missing_rows_list"})
            continue
        packet_paths.append(str(path))
        rows.extend(row for row in packet_rows if isinstance(row, Mapping))
    return {
        "packet_count": len(packet_paths),
        "packet_paths": packet_paths,
        "rows": rows,
        "unsafe_packets": unsafe_packets,
    }


def dedupe_by_id(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        oid = str(row.get("observation_id") or "")
        if oid and oid not in output:
            output[oid] = dict(row)
    return sorted(output.values(), key=lambda item: str(item.get("observation_id") or ""))


def observation_ids(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    return {str(row.get("observation_id") or "") for row in rows if row.get("observation_id")}


def packet_rows(packet: Any) -> list[dict[str, Any]]:
    if not isinstance(packet, Mapping) or not isinstance(packet.get("rows"), list):
        return []
    return [dict(row) for row in packet["rows"] if isinstance(row, Mapping)]


def safe_packet(
    *,
    generated_utc: str,
    packet_type: str,
    rows: Sequence[Mapping[str, Any]],
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_utc": generated_utc,
        "packet_type": packet_type,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
        "usable": False,
        "inputs": dict(inputs),
        "summary": {"row_count": len(rows)},
        "rows": [dict(row) for row in rows],
        "safety": safety_flags(public_market_data_calls=False),
    }


def blocked_label(row: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "observation_id": row.get("observation_id"),
        "contract_ticker": row.get("contract_ticker"),
        "series_ticker": row.get("series_ticker"),
        "decision_time": row.get("decision_time"),
        "label_status": reason,
    }


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def gate_counts(gates: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return counts(item.get("status") for item in gates)


def counts(values: Any) -> dict[str, int]:
    counter = Counter(str(value or "unknown") for value in values)
    return dict(sorted(counter.items()))


def first_present(mapping: Mapping[str, Any], keys: Sequence[str], fallback: Any = None) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return fallback


def iso_time(value: Any) -> str | None:
    ts = timestamp(value)
    return iso_from_timestamp(ts) if ts is not None else None


def observation_id(*, ticker: str, decision_time: str, source_row_index: int) -> str:
    key = f"{ticker}|{decision_time}|{source_row_index}"
    return "world_cup_obs_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def fetch_json_url(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.load(response)
    return payload if isinstance(payload, dict) else {}


def safe_stamp(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum())[:32]


def safety_flags(*, public_market_data_calls: bool) -> dict[str, Any]:
    return {
        "research_only": True,
        "public_market_data_calls": public_market_data_calls,
        "authenticated_api_calls": False,
        "account_or_order_paths": False,
        "market_execution": False,
        "database_writes": False,
        "paid_calls": False,
        "staking_or_sizing_guidance": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-scan-path", type=Path, default=DEFAULT_UNIVERSE_SCAN_PATH)
    parser.add_argument("--settled-snapshot-path", type=Path, default=DEFAULT_SETTLED_SNAPSHOT_PATH)
    parser.add_argument("--settled-raw-dir", type=Path, default=DEFAULT_SETTLED_RAW_DIR)
    parser.add_argument("--observation-dir", type=Path, default=DEFAULT_OBSERVATION_DIR)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-contracts", type=int, default=DEFAULT_MAX_CONTRACTS)
    parser.add_argument("--observed-probe-max-tickers", type=int, default=DEFAULT_MAX_CONTRACTS)
    parser.add_argument("--probe-observed-public", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    generated = utc_now()
    settled_snapshot_path = args.settled_snapshot_path
    public_calls = False
    if args.probe_observed_public:
        tickers = due_observed_tickers(
            universe_scan_path=args.universe_scan_path,
            observation_dir=args.observation_dir,
            generated_utc=generated,
            max_tickers=args.observed_probe_max_tickers,
        )
        settled_snapshot_path = capture_public_observed_markets_snapshot(
            tickers=tickers,
            raw_dir=args.settled_raw_dir,
            base_snapshot_path=args.settled_snapshot_path
            if args.settled_snapshot_path.exists()
            else None,
            generated_utc=generated,
        )
        public_calls = bool(tickers)
    report = build_world_cup_proxy_observation_loop(
        universe_scan_path=args.universe_scan_path,
        settled_snapshot_path=settled_snapshot_path,
        observation_dir=args.observation_dir,
        label_dir=args.label_dir,
        generated_utc=generated,
        max_contracts=args.max_contracts,
        public_market_data_calls=public_calls,
    )
    if args.write:
        paths = write_world_cup_proxy_observation_outputs(
            report,
            out_dir=args.out_dir,
            observation_dir=args.observation_dir,
            label_dir=args.label_dir,
        )
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
