from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from predmarket.sports_mlb_dense_panel import (
    FROZEN_CANDIDATES,
    MIN_EVENTS_OVERALL,
    MIN_SLATE_DATES,
    CaptureLock,
    append_raw_snapshot_jsonl,
    assess_panel_coverage,
    build_panel_registration,
    confirmation_power_met,
    frozen_candidate_confirmation_state,
    load_raw_snapshots,
    registration_markdown,
    snapshot_payload_hash,
)


def load_ops():
    path = Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_mlb_dense_panel_ops.py"
    spec = importlib.util.spec_from_file_location("kalshi_sports_mlb_dense_panel_ops", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_registration_is_hashed_and_freezes_candidate() -> None:
    reg = build_panel_registration(generated_utc="2026-07-10T06:00:00Z")
    assert reg["panel_family_id"] == "sports_mlb_dense_fixed_clock_panel_v1"
    assert reg["registration_sha256"]
    assert reg["research_only"] is True
    assert reg["execution_enabled"] is False
    frozen = reg["frozen_candidates"]
    assert len(frozen) == 1
    assert frozen[0]["model_id"] == "tight_spread_favorite_buy_yes_t60m"
    assert frozen[0]["spread_max"] == 0.03
    assert frozen[0]["threshold"] == 0.62
    assert frozen[0]["do_not_retune"] is True
    md = registration_markdown(reg)
    assert "tight_spread_favorite_buy_yes_t60m" in md
    assert "do not retune" in md.lower() or "Do not retune" in md


def test_append_only_duplicate_suppression(tmp_path: Path) -> None:
    path = tmp_path / "raw.jsonl"
    rows = [
        {
            "contract_ticker": "KXMLBGAME-26JUL081805BOSNYY-BOS",
            "event_ticker": "KXMLBGAME-26JUL081805BOSNYY",
            "observed_at_utc": "2026-07-08T22:00:00Z",
            "best_yes_bid": 0.54,
            "best_yes_ask": 0.56,
            "best_no_bid": 0.44,
            "best_no_ask": 0.46,
            "yes_bid_depth_top1": 10,
            "yes_ask_depth_top1": 12,
            "entry_source": "dense_public_orderbook",
        }
    ]
    stats1 = append_raw_snapshot_jsonl(path, rows)
    assert stats1["written"] == 1
    append_raw_snapshot_jsonl(path, rows, seen_hashes={snapshot_payload_hash(rows[0])})
    # Subsequent calls dedupe via preloaded payload hashes.
    loaded = load_raw_snapshots(path)
    seen = {str(r.get("raw_payload_hash")) for r in loaded}
    stats3 = append_raw_snapshot_jsonl(path, rows, seen_hashes=seen)
    assert stats3["written"] == 0
    assert stats3["skipped_duplicates"] == 1
    assert len(load_raw_snapshots(path)) == 1


def test_capture_lock_blocks_duplicate(tmp_path: Path) -> None:
    lock_path = tmp_path / "collector.lock"
    lock_a = CaptureLock(lock_path)
    ok_a, _ = lock_a.acquire()
    assert ok_a
    lock_b = CaptureLock(lock_path)
    ok_b, msg = lock_b.acquire()
    assert not ok_b
    assert "already_running" in msg
    lock_a.release()
    ok_c, _ = lock_b.acquire()
    assert ok_c
    lock_b.release()


def test_panel_coverage_gates_fail_on_sparse_and_no_pnl() -> None:
    snapshots = []
    for i in range(5):
        snapshots.append(
            {
                "contract_ticker": f"KXMLBGAME-26JUL{i:02d}1800AAAABB-AAA",
                "event_ticker": f"KXMLBGAME-26JUL{i:02d}1800AAAABB",
                "observed_at_utc": f"2026-07-{i + 1:02d}T17:00:00Z",
                "occurrence_datetime": f"2026-07-{i + 1:02d}T18:00:00Z",
                "best_yes_bid": 0.5,
                "best_yes_ask": 0.52,
                "best_no_bid": 0.48,
                "best_no_ask": 0.5,
                "yes_ask_depth_top1": 5,
                "entry_source": "dense_public_orderbook",
            }
        )
    coverage = assess_panel_coverage(snapshots)
    assert coverage["capture_infrastructure_ready"] is True
    assert coverage["evidence_panel_ready"] is False
    assert coverage["distinct_events"] == 5
    assert coverage["distinct_slate_dates"] < MIN_SLATE_DATES
    assert coverage["candidate_performance_revealed"] is False
    assert coverage["distinct_events"] < MIN_EVENTS_OVERALL
    conf = frozen_candidate_confirmation_state(coverage)
    assert conf["confirmation_power_met"] is False
    assert conf["candidates"][0]["confirmation_status"] == "confirmation_pending"
    assert confirmation_power_met(coverage) is False


def test_ops_register_and_replay_offline(tmp_path: Path) -> None:
    module = load_ops()
    reg_out = module.cmd_register(out_dir=tmp_path / "reg")
    assert reg_out["status"] == "panel_registration_written"
    assert Path(reg_out["json"]).is_file()
    assert Path(reg_out["md"]).is_file()
    payload = json.loads(Path(reg_out["json"]).read_text(encoding="utf-8"))
    assert payload["registration_sha256"] == reg_out["registration_sha256"]

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    # Seed sparse raw snapshots.
    rows = [
        {
            "contract_ticker": "KXMLBGAME-26JUL081805BOSNYY-BOS",
            "event_ticker": "KXMLBGAME-26JUL081805BOSNYY",
            "observed_at_utc": "2026-07-08T22:00:00Z",
            "occurrence_datetime": "2026-07-08T23:05:00Z",
            "best_yes_bid": 0.54,
            "best_yes_ask": 0.56,
            "best_no_bid": 0.44,
            "best_no_ask": 0.46,
            "yes_ask_depth_top1": 8,
            "entry_source": "dense_public_orderbook",
        }
    ]
    append_raw_snapshot_jsonl(raw_dir / "mlb_dense_panel_snapshots.jsonl", rows)
    replay = module.cmd_replay(raw_dir=raw_dir)
    assert replay["network_access"] is False
    assert replay["snapshot_count"] == 1
    assert replay["coverage"]["evidence_panel_ready"] is False

    status = module.cmd_status(raw_dir=raw_dir, status_dir=tmp_path / "status")
    assert status["evidence_panel_ready"] is False
    assert (
        status["frozen_confirmation"]["candidates"][0]["model_id"]
        == FROZEN_CANDIDATES[0]["model_id"]
    )
