#!/usr/bin/env python3
"""Build live-autonomous Kalshi preflight decisions without submitting orders."""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from kalshi_live_common import (
    DEFAULT_EXTERNAL_PREFLIGHT,
    DEFAULT_PAPER_DECISIONS,
    DEFAULT_RETIREMENT,
    DEFAULT_STATE_DIR,
    MACRO_DIR,
    write_and_print,
)

from predmarket.config import load_config
from predmarket.kalshi_live_engine import (
    build_live_preflight_report,
    normalize_market_snapshot_index,
    paper_usable_tickers,
)
from predmarket.shared_helpers import read_json_or_empty, utc_now

DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-live-preflight-latest"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-decisions-path", type=Path, default=DEFAULT_PAPER_DECISIONS)
    parser.add_argument("--external-preflight-path", type=Path, default=DEFAULT_EXTERNAL_PREFLIGHT)
    parser.add_argument("--retirement-path", type=Path, default=DEFAULT_RETIREMENT)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--market-snapshots-path", type=Path, default=None)
    parser.add_argument("--capture-market-snapshots", action="store_true")
    parser.add_argument("--market-snapshot-depth", type=int, default=10)
    parser.add_argument("--market-snapshot-timeout-seconds", type=float, default=10.0)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--execution-mode", default=None)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def fetch_json_url(url: str, *, timeout_seconds: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def public_market_snapshots(
    *,
    paper_report: dict[str, Any],
    base_url: str,
    depth: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    tickers = sorted(ticker for ticker in paper_usable_tickers(paper_report) if ticker)
    snapshots: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    base = base_url.rstrip("/")
    for ticker in tickers:
        encoded = urllib.parse.quote(ticker, safe="")
        try:
            market_payload = fetch_json_url(
                f"{base}/markets/{encoded}",
                timeout_seconds=timeout_seconds,
            )
            orderbook_payload = fetch_json_url(
                f"{base}/markets/{encoded}/orderbook?depth={int(depth)}",
                timeout_seconds=timeout_seconds,
            )
            snapshots[ticker] = enrich_market_snapshot(market_payload, orderbook_payload)
        except Exception as exc:
            errors.append({"ticker": ticker, "error": str(exc)})
    return {
        "schema_version": 1,
        "generated_utc": utc_now(),
        "status": "kalshi_live_market_snapshots_ready"
        if snapshots
        else "kalshi_live_market_snapshots_empty",
        "summary": {
            "requested_ticker_count": len(tickers),
            "market_snapshot_count": len(snapshots),
            "error_count": len(errors),
            "public_market_data_calls": True,
            "depth": int(depth),
        },
        "market_snapshots": snapshots,
        "errors": errors,
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "authenticated": False,
        },
    }


def enrich_market_snapshot(
    market_payload: dict[str, Any], orderbook_payload: dict[str, Any]
) -> dict[str, Any]:
    market = dict(market_payload.get("market") if isinstance(market_payload.get("market"), dict) else market_payload)
    for side in ("yes", "no"):
        level = selected_side_top_ask(orderbook_payload, side)
        if level is None:
            continue
        market[f"{side}_ask_dollars"] = f"{level['ask_price']:.4f}"
        market[f"{side}_ask_size_fp"] = f"{level['contracts']:.2f}"
    return {"market": market, "orderbook": orderbook_payload}


def selected_side_top_ask(orderbook: dict[str, Any], side: str) -> dict[str, float] | None:
    book = orderbook.get("orderbook_fp") if isinstance(orderbook.get("orderbook_fp"), dict) else {}
    if not book:
        book = orderbook.get("orderbook") if isinstance(orderbook.get("orderbook"), dict) else {}
    bid_key = "no_dollars" if side == "yes" else "yes_dollars"
    legacy_key = "no" if side == "yes" else "yes"
    raw_levels = book.get(bid_key) or book.get(f"{bid_key}_fp") or book.get(legacy_key) or []
    levels: list[dict[str, float]] = []
    for raw_level in raw_levels if isinstance(raw_levels, list) else []:
        if not isinstance(raw_level, list | tuple) or len(raw_level) < 2:
            continue
        bid_price = price_probability(raw_level[0])
        contracts = nonnegative_float(raw_level[1])
        if bid_price is None or contracts is None or contracts <= 0:
            continue
        ask_price = 1.0 - bid_price
        if 0.0 < ask_price <= 1.0:
            levels.append({"ask_price": ask_price, "contracts": contracts})
    return min(levels, key=lambda item: item["ask_price"]) if levels else None


def price_probability(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if 0.0 <= number <= 1.0:
        return number
    if 1.0 < number <= 100.0:
        return number / 100.0
    return None


def nonnegative_float(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number >= 0.0 else None


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config()
    paper_report = read_json_or_empty(args.paper_decisions_path)
    market_snapshots: dict[str, Any] = {}
    if args.market_snapshots_path:
        market_snapshots.update(
            normalize_market_snapshot_index(read_json_or_empty(args.market_snapshots_path))
        )
    if args.capture_market_snapshots:
        capture = public_market_snapshots(
            paper_report=paper_report,
            base_url=config.venues.kalshi.api_url,
            depth=args.market_snapshot_depth,
            timeout_seconds=args.market_snapshot_timeout_seconds,
        )
        market_snapshots.update(normalize_market_snapshot_index(capture))
    report = build_live_preflight_report(
        paper_decisions_path=args.paper_decisions_path,
        external_preflight_path=args.external_preflight_path,
        retirement_path=args.retirement_path,
        state_path=args.state_dir,
        market_snapshots=market_snapshots,
        execution_mode=args.execution_mode,
        config=config,
    )
    if args.write:
        write_and_print(
            report,
            out_dir=args.out_dir,
            stem="kalshi-live-preflight",
            title="Kalshi Live Preflight",
        )
    else:
        import json

        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
