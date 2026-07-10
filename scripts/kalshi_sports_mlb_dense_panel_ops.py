#!/usr/bin/env python3
"""Operate the dense multi-slate MLB fixed-clock panel (research-only).

Commands:
  register  — write immutable preregistration artifacts + hashes
  capture   — one restart-safe public capture cycle (PID lock, append-only raw)
  status    — infrastructure / accumulation / evidence readiness (no P&L)
  replay    — reconstruct coverage from local raw JSONL without network

No accounts, orders, sizing, or live execution.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

import importlib.util  # noqa: E402

from predmarket.shared_helpers import manual_drop_path, timestamp, utc_now  # noqa: E402
from predmarket.sports_mlb_dense_panel import (  # noqa: E402
    CAPTURE_CADENCE_SECONDS,
    PANEL_FAMILY_ID,
    PRIMARY_CLOCKS_SECONDS,
    PRIMARY_STALENESS_SECONDS,
    SECONDARY_CLOCKS_SECONDS,
    SECONDARY_STALENESS_SECONDS,
    CaptureLock,
    append_raw_snapshot_jsonl,
    assess_panel_coverage,
    atomic_write_json,
    atomic_write_text,
    build_panel_registration,
    frozen_candidate_confirmation_state,
    health_status,
    load_raw_snapshots,
    registration_markdown,
    snapshot_payload_hash,
)


def _load_dense_capture():
    path = CONTROL_REPO / "scripts" / "kalshi_sports_mlb_dense_book_capture.py"
    spec = importlib.util.spec_from_file_location("kalshi_sports_mlb_dense_book_capture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_dense_capture = _load_dense_capture()
capture_rows = _dense_capture.capture_rows
list_open_mlb = _dense_capture.list_open_mlb

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_REG_DIR = MACRO_DIR / "kalshi-sports-mlb-dense-panel-registration-latest"
DEFAULT_STATUS_DIR = manual_drop_path(
    "kalshi_sports_mlb_dense_panel_status",
    env_vars=("KALSHI_SPORTS_MLB_DENSE_PANEL_STATUS_DIR",),
)
DEFAULT_RAW_DIR = manual_drop_path(
    "kalshi_sports_mlb_dense_panel_raw",
    env_vars=("KALSHI_SPORTS_MLB_DENSE_PANEL_RAW_DIR",),
)
DEFAULT_BOOK_DIR = manual_drop_path(
    "kalshi_sports_mlb_fixed_clock_books",
    env_vars=("KALSHI_SPORTS_MLB_DENSE_BOOK_DIR",),
)


def eligible_capture_clocks(
    market: Mapping[str, Any], *, observed_utc: str
) -> tuple[str, ...]:
    """Return preregistered as-of windows that need an order-book request."""
    observed_ts = timestamp(observed_utc)
    game_start = timestamp(
        market.get("occurrence_datetime") or market.get("expected_expiration_time")
    )
    if observed_ts is None or game_start is None:
        return ()
    clocks = {**PRIMARY_CLOCKS_SECONDS, **SECONDARY_CLOCKS_SECONDS}
    staleness = {**PRIMARY_STALENESS_SECONDS, **SECONDARY_STALENESS_SECONDS}
    return tuple(
        name
        for name, offset in clocks.items()
        if 0.0
        <= float(game_start) - float(offset) - float(observed_ts)
        <= float(staleness[name])
    )


def select_capture_window_markets(
    markets: Sequence[Mapping[str, Any]], *, observed_utc: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Filter discovery to rate-limit-friendly fixed-clock windows."""
    selected: list[dict[str, Any]] = []
    clock_counts: Counter[str] = Counter()
    next_window_open_ts: float | None = None
    observed_ts = timestamp(observed_utc)
    clocks = {**PRIMARY_CLOCKS_SECONDS, **SECONDARY_CLOCKS_SECONDS}
    staleness = {**PRIMARY_STALENESS_SECONDS, **SECONDARY_STALENESS_SECONDS}
    for market in markets:
        names = eligible_capture_clocks(market, observed_utc=observed_utc)
        if names:
            item = dict(market)
            item["_eligible_capture_clocks"] = list(names)
            selected.append(item)
            clock_counts.update(names)
        game_start = timestamp(
            market.get("occurrence_datetime") or market.get("expected_expiration_time")
        )
        if observed_ts is None or game_start is None:
            continue
        for clock_name, offset in clocks.items():
            window_open = float(game_start) - float(offset) - float(staleness[clock_name])
            if window_open > float(observed_ts) and (
                next_window_open_ts is None or window_open < next_window_open_ts
            ):
                next_window_open_ts = window_open
    next_window = (
        datetime.fromtimestamp(next_window_open_ts, tz=UTC).isoformat().replace("+00:00", "Z")
        if next_window_open_ts is not None
        else None
    )
    return selected, {
        "discovered_market_count": len(markets),
        "eligible_market_count": len(selected),
        "eligible_clock_counts": dict(sorted(clock_counts.items())),
        "next_capture_window_opens_utc": next_window,
        "orderbook_requests_avoided": len(markets) - len(selected),
    }


