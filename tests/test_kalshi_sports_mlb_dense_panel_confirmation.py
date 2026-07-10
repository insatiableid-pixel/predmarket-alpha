from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from predmarket.sports_mlb_dense_panel import snapshot_payload_hash
from predmarket.sports_mlb_dense_panel_confirmation import (
    EXPECTED_FORMULA_SHA256,
    EXPECTED_PANEL_REGISTRATION_SHA256,
    build_confirmation_contract,
    confirmation_preflight,
    evaluate_frozen_attempt,
    run_single_shot_confirmation,
    select_frozen_candidate_rows,
    validate_contract,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRATION = ROOT / "docs/codex/macro/latest-kalshi-sports-mlb-dense-panel-registration.json"
DENSE_PANEL_IMPLEMENTATION = ROOT / "predmarket/sports_mlb_dense_panel.py"
IMPLEMENTATION = ROOT / "predmarket/sports_mlb_dense_panel_confirmation.py"
DENSE_BOOK_CAPTURE_SCRIPT = ROOT / "scripts/kalshi_sports_mlb_dense_book_capture.py"
DENSE_PANEL_OPS_SCRIPT = ROOT / "scripts/kalshi_sports_mlb_dense_panel_ops.py"
SCRIPT = ROOT / "scripts/kalshi_sports_mlb_dense_panel_confirmation.py"


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def build_dense_rows() -> list[dict]:
    rows: list[dict] = []
    start_date = datetime(2026, 7, 11, 20, 0, tzinfo=UTC)
    for slate_index in range(10):
        for event_index in range(12):
            game_start = start_date + timedelta(days=slate_index, minutes=event_index * 5)
            event = f"KXMLBGAME-26JUL{11 + slate_index:02d}{event_index:04d}AAABBB"
            ticker = f"{event}-AAA"
            candidate = event_index < 2
            yes_bid = 0.64 if candidate else 0.49
            yes_ask = 0.66 if candidate else 0.51
            for clock_name, offset in (("T-60m", 3600), ("T-15m", 900)):
                observed = game_start - timedelta(seconds=offset)
                row = {
                    "snapshot_id": f"synthetic|{ticker}|{clock_name}",
                    "contract_ticker": ticker,
                    "event_ticker": event,
                    "series_ticker": "KXMLBGAME",
                    "observed_at_utc": iso(observed),
                    "occurrence_datetime": iso(game_start),
                    "expected_expiration_time": iso(game_start),
                    "best_yes_bid": yes_bid,
                    "best_yes_ask": yes_ask,
                    "best_no_bid": 1.0 - yes_ask,
                    "best_no_ask": 1.0 - yes_bid,
                    "yes_bid_depth_top1": 10,
                    "yes_ask_depth_top1": 12,
                    "no_bid_depth_top1": 12,
                    "no_ask_depth_top1": 10,
                    "yes_spread": yes_ask - yes_bid,
                    "entry_source": "dense_public_orderbook",
                    "orderbook_fetch_succeeded": True,
                    "research_only": True,
                    "execution_enabled": False,
                }
                row["raw_payload_hash"] = snapshot_payload_hash(row)
                rows.append(row)
    return rows


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )


def contract_payload() -> dict:
    return build_confirmation_contract(
        repo_root=ROOT,
        registered_at_utc="2026-07-10T06:30:00Z",
        implementation_paths=(
            DENSE_PANEL_IMPLEMENTATION,
            IMPLEMENTATION,
            DENSE_BOOK_CAPTURE_SCRIPT,
            DENSE_PANEL_OPS_SCRIPT,
            SCRIPT,
        ),
    )


