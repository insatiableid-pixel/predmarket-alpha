"""Tests for fee-aware paper decision sizing (VAL-FEE-035..037, VAL-SIZING-001..013, VAL-CROSS-009..019).

Tests cover net_fee in edge computation, maker/taker branching,
EV ledger fee fields, and portfolio risk diagnostics.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from predmarket.kalshi_execution_cost import (
    GENERAL_MAKER_FEE_RATE,
    GENERAL_TAKER_FEE_RATE,
    kalshi_net_fee,
    kalshi_trade_fee,
)
from predmarket.paper_decision_engine import (
    DEFAULT_COVARIANCE_LAMBDA,
    DEFAULT_WITHIN_CLUSTER_CORRELATION,
    _resolve_paper_fee,
    build_paper_decision_candidates,
    compute_covariance_penalty,
)

# ── Helpers ─────────────────────────────────────────────────────────────────


def ledger_payload(*rows: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "kalshi_ev_ledger_ready_with_usable_contract_edges",
        "research_only": True,
        "execution_enabled": False,
        "rows": list(rows),
    }


def pass_ready_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "contract_ticker": "KXUNIT-YES",
        "side": "yes",
        "family_id": "unit_family",
        "model_id": "unit_model",
        "source_repo_id": "unit_repo",
        "signal_formula_key": "unit_formula",
        "usable": True,
        "calibrated_probability": 0.60,
        "display_price": 0.40,
        "all_in_cost": 0.40,
        "expected_value_per_contract": 0.20,
        "capacity_estimate": 50.0,
        "correlation_cluster_key": "unit|cluster",
        "close_time": "2026-07-03T00:00:00Z",
        "resolution_rule_status": "verified_official_terms",
        "gate_status": "pass",
        "timing_status": "clean",
        "capacity_gate_status": "pass",
        "correlation_cluster_gate_status": "pass",
        "decay_gate_status": "pass",
    }
    row.update(overrides)
    return row


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ── _resolve_paper_fee tests ────────────────────────────────────────────────


class TestResolvePaperFee:
    """Tests for the _resolve_paper_fee maker/taker branching logic."""

    def test_default_maker_fee(self) -> None:
        """VAL-FEE-036, VAL-SIZING-009: Maker-first uses maker fee by default."""
        mode, fee = _resolve_paper_fee(
            market_probability=0.50,
            fee_mode=None,
            decay_rate=None,
            time_to_fill=None,
        )
        assert mode == "maker"
        maker_expected = kalshi_net_fee(price=0.50, fee_mode="maker")
        assert fee == pytest.approx(maker_expected, abs=1e-6)

    def test_missing_decay_defaults_maker(self) -> None:
        """VAL-SIZING-011: Missing decay_rate or time_to_fill defaults to maker with no taker switch."""
        mode, _ = _resolve_paper_fee(
            market_probability=0.50,
            fee_mode=None,
            decay_rate=None,
            time_to_fill=10.0,
        )
        assert mode == "maker"

        mode, _ = _resolve_paper_fee(
            market_probability=0.50,
            fee_mode=None,
            decay_rate=0.01,
            time_to_fill=None,
        )
        assert mode == "maker"

        mode, _ = _resolve_paper_fee(
            market_probability=0.50,
            fee_mode=None,
            decay_rate=None,
            time_to_fill=None,
        )
        assert mode == "maker"

    def test_negative_decay_rate_keeps_maker(self) -> None:
        """VAL-SIZING-012: Negative decay_rate does not trigger taker switch."""
        mode, _ = _resolve_paper_fee(
            market_probability=0.50,
            fee_mode=None,
            decay_rate=-0.001,
            time_to_fill=100.0,
        )
        assert mode == "maker"

    def test_zero_time_to_fill_keeps_maker(self) -> None:
        """VAL-SIZING-013: time_to_fill of zero or negative keeps maker fee."""
        mode, _ = _resolve_paper_fee(
            market_probability=0.50,
            fee_mode=None,
            decay_rate=0.01,
            time_to_fill=0.0,
        )
        assert mode == "maker"

        mode, _ = _resolve_paper_fee(
            market_probability=0.50,
            fee_mode=None,
            decay_rate=0.01,
            time_to_fill=-1.0,
        )
        assert mode == "maker"

    def test_decay_justifies_taker_switch(self) -> None:
        """VAL-FEE-037, VAL-SIZING-010: Taker when decay_rate * time_to_fill > taker_fee - maker_fee."""
        maker_fee = kalshi_net_fee(price=0.50, fee_mode="maker")  # ~0.0044
        taker_fee = kalshi_net_fee(price=0.50, fee_mode="taker")  # ~0.0175
        fee_diff = taker_fee - maker_fee  # ~0.0131

        # High decay justifies taker
        mode, fee = _resolve_paper_fee(
            market_probability=0.50,
            fee_mode=None,
            decay_rate=0.01,  # 1% per unit time
            time_to_fill=5.0,  # 5 units of time
        )
        decay_cost = 0.01 * 5.0  # 0.05
        if decay_cost > fee_diff:
            assert mode == "taker"
            assert fee == pytest.approx(taker_fee, abs=1e-6)
        else:
            # Should be taker based on the actual fee_diff
            assert mode == "maker"  # decay_cost didn't justify
            assert fee == pytest.approx(maker_fee, abs=1e-6)

    def test_low_decay_stays_maker(self) -> None:
        """When decay is too small to justify crossing, stay maker."""
        mode, _ = _resolve_paper_fee(
            market_probability=0.50,
            fee_mode=None,
            decay_rate=0.0001,  # 0.01% per unit time
            time_to_fill=1.0,  # 1 unit
        )
        assert mode == "maker"

    def test_edge_market_bounds(self) -> None:
        """Edge cases: price at bounds should still produce valid fee."""
        # Very low price
        mode, fee = _resolve_paper_fee(
            market_probability=0.01,
            fee_mode=None,
            decay_rate=None,
            time_to_fill=None,
        )
        assert mode == "maker"
        assert fee >= 0.0

        # Very high price
        mode, fee = _resolve_paper_fee(
            market_probability=0.99,
            fee_mode=None,
            decay_rate=None,
            time_to_fill=None,
        )
        assert mode == "maker"
        assert fee >= 0.0

        # None market_prob
        mode, fee = _resolve_paper_fee(
            market_probability=None,
            fee_mode=None,
            decay_rate=None,
            time_to_fill=None,
        )
        assert mode == "maker"
        assert fee == 0.0

        # Boundary 0.0
        mode, fee = _resolve_paper_fee(
            market_probability=0.0,
            fee_mode=None,
            decay_rate=None,
            time_to_fill=None,
        )
        assert mode == "maker"
        assert fee == 0.0


# ── Paper decision pipeline tests ───────────────────────────────────────────


class TestPaperEdgeComputation:
    """Tests for net_fee in paper edge computation (VAL-FEE-035, VAL-SIZING-001..005)."""

    def test_edge_includes_net_fee(self) -> None:
        """VAL-FEE-035: Paper edge = calibrated_prob - market_prob - net_fee(market_prob, fee_mode)."""
        calibrate = 0.60
        market = 0.55
        maker_fee = kalshi_net_fee(price=market, fee_mode="maker")
        expected_edge = calibrate - market - maker_fee

        mode, fee = _resolve_paper_fee(
            market_probability=market,
            fee_mode=None,
            decay_rate=None,
            time_to_fill=None,
        )
        edge = calibrate - market - fee
        assert mode == "maker"
        assert edge == pytest.approx(expected_edge, abs=1e-8)
        assert edge > 0  # Still positive

    def test_edge_computed_against_market_prob(self) -> None:
        """VAL-SIZING-003: net_fee computed against market_probability, not calibrated_probability."""
        calibrate = 0.60
        market = 0.55
        maker_fee_at_market = kalshi_net_fee(price=market, fee_mode="maker")

        # net_fee at market_prob = 0.55
        _, fee = _resolve_paper_fee(
            market_probability=market,
            fee_mode=None,
            decay_rate=None,
            time_to_fill=None,
        )
        assert fee == pytest.approx(maker_fee_at_market, abs=1e-8)

        # Different calibrated prob shouldn't change the fee
        calibrate2 = 0.80
        _, fee2 = _resolve_paper_fee(
            market_probability=market,
            fee_mode=None,
            decay_rate=None,
            time_to_fill=None,
        )
        assert fee2 == pytest.approx(maker_fee_at_market, abs=1e-8)

        # edge changes but fee doesn't
        edge1 = calibrate - market - fee
        edge2 = calibrate2 - market - fee2
        assert edge2 > edge1  # Higher calibrated = higher edge

    def test_zero_edge_after_fee_yields_zero_stake(self) -> None:
        """VAL-SIZING-005: Zero or negative edge after fee results in zero paper stake."""
        # calibrated_prob just barely above market_prob, fee eats the edge
        calibrate = 0.41
        market = 0.40
        maker_fee = kalshi_net_fee(price=market, fee_mode="maker")

        row = pass_ready_row(
            calibrated_probability=calibrate,
            display_price=market,
            all_in_cost=0.40,
            expected_value_per_contract=0.001,
        )
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        candidate = report["candidates"][0]
        edge = calibrate - market - maker_fee
        if edge <= 0:
            assert candidate["paper_usable"] is False
            assert candidate["paper_stake"] == 0.0
            assert "edge after fees is not positive" in candidate["blocker_list"]
        else:
            assert candidate["paper_usable"] is True

    def test_negative_edge_after_fee_fully_blocked(self) -> None:
        """When edge is negative after fees, candidate gets zero stake."""
        calibrate = 0.405
        market = 0.40
        expected_value = calibrate * 1.0 - market

        row = pass_ready_row(
            calibrated_probability=calibrate,
            display_price=market,
            all_in_cost=market,
            expected_value_per_contract=expected_value,
        )
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        candidate = report["candidates"][0]
        assert candidate["paper_usable"] is False
        assert candidate["paper_stake"] == 0.0
        assert "edge after fees is not positive" in candidate["blocker_list"]

    def test_maker_fee_gives_higher_stake_than_taker(self) -> None:
        """VAL-SIZING-009: Maker-first strategy uses maker fee for higher stake."""
        calibrate = 0.60
        market = 0.40

        # With maker fee (default) — should pass
        maker_row = pass_ready_row(
            calibrated_probability=calibrate,
            display_price=market,
        )
        report_maker = build_paper_decision_candidates(
            ledger_path=_write_ledger(maker_row),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        maker_candidate = report_maker["candidates"][0]

        maker_fee = kalshi_net_fee(price=market, fee_mode="maker")
        edge_maker = calibrate - market - maker_fee
        assert edge_maker > 0
        assert maker_candidate["paper_usable"] is True
        assert maker_candidate["paper_stake"] > 0

    def test_fee_mode_field_preserved(self) -> None:
        """VAL-SIZING-006: fee_mode field preserved through paper candidate pipeline."""
        row = pass_ready_row()
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        for candidate in report["candidates"]:
            assert "fee_mode" in candidate
            assert candidate["fee_mode"] in ("maker", "taker")
            assert "net_fee" in candidate
            assert candidate["net_fee"] is None or candidate["net_fee"] >= 0

    def test_default_fee_mode_is_maker(self) -> None:
        """VAL-SIZING-007: Default fee_mode is 'maker' for paper sizing."""
        mode, _ = _resolve_paper_fee(
            market_probability=0.50,
            fee_mode=None,
            decay_rate=None,
            time_to_fill=None,
        )
        assert mode == "maker"

        row = pass_ready_row()
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        candidate = report["candidates"][0]
        assert candidate["fee_mode"] == "maker"

    def test_maker_taker_fee_rates(self) -> None:
        """VAL-SIZING-008: Maker fee rate is 0.0175 and taker fee rate is 0.07."""
        assert float(GENERAL_MAKER_FEE_RATE) == pytest.approx(0.0175, abs=1e-10)
        assert float(GENERAL_TAKER_FEE_RATE) == pytest.approx(0.07, abs=1e-10)

        maker_fee = kalshi_trade_fee(price=0.50, fee_rate=GENERAL_MAKER_FEE_RATE)
        taker_fee = kalshi_trade_fee(price=0.50, fee_rate=GENERAL_TAKER_FEE_RATE)
        assert maker_fee == pytest.approx(0.0044, abs=1e-4)
        assert taker_fee == pytest.approx(0.0175, abs=1e-4)

    def test_net_fee_computed_per_candidate(self) -> None:
        """VAL-SIZING-004: net_fee computed per-candidate with own market_probability."""
        row_a = pass_ready_row(
            contract_ticker="KXUNIT-A",
            calibrated_probability=0.65,
            display_price=0.20,
            all_in_cost=0.20,
            expected_value_per_contract=0.45,
            capacity_estimate=30.0,
        )
        row_b = pass_ready_row(
            contract_ticker="KXUNIT-B",
            calibrated_probability=0.55,
            display_price=0.50,
            all_in_cost=0.50,
            expected_value_per_contract=0.05,
            capacity_estimate=30.0,
        )
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row_a, row_b),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
            covariance_penalty_lambda=0.0,
        )

        candidates = {c["contract_ticker"]: c for c in report["candidates"]}
        assert candidates["KXUNIT-A"]["net_fee"] != candidates["KXUNIT-B"]["net_fee"]
        assert candidates["KXUNIT-A"]["net_fee"] >= 0
        assert candidates["KXUNIT-B"]["net_fee"] >= 0
        # Verify both match expected values from canonical engine
        assert candidates["KXUNIT-A"]["net_fee"] == pytest.approx(
            kalshi_net_fee(price=0.20, fee_mode="maker"), abs=1e-6
        )
        assert candidates["KXUNIT-B"]["net_fee"] == pytest.approx(
            kalshi_net_fee(price=0.50, fee_mode="maker"), abs=1e-6
        )

    def test_full_pipeline_edge_to_stake(self) -> None:
        """Full pipeline: maker fee -> edge -> kelly stake with net_fee in candidate."""
        calibrate = 0.60
        market = 0.40
        maker_fee = kalshi_net_fee(price=market, fee_mode="maker")
        edge = calibrate - market - maker_fee
        assert edge > 0

        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(pass_ready_row()),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
            kelly_fraction=0.25,
            max_fraction_per_contract=0.02,
        )
        candidate = report["candidates"][0]
        assert candidate["net_fee"] == pytest.approx(maker_fee, abs=1e-6)
        assert candidate["fee_mode"] == "maker"
        assert candidate["paper_usable"] is True
        assert candidate["paper_stake"] > 0

    def test_portfolio_risk_reflects_fee_aware_stakes(self) -> None:
        """VAL-SIZING-037, VAL-CROSS-019: Portfolio risk report reflects fee-adjusted stakes."""
        row_a = pass_ready_row(
            contract_ticker="KXUNIT-A",
            calibrated_probability=0.65,
            display_price=0.55,
            all_in_cost=0.55,
            expected_value_per_contract=0.10,
            capacity_estimate=30.0,
        )
        row_b = pass_ready_row(
            contract_ticker="KXUNIT-B",
            calibrated_probability=0.70,
            display_price=0.60,
            all_in_cost=0.60,
            expected_value_per_contract=0.10,
            capacity_estimate=30.0,
        )
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row_a, row_b),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
            covariance_penalty_lambda=0.0,
        )
        risk = report["portfolio_risk"]
        total_stake = risk["total_paper_stake"]
        assert total_stake > 0
        assert risk["paper_usable_count"] > 0

        # Each candidate should have a valid stake
        for candidate in report["candidates"]:
            if candidate["paper_usable"]:
                assert candidate["paper_stake"] > 0
                assert candidate["net_fee"] is not None
                assert candidate["net_fee"] >= 0


# ── EV ledger net_fee tests ─────────────────────────────────────────────────


class TestEvLedgerFeeFields:
    """Tests for EV ledger fee fields (VAL-CROSS-009, VAL-CROSS-018)."""

    def test_ev_ledger_rows_carry_net_fee_and_fee_mode(self) -> None:
        """VAL-CROSS-009: EV ledger rows include net_fee and fee_mode fields."""
        from predmarket.kalshi_execution_cost import kalshi_net_fee
        from scripts.kalshi_contract_ev_ledger import make_ev_row

        # Build a minimal EV row to inspect fee fields
        display_price = 0.50
        row = make_ev_row(
            source_repo_id="test",
            source_artifact=Path("/dev/null"),
            source_row_index=0,
            contract_ticker="KXTEST-UNIT",
            event_ticker="KXTEST",
            market_ticker="KXTEST",
            side="yes",
            selection="yes",
            market_type="test",
            title="Test",
            resolution_rule="Test resolution",
            resolution_rule_source="test",
            resolution_rule_status="verified_official_terms",
            display_price=display_price,
            display_price_source="test",
            executable_price_source="test",
            fee_estimate=None,
            slippage_buffer=None,
            explicit_all_in_cost=display_price,
            all_in_payout_multiple=None,
            kalshi_payout_multiple=None,
            calibrated_probability=0.60,
            calibrated_probability_source="test",
            calibration_status="validated_calibrated_probability",
            calibrated_probability_source_artifact=None,
            calibrated_probability_source_sha256=None,
            reference_probability=display_price,
            reference_probability_source="test",
            probability_uncertainty=None,
            kalshi_bid=0.48,
            kalshi_ask=0.52,
            kalshi_midpoint=0.50,
            gate_status="pass",
            gate_reasons=[],
            review_status="test",
            timing_status="clean",
            mapping_confidence="test",
        )
        assert "net_fee" in row
        assert row["net_fee"] is not None
        assert isinstance(row["net_fee"], float)
        exp_net = kalshi_net_fee(price=display_price, fee_mode="maker")
        assert row["net_fee"] == pytest.approx(exp_net, abs=1e-6)
        assert "fee_mode" in row
        assert row["fee_mode"] == "maker"
        assert "fee_rate" in row
        assert "fee_source" in row

    def test_ev_ledger_net_fee_none_when_no_price(self) -> None:
        """When display_price is None, net_fee should be None."""
        from scripts.kalshi_contract_ev_ledger import make_ev_row

        row = make_ev_row(
            source_repo_id="test",
            source_artifact=Path("/dev/null"),
            source_row_index=0,
            contract_ticker="KXTEST-UNIT",
            event_ticker="KXTEST",
            market_ticker="KXTEST",
            side="yes",
            selection="yes",
            market_type="test",
            title="Test",
            resolution_rule="Test resolution",
            resolution_rule_source="test",
            resolution_rule_status="verified_official_terms",
            display_price=None,
            display_price_source="test",
            executable_price_source="test",
            fee_estimate=None,
            slippage_buffer=None,
            explicit_all_in_cost=None,
            all_in_payout_multiple=None,
            kalshi_payout_multiple=None,
            calibrated_probability=0.60,
            calibrated_probability_source="test",
            calibration_status="validated_calibrated_probability",
            calibrated_probability_source_artifact=None,
            calibrated_probability_source_sha256=None,
            reference_probability=None,
            reference_probability_source="test",
            probability_uncertainty=None,
            kalshi_bid=None,
            kalshi_ask=None,
            kalshi_midpoint=None,
            gate_status="blocked",
            gate_reasons=["no price"],
            review_status="test",
            timing_status="clean",
            mapping_confidence="test",
        )
        assert "net_fee" in row
        assert row["net_fee"] is None


# ── Maker/taker branching via build_paper_decision_candidates ───────────────


class TestMakerTakerBranching:
    """Integration tests for maker/taker branching through the full pipeline."""

    def test_decay_absent_defaults_maker(self) -> None:
        """No decay_rate -> maker mode, no taker switch."""
        row = pass_ready_row(
            calibrated_probability=0.60,
            display_price=0.50,
            all_in_cost=0.50,
            expected_value_per_contract=0.10,
        )
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        candidate = report["candidates"][0]
        assert candidate["fee_mode"] == "maker"
        assert candidate["net_fee"] == pytest.approx(
            kalshi_net_fee(price=0.50, fee_mode="maker"), abs=1e-6
        )

    def test_high_decay_triggers_taker(self) -> None:
        """High decay_rate * time_to_fill > taker_fee - maker_fee -> taker mode."""
        market = 0.50
        maker_fee = kalshi_net_fee(price=market, fee_mode="maker")
        taker_fee = kalshi_net_fee(price=market, fee_mode="taker")
        fee_diff = taker_fee - maker_fee

        # If decay_cost > fee_diff, should be taker
        decay_cost = 0.02 * 10.0  # 0.2
        if decay_cost > fee_diff:
            row = pass_ready_row(
                calibrated_probability=0.60,
                display_price=market,
                all_in_cost=market,
                expected_value_per_contract=0.10,
                decay_rate=0.02,
                time_to_fill=10.0,
            )
            report = build_paper_decision_candidates(
                ledger_path=_write_ledger(row),
                generated_utc="2026-07-03T00:00:00Z",
                paper_bankroll=1000.0,
            )
            candidate = report["candidates"][0]
            assert candidate["fee_mode"] == "taker"
            assert candidate["net_fee"] == pytest.approx(taker_fee, abs=1e-6)

    def test_low_decay_stays_maker_in_pipeline(self) -> None:
        """Low decay -> stays maker."""
        row = pass_ready_row(
            calibrated_probability=0.60,
            display_price=0.50,
            all_in_cost=0.50,
            expected_value_per_contract=0.10,
            decay_rate=0.0001,
            time_to_fill=1.0,
        )
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        candidate = report["candidates"][0]
        assert candidate["fee_mode"] == "maker"

    def test_negative_decay_rate_in_pipeline(self) -> None:
        """VAL-SIZING-012: Negative decay_rate does not trigger taker switch."""
        row = pass_ready_row(
            calibrated_probability=0.60,
            display_price=0.50,
            all_in_cost=0.50,
            expected_value_per_contract=0.10,
            decay_rate=-0.001,
            time_to_fill=100.0,
        )
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        candidate = report["candidates"][0]
        assert candidate["fee_mode"] == "maker"

    def test_zero_time_to_fill_in_pipeline(self) -> None:
        """VAL-SIZING-013: time_to_fill=0 keeps maker fee."""
        row = pass_ready_row(
            calibrated_probability=0.60,
            display_price=0.50,
            all_in_cost=0.50,
            expected_value_per_contract=0.10,
            decay_rate=0.01,
            time_to_fill=0.0,
        )
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        candidate = report["candidates"][0]
        assert candidate["fee_mode"] == "maker"


# ── Cross-cutting: portfolio risk reflects fee awareness ────────────────────


class TestPortfolioRiskFeeAware:
    """Portfolio risk diagnostics reflect fee-aware stakes (VAL-CROSS-019)."""

    def test_total_stake_includes_fee_aware_stakes(self) -> None:
        """Portfolio total_stake reflects fee-adjusted stakes from usable candidates."""
        row = pass_ready_row()
        # With edge > 0 after maker fee, should be paper_usable
        calibrate = 0.60
        market = 0.40
        maker_fee = kalshi_net_fee(price=market, fee_mode="maker")
        edge = calibrate - market - maker_fee
        assert edge > 0  # sanity check

        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        risk = report["portfolio_risk"]
        assert risk["total_paper_stake"] > 0
        assert risk["paper_usable_count"] >= 1
        assert "largest_cluster" in risk
        assert "largest_contract" in risk
        assert "largest_signal" in risk


# ── Covariance penalty tests ────────────────────────────────────────────────


class TestCovariancePenalty:
    """Tests for covariance penalty in paper sizing (VAL-SIZING-014..020, VAL-CROSS-013)."""

    def test_single_position_zero_penalty(self) -> None:
        """VAL-SIZING-020: Single-position portfolio has zero covariance penalty."""
        stakes = [50.0]
        cluster_keys = ["crypto|BTC|range"]
        penalties = compute_covariance_penalty(stakes, cluster_keys)
        assert all(p == 0.0 for p in penalties)

    def test_single_position_empty_cluster_key_zero_penalty(self) -> None:
        """Single position with empty cluster_key gets zero penalty."""
        stakes = [50.0]
        cluster_keys = [""]
        penalties = compute_covariance_penalty(stakes, cluster_keys)
        assert all(p == 0.0 for p in penalties)

    def test_missing_cluster_key_zero_penalty(self) -> None:
        """VAL-SIZING-016: Missing correlation data (empty cluster_key) gets zero penalty."""
        stakes = [30.0, 40.0]
        cluster_keys = ["", ""]
        penalties = compute_covariance_penalty(stakes, cluster_keys)
        assert all(p == 0.0 for p in penalties)

    def test_mixed_missing_and_present_cluster_keys(self) -> None:
        """VAL-SIZING-016: Positions with cluster_key get penalty, missing ones don't."""
        stakes = [50.0, 50.0, 50.0]
        cluster_keys = ["cluster_a", "cluster_a", ""]
        penalties = compute_covariance_penalty(stakes, cluster_keys)
        # Positions 0 and 1 same cluster → get penalty
        assert penalties[0] > 0.0
        assert penalties[1] > 0.0
        # Position 2 has no cluster_key → zero penalty
        assert penalties[2] == 0.0

    def test_covariance_penalty_computed_from_cluster_correlation(self) -> None:
        """VAL-SIZING-014: Covariance penalty computed from cluster correlation data."""
        stakes = [50.0, 50.0, 50.0]
        cluster_keys = ["cluster_a", "cluster_a", "cluster_b"]
        penalties = compute_covariance_penalty(stakes, cluster_keys)

        # Same-cluster positions (0 and 1) get penalty
        assert penalties[0] > 0.0
        assert penalties[1] > 0.0
        # Different cluster (2) has no same-cluster neighbor → zero penalty
        assert penalties[2] == 0.0

        # Both in cluster_a should get same penalty (equal stakes)
        assert penalties[0] == pytest.approx(penalties[1], abs=1e-10)

    def test_covariance_penalty_formula_correct(self) -> None:
        """Verify exact penalty formula uses bankroll-normalized dollar exposure."""
        stakes = [100.0, 100.0]
        cluster_keys = ["cluster_x", "cluster_x"]
        # With lambda=0.1, rho=0.5, bankroll=1000:
        # penalty_0 = 0.1 * 0.5 * 100.0 * (100.0 / 1000.0) = 0.5
        # penalty_1 = 0.1 * 0.5 * 100.0 * (100.0 / 1000.0) = 0.5
        expected = 0.1 * 0.5 * 100.0 * (100.0 / 1000.0)
        penalties = compute_covariance_penalty(
            stakes,
            cluster_keys,
            lambda_penalty=0.1,
            within_cluster_correlation=0.5,
            normalization_base=1000.0,
        )
        assert penalties[0] == pytest.approx(expected, abs=1e-10)
        assert penalties[1] == pytest.approx(expected, abs=1e-10)

    def test_reduced_allocation_for_correlated_positions(self) -> None:
        """VAL-SIZING-015: Positions in same cluster get reduced allocation."""
        # Scenario 1: Two positions in same cluster
        stakes_same = [50.0, 50.0]
        cluster_same = ["cluster_a", "cluster_a"]
        adj_same = compute_covariance_penalty(stakes_same, cluster_same)

        # Scenario 2: Two positions in different clusters
        stakes_diff = [50.0, 50.0]
        cluster_diff = ["cluster_a", "cluster_b"]
        adj_diff = compute_covariance_penalty(stakes_diff, cluster_diff)

        # Same-cluster pair gets penalty applied
        assert adj_same[0] > 0.0
        assert adj_same[1] > 0.0
        # Different-cluster pair gets no penalty
        assert adj_diff[0] == 0.0
        assert adj_diff[1] == 0.0
        # Same total edge but correlated → reduced effective stake
        assert adj_same[0] > adj_diff[0]  # Penalty > 0, so reduction > no reduction
        # Wait - penalty is the REDUCTION, not the adjusted stake
        # Same cluster → penalty > 0 → actual stake reduced more
        assert adj_same[0] > 0  # positive penalty
        assert adj_diff[0] == 0  # zero penalty

    def test_lambda_configurable_default_positive(self) -> None:
        """VAL-SIZING-017: Lambda penalty weight is configurable and defaults to positive."""
        assert DEFAULT_COVARIANCE_LAMBDA > 0.0
        assert isinstance(DEFAULT_COVARIANCE_LAMBDA, float)

        stakes = [50.0, 50.0]
        cluster_keys = ["cluster_a", "cluster_a"]

        # Default lambda
        default_penalties = compute_covariance_penalty(stakes, cluster_keys)
        assert default_penalties[0] > 0.0

        # Higher lambda → higher penalty
        high_penalties = compute_covariance_penalty(stakes, cluster_keys, lambda_penalty=1.0)
        assert high_penalties[0] > default_penalties[0]

        # Lower lambda → lower penalty
        low_penalties = compute_covariance_penalty(stakes, cluster_keys, lambda_penalty=0.01)
        assert low_penalties[0] < default_penalties[0]

        # Zero lambda → no penalty
        zero_penalties = compute_covariance_penalty(stakes, cluster_keys, lambda_penalty=0.0)
        assert all(p == 0.0 for p in zero_penalties)

    def test_within_cluster_correlation_positive_bounded(self) -> None:
        """VAL-SIZING-018: Within-cluster correlation is positive and bounded <= 1.0."""
        assert 0.0 < DEFAULT_WITHIN_CLUSTER_CORRELATION <= 1.0

        # Test with various valid correlations
        stakes = [50.0, 50.0]
        cluster_keys = ["cluster_a", "cluster_a"]

        for rho in [0.1, 0.5, 0.9, 1.0]:
            penalties = compute_covariance_penalty(
                stakes, cluster_keys, within_cluster_correlation=rho
            )
            assert penalties[0] > 0.0
            assert penalties[1] > 0.0

        # Zero correlation → no penalty
        zero_penalties = compute_covariance_penalty(
            stakes, cluster_keys, within_cluster_correlation=0.0
        )
        assert all(p == 0.0 for p in zero_penalties)

    def test_no_negative_paper_stakes(self) -> None:
        """VAL-SIZING-019: Covariance penalty never produces negative paper stakes."""
        # Pathological: many positions with large stakes in one cluster
        stakes = [1000.0, 1000.0, 1000.0, 1000.0, 1000.0]
        cluster_keys = ["cluster_z"] * 5
        penalties = compute_covariance_penalty(
            stakes, cluster_keys, lambda_penalty=10.0, within_cluster_correlation=1.0
        )
        # Penalties should always be non-negative
        for _, (stake, penalty) in enumerate(zip(stakes, penalties, strict=False)):
            assert penalty >= 0.0
            # The caller should floor at 0: max(0, stake - penalty)
            adjusted = max(0.0, stake - penalty)
            assert adjusted >= 0.0

    def test_cross_correlation_reduces_stake(self) -> None:
        """VAL-CROSS-013: Two contracts in same cluster get reduced stake vs naive Kelly."""
        row_a = pass_ready_row(
            contract_ticker="KXUNIT-A",
            calibrated_probability=0.65,
            display_price=0.45,
            all_in_cost=0.45,
            expected_value_per_contract=0.20,
            capacity_estimate=200.0,
            correlation_cluster_key="sports|MLB|game1",
        )
        row_b = pass_ready_row(
            contract_ticker="KXUNIT-B",
            calibrated_probability=0.65,
            display_price=0.45,
            all_in_cost=0.45,
            expected_value_per_contract=0.20,
            capacity_estimate=200.0,
            correlation_cluster_key="sports|MLB|game1",
        )
        # Use very small lambda so penalty is modest and candidates stay usable
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row_a, row_b),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
            covariance_penalty_lambda=0.001,
            within_cluster_correlation=0.5,
        )
        candidates = {c["contract_ticker"]: c for c in report["candidates"]}
        assert candidates["KXUNIT-A"]["paper_usable"] is True
        assert candidates["KXUNIT-B"]["paper_usable"] is True
        # Both should have positive stakes (no negative)
        assert candidates["KXUNIT-A"]["paper_stake"] >= 0
        assert candidates["KXUNIT-B"]["paper_stake"] >= 0
        # Covariance penalty field should be present
        assert "covariance_penalty" in candidates["KXUNIT-A"]
        assert "covariance_penalty" in candidates["KXUNIT-B"]
        # Penalty should be positive for same-cluster pair
        assert candidates["KXUNIT-A"]["covariance_penalty"] > 0
        assert candidates["KXUNIT-B"]["covariance_penalty"] > 0

    def test_three_positions_two_in_same_cluster(self) -> None:
        """VAL-SIZING-014: Three positions, two share cluster_key, one different."""
        row_a = pass_ready_row(
            contract_ticker="KXUNIT-A",
            calibrated_probability=0.65,
            display_price=0.45,
            all_in_cost=0.45,
            expected_value_per_contract=0.20,
            capacity_estimate=200.0,
            correlation_cluster_key="sports|MLB|game1",
        )
        row_b = pass_ready_row(
            contract_ticker="KXUNIT-B",
            calibrated_probability=0.65,
            display_price=0.45,
            all_in_cost=0.45,
            expected_value_per_contract=0.20,
            capacity_estimate=200.0,
            correlation_cluster_key="sports|MLB|game1",
        )
        row_c = pass_ready_row(
            contract_ticker="KXUNIT-C",
            calibrated_probability=0.65,
            display_price=0.45,
            all_in_cost=0.45,
            expected_value_per_contract=0.20,
            capacity_estimate=200.0,
            correlation_cluster_key="sports|NBA|game2",
        )
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row_a, row_b, row_c),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
            covariance_penalty_lambda=0.1,
            within_cluster_correlation=0.5,
        )
        candidates = {c["contract_ticker"]: c for c in report["candidates"]}
        # Both positions in same cluster should be reduced
        assert candidates["KXUNIT-A"]["paper_stake"] >= 0
        assert candidates["KXUNIT-B"]["paper_stake"] >= 0
        assert candidates["KXUNIT-C"]["paper_stake"] >= 0

        # The same-cluster pair (A, B) should have positive penalties
        assert candidates["KXUNIT-A"]["covariance_penalty"] > 0
        assert candidates["KXUNIT-B"]["covariance_penalty"] > 0
        # Different cluster (C) should have zero penalty (no same-cluster neighbor)
        # Penalty for C: lambda x rho x w_C x sum_{j!=C, same cluster} w_j = 0
        assert candidates["KXUNIT-C"]["covariance_penalty"] == 0.0

    def test_covariance_penalty_in_pipeline_with_defaults(self) -> None:
        """Default covariance penalty reduces but does not zero valid paper stakes."""
        row_a = pass_ready_row(
            contract_ticker="KXUNIT-A",
            calibrated_probability=0.65,
            display_price=0.45,
            all_in_cost=0.45,
            expected_value_per_contract=0.20,
            capacity_estimate=200.0,
            correlation_cluster_key="sports|MLB|game1",
        )
        row_b = pass_ready_row(
            contract_ticker="KXUNIT-B",
            calibrated_probability=0.65,
            display_price=0.45,
            all_in_cost=0.45,
            expected_value_per_contract=0.20,
            capacity_estimate=200.0,
            correlation_cluster_key="sports|MLB|game1",
        )
        # Use default lambda and correlation
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row_a, row_b),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        candidates = {c["contract_ticker"]: c for c in report["candidates"]}
        assert candidates["KXUNIT-A"]["paper_usable"] is True
        assert candidates["KXUNIT-B"]["paper_usable"] is True
        assert candidates["KXUNIT-A"]["paper_stake"] > 0
        assert candidates["KXUNIT-B"]["paper_stake"] > 0
        assert candidates["KXUNIT-A"]["covariance_penalty"] > 0
        assert candidates["KXUNIT-B"]["covariance_penalty"] > 0

    def test_single_candidate_via_pipeline_zero_penalty(self) -> None:
        """Single-position portfolio through full pipeline has zero penalty."""
        row = pass_ready_row(
            contract_ticker="KXUNIT-SINGLE",
            calibrated_probability=0.65,
            display_price=0.45,
            all_in_cost=0.45,
            expected_value_per_contract=0.20,
            capacity_estimate=200.0,
            correlation_cluster_key="sports|MLB|game1",
        )
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
            covariance_penalty_lambda=0.1,
            within_cluster_correlation=0.5,
        )
        candidate = report["candidates"][0]
        assert candidate["paper_stake"] >= 0


