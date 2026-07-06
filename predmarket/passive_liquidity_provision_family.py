"""PassiveLiquidityProvisionFamily — maker-side liquidity provision signal family.

Hypothesis: placing maker (post-only) quotes on the best-bid side of Kalshi
orderbooks yields positive net expected value after accounting for adverse
selection — i.e., the maker fee savings outweigh the cost of being picked off
by informed flow.

This is NOT a directional-edge family.  The acceptance criterion is
``maker_fill_net_ev_after_adverse_selection > 0``, not binomial survival
against a null rate.  Each evaluator simulates virtual maker orders against
public microstructure observation snapshots, computes counterfactual fill
outcomes under an assumed time-to-leave (TTL), adjusts for adverse-selection
mid-drift, and aggregates net EV.

Falsification proceeds through the same generic ``build_falsification()``
spine as directional families.  The evaluator returns a ``p_value`` from a
one-sided significance test against the null hypothesis that net EV ≤ 0,
enabling BH-FDR control across evaluators.  The evaluator method dict also
carries ``maker_fill_net_ev_after_adverse_selection`` as the primary
acceptance metric.

Virtual order sequence replay: microstructure observations
(``kalshi_sports_microstructure_observation_loop.py`` artifacts) are replayed
in chronological order per contract.  At each snapshot, a virtual maker quote
is placed one tick inside the best ask.  Future snapshots within the TTL
window are scanned for a crossing event (best ask ≤ quote price).  If crossed,
the mid-price before and after the touch is compared to measure adverse
selection.

Research-only guardrails: all output rows carry ``research_only=True`` and
``execution_enabled=False``.  This family never submits live quotes or orders.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from predmarket.kalshi_execution_cost import GENERAL_MAKER_FEE_RATE, GENERAL_TAKER_FEE_RATE
from predmarket.shared_helpers import json_float, timestamp
from predmarket.signal_family import SignalFamily

FAMILY_ID = "passive_liquidity_provision"
STATUS_PREFIX = "passive_liquidity_provision"
PASSIVE_LIQUIDITY_OFFICIAL_SETTLEMENT_SOURCE = "Kalshi public settlement"

# Default TTL for virtual maker quotes (seconds).
DEFAULT_TTL_SECONDS = 180

# Minimum number of virtual orders for a statistically meaningful evaluator.
MIN_VIRTUAL_ORDERS = 10

# Time-bucket size (hours) for cluster key composability.
CLUSTER_TIME_BUCKET_HOURS = 6

# Evaluator model-id prefix.
EVALUATOR_MODEL_ID_PREFIX = f"{FAMILY_ID}_maker_side"


def _as_float(value: Any) -> float | None:
    """Safely convert a value to float or return None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ── Prediction rule ──────────────────────────────────────────────────────


def passive_liquidity_prediction_rule(
    row: Mapping[str, Any],
) -> tuple[str | None, float | None]:
    """Passive liquidity prediction rule.

    Returns a maker-quote side prediction based on the microstructure row:

    - If the yes-side spread is >= 1 cent AND the no-side spread is narrower,
      predict quoting on the YES side (return ``"yes"``).
    - If the no-side spread is >= 1 cent AND the yes-side spread is narrower,
      predict quoting on the NO side (return ``"no"``).
    - If both spreads are below 1 cent or both are equal, return ``None``
      (no reliable maker opportunity).

    The idea: a maker quote improves the best bid by one tick.  On the side
    with wider spread, the quote is more likely to be the best rate and
    therefore more attractive to the counterparty.

    Returns ``(side_str | None, None)`` — no confidence score for this rule.
    """
    yes_spread = _as_float(row.get("yes_spread"))
    no_spread = _as_float(row.get("no_spread"))
    best_yes_bid = _as_float(row.get("best_yes_bid"))
    best_no_bid = _as_float(row.get("best_no_bid"))
    best_yes_ask = _as_float(row.get("best_yes_ask"))
    best_no_ask = _as_float(row.get("best_no_ask"))

    # Need all four book levels and both spreads.
    if any(
        v is None
        for v in (yes_spread, no_spread, best_yes_bid, best_no_bid, best_yes_ask, best_no_ask)
    ):
        return None, None

    # Need at least 1¢ spread on at least one side for a viable maker quote.
    if not (yes_spread is not None and no_spread is not None):
        return None, None
    if yes_spread < 0.01 and no_spread < 0.01:
        return None, None

    # Quote on the side with wider spread (more room for maker improvement).
    if yes_spread >= 0.01 and (no_spread < 0.01 or yes_spread >= no_spread):
        return "yes", None
    if no_spread >= 0.01 and (yes_spread < 0.01 or no_spread > yes_spread):
        return "no", None

    return None, None


