"""Cross-venue arbitrage detection with semantic safety checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class VenueQuote:
    venue: str
    market_id: str
    bid: float
    ask: float
    no_ask: Optional[float] = None
    yes_fee: float = 0.0
    no_fee: float = 0.0
    max_size: float = 0.0
    capital_lockup_days: float = 1.0
    semantic_confidence: float = 1.0


@dataclass
class ArbitrageOpportunity:
    event_id: str
    long_yes: VenueQuote
    long_no: VenueQuote
    net_edge: float
    max_size: float
    capital_lockup_days: float
    semantic_confidence: float


def detect_cross_venue_arbitrage(
    event_id: str,
    quotes: Iterable[VenueQuote | Dict[str, Any]],
    min_net_edge: float = 0.005,
    min_semantic_confidence: float = 0.85,
) -> List[ArbitrageOpportunity]:
    """Find executable YES/NO packages costing less than one payout unit."""
    normalized = [_coerce_quote(q) for q in quotes]
    opportunities: List[ArbitrageOpportunity] = []
    for yes_quote in normalized:
        for no_quote in normalized:
            if yes_quote.market_id == no_quote.market_id and yes_quote.venue == no_quote.venue:
                continue
            semantic_confidence = min(
                yes_quote.semantic_confidence, no_quote.semantic_confidence
            )
            if semantic_confidence < min_semantic_confidence:
                continue
            yes_cost = yes_quote.ask + yes_quote.yes_fee
            no_cost = _no_ask(no_quote) + no_quote.no_fee
            executable_cost = yes_cost + no_cost
            net_edge = 1.0 - executable_cost
            if net_edge < min_net_edge:
                continue
            opportunities.append(
                ArbitrageOpportunity(
                    event_id=event_id,
                    long_yes=yes_quote,
                    long_no=no_quote,
                    net_edge=float(net_edge),
                    max_size=min_positive(yes_quote.max_size, no_quote.max_size),
                    capital_lockup_days=max(
                        yes_quote.capital_lockup_days, no_quote.capital_lockup_days
                    ),
                    semantic_confidence=semantic_confidence,
                )
            )
    return sorted(opportunities, key=lambda item: item.net_edge, reverse=True)


def min_positive(a: float, b: float) -> float:
    values = [value for value in (float(a), float(b)) if value > 0]
    return min(values) if values else 0.0


def _coerce_quote(value: VenueQuote | Dict[str, Any]) -> VenueQuote:
    if isinstance(value, VenueQuote):
        return value
    return VenueQuote(
        venue=str(value.get("venue", "")),
        market_id=str(value.get("market_id", value.get("contract_id", ""))),
        bid=float(value.get("bid", 0.0)),
        ask=float(value.get("ask", value.get("market_implied", 1.0))),
        no_ask=(
            float(value["no_ask"])
            if value.get("no_ask") is not None
            else None
        ),
        yes_fee=float(value.get("yes_fee", value.get("fee", 0.0))),
        no_fee=float(value.get("no_fee", value.get("fee", 0.0))),
        max_size=float(value.get("max_size", value.get("size", 0.0))),
        capital_lockup_days=float(value.get("capital_lockup_days", 1.0)),
        semantic_confidence=float(value.get("semantic_confidence", 1.0)),
    )


def _no_ask(quote: VenueQuote) -> float:
    if quote.no_ask is not None:
        return float(quote.no_ask)
    return max(0.0, 1.0 - float(quote.bid))