def ready_preflight(tmp_path: Path) -> tuple[dict, Path, Path]:
    raw_path = tmp_path / "raw.jsonl"
    contract_path = tmp_path / "contract.json"
    state_dir = tmp_path / "state"
    write_jsonl(raw_path, build_dense_rows())
    write_json(contract_path, contract_payload())
    preflight = confirmation_preflight(
        raw_path=raw_path,
        registration_path=REGISTRATION,
        contract_path=contract_path,
        state_dir=state_dir,
        repo_root=ROOT,
        now_utc="2026-07-21T12:30:00Z",
    )
    return preflight, raw_path, state_dir


def exact_fee(_price: float, **_kwargs) -> dict:
    return {
        "fee": 0.01,
        "fee_rate": 0.07,
        "fee_type": "quadratic",
        "fee_multiplier": 1.0,
        "fee_source": "synthetic_exact_series_fee",
        "fee_effective_scheduled_ts": "2026-01-01T00:00:00Z",
        "fee_lookup_time_utc": "2026-07-21T12:30:00Z",
        "fee_series_ticker": "KXMLBGAME",
        "fee_fallback_state": "none",
        "fee_mode": "taker",
    }


def test_contract_pins_registration_formula_and_implementation() -> None:
    contract = contract_payload()
    assert contract["panel_registration_sha256"] == EXPECTED_PANEL_REGISTRATION_SHA256
    assert contract["candidate"]["formula_sha256"] == EXPECTED_FORMULA_SHA256
    assert {row["path"] for row in contract["implementation_files"]} == {
        "predmarket/sports_mlb_dense_panel.py",
        "predmarket/sports_mlb_dense_panel_confirmation.py",
        "scripts/kalshi_sports_mlb_dense_book_capture.py",
        "scripts/kalshi_sports_mlb_dense_panel_ops.py",
        "scripts/kalshi_sports_mlb_dense_panel_confirmation.py",
    }
    validation = validate_contract(contract, repo_root=ROOT)
    assert validation["passed"] is True
    assert all(row["passed"] for row in validation["implementation_checks"])


def test_candidate_selection_uses_latest_observed_reschedule() -> None:
    event = "KXMLBGAME-26JUL12POSTPONED"
    ticker = f"{event}-AAA"
    rows = []
    for schedule, game_start, observed in (
        ("original", "2026-07-12T20:00:00Z", "2026-07-12T18:59:00Z"),
        ("rescheduled", "2026-07-13T20:00:00Z", "2026-07-13T18:59:00Z"),
    ):
        row = {
            "snapshot_id": schedule,
            "contract_ticker": ticker,
            "event_ticker": event,
            "observed_at_utc": observed,
            "occurrence_datetime": game_start,
            "best_yes_bid": 0.64,
            "best_yes_ask": 0.66,
            "yes_bid_depth_top1": 10,
            "yes_ask_depth_top1": 12,
            "yes_spread": 0.02,
            "entry_source": "dense_public_orderbook",
        }
        row["raw_payload_hash"] = snapshot_payload_hash(row)
        rows.append(row)

    selected = select_frozen_candidate_rows(
        rows,
        registration_utc="2026-07-10T05:37:38Z",
    )

    assert len(selected) == 1
    assert selected[0]["snapshot_id"] == "rescheduled"
    assert selected[0]["slate_date"] == "2026-07-13"
    assert selected[0]["game_start_resolution"] == "latest_observed_start_per_event"


def test_schedule_revision_marker_blocks_old_candidate_until_new_book() -> None:
    event = "KXMLBGAME-26JUL12POSTPONED"
    old_book = {
        "snapshot_id": "original-t60",
        "contract_ticker": f"{event}-AAA",
        "event_ticker": event,
        "observed_at_utc": "2026-07-12T18:59:00Z",
        "occurrence_datetime": "2026-07-12T20:00:00Z",
        "best_yes_bid": 0.64,
        "best_yes_ask": 0.66,
        "yes_bid_depth_top1": 10,
        "yes_ask_depth_top1": 12,
        "yes_spread": 0.02,
        "entry_source": "dense_public_orderbook",
    }
    marker = {
        "snapshot_id": "schedule-revision",
        "contract_ticker": f"{event}-AAA",
        "event_ticker": event,
        "observed_at_utc": "2026-07-12T19:30:00Z",
        "game_start_ts": datetime(2026, 7, 13, 20, tzinfo=UTC).timestamp(),
        "schedule_revision": True,
        "entry_source": "public_kalshi_market_schedule_revision",
    }

    selected = select_frozen_candidate_rows(
        [old_book, marker],
        registration_utc="2026-07-10T05:37:38Z",
    )

    assert selected == []


