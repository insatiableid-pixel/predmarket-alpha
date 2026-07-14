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
import shutil
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
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
    latest_observed_event_schedule,
    load_raw_snapshots,
    registration_markdown,
    row_game_start_ts,
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
DEFAULT_LOG_DIR = manual_drop_path(
    "kalshi_sports_mlb_dense_panel_logs",
    env_vars=("KALSHI_SPORTS_MLB_DENSE_PANEL_LOG_DIR",),
)

# Dense-panel operational controls.
MAX_CAPTURE_DEADLINE_SECONDS = 300  # outer deadline for one capture cycle
MAX_BOUNDED_RETRIES_PER_MARKET = 2
DISK_CEILING_BYTES = 500 * 1024 * 1024  # 500 MB max raw data before alarm
FRESHNESS_ALARM_SECONDS = 600  # warn if last capture older than 10 minutes
DENSE_PANEL_SCRIPT_VERSION = "mlb_dense_panel_ops_v2"


def _rotate_collector_log(log_dir: Path) -> None:
    """Rotate collector.log if it exists and is too large."""
    import hashlib
    log_path = log_dir / "collector.log"
    if not log_path.is_file():
        return
    MAX_LOG_SIZE = 10 * 1024 * 1024
    if log_path.stat().st_size <= MAX_LOG_SIZE:
        return
    MAX_BACKUPS = 5
    for i in range(MAX_BACKUPS - 1, 0, -1):
        src = log_dir / f"collector.log.{i}"
        src_meta = log_dir / f"collector.log.{i}.meta.json"
        dst = log_dir / f"collector.log.{i+1}"
        dst_meta = log_dir / f"collector.log.{i+1}.meta.json"
        if src.is_file():
            if dst.is_file():
                dst.unlink()
            src.rename(dst)
        if src_meta.is_file():
            if dst_meta.is_file():
                dst_meta.unlink()
            src_meta.rename(dst_meta)

    backup_path = log_dir / "collector.log.1"
    backup_meta_path = log_dir / "collector.log.1.meta.json"
    try:
        content = log_path.read_bytes()
        sha256 = hashlib.sha256(content).hexdigest()
        backup_path.write_bytes(content)
        meta = {
            "rotated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "original_size_bytes": len(content),
            "sha256": sha256,
        }
        backup_meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        log_path.write_bytes(b"")
    except Exception as exc:
        sys.stderr.write(f"Warning: collector log rotation failed: {exc}\n")



def eligible_capture_clocks(market: Mapping[str, Any], *, observed_utc: str) -> tuple[str, ...]:
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
        if 0.0 <= float(game_start) - float(offset) - float(observed_ts) <= float(staleness[name])
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


def _disk_usage_ok(raw_dir: Path) -> tuple[bool, str]:
    """Check disk usage for raw data directory."""
    total = sum(
        f.stat().st_size for f in raw_dir.rglob("*") if f.is_file()
    ) if raw_dir.is_dir() else 0
    ok = total <= DISK_CEILING_BYTES
    msg = (
        f"raw data disk usage {total} bytes / {DISK_CEILING_BYTES} ceiling OK"
        if ok
        else f"raw data disk usage {total} bytes exceeds {DISK_CEILING_BYTES} ceiling"
    )
    return ok, msg


def _freshness_alarm(last_capture_utc: str | None) -> tuple[bool, str | None]:
    """Return stale alarm if latest snapshot exceeds freshness threshold."""
    if last_capture_utc is None:
        return True, "no captures yet"
    ts = timestamp(last_capture_utc)
    if ts is None:
        return True, "cannot parse last_capture_utc"
    elapsed = time.time() - ts
    if elapsed > FRESHNESS_ALARM_SECONDS:
        return True, f"last capture {elapsed:.0f}s ago exceeds {FRESHNESS_ALARM_SECONDS}s threshold"
    return False, None


