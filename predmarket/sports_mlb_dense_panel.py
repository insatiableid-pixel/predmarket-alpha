"""Dense multi-slate MLB fixed-clock order-book panel (research-only).

Preregistration, coverage/readiness gates, offline replay helpers, and
process-safe capture bookkeeping for KXMLBGAME. Does not size, stake, or trade.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from predmarket.shared_helpers import json_float, optional_float, timestamp
from predmarket.sports_mlb_settlement_miscalibration import (
    ANALYSIS_CONTRACT_VERSION,
    FAMILY_ID,
    SERIES_ALLOWLIST,
    sha256_file,
    sha256_text,
)

PANEL_FAMILY_ID = "sports_mlb_dense_fixed_clock_panel_v1"
PANEL_REGISTRATION_VERSION = "mlb_dense_panel_registration_v1"
PRIMARY_CLOCKS_SECONDS: dict[str, int] = {
    "T-60m": 3600,
    "T-15m": 900,
}
SECONDARY_CLOCKS_SECONDS: dict[str, int] = {
    "T-24h": 24 * 3600,
    "T-6h": 6 * 3600,
}
# Dense-panel staleness (stricter than sparse discovery ceilings).
PRIMARY_STALENESS_SECONDS: dict[str, int] = {
    "T-60m": 5 * 60,
    "T-15m": 2 * 60,
}
SECONDARY_STALENESS_SECONDS: dict[str, int] = {
    "T-24h": 30 * 60,
    "T-6h": 15 * 60,
}

# Preregistered panel-readiness gates (do not tune on candidate P&L).
MIN_SLATE_DATES = 10
MIN_EVENTS_OVERALL = 120
MIN_EVENTS_PER_PRIMARY_CLOCK = 100
MIN_SLATES_PER_CANDIDATE = 8
MAX_SLATE_SHARE = 0.20
MIN_PUBLIC_ORDERBOOK_SOURCE_SHARE = 0.95
MIN_EXECUTABLE_DEPTH_SHARE = 0.90
P90_STALENESS_T60M_SECONDS = 5 * 60
P90_STALENESS_T15M_SECONDS = 2 * 60

# Capture cadence (seconds) around primary clocks; public rate-limit friendly.
CAPTURE_CADENCE_SECONDS = 60
REQUEST_DELAY_SECONDS = 0.08

# Frozen candidate from repaired PR #71 discovery (exact; do not retune).
FROZEN_CANDIDATES: tuple[dict[str, Any], ...] = (
    {
        "model_id": "tight_spread_favorite_buy_yes_t60m",
        "clock_name": "T-60m",
        "side": "yes",
        "feature": "p_hat",
        "direction": "gt_and_spread_le",
        "threshold": 0.62,
        "spread_max": 0.03,
        "formula_hash": ("9cd76b9703cd167988fd94d53a9cc82ed9b37a7e3b30f316796f9dbb46cfa56d"),
        "source_family": FAMILY_ID,
        "analysis_contract_version": ANALYSIS_CONTRACT_VERSION,
        "forward_confirmation_registered_at_utc": "2026-07-10T05:37:38Z",
        "historical_discovery_data_cutoff_utc": "2026-07-10T05:18:29Z",
        "fee_rule": "executable_ask_plus_series_resolved_taker_entry_fee",
        "as_of_rule": "strict_latest_book_at_or_before_clock_within_staleness",
        "status": "frozen_candidate_waiting_multi_slate_confirmation",
        "do_not_retune": True,
    },
)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def slate_date_from_ts(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts), tz=UTC).strftime("%Y-%m-%d")


def build_panel_registration(*, generated_utc: str | None = None) -> dict[str, Any]:
    generated = generated_utc or utc_now_iso()
    registration = {
        "schema_version": 1,
        "registration_version": PANEL_REGISTRATION_VERSION,
        "panel_family_id": PANEL_FAMILY_ID,
        "generated_utc": generated,
        "research_only": True,
        "execution_enabled": False,
        "market_family": {
            "series_allowlist": sorted(SERIES_ALLOWLIST),
            "ticker_prefix": "KXMLBGAME",
            "scope_note": "KXMLBGAME only unless a later distinct family is separately registered",
        },
        "event_identity": {
            "primary_key": "event_ticker",
            "complementary_contracts": "collapse_to_one_event_for_independence",
            "doubleheaders": "distinct event_ticker per listing; slate_date from game_start",
            "postponements_relistings": "track by event_ticker; reschedule updates game_start_ts",
            "multiple_clocks_same_game": "repeated_measures_not_independent",
        },
        "clocks": {
            "primary": PRIMARY_CLOCKS_SECONDS,
            "secondary": SECONDARY_CLOCKS_SECONDS,
            "primary_staleness_seconds": PRIMARY_STALENESS_SECONDS,
            "secondary_staleness_seconds": SECONDARY_STALENESS_SECONDS,
            "missing_long_horizon_listings_do_not_block_primary_readiness": True,
        },
        "capture": {
            "cadence_seconds": CAPTURE_CADENCE_SECONDS,
            "request_delay_seconds": REQUEST_DELAY_SECONDS,
            "source": "public_kalshi_rest_orderbook_and_markets",
            "auth": "public_read_only",
            "append_only_raw": True,
            "atomic_writes": True,
            "duplicate_suppression": "snapshot_id_and_payload_hash",
        },
        "book_quality_gates": {
            "public_orderbook_source_share_min": MIN_PUBLIC_ORDERBOOK_SOURCE_SHARE,
            "executable_side_and_depth_share_min": MIN_EXECUTABLE_DEPTH_SHARE,
            "p90_staleness_seconds": {
                "T-60m": P90_STALENESS_T60M_SECONDS,
                "T-15m": P90_STALENESS_T15M_SECONDS,
            },
        },
        "panel_readiness_gates": {
            "min_distinct_slate_dates": MIN_SLATE_DATES,
            "min_distinct_events_overall": MIN_EVENTS_OVERALL,
            "min_eligible_events_per_primary_clock": MIN_EVENTS_PER_PRIMARY_CLOCK,
            "min_independent_slates_per_tested_candidate": MIN_SLATES_PER_CANDIDATE,
            "max_largest_slate_share": MAX_SLATE_SHARE,
            "zero_unhandled_duplicates_complements_lookahead": True,
            "complete_settlement_provenance_for_labeled_inference": True,
        },
        "fee_rules": {
            "series": "KXMLBGAME",
            "mode": "taker_entry_only_hold_to_settlement",
            "resolver": "resolve_kxmlbgame_taker_fee with offline conservative quadratic fallback",
            "uncertainty_blocks_research_ready": True,
        },
        "inference": {
            "cluster_unit": "mlb_slate_date_utc",
            "independence_unit": "event_ticker",
            "method": "slate_cluster_sign_flip + BH on p_joint for novel families",
            "evaluation_policy": "single_evaluation_at_preregistered_power_not_continuous_peeking",
            "no_modeling_before_evidence_panel_ready": True,
        },
        "frozen_candidates": list(FROZEN_CANDIDATES),
        "roles": {
            "discovery": "not_started_until_panel_ready_and_frozen_candidates_resolved",
            "confirmation": "frozen_candidates_only_on_strictly_post_registration_events",
        },
        "states": {
            "accumulating": "panel gates not yet met; coverage diagnostics only",
            "evidence_panel_ready": "all preregistered coverage/quality gates pass",
            "confirmation_pending": "frozen candidate awaiting powered confirmation sample",
            "confirmation_failed": "frozen candidate failed at preregistered power",
            "research_ready_survivor": "passed discovery+confirmation; research only",
            "outcome_b": "all members resolved without survivor at full power",
        },
        "failure_continuation": {
            "calendar_pending": "not a blocker; keep collector restart-safe and report forecast",
            "do_not_weaken_gates": True,
            "do_not_retune_frozen_candidates": True,
            "v2_family_only_after_frozen_resolution_and_panel_ready": True,
        },
    }
    payload = json.dumps(registration, sort_keys=True, separators=(",", ":"))
    registration["registration_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return registration


def registration_markdown(registration: Mapping[str, Any]) -> str:
    frozen = registration.get("frozen_candidates") or []
    lines = [
        "# MLB Dense Fixed-Clock Panel Registration",
        "",
        f"- Panel family: `{registration.get('panel_family_id')}`",
        f"- Registration version: `{registration.get('registration_version')}`",
        f"- Generated: `{registration.get('generated_utc')}`",
        f"- Registration hash: `{registration.get('registration_sha256')}`",
        f"- Research only: `{registration.get('research_only')}`",
        "",
        "## Primary clocks",
        "",
        f"- Primary: `{(registration.get('clocks') or {}).get('primary')}`",
        f"- Primary staleness: `{(registration.get('clocks') or {}).get('primary_staleness_seconds')}`",
        f"- Secondary: `{(registration.get('clocks') or {}).get('secondary')}`",
        "",
        "## Panel readiness gates",
        "",
    ]
    for key, value in (registration.get("panel_readiness_gates") or {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Frozen candidates (exact; do not retune)", ""])
    for row in frozen:
        lines.append(
            f"- `{row.get('model_id')}` clock=`{row.get('clock_name')}` "
            f"side=`{row.get('side')}` feature=`{row.get('feature')}` "
            f"threshold=`{row.get('threshold')}` spread_max=`{row.get('spread_max')}` "
            f"formula_hash=`{row.get('formula_hash')}` "
            f"registered=`{row.get('forward_confirmation_registered_at_utc')}`"
        )
    lines.extend(
        [
            "",
            "## Operating rules",
            "",
            "- No outcome-conditioned threshold search until `evidence_panel_ready`.",
            "- Frozen candidates evaluated once at preregistered confirmation power only.",
            "- At most one distinct v2 family after frozen-candidate resolution.",
            "- No live execution, sizing, accounts, orders, or credentials.",
            "",
        ]
    )
    return "\n".join(lines)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


class CaptureLock:
    """Exclusive process ownership via PID file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.held = False

    def acquire(self) -> tuple[bool, str]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                existing = int(self.path.read_text(encoding="utf-8").strip() or "0")
            except ValueError:
                existing = 0
            if existing > 0 and _pid_alive(existing):
                return False, f"collector_already_running pid={existing}"
        atomic_write_text(self.path, f"{os.getpid()}\n")
        self.held = True
        return True, f"acquired pid={os.getpid()}"

    def release(self) -> None:
        if not self.held:
            return
        try:
            if self.path.exists() and self.path.read_text(encoding="utf-8").strip() == str(
                os.getpid()
            ):
                self.path.unlink(missing_ok=True)
        finally:
            self.held = False


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def snapshot_payload_hash(row: Mapping[str, Any]) -> str:
    keys = (
        "contract_ticker",
        "observed_at_utc",
        "best_yes_bid",
        "best_yes_ask",
        "best_no_bid",
        "best_no_ask",
        "yes_bid_depth_top1",
        "yes_ask_depth_top1",
    )
    material = {key: row.get(key) for key in keys}
    return sha256_text(json.dumps(material, sort_keys=True, separators=(",", ":")))