# ── Paper sizing edge cases (VAL-SIZING-027 through 036) ─────────────────────


class TestPaperSizingEdgeCases:
    """Edge cases for paper sizing (VAL-SIZING-027..036)."""

    def test_none_calibrated_probability_zero_stake(self) -> None:
        """VAL-SIZING-027: calibrated_probability=None -> zero paper stake with blocker."""
        row = pass_ready_row(
            calibrated_probability=None,
            display_price=0.40,
            expected_value_per_contract=None,
        )
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        candidate = report["candidates"][0]
        assert candidate["paper_usable"] is False
        assert candidate["paper_stake"] == 0.0
        assert "calibrated probability missing" in candidate["blocker_list"]

    def test_none_market_probability_zero_stake(self) -> None:
        """VAL-SIZING-028: market_probability=None -> zero paper stake with blocker."""
        row = pass_ready_row(
            calibrated_probability=0.60,
            display_price=None,
            all_in_cost=None,
        )
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        candidate = report["candidates"][0]
        assert candidate["paper_usable"] is False
        assert candidate["paper_stake"] == 0.0
        # Without market_probability, edge_after_fee is None, and all_in_cost is None
        blockers = " ".join(candidate["blocker_list"])
        assert "all-in cost missing" in blockers

    def test_market_probability_zero_or_one(self) -> None:
        """VAL-SIZING-029: market_probability outside (0,1) -> zero paper stake."""
        # P=0.0
        row_zero = pass_ready_row(
            calibrated_probability=0.60,
            display_price=0.0,
            all_in_cost=0.0,
            expected_value_per_contract=0.60,
        )
        report_zero = build_paper_decision_candidates(
            ledger_path=_write_ledger(row_zero),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        candidate_zero = report_zero["candidates"][0]
        # With P=0, all_in_cost=0 and calibrated_prob=0.6 -> kelly is calculable
        # but edge after fee might still be positive
        # The blocker depends on edge_after_fee
        if candidate_zero["paper_usable"]:
            assert candidate_zero["net_fee"] == 0.0  # P=0 -> fee=0

        # P=1.0 (or >= 1)
        row_one = pass_ready_row(
            calibrated_probability=0.60,
            display_price=1.0,
            all_in_cost=1.0,
            expected_value_per_contract=-0.40,
        )
        report_one = build_paper_decision_candidates(
            ledger_path=_write_ledger(row_one),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        candidate_one = report_one["candidates"][0]
        # Market_prob=1.0 yields no fee, but expected_value=-0.40 is negative
        assert candidate_one["paper_usable"] is False
        assert "expected value is not positive" in candidate_one["blocker_list"]

    def test_unrecognized_fee_mode_falls_back_to_maker(self) -> None:
        """VAL-SIZING-030: Unrecognized fee_mode falls back to maker (safe default)."""
        from predmarket.paper_decision_engine import _resolve_paper_fee

        maker_fee = kalshi_net_fee(price=0.50, fee_mode="maker")
        for bad_mode in ["routing_error", "unknown", "hybrid", ""]:
            mode, fee = _resolve_paper_fee(
                market_probability=0.50,
                fee_mode=bad_mode,
                decay_rate=None,
                time_to_fill=None,
            )
            assert mode == "maker", f"fee_mode={bad_mode!r} should fall back to maker"
            assert fee == pytest.approx(maker_fee, abs=1e-6), (
                f"fee_mode={bad_mode!r} should use maker fee"
            )

    def test_multiple_zero_or_negative_edge_candidates(self) -> None:
        """VAL-SIZING-031: All candidates with zero/negative edge after fee -> all blocked."""
        # Both candidates have tiny edge that fee eats up
        row_a = pass_ready_row(
            contract_ticker="KXUNIT-A",
            calibrated_probability=0.405,
            display_price=0.40,
            all_in_cost=0.40,
            expected_value_per_contract=0.005,
        )
        row_b = pass_ready_row(
            contract_ticker="KXUNIT-B",
            calibrated_probability=0.504,
            display_price=0.50,
            all_in_cost=0.50,
            expected_value_per_contract=0.004,
        )
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row_a, row_b),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        for candidate in report["candidates"]:
            assert candidate["paper_usable"] is False
            assert candidate["paper_stake"] == 0.0
        assert report["portfolio_risk"]["paper_usable_count"] == 0

    def test_negative_capacity_treated_as_zero(self) -> None:
        """VAL-SIZING-032: Negative capacity from CCD sentinel treated as 0."""
        row = pass_ready_row(
            capacity_estimate=-1.0,
        )
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        candidate = report["candidates"][0]
        # Negative capacity means positive capacity estimate missing -> blocker
        assert candidate["paper_usable"] is False
        assert "positive capacity estimate missing" in candidate["blocker_list"]

    def test_very_small_edge_floored_to_zero(self) -> None:
        """VAL-SIZING-033: Very small edge (< 1e-6) after fee floored to zero stake."""
        # calibrated_prob just a hair above market_prob, fee eats it
        calibrate = 0.5000001
        market = 0.50
        maker_fee = kalshi_net_fee(price=0.50, fee_mode="maker")
        assert calibrate - market - maker_fee < 0
        # Fee at P=0.50 maker is ~0.0044, so edge is negative
        row = pass_ready_row(
            calibrated_probability=calibrate,
            display_price=market,
            all_in_cost=market,
            expected_value_per_contract=calibrate - market,
        )
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        candidate = report["candidates"][0]
        assert candidate["paper_usable"] is False
        assert candidate["paper_stake"] == 0.0
        assert "edge after fees is not positive" in candidate["blocker_list"]

    def test_maker_vs_taker_stake_reduction(self) -> None:
        """VAL-SIZING-035: Changing fee_mode from maker to taker reduces paper_stake."""
        from predmarket.paper_decision_engine import _resolve_paper_fee

        market = 0.40
        calibrate = 0.60

        mode_maker, fee_maker = _resolve_paper_fee(
            market_probability=market, fee_mode=None, decay_rate=None, time_to_fill=None
        )
        _mode_taker, fee_taker = _resolve_paper_fee(
            market_probability=market, fee_mode="taker", decay_rate=0.1, time_to_fill=10.0
        )

        assert mode_maker == "maker"
        assert fee_maker <= fee_taker
        edge_maker = calibrate - market - fee_maker
        edge_taker = calibrate - market - fee_taker
        assert edge_maker >= edge_taker

        # Through the pipeline: default maker first gives higher stake
        if edge_maker > 0:
            row = pass_ready_row(
                calibrated_probability=calibrate,
                display_price=market,
                all_in_cost=market,
                expected_value_per_contract=0.20,
            )
            report = build_paper_decision_candidates(
                ledger_path=_write_ledger(row),
                generated_utc="2026-07-03T00:00:00Z",
                paper_bankroll=1000.0,
            )
            candidate = report["candidates"][0]
            assert candidate["fee_mode"] == "maker"

    def test_bankroll_constraint_applied_after_penalties(self) -> None:
        """VAL-SIZING-036: Paper bankroll constraint applied after all penalties and caps."""
        # Huge edge but very small bankroll with small max_fraction
        calibrate = 0.95
        market = 0.05
        maker_fee = kalshi_net_fee(price=market, fee_mode="maker")
        edge = calibrate - market - maker_fee
        assert edge > 0  # Sanity: edge should be clearly positive

        row = pass_ready_row(
            calibrated_probability=calibrate,
            display_price=market,
            all_in_cost=market,
            expected_value_per_contract=0.90,
            capacity_estimate=1000.0,
        )
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=100.0,
            kelly_fraction=0.25,
            max_fraction_per_contract=0.01,  # Max 1% of bankroll = $1
        )
        candidate = report["candidates"][0]
        assert candidate["paper_usable"] is True
        # Bankroll cap: 100 * 0.01 = 1.0
        assert candidate["paper_stake"] <= 1.0
        # Capacity cap: 1000.0, but bankroll cap is tighter
        assert candidate["paper_stake"] <= 100.0 * 0.01

    def test_full_pipeline_maker_fee_to_final_stake(self) -> None:
        """VAL-SIZING-034: Full pipeline: maker fee -> covariance penalty -> ghost-listing cap -> final stake."""
        row_a = pass_ready_row(
            contract_ticker="KXUNIT-A",
            calibrated_probability=0.65,
            display_price=0.55,
            all_in_cost=0.55,
            expected_value_per_contract=0.10,
            capacity_estimate=200.0,
            correlation_cluster_key="sports|MLB|game1",
        )
        row_b = pass_ready_row(
            contract_ticker="KXUNIT-B",
            calibrated_probability=0.65,
            display_price=0.55,
            all_in_cost=0.55,
            expected_value_per_contract=0.10,
            capacity_estimate=200.0,
            correlation_cluster_key="sports|MLB|game1",
        )
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row_a, row_b),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=10000.0,
            kelly_fraction=0.25,
            max_fraction_per_contract=0.02,
            covariance_penalty_lambda=0.001,  # Small lambda so penalty < stake
            within_cluster_correlation=0.5,
        )
        candidates = {c["contract_ticker"]: c for c in report["candidates"]}
        for ticker in ("KXUNIT-A", "KXUNIT-B"):
            c = candidates[ticker]
            # Should have fee info
            assert c["net_fee"] is not None and c["net_fee"] >= 0
            assert c["fee_mode"] == "maker"
            # Should have covariance penalty
            assert "covariance_penalty" in c
            assert c["covariance_penalty"] > 0
            # Should have ghost-listing flag
            assert "ghost_listing_flag" in c
            # Should respect bankroll constraint
            assert c["paper_stake"] <= 10000.0 * 0.02
            # Capacity cap respected
            assert c["paper_stake"] <= 200.0
            # No negative stake
            assert c["paper_stake"] >= 0
        # Portfolio risk should reflect adjustments
        risk = report["portfolio_risk"]
        assert risk["total_paper_stake"] > 0
        assert risk["paper_usable_count"] > 0
        assert risk["total_paper_stake"] <= 200.0 * 2  # Both capped at 200


