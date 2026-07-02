#!/usr/bin/env python3
"""Scout fast-settling Kalshi routes for calibrated-probability breadth.

This sits between the public universe scanner and any model/EV work. It asks:
which market families can teach us fastest while pending OOS observations wait
for settlement, and what exact data source gap must be solved before modeling?

The report is inventory and source readiness only. It does not compute EV,
does not create calibrated probabilities, and does not treat proxy feeds as
official settlement labels.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.request
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_UNIVERSE_SCAN_PATH = MACRO_DIR / "latest-kalshi-universe-scan.json"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-probability-breadth-scout-latest"
DEFAULT_RAW_PROBE_DIR = Path("/home/mrwatson/manual_drops/kalshi_probability_sources")
DEFAULT_MAX_CLOSE_HOURS = 6.0
CSV_FIELDS = [
    "rank",
    "ticker",
    "series_ticker",
    "classification",
    "title",
    "time_to_close_hours",
    "yes_bid",
    "yes_ask",
    "yes_spread",
    "softness_score",
    "model_route",
    "source_route",
    "official_settlement_source",
    "proxy_source_policy",
]
HORIZONS = (1, 3, 6, 12, 24, 72)
CORE_FAST_ROUTES = {"finance_crypto", "weather"}
CRYPTO_SERIES_PREFIXES = (
    "KXBTC",
    "KXETH",
    "KXSOL",
    "KXDOGE",
    "KXXRP",
    "KXZEC",
    "KXNEAR",
    "KXBNB",
    "KXHYPE",
)
CRYPTO_TEXT_MARKERS = (
    "bitcoin",
    "btc",
    "ethereum",
    "eth",
    "solana",
    " sol ",
    "dogecoin",
    "doge",
    "xrp",
    "zcash",
    "zec",
    "near protocol",
    "bnb",
    "hyperliquid",
    "hype",
)
CRYPTO_PROXY_PROBES: tuple[tuple[str, str, str, Callable[[Any], dict[str, Any]]], ...] = (
    (
        "coinbase_btc",
        "BTC-USD",
        "https://api.exchange.coinbase.com/products/BTC-USD/ticker",
        lambda payload: {
            "price": payload.get("price") if isinstance(payload, Mapping) else None,
            "time": payload.get("time") if isinstance(payload, Mapping) else None,
        },
    ),
    (
        "coinbase_eth",
        "ETH-USD",
        "https://api.exchange.coinbase.com/products/ETH-USD/ticker",
        lambda payload: {
            "price": payload.get("price") if isinstance(payload, Mapping) else None,
            "time": payload.get("time") if isinstance(payload, Mapping) else None,
        },
    ),
    (
        "coinbase_sol",
        "SOL-USD",
        "https://api.exchange.coinbase.com/products/SOL-USD/ticker",
        lambda payload: {
            "price": payload.get("price") if isinstance(payload, Mapping) else None,
            "time": payload.get("time") if isinstance(payload, Mapping) else None,
        },
    ),
    (
        "kraken_btc",
        "XBT/USD",
        "https://api.kraken.com/0/public/Ticker?pair=XBTUSD",
        lambda payload: {
            "error": payload.get("error") if isinstance(payload, Mapping) else None,
            "pair_count": len(payload.get("result") or {}) if isinstance(payload, Mapping) else 0,
        },
    ),
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_probability_breadth_scout(
    *,
    universe_scan_path: Path = DEFAULT_UNIVERSE_SCAN_PATH,
    max_close_hours: float = DEFAULT_MAX_CLOSE_HOURS,
    generated_utc: str | None = None,
    probe_public_sources: bool = False,
    raw_probe_dir: Path = DEFAULT_RAW_PROBE_DIR,
    fetch_json: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    universe = read_json_or_empty(universe_scan_path)
    universe_safe = safe_research_artifact(universe)
    candidates = [
        row
        for row in universe.get("candidates", [])
        if isinstance(row, Mapping) and number(row.get("time_to_close_hours")) is not None
    ]
    fast_candidates = [
        row
        for row in candidates
        if float(row.get("time_to_close_hours") or 0.0) <= max_close_hours
    ]
    crypto_fast = [row for row in fast_candidates if is_crypto_proxy_candidate(row)]
    weather_fast = [row for row in fast_candidates if row.get("classification") == "weather"]
    fast_by_horizon = horizon_counts(candidates)
    selected_route = select_route(crypto_fast=crypto_fast, weather_fast=weather_fast)
    source_plan = build_source_plan(selected_route=selected_route)
    proxy_probe = (
        probe_crypto_proxy_sources(raw_probe_dir=raw_probe_dir, fetch_json=fetch_json)
        if probe_public_sources
        else no_proxy_probe(raw_probe_dir=raw_probe_dir)
    )
    available_proxy_count = sum(
        1 for item in proxy_probe["sources"] if item.get("status") == "available"
    )
    status = scout_status(
        universe_safe=universe_safe,
        selected_route=selected_route,
        crypto_fast_count=len(crypto_fast),
        weather_fast_count=len(weather_fast),
        available_proxy_count=available_proxy_count,
        probe_public_sources=probe_public_sources,
    )
    work_order_candidates = build_work_order_candidates(crypto_fast, weather_fast)

    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": probe_public_sources,
        "authenticated_api_calls": False,
        "provider_api_calls": probe_public_sources,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "summary": {
            "universe_candidate_count": len(candidates),
            "fast_candidate_count": len(fast_candidates),
            "max_close_hours": max_close_hours,
            "crypto_fast_candidate_count": len(crypto_fast),
            "weather_fast_candidate_count": len(weather_fast),
            "fast_classification_counts": counts(row.get("classification") for row in fast_candidates),
            "fast_by_horizon": fast_by_horizon,
            "crypto_series_counts": counts(row.get("series_ticker") for row in crypto_fast),
            "selected_route": selected_route,
            "available_proxy_source_count": available_proxy_count,
            "official_source_available_without_auth": False,
            "work_order_candidate_count": len(work_order_candidates),
        },
        "inputs": {
            "universe_scan_path": str(universe_scan_path),
            "universe_scan_status": universe.get("status") if isinstance(universe, Mapping) else None,
            "universe_scan_generated_utc": universe.get("generated_utc") if isinstance(universe, Mapping) else None,
        },
        "source_plan": source_plan,
        "proxy_probe": proxy_probe,
        "work_order_candidates": work_order_candidates,
        "next_action": next_action(status),
        "safety": safety_flags(public_market_data_calls=probe_public_sources),
    }


def select_route(*, crypto_fast: Sequence[Mapping[str, Any]], weather_fast: Sequence[Mapping[str, Any]]) -> str:
    if crypto_fast:
        return "crypto_proxy_fast_label_route"
    if weather_fast:
        return "weather_fast_reference_route"
    return "no_fast_probability_breadth_route"


def is_crypto_proxy_candidate(row: Mapping[str, Any]) -> bool:
    if row.get("classification") != "finance_crypto":
        return False
    series = str(row.get("series_ticker") or "").upper()
    if any(series.startswith(prefix) for prefix in CRYPTO_SERIES_PREFIXES):
        return True
    text = f" {row.get('title') or ''} {row.get('subtitle') or ''} ".lower()
    return any(marker in text for marker in CRYPTO_TEXT_MARKERS)


def build_source_plan(*, selected_route: str) -> dict[str, Any]:
    if selected_route == "crypto_proxy_fast_label_route":
        return {
            "route": selected_route,
            "why": (
                "Crypto has the largest count of sub-hour and sub-six-hour Kalshi contracts, "
                "so it is the fastest place to collect repeated probability-decay labels."
            ),
            "official_settlement_source": "CF Benchmarks Real-Time Indices (RTIs)",
            "official_settlement_method": (
                "Kalshi crypto contracts settle from the relevant CF Benchmarks RTI average "
                "over the final sixty seconds before expiration."
            ),
            "official_source_availability": "authenticated_or_licensed_required",
            "official_source_docs": [
                "https://help.kalshi.com/en/articles/13823838-crypto-markets",
                "https://www.cfbenchmarks.com/data/indices/BRTI",
                "https://docs.cfbenchmarks.com/api/",
                "https://docs.kalshi.com/cfbenchmarks/rest-passthrough",
            ],
            "proxy_feature_sources": [
                "Coinbase Exchange public ticker API",
                "Kraken public ticker API",
            ],
            "proxy_policy": (
                "Proxy exchange prices may be used as model features only. They are not official "
                "settlement labels and cannot promote hypotheses without settled Kalshi outcomes."
            ),
        }
    if selected_route == "weather_fast_reference_route":
        return {
            "route": selected_route,
            "why": "Weather has fast-settling contracts, but the current count is smaller than crypto.",
            "official_settlement_source": "market-specific weather station/reference agency",
            "official_source_availability": "route_specific_public_source_required",
            "official_source_docs": [],
            "proxy_feature_sources": ["NOAA/NWS public observations and forecasts"],
            "proxy_policy": "Weather source mapping must be audited per contract before feature or label use.",
        }
    return {
        "route": selected_route,
        "why": "No high-count fast-settling route is available in the current universe scan.",
        "official_settlement_source": None,
        "official_source_availability": "not_applicable",
        "official_source_docs": [],
        "proxy_feature_sources": [],
        "proxy_policy": "No proxy feature route selected.",
    }


def probe_crypto_proxy_sources(
    *,
    raw_probe_dir: Path,
    fetch_json: Callable[[str], Any] | None,
) -> dict[str, Any]:
    raw_probe_dir.mkdir(parents=True, exist_ok=True)
    fetched_at = utc_now()
    sources: list[dict[str, Any]] = []
    raw_payloads: dict[str, Any] = {}
    getter = fetch_json or fetch_public_json

    for name, market, url, shape in CRYPTO_PROXY_PROBES:
        started = time.time()
        try:
            payload = getter(url)
            shaped = shape(payload)
            status = "available"
            error = None
            raw_payloads[name] = {
                "market": market,
                "url": url,
                "payload": payload,
            }
        except Exception as exc:
            shaped = {}
            status = "unavailable"
            error = f"{type(exc).__name__}: {str(exc)[:240]}"
        sources.append(
            {
                "name": name,
                "market": market,
                "url": url,
                "status": status,
                "latency_ms": round((time.time() - started) * 1000, 2),
                "summary": shaped,
                "error": error,
                "role": "proxy_feature_source_not_official_settlement",
            }
        )

    raw_snapshot = {
        "schema_version": 1,
        "fetched_at_utc": fetched_at,
        "research_only": True,
        "execution_enabled": False,
        "source_role": "crypto_proxy_feature_source_not_official_settlement",
        "payloads": raw_payloads,
        "safety": safety_flags(public_market_data_calls=True),
    }
    stamp = fetched_at.replace("-", "").replace(":", "")
    raw_snapshot_path = raw_probe_dir / f"crypto_proxy_probe_{stamp}.json"
    raw_snapshot_path.write_text(json.dumps(raw_snapshot, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    latest_path = raw_probe_dir / "crypto_proxy_probe_latest.json"
    latest_path.write_text(json.dumps(raw_snapshot, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return {
        "status": "public_proxy_probe_completed",
        "fetched_at_utc": fetched_at,
        "raw_snapshot_path": str(raw_snapshot_path),
        "latest_raw_snapshot_path": str(latest_path),
        "raw_snapshot_outside_repo": is_outside_repo(raw_snapshot_path),
        "sources": sources,
    }


def no_proxy_probe(*, raw_probe_dir: Path) -> dict[str, Any]:
    return {
        "status": "public_proxy_probe_not_run",
        "raw_probe_dir": str(raw_probe_dir),
        "raw_snapshot_outside_repo": is_outside_repo(raw_probe_dir),
        "sources": [
            {
                "name": name,
                "market": market,
                "url": url,
                "status": "not_probed",
                "summary": {},
                "error": None,
                "role": "proxy_feature_source_not_official_settlement",
            }
            for name, market, url, _shape in CRYPTO_PROXY_PROBES
        ],
    }


def fetch_public_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "predmarket-alpha research-only"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def scout_status(
    *,
    universe_safe: bool,
    selected_route: str,
    crypto_fast_count: int,
    weather_fast_count: int,
    available_proxy_count: int,
    probe_public_sources: bool,
) -> str:
    if not universe_safe:
        return "probability_breadth_scout_blocked_missing_safe_universe_scan"
    if selected_route == "crypto_proxy_fast_label_route" and crypto_fast_count > 0:
        if probe_public_sources and available_proxy_count == 0:
            return "probability_breadth_scout_blocked_crypto_proxy_sources_unavailable"
        if available_proxy_count > 0:
            return "probability_breadth_scout_ready_crypto_proxy_feature_route"
        return "probability_breadth_scout_ready_crypto_route_needs_proxy_probe"
    if selected_route == "weather_fast_reference_route" and weather_fast_count > 0:
        return "probability_breadth_scout_ready_weather_reference_route"
    return "probability_breadth_scout_blocked_no_fast_route"


def build_work_order_candidates(
    crypto_fast: Sequence[Mapping[str, Any]],
    weather_fast: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_route, items in (
        ("crypto_proxy_fast_label_route", crypto_fast),
        ("weather_fast_reference_route", weather_fast),
    ):
        for idx, row in enumerate(
            sorted(
                items,
                key=lambda item: (
                    float(item.get("time_to_close_hours") or 999999.0),
                    -float(item.get("softness_score") or 0.0),
                    str(item.get("ticker") or ""),
                ),
            )[:100],
            start=1,
        ):
            compact = compact_candidate(row)
            compact["rank"] = idx
            compact["source_route"] = source_route
            compact["official_settlement_source"] = (
                "CF Benchmarks RTI"
                if source_route == "crypto_proxy_fast_label_route"
                else "market-specific official weather source"
            )
            compact["proxy_source_policy"] = (
                "proxy_feature_only_not_official_label"
                if source_route == "crypto_proxy_fast_label_route"
                else "contract_specific_source_audit_required"
            )
            rows.append(compact)
    return rows


def compact_candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ticker": row.get("ticker"),
        "event_ticker": row.get("event_ticker"),
        "series_ticker": row.get("series_ticker"),
        "classification": row.get("classification"),
        "title": row.get("title"),
        "time_to_close_hours": row.get("time_to_close_hours"),
        "yes_bid": row.get("yes_bid"),
        "yes_ask": row.get("yes_ask"),
        "yes_spread": row.get("yes_spread"),
        "softness_score": row.get("softness_score"),
        "model_route": row.get("model_route"),
        "ev_status": "not_evaluated_probability_breadth_inventory_only",
        "calibrated_probability": None,
        "usable": False,
    }


def horizon_counts(candidates: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for horizon in HORIZONS:
        counter = Counter(
            str(row.get("classification") or "unknown")
            for row in candidates
            if float(row.get("time_to_close_hours") or 999999.0) <= horizon
        )
        output[f"lte_{horizon}h"] = dict(sorted(counter.items()))
    return output


def next_action(status: str) -> dict[str, str]:
    if status == "probability_breadth_scout_ready_crypto_proxy_feature_route":
        return {
            "name": "kalshi_crypto_proxy_feature_packet",
            "why": (
                "Crypto is the highest-count fast-settling route and public proxy feeds are reachable; "
                "build feature packets while keeping CF Benchmarks as the official settlement source."
            ),
            "stop_condition": (
                "Stop before treating proxy prices as official labels, computing usable EV, sizing, execution, "
                "or account/order paths."
            ),
        }
    if status == "probability_breadth_scout_ready_crypto_route_needs_proxy_probe":
        return {
            "name": "kalshi_crypto_proxy_source_probe",
            "why": "Crypto is the fastest route, but proxy-source availability has not been recorded yet.",
            "stop_condition": "Stop before using any proxy feed as settlement truth or calibrated probability evidence.",
        }
    if status == "probability_breadth_scout_ready_weather_reference_route":
        return {
            "name": "kalshi_weather_reference_source_audit",
            "why": "Weather is the best available fast route after crypto, but each contract needs source mapping.",
            "stop_condition": "Stop before modeling weather contracts without official station/source mapping.",
        }
    return {
        "name": "kalshi_probability_breadth_blocker_review",
        "why": "No safe high-count fast-settling route is ready from the current universe scan.",
        "stop_condition": "Stop before inventing data sources or calibrated probabilities.",
    }


def write_probability_breadth_scout(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-probability-breadth-scout.json"
    md_path = out_dir / "kalshi-probability-breadth-scout.md"
    csv_path = out_dir / "kalshi-probability-breadth-scout-candidates.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_candidates_csv(report.get("work_order_candidates", []), csv_path)
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-probability-breadth-scout.json"
    latest_md = MACRO_DIR / "latest-kalshi-probability-breadth-scout.md"
    latest_csv = MACRO_DIR / "latest-kalshi-probability-breadth-scout-candidates.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_candidates_csv(report.get("work_order_candidates", []), latest_csv)
    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
        "latest_csv_path": str(latest_csv),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    source_plan = report.get("source_plan") if isinstance(report.get("source_plan"), Mapping) else {}
    next_step = report.get("next_action") if isinstance(report.get("next_action"), Mapping) else {}
    lines = [
        "# Kalshi Probability Breadth Scout",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Research only: `{str(report.get('research_only')).lower()}`",
        f"- Execution enabled: `{str(report.get('execution_enabled')).lower()}`",
        f"- Fast candidate window: `{summary.get('max_close_hours')}` hours",
        f"- Fast candidates: `{summary.get('fast_candidate_count')}`",
        f"- Crypto fast candidates: `{summary.get('crypto_fast_candidate_count')}`",
        f"- Weather fast candidates: `{summary.get('weather_fast_candidate_count')}`",
        f"- Selected route: `{summary.get('selected_route')}`",
        "",
        "## Learned",
        "",
        f"- Official settlement source: `{source_plan.get('official_settlement_source')}`",
        f"- Official availability: `{source_plan.get('official_source_availability')}`",
        f"- Proxy policy: {source_plan.get('proxy_policy')}",
        "",
        "## Proxy Sources",
        "",
        "| Source | Status | Role | Summary |",
        "| --- | --- | --- | --- |",
    ]
    proxy_probe = report.get("proxy_probe") if isinstance(report.get("proxy_probe"), Mapping) else {}
    for source in proxy_probe.get("sources", []):
        if not isinstance(source, Mapping):
            continue
        lines.append(
            f"| `{source.get('name')}` | `{source.get('status')}` | `{source.get('role')}` | "
            f"`{json.dumps(source.get('summary') or {}, sort_keys=True)}` |"
        )
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            f"- Name: `{next_step.get('name')}`",
            f"- Why: {next_step.get('why')}",
            f"- Stop condition: {next_step.get('stop_condition')}",
            "",
            "## Guardrail",
            "",
            "This is a routing and evidence-source scout. It is not a bet list, EV ledger, or execution signal.",
            "",
        ]
    )
    return "\n".join(lines)


def write_candidates_csv(candidates: Any, path: Path) -> None:
    rows = [row for row in candidates if isinstance(row, Mapping)]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def safety_flags(*, public_market_data_calls: bool) -> dict[str, Any]:
    return {
        "research_only": True,
        "public_market_data_calls": public_market_data_calls,
        "authenticated_api_calls": False,
        "account_or_order_paths": False,
        "market_execution": False,
        "database_writes": False,
        "paid_calls": False,
        "raw_secrets_copied": False,
        "raw_payloads_copied_to_repo": False,
        "staking_or_sizing_guidance": False,
    }


def safe_research_artifact(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    safety = value.get("safety") if isinstance(value.get("safety"), Mapping) else {}
    return (
        value.get("research_only") is True
        and value.get("execution_enabled") is False
        and safety.get("market_execution") is False
        and safety.get("account_or_order_paths") is False
        and safety.get("database_writes") is False
    )


def is_outside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(CONTROL_REPO.resolve())
    except ValueError:
        return True
    return False


def counts(values: Sequence[Any]) -> dict[str, int]:
    counter = Counter(str(value or "unknown") for value in values)
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_json_or_empty(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-scan-path", type=Path, default=DEFAULT_UNIVERSE_SCAN_PATH)
    parser.add_argument("--max-close-hours", type=float, default=DEFAULT_MAX_CLOSE_HOURS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--raw-probe-dir", type=Path, default=DEFAULT_RAW_PROBE_DIR)
    parser.add_argument("--probe-public-sources", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_probability_breadth_scout(
        universe_scan_path=args.universe_scan_path,
        max_close_hours=args.max_close_hours,
        probe_public_sources=args.probe_public_sources,
        raw_probe_dir=args.raw_probe_dir,
    )
    if args.write:
        paths = write_probability_breadth_scout(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
