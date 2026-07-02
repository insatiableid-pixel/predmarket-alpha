"""Kalshi execution-cost normalization for contract EV work.

This module is deliberately local and offline. It does not place orders,
inspect accounts, call providers, or infer that any row is tradable. It only
normalizes the cost hurdle a calibrated probability would have to beat.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING


DEFAULT_BINARY_PAYOUT = 1.0
GENERAL_TAKER_FEE_RATE = Decimal("0.07")
GENERAL_MAKER_FEE_RATE = Decimal("0.0175")
INDEX_TAKER_FEE_RATE = Decimal("0.035")
CENTICENT = Decimal("0.0001")


@dataclass(frozen=True)
class KalshiExecutionCost:
    """Normalized per-contract cost basis for a binary $1-payout contract."""

    all_in_cost: float | None
    break_even_probability: float | None
    cost_basis_source: str | None
    break_even_source: str | None
    gross_execution_cost: float | None
    display_price_break_even: float | None
    contract_price_break_even: float | None
    gross_payout_break_even: float | None
    fee_inclusive_payout_break_even: float | None
    payout_implied_break_even: float | None
    fee_estimate: float | None
    fee_source: str | None
    fee_rate: float | None
    fee_mode: str
    slippage_buffer: float | None
    cost_quality: str
    gate_status: str
    gate_reasons: tuple[str, ...]


def normalize_kalshi_execution_cost(
    *,
    display_price: float | None,
    executable_price: float | None,
    executable_price_source: str,
    explicit_all_in_cost: float | None = None,
    fee_inclusive_payout_multiple: float | None = None,
    gross_payout_multiple: float | None = None,
    explicit_fee_estimate: float | None = None,
    slippage_buffer: float | None = None,
    payout_if_correct: float = DEFAULT_BINARY_PAYOUT,
    fee_mode: str = "taker",
    ticker: str | None = None,
    fee_rate_override: float | None = None,
) -> KalshiExecutionCost:
    """Return the best available all-in cost basis for a Kalshi contract row.

    Priority order:
    1. Explicit all-in execution cost.
    2. Fee-inclusive/net payout multiple.
    3. Gross ticket/order payout multiple plus explicit or official estimated fee.
    4. Executable contract price plus explicit or official estimated fee.
    """

    payout = positive_float(payout_if_correct) or DEFAULT_BINARY_PAYOUT
    explicit_cost = bounded_cost(explicit_all_in_cost, payout)
    fee_inclusive_break_even = reciprocal(fee_inclusive_payout_multiple)
    gross_payout_break_even = reciprocal(gross_payout_multiple)
    contract_price_break_even = safe_divide(executable_price, payout)
    display_price_break_even = safe_divide(display_price, payout)
    slippage = nonnegative_float(slippage_buffer) or 0.0
    fee_rate = resolve_fee_rate(
        fee_mode=fee_mode,
        ticker=ticker,
        fee_rate_override=fee_rate_override,
    )

    gate_reasons: list[str] = []
    fee_estimate: float | None = None
    fee_source: str | None = None
    gross_execution_cost: float | None = None

    if explicit_cost is not None:
        all_in_cost = explicit_cost
        cost_basis_source = "explicit_all_in_cost"
        break_even_source = "explicit_all_in_cost"
        fee_source = "included_in_explicit_all_in_cost"
        cost_quality = "observed_all_in"
    elif fee_inclusive_break_even is not None:
        all_in_cost = payout * fee_inclusive_break_even
        gross_execution_cost = all_in_cost
        cost_basis_source = "fee_inclusive_payout_multiple"
        break_even_source = "fee_inclusive_payout_multiple"
        fee_source = "included_in_fee_inclusive_payout_multiple"
        cost_quality = "observed_fee_inclusive_payout"
    elif gross_payout_break_even is not None:
        gross_execution_cost = payout * gross_payout_break_even
        fee_estimate, fee_source = resolve_fee_estimate(
            explicit_fee_estimate=explicit_fee_estimate,
            gross_price=gross_execution_cost,
            contract_count=1.0,
            fee_rate=fee_rate,
            fee_mode=fee_mode,
        )
        all_in_cost = gross_execution_cost + (fee_estimate or 0.0) + slippage
        cost_basis_source = "kalshi_payout_multiple_plus_fee_estimate"
        break_even_source = "kalshi_payout_multiple_plus_fee_estimate"
        cost_quality = "estimated_fee_from_gross_payout"
    elif executable_price is not None:
        gross_execution_cost = executable_price
        fee_estimate, fee_source = resolve_fee_estimate(
            explicit_fee_estimate=explicit_fee_estimate,
            gross_price=executable_price,
            contract_count=1.0,
            fee_rate=fee_rate,
            fee_mode=fee_mode,
        )
        all_in_cost = executable_price + (fee_estimate or 0.0) + slippage
        cost_basis_source = executable_price_source
        break_even_source = "executable_contract_price_plus_fee_estimate"
        cost_quality = "estimated_fee_from_executable_price"
    else:
        all_in_cost = None
        cost_basis_source = None
        break_even_source = None
        cost_quality = "missing_cost_basis"
        gate_reasons.append("execution cost basis is missing")

    break_even = safe_divide(all_in_cost, payout)
    if explicit_fee_estimate is not None and explicit_fee_estimate < 0:
        gate_reasons.append("explicit fee estimate is negative")
    if slippage_buffer is not None and slippage_buffer < 0:
        gate_reasons.append("slippage buffer is negative")
    gate_status = "blocked" if any("missing" in reason for reason in gate_reasons) else "pass"

    return KalshiExecutionCost(
        all_in_cost=all_in_cost,
        break_even_probability=break_even,
        cost_basis_source=cost_basis_source,
        break_even_source=break_even_source,
        gross_execution_cost=gross_execution_cost,
        display_price_break_even=display_price_break_even,
        contract_price_break_even=contract_price_break_even,
        gross_payout_break_even=gross_payout_break_even,
        fee_inclusive_payout_break_even=fee_inclusive_break_even,
        payout_implied_break_even=fee_inclusive_break_even or gross_payout_break_even,
        fee_estimate=fee_estimate,
        fee_source=fee_source,
        fee_rate=float(fee_rate),
        fee_mode=fee_mode,
        slippage_buffer=slippage_buffer,
        cost_quality=cost_quality,
        gate_status=gate_status,
        gate_reasons=tuple(gate_reasons),
    )


def resolve_fee_estimate(
    *,
    explicit_fee_estimate: float | None,
    gross_price: float,
    contract_count: float,
    fee_rate: Decimal,
    fee_mode: str,
) -> tuple[float | None, str | None]:
    explicit = nonnegative_float(explicit_fee_estimate)
    if explicit is not None:
        return explicit, "explicit_fee_estimate"
    estimate = kalshi_trade_fee(
        price=gross_price,
        contract_count=contract_count,
        fee_rate=fee_rate,
    )
    return estimate, f"kalshi_official_{fee_mode}_fee_estimate"


def kalshi_trade_fee(
    *,
    price: float,
    contract_count: float = 1.0,
    fee_rate: Decimal | float = GENERAL_TAKER_FEE_RATE,
) -> float:
    """Official trade-fee model rounded up to the nearest centicent."""

    p = Decimal(str(price))
    c = Decimal(str(contract_count))
    rate = fee_rate if isinstance(fee_rate, Decimal) else Decimal(str(fee_rate))
    raw_fee = rate * c * p * (Decimal("1") - p)
    return float(round_up_centicent(raw_fee))


def round_up_centicent(value: Decimal) -> Decimal:
    if value <= 0:
        return Decimal("0")
    return value.quantize(CENTICENT, rounding=ROUND_CEILING)


def resolve_fee_rate(
    *,
    fee_mode: str,
    ticker: str | None,
    fee_rate_override: float | None,
) -> Decimal:
    if fee_rate_override is not None and fee_rate_override >= 0:
        return Decimal(str(fee_rate_override))
    normalized = fee_mode.lower().strip()
    if normalized == "maker":
        return GENERAL_MAKER_FEE_RATE
    if is_index_fee_ticker(ticker):
        return INDEX_TAKER_FEE_RATE
    return GENERAL_TAKER_FEE_RATE


def is_index_fee_ticker(ticker: str | None) -> bool:
    if not ticker:
        return False
    upper = ticker.upper()
    return upper.startswith("INX") or upper.startswith("NASDAQ100") or "-INX" in upper


def reciprocal(value: float | None) -> float | None:
    value = positive_float(value)
    if value is None:
        return None
    return 1.0 / value


def bounded_cost(value: float | None, payout: float) -> float | None:
    value = positive_float(value)
    if value is None:
        return None
    return value if value <= payout else None


def nonnegative_float(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out >= 0 else None


def positive_float(value: float | None) -> float | None:
    out = nonnegative_float(value)
    if out is None or out <= 0:
        return None
    return out


def safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator
