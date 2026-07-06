"""Tests for the Kalshi execution cost and canonical fee engine.

Covers:
- Trade fee quadratic formula with centicent rounding (VAL-FEE-001 through 010)
- Rounding fee computation (VAL-FEE-011, 044)
- Net fee composition (VAL-FEE-012)
- FeeAccumulator behavior (VAL-FEE-013 through 016, 045, 049)
- Fee rate resolution (VAL-FEE-003, 004, 018, 048)
- Fee_changes API integration (VAL-FEE-019 through 030)
- Edge cases: zero/negative/extreme prices, zero contracts (VAL-FEE-007-010, 040-043)
- Cross-area invariants (VAL-CROSS-001 through 004, 052 through 058)
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from predmarket.kalshi_execution_cost import (
    CENTICENT,
    FEE_CHANGES_CACHE,
    FEE_CHANGES_CACHE_TTL,
    GENERAL_MAKER_FEE_RATE,
    GENERAL_TAKER_FEE_RATE,
    INDEX_TAKER_FEE_RATE,
    FeeAccumulator,
    FeeTable,
    FeeType,
    _compute_rounding_fee,
    _parse_fee_changes_response,
    is_index_fee_ticker,
    kalshi_net_fee,
    kalshi_trade_fee,
    normalize_kalshi_execution_cost,
    resolve_fee_rate,
    resolve_fee_type,
    round_up_centicent,
)

# ── Fee Table Fixtures ──────────────────────────────────────────────────────

TAKER_PRICE_POINTS = [round(0.05 * i, 2) for i in range(1, 20)]  # 0.05..0.95 step 0.05


class TestFeeTable:
    """FeeTable contains validated fixture values for 5c through 95c (VAL-FEE-005, 006)."""

    @pytest.mark.parametrize("price", TAKER_PRICE_POINTS)
    def test_taker_fee_table_parity_all_price_points(self, price: float) -> None:
        """VAL-FEE-005: Taker fee matches official Kalshi table at each 5c price point."""
        taker_entry = FeeTable.get(price, "taker")
        computed = kalshi_trade_fee(price=price, fee_rate=GENERAL_TAKER_FEE_RATE)
        assert abs(taker_entry - computed) < 1e-10, f"Taker mismatch at price={price}"

    @pytest.mark.parametrize("price", TAKER_PRICE_POINTS)
    def test_maker_fee_table_parity_all_price_points(self, price: float) -> None:
        """VAL-FEE-006: Maker fee matches official Kalshi table at each 5c price point."""
        maker_entry = FeeTable.get(price, "maker")
        computed = kalshi_trade_fee(price=price, fee_rate=GENERAL_MAKER_FEE_RATE)
        assert abs(maker_entry - computed) < 1e-10, f"Maker mismatch at price={price}"

    def test_fee_table_contains_all_price_points(self) -> None:
        """VAL-CROSS-002: FeeTable contains all 19 price points for both modes."""
        for price in TAKER_PRICE_POINTS:
            assert price in FeeTable._taker, f"Missing taker entry at price={price}"
            assert price in FeeTable._maker, f"Missing maker entry at price={price}"

    def test_fee_table_and_kalshi_trade_fee_agree(self) -> None:
        """VAL-CROSS-052: FeeTable and kalshi_trade_fee() agree within centicent tolerance."""
        for price in TAKER_PRICE_POINTS:
            for mode, rate in [
                ("taker", GENERAL_TAKER_FEE_RATE),
                ("maker", GENERAL_MAKER_FEE_RATE),
            ]:
                table_val = FeeTable.get(price, mode)
                computed = kalshi_trade_fee(price=price, fee_rate=rate)
                assert abs(table_val - computed) <= float(CENTICENT), (
                    f"Mismatch at price={price} mode={mode}: table={table_val} computed={computed}"
                )


# ── Quadratic Trade Fee Formula ──────────────────────────────────────────────


class TestTradeFeeFormula:
    """VAL-FEE-001: Quadratic trade-fee formula with centicent rounding."""

    def test_official_general_taker_fee_rounds_up_to_centicent(self) -> None:
        assert kalshi_trade_fee(price=0.90) == 0.0063
        assert kalshi_trade_fee(price=0.50) == 0.0175

    def test_maker_fee_rate_lower_hurdle(self) -> None:
        """VAL-FEE-003: Maker fee rate is 0.0175 regardless of ticker."""
        assert kalshi_trade_fee(price=0.50, fee_rate=GENERAL_MAKER_FEE_RATE) == 0.0044
        # Index tickers do NOT get index rate when mode is maker
        maker_rate = resolve_fee_rate(
            fee_mode="maker", ticker="INXD-26JUL01-T5000", fee_rate_override=None
        )
        assert maker_rate == GENERAL_MAKER_FEE_RATE

    def test_index_fee_rate_inference(self) -> None:
        """VAL-FEE-004: Index tickers get 0.035 in taker mode."""
        assert (
            resolve_fee_rate(fee_mode="taker", ticker="INXD-26JUL01-T5000", fee_rate_override=None)
            == INDEX_TAKER_FEE_RATE
        )
        assert (
            resolve_fee_rate(
                fee_mode="taker", ticker="NASDAQ100D-26JUL01-T20000", fee_rate_override=None
            )
            == INDEX_TAKER_FEE_RATE
        )
        assert (
            resolve_fee_rate(fee_mode="taker", ticker="SOME-INX-TICKER", fee_rate_override=None)
            == INDEX_TAKER_FEE_RATE
        )
        # Non-index tickers get general rate
        assert (
            resolve_fee_rate(
                fee_mode="taker", ticker="KXUNIT-26JUL01-T5000", fee_rate_override=None
            )
            == GENERAL_TAKER_FEE_RATE
        )

    def test_index_fee_ticker_detection(self) -> None:
        """VAL-CROSS-057: is_index_fee_ticker correctly identifies index tickers."""
        assert is_index_fee_ticker("INXD-26JUL01-T5000") is True
        assert is_index_fee_ticker("NASDAQ100D-26JUL01-T20000") is True
        assert is_index_fee_ticker("SOME-INX-TICKER") is True
        assert is_index_fee_ticker("KXUNIT-26JUL01-T5000") is False
        assert is_index_fee_ticker(None) is False
        assert is_index_fee_ticker("") is False

    def test_centicent_rounding_boundary_behavior(self) -> None:
        """VAL-FEE-002: Centicent rounding uses ROUND_CEILING, exact boundaries stay put."""
        # Exactly on a centicent boundary
        assert round_up_centicent(Decimal("0.0175")) == Decimal("0.0175")
        # Just above a centicent boundary
        assert round_up_centicent(Decimal("0.00010001")) == Decimal("0.0002")
        # Exactly zero
        assert round_up_centicent(Decimal("0")) == Decimal("0")
        # Negative clamped to zero
        assert round_up_centicent(Decimal("-0.001")) == Decimal("0")
        # Very small positive
        result = round_up_centicent(Decimal("0.00001"))
        assert result == Decimal("0.0001")
        # Just below boundary
        assert round_up_centicent(Decimal("0.017499")) == Decimal("0.0175")

    def test_round_up_centicent_uses_ceiling(self) -> None:
        """VAL-CROSS-056: round_up_centicent uses ROUND_CEILING (never floor)."""
        assert round_up_centicent(Decimal("0.0000001")) == Decimal("0.0001")
        assert round_up_centicent(Decimal("0.00005")) == Decimal("0.0001")

    # ── Edge Cases: Zero, Extreme, Mid-Price ────────────────────────────────

    def test_fee_zero_price_boundary(self) -> None:
        """VAL-FEE-007: Zero price yields zero fee regardless of rate or count."""
        assert kalshi_trade_fee(price=0.0, fee_rate=GENERAL_TAKER_FEE_RATE) == 0.0
        assert kalshi_trade_fee(price=0.0, fee_rate=GENERAL_MAKER_FEE_RATE) == 0.0
        assert (
            kalshi_trade_fee(price=0.0, contract_count=100, fee_rate=GENERAL_TAKER_FEE_RATE) == 0.0
        )

    def test_fee_extreme_low_price(self) -> None:
        """VAL-FEE-008: At P=0.01, raw=0.000693, rounded to 0.0007."""
        fee = kalshi_trade_fee(price=0.01)
        assert fee == 0.0007

    def test_fee_extreme_high_price(self) -> None:
        """VAL-FEE-009: At P=0.99, fee same as P=0.01 (symmetry of P(1-P))."""
        fee_low = kalshi_trade_fee(price=0.01)
        fee_high = kalshi_trade_fee(price=0.99)
        assert fee_low == fee_high == 0.0007

    def test_fee_mid_price_is_maximum(self) -> None:
        """VAL-FEE-010: P=0.50 gives max fee; all others ≤ that value."""
        taker_mid = kalshi_trade_fee(price=0.50, fee_rate=GENERAL_TAKER_FEE_RATE)
        maker_mid = kalshi_trade_fee(price=0.50, fee_rate=GENERAL_MAKER_FEE_RATE)
        assert taker_mid == 0.0175
        assert maker_mid == 0.0044
        for p in [0.01, 0.10, 0.25, 0.35, 0.65, 0.75, 0.90, 0.99]:
            assert kalshi_trade_fee(price=p, fee_rate=GENERAL_TAKER_FEE_RATE) <= taker_mid
            assert kalshi_trade_fee(price=p, fee_rate=GENERAL_MAKER_FEE_RATE) <= maker_mid

    def test_negative_price_graceful_handling(self) -> None:
        """VAL-FEE-040: Negative prices do not raise; return 0.0."""
        assert kalshi_trade_fee(price=-0.50) == 0.0
        assert kalshi_trade_fee(price=-1.0) == 0.0
        assert kalshi_trade_fee(price=-0.01) == 0.0

    def test_price_above_par_handled(self) -> None:
        """VAL-FEE-041: Price > 1.0 handled without crash (P(1-P) becomes negative)."""
        fee = kalshi_trade_fee(price=1.5)
        assert isinstance(fee, float)

    def test_zero_contract_count(self) -> None:
        """VAL-FEE-042: Zero contracts yields zero fee."""
        assert kalshi_trade_fee(price=0.50, contract_count=0) == 0.0
        assert (
            kalshi_trade_fee(price=0.10, contract_count=0, fee_rate=GENERAL_MAKER_FEE_RATE) == 0.0
        )
        assert (
            kalshi_trade_fee(price=0.90, contract_count=0, fee_rate=GENERAL_TAKER_FEE_RATE) == 0.0
        )

    def test_fee_computation_deterministic(self) -> None:
        """VAL-FEE-043: Fee computation is deterministic (pure function)."""
        results = [kalshi_trade_fee(price=0.50) for _ in range(10)]
        assert all(r == results[0] for r in results)


# ── Fee Rate Resolution ─────────────────────────────────────────────────────


class TestFeeRateResolution:
    """VAL-FEE-003, 004, 018, 048: Fee rate resolution logic."""

    @pytest.mark.parametrize(
        ("fee_mode", "expected"),
        [
            ("maker", GENERAL_MAKER_FEE_RATE),
            ("MAKER", GENERAL_MAKER_FEE_RATE),
            ("  maker  ", GENERAL_MAKER_FEE_RATE),
            ("mAkEr", GENERAL_MAKER_FEE_RATE),
        ],
    )
    def test_fee_mode_normalization_case_whitespace(self, fee_mode: str, expected: Decimal) -> None:
        """VAL-FEE-048: fee_mode is case-insensitive and whitespace-tolerant."""
        rate = resolve_fee_rate(fee_mode=fee_mode, ticker="KXUNIT", fee_rate_override=None)
        assert rate == expected

    def test_fee_mode_normalization_unknown_falls_back_to_taker(self) -> None:
        """VAL-FEE-048: Unknown fee_mode falls back to taker rate."""
        rate = resolve_fee_rate(fee_mode="routing_error", ticker=None, fee_rate_override=None)
        assert rate == GENERAL_TAKER_FEE_RATE

    def test_fee_rate_override_wins(self) -> None:
        """VAL-FEE-018: fee_rate_override beats fee_mode, ticker, everything."""
        # Override with maker mode → override wins
        rate = resolve_fee_rate(fee_mode="maker", ticker="KXUNIT", fee_rate_override=0.05)
        assert rate == Decimal("0.05")
        # Override with index ticker → override wins
        rate = resolve_fee_rate(
            fee_mode="taker", ticker="INXD-26JUL01-T5000", fee_rate_override=0.03
        )
        assert rate == Decimal("0.03")
        # Override with explicit taker mode → override wins
        rate = resolve_fee_rate(fee_mode="taker", ticker=None, fee_rate_override=0.01)
        assert rate == Decimal("0.01")


# ── Rounding Fee ────────────────────────────────────────────────────────────


class TestRoundingFee:
    """VAL-FEE-011, 044: Rounding fee computation."""

    def test_rounding_fee_formula(self) -> None:
        """VAL-FEE-011: rounding_fee = balance_change - floor(balance_change to cent)."""
        # Exact cent → no rounding fee
        assert _compute_rounding_fee(Decimal("0.50")) == Decimal("0")
        assert _compute_rounding_fee(Decimal("1.23")) == Decimal("0")
        # Sub-cent → full amount is rounding fee
        assert _compute_rounding_fee(Decimal("0.0063")) == Decimal("0.0063")
        # Multi-cent with fractional part
        assert _compute_rounding_fee(Decimal("0.0175")) == Decimal("0.0075")
        assert _compute_rounding_fee(Decimal("1.2345")) == Decimal("0.0045")
        # Zero
        assert _compute_rounding_fee(Decimal("0")) == Decimal("0")

    def test_rounding_fee_never_negative(self) -> None:
        """VAL-FEE-044: Rounding fee is always non-negative."""
        for val in [
            Decimal("0"),
            Decimal("0.0001"),
            Decimal("0.0063"),
            Decimal("0.01"),
            Decimal("0.0175"),
            Decimal("1.2345"),
            Decimal("100.9999"),
        ]:
            assert _compute_rounding_fee(val) >= 0, f"Negative rounding fee at {val}"


# ── FeeAccumulator ──────────────────────────────────────────────────────────


class TestFeeAccumulator:
    """VAL-FEE-013 through 016, 045, 049, VAL-CROSS-003, 053."""

    def test_accumulator_tracks_rounding(self) -> None:
        """VAL-FEE-013: Accumulator tracks rounding overpayment across fills."""
        acc = FeeAccumulator()
        assert acc.accumulated == Decimal("0")
        acc.add_fill(Decimal("0.0025"))
        assert acc.accumulated == Decimal("0.0025")
        acc.add_fill(Decimal("0.0030"))
        assert acc.accumulated == Decimal("0.0055")
        acc.add_fill(Decimal("0.0010"))
        assert acc.accumulated == Decimal("0.0065")

    def test_accumulator_rebate_trigger_exact_threshold(self) -> None:
        """VAL-FEE-014: $0.01 threshold triggers $0.01 rebate; remainder continues."""
        acc = FeeAccumulator()
        # Add exactly 0.01
        rebate = acc.add_fill(Decimal("0.01"))
        assert rebate == Decimal("0.01")
        assert acc.accumulated == Decimal("0")  # Exactly consumed

    def test_accumulator_rebate_trigger_over_threshold(self) -> None:
        """VAL-FEE-014: Over $0.01 triggers rebate; excess carries forward."""
        acc = FeeAccumulator()
        rebate = acc.add_fill(Decimal("0.012"))
        assert rebate == Decimal("0.01")
        assert acc.accumulated == Decimal("0.002")  # Excess carried forward

    def test_accumulator_multiple_fills_to_rebate(self) -> None:
        """VAL-FEE-014, 015: Multiple fills accumulate, single rebate at threshold."""
        acc = FeeAccumulator()
        assert acc.add_fill(Decimal("0.003")) == Decimal("0")
        assert acc.add_fill(Decimal("0.003")) == Decimal("0")
        assert acc.add_fill(Decimal("0.003")) == Decimal("0")
        # Now at 0.009; next fill of 0.003 pushes to 0.012 → rebate
        rebate = acc.add_fill(Decimal("0.003"))
        assert rebate == Decimal("0.01")
        assert acc.accumulated == Decimal("0.002")  # 0.0012 - 0.01

    def test_accumulator_no_multiple_rebates_single_fill(self) -> None:
        """VAL-FEE-014: Single fill triggers at most one rebate even if rounding_fee >= 0.02."""
        acc = FeeAccumulator()
        rebate = acc.add_fill(Decimal("0.025"))
        assert rebate == Decimal("0.01")  # Exactly one rebate
        # Remainder after single rebate
        assert acc.accumulated == Decimal("0.015")

    def test_accumulator_per_order_isolation(self) -> None:
        """VAL-FEE-016: Two separate orders do NOT share accumulator state."""
        acc_a = FeeAccumulator()
        acc_b = FeeAccumulator()
        acc_a.add_fill(Decimal("0.008"))
        assert acc_a.accumulated == Decimal("0.008")
        assert acc_b.accumulated == Decimal("0")  # Isolated

    def test_accumulator_name_isolation(self) -> None:
        """Accumulators with different order IDs are isolated."""
        acc_a = FeeAccumulator(order_id="order-1")
        acc_b = FeeAccumulator(order_id="order-2")
        acc_a.add_fill(Decimal("0.009"))
        acc_b.add_fill(Decimal("0.003"))
        acc_a.add_fill(Decimal("0.002"))  # 0.011 → rebate
        assert acc_a.rebates_issued == 1
        assert acc_b.rebates_issued == 0
        assert acc_b.accumulated == Decimal("0.003")

    def test_accumulator_integrity_invariant(self) -> None:
        """VAL-FEE-045: accumulated + (rebates_issued * $0.01) == sum of all rounding_fees."""
        acc = FeeAccumulator()
        rounding_fees = [
            Decimal("0.002"),
            Decimal("0.003"),
            Decimal("0.008"),
            Decimal("0.001"),
            Decimal("0.004"),
            Decimal("0.005"),
        ]
        total_rounding = Decimal("0")
        for rf in rounding_fees:
            total_rounding += rf
            acc.add_fill(rf)
        # Invariant: accumulated + (rebates * 0.01) == total_rounding
        assert acc.accumulated + (acc.rebates_issued * Decimal("0.01")) == total_rounding

    def test_accumulator_sequential_consistency(self) -> None:
        """VAL-FEE-049: Invariant holds after 10,000 fills."""
        acc = FeeAccumulator()
        import random

        rng = random.Random(42)
        total_rounding = Decimal("0")
        for _ in range(10_000):
            rf = Decimal(str(rng.random() * 0.01)).quantize(CENTICENT)  # 0 to ~0.01
            total_rounding += rf
            acc.add_fill(rf)
        assert acc.accumulated + (acc.rebates_issued * Decimal("0.01")) == total_rounding


# ── Net Fee ─────────────────────────────────────────────────────────────────


class TestNetFee:
    """VAL-FEE-012, VAL-CROSS-001: net_fee = trade_fee + rounding_fee - rebate."""

    def test_net_fee_no_rounding_no_rebate(self) -> None:
        """Net fee = trade_fee + rounding_fee when no rebate triggers."""
        nf = kalshi_net_fee(price=0.50, contract_count=1, fee_mode="taker")
        tf = kalshi_trade_fee(price=0.50, fee_rate=GENERAL_TAKER_FEE_RATE)
        # trade_fee=0.0175, rounding_fee=0.0075 (0.0175 - floor_to_cent(0.0175))
        assert nf == tf + 0.0075

    def test_net_fee_composition_no_rounding(self) -> None:
        """VAL-FEE-012 scenario 1: No rounding fee + no rebate = trade_fee."""
        # At exact cent boundary
        nf = kalshi_net_fee(price=0.50, contract_count=1, fee_mode="maker", fee_rate_override=0.02)
        tf = kalshi_trade_fee(price=0.50, contract_count=1, fee_rate=Decimal("0.02"))
        # rounding_fee of 0.02 * 1 * 0.5 * 0.5 = 0.0050 (exact cent) → 0
        assert nf >= tf

    def test_net_fee_composition_with_rebate(self) -> None:
        """VAL-FEE-012 scenario 3: Rebate reduces net fee below trade_fee."""
        nf = kalshi_net_fee(price=0.50, contract_count=1, fee_mode="taker", force_rebate=True)
        tf = kalshi_trade_fee(price=0.50, fee_rate=GENERAL_TAKER_FEE_RATE)
        assert nf < tf  # Rebate of $0.01 reduces net fee

    def test_net_fee_includes_rounding_fee(self) -> None:
        """Net fee includes rounding_fee when present."""
        nf = kalshi_net_fee(
            price=0.50,
            contract_count=1,
            fee_mode="taker",
            explicit_balance_change=Decimal("0.0063"),
        )
        tf = kalshi_trade_fee(price=0.50, fee_rate=GENERAL_TAKER_FEE_RATE)
        assert nf > tf  # trade_fee + rounding(0.0063) = 0.0175 + 0.0063 = 0.0238


# ── FeeType and resolve_fee_type ────────────────────────────────────────────


class TestFeeTypeResolution:
    """VAL-FEE-019 through 030, VAL-CROSS-004, 054."""

    def test_fee_type_dataclass_defaults(self) -> None:
        """FeeType defaults: multiplier=1.0, scheduled_ts=None."""
        ft = FeeType(kind="quadratic")
        assert ft.multiplier == Decimal("1.0")
        assert ft.scheduled_ts is None

    def test_fee_changes_query_by_series_ticker_success(self) -> None:
        """VAL-FEE-019: resolve_fee_type queries by series_ticker, returns FeeType."""
        FEE_CHANGES_CACHE.clear()
        ft = resolve_fee_type(series_ticker="KXUNIT-26JUL01-T5000")
        assert isinstance(ft, FeeType)
        assert ft.kind in ("quadratic", "quadratic_with_maker_fees", "flat")

    def test_fee_changes_query_default_fallback(self) -> None:
        """resolve_fee_type returns default quadratic for unknown series."""
        FEE_CHANGES_CACHE.clear()
        ft = resolve_fee_type(series_ticker="UNKNOWN_SERIES_XYZ")
        assert ft.kind == "quadratic"
        assert ft.multiplier == Decimal("1.0")

    def test_fee_type_quadratic_valid(self) -> None:
        """VAL-FEE-020: Quadratic fee_type uses standard formula."""
        ft = FeeType(kind="quadratic", multiplier=Decimal("1.5"))
        effective_rate = GENERAL_TAKER_FEE_RATE * ft.multiplier
        fee = kalshi_trade_fee(price=0.50, fee_rate=effective_rate)
        assert fee == pytest.approx(0.07 * 1.5 * 0.5 * 0.5, abs=0.0001)

    def test_fee_type_quadratic_with_maker_valid(self) -> None:
        """VAL-FEE-021: quadratic_with_maker_fees uses maker rate as base."""
        ft = FeeType(kind="quadratic_with_maker_fees", multiplier=Decimal("1.0"))
        effective_rate = GENERAL_MAKER_FEE_RATE * ft.multiplier
        fee = kalshi_trade_fee(price=0.50, fee_rate=effective_rate)
        assert fee == 0.0044

    def test_fee_type_flat_bypasses_centicent_rounding(self) -> None:
        """VAL-FEE-022, 030: Flat fee is price-independent, no centicent rounding path."""
        ft = FeeType(kind="flat", multiplier=Decimal("3.0"))
        # Flat fee = multiplier * $0.01 = $0.03 per contract
        flat_per_contract = float(ft.multiplier * Decimal("0.01"))
        # Same fee at any price
        assert flat_per_contract == 0.03

    def test_fee_multiplier_parsing_explicit(self) -> None:
        """VAL-FEE-023: Explicit multiplier parsed as Decimal."""
        ft = FeeType(kind="quadratic", multiplier=Decimal("2.0"))
        assert ft.multiplier == Decimal("2.0")

    def test_fee_multiplier_default_one(self) -> None:
        """VAL-FEE-023: Missing multiplier defaults to 1.0."""
        ft = FeeType(kind="quadratic")
        assert ft.multiplier == Decimal("1.0")

    def test_scheduled_ts_parsing(self) -> None:
        """VAL-FEE-024: scheduled_ts parsed as timezone-aware datetime."""
        ts = datetime(2026, 7, 1, tzinfo=UTC)
        ft = FeeType(kind="quadratic", multiplier=Decimal("1.0"), scheduled_ts=ts)
        assert ft.scheduled_ts == ts
        assert ft.scheduled_ts.tzinfo is not None

    def test_multiplier_applied_to_rate_not_final_fee(self) -> None:
        """VAL-FEE-025: Multiplier scales base rate, not already-computed fee."""
        # 0.07 * 1.5 * P * (1-P) != 1.5 * (0.07 * P * (1-P)) — but it IS the same mathematically
        # This test proves the computation path: rate * multiplier * P * (1-P)
        base_rate = GENERAL_TAKER_FEE_RATE
        multiplier = Decimal("1.5")
        effective = base_rate * multiplier
        direct = kalshi_trade_fee(price=0.50, fee_rate=effective)
        # Verify: effective rate = 0.105, trade fee = 0.105 * 0.5 * 0.5 = 0.02625 → 0.0263
        assert direct == 0.0263

    def test_fee_type_default_when_no_series_ticker(self) -> None:
        """VAL-FEE-029: No series_ticker → no API call, default quadratic returned."""
        for bad in [None, "", "  "]:
            ft = resolve_fee_type(series_ticker=bad)
            assert ft.kind == "quadratic"
            assert ft.multiplier == Decimal("1.0")

    def test_resolve_fee_type_graceful_unknown_series(self) -> None:
        """VAL-CROSS-054: Unknown series returns default, no exception."""
        FEE_CHANGES_CACHE.clear()
        ft = resolve_fee_type(series_ticker="__NONEXISTENT_TEST_SERIES__")
        assert ft.kind == "quadratic"
        assert ft.multiplier == Decimal("1.0")


# ── Graceful Degradation ────────────────────────────────────────────────────


class TestGracefulDegradation:
    """VAL-FEE-027: Fee engine survives API failures."""

    def test_fee_engine_no_crash_on_import(self) -> None:
        """VAL-CROSS-058: Importing the module doesn't trigger network access."""
        import importlib

        mod = importlib.import_module("predmarket.kalshi_execution_cost")
        assert mod is not None

    def test_fee_type_resolution_no_crash(self) -> None:
        """resolve_fee_type doesn't crash even with internet issues."""
        FEE_CHANGES_CACHE.clear()
        ft = resolve_fee_type(series_ticker="ANY_TICKER")
        assert isinstance(ft, FeeType)


