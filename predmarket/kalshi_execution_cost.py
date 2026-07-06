"""Kalshi execution-cost normalization for contract EV work.

This module is deliberately local and offline. It does not place orders,
inspect accounts, call providers, or infer that any row is tradable. It only
normalizes the cost hurdle a calibrated probability would have to beat.

Canonical fee engine components:
- kalshi_trade_fee()  — quadratic fee rounded up to nearest centicent
- kalshi_net_fee()    — net_fee = trade_fee + rounding_fee - rebate
- FeeAccumulator      — per-order rounding tracker with $0.01 rebate triggers
- FeeType             — fee schedule type from /series/fee_changes API
- resolve_fee_type()  — query fee_changes by series_ticker (with caching)
- FeeTable            — pre-computed fixture values for 5c through 95c
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_DOWN, Decimal
from typing import Any, ClassVar

DEFAULT_BINARY_PAYOUT = 1.0
GENERAL_TAKER_FEE_RATE = Decimal("0.07")
GENERAL_MAKER_FEE_RATE = Decimal("0.0175")
INDEX_TAKER_FEE_RATE = Decimal("0.035")
CENTICENT = Decimal("0.0001")
CENT = Decimal("0.01")

logger = logging.getLogger(__name__)

# ── Fee Type ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FeeType:
    """Fee schedule for a series as returned by /series/fee_changes.

    Attributes:
        kind: One of "quadratic", "quadratic_with_maker_fees", "flat".
        multiplier: Multiplier applied to the base fee rate (default 1.0).
        scheduled_ts: When this fee type takes effect (UTC); None if current.
    """

    kind: str = "quadratic"
    multiplier: Decimal = Decimal("1.0")
    scheduled_ts: datetime | None = None


# ── Fee Table — Official fixture values ─────────────────────────────────────


class FeeTable:
    """Pre-computed official fee table for 5¢ through 95¢ (in 5¢ increments).

    Each entry equals kalshi_trade_fee(price=P, fee_rate=R) for the given rate.
    """

    _taker: ClassVar[dict[float, float]] = {}
    _maker: ClassVar[dict[float, float]] = {}

    @classmethod
    def _build(cls) -> None:
        if cls._taker:
            return
        for i in range(1, 20):
            price = round(0.05 * i, 2)
            cls._taker[price] = kalshi_trade_fee(
                price=price,
                fee_rate=GENERAL_TAKER_FEE_RATE,
            )
            cls._maker[price] = kalshi_trade_fee(
                price=price,
                fee_rate=GENERAL_MAKER_FEE_RATE,
            )

    @classmethod
    def get(cls, price: float, mode: str = "taker") -> float:
        cls._build()
        table = cls._maker if mode.lower().strip() == "maker" else cls._taker
        return table.get(price, 0.0)

    @classmethod
    def taker_fees(cls) -> dict[float, float]:
        cls._build()
        return dict(cls._taker)

    @classmethod
    def maker_fees(cls) -> dict[float, float]:
        cls._build()
        return dict(cls._maker)


# ── Fee Changes Cache ──────────────────────────────────────────────────────
# Cache keyed by series_ticker; stores (FeeType, cached_at_timestamp)

FEE_CHANGES_CACHE: dict[str, tuple[FeeType, float]] = {}
FEE_CHANGES_CACHE_TTL: float = 60.0  # seconds


# ── Rounding Fee ────────────────────────────────────────────────────────────


def _compute_rounding_fee(balance_change: Decimal) -> Decimal:
    """Compute rounding fee = balance_change - floor_to_cent(balance_change).

    Kalshi rounds balance changes down to the nearest cent ($0.01). The
    rounding fee captures the fractional cent that was truncated.
    Always in [0, $0.01).
    """
    if balance_change <= 0:
        return Decimal("0")
    truncated = balance_change.quantize(CENT, rounding=ROUND_DOWN)
    return balance_change - truncated


# ── Fee Accumulator ─────────────────────────────────────────────────────────


class FeeAccumulator:
    """Per-order accumulator tracking centicent rounding overpayment.

    Each fill contributes its rounding_fee to the running total. When the
    accumulated amount reaches or exceeds $0.01, a $0.01 rebate is issued
    and the accumulator is reduced by $0.01 (carrying forward any excess).

    Multiple fills toward the same order share one accumulator.
    """

    def __init__(self, order_id: str = "") -> None:
        self._order_id: str = order_id
        self._accumulated: Decimal = Decimal("0")
        self._rebates_issued: int = 0

    @property
    def accumulated(self) -> Decimal:
        return self._accumulated

    @property
    def rebates_issued(self) -> int:
        return self._rebates_issued

    @property
    def order_id(self) -> str:
        return self._order_id

    def add_fill(self, rounding_fee: Decimal) -> Decimal:
        """Record a fill's rounding_fee. Returns rebate amount (0 or $0.01)."""
        self._accumulated += rounding_fee
        if self._accumulated >= CENT:
            self._rebates_issued += 1
            self._accumulated -= CENT
            return CENT
        return Decimal("0")


# ── Net Fee ─────────────────────────────────────────────────────────────────