def _runtime_info() -> dict[str, Any]:
    return {
        "script_version": DENSE_PANEL_SCRIPT_VERSION,
        "capture_cadence_seconds": CAPTURE_CADENCE_SECONDS,
        "outer_deadline_seconds": MAX_CAPTURE_DEADLINE_SECONDS,
        "bounded_retries_per_market": MAX_BOUNDED_RETRIES_PER_MARKET,
        "disk_ceiling_bytes": DISK_CEILING_BYTES,
        "freshness_alarm_seconds": FRESHNESS_ALARM_SECONDS,
    }


def build_schedule_revision_rows(
    markets: Sequence[Mapping[str, Any]],
    existing_rows: Sequence[Mapping[str, Any]],
    *,
    generated_utc: str,
) -> list[dict[str, Any]]:
    """Persist changed starts for known events without requesting an order book."""
    existing_by_event: dict[str, list[dict[str, Any]]] = {}
    for raw in existing_rows:
        ticker = str(raw.get("contract_ticker") or "")
        event = str(raw.get("event_ticker") or ticker.rsplit("-", 1)[0])
        if event:
            existing_by_event.setdefault(event, []).append(dict(raw))
    known_starts = {
        event: latest_observed_event_schedule(rows)[0] for event, rows in existing_by_event.items()
    }

    revisions: list[dict[str, Any]] = []
    handled_events: set[str] = set()
    for market in markets:
        ticker = str(market.get("ticker") or "")
        event = str(market.get("event_ticker") or ticker.rsplit("-", 1)[0])
        current_start = row_game_start_ts(market)
        previous_start = known_starts.get(event)
        if (
            not event
            or event in handled_events
            or current_start is None
            or previous_start is None
            or float(current_start) == float(previous_start)
        ):
            continue
        handled_events.add(event)
        marker = {
            "snapshot_id": f"schedule-revision|{event}|{int(float(current_start))}",
            "contract_ticker": ticker,
            "event_ticker": event,
            "series_ticker": "KXMLBGAME",
            "observed_at_utc": generated_utc,
            "request_timestamp_utc": generated_utc,
            "capture_generated_utc": generated_utc,
            "game_start_ts": float(current_start),
            "previous_game_start_ts": float(previous_start),
            "occurrence_datetime": market.get("occurrence_datetime"),
            "expected_expiration_time": market.get("expected_expiration_time"),
            "entry_source": "public_kalshi_market_schedule_revision",
            "schedule_revision": True,
            "orderbook_fetch_succeeded": False,
            "usable": False,
            "research_only": True,
            "execution_enabled": False,
        }
        marker["raw_payload_hash"] = snapshot_payload_hash(marker)
        revisions.append(marker)
    return revisions


