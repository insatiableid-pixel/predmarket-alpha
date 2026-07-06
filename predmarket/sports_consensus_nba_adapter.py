"""Adapt NBA sharp-consensus odds into predmarket strict consensus rows."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from predmarket.sports_consensus_provider_policy import normalize_provider_id, provider_spec

NBA_TEAM_TO_ABBR = {
    "Atlanta Hawks": "ATL",
    "Boston Celtics": "BOS",
    "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW",
    "Houston Rockets": "HOU",
    "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC",
    "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}

NBA_ABBR_TO_TEAM = {abbr: team for team, abbr in NBA_TEAM_TO_ABBR.items()}
NBA_TEAM_ALIASES = {
    "la clippers": "Los Angeles Clippers",
    "la lakers": "Los Angeles Lakers",
    "ny knicks": "New York Knicks",
    "oklahoma city": "Oklahoma City Thunder",
    "philadelphia sixers": "Philadelphia 76ers",
    "phoenix suns": "Phoenix Suns",
    "portland trailblazers": "Portland Trail Blazers",
    "sa spurs": "San Antonio Spurs",
}

DEFAULT_ALLOWED_BOOKS = (
    "pinnacle",
    "circa",
    "bookmaker",
    "betcris",
    "betfair_exchange",
    "matchbook",
    "smarkets",
)


def build_nba_consensus_adapter(
    *,
    existing_reference: Mapping[str, Any] | None,
    base_kalshi_payload: Mapping[str, Any] | None,
    nba_kalshi_payload: Mapping[str, Any] | None,
    nba_odds_payload: Sequence[Mapping[str, Any]],
    nba_odds_meta: Mapping[str, Any] | None,
    existing_reference_path: Path | None = None,
    base_kalshi_path: Path | None = None,
    nba_kalshi_path: Path | None = None,
    nba_odds_path: Path | None = None,
    nba_odds_meta_path: Path | None = None,
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
        (nba_kalshi_payload or {}).get("created_at_utc")
        or (nba_kalshi_payload or {}).get("generated_utc")
        or (base_kalshi_payload or {}).get("created_at_utc")
        or (base_kalshi_payload or {}).get("generated_utc")
        or created_at
    )
    odds_capture_time = _parse_utc((nba_odds_meta or {}).get("created_at_utc")) or _parse_utc(
        created_at
    )
    nba_index = _index_nba_kalshi_events(
        nba_kalshi_payload or base_kalshi_payload or {},
        kalshi_capture_time=kalshi_capture_time,
    )
    nba_rows, skipped = _build_nba_reference_rows(
        nba_odds_payload,
        meta=nba_odds_meta or {},
        raw_path=nba_odds_path,
        kalshi_events=nba_index,
        capture_time=odds_capture_time,
        allowed_books=allowed,
        max_source_age_seconds=max_source_age_seconds,
        max_game_duration_seconds=max_game_duration_seconds,
    )
    merged_rows = _dedupe_reference_rows([*existing_rows, *nba_rows])
    combined_kalshi = _combined_kalshi_payload(
        base_kalshi_payload or {},
        nba_kalshi_payload or base_kalshi_payload or {},
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
            "payloads stay outside the repo. NBA rows are exact KXNBA adapters, not model probabilities."
        ),
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "raw_provider_payload_copied": False,
        "provider_api_calls": bool((nba_odds_meta or {}).get("provider_api_calls")),
        "policy": {
            **_mapping(existing_reference, "policy"),
            "probability_source": "timestamp_matched_sharp_no_vig_consensus",
            "nba_adapter": "basketball_nba_h2h_exact_kxnba_ticker",
            "allowed_nba_books": list(allowed),
            "matching_policy": "nba_team_pair_plus_start_time_against_exact_kxnba_event_sides",
            "max_source_age_seconds": float(max_source_age_seconds),
            "max_game_duration_seconds": float(max_game_duration_seconds),
        },
        "quality": {
            "reference_row_count": len(merged_rows),
            "existing_reference_row_count": len(existing_rows),
            "nba_reference_row_count": len(nba_rows),
            "unique_kalshi_ticker_count": len({row["kalshi_ticker"] for row in merged_rows}),
            "nba_unique_kalshi_ticker_count": len({row["kalshi_ticker"] for row in nba_rows}),
            "distinct_book_count": len({row["book_id"] for row in merged_rows}),
            "nba_distinct_book_count": len({row["book_id"] for row in nba_rows}),
            "nba_matched_event_count": len({row["event_ticker"] for row in nba_rows}),
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
            "nba_kalshi_json": str(nba_kalshi_path) if nba_kalshi_path else None,
            "nba_kalshi_sha256": _sha256(nba_kalshi_path),
            "nba_odds_json": str(nba_odds_path) if nba_odds_path else None,
            "nba_odds_sha256": _sha256(nba_odds_path),
            "nba_odds_meta_json": str(nba_odds_meta_path) if nba_odds_meta_path else None,
            "nba_odds_meta_sha256": _sha256(nba_odds_meta_path),
            "combined_kalshi_json": str(combined_kalshi_path) if combined_kalshi_path else None,
        },
        "rows": merged_rows,
    }
    status = _status(nba_rows=nba_rows, skipped=skipped, duplicate_ids=duplicate_reference_ids)
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
        "provider_api_calls": bool((nba_odds_meta or {}).get("provider_api_calls")),
        "paid_calls": False,
        "database_writes": False,
        "raw_provider_payload_copied": False,
        "safety": {
            "provider_api_calls": bool((nba_odds_meta or {}).get("provider_api_calls")),
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
        "provider_counts": dict(sorted(_provider_counts(nba_rows).items())),
        "sport_key_counts": dict(sorted(_sport_counts(nba_rows).items())),
    }
    return reference, combined_kalshi, report


def render_nba_consensus_adapter_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Sports Consensus NBA Adapter",
        "",
        f"- Status: `{report.get('status')}`",
        "- Mode: research-only",
        "- Execution enabled: `false`",
        "",
        "## Summary",
        "",
        f"- Existing reference rows: `{summary.get('existing_reference_row_count', 0)}`",
        f"- NBA reference rows: `{summary.get('nba_reference_row_count', 0)}`",
        f"- NBA unique Kalshi tickers: `{summary.get('nba_unique_kalshi_ticker_count', 0)}`",
        f"- NBA matched events: `{summary.get('nba_matched_event_count', 0)}`",
        f"- NBA distinct books: `{summary.get('nba_distinct_book_count', 0)}`",
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


def _build_nba_reference_rows(
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
        event_rows, event_skips = _nba_event_rows(
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


def _nba_event_rows(
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
    match, match_skip = _resolve_nba_event_match(
        event,
        kalshi_events=kalshi_events,
        max_game_duration_seconds=max_game_duration_seconds,
    )
    if match_skip is not None:
        return [], [match_skip]
    assert match is not None
    away = match["away"]
    home = match["home"]
    away_abbr = match["away_abbr"]
    home_abbr = match["home_abbr"]
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
        outcomes = _outcomes_by_name(market)
        if away not in outcomes or home not in outcomes:
            skipped.append(
                _skip(
                    event,
                    "missing_two_sided_h2h_outcomes",
                    f"{book_id} did not expose both NBA h2h teams.",
                )
            )
            continue
        for abbr, team, opponent in ((away_abbr, away, home), (home_abbr, home, away)):
            kalshi_row = kalshi_event["rows"].get(abbr)
            if not isinstance(kalshi_row, Mapping):
                skipped.append(
                    _skip(
                        event,
                        "missing_exact_nba_kalshi_side",
                        f"{event_ticker} missing side {abbr}.",
                    )
                )
                continue
            spec = provider_spec(book_id)
            rows.append(
                {
                    "reference_id": f"{event_ticker.lower()}-{abbr.lower()}-{book_id}",
                    "kalshi_ticker": kalshi_row["ticker"],
                    "side": "yes",
                    "book_id": book_id,
                    "sportsbook": book_id,
                    "source_type": spec.provider_kind if spec else "sportsbook",
                    "market_label": f"{team} moneyline vs {opponent}",
                    "capture_time_utc": _format_utc(capture_time),
                    "book_last_update_utc": _format_utc(last_update),
                    "source_snapshot": str(raw_path) if raw_path else None,
                    "source_snapshot_sha256": _sha256(raw_path),
                    "sport_key": str(
                        event.get("sport_key") or meta.get("sport_key") or "basketball_nba"
                    ),
                    "market_key": "h2h",
                    "market_type": "game_winner",
                    "event_id": event_id,
                    "event_ticker": event_ticker,
                    "team": team,
                    "opponent": opponent,
                    "commence_time_utc": _format_utc(commence),
                    "kalshi_event_start_utc": _format_utc(kalshi_event.get("expected_expiration")),
                    "event_match_delta_seconds": duration,
                    "provider_name": bookmaker.get("title"),
                    "provider_key": bookmaker.get("key"),
                    "exchange_liquidity_required_downstream": book_id
                    in {"betfair_exchange", "matchbook", "smarkets"},
                    "yes": {"american": outcomes[team]},
                    "no": {"american": outcomes[opponent]},
                }
            )
    if not rows:
        skipped.append(_skip(event, "no_allowed_nba_book_rows", "No allowed sharp book h2h rows."))
    return rows, skipped


def _resolve_nba_event_match(
    event: Mapping[str, Any],
    *,
    kalshi_events: Mapping[str, Mapping[str, Any]],
    max_game_duration_seconds: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    away = _canonical_team_name(event.get("away_team"))
    home = _canonical_team_name(event.get("home_team"))
    away_abbr = NBA_TEAM_TO_ABBR.get(away or "")
    home_abbr = NBA_TEAM_TO_ABBR.get(home or "")
    commence = _parse_utc(event.get("commence_time"))
    if not away or not home or not away_abbr or not home_abbr or commence is None:
        return None, _skip(
            event,
            "missing_team_or_commence_time",
            "Team abbreviation or commence_time unavailable.",
        )
    matches = []
    for event_ticker, kalshi_event in kalshi_events.items():
        if away_abbr not in kalshi_event.get("rows", {}) or home_abbr not in kalshi_event.get(
            "rows", {}
        ):
            continue
        duration = _event_duration_seconds(kalshi_event, commence)
        if duration is None or duration > max_game_duration_seconds:
            continue
        matches.append((duration, event_ticker, kalshi_event))
    if not matches:
        return None, _skip(
            event,
            "kalshi_event_not_matched",
            f"No KXNBA event matched {away} at {home}.",
        )
    duration, event_ticker, kalshi_event = sorted(matches, key=lambda item: item[0])[0]
    return {
        "away": away,
        "home": home,
        "away_abbr": away_abbr,
        "home_abbr": home_abbr,
        "commence": commence,
        "event_ticker": event_ticker,
        "kalshi_event": kalshi_event,
        "duration": duration,
    }, None


def _combined_kalshi_payload(
    base_payload: Mapping[str, Any],
    nba_payload: Mapping[str, Any],
    *,
    created_at: str | None,
) -> dict[str, Any]:
    combined: dict[str, dict[str, Any]] = {}
    for row in _kalshi_rows(base_payload):
        ticker = str(row.get("ticker") or row.get("contract_ticker") or row.get("market_id") or "")
        if ticker:
            combined[ticker] = dict(row)
    for row in _kalshi_rows(nba_payload):
        ticker = str(row.get("ticker") or row.get("contract_ticker") or "").strip()
        if not ticker.startswith("KXNBA"):
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
            "sport_key": "basketball_nba",
            "market_key": "h2h",
            "market_type": "game_winner",
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


def _index_nba_kalshi_events(
    payload: Mapping[str, Any], *, kalshi_capture_time: datetime | None
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _kalshi_rows(payload):
        ticker = str(row.get("ticker") or row.get("contract_ticker") or "")
        if not ticker.startswith("KXNBA"):
            continue
        event_ticker = str(row.get("event_ticker") or ticker.rsplit("-", 1)[0])
        abbr = _abbr_from_kalshi_row(row)
        if not event_ticker or not abbr:
            continue
        event = out.setdefault(
            event_ticker,
            {
                "rows": {},
                "expected_expiration": _parse_utc(row.get("expected_expiration_time")),
                "kalshi_capture_time": kalshi_capture_time,
            },
        )
        event["rows"][abbr] = dict(row)
    return out


def _abbr_from_kalshi_row(row: Mapping[str, Any]) -> str | None:
    ticker = str(row.get("ticker") or row.get("contract_ticker") or "")
    suffix = ticker.rsplit("-", 1)[-1].upper()
    if suffix in NBA_ABBR_TO_TEAM:
        return suffix
    side_text = str(row.get("yes_sub_title") or row.get("title") or "")
    return _team_abbr_from_text(side_text)


def _canonical_team_name(value: Any) -> str | None:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return None
    if text in NBA_TEAM_TO_ABBR:
        return text
    return NBA_TEAM_ALIASES.get(text.lower())


def _team_abbr_from_text(value: Any) -> str | None:
    text = str(value or "").lower()
    for team, abbr in NBA_TEAM_TO_ABBR.items():
        if team.lower() in text:
            return abbr
    for alias, team in NBA_TEAM_ALIASES.items():
        if alias in text:
            return NBA_TEAM_TO_ABBR.get(team)
    return None


def _event_duration_seconds(event: Mapping[str, Any], commence: datetime) -> float | None:
    expected = event.get("expected_expiration")
    if not isinstance(expected, datetime):
        return None
    delta = abs((expected - commence).total_seconds())
    if not math.isfinite(delta):
        return None
    return delta


def _h2h_market(bookmaker: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for market in bookmaker.get("markets") or []:
        if isinstance(market, Mapping) and market.get("key") == "h2h":
            return market
    return None


def _outcomes_by_name(market: Mapping[str, Any]) -> dict[str, int]:
    outcomes: dict[str, int] = {}
    for outcome in market.get("outcomes") or []:
        if not isinstance(outcome, Mapping):
            continue
        name = _canonical_team_name(outcome.get("name"))
        price = outcome.get("price")
        if name and isinstance(price, int | float):
            outcomes[name] = int(price)
    return outcomes


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
    nba_rows: Sequence[Mapping[str, Any]],
    skipped: Sequence[Mapping[str, Any]],
    duplicate_ids: Sequence[str],
) -> str:
    if duplicate_ids:
        return "sports_consensus_nba_adapter_blocked_duplicate_reference_ids"
    if nba_rows:
        return (
            "sports_consensus_nba_adapter_ready_with_warnings"
            if skipped
            else "sports_consensus_nba_adapter_ready"
        )
    return "sports_consensus_nba_adapter_blocked_no_nba_rows"


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


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stable_run_id(reference: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(reference, sort_keys=True, default=str).encode()).hexdigest()
    return f"kalshi-sports-consensus-nba-adapter-{digest[:12]}"


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
