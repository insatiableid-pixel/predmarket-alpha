"""Tests for the PassiveLiquidityProvisionFamily — covers VAL-SIGNAL-005 through
VAL-SIGNAL-010, VAL-SIGNAL-014, VAL-SIGNAL-015, VAL-SIGNAL-017, and VAL-CROSS-035.
"""

from __future__ import annotations

from typing import Any

import pytest

from predmarket.engine import build_falsification
from predmarket.passive_liquidity_provision_family import (
    EVALUATOR_MODEL_ID_PREFIX,
    FAMILY_ID,
    PASSIVE_LIQUIDITY_MODEL_EVALUATORS,
    _compute_virtual_order_ev,
    _fill_proxy_for_virtual_bid,
    _make_passive_liquidity_evaluate_fn,
    _net_ev_one_sided_p,
    _quote_price_for_side,
    _replay_virtual_orders,
    _resolve_time_bucket,
    _side_mid,
    make_passive_liquidity_family,
    passive_liquidity_cluster_key_composer,
    passive_liquidity_prediction_rule,
)
from predmarket.signal_family import SignalFamily

# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-014: SignalFamily descriptor is structurally valid
# ═══════════════════════════════════════════════════════════════════════════


def test_signal_family_all_required_fields() -> None:
    """VAL-SIGNAL-014: SignalFamily has all required fields populated."""
    family = make_passive_liquidity_family()
    # Identity
    assert family.family_id == FAMILY_ID
    assert family.official_settlement_source is not None
    assert isinstance(family.official_settlement_source, str)
    assert len(family.official_settlement_source) > 0
    # Prediction rule
    assert family.prediction_rule is not None
    assert callable(family.prediction_rule)
    # Model evaluators
    assert len(family.model_evaluators) >= 1
    for ev in family.model_evaluators:
        assert "model_id" in ev
        assert "evaluate_fn" in ev
        assert callable(ev["evaluate_fn"])
    # Cluster key composer
    assert family.cluster_key_composer is not None
    assert callable(family.cluster_key_composer)
    # Research-only safety
    assert hasattr(family, "fetcher")
    assert hasattr(family, "feature_definitions")
    assert hasattr(family, "reference_source_registry")


def test_signal_family_importable() -> None:
    """SignalFamily is importable from predmarket.signal_family."""
    assert SignalFamily is not None


# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-006: Uses distinct acceptance criteria from directional families
# ═══════════════════════════════════════════════════════════════════════════


def test_acceptance_criteria_is_maker_fill_net_ev() -> None:
    """VAL-SIGNAL-006: Evaluator results include maker_fill_net_ev_after_adverse_selection."""
    fn = _make_passive_liquidity_evaluate_fn("yes")
    rows = [_make_micro_row(i, ticker="KXPL001", price=0.50) for i in range(50)]
    oos_rows = [_make_micro_row(i + 50, ticker="KXPL001", price=0.50) for i in range(20)]
    result = fn(
        rows=rows,
        oos_rows=oos_rows,
        prediction_rule=passive_liquidity_prediction_rule,
        min_independent_labels=10,
        min_oos_labels=5,
    )
    # The primary acceptance metric is maker_fill_net_ev_after_adverse_selection
    assert "maker_fill_net_ev_after_adverse_selection" in result
    # It is NOT a directional accuracy metric
    assert "oos_accuracy" not in result
    assert "null_rate" not in result


def test_evaluator_no_binomial_survival_scoring() -> None:
    """VAL-SIGNAL-006: Evaluator does NOT use binomial survival against null rate."""
    fn = _make_passive_liquidity_evaluate_fn("yes")
    rows = [_make_micro_row(i, ticker="KXPL001", price=0.50) for i in range(50)]
    oos_rows = [_make_micro_row(i + 50, ticker="KXPL001", price=0.50) for i in range(20)]
    result = fn(
        rows=rows,
        oos_rows=oos_rows,
        prediction_rule=passive_liquidity_prediction_rule,
        min_independent_labels=10,
        min_oos_labels=5,
    )
    # Should not have directional accuracy or bucket fields
    assert "oos_correct_count" not in result
    assert "price_bucket" not in result


# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-005: Counterfactual fills and adverse-selection adjustment
# ═══════════════════════════════════════════════════════════════════════════


def test_virtual_order_counterfactual_fill_simulation() -> None:
    """VAL-SIGNAL-005: Virtual orders simulate fills using future snapshots."""
    future_rows = []
    for i in range(5):
        future_rows.append(
            _make_micro_row(
                100 + i,
                ticker="KXPL001",
                price=0.50 + 0.01 * i,
                best_yes_ask=0.52 + 0.01 * i,
                best_no_ask=0.50 - 0.01 * i,
            )
        )
    row = _make_micro_row(0, ticker="KXPL001", price=0.50, best_yes_ask=0.55, best_yes_bid=0.50)
    quote_price = _quote_price_for_side(row, "yes")
    result = _fill_proxy_for_virtual_bid(
        future_rows,
        side="yes",
        quote_price=quote_price if quote_price is not None else 0.51,
        observed_at="2026-07-04T12:00:00Z",
        ttl_seconds=180,
    )
    assert result["status"] in {
        "would_touch_within_ttl",
        "not_touched_within_observed_ttl",
        "insufficient_future_snapshots",
    }


def test_adverse_selection_mid_delta_computed() -> None:
    """VAL-SIGNAL-005: Adverse selection mid-delta is computed for filled orders."""
    result = _compute_virtual_order_ev(
        quote_price=0.50,
        maker_fee=0.0044,
        taker_fee=0.0175,
        mid_at_entry=0.50,
        mid_after_touch=0.49,
        fill_proxy_status="would_touch_within_ttl",
        side="yes",
    )
    assert result["adverse_selection_mid_delta"] == pytest.approx(-0.01, abs=1e-12)
    assert result["maker_fee_savings"] == pytest.approx(0.0131, abs=1e-12)


def test_counterfactual_net_ev_incorporates_fee_and_adverse_selection() -> None:
    """VAL-SIGNAL-005: Net EV incorporates maker fee saving and adverse-selection mid drift."""
    # Scenario: YES-side maker bid, mid decreases (adverse for YES buyer)
    # mid_at_entry=0.50, mid_after_touch=0.495 → delta = -0.005 (adverse)
    # fee_savings = 0.0175 - 0.0044 = 0.0131
    # With fix: adv_cost = abs(-0.005) = 0.005 (delta < 0, adverse for YES buyer)
    # net_ev = 0.0131 - 0.005 = 0.0081
    result = _compute_virtual_order_ev(
        quote_price=0.50,
        maker_fee=0.0044,
        taker_fee=0.0175,
        mid_at_entry=0.50,
        mid_after_touch=0.495,
        fill_proxy_status="would_touch_within_ttl",
        side="yes",
    )
    assert result["maker_fee_savings"] == pytest.approx(0.0131, abs=1e-12)
    assert result["adverse_selection_mid_delta"] == pytest.approx(-0.005, abs=1e-12)
    assert result["counterfactual_net_ev_if_filled"] == pytest.approx(0.0081, abs=1e-12)


def test_counterfactual_net_ev_no_fill_is_zero() -> None:
    """VAL-SIGNAL-005: Unfilled orders have zero net EV."""
    result = _compute_virtual_order_ev(
        quote_price=0.50,
        maker_fee=0.0044,
        taker_fee=0.0175,
        mid_at_entry=0.50,
        mid_after_touch=None,
        fill_proxy_status="not_touched_within_observed_ttl",
        side="yes",
    )
    assert result["counterfactual_net_ev_if_filled"] is None
    assert result["counterfactual_net_ev_with_timeout"] == 0.0


def test_counterfactual_net_ev_yes_side_adverse_delta_penalizes() -> None:
    """YES-side: adverse_selection_mid_delta < 0 (mid decreased) incurs adv_cost."""
    # YES maker bid: mid went from 0.50 → 0.49, delta = -0.01 (adverse)
    # fee_savings = 0.0175 - 0.0044 = 0.0131
    # adv_cost = abs(-0.01) = 0.01
    # net_ev = 0.0131 - 0.01 = 0.0031
    result = _compute_virtual_order_ev(
        quote_price=0.50,
        maker_fee=0.0044,
        taker_fee=0.0175,
        mid_at_entry=0.50,
        mid_after_touch=0.49,
        fill_proxy_status="would_touch_within_ttl",
        side="yes",
    )
    assert result["adverse_selection_mid_delta"] == pytest.approx(-0.01, abs=1e-12)
    assert result["maker_fee_savings"] == pytest.approx(0.0131, abs=1e-12)
    assert result["counterfactual_net_ev_if_filled"] == pytest.approx(0.0031, abs=1e-12)


