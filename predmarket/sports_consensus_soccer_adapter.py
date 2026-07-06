"""Adapt World Cup soccer sharp-consensus odds into strict consensus rows."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from predmarket.sports_consensus_provider_policy import normalize_provider_id, provider_spec

SOCCER_TEAM_TO_ABBR = {
    "Argentina": "ARG",
    "Belgium": "BEL",
    "Brazil": "BRA",
    "Colombia": "COL",
    "Egypt": "EGY",
    "England": "ENG",
    "France": "FRA",
    "Mexico": "MEX",
    "Morocco": "MAR",
    "Norway": "NOR",
    "Portugal": "POR",
    "Spain": "ESP",
    "Switzerland": "SUI",
    "USA": "USA",
    "United States": "USA",
}

MONTH_ABBR = {
    1: "JAN",
    2: "FEB",
    3: "MAR",
    4: "APR",
    5: "MAY",
    6: "JUN",
    7: "JUL",
    8: "AUG",
    9: "SEP",
    10: "OCT",
    11: "NOV",
    12: "DEC",
}

DEFAULT_ALLOWED_BOOKS = (
    "pinnacle",
    "betcris",
    "betfair_exchange",
    "matchbook",
    "smarkets",
)


def build_soccer_consensus_adapter(
    *,
    existing_reference: Mapping[str, Any] | None,
    base_kalshi_payload: Mapping[str, Any] | None,
    soccer_kalshi_payload: Mapping[str, Any] | None,
    soccer_odds_payload: Sequence[Mapping[str, Any]],
    soccer_odds_meta: Mapping[str, Any] | None,
    existing_reference_path: Path | None = None,
    base_kalshi_path: Path | None = None,
    soccer_kalshi_path: Path | None = None,
    soccer_odds_path: Path | None = None,
    soccer_odds_meta_path: Path | None = None,
    combined_kalshi_path: Path | None = None,
    run_id: str | None = None,
    created_ts: float | None = None,
    allowed_books: Sequence[str] = DEFAULT_ALLOWED_BOOKS,
    max_source_age_seconds: float = 900.0,
    max_game_duration_seconds: float = 21_600.0,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return merged strict reference, combined Kalshi payload, and adapter report."""
    ts = float(created_ts or time.time())
    created_at = _format_utc(datetime.fromtimestamp(ts, UTC))
    allowed = tuple(normalize_provider_id(book) for book in allowed_books if book)
    existing_rows = _existing_reference_rows(existing_reference)
    kalshi_capture_time = _parse_utc(
        (soccer_kalshi_payload or {}).get("created_at_utc")
        or (soccer_kalshi_payload or {}).get("generated_utc")
        or created_at
    )
    odds_capture_time = _parse_utc((soccer_odds_meta or {}).get("created_at_utc")) or _parse_utc(
        created_at
    )
    soccer_index = _index_soccer_kalshi_events(
        soccer_kalshi_payload or {}, kalshi_capture_time=kalshi_capture_time
    )
    soccer_rows, skipped = _build_soccer_reference_rows(
        soccer_odds_payload,
        meta=soccer_odds_meta or {},
        raw_path=soccer_odds_path,
        kalshi_events=soccer_index,
        capture_time=odds_capture_time,
        allowed_books=allowed,
        max_source_age_seconds=max_source_age_seconds,
        max_game_duration_seconds=max_game_duration_seconds,
    )
    merged_rows = _dedupe_reference_rows([*existing_rows, *soccer_rows])
    combined_kalshi = _combined_kalshi_payload(
        base_kalshi_payload or {},
        soccer_kalshi_payload or {},
        created_at=_format_utc(kalshi_capture_time) or created_at,
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
            "payloads stay outside the repo. World Cup rows are exact KXWCGAME "
            "three-way adapters, not soccer handicap model probabilities."
        ),
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "raw_provider_payload_copied": False,
        "provider_api_calls": bool((soccer_odds_meta or {}).get("provider_api_calls")),
        "policy": {
            **_mapping(existing_reference, "policy"),
            "probability_source": "timestamp_matched_sharp_no_vig_consensus",
            "soccer_adapter": "soccer_fifa_world_cup_h2h_three_way_exact_kxwcgame_ticker",
            "allowed_soccer_books": list(allowed),
            "matching_policy": "world_cup_home_away_pair_plus_local_commence_date_exact_event_ticker",
            "three_way_policy": "normalize home_away_draw implied probabilities, then map selected outcome vs field",
            "max_source_age_seconds": float(max_source_age_seconds),
            "max_game_duration_seconds": float(max_game_duration_seconds),
        },
        "quality": {
            "reference_row_count": len(merged_rows),
            "existing_reference_row_count": len(existing_rows),
            "soccer_reference_row_count": len(soccer_rows),
            "unique_kalshi_ticker_count": len({row["kalshi_ticker"] for row in merged_rows}),
            "soccer_unique_kalshi_ticker_count": len({row["kalshi_ticker"] for row in soccer_rows}),
            "distinct_book_count": len({row["book_id"] for row in merged_rows}),
            "soccer_distinct_book_count": len({row["book_id"] for row in soccer_rows}),
            "soccer_matched_event_count": len({row["event_ticker"] for row in soccer_rows}),
            "duplicate_reference_id_count": len(duplicate_reference_ids),
            "skipped_count": len(skipped),
        },
        "inputs": {
            **_mapping(existing_reference, "inputs"),
            "existing_reference_json": str(existing_reference_path)
            if existing_reference_path
            else None,
            "existing_reference_sha256": _sha256(existing_reference_path),
            "base_kalshi_json": str(base_kalshi_path) if base_kalshi_path else None,
            "base_kalshi_sha256": _sha256(base_kalshi_path),
            "soccer_kalshi_json": str(soccer_kalshi_path) if soccer_kalshi_path else None,
            "soccer_kalshi_sha256": _sha256(soccer_kalshi_path),
            "soccer_odds_json": str(soccer_odds_path) if soccer_odds_path else None,
            "soccer_odds_sha256": _sha256(soccer_odds_path),
            "soccer_odds_meta_json": str(soccer_odds_meta_path) if soccer_odds_meta_path else None,
            "soccer_odds_meta_sha256": _sha256(soccer_odds_meta_path),
            "combined_kalshi_json": str(combined_kalshi_path) if combined_kalshi_path else None,
        },
        "rows": merged_rows,
    }
    status = _status(
        soccer_rows=soccer_rows, skipped=skipped, duplicate_ids=duplicate_reference_ids
    )
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
        "provider_api_calls": bool((soccer_odds_meta or {}).get("provider_api_calls")),
        "paid_calls": False,
        "database_writes": False,
        "raw_provider_payload_copied": False,
        "safety": {
            "provider_api_calls": bool((soccer_odds_meta or {}).get("provider_api_calls")),
            "paid_calls": False,
            "database_writes": False,
            "account_or_order_paths": False,
            "market_execution": False,
            "raw_provider_payload_copied": False,
            "api_key_printed": False,
        },
        "summary": reference["quality"],
        "inputs": reference["inputs"],
        "duplicate_reference_ids": duplicate_reference_ids,
        "skipped": skipped,
        "provider_counts": dict(sorted(_provider_counts(soccer_rows).items())),
        "sport_key_counts": dict(sorted(_sport_counts(soccer_rows).items())),
    }
    return reference, combined_kalshi, report