def latest_snapshot_utc(snapshots: Sequence[Mapping[str, Any]]) -> str | None:
    values = [
        str(row.get("observed_at_utc"))
        for row in snapshots
        if timestamp(row.get("observed_at_utc")) is not None
    ]
    return max(values) if values else None


def cmd_register(*, out_dir: Path) -> dict[str, Any]:
    registration = build_panel_registration()
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "mlb-dense-panel-registration.json"
    md_path = out_dir / "mlb-dense-panel-registration.md"
    atomic_write_json(json_path, registration)
    atomic_write_text(md_path, registration_markdown(registration))
    # Latest aliases under macro.
    if out_dir.resolve() == DEFAULT_REG_DIR.resolve() or out_dir.parent == MACRO_DIR:
        atomic_write_json(
            MACRO_DIR / "latest-kalshi-sports-mlb-dense-panel-registration.json", registration
        )
        atomic_write_text(
            MACRO_DIR / "latest-kalshi-sports-mlb-dense-panel-registration.md",
            registration_markdown(registration),
        )
    return {
        "status": "panel_registration_written",
        "panel_family_id": PANEL_FAMILY_ID,
        "registration_sha256": registration.get("registration_sha256"),
        "json": str(json_path),
        "md": str(md_path),
        "frozen_candidate_count": len(registration.get("frozen_candidates") or []),
        "research_only": True,
        "execution_enabled": False,
    }