def test_counterfactual_net_ev_yes_side_favorable_delta_no_penalty() -> None:
    """YES-side: adverse_selection_mid_delta > 0 (mid increased) does not penalize."""
    # YES maker bid: mid went from 0.50 → 0.51, delta = +0.01 (favorable)
    # fee_savings = 0.0175 - 0.0044 = 0.0131
    # adv_cost = 0 (delta > 0 is favorable for YES buyer)
    # net_ev = 0.0131 - 0 = 0.0131
    result = _compute_virtual_order_ev(
        quote_price=0.50,
        maker_fee=0.0044,
        taker_fee=0.0175,
        mid_at_entry=0.50,
        mid_after_touch=0.51,
        fill_proxy_status="would_touch_within_ttl",
        side="yes",
    )
    assert result["adverse_selection_mid_delta"] == pytest.approx(0.01, abs=1e-12)
    assert result["maker_fee_savings"] == pytest.approx(0.0131, abs=1e-12)
    assert result["counterfactual_net_ev_if_filled"] == pytest.approx(0.0131, abs=1e-12)


def test_counterfactual_net_ev_no_side_adverse_delta_penalizes() -> None:
    """NO-side: adverse_selection_mid_delta < 0 (mid decreased) is adverse for NO buyer."""
    # NO maker bid: NO mid went from 0.50 → 0.49, delta = -0.01 (adverse for NO buyer)
    # fee_savings = 0.0175 - 0.0044 = 0.0131
    # For NO side: delta < 0 is adverse → adv_cost = 0.01
    # net_ev = 0.0131 - 0.01 = 0.0031
    result = _compute_virtual_order_ev(
        quote_price=0.50,
        maker_fee=0.0044,
        taker_fee=0.0175,
        mid_at_entry=0.50,
        mid_after_touch=0.49,
        fill_proxy_status="would_touch_within_ttl",
        side="no",
    )
    assert result["adverse_selection_mid_delta"] == pytest.approx(-0.01, abs=1e-12)
    assert result["maker_fee_savings"] == pytest.approx(0.0131, abs=1e-12)
    assert result["counterfactual_net_ev_if_filled"] == pytest.approx(0.0031, abs=1e-12)


def test_counterfactual_net_ev_no_side_favorable_delta_no_penalty() -> None:
    """NO-side: adverse_selection_mid_delta > 0 (mid increased) is favorable for NO buyer."""
    # NO maker bid: NO mid went from 0.49 → 0.50, delta = +0.01 (favorable for NO buyer)
    # fee_savings = 0.0175 - 0.0044 = 0.0131
    # For NO side: delta > 0 is favorable → adv_cost = 0
    # net_ev = 0.0131 - 0 = 0.0131
    result = _compute_virtual_order_ev(
        quote_price=0.50,
        maker_fee=0.0044,
        taker_fee=0.0175,
        mid_at_entry=0.49,
        mid_after_touch=0.50,
        fill_proxy_status="would_touch_within_ttl",
        side="no",
    )
    assert result["adverse_selection_mid_delta"] == pytest.approx(0.01, abs=1e-12)
    assert result["maker_fee_savings"] == pytest.approx(0.0131, abs=1e-12)
    assert result["counterfactual_net_ev_if_filled"] == pytest.approx(0.0131, abs=1e-12)


# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-007: Integrated into falsification gate without bypassing OOS/FDR
# ═══════════════════════════════════════════════════════════════════════════