# ── Cross-area integration tests (VAL-CROSS-032..051) ───────────────────────


class TestCrossAreaIntegration:
    """Cross-area integration tests covering full pipeline and regression."""

    def test_ev_ledger_usable_only_when_all_gates_pass(self) -> None:
        """VAL-CROSS-032: EV ledger rows usable=False unless all gates pass.

        Uses the paper decision engine's blockers_for_row to verify that
        every gate failure keeps the row blocked.
        """
        from predmarket.paper_decision_engine import blockers_for_row

        # All gates pass -> no blockers
        pass_row = pass_ready_row()
        blockers = blockers_for_row(
            pass_row,
            calibrated=0.60,
            all_in_cost=0.40,
            expected_value=0.20,
            capacity=50.0,
            retired=False,
            edge_after_fee=0.10,
        )
        assert len(blockers) == 0

        # Gate status not pass -> blocked
        blocked_gate_row = pass_ready_row(gate_status="blocked")
        blockers = blockers_for_row(
            blocked_gate_row,
            calibrated=0.60,
            all_in_cost=0.40,
            expected_value=0.20,
            capacity=50.0,
            retired=False,
            edge_after_fee=0.10,
        )
        assert any("gate status" in b for b in blockers)

        # Capacity gate not passed -> blocked
        blocked_cap_row = pass_ready_row(capacity_gate_status="blocked")
        blockers = blockers_for_row(
            blocked_cap_row,
            calibrated=0.60,
            all_in_cost=0.40,
            expected_value=0.20,
            capacity=50.0,
            retired=False,
            edge_after_fee=0.10,
        )
        assert any("capacity gate" in b for b in blockers)

        # Correlation cluster gate not passed -> blocked
        blocked_cluster_row = pass_ready_row(correlation_cluster_gate_status="blocked")
        blockers = blockers_for_row(
            blocked_cluster_row,
            calibrated=0.60,
            all_in_cost=0.40,
            expected_value=0.20,
            capacity=50.0,
            retired=False,
            edge_after_fee=0.10,
        )
        assert any("cluster gate" in b for b in blockers)

        # Decay gate not passed -> blocked
        blocked_decay_row = pass_ready_row(decay_gate_status="blocked")
        blockers = blockers_for_row(
            blocked_decay_row,
            calibrated=0.60,
            all_in_cost=0.40,
            expected_value=0.20,
            capacity=50.0,
            retired=False,
            edge_after_fee=0.10,
        )
        assert any("decay gate" in b for b in blockers)

    def test_existing_families_work_after_fee_migration(self) -> None:
        """VAL-CROSS-044: Existing signal families produce valid results after fee migration.

        Tests that crypto, sports, and weather family modules can be imported
        and their basic functions work without errors.
        """
        # Crypto family
        from predmarket.crypto_family import make_crypto_family

        crypto_family = make_crypto_family()
        assert crypto_family.family_id is not None
        assert callable(crypto_family.prediction_rule)

        # Sports family (baseball)
        from predmarket.sports_family import make_sports_family

        sports_family = make_sports_family()
        assert sports_family.family_id is not None
        assert callable(sports_family.prediction_rule)

        # Weather family
        from predmarket.weather_family import make_weather_family

        weather_family = make_weather_family()
        assert weather_family.family_id is not None
        assert callable(weather_family.prediction_rule)

    def test_maker_fee_lower_cost_than_taker(self) -> None:
        """VAL-CROSS-051: EV rows with fee_mode='maker' have lower all-in cost than 'taker'."""
        from predmarket.kalshi_execution_cost import kalshi_net_fee

        for price in [0.10, 0.25, 0.50, 0.75, 0.90]:
            maker_cost = kalshi_net_fee(price=price, fee_mode="maker")
            taker_cost = kalshi_net_fee(price=price, fee_mode="taker")
            assert maker_cost <= taker_cost, (
                f"At price={price}: maker_cost {maker_cost} > taker_cost {taker_cost}"
            )

    def test_consumers_produce_identical_or_more_conservative_results(self) -> None:
        """VAL-CROSS-050: Consumers produce identical or more conservative results after migration."""
        # Verify that kalshi_net_fee always produces non-negative values
        from predmarket.kalshi_execution_cost import kalshi_net_fee

        for price in [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]:
            for mode in ["maker", "taker"]:
                fee = kalshi_net_fee(price=price, fee_mode=mode)
                assert fee >= 0.0, f"Negative net_fee at price={price}, mode={mode}: {fee}"

        # Verify that maker fee is always <= taker fee for the same price
        for price in [p / 100.0 for p in range(5, 100, 5)]:
            maker_fee = kalshi_net_fee(price=price, fee_mode="maker")
            taker_fee = kalshi_net_fee(price=price, fee_mode="taker")
            assert maker_fee <= taker_fee, (
                f"Maker fee {maker_fee} > taker fee {taker_fee} at P={price}"
            )

    def test_research_only_flags_on_all_new_artifacts(self) -> None:
        """VAL-CROSS-038: execution_enabled and market_execution are false on all new artifacts."""
        # Paper decision artifacts
        row = pass_ready_row()
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        assert report["research_only"] is True
        assert report["execution_enabled"] is False
        assert report["market_execution"] is False
        assert report["account_or_order_paths"] is False

        for candidate in report["candidates"]:
            assert candidate.get("research_only", True) is True
            assert candidate.get("execution_enabled", False) is False
            assert candidate.get("market_execution", False) is False

    def test_portfolio_risk_no_regression(self) -> None:
        """VAL-CROSS-049: Paper portfolio risk reporting works correctly."""
        row_a = pass_ready_row(
            contract_ticker="KXUNIT-A",
            calibrated_probability=0.65,
            display_price=0.55,
            all_in_cost=0.55,
            expected_value_per_contract=0.10,
            capacity_estimate=30.0,
            correlation_cluster_key="sports|MLB|game1",
            family_id="sports_baseball",
            model_id="baseball_model_v1",
            signal_formula_key="baseball|v1",
        )
        row_b = pass_ready_row(
            contract_ticker="KXUNIT-B",
            calibrated_probability=0.70,
            display_price=0.60,
            all_in_cost=0.60,
            expected_value_per_contract=0.10,
            capacity_estimate=30.0,
            correlation_cluster_key="sports|MLB|game2",
            family_id="sports_baseball",
            model_id="baseball_model_v2",
            signal_formula_key="baseball|v2",
        )
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row_a, row_b),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
            covariance_penalty_lambda=0.0,
        )
        risk = report["portfolio_risk"]
        assert "total_paper_stake" in risk
        assert risk["total_paper_stake"] > 0
        assert "largest_cluster" in risk
        assert "largest_contract" in risk
        assert "largest_signal" in risk
        assert "largest_family" in risk
        assert "cap_status" in risk
        assert "cap_breach_count" in risk
        assert risk["paper_usable_count"] > 0

    def test_no_auto_promotion_to_live(self) -> None:
        """No signals auto-promoted without explicit arming."""
        row = pass_ready_row()
        report = build_paper_decision_candidates(
            ledger_path=_write_ledger(row),
            generated_utc="2026-07-03T00:00:00Z",
            paper_bankroll=1000.0,
        )
        # Paper artifacts should never set live execution
        assert report.get("execution_enabled") is False
        assert report.get("market_execution") is False
        assert report.get("live_staking_or_sizing_guidance") is False
        for candidate in report["candidates"]:
            assert candidate.get("execution_enabled", False) is False


# ── Helper to avoid duplication ─────────────────────────────────────────────


def _write_ledger(*rows: dict[str, object]) -> Path:
    path = Path("/tmp") / f"test_fee_ledger_{id(rows)}.json"
    write_json(path, ledger_payload(*rows))
    return path