def _side_to_str(side: str | int) -> str:
    """Convert a side to its string representation."""
    if isinstance(side, int):
        return "yes" if side == 1 else "no"
    return side


# ── Virtual order helpers ───────────────────────────────────────────────


def _quote_price_for_side(row: Mapping[str, Any], side: str) -> float | None:
    """Compute a maker quote price one tick inside the best ask.

    For side="yes": quote just above best_yes_bid (improve the bid).
    For side="no": quote just above best_no_bid (improve the bid on the no side).
    """
    bid = _as_float(row.get(f"best_{side}_bid"))
    ask = _as_float(row.get(f"best_{side}_ask"))
    if bid is None or ask is None:
        return None
    # One tick ($0.01) improvement over the best bid.
    price = min(ask - 0.01, bid + 0.01)
    if 0.0 < price < ask and price < 1.0:
        return round(price, 4)
    return None


def _side_mid(row: Mapping[str, Any], side: str) -> float | None:
    """Compute the mid-price for a given side.

    For yes: use yes_mid field.
    For no: compute (best_no_bid + best_no_ask) / 2.
    """
    if side == "yes":
        return _as_float(row.get("yes_mid"))
    bid = _as_float(row.get("best_no_bid"))
    ask = _as_float(row.get("best_no_ask"))
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    return None


def _ts(value: Any) -> float | None:
    """Convert a timestamp string or int to a float UNIX timestamp."""
    return timestamp(value)


