"""Capture Kalshi market-data snapshots for manual-drop workflows."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from predmarket.config import load_config
from predmarket.kalshi_dataset import KalshiMarketDataClient

DEFAULT_MLB_SERIES = (
    "KXMLBGAME",
    "KXMLBTOTAL",
    "KXMLBSPREAD",
    "KXMLBF5",
    "KXMLBF5TOTAL",
    "KXMLBF5SPREAD",
)

SERIES_SNAPSHOT_PREFIXES = {
    ("KXNFLGAME",): "kalshi_nfl_game_series",
    ("KXWCGAME",): "kalshi_world_cup_game_series",
}


@dataclass(frozen=True)
class KalshiManualDropCaptureArtifacts:
    snapshot: dict[str, Any]
    report: dict[str, Any]
    snapshot_path: Path
    latest_path: Path
    report_json_path: Path
    report_markdown_path: Path


async def capture_kalshi_market_snapshot(
    *,
    series_tickers: Sequence[str] = DEFAULT_MLB_SERIES,
    status: str = "open",
    limit: int = 100,
    max_pages: int = 1,
    delay_seconds: float = 0.75,
    created_ts: float | None = None,
    client: KalshiMarketDataClient | None = None,
) -> dict[str, Any]:
    ts = float(created_ts or time.time())
    created_at = _iso_ts(ts)
    all_markets: list[dict[str, Any]] = []
    series_counts: dict[str, int] = {}
    series_errors: dict[str, str] = {}

    if client is not None:
        for series in series_tickers:
            await _capture_series(
                client,
                series,
                status=status,
                limit=limit,
                max_pages=max_pages,
                all_markets=all_markets,
                series_counts=series_counts,
                series_errors=series_errors,
            )
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
    else:
        config = load_config()
        async with KalshiMarketDataClient(config) as live_client:
            for series in series_tickers:
                await _capture_series(
                    live_client,
                    series,
                    status=status,
                    limit=limit,
                    max_pages=max_pages,
                    all_markets=all_markets,
                    series_counts=series_counts,
                    series_errors=series_errors,
                )
                if delay_seconds > 0:
                    await asyncio.sleep(delay_seconds)

    all_markets.sort(
        key=lambda row: (str(row.get("event_ticker") or ""), str(row.get("ticker") or ""))
    )
    return {
        "schema_version": 1,
        "created_at_utc": created_at,
        "status": "kalshi_manual_drop_public_fetch_ok"
        if all_markets
        else "kalshi_manual_drop_public_fetch_empty",
        "research_only": True,
        "execution_enabled": False,
        "safety": {
            "market_data_calls": True,
            "account_or_order_paths": False,
            "market_execution": False,
            "database_writes": False,
            "paid_calls": False,
            "raw_secrets_copied": False,
        },
        "series_tickers": list(series_tickers),
        "series_counts": series_counts,
        "series_errors": series_errors,
        "market_count": len(all_markets),
        "all_scored": all_markets,
    }


async def _capture_series(
    client: KalshiMarketDataClient,
    series: str,
    *,
    status: str,
    limit: int,
    max_pages: int,
    all_markets: list[dict[str, Any]],
    series_counts: dict[str, int],
    series_errors: dict[str, str],
) -> None:
    try:
        markets = await client.fetch_markets(
            status=status, limit=limit, max_pages=max_pages, series_ticker=series
        )
    except Exception as exc:
        series_counts[series] = 0
        series_errors[series] = str(exc)
        return
    series_counts[series] = len(markets)
    all_markets.extend(dict(market) for market in markets if isinstance(market, Mapping))


def build_capture_report(
    snapshot: Mapping[str, Any],
    *,
    snapshot_path: Path | None = None,
    latest_path: Path | None = None,
) -> dict[str, Any]:
    series_errors = (
        snapshot.get("series_errors") if isinstance(snapshot.get("series_errors"), Mapping) else {}
    )
    return {
        "schema_version": 1,
        "created_at_utc": snapshot.get("created_at_utc"),
        "status": "kalshi_manual_drop_capture_written"
        if snapshot.get("market_count")
        else "kalshi_manual_drop_capture_empty",
        "research_only": True,
        "execution_enabled": False,
        "safety": dict(snapshot.get("safety") or {}),
        "outputs": {
            "snapshot_path": str(snapshot_path) if snapshot_path else None,
            "latest_path": str(latest_path) if latest_path else None,
        },
        "summary": {
            "market_count": snapshot.get("market_count", 0),
            "series_counts": snapshot.get("series_counts", {}),
            "series_error_count": len(series_errors),
            "series_errors": dict(series_errors),
        },
    }


def write_capture_artifacts(
    snapshot: Mapping[str, Any],
    *,
    output_dir: Path,
    latest_path: Path,
    report_dir: Path,
    run_id: str = "kalshi-manual-drop-capture-latest",
) -> KalshiManualDropCaptureArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = (
        str(snapshot.get("created_at_utc") or _iso_ts(time.time()))
        .replace("-", "")
        .replace(":", "")
        .replace("+00:00", "Z")
    )
    stamp = stamp.replace("T", "T").replace("Z", "Z")
    snapshot_prefix = _snapshot_prefix(snapshot)
    snapshot_path = output_dir / f"{snapshot_prefix}_{stamp}.json"
    text = json.dumps(snapshot, indent=2, sort_keys=True, default=str) + "\n"
    snapshot_path.write_text(text, encoding="utf-8")
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(text, encoding="utf-8")
    report = build_capture_report(snapshot, snapshot_path=snapshot_path, latest_path=latest_path)
    report_json_path = report_dir / f"{run_id}.json"
    report_markdown_path = report_dir / f"{run_id}.md"
    report_json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    report_markdown_path.write_text(render_capture_report_markdown(report), encoding="utf-8")
    return KalshiManualDropCaptureArtifacts(
        snapshot=dict(snapshot),
        report=report,
        snapshot_path=snapshot_path,
        latest_path=latest_path,
        report_json_path=report_json_path,
        report_markdown_path=report_markdown_path,
    )


def _snapshot_prefix(snapshot: Mapping[str, Any]) -> str:
    series = tuple(str(value) for value in snapshot.get("series_tickers") or ())
    if series == DEFAULT_MLB_SERIES:
        return "kalshi_mlb_game_series"
    if series in SERIES_SNAPSHOT_PREFIXES:
        return SERIES_SNAPSHOT_PREFIXES[series]
    if series:
        normalized = "_".join(_normalize_series_part(value) for value in series)
        return f"kalshi_{normalized}_series"
    return "kalshi_manual_drop_series"


def _normalize_series_part(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    return "_".join(part for part in normalized.split("_") if part) or "unknown"


def render_capture_report_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Kalshi Manual Drop Capture",
        "",
        f"- Created at UTC: `{report.get('created_at_utc', '')}`",
        "- Mode: research-only market data",
        "- Execution enabled: false",
        f"- Status: `{report.get('status', '')}`",
        "",
        "## Summary",
        "",
        f"- Markets captured: {summary.get('market_count', 0)}",
        f"- Series counts: `{summary.get('series_counts', {})}`",
        f"- Series errors: {summary.get('series_error_count', 0)}",
        "",
        "## Outputs",
        "",
        f"- Snapshot: `{report.get('outputs', {}).get('snapshot_path')}`",
        f"- Latest: `{report.get('outputs', {}).get('latest_path')}`",
    ]
    errors = summary.get("series_errors", {}) if isinstance(summary, Mapping) else {}
    if errors:
        lines.extend(["", "## Series Errors", ""])
        for series, error in dict(errors).items():
            lines.append(f"- `{series}`: {error}")
    lines.extend(
        [
            "",
            "## Guardrail",
            "",
            "This capture contains market data only. It does not authorize execution or account activity.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _iso_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


async def _async_main(args: argparse.Namespace) -> KalshiManualDropCaptureArtifacts:
    snapshot = await capture_kalshi_market_snapshot(
        series_tickers=tuple(args.series_tickers.split(",")),
        status=args.status,
        limit=args.limit,
        max_pages=args.max_pages,
        delay_seconds=args.delay_seconds,
    )
    return write_capture_artifacts(
        snapshot,
        output_dir=Path(args.output_dir),
        latest_path=Path(args.latest_path),
        report_dir=Path(args.report_dir),
        run_id=args.run_id,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture Kalshi MLB game-series market data into manual_drops."
    )
    parser.add_argument("--series-tickers", default=",".join(DEFAULT_MLB_SERIES))
    parser.add_argument("--status", default="open")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--delay-seconds", type=float, default=0.75)
    parser.add_argument("--output-dir", default="/home/mrwatson/manual_drops/kalshi")
    parser.add_argument(
        "--latest-path",
        default="/home/mrwatson/manual_drops/kalshi/kalshi_mlb_game_series_latest.json",
    )
    parser.add_argument(
        "--report-dir", default="docs/codex/artifacts/kalshi-manual-drop-capture-latest"
    )
    parser.add_argument("--run-id", default="kalshi-manual-drop-capture-latest")
    args = parser.parse_args(argv)
    artifacts = asyncio.run(_async_main(args))
    print(
        json.dumps(
            {
                "status": artifacts.report.get("status"),
                "snapshot_path": str(artifacts.snapshot_path),
                "latest_path": str(artifacts.latest_path),
                "report_json_path": str(artifacts.report_json_path),
                "report_markdown_path": str(artifacts.report_markdown_path),
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