def enrich_capture_rows(
    rows: Sequence[Mapping[str, Any]], *, generated_utc: str
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["capture_generated_utc"] = generated_utc
        item.setdefault("request_timestamp_utc", item.get("observed_at_utc") or generated_utc)
        item["parse_version"] = "mlb_dense_panel_v1"
        item["series_ticker"] = item.get("series_ticker") or "KXMLBGAME"
        item["raw_payload_hash"] = snapshot_payload_hash(item)
        item["research_only"] = True
        item["execution_enabled"] = False
        enriched.append(item)
    return enriched


def cmd_capture(
    *,
    raw_dir: Path,
    book_dir: Path,
    status_dir: Path,
    limit: int,
    fetch_orderbook: bool,
    request_delay: float,
    write_repo_latest: bool = False,
) -> dict[str, Any]:
    lock = CaptureLock(raw_dir / "collector.lock")
    ok, lock_msg = lock.acquire()
    if not ok:
        return {
            "status": "capture_blocked_duplicate_collector",
            "detail": lock_msg,
            "research_only": True,
            "execution_enabled": False,
        }
    try:
        generated = utc_now()
        markets = list_open_mlb(limit=limit)
        eligible_markets, window_diagnostics = select_capture_window_markets(
            markets, observed_utc=generated
        )
        rows = capture_rows(
            eligible_markets,
            fetch_orderbook=fetch_orderbook,
            request_delay_seconds=request_delay,
        )
        enriched = enrich_capture_rows(rows, generated_utc=generated)
        raw_path = raw_dir / "mlb_dense_panel_snapshots.jsonl"
        # Load existing hashes for idempotent restart.
        existing = load_raw_snapshots(raw_path)
        seen = {str(row.get("raw_payload_hash") or snapshot_payload_hash(row)) for row in existing}
        append_stats = append_raw_snapshot_jsonl(raw_path, enriched, seen_hashes=seen)
        # Compact latest packet for compatibility with dense book helper consumers.
        packet_written = False
        if enriched:
            book_dir.mkdir(parents=True, exist_ok=True)
            packet = {
                "generated_utc": generated,
                "research_only": True,
                "execution_enabled": False,
                "packet_type": "kalshi_mlb_dense_panel_cycle",
                "rows": enriched,
                "count": len(enriched),
                "append_stats": append_stats,
                "window_diagnostics": window_diagnostics,
            }
            stamp = generated.replace(":", "").replace("-", "")
            atomic_write_json(book_dir / f"mlb_dense_panel_cycle_{stamp}.json", packet)
            atomic_write_json(book_dir / "mlb_dense_panel_cycle_latest.json", packet)
            packet_written = True

        # Re-read the append-only truth so skipped duplicates cannot inflate status.
        all_rows = load_raw_snapshots(raw_path)
        coverage = assess_panel_coverage(all_rows)
        health = health_status(
            lock_path=lock.path,
            raw_path=raw_path,
            coverage=coverage,
            last_capture_utc=latest_snapshot_utc(all_rows),
            last_cycle_utc=generated,
        )
        confirmation = frozen_candidate_confirmation_state(coverage)
        status_payload = {
            "generated_utc": generated,
            "panel_family_id": PANEL_FAMILY_ID,
            "capture": {
                "market_count": len(markets),
                **window_diagnostics,
                "row_count": len(enriched),
                "append_stats": append_stats,
                "lock": lock_msg,
                "packet_written": packet_written,
            },
            "coverage": coverage,
            "health": health,
            "frozen_confirmation": confirmation,
            "research_only": True,
            "execution_enabled": False,
            "candidate_performance_revealed": False,
        }
        status_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(status_dir / "mlb-dense-panel-status.json", status_payload)
        if write_repo_latest:
            atomic_write_json(
                MACRO_DIR / "latest-kalshi-sports-mlb-dense-panel-status.json", status_payload
            )
        return {
            "status": coverage.get("status"),
            "generated_utc": generated,
            "markets": len(markets),
            **window_diagnostics,
            "rows": len(enriched),
            "append_stats": append_stats,
            "distinct_events": coverage.get("distinct_events"),
            "distinct_slate_dates": coverage.get("distinct_slate_dates"),
            "evidence_panel_ready": coverage.get("evidence_panel_ready"),
            "raw_path": str(raw_path),
            "runtime_status_path": str(status_dir / "mlb-dense-panel-status.json"),
            "repo_latest_written": write_repo_latest,
            "research_only": True,
            "execution_enabled": False,
        }
    finally:
        lock.release()


def cmd_status(
    *, raw_dir: Path, status_dir: Path, write_repo_latest: bool = False
) -> dict[str, Any]:
    raw_path = raw_dir / "mlb_dense_panel_snapshots.jsonl"
    rows = load_raw_snapshots(raw_path)
    coverage = assess_panel_coverage(rows)
    health = health_status(
        lock_path=raw_dir / "collector.lock",
        raw_path=raw_path,
        coverage=coverage,
        last_capture_utc=latest_snapshot_utc(rows),
    )
    confirmation = frozen_candidate_confirmation_state(coverage)
    payload = {
        "generated_utc": utc_now(),
        "panel_family_id": PANEL_FAMILY_ID,
        "coverage": coverage,
        "health": health,
        "frozen_confirmation": confirmation,
        "research_only": True,
        "execution_enabled": False,
        "candidate_performance_revealed": False,
        "next_action": (
            "run_single_shot_frozen_confirmation"
            if confirmation.get("confirmation_power_met")
            else ("continue_dense_capture_accumulation; do not model or retune")
        ),
        "capture_cadence_seconds": CAPTURE_CADENCE_SECONDS,
        "scheduling_note": (
            f"Recommended: systemd user timer or cron every {CAPTURE_CADENCE_SECONDS}s "
            "invoking `python scripts/kalshi_sports_mlb_dense_panel_ops.py capture`. "
            "PID lock prevents duplicate collectors."
        ),
    }
    status_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(status_dir / "mlb-dense-panel-status.json", payload)
    if write_repo_latest:
        atomic_write_json(MACRO_DIR / "latest-kalshi-sports-mlb-dense-panel-status.json", payload)
    return {
        "status": coverage.get("status"),
        "evidence_panel_ready": coverage.get("evidence_panel_ready"),
        "distinct_events": coverage.get("distinct_events"),
        "distinct_slate_dates": coverage.get("distinct_slate_dates"),
        "gates": coverage.get("gates"),
        "frozen_confirmation": confirmation,
        "research_only": True,
        "execution_enabled": False,
        "runtime_status_path": str(status_dir / "mlb-dense-panel-status.json"),
        "repo_latest_written": write_repo_latest,
    }


def cmd_replay(*, raw_dir: Path) -> dict[str, Any]:
    raw_path = raw_dir / "mlb_dense_panel_snapshots.jsonl"
    rows = load_raw_snapshots(raw_path)
    coverage = assess_panel_coverage(rows)
    return {
        "status": "replay_ok",
        "network_access": False,
        "snapshot_count": len(rows),
        "coverage": coverage,
        "frozen_confirmation": frozen_candidate_confirmation_state(coverage),
        "research_only": True,
        "execution_enabled": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    reg = sub.add_parser("register", help="Write preregistration artifacts")
    reg.add_argument("--out-dir", type=Path, default=DEFAULT_REG_DIR)

    cap = sub.add_parser("capture", help="One restart-safe capture cycle")
    cap.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    cap.add_argument("--book-dir", type=Path, default=DEFAULT_BOOK_DIR)
    cap.add_argument("--status-dir", type=Path, default=DEFAULT_STATUS_DIR)
    cap.add_argument("--limit", type=int, default=200)
    cap.add_argument("--fetch-orderbook", action=argparse.BooleanOptionalAction, default=True)
    cap.add_argument("--request-delay-seconds", type=float, default=0.08)
    cap.add_argument(
        "--write-repo-latest", action=argparse.BooleanOptionalAction, default=False
    )

    st = sub.add_parser("status", help="Panel health/readiness without P&L")
    st.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    st.add_argument("--status-dir", type=Path, default=DEFAULT_STATUS_DIR)
    st.add_argument(
        "--write-repo-latest", action=argparse.BooleanOptionalAction, default=False
    )

    rp = sub.add_parser("replay", help="Offline replay from raw JSONL")
    rp.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)

    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "register":
            result = cmd_register(out_dir=args.out_dir)
        elif args.command == "capture":
            result = cmd_capture(
                raw_dir=args.raw_dir,
                book_dir=args.book_dir,
                status_dir=args.status_dir,
                limit=int(args.limit),
                fetch_orderbook=bool(args.fetch_orderbook),
                request_delay=float(args.request_delay_seconds),
                write_repo_latest=bool(args.write_repo_latest),
            )
        elif args.command == "status":
            result = cmd_status(
                raw_dir=args.raw_dir,
                status_dir=args.status_dir,
                write_repo_latest=bool(args.write_repo_latest),
            )
        elif args.command == "replay":
            result = cmd_replay(raw_dir=args.raw_dir)
        else:
            raise SystemExit(f"unknown command {args.command}")
    except (
        OSError,
        ValueError,
        TimeoutError,
        json.JSONDecodeError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    # Allow `from scripts...` when run as file by ensuring package path.
    raise SystemExit(main())