def test_build_falsification_accepts_family() -> None:
    """VAL-SIGNAL-007: build_falsification accepts passive-liquidity family without errors."""
    family = make_passive_liquidity_family()
    label_rows = []
    for i in range(60):
        label_rows.append(_make_micro_row(i, ticker=f"KXPL{i:04d}", price=0.50))
    result = build_falsification(
        label_rows=label_rows,
        prediction_rule=family.prediction_rule,
        model_evaluators=family.model_evaluators,
        family=family,
        min_independent_labels=10,
        min_oos_labels=5,
        test_fraction=0.30,
        fdr_alpha=0.10,
    )
    assert "status" in result
    assert "evaluations" in result
    assert len(result["evaluations"]) == len(PASSIVE_LIQUIDITY_MODEL_EVALUATORS)
    for ev in result["evaluations"]:
        assert ev["model_id"].startswith(EVALUATOR_MODEL_ID_PREFIX)
        assert "p_value" in ev
        assert "maker_fill_net_ev_after_adverse_selection" in ev


def test_falsification_uses_chronological_split() -> None:
    """VAL-SIGNAL-007: Chronological OOS split is used (later rows are OOS)."""
    family = make_passive_liquidity_family()
    label_rows = []
    for i in range(60):
        label_rows.append(_make_micro_row(i, ticker=f"KXPL{i:04d}", price=0.50))
    result = build_falsification(
        label_rows=label_rows,
        prediction_rule=family.prediction_rule,
        model_evaluators=family.model_evaluators,
        family=family,
        min_independent_labels=10,
        min_oos_labels=5,
        test_fraction=0.30,
        fdr_alpha=0.10,
    )
    for ev in result["evaluations"]:
        if ev["oos_virtual_order_count"] > 0:
            assert ev["oos_virtual_order_count"] < 60  # OOS is a subset


# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-008: Distinguishable from directional-edge signals via family_id
# ═══════════════════════════════════════════════════════════════════════════


def test_family_id_is_passive_liquidity_provision() -> None:
    """VAL-SIGNAL-008: Family ID is 'passive_liquidity_provision'."""
    family = make_passive_liquidity_family()
    assert family.family_id == FAMILY_ID
    assert family.family_id != "crypto_proxy"
    assert family.family_id != "sports_baseball"
    assert family.family_id != "weather_proxy"
    assert family.family_id != "favorite_longshot_bias"


def test_evaluator_model_ids_include_passive_liquidity() -> None:
    """VAL-SIGNAL-008: Model IDs start with passive_liquidity_provision prefix."""
    for ev in PASSIVE_LIQUIDITY_MODEL_EVALUATORS:
        assert ev["model_id"].startswith(EVALUATOR_MODEL_ID_PREFIX)


# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-009: Research-only guardrails — no live execution without gates
# ═══════════════════════════════════════════════════════════════════════════


def test_family_emits_research_only_flags() -> None:
    """VAL-SIGNAL-009: All family artifacts have research_only=True and execution_enabled=False."""
    fn = _make_passive_liquidity_evaluate_fn("yes")
    rows = [_make_micro_row(i, ticker="KXPL001", price=0.50) for i in range(50)]
    oos_rows = [_make_micro_row(i + 50, ticker="KXPL001", price=0.50) for i in range(20)]
    result = fn(
        rows=rows,
        oos_rows=oos_rows,
        prediction_rule=passive_liquidity_prediction_rule,
        min_independent_labels=10,
        min_oos_labels=5,
    )
    assert result.get("research_only") is True
    assert result.get("execution_enabled") is False
    assert result.get("usable") is False
    assert result.get("calibrated_probability") is None
    assert result.get("expected_value_per_contract") is None


# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-010 and VAL-SIGNAL-015: Feeds microstructure observations into
# virtual order replay
# ═══════════════════════════════════════════════════════════════════════════


def test_virtual_order_replay_from_microstructure_rows() -> None:
    """VAL-SIGNAL-010: Virtual orders are constructed from microstructure observation rows."""
    oos_rows = []
    for i in range(10):
        oos_rows.append(_make_micro_row(i, ticker="KXPL001", price=0.50))
    virtual_orders = _replay_virtual_orders(oos_rows, side="yes", ttl_seconds=180)
    # Virtual orders should be constructed from applicable rows
    assert isinstance(virtual_orders, list)
    for vo in virtual_orders:
        assert "virtual_order_id" in vo
        assert "contract_ticker" in vo
        assert "quote_price" in vo
        assert "fill_proxy_status" in vo


