#!/usr/bin/env python3
"""Replay historical sharp-consensus snapshots through the sports FDR grid.

This is the historical counterpart to the forward sports consensus collector.
It consumes an already-acquired, replayable historical no-vig consensus archive,
joins it to Kalshi historical candlesticks and exact public Kalshi settlements,
then reuses ``predmarket.sports_consensus_falsification``.  It never calls paid
provider APIs, never uses sportsbook rows as settlement labels, and never emits
EV, paper stake, or live orders.
"""

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
    gate,
    gate_counts,
    iso_from_timestamp,
    iso_time,
    json_float,
    manual_drop_path,
    path_is_within,
    probability,
    read_json_or_empty,
    safety_flags,
    sha256_or_none,
    timestamp,
)
from predmarket.sports_consensus_falsification import (  # noqa: E402
    build_sports_consensus_falsification,
    render_sports_consensus_falsification_markdown,
)
from scripts.kalshi_resolved_archive_backfill import (  # noqa: E402
    candle_mid,
    load_raw_candlesticks,
    load_raw_markets,
    series_ticker,
    settlement_outcome,
    settlement_timestamp,
    sport_key,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-historical-consensus-backfill-latest"
DEFAULT_FEASIBILITY_PATH = (
    MACRO_DIR / "latest-kalshi-sports-historical-consensus-feasibility.json"
)
DEFAULT_HISTORICAL_CONSENSUS_PATH = manual_drop_path(
    "kalshi_sports_historical_consensus",
    "kalshi_sports_historical_consensus_latest.json",
    env_vars=("KALSHI_SPORTS_HISTORICAL_CONSENSUS_ROWS_PATH",),
)
DEFAULT_MARKETS_RAW_PATH = manual_drop_path(
    "kalshi_resolved_archive_backfill",
    "kalshi_resolved_archive_markets_latest.json",
    env_vars=("KALSHI_RESOLVED_ARCHIVE_MARKETS_RAW_PATH",),
)
DEFAULT_CANDLESTICKS_RAW_PATH = manual_drop_path(
    "kalshi_resolved_archive_backfill",
    "kalshi_resolved_archive_candlesticks_latest.json",
    env_vars=("KALSHI_RESOLVED_ARCHIVE_CANDLESTICKS_RAW_PATH",),
)

CSV_FIELDS = [
    "contract_ticker",
    "event_ticker",
    "series_ticker",
    "side",
    "sport_key",
    "observed_utc",
    "provider_snapshot_utc",
    "kalshi_quote_time_utc",
    "provider_snapshot_skew_seconds",
    "kalshi_quote_skew_seconds",
    "kalshi_mid_for_side",
    "consensus_probability_for_side",
    "divergence",
    "book_count",
    "usable",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_historical_consensus_backfill(
    *,
    feasibility_report: Mapping[str, Any] | None,
    historical_consensus_rows: Sequence[Mapping[str, Any]],
    markets: Sequence[Mapping[str, Any]],
    candlesticks_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    generated_utc: str | None = None,
    historical_consensus_path: Path | None = None,
    raw_markets_path: Path | None = None,
    raw_candlesticks_path: Path | None = None,
    max_skew_seconds: int | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    candles = candlesticks_by_ticker or {}
    max_skew = int(
        max_skew_seconds
        or (feasibility_report or {}).get("summary", {}).get("max_allowed_skew_seconds")
        or 180
    )
    observations, blockers = build_observations(
        historical_consensus_rows,
        markets=markets,
        candlesticks_by_ticker=candles,
        max_skew_seconds=max_skew,
        source_path=historical_consensus_path,
    )
    labels = build_labels(markets, required_sides=required_label_sides(observations))
    preflight_report = {
        "status": "historical_consensus_backfill_replay",
        "summary": {"valid_candidate_count": len(observations)},
    }
    falsification = build_sports_consensus_falsification(
        preflight_report=preflight_report,
        consensus_observations=observations,
        settlement_labels=labels,
        generated_utc=generated,
        preflight_path=historical_consensus_path,
    )
    gates = build_gates(
        feasibility_report=feasibility_report,
        historical_rows=historical_consensus_rows,
        observations=observations,
        labels=labels,
        blockers=blockers,
        falsification=falsification,
    )
    status = report_status(gates, falsification)
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "family_id": "sports_no_vig_consensus_historical_backfill",
        "public_market_data_calls": False,
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "paid_historical_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "inputs": {
            "feasibility_status": (feasibility_report or {}).get("status"),
            "historical_consensus_path": str(historical_consensus_path)
            if historical_consensus_path
            else None,
            "historical_consensus_sha256": sha256_or_none(historical_consensus_path)
            if historical_consensus_path
            else None,
            "raw_markets_path": str(raw_markets_path) if raw_markets_path else None,
            "raw_markets_sha256": sha256_or_none(raw_markets_path) if raw_markets_path else None,
            "raw_candlesticks_path": str(raw_candlesticks_path) if raw_candlesticks_path else None,
            "raw_candlesticks_sha256": sha256_or_none(raw_candlesticks_path)
            if raw_candlesticks_path
            else None,
        },
        "method": {
            "source": "Replayable historical sharp no-vig consensus rows plus Kalshi public history.",
            "historical_consensus_contract": (
                "Rows must carry exact contract_ticker, side, observed_utc, "
                "consensus_probability_for_side or consensus_yes_probability, "
                "and timestamp provenance."
            ),
            "kalshi_price_join": (
                "Select the nearest Kalshi candlestick for the exact ticker within "
                f"{max_skew} seconds of observed_utc; convert YES mid to side mid."
            ),
            "label_rule": "Exact public Kalshi settlement outcome matched by contract_ticker.",
            "skew_policy": f"Provider snapshot and Kalshi quote skew must both be <= {max_skew}s.",
            "promotion_boundary": "Research-only falsification input; no EV, paper, or live output.",
        },
        "summary": {
            "historical_consensus_row_count": len(historical_consensus_rows),
            "valid_observation_count": len(observations),
            "settlement_label_count": len(labels),
            "join_blocker_count": len(blockers),
            "max_allowed_skew_seconds": max_skew,
            "max_provider_snapshot_skew_seconds": max_float(
                row.get("provider_snapshot_skew_seconds") for row in observations
            ),
            "max_kalshi_quote_skew_seconds": max_float(
                row.get("kalshi_quote_skew_seconds") for row in observations
            ),
            "falsification_status": falsification.get("status"),
            "tested_hypothesis_count": falsification.get("summary", {}).get(
                "tested_hypothesis_count"
            ),
            "fdr_survivor_count": falsification.get("summary", {}).get("fdr_survivor_count"),
            "max_hypothesis_oos_count": falsification.get("summary", {}).get(
                "max_hypothesis_oos_count"
            ),
            "gate_counts": gate_counts(gates),
        },
        "gates": gates,
        "observations": observations,
        "labels": labels,
        "join_blockers": blockers[:200],
        "falsification": falsification,
        "next_action": next_action(status),
        "safety": safety_flags(),
    }


def build_observations(
    rows: Sequence[Mapping[str, Any]],
    *,
    markets: Sequence[Mapping[str, Any]],
    candlesticks_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
    max_skew_seconds: int,
    source_path: Path | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    market_lookup = {
        str(row.get("ticker") or row.get("contract_ticker") or "").strip(): row
        for row in markets
        if str(row.get("ticker") or row.get("contract_ticker") or "").strip()
    }
    source_hash = sha256_or_none(source_path) if source_path else None
    observations: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        normalized, blocker = normalize_historical_row(
            row,
            market_lookup=market_lookup,
            candlesticks_by_ticker=candlesticks_by_ticker,
            max_skew_seconds=max_skew_seconds,
            source_hash=source_hash,
        )
        if blocker:
            blockers.append(blocker)
            continue
        assert normalized is not None
        key = (
            str(normalized["contract_ticker"]),
            str(normalized["side"]),
            str(normalized["observed_utc"]),
        )
        if key in seen:
            continue
        seen.add(key)
        observations.append(normalized)
    observations.sort(key=lambda item: (item["observed_utc"], item["contract_ticker"]))
    return observations, blockers


def normalize_historical_row(
    row: Mapping[str, Any],
    *,
    market_lookup: Mapping[str, Mapping[str, Any]],
    candlesticks_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
    max_skew_seconds: int,
    source_hash: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    ticker = str(row.get("contract_ticker") or row.get("ticker") or "").strip()
    side = normalize_side(row.get("side") or row.get("contract_side"))
    observed = iso_time(
        row.get("observed_utc")
        or row.get("target_time_utc")
        or row.get("decision_time")
        or row.get("timestamp")
    )
    if not ticker or side is None or observed is None:
        return None, blocker(row, "missing_exact_ticker_side_or_observed_time", ticker=ticker)
    observed_ts = timestamp(observed)
    consensus = consensus_for_side(row, side)
    if consensus is None:
        return None, blocker(row, "missing_consensus_probability", ticker=ticker, side=side)
    provider_snapshot = iso_time(
        row.get("provider_snapshot_utc")
        or row.get("snapshot_timestamp_utc")
        or row.get("snapshot_time")
        or observed
    )
    provider_skew = explicit_or_computed_skew(row, observed_ts, provider_snapshot)
    if provider_skew is None or provider_skew > max_skew_seconds:
        return None, blocker(
            row,
            "provider_snapshot_skew_exceeds_policy",
            ticker=ticker,
            side=side,
            skew=provider_skew,
        )
    market = market_lookup.get(ticker)
    if market is None:
        return None, blocker(row, "missing_exact_kalshi_settled_market", ticker=ticker, side=side)
    candle, quote_skew = nearest_candle(
        candlesticks_by_ticker.get(ticker, []),
        target_ts=observed_ts,
        max_skew_seconds=max_skew_seconds,
    )
    if candle is None:
        return None, blocker(row, "missing_kalshi_historical_quote", ticker=ticker, side=side)
    yes_mid = candle_mid(candle)
    if yes_mid is None:
        return None, blocker(row, "missing_kalshi_historical_mid", ticker=ticker, side=side)
    side_mid = float(yes_mid) if side == "yes" else 1.0 - float(yes_mid)
    event = str(row.get("event_ticker") or market.get("event_ticker") or derive_event(ticker))
    series = str(row.get("series_ticker") or series_ticker(market, ticker))
    sport = str(row.get("sport_key") or sport_key(series, ticker))
    quote_time = iso_time(candle.get("end_period_ts") or candle.get("ts") or candle.get("time"))
    return (
        {
            "schema_version": "KalshiHistoricalConsensusObservationV1",
            "observation_id": f"historical_consensus_{ticker}_{side}_{observed}",
            "contract_ticker": ticker,
            "event_ticker": event,
            "series_ticker": series,
            "side": side,
            "family_id": "sports_no_vig_consensus_historical_backfill",
            "sport_key": sport,
            "market_key": str(row.get("market_key") or series),
            "cluster_key": str(row.get("cluster_key") or f"{sport}|{series}|{event}"),
            "observed_utc": observed,
            "decision_time": observed,
            "quote_time": observed,
            "provider_snapshot_utc": provider_snapshot,
            "kalshi_quote_time_utc": quote_time,
            "provider_snapshot_skew_seconds": json_float(provider_skew),
            "kalshi_quote_skew_seconds": json_float(quote_skew),
            "kalshi_mid_for_side": json_float(side_mid),
            "consensus_probability_for_side": json_float(consensus),
            "consensus_no_vig_probability_for_side": json_float(consensus),
            "divergence": json_float(float(consensus) - side_mid),
            "book_count": int(row.get("book_count") or len(row.get("distinct_books") or [])),
            "distinct_books": list(row.get("distinct_books") or row.get("books") or []),
            "consensus_method": str(row.get("consensus_method") or "historical_no_vig_consensus"),
            "source_reference_sha256": row.get("source_reference_sha256") or source_hash,
            "calibrated_probability": None,
            "expected_value_per_contract": None,
            "usable": False,
            "research_only": True,
            "execution_enabled": False,
        },
        None,
    )


def build_labels(
    markets: Sequence[Mapping[str, Any]],
    *,
    required_sides: Mapping[str, set[str]],
) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []
    for market in markets:
        ticker = str(market.get("ticker") or market.get("contract_ticker") or "").strip()
        if ticker not in required_sides:
            continue
        yes_outcome = settlement_outcome(market)
        settled_ts = settlement_timestamp(market)
        if yes_outcome is None or settled_ts is None:
            continue
        for side in sorted(required_sides[ticker]):
            labels.append(
                {
                    "contract_ticker": ticker,
                    "event_ticker": market.get("event_ticker") or derive_event(ticker),
                    "series_ticker": series_ticker(market, ticker),
                    "side": side,
                    "yes_outcome": int(yes_outcome),
                    "side_outcome": int(yes_outcome if side == "yes" else 1 - yes_outcome),
                    "settled_time": iso_from_timestamp(settled_ts),
                    "settlement_time_utc": iso_from_timestamp(settled_ts),
                    "settlement_result": market.get("result") or market.get("expiration_value"),
                    "label_source": "public_kalshi_settled_market_payload",
                    "label_status": "labeled_from_public_kalshi_resolved_archive",
                    "usable": False,
                    "research_only": True,
                    "execution_enabled": False,
                }
            )
    labels.sort(key=lambda item: (item["contract_ticker"], item["side"]))
    return labels


def required_label_sides(observations: Sequence[Mapping[str, Any]]) -> dict[str, set[str]]:
    sides: dict[str, set[str]] = {}
    for row in observations:
        ticker = str(row.get("contract_ticker") or "")
        side = normalize_side(row.get("side"))
        if ticker and side:
            sides.setdefault(ticker, set()).add(side)
    return sides


def build_gates(
    *,
    feasibility_report: Mapping[str, Any] | None,
    historical_rows: Sequence[Mapping[str, Any]],
    observations: Sequence[Mapping[str, Any]],
    labels: Sequence[Mapping[str, Any]],
    blockers: Sequence[Mapping[str, Any]],
    falsification: Mapping[str, Any],
) -> list[dict[str, str]]:
    feasibility_status = str((feasibility_report or {}).get("status") or "")
    skew_pass = bool((feasibility_report or {}).get("summary", {}).get("skew_gate_pass"))
    tested = int(falsification.get("summary", {}).get("tested_hypothesis_count") or 0)
    return [
        gate(
            "historical_feasibility_skew_gate",
            "pass" if skew_pass else "blocked",
            f"Feasibility status `{feasibility_status or 'missing'}`.",
        ),
        gate(
            "historical_consensus_rows_available",
            "pass" if historical_rows else "blocked",
            f"{len(historical_rows)} historical consensus row(s) supplied.",
        ),
        gate(
            "exact_kalshi_price_and_label_join",
            "pass" if observations and labels else "blocked",
            f"{len(observations)} valid observation(s), {len(labels)} exact label(s), {len(blockers)} blocker(s).",
        ),
        gate(
            "falsification_reached",
            "pass" if tested else "blocked",
            f"{tested} hypothesis cell(s) reached OOS/FDR testing.",
        ),
        gate("no_live_or_paper_paths", "pass", "No EV, paper stake, account state, or orders."),
    ]


def report_status(gates: Sequence[Mapping[str, Any]], falsification: Mapping[str, Any]) -> str:
    if any(item.get("status") == "fail" for item in gates):
        return "kalshi_sports_historical_consensus_backfill_failed_safety_gate"
    gate_by_name = {str(item.get("name")): str(item.get("status")) for item in gates}
    if gate_by_name.get("historical_feasibility_skew_gate") != "pass":
        return "kalshi_sports_historical_consensus_backfill_blocked_feasibility_skew"
    if gate_by_name.get("historical_consensus_rows_available") != "pass":
        return "kalshi_sports_historical_consensus_backfill_blocked_missing_historical_archive"
    if gate_by_name.get("exact_kalshi_price_and_label_join") != "pass":
        return "kalshi_sports_historical_consensus_backfill_blocked_no_valid_join"
    if not falsification.get("summary", {}).get("tested_hypothesis_count"):
        return "kalshi_sports_historical_consensus_backfill_ready_no_testable_hypotheses"
    if falsification.get("summary", {}).get("fdr_survivor_count"):
        return "kalshi_sports_historical_consensus_backfill_ready_with_research_candidates"
    return "kalshi_sports_historical_consensus_backfill_ready_no_research_candidates"


def next_action(status: str) -> dict[str, str]:
    if status == "kalshi_sports_historical_consensus_backfill_ready_with_research_candidates":
        return {
            "name": "sports_consensus_historical_survivor_downstream_gates",
            "why": "At least one historical divergence cell survived OOS/FDR.",
            "stop_condition": "Stop before EV or paper unless existing cost/capacity/correlation/decay gates pass.",
        }
    if status == "kalshi_sports_historical_consensus_backfill_blocked_missing_historical_archive":
        return {
            "name": "acquire_replayable_historical_no_vig_consensus_archive",
            "why": "Skew feasibility is compatible, but no normalized historical consensus rows were supplied.",
            "stop_condition": "Do not infer rows from non-timestamped book boards.",
        }
    if status == "kalshi_sports_historical_consensus_backfill_blocked_no_valid_join":
        return {
            "name": "repair_exact_ticker_or_quote_join",
            "why": "Historical consensus rows exist but do not join to exact Kalshi prices and settlements.",
            "stop_condition": "Do not loosen exact ticker or skew gates.",
        }
    return {
        "name": "continue_historical_consensus_evidence_accumulation",
        "why": "The replay surface is operating but has no admitted research candidate at current gates.",
        "stop_condition": "Do not lower thresholds or add post-hoc hypotheses.",
    }


def nearest_candle(
    candles: Sequence[Mapping[str, Any]],
    *,
    target_ts: float | None,
    max_skew_seconds: int,
) -> tuple[Mapping[str, Any] | None, float | None]:
    if target_ts is None:
        return None, None
    candidates: list[tuple[float, Mapping[str, Any]]] = []
    for candle in candles:
        if not isinstance(candle, Mapping):
            continue
        candle_ts = timestamp(candle.get("end_period_ts") or candle.get("ts") or candle.get("time"))
        if candle_ts is None:
            continue
        skew = abs(float(candle_ts) - float(target_ts))
        if skew <= max_skew_seconds:
            candidates.append((skew, candle))
    if not candidates:
        return None, None
    skew, candle = min(candidates, key=lambda item: item[0])
    return candle, skew


def consensus_for_side(row: Mapping[str, Any], side: str) -> float | None:
    direct = probability(
        row.get("consensus_probability_for_side")
        or row.get("consensus_no_vig_probability_for_side")
        or row.get("no_vig_probability_for_side")
    )
    if direct is not None:
        return direct
    yes_probability = probability(
        row.get("consensus_yes_probability")
        or row.get("consensus_no_vig_yes_probability")
        or row.get("yes_probability")
    )
    if yes_probability is None:
        return None
    return yes_probability if side == "yes" else 1.0 - yes_probability


def explicit_or_computed_skew(
    row: Mapping[str, Any], observed_ts: float | None, provider_snapshot_utc: str | None
) -> float | None:
    explicit = row.get("timestamp_skew_seconds") or row.get("provider_snapshot_skew_seconds")
    if explicit is not None:
        try:
            return abs(float(explicit))
        except (TypeError, ValueError):
            return None
    provider_ts = timestamp(provider_snapshot_utc)
    if observed_ts is None or provider_ts is None:
        return None
    return abs(float(provider_ts) - float(observed_ts))


def blocker(
    row: Mapping[str, Any],
    reason: str,
    *,
    ticker: str | None = None,
    side: str | None = None,
    skew: float | None = None,
) -> dict[str, Any]:
    return {
        "reason": reason,
        "contract_ticker": ticker or row.get("contract_ticker") or row.get("ticker"),
        "side": side or row.get("side"),
        "observed_utc": row.get("observed_utc") or row.get("target_time_utc"),
        "skew_seconds": json_float(skew),
        "research_only": True,
        "usable": False,
    }


def normalize_side(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"yes", "y"}:
        return "yes"
    if text in {"no", "n"}:
        return "no"
    return None


def derive_event(ticker: str) -> str:
    pieces = ticker.split("-")
    return "-".join(pieces[:2]) if len(pieces) >= 2 else ticker


def max_float(values: Sequence[Any]) -> float | None:
    parsed: list[float] = []
    for value in values:
        try:
            if value is not None:
                parsed.append(float(value))
        except (TypeError, ValueError):
            continue
    return max(parsed) if parsed else None


def load_historical_consensus_rows(path: Path | None) -> list[dict[str, Any]]:
    payload = read_json_or_empty(path) if path and path.is_file() else {}
    rows = (
        payload.get("rows")
        or payload.get("historical_consensus_rows")
        or payload.get("consensus_rows")
        or payload.get("observations")
        or []
    )
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def write_outputs(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-historical-consensus-backfill.json"
    md_path = out_dir / "kalshi-sports-historical-consensus-backfill.md"
    csv_path = out_dir / "kalshi-sports-historical-consensus-backfill.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    markdown = render_markdown(report)
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    write_csv(report.get("observations", []), csv_path)
    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
    }
    if path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-sports-historical-consensus-backfill.json"
        latest_md = MACRO_DIR / "latest-kalshi-sports-historical-consensus-backfill.md"
        latest_csv = MACRO_DIR / "latest-kalshi-sports-historical-consensus-backfill.csv"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(markdown, encoding="utf-8")
        write_csv(report.get("observations", []), latest_csv)
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
        "# Kalshi Sports Historical Consensus Backfill",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Historical consensus rows: `{summary.get('historical_consensus_row_count')}`",
        f"- Valid observations: `{summary.get('valid_observation_count')}`",
        f"- Settlement labels: `{summary.get('settlement_label_count')}`",
        f"- Tested hypotheses: `{summary.get('tested_hypothesis_count')}`",
        f"- FDR survivors: `{summary.get('fdr_survivor_count')}`",
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
            "## Falsification",
            "",
            render_sports_consensus_falsification_markdown(
                report.get("falsification", {}) if isinstance(report.get("falsification"), Mapping) else {}
            ),
            "",
            "Research-only historical replay. No sportsbook settlement labels, no EV, no paper stake, and no live execution.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in CSV_FIELDS})


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--feasibility-path", type=Path, default=DEFAULT_FEASIBILITY_PATH)
    parser.add_argument("--historical-consensus-path", type=Path, default=DEFAULT_HISTORICAL_CONSENSUS_PATH)
    parser.add_argument("--markets-raw-path", type=Path, default=DEFAULT_MARKETS_RAW_PATH)
    parser.add_argument("--candlesticks-raw-path", type=Path, default=DEFAULT_CANDLESTICKS_RAW_PATH)
    parser.add_argument("--max-skew-seconds", type=int)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_historical_consensus_backfill(
        feasibility_report=read_json_or_empty(args.feasibility_path)
        if args.feasibility_path.is_file()
        else {},
        historical_consensus_rows=load_historical_consensus_rows(args.historical_consensus_path),
        markets=load_raw_markets(args.markets_raw_path),
        candlesticks_by_ticker=load_raw_candlesticks(args.candlesticks_raw_path),
        generated_utc=utc_now(),
        historical_consensus_path=args.historical_consensus_path,
        raw_markets_path=args.markets_raw_path,
        raw_candlesticks_path=args.candlesticks_raw_path,
        max_skew_seconds=args.max_skew_seconds,
    )
    if args.write:
        paths = write_outputs(report, args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
