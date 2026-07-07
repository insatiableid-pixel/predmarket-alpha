#!/usr/bin/env python3
"""Record sharp sportsbook line moves as delta-only JSONL."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import (  # noqa: E402
    counts,
    manual_drop_path,
    path_is_within,
    read_json_or_empty,
    safe_stamp,
    safety_flags,
    sha256_or_none,
)
from predmarket.sports_consensus_reference_builder import (  # noqa: E402
    DEFAULT_KEY_FILE,
    THE_ODDS_API_ENDPOINT,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-line-move-delta-logger-latest"
DEFAULT_STATE_DIR = manual_drop_path(
    "kalshi_sports_line_moves",
    env_vars=("KALSHI_SPORTS_LINE_MOVE_STATE_DIR",),
)
DEFAULT_SPORT_KEYS = (
    "baseball_mlb",
    "tennis_atp_wimbledon",
    "soccer_fifa_world_cup",
    "americanfootball_nfl",
)
DEFAULT_BOOKMAKERS = ("pinnacle", "betfair_ex_uk", "matchbook", "smarkets")
SPORT_KEY_FALLBACKS = {
    "tennis_atp": ("tennis_atp_wimbledon",),
}

Transport = Callable[[str, float], "HttpResponse"]


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_delta_logger(
    *,
    sport_keys: Sequence[str],
    bookmakers: Sequence[str],
    markets: Sequence[str],
    state_dir: Path,
    api_key_file: Path = DEFAULT_KEY_FILE,
    regions: Sequence[str] = ("us",),
    odds_format: str = "american",
    timeout_seconds: float = 20.0,
    generated_utc: str | None = None,
    transport: Transport | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    try:
        api_key = read_api_key(api_key_file)
    except (OSError, ValueError) as exc:
        return report(
            generated_utc=generated,
            status="kalshi_sports_line_move_delta_logger_blocked_missing_api_key",
            sport_keys=sport_keys,
            bookmakers=bookmakers,
            markets=markets,
            state_dir=state_dir,
            delta_path=daily_delta_path(state_dir, generated),
            snapshots=[],
            deltas=[],
            errors=[{"type": type(exc).__name__, "message": str(exc)}],
            fallbacks=[],
            provider_api_calls=False,
        )

    previous = previous_quotes(state_dir)
    current: dict[str, dict[str, Any]] = {}
    snapshots: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    fallbacks: list[dict[str, Any]] = []
    for requested_sport_key in sport_keys:
        payload: list[Mapping[str, Any]] | None = None
        meta: dict[str, Any] | None = None
        attempts: list[dict[str, Any]] = []
        for sport_key in sport_key_candidates(requested_sport_key):
            try:
                payload, meta = fetch_current_odds(
                    api_key=api_key,
                    sport_key=sport_key,
                    regions=regions,
                    bookmakers=bookmakers,
                    markets=markets,
                    odds_format=odds_format,
                    timeout_seconds=timeout_seconds,
                    transport=transport,
                )
            except (OSError, ValueError, RuntimeError) as exc:
                attempts.append(
                    {
                        "sport_key": sport_key,
                        "type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
                continue
            meta["requested_sport_key"] = requested_sport_key
            meta["resolved_sport_key"] = sport_key
            if sport_key != requested_sport_key:
                meta["sport_key_fallback_used"] = True
                fallbacks.append(
                    {
                        "requested_sport_key": requested_sport_key,
                        "resolved_sport_key": sport_key,
                        "failed_attempts": attempts,
                    }
                )
            break
        if payload is None or meta is None:
            errors.append(
                {
                    "sport_key": requested_sport_key,
                    "type": "SportKeyFetchError",
                    "message": "all sport-key attempts failed",
                    "attempts": attempts,
                }
            )
            continue
        snapshots.append(meta)
        for quote in extract_quotes(
            payload,
            sport_key=str(meta["resolved_sport_key"]),
            captured_at_utc=generated,
        ):
            current[quote["quote_key"]] = quote

    deltas = compute_deltas(previous, current, captured_at_utc=generated)
    delta_path = daily_delta_path(state_dir, generated)
    append_deltas(delta_path, deltas)
    write_state(state_dir, current, generated_utc=generated)
    status = delta_status(current=current, deltas=deltas, errors=errors)
    return report(
        generated_utc=generated,
        status=status,
        sport_keys=sport_keys,
        bookmakers=bookmakers,
        markets=markets,
        state_dir=state_dir,
        delta_path=delta_path,
        snapshots=snapshots,
        deltas=deltas,
        errors=errors,
        fallbacks=fallbacks,
        provider_api_calls=bool(snapshots),
    )


def fetch_current_odds(
    *,
    api_key: str,
    sport_key: str,
    regions: Sequence[str],
    bookmakers: Sequence[str],
    markets: Sequence[str],
    odds_format: str,
    timeout_seconds: float,
    transport: Transport | None = None,
) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    if not api_key.strip():
        raise ValueError("api_key must be non-empty")
    url = odds_api_url(
        api_key=api_key,
        sport_key=sport_key,
        regions=regions,
        bookmakers=bookmakers,
        markets=markets,
        odds_format=odds_format,
    )
    response = (transport or urlopen_fetch)(url, timeout_seconds)
    payload = decode_json(response.body)
    if response.status_code != 200:
        raise RuntimeError(f"The Odds API returned HTTP {response.status_code}")
    if not isinstance(payload, list):
        raise ValueError("The Odds API response was not a JSON list")
    rows = [row for row in payload if isinstance(row, Mapping)]
    meta = {
        "sport_key": sport_key,
        "status_code": response.status_code,
        "event_count": len(rows),
        "quota_headers": quota_headers(response.headers),
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
        "api_key_printed": False,
    }
    return rows, meta


def odds_api_url(
    *,
    api_key: str,
    sport_key: str,
    regions: Sequence[str],
    bookmakers: Sequence[str],
    markets: Sequence[str],
    odds_format: str,
) -> str:
    provider_param = (
        {"bookmakers": ",".join(bookmakers)} if bookmakers else {"regions": ",".join(regions)}
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


def sport_key_candidates(sport_key: str) -> tuple[str, ...]:
    fallbacks = SPORT_KEY_FALLBACKS.get(sport_key, ())
    return tuple(dict.fromkeys((sport_key, *fallbacks)))


def urlopen_fetch(url: str, timeout_seconds: float) -> HttpResponse:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "predmarket-alpha-line-move-delta/1.0",
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


def decode_json(body: bytes) -> Any:
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON response: {exc}") from exc


def extract_quotes(
    payload: Sequence[Mapping[str, Any]],
    *,
    sport_key: str,
    captured_at_utc: str,
) -> list[dict[str, Any]]:
    quotes: list[dict[str, Any]] = []
    for event in payload:
        event_id = str(event.get("id") or "")
        commence = str(event.get("commence_time") or "")
        home_team = str(event.get("home_team") or "")
        away_team = str(event.get("away_team") or "")
        for bookmaker in event.get("bookmakers") or []:
            if not isinstance(bookmaker, Mapping):
                continue
            book_key = str(bookmaker.get("key") or "")
            book_title = str(bookmaker.get("title") or book_key)
            for market in bookmaker.get("markets") or []:
                if not isinstance(market, Mapping):
                    continue
                market_key = str(market.get("key") or "")
                market_last_update = str(
                    market.get("last_update") or bookmaker.get("last_update") or ""
                )
                for outcome in market.get("outcomes") or []:
                    if not isinstance(outcome, Mapping):
                        continue
                    outcome_name = str(outcome.get("name") or "")
                    if not event_id or not book_key or not market_key or not outcome_name:
                        continue
                    price = outcome.get("price")
                    point = outcome.get("point")
                    key = quote_key(
                        sport_key=sport_key,
                        event_id=event_id,
                        bookmaker_key=book_key,
                        market_key=market_key,
                        outcome_name=outcome_name,
                    )
                    quotes.append(
                        {
                            "quote_key": key,
                            "sport_key": sport_key,
                            "event_id": event_id,
                            "commence_time_utc": commence,
                            "home_team": home_team,
                            "away_team": away_team,
                            "bookmaker_key": book_key,
                            "bookmaker_title": book_title,
                            "market_key": market_key,
                            "outcome_name": outcome_name,
                            "price": price,
                            "point": point,
                            "book_last_update_utc": market_last_update,
                            "captured_at_utc": captured_at_utc,
                        }
                    )
    return quotes


def quote_key(
    *,
    sport_key: str,
    event_id: str,
    bookmaker_key: str,
    market_key: str,
    outcome_name: str,
) -> str:
    raw = "|".join([sport_key, event_id, bookmaker_key, market_key, outcome_name])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_deltas(
    previous: Mapping[str, Mapping[str, Any]],
    current: Mapping[str, Mapping[str, Any]],
    *,
    captured_at_utc: str,
) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []
    for key, quote in sorted(current.items()):
        old = previous.get(key)
        if old is None:
            deltas.append(delta_row("initial_quote", quote, None, captured_at_utc))
            continue
        if old.get("price") != quote.get("price") or old.get("point") != quote.get("point"):
            deltas.append(delta_row("line_move", quote, old, captured_at_utc))
    return deltas


def delta_row(
    delta_type: str,
    quote: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    captured_at_utc: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "delta_type": delta_type,
        "captured_at_utc": captured_at_utc,
        "quote_key": quote.get("quote_key"),
        "sport_key": quote.get("sport_key"),
        "event_id": quote.get("event_id"),
        "commence_time_utc": quote.get("commence_time_utc"),
        "bookmaker_key": quote.get("bookmaker_key"),
        "market_key": quote.get("market_key"),
        "outcome_name": quote.get("outcome_name"),
        "previous_price": previous.get("price") if previous else None,
        "new_price": quote.get("price"),
        "previous_point": previous.get("point") if previous else None,
        "new_point": quote.get("point"),
        "book_last_update_utc": quote.get("book_last_update_utc"),
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "signal_or_probability": False,
    }


def previous_quotes(state_dir: Path) -> dict[str, dict[str, Any]]:
    state = read_json_or_empty(state_dir / "latest-quotes.json")
    quotes = state.get("quotes")
    if not isinstance(quotes, Mapping):
        return {}
    return {str(key): dict(value) for key, value in quotes.items() if isinstance(value, Mapping)}


def write_state(
    state_dir: Path, quotes: Mapping[str, Mapping[str, Any]], *, generated_utc: str
) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "latest-quotes.json").write_text(
        json.dumps(
            {"schema_version": 1, "generated_utc": generated_utc, "quotes": quotes},
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )


def daily_delta_path(state_dir: Path, generated_utc: str) -> Path:
    date = safe_stamp(generated_utc[:10])
    return state_dir / f"sports_line_move_deltas_{date}.jsonl"


def append_deltas(path: Path, deltas: Sequence[Mapping[str, Any]]) -> None:
    if not deltas:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in deltas:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def report(
    *,
    generated_utc: str,
    status: str,
    sport_keys: Sequence[str],
    bookmakers: Sequence[str],
    markets: Sequence[str],
    state_dir: Path,
    delta_path: Path,
    snapshots: Sequence[Mapping[str, Any]],
    deltas: Sequence[Mapping[str, Any]],
    errors: Sequence[Mapping[str, Any]],
    fallbacks: Sequence[Mapping[str, Any]],
    provider_api_calls: bool,
) -> dict[str, Any]:
    delta_types = counts([row.get("delta_type") for row in deltas])
    return {
        "schema_version": 1,
        "generated_utc": generated_utc,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "provider_api_calls": provider_api_calls,
        "paid_historical_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "raw_provider_payload_copied_to_repo": False,
        "api_key_printed": False,
        "inputs": {
            "sport_keys": list(sport_keys),
            "bookmakers": list(bookmakers),
            "markets": list(markets),
            "state_dir": str(state_dir),
            "delta_jsonl_path": str(delta_path),
            "delta_jsonl_sha256": sha256_or_none(delta_path),
        },
        "summary": {
            "sport_count": len(sport_keys),
            "snapshot_count": len(snapshots),
            "event_count": sum(int(meta.get("event_count") or 0) for meta in snapshots),
            "delta_count": len(deltas),
            "initial_quote_count": int(delta_types.get("initial_quote", 0)),
            "line_move_count": int(delta_types.get("line_move", 0)),
            "error_count": len(errors),
            "sport_key_fallback_count": len(fallbacks),
            "quota_headers": [meta.get("quota_headers") for meta in snapshots],
        },
        "provider_snapshots": list(snapshots),
        "errors": list(errors),
        "sport_key_fallbacks": list(fallbacks),
        "next_action": next_action(status),
        "safety": {
            **safety_flags(public_market_data_calls=provider_api_calls),
            "provider_api_calls": provider_api_calls,
            "paid_historical_calls": False,
            "api_key_printed": False,
            "account_or_order_paths": False,
            "market_execution": False,
        },
    }


def delta_status(
    *,
    current: Mapping[str, Mapping[str, Any]],
    deltas: Sequence[Mapping[str, Any]],
    errors: Sequence[Mapping[str, Any]],
) -> str:
    if not current and errors:
        return "kalshi_sports_line_move_delta_logger_blocked_provider_fetch_error"
    if errors:
        return "kalshi_sports_line_move_delta_logger_ready_partial_provider_errors"
    if not current:
        return "kalshi_sports_line_move_delta_logger_blocked_no_quotes"
    if deltas:
        return "kalshi_sports_line_move_delta_logger_ready_with_deltas"
    return "kalshi_sports_line_move_delta_logger_ready_no_deltas"


def next_action(status: str) -> dict[str, Any]:
    if status == "kalshi_sports_line_move_delta_logger_ready_with_deltas":
        return {
            "name": "continue_line_move_delta_capture",
            "why": "Sharp line-move evidence is now accruing. Keep collecting before stale-quote falsification.",
            "stop_condition": "Stop before turning deltas into signals until stale-quote rules are pre-registered.",
        }
    if "blocked" in status:
        return {
            "name": "repair_line_move_delta_input",
            "why": "Line-move evidence cannot accrue until provider input is available.",
            "stop_condition": "Stop before using stale-quote signals.",
        }
    return {
        "name": "sleep_then_repeat_line_move_capture",
        "why": "No line changes in this cycle; keep polling on the configured cadence.",
        "stop_condition": "Stop before signal fitting.",
    }


def write_outputs(
    report_payload: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-line-move-delta-logger.json"
    md_path = out_dir / "kalshi-sports-line-move-delta-logger.md"
    text = json.dumps(report_payload, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report_payload), encoding="utf-8")
    paths = {"json_path": str(json_path), "markdown_path": str(md_path)}
    if path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-sports-line-move-delta-logger.json"
        latest_md = MACRO_DIR / "latest-kalshi-sports-line-move-delta-logger.md"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report_payload), encoding="utf-8")
        paths.update({"latest_json_path": str(latest_json), "latest_markdown_path": str(latest_md)})
    return paths


def render_markdown(report_payload: Mapping[str, Any]) -> str:
    summary = (
        report_payload.get("summary") if isinstance(report_payload.get("summary"), Mapping) else {}
    )
    inputs = (
        report_payload.get("inputs") if isinstance(report_payload.get("inputs"), Mapping) else {}
    )
    return "\n".join(
        [
            "# Kalshi Sports Line-Move Delta Logger",
            "",
            f"- Status: `{report_payload.get('status')}`",
            f"- Sports: `{summary.get('sport_count')}`",
            f"- Events fetched: `{summary.get('event_count')}`",
            f"- Deltas: `{summary.get('delta_count')}`",
            f"- Line moves: `{summary.get('line_move_count')}`",
            f"- Delta JSONL: `{inputs.get('delta_jsonl_path')}`",
            "",
            "Research-only evidence capture. No probabilities, paper stake, orders, balances, or account paths.",
            "",
        ]
    )


def read_api_key(path: Path) -> str:
    text = path.expanduser().read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"API key file is empty: {path}")
    return text


def quota_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        str(k).lower(): str(v)
        for k, v in headers.items()
        if str(k).lower().startswith("x-requests")
    }


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--api-key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--sport-keys", default=",".join(DEFAULT_SPORT_KEYS))
    parser.add_argument("--bookmakers", default=",".join(DEFAULT_BOOKMAKERS))
    parser.add_argument("--regions", default="us")
    parser.add_argument("--markets", default="h2h")
    parser.add_argument("--odds-format", default="american")
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--max-cycles", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    max_cycles = int(args.max_cycles)
    cycle = 0
    latest_report: dict[str, Any] = {}
    while True:
        latest_report = run_delta_logger(
            sport_keys=parse_csv(args.sport_keys),
            bookmakers=parse_csv(args.bookmakers),
            markets=parse_csv(args.markets),
            regions=parse_csv(args.regions),
            state_dir=args.state_dir,
            api_key_file=args.api_key_file,
            odds_format=str(args.odds_format),
            timeout_seconds=float(args.timeout_seconds),
        )
        if args.write:
            paths = write_outputs(latest_report, args.out_dir)
            print(
                json.dumps({"status": latest_report["status"], **paths}, indent=2, sort_keys=True)
            )
        else:
            print(json.dumps(latest_report, indent=2, sort_keys=True, default=str))
        cycle += 1
        if max_cycles > 0 and cycle >= max_cycles:
            return 0
        time.sleep(max(1.0, float(args.interval_seconds)))


if __name__ == "__main__":
    raise SystemExit(main())