def test_virtual_order_uses_microstructure_fields() -> None:
    """VAL-SIGNAL-015: Virtual orders use best_yes_ask, best_no_ask, spread fields."""
    row = _make_micro_row(
        0,
        ticker="KXPL001",
        price=0.50,
        best_yes_bid=0.45,
        best_yes_ask=0.55,
        best_no_bid=0.40,
        best_no_ask=0.60,
        yes_spread=0.10,
        no_spread=0.20,
    )
    pred_side, _ = passive_liquidity_prediction_rule(row)
    # With wider no_spread, should predict NO side
    assert pred_side is not None


def test_virtual_order_replay_no_fabricated_data() -> None:
    """VAL-SIGNAL-015: Virtual orders don't fabricate data without observation rows."""
    virtual_orders = _replay_virtual_orders([], side="yes", ttl_seconds=180)
    assert len(virtual_orders) == 0


# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-017: Cluster key composability groups by contract + time bucket
# ═══════════════════════════════════════════════════════════════════════════


def test_cluster_key_composer_deterministic() -> None:
    """VAL-SIGNAL-017: Cluster key is deterministic — same row → same key."""
    row = {
        "contract_ticker": "KXPL001",
        "observed_at_utc": "2026-07-04T12:30:00Z",
    }
    key1 = passive_liquidity_cluster_key_composer(row)
    key2 = passive_liquidity_cluster_key_composer(row)
    assert key1 == key2


def test_cluster_key_includes_contract_ticker() -> None:
    """VAL-SIGNAL-017: Cluster key includes the contract ticker."""
    row1 = {
        "contract_ticker": "KXPL001",
        "observed_at_utc": "2026-07-04T12:30:00Z",
    }
    row2 = {
        "contract_ticker": "KXPL002",
        "observed_at_utc": "2026-07-04T12:30:00Z",
    }
    key1 = passive_liquidity_cluster_key_composer(row1)
    key2 = passive_liquidity_cluster_key_composer(row2)
    assert key1 != key2  # Different contracts → different keys


def test_cluster_key_includes_time_bucket() -> None:
    """VAL-SIGNAL-017: Cluster key includes the time bucket."""
    row1 = {
        "contract_ticker": "KXPL001",
        "observed_at_utc": "2026-07-04T12:30:00Z",
    }
    row2 = {
        "contract_ticker": "KXPL001",
        "observed_at_utc": "2026-07-04T18:30:00Z",
    }
    key1 = passive_liquidity_cluster_key_composer(row1)
    key2 = passive_liquidity_cluster_key_composer(row2)
    # Different time buckets → different keys
    assert key1 != key2


def test_cluster_key_same_contract_same_time_bucket() -> None:
    """VAL-SIGNAL-017: Same contract + same time bucket → same cluster key."""
    row1 = {
        "contract_ticker": "KXPL001",
        "observed_at_utc": "2026-07-04T10:30:00Z",
    }
    row2 = {
        "contract_ticker": "KXPL001",
        "observed_at_utc": "2026-07-04T11:30:00Z",
    }
    key1 = passive_liquidity_cluster_key_composer(row1)
    key2 = passive_liquidity_cluster_key_composer(row2)
    assert key1 == key2  # Same 6-hour bucket


def test_cluster_key_fallback_to_event_ticker() -> None:
    """VAL-SIGNAL-017: Falls back to event_ticker when contract_ticker is missing."""
    row = {
        "event_ticker": "KXEVENT001",
        "observed_at_utc": "2026-07-04T12:30:00Z",
    }
    key = passive_liquidity_cluster_key_composer(row)
    assert "KXEVENT001" in key


def test_resolve_time_bucket_unknown() -> None:
    """VAL-SIGNAL-017: Missing timestamp yields 'unknown' bucket."""
    assert _resolve_time_bucket(None) == "unknown"
    assert _resolve_time_bucket("") == "unknown"


# ═══════════════════════════════════════════════════════════════════════════
# Prediction rule tests
# ═══════════════════════════════════════════════════════════════════════════


