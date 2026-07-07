"""Build a review-only Type 2 sportsbook reference from local MLB snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from predmarket.shared_helpers import manual_drop_path

TEAM_TO_ABBR = {
    "Arizona Diamondbacks": "ARI",
    "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC",
    "Chicago White Sox": "CWS",
    "Cincinnati Reds": "CIN",
    "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL",
    "Detroit Tigers": "DET",
    "Houston Astros": "HOU",
    "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA",
    "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",
    "New York Mets": "NYM",
    "New York Yankees": "NYY",
    "Athletics": "ATH",
    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SD",
    "San Francisco Giants": "SF",
    "Seattle Mariners": "SEA",
    "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TB",
    "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSH",
}

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

EVENT_RE = re.compile(
    r"^KXMLBGAME-(?P<year>\d{2})(?P<month>[A-Z]{3})(?P<day>\d{2})(?P<hour>\d{2})(?P<minute>\d{2})(?P<teams>[A-Z]+)$"
)


@dataclass(frozen=True)
class Type2ReferenceBuilderArtifacts:
    report: dict[str, Any]
    reference: dict[str, Any]
    report_json_path: Path
    report_markdown_path: Path
    reference_json_path: Path


def build_type2_reference(
    odds_payload: Sequence[Mapping[str, Any]],
    odds_meta: Mapping[str, Any],
    kalshi_payload: Mapping[str, Any],
    *,
    odds_raw_path: Path | None = None,
    odds_meta_path: Path | None = None,
    kalshi_path: Path | None = None,
    run_id: str | None = None,
    created_ts: float | None = None,
    preferred_bookmaker: str | None = None,
    max_event_delta_seconds: float = 180.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ts = float(created_ts or time.time())
    kalshi_events = _index_kalshi_game_events(kalshi_payload)
    markets: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for event in odds_payload:
        event_markets, event_skips = _reference_rows_for_event(
            event,
            kalshi_events=kalshi_events,
            odds_meta=odds_meta,
            preferred_bookmaker=preferred_bookmaker,
            max_event_delta_seconds=max_event_delta_seconds,
        )
        markets.extend(event_markets)
        skipped.extend(event_skips)

    duplicate_tickers = _duplicate_values(row["kalshi_ticker"] for row in markets)
    max_delta = max((row.get("event_match_delta_seconds", 0.0) for row in markets), default=None)
    reference = {
        "schema_version": 1,
        "created_at_utc": datetime.fromtimestamp(ts, UTC).isoformat().replace("+00:00", "Z"),
        "source_note": (
            "Derived local sportsbook reference from local MLB Odds API and Kalshi snapshots. "
            "Review-only; not a raw provider dump."
        ),
        "research_only": True,
        "execution_enabled": False,
        "raw_provider_payload_copied": False,
        "quality": {
            "market_count": len(markets),
            "unique_kalshi_ticker_count": len({row["kalshi_ticker"] for row in markets}),
            "duplicate_kalshi_ticker_count": len(duplicate_tickers),
            "max_event_match_delta_seconds": max_delta,
            "skipped_event_count": len(skipped),
        },
        "inputs": {
            "sportsbook_raw_path": str(odds_raw_path) if odds_raw_path else None,
            "sportsbook_meta_path": str(odds_meta_path) if odds_meta_path else None,
            "kalshi_json_path": str(kalshi_path) if kalshi_path else None,
        },
        "markets": markets,
    }
    status = _report_status(markets=markets, duplicate_tickers=duplicate_tickers, skipped=skipped)
    report = {
        "schema_version": 1,
        "run_id": run_id or _stable_run_id(reference),
        "created_ts": ts,
        "created_at_utc": reference["created_at_utc"],
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "safety": {
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "account_or_order_paths": False,
            "raw_provider_payload_copied": False,
        },
        "policy": {
            "matching_policy": "team_pair_plus_kalshi_event_time",
            "kalshi_event_time_policy": "parse_event_ticker_as_america_new_york_start_time",
            "max_event_delta_seconds": float(max_event_delta_seconds),
            "provider_calls_allowed": False,
        },
        "summary": {
            **reference["quality"],
            "duplicate_kalshi_tickers": duplicate_tickers,
        },
        "inputs": reference["inputs"],
        "skipped_events": skipped,
    }
    return reference, report


def run_type2_reference_builder(
    *,
    odds_raw_json: Path,
    odds_meta_json: Path,
    kalshi_json: Path,
    reference_json: Path,
    report_dir: Path,
    run_id: str | None = None,
    preferred_bookmaker: str | None = None,
    max_event_delta_seconds: float = 180.0,
) -> Type2ReferenceBuilderArtifacts:
    odds_payload = _read_json_list(odds_raw_json)
    odds_meta = _read_json_object(odds_meta_json)
    kalshi_payload = _read_json_object(kalshi_json)
    reference, report = build_type2_reference(
        odds_payload,
        odds_meta,
        kalshi_payload,
        odds_raw_path=odds_raw_json,
        odds_meta_path=odds_meta_json,
        kalshi_path=kalshi_json,
        run_id=run_id,
        preferred_bookmaker=preferred_bookmaker,
        max_event_delta_seconds=max_event_delta_seconds,
    )
    reference_json.parent.mkdir(parents=True, exist_ok=True)
    reference_json.write_text(
        json.dumps(reference, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    resolved_run_id = str(report.get("run_id") or "type2-reference-builder-latest")
    report_json_path = report_dir / f"{resolved_run_id}.json"
    report_markdown_path = report_dir / f"{resolved_run_id}.md"
    report_json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report_markdown_path.write_text(
        render_type2_reference_builder_markdown(report), encoding="utf-8"
    )
    return Type2ReferenceBuilderArtifacts(
        report=report,
        reference=reference,
        report_json_path=report_json_path,
        report_markdown_path=report_markdown_path,
        reference_json_path=reference_json,
    )


def render_type2_reference_builder_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# Type 2 Reference Builder: {report.get('run_id', '')}",
        "",
        "## Scope",
        "",
        "- Mode: review-only",
        "- Research only: true",
        "- Execution enabled: false",
        f"- Status: `{report.get('status', '')}`",
        f"- Matching policy: `{report.get('policy', {}).get('matching_policy', '')}`",
        "",
        "## Summary",
        "",
        f"- Reference rows: {summary.get('market_count', 0)}",
        f"- Unique Kalshi tickers: {summary.get('unique_kalshi_ticker_count', 0)}",
        f"- Duplicate Kalshi tickers: {summary.get('duplicate_kalshi_ticker_count', 0)}",
        f"- Max event-match delta seconds: {summary.get('max_event_match_delta_seconds')}",
        f"- Skipped events: {summary.get('skipped_event_count', 0)}",
        "",
    ]
    skipped = list(report.get("skipped_events", []))
    if skipped:
        lines.extend(["## Skipped Events", ""])
        for row in skipped[:25]:
            lines.append(f"- `{row.get('reason', '')}`: {row.get('detail', '')}")
    lines.extend(
        [
            "## Guardrail",
            "",
            "This builds a derived local reference for manual research review only. It does not authorize execution or account activity.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def parse_kalshi_game_start_utc(event_ticker: str) -> datetime | None:
    match = EVENT_RE.match(event_ticker)
    if not match:
        return None
    month = MONTHS.get(match.group("month"))
    if month is None:
        return None
    local = datetime(
        2000 + int(match.group("year")),
        month,
        int(match.group("day")),
        int(match.group("hour")),
        int(match.group("minute")),
        tzinfo=ZoneInfo("America/New_York"),
    )
    return local.astimezone(UTC)


def _reference_rows_for_event(
    event: Mapping[str, Any],
    *,
    kalshi_events: Mapping[str, Mapping[str, Any]],
    odds_meta: Mapping[str, Any],
    preferred_bookmaker: str | None,
    max_event_delta_seconds: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    away = str(event.get("away_team") or "")
    home = str(event.get("home_team") or "")
    away_abbr = TEAM_TO_ABBR.get(away)
    home_abbr = TEAM_TO_ABBR.get(home)
    commence = _parse_time(event.get("commence_time"))
    if not away_abbr or not home_abbr or commence is None:
        return [], [
            _skip(
                event,
                "missing_team_or_commence_time",
                "Team abbreviation or commence_time is unavailable.",
            )
        ]

    event_match = _select_kalshi_event(
        kalshi_events,
        away_abbr=away_abbr,
        home_abbr=home_abbr,
        commence=commence,
        max_event_delta_seconds=max_event_delta_seconds,
    )
    if event_match is None:
        return [], [
            _skip(event, "kalshi_event_not_matched", f"No Kalshi event matched {away} at {home}.")
        ]
    event_ticker, kalshi_event, delta = event_match
    market = _select_h2h_market(event, preferred_bookmaker=preferred_bookmaker)
    if market is None:
        return [], [
            _skip(
                event,
                "h2h_market_not_found",
                f"No two-sided h2h market found for {away} at {home}.",
            )
        ]

    sportsbook, outcomes = market
    rows = []
    for abbr, team, opponent, side in (
        (away_abbr, away, home, "away"),
        (home_abbr, home, away, "home"),
    ):
        kalshi_row = kalshi_event["rows"].get(abbr)
        if not kalshi_row:
            continue
        rows.append(
            {
                "reference_id": f"{event_ticker.lower()}-{abbr.lower()}-{sportsbook}",
                "kalshi_ticker": kalshi_row["ticker"],
                "sportsbook": sportsbook,
                "market_label": f"{team} moneyline vs {opponent}",
                "capture_time_utc": odds_meta.get("created_at_utc"),
                "source_snapshot": odds_meta.get("raw_path") or "local_odds_api_snapshot",
                "sport_key": event.get("sport_key") or odds_meta.get("sport_key"),
                "event_ticker": event_ticker,
                "team": team,
                "opponent": opponent,
                "side": side,
                "commence_time_utc": event.get("commence_time"),
                "kalshi_event_start_utc": _format_time(kalshi_event.get("start_utc")),
                "event_match_rule": "team_pair_plus_kalshi_event_time",
                "event_match_delta_seconds": delta,
                "yes": {"american": outcomes[team]},
                "no": {"american": outcomes[opponent]},
            }
        )
    return rows, []


def _index_kalshi_game_events(kalshi_payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    rows = (
        kalshi_payload.get("all_scored")
        or kalshi_payload.get("markets")
        or kalshi_payload.get("rows")
        or []
    )
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        ticker = str(row.get("ticker") or "")
        event_ticker = str(row.get("event_ticker") or "")
        if not ticker.startswith("KXMLBGAME-") or not event_ticker:
            continue
        suffix = ticker.rsplit("-", 1)[-1]
        event = out.setdefault(
            event_ticker, {"rows": {}, "start_utc": parse_kalshi_game_start_utc(event_ticker)}
        )
        event["rows"][suffix] = dict(row)
    return out


def _select_kalshi_event(
    kalshi_events: Mapping[str, Mapping[str, Any]],
    *,
    away_abbr: str,
    home_abbr: str,
    commence: datetime,
    max_event_delta_seconds: float,
) -> tuple[str, Mapping[str, Any], float] | None:
    candidates = []
    for event_ticker, event in kalshi_events.items():
        if not (
            event_ticker.endswith(f"{away_abbr}{home_abbr}")
            or event_ticker.endswith(f"{home_abbr}{away_abbr}")
        ):
            continue
        rows = event.get("rows")
        start = event.get("start_utc")
        if (
            not isinstance(rows, Mapping)
            or away_abbr not in rows
            or home_abbr not in rows
            or not isinstance(start, datetime)
        ):
            continue
        delta = abs((start - commence).total_seconds())
        if math.isfinite(delta):
            candidates.append((delta, event_ticker, event))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    delta, event_ticker, event = candidates[0]
    if delta > float(max_event_delta_seconds):
        return None
    return event_ticker, event, delta


def _select_h2h_market(
    event: Mapping[str, Any],
    *,
    preferred_bookmaker: str | None,
) -> tuple[str, dict[str, int]] | None:
    bookmakers = list(event.get("bookmakers") or [])
    if preferred_bookmaker:
        bookmakers.sort(
            key=lambda row: (
                0 if isinstance(row, Mapping) and row.get("key") == preferred_bookmaker else 1
            )
        )
    away = str(event.get("away_team") or "")
    home = str(event.get("home_team") or "")
    for bookmaker in bookmakers:
        if not isinstance(bookmaker, Mapping):
            continue
        for market in bookmaker.get("markets") or []:
            if not isinstance(market, Mapping) or market.get("key") != "h2h":
                continue
            outcomes = {
                outcome.get("name"): outcome.get("price")
                for outcome in market.get("outcomes") or []
                if isinstance(outcome, Mapping)
                and outcome.get("name")
                and outcome.get("price") is not None
            }
            if away in outcomes and home in outcomes:
                return str(bookmaker.get("key") or "unknown-bookmaker"), {
                    away: int(outcomes[away]),
                    home: int(outcomes[home]),
                }
    return None


def _report_status(
    *,
    markets: Sequence[Mapping[str, Any]],
    duplicate_tickers: Sequence[str],
    skipped: Sequence[Mapping[str, Any]],
) -> str:
    if duplicate_tickers:
        return "reference_build_blocked_duplicate_tickers"
    if not markets:
        return "reference_build_blocked_no_rows"
    if skipped:
        return "reference_built_with_warnings"
    return "reference_built"


def _skip(event: Mapping[str, Any], reason: str, detail: str) -> dict[str, Any]:
    return {
        "reason": reason,
        "detail": detail,
        "away_team": event.get("away_team"),
        "home_team": event.get("home_team"),
        "commence_time": event.get("commence_time"),
    }


def _duplicate_values(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_time(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _stable_run_id(reference: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps(reference, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]
    return f"type2-reference-builder-{digest}"


def _read_json_object(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _read_json_list(path: Path) -> list[Mapping[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, list):
        raise ValueError(f"Expected JSON list in {path}")
    return [row for row in payload if isinstance(row, Mapping)]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a local Type 2 sportsbook reference from MLB snapshots."
    )
    parser.add_argument(
        "--odds-raw-json",
        default=manual_drop_path("odds_api", "baseball_mlb_current_20260620T225933Z.json"),
    )
    parser.add_argument(
        "--odds-meta-json",
        default=manual_drop_path(
            "odds_api", "baseball_mlb_current_20260620T225933Z.meta.json"
        ),
    )
    parser.add_argument(
        "--kalshi-json", default="data/kalshi_mlb_game_series_live_current_20260620T230203Z.json"
    )
    parser.add_argument(
        "--reference-json",
        default=manual_drop_path("predmarket", "type2-sportsbook-reference.json"),
    )
    parser.add_argument(
        "--report-dir", default="docs/codex/artifacts/type2-reference-builder-latest"
    )
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--preferred-bookmaker", default=None)
    parser.add_argument("--max-event-delta-seconds", type=float, default=180.0)
    args = parser.parse_args(argv)

    artifacts = run_type2_reference_builder(
        odds_raw_json=Path(args.odds_raw_json),
        odds_meta_json=Path(args.odds_meta_json),
        kalshi_json=Path(args.kalshi_json),
        reference_json=Path(args.reference_json),
        report_dir=Path(args.report_dir),
        run_id=args.run_id,
        preferred_bookmaker=args.preferred_bookmaker,
        max_event_delta_seconds=args.max_event_delta_seconds,
    )
    print(
        json.dumps(
            {
                "status": artifacts.report.get("status"),
                "json_path": str(artifacts.report_json_path),
                "markdown_path": str(artifacts.report_markdown_path),
                "reference_json_path": str(artifacts.reference_json_path),
                "research_only": artifacts.report.get("research_only"),
                "execution_enabled": artifacts.report.get("execution_enabled"),
                "summary": artifacts.report.get("summary"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