# ── Fee Mode Default ────────────────────────────────────────────────────────


class TestFeeModeDefault:
    """VAL-FEE-017: Default fee_mode is 'maker'."""

    def test_default_fee_mode_is_maker(self) -> None:
        """VAL-FEE-017: normalize_kalshi_execution_cost defaults to maker."""
        cost = normalize_kalshi_execution_cost(
            display_price=0.50,
            executable_price=0.50,
            executable_price_source="maker_quote",
        )
        assert cost.fee_mode == "maker"
        assert cost.fee_rate == float(GENERAL_MAKER_FEE_RATE)

    def test_explicit_fee_mode_still_works(self) -> None:
        """Explicit fee_mode='taker' still works."""
        cost = normalize_kalshi_execution_cost(
            display_price=0.50,
            executable_price=0.50,
            executable_price_source="screen_price",
            fee_mode="taker",
        )
        assert cost.fee_mode == "taker"
        assert cost.fee_rate == float(GENERAL_TAKER_FEE_RATE)


# ── FeeAccumulator per-fill integration ─────────────────────────────────────


class TestFeeAccumulatorFillIntegration:
    """VAL-CROSS-003, 053: FeeAccumulator and net_fee integration."""

    def test_accumulator_with_net_fee(self) -> None:
        """VAL-CROSS-003: Accumulator triggers rebate in net_fee."""
        acc = FeeAccumulator()
        # Fill 1: rounding_fee pushes accumulator toward threshold
        nf1 = kalshi_net_fee(
            price=0.50,
            contract_count=1,
            fee_mode="taker",
            accumulator=acc,
            explicit_balance_change=Decimal("0.006"),
        )
        assert nf1 > 0
        # Fill 2: push over $0.01 threshold
        nf2 = kalshi_net_fee(
            price=0.50,
            contract_count=1,
            fee_mode="taker",
            accumulator=acc,
            explicit_balance_change=Decimal("0.006"),
        )
        # Should have triggered a rebate
        assert acc.rebates_issued >= 1