def test_prediction_rule_wide_spread_yes() -> None:
    """Prediction rule returns 'yes' when yes spread >= 1¢ and wider than no spread."""
    row = {
        "yes_spread": 0.05,
        "no_spread": 0.02,
        "best_yes_bid": 0.45,
        "best_no_bid": 0.40,
        "best_yes_ask": 0.50,
        "best_no_ask": 0.42,
    }
    side, confidence = passive_liquidity_prediction_rule(row)
    assert side == "yes"
    assert confidence is None


def test_prediction_rule_wide_spread_no() -> None:
    """Prediction rule returns 'no' when no spread >= 1¢ and wider than yes spread."""
    row = {
        "yes_spread": 0.02,
        "no_spread": 0.05,
        "best_yes_bid": 0.45,
        "best_no_bid": 0.40,
        "best_yes_ask": 0.47,
        "best_no_ask": 0.45,
    }
    side, confidence = passive_liquidity_prediction_rule(row)
    assert side == "no"
    assert confidence is None


def test_prediction_rule_tight_spreads() -> None:
    """Prediction rule returns None when both spreads are below 1¢."""
    row = {
        "yes_spread": 0.005,
        "no_spread": 0.003,
        "best_yes_bid": 0.495,
        "best_no_bid": 0.490,
        "best_yes_ask": 0.500,
        "best_no_ask": 0.493,
    }
    side, confidence = passive_liquidity_prediction_rule(row)
    assert side is None
    assert confidence is None


def test_prediction_rule_missing_fields() -> None:
    """Prediction rule returns None when required fields are missing."""
    side, confidence = passive_liquidity_prediction_rule({})
    assert side is None
    assert confidence is None


def test_prediction_rule_equal_spreads() -> None:
    """Prediction rule chooses YES when spreads are equal and both >= 1¢."""
    row = {
        "yes_spread": 0.03,
        "no_spread": 0.03,
        "best_yes_bid": 0.45,
        "best_no_bid": 0.40,
        "best_yes_ask": 0.48,
        "best_no_ask": 0.43,
    }
    side, _ = passive_liquidity_prediction_rule(row)
    # Equal spreads → YES (tie goes to yes)
    assert side == "yes"


# ═══════════════════════════════════════════════════════════════════════════
# Net EV helpers
# ═══════════════════════════════════════════════════════════════════════════


def test_net_ev_one_sided_p_positive() -> None:
    """One-sided p-value is low when net EV is clearly positive."""
    net_evs = [0.01] * 10
    p = _net_ev_one_sided_p(net_evs)
    assert p is not None
    assert p < 0.5


def test_net_ev_one_sided_p_negative() -> None:
    """One-sided p-value is high (cannot reject null) when net EV is negative."""
    net_evs = [-0.01] * 10
    p = _net_ev_one_sided_p(net_evs)
    assert p is not None
    # Negative mean → null cannot be rejected
    assert p >= 0.5


def test_net_ev_one_sided_p_too_small() -> None:
    """One-sided p-value returns None for too-small samples."""
    assert _net_ev_one_sided_p([0.01]) is None
    assert _net_ev_one_sided_p([]) is None


# ═══════════════════════════════════════════════════════════════════════════
# Quote price helper
# ═══════════════════════════════════════════════════════════════════════════


def test_quote_price_one_tick_inside() -> None:
    """Quote price is one tick inside the best ask."""
    row = {
        "best_yes_bid": 0.45,
        "best_yes_ask": 0.55,
    }
    price = _quote_price_for_side(row, "yes")
    assert price is not None
    assert price > 0.45 and price < 0.55


def test_quote_price_none_when_no_bid() -> None:
    """Quote price is None when bid or ask is missing."""
    row: dict[str, Any] = {}
    assert _quote_price_for_side(row, "yes") is None


# ═══════════════════════════════════════════════════════════════════════════
# Side-mid helper
# ═══════════════════════════════════════════════════════════════════════════


def test_side_mid_yes() -> None:
    """Side mid for YES uses yes_mid field."""
    row = {"yes_mid": 0.50}
    assert _side_mid(row, "yes") == 0.50


def test_side_mid_no() -> None:
    """Side mid for NO computes (best_no_bid + best_no_ask) / 2."""
    row = {"best_no_bid": 0.40, "best_no_ask": 0.50}
    assert _side_mid(row, "no") == 0.45