def append_raw_snapshot_jsonl(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    seen_hashes: set[str] | None = None,
) -> dict[str, int]:
    """Append-only raw snapshots with duplicate suppression by payload hash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = seen_hashes if seen_hashes is not None else set()
    written = 0
    skipped = 0
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            item = dict(row)
            digest = str(item.get("raw_payload_hash") or snapshot_payload_hash(item))
            item["raw_payload_hash"] = digest
            if digest in seen:
                skipped += 1
                continue
            seen.add(digest)
            handle.write(json.dumps(item, sort_keys=True) + "\n")
            written += 1
    return {"written": written, "skipped_duplicates": skipped}


def load_raw_snapshots(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, Mapping):
            rows.append(dict(payload))
    return rows


def percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = min(max(q, 0.0), 1.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(len(ordered) - 1, low + 1)
    frac = rank - low
    return ordered[low] * (1.0 - frac) + ordered[high] * frac


def public_orderbook_source_ok(row: Mapping[str, Any]) -> bool:
    explicit = row.get("orderbook_fetch_succeeded")
    if explicit is not None:
        return explicit is True
    source = str(row.get("entry_source") or "").lower()
    has_depth = any(
        optional_float(row.get(key)) is not None
        for key in (
            "yes_bid_depth_top1",
            "yes_ask_depth_top1",
            "no_bid_depth_top1",
            "no_ask_depth_top1",
        )
    )
    return "orderbook" in source and has_depth


def assess_panel_coverage(  # noqa: C901
    snapshots: Sequence[Mapping[str, Any]],
    *,
    settlements: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Coverage/freshness/integrity diagnostics only — no candidate P&L."""
    by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_counts: Counter[str] = Counter()
    for row in snapshots:
        event = str(row.get("event_ticker") or "")
        ticker = str(row.get("contract_ticker") or "")
        if not ticker.startswith("KXMLBGAME"):
            continue
        if not event:
            event = ticker.rsplit("-", 1)[0]
        item = dict(row)
        item["_event"] = event
        by_event[event].append(item)
        source_counts[str(row.get("entry_source") or "unknown")] += 1

    # Event-level dedupe for independence accounting.
    events = sorted(by_event)
    slate_dates: set[str] = set()
    for _event, rows in by_event.items():
        starts = [
            optional_float(r.get("game_start_ts"))
            or timestamp(r.get("occurrence_datetime") or r.get("expected_expiration_time"))
            for r in rows
        ]
        starts = [s for s in starts if s is not None]
        if starts:
            slate = slate_date_from_ts(min(starts))
            if slate:
                slate_dates.add(slate)

    primary_event_counts: dict[str, int] = {}
    primary_staleness: dict[str, list[float]] = {name: [] for name in PRIMARY_CLOCKS_SECONDS}
    executable_ok = 0
    depth_ok = 0
    orderbook_ok = 0
    eligible_primary = 0
    for clock_name, offset in PRIMARY_CLOCKS_SECONDS.items():
        count = 0
        for _event, rows in by_event.items():
            starts = [
                optional_float(r.get("game_start_ts"))
                or timestamp(r.get("occurrence_datetime") or r.get("expected_expiration_time"))
                for r in rows
            ]
            starts = [s for s in starts if s is not None]
            if not starts:
                continue
            game_start = min(starts)
            clock_ts = float(game_start) - float(offset)
            # Strict as-of: latest observation <= clock.
            candidates = []
            for row in rows:
                obs = timestamp(row.get("observed_at_utc")) or optional_float(
                    row.get("observed_ts")
                )
                if obs is None or obs > clock_ts:
                    continue
                candidates.append((obs, row))
            if not candidates:
                continue
            obs_ts, book = max(candidates, key=lambda item: item[0])
            age = clock_ts - float(obs_ts)
            max_age = float(PRIMARY_STALENESS_SECONDS[clock_name])
            if age > max_age:
                continue
            count += 1
            primary_staleness[clock_name].append(age)
            eligible_primary += 1
            yes_ask = optional_float(book.get("best_yes_ask"))
            no_ask = optional_float(book.get("best_no_ask"))
            if (yes_ask is not None and 0 < yes_ask < 1) or (no_ask is not None and 0 < no_ask < 1):
                executable_ok += 1
            depth = optional_float(book.get("yes_ask_depth_top1")) or optional_float(
                book.get("no_ask_depth_top1")
            )
            if depth is not None and depth > 0:
                depth_ok += 1
            if public_orderbook_source_ok(book):
                orderbook_ok += 1
        primary_event_counts[clock_name] = count

    source_share = (orderbook_ok / eligible_primary) if eligible_primary else 0.0
    exec_share = (executable_ok / eligible_primary) if eligible_primary else 0.0
    depth_share = (depth_ok / eligible_primary) if eligible_primary else 0.0
    p90_t60 = percentile(primary_staleness["T-60m"], 0.90)
    p90_t15 = percentile(primary_staleness["T-15m"], 0.90)

    settlement_complete = True
    settlement_labeled = 0
    if settlements:
        for event in events:
            # Any contract under event with settlement counts.
            tickers = {
                str(row.get("contract_ticker"))
                for row in by_event[event]
                if row.get("contract_ticker")
            }
            if any(ticker in settlements for ticker in tickers):
                settlement_labeled += 1
        # Not required for infrastructure readiness; required for inference readiness.
        settlement_complete = settlement_labeled == len(events) if events else False

    gates = {
        "min_distinct_slate_dates": len(slate_dates) >= MIN_SLATE_DATES,
        "min_distinct_events_overall": len(events) >= MIN_EVENTS_OVERALL,
        "min_events_t60m": primary_event_counts.get("T-60m", 0) >= MIN_EVENTS_PER_PRIMARY_CLOCK,
        "min_events_t15m": primary_event_counts.get("T-15m", 0) >= MIN_EVENTS_PER_PRIMARY_CLOCK,
        "public_orderbook_source_share": source_share >= MIN_PUBLIC_ORDERBOOK_SOURCE_SHARE,
        "executable_depth_share": (
            exec_share >= MIN_EXECUTABLE_DEPTH_SHARE and depth_share >= MIN_EXECUTABLE_DEPTH_SHARE
        ),
        "p90_staleness_t60m": (p90_t60 is not None and p90_t60 <= P90_STALENESS_T60M_SECONDS),
        "p90_staleness_t15m": (p90_t15 is not None and p90_t15 <= P90_STALENESS_T15M_SECONDS),
    }
    evidence_panel_ready = all(gates.values())
    return {
        "capture_infrastructure_ready": True,
        "evidence_panel_ready": evidence_panel_ready,
        "status": (
            "evidence_panel_ready"
            if evidence_panel_ready
            else "capture_infrastructure_ready_panel_accumulating"
        ),
        "snapshot_count": len(snapshots),
        "distinct_events": len(events),
        "distinct_slate_dates": len(slate_dates),
        "slate_dates": sorted(slate_dates),
        "primary_event_counts": primary_event_counts,
        "source_counts": dict(source_counts),
        "public_orderbook_source_share": json_float(source_share),
        "executable_side_share": json_float(exec_share),
        "depth_share": json_float(depth_share),
        "p90_staleness_seconds": {
            "T-60m": json_float(p90_t60),
            "T-15m": json_float(p90_t15),
        },
        "gates": {name: ("pass" if ok else "fail") for name, ok in gates.items()},
        "settlement_labeled_events": settlement_labeled if settlements is not None else None,
        "settlement_complete_for_all_events": settlement_complete if settlements else None,
        "research_only": True,
        "execution_enabled": False,
        "candidate_performance_revealed": False,
    }


def health_status(
    *,
    lock_path: Path,
    raw_path: Path,
    coverage: Mapping[str, Any],
    last_capture_utc: str | None = None,
    last_cycle_utc: str | None = None,
) -> dict[str, Any]:
    lock_pid = None
    lock_alive = False
    if lock_path.exists():
        try:
            lock_pid = int(lock_path.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            lock_pid = None
        if lock_pid:
            lock_alive = _pid_alive(lock_pid)
    return {
        "process_health": {
            "lock_path": str(lock_path),
            "lock_pid": lock_pid,
            "lock_holder_alive": lock_alive,
            "lock_held_by_current_process": lock_pid == os.getpid(),
            "collector_running_at_status_time": bool(lock_alive),
            "duplicate_collector_blocked": bool(lock_alive and lock_pid != os.getpid()),
        },
        "infrastructure_ready": bool(coverage.get("capture_infrastructure_ready")),
        "panel_accumulation": {
            "snapshot_count": coverage.get("snapshot_count"),
            "distinct_events": coverage.get("distinct_events"),
            "distinct_slate_dates": coverage.get("distinct_slate_dates"),
            "primary_event_counts": coverage.get("primary_event_counts"),
            "raw_path": str(raw_path),
            "raw_exists": raw_path.is_file(),
            "raw_sha256": sha256_file(raw_path) if raw_path.is_file() else None,
        },
        "evidence_ready": bool(coverage.get("evidence_panel_ready")),
        "status": coverage.get("status"),
        "last_capture_utc": last_capture_utc,
        "last_cycle_utc": last_cycle_utc,
        "research_only": True,
        "execution_enabled": False,
    }


def confirmation_power_met(coverage: Mapping[str, Any], *, clock_name: str = "T-60m") -> bool:
    """Panel-level power proxy for frozen confirmation (no P&L peek)."""
    if not coverage.get("evidence_panel_ready"):
        return False
    events = int((coverage.get("primary_event_counts") or {}).get(clock_name) or 0)
    slates = int(coverage.get("distinct_slate_dates") or 0)
    return events >= MIN_EVENTS_PER_PRIMARY_CLOCK and slates >= MIN_SLATES_PER_CANDIDATE


def frozen_candidate_confirmation_state(coverage: Mapping[str, Any]) -> dict[str, Any]:
    """Honest confirmation state without evaluating outcomes until powered."""
    powered = confirmation_power_met(coverage, clock_name="T-60m")
    states = []
    for cand in FROZEN_CANDIDATES:
        if not powered:
            status = "confirmation_pending"
            reason = "panel_or_confirmation_power_not_met"
        else:
            # Outcomes must be joined in a separate single-shot evaluation pass.
            status = "confirmation_ready_for_single_shot_eval"
            reason = "panel_ready_and_confirmation_power_met_run_single_eval"
        states.append(
            {
                **cand,
                "confirmation_status": status,
                "confirmation_reason": reason,
                "do_not_retune": True,
            }
        )
    return {
        "evidence_panel_ready": bool(coverage.get("evidence_panel_ready")),
        "confirmation_power_met": powered,
        "candidates": states,
        "research_only": True,
        "execution_enabled": False,
    }
