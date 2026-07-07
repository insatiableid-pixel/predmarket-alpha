#!/usr/bin/env python3
"""Check whether historical sharp-consensus snapshots can satisfy skew gates."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import path_is_within, safety_flags, timestamp  # noqa: E402
from predmarket.sports_consensus_reference_builder import (  # noqa: E402
    DEFAULT_KEY_FILE,
    THE_ODDS_API_ENDPOINT,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-historical-consensus-feasibility-latest"
OFFICIAL_DOCS = (
    "https://the-odds-api.com/liveapi/guides/v4/#get-historical-odds",
    "https://the-odds-api.com/historical-odds-data/",
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_feasibility(
    *,
    generated_utc: str | None = None,
    snapshot_interval_seconds: int = 300,
    max_allowed_skew_seconds: int = 180,
    paid_access_verified: bool = False,
    paid_probe: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    nearest_strategy_skew = snapshot_interval_seconds / 2.0
    skew_pass = nearest_strategy_skew <= max_allowed_skew_seconds
    paid_probe_status = str((paid_probe or {}).get("status") or "")
    access_verified = (
        paid_access_verified or paid_probe_status == "historical_probe_access_verified"
    )
    if not skew_pass:
        status = "kalshi_sports_historical_consensus_feasibility_blocked_snapshot_skew"
    elif not access_verified:
        status = "kalshi_sports_historical_consensus_feasibility_ready_paid_access_unverified"
    else:
        status = "kalshi_sports_historical_consensus_feasibility_ready_for_backfill"
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "provider_api_calls": bool(paid_probe),
        "paid_historical_calls": bool(paid_probe),
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "sources": [
            {
                "provider": "The Odds API",
                "url": OFFICIAL_DOCS[0],
                "claim": (
                    "Historical odds snapshots are available at 5-minute intervals "
                    "from September 2022 and require paid usage plans."
                ),
            },
            {
                "provider": "The Odds API",
                "url": OFFICIAL_DOCS[1],
                "claim": (
                    "Historical endpoint usage cost is documented as 10 quota units "
                    "per region per market for featured markets."
                ),
            },
        ],
        "method": {
            "snapshot_interval_seconds": snapshot_interval_seconds,
            "nearest_snapshot_query_offset_seconds": snapshot_interval_seconds / 2.0,
            "max_expected_absolute_skew_seconds": nearest_strategy_skew,
            "max_allowed_skew_seconds": max_allowed_skew_seconds,
            "skew_policy": (
                "For historical backfill, request target_time + interval/2 because "
                "The Odds API returns the closest snapshot equal to or earlier than "
                "the requested date. With 5-minute snapshots this bounds absolute "
                "target skew at 150 seconds."
            ),
            "backfill_boundary": (
                "Historical consensus divergence backfill is allowed only after paid "
                "endpoint access is verified and exact Kalshi ticker mappings are present."
            ),
        },
        "summary": {
            "snapshot_interval_seconds": snapshot_interval_seconds,
            "max_expected_absolute_skew_seconds": nearest_strategy_skew,
            "max_allowed_skew_seconds": max_allowed_skew_seconds,
            "skew_gate_pass": skew_pass,
            "paid_access_verified": access_verified,
            "historical_endpoint_cost_per_region_market": 10,
            "paid_probe_status": paid_probe_status or None,
        },
        "paid_probe": dict(paid_probe or {}),
        "next_action": next_action(status),
        "safety": {
            **safety_flags(public_market_data_calls=bool(paid_probe)),
            "provider_api_calls": bool(paid_probe),
            "paid_historical_calls": bool(paid_probe),
            "account_or_order_paths": False,
            "market_execution": False,
        },
    }


def probe_historical_endpoint(
    *,
    api_key_file: Path,
    sport_key: str,
    regions: str,
    markets: str,
    odds_format: str,
    date_utc: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        api_key = api_key_file.expanduser().read_text(encoding="utf-8").strip()
    except OSError as exc:
        return {"status": "historical_probe_blocked_missing_api_key", "error": str(exc)}
    if not api_key:
        return {"status": "historical_probe_blocked_missing_api_key", "error": "empty key file"}
    endpoint = THE_ODDS_API_ENDPOINT.format(sport_key=sport_key).replace(
        "/v4/sports/", "/v4/historical/sports/"
    )
    params = urllib.parse.urlencode(
        {
            "apiKey": api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
            "dateFormat": "iso",
            "date": date_utc,
        }
    )
    url = f"{endpoint}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            payload = json.load(response)
            headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
    except HTTPError as exc:
        return {
            "status": "historical_probe_blocked_http_error",
            "status_code": int(exc.code),
            "error": exc.reason,
        }
    except Exception as exc:
        return {"status": "historical_probe_failed_runtime_error", "error": str(exc)}
    snapshot_time = str(payload.get("timestamp") or "")
    requested_ts = timestamp(date_utc)
    snapshot_ts = timestamp(snapshot_time)
    skew = (
        abs(requested_ts - snapshot_ts)
        if requested_ts is not None and snapshot_ts is not None
        else None
    )
    return {
        "status": "historical_probe_access_verified",
        "sport_key": sport_key,
        "markets": markets,
        "regions": regions,
        "requested_date_utc": date_utc,
        "snapshot_timestamp_utc": snapshot_time or None,
        "absolute_skew_seconds": skew,
        "quota_headers": {
            key: value for key, value in headers.items() if key.startswith("x-requests")
        },
        "api_key_printed": False,
    }


def next_action(status: str) -> dict[str, Any]:
    if status == "kalshi_sports_historical_consensus_feasibility_ready_for_backfill":
        return {
            "name": "build_historical_consensus_divergence_backfill",
            "why": "Skew and paid access are verified; historical divergence can enter the existing OOS/FDR grid.",
            "stop_condition": "Stop before using historical snapshots unless exact Kalshi ticker mapping and <=180s skew are present.",
        }
    if status == "kalshi_sports_historical_consensus_feasibility_ready_paid_access_unverified":
        return {
            "name": "verify_paid_historical_provider_access",
            "why": "Provider cadence is compatible with the 180s gate, but paid endpoint access is not verified.",
            "stop_condition": "Stop before historical divergence backfill.",
        }
    return {
        "name": "keep_kalshi_only_bucket_backfill",
        "why": "Historical consensus snapshots do not currently satisfy the skew/access gate.",
        "stop_condition": "Stop before weakening timestamp-skew requirements.",
    }


def write_outputs(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-historical-consensus-feasibility.json"
    md_path = out_dir / "kalshi-sports-historical-consensus-feasibility.md"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    paths = {"json_path": str(json_path), "markdown_path": str(md_path)}
    if path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-sports-historical-consensus-feasibility.json"
        latest_md = MACRO_DIR / "latest-kalshi-sports-historical-consensus-feasibility.md"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        paths.update({"latest_json_path": str(latest_json), "latest_markdown_path": str(latest_md)})
    return paths


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Sports Historical Consensus Feasibility",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Snapshot interval: `{summary.get('snapshot_interval_seconds')}` seconds",
        f"- Max expected skew: `{summary.get('max_expected_absolute_skew_seconds')}` seconds",
        f"- Skew gate pass: `{summary.get('skew_gate_pass')}`",
        f"- Paid access verified: `{summary.get('paid_access_verified')}`",
        "",
        "Research-only feasibility check. No probabilities, labels, EV, paper stake, orders, or account paths.",
        "",
    ]
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--snapshot-interval-seconds", type=int, default=300)
    parser.add_argument("--max-allowed-skew-seconds", type=int, default=180)
    parser.add_argument("--probe-paid-endpoint", action="store_true")
    parser.add_argument("--api-key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--probe-sport-key", default="baseball_mlb")
    parser.add_argument("--probe-regions", default="us")
    parser.add_argument("--probe-markets", default="h2h")
    parser.add_argument("--probe-odds-format", default="american")
    parser.add_argument("--probe-date-utc", default="2026-07-01T12:00:00Z")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    paid_probe = (
        probe_historical_endpoint(
            api_key_file=args.api_key_file,
            sport_key=args.probe_sport_key,
            regions=args.probe_regions,
            markets=args.probe_markets,
            odds_format=args.probe_odds_format,
            date_utc=args.probe_date_utc,
            timeout_seconds=float(args.timeout_seconds),
        )
        if args.probe_paid_endpoint
        else None
    )
    report = build_feasibility(
        snapshot_interval_seconds=int(args.snapshot_interval_seconds),
        max_allowed_skew_seconds=int(args.max_allowed_skew_seconds),
        paid_probe=paid_probe,
    )
    if args.write:
        paths = write_outputs(report, args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
