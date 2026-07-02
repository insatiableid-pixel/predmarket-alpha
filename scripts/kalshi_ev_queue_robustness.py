#!/usr/bin/env python3
"""Check whether Kalshi EV review-queue rows persist across local snapshots."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.kalshi_execution_cost import normalize_kalshi_execution_cost  # noqa: E402

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_QUEUE_PATH = MACRO_DIR / "latest-kalshi-ev-review-queue.json"
DEFAULT_SNAPSHOT_DIR = Path("/home/mrwatson/manual_drops/kalshi")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-ev-queue-robustness-latest"
DEFAULT_MIN_ROBUST_MARGIN = 0.02
CSV_FIELDS = [
    "queue_rank",
    "contract_ticker",
    "selection",
    "snapshot_count",
    "positive_snapshot_count",
    "latest_all_in_break_even",
    "latest_margin_probability",
    "min_margin_probability",
    "max_margin_probability",
    "margin_delta_first_to_latest",
    "disposition",
    "robustness_reasons",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_queue_robustness(
    *,
    queue_path: Path = DEFAULT_QUEUE_PATH,
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    generated_utc: str | None = None,
    min_robust_margin: float = DEFAULT_MIN_ROBUST_MARGIN,
) -> dict[str, Any]:
    queue = read_json_or_empty(queue_path)
    queue_rows = queue.get("rows") if isinstance(queue.get("rows"), list) else []
    rows = [row for row in queue_rows if isinstance(row, Mapping)]
    snapshots = distinct_nfl_snapshots(snapshot_dir)
    robustness_rows = [
        robustness_row(row, snapshots=snapshots, min_robust_margin=min_robust_margin)
        for row in rows
    ]
    repeat_positive = [
        row
        for row in robustness_rows
        if row.get("positive_snapshot_count", 0) >= 2 and row.get("min_margin_probability", 0) > 0
    ]
    robust_candidates = [
        row
        for row in robustness_rows
        if row.get("disposition") == "repeat_positive_robustness_candidate"
    ]
    if robust_candidates:
        status = "kalshi_ev_queue_robustness_ready"
    elif repeat_positive:
        status = "kalshi_ev_queue_robustness_repeat_positive_cost_caveated"
    elif snapshots:
        status = "kalshi_ev_queue_robustness_observed_not_repeat_positive"
    else:
        status = "kalshi_ev_queue_robustness_blocked_no_snapshots"

    return {
        "schema_version": 1,
        "generated_utc": generated_utc or utc_now(),
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "live_calls_made": False,
        "provider_api_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "inputs": {
            "queue_path": str(queue_path),
            "queue_status": queue.get("status"),
            "snapshot_dir": str(snapshot_dir),
        },
        "policy": {
            "distinct_snapshot_key": "created_at_utc",
            "min_robust_margin": min_robust_margin,
            "repeat_positive_rule": "at least two distinct snapshots with positive margin",
            "robust_rule": (
                "repeat positive plus min margin >= threshold and no cost-quality caveat; "
                "current public snapshots normally remain cost-caveated until actual all-in ticket cost is verified"
            ),
        },
        "summary": {
            "queue_row_count": len(rows),
            "distinct_snapshot_count": len(snapshots),
            "rows_with_two_plus_snapshots": sum(1 for row in robustness_rows if row["snapshot_count"] >= 2),
            "repeat_positive_row_count": len(repeat_positive),
            "robust_candidate_count": len(robust_candidates),
            "missing_latest_quote_count": sum(1 for row in robustness_rows if row["snapshot_count"] == 0),
            "cost_caveated_row_count": sum(
                1
                for row in robustness_rows
                if "fee is estimated from executable price" in row.get("robustness_reasons", [])
            ),
        },
        "snapshots": [
            {
                "created_at_utc": snapshot["created_at_utc"],
                "path": str(snapshot["path"]),
                "sha256": snapshot["sha256"],
                "market_count": len(snapshot["markets_by_ticker"]),
            }
            for snapshot in snapshots
        ],
        "rows": robustness_rows,
        "next_action": next_action(status),
        "safety": {
            "research_only": True,
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "raw_payloads_copied_to_repo": False,
        },
    }


def robustness_row(
    row: Mapping[str, Any],
    *,
    snapshots: Sequence[Mapping[str, Any]],
    min_robust_margin: float,
) -> dict[str, Any]:
    ticker = str(row.get("contract_ticker") or "")
    calibrated_probability = optional_float(row.get("calibrated_probability"))
    observations = [
        observation_for(ticker, snapshot=snapshot, calibrated_probability=calibrated_probability)
        for snapshot in snapshots
    ]
    observations = [item for item in observations if item is not None]
    margins = [item["margin_probability"] for item in observations if item.get("margin_probability") is not None]
    positive_count = sum(1 for item in observations if item.get("margin_probability", 0) > 0)
    latest = observations[-1] if observations else {}
    min_margin = min(margins) if margins else None
    max_margin = max(margins) if margins else None
    delta = (
        observations[-1]["margin_probability"] - observations[0]["margin_probability"]
        if len(observations) >= 2
        and observations[-1].get("margin_probability") is not None
        and observations[0].get("margin_probability") is not None
        else None
    )
    reasons = robustness_reasons(
        snapshot_count=len(observations),
        positive_count=positive_count,
        min_margin=min_margin,
        min_robust_margin=min_robust_margin,
        cost_quality=str(latest.get("cost_quality") or row.get("cost_quality") or ""),
    )
    if not reasons:
        disposition = "repeat_positive_robustness_candidate"
    elif positive_count >= 2 and min_margin is not None and min_margin > 0:
        disposition = "repeat_positive_cost_caveated"
    elif observations:
        disposition = "not_repeat_positive_watch"
    else:
        disposition = "missing_snapshot_quote"
    return {
        "queue_rank": row.get("queue_rank"),
        "contract_ticker": ticker,
        "side": row.get("side"),
        "selection": row.get("selection"),
        "source_repo_id": row.get("source_repo_id"),
        "calibrated_probability": calibrated_probability,
        "snapshot_count": len(observations),
        "positive_snapshot_count": positive_count,
        "latest_all_in_break_even": latest.get("all_in_break_even_probability"),
        "latest_margin_probability": latest.get("margin_probability"),
        "min_margin_probability": min_margin,
        "max_margin_probability": max_margin,
        "margin_delta_first_to_latest": delta,
        "disposition": disposition,
        "robustness_reasons": reasons,
        "observations": observations,
    }


def observation_for(
    ticker: str,
    *,
    snapshot: Mapping[str, Any],
    calibrated_probability: float | None,
) -> dict[str, Any] | None:
    market = snapshot.get("markets_by_ticker", {}).get(ticker)
    if not isinstance(market, Mapping):
        return None
    ask = first_float(market, ("yes_ask_dollars", "yes_ask", "ask", "ask_dollars"))
    bid = first_float(market, ("yes_bid_dollars", "yes_bid", "bid", "bid_dollars"))
    cost = normalize_kalshi_execution_cost(
        display_price=ask,
        executable_price=ask,
        executable_price_source="public_kalshi_snapshot_yes_ask",
        ticker=ticker,
    )
    break_even = cost.break_even_probability
    margin = (
        calibrated_probability - break_even
        if calibrated_probability is not None and break_even is not None
        else None
    )
    return {
        "created_at_utc": snapshot.get("created_at_utc"),
        "source_path": str(snapshot.get("path")),
        "source_sha256": snapshot.get("sha256"),
        "yes_bid": bid,
        "yes_ask": ask,
        "yes_spread": round(ask - bid, 6) if ask is not None and bid is not None else None,
        "all_in_break_even_probability": break_even,
        "fee_estimate": cost.fee_estimate,
        "cost_quality": cost.cost_quality,
        "margin_probability": margin,
        "positive": margin is not None and margin > 0,
    }


def robustness_reasons(
    *,
    snapshot_count: int,
    positive_count: int,
    min_margin: float | None,
    min_robust_margin: float,
    cost_quality: str,
) -> list[str]:
    reasons: list[str] = []
    if snapshot_count < 2:
        reasons.append("fewer than two distinct snapshots")
    if positive_count < 2:
        reasons.append("positive margin did not repeat across two snapshots")
    if min_margin is None:
        reasons.append("margin is missing across snapshots")
    elif min_margin < min_robust_margin:
        reasons.append(f"minimum repeated margin below robust threshold {min_robust_margin:.4f}")
    if cost_quality == "estimated_fee_from_executable_price":
        reasons.append("fee is estimated from executable price")
    return reasons


def distinct_nfl_snapshots(snapshot_dir: Path) -> list[dict[str, Any]]:
    by_created: dict[str, dict[str, Any]] = {}
    for path in sorted(snapshot_dir.glob("*.json")):
        raw = read_json_or_empty(path)
        if "KXNFLGAME" not in set(raw.get("series_tickers") or []):
            continue
        created_at = str(raw.get("created_at_utc") or path.stat().st_mtime)
        markets = raw.get("all_scored") or raw.get("markets") or []
        markets_by_ticker = {
            str(market.get("ticker")): market
            for market in markets
            if isinstance(market, Mapping) and market.get("ticker")
        }
        if not markets_by_ticker:
            continue
        candidate = {
            "created_at_utc": created_at,
            "path": path,
            "sha256": sha256_file(path),
            "markets_by_ticker": markets_by_ticker,
        }
        existing = by_created.get(created_at)
        if existing is None or path.name != "kalshi_nfl_game_series_latest.json":
            by_created[created_at] = candidate
    return sorted(by_created.values(), key=lambda item: str(item["created_at_utc"]))


def next_action(status: str) -> str:
    if status == "kalshi_ev_queue_robustness_ready":
        return "Review robustness candidates manually; execution remains disabled."
    if status == "kalshi_ev_queue_robustness_repeat_positive_cost_caveated":
        return (
            "Repeat-positive rows exist, but current robustness is cost-caveated. Next useful input is actual all-in "
            "ticket-cost confirmation without order submission, plus forward-context and independent validation."
        )
    if status == "kalshi_ev_queue_robustness_observed_not_repeat_positive":
        return "Rows did not repeat as positive across snapshots; keep them watch-only and gather another independent snapshot later."
    return "Add at least two local KXNFLGAME public snapshots, then rerun queue robustness."


def write_queue_robustness(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-ev-queue-robustness.json"
    md_path = out_dir / "kalshi-ev-queue-robustness.md"
    csv_path = out_dir / "kalshi-ev-queue-robustness.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("rows") if isinstance(report.get("rows"), list) else [], csv_path)
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-ev-queue-robustness.json"
    latest_md = MACRO_DIR / "latest-kalshi-ev-queue-robustness.md"
    latest_csv = MACRO_DIR / "latest-kalshi-ev-queue-robustness.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("rows") if isinstance(report.get("rows"), list) else [], latest_csv)
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
    lines = [
        "# Kalshi EV Queue Robustness",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Research only: `{str(report.get('research_only')).lower()}`",
        f"- Execution enabled: `{str(report.get('execution_enabled')).lower()}`",
        f"- Distinct snapshots: `{summary.get('distinct_snapshot_count')}`",
        f"- Queue rows: `{summary.get('queue_row_count')}`",
        f"- Repeat-positive rows: `{summary.get('repeat_positive_row_count')}`",
        f"- Robust candidates: `{summary.get('robust_candidate_count')}`",
        "",
        "## Rows",
        "",
        "| Rank | Contract | Selection | Snapshots | Positive | Latest Margin | Min Margin | Disposition | Reasons |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    for row in rows[:25]:
        reasons = "; ".join(str(reason) for reason in row.get("robustness_reasons") or [])
        lines.append(
            f"| {row.get('queue_rank')} | `{row.get('contract_ticker')}` | `{row.get('selection')}` | "
            f"{row.get('snapshot_count')} | {row.get('positive_snapshot_count')} | "
            f"{format_number(row.get('latest_margin_probability'))} | "
            f"{format_number(row.get('min_margin_probability'))} | `{row.get('disposition')}` | {reasons or 'none'} |"
        )
    lines.extend(["", "## Next Action", "", str(report.get("next_action") or ""), ""])
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["robustness_reasons"] = "; ".join(str(reason) for reason in row.get("robustness_reasons") or [])
            writer.writerow(out)


def first_float(item: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        value = optional_float(item.get(key))
        if value is not None:
            return value
    return None


def optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(str(value).strip().rstrip("x%"))
    except (TypeError, ValueError):
        return None


def format_number(value: Any) -> str:
    number = optional_float(value)
    return "" if number is None else f"{number:.6f}"


def read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    raw = digest.hexdigest()
    return "sha256:" + " ".join(raw[index : index + 8] for index in range(0, len(raw), 8))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-path", type=Path, default=DEFAULT_QUEUE_PATH)
    parser.add_argument("--snapshot-dir", type=Path, default=DEFAULT_SNAPSHOT_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--min-robust-margin", type=float, default=DEFAULT_MIN_ROBUST_MARGIN)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_queue_robustness(
        queue_path=args.queue_path,
        snapshot_dir=args.snapshot_dir,
        min_robust_margin=args.min_robust_margin,
    )
    if args.write:
        paths = write_queue_robustness(report, args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
