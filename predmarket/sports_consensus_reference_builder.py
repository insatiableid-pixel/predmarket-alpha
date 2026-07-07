"""Build strict sports no-vig consensus references from local odds captures.

The output is the small derived file consumed by sports consensus preflight. Raw
provider payloads stay outside the repository, and this module never imports
donor repos at runtime.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from predmarket.shared_helpers import manual_drop_path

MLB_TEAM_TO_ABBR = {
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

THE_ODDS_API_ENDPOINT = "https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
DEFAULT_REQUIRED_BOOKS = ("pinnacle", "betfair_ex_uk", "matchbook", "smarkets")
DEFAULT_RAW_DIR = manual_drop_path("odds_api")
DEFAULT_REFERENCE_JSON = manual_drop_path("predmarket", "sports-no-vig-consensus.json")
DEFAULT_KEY_FILE = Path("/mnt/c/Users/mrwat/OneDrive/Desktop/Welcome to The Odds API!.txt")

Transport = Callable[[str, float], "HttpResponse"]


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class ConsensusReferenceBuildArtifacts:
    report: dict[str, Any]
    reference: dict[str, Any]
    report_json_path: Path
    report_markdown_path: Path
    reference_json_path: Path


def build_sports_consensus_reference(
    *,
    kalshi_payload: Mapping[str, Any],
    odds_captures: Sequence[tuple[Sequence[Mapping[str, Any]], Mapping[str, Any], Path | None]],
    kalshi_path: Path | None = None,
    reference_json: Path = DEFAULT_REFERENCE_JSON,
    run_id: str | None = None,
    created_ts: float | None = None,
    required_books: Sequence[str] = DEFAULT_REQUIRED_BOOKS,
    max_event_delta_seconds: float = 900.0,
    max_source_age_seconds: float = 900.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ts = float(created_ts or time.time())
    created_at = (
        datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    required = tuple(_norm_book(book) for book in required_books if _norm_book(book))
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    mlb_events = _index_mlb_game_events(kalshi_payload)

    for payload, meta, raw_path in odds_captures:
        sport_key = str(meta.get("sport_key") or _infer_sport_key(payload) or "")
        capture_time = _parse_utc(meta.get("created_at_utc")) or datetime.fromtimestamp(ts, UTC)
        if sport_key == "baseball_mlb":
            built, event_skips = _mlb_h2h_rows(
                payload,
                meta=meta,
                raw_path=raw_path,
                kalshi_events=mlb_events,
                capture_time=capture_time,
                required_books=required,
                max_event_delta_seconds=max_event_delta_seconds,
                max_source_age_seconds=max_source_age_seconds,
            )
            rows.extend(built)
            skipped.extend(event_skips)
        else:
            skipped.append(
                {
                    "reason": "unsupported_sport_key",
                    "sport_key": sport_key,
                    "detail": "Only baseball_mlb h2h has an exact ticker mapper in this tranche.",
                    "raw_path": str(raw_path) if raw_path else None,
                }
            )

    duplicate_ids = _duplicates(row["reference_id"] for row in rows)
    reference = {
        "schema_version": 1,
        "created_at_utc": created_at,
        "source_note": (
            "Derived timestamp-matched sports no-vig consensus reference. Raw provider "
            "payloads stay outside the repo."
        ),
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "raw_provider_payload_copied": False,
        "provider_api_calls": any(
            bool(meta.get("provider_api_calls")) for _, meta, _ in odds_captures
        ),
        "policy": {
            "probability_source": "configured_book_multi_book_no_vig_consensus",
            "required_books": list(required),
            "market_scope": "baseball_mlb_h2h_game_winner",
            "matching_policy": "mlb_team_pair_plus_kalshi_event_ticker_start",
            "max_event_delta_seconds": float(max_event_delta_seconds),
            "max_source_age_seconds": float(max_source_age_seconds),
        },
        "quality": {
            "reference_row_count": len(rows),
            "unique_kalshi_ticker_count": len({row["kalshi_ticker"] for row in rows}),
            "distinct_book_count": len({row["book_id"] for row in rows}),
            "duplicate_reference_id_count": len(duplicate_ids),
            "skipped_count": len(skipped),
        },
        "inputs": {
            "kalshi_json": str(kalshi_path) if kalshi_path else None,
            "kalshi_sha256": _sha256(kalshi_path)
            if kalshi_path and kalshi_path.is_file()
            else None,
            "raw_odds_paths": [str(raw_path) for _, _, raw_path in odds_captures if raw_path],
        },
        "rows": rows,
    }
    status = _status(rows=rows, duplicate_ids=duplicate_ids, skipped=skipped)
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
        "raw_provider_payload_copied": False,
        "safety": {
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "raw_provider_payload_copied": False,
            "api_key_printed": False,
        },
        "summary": reference["quality"],
        "policy": reference["policy"],
        "inputs": reference["inputs"],
        "reference_json_path": str(reference_json),
        "duplicate_reference_ids": duplicate_ids,
        "skipped": skipped,
    }
    return reference, report


def capture_the_odds_api_current(
    *,
    api_key: str,
    sport_key: str,
    output_dir: Path = DEFAULT_RAW_DIR,
    regions: Sequence[str] = ("us",),
    bookmakers: Sequence[str] = (),
    markets: Sequence[str] = ("h2h",),
    odds_format: str = "american",
    timeout_seconds: float = 20.0,
    created_at_utc: str | None = None,
    transport: Transport | None = None,
) -> tuple[list[Mapping[str, Any]], dict[str, Any], Path]:
    if not api_key.strip():
        raise ValueError("api_key must be non-empty")
    created = created_at_utc or datetime.now(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    stamp = _stamp(created)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / f"{sport_key}_current_{stamp}.json"
    meta_path = output_dir / f"{sport_key}_current_{stamp}.meta.json"
    url = _odds_api_url(
        api_key=api_key,
        sport_key=sport_key,
        regions=regions,
        bookmakers=bookmakers,
        markets=markets,
        odds_format=odds_format,
    )
    response = (transport or _urlopen_fetch)(url, timeout_seconds)
    payload, json_ok = _decode_json(response.body)
    rows = payload if isinstance(payload, list) else []
    raw_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    meta = {
        "schema_version": 1,
        "status": "odds_api_current_capture_written"
        if response.status_code == 200 and json_ok
        else "blocked_odds_api_current_capture",
        "created_at_utc": created,
        "sport_key": sport_key,
        "regions": list(regions),
        "bookmakers": list(bookmakers),
        "markets": list(markets),
        "odds_format": odds_format,
        "provider_api_calls": True,
        "paid_historical_calls": False,
        "database_writes": False,
        "account_or_order_paths": False,
        "raw_payload_copied_into_repo": False,
        "api_key_printed": False,
        "status_code": response.status_code,
        "quota_headers": _quota_headers(response.headers),
        "event_count": len(rows),
        "json_decode_ok": json_ok,
        "raw_path": str(raw_path),
        "request": {
            "endpoint": THE_ODDS_API_ENDPOINT.format(sport_key=sport_key),
            "params": {
                **(
                    {"bookmakers": ",".join(bookmakers)}
                    if bookmakers
                    else {"regions": ",".join(regions)}
                ),
                "markets": ",".join(markets),
                "oddsFormat": odds_format,
                "dateFormat": "iso",
            },
        },
        "safety": {
            "provider_api_calls": True,
            "paid_historical_calls": False,
            "database_writes": False,
            "account_or_order_paths": False,
            "raw_payload_copied_into_repo": False,
            "api_key_printed": False,
        },
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return [row for row in rows if isinstance(row, Mapping)], meta, raw_path


def run_sports_consensus_reference_build(
    *,
    kalshi_json: Path,
    reference_json: Path,
    report_dir: Path,
    run_id: str | None = None,
    odds_raw_json: Sequence[Path] = (),
    odds_meta_json: Sequence[Path] = (),
    capture_current: bool = False,
    api_key_file: Path = DEFAULT_KEY_FILE,
    sport_keys: Sequence[str] = ("baseball_mlb",),
    regions: Sequence[str] = ("us",),
    bookmakers: Sequence[str] = (),
    markets: Sequence[str] = ("h2h",),
    odds_format: str = "american",
    raw_output_dir: Path = DEFAULT_RAW_DIR,
    required_books: Sequence[str] = DEFAULT_REQUIRED_BOOKS,
    max_event_delta_seconds: float = 900.0,
    max_source_age_seconds: float = 900.0,
    timeout_seconds: float = 20.0,
) -> ConsensusReferenceBuildArtifacts:
    kalshi_payload = _read_json_object(kalshi_json)
    captures: list[tuple[Sequence[Mapping[str, Any]], Mapping[str, Any], Path | None]] = []
    for raw_path, meta_path in zip(odds_raw_json, odds_meta_json, strict=False):
        captures.append((_read_json_list(raw_path), _read_json_object(meta_path), raw_path))
    if capture_current:
        api_key = _read_api_key(api_key_file)
        for sport_key in sport_keys:
            payload, meta, raw_path = capture_the_odds_api_current(
                api_key=api_key,
                sport_key=sport_key,
                output_dir=raw_output_dir,
                regions=regions,
                bookmakers=bookmakers,
                markets=markets,
                odds_format=odds_format,
                timeout_seconds=timeout_seconds,
            )
            captures.append((payload, meta, raw_path))
    reference, report = build_sports_consensus_reference(
        kalshi_payload=kalshi_payload,
        odds_captures=captures,
        kalshi_path=kalshi_json,
        reference_json=reference_json,
        run_id=run_id,
        required_books=required_books,
        max_event_delta_seconds=max_event_delta_seconds,
        max_source_age_seconds=max_source_age_seconds,
    )
    if not captures:
        report = {
            **report,
            "status": "sports_consensus_reference_build_blocked_missing_odds_capture",
            "skipped": [
                *list(report.get("skipped", [])),
                {
                    "reason": "missing_odds_capture",
                    "detail": "Provide raw odds paths or pass --capture-current with a valid key file.",
                },
            ],
        }
    return write_sports_consensus_reference_build(
        reference,
        report,
        reference_json=reference_json,
        report_dir=report_dir,
    )


def write_sports_consensus_reference_build(
    reference: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    reference_json: Path,
    report_dir: Path,
) -> ConsensusReferenceBuildArtifacts:
    reference_json.parent.mkdir(parents=True, exist_ok=True)
    reference_json.write_text(
        json.dumps(reference, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    report_json_path = report_dir / "kalshi-sports-consensus-reference-build.json"
    report_markdown_path = report_dir / "kalshi-sports-consensus-reference-build.md"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    report_json_path.write_text(text, encoding="utf-8")
    report_markdown_path.write_text(
        render_sports_consensus_reference_build_markdown(report), encoding="utf-8"
    )
    latest_json = report_dir.parent / "latest-kalshi-sports-consensus-reference-build.json"
    latest_md = report_dir.parent / "latest-kalshi-sports-consensus-reference-build.md"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_sports_consensus_reference_build_markdown(report), encoding="utf-8")
    return ConsensusReferenceBuildArtifacts(
        report=dict(report),
        reference=dict(reference),
        report_json_path=report_json_path,
        report_markdown_path=report_markdown_path,
        reference_json_path=reference_json,
    )


def render_sports_consensus_reference_build_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    policy = report.get("policy", {}) if isinstance(report.get("policy"), Mapping) else {}
    lines = [
        "# Kalshi Sports Consensus Reference Build",
        "",
        f"- Status: `{report.get('status')}`",
        "- Mode: research-only",
        "- Execution enabled: `false`",
        f"- Required books: `{', '.join(policy.get('required_books', []))}`",
        "",
        "## Summary",
        "",
        f"- Reference rows: `{summary.get('reference_row_count', 0)}`",
        f"- Unique Kalshi tickers: `{summary.get('unique_kalshi_ticker_count', 0)}`",
        f"- Distinct books: `{summary.get('distinct_book_count', 0)}`",
        f"- Skipped: `{summary.get('skipped_count', 0)}`",
        "",
    ]
    skipped = [row for row in report.get("skipped", []) if isinstance(row, Mapping)]
    if skipped:
        lines.extend(["## Skipped", ""])
        for row in skipped[:25]:
            lines.append(f"- `{row.get('reason')}`: {row.get('detail')}")
    lines.extend(
        [
            "",
            "> Derived reference only. Raw provider payloads stay outside the repo; this does not authorize orders or sizing.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _mlb_h2h_rows(
    odds_payload: Sequence[Mapping[str, Any]],
    *,
    meta: Mapping[str, Any],
    raw_path: Path | None,
    kalshi_events: Mapping[str, Mapping[str, Any]],
    capture_time: datetime,
    required_books: Sequence[str],
    max_event_delta_seconds: float,
    max_source_age_seconds: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for event in odds_payload:
        event_rows, event_skips = _mlb_event_rows(
            event,
            meta=meta,
            raw_path=raw_path,
            kalshi_events=kalshi_events,
            capture_time=capture_time,
            required_books=required_books,
            max_event_delta_seconds=max_event_delta_seconds,
            max_source_age_seconds=max_source_age_seconds,
        )
        rows.extend(event_rows)
        skipped.extend(event_skips)
    return rows, skipped


def _mlb_event_rows(
    event: Mapping[str, Any],
    *,
    meta: Mapping[str, Any],
    raw_path: Path | None,
    kalshi_events: Mapping[str, Mapping[str, Any]],
    capture_time: datetime,
    required_books: Sequence[str],
    max_event_delta_seconds: float,
    max_source_age_seconds: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    away = str(event.get("away_team") or "")
    home = str(event.get("home_team") or "")
    away_abbr = MLB_TEAM_TO_ABBR.get(away)
    home_abbr = MLB_TEAM_TO_ABBR.get(home)
    commence = _parse_utc(event.get("commence_time"))
    if not away_abbr or not home_abbr or commence is None:
        return [], [
            _skip(
                event,
                "missing_team_or_commence_time",
                "Team abbreviation or commence_time unavailable.",
            )
        ]
    match = _select_mlb_kalshi_event(
        kalshi_events,
        away_abbr=away_abbr,
        home_abbr=home_abbr,
        commence=commence,
        max_event_delta_seconds=max_event_delta_seconds,
    )
    if match is None:
        return [], [
            _skip(
                event, "kalshi_event_not_matched", f"No KXMLBGAME event matched {away} at {home}."
            )
        ]
    event_ticker, kalshi_event, delta = match
    rows: list[dict[str, Any]] = []
    for bookmaker in event.get("bookmakers") or []:
        if not isinstance(bookmaker, Mapping):
            continue
        book_id = _norm_book(bookmaker.get("key"))
        if required_books and book_id not in set(required_books):
            continue
        market = _h2h_market(bookmaker)
        if market is None:
            continue
        last_update = _parse_utc(market.get("last_update") or bookmaker.get("last_update"))
        if _source_age_seconds(capture_time, last_update) > max_source_age_seconds:
            continue
        outcomes = _outcomes_by_name(market)
        if away not in outcomes or home not in outcomes:
            continue
        for abbr, team, opponent in ((away_abbr, away, home), (home_abbr, home, away)):
            kalshi_row = kalshi_event["rows"].get(abbr)
            if not isinstance(kalshi_row, Mapping):
                continue
            rows.append(
                {
                    "reference_id": f"{event_ticker.lower()}-{abbr.lower()}-{book_id}",
                    "kalshi_ticker": kalshi_row["ticker"],
                    "side": "yes",
                    "book_id": book_id,
                    "sportsbook": book_id,
                    "source_type": "sportsbook",
                    "market_label": f"{team} moneyline vs {opponent}",
                    "capture_time_utc": _format_utc(capture_time),
                    "book_last_update_utc": _format_utc(last_update),
                    "source_snapshot": str(raw_path) if raw_path else None,
                    "source_snapshot_sha256": _sha256(raw_path)
                    if raw_path and raw_path.is_file()
                    else None,
                    "sport_key": str(
                        event.get("sport_key") or meta.get("sport_key") or "baseball_mlb"
                    ),
                    "market_key": "h2h",
                    "event_id": event.get("id"),
                    "event_ticker": event_ticker,
                    "team": team,
                    "opponent": opponent,
                    "commence_time_utc": _format_utc(commence),
                    "kalshi_event_start_utc": _format_utc(kalshi_event.get("start_utc")),
                    "event_match_delta_seconds": delta,
                    "yes": {"american": outcomes[team]},
                    "no": {"american": outcomes[opponent]},
                }
            )
    if required_books and not _event_has_required_books(rows, required_books):
        return rows, [
            _skip(
                event,
                "required_books_incomplete",
                f"Need h2h rows from {', '.join(required_books)} after source-age filtering.",
            )
        ]
    return rows, []


def _index_mlb_game_events(kalshi_payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _kalshi_rows(kalshi_payload):
        ticker = str(row.get("ticker") or "")
        event_ticker = str(row.get("event_ticker") or "")
        if not ticker.startswith("KXMLBGAME-") or not event_ticker:
            continue
        suffix = ticker.rsplit("-", 1)[-1]
        event = out.setdefault(
            event_ticker,
            {"rows": {}, "start_utc": _parse_kalshi_mlb_start(event_ticker)},
        )
        event["rows"][suffix] = dict(row)
    return out


def _kalshi_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in ("all_scored", "candidates", "markets", "rows", "top_50"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, Mapping)]
    return []


def _select_mlb_kalshi_event(
    kalshi_events: Mapping[str, Mapping[str, Any]],
    *,
    away_abbr: str,
    home_abbr: str,
    commence: datetime,
    max_event_delta_seconds: float,
) -> tuple[str, Mapping[str, Any], float] | None:
    candidates = []
    for event_ticker, event in kalshi_events.items():
        if not event_ticker.endswith(f"{away_abbr}{home_abbr}"):
            continue
        rows = event.get("rows")
        start = event.get("start_utc")
        if not isinstance(rows, Mapping) or not isinstance(start, datetime):
            continue
        if away_abbr not in rows or home_abbr not in rows:
            continue
        delta = abs((start - commence).total_seconds())
        if math.isfinite(delta):
            candidates.append((delta, event_ticker, event))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    delta, event_ticker, event = candidates[0]
    if delta > max_event_delta_seconds:
        return None
    return event_ticker, event, delta


def _parse_kalshi_mlb_start(event_ticker: str) -> datetime | None:
    pieces = event_ticker.split("-")
    if len(pieces) < 2:
        return None
    stamp = pieces[1]
    if len(stamp) < 11:
        return None
    month = MONTHS.get(stamp[2:5])
    if month is None:
        return None
    try:
        local = datetime(
            2000 + int(stamp[:2]),
            month,
            int(stamp[5:7]),
            int(stamp[7:9]),
            int(stamp[9:11]),
            tzinfo=ZoneInfo("America/New_York"),
        )
    except ValueError:
        return None
    return local.astimezone(UTC)


def _h2h_market(bookmaker: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for market in bookmaker.get("markets") or []:
        if isinstance(market, Mapping) and market.get("key") == "h2h":
            return market
    return None


def _outcomes_by_name(market: Mapping[str, Any]) -> dict[str, int]:
    outcomes = {}
    for outcome in market.get("outcomes") or []:
        if not isinstance(outcome, Mapping):
            continue
        name = str(outcome.get("name") or "")
        price = outcome.get("price")
        if name and isinstance(price, int | float):
            outcomes[name] = int(price)
    return outcomes


def _event_has_required_books(
    rows: Sequence[Mapping[str, Any]], required_books: Sequence[str]
) -> bool:
    books = {str(row.get("book_id") or "") for row in rows}
    return set(required_books).issubset(books)


def _read_api_key(path: Path) -> str:
    key = path.expanduser().read_text(encoding="utf-8").strip()
    if not key:
        raise ValueError(f"API key file is empty: {path}")
    return key


def _odds_api_url(
    *,
    api_key: str,
    sport_key: str,
    regions: Sequence[str],
    bookmakers: Sequence[str],
    markets: Sequence[str],
    odds_format: str,
) -> str:
    provider_param = (
        {"bookmakers": ",".join(bookmakers)}
        if bookmakers
        else {"regions": ",".join(regions)}
    )
    query = urllib.parse.urlencode(
        {
            "apiKey": api_key,
            **provider_param,
            "markets": ",".join(markets),
            "oddsFormat": odds_format,
            "dateFormat": "iso",
        }
    )
    return f"{THE_ODDS_API_ENDPOINT.format(sport_key=sport_key)}?{query}"


def _urlopen_fetch(url: str, timeout_seconds: float) -> HttpResponse:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "predmarket-alpha-sports-consensus/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return HttpResponse(
                status_code=int(response.status),
                headers={str(k): str(v) for k, v in response.headers.items()},
                body=response.read(),
            )
    except urllib.error.HTTPError as exc:
        return HttpResponse(
            status_code=int(exc.code),
            headers={str(k): str(v) for k, v in exc.headers.items()},
            body=exc.read(),
        )


def _decode_json(body: bytes) -> tuple[Any, bool]:
    try:
        return json.loads(body.decode("utf-8")), True
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {
            "decode_error": str(exc),
            "body_preview": body[:500].decode("utf-8", errors="replace"),
        }, False


def _quota_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        str(k).lower(): str(v)
        for k, v in headers.items()
        if str(k).lower().startswith("x-requests")
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


def _format_utc(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _source_age_seconds(capture_time: datetime, source_time: datetime | None) -> float:
    if source_time is None:
        return math.inf
    return max(0.0, (capture_time - source_time).total_seconds())


def _norm_book(value: Any) -> str:
    return str(value or "").strip().lower()


def _infer_sport_key(payload: Sequence[Mapping[str, Any]]) -> str | None:
    for row in payload:
        sport_key = row.get("sport_key")
        if sport_key:
            return str(sport_key)
    return None


def _status(
    *,
    rows: Sequence[Mapping[str, Any]],
    duplicate_ids: Sequence[str],
    skipped: Sequence[Mapping[str, Any]],
) -> str:
    if duplicate_ids:
        return "sports_consensus_reference_build_blocked_duplicate_reference_ids"
    if not rows:
        return "sports_consensus_reference_build_blocked_no_rows"
    if skipped:
        return "sports_consensus_reference_built_with_warnings"
    return "sports_consensus_reference_built"


def _skip(event: Mapping[str, Any], reason: str, detail: str) -> dict[str, Any]:
    return {
        "reason": reason,
        "detail": detail,
        "away_team": event.get("away_team"),
        "home_team": event.get("home_team"),
        "commence_time": event.get("commence_time"),
        "event_id": event.get("id"),
    }


def _duplicates(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _stable_run_id(reference: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps(reference, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]
    return f"kalshi-sports-consensus-reference-build-{digest}"


def _sha256(path: Path | None) -> str | None:
    if path is None:
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stamp(created_at_utc: str) -> str:
    return created_at_utc.replace("-", "").replace(":", "").replace("+00:00", "Z")


def _read_json_object(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _read_json_list(path: Path) -> list[Mapping[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError(f"Expected JSON list in {path}")
    return [row for row in payload if isinstance(row, Mapping)]
