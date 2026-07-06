#!/usr/bin/env python3
"""Forecast sports evidence velocity and exact label deficits.

This is a control-plane report. It does not compute probabilities, EV, paper
stakes, or orders. Its job is to turn "insufficient labels" into an explicit
per-surface evidence backlog with a conservative ETA/probe state.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import (  # noqa: E402
    iso_time,
    path_is_within,
    read_json_or_empty,
    safe_research_artifact,
    safety_flags,
    sha256_or_none,
    timestamp,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_UNIVERSE_PATH = MACRO_DIR / "latest-kalshi-universe-scan.json"
DEFAULT_SPORTS_MODEL_PATH = (
    MACRO_DIR / "latest-kalshi-sports-proxy-feature-model-falsification.json"
)
DEFAULT_ATP_EVIDENCE_PATH = MACRO_DIR / "latest-kalshi-atp-proxy-evidence-gate.json"
DEFAULT_WORLD_CUP_MODEL_PATH = (
    MACRO_DIR / "latest-kalshi-world-cup-proxy-feature-model-falsification.json"
)
DEFAULT_WORLD_CUP_OUTCOME_INDEPENDENCE_PATH = (
    MACRO_DIR / "latest-kalshi-world-cup-outcome-independence-diagnostic.json"
)
DEFAULT_CONSENSUS_PREFLIGHT_PATH = MACRO_DIR / "latest-kalshi-sports-consensus-preflight.json"
DEFAULT_CONSENSUS_OBSERVATION_PATH = (
    MACRO_DIR / "latest-kalshi-sports-consensus-observation-loop.json"
)
DEFAULT_CONSENSUS_FALSIFICATION_PATH = (
    MACRO_DIR / "latest-kalshi-sports-consensus-falsification.json"
)
DEFAULT_CONSENSUS_NBA_ADAPTER_PATH = MACRO_DIR / "latest-kalshi-sports-consensus-nba-adapter.json"
DEFAULT_FLOW_PATH = MACRO_DIR / "latest-kalshi-near-resolution-informed-flow-evidence-gate.json"
DEFAULT_PASSIVE_FILL_FALSIFICATION_PATH = (
    MACRO_DIR / "latest-kalshi-passive-liquidity-paper-fill-falsification.json"
)
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-event-velocity-eta-latest"

TARGET_CONSENSUS_SPORTS = {
    "baseball_mlb": "mlb",
    "tennis_atp": "atp",
    "soccer_world_cup": "world_cup_soccer",
    "football_nfl": "nfl",
    "basketball_nba": "nba",
}

ROLLUP_SURFACES = frozenset({"sports_consensus_all"})
SOURCE_BLOCKER_BOTTLENECKS = frozenset(
    {
        "missing_strict_consensus_feed",
        "stale_or_unmatched_strict_consensus_reference",
        "stale_strict_consensus_reference",
        "missing_exact_kalshi_mapping",
        "insufficient_strict_consensus_books",
    }
)

WAITING_EVIDENCE_BOTTLENECKS = frozenset(
    {
        "calendar_or_offseason_no_current_markets",
        "external_forward_oos",
    }
)

CSV_FIELDS = [
    "surface_id",
    "source_status",
    "bottleneck_type",
    "eta_status",
    "candidate_count",
    "rejected_candidate_count",
    "active_candidate_count",
    "due_count",
    "current_label_count",
    "independent_label_count",
    "oos_label_count",
    "min_independent_labels",
    "min_oos_labels",
    "label_deficit",
    "oos_deficit",
    "paper_fill_count",
    "min_oos_fills",
    "paper_fill_deficit",
    "timestamp_skew_blocker_count",
    "kalshi_ticker_not_found_blocker_count",
    "insufficient_distinct_books_blocker_count",
    "next_probe_utc",
    "eta_days",
    "model_id",
    "hypothesis_accumulation_opportunity_count",
    "hypothesis_accumulation_opportunity_distinct_contract_count",
    "nearest_hypothesis_current_opportunity_count",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_sports_event_velocity_eta(
    *,
    universe_path: Path = DEFAULT_UNIVERSE_PATH,
    sports_model_path: Path = DEFAULT_SPORTS_MODEL_PATH,
    atp_evidence_path: Path = DEFAULT_ATP_EVIDENCE_PATH,
    world_cup_model_path: Path = DEFAULT_WORLD_CUP_MODEL_PATH,
    world_cup_outcome_independence_path: Path = DEFAULT_WORLD_CUP_OUTCOME_INDEPENDENCE_PATH,
    consensus_preflight_path: Path = DEFAULT_CONSENSUS_PREFLIGHT_PATH,
    consensus_observation_path: Path = DEFAULT_CONSENSUS_OBSERVATION_PATH,
    consensus_falsification_path: Path = DEFAULT_CONSENSUS_FALSIFICATION_PATH,
    consensus_nba_adapter_path: Path = DEFAULT_CONSENSUS_NBA_ADAPTER_PATH,
    flow_path: Path = DEFAULT_FLOW_PATH,
    passive_fill_falsification_path: Path = DEFAULT_PASSIVE_FILL_FALSIFICATION_PATH,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    now_ts = timestamp(generated) or datetime.now(UTC).timestamp()
    artifacts = {
        "universe": artifact(universe_path),
        "sports_model": artifact(sports_model_path),
        "atp_evidence": artifact(atp_evidence_path),
        "world_cup_model": artifact(world_cup_model_path),
        "world_cup_outcome_independence": artifact(world_cup_outcome_independence_path),
        "consensus_preflight": artifact(consensus_preflight_path),
        "consensus_observation": artifact(consensus_observation_path),
        "consensus_falsification": artifact(consensus_falsification_path),
        "consensus_nba_adapter": artifact(consensus_nba_adapter_path),
        "flow": artifact(flow_path),
        "passive_fill_falsification": artifact(passive_fill_falsification_path),
    }
    active_candidates = active_candidate_counts(artifacts["universe"]["payload"], now_ts=now_ts)
    consensus_counts = consensus_sport_counts(
        preflight=artifacts["consensus_preflight"]["payload"],
        falsification=artifacts["consensus_falsification"]["payload"],
    )
    rows = [
        consensus_overall_row(
            artifacts=artifacts,
            consensus_counts=consensus_counts,
            now_ts=now_ts,
        ),
        consensus_rule_bucket_accumulation_row(
            artifacts=artifacts,
            now_ts=now_ts,
        ),
        *consensus_sport_rows(
            artifacts=artifacts,
            active_candidates=active_candidates,
            consensus_counts=consensus_counts,
            nba_adapter=artifacts["consensus_nba_adapter"],
            now_ts=now_ts,
        ),
        model_label_row(
            surface_id="mlb_proxy_directional",
            source=artifacts["sports_model"],
            active_candidate_count=active_candidates.get("mlb", 0),
            now_ts=now_ts,
        ),
        atp_row(artifacts["atp_evidence"], active_candidates=active_candidates, now_ts=now_ts),
        world_cup_row(
            model_source=artifacts["world_cup_model"],
            independence_source=artifacts["world_cup_outcome_independence"],
            active_candidate_count=active_candidates.get("world_cup_soccer", 0),
            now_ts=now_ts,
        ),
        flow_row(artifacts["flow"], now_ts=now_ts),
        passive_fill_row(artifacts["passive_fill_falsification"], now_ts=now_ts),
    ]
    rows = [normalize_row(row) for row in rows]
    gates = build_gates(artifacts, rows)
    status = report_status(gates, rows)
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
        "north_star": "Extract and exploit mispricings in Kalshi sports contracts before the crowd corrects them.",
        "method": {
            "purpose": "Make label deficits, OOS deficits, paper-fill deficits, and next probe state explicit per sports evidence surface.",
            "boundary": "ETA rows are control-plane evidence only; they do not lower thresholds or promote candidates.",
            "eta_policy": "Use exact next-probe timestamps when present; otherwise classify the blocker without inventing a settlement date.",
        },
        "inputs": {
            key: {
                "path": item["path"],
                "sha256": item["sha256"],
                "exists": item["exists"],
                "safe": item["safe"],
                "status": item["status"],
            }
            for key, item in artifacts.items()
        },
        "summary": build_summary(artifacts, rows),
        "eta_rows": rows,
        "gates": gates,
        "next_action": next_action(status, rows),
        "safety": safety_flags(),
    }


def artifact(path: Path) -> dict[str, Any]:
    payload = read_json_or_empty(path)
    return {
        "path": str(path),
        "sha256": sha256_or_none(path),
        "exists": path.is_file(),
        "safe": safe_research_artifact(payload),
        "status": payload.get("status"),
        "payload": payload,
        "summary": payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {},
    }


def active_candidate_counts(universe: Mapping[str, Any], *, now_ts: float) -> dict[str, int]:
    raw = universe.get("candidates") if isinstance(universe.get("candidates"), list) else []
    counter: Counter[str] = Counter()
    for row in raw:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("gate_status") or "") not in {"pass", "warn"}:
            continue
        settle_ts = timestamp(
            row.get("settlement_time")
            or row.get("expected_expiration_time")
            or row.get("expiration_time")
            or row.get("close_time")
        )
        if settle_ts is not None and settle_ts <= now_ts:
            continue
        surface = universe_surface(row)
        if surface:
            counter[surface] += 1
    return dict(counter)


def universe_surface(row: Mapping[str, Any]) -> str | None:
    classification = str(row.get("classification") or "")
    series = str(row.get("series_ticker") or "").upper()
    if classification == "mlb" or series.startswith("KXMLB"):
        return "mlb"
    if classification == "atp" or series.startswith("KXATP"):
        return "atp"
    if "WC" in series or series.startswith("KXWCGAME"):
        return "world_cup_soccer"
    if classification == "nfl" or series.startswith("KXNFL"):
        return "nfl"
    if classification == "nba" or series.startswith("KXNBA"):
        return "nba"
    return None


def consensus_sport_counts(
    *,
    preflight: Mapping[str, Any],
    falsification: Mapping[str, Any],
) -> dict[str, dict[str, int]]:
    counts_by_sport: dict[str, dict[str, int]] = {
        sport: {
            "candidate_count": 0,
            "active_candidate_count": 0,
            "rejected_candidate_count": 0,
            "timestamp_skew_blocker_count": 0,
            "kalshi_ticker_not_found_blocker_count": 0,
            "insufficient_distinct_books_blocker_count": 0,
            "current_label_count": 0,
            "independent_label_count": 0,
            "oos_label_count": 0,
        }
        for sport in TARGET_CONSENSUS_SPORTS
    }
    add_consensus_candidate_counts(counts_by_sport, preflight)
    add_consensus_label_counts(counts_by_sport, falsification)
    return counts_by_sport


def add_consensus_candidate_counts(
    counts_by_sport: dict[str, dict[str, int]],
    preflight: Mapping[str, Any],
) -> None:
    candidates = (
        preflight.get("candidates") if isinstance(preflight.get("candidates"), list) else []
    )
    for row in candidates:
        if isinstance(row, Mapping):
            sport = sport_from_ticker(row.get("kalshi_ticker"))
            if sport not in counts_by_sport:
                continue
            counts_by_sport[sport]["candidate_count"] += 1
            if row.get("valid") is True:
                counts_by_sport[sport]["active_candidate_count"] += 1
                continue
            counts_by_sport[sport]["rejected_candidate_count"] += 1
            reasons = (
                row.get("blocker_reasons") if isinstance(row.get("blocker_reasons"), list) else []
            )
            reason_set = {str(reason) for reason in reasons}
            if "timestamp_skew_exceeds_policy" in reason_set:
                counts_by_sport[sport]["timestamp_skew_blocker_count"] += 1
            if "kalshi_ticker_not_found" in reason_set:
                counts_by_sport[sport]["kalshi_ticker_not_found_blocker_count"] += 1
            if "insufficient_distinct_books" in reason_set:
                counts_by_sport[sport]["insufficient_distinct_books_blocker_count"] += 1


def add_consensus_label_counts(
    counts_by_sport: dict[str, dict[str, int]],
    falsification: Mapping[str, Any],
) -> None:
    labels: dict[str, dict[str, Any]] = {}
    rows = falsification.get("rows") if isinstance(falsification.get("rows"), list) else []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        ticker = str(row.get("contract_ticker") or "")
        if not ticker or row.get("settlement_outcome") is None:
            continue
        if ticker in labels:
            continue
        sport = str(row.get("sport_key") or sport_from_ticker(ticker))
        labels[ticker] = {
            "sport": sport,
            "observed_ts": timestamp(row.get("observed_utc") or row.get("decision_time")) or 0.0,
        }
    for label in labels.values():
        sport = str(label.get("sport") or "")
        if sport in counts_by_sport:
            counts_by_sport[sport]["current_label_count"] += 1
            counts_by_sport[sport]["independent_label_count"] += 1
    by_sport: dict[str, list[dict[str, Any]]] = {}
    for label in labels.values():
        by_sport.setdefault(str(label.get("sport") or ""), []).append(label)
    for sport, sport_labels in by_sport.items():
        if sport not in counts_by_sport:
            continue
        ordered = sorted(sport_labels, key=lambda item: float(item.get("observed_ts") or 0.0))
        test_count = max(1, round(len(ordered) * 0.30)) if ordered else 0
        counts_by_sport[sport]["oos_label_count"] = test_count


def sport_from_ticker(value: Any) -> str:
    ticker = str(value or "").upper()
    if ticker.startswith("KXMLB"):
        return "baseball_mlb"
    if ticker.startswith("KXATP"):
        return "tennis_atp"
    if ticker.startswith("KXNFL"):
        return "football_nfl"
    if ticker.startswith("KXNBA"):
        return "basketball_nba"
    if ticker.startswith("KXWC"):
        return "soccer_world_cup"
    return "unknown"


def consensus_overall_row(
    *,
    artifacts: Mapping[str, Mapping[str, Any]],
    consensus_counts: Mapping[str, Mapping[str, int]],
    now_ts: float,
) -> dict[str, Any]:
    summary = artifacts["consensus_falsification"]["summary"]
    obs_summary = artifacts["consensus_observation"]["summary"]
    due_count, next_probe_utc = consensus_probe_state(obs_summary, now_ts=now_ts)
    active = sum(
        int_value(counts.get("active_candidate_count")) for counts in consensus_counts.values()
    )
    row = deficit_row(
        surface_id="sports_consensus_all",
        source_status=str(artifacts["consensus_falsification"]["status"] or ""),
        bottleneck_type="calendar_settlement_labels",
        active_candidate_count=active,
        due_count=due_count if active > 0 else 0,
        current_label_count=int_value(summary.get("joined_label_count")),
        independent_label_count=int_value(summary.get("independent_label_count")),
        oos_label_count=int_value(summary.get("oos_label_count")),
        min_independent_labels=int_value(summary.get("min_independent_labels")),
        min_oos_labels=int_value(summary.get("min_oos_labels")),
        next_probe_utc=next_probe_utc,
        now_ts=now_ts,
    )
    row.update(
        {
            "candidate_count": sum(
                int_value(counts.get("candidate_count")) for counts in consensus_counts.values()
            ),
            "rejected_candidate_count": sum(
                int_value(counts.get("rejected_candidate_count"))
                for counts in consensus_counts.values()
            ),
            "timestamp_skew_blocker_count": sum(
                int_value(counts.get("timestamp_skew_blocker_count"))
                for counts in consensus_counts.values()
            ),
            "kalshi_ticker_not_found_blocker_count": sum(
                int_value(counts.get("kalshi_ticker_not_found_blocker_count"))
                for counts in consensus_counts.values()
            ),
            "insufficient_distinct_books_blocker_count": sum(
                int_value(counts.get("insufficient_distinct_books_blocker_count"))
                for counts in consensus_counts.values()
            ),
        }
    )
    return row


def consensus_rule_bucket_accumulation_row(
    *,
    artifacts: Mapping[str, Mapping[str, Any]],
    now_ts: float,
) -> dict[str, Any]:
    summary = artifacts["consensus_falsification"]["summary"]
    obs_summary = artifacts["consensus_observation"]["summary"]
    due_count, next_probe_utc = consensus_probe_state(obs_summary, now_ts=now_ts)
    source_status = str(artifacts["consensus_falsification"]["status"] or "")
    nearest_model = str(summary.get("nearest_hypothesis_model_id") or "")
    nearest_oos = int_value(summary.get("max_hypothesis_oos_count"))
    min_oos = int_value(summary.get("min_oos_labels"))
    nearest_deficit = int_value(summary.get("nearest_hypothesis_oos_deficit"))
    nearest_opportunities = int_value(
        summary.get("nearest_hypothesis_current_opportunity_count")
    )
    total_opportunities = int_value(summary.get("hypothesis_accumulation_opportunity_count"))
    distinct_opportunities = int_value(
        summary.get("hypothesis_accumulation_opportunity_distinct_contract_count")
    )
    if source_status != "sports_consensus_falsification_blocked_no_testable_hypotheses":
        nearest_oos = min_oos
        nearest_deficit = 0
        nearest_opportunities = 0
        total_opportunities = 0
        distinct_opportunities = 0
        next_probe_utc = None
    row = deficit_row(
        surface_id="sports_consensus_rule_bucket_accumulation",
        source_status=source_status,
        bottleneck_type="calendar_settlement_labels",
        active_candidate_count=nearest_opportunities,
        due_count=due_count if nearest_opportunities > 0 else 0,
        current_label_count=nearest_oos,
        independent_label_count=int_value(summary.get("independent_label_count")),
        oos_label_count=nearest_oos,
        min_independent_labels=int_value(summary.get("min_independent_labels")),
        min_oos_labels=min_oos,
        next_probe_utc=next_probe_utc if nearest_opportunities > 0 else None,
        now_ts=now_ts,
    )
    row.update(
        {
            "model_id": nearest_model or None,
            "label_deficit": 0,
            "oos_deficit": nearest_deficit,
            "hypothesis_accumulation_opportunity_count": total_opportunities,
            "hypothesis_accumulation_opportunity_distinct_contract_count": (
                distinct_opportunities
            ),
            "nearest_hypothesis_current_opportunity_count": nearest_opportunities,
        }
    )
    row["eta_status"] = eta_status_for(
        label_deficit=0,
        oos_deficit=nearest_deficit,
        active_candidate_count=nearest_opportunities,
        due_count=int(row.get("due_count") or 0),
        next_probe_utc=row.get("next_probe_utc"),
        bottleneck_type=row["bottleneck_type"],
    )
    row["eta_days"] = eta_days(row.get("next_probe_utc"), now_ts=now_ts)
    return row


def consensus_sport_rows(
    *,
    artifacts: Mapping[str, Mapping[str, Any]],
    active_candidates: Mapping[str, int],
    consensus_counts: Mapping[str, Mapping[str, int]],
    nba_adapter: Mapping[str, Any],
    now_ts: float,
) -> list[dict[str, Any]]:
    summary = artifacts["consensus_falsification"]["summary"]
    obs_summary = artifacts["consensus_observation"]["summary"]
    min_independent = int_value(summary.get("min_independent_labels"))
    min_oos = int_value(summary.get("min_oos_labels"))
    rows: list[dict[str, Any]] = []
    for sport_key, surface in TARGET_CONSENSUS_SPORTS.items():
        due_count, next_probe_utc = consensus_probe_state(
            obs_summary, sport_key=sport_key, now_ts=now_ts
        )
        counts = consensus_counts.get(sport_key, {})
        candidate_count = int_value(counts.get("candidate_count"))
        active = (
            int_value(counts.get("active_candidate_count"))
            if candidate_count > 0
            else active_candidates.get(surface, 0)
        )
        bottleneck_type = "calendar_settlement_labels"
        stale_count = int_value(counts.get("timestamp_skew_blocker_count"))
        missing_ticker_count = int_value(counts.get("kalshi_ticker_not_found_blocker_count"))
        insufficient_books_count = int_value(
            counts.get("insufficient_distinct_books_blocker_count")
        )
        if candidate_count > 0 and active == 0:
            if stale_count and missing_ticker_count:
                bottleneck_type = "stale_or_unmatched_strict_consensus_reference"
            elif stale_count:
                bottleneck_type = "stale_strict_consensus_reference"
            elif missing_ticker_count:
                bottleneck_type = "missing_exact_kalshi_mapping"
            elif insufficient_books_count:
                bottleneck_type = "insufficient_strict_consensus_books"
        if surface == "nba" and active == 0:
            bottleneck_type = (
                "calendar_or_offseason_no_current_markets"
                if nba_adapter.get("exists") and nba_adapter.get("safe")
                else "missing_strict_consensus_feed"
            )
        row = deficit_row(
            surface_id=f"sports_consensus_{surface}",
            source_status=str(artifacts["consensus_falsification"]["status"] or ""),
            bottleneck_type=bottleneck_type,
            active_candidate_count=active,
            due_count=due_count if active > 0 else 0,
            current_label_count=int_value(counts.get("current_label_count")),
            independent_label_count=int_value(counts.get("independent_label_count")),
            oos_label_count=int_value(counts.get("oos_label_count")),
            min_independent_labels=min_independent,
            min_oos_labels=min_oos,
            next_probe_utc=next_probe_utc if active > 0 else None,
            now_ts=now_ts,
        )
        row.update(
            {
                "candidate_count": candidate_count,
                "rejected_candidate_count": int_value(counts.get("rejected_candidate_count")),
                "timestamp_skew_blocker_count": stale_count,
                "kalshi_ticker_not_found_blocker_count": missing_ticker_count,
                "insufficient_distinct_books_blocker_count": insufficient_books_count,
            }
        )
        rows.append(row)
    return rows


def consensus_probe_state(
    obs_summary: Mapping[str, Any], *, sport_key: str | None = None, now_ts: float
) -> tuple[int, str | None]:
    due_count = consensus_due_count(obs_summary, sport_key=sport_key)
    public_probe = iso_time(obs_summary.get("next_public_label_probe_utc"))
    expected_expiration = iso_time(obs_summary.get("next_expected_expiration_utc"))
    public_ts = timestamp(public_probe)
    expected_ts = timestamp(expected_expiration)

    if due_count > 0:
        if public_probe and public_ts is not None and public_ts <= now_ts:
            return due_count, public_probe
        if public_probe and public_ts is not None and public_ts > now_ts:
            return 0, public_probe
        return due_count, None

    next_probe = public_probe
    if expected_expiration and expected_ts is not None and expected_ts > now_ts:
        next_probe = expected_expiration
    elif public_probe and public_ts is not None and public_ts > now_ts:
        next_probe = public_probe

    probe_ts = timestamp(next_probe)
    effective_due_count = 0 if probe_ts is not None and probe_ts > now_ts else due_count
    return effective_due_count, next_probe


def consensus_due_count(obs_summary: Mapping[str, Any], *, sport_key: str | None) -> int:
    if sport_key:
        counts = obs_summary.get("due_distinct_contract_count_by_sport")
        if isinstance(counts, Mapping):
            return int_value(counts.get(sport_key))
        return 0
    return int_value(obs_summary.get("due_distinct_contract_count"))


def model_label_row(
    *,
    surface_id: str,
    source: Mapping[str, Any],
    active_candidate_count: int,
    now_ts: float,
) -> dict[str, Any]:
    summary = source.get("summary") if isinstance(source.get("summary"), Mapping) else {}
    independent = int_value(
        summary.get("independent_contract_label_count")
        or summary.get("independent_label_count")
        or summary.get("valid_label_row_count")
    )
    return deficit_row(
        surface_id=surface_id,
        source_status=str(source.get("status") or ""),
        bottleneck_type="calendar_settlement_labels",
        active_candidate_count=active_candidate_count,
        due_count=0,
        current_label_count=int_value(summary.get("valid_label_row_count")) or independent,
        independent_label_count=independent,
        oos_label_count=int_value(summary.get("oos_label_count"))
        or inferred_oos_count(independent),
        min_independent_labels=int_value(summary.get("min_independent_labels")),
        min_oos_labels=int_value(summary.get("min_oos_labels")),
        next_probe_utc=None,
        now_ts=now_ts,
    )


def atp_row(
    source: Mapping[str, Any],
    *,
    active_candidates: Mapping[str, int],
    now_ts: float,
) -> dict[str, Any]:
    summary = source.get("summary") if isinstance(source.get("summary"), Mapping) else {}
    settled = int_value(summary.get("settled_label_count"))
    min_settled = int_value(summary.get("min_settled_labels"))
    bottleneck_type = "calendar_settlement_labels"
    next_probe_utc = iso_time(summary.get("next_public_label_probe_utc"))
    if settled >= min_settled:
        bottleneck_type = "external_forward_oos"
        next_probe_utc = (
            iso_time(summary.get("next_expected_expiration_utc"))
            or iso_time(summary.get("next_public_label_probe_utc"))
        )
    return deficit_row(
        surface_id="atp_proxy_settlement_window",
        source_status=str(source.get("status") or ""),
        bottleneck_type=bottleneck_type,
        active_candidate_count=active_candidates.get("atp", 0),
        due_count=0,
        current_label_count=settled,
        independent_label_count=settled,
        oos_label_count=int_value(summary.get("forward_oos_resolved")),
        min_independent_labels=min_settled,
        min_oos_labels=int_value(summary.get("forward_oos_min_probe")),
        next_probe_utc=next_probe_utc,
        now_ts=now_ts,
    )


def world_cup_row(
    *,
    model_source: Mapping[str, Any],
    independence_source: Mapping[str, Any],
    active_candidate_count: int,
    now_ts: float,
) -> dict[str, Any]:
    row = model_label_row(
        surface_id="world_cup_proxy_directional",
        source=model_source,
        active_candidate_count=active_candidate_count,
        now_ts=now_ts,
    )
    diagnostic = (
        independence_source.get("summary")
        if isinstance(independence_source.get("summary"), Mapping)
        else {}
    )
    if diagnostic.get("current_candidate_independence_requires_review") is True:
        independent = int_value(diagnostic.get("outcome_family_label_count"))
        minimum = int_value(diagnostic.get("min_independent_labels"))
        row.update(
            {
                "source_status": str(independence_source.get("status") or row["source_status"]),
                "bottleneck_type": "independence_definition_review",
                "eta_status": "blocked_world_cup_independence_review",
                "current_label_count": int_value(diagnostic.get("exact_contract_label_count")),
                "independent_label_count": independent,
                "min_independent_labels": minimum,
                "label_deficit": max(minimum - independent, 0),
                "oos_label_count": 0,
                "oos_deficit": int_value(diagnostic.get("min_oos_labels")),
                "match_cluster_count": int_value(diagnostic.get("match_cluster_count")),
                "portfolio_cluster_unit": diagnostic.get("recommended_portfolio_cluster_unit"),
                "next_probe_utc": None,
                "eta_days": None,
            }
        )
    return row


def flow_row(source: Mapping[str, Any], *, now_ts: float) -> dict[str, Any]:
    summary = source.get("summary") if isinstance(source.get("summary"), Mapping) else {}
    settled = int_value(summary.get("settled_contract_label_count"))
    row = deficit_row(
        surface_id="near_resolution_informed_flow",
        source_status=str(source.get("status") or ""),
        bottleneck_type="compute_or_downstream_gates",
        active_candidate_count=int_value(summary.get("distinct_contract_count")),
        due_count=0,
        current_label_count=settled,
        independent_label_count=settled,
        oos_label_count=int_value(summary.get("min_oos_labels")),
        min_independent_labels=int_value(summary.get("min_settled_contracts")),
        min_oos_labels=int_value(summary.get("min_oos_labels")),
        next_probe_utc=None,
        now_ts=now_ts,
    )
    if int_value(summary.get("research_candidate_count")) > 0:
        row["eta_status"] = "label_threshold_met_downstream_gates_active"
        row["bottleneck_type"] = "compute_or_downstream_gates"
    return row


def passive_fill_row(source: Mapping[str, Any], *, now_ts: float) -> dict[str, Any]:
    summary = source.get("summary") if isinstance(source.get("summary"), Mapping) else {}
    fdr_survivors = int_value(summary.get("fdr_survivor_count"))
    research_candidates = int_value(summary.get("research_candidate_count"))
    row = deficit_row(
        surface_id="passive_liquidity_paper_fill",
        source_status=str(source.get("status") or ""),
        bottleneck_type="paper_fill_clock",
        active_candidate_count=int_value(summary.get("paper_intent_count")),
        due_count=0,
        current_label_count=int_value(summary.get("valid_paper_fill_label_count")),
        independent_label_count=int_value(summary.get("valid_paper_fill_label_count")),
        oos_label_count=int_value(summary.get("paper_filled_count")),
        min_independent_labels=int_value(summary.get("min_independent_labels")),
        min_oos_labels=int_value(summary.get("min_oos_labels")),
        next_probe_utc=None,
        now_ts=now_ts,
    )
    row["paper_fill_count"] = int_value(summary.get("paper_filled_count"))
    row["min_oos_fills"] = int_value(summary.get("min_oos_fills"))
    row["fdr_survivor_count"] = fdr_survivors
    row["research_candidate_count"] = research_candidates
    row["paper_fill_deficit"] = max(
        int(row["min_oos_fills"] or 0) - int(row["paper_fill_count"] or 0), 0
    )
    if row["paper_fill_deficit"] > 0:
        row["eta_status"] = "blocked_waiting_for_paper_maker_fills"
    elif int(row["label_deficit"] or 0) <= 0 and int(row["oos_deficit"] or 0) <= 0:
        row["bottleneck_type"] = "compute_or_downstream_gates"
        row["eta_status"] = (
            "label_threshold_met_downstream_gates_active"
            if fdr_survivors > 0 or research_candidates > 0
            else "label_threshold_met_no_fdr_survivor"
        )
    return row


def deficit_row(
    *,
    surface_id: str,
    source_status: str,
    bottleneck_type: str,
    active_candidate_count: int,
    due_count: int,
    current_label_count: int,
    independent_label_count: int,
    oos_label_count: int,
    min_independent_labels: int,
    min_oos_labels: int,
    next_probe_utc: str | None,
    now_ts: float,
) -> dict[str, Any]:
    label_deficit = max(min_independent_labels - independent_label_count, 0)
    oos_deficit = max(min_oos_labels - oos_label_count, 0)
    eta_status = eta_status_for(
        label_deficit=label_deficit,
        oos_deficit=oos_deficit,
        active_candidate_count=active_candidate_count,
        due_count=due_count,
        next_probe_utc=next_probe_utc,
        bottleneck_type=bottleneck_type,
    )
    return {
        "surface_id": surface_id,
        "source_status": source_status,
        "bottleneck_type": bottleneck_type,
        "eta_status": eta_status,
        "active_candidate_count": active_candidate_count,
        "due_count": due_count,
        "current_label_count": current_label_count,
        "independent_label_count": independent_label_count,
        "oos_label_count": oos_label_count,
        "min_independent_labels": min_independent_labels,
        "min_oos_labels": min_oos_labels,
        "label_deficit": label_deficit,
        "oos_deficit": oos_deficit,
        "paper_fill_count": 0,
        "min_oos_fills": 0,
        "paper_fill_deficit": 0,
        "next_probe_utc": next_probe_utc,
        "eta_days": eta_days(next_probe_utc, now_ts=now_ts),
    }


def eta_status_for(
    *,
    label_deficit: int,
    oos_deficit: int,
    active_candidate_count: int,
    due_count: int,
    next_probe_utc: str | None,
    bottleneck_type: str,
) -> str:
    fixed_statuses = {
        "missing_strict_consensus_feed": "blocked_missing_strict_consensus_feed",
        "calendar_or_offseason_no_current_markets": "blocked_no_current_nba_consensus_rows",
        "stale_or_unmatched_strict_consensus_reference": (
            "blocked_stale_or_unmatched_strict_consensus_reference"
        ),
        "stale_strict_consensus_reference": "blocked_stale_strict_consensus_reference",
        "missing_exact_kalshi_mapping": "blocked_missing_exact_kalshi_mapping",
        "insufficient_strict_consensus_books": ("blocked_insufficient_strict_consensus_books"),
        "external_forward_oos": "blocked_atp_forward_oos",
    }
    if bottleneck_type in fixed_statuses:
        return fixed_statuses[bottleneck_type]
    if label_deficit <= 0 and oos_deficit <= 0:
        return "label_threshold_met"
    if active_candidate_count <= 0 and bottleneck_type == "calendar_settlement_labels":
        return "blocked_no_active_candidate_capacity"
    if due_count > 0:
        return "next_probe_due_now"
    if next_probe_utc:
        return "waiting_for_next_probe_or_settlement"
    if bottleneck_type == "paper_fill_clock":
        return "blocked_waiting_for_paper_maker_fills"
    return "waiting_for_future_settlements"


def eta_days(next_probe_utc: str | None, *, now_ts: float) -> float | None:
    probe_ts = timestamp(next_probe_utc)
    if probe_ts is None:
        return None
    return round(max((probe_ts - now_ts) / 86400.0, 0.0), 4)


def normalize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = dict(row)
    for key in CSV_FIELDS:
        output.setdefault(key, None)
    return output


def inferred_oos_count(independent_label_count: int) -> int:
    if independent_label_count <= 0:
        return 0
    return max(1, round(independent_label_count * 0.30))


def build_summary(
    artifacts: Mapping[str, Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    blockers = [
        row
        for row in rows
        if positive(row.get("label_deficit")) or positive(row.get("oos_deficit"))
    ]
    paper_blockers = [row for row in rows if positive(row.get("paper_fill_deficit"))]
    actionable_calendar_blockers = [
        row
        for row in blockers
        if str(row.get("surface_id") or "") not in ROLLUP_SURFACES
        and str(row.get("bottleneck_type") or "") == "calendar_settlement_labels"
    ]
    external_source_blockers = [
        row
        for row in blockers
        if str(row.get("surface_id") or "") not in ROLLUP_SURFACES
        and str(row.get("bottleneck_type") or "") in SOURCE_BLOCKER_BOTTLENECKS
    ]
    waiting_evidence_blockers = [
        row
        for row in blockers
        if str(row.get("surface_id") or "") not in ROLLUP_SURFACES
        and str(row.get("bottleneck_type") or "") in WAITING_EVIDENCE_BOTTLENECKS
    ]
    rollup_blockers = [
        row for row in blockers if str(row.get("surface_id") or "") in ROLLUP_SURFACES
    ]
    statistical_no_survivor = [
        row
        for row in rows
        if str(row.get("eta_status") or "") == "label_threshold_met_no_fdr_survivor"
    ]
    status_counts = Counter(str(row.get("eta_status") or "unknown") for row in rows)
    bottleneck_counts = Counter(str(row.get("bottleneck_type") or "unknown") for row in rows)
    return {
        "safe_artifact_count": sum(1 for item in artifacts.values() if item.get("safe")),
        "artifact_count": len(artifacts),
        "unsafe_artifact_keys": [
            key for key, item in artifacts.items() if item.get("exists") and not item.get("safe")
        ],
        "missing_artifact_keys": [key for key, item in artifacts.items() if not item.get("exists")],
        "surface_count": len(rows),
        "label_blocked_surface_count": len(blockers),
        "actionable_calendar_label_blocked_surface_count": len(actionable_calendar_blockers),
        "external_or_source_blocked_surface_count": len(external_source_blockers),
        "waiting_evidence_blocked_surface_count": len(waiting_evidence_blockers),
        "rollup_label_blocked_surface_count": len(rollup_blockers),
        "statistical_no_survivor_surface_count": len(statistical_no_survivor),
        "paper_fill_blocked_surface_count": len(paper_blockers),
        "eta_status_counts": dict(sorted(status_counts.items())),
        "bottleneck_type_counts": dict(sorted(bottleneck_counts.items())),
        "total_label_deficit": sum(int(row.get("label_deficit") or 0) for row in rows),
        "total_oos_deficit": sum(int(row.get("oos_deficit") or 0) for row in rows),
        "actionable_calendar_label_deficit": sum(
            int(row.get("label_deficit") or 0) for row in actionable_calendar_blockers
        ),
        "actionable_calendar_oos_deficit": sum(
            int(row.get("oos_deficit") or 0) for row in actionable_calendar_blockers
        ),
        "external_or_source_label_deficit": sum(
            int(row.get("label_deficit") or 0) for row in external_source_blockers
        ),
        "external_or_source_oos_deficit": sum(
            int(row.get("oos_deficit") or 0) for row in external_source_blockers
        ),
        "waiting_evidence_label_deficit": sum(
            int(row.get("label_deficit") or 0) for row in waiting_evidence_blockers
        ),
        "waiting_evidence_oos_deficit": sum(
            int(row.get("oos_deficit") or 0) for row in waiting_evidence_blockers
        ),
        "rollup_label_deficit": sum(int(row.get("label_deficit") or 0) for row in rollup_blockers),
        "rollup_oos_deficit": sum(int(row.get("oos_deficit") or 0) for row in rollup_blockers),
        "total_paper_fill_deficit": sum(int(row.get("paper_fill_deficit") or 0) for row in rows),
        "next_due_surface": next_due_surface(rows),
        "next_probe_surface": next_probe_surface(rows),
    }


def next_due_surface(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    due = [
        row
        for row in rows
        if int(row.get("due_count") or 0) > 0
        or str(row.get("eta_status") or "") == "next_probe_due_now"
    ]
    if not due:
        return None
    row = sorted(
        due,
        key=lambda item: (
            str(item.get("surface_id") or "") in ROLLUP_SURFACES,
            -int(item.get("due_count") or 0),
            str(item.get("surface_id") or ""),
        ),
    )[0]
    return {
        "surface_id": row.get("surface_id"),
        "due_count": row.get("due_count"),
        "next_probe_utc": row.get("next_probe_utc"),
    }


def next_probe_surface(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        row
        for row in rows
        if row.get("next_probe_utc")
        and positive_float(row.get("eta_days"))
        and (
            positive(row.get("label_deficit"))
            or positive(row.get("oos_deficit"))
            or positive(row.get("paper_fill_deficit"))
        )
    ]
    non_rollup = [
        row for row in candidates if str(row.get("surface_id") or "") not in ROLLUP_SURFACES
    ]
    if non_rollup:
        candidates = non_rollup
    if not candidates:
        return None
    row = sorted(
        candidates,
        key=lambda item: (
            timestamp(item.get("next_probe_utc")) or float("inf"),
            str(item.get("surface_id") or "") in ROLLUP_SURFACES,
            -int(item.get("nearest_hypothesis_current_opportunity_count") or 0),
            -int(item.get("active_candidate_count") or 0),
            str(item.get("surface_id") or ""),
        ),
    )[0]
    return {
        "surface_id": row.get("surface_id"),
        "next_probe_utc": row.get("next_probe_utc"),
        "eta_days": row.get("eta_days"),
        "due_count": row.get("due_count"),
        "label_deficit": row.get("label_deficit"),
        "oos_deficit": row.get("oos_deficit"),
        "paper_fill_deficit": row.get("paper_fill_deficit"),
        "bottleneck_type": row.get("bottleneck_type"),
        "eta_status": row.get("eta_status"),
        "model_id": row.get("model_id"),
    }


def build_gates(
    artifacts: Mapping[str, Mapping[str, Any]], rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, str]]:
    unsafe = [key for key, item in artifacts.items() if item.get("exists") and not item.get("safe")]
    missing = [key for key, item in artifacts.items() if not item.get("exists")]
    return [
        gate(
            "all_existing_artifacts_safe",
            "pass" if not unsafe else "fail",
            f"Unsafe artifacts: {unsafe or []}.",
        ),
        gate(
            "required_eta_artifacts_exist",
            "pass" if not missing else "blocked",
            f"Missing artifacts: {missing or []}.",
        ),
        gate(
            "label_deficits_are_explicit",
            "pass" if rows and all("label_deficit" in row for row in rows) else "blocked",
            f"{len(rows)} ETA row(s) carry label-deficit fields.",
        ),
    ]


def report_status(gates: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]]) -> str:
    if any(item.get("status") == "fail" for item in gates):
        return "sports_event_velocity_eta_failed_safety_gate"
    if any(item.get("status") == "blocked" for item in gates):
        return "sports_event_velocity_eta_blocked_missing_artifacts"
    if any(positive(row.get("paper_fill_deficit")) for row in rows):
        return "sports_event_velocity_eta_ready_with_paper_fill_deficits"
    if any(positive(row.get("label_deficit")) or positive(row.get("oos_deficit")) for row in rows):
        return "sports_event_velocity_eta_ready_with_label_deficits"
    return "sports_event_velocity_eta_ready_all_label_thresholds_met"


def next_action(status: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    if status.endswith("failed_safety_gate"):
        return {
            "name": "kalshi_sports_eta_artifact_safety_audit",
            "why": "At least one ETA input artifact is unsafe.",
            "stop_condition": "Stop before using unsafe artifacts or overriding research-only flags.",
        }
    due = next_due_surface(rows)
    if due is not None:
        return {
            "name": "kalshi_sports_exact_settlement_probe",
            "why": f"{due['surface_id']} has due observed contracts ready for public Kalshi settlement probing.",
            "stop_condition": "Stop before using non-Kalshi labels or unsettled outcomes.",
        }
    if any(str(row.get("eta_status")) == "blocked_missing_strict_consensus_feed" for row in rows):
        return {
            "name": "kalshi_sports_missing_consensus_feed",
            "why": "At least one target sport has no strict timestamp-matched sharp consensus feed.",
            "stop_condition": "Stop before substituting projection/Elo probabilities for sharp no-vig consensus.",
        }
    if any(str(row.get("bottleneck_type") or "") in SOURCE_BLOCKER_BOTTLENECKS for row in rows):
        return {
            "name": "kalshi_sports_stale_or_source_blocker_refresh",
            "why": "At least one sports surface is blocked by stale, unmatched, or externally missing consensus evidence.",
            "stop_condition": "Stop before treating stale donor/reference rows as current sharp consensus.",
        }
    if any(
        str(row.get("bottleneck_type") or "") in WAITING_EVIDENCE_BOTTLENECKS
        for row in rows
    ):
        probe = next_probe_surface(rows)
        why = (
            f"Remaining non-statistical blockers are waiting on {probe['surface_id']} "
            f"at {probe['next_probe_utc']}."
            if probe is not None
            else "Remaining non-statistical blockers are offseason/current-market clocks or forward-OOS settlement clocks, not stale consensus inputs."
        )
        return {
            "name": "kalshi_sports_wait_for_next_settlement_clock",
            "why": why,
            "stop_condition": "Stop before lowering label, OOS, or provider-quality thresholds.",
        }
    probe = next_probe_surface(rows)
    if probe is not None:
        return {
            "name": "kalshi_sports_wait_for_next_settlement_clock",
            "why": f"{probe['surface_id']} is the next deficient evidence surface with a known probe time: {probe['next_probe_utc']}.",
            "stop_condition": "Stop before repeat-probing early or lowering label/FDR thresholds.",
        }
    if any(positive(row.get("paper_fill_deficit")) for row in rows):
        return {
            "name": "kalshi_passive_liquidity_paper_fill_clock",
            "why": "Passive liquidity needs actual paper maker fills before its FDR gate can test a candidate.",
            "stop_condition": "Stop before treating timeout-only or proxy labels as real fill evidence.",
        }
    return {
        "name": "kalshi_sports_label_accumulation",
        "why": "The remaining sports surfaces are waiting for exact labels or OOS evidence.",
        "stop_condition": "Stop before lowering label or FDR thresholds.",
    }


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def positive(value: Any) -> bool:
    return int_value(value) > 0


def positive_float(value: Any) -> bool:
    try:
        return float(value or 0) > 0
    except (TypeError, ValueError):
        return False


def write_outputs(report: Mapping[str, Any], *, out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-event-velocity-eta.json"
    md_path = out_dir / "kalshi-sports-event-velocity-eta.md"
    csv_path = out_dir / "kalshi-sports-event-velocity-eta.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("eta_rows", []), csv_path)

    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
    }
    if path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-sports-event-velocity-eta.json"
        latest_md = MACRO_DIR / "latest-kalshi-sports-event-velocity-eta.md"
        latest_csv = MACRO_DIR / "latest-kalshi-sports-event-velocity-eta.csv"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        write_csv(report.get("eta_rows", []), latest_csv)
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
        "# Kalshi Sports Event-Velocity ETA",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Surfaces: `{summary.get('surface_count')}`",
        f"- Label-blocked surfaces: `{summary.get('label_blocked_surface_count')}`",
        f"- Actionable calendar label blockers: `{summary.get('actionable_calendar_label_blocked_surface_count')}`",
        f"- External/source blockers: `{summary.get('external_or_source_blocked_surface_count')}`",
        f"- Paper-fill-blocked surfaces: `{summary.get('paper_fill_blocked_surface_count')}`",
        f"- Total label deficit: `{summary.get('total_label_deficit')}`",
        f"- Total OOS deficit: `{summary.get('total_oos_deficit')}`",
        f"- Actionable calendar label deficit: `{summary.get('actionable_calendar_label_deficit')}`",
        f"- Actionable calendar OOS deficit: `{summary.get('actionable_calendar_oos_deficit')}`",
        f"- External/source label deficit: `{summary.get('external_or_source_label_deficit')}`",
        f"- External/source OOS deficit: `{summary.get('external_or_source_oos_deficit')}`",
        f"- Total paper-fill deficit: `{summary.get('total_paper_fill_deficit')}`",
        f"- Next due surface: `{summary.get('next_due_surface')}`",
        f"- Next probe surface: `{summary.get('next_probe_surface')}`",
        f"- Bottleneck counts: `{summary.get('bottleneck_type_counts')}`",
        "",
        "| Surface | Bottleneck | ETA status | Labels | OOS | Fill | Active | Due | Next probe |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("eta_rows", []):
        if not isinstance(row, Mapping):
            continue
        lines.append(
            "| "
            f"`{row.get('surface_id')}` | "
            f"`{row.get('bottleneck_type')}` | "
            f"`{row.get('eta_status')}` | "
            f"`{row.get('independent_label_count')}/{row.get('min_independent_labels')}` | "
            f"`{row.get('oos_label_count')}/{row.get('min_oos_labels')}` | "
            f"`{row.get('paper_fill_count')}/{row.get('min_oos_fills')}` | "
            f"`{row.get('active_candidate_count')}` | "
            f"`{row.get('due_count')}` | "
            f"`{row.get('next_probe_utc')}` |"
        )
    lines.extend(
        [
            "",
            "> Research-only control-plane report. It does not lower thresholds, compute EV, size paper positions, or touch live execution.",
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
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--universe-path", type=Path, default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument("--sports-model-path", type=Path, default=DEFAULT_SPORTS_MODEL_PATH)
    parser.add_argument("--atp-evidence-path", type=Path, default=DEFAULT_ATP_EVIDENCE_PATH)
    parser.add_argument("--world-cup-model-path", type=Path, default=DEFAULT_WORLD_CUP_MODEL_PATH)
    parser.add_argument(
        "--consensus-preflight-path", type=Path, default=DEFAULT_CONSENSUS_PREFLIGHT_PATH
    )
    parser.add_argument(
        "--consensus-observation-path", type=Path, default=DEFAULT_CONSENSUS_OBSERVATION_PATH
    )
    parser.add_argument(
        "--consensus-falsification-path",
        type=Path,
        default=DEFAULT_CONSENSUS_FALSIFICATION_PATH,
    )
    parser.add_argument(
        "--consensus-nba-adapter-path",
        type=Path,
        default=DEFAULT_CONSENSUS_NBA_ADAPTER_PATH,
    )
    parser.add_argument("--flow-path", type=Path, default=DEFAULT_FLOW_PATH)
    parser.add_argument(
        "--passive-fill-falsification-path",
        type=Path,
        default=DEFAULT_PASSIVE_FILL_FALSIFICATION_PATH,
    )
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_sports_event_velocity_eta(
        universe_path=args.universe_path,
        sports_model_path=args.sports_model_path,
        atp_evidence_path=args.atp_evidence_path,
        world_cup_model_path=args.world_cup_model_path,
        consensus_preflight_path=args.consensus_preflight_path,
        consensus_observation_path=args.consensus_observation_path,
        consensus_falsification_path=args.consensus_falsification_path,
        consensus_nba_adapter_path=args.consensus_nba_adapter_path,
        flow_path=args.flow_path,
        passive_fill_falsification_path=args.passive_fill_falsification_path,
    )
    if args.write:
        paths = write_outputs(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
