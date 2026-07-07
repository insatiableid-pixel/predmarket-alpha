#!/usr/bin/env python3
"""Record read-only Kalshi sports WebSocket ticks to append-only JSONL."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.config import load_config  # noqa: E402
from predmarket.kalshi_live_client import (  # noqa: E402
    KalshiAuthError,
    trading_client_config_from_app_config,
)
from predmarket.kalshi_websocket import (  # noqa: E402
    KalshiWebSocketClient,
    RawWebSocketMessage,
)
from predmarket.shared_helpers import (  # noqa: E402
    counts,
    path_is_within,
    read_json_or_empty,
    safe_stamp,
    safety_flags,
    sha256_or_none,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-tick-recorder-latest"
DEFAULT_JSONL_DIR = Path("/home/mrwatson/manual_drops/kalshi_ticks")
DEFAULT_UNIVERSE_PATH = MACRO_DIR / "latest-kalshi-universe-scan.json"
SPORT_CLASSIFICATIONS = {"mlb", "atp", "nfl", "nba", "other_sports", "world_cup"}
SPORT_SERIES_PREFIXES = ("KXMLB", "KXATP", "KXWIM", "KXWC", "KXFIFA", "KXNFL", "KXNBA")


@dataclass
class RecorderStats:
    line_count: int = 0
    gap_count: int = 0
    max_gap_seconds: float = 0.0
    first_received_utc: str | None = None
    last_received_utc: str | None = None
    previous_monotonic: float | None = None


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def select_sports_tickers(
    universe: Mapping[str, Any],
    *,
    explicit_tickers: Sequence[str] = (),
    max_tickers: int = 250,
) -> list[str]:
    if explicit_tickers:
        return dedupe_tickers(explicit_tickers)[: max(0, max_tickers)]
    rows = market_rows(universe)
    tickers: list[str] = []
    for row in rows:
        ticker = str(row.get("ticker") or row.get("contract_ticker") or "").strip()
        if not ticker or not is_sports_row(row, ticker):
            continue
        tickers.append(ticker)
    return dedupe_tickers(tickers)[: max(0, max_tickers)]


def market_rows(universe: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in ("all_scored", "candidates", "markets", "rows", "top_50"):
        value = universe.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, Mapping)]
    return []


def is_sports_row(row: Mapping[str, Any], ticker: str) -> bool:
    classification = str(row.get("classification") or "").strip().lower()
    series = str(row.get("series_ticker") or ticker.split("-", 1)[0]).upper()
    if classification in SPORT_CLASSIFICATIONS:
        return True
    return series.startswith(SPORT_SERIES_PREFIXES)


def dedupe_tickers(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        ticker = str(value).strip()
        if ticker and ticker not in seen:
            seen.add(ticker)
            output.append(ticker)
    return output


async def record_ticks(
    *,
    tickers: Sequence[str],
    channels: Sequence[str],
    jsonl_path: Path,
    duration_seconds: float,
    max_gap_seconds: float,
    execution_mode: str,
) -> dict[str, Any]:
    generated = utc_now()
    if not tickers:
        return recorder_report(
            generated_utc=generated,
            status="kalshi_tick_recorder_blocked_no_sports_tickers",
            tickers=[],
            channels=channels,
            jsonl_path=jsonl_path,
            stats=RecorderStats(),
            authenticated=False,
            error=None,
        )
    try:
        config = trading_client_config_from_app_config(load_config(), execution_mode=execution_mode)
        client = KalshiWebSocketClient(config)
    except (KalshiAuthError, OSError, ValueError) as exc:
        return recorder_report(
            generated_utc=generated,
            status="kalshi_tick_recorder_blocked_missing_or_invalid_auth",
            tickers=tickers,
            channels=channels,
            jsonl_path=jsonl_path,
            stats=RecorderStats(),
            authenticated=False,
            error=f"{type(exc).__name__}: {exc}",
        )
    stats = RecorderStats()
    try:
        async with client:
            await client.subscribe(list(tickers), channels=channels)
            await drain_messages(
                client.raw_messages(),
                jsonl_path=jsonl_path,
                duration_seconds=duration_seconds,
                max_gap_seconds=max_gap_seconds,
                stats=stats,
            )
    except Exception as exc:
        return recorder_report(
            generated_utc=generated,
            status="kalshi_tick_recorder_failed_runtime_error",
            tickers=tickers,
            channels=channels,
            jsonl_path=jsonl_path,
            stats=stats,
            authenticated=True,
            error=f"{type(exc).__name__}: {exc}",
        )
    return recorder_report(
        generated_utc=generated,
        status="kalshi_tick_recorder_ready",
        tickers=tickers,
        channels=channels,
        jsonl_path=jsonl_path,
        stats=stats,
        authenticated=True,
        error=None,
    )


async def drain_messages(
    messages: AsyncIterator[RawWebSocketMessage],
    *,
    jsonl_path: Path,
    duration_seconds: float,
    max_gap_seconds: float,
    stats: RecorderStats,
) -> None:
    deadline = time.monotonic() + max(0.0, duration_seconds)
    while time.monotonic() < deadline:
        timeout = max(0.05, min(5.0, deadline - time.monotonic()))
        try:
            message = await asyncio.wait_for(anext(messages), timeout=timeout)
        except TimeoutError:
            continue
        append_message(jsonl_path, message, stats=stats, max_gap_seconds=max_gap_seconds)


def append_message(
    path: Path,
    message: RawWebSocketMessage | Mapping[str, Any],
    *,
    stats: RecorderStats,
    max_gap_seconds: float,
) -> None:
    now_mono = time.monotonic()
    if stats.previous_monotonic is not None:
        gap = now_mono - stats.previous_monotonic
        stats.max_gap_seconds = max(stats.max_gap_seconds, gap)
        if gap > max_gap_seconds:
            stats.gap_count += 1
    stats.previous_monotonic = now_mono
    received = getattr(message, "received_at_utc", None) or str(message.get("received_at_utc"))
    text = getattr(message, "text", None) or str(message.get("text") or "")
    payload = getattr(message, "payload", None)
    if payload is None and isinstance(message, Mapping):
        payload = message.get("payload")
    row = {
        "received_at_utc": received,
        "type": payload.get("type") if isinstance(payload, Mapping) else None,
        "sid": payload.get("sid") if isinstance(payload, Mapping) else None,
        "raw_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "raw_text": text,
        "payload": payload if isinstance(payload, Mapping) else None,
        "research_only": True,
        "execution_enabled": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str) + "\n")
    stats.line_count += 1
    stats.first_received_utc = stats.first_received_utc or received
    stats.last_received_utc = received


def recorder_report(
    *,
    generated_utc: str,
    status: str,
    tickers: Sequence[str],
    channels: Sequence[str],
    jsonl_path: Path,
    stats: RecorderStats,
    authenticated: bool,
    error: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_utc": generated_utc,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": bool(authenticated),
        "authenticated_api_calls": bool(authenticated),
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "inputs": {
            "jsonl_path": str(jsonl_path),
            "jsonl_sha256": sha256_or_none(jsonl_path),
            "ticker_count": len(tickers),
            "channels": list(channels),
        },
        "summary": {
            "recorded_line_count": stats.line_count,
            "gap_count": stats.gap_count,
            "max_gap_seconds": round(stats.max_gap_seconds, 6),
            "first_received_utc": stats.first_received_utc,
            "last_received_utc": stats.last_received_utc,
            "ticker_count": len(tickers),
            "channel_counts": counts(channels),
            "error": error,
        },
        "tickers_sample": list(tickers[:50]),
        "next_action": next_action(status),
        "safety": {
            **safety_flags(public_market_data_calls=bool(authenticated)),
            "authenticated_api_calls": bool(authenticated),
            "account_or_order_paths": False,
            "market_execution": False,
        },
    }


def next_action(status: str) -> dict[str, str]:
    if status == "kalshi_tick_recorder_ready":
        return {
            "name": "kalshi_stale_quote_feature_packet_after_72h_capture",
            "why": "Raw tick capture has started; wait for enough proprietary tick history before hypothesis testing.",
            "stop_condition": "Stop before fitting stale-quote rules until rules are pre-registered.",
        }
    return {
        "name": "kalshi_tick_recorder_input_or_auth_repair",
        "why": "Stale-quote evidence cannot accrue until read-only sports tick recording is running.",
        "stop_condition": "Stop before live/account/order paths.",
    }


def write_outputs(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-tick-recorder.json"
    md_path = out_dir / "kalshi-tick-recorder.md"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    paths = {"json_path": str(json_path), "markdown_path": str(md_path)}
    if path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-tick-recorder.json"
        latest_md = MACRO_DIR / "latest-kalshi-tick-recorder.md"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        paths.update({"latest_json_path": str(latest_json), "latest_markdown_path": str(latest_md)})
    return paths


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Tick Recorder",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Tickers: `{summary.get('ticker_count')}`",
        f"- Recorded lines: `{summary.get('recorded_line_count')}`",
        f"- Gaps: `{summary.get('gap_count')}`",
        f"- JSONL: `{report.get('inputs', {}).get('jsonl_path')}`",
        "",
        "Read-only evidence capture. No orders, balances, accounts, EV, or paper stake.",
        "",
    ]
    return "\n".join(lines)


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--jsonl-dir", type=Path, default=DEFAULT_JSONL_DIR)
    parser.add_argument("--universe-path", type=Path, default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument("--tickers", default="")
    parser.add_argument("--channels", default="ticker,orderbook_delta")
    parser.add_argument("--max-tickers", type=int, default=250)
    parser.add_argument("--duration-seconds", type=float, default=300.0)
    parser.add_argument("--max-gap-seconds", type=float, default=30.0)
    parser.add_argument("--execution-mode", default="live")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


async def async_main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    generated = utc_now()
    explicit = parse_csv(args.tickers)
    universe = read_json_or_empty(args.universe_path)
    tickers = select_sports_tickers(
        universe,
        explicit_tickers=explicit,
        max_tickers=args.max_tickers,
    )
    jsonl_path = args.jsonl_dir / f"kalshi_sports_ticks_{safe_stamp(generated)}.jsonl"
    report = await record_ticks(
        tickers=tickers,
        channels=parse_csv(args.channels),
        jsonl_path=jsonl_path,
        duration_seconds=args.duration_seconds,
        max_gap_seconds=args.max_gap_seconds,
        execution_mode=args.execution_mode,
    )
    if args.write:
        paths = write_outputs(report, args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
