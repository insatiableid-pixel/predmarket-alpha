from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from predmarket.config import Config
from predmarket.kalshi_live_engine import (
    LiveRiskLimits,
    LiveStateStore,
    build_live_decision_report,
    build_live_risk_snapshot,
    normalize_market_snapshot_index,
    paper_usable_tickers,
    reconcile_live_orders,
    source_repo_is_live_safe,
)


def paper_candidate(**overrides: object) -> dict[str, object]:
    row = {
        "contract_ticker": "KXUNIT-YES",
        "side": "yes",
        "family_id": "unit_family",
        "model_id": "unit_model",
        "source_repo_id": "unit_repo",
        "signal_key": "unit_family|unit_model|unit_formula|unit_repo",
        "signal_formula_key": "unit_formula",
        "cluster_key": "unit|cluster",
        "paper_usable": True,
        "paper_stake": 20.0,
        "calibrated_probability": 0.60,
        "market_probability": 0.40,
        "all_in_cost": 0.40,
        "expected_value_per_contract": 0.20,
        "capacity_estimate": 50.0,
        "close_time": "2026-07-03T12:00:00Z",
        "blocker_list": [],
    }
    row.update(overrides)
    return row


def paper_report(*rows: dict[str, object]) -> dict[str, object]:
    return {"summary": {"candidate_count": len(rows)}, "candidates": list(rows)}


def external_preflight(source_repo_id: str = "unit_repo") -> dict[str, object]:
    return {
        "summary": {"safe_artifact_count": 1},
        "artifacts": [{"source_repo_id": source_repo_id, "safe": True}],
    }


def market_snapshot(**overrides: object) -> dict[str, object]:
    market = {
        "ticker": "KXUNIT-YES",
        "status": "open",
        "yes_ask_dollars": "0.4000",
        "yes_ask_size_fp": "100.00",
        "close_time": "2026-07-03T12:00:00Z",
    }
    market.update(overrides)
    return {"market": market}


def armed_demo_config() -> Config:
    config = Config()
    config.venues.kalshi.execution_enabled = True
    config.venues.kalshi.use_demo = True
    config.kalshi_live.execution_mode = "demo"
    return config


def test_live_decision_promotes_only_fully_safe_armed_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KALSHI_LIVE_TRADING_ENABLED", "1")
    config = armed_demo_config()

    report = build_live_decision_report(
        paper_report=paper_report(paper_candidate()),
        external_preflight=external_preflight(),
        retirement_ledger={"signals": []},
        state={"orders": []},
        market_snapshots={"KXUNIT-YES": market_snapshot()},
        account_balance_usd=1000.0,
        execution_mode="demo",
        generated_utc="2026-07-03T11:00:00Z",
        config=config,
    )

    decision = report["decisions"][0]
    assert report["status"] == "kalshi_live_ready_with_eligible_orders"
    assert report["summary"]["live_eligible_count"] == 1
    assert decision["live_eligible"] is True
    assert decision["execution_strategy"] == "maker_first"
    assert decision["fee_mode"] == "maker"
    assert decision["post_only"] is True
    assert decision["time_in_force"] == "good_till_canceled"
    assert decision["modeled_limit_price"] == pytest.approx(0.40)
    assert decision["limit_price"] == pytest.approx(0.39)
    assert decision["order_count"] == 51
    assert decision["live_stake"] == pytest.approx(19.89)
    assert decision["order_expiration_time"] is not None
    assert decision["maker_fee_savings"] > 0
    assert decision["client_order_id"]
    assert decision["source_repo_id"] == "unit_repo"


