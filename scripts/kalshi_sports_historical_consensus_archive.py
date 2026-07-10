#!/usr/bin/env python3
"""Acquire a bounded, replayable paid MLB historical sharp-consensus archive."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import (  # noqa: E402
    iso_from_timestamp,
    manual_drop_path,
    path_is_within,
    safety_flags,
    sha256_or_none,
    timestamp,
)
from predmarket.sports_consensus_reference_builder import (  # noqa: E402
    DEFAULT_KEY_FILE,
    THE_ODDS_API_ENDPOINT,
    build_mlb_h2h_reference_rows,
    index_mlb_game_events,
)
from predmarket.type2_paper_matcher import no_vig_midpoint_from_reference  # noqa: E402
from scripts.kalshi_resolved_archive_backfill import (  # noqa: E402
    load_raw_candlesticks,
    load_raw_markets,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-historical-consensus-archive-latest"
DEFAULT_ARCHIVE_PATH = manual_drop_path(
    "kalshi_sports_historical_consensus",
    "kalshi_sports_historical_consensus_latest.json",
    env_vars=("KALSHI_SPORTS_HISTORICAL_CONSENSUS_ROWS_PATH",),
)
DEFAULT_RAW_DIR = manual_drop_path("kalshi_sports_historical_consensus", "raw")
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
DEFAULT_BOOKMAKERS = (
    "pinnacle",
    "circa",
    "bookmaker",
    "betcris",
    "betfair_ex_uk",
    "matchbook",
    "smarkets",
)
Fetch = Callable[[str, float], tuple[Mapping[str, Any], Mapping[str, str]]]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_snapshot_plan(
    markets: Sequence[Mapping[str, Any]],
    candlesticks_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    pregame_lead_seconds: int = 3600,
    max_snapshots: int = 0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Choose one shared Kalshi candle timestamp per settled MLB event."""
    by_event: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for market in markets:
        event = str(market.get("event_ticker") or "")
        ticker = str(market.get("ticker") or market.get("contract_ticker") or "")
        if event.startswith("KXMLBGAME-") and ticker:
            by_event[event].append(market)
    by_target: dict[int, dict[str, Any]] = {}
    blockers: list[dict[str, Any]] = []
    for event, event_markets in sorted(by_event.items()):
        # ``occurrence_datetime`` in the resolved archive has a known timezone
        # offset.  The KXMLBGAME ticker is the stable, exact game identity used
        # again by the reference mapper, so anchor the historical request window
        # to its parsed start whenever that identity is available.
        indexed_event = index_mlb_game_events({"markets": event_markets}).get(event)
        ticker_start = (
            indexed_event.get("start_utc") if isinstance(indexed_event, Mapping) else None
        )
        start_ts = (
            ticker_start.timestamp()
            if isinstance(ticker_start, datetime)
            else timestamp(
                event_markets[0].get("occurrence_datetime")
                or event_markets[0].get("expected_expiration_time")
                or event_markets[0].get("close_time")
            )
        )
        if start_ts is None:
            blockers.append({"event_ticker": event, "reason": "missing_event_start"})
            continue
        shared: set[int] | None = None
        tickers: list[str] = []
        for market in event_markets:
            ticker = str(market.get("ticker") or market.get("contract_ticker") or "")
            tickers.append(ticker)
            eligible = {
                int(candle_ts)
                for candle in candlesticks_by_ticker.get(ticker, ())
                if (candle_ts := timestamp(candle.get("end_period_ts"))) is not None
                and candle_ts <= start_ts - pregame_lead_seconds
            }
            shared = eligible if shared is None else shared.intersection(eligible)
        if not shared:
            blockers.append(
                {"event_ticker": event, "reason": "missing_shared_pregame_kalshi_candle"}
            )
            continue
        target_ts = max(shared)
        entry = by_target.setdefault(
            target_ts,
            {
                "target_ts": target_ts,
                "target_time_utc": iso_from_timestamp(target_ts),
                "event_tickers": [],
                "contract_tickers": [],
            },
        )
        entry["event_tickers"].append(event)
        entry["contract_tickers"].extend(sorted(tickers))
    plan = [by_target[key] for key in sorted(by_target)]
    if max_snapshots > 0:
        plan = plan[:max_snapshots]
    return plan, blockers


def build_archive_rows_for_snapshot(
    payload: Mapping[str, Any],
    plan_row: Mapping[str, Any],
    *,
    kalshi_events: Mapping[str, Mapping[str, Any]],
    source_sha256: str | None,
    min_distinct_books: int = 2,
    max_skew_seconds: int = 180,
    max_source_age_seconds: int = 1800,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    target_ts = timestamp(plan_row.get("target_time_utc") or plan_row.get("target_ts"))
    snapshot_utc = str(payload.get("timestamp") or "")
    snapshot_ts = timestamp(snapshot_utc)
    if target_ts is None or snapshot_ts is None:
        return [], [{"reason": "missing_target_or_provider_snapshot_timestamp"}]
    provider_skew = abs(snapshot_ts - target_ts)
    if provider_skew > max_skew_seconds:
        return [], [
            {
                "reason": "provider_snapshot_skew_exceeds_policy",
                "target_time_utc": iso_from_timestamp(target_ts),
                "provider_snapshot_utc": snapshot_utc,
                "skew_seconds": provider_skew,
            }
        ]
    data = payload.get("data")
    odds_rows = (
        [dict(row) for row in data if isinstance(row, Mapping)] if isinstance(data, list) else []
    )
    references, mapping_skips = build_mlb_h2h_reference_rows(
        odds_rows,
        meta={"sport_key": "baseball_mlb", "created_at_utc": snapshot_utc},
        kalshi_events=kalshi_events,
        capture_time=datetime.fromtimestamp(snapshot_ts, UTC),
        max_source_age_seconds=max_source_age_seconds,
    )
    expected_events = {str(value) for value in plan_row.get("event_tickers") or []}
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for reference in references:
        if str(reference.get("event_ticker") or "") in expected_events:
            grouped[str(reference.get("kalshi_ticker") or "")].append(reference)
    rows: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for ticker, book_references in sorted(grouped.items()):
        book_probabilities: dict[str, float] = {}
        for reference in book_references:
            book_id = str(reference.get("book_id") or "")
            if not book_id or book_id in book_probabilities:
                continue
            try:
                book_probabilities[book_id] = float(
                    no_vig_midpoint_from_reference(reference)["no_vig_yes"]
                )
            except ValueError:
                continue
        if len(book_probabilities) < min_distinct_books:
            blockers.append(
                {
                    "reason": "insufficient_distinct_books",
                    "contract_ticker": ticker,
                    "book_count": len(book_probabilities),
                }
            )
            continue
        first = book_references[0]
        probability = statistics.median(book_probabilities.values())
        rows.append(
            {
                "schema_version": "KalshiSportsHistoricalConsensusRowV1",
                "contract_ticker": ticker,
                "event_ticker": first.get("event_ticker"),
                "series_ticker": "KXMLBGAME",
                "side": "yes",
                "sport_key": "baseball_mlb",
                "market_key": "h2h",
                "observed_utc": iso_from_timestamp(target_ts),
                "provider_snapshot_utc": snapshot_utc,
                "provider_snapshot_skew_seconds": provider_skew,
                "consensus_yes_probability": probability,
                "consensus_probability_for_side": probability,
                "consensus_method": "median_of_book_level_two_way_no_vig_probabilities",
                "book_count": len(book_probabilities),
                "distinct_books": sorted(book_probabilities),
                "book_no_vig_yes_probabilities": book_probabilities,
                "source_reference_sha256": source_sha256,
                "research_only": True,
                "execution_enabled": False,
                "usable": False,
            }
        )
    mapped_events = {str(row.get("event_ticker") or "") for row in rows}
    for event in sorted(expected_events - mapped_events):
        blockers.append({"reason": "expected_event_not_mapped", "event_ticker": event})
    blockers.extend(
        {
            "reason": str(item.get("reason") or "provider_mapping_skip"),
            "event_id": item.get("event_id"),
        }
        for item in mapping_skips
        if str(item.get("reason") or "") != "kalshi_event_not_matched"
    )
    return rows, blockers


def historical_request_url(
    *,
    api_key: str,
    target_ts: float,
    bookmakers: Sequence[str],
    snapshot_interval_seconds: int = 300,
) -> tuple[str, str]:
    requested_ts = target_ts + snapshot_interval_seconds / 2.0
    requested_utc = iso_from_timestamp(requested_ts) or ""
    endpoint = THE_ODDS_API_ENDPOINT.format(sport_key="baseball_mlb").replace(
        "/v4/sports/", "/v4/historical/sports/"
    )
    query = urllib.parse.urlencode(
        {
            "apiKey": api_key,
            "bookmakers": ",".join(bookmakers),
            "markets": "h2h",
            "oddsFormat": "american",
            "dateFormat": "iso",
            "date": requested_utc,
        }
    )
    return f"{endpoint}?{query}", requested_utc


def fetch_historical_json(
    url: str,
    timeout_seconds: float,
    *,
    max_attempts: int = 4,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[Mapping[str, Any], Mapping[str, str]]:
    for attempt in range(1, max_attempts + 1):
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "predmarket-alpha/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = json.load(response)
                headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
            if not isinstance(payload, Mapping):
                raise RuntimeError("historical provider returned a non-object payload")
            return payload, headers
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt >= max_attempts:
                raise RuntimeError(f"historical provider HTTP {exc.code}") from exc
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = float(retry_after) if retry_after is not None else 2.0**attempt
            except ValueError:
                delay = 2.0**attempt
            sleep_fn(max(0.0, min(delay, 30.0)))
    raise RuntimeError("historical provider retry budget exhausted")


def acquire_snapshots(
    plan: Sequence[Mapping[str, Any]],
    *,
    api_key: str,
    raw_dir: Path,
    bookmakers: Sequence[str],
    capture_paid: bool,
    max_paid_credits: int,
    snapshot_interval_seconds: int = 300,
    timeout_seconds: float = 20.0,
    fetch_fn: Fetch = fetch_historical_json,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    uncached = [row for row in plan if not _snapshot_paths(raw_dir, row)[0].is_file()]
    estimated_credits = len(uncached) * 10
    if capture_paid and estimated_credits > max_paid_credits:
        return [], [
            {
                "reason": "paid_credit_cap_exceeded",
                "uncached_snapshot_count": len(uncached),
                "estimated_credits": estimated_credits,
                "max_paid_credits": max_paid_credits,
            }
        ]
    snapshots: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for plan_row in plan:
        raw_path, meta_path = _snapshot_paths(raw_dir, plan_row)
        cached = raw_path.is_file() and meta_path.is_file()
        if cached:
            payload = _read_object(raw_path)
            meta = _read_object(meta_path)
            snapshots.append(
                {"plan": dict(plan_row), "payload": payload, "meta": meta, "raw_path": raw_path}
            )
            continue
        if not capture_paid:
            continue
        try:
            url, requested_utc = historical_request_url(
                api_key=api_key,
                target_ts=float(plan_row["target_ts"]),
                bookmakers=bookmakers,
                snapshot_interval_seconds=snapshot_interval_seconds,
            )
            payload, headers = fetch_fn(url, timeout_seconds)
            raw_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            meta = {
                "schema_version": 1,
                "status": "historical_snapshot_capture_written",
                "target_time_utc": plan_row.get("target_time_utc"),
                "requested_date_utc": requested_utc,
                "provider_snapshot_utc": payload.get("timestamp"),
                "sport_key": "baseball_mlb",
                "market": "h2h",
                "bookmakers": list(bookmakers),
                "paid_historical_calls": True,
                "api_key_printed": False,
                "quota_headers": {
                    key: value for key, value in headers.items() if key.startswith("x-requests")
                },
                "raw_path": str(raw_path),
                "raw_sha256": sha256_or_none(raw_path),
            }
            meta_path.write_text(
                json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            snapshots.append(
                {
                    "plan": dict(plan_row),
                    "payload": dict(payload),
                    "meta": meta,
                    "raw_path": raw_path,
                }
            )
        except (OSError, RuntimeError, ValueError) as exc:
            errors.append(
                {
                    "reason": "historical_snapshot_capture_failed",
                    "target_time_utc": plan_row.get("target_time_utc"),
                    "error": str(exc),
                }
            )
    return snapshots, errors


def assemble_archive(
    plan: Sequence[Mapping[str, Any]],
    plan_blockers: Sequence[Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]],
    capture_errors: Sequence[Mapping[str, Any]],
    *,
    markets: Sequence[Mapping[str, Any]],
    min_distinct_books: int,
    max_skew_seconds: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    kalshi_events = index_mlb_game_events({"markets": list(markets)})
    rows: list[dict[str, Any]] = []
    row_blockers: list[dict[str, Any]] = []
    quota_headers: dict[str, str] = {}
    for snapshot in snapshots:
        built, blockers = build_archive_rows_for_snapshot(
            snapshot.get("payload") if isinstance(snapshot.get("payload"), Mapping) else {},
            snapshot.get("plan") if isinstance(snapshot.get("plan"), Mapping) else {},
            kalshi_events=kalshi_events,
            source_sha256=sha256_or_none(snapshot.get("raw_path")),
            min_distinct_books=min_distinct_books,
            max_skew_seconds=max_skew_seconds,
        )
        rows.extend(built)
        row_blockers.extend(blockers)
        meta = snapshot.get("meta") if isinstance(snapshot.get("meta"), Mapping) else {}
        quota = meta.get("quota_headers") if isinstance(meta.get("quota_headers"), Mapping) else {}
        quota_headers.update({str(key): str(value) for key, value in quota.items()})
    deduped = {(str(row["contract_ticker"]), str(row["observed_utc"])): row for row in rows}
    ordered_rows = sorted(
        deduped.values(), key=lambda row: (str(row["observed_utc"]), str(row["contract_ticker"]))
    )
    generated = utc_now()
    archive = {
        "schema_version": 1,
        "generated_utc": generated,
        "status": "kalshi_sports_historical_consensus_archive_ready"
        if ordered_rows
        else "kalshi_sports_historical_consensus_archive_empty",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "provider_api_calls": bool(snapshots),
        "paid_historical_calls": bool(snapshots),
        "rows": ordered_rows,
    }
    status = (
        "kalshi_sports_historical_consensus_archive_ready"
        if ordered_rows and not capture_errors
        else "kalshi_sports_historical_consensus_archive_partial"
        if ordered_rows
        else "kalshi_sports_historical_consensus_archive_planned_or_blocked"
    )
    report = {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "provider_api_calls": bool(snapshots),
        "paid_historical_calls": bool(snapshots),
        "summary": {
            "planned_snapshot_count": len(plan),
            "captured_or_cached_snapshot_count": len(snapshots),
            "estimated_full_plan_credits": len(plan) * 10,
            "historical_consensus_row_count": len(ordered_rows),
            "distinct_contract_count": len({row["contract_ticker"] for row in ordered_rows}),
            "distinct_event_count": len({row["event_ticker"] for row in ordered_rows}),
            "plan_blocker_count": len(plan_blockers),
            "capture_error_count": len(capture_errors),
            "row_blocker_count": len(row_blockers),
            "max_provider_snapshot_skew_seconds": max(
                (float(row["provider_snapshot_skew_seconds"]) for row in ordered_rows),
                default=None,
            ),
            "quota_headers": quota_headers,
        },
        "method": {
            "sport": "baseball_mlb",
            "market": "h2h",
            "snapshot_policy": "latest shared hourly Kalshi candle at least one hour pregame",
            "provider_query_policy": "target_time + 150 seconds for five-minute historical snapshots",
            "consensus_method": "median of book-level two-way no-vig probabilities",
            "settlement_label_source": "none; downstream uses exact public Kalshi settlements",
        },
        "plan_blockers": list(plan_blockers)[:200],
        "capture_errors": list(capture_errors)[:200],
        "row_blockers": row_blockers[:200],
        "safety": {
            **safety_flags(public_market_data_calls=bool(snapshots)),
            "provider_api_calls": bool(snapshots),
            "paid_historical_calls": bool(snapshots),
            "api_key_printed": False,
        },
    }
    return archive, report


def write_outputs(
    archive: Mapping[str, Any],
    report: dict[str, Any],
    *,
    archive_path: Path,
    out_dir: Path,
) -> dict[str, str]:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    if archive.get("rows"):
        archive_path.write_text(
            json.dumps(archive, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
    report["archive_path"] = str(archive_path)
    report["archive_sha256"] = sha256_or_none(archive_path)
    json_path = out_dir / "kalshi-sports-historical-consensus-archive.json"
    md_path = out_dir / "kalshi-sports-historical-consensus-archive.md"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    markdown = render_markdown(report)
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    paths = {"json_path": str(json_path), "markdown_path": str(md_path)}
    if path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-sports-historical-consensus-archive.json"
        latest_md = MACRO_DIR / "latest-kalshi-sports-historical-consensus-archive.md"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(markdown, encoding="utf-8")
        paths.update({"latest_json_path": str(latest_json), "latest_markdown_path": str(latest_md)})
    return paths


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    return "\n".join(
        [
            "# Kalshi Sports Historical Consensus Archive",
            "",
            f"- Status: `{report.get('status')}`",
            f"- Planned snapshots: `{summary.get('planned_snapshot_count')}`",
            f"- Captured/cached snapshots: `{summary.get('captured_or_cached_snapshot_count')}`",
            f"- Estimated full-plan credits: `{summary.get('estimated_full_plan_credits')}`",
            f"- Consensus rows: `{summary.get('historical_consensus_row_count')}`",
            f"- Distinct events: `{summary.get('distinct_event_count')}`",
            f"- Max provider skew: `{summary.get('max_provider_snapshot_skew_seconds')}` seconds",
            "",
            "Research-only paid historical capture. No settlement labels, EV, paper stake, or orders.",
            "",
        ]
    )


def _snapshot_paths(raw_dir: Path, plan_row: Mapping[str, Any]) -> tuple[Path, Path]:
    target = str(plan_row.get("target_time_utc") or "unknown")
    stamp = target.replace("-", "").replace(":", "").replace("+", "").replace("Z", "Z")
    return (
        raw_dir / f"baseball_mlb_historical_{stamp}.json",
        raw_dir / f"baseball_mlb_historical_{stamp}.meta.json",
    )


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in str(value).split(",") if part.strip())


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--archive-path", type=Path, default=DEFAULT_ARCHIVE_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--markets-raw-path", type=Path, default=DEFAULT_MARKETS_RAW_PATH)
    parser.add_argument("--candlesticks-raw-path", type=Path, default=DEFAULT_CANDLESTICKS_RAW_PATH)
    parser.add_argument("--api-key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--bookmakers", default=",".join(DEFAULT_BOOKMAKERS))
    parser.add_argument("--pregame-lead-seconds", type=int, default=3600)
    parser.add_argument("--snapshot-interval-seconds", type=int, default=300)
    parser.add_argument("--max-skew-seconds", type=int, default=180)
    parser.add_argument("--min-distinct-books", type=int, default=2)
    parser.add_argument("--max-snapshots", type=int, default=0)
    parser.add_argument("--max-paid-credits", type=int, default=3000)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--capture-paid", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    markets = load_raw_markets(args.markets_raw_path)
    candles = load_raw_candlesticks(args.candlesticks_raw_path)
    plan, plan_blockers = build_snapshot_plan(
        markets,
        candles,
        pregame_lead_seconds=int(args.pregame_lead_seconds),
        max_snapshots=int(args.max_snapshots),
    )
    api_key = ""
    if args.capture_paid:
        try:
            api_key = args.api_key_file.expanduser().read_text(encoding="utf-8").strip()
        except OSError as exc:
            print(json.dumps({"status": "blocked_missing_api_key", "error": str(exc)}))
            return 70
        if not api_key:
            print(json.dumps({"status": "blocked_missing_api_key"}))
            return 70
    snapshots, capture_errors = acquire_snapshots(
        plan,
        api_key=api_key,
        raw_dir=args.raw_dir,
        bookmakers=_split_csv(args.bookmakers),
        capture_paid=bool(args.capture_paid),
        max_paid_credits=int(args.max_paid_credits),
        snapshot_interval_seconds=int(args.snapshot_interval_seconds),
        timeout_seconds=float(args.timeout_seconds),
    )
    archive, report = assemble_archive(
        plan,
        plan_blockers,
        snapshots,
        capture_errors,
        markets=markets,
        min_distinct_books=int(args.min_distinct_books),
        max_skew_seconds=int(args.max_skew_seconds),
    )
    paths = (
        write_outputs(archive, report, archive_path=args.archive_path, out_dir=args.out_dir)
        if args.write
        else {}
    )
    print(
        json.dumps(
            {"status": report["status"], "summary": report["summary"], **paths},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