def kalshi_net_fee(
    *,
    price: float,
    contract_count: float = 1.0,
    fee_mode: str = "taker",
    ticker: str | None = None,
    fee_rate_override: float | None = None,
    accumulator: FeeAccumulator | None = None,
    force_rebate: bool = False,
    explicit_balance_change: Decimal | None = None,
) -> float:
    """Compute net_fee = trade_fee + rounding_fee - rebate for a single fill.

    Args:
        price: Contract price (dollars, 0..1 range for binary contracts).
        contract_count: Number of contracts in the fill.
        fee_mode: "maker" or "taker" (case-insensitive).
        ticker: Series ticker for index fee rate inference.
        fee_rate_override: If provided, overrides all other fee rate sources.
        accumulator: FeeAccumulator for tracking rounding overpayment rebates.
        force_rebate: If True, apply a $0.01 rebate (for testing).
        explicit_balance_change: Explicit balance change for rounding fee
            computation (for testing); otherwise uses trade_fee.

    Returns:
        Net fee as a float.
    """
    fee_rate = resolve_fee_rate(
        fee_mode=fee_mode,
        ticker=ticker,
        fee_rate_override=fee_rate_override,
    )
    trade_fee_val = kalshi_trade_fee(
        price=price,
        contract_count=contract_count,
        fee_rate=fee_rate,
    )

    # Rounding fee: compute from the trade fee (or explicit value)
    balance_change = (
        explicit_balance_change
        if explicit_balance_change is not None
        else Decimal(str(trade_fee_val))
    )
    rounding = _compute_rounding_fee(balance_change)

    # Rebate handling
    rebate = Decimal("0")
    if force_rebate:
        rebate = CENT
    if accumulator is not None:
        rebate = accumulator.add_fill(rounding)

    net = Decimal(str(trade_fee_val)) + rounding - rebate
    return float(net)


# ── Fee Type Resolution (API Integration) ───────────────────────────────────


def resolve_fee_type(
    series_ticker: str | None,
    now: datetime | None = None,
) -> FeeType:
    """Resolve the fee type for a series via /series/fee_changes (with caching).

    Queries the Kalshi API by series_ticker, parses fee_type/multiplier/
    scheduled_ts from the response. Results are cached per series_ticker for
    FEE_CHANGES_CACHE_TTL seconds.

    Args:
        series_ticker: The series ticker to look up. If None, empty, or
            whitespace-only, returns default quadratic with no API call.
        now: Override current time (for testing). Defaults to UTC now.

    Returns:
        FeeType with kind, multiplier, and optional scheduled_ts.
    """
    # Handle missing/empty series_ticker — no API call
    if not series_ticker or not series_ticker.strip():
        return FeeType()

    ticker = series_ticker.strip()
    now = now or datetime.now(UTC)
    now_ts = now.timestamp()

    # Check cache
    cached = FEE_CHANGES_CACHE.get(ticker)
    if cached is not None:
        cached_ft, cached_at = cached
        age = now_ts - cached_at
        if age < FEE_CHANGES_CACHE_TTL:
            return cached_ft

    # Attempt API call
    try:
        import requests

        url = f"https://external-api.kalshi.com/trade-api/v2/series/fee_changes?series_ticker={ticker}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            ft = _parse_fee_changes_response(data, now)
            # Cache the result
            FEE_CHANGES_CACHE[ticker] = (ft, now_ts)
            return ft
        else:
            logger.warning(
                "fee_changes API returned %s for %s; using default",
                resp.status_code,
                ticker,
            )
    except Exception:
        logger.warning(
            "fee_changes API unavailable for %s; using default fee type",
            ticker,
            exc_info=True,
        )

    return FeeType()


def _parse_fee_changes_response(
    data: dict[str, Any],
    now: datetime,
) -> FeeType:
    """Parse /series/fee_changes API response into FeeType.

    Selects the record with the most recent scheduled_ts ≤ now.
    If all records have future scheduled_ts, returns default.
    """
    records = data.get("fee_changes", []) if isinstance(data, dict) else []
    if not records:
        return FeeType()

    # Find the most recent record with scheduled_ts ≤ now
    parsed_applicable: list[tuple[datetime, dict[str, Any]]] = []

    for record in records:
        raw_ts = record.get("scheduled_ts")
        if raw_ts:
            try:
                ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                if ts <= now:
                    parsed_applicable.append((ts, record))
            except (ValueError, TypeError):
                parsed_applicable.append(
                    (datetime.min.replace(tzinfo=UTC), record)
                )
        else:
            parsed_applicable.append(
                (datetime.min.replace(tzinfo=UTC), record)
            )

    if not parsed_applicable:
        # All records have future scheduled_ts
        return FeeType()

    # Use the most recent applicable record (compare parsed datetimes)
    _chosen_ts, chosen = max(parsed_applicable, key=lambda pair: pair[0])

    kind = chosen.get("fee_type", "quadratic")
    raw_mult = chosen.get("fee_multiplier")
    multiplier = Decimal(str(raw_mult)) if raw_mult is not None else Decimal("1.0")
    raw_ts = chosen.get("scheduled_ts")
    scheduled_ts: datetime | None = None
    if raw_ts:
        try:
            scheduled_ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass

    return FeeType(kind=kind, multiplier=multiplier, scheduled_ts=scheduled_ts)


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
    fee_mode: str = "maker",
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