def cmd_capture(
    *,
    raw_dir: Path,
    book_dir: Path,
    status_dir: Path,
    limit: int,
    fetch_orderbook: bool,
    request_delay: float,
    write_repo_latest: bool = False,
    log_dir: Path | None = None,
) -> dict[str, Any]:
    deadline = time.time() + MAX_CAPTURE_DEADLINE_SECONDS

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
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / "mlb_dense_panel_snapshots.jsonl"

        # Disk ceiling check before collection.
        disk_ok, disk_msg = _disk_usage_ok(raw_dir)
        if not disk_ok:
            return {
                "status": "capture_aborted_disk_ceiling_exceeded",
                "detail": disk_msg,
                "research_only": True,
                "execution_enabled": False,
            }

        # Log retention for collector log.
        if log_dir is not None:
            _rotate_collector_log(log_dir)

        markets = list_open_mlb(limit=limit)
        existing = load_raw_snapshots(raw_path)
        stale, stale_msg = _freshness_alarm(latest_snapshot_utc(existing))

        schedule_revisions = build_schedule_revision_rows(
            markets,
            existing,
            generated_utc=generated,
        )
        eligible_markets, window_diagnostics = select_capture_window_markets(
            markets, observed_utc=generated
        )

        # Bounded retries with outer deadline.
        rows = capture_rows(
            eligible_markets,
            fetch_orderbook=fetch_orderbook,
            request_delay_seconds=request_delay,
            max_retries_per_market=MAX_BOUNDED_RETRIES_PER_MARKET,
            deadline=deadline,
        )

        enriched = enrich_capture_rows(rows, generated_utc=generated)
        # Load existing hashes for idempotent restart.
        seen = {str(row.get("raw_payload_hash") or snapshot_payload_hash(row)) for row in existing}
        append_stats = append_raw_snapshot_jsonl(
            raw_path,
            [*schedule_revisions, *enriched],
            seen_hashes=seen,
        )
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
                "schedule_revision_row_count": len(schedule_revisions),
                "append_stats": append_stats,
                "lock": lock_msg,
                "packet_written": packet_written,
                "max_bounded_retries": MAX_BOUNDED_RETRIES_PER_MARKET,
                "deadline_seconds": MAX_CAPTURE_DEADLINE_SECONDS,
            },
            "coverage": coverage,
            "health": health,
            "frozen_confirmation": confirmation,
            "research_only": True,
            "execution_enabled": False,
            "candidate_performance_revealed": False,
            "runtime": _runtime_info(),
            "controls": {
                "stale": stale,
                "stale_detail": stale_msg,
                "disk_ok": disk_ok,
                "disk_detail": disk_msg,
            },
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
            "schedule_revision_rows": len(schedule_revisions),
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
    *, raw_dir: Path, status_dir: Path, write_repo_latest: bool = False, check: bool = False
) -> dict[str, Any]:
    raw_path = raw_dir / "mlb_dense_panel_snapshots.jsonl"
    rows = load_raw_snapshots(raw_path)
    coverage = assess_panel_coverage(rows)
    last_cap_utc = latest_snapshot_utc(rows)
    stale, stale_msg = _freshness_alarm(last_cap_utc)
    disk_ok, disk_msg = _disk_usage_ok(raw_dir)
    health = health_status(
        lock_path=raw_dir / "collector.lock",
        raw_path=raw_path,
        coverage=coverage,
        last_capture_utc=last_cap_utc,
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
        "runtime": _runtime_info(),
        "controls": {
            "stale": stale,
            "stale_detail": stale_msg,
            "disk_ok": disk_ok,
            "disk_detail": disk_msg,
        },
        "scheduling_note": (
            f"Recommended: systemd user timer or cron every {CAPTURE_CADENCE_SECONDS}s "
            "invoking `python scripts/kalshi_sports_mlb_dense_panel_ops.py capture`. "
            "PID lock prevents duplicate collectors."
        ),
    }
    if check:
        all_ok = (
            bool(coverage.get("capture_infrastructure_ready"))
            and not stale
            and disk_ok
        )
        payload["preflight_check"] = {
            "all_ok": all_ok,
            "infrastructure_ready": bool(coverage.get("capture_infrastructure_ready")),
            "freshness_ok": not stale,
            "disk_ok": disk_ok,
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
        "preflight_check": payload.get("preflight_check"),
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
    cap.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    cap.add_argument("--limit", type=int, default=200)
    cap.add_argument("--fetch-orderbook", action=argparse.BooleanOptionalAction, default=True)
    cap.add_argument("--request-delay-seconds", type=float, default=0.08)
    cap.add_argument("--write-repo-latest", action=argparse.BooleanOptionalAction, default=False)

    st = sub.add_parser("status", help="Panel health/readiness without P&L")
    st.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    st.add_argument("--status-dir", type=Path, default=DEFAULT_STATUS_DIR)
    st.add_argument("--write-repo-latest", action=argparse.BooleanOptionalAction, default=False)
    st.add_argument("--check", action="store_true", help="Outcome-blind preflight check (no capture)")

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
                log_dir=args.log_dir,
            )
        elif args.command == "status":
            result = cmd_status(
                raw_dir=args.raw_dir,
                status_dir=args.status_dir,
                write_repo_latest=bool(args.write_repo_latest),
                check=bool(args.check),
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
