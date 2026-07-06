#!/usr/bin/env python3
"""Archive sports consensus observations and exact Kalshi settlement labels.

This is the accumulator for the sports no-vig consensus lane:

- Snapshot valid preflight candidates with timestamp-matched Kalshi mid prices.
- Persist observation packets outside the repo under manual_drops.
- Attach labels only from exact public Kalshi settlement payloads.
- Feed the falsification ledger with replayable observation/label packets.

The output remains research-only. No EV, sizing, paper stake, live eligibility,
account path, or order path is created here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import (  # noqa: E402
    counts,
    gate,
    gate_counts,
    iso_time,
    optional_float,
    outside_repo,
    path_is_within,
    probability,
    read_json_or_empty,
    safe_research_artifact,
    safe_stamp,
    safety_flags,
    sha256_or_none,
    timestamp,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_PREFLIGHT_PATH = MACRO_DIR / "latest-kalshi-sports-consensus-preflight.json"
DEFAULT_UNIVERSE_PATH = MACRO_DIR / "latest-kalshi-universe-scan.json"
DEFAULT_SETTLED_RAW_DIR = Path("/home/mrwatson/manual_drops/kalshi_sports_consensus_settlements")
DEFAULT_SETTLED_SNAPSHOT_PATH = (
    DEFAULT_SETTLED_RAW_DIR / "kalshi_sports_consensus_observed_markets_latest.json"
)
DEFAULT_OBSERVATION_DIR = Path("/home/mrwatson/manual_drops/kalshi_sports_consensus_observations")
DEFAULT_LABEL_DIR = Path("/home/mrwatson/manual_drops/kalshi_sports_consensus_labels")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-consensus-observation-loop-latest"
KALSHI_PUBLIC_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
FAMILY_ID = "sports_no_vig_consensus"

CSV_FIELDS = [
    "observation_id",
    "contract_ticker",
    "event_ticker",
    "side",
    "family_id",
    "sport_key",
    "market_key",
    "cluster_key",
    "observed_utc",
    "close_time",
    "expected_expiration_time",
    "kalshi_mid_for_side",
    "consensus_probability_for_side",
    "divergence",
    "book_count",
    "distinct_books",
    "label_status",
    "yes_outcome",
    "side_outcome",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_sports_consensus_observation_loop(
    *,
    preflight_path: Path = DEFAULT_PREFLIGHT_PATH,
    universe_path: Path = DEFAULT_UNIVERSE_PATH,
    settled_snapshot_path: Path = DEFAULT_SETTLED_SNAPSHOT_PATH,
    observation_dir: Path = DEFAULT_OBSERVATION_DIR,
    label_dir: Path = DEFAULT_LABEL_DIR,
    generated_utc: str | None = None,
    public_market_data_calls: bool = False,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    preflight = read_json_or_empty(preflight_path) if preflight_path.is_file() else {}
    universe = read_json_or_empty(universe_path) if universe_path.is_file() else {}
    settled_snapshot = (
        read_json_or_empty(settled_snapshot_path) if settled_snapshot_path.is_file() else {}
    )
    preflight_safe = safe_research_artifact(preflight)
    universe_safe = safe_research_artifact(universe)
    candidate_rows = (
        consensus_observations(
            preflight=preflight,
            universe=universe,
            preflight_path=preflight_path,
            universe_path=universe_path,
            generated_utc=generated,
        )
        if preflight_safe and universe_safe
        else []
    )

    existing_observations = load_packets(observation_dir)
    existing_ids = observation_ids(existing_observations["rows"])
    new_observations = [
        row for row in candidate_rows if str(row.get("observation_id") or "") not in existing_ids
    ]
    all_observations = dedupe_by_id([*existing_observations["rows"], *candidate_rows])

    existing_labels = load_packets(label_dir)
    existing_label_ids = observation_ids(existing_labels["rows"])
    settled_index = settled_market_index(settled_snapshot)
    market_index = market_snapshot_index(settled_snapshot)
    computed_labels, blocked_labels = label_observations(all_observations, settled_index)
    new_labels = [
        row for row in computed_labels if str(row.get("observation_id") or "") not in existing_label_ids
    ]
    all_labels = dedupe_by_id([*existing_labels["rows"], *computed_labels])
    due = due_summary(
        all_observations,
        generated_utc=generated,
        labeled_contract_tickers={
            str(row.get("contract_ticker") or "").strip()
            for row in all_labels
            if str(row.get("contract_ticker") or "").strip()
        },
        market_index=market_index,
    )
    gates = build_gates(
        preflight_safe=preflight_safe,
        universe_safe=universe_safe,
        observation_count=len(all_observations),
        new_observation_count=len(new_observations),
        label_count=len(all_labels),
        settled_market_count=len(settled_index),
        observation_dir=observation_dir,
        label_dir=label_dir,
        rows=[*all_observations, *all_labels],
    )
    status = loop_status(
        preflight_safe=preflight_safe,
        universe_safe=universe_safe,
        observation_count=len(all_observations),
        label_count=len(all_labels),
    )
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "family_id": FAMILY_ID,
        "public_market_data_calls": public_market_data_calls,
        "authenticated_api_calls": False,
        "provider_api_calls": public_market_data_calls,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "inputs": {
            "preflight_path": str(preflight_path),
            "preflight_sha256": sha256_or_none(preflight_path),
            "preflight_status": preflight.get("status") if isinstance(preflight, Mapping) else None,
            "universe_path": str(universe_path),
            "universe_sha256": sha256_or_none(universe_path),
            "settled_snapshot_path": str(settled_snapshot_path),
            "settled_snapshot_sha256": sha256_or_none(settled_snapshot_path),
            "observation_dir": str(observation_dir),
            "label_dir": str(label_dir),
        },
        "method": {
            "observation_rule": "Archive every valid sports no-vig consensus preflight candidate with exact Kalshi ticker and timestamp-matched Kalshi mid.",
            "label_rule": "Attach outcomes only from public Kalshi market payloads matched by exact contract_ticker.",
            "model_boundary": "The sharp timestamp-matched multi-book no-vig consensus line is source evidence, not an automatically tradable probability.",
            "ev_boundary": "This loop does not compute EV, calibrated probability, paper stake, live eligibility, or orders.",
        },
        "summary": {
            "preflight_safe": preflight_safe,
            "universe_safe": universe_safe,
            "preflight_valid_candidate_count": _int(
                _summary(preflight).get("valid_candidate_count")
            ),
            "new_observation_row_count": len(new_observations),
            "existing_observation_packet_count": existing_observations["packet_count"],
            "existing_observation_row_count": len(existing_observations["rows"]),
            "total_observation_row_count": len(all_observations),
            "distinct_contract_count": len({row.get("contract_ticker") for row in all_observations}),
            "settled_market_count": len(settled_index),
            "existing_label_packet_count": existing_labels["packet_count"],
            "existing_label_row_count": len(existing_labels["rows"]),
            "new_label_row_count": len(new_labels),
            "label_row_count": len(all_labels),
            "blocked_label_row_count": len(blocked_labels),
            "sport_key_counts": counts([row.get("sport_key") for row in all_observations]),
            "label_status_counts": counts(
                [row.get("label_status") for row in [*all_labels, *blocked_labels]]
            ),
            "due_observation_row_count": due["due_observation_row_count"],
            "due_distinct_contract_count": due["due_distinct_contract_count"],
            "due_observation_row_count_by_sport": due["due_observation_row_count_by_sport"],
            "due_distinct_contract_count_by_sport": due["due_distinct_contract_count_by_sport"],
            "labeled_due_observation_row_count": due["labeled_due_observation_row_count"],
            "labeled_due_distinct_contract_count": due["labeled_due_distinct_contract_count"],
            "labeled_due_observation_row_count_by_sport": due[
                "labeled_due_observation_row_count_by_sport"
            ],
            "labeled_due_distinct_contract_count_by_sport": due[
                "labeled_due_distinct_contract_count_by_sport"
            ],
            "not_due_distinct_contract_count": due["not_due_distinct_contract_count"],
            "not_due_distinct_contract_count_by_sport": due[
                "not_due_distinct_contract_count_by_sport"
            ],
            "next_expected_expiration_utc": due["next_expected_expiration_utc"],
            "next_public_label_probe_utc": due["next_public_label_probe_utc"],
            "gate_counts": gate_counts(gates),
        },
        "observation_packet": safe_packet(
            generated_utc=generated,
            packet_type="kalshi_sports_consensus_observations",
            rows=new_observations,
            inputs={"preflight_path": str(preflight_path), "universe_path": str(universe_path)},
        ),
        "label_packet": safe_packet(
            generated_utc=generated,
            packet_type="kalshi_sports_consensus_labels",
            rows=new_labels,
            inputs={
                "observation_dir": str(observation_dir),
                "settled_snapshot_path": str(settled_snapshot_path),
            },
        ),
        "gates": gates,
        "observation_rows_sample": all_observations[:20],
        "label_rows_sample": all_labels[:20],
        "blocked_label_rows_sample": blocked_labels[:50],
        "label_probe_schedule": due,
        "next_action": next_action(status),
        "safety": safety_flags(public_market_data_calls=public_market_data_calls),
    }


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
    base_markets = _market_list(base_snapshot)
    markets: list[Mapping[str, Any]] = [row for row in base_markets if isinstance(row, Mapping)]
    seen = {str(row.get("ticker") or "") for row in markets}
    errors: list[dict[str, str]] = []
    for ticker in tickers:
        if not ticker or ticker in seen:
            continue
        try:
            payload = fetch(
                f"{KALSHI_PUBLIC_BASE_URL}/markets/{urllib.parse.quote(ticker, safe='')}"
            )
        except Exception as exc:
            errors.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})
            continue
        market = payload.get("market") if isinstance(payload, Mapping) else None
        if isinstance(market, Mapping):
            markets.append(market)
            seen.add(ticker)
    snapshot = {
        "schema_version": 1,
        "created_at_utc": generated,
        "status": "kalshi_sports_consensus_observed_market_fetch_ok"
        if markets
        else "kalshi_sports_consensus_observed_market_fetch_empty",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "query": {
            "mode": "exact_consensus_observed_ticker_probe",
            "observed_ticker_count": len(tickers),
            "base_snapshot_path": str(base_snapshot_path) if base_snapshot_path else None,
        },
        "summary": {
            "market_count": len(markets),
            "base_market_count": len(base_markets),
            "observed_ticker_count": len(tickers),
            "probe_error_count": len(errors),
            "settled_label_ready_count": sum(
                1 for market in markets if settlement_outcome(market) is not None
            ),
        },
        "probe_errors_sample": errors[:50],
        "safety": safety_flags(public_market_data_calls=True),
        "markets": markets,
    }
    stamp = safe_stamp(generated)
    snapshot_path = raw_dir / f"kalshi_sports_consensus_observed_markets_{stamp}.json"
    latest_path = raw_dir / "kalshi_sports_consensus_observed_markets_latest.json"
    text = json.dumps(snapshot, indent=2, sort_keys=True, default=str) + "\n"
    snapshot_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return latest_path


def due_observed_tickers(
    *,
    preflight_path: Path,
    universe_path: Path,
    observation_dir: Path,
    generated_utc: str,
    max_tickers: int,
) -> list[str]:
    preflight = read_json_or_empty(preflight_path) if preflight_path.is_file() else {}
    universe = read_json_or_empty(universe_path) if universe_path.is_file() else {}
    rows: list[Mapping[str, Any]] = []
    if safe_research_artifact(preflight) and safe_research_artifact(universe):
        rows.extend(
            consensus_observations(
                preflight=preflight,
                universe=universe,
                preflight_path=preflight_path,
                universe_path=universe_path,
                generated_utc=generated_utc,
            )
        )
    rows.extend(load_packets(observation_dir)["rows"])
    cutoff = timestamp(generated_utc) or datetime.now(UTC).timestamp()
    output: list[str] = []
    seen: set[str] = set()
    for row in rows:
        due_at = timestamp(_first_present(row, ["expected_expiration_time", "settlement_time", "close_time"]))
        ticker = str(row.get("contract_ticker") or "").strip()
        if not ticker or ticker in seen or due_at is None or due_at > cutoff:
            continue
        seen.add(ticker)
        output.append(ticker)
        if len(output) >= max(0, max_tickers):
            break
    return output


def consensus_observations(
    *,
    preflight: Mapping[str, Any],
    universe: Mapping[str, Any],
    preflight_path: Path,
    universe_path: Path,
    generated_utc: str,
) -> list[dict[str, Any]]:
    market_index = index_market_rows(universe)
    source_preflight_sha = sha256_or_none(preflight_path)
    source_universe_sha = sha256_or_none(universe_path)
    rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(valid_preflight_candidates(preflight)):
        ticker = str(candidate.get("kalshi_ticker") or candidate.get("contract_ticker") or "").strip()
        side = _normalize_side(candidate.get("side"))
        universe_row = market_index.get(ticker, {})
        observed_utc = iso_time(
            candidate.get("kalshi_observed_utc")
            or preflight.get("created_at_utc")
            or preflight.get("generated_utc")
            or generated_utc
        )
        kalshi_mid = market_mid_for_side(universe_row, side)
        consensus_probability = probability(
            candidate.get(
                "consensus_no_vig_probability_for_side",
                candidate.get("consensus_probability_for_side"),
            )
        )
        blockers = observation_blockers(
            ticker=ticker,
            side=side,
            observed_utc=observed_utc,
            kalshi_mid=kalshi_mid,
            consensus_probability=consensus_probability,
            universe_row=universe_row,
        )
        if blockers:
            continue
        event_ticker = (
            universe_row.get("event_ticker")
            or candidate.get("event_ticker")
            or derive_event_ticker(ticker)
        )
        series_ticker = universe_row.get("series_ticker") or derive_market_key(ticker)
        sport_key = sport_key_for_row(universe_row, ticker)
        market_key = str(series_ticker or derive_market_key(ticker) or "unknown")
        cluster_key = f"{sport_key}|{market_key}|{event_ticker}"
        divergence = float(consensus_probability) - float(kalshi_mid)
        rows.append(
            {
                "schema_version": "KalshiSportsConsensusObservationV1",
                "observation_id": observation_id(
                    ticker=ticker,
                    side=side or "unknown",
                    observed_utc=observed_utc or generated_utc,
                    source_row_index=index,
                ),
                "contract_ticker": ticker,
                "event_ticker": event_ticker,
                "series_ticker": series_ticker,
                "side": side,
                "family_id": FAMILY_ID,
                "sport_key": sport_key,
                "market_key": market_key,
                "cluster_key": cluster_key,
                "observed_utc": observed_utc,
                "decision_time": observed_utc,
                "quote_time": observed_utc,
                "timestamp_source": "sports_consensus_preflight_kalshi_observed_utc",
                "close_time": iso_time(universe_row.get("close_time")),
                "expected_expiration_time": iso_time(
                    _first_present(
                        universe_row,
                        ["expected_expiration_time", "settlement_time", "expiration_time"],
                    )
                ),
                "kalshi_mid_for_side": kalshi_mid,
                "consensus_probability_for_side": consensus_probability,
                "consensus_no_vig_probability_for_side": consensus_probability,
                "divergence": divergence,
                "book_count": _int(candidate.get("book_count")),
                "distinct_books": list(candidate.get("distinct_books") or []),
                "timestamp_skew_seconds": optional_float(candidate.get("timestamp_skew_seconds")),
                "consensus_method": candidate.get("consensus_method"),
                "source_reference_sha256": _input_sha(preflight, "consensus_sha256"),
                "source_preflight_artifact": str(preflight_path),
                "source_preflight_sha256": source_preflight_sha,
                "source_universe_artifact": str(universe_path),
                "source_universe_sha256": source_universe_sha,
                "source_row_index": index,
                "label_status": "pending_settled_kalshi_outcome",
                "calibrated_probability": None,
                "expected_value_per_contract": None,
                "usable": False,
                "research_only": True,
                "execution_enabled": False,
            }
        )
    return rows


def observation_blockers(
    *,
    ticker: str,
    side: str | None,
    observed_utc: str | None,
    kalshi_mid: float | None,
    consensus_probability: float | None,
    universe_row: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not ticker:
        blockers.append("missing_exact_kalshi_ticker")
    if side not in {"yes", "no"}:
        blockers.append("missing_side")
    if observed_utc is None:
        blockers.append("missing_observed_utc")
    if not universe_row:
        blockers.append("missing_universe_row")
    if kalshi_mid is None:
        blockers.append("missing_timestamp_matched_kalshi_mid")
    if consensus_probability is None:
        blockers.append("missing_consensus_probability_for_side")
    return blockers


def label_observations(
    observations: Sequence[Mapping[str, Any]],
    settled_index: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    labels: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for row in observations:
        ticker = str(row.get("contract_ticker") or "").strip()
        side = _normalize_side(row.get("side"))
        market = settled_index.get(ticker)
        if market is None:
            blocked.append(blocked_label(row, "pending_contract_not_settled_in_snapshot"))
            continue
        yes_outcome = settlement_outcome(market)
        if yes_outcome is None:
            blocked.append(blocked_label(row, "settlement_outcome_missing"))
            continue
        settled_time = iso_time(
            _first_present(market, ["settlement_ts", "settled_time", "expiration_time", "close_time"])
        )
        close_time = iso_time(
            _first_present(
                market,
                ["close_time", "expected_expiration_time", "expiration_time"],
                row.get("close_time"),
            )
        )
        if settled_time is None or close_time is None:
            blocked.append(blocked_label(row, "settlement_timestamps_missing"))
            continue
        labels.append(
            {
                **dict(row),
                "label_status": "labeled_from_public_kalshi_settled_market",
                "yes_outcome": yes_outcome,
                "side_outcome": yes_outcome if side == "yes" else 1 - yes_outcome,
                "close_time": close_time,
                "settled_time": settled_time,
                "settlement_time": settled_time,
                "settlement_time_utc": settled_time,
                "label_source": "public_kalshi_settled_market_payload",
                "settlement_result": market.get("result"),
                "settlement_value_dollars": market.get("settlement_value_dollars"),
                "calibrated_probability": None,
                "expected_value_per_contract": None,
                "usable": False,
                "research_only": True,
                "execution_enabled": False,
            }
        )
    return labels, blocked


def blocked_label(row: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "observation_id": row.get("observation_id"),
        "contract_ticker": row.get("contract_ticker"),
        "side": row.get("side"),
        "observed_utc": row.get("observed_utc"),
        "label_status": reason,
    }


def settled_market_index(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    for market in _market_list(snapshot):
        ticker = str(market.get("ticker") or market.get("contract_ticker") or "").strip()
        if ticker and settlement_outcome(market) is not None:
            output[ticker] = market
    return output


def market_snapshot_index(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    for market in _market_list(snapshot):
        ticker = str(market.get("ticker") or market.get("contract_ticker") or "").strip()
        if ticker:
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


def build_gates(
    *,
    preflight_safe: bool,
    universe_safe: bool,
    observation_count: int,
    new_observation_count: int,
    label_count: int,
    settled_market_count: int,
    observation_dir: Path,
    label_dir: Path,
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    return [
        gate(
            "sports_consensus_preflight_safe",
            "pass" if preflight_safe else "blocked",
            "Research-only sports consensus preflight artifact is required.",
        ),
        gate(
            "kalshi_universe_safe",
            "pass" if universe_safe else "blocked",
            "Research-only Kalshi universe artifact is required for timestamp-matched mids.",
        ),
        gate(
            "new_observations_recorded",
            "pass" if new_observation_count else "warn",
            f"{new_observation_count} new consensus observation row(s).",
        ),
        gate(
            "observations_available",
            "pass" if observation_count else "blocked",
            f"{observation_count} total consensus observation row(s).",
        ),
        gate(
            "settled_markets_available",
            "pass" if settled_market_count else "warn",
            f"{settled_market_count} settled public market row(s) loaded.",
        ),
        gate(
            "label_rows_available",
            "pass" if label_count else "warn",
            f"{label_count} consensus settlement label row(s).",
        ),
        gate(
            "manual_drop_dirs_outside_repo",
            "pass" if outside_repo(observation_dir, CONTROL_REPO) and outside_repo(label_dir, CONTROL_REPO) else "blocked",
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
            "Observations and labels remain evidence only.",
        ),
    ]


def loop_status(
    *,
    preflight_safe: bool,
    universe_safe: bool,
    observation_count: int,
    label_count: int,
) -> str:
    if not preflight_safe:
        return "sports_consensus_observation_loop_blocked_missing_preflight"
    if not universe_safe:
        return "sports_consensus_observation_loop_blocked_missing_universe"
    if label_count:
        return "sports_consensus_observation_loop_label_rows_ready"
    if observation_count:
        return "sports_consensus_observation_loop_ready_waiting_settlement"
    return "sports_consensus_observation_loop_blocked_no_observations"


def next_action(status: str) -> dict[str, str]:
    if status == "sports_consensus_observation_loop_label_rows_ready":
        return {
            "name": "kalshi_sports_consensus_falsification",
            "why": "Consensus observations now have exact Kalshi settlement labels; run OOS/FDR falsification.",
            "stop_condition": "Stop before EV, paper stake, or live promotion unless falsification gates pass.",
        }
    if status == "sports_consensus_observation_loop_ready_waiting_settlement":
        return {
            "name": "kalshi_sports_consensus_label_accumulation",
            "why": "Consensus observations are archived; keep probing exact public Kalshi tickers after settlement.",
            "stop_condition": "Stop before using sportsbook outcomes or projection outputs as settlement labels.",
        }
    return {
        "name": "kalshi_sports_consensus_input_repair",
        "why": "The consensus observation loop lacks safe preflight/universe inputs or valid observations.",
        "stop_condition": "Stop before fabricating observations, labels, probabilities, EV, stakes, or orders.",
    }


def write_sports_consensus_observation_outputs(
    report: Mapping[str, Any],
    *,
    out_dir: Path = DEFAULT_OUT_DIR,
    observation_dir: Path = DEFAULT_OBSERVATION_DIR,
    label_dir: Path = DEFAULT_LABEL_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-consensus-observation-loop.json"
    md_path = out_dir / "kalshi-sports-consensus-observation-loop.md"
    csv_path = out_dir / "kalshi-sports-consensus-observation-loop.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, csv_path)
    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
    }
    stamp = safe_stamp(str(report.get("generated_utc") or utc_now()))
    paths.update(write_packets(report, observation_dir=observation_dir, label_dir=label_dir, stamp=stamp))
    if path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-sports-consensus-observation-loop.json"
        latest_md = MACRO_DIR / "latest-kalshi-sports-consensus-observation-loop.md"
        latest_csv = MACRO_DIR / "latest-kalshi-sports-consensus-observation-loop.csv"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        write_csv(report, latest_csv)
        paths.update(
            {
                "latest_json_path": str(latest_json),
                "latest_markdown_path": str(latest_md),
                "latest_csv_path": str(latest_csv),
            }
        )
    return paths


def write_packets(
    report: Mapping[str, Any],
    *,
    observation_dir: Path,
    label_dir: Path,
    stamp: str,
) -> dict[str, str]:
    paths: dict[str, str] = {}
    observation_rows = packet_rows(report.get("observation_packet"))
    if observation_rows:
        observation_dir.mkdir(parents=True, exist_ok=True)
        obs_path = observation_dir / f"sports_consensus_observations_{stamp}.json"
        obs_latest = observation_dir / "sports_consensus_observations_latest.json"
        obs_text = json.dumps(report["observation_packet"], indent=2, sort_keys=True, default=str) + "\n"
        obs_path.write_text(obs_text, encoding="utf-8")
        obs_latest.write_text(obs_text, encoding="utf-8")
        paths["observation_packet_path"] = str(obs_path)
        paths["observation_packet_latest_path"] = str(obs_latest)
    label_rows = packet_rows(report.get("label_packet"))
    if label_rows:
        label_dir.mkdir(parents=True, exist_ok=True)
        label_path = label_dir / f"sports_consensus_labels_{stamp}.json"
        label_latest = label_dir / "sports_consensus_labels_latest.json"
        label_text = json.dumps(report["label_packet"], indent=2, sort_keys=True, default=str) + "\n"
        label_path.write_text(label_text, encoding="utf-8")
        label_latest.write_text(label_text, encoding="utf-8")
        paths["label_packet_path"] = str(label_path)
        paths["label_packet_latest_path"] = str(label_latest)
    return paths


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = _summary(report)
    next_step = report.get("next_action") if isinstance(report.get("next_action"), Mapping) else {}
    lines = [
        "# Kalshi Sports Consensus Observation Loop",
        "",
        f"- Status: `{report.get('status')}`",
        f"- New observations: `{summary.get('new_observation_row_count')}`",
        f"- Total observations: `{summary.get('total_observation_row_count')}`",
        f"- Due observations: `{summary.get('due_observation_row_count')}`",
        f"- Due contracts: `{summary.get('due_distinct_contract_count')}`",
        f"- Already labeled due observations: `{summary.get('labeled_due_observation_row_count')}`",
        f"- Already labeled due contracts: `{summary.get('labeled_due_distinct_contract_count')}`",
        f"- Next expected expiration: `{summary.get('next_expected_expiration_utc')}`",
        f"- Next public label probe: `{summary.get('next_public_label_probe_utc')}`",
        f"- Label rows: `{summary.get('label_row_count')}`",
        "",
        "## Label Source",
        "",
        "Labels come only from exact public Kalshi settlement payloads matched by contract ticker.",
        "Sportsbook consensus rows are source evidence, not labels and not automatic tradable probabilities.",
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
            "## Next Action",
            "",
            f"- Name: `{next_step.get('name')}`",
            f"- Why: {next_step.get('why')}",
            f"- Stop condition: {next_step.get('stop_condition')}",
            "",
            "Research-only evidence archive. No EV, sizing, paper stake, live eligibility, or order path is authorized here.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(report: Mapping[str, Any], path: Path) -> None:
    rows: list[Mapping[str, Any]] = []
    rows.extend(row for row in report.get("label_rows_sample", []) if isinstance(row, Mapping))
    rows.extend(row for row in report.get("observation_rows_sample", []) if isinstance(row, Mapping))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in CSV_FIELDS})


def load_packets(directory: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    paths: list[str] = []
    if not directory.exists():
        return {"packet_count": 0, "paths": [], "rows": []}
    for path in sorted(directory.glob("*.json")):
        payload = read_json_or_empty(path)
        if not safe_research_artifact(payload):
            continue
        packet_rows = payload.get("rows", [])
        if not isinstance(packet_rows, list):
            continue
        paths.append(str(path))
        rows.extend(dict(row) for row in packet_rows if isinstance(row, Mapping))
    return {"packet_count": len(paths), "paths": paths, "rows": dedupe_by_id(rows)}


def dedupe_by_id(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.get("observation_id") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(dict(row))
    output.sort(key=lambda item: (str(item.get("observed_utc") or ""), str(item.get("contract_ticker") or "")))
    return output


def observation_ids(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    return {str(row.get("observation_id") or "") for row in rows if row.get("observation_id")}


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
        "staking_or_sizing_guidance": False,
        "inputs": dict(inputs),
        "rows": list(rows),
        "safety": safety_flags(public_market_data_calls=False),
    }


def packet_rows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        return []
    rows = value.get("rows", [])
    return [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


def due_summary(
    rows: Sequence[Mapping[str, Any]],
    *,
    generated_utc: str,
    labeled_contract_tickers: set[str] | None = None,
    market_index: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    cutoff = timestamp(generated_utc) or datetime.now(UTC).timestamp()
    labeled = labeled_contract_tickers or set()
    markets = market_index or {}
    due_rows = 0
    due_contracts: set[str] = set()
    due_rows_by_sport: dict[str, int] = {}
    due_contracts_by_sport: dict[str, set[str]] = {}
    labeled_due_rows = 0
    labeled_due_contracts: set[str] = set()
    labeled_due_rows_by_sport: dict[str, int] = {}
    labeled_due_contracts_by_sport: dict[str, set[str]] = {}
    not_due_contracts: set[str] = set()
    not_due_contracts_by_sport: dict[str, set[str]] = {}
    future_times: list[float] = []
    for row in rows:
        ticker = str(row.get("contract_ticker") or "").strip()
        due_at = due_timestamp_for_observation(row, markets.get(ticker))
        if not ticker or due_at is None:
            continue
        sport = str(row.get("sport_key") or sport_key_for_row(row, ticker) or "unknown")
        if due_at <= cutoff:
            if ticker in labeled:
                labeled_due_rows += 1
                labeled_due_contracts.add(ticker)
                labeled_due_rows_by_sport[sport] = labeled_due_rows_by_sport.get(sport, 0) + 1
                labeled_due_contracts_by_sport.setdefault(sport, set()).add(ticker)
                continue
            due_rows += 1
            due_contracts.add(ticker)
            due_rows_by_sport[sport] = due_rows_by_sport.get(sport, 0) + 1
            due_contracts_by_sport.setdefault(sport, set()).add(ticker)
        else:
            not_due_contracts.add(ticker)
            not_due_contracts_by_sport.setdefault(sport, set()).add(ticker)
            future_times.append(due_at)
    next_expiration = min(future_times) if future_times else None
    due_distinct_by_sport = {
        sport: len(tickers) for sport, tickers in sorted(due_contracts_by_sport.items())
    }
    labeled_due_distinct_by_sport = {
        sport: len(tickers) for sport, tickers in sorted(labeled_due_contracts_by_sport.items())
    }
    not_due_distinct_by_sport = {
        sport: len(tickers - due_contracts_by_sport.get(sport, set()))
        for sport, tickers in sorted(not_due_contracts_by_sport.items())
    }
    return {
        "generated_utc": generated_utc,
        "due_observation_row_count": due_rows,
        "due_distinct_contract_count": len(due_contracts),
        "due_observation_row_count_by_sport": dict(sorted(due_rows_by_sport.items())),
        "due_distinct_contract_count_by_sport": due_distinct_by_sport,
        "labeled_due_observation_row_count": labeled_due_rows,
        "labeled_due_distinct_contract_count": len(labeled_due_contracts),
        "labeled_due_observation_row_count_by_sport": dict(
            sorted(labeled_due_rows_by_sport.items())
        ),
        "labeled_due_distinct_contract_count_by_sport": labeled_due_distinct_by_sport,
        "not_due_distinct_contract_count": len(not_due_contracts - due_contracts),
        "not_due_distinct_contract_count_by_sport": not_due_distinct_by_sport,
        "next_expected_expiration_utc": iso_time(next_expiration),
        "next_public_label_probe_utc": generated_utc if due_contracts else iso_time(next_expiration),
    }


def due_timestamp_for_observation(
    row: Mapping[str, Any], current_market: Mapping[str, Any] | None = None
) -> float | None:
    if current_market:
        status = str(current_market.get("status") or "").strip().lower()
        if settlement_outcome(current_market) is not None:
            return timestamp(
                _first_present(
                    current_market,
                    ["settled_time", "settlement_ts", "close_time", "expiration_time"],
                )
            )
        if status in {"active", "open"}:
            return timestamp(
                _first_present(current_market, ["close_time", "expiration_time"])
            )
        current_due = timestamp(
            _first_present(
                current_market,
                ["settlement_time", "expected_expiration_time", "close_time", "expiration_time"],
            )
        )
        if current_due is not None:
            return current_due
    return timestamp(_first_present(row, ["expected_expiration_time", "settlement_time", "close_time"]))


def valid_preflight_candidates(preflight: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = preflight.get("candidates", [])
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, Mapping) and row.get("valid") is True]


def index_market_rows(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    for row in _market_list(payload):
        for key in ("ticker", "contract_ticker", "market_id"):
            ticker = str(row.get(key) or "").strip()
            if ticker and ticker not in output:
                output[ticker] = row
    return output


def _market_list(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in ("all_scored", "candidates", "markets", "rows", "top_50"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, Mapping)]
    return []


def market_mid_for_side(row: Mapping[str, Any], side: str | None) -> float | None:
    if side == "yes":
        bid = probability(row.get("yes_bid", row.get("bid")))
        ask = probability(row.get("yes_ask", row.get("ask")))
    elif side == "no":
        bid = probability(row.get("no_bid"))
        ask = probability(row.get("no_ask"))
    else:
        return None
    if bid is None or ask is None:
        return None
    return (bid + ask) / 2.0


def sport_key_for_row(row: Mapping[str, Any], ticker: str) -> str:
    classification = str(row.get("classification") or "").strip().lower()
    if classification == "mlb":
        return "baseball_mlb"
    if classification == "atp":
        return "tennis_atp"
    if classification in {"other_sports", "world_cup"} and (
        ticker.startswith("KXWC") or ticker.startswith("KXFIFA")
    ):
        return "soccer_world_cup"
    return derive_sport_key(ticker)


def derive_sport_key(ticker: str) -> str:
    text = (ticker or "").upper()
    if text.startswith(("KXMLB", "KXMLB", "KXKBO")):
        return "baseball_mlb"
    if text.startswith(("KXATP", "KXWIM")):
        return "tennis_atp"
    if text.startswith(("KXWC", "KXFIFA")):
        return "soccer_world_cup"
    if text.startswith(("KXNFL", "KNFL")):
        return "football_nfl"
    if text.startswith("KXNBA"):
        return "basketball_nba"
    return "other_sports"


def derive_event_ticker(ticker: str) -> str | None:
    if not ticker:
        return None
    parts = ticker.split("-")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return parts[0] if parts else None


def derive_market_key(ticker: str) -> str | None:
    if not ticker:
        return None
    return ticker.split("-", 1)[0] or None


def observation_id(*, ticker: str, side: str, observed_utc: str, source_row_index: int) -> str:
    material = f"{ticker}|{side}|{observed_utc}|{source_row_index}".encode()
    return "sports_consensus_obs_" + hashlib.sha256(material).hexdigest()[:20]


def fetch_json_url(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.load(response)
    return payload if isinstance(payload, dict) else {}


def _summary(value: Mapping[str, Any]) -> Mapping[str, Any]:
    summary = value.get("summary")
    return summary if isinstance(summary, Mapping) else {}


def _input_sha(value: Mapping[str, Any], name: str) -> str | None:
    inputs = value.get("inputs")
    if not isinstance(inputs, Mapping):
        return None
    output = inputs.get(name)
    return str(output) if output else None


def _normalize_side(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text if text in {"yes", "no"} else None


def _first_present(row: Mapping[str, Any], keys: Sequence[str], fallback: Any = None) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in {None, ""}:
            return value
    return fallback


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-path", type=Path, default=DEFAULT_PREFLIGHT_PATH)
    parser.add_argument("--universe-path", type=Path, default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument("--settled-snapshot-path", type=Path, default=DEFAULT_SETTLED_SNAPSHOT_PATH)
    parser.add_argument("--settled-raw-dir", type=Path, default=DEFAULT_SETTLED_RAW_DIR)
    parser.add_argument("--observation-dir", type=Path, default=DEFAULT_OBSERVATION_DIR)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--observed-probe-max-tickers", type=int, default=100)
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
            preflight_path=args.preflight_path,
            universe_path=args.universe_path,
            observation_dir=args.observation_dir,
            generated_utc=generated,
            max_tickers=args.observed_probe_max_tickers,
        )
        settled_snapshot_path = capture_public_observed_markets_snapshot(
            tickers=tickers,
            raw_dir=args.settled_raw_dir,
            base_snapshot_path=args.settled_snapshot_path if args.settled_snapshot_path.is_file() else None,
            generated_utc=generated,
        )
        public_calls = True
    report = build_sports_consensus_observation_loop(
        preflight_path=args.preflight_path,
        universe_path=args.universe_path,
        settled_snapshot_path=settled_snapshot_path,
        observation_dir=args.observation_dir,
        label_dir=args.label_dir,
        generated_utc=generated,
        public_market_data_calls=public_calls,
    )
    if args.write:
        paths = write_sports_consensus_observation_outputs(
            report,
            out_dir=args.out_dir,
            observation_dir=args.observation_dir,
            label_dir=args.label_dir,
        )
        report = {**report, "output_paths": paths}
        output = {"status": report.get("status"), **paths}
    else:
        output = report
    print(json.dumps(output, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