def test_internal_predmarket_candidate_does_not_need_external_donor_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KALSHI_LIVE_TRADING_ENABLED", "1")
    config = armed_demo_config()

    report = build_live_decision_report(
        paper_report=paper_report(
            paper_candidate(
                source_repo_id="predmarket-alpha",
                signal_key="microstructure_informed_flow|unit_model|unit_formula|predmarket-alpha",
            )
        ),
        external_preflight={"summary": {"safe_artifact_count": 0}, "artifacts": []},
        retirement_ledger={"signals": []},
        state={"orders": []},
        market_snapshots={"KXUNIT-YES": market_snapshot()},
        account_balance_usd=1000.0,
        execution_mode="demo",
        generated_utc="2026-07-03T11:00:00Z",
        config=config,
    )

    decision = report["decisions"][0]
    assert decision["live_eligible"] is True
    assert decision["source_repo_id"] == "predmarket-alpha"
    assert "source repo artifact did not pass external preflight" not in decision["blocker_list"]


def test_external_donor_candidate_still_requires_external_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KALSHI_LIVE_TRADING_ENABLED", "1")
    config = armed_demo_config()

    report = build_live_decision_report(
        paper_report=paper_report(paper_candidate(source_repo_id="unknown-donor")),
        external_preflight={"summary": {"safe_artifact_count": 0}, "artifacts": []},
        retirement_ledger={"signals": []},
        state={"orders": []},
        market_snapshots={"KXUNIT-YES": market_snapshot()},
        account_balance_usd=1000.0,
        execution_mode="demo",
        generated_utc="2026-07-03T11:00:00Z",
        config=config,
    )

    decision = report["decisions"][0]
    assert decision["live_eligible"] is False
    assert "source repo artifact did not pass external preflight" in decision["blocker_list"]


def test_source_repo_live_safety_boundary() -> None:
    assert source_repo_is_live_safe("predmarket-alpha", set())
    assert source_repo_is_live_safe("unit-donor", {"unit-donor"})
    assert not source_repo_is_live_safe("unit-donor", set())


def test_paper_usable_tickers_only_returns_sized_rows() -> None:
    report = paper_report(
        paper_candidate(contract_ticker="KXUNIT-YES", paper_usable=True),
        paper_candidate(contract_ticker="KXBLOCKED-YES", paper_usable=False),
        paper_candidate(contract_ticker="", paper_usable=True),
    )

    assert paper_usable_tickers(report) == {"KXUNIT-YES"}


def test_normalize_market_snapshot_index_accepts_capture_artifact() -> None:
    payload = {
        "market_snapshots": {
            "KXUNIT-YES": {
                "market": {
                    "ticker": "KXUNIT-YES",
                    "yes_ask_dollars": "0.4000",
                    "yes_ask_size_fp": "100.00",
                }
            }
        }
    }

    index = normalize_market_snapshot_index(payload)

    assert index["KXUNIT-YES"]["market"]["yes_ask_dollars"] == "0.4000"


def test_missing_account_balance_does_not_emit_cap_rounding_noise() -> None:
    report = build_live_decision_report(
        paper_report=paper_report(paper_candidate()),
        external_preflight=external_preflight(),
        retirement_ledger={"signals": []},
        state={"orders": []},
        market_snapshots={"KXUNIT-YES": market_snapshot()},
        account_balance_usd=None,
        execution_mode="disabled",
        generated_utc="2026-07-03T11:00:00Z",
        config=Config(),
    )

    blockers = report["decisions"][0]["blocker_list"]
    assert "account balance missing" in blockers
    assert "live stake rounds down below one contract" not in blockers


def test_taker_cross_blocks_when_market_price_moved() -> None:
    config = Config()
    config.kalshi_live.execution_strategy = "taker_cross"

    report = build_live_decision_report(
        paper_report=paper_report(paper_candidate()),
        external_preflight=external_preflight(),
        retirement_ledger={"signals": []},
        state={"orders": []},
        market_snapshots={"KXUNIT-YES": market_snapshot(yes_ask_dollars="0.5000")},
        account_balance_usd=1000.0,
        execution_mode="disabled",
        generated_utc="2026-07-03T11:00:00Z",
        config=config,
    )

    blockers = report["decisions"][0]["blocker_list"]
    assert report["status"] == "kalshi_live_blocked"
    assert "live execution mode is disabled" in blockers
    assert "current side ask exceeds modeled limit price" in blockers
    assert report["decisions"][0]["live_stake"] == 0.0


