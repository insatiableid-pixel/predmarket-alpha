from __future__ import annotations

from predmarket.kalshi_execution_cost import (
    INDEX_TAKER_FEE_RATE,
    kalshi_trade_fee,
    normalize_kalshi_execution_cost,
    resolve_fee_rate,
)


def test_official_general_taker_fee_rounds_up_to_centicent() -> None:
    assert kalshi_trade_fee(price=0.90) == 0.0063
    assert kalshi_trade_fee(price=0.50) == 0.0175


def test_ticket_payout_multiple_becomes_gross_price_plus_official_fee() -> None:
    cost = normalize_kalshi_execution_cost(
        display_price=0.89,
        executable_price=0.89,
        executable_price_source="screen_price",
        gross_payout_multiple=1.11,
    )

    gross = 1.0 / 1.11
    fee = kalshi_trade_fee(price=gross)
    assert abs(cost.gross_execution_cost - gross) < 1e-12
    assert cost.fee_estimate == fee
    assert cost.fee_source == "kalshi_official_taker_fee_estimate"
    assert abs(cost.all_in_cost - (gross + fee)) < 1e-12
    assert cost.cost_basis_source == "kalshi_payout_multiple_plus_fee_estimate"
    assert cost.gate_status == "pass"


def test_fee_inclusive_payout_multiple_is_not_charged_twice() -> None:
    cost = normalize_kalshi_execution_cost(
        display_price=0.89,
        executable_price=0.89,
        executable_price_source="screen_price",
        fee_inclusive_payout_multiple=1.11,
    )

    assert abs(cost.all_in_cost - (1.0 / 1.11)) < 1e-12
    assert cost.fee_estimate is None
    assert cost.fee_source == "included_in_fee_inclusive_payout_multiple"
    assert cost.cost_basis_source == "fee_inclusive_payout_multiple"


def test_explicit_all_in_cost_overrides_other_cost_sources() -> None:
    cost = normalize_kalshi_execution_cost(
        display_price=0.89,
        executable_price=0.89,
        executable_price_source="screen_price",
        explicit_all_in_cost=0.92,
        fee_inclusive_payout_multiple=1.11,
        gross_payout_multiple=1.12,
    )

    assert cost.all_in_cost == 0.92
    assert cost.break_even_probability == 0.92
    assert cost.cost_basis_source == "explicit_all_in_cost"
    assert cost.fee_source == "included_in_explicit_all_in_cost"


def test_executable_price_fallback_adds_official_fee_and_slippage() -> None:
    cost = normalize_kalshi_execution_cost(
        display_price=0.71,
        executable_price=0.71,
        executable_price_source="kalshi_ask",
        slippage_buffer=0.005,
    )

    fee = kalshi_trade_fee(price=0.71)
    assert cost.fee_estimate == fee
    assert abs(cost.all_in_cost - (0.71 + fee + 0.005)) < 1e-12
    assert cost.cost_basis_source == "kalshi_ask"


def test_index_fee_rate_can_be_inferred_from_ticker() -> None:
    assert resolve_fee_rate(fee_mode="taker", ticker="INXD-26JUL01-T5000", fee_rate_override=None) == INDEX_TAKER_FEE_RATE
    assert resolve_fee_rate(fee_mode="taker", ticker="NASDAQ100D-26JUL01-T20000", fee_rate_override=None) == INDEX_TAKER_FEE_RATE


def test_missing_cost_basis_blocks_normalizer() -> None:
    cost = normalize_kalshi_execution_cost(
        display_price=None,
        executable_price=None,
        executable_price_source="missing",
    )

    assert cost.all_in_cost is None
    assert cost.gate_status == "blocked"
    assert "execution cost basis is missing" in cost.gate_reasons
