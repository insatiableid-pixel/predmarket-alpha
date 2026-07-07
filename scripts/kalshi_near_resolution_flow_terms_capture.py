#!/usr/bin/env python3
"""Capture official Kalshi terms for near-resolution flow candidates.

The flow replay gate can prove a signal statistically, but the EV ledger will
not promote any row without verified official contract terms. This script
captures public Kalshi market-detail payloads for current flow capacity rows
and writes them outside the repo using the existing ``kalshi_scored*`` filename
convention so the EV ledger's official-terms index can consume them.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import (  # noqa: E402
    manual_drop_path,
    outside_repo,
    read_json_or_empty,
    safe_stamp,
    safety_flags,
    sha256_or_none,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
KALSHI_PUBLIC_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
DEFAULT_FLOW_REPLAY_PATH = MACRO_DIR / "latest-kalshi-near-resolution-flow-replay-gates.json"
DEFAULT_RAW_TERMS_DIR = manual_drop_path("kalshi")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-near-resolution-flow-terms-capture-latest"
DEFAULT_MAX_MARKETS = 120
DEFAULT_DELAY_SECONDS = 0.03
CSV_FIELDS = [
    "ticker",
    "event_ticker",
    "status",
    "rules_present",
    "rules_primary_length",
    "rules_secondary_length",
    "source_status",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_flow_terms_capture(
    *,
    flow_replay_path: Path = DEFAULT_FLOW_REPLAY_PATH,
    raw_terms_dir: Path = DEFAULT_RAW_TERMS_DIR,
    generated_utc: str | None = None,
    max_markets: int = DEFAULT_MAX_MARKETS,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    capture_terms: bool = False,
    fetch_json: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    flow = read_json_or_empty(flow_replay_path)
    selected_tickers = flow_capacity_tickers(flow, max_markets=max_markets)
    if capture_terms:
        capture = capture_public_market_terms(
            tickers=selected_tickers,
            raw_terms_dir=raw_terms_dir,
            generated_utc=generated,
            delay_seconds=delay_seconds,
            fetch_json=fetch_json,
        )
    else:
        capture = load_latest_terms_capture(raw_terms_dir)
    markets = capture_markets(capture)
    market_rows = [market_row(market) for market in markets]
    target_set = set(selected_tickers)
    captured_set = {str(row.get("ticker") or "") for row in market_rows}
    rules_count = sum(1 for row in market_rows if row.get("rules_present"))
    summary = {
        "selected_ticker_count": len(selected_tickers),
        "captured_market_count": len(markets),
        "captured_target_count": len(target_set & captured_set),
        "missing_target_count": len(target_set - captured_set),
        "official_rules_market_count": rules_count,
        "raw_terms_path": capture.get("path"),
        "raw_terms_sha256": sha256_or_none(Path(str(capture.get("path") or ""))),
        "raw_terms_outside_repo": outside_repo(raw_terms_dir, CONTROL_REPO),
    }
    gates = build_gates(summary)
    status = report_status(gates)
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": bool(capture_terms),
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "inputs": {
            "flow_replay_path": str(flow_replay_path),
            "flow_replay_sha256": sha256_or_none(flow_replay_path),
            "flow_replay_status": flow.get("status"),
            "raw_terms_dir": str(raw_terms_dir),
            "max_markets": max_markets,
            "capture_terms": capture_terms,
        },
        "summary": summary,
        "gates": gates,
        "market_rows": market_rows,
        "missing_tickers": sorted(target_set - captured_set),
        "next_action": next_action(status),
        "safety": safety_flags(public_market_data_calls=bool(capture_terms)),
    }


def flow_capacity_tickers(flow: Mapping[str, Any], *, max_markets: int) -> list[str]:
    rows = flow.get("capacity_rows") if isinstance(flow.get("capacity_rows"), list) else []
    tickers: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if row.get("gate_status") != "pass":
            continue
        ticker = str(row.get("contract_ticker") or "").strip()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        tickers.append(ticker)
        if len(tickers) >= max(0, int(max_markets)):
            break
    return tickers


def capture_public_market_terms(
    *,
    tickers: Sequence[str],
    raw_terms_dir: Path,
    generated_utc: str,
    delay_seconds: float,
    fetch_json: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    raw_terms_dir.mkdir(parents=True, exist_ok=True)
    fetch = fetch_json or fetch_public_json
    markets: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for ticker in tickers:
        url = f"{KALSHI_PUBLIC_BASE_URL}/markets/{urllib.parse.quote(ticker, safe='')}"
        try:
            payload = fetch(url)
        except Exception as exc:  # pragma: no cover - network failures are exercised via fakes.
            errors.append({"ticker": ticker, "error": str(exc)})
            continue
        market = payload.get("market") if isinstance(payload, Mapping) else None
        if isinstance(market, Mapping):
            markets.append(dict(market))
        else:
            errors.append({"ticker": ticker, "error": "response missing market object"})
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    capture = {
        "schema_version": 1,
        "captured_at_utc": generated_utc,
        "source": "kalshi_public_market_details",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "ticker_count": len(tickers),
        "market_count": len(markets),
        "error_count": len(errors),
        "markets": markets,
        "all_scored": markets,
        "errors": errors,
        "safety": safety_flags(public_market_data_calls=True),
    }
    stamp = safe_stamp(generated_utc)
    path = raw_terms_dir / f"kalshi_scored_sports_flow_terms_{stamp}.json"
    latest = raw_terms_dir / "kalshi_scored_sports_flow_terms_latest.json"
    text = json.dumps(capture, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    capture["path"] = str(path)
    capture["latest_path"] = str(latest)
    return capture


def fetch_public_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def load_latest_terms_capture(raw_terms_dir: Path) -> dict[str, Any]:
    latest = raw_terms_dir / "kalshi_scored_sports_flow_terms_latest.json"
    if latest.exists():
        raw = read_json_or_empty(latest)
        raw["path"] = str(latest)
        return raw
    paths = sorted(raw_terms_dir.glob("kalshi_scored_sports_flow_terms_*.json"))
    if not paths:
        return {"markets": [], "all_scored": [], "path": None}
    raw = read_json_or_empty(paths[-1])
    raw["path"] = str(paths[-1])
    return raw


def capture_markets(capture: Mapping[str, Any]) -> list[dict[str, Any]]:
    markets = capture.get("markets")
    if not isinstance(markets, list):
        markets = capture.get("all_scored")
    if not isinstance(markets, list):
        return []
    return [dict(row) for row in markets if isinstance(row, Mapping)]


def market_row(market: Mapping[str, Any]) -> dict[str, Any]:
    rules_primary = str(market.get("rules_primary") or "")
    rules_secondary = str(market.get("rules_secondary") or "")
    return {
        "ticker": str(market.get("ticker") or ""),
        "event_ticker": str(market.get("event_ticker") or ""),
        "status": str(market.get("status") or ""),
        "rules_present": bool(rules_primary.strip() or rules_secondary.strip()),
        "rules_primary_length": len(rules_primary.strip()),
        "rules_secondary_length": len(rules_secondary.strip()),
        "source_status": "official_terms_present"
        if rules_primary.strip() or rules_secondary.strip()
        else "official_terms_missing",
    }


def build_gates(summary: Mapping[str, Any]) -> list[dict[str, str]]:
    selected = int(summary.get("selected_ticker_count") or 0)
    captured_targets = int(summary.get("captured_target_count") or 0)
    rules = int(summary.get("official_rules_market_count") or 0)
    outside = summary.get("raw_terms_outside_repo") is True
    return [
        gate("flow_capacity_tickers_present", "pass" if selected else "blocked"),
        gate("terms_capture_outside_repo", "pass" if outside else "fail"),
        gate(
            "target_market_details_captured",
            "pass" if selected and captured_targets == selected else "blocked",
        ),
        gate("official_rules_present", "pass" if selected and rules >= selected else "blocked"),
    ]


def gate(name: str, status: str) -> dict[str, str]:
    return {"name": name, "status": status}


def report_status(gates: Sequence[Mapping[str, str]]) -> str:
    if any(gate.get("status") == "fail" for gate in gates):
        return "near_resolution_flow_terms_capture_failed_safety_gate"
    if all(gate.get("status") == "pass" for gate in gates):
        return "near_resolution_flow_terms_capture_ready"
    return "near_resolution_flow_terms_capture_blocked_missing_terms"


def next_action(status: str) -> dict[str, str]:
    if status == "near_resolution_flow_terms_capture_ready":
        return {
            "name": "kalshi_ev_ledger",
            "why": "Official terms are captured under the EV ledger's local terms convention.",
            "stop_condition": "Stop before paper/live execution if EV ledger or paper gates still block.",
        }
    return {
        "name": "kalshi_near_resolution_flow_terms_capture",
        "why": "Official terms are still missing for one or more current flow candidates.",
        "stop_condition": "Stop before inferring rules from titles or unofficial sources.",
    }


def write_report(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-near-resolution-flow-terms-capture.json"
    md_path = out_dir / "kalshi-near-resolution-flow-terms-capture.md"
    csv_path = out_dir / "kalshi-near-resolution-flow-terms-capture.csv"
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("market_rows") if isinstance(report.get("market_rows"), list) else [], csv_path)
    latest_json = MACRO_DIR / "latest-kalshi-near-resolution-flow-terms-capture.json"
    latest_md = MACRO_DIR / "latest-kalshi-near-resolution-flow-terms-capture.md"
    latest_csv = MACRO_DIR / "latest-kalshi-near-resolution-flow-terms-capture.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("market_rows") if isinstance(report.get("market_rows"), list) else [], latest_csv)
    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
        "latest_csv_path": str(latest_csv),
    }


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    import csv

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Near-Resolution Flow Terms Capture",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Selected tickers: `{summary.get('selected_ticker_count')}`",
        f"- Captured targets: `{summary.get('captured_target_count')}`",
        f"- Markets with official rules: `{summary.get('official_rules_market_count')}`",
        f"- Raw terms path: `{summary.get('raw_terms_path')}`",
        "",
        "## Gates",
        "",
        "| Gate | Status |",
        "| --- | --- |",
    ]
    for item in report.get("gates", []):
        lines.append(f"| `{item.get('name')}` | `{item.get('status')}` |")
    lines.extend(["", "## Next Action", "", str(report.get("next_action") or ""), ""])
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flow-replay-path", type=Path, default=DEFAULT_FLOW_REPLAY_PATH)
    parser.add_argument("--raw-terms-dir", type=Path, default=DEFAULT_RAW_TERMS_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-markets", type=int, default=DEFAULT_MAX_MARKETS)
    parser.add_argument("--delay-seconds", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--capture-terms", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_flow_terms_capture(
        flow_replay_path=args.flow_replay_path,
        raw_terms_dir=args.raw_terms_dir,
        max_markets=args.max_markets,
        delay_seconds=args.delay_seconds,
        capture_terms=args.capture_terms,
    )
    if args.write:
        paths = write_report(report, args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
