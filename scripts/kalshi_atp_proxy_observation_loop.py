#!/usr/bin/env python3
"""Archive ATP/Wimbledon Kalshi match observations and settled labels.

The ATP donor snapshot is treated as a research-only feature/market-observation
source. It can say which Kalshi match contracts exist and what the visible
market prices were; it cannot provide labels, calibrated probabilities, EV,
sizing, or orders. Labels come only from Kalshi public settlement matched by
exact ticker.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import (  # noqa: E402
    manual_drop_path,
    optional_float,
    outside_repo,
    project_path,
    safe_research_artifact,
    sha256_or_none,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_ATP_MATCH_SNAPSHOT_DIR = project_path("atp-oracle", "data/kalshi")


def latest_atp_match_snapshot_path(
    snapshot_dir: Path = DEFAULT_ATP_MATCH_SNAPSHOT_DIR,
) -> Path:
    candidates = sorted(
        path
        for path in snapshot_dir.glob("matches-*.json")
        if re.match(r"^matches-\d{4}-\d{2}-\d{2}\.json$", path.name)
    )
    if candidates:
        return candidates[-1]
    return snapshot_dir / "matches-latest.json"


DEFAULT_ATP_MATCH_SNAPSHOT_PATH = latest_atp_match_snapshot_path()
DEFAULT_SETTLED_SNAPSHOT_PATH = manual_drop_path(
    "kalshi_atp_settlements", "kalshi_atp_settled_markets_latest.json"
)
DEFAULT_SETTLED_RAW_DIR = manual_drop_path("kalshi_atp_settlements")
DEFAULT_OBSERVATION_DIR = manual_drop_path("kalshi_atp_proxy_observations")
DEFAULT_LABEL_DIR = manual_drop_path("kalshi_atp_proxy_labels")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-atp-proxy-observation-loop-latest"
KALSHI_PUBLIC_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"

CSV_FIELDS = [
    "observation_id",
    "contract_ticker",
    "event_ticker",
    "player",
    "opponent",
    "tourney_name",
    "surface",
    "decision_time",
    "close_time",
    "expected_expiration_time",
    "yes_ask",
    "market_probability",
    "label_status",
    "yes_outcome",
]

MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_atp_proxy_observation_loop(
    *,
    atp_match_snapshot_path: Path = DEFAULT_ATP_MATCH_SNAPSHOT_PATH,
    settled_snapshot_path: Path = DEFAULT_SETTLED_SNAPSHOT_PATH,
    observation_dir: Path = DEFAULT_OBSERVATION_DIR,
    label_dir: Path = DEFAULT_LABEL_DIR,
    generated_utc: str | None = None,
    public_market_data_calls: bool = False,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    snapshot = read_json_or_empty(atp_match_snapshot_path)
    settled_snapshot = read_json_or_empty(settled_snapshot_path)
    source_safe = atp_snapshot_safe(snapshot, atp_match_snapshot_path)
    candidate_observations = (
        atp_match_observations(
            snapshot, source_path=atp_match_snapshot_path, generated_utc=generated
        )
        if source_safe
        else []
    )
    existing_observations = load_packets(observation_dir)
    existing_observation_ids = observation_ids(existing_observations["rows"])
    new_observations = [
        row
        for row in candidate_observations
        if str(row.get("observation_id") or "") not in existing_observation_ids
    ]
    all_observations = dedupe_by_id([*existing_observations["rows"], *candidate_observations])

    existing_labels = load_packets(label_dir)
    existing_label_ids = observation_ids(existing_labels["rows"])
    due_summary = observation_due_summary(all_observations, generated_utc=generated)
    settled_index = settled_market_index(settled_snapshot)
    computed_labels, blocked_labels = label_observations(all_observations, settled_index)
    new_labels = [
        row
        for row in computed_labels
        if str(row.get("observation_id") or "") not in existing_label_ids
    ]
    all_labels = dedupe_by_id([*existing_labels["rows"], *computed_labels])

    gates = build_gates(
        source_safe=source_safe,
        observation_count=len(all_observations),
        new_observation_count=len(new_observations),
        settled_market_count=len(settled_index),
        label_count=len(all_labels),
        observation_dir=observation_dir,
        label_dir=label_dir,
        rows=[*all_observations, *all_labels],
    )
    status = loop_status(
        source_safe=source_safe,
        total_observation_count=len(all_observations),
        label_count=len(all_labels),
    )
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "family_id": "atp",
        "public_market_data_calls": public_market_data_calls,
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "inputs": {
            "atp_match_snapshot_path": str(atp_match_snapshot_path),
            "atp_match_snapshot_sha256": sha256_or_none(atp_match_snapshot_path),
            "atp_match_snapshot_outside_control_repo": outside_repo(
                atp_match_snapshot_path, CONTROL_REPO
            ),
            "settled_snapshot_path": str(settled_snapshot_path),
            "settled_snapshot_sha256": sha256_or_none(settled_snapshot_path),
            "observation_dir": str(observation_dir),
            "label_dir": str(label_dir),
        },
        "method": {
            "observation_rule": "Record ATP donor match rows as exact Kalshi contract observations.",
            "label_rule": "Attach labels only from public Kalshi settlement matched by exact ticker.",
            "probe_schedule_rule": (
                "When the donor lacks expected expiration, derive only a label-probe time "
                "from the KXATPMATCH event date; never use it as a result label."
            ),
            "ev_boundary": "This loop does not create calibrated probabilities, EV, usable rows, sizing, or orders.",
        },
        "summary": {
            "atp_snapshot_safe": source_safe,
            "source_match_count": len(match_rows(snapshot)),
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
            "new_label_row_count": len(new_labels),
            "label_row_count": len(all_labels),
            "blocked_label_row_count": len(blocked_labels),
            "tourney_counts": counts(row.get("tourney_name") for row in all_observations),
            "label_status_counts": counts(
                row.get("label_status") for row in [*all_labels, *blocked_labels]
            ),
            "due_observation_row_count": due_summary["due_observation_row_count"],
            "due_distinct_contract_count": due_summary["due_distinct_contract_count"],
            "not_due_distinct_contract_count": due_summary["not_due_distinct_contract_count"],
            "next_expected_expiration_utc": due_summary["next_expected_expiration_utc"],
            "next_public_label_probe_utc": due_summary["next_public_label_probe_utc"],
            "expected_expiration_bucket_counts": due_summary["expected_expiration_bucket_counts"],
            "gate_counts": gate_counts(gates),
        },
        "observation_packet": safe_packet(
            generated_utc=generated,
            packet_type="kalshi_atp_proxy_match_observations",
            rows=new_observations,
            inputs={"atp_match_snapshot_path": str(atp_match_snapshot_path)},
        ),
        "label_packet": safe_packet(
            generated_utc=generated,
            packet_type="kalshi_atp_proxy_match_labels",
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
        "next_action": next_action(status),
        "label_probe_schedule": due_summary,
        "safety": safety_flags(public_market_data_calls=public_market_data_calls),
    }


def atp_snapshot_safe(snapshot: Mapping[str, Any], path: Path) -> bool:
    return bool(path.exists() and outside_repo(path, CONTROL_REPO) and match_rows(snapshot))


def match_rows(snapshot: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = snapshot.get("matches", []) if isinstance(snapshot, Mapping) else []
    return [row for row in rows if isinstance(row, Mapping)]


def atp_match_observations(
    snapshot: Mapping[str, Any], *, source_path: Path, generated_utc: str
) -> list[dict[str, Any]]:
    source_sha = sha256_or_none(source_path)
    observations: list[dict[str, Any]] = []
    for match_index, match in enumerate(match_rows(snapshot)):
        event_ticker = str(match.get("_kalshi_event_ticker") or "")
        cluster_key = f"ATP|match_winner|{event_ticker or 'unknown'}"
        expected_expiration, expected_source = expected_expiration_for_match(match)
        for suffix, selection_side, player_key, opponent_key in (
            ("a", "a", "player_a", "player_b"),
            ("b", "b", "player_b", "player_a"),
        ):
            ticker = str(match.get(f"kalshi_market_id_{suffix}") or "").strip()
            if not ticker:
                continue
            yes_ask = probability(match.get(f"_yes_ask_{suffix}"))
            observation = {
                "schema_version": "KalshiAtpProxyMatchObservationV1",
                "observation_id": observation_id(ticker=ticker, decision_time=generated_utc),
                "contract_ticker": ticker,
                "event_ticker": event_ticker,
                "series_ticker": "KXATPMATCH",
                "family_id": "atp",
                "side": "yes",
                "selection_side": selection_side,
                "player": match.get(player_key),
                "opponent": match.get(opponent_key),
                "tourney_name": match.get("tourney_name"),
                "tourney_level": match.get("tourney_level"),
                "surface": match.get("surface"),
                "best_of": match.get("best_of"),
                "cluster_key": cluster_key,
                "decision_time": generated_utc,
                "quote_time": generated_utc,
                "timestamp_source": "atp_oracle_kalshi_match_snapshot",
                "close_time": match.get(f"_close_time_{suffix}"),
                "expected_expiration_time": expected_expiration,
                "expected_expiration_source": expected_source,
                "yes_bid": probability(match.get(f"_yes_bid_{suffix}")),
                "yes_ask": yes_ask,
                "no_bid": probability(match.get(f"_no_bid_{suffix}")),
                "no_ask": probability(match.get(f"_no_ask_{suffix}")),
                "last_price": probability(match.get(f"_last_price_{suffix}")),
                "market_probability": probability(match.get(f"kalshi_price_{suffix}")) or yes_ask,
                "volume": optional_float(match.get(f"_volume_{suffix}")),
                "open_interest": optional_float(match.get(f"_open_interest_{suffix}")),
                "model_id": "atp_oracle_kalshi_watch_snapshot",
                "feature_status": "atp_proxy_observation_ready",
                "feature_policy": "market_observation_only_not_model_probability_or_settlement_label",
                "label_status": "pending_settled_kalshi_outcome",
                "calibrated_probability": None,
                "expected_value_per_contract": None,
                "usable": False,
                "source_artifact": str(source_path),
                "source_artifact_sha256": source_sha,
                "source_row_index": match_index,
                "research_only": True,
                "execution_enabled": False,
            }
            observations.append(observation)
    return observations


def expected_expiration_for_match(match: Mapping[str, Any]) -> tuple[str | None, str | None]:
    for key in ("expected_expiration_time", "match_date"):
        value = iso_time(match.get(key))
        if value:
            return value, key
    event_ticker = str(match.get("_kalshi_event_ticker") or "")
    date_value = event_date_probe_time(event_ticker)
    if date_value:
        return date_value, "event_ticker_date_next_morning_probe_schedule"
    return iso_time(match.get("_close_time_a") or match.get("_close_time_b")), "close_time_fallback"


def event_date_probe_time(event_ticker: str) -> str | None:
    # KXATPMATCH-26JUL03AUGZHE -> 2026-07-04T06:00:00Z label probe.
    match = re.search(r"-(?P<year>\d{2})(?P<month>[A-Z]{3})(?P<day>\d{2})", event_ticker)
    if not match:
        return None
    month = MONTHS.get(match.group("month"))
    if month is None:
        return None
    dt = datetime(2000 + int(match.group("year")), month, int(match.group("day")), tzinfo=UTC)
    return (dt + timedelta(days=1, hours=6)).isoformat(timespec="seconds").replace("+00:00", "Z")


def capture_public_settled_snapshot(
    *,
    raw_dir: Path = DEFAULT_SETTLED_RAW_DIR,
    limit: int = 1000,
    max_pages: int = 1,
    generated_utc: str | None = None,
    fetch_json: Any | None = None,
) -> Path:
    generated = generated_utc or utc_now()
    fetch = fetch_json or fetch_json_url
    raw_dir.mkdir(parents=True, exist_ok=True)
    markets: list[Mapping[str, Any]] = []
    cursor = ""
    for _ in range(max(1, max_pages)):
        query = urllib.parse.urlencode(
            {
                "status": "settled",
                "limit": max(1, min(int(limit), 1000)),
                "mve_filter": "exclude",
                **({"cursor": cursor} if cursor else {}),
            }
        )
        payload = fetch(f"{KALSHI_PUBLIC_BASE_URL}/markets?{query}")
        if not isinstance(payload, Mapping):
            break
        markets.extend(row for row in payload.get("markets", []) if isinstance(row, Mapping))
        cursor = str(payload.get("cursor") or "")
        if not cursor:
            break
    return write_settlement_snapshot(
        raw_dir=raw_dir,
        generated_utc=generated,
        status="kalshi_public_settled_fetch_ok" if markets else "kalshi_public_settled_fetch_empty",
        markets=markets,
        query={"status": "settled", "limit": max(1, min(int(limit), 1000)), "max_pages": max_pages},
    )


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
    probe_errors: list[dict[str, str]] = []
    seen = {str(row.get("ticker") or "") for row in markets}
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
    path = write_settlement_snapshot(
        raw_dir=raw_dir,
        generated_utc=generated,
        status="kalshi_public_observed_market_fetch_ok"
        if markets
        else "kalshi_public_observed_market_fetch_empty",
        markets=markets,
        query={"mode": "exact_observed_ticker_probe", "observed_ticker_count": len(tickers)},
    )
    payload = read_json_or_empty(path)
    payload["summary"]["probe_error_count"] = len(probe_errors)
    payload["summary"]["settled_label_ready_count"] = sum(
        1 for market in markets if settlement_outcome(market) is not None
    )
    payload["probe_errors_sample"] = probe_errors[:50]
    text = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    path.write_text(text, encoding="utf-8")
    (raw_dir / "kalshi_atp_settled_markets_latest.json").write_text(text, encoding="utf-8")
    return path


def write_settlement_snapshot(
    *,
    raw_dir: Path,
    generated_utc: str,
    status: str,
    markets: Sequence[Mapping[str, Any]],
    query: Mapping[str, Any],
) -> Path:
    snapshot = {
        "schema_version": 1,
        "created_at_utc": generated_utc,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "query": dict(query),
        "summary": {"market_count": len(markets)},
        "safety": safety_flags(public_market_data_calls=True),
        "markets": list(markets),
    }
    stamp = safe_stamp(generated_utc)
    snapshot_path = raw_dir / f"kalshi_atp_settled_markets_{stamp}.json"
    latest_path = raw_dir / "kalshi_atp_settled_markets_latest.json"
    text = json.dumps(snapshot, indent=2, sort_keys=True, default=str) + "\n"
    snapshot_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return latest_path


def due_observed_tickers(
    *, atp_match_snapshot_path: Path, observation_dir: Path, generated_utc: str, max_tickers: int
) -> list[str]:
    rows: list[Mapping[str, Any]] = []
    snapshot = read_json_or_empty(atp_match_snapshot_path)
    if atp_snapshot_safe(snapshot, atp_match_snapshot_path):
        rows.extend(
            atp_match_observations(
                snapshot, source_path=atp_match_snapshot_path, generated_utc=generated_utc
            )
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


def observation_due_summary(
    rows: Sequence[Mapping[str, Any]], *, generated_utc: str
) -> dict[str, Any]:
    cutoff = timestamp(generated_utc) or datetime.now(UTC).timestamp()
    due_contracts: set[str] = set()
    not_due_contracts: set[str] = set()
    future_times: list[float] = []
    bucket_counter: Counter[str] = Counter()
    due_rows = 0
    for row in rows:
        ticker = str(row.get("contract_ticker") or "").strip()
        due_at = timestamp(row.get("expected_expiration_time") or row.get("close_time"))
        if not ticker or due_at is None:
            continue
        bucket_counter[bucket_time(due_at)] += 1
        if due_at <= cutoff:
            due_rows += 1
            due_contracts.add(ticker)
        else:
            not_due_contracts.add(ticker)
            future_times.append(due_at)
    next_expiration = min(future_times) if future_times else None
    return {
        "generated_utc": generated_utc,
        "due_observation_row_count": due_rows,
        "due_distinct_contract_count": len(due_contracts),
        "not_due_distinct_contract_count": len(not_due_contracts - due_contracts),
        "next_expected_expiration_utc": iso_from_timestamp(next_expiration),
        "next_public_label_probe_utc": generated_utc
        if due_contracts
        else iso_from_timestamp(next_expiration),
        "expected_expiration_bucket_counts": dict(sorted(bucket_counter.items())),
    }


def label_observations(
    observations: Sequence[Mapping[str, Any]], settled_index: Mapping[str, Mapping[str, Any]]
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
        labels.append(
            {
                **dict(row),
                "label_status": "labeled_from_public_kalshi_settled_market",
                "yes_outcome": yes_outcome,
                "side_outcome": yes_outcome,
                "settled_time": iso_time(
                    market.get("settlement_ts")
                    or market.get("settled_time")
                    or market.get("expiration_time")
                    or market.get("close_time")
                ),
                "label_source": "public_kalshi_settled_market_payload",
                "settlement_result": market.get("result"),
                "settlement_value_dollars": market.get("settlement_value_dollars"),
                "calibrated_probability": None,
                "expected_value_per_contract": None,
                "usable": False,
            }
        )
    return labels, blocked


def blocked_label(row: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "observation_id": row.get("observation_id"),
        "contract_ticker": row.get("contract_ticker"),
        "player": row.get("player"),
        "decision_time": row.get("decision_time"),
        "label_status": reason,
    }


def settled_market_index(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    markets = snapshot.get("markets", [])
    if not isinstance(markets, list):
        return {}
    return {
        str(market.get("ticker")): market
        for market in markets
        if isinstance(market, Mapping)
        and market.get("ticker")
        and settlement_outcome(market) is not None
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


def build_gates(
    *,
    source_safe: bool,
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
            "atp_match_snapshot_safe",
            "pass" if source_safe else "blocked",
            "ATP donor snapshot must exist outside the control repo.",
        ),
        gate(
            "new_observations_recorded",
            "pass" if new_observation_count else "warn",
            f"{new_observation_count} new observation row(s).",
        ),
        gate(
            "observations_available",
            "pass" if observation_count else "blocked",
            f"{observation_count} total ATP observation row(s).",
        ),
        gate(
            "settled_markets_available",
            "pass" if settled_market_count else "warn",
            f"{settled_market_count} public settled market row(s).",
        ),
        gate(
            "label_rows_available",
            "pass" if label_count else "warn",
            f"{label_count} ATP label row(s) emitted.",
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
            "Rows remain observation/outcome data only.",
        ),
    ]


def loop_status(*, source_safe: bool, total_observation_count: int, label_count: int) -> str:
    if not source_safe:
        return "atp_proxy_observation_loop_blocked_missing_match_snapshot"
    if label_count:
        return "atp_proxy_observation_loop_label_rows_ready"
    if total_observation_count:
        return "atp_proxy_observation_loop_ready_waiting_settlement"
    return "atp_proxy_observation_loop_blocked_no_observations"


def next_action(status: str) -> dict[str, str]:
    if status == "atp_proxy_observation_loop_label_rows_ready":
        return {
            "name": "kalshi_atp_proxy_feature_model_falsification",
            "why": "ATP observations now have Kalshi settled labels; next step is an OOS falsification harness.",
            "stop_condition": "Stop before promoting, sizing, or executing without calibrated probability and FDR survival.",
        }
    if status == "atp_proxy_observation_loop_ready_waiting_settlement":
        return {
            "name": "kalshi_atp_proxy_observation_accumulation",
            "why": "ATP match observations are archived; keep exact-ticker public probes until settlement labels arrive.",
            "stop_condition": "Stop before using donor market prices as labels, EV, sizing, or execution evidence.",
        }
    return {
        "name": "kalshi_atp_proxy_observation_blocker_review",
        "why": "The ATP loop lacks a safe donor match snapshot.",
        "stop_condition": "Stop before inventing observations, labels, probabilities, EV, sizing, or execution evidence.",
    }


def write_atp_proxy_observation_outputs(
    report: Mapping[str, Any],
    *,
    out_dir: Path = DEFAULT_OUT_DIR,
    observation_dir: Path = DEFAULT_OBSERVATION_DIR,
    label_dir: Path = DEFAULT_LABEL_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-atp-proxy-observation-loop.json"
    md_path = out_dir / "kalshi-atp-proxy-observation-loop.md"
    csv_path = out_dir / "kalshi-atp-proxy-observation-loop.csv"
    timer_path = out_dir / "kalshi-atp-proxy-observation-loop.timer.example"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, csv_path)
    timer_path.write_text(render_timer_template(), encoding="utf-8")
    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
        "schedule_template_path": str(timer_path),
    }
    stamp = safe_stamp(str(report.get("generated_utc") or utc_now()))
    write_packet_if_rows(
        report.get("observation_packet"),
        directory=observation_dir,
        prefix="atp_proxy_observations",
        stamp=stamp,
        paths=paths,
        path_key="observation_packet_path",
        latest_key="observation_packet_latest_path",
    )
    write_packet_if_rows(
        report.get("label_packet"),
        directory=label_dir,
        prefix="atp_proxy_labels",
        stamp=stamp,
        paths=paths,
        path_key="label_packet_path",
        latest_key="label_packet_latest_path",
    )
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-atp-proxy-observation-loop.json"
    latest_md = MACRO_DIR / "latest-kalshi-atp-proxy-observation-loop.md"
    latest_csv = MACRO_DIR / "latest-kalshi-atp-proxy-observation-loop.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, latest_csv)
    paths["latest_json_path"] = str(latest_json)
    paths["latest_markdown_path"] = str(latest_md)
    paths["latest_csv_path"] = str(latest_csv)
    return paths


def write_packet_if_rows(
    packet: Any,
    *,
    directory: Path,
    prefix: str,
    stamp: str,
    paths: dict[str, str],
    path_key: str,
    latest_key: str,
) -> None:
    rows = packet_rows(packet)
    if not rows:
        return
    directory.mkdir(parents=True, exist_ok=True)
    packet_path = directory / f"{prefix}_{stamp}.json"
    latest_path = directory / f"{prefix}_latest.json"
    text = json.dumps(packet, indent=2, sort_keys=True, default=str) + "\n"
    packet_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    paths[path_key] = str(packet_path)
    paths[latest_key] = str(latest_path)


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    next_step = report.get("next_action") if isinstance(report.get("next_action"), Mapping) else {}
    lines = [
        "# Kalshi ATP Proxy Observation Loop",
        "",
        f"- Status: `{report.get('status')}`",
        f"- New observations: `{summary.get('new_observation_row_count')}`",
        f"- Total observations: `{summary.get('total_observation_row_count')}`",
        f"- Due observations: `{summary.get('due_observation_row_count')}`",
        f"- Label rows: `{summary.get('label_row_count')}`",
        f"- Tournaments: `{summary.get('tourney_counts')}`",
        "",
        "## Label Source",
        "",
        "Labels come from Kalshi public settlement only. ATP donor prices are observations, not labels or probabilities.",
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
        ]
    )
    return "\n".join(lines)


def render_timer_template() -> str:
    return """# Example systemd user timer. Do not enable automatically.
