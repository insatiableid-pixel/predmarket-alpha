"""Strict sports no-vig consensus intake helpers.

Sports probabilities should come from timestamp-matched sharp consensus, not
from an internal projection model. This module validates that boundary before
any row can feed downstream research gates.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from predmarket.type2_paper_matcher import no_vig_midpoint_from_reference

FORBIDDEN_PRIMARY_SOURCE_TYPES = {
    "elo",
    "internal_model",
    "projection",
    "projection_model",
    "sim",
    "simulation",
}

ALLOWED_SPORTS_EDGE_FAMILIES = [
    "kalshi_vs_no_vig_multi_book_consensus",
    "stale_quote_slow_update_after_consensus_move",
    "settlement_window_probability_decay",
    "resolved_archive_price_bucket_bias",
]


def sports_consensus_doctrine() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "primary_sports_probability_source": "timestamp_matched_multi_book_no_vig_consensus",
        "projection_model_policy": (
            "Internal Elo, simulation, and projection probabilities may be metadata or "
            "separately falsified hypotheses, but they are not the default sports model "
            "and cannot directly supply tradable probabilities."
        ),
        "allowed_edge_families": list(ALLOWED_SPORTS_EDGE_FAMILIES),
        "required_downstream_gates": [
            "exact_kalshi_mapping",
            "out_of_sample_falsification",
            "fdr_control",
            "kalshi_fee_and_spread_replay",
            "capacity_depth",
            "correlation_cluster_control",
            "decay_survival",
        ],
        "no_discretion_boundary": (
            "Humans may configure thresholds and allowed sources; rows are admitted, "
            "blocked, sized, retired, or replaced mechanically."
        ),
    }


def build_sports_consensus_preflight(
    kalshi_payload: Mapping[str, Any],
    consensus_payload: Mapping[str, Any] | None,
    *,
    kalshi_path: Path | None = None,
    consensus_path: Path | None = None,
    run_id: str | None = None,
    created_ts: float | None = None,
    min_distinct_books: int = 2,
    max_timestamp_skew_seconds: float = 180.0,
) -> dict[str, Any]:
    ts = float(created_ts or time.time())
    rows = _consensus_rows(consensus_payload)
    row_by_ticker = _index_kalshi_rows(kalshi_payload)
    grouped = _group_reference_rows(rows)
    candidates: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []

    if consensus_payload is None:
        blockers.append(
            {
                "reason": "missing_no_vig_consensus_reference",
                "detail": (
                    "Supply timestamp-matched multi-book no-vig sports consensus rows "
                    "outside the repo."
                ),
            }
        )
    elif not rows:
        blockers.append(
            {
                "reason": "empty_no_vig_consensus_reference",
                "detail": "Consensus JSON must contain a non-empty markets, references, rows, or consensus_rows list.",
            }
        )

    for key, group_rows in grouped.items():
        candidate = _candidate_from_group(
            key,
            group_rows,
            row_by_ticker=row_by_ticker,
            kalshi_payload=kalshi_payload,
            min_distinct_books=min_distinct_books,
            max_timestamp_skew_seconds=max_timestamp_skew_seconds,
        )
        candidates.append(candidate)
        blockers.extend(candidate["blockers"])

    valid_count = sum(1 for candidate in candidates if candidate["valid"])
    status = _status(
        consensus_payload=consensus_payload,
        rows=rows,
        valid_count=valid_count,
        blockers=blockers,
    )
    ready = valid_count > 0
    return {
        "schema_version": 1,
        "run_id": run_id
        or _stable_run_id(
            kalshi_payload,
            consensus_payload or {},
            min_distinct_books=min_distinct_books,
            max_timestamp_skew_seconds=max_timestamp_skew_seconds,
        ),
        "created_ts": ts,
        "created_at_utc": datetime.fromtimestamp(ts, UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "ready": ready,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "raw_provider_payload_copied": False,
        "staking_or_sizing_guidance": False,
        "safety": {
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "account_or_order_paths": False,
            "market_execution": False,
            "raw_provider_payload_copied": False,
        },
        "doctrine": sports_consensus_doctrine(),
        "policy": {
            "probability_source": "timestamp_matched_multi_book_no_vig_consensus",
            "min_distinct_books": int(min_distinct_books),
            "max_timestamp_skew_seconds": float(max_timestamp_skew_seconds),
            "exact_kalshi_ticker_required": True,
            "forbidden_primary_source_types": sorted(FORBIDDEN_PRIMARY_SOURCE_TYPES),
            "provider_calls_allowed": False,
        },
        "inputs": {
            "kalshi_json": str(kalshi_path) if kalshi_path else None,
            "consensus_json": str(consensus_path) if consensus_path else None,
            "kalshi_sha256": _sha256(kalshi_path)
            if kalshi_path and kalshi_path.is_file()
            else None,
            "consensus_sha256": _sha256(consensus_path)
            if consensus_path and consensus_path.is_file()
            else None,
            "kalshi_rows": len(row_by_ticker),
            "consensus_rows": len(rows),
        },
        "summary": {
            "candidate_count": len(candidates),
            "valid_candidate_count": valid_count,
            "blocked_candidate_count": len(candidates) - valid_count,
            "reference_row_count": len(rows),
            "distinct_book_count": len(
                {
                    str(row.get("book_id") or row.get("book") or row.get("sportsbook") or "")
                    for row in rows
                    if str(row.get("book_id") or row.get("book") or row.get("sportsbook") or "")
                }
            ),
            "blocker_count": len(blockers),
            "projection_source_blocker_count": sum(
                1
                for blocker in blockers
                if blocker["reason"] == "forbidden_projection_primary_source"
            ),
            "single_book_blocker_count": sum(
                1 for blocker in blockers if blocker["reason"] == "insufficient_distinct_books"
            ),
            "timestamp_blocker_count": sum(
                1
                for blocker in blockers
                if blocker["reason"]
                in {
                    "missing_reference_timestamp",
                    "missing_kalshi_timestamp",
                    "timestamp_skew_exceeds_policy",
                }
            ),
        },
        "gates": _gates(
            consensus_payload=consensus_payload,
            rows=rows,
            candidates=candidates,
            blockers=blockers,
        ),
        "candidates": candidates,
        "blockers": blockers,
    }


def render_sports_consensus_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Sports No-Vig Consensus Preflight",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Ready: `{str(report.get('ready', False)).lower()}`",
        "- Mode: research-only",
        "- Execution enabled: `false`",
        "",
        "## Doctrine",
        "",
        "- The sharp timestamp-matched no-vig consensus line is the primary sports probability source.",
        "- Internal projection, Elo, and simulation probabilities cannot directly supply sports tradable probabilities.",
        "- Valid rows still require OOS/FDR, fee/spread replay, capacity, cluster, and decay gates downstream.",
        "",
        "## Summary",
        "",
        f"- Reference rows: `{summary.get('reference_row_count', 0)}`",
        f"- Candidates: `{summary.get('candidate_count', 0)}`",
        f"- Valid candidates: `{summary.get('valid_candidate_count', 0)}`",
        f"- Blocked candidates: `{summary.get('blocked_candidate_count', 0)}`",
        f"- Distinct books: `{summary.get('distinct_book_count', 0)}`",
        f"- Blockers: `{summary.get('blocker_count', 0)}`",
        "",
        "## Gates",
        "",
    ]
    for gate in report.get("gates", []):
        if isinstance(gate, Mapping):
            lines.append(f"- `{gate.get('name')}`: `{gate.get('status')}` - {gate.get('reason')}")
    blockers = [item for item in report.get("blockers", []) if isinstance(item, Mapping)]
    if blockers:
        lines.extend(["", "## Blockers", ""])
        for blocker in blockers[:25]:
            lines.append(
                f"- `{blocker.get('reason')}`"
                f" `{blocker.get('kalshi_ticker', blocker.get('reference_id', ''))}`:"
                f" {blocker.get('detail')}"
            )
    lines.extend(
        [
            "",
            "> Research-only preflight. This artifact does not compute stake, authorize orders, or bypass downstream gates.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _candidate_from_group(
    key: tuple[str, str],
    rows: Sequence[Mapping[str, Any]],
    *,
    row_by_ticker: Mapping[str, Mapping[str, Any]],
    kalshi_payload: Mapping[str, Any],
    min_distinct_books: int,
    max_timestamp_skew_seconds: float,
) -> dict[str, Any]:
    kalshi_ticker, side = key
    blockers: list[dict[str, Any]] = []
    book_rows: list[dict[str, Any]] = []
    kalshi_row = row_by_ticker.get(kalshi_ticker)
    kalshi_time = _kalshi_timestamp(kalshi_row or {}, kalshi_payload)

    if not kalshi_ticker:
        blockers.append(
            _blocker(
                "missing_explicit_kalshi_ticker", key, "Consensus row is missing kalshi_ticker."
            )
        )
    elif kalshi_row is None:
        blockers.append(_blocker("kalshi_ticker_not_found", key, kalshi_ticker))

    if kalshi_time is None:
        blockers.append(
            _blocker(
                "missing_kalshi_timestamp",
                key,
                "Kalshi artifact or mapped row must expose an observed/captured timestamp.",
            )
        )

    for row in rows:
        row_blockers: list[dict[str, Any]] = []
        reference_id = str(
            row.get("reference_id") or row.get("id") or f"{kalshi_ticker}:{len(book_rows)}"
        )
        book_id = str(row.get("book_id") or row.get("book") or row.get("sportsbook") or "").strip()
        source_type = (
            str(row.get("source_type") or row.get("probability_source_type") or "").strip().lower()
        )
        captured = _parse_utc(
            row.get("observed_utc")
            or row.get("capture_time_utc")
            or row.get("captured_at_utc")
            or row.get("timestamp_utc")
        )
        if source_type in FORBIDDEN_PRIMARY_SOURCE_TYPES:
            row_blockers.append(
                _blocker(
                    "forbidden_projection_primary_source",
                    key,
                    f"source_type={source_type} cannot be the sports consensus probability source.",
                    reference_id=reference_id,
                )
            )
        if not book_id:
            row_blockers.append(
                _blocker(
                    "missing_book_id",
                    key,
                    "Every consensus row must identify the sportsbook/book.",
                    reference_id=reference_id,
                )
            )
        if captured is None:
            row_blockers.append(
                _blocker(
                    "missing_reference_timestamp",
                    key,
                    "Every consensus row must include observed_utc/capture_time_utc.",
                    reference_id=reference_id,
                )
            )
        try:
            no_vig = no_vig_midpoint_from_reference(row)
        except ValueError as exc:
            row_blockers.append(
                _blocker(
                    "invalid_two_sided_no_vig_odds",
                    key,
                    str(exc),
                    reference_id=reference_id,
                )
            )
            no_vig = None
        blockers.extend(row_blockers)
        if not row_blockers and no_vig is not None and captured is not None:
            book_rows.append(
                {
                    "reference_id": reference_id,
                    "book_id": book_id,
                    "captured_at_utc": _format_utc(captured),
                    "no_vig_yes": no_vig["no_vig_yes"],
                    "no_vig_no": no_vig["no_vig_no"],
                    "raw_yes_implied": no_vig["raw_yes_implied"],
                    "raw_no_implied": no_vig["raw_no_implied"],
                    "overround": no_vig["overround"],
                }
            )

    distinct_books = sorted({row["book_id"] for row in book_rows})
    if len(distinct_books) < min_distinct_books:
        blockers.append(
            _blocker(
                "insufficient_distinct_books",
                key,
                f"{len(distinct_books)} distinct book(s); require at least {min_distinct_books}.",
            )
        )

    timestamp_skew = _timestamp_skew_seconds(book_rows, kalshi_time)
    if timestamp_skew is not None and timestamp_skew > max_timestamp_skew_seconds:
        blockers.append(
            _blocker(
                "timestamp_skew_exceeds_policy",
                key,
                f"max skew {timestamp_skew:.3f}s exceeds {max_timestamp_skew_seconds:.3f}s.",
            )
        )

    valid = not blockers
    probabilities = [float(row["no_vig_yes"]) for row in book_rows]
    consensus_yes = statistics.median(probabilities) if probabilities else None
    consensus_for_side = _side_probability(consensus_yes, side)
    return {
        "kalshi_ticker": kalshi_ticker,
        "side": side,
        "valid": valid,
        "book_count": len(book_rows),
        "distinct_books": distinct_books,
        "kalshi_observed_utc": _format_utc(kalshi_time),
        "timestamp_skew_seconds": timestamp_skew,
        "consensus_no_vig_yes_probability": consensus_yes,
        "consensus_no_vig_probability_for_side": consensus_for_side,
        "consensus_method": "median_of_book_level_two_way_no_vig_probabilities",
        "book_rows": book_rows,
        "blocker_reasons": [blocker["reason"] for blocker in blockers],
        "blockers": blockers,
    }


def _group_reference_rows(
    rows: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        ticker = str(
            row.get("kalshi_ticker") or row.get("contract_ticker") or row.get("ticker") or ""
        ).strip()
        side = str(row.get("side") or row.get("kalshi_side") or "yes").strip().lower()
        if side not in {"yes", "no"}:
            side = "yes"
        grouped[(ticker, side)].append(row)
    return dict(grouped)


def _consensus_rows(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    for key in ("consensus_rows", "markets", "references", "rows"):
        rows = payload.get(key)
        if isinstance(rows, list):
            expanded: list[dict[str, Any]] = []
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                books = row.get("books") or row.get("bookmakers")
                if isinstance(books, list):
                    for book_row in books:
                        if isinstance(book_row, Mapping):
                            expanded.append({**dict(row), **dict(book_row)})
                    continue
                expanded.append(dict(row))
            return expanded
    return []


def _index_kalshi_rows(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows: Any
    if isinstance(payload, list):
        rows = payload
    else:
        rows = (
            payload.get("all_scored")
            or payload.get("candidates")
            or payload.get("markets")
            or payload.get("rows")
            or payload.get("top_50")
            or []
        )
    out: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if isinstance(row, Mapping):
            for key in ("ticker", "contract_ticker", "market_id"):
                ticker = str(row.get(key) or "").strip()
                if ticker and ticker not in out:
                    out[ticker] = row
    return out


def _timestamp_skew_seconds(
    book_rows: Sequence[Mapping[str, Any]], kalshi_time: datetime | None
) -> float | None:
    if kalshi_time is None or not book_rows:
        return None
    deltas = []
    for row in book_rows:
        captured = _parse_utc(row.get("captured_at_utc"))
        if captured is not None:
            deltas.append(abs((captured - kalshi_time).total_seconds()))
    return max(deltas) if deltas else None


def _kalshi_timestamp(row: Mapping[str, Any], payload: Mapping[str, Any]) -> datetime | None:
    for source in (row, payload):
        for key in (
            "observed_utc",
            "capture_time_utc",
            "captured_at_utc",
            "created_at_utc",
            "generated_utc",
        ):
            parsed = _parse_utc(source.get(key))
            if parsed is not None:
                return parsed
    return None


def _parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _side_probability(consensus_yes: float | None, side: str) -> float | None:
    if consensus_yes is None or not math.isfinite(consensus_yes):
        return None
    if side == "no":
        return 1.0 - consensus_yes
    return consensus_yes


def _status(
    *,
    consensus_payload: Mapping[str, Any] | None,
    rows: Sequence[Mapping[str, Any]],
    valid_count: int,
    blockers: Sequence[Mapping[str, Any]],
) -> str:
    if consensus_payload is None:
        return "sports_consensus_preflight_blocked_missing_reference"
    if not rows:
        return "sports_consensus_preflight_blocked_empty_reference"
    if valid_count <= 0:
        return "sports_consensus_preflight_blocked_no_valid_consensus_rows"
    if blockers:
        return "sports_consensus_preflight_ready_with_rejected_rows"
    return "sports_consensus_preflight_ready"


def _gates(
    *,
    consensus_payload: Mapping[str, Any] | None,
    rows: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    blockers: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    blocker_reasons = {str(blocker.get("reason")) for blocker in blockers}
    valid_count = sum(1 for candidate in candidates if candidate.get("valid") is True)
    return [
        _gate(
            "research_only_safety",
            "pass",
            "No provider, paid, database, account, order, or execution calls are used.",
        ),
        _gate(
            "consensus_reference_available",
            "pass" if consensus_payload is not None else "blocked",
            "Consensus reference supplied."
            if consensus_payload is not None
            else "Consensus reference is missing.",
        ),
        _gate(
            "consensus_rows_present",
            "pass" if rows else "blocked",
            f"Consensus reference rows: {len(rows)}.",
        ),
        _gate(
            "projection_sources_rejected",
            "blocked" if "forbidden_projection_primary_source" in blocker_reasons else "pass",
            "Projection/model rows are not allowed as the sports consensus probability source.",
        ),
        _gate(
            "multi_book_no_vig_consensus",
            "pass" if valid_count > 0 else "blocked",
            f"Valid multi-book no-vig consensus candidates: {valid_count}.",
        ),
        _gate(
            "timestamp_matched",
            "blocked"
            if {
                "missing_reference_timestamp",
                "missing_kalshi_timestamp",
                "timestamp_skew_exceeds_policy",
            }
            & blocker_reasons
            else ("pass" if valid_count > 0 else "blocked"),
            "Every valid candidate is timestamp matched to the Kalshi observation.",
        ),
        _gate(
            "exact_kalshi_mapping",
            "blocked"
            if {"missing_explicit_kalshi_ticker", "kalshi_ticker_not_found"} & blocker_reasons
            else ("pass" if valid_count > 0 else "blocked"),
            "Only exact Kalshi ticker mappings are admitted.",
        ),
    ]


def _gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def _blocker(
    reason: str,
    key: tuple[str, str],
    detail: str,
    *,
    reference_id: str | None = None,
) -> dict[str, str]:
    ticker, side = key
    return {
        "reason": reason,
        "detail": detail,
        "kalshi_ticker": ticker,
        "side": side,
        "reference_id": reference_id or ticker,
    }


def _stable_run_id(
    kalshi_payload: Mapping[str, Any],
    consensus_payload: Mapping[str, Any],
    *,
    min_distinct_books: int,
    max_timestamp_skew_seconds: float,
) -> str:
    payload = {
        "kalshi": kalshi_payload,
        "consensus": consensus_payload,
        "min_distinct_books": min_distinct_books,
        "max_timestamp_skew_seconds": max_timestamp_skew_seconds,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[
        :12
    ]
    return f"kalshi-sports-consensus-preflight-{digest}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