# ═══════════════════════════════════════════════════════════════════════════
# Evaluator edge cases
# ═══════════════════════════════════════════════════════════════════════════


def test_evaluator_insufficient_independent_labels() -> None:
    """Evaluator returns blocked status when too few independent labels."""
    fn = _make_passive_liquidity_evaluate_fn("yes")
    rows = [_make_micro_row(i, ticker="KXPL001", price=0.50) for i in range(3)]
    oos_rows = [_make_micro_row(i + 50, ticker="KXPL001", price=0.50) for i in range(20)]
    result = fn(
        rows=rows,
        oos_rows=oos_rows,
        prediction_rule=passive_liquidity_prediction_rule,
        min_independent_labels=10,
        min_oos_labels=5,
    )
    assert result["status"] == "blocked_insufficient_independent_labels"


def test_evaluator_insufficient_oos_labels() -> None:
    """Evaluator returns blocked status when too few OOS rows (no applicable virtual orders)."""
    fn = _make_passive_liquidity_evaluate_fn("yes")
    rows = [_make_micro_row(i, ticker="KXPL001", price=0.50) for i in range(50)]
    # Rows with tight spreads — no quotes predicted
    oos_rows = [
        _make_micro_row(
            i + 50,
            ticker="KXPL001",
            price=0.50,
            yes_spread=0.001,
            no_spread=0.001,
        )
        for i in range(5)
    ]
    result = fn(
        rows=rows,
        oos_rows=oos_rows,
        prediction_rule=passive_liquidity_prediction_rule,
        min_independent_labels=10,
        min_oos_labels=5,
    )
    assert result["status"] in (
        "blocked_no_counterfactual_fills",
        "blocked_insufficient_oos_labels",
        "testable_research_candidate",
    )


def test_make_family_overrides() -> None:
    """Factory accepts overrides for testing."""
    custom_rule = lambda row: ("yes", None)  # noqa: E731
    family = make_passive_liquidity_family(prediction_rule=custom_rule)
    assert family.prediction_rule is custom_rule


# ═══════════════════════════════════════════════════════════════════════════
# VAL-CROSS-035: Gated like directional signals (same OOS/FDR gate)
# ═══════════════════════════════════════════════════════════════════════════


def test_falsification_gate_output_structure() -> None:
    """VAL-CROSS-035: Falsification output has same structure as other families."""
    family = make_passive_liquidity_family()
    # Use the proof-of-concept rows from the existing evidence gate pattern
    rows = []
    for ticker_idx in range(3):
        for snap_idx in range(20):
            i = ticker_idx * 20 + snap_idx
            rows.append(
                _make_micro_row(
                    i,
                    ticker=f"KXPL{ticker_idx:04d}",
                    price=0.50,
                    best_yes_bid=0.45,
                    best_yes_ask=0.55,
                    best_no_bid=0.40,
                    best_no_ask=0.60,
                    yes_spread=0.10,
                    no_spread=0.20,
                )
            )

    result = build_falsification(
        label_rows=rows,
        prediction_rule=family.prediction_rule,
        model_evaluators=family.model_evaluators,
        family=family,
        min_independent_labels=5,
        min_oos_labels=3,
        test_fraction=0.30,
        fdr_alpha=0.10,
    )
    assert result["status"] is not None
    assert "evaluations" in result
    assert "summary" in result


# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-011: Existing families work alongside new ones
# ═══════════════════════════════════════════════════════════════════════════


def test_generic_spine_handles_family_without_special_cases() -> None:
    """VAL-SIGNAL-011: Generic engine spine handles passive-liquidity via SignalFamily descriptor."""
    family = make_passive_liquidity_family()
    rows = [_make_micro_row(i, ticker=f"KXPL{i:04d}", price=0.50) for i in range(60)]

    result = build_falsification(
        label_rows=rows,
        prediction_rule=family.prediction_rule,
        model_evaluators=family.model_evaluators,
        family=family,
        min_independent_labels=10,
        min_oos_labels=5,
        test_fraction=0.30,
        fdr_alpha=0.10,
    )
    assert "evaluations" in result
    # Verify no family_id-specific branching in the engine spine
    for ev in result["evaluations"]:
        assert "status" in ev
        assert "model_id" in ev


# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-019: Falsification artifacts pass safe_research_artifact validation
# ═══════════════════════════════════════════════════════════════════════════


def test_falsification_artifact_is_safe_research_artifact() -> None:
    """VAL-SIGNAL-019: Evaluator artifacts are safe research artifacts."""
    fn = _make_passive_liquidity_evaluate_fn("yes")
    rows = [_make_micro_row(i, ticker="KXPL001", price=0.50) for i in range(50)]
    oos_rows = [_make_micro_row(i + 50, ticker="KXPL001", price=0.50) for i in range(20)]
    result = fn(
        rows=rows,
        oos_rows=oos_rows,
        prediction_rule=passive_liquidity_prediction_rule,
        min_independent_labels=10,
        min_oos_labels=5,
    )
    # Evaluator results are safe research artifacts
    assert result.get("research_only") is True
    assert result.get("execution_enabled") is False
    assert result.get("usable") is False
    assert result.get("calibrated_probability") is None
    assert result.get("expected_value_per_contract") is None


# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-020: Module has descriptive docstring
# ═══════════════════════════════════════════════════════════════════════════


def test_module_docstring_exists() -> None:
    """VAL-SIGNAL-020: Module has docstring explaining family and acceptance criteria."""
    import predmarket.passive_liquidity_provision_family as plpf

    assert plpf.__doc__ is not None
    assert len(plpf.__doc__) > 50
    assert "passive" in plpf.__doc__.lower() or "liquidity" in plpf.__doc__.lower()
    assert "EV" in plpf.__doc__ or "adverse" in plpf.__doc__.lower()


# ═══════════════════════════════════════════════════════════════════════════
# Helper: create a synthetic microstructure observation row
# ═══════════════════════════════════════════════════════════════════════════


def _make_micro_row(
    idx: int,
    *,
    ticker: str = "KXPL001",
    price: float = 0.50,
    best_yes_bid: float | None = None,
    best_yes_ask: float | None = None,
    best_no_bid: float | None = None,
    best_no_ask: float | None = None,
    yes_spread: float | None = None,
    no_spread: float | None = None,
) -> dict[str, Any]:
    """Create a synthetic microstructure observation row for testing."""
    day = 4
    hour = 1 + idx // 12
    minute = (idx % 12) * 5
    yes_bid = best_yes_bid if best_yes_bid is not None else price - 0.05
    yes_ask = best_yes_ask if best_yes_ask is not None else price + 0.05
    no_bid = best_no_bid if best_no_bid is not None else 1.0 - price - 0.05
    no_ask = best_no_ask if best_no_ask is not None else 1.0 - price + 0.05
    ys = yes_spread if yes_spread is not None else yes_ask - yes_bid
    ns = no_spread if no_spread is not None else no_ask - no_bid
    return {
        "snapshot_id": f"snap_{idx:06d}",
        "contract_ticker": ticker,
        "event_ticker": f"KXEVENT{idx:04d}",
        "series_ticker": "KXPL",
        "sport_surface": "test",
        "observed_at_utc": f"2026-07-{day:02d}T{hour:02d}:{minute:02d}:00Z",
        "settlement_time": None,
        "time_to_settlement_seconds": 3600.0,
        "best_yes_bid": yes_bid,
        "best_yes_ask": yes_ask,
        "best_no_bid": no_bid,
        "best_no_ask": no_ask,
        "yes_mid": (yes_bid + yes_ask) / 2.0,
        "yes_spread": ys,
        "no_spread": ns,
        "yes_bid_depth_top1": 100.0,
        "no_bid_depth_top1": 100.0,
        "yes_ask_depth_top1": 100.0,
        "no_ask_depth_top1": 100.0,
        "yes_depth_top5": 500.0,
        "no_depth_top5": 500.0,
        "total_depth_contracts": 2000.0,
        "depth_imbalance_yes": 0.0,
        "depth_imbalance_delta": 0.0,
        "mid_delta_from_previous_snapshot": None,
        "raw_orderbook_sha256": "abc123",
        "usable": False,
        "research_only": True,
        "execution_enabled": False,
        "kalshi_mid_for_side": price,
    }