def render_soccer_consensus_adapter_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Sports Consensus Soccer Adapter",
        "",
        f"- Status: `{report.get('status')}`",
        "- Mode: research-only",
        "- Execution enabled: `false`",
        "",
        "## Summary",
        "",
        f"- Existing reference rows: `{summary.get('existing_reference_row_count', 0)}`",
        f"- Soccer reference rows: `{summary.get('soccer_reference_row_count', 0)}`",
        f"- Soccer unique Kalshi tickers: `{summary.get('soccer_unique_kalshi_ticker_count', 0)}`",
        f"- Soccer matched events: `{summary.get('soccer_matched_event_count', 0)}`",
        f"- Soccer distinct books: `{summary.get('soccer_distinct_book_count', 0)}`",
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
    if skipped:
        lines.extend(["", "## Skipped", ""])
        for row in skipped[:25]:
            lines.append(f"- `{row.get('reason')}`: {row.get('detail')}")
    lines.extend(
        [
            "",
            "> Adapter only. This artifact does not compute stake, authorize orders, or bypass OOS/FDR gates.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _build_soccer_reference_rows(
    odds_payload: Sequence[Mapping[str, Any]],
    *,
    meta: Mapping[str, Any],
    raw_path: Path | None,
    kalshi_events: Mapping[str, Mapping[str, Any]],
    capture_time: datetime | None,
    allowed_books: Sequence[str],
    max_source_age_seconds: float,
    max_game_duration_seconds: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for event in odds_payload:
        event_rows, event_skips = _soccer_event_rows(
            event,
            meta=meta,
            raw_path=raw_path,
            kalshi_events=kalshi_events,
            capture_time=capture_time,
            allowed_books=allowed_books,
            max_source_age_seconds=max_source_age_seconds,
            max_game_duration_seconds=max_game_duration_seconds,
        )
        rows.extend(event_rows)
        skipped.extend(event_skips)
    return rows, skipped


def _soccer_event_rows(
    event: Mapping[str, Any],
    *,
    meta: Mapping[str, Any],
    raw_path: Path | None,
    kalshi_events: Mapping[str, Mapping[str, Any]],
    capture_time: datetime | None,
    allowed_books: Sequence[str],
    max_source_age_seconds: float,
    max_game_duration_seconds: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    match, match_skip = _resolve_soccer_event_match(
        event,
        kalshi_events=kalshi_events,
        max_game_duration_seconds=max_game_duration_seconds,
    )
    if match_skip is not None:
        return [], [match_skip]
    assert match is not None
    home = match["home"]
    away = match["away"]
    home_abbr = match["home_abbr"]
    away_abbr = match["away_abbr"]
    commence = match["commence"]
    event_ticker = match["event_ticker"]
    kalshi_event = match["kalshi_event"]
    duration = match["duration"]
    event_id = str(event.get("id") or "").strip()

    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    allowed = set(allowed_books)
    for bookmaker in event.get("bookmakers") or []:
        if not isinstance(bookmaker, Mapping):
            continue
        book_id = normalize_provider_id(bookmaker.get("key") or bookmaker.get("title"))
        if allowed and book_id not in allowed:
            continue
        market = _h2h_market(bookmaker)
        if market is None:
            continue
        last_update = _parse_utc(market.get("last_update") or bookmaker.get("last_update"))
        if _source_age_seconds(capture_time, last_update) > max_source_age_seconds:
            skipped.append(
                _skip(
                    event,
                    "book_source_age_exceeds_policy",
                    f"{book_id} last_update too old for timestamp-matched consensus.",
                )
            )
            continue
        probabilities = _three_way_no_vig_probabilities(market, home=home, away=away)
        if probabilities is None:
            skipped.append(
                _skip(
                    event,
                    "missing_three_way_h2h_outcomes",
                    f"{book_id} did not expose home/away/draw h2h outcomes.",
                )
            )
            continue
        for code, label in ((home_abbr, home), (away_abbr, away), ("TIE", "Draw")):
            kalshi_row = kalshi_event["rows"].get(code)
            if not isinstance(kalshi_row, Mapping):
                skipped.append(
                    _skip(event, "missing_exact_soccer_kalshi_side", f"{event_ticker} {code}.")
                )
                continue
            selected_probability = probabilities[label]
            spec = provider_spec(book_id)
            rows.append(
                {
                    "reference_id": f"{event_ticker.lower()}-{code.lower()}-{book_id}",
                    "kalshi_ticker": kalshi_row["ticker"],
                    "side": "yes",
                    "book_id": book_id,
                    "sportsbook": book_id,
                    "source_type": spec.provider_kind if spec else "sportsbook",
                    "market_label": f"{label} regulation-time result in {home} vs {away}",
                    "capture_time_utc": _format_utc(capture_time),
                    "book_last_update_utc": _format_utc(last_update),
                    "source_snapshot": str(raw_path) if raw_path else None,
                    "source_snapshot_sha256": _sha256(raw_path),
                    "sport_key": str(
                        event.get("sport_key") or meta.get("sport_key") or "soccer_fifa_world_cup"
                    ),
                    "market_key": "h2h",
                    "market_type": "regulation_time_result",
                    "event_id": event_id,
                    "event_ticker": event_ticker,
                    "team": label,
                    "opponent": _opponent_label(label, home=home, away=away),
                    "commence_time_utc": _format_utc(commence),
                    "kalshi_event_start_utc": _format_utc(kalshi_event.get("expected_expiration")),
                    "event_match_delta_seconds": duration,
                    "provider_name": bookmaker.get("title"),
                    "provider_key": bookmaker.get("key"),
                    "three_way_no_vig": True,
                    "exchange_liquidity_required_downstream": book_id
                    in {"betfair_exchange", "matchbook", "smarkets"},
                    "yes": {"probability": selected_probability},
                    "no": {"probability": 1.0 - selected_probability},
                    "raw_three_way_implied": probabilities["_raw_implied"],
                    "raw_three_way_overround": probabilities["_overround"],
                }
            )
    if not rows:
        skipped.append(
            _skip(event, "no_allowed_soccer_book_rows", "No allowed sharp book h2h rows.")
        )
    return rows, skipped


def _resolve_soccer_event_match(
    event: Mapping[str, Any],
    *,
    kalshi_events: Mapping[str, Mapping[str, Any]],
    max_game_duration_seconds: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    home = str(event.get("home_team") or "").strip()
    away = str(event.get("away_team") or "").strip()
    home_abbr = SOCCER_TEAM_TO_ABBR.get(home)
    away_abbr = SOCCER_TEAM_TO_ABBR.get(away)
    commence = _parse_utc(event.get("commence_time"))
    if not home_abbr or not away_abbr or commence is None:
        return None, _skip(
            event,
            "missing_team_or_commence_time",
            "Team abbreviation or commence_time unavailable.",
        )
    event_ticker = _soccer_event_ticker(home_abbr=home_abbr, away_abbr=away_abbr, commence=commence)
    kalshi_event = kalshi_events.get(event_ticker)
    if not isinstance(kalshi_event, Mapping):
        return None, _skip(
            event,
            "kalshi_event_not_matched",
            f"No KXWCGAME event matched {home} vs {away}.",
        )
    duration = _event_duration_seconds(kalshi_event, commence)
    if duration is None or duration > max_game_duration_seconds:
        return None, _skip(
            event,
            "kalshi_event_time_delta_exceeds_policy",
            f"{event_ticker} start/expiration delta unavailable or above policy.",
        )
    return {
        "home": home,
        "away": away,
        "home_abbr": home_abbr,
        "away_abbr": away_abbr,
        "commence": commence,
        "event_ticker": event_ticker,
        "kalshi_event": kalshi_event,
        "duration": duration,
    }, None


def _three_way_no_vig_probabilities(
    market: Mapping[str, Any], *, home: str, away: str
) -> dict[str, Any] | None:
    raw: dict[str, float] = {}
    for outcome in market.get("outcomes") or []:
        if not isinstance(outcome, Mapping):
            continue
        name = str(outcome.get("name") or "").strip()
        if name not in {home, away, "Draw"}:
            continue
        implied = _american_implied(outcome.get("price"))
        if implied is not None:
            raw[name] = implied
    if set(raw) != {home, away, "Draw"}:
        return None
    total = sum(raw.values())
    if not math.isfinite(total) or total <= 0.0:
        return None
    return {
        home: raw[home] / total,
        away: raw[away] / total,
        "Draw": raw["Draw"] / total,
        "_raw_implied": raw,
        "_overround": total - 1.0,
    }


def _combined_kalshi_payload(
    base_payload: Mapping[str, Any],
    soccer_payload: Mapping[str, Any],
    *,
    created_at: str | None,
) -> dict[str, Any]:
    combined: dict[str, dict[str, Any]] = {}
    for row in _kalshi_rows(base_payload):
        ticker = str(row.get("ticker") or row.get("contract_ticker") or row.get("market_id") or "")
        if ticker:
            combined[ticker] = dict(row)
    for row in _kalshi_rows(soccer_payload):
        ticker = str(row.get("ticker") or row.get("contract_ticker") or "").strip()
        if not ticker.startswith("KXWCGAME-"):
            continue
        combined[ticker] = {
            "ticker": ticker,
            "contract_ticker": ticker,
            "event_ticker": row.get("event_ticker"),
            "title": row.get("title"),
            "yes_bid": _optional_float(row.get("yes_bid") or row.get("yes_bid_dollars")),
            "yes_ask": _optional_float(row.get("yes_ask") or row.get("yes_ask_dollars")),
            "last_price": _optional_float(row.get("last_price") or row.get("last_price_dollars")),
            "volume": _optional_float(row.get("volume") or row.get("volume_fp")),
            "open_interest": _optional_float(
                row.get("open_interest") or row.get("open_interest_fp")
            ),
            "close_time": row.get("close_time"),
            "expected_expiration_time": row.get("expected_expiration_time"),
            "observed_utc": created_at,
            "sport_key": "soccer_fifa_world_cup",
            "market_key": "h2h",
            "market_type": "regulation_time_result",
            "source": "kalshi_public_api",
            "side": row.get("yes_sub_title"),
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
        "candidates": sorted(combined.values(), key=lambda item: str(item.get("ticker"))),
    }


def _index_soccer_kalshi_events(
    payload: Mapping[str, Any], *, kalshi_capture_time: datetime | None
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _kalshi_rows(payload):
        ticker = str(row.get("ticker") or row.get("contract_ticker") or "")
        event_ticker = str(row.get("event_ticker") or "")
        if not ticker.startswith("KXWCGAME-") or not event_ticker:
            continue
        suffix = ticker.rsplit("-", 1)[-1]
        event = out.setdefault(
            event_ticker,
            {
                "rows": {},
                "expected_expiration": _parse_utc(row.get("expected_expiration_time")),
                "kalshi_capture_time": kalshi_capture_time,
            },
        )
        event["rows"][suffix] = dict(row)
    return out


def _soccer_event_ticker(*, home_abbr: str, away_abbr: str, commence: datetime) -> str:
    local = commence.astimezone(ZoneInfo("America/New_York"))
    stamp = f"{local.year % 100:02d}{MONTH_ABBR[local.month]}{local.day:02d}"
    return f"KXWCGAME-{stamp}{home_abbr}{away_abbr}"


def _event_duration_seconds(event: Mapping[str, Any], commence: datetime) -> float | None:
    expected = event.get("expected_expiration")
    if not isinstance(expected, datetime):
        return None
    delta = (expected - commence).total_seconds()
    if not math.isfinite(delta) or delta < 0:
        return None
    return delta


def _h2h_market(bookmaker: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for market in bookmaker.get("markets") or []:
        if isinstance(market, Mapping) and market.get("key") == "h2h":
            return market
    return None


def _opponent_label(label: str, *, home: str, away: str) -> str:
    if label == "Draw":
        return f"{home}/{away}"
    return away if label == home else home


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
    soccer_rows: Sequence[Mapping[str, Any]],
    skipped: Sequence[Mapping[str, Any]],
    duplicate_ids: Sequence[str],
) -> str:
    if duplicate_ids:
        return "sports_consensus_soccer_adapter_blocked_duplicate_reference_ids"
    if soccer_rows:
        return (
            "sports_consensus_soccer_adapter_ready_with_warnings"
            if skipped
            else "sports_consensus_soccer_adapter_ready"
        )
    return "sports_consensus_soccer_adapter_blocked_no_soccer_rows"


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


def _skip(event: Mapping[str, Any], reason: str, detail: Any) -> dict[str, Any]:
    return {
        "reason": reason,
        "event_id": event.get("id"),
        "away_team": event.get("away_team"),
        "home_team": event.get("home_team"),
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


def _source_age_seconds(capture_time: datetime | None, source_time: datetime | None) -> float:
    if capture_time is None or source_time is None:
        return math.inf
    return max(0.0, (capture_time - source_time).total_seconds())


def _american_implied(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if price == 0.0 or not math.isfinite(price):
        return None
    if price > 0:
        return 100.0 / (price + 100.0)
    return abs(price) / (abs(price) + 100.0)


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stable_run_id(reference: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(reference, sort_keys=True, default=str).encode()).hexdigest()
    return f"kalshi-sports-consensus-soccer-adapter-{digest[:12]}"


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