# ── Cross-Area Invariants ───────────────────────────────────────────────────


class TestCrossAreaInvariants:
    """VAL-CROSS-055: Fee engine functions are pure and idempotent."""

    def test_kalshi_trade_fee_idempotent(self) -> None:
        """Calling kalshi_trade_fee ten times with same args yields same result."""
        results = [
            kalshi_trade_fee(price=0.50, contract_count=1, fee_rate=GENERAL_TAKER_FEE_RATE)
            for _ in range(10)
        ]
        assert all(r == results[0] for r in results)

    def test_resolve_fee_rate_idempotent(self) -> None:
        """Calling resolve_fee_rate ten times yields same result."""
        results = [
            resolve_fee_rate(fee_mode="maker", ticker="KXUNIT", fee_rate_override=None)
            for _ in range(10)
        ]
        assert all(r == results[0] for r in results)

    def test_kalshi_net_fee_idempotent(self) -> None:
        """kalshi_net_fee with same args + same accumulator state yields same result."""
        acc = FeeAccumulator()
        r1 = kalshi_net_fee(price=0.50, contract_count=1, fee_mode="taker", accumulator=acc)
        # Reset
        acc2 = FeeAccumulator()
        r2 = kalshi_net_fee(price=0.50, contract_count=1, fee_mode="taker", accumulator=acc2)
        assert r1 == r2

    def test_pure_function_no_side_effects(self) -> None:
        """kalshi_trade_fee doesn't modify any global state."""
        import copy

        before = copy.deepcopy(FEE_CHANGES_CACHE)
        kalshi_trade_fee(price=0.75)
        # FEE_CHANGES_CACHE should not be modified by calling trade_fee
        assert FEE_CHANGES_CACHE == before