def test_outcome_blind_preflight_passes_only_at_registered_power(tmp_path: Path) -> None:
    preflight, _raw_path, _state_dir = ready_preflight(tmp_path)
    assert preflight["status"] == "ready_to_freeze_single_shot_sample"
    assert preflight["confirmation_start_ready"] is True
    assert preflight["candidate_performance_revealed"] is False
    assert preflight["candidate_sample"]["event_count"] == 20
    assert preflight["candidate_sample"]["slate_date_count"] == 10
    assert preflight["candidate_sample"]["largest_slate_share"] == 0.1
    assert all(status == "pass" for status in preflight["gates"].values())


def test_pending_preflight_never_fetches_settlements(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.jsonl"
    contract_path = tmp_path / "contract.json"
    state_dir = tmp_path / "state"
    write_jsonl(raw_path, build_dense_rows()[:2])
    write_json(contract_path, contract_payload())
    preflight = confirmation_preflight(
        raw_path=raw_path,
        registration_path=REGISTRATION,
        contract_path=contract_path,
        state_dir=state_dir,
        repo_root=ROOT,
        now_utc="2026-07-21T12:30:00Z",
    )
    calls = []

    def forbidden_fetch(ticker: str):
        calls.append(ticker)
        raise AssertionError("settlement fetch must not run")

    result = run_single_shot_confirmation(
        preflight=preflight,
        state_dir=state_dir,
        now_utc="2026-07-21T12:30:00Z",
        fetcher=forbidden_fetch,
        fee_resolver=exact_fee,
        request_delay_seconds=0,
    )
    assert result["status"] == "confirmation_pending_preflight_not_ready"
    assert result["candidate_performance_revealed"] is False
    assert calls == []
    assert not (state_dir / "single-shot-attempt.json").exists()


def test_attempt_freezes_sample_resumes_and_final_is_idempotent(tmp_path: Path) -> None:
    preflight, _raw_path, state_dir = ready_preflight(tmp_path)

    def unresolved(ticker: str) -> dict:
        return {"ticker": ticker, "status": "open"}

    waiting = run_single_shot_confirmation(
        preflight=preflight,
        state_dir=state_dir,
        now_utc="2026-07-21T12:30:00Z",
        fetcher=unresolved,
        fee_resolver=exact_fee,
        request_delay_seconds=0,
    )
    assert waiting["status"] == "single_shot_sample_frozen_waiting_exact_settlements"
    assert waiting["candidate_performance_revealed"] is False
    attempt = json.loads((state_dir / "single-shot-attempt.json").read_text(encoding="utf-8"))
    assert attempt["candidate_event_count"] == 20
    assert attempt["settlement_outcomes_read"] is False

    expanded = dict(preflight)
    expanded["_candidate_rows"] = [
        *preflight["_candidate_rows"],
        {**preflight["_candidate_rows"][0], "event_ticker": "SHOULD-NOT-ENTER"},
    ]

    def settled_yes(ticker: str) -> dict:
        return {"ticker": ticker, "result": "yes"}

    final = run_single_shot_confirmation(
        preflight=expanded,
        state_dir=state_dir,
        now_utc="2026-07-21T12:35:00Z",
        fetcher=settled_yes,
        fee_resolver=exact_fee,
        request_delay_seconds=0,
    )
    assert final["status"] == "research_ready_survivor_research_only"
    assert final["event_count"] == 20
    assert final["finalizable"] is True
    assert (state_dir / "single-shot-final.json").is_file()

    def fetch_must_not_repeat(_ticker: str) -> dict:
        raise AssertionError("finalized confirmation must be idempotent")

    replay = run_single_shot_confirmation(
        preflight=expanded,
        state_dir=state_dir,
        now_utc="2026-07-22T12:35:00Z",
        fetcher=fetch_must_not_repeat,
        fee_resolver=exact_fee,
        request_delay_seconds=0,
    )
    assert replay["idempotent_replay"] is True
    assert replay["attempt_id"] == final["attempt_id"]


def test_fee_uncertainty_blocks_before_any_settlement_fetch(tmp_path: Path) -> None:
    preflight, _raw_path, state_dir = ready_preflight(tmp_path)
    calls = []

    def fallback_fee(price: float, **_kwargs) -> dict:
        return {
            **exact_fee(price),
            "fee_source": "conservative_general_quadratic_fallback",
            "fee_fallback_state": "conservative_general_quadratic",
        }

    def forbidden_fetch(ticker: str) -> dict:
        calls.append(ticker)
        raise AssertionError("settlements must remain unread until exact fee evidence")

    result = run_single_shot_confirmation(
        preflight=preflight,
        state_dir=state_dir,
        now_utc="2026-07-21T12:30:00Z",
        fetcher=forbidden_fetch,
        fee_resolver=fallback_fee,
        request_delay_seconds=0,
    )
    assert result["status"] == "single_shot_sample_frozen_waiting_exact_series_fee"
    assert result["candidate_performance_revealed"] is False
    assert calls == []
    assert not (state_dir / "single-shot-final.json").exists()


def test_tampered_attempt_is_rejected_before_fetch(tmp_path: Path) -> None:
    preflight, _raw_path, state_dir = ready_preflight(tmp_path)

    def unresolved(ticker: str) -> dict:
        return {"ticker": ticker, "status": "open"}

    run_single_shot_confirmation(
        preflight=preflight,
        state_dir=state_dir,
        now_utc="2026-07-21T12:30:00Z",
        fetcher=unresolved,
        fee_resolver=exact_fee,
        request_delay_seconds=0,
    )
    attempt_path = state_dir / "single-shot-attempt.json"
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    attempt["candidate_event_count"] += 1
    write_json(attempt_path, attempt)
    calls = []

    def forbidden_fetch(ticker: str) -> dict:
        calls.append(ticker)
        raise AssertionError("tampered attempt must fail before settlement fetch")

    result = run_single_shot_confirmation(
        preflight=preflight,
        state_dir=state_dir,
        now_utc="2026-07-21T12:35:00Z",
        fetcher=forbidden_fetch,
        fee_resolver=exact_fee,
        request_delay_seconds=0,
    )
    assert result["status"] == "confirmation_pending_attempt_integrity_failed"
    assert result["candidate_performance_revealed"] is False
    assert calls == []


def test_powered_negative_confirmation_finalizes_as_failed(tmp_path: Path) -> None:
    preflight, _raw_path, _state_dir = ready_preflight(tmp_path)
    rows = list(preflight["_candidate_rows"])
    attempt = {
        "attempt_id": "negative",
        "candidate_event_count": len(rows),
        "candidate_rows": rows,
    }
    settlements = {
        row["contract_ticker"]: {
            "ticker": row["contract_ticker"],
            "result": "yes" if index % 2 == 0 else "no",
        }
        for index, row in enumerate(rows)
    }
    result = evaluate_frozen_attempt(attempt, settlements, fee_resolver=exact_fee)
    assert result["status"] == "confirmation_failed"
    assert result["finalizable"] is True
    assert result["outcome_gates"]["positive_mean_net"] == "fail"
    assert result["candidate_performance_revealed"] is True