[Unit]
Description=Run research-only Kalshi ATP proxy observation loop every 10 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
RandomizedDelaySec=45s
Persistent=true

[Install]
WantedBy=timers.target

# Matching service:
# [Service]
# Type=oneshot
# WorkingDirectory=/path/to/predmarket-alpha
# ExecStart=/usr/bin/make kalshi-atp-proxy-observation-watch-once
"""


def write_csv(report: Mapping[str, Any], path: Path) -> None:
    rows: list[Mapping[str, Any]] = []
    rows.extend(row for row in report.get("label_rows_sample", []) if isinstance(row, Mapping))
    rows.extend(
        row for row in report.get("observation_rows_sample", []) if isinstance(row, Mapping)
    )
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
        packet_rows_value = payload.get("rows", [])
        if not isinstance(packet_rows_value, list):
            continue
        paths.append(str(path))
        rows.extend(dict(row) for row in packet_rows_value if isinstance(row, Mapping))
    return {"packet_count": len(paths), "paths": paths, "rows": rows}


def dedupe_by_id(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.get("observation_id") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(dict(row))
    output.sort(
        key=lambda item: (
            str(item.get("decision_time") or ""),
            str(item.get("contract_ticker") or ""),
        )
    )
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


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def gate_counts(gates: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counter = Counter(str(item.get("status") or "blocked") for item in gates)
    return {
        "pass": counter["pass"],
        "warn": counter["warn"],
        "blocked": counter["blocked"],
        "fail": counter["fail"],
    }


def counts(values: Sequence[Any]) -> dict[str, int]:
    counter = Counter(str(value or "unknown") for value in values)
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def probability(value: Any) -> float | None:
    number = optional_float(value)
    if number is None or number < 0 or number > 1:
        return None
    return number


def read_json_or_empty(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def observation_id(*, ticker: str, decision_time: str) -> str:
    digest = hashlib.sha256(f"atp|{ticker}|{decision_time}".encode()).hexdigest()
    return f"atp_obs_{digest[:24]}"


def timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def iso_time(value: Any) -> str | None:
    ts = timestamp(value)
    return iso_from_timestamp(ts)


def iso_from_timestamp(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def bucket_time(value: float | None) -> str:
    if value is None:
        return "unknown"
    return datetime.fromtimestamp(value, UTC).date().isoformat()


def safe_stamp(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum())


def safety_flags(*, public_market_data_calls: bool) -> dict[str, Any]:
    return {
        "research_only": True,
        "public_market_data_calls": public_market_data_calls,
        "authenticated_api_calls": False,
        "account_or_order_paths": False,
        "market_execution": False,
        "database_writes": False,
        "paid_calls": False,
        "raw_secrets_copied": False,
        "raw_payloads_copied_to_repo": False,
        "staking_or_sizing_guidance": False,
    }


def fetch_json_url(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.load(response)
    return payload if isinstance(payload, dict) else {}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--atp-match-snapshot-path", type=Path, default=DEFAULT_ATP_MATCH_SNAPSHOT_PATH
    )
    parser.add_argument("--settled-snapshot-path", type=Path, default=DEFAULT_SETTLED_SNAPSHOT_PATH)
    parser.add_argument("--observation-dir", type=Path, default=DEFAULT_OBSERVATION_DIR)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument("--settled-raw-dir", type=Path, default=DEFAULT_SETTLED_RAW_DIR)
    parser.add_argument("--settled-limit", type=int, default=1000)
    parser.add_argument("--settled-max-pages", type=int, default=1)
    parser.add_argument("--observed-probe-max-tickers", type=int, default=300)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--capture-settled-public", action="store_true")
    parser.add_argument("--probe-observed-public", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    generated = utc_now()
    settled_snapshot_path = args.settled_snapshot_path
    public_calls = False
    if args.capture_settled_public:
        settled_snapshot_path = capture_public_settled_snapshot(
            raw_dir=args.settled_raw_dir,
            limit=args.settled_limit,
            max_pages=args.settled_max_pages,
            generated_utc=generated,
        )
        public_calls = True
    if args.probe_observed_public:
        tickers = due_observed_tickers(
            atp_match_snapshot_path=args.atp_match_snapshot_path,
            observation_dir=args.observation_dir,
            generated_utc=generated,
            max_tickers=args.observed_probe_max_tickers,
        )
        if tickers:
            settled_snapshot_path = capture_public_observed_markets_snapshot(
                tickers=tickers,
                raw_dir=args.settled_raw_dir,
                base_snapshot_path=settled_snapshot_path,
                generated_utc=generated,
            )
            public_calls = True
    report = build_atp_proxy_observation_loop(
        atp_match_snapshot_path=args.atp_match_snapshot_path,
        settled_snapshot_path=settled_snapshot_path,
        observation_dir=args.observation_dir,
        label_dir=args.label_dir,
        generated_utc=generated,
        public_market_data_calls=public_calls,
    )
    if args.write:
        paths = write_atp_proxy_observation_outputs(
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