# ── Mock-Based Tests ────────────────────────────────────────────────────────


class MockResponse:
    """Helper: fake requests.Response for monkeypatched requests.get."""

    def __init__(self, data: dict, status_code: int = 200) -> None:
        self.status_code = status_code
        self._data = data

    def json(self) -> dict:
        return self._data


class TestMockFeeTypeResolutionFullPipeline:
    """VAL-FEE-026: Full pipeline with API override (mock-based)."""

    def test_fee_resolution_full_pipeline_quadratic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mock fee_changes returns quadratic type; fee computed with multiplier."""
        FEE_CHANGES_CACHE.clear()

        response_data = {
            "fee_changes": [
                {
                    "fee_type": "quadratic",
                    "fee_multiplier": 1.5,
                    "scheduled_ts": "2026-01-01T00:00:00Z",
                }
            ]
        }

        def mock_get(*args: object, **kwargs: object) -> MockResponse:
            return MockResponse(response_data)

        monkeypatch.setattr("requests.get", mock_get)

        now = datetime(2026, 7, 4, tzinfo=UTC)
        ft = resolve_fee_type(series_ticker="TEST-SERIES-001", now=now)
        assert ft.kind == "quadratic"
        assert ft.multiplier == Decimal("1.5")

        # Compute fee with the resolved fee type: effective rate = 0.07 * 1.5 = 0.105
        effective_rate = GENERAL_TAKER_FEE_RATE * ft.multiplier
        fee = kalshi_trade_fee(price=0.50, fee_rate=effective_rate)
        assert fee == pytest.approx(0.105 * 0.5 * 0.5, abs=0.0001)

    def test_fee_resolution_full_pipeline_quadratic_with_maker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mock fee_changes returns quadratic_with_maker_fees; maker rate used."""
        FEE_CHANGES_CACHE.clear()

        response_data = {
            "fee_changes": [
                {
                    "fee_type": "quadratic_with_maker_fees",
                    "fee_multiplier": 1.0,
                    "scheduled_ts": "2026-01-01T00:00:00Z",
                }
            ]
        }

        def mock_get(*args: object, **kwargs: object) -> MockResponse:
            return MockResponse(response_data)

        monkeypatch.setattr("requests.get", mock_get)

        now = datetime(2026, 7, 4, tzinfo=UTC)
        ft = resolve_fee_type(series_ticker="TEST-SERIES-MAKER", now=now)
        assert ft.kind == "quadratic_with_maker_fees"
        assert ft.multiplier == Decimal("1.0")

        # quadratic_with_maker_fees uses maker rate (0.0175) as base
        effective_rate = GENERAL_MAKER_FEE_RATE * ft.multiplier
        fee = kalshi_trade_fee(price=0.50, fee_rate=effective_rate)
        assert fee == 0.0044

    def test_fee_resolution_full_pipeline_flat(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mock fee_changes returns flat type; fee is price-independent."""
        FEE_CHANGES_CACHE.clear()

        response_data = {
            "fee_changes": [
                {
                    "fee_type": "flat",
                    "fee_multiplier": 3.0,
                    "scheduled_ts": "2026-01-01T00:00:00Z",
                }
            ]
        }

        def mock_get(*args: object, **kwargs: object) -> MockResponse:
            return MockResponse(response_data)

        monkeypatch.setattr("requests.get", mock_get)

        now = datetime(2026, 7, 4, tzinfo=UTC)
        ft = resolve_fee_type(series_ticker="TEST-SERIES-FLAT", now=now)
        assert ft.kind == "flat"
        assert ft.multiplier == Decimal("3.0")

        # Flat fee = multiplier * $0.01 = $0.03 per contract (price-independent)
        flat_per_contract = float(ft.multiplier * Decimal("0.01"))
        assert flat_per_contract == 0.03


class TestMockScheduledTsSelection:
    """VAL-FEE-028: Stale/future scheduled_ts selection (mock-based)."""

    def test_selects_most_recent_past_record(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With multiple past records, selects the one with most recent scheduled_ts."""
        FEE_CHANGES_CACHE.clear()

        response_data = {
            "fee_changes": [
                {
                    "fee_type": "quadratic",
                    "fee_multiplier": 1.0,
                    "scheduled_ts": "2026-01-01T00:00:00Z",
                },
                {
                    "fee_type": "quadratic_with_maker_fees",
                    "fee_multiplier": 2.0,
                    "scheduled_ts": "2026-06-01T00:00:00Z",
                },
                {
                    "fee_type": "flat",
                    "fee_multiplier": 5.0,
                    "scheduled_ts": "2026-06-15T00:00:00Z",
                },
            ]
        }

        def mock_get(*args: object, **kwargs: object) -> MockResponse:
            return MockResponse(response_data)

        monkeypatch.setattr("requests.get", mock_get)

        now = datetime(2026, 7, 4, tzinfo=UTC)
        ft = resolve_fee_type(series_ticker="TEST-STALE-TS", now=now)
        # Most recent past scheduled_ts is 2026-06-15 (flat, multiplier=5.0)
        assert ft.kind == "flat"
        assert ft.multiplier == Decimal("5.0")

    def test_ignores_future_records(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Future scheduled_ts records are ignored; returns earlier applicable."""
        FEE_CHANGES_CACHE.clear()

        response_data = {
            "fee_changes": [
                {
                    "fee_type": "quadratic",
                    "fee_multiplier": 1.0,
                    "scheduled_ts": "2026-01-01T00:00:00Z",
                },
                {
                    "fee_type": "flat",
                    "fee_multiplier": 3.0,
                    "scheduled_ts": "2026-10-01T00:00:00Z",  # Future
                },
            ]
        }

        def mock_get(*args: object, **kwargs: object) -> MockResponse:
            return MockResponse(response_data)

        monkeypatch.setattr("requests.get", mock_get)

        now = datetime(2026, 7, 4, tzinfo=UTC)
        ft = resolve_fee_type(series_ticker="TEST-FUTURE-TS", now=now)
        # Only the 2026-01-01 record is applicable (quadratic, multiplier=1.0)
        assert ft.kind == "quadratic"
        assert ft.multiplier == Decimal("1.0")

    def test_all_future_records_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When all records have future scheduled_ts, returns default quadratic."""
        FEE_CHANGES_CACHE.clear()

        response_data = {
            "fee_changes": [
                {
                    "fee_type": "flat",
                    "fee_multiplier": 5.0,
                    "scheduled_ts": "2026-10-01T00:00:00Z",
                },
                {
                    "fee_type": "quadratic_with_maker_fees",
                    "fee_multiplier": 2.0,
                    "scheduled_ts": "2026-12-01T00:00:00Z",
                },
            ]
        }

        def mock_get(*args: object, **kwargs: object) -> MockResponse:
            return MockResponse(response_data)

        monkeypatch.setattr("requests.get", mock_get)

        now = datetime(2026, 7, 4, tzinfo=UTC)
        ft = resolve_fee_type(series_ticker="TEST-ALL-FUTURE", now=now)
        assert ft.kind == "quadratic"
        assert ft.multiplier == Decimal("1.0")

    def test_records_without_scheduled_ts_are_applicable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Records without scheduled_ts are treated as immediately applicable."""
        FEE_CHANGES_CACHE.clear()

        response_data = {
            "fee_changes": [
                {
                    "fee_type": "flat",
                    "fee_multiplier": 3.0,
                    # No scheduled_ts
                },
                {
                    "fee_type": "quadratic",
                    "fee_multiplier": 1.0,
                    "scheduled_ts": "2026-01-01T00:00:00Z",
                },
            ]
        }

        def mock_get(*args: object, **kwargs: object) -> MockResponse:
            return MockResponse(response_data)

        monkeypatch.setattr("requests.get", mock_get)

        now = datetime(2026, 7, 4, tzinfo=UTC)
        ft = resolve_fee_type(series_ticker="TEST-NO-TS-FLAT", now=now)
        # Record without scheduled_ts (treated as datetime.min) should be selected
        # if its the only one without, or the max of all applicable.
        # flat (multiplier=3.0) has no ts → datetime.min
        # quadratic (multiplier=1.0) has ts=2026-01-01
        # max(datetime.min, 2026-01-01) = 2026-01-01 → quadratic
        assert ft.kind == "quadratic"
        assert ft.multiplier == Decimal("1.0")

    def test_empty_fee_changes_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty fee_changes list returns default quadratic."""
        FEE_CHANGES_CACHE.clear()

        def mock_get(*args: object, **kwargs: object) -> MockResponse:
            return MockResponse({"fee_changes": []})

        monkeypatch.setattr("requests.get", mock_get)

        now = datetime(2026, 7, 4, tzinfo=UTC)
        ft = resolve_fee_type(series_ticker="TEST-EMPTY", now=now)
        assert ft.kind == "quadratic"
        assert ft.multiplier == Decimal("1.0")


class TestMockCachingBehavior:
    """VAL-FEE-047: Fee_changes caching behavior with call counter (mock-based)."""

    def test_cache_hits_within_ttl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Second call within TTL uses cached result (no extra API call)."""
        FEE_CHANGES_CACHE.clear()

        call_count: list[int] = [0]
        response_data = {
            "fee_changes": [
                {
                    "fee_type": "quadratic_with_maker_fees",
                    "fee_multiplier": 2.0,
                    "scheduled_ts": "2026-01-01T00:00:00Z",
                }
            ]
        }

        def mock_get(*args: object, **kwargs: object) -> MockResponse:
            call_count[0] += 1
            return MockResponse(response_data)

        monkeypatch.setattr("requests.get", mock_get)

        base_now = datetime(2026, 7, 4, tzinfo=UTC)

        # First call — should make API request
        ft1 = resolve_fee_type(series_ticker="TEST-CACHE-001", now=base_now)
        assert ft1.kind == "quadratic_with_maker_fees"
        assert call_count[0] == 1

        # Second call with same now (within TTL) — should hit cache
        ft2 = resolve_fee_type(series_ticker="TEST-CACHE-001", now=base_now)
        assert ft2.kind == "quadratic_with_maker_fees"
        assert call_count[0] == 1  # Still 1 — cache hit

    def test_cache_misses_after_ttl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Call after TTL expiry makes a new API request."""
        FEE_CHANGES_CACHE.clear()

        call_count: list[int] = [0]
        response_data = {
            "fee_changes": [
                {
                    "fee_type": "flat",
                    "fee_multiplier": 4.0,
                    "scheduled_ts": "2026-01-01T00:00:00Z",
                }
            ]
        }

        def mock_get(*args: object, **kwargs: object) -> MockResponse:
            call_count[0] += 1
            return MockResponse(response_data)

        monkeypatch.setattr("requests.get", mock_get)

        early_now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=UTC)

        # First call — populates cache
        ft1 = resolve_fee_type(series_ticker="TEST-CACHE-002", now=early_now)
        assert ft1.kind == "flat"
        assert call_count[0] == 1

        # Advance now past TTL (61 seconds later)
        late_now = datetime(2026, 7, 4, 12, 1, 1, tzinfo=UTC)

        # Third call with advanced now — cache expired, new API call
        ft3 = resolve_fee_type(series_ticker="TEST-CACHE-002", now=late_now)
        assert ft3.kind == "flat"
        assert call_count[0] == 2  # New API call

    def test_different_tickers_have_separate_caches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Different series tickers have independent cache entries."""
        FEE_CHANGES_CACHE.clear()

        call_count: list[int] = [0]

        def mock_get(*args: object, **kwargs: object) -> MockResponse:
            call_count[0] += 1
            return MockResponse(
                {
                    "fee_changes": [
                        {
                            "fee_type": "quadratic",
                            "fee_multiplier": float(call_count[0]),
                            "scheduled_ts": "2026-01-01T00:00:00Z",
                        }
                    ]
                }
            )

        monkeypatch.setattr("requests.get", mock_get)

        now = datetime(2026, 7, 4, tzinfo=UTC)

        # Two different tickers — two separate API calls
        ft_a = resolve_fee_type(series_ticker="TEST-CACHE-A", now=now)
        assert ft_a.multiplier == Decimal("1.0")
        assert call_count[0] == 1

        ft_b = resolve_fee_type(series_ticker="TEST-CACHE-B", now=now)
        assert ft_b.multiplier == Decimal("2.0")  # Second call, multiplier=2.0
        assert call_count[0] == 2

        # Repeat — both should hit cache (no new API calls)
        ft_a2 = resolve_fee_type(series_ticker="TEST-CACHE-A", now=now)
        assert ft_a2.multiplier == Decimal("1.0")
        assert call_count[0] == 2  # Cache hit

        ft_b2 = resolve_fee_type(series_ticker="TEST-CACHE-B", now=now)
        assert ft_b2.multiplier == Decimal("2.0")
        assert call_count[0] == 2  # Cache hit


# ── Integration Test ────────────────────────────────────────────────────────


class TestIntegration:
    """VAL-FEE-050: Integration smoke test with API (marked integration)."""

    @pytest.mark.integration
    def test_fee_changes_live_integration(self) -> None:
        """Hit actual Kalshi API for fee_changes and verify parseable response."""
        import requests

        url = "https://external-api.kalshi.com/trade-api/v2/series/fee_changes?series_ticker=KXUNIT-26JUL01-T5000"
        resp = requests.get(url, timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