def _expiry(observed_at: str, ttl_seconds: int) -> str:
    """Compute the expiry time as an ISO-8601 UTC string."""
    ts = _ts(observed_at)
    if ts is None:
        return ""
    return (
        (datetime.fromtimestamp(ts, UTC) + timedelta(seconds=max(1, ttl_seconds)))
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _fill_proxy_for_virtual_bid(
    future_rows: Sequence[Mapping[str, Any]],
    *,
    side: str,
    quote_price: float,
    observed_at: str,
    ttl_seconds: int,
) -> dict[str, Any]:
    """Simulate a counterfactual fill by scanning future snapshots.

    Returns a dict with:
    - ``status``: ``"would_touch_within_ttl"``, ``"not_touched_within_observed_ttl"``,
      or ``"insufficient_future_snapshots"``.
    - ``touch_row``: the row where the touch was detected.
    - ``expiry_row``: the last row within the TTL window.
    - ``first_touch_utc``: timestamp of the touch.
    - ``fill_proxy_latency_seconds``: seconds from quote to touch.
    """
    observed_ts = _ts(observed_at)
    if observed_ts is None:
        return {"status": "insufficient_future_snapshots"}
    expiry_ts = observed_ts + max(1, ttl_seconds)
    candidates: list[Mapping[str, Any]] = []
    for row in future_rows:
        row_ts = _ts(row.get("observed_at_utc"))
        if row_ts is None or row_ts <= observed_ts or row_ts > expiry_ts:
            continue
        candidates.append(row)
    if not candidates:
        return {"status": "insufficient_future_snapshots"}
    for row in candidates:
        best_ask = _as_float(row.get(f"best_{side}_ask"))
        if best_ask is not None and best_ask <= quote_price:
            touch_ts = _ts(row.get("observed_at_utc")) or 0.0
            return {
                "status": "would_touch_within_ttl",
                "touch_row": row,
                "expiry_row": candidates[-1],
                "first_touch_utc": row.get("observed_at_utc"),
                "fill_proxy_latency_seconds": touch_ts - observed_ts,
            }
    return {"status": "not_touched_within_observed_ttl", "expiry_row": candidates[-1]}


def _compute_virtual_order_ev(
    *,
    quote_price: float,
    maker_fee: float,
    taker_fee: float,
    mid_at_entry: float | None,
    mid_after_touch: float | None,
    fill_proxy_status: str,
    side: str,
) -> dict[str, float | None]:
    """Compute counterfactual net EV for a single virtual order.

    For a filled virtual order:
    - The maker-fee saving is ``taker_fee - maker_fee``.
    - The adverse-selection cost is the mid-price drift after the touch.
    - ``counterfactual_net_ev_if_filled = fee_savings - adverse_selection_cost``.

    For an unfilled order (timeout):
    - ``counterfactual_net_ev_with_timeout = 0`` (no fill, no P&L impact).

    Returns a dict with ``maker_fee_savings``, ``adverse_selection_mid_delta``,
    ``counterfactual_net_ev_if_filled``, and ``counterfactual_net_ev_with_timeout``.
    """
    maker_fee_savings = taker_fee - maker_fee

    if fill_proxy_status == "would_touch_within_ttl":
        if mid_at_entry is not None and mid_after_touch is not None:
            adverse_selection_mid_delta = mid_after_touch - mid_at_entry
        else:
            adverse_selection_mid_delta = None
    else:
        adverse_selection_mid_delta = None

    if (
        fill_proxy_status == "would_touch_within_ttl"
        and maker_fee_savings is not None
        and adverse_selection_mid_delta is not None
    ):
        # Net EV = fee savings - adverse selection cost.
        # For a YES maker bid: mid decreasing (delta < 0, adverse for YES buyer)
        # incurs cost; mid increasing (delta > 0, favorable) does not.
        # For a NO maker bid: applying the same delta < 0 logic means mid
        # decreasing (adverse for NO buyer) incurs cost; mid increasing
        # (favorable) does not. Both sides penalize when the mid moves down
        # after the maker buys their respective side.
        if side == "yes":
            adv_cost = abs(adverse_selection_mid_delta) if adverse_selection_mid_delta < 0 else 0.0
        else:
            adv_cost = abs(adverse_selection_mid_delta) if adverse_selection_mid_delta < 0 else 0.0
        net_ev = maker_fee_savings - adv_cost
    else:
        net_ev = None

    return {
        "maker_fee_savings": maker_fee_savings,
        "adverse_selection_mid_delta": adverse_selection_mid_delta,
        "counterfactual_net_ev_if_filled": net_ev,
        "counterfactual_net_ev_with_timeout": 0.0,
    }


# ── Evaluator factory ────────────────────────────────────────────────────


def _make_passive_liquidity_evaluate_fn(
    side_label: str,
    side_int: int | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> Callable[..., dict[str, Any]]:
    """Create an evaluate_fn for a maker-side (yes or no).

    The returned callable simulates virtual maker orders on microstructure
    observation rows and computes aggregate net EV after adverse selection.
    """

    def _is_applicable(row: Mapping[str, Any]) -> bool:
        """Check if this row is applicable for the given side."""
        pred_side, _ = passive_liquidity_prediction_rule(row)
        return pred_side == side_label

    def evaluate_fn(
        *,
        rows: Sequence[Mapping[str, Any]],
        oos_rows: Sequence[Mapping[str, Any]],
        prediction_rule: Callable[[Mapping[str, Any]], tuple[str | None, float | None]]
        | None = None,
        min_independent_labels: int = 30,
        min_oos_labels: int = 10,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Evaluate passive-liquidity maker EV for this side on OOS rows."""
        n_independent = len(rows)

        # Replay virtual orders on OOS rows in chronological order per contract.
        virtual_orders = _replay_virtual_orders(oos_rows, side=side_label, ttl_seconds=ttl_seconds)
        n_virtual = len(virtual_orders)
        n_filled = sum(
            1 for vo in virtual_orders if vo["fill_proxy_status"] == "would_touch_within_ttl"
        )

        # Compute aggregate net EV statistics.
        net_evs = [
            vo["counterfactual_net_ev_if_filled"]
            for vo in virtual_orders
            if vo["counterfactual_net_ev_if_filled"] is not None
        ]
        maker_fee_savings_list = [
            vo["maker_fee_savings"] for vo in virtual_orders if vo["maker_fee_savings"] is not None
        ]
        adverse_selection_deltas = [
            vo["adverse_selection_mid_delta"]
            for vo in virtual_orders
            if vo["adverse_selection_mid_delta"] is not None
        ]

        mean_net_ev = sum(net_evs) / len(net_evs) if net_evs else None
        mean_fee_savings = (
            sum(maker_fee_savings_list) / len(maker_fee_savings_list)
            if maker_fee_savings_list
            else None
        )
        mean_adverse_selection = (
            sum(adverse_selection_deltas) / len(adverse_selection_deltas)
            if adverse_selection_deltas
            else None
        )

        # Compute p_value via a one-sided t-test against null (net EV ≤ 0).
        # A negative p_value sentinel means "no test possible" (too few fills).
        p_value = _net_ev_one_sided_p(net_evs) if len(net_evs) >= 3 else None

        if n_independent < min_independent_labels:
            status = "blocked_insufficient_independent_labels"
        elif n_virtual < min_oos_labels:
            status = "blocked_insufficient_oos_labels"
        elif n_filled == 0:
            status = "blocked_no_counterfactual_fills"
        elif mean_net_ev is not None and mean_net_ev > 0:
            status = "testable_research_candidate"
        else:
            status = "testable_research_candidate_non_positive_net_ev"

        return {
            "model_id": f"{EVALUATOR_MODEL_ID_PREFIX}_{side_label}",
            "candidate_rule": f"{FAMILY_ID}_maker_side",
            "signal_key": f"{FAMILY_ID}_maker_{side_label}",
            "maker_side": side_label,
            "ttl_seconds": ttl_seconds,
            "independent_label_count": n_independent,
            "oos_virtual_order_count": n_virtual,
            "oos_fill_count": n_filled,
            "oos_unfilled_count": n_virtual - n_filled,
            "fill_rate": json_float(n_filled / n_virtual) if n_virtual > 0 else 0.0,
            "mean_maker_fee_savings": json_float(mean_fee_savings),
            "mean_adverse_selection_mid_delta": json_float(mean_adverse_selection),
            "maker_fill_net_ev_after_adverse_selection": json_float(mean_net_ev),
            "p_value": p_value,
            "q_value": None,
            "status": status,
            "usable": False,
            "calibrated_probability": None,
            "expected_value_per_contract": None,
            "research_only": True,
            "execution_enabled": False,
        }

    return evaluate_fn


def _replay_virtual_orders(
    oos_rows: Sequence[Mapping[str, Any]],
    *,
    side: str,
    ttl_seconds: int,
) -> list[dict[str, Any]]:
    """Replay virtual maker orders on OOS rows in chronological order per contract.

    For each microstructure observation row that is applicable for the given
    side, construct a virtual maker quote and scan future rows for a touch.
    """
    output: list[dict[str, Any]] = []
    # Group rows by contract ticker.
    by_ticker: dict[str, list[Mapping[str, Any]]] = {}
    for row in oos_rows:
        ticker = str(row.get("contract_ticker") or "")
        by_ticker.setdefault(ticker, []).append(row)

    for _ticker, ticker_rows in by_ticker.items():
        ordered = sorted(ticker_rows, key=lambda r: str(r.get("observed_at_utc") or ""))
        for index, row in enumerate(ordered):
            if not _is_applicable_side(row, side):
                continue
            future_rows = ordered[index + 1 :]
            vo = _build_virtual_order(
                row, side=side, ttl_seconds=ttl_seconds, future_rows=future_rows
            )
            if vo:
                output.append(vo)
    return output


def _is_applicable_side(row: Mapping[str, Any], side: str) -> bool:
    """Check if the row is applicable for maker quoting on the given side."""
    pred_side, _ = passive_liquidity_prediction_rule(row)
    return pred_side is not None and pred_side == side


def _build_virtual_order(
    row: Mapping[str, Any],
    *,
    side: str,
    ttl_seconds: int,
    future_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a single virtual order dict from a microstructure row."""
    side_str = side
    quote_price = _quote_price_for_side(row, side_str)
    if quote_price is None:
        return {}

    maker_fee = float(GENERAL_MAKER_FEE_RATE) * quote_price * (1.0 - quote_price)
    taker_fee = float(GENERAL_TAKER_FEE_RATE) * quote_price * (1.0 - quote_price)

    best_ask = _as_float(row.get(f"best_{side_str}_ask"))
    spread = _as_float(row.get(f"{side_str}_spread"))
    observed = str(row.get("observed_at_utc") or "")
    order_expires = _expiry(observed, ttl_seconds)

    fill_proxy = _fill_proxy_for_virtual_bid(
        future_rows,
        side=side_str,
        quote_price=quote_price,
        observed_at=observed,
        ttl_seconds=ttl_seconds,
    )

    mid_at_entry = _side_mid(row, side_str)
    touch_row = fill_proxy.get("touch_row", {})
    if isinstance(touch_row, Mapping):
        mid_after_touch = _side_mid(touch_row, side_str)
    else:
        mid_after_touch = None

    ev_result = _compute_virtual_order_ev(
        quote_price=quote_price,
        maker_fee=maker_fee,
        taker_fee=taker_fee,
        mid_at_entry=mid_at_entry,
        mid_after_touch=mid_after_touch,
        fill_proxy_status=fill_proxy["status"],
        side=side_str,
    )

    virtual_id = hashlib.sha256(
        f"{row.get('snapshot_id')}|{side_str}|{quote_price}|{ttl_seconds}".encode()
    ).hexdigest()

    return {
        "virtual_order_id": virtual_id,
        "hypothesis_id": FAMILY_ID,
        "feature_family": FAMILY_ID,
        "snapshot_id": row.get("snapshot_id"),
        "contract_ticker": row.get("contract_ticker"),
        "side": side_str,
        "quote_rule": "improve_best_bid_one_tick",
        "quote_price": json_float(quote_price),
        "quote_size_contracts": 1,
        "post_only_assumed": True,
        "ttl_seconds": ttl_seconds,
        "order_expires_at_utc": order_expires,
        "best_ask_at_entry": json_float(best_ask),
        "spread_at_entry": json_float(spread),
        "maker_fee_estimate": json_float(maker_fee),
        "taker_fee_estimate": json_float(taker_fee),
        "maker_fee_savings": ev_result["maker_fee_savings"],
        "fill_proxy_status": fill_proxy["status"],
        "first_touch_utc": fill_proxy.get("first_touch_utc"),
        "fill_proxy_latency_seconds": json_float(fill_proxy.get("fill_proxy_latency_seconds")),
        "mid_at_entry": json_float(mid_at_entry),
        "mid_after_touch": json_float(mid_after_touch),
        "adverse_selection_mid_delta": ev_result["adverse_selection_mid_delta"],
        "counterfactual_net_ev_if_filled": ev_result["counterfactual_net_ev_if_filled"],
        "counterfactual_net_ev_with_timeout": ev_result["counterfactual_net_ev_with_timeout"],
        "maker_fill_net_ev_after_adverse_selection": ev_result["counterfactual_net_ev_if_filled"],
        "label_status": "proxy_only_no_real_fill_label",
        "usable": False,
    }


def _net_ev_one_sided_p(net_evs: list[float]) -> float | None:
    """One-sided p-value for the null hypothesis that mean net EV ≤ 0.

    Uses a t-test approximation.  Returns None when the sample is too small
    for a meaningful test (fewer than 3 observations).
    """
    import math

    if len(net_evs) < 3:
        return None
    n = len(net_evs)
    mean = sum(net_evs) / n
    if mean <= 0:
        return 1.0  # Null cannot be rejected.
    variance = sum((x - mean) ** 2 for x in net_evs) / (n - 1)
    if variance <= 0:
        return 0.0 if mean > 0 else 1.0
    se = math.sqrt(variance / n)
    if se <= 0:
        return 0.0 if mean > 0 else 1.0
    t_stat = mean / se
    # Approximate one-sided p-value using the normal distribution.
    # For t ≥ 3, p < 0.001; t ≥ 2, p < 0.023; t ≥ 1, p < 0.159.
    # Use a simple logistic approximation of the normal CDF.
    p = 1.0 / (1.0 + math.exp(1.702 * t_stat))
    return p


# ── Model evaluators ─────────────────────────────────────────────────────


PASSIVE_LIQUIDITY_MODEL_EVALUATORS: list[dict[str, Any]] = [
    {
        "model_id": f"{EVALUATOR_MODEL_ID_PREFIX}_yes",
        "evaluate_fn": _make_passive_liquidity_evaluate_fn("yes"),
    },
    {
        "model_id": f"{EVALUATOR_MODEL_ID_PREFIX}_no",
        "evaluate_fn": _make_passive_liquidity_evaluate_fn("no"),
    },
]


# ── Cluster-key composer ─────────────────────────────────────────────────


def passive_liquidity_cluster_key_composer(row: Mapping[str, Any]) -> str:
    """Compose correlation cluster key: contract_ticker | time_bucket.

    Groups virtual orders by the underlying contract + a 6-hour time bucket.
    Passive liquidity risk is concentrated per contract (each contract can
    receive multiple virtual orders), so the cluster key reflects that.

    The time bucket is computed from the ``observed_at_utc`` or
    ``order_expires_at_utc`` timestamp.
    """
    contract = str(row.get("contract_ticker") or row.get("event_ticker") or "unknown")
    observed = row.get("observed_at_utc") or row.get("order_expires_at_utc")
    bucket_str = _resolve_time_bucket(observed)
    return f"{contract}|{bucket_str}"


def _resolve_time_bucket(timestamp_str: Any) -> str:
    """Resolve a timestamp to a 6-hour bucket string, or 'unknown'."""
    ts = _ts(timestamp_str)
    if ts is None:
        return "unknown"
    dt = datetime.fromtimestamp(ts, UTC)
    bucket_hour = (dt.hour // CLUSTER_TIME_BUCKET_HOURS) * CLUSTER_TIME_BUCKET_HOURS
    return f"{dt.year}-{dt.month:02d}-{dt.day:02d}T{bucket_hour:02d}"


# ── PassiveLiquidityProvisionFamily factory ──────────────────────────────


def make_passive_liquidity_family(**overrides: Any) -> SignalFamily:
    """Factory that returns the canonical PassiveLiquidityProvisionFamily descriptor.

    Accepts optional overrides (e.g. for tests to inject a custom
    ``prediction_rule`` or ``model_evaluators``).
    """
    import dataclasses

    base = SignalFamily(
        family_id=FAMILY_ID,
        status_prefix=STATUS_PREFIX,
        classification_tag="",
        official_settlement_source=PASSIVE_LIQUIDITY_OFFICIAL_SETTLEMENT_SOURCE,
        reference_source_registry={},
        fetcher=None,
        feature_definitions={},
        prediction_rule=passive_liquidity_prediction_rule,
        model_evaluators=list(PASSIVE_LIQUIDITY_MODEL_EVALUATORS),
        cluster_key_composer=passive_liquidity_cluster_key_composer,
    )
    if overrides:
        return dataclasses.replace(base, **overrides)
    return base
