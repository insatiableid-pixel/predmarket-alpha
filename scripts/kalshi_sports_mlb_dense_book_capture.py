#!/usr/bin/env python3
"""Read-only dense MLB moneyline orderbook capture for fixed-clock research.

Captures public top-of-book and orderbook_fp ladders for open KXMLBGAME markets.
Research-only: no accounts, orders, sizing, or live execution.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import manual_drop_path, utc_now  # noqa: E402

KALSHI_PUBLIC_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
DEFAULT_OUT_DIR = manual_drop_path(
    "kalshi_sports_mlb_fixed_clock_books",
    env_vars=("KALSHI_SPORTS_MLB_DENSE_BOOK_DIR",),
)


def fetch_json(url: str, *, timeout: float = 30.0) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "predmarket-research-mlb-dense-books/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object from {url}")
    return payload


def list_open_mlb(*, limit: int = 200) -> list[dict[str, Any]]:
    markets: list[dict[str, Any]] = []
    cursor: str | None = None
    while len(markets) < limit:
        params: dict[str, str] = {
            "series_ticker": "KXMLBGAME",
            "status": "open",
            "limit": str(min(200, limit - len(markets))),
        }
        if cursor:
            params["cursor"] = cursor
        payload = fetch_json(
            f"{KALSHI_PUBLIC_BASE_URL}/markets?{urllib.parse.urlencode(params)}"
        )
        batch = payload.get("markets") or []
        if not isinstance(batch, list) or not batch:
            break
        markets.extend([dict(row) for row in batch if isinstance(row, Mapping)])
        cursor = payload.get("cursor")
        if not cursor:
            break
        time.sleep(0.08)
    return markets[:limit]


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_orderbook_fp(payload: Mapping[str, Any]) -> dict[str, float | None]:
    book = payload.get("orderbook_fp") or payload.get("orderbook") or payload
    yes_levels = book.get("yes_dollars") or book.get("yes") or []
    no_levels = book.get("no_dollars") or book.get("no") or []

    def best_bid(levels: Sequence[Any]) -> tuple[float | None, float | None]:
        parsed: list[tuple[float, float]] = []
        for level in levels:
            if isinstance(level, (list, tuple)) and len(level) >= 2:
                price = _float(level[0])
                size = _float(level[1])
                if price is None or size is None:
                    continue
                if price > 1.0:
                    price = price / 100.0
                parsed.append((price, size))
        if not parsed:
            return None, None
        parsed.sort(key=lambda item: item[0], reverse=True)
        return parsed[0][0], parsed[0][1]

    yes_bid, yes_bid_depth = best_bid(yes_levels if isinstance(yes_levels, list) else [])
    no_bid, no_bid_depth = best_bid(no_levels if isinstance(no_levels, list) else [])
    yes_ask = (1.0 - no_bid) if no_bid is not None else None
    no_ask = (1.0 - yes_bid) if yes_bid is not None else None
    return {
        "best_yes_bid": yes_bid,
        "best_yes_ask": yes_ask,
        "best_no_bid": no_bid,
        "best_no_ask": no_ask,
        "yes_bid_depth_top1": yes_bid_depth,
        "yes_ask_depth_top1": no_bid_depth,
        "no_bid_depth_top1": no_bid_depth,
        "no_ask_depth_top1": yes_bid_depth,
    }


def market_top_of_book(market: Mapping[str, Any]) -> dict[str, float | None]:
    yes_bid = _float(market.get("yes_bid_dollars", market.get("yes_bid")))
    yes_ask = _float(market.get("yes_ask_dollars", market.get("yes_ask")))
    no_bid = _float(market.get("no_bid_dollars", market.get("no_bid")))
    no_ask = _float(market.get("no_ask_dollars", market.get("no_ask")))
    return {
        "best_yes_bid": yes_bid,
        "best_yes_ask": yes_ask,
        "best_no_bid": no_bid,
        "best_no_ask": no_ask,
        "yes_bid_depth_top1": _float(market.get("yes_bid_size_fp")),
        "yes_ask_depth_top1": _float(market.get("yes_ask_size_fp")),
        "no_bid_depth_top1": None,
        "no_ask_depth_top1": None,
    }


def capture_rows(
    markets: Sequence[Mapping[str, Any]],
    *,
    fetch_orderbook: bool = True,
    request_delay_seconds: float = 0.08,
    generated_utc: str | None = None,
) -> list[dict[str, Any]]:
    generated = generated_utc or utc_now()
    rows: list[dict[str, Any]] = []
    for market in markets:
        ticker = str(market.get("ticker") or "").strip()
        if not ticker.startswith("KXMLBGAME"):
            continue
        quotes = market_top_of_book(market)
        if fetch_orderbook:
            try:
                payload = fetch_json(
                    f"{KALSHI_PUBLIC_BASE_URL}/markets/"
                    f"{urllib.parse.quote(ticker, safe='')}/orderbook"
                )
                ladder = parse_orderbook_fp(payload)
                # Prefer explicit market top-of-book prices when present; fill depth from ladder.
                for key, value in ladder.items():
                    if quotes.get(key) is None and value is not None:
                        quotes[key] = value
                    if key.endswith("depth_top1") and value is not None:
                        quotes[key] = value
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
                pass
            if request_delay_seconds > 0:
                time.sleep(request_delay_seconds)
        yes_bid = quotes.get("best_yes_bid")
        yes_ask = quotes.get("best_yes_ask")
        mid = None
        if yes_bid is not None and yes_ask is not None:
            mid = (float(yes_bid) + float(yes_ask)) / 2.0
        rows.append(
            {
                "snapshot_id": f"dense|{ticker}|{generated}",
                "contract_ticker": ticker,
                "event_ticker": market.get("event_ticker"),
                "series_ticker": "KXMLBGAME",
                "observed_at_utc": generated,
                "best_yes_bid": yes_bid,
                "best_yes_ask": yes_ask,
                "best_no_bid": quotes.get("best_no_bid"),
                "best_no_ask": quotes.get("best_no_ask"),
                "yes_bid_depth_top1": quotes.get("yes_bid_depth_top1"),
                "yes_ask_depth_top1": quotes.get("yes_ask_depth_top1"),
                "no_bid_depth_top1": quotes.get("no_bid_depth_top1"),
                "no_ask_depth_top1": quotes.get("no_ask_depth_top1"),
                "yes_mid": mid,
                "yes_spread": (
                    None
                    if yes_bid is None or yes_ask is None
                    else float(yes_ask) - float(yes_bid)
                ),
                "open_time": market.get("open_time"),
                "created_time": market.get("created_time"),
                "occurrence_datetime": market.get("occurrence_datetime"),
                "expected_expiration_time": market.get("expected_expiration_time"),
                "entry_source": "dense_public_orderbook",
                "usable": False,
                "research_only": True,
                "execution_enabled": False,
            }
        )
    return rows


def write_packet(rows: Sequence[Mapping[str, Any]], *, out_dir: Path, generated_utc: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = generated_utc.replace(":", "").replace("-", "")
    payload = {
        "generated_utc": generated_utc,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "packet_type": "kalshi_mlb_dense_fixed_clock_books",
        "rows": list(rows),
        "count": len(rows),
    }
    path = out_dir / f"mlb_dense_books_{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "mlb_dense_books_latest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--fetch-orderbook", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--request-delay-seconds", type=float, default=0.08)
    args = parser.parse_args(argv)
    generated = utc_now()
    try:
        markets = list_open_mlb(limit=int(args.limit))
        rows = capture_rows(
            markets,
            fetch_orderbook=bool(args.fetch_orderbook),
            request_delay_seconds=float(args.request_delay_seconds),
            generated_utc=generated,
        )
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    path = write_packet(rows, out_dir=args.out_dir, generated_utc=generated)
    print(
        json.dumps(
            {
                "status": "mlb_dense_book_capture_ready",
                "generated_utc": generated,
                "market_count": len(markets),
                "row_count": len(rows),
                "with_yes_ask": sum(1 for row in rows if row.get("best_yes_ask") is not None),
                "path": str(path),
                "research_only": True,
                "execution_enabled": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