def test_taker_cross_uses_ioc_when_explicitly_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KALSHI_LIVE_TRADING_ENABLED", "1")
    config = armed_demo_config()
    config.kalshi_live.execution_strategy = "taker_cross"

    report = build_live_decision_report(
        paper_report=paper_report(paper_candidate()),
        external_preflight=external_preflight(),
        retirement_ledger={"signals": []},
        state={"orders": []},
        market_snapshots={"KXUNIT-YES": market_snapshot()},
        account_balance_usd=1000.0,
        execution_mode="demo",
        generated_utc="2026-07-03T11:00:00Z",
        config=config,
    )

    decision = report["decisions"][0]
    assert decision["live_eligible"] is True
    assert decision["execution_strategy"] == "taker_cross"
    assert decision["fee_mode"] == "taker"
    assert decision["post_only"] is False
    assert decision["time_in_force"] == "immediate_or_cancel"
    assert decision["limit_price"] == pytest.approx(0.40)
    assert decision["order_expiration_time"] is None


def test_taker_if_decay_justifies_blocks_without_decay_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KALSHI_LIVE_TRADING_ENABLED", "1")
    config = armed_demo_config()
    config.kalshi_live.execution_strategy = "taker_if_decay_justifies"

    report = build_live_decision_report(
        paper_report=paper_report(paper_candidate()),
        external_preflight=external_preflight(),
        retirement_ledger={"signals": []},
        state={"orders": []},
        market_snapshots={"KXUNIT-YES": market_snapshot()},
        account_balance_usd=1000.0,
        execution_mode="demo",
        generated_utc="2026-07-03T11:00:00Z",
        config=config,
    )

    decision = report["decisions"][0]
    assert decision["live_eligible"] is False
    assert "edge decay rate missing for taker-cross decision" in decision["blocker_list"]
    assert decision["live_stake"] == 0.0


def test_risk_snapshot_kill_switches_stale_unreconciled_order() -> None:
    now = time.time()
    state = {
        "orders": [
            {
                "client_order_id": "cid",
                "created_ts": now - 120,
                "status": "SUBMITTED",
                "notional_usd": 10.0,
                "contract_ticker": "KXUNIT-YES",
                "family_id": "unit_family",
                "cluster_key": "unit|cluster",
            }
        ]
    }

    snapshot = build_live_risk_snapshot(
        state=state,
        account_balance_usd=1000.0,
        limits=LiveRiskLimits(unreconciled_order_timeout_seconds=60),
        generated_utc=None,
    )

    assert snapshot["stale_unreconciled_order_count"] == 1
    assert "unreconciled live order timeout" in snapshot["kill_switch_reasons"]


def test_reconcile_updates_unresolved_order_without_duplicate(tmp_path: Path) -> None:
    store = LiveStateStore(tmp_path)
    store.write(
        {
            "schema_version": 1,
            "orders": [
                {
                    "client_order_id": "cid",
                    "exchange_order_id": "order-1",
                    "created_ts": time.time(),
                    "status": "SUBMITTED",
                    "notional_usd": 10.0,
                }
            ],
        }
    )

    class FakeClient:
        def get_order(self, order_id: str) -> dict[str, object]:
            assert order_id == "order-1"
            return {
                "order": {
                    "order_id": "order-1",
                    "fill_count_fp": "1.00",
                    "remaining_count_fp": "0.00",
                }
            }

    result = reconcile_live_orders(client=FakeClient(), state_store=store)
    state = json.loads((tmp_path / "kalshi-live-state.json").read_text(encoding="utf-8"))

    assert result["updated_order_count"] == 1
    assert len(state["orders"]) == 1
    assert state["orders"][0]["status"] == "FILLED"
    assert len(state["fills"]) == 1
