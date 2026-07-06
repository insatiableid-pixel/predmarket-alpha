"""Adapt ATP donor sharp-consensus artifacts into predmarket strict consensus rows."""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from predmarket.sports_consensus_provider_policy import normalize_provider_id

DEFAULT_ALLOWED_BOOKS = (
    "pinnacle",
    "betfair_exchange",
    "matchbook",
    "smarkets",
)


def build_atp_donor_consensus_adapter(
    *,
    existing_reference: Mapping[str, Any] | None,
    base_kalshi_payload: Mapping[str, Any] | None,
    atp_book_rows: Sequence[Mapping[str, Any]],
    atp_kalshi_rows: Sequence[Mapping[str, Any]],
    atp_book_path: Path | None = None,
    atp_kalshi_path: Path | None = None,
    existing_reference_path: Path | None = None,
    combined_kalshi_path: Path | None = None,
    run_id: str | None = None,
    created_ts: float | None = None,
    max_book_overround: float = 0.08,
    provider_api_calls: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return merged strict reference, combined Kalshi payload, and adapter report."""
    ts = float(created_ts or time.time())
    created_at = _format_utc(datetime.fromtimestamp(ts, UTC))
    existing_rows = _existing_reference_rows(existing_reference)
    atp_index = _index_atp_kalshi(atp_kalshi_rows)
    atp_rows, skipped = _build_atp_reference_rows(
        atp_book_rows,
        atp_index=atp_index,
        atp_book_path=atp_book_path,
        max_book_overround=max_book_overround,
    )
    merged_rows = _dedupe_reference_rows([*existing_rows, *atp_rows])
    combined_kalshi = _combined_kalshi_payload(
        base_kalshi_payload or {},
        atp_kalshi_rows,
        created_at=created_at,
    )
    duplicate_reference_ids = _duplicates(row["reference_id"] for row in merged_rows)
    reference = {
        **{
            key: value
            for key, value in dict(existing_reference or {}).items()
            if key not in {"rows", "quality", "inputs", "policy", "created_at_utc", "source_note"}
        },
        "schema_version": 1,
        "created_at_utc": created_at,
        "source_note": (
            "Derived timestamp-matched sports no-vig consensus reference. Raw provider "
            "payloads stay outside the repo. ATP donor rows are strict-schema adapters, "
            "not model probabilities."
        ),
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "raw_provider_payload_copied": False,
        "provider_api_calls": bool(provider_api_calls),
        "policy": {
            **_mapping(existing_reference, "policy"),
            "probability_source": "timestamp_matched_sharp_no_vig_consensus",
            "atp_donor_adapter": "tennis_match_winner_h2h_exact_ticker",
            "sharp_provider_policy": "pinnacle_and_liquid_exchange_rows_allowed",
            "soft_book_policy": "comparison_only_not_anchor",
        },
        "quality": {
            "reference_row_count": len(merged_rows),
            "existing_reference_row_count": len(existing_rows),
            "atp_reference_row_count": len(atp_rows),
            "unique_kalshi_ticker_count": len({row["kalshi_ticker"] for row in merged_rows}),
            "atp_unique_kalshi_ticker_count": len({row["kalshi_ticker"] for row in atp_rows}),
            "distinct_book_count": len({row["book_id"] for row in merged_rows}),
            "atp_distinct_book_count": len({row["book_id"] for row in atp_rows}),
            "duplicate_reference_id_count": len(duplicate_reference_ids),
            "skipped_count": len(skipped),
        },
        "inputs": {
            **_mapping(existing_reference, "inputs"),
            "existing_reference_json": str(existing_reference_path)
            if existing_reference_path
            else None,
            "existing_reference_sha256": _sha256(existing_reference_path),
            "atp_book_jsonl": str(atp_book_path) if atp_book_path else None,
            "atp_book_sha256": _sha256(atp_book_path),
            "atp_kalshi_jsonl": str(atp_kalshi_path) if atp_kalshi_path else None,
            "atp_kalshi_sha256": _sha256(atp_kalshi_path),
            "combined_kalshi_json": str(combined_kalshi_path) if combined_kalshi_path else None,
        },
        "rows": merged_rows,
    }
    status = _status(atp_rows=atp_rows, skipped=skipped, duplicate_ids=duplicate_reference_ids)
    report = {
        "schema_version": 1,
        "run_id": run_id or _stable_run_id(reference),
        "created_ts": ts,
        "created_at_utc": created_at,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "provider_api_calls": bool(provider_api_calls),
        "paid_calls": False,
        "database_writes": False,
        "raw_provider_payload_copied": False,
        "safety": {
            "provider_api_calls": bool(provider_api_calls),
            "paid_calls": False,
            "database_writes": False,
            "account_or_order_paths": False,
            "market_execution": False,
            "raw_provider_payload_copied": False,
        },
        "summary": reference["quality"],
        "inputs": reference["inputs"],
        "duplicate_reference_ids": duplicate_reference_ids,
        "skipped": skipped,
        "provider_counts": dict(sorted(_provider_counts(atp_rows).items())),
        "sport_key_counts": dict(sorted(_sport_counts(atp_rows).items())),
    }
    return reference, combined_kalshi, report


def build_atp_kalshi_rows_from_payload(
    kalshi_payload: Mapping[str, Any],
    *,
    observed_at: str | None = None,
) -> list[dict[str, Any]]:
    """Extract current KXATPMATCH match-winner rows from a Kalshi universe payload."""
    fallback_observed = (
        observed_at
        or str(
            kalshi_payload.get("observed_utc")
            or kalshi_payload.get("capture_time_utc")
            or kalshi_payload.get("created_at_utc")
            or kalshi_payload.get("generated_utc")
            or ""
        ).strip()
        or None
    )
    rows: list[dict[str, Any]] = []
    for row in _kalshi_rows(kalshi_payload):
        ticker = str(row.get("ticker") or row.get("contract_ticker") or "").strip()
        event_id = str(row.get("event_ticker") or "").strip()
        series = str(row.get("series_ticker") or "").strip()
        if not ticker.startswith("KXATPMATCH-") or not event_id.startswith("KXATPMATCH-"):
            continue
        if series and series != "KXATPMATCH":
            continue
        side = str(row.get("side") or "").strip() or _selected_player_from_title(row.get("title"))
        if not side:
            continue
        close_time = (
            row.get("expected_expiration_time")
            or row.get("expected_expiration_utc")
            or row.get("close_time")
            or row.get("expiration_time")
        )
        rows.append(
            {
                "close_time": close_time,
                "event_id": event_id,
                "last_price": row.get("last_price"),
                "market_ticker": ticker,
                "market_type": "match_winner",
                "observed_at": row.get("observed_utc")
                or row.get("capture_time_utc")
                or row.get("captured_at_utc")
                or fallback_observed,
                "open_interest": row.get("open_interest"),
                "side": side,
                "source": row.get("source") or "kalshi_universe_scan",
                "sport": "tennis",
                "volume": row.get("volume"),
                "yes_ask": row.get("yes_ask"),
                "yes_bid": row.get("yes_bid"),
            }
        )
    return rows


def build_atp_book_rows_from_odds_api(
    odds_payload: Sequence[Mapping[str, Any]],
    *,
    atp_kalshi_rows: Sequence[Mapping[str, Any]],
    odds_meta: Mapping[str, Any] | None = None,
    raw_path: Path | None = None,
    allowed_books: Sequence[str] = DEFAULT_ALLOWED_BOOKS,
    max_source_age_seconds: float = 900.0,
    max_game_duration_seconds: float = 21_600.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert current The Odds API tennis h2h payloads into ATP donor row shape."""
    allowed = {normalize_provider_id(book) for book in allowed_books if book}
    meta = odds_meta or {}
    capture_time = _parse_utc(meta.get("created_at_utc")) or datetime.now(UTC)
    odds_format = str(meta.get("odds_format") or "american").strip().lower()
    events = _index_atp_match_events(atp_kalshi_rows)
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for event in odds_payload:
        match, skip = _resolve_atp_event_match(
            event,
            events=events,
            max_game_duration_seconds=max_game_duration_seconds,
        )
        if skip is not None:
            skipped.append(skip)
            continue
        assert match is not None
        for bookmaker in event.get("bookmakers") or []:
            if not isinstance(bookmaker, Mapping):
                continue
            provider_id = normalize_provider_id(bookmaker.get("key") or bookmaker.get("title"))
            if allowed and provider_id not in allowed:
                continue
            market = _h2h_market(bookmaker)
            if market is None:
                continue
            last_update = _parse_utc(market.get("last_update") or bookmaker.get("last_update"))
            if (
                last_update is not None
                and abs((capture_time - last_update).total_seconds()) > max_source_age_seconds
            ):
                skipped.append(
                    _skip(
                        str(event.get("id") or ""),
                        "provider_quote_stale",
                        provider_id,
                        _format_utc(last_update),
                    )
                )
                continue
            outcome_rows = _atp_outcomes_by_player_key(market, odds_format=odds_format)
            missing = sorted(set(match["side_keys"]) - set(outcome_rows))
            if missing:
                skipped.append(
                    _skip(
                        str(event.get("id") or ""),
                        "provider_outcomes_do_not_match_atp_sides",
                        provider_id,
                        ",".join(missing),
                    )
                )
                continue
            implied_sum = sum(1.0 / outcome_rows[key]["decimal_odds"] for key in match["side_keys"])
            for side_key in match["side_keys"]:
                side = match["side_names"][side_key]
                opponent_key = next(key for key in match["side_keys"] if key != side_key)
                quote = outcome_rows[side_key]
                opponent_quote = outcome_rows[opponent_key]
                rows.append(
                    {
                        "away_team": event.get("away_team"),
                        "commence_time": _format_utc(_parse_utc(event.get("commence_time"))),
                        "decimal_odds": quote["decimal_odds"],
                        "event_id": match["event_id"],
                        "home_team": event.get("home_team"),
                        "market_type": "match_winner",
                        "observed_at": _format_utc(last_update or capture_time),
                        "provider": bookmaker.get("title") or bookmaker.get("key"),
                        "provider_implied_sum": implied_sum,
                        "provider_key": provider_id,
                        "side": side,
                        "source": "the_odds_api_current",
                        "source_event_id": event.get("id"),
                        "source_snapshot": str(raw_path) if raw_path else None,
                        "sport": "tennis",
                        "yes": {"decimal": quote["decimal_odds"]},
                        "no": {"decimal": opponent_quote["decimal_odds"]},
                    }
                )
    return rows, skipped


def render_atp_donor_adapter_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Sports Consensus ATP Donor Adapter",
        "",
        f"- Status: `{report.get('status')}`",
        "- Mode: research-only",
        "- Execution enabled: `false`",
        "- Provider/API calls: `false`",
        "",
        "## Summary",
        "",
        f"- Existing reference rows: `{summary.get('existing_reference_row_count', 0)}`",
        f"- ATP reference rows: `{summary.get('atp_reference_row_count', 0)}`",
        f"- ATP unique Kalshi tickers: `{summary.get('atp_unique_kalshi_ticker_count', 0)}`",
        f"- ATP distinct books: `{summary.get('atp_distinct_book_count', 0)}`",
        f"- Merged reference rows: `{summary.get('reference_row_count', 0)}`",
        f"- Skipped: `{summary.get('skipped_count', 0)}`",
        "",
        "## Provider Counts",
        "",
    ]
    providers = report.get("provider_counts", {})
    if isinstance(providers, Mapping):
        for provider_id, count in providers.items():
            lines.append(f"- `{provider_id}`: `{count}`")
    skipped = [row for row in report.get("skipped", []) if isinstance(row, Mapping)]
    conversion_skipped = [
        row for row in report.get("conversion_skipped", []) if isinstance(row, Mapping)
    ]
    if skipped:
        lines.extend(["", "## Skipped", ""])
        for row in skipped[:25]:
            lines.append(f"- `{row.get('reason')}`: {row.get('detail')}")
    if conversion_skipped:
        lines.extend(["", "## Conversion Skipped", ""])
        for row in conversion_skipped[:25]:
            lines.append(f"- `{row.get('reason')}`: {row.get('detail')}")
    lines.extend(
        [
            "",
            "> Adapter only. This artifact does not compute stake, authorize orders, or bypass OOS/FDR gates.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _build_atp_reference_rows(
    book_rows: Sequence[Mapping[str, Any]],
    *,
    atp_index: Mapping[str, Mapping[str, Any]],
    atp_book_path: Path | None,
    max_book_overround: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_event_provider: dict[tuple[str, str], dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in book_rows:
        event_id = str(row.get("event_id") or "").strip()
        provider_id = normalize_provider_id(row.get("provider_key") or row.get("provider"))
        side = str(row.get("side") or "").strip()
        if event_id and provider_id and side:
            by_event_provider[(event_id, provider_id)][side] = row

    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for (event_id, provider_id), side_rows in sorted(by_event_provider.items()):
        if len(side_rows) != 2:
            skipped.append(
                _skip(event_id, "incomplete_two_sided_provider_quote", provider_id, len(side_rows))
            )
            continue
        implied_sum = _provider_implied_sum(side_rows.values())
        if implied_sum is not None and implied_sum - 1.0 > max_book_overround:
            skipped.append(
                _skip(
                    event_id,
                    "provider_overround_exceeds_policy",
                    provider_id,
                    implied_sum,
                )
            )
            continue
        for side_name, quote in sorted(side_rows.items()):
            opponent_name = next(name for name in side_rows if name != side_name)
            kalshi = atp_index.get(_atp_key(event_id, side_name))
            if kalshi is None:
                skipped.append(
                    {
                        "reason": "missing_exact_atp_kalshi_ticker",
                        "event_id": event_id,
                        "provider_id": provider_id,
                        "side": side_name,
                        "detail": "ATP donor Kalshi snapshot did not contain this exact player side.",
                    }
                )
                continue
            rows.append(
                {
                    "reference_id": f"{event_id.lower()}-{_slug(side_name)}-{provider_id}",
                    "kalshi_ticker": kalshi["ticker"],
                    "side": "yes",
                    "book_id": provider_id,
                    "sportsbook": provider_id,
                    "source_type": "sportsbook" if provider_id in {"pinnacle"} else "exchange",
                    "market_label": f"{side_name} match winner vs {opponent_name}",
                    "capture_time_utc": _format_utc(_parse_utc(quote.get("observed_at"))),
                    "book_last_update_utc": _format_utc(_parse_utc(quote.get("observed_at"))),
                    "source_snapshot": str(atp_book_path) if atp_book_path else None,
                    "source_snapshot_sha256": _sha256(atp_book_path),
                    "sport_key": str(quote.get("sport") or "tennis"),
                    "market_key": "h2h",
                    "market_type": str(quote.get("market_type") or "match_winner"),
                    "event_id": event_id,
                    "event_ticker": event_id,
                    "team": side_name,
                    "opponent": opponent_name,
                    "commence_time_utc": _format_utc(_parse_utc(quote.get("commence_time"))),
                    "kalshi_event_start_utc": _format_utc(_parse_utc(quote.get("commence_time"))),
                    "event_match_delta_seconds": 0.0,
                    "provider_name": quote.get("provider"),
                    "provider_key": quote.get("provider_key"),
                    "exchange_liquidity_required_downstream": provider_id
                    in {"betfair_exchange", "matchbook", "smarkets"},
                    "yes": {"decimal": quote.get("decimal_odds")},
                    "no": {"decimal": side_rows[opponent_name].get("decimal_odds")},
                }
            )
    return rows, skipped


def _combined_kalshi_payload(
    base_payload: Mapping[str, Any],
    atp_kalshi_rows: Sequence[Mapping[str, Any]],
    *,
    created_at: str,
) -> dict[str, Any]:
    base_rows = _kalshi_rows(base_payload)
    combined: dict[str, dict[str, Any]] = {}
    for row in base_rows:
        ticker = str(row.get("ticker") or row.get("contract_ticker") or row.get("market_id") or "")
        if ticker:
            combined[ticker] = dict(row)
    for row in atp_kalshi_rows:
        ticker = str(row.get("market_ticker") or row.get("ticker") or "").strip()
        if not ticker:
            continue
        combined[ticker] = {
            "ticker": ticker,
            "contract_ticker": ticker,
            "event_ticker": row.get("event_id"),
            "title": f"{row.get('side')} match winner",
            "yes_bid": row.get("yes_bid"),
            "yes_ask": row.get("yes_ask"),
            "last_price": row.get("last_price"),
            "volume": row.get("volume"),
            "open_interest": row.get("open_interest"),
            "close_time": row.get("close_time"),
            "observed_utc": _format_utc(_parse_utc(row.get("observed_at"))),
            "sport_key": row.get("sport"),
            "market_key": "h2h",
            "market_type": row.get("market_type"),
            "source": row.get("source"),
            "side": row.get("side"),
        }
    return {
        "schema_version": 1,
        "created_at_utc": created_at,
        "generated_utc": created_at,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "provider_api_calls": False,
        "raw_provider_payload_copied": False,
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
            "provider_api_calls": False,
            "paid_calls": False,
        },
        "candidates": sorted(combined.values(), key=lambda row: str(row.get("ticker"))),
    }


def _index_atp_kalshi(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        event_id = str(row.get("event_id") or "").strip()
        side = str(row.get("side") or "").strip()
        ticker = str(row.get("market_ticker") or row.get("ticker") or "").strip()
        if event_id and side and ticker:
            out[_atp_key(event_id, side)] = {"ticker": ticker, **dict(row)}
            out[_atp_key(event_id, _player_key(side))] = {"ticker": ticker, **dict(row)}
    return out


def _index_atp_match_events(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    events: dict[str, dict[str, Any]] = {}
    for row in rows:
        event_id = str(row.get("event_id") or "").strip()
        side = str(row.get("side") or "").strip()
        ticker = str(row.get("market_ticker") or row.get("ticker") or "").strip()
        if not event_id.startswith("KXATPMATCH-") or not side or not ticker:
            continue
        event = events.setdefault(
            event_id,
            {
                "event_id": event_id,
                "side_names": {},
                "side_keys": [],
                "commence": _parse_utc(row.get("close_time")),
            },
        )
        key = _player_key(side)
        if key and key not in event["side_names"]:
            event["side_names"][key] = side
            event["side_keys"].append(key)
        if event.get("commence") is None:
            event["commence"] = _parse_utc(row.get("close_time"))
    return {key: value for key, value in events.items() if len(value["side_keys"]) == 2}


def _existing_reference_rows(reference: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(reference, Mapping):
        return []
    rows = reference.get("rows")
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _dedupe_reference_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        reference_id = str(row.get("reference_id") or "").strip()
        if reference_id:
            out[reference_id] = dict(row)
    return [out[key] for key in sorted(out)]


def _kalshi_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in ("all_scored", "candidates", "markets", "rows", "top_50"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, Mapping)]
    return []


def _resolve_atp_event_match(
    event: Mapping[str, Any],
    *,
    events: Mapping[str, Mapping[str, Any]],
    max_game_duration_seconds: float,
) -> tuple[Mapping[str, Any] | None, dict[str, Any] | None]:
    away = str(event.get("away_team") or "").strip()
    home = str(event.get("home_team") or "").strip()
    commence = _parse_utc(event.get("commence_time"))
    event_side_keys = {_player_key(away), _player_key(home)}
    if len(event_side_keys) != 2 or "" in event_side_keys:
        return None, _skip(
            str(event.get("id") or ""),
            "missing_atp_teams",
            "the_odds_api",
            "ATP event missing two named sides.",
        )
    matches: list[tuple[float, str, Mapping[str, Any]]] = []
    for event_id, kalshi_event in events.items():
        side_keys = set(kalshi_event.get("side_keys") or [])
        if side_keys != event_side_keys:
            continue
        kalshi_commence = kalshi_event.get("commence")
        delta = 0.0
        if isinstance(commence, datetime) and isinstance(kalshi_commence, datetime):
            delta = abs((kalshi_commence - commence).total_seconds())
            if delta > max_game_duration_seconds:
                continue
        matches.append((delta, event_id, kalshi_event))
    if not matches:
        return None, _skip(
            str(event.get("id") or ""),
            "missing_exact_atp_kalshi_event",
            "the_odds_api",
            f"No current KXATPMATCH event matched {away} vs {home}.",
        )
    matches.sort(key=lambda item: (item[0], item[1]))
    return matches[0][2], None


def _h2h_market(bookmaker: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for market in bookmaker.get("markets") or []:
        if isinstance(market, Mapping) and str(market.get("key") or "").lower() == "h2h":
            return market
    return None


def _atp_outcomes_by_player_key(
    market: Mapping[str, Any],
    *,
    odds_format: str,
) -> dict[str, dict[str, Any]]:
    outcomes: dict[str, dict[str, Any]] = {}
    for outcome in market.get("outcomes") or []:
        if not isinstance(outcome, Mapping):
            continue
        name = str(outcome.get("name") or "").strip()
        key = _player_key(name)
        decimal = _decimal_odds(outcome.get("price"), odds_format=odds_format)
        if key and decimal is not None:
            outcomes[key] = {"name": name, "decimal_odds": decimal}
    return outcomes


def _decimal_odds(value: Any, *, odds_format: str) -> float | None:
    numeric = _optional_float(value)
    if numeric is None:
        return None
    if odds_format == "decimal":
        return numeric if numeric > 1.0 else None
    if odds_format == "american" or numeric < 0 or numeric >= 20:
        if numeric == 0:
            return None
        if numeric > 0:
            return 1.0 + numeric / 100.0
        return 1.0 + 100.0 / abs(numeric)
    return numeric if numeric > 1.0 else None


def _provider_implied_sum(rows: Sequence[Mapping[str, Any]]) -> float | None:
    probs = []
    for row in rows:
        value = _optional_float(row.get("decimal_odds"))
        if value is None or value <= 1.0:
            return None
        probs.append(1.0 / value)
    return sum(probs) if probs else None


def _provider_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("book_id") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _sport_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("sport_key") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _status(
    *,
    atp_rows: Sequence[Mapping[str, Any]],
    skipped: Sequence[Mapping[str, Any]],
    duplicate_ids: Sequence[str],
) -> str:
    if duplicate_ids:
        return "sports_consensus_atp_donor_adapter_blocked_duplicate_reference_ids"
    if atp_rows:
        return (
            "sports_consensus_atp_donor_adapter_ready_with_warnings"
            if skipped
            else "sports_consensus_atp_donor_adapter_ready"
        )
    return "sports_consensus_atp_donor_adapter_blocked_no_atp_rows"


def _mapping(payload: Mapping[str, Any] | None, key: str) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    value = payload.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def _duplicates(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        else:
            seen.add(value)
    return sorted(duplicates)


def _skip(event_id: str, reason: str, provider_id: str, detail: Any) -> dict[str, Any]:
    return {
        "reason": reason,
        "event_id": event_id,
        "provider_id": provider_id,
        "detail": str(detail),
    }


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


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _atp_key(event_id: str, side: str) -> str:
    return f"{event_id.strip()}::{side.strip().casefold()}"


def _player_key(value: Any) -> str:
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())


def _selected_player_from_title(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text.lower().startswith("will "):
        return None
    body = text[5:]
    marker = " win "
    index = body.lower().find(marker)
    if index < 0:
        return None
    return body[:index].strip() or None


def _slug(value: Any) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value)).strip("-")


def _stable_run_id(reference: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(reference, sort_keys=True, default=str).encode()).hexdigest()
    return f"kalshi-sports-consensus-atp-donor-adapter-{digest[:12]}"


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
