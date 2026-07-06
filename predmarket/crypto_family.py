"""CryptoProxyFamily — the crypto-proxy signal family descriptor.

Aggregates every crypto-specific element from the existing lane:
Coinbase fetcher, ASSET_CONFIG, proxy-state prediction rule,
asset|family|close_bucket cluster key, and crypto model evaluators.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from predmarket.shared_helpers import bucket_time
from predmarket.signal_family import SignalFamily

# ── Asset configuration ───────────────────────────────────────────────────

ASSET_CONFIG: dict[str, dict[str, str]] = {
    "BTC": {"coinbase_product": "BTC-USD", "official_index": "BRTI"},
    "ETH": {"coinbase_product": "ETH-USD", "official_index": "ETHUSDRTI"},
    "SOL": {"coinbase_product": "SOL-USD", "official_index": "SOLUSDRTI"},
    "DOGE": {"coinbase_product": "DOGE-USD", "official_index": "DOGEUSDRTI"},
    "XRP": {"coinbase_product": "XRP-USD", "official_index": "XRPUSDRTI"},
    "ZEC": {"coinbase_product": "ZEC-USD", "official_index": "ZECUSDRTI"},
    "NEAR": {"coinbase_product": "NEAR-USD", "official_index": "NEARUSDRTI"},
    "BNB": {"coinbase_product": "BNB-USD", "official_index": "BNBUSDRTI"},
    "HYPE": {"coinbase_product": "HYPE-USD", "official_index": "HYPEUSDRTI"},
}
ASSET_ORDER = tuple(ASSET_CONFIG)

CRYPTO_OFFICIAL_SETTLEMENT_SOURCE = "CF Benchmarks RTI"


# ── Prediction rule ──────────────────────────────────────────────────────


def crypto_prediction_rule(row: Mapping[str, Any]) -> tuple[int | None, float | None]:
    """Crypto proxy-state prediction rule.

    Returns (1, confidence) when proxy_state contains "above",
    (0, confidence) when it contains "below", and (None, None) otherwise.
    """
    text = str(row.get("proxy_state") or "").lower()
    if "above" in text:
        return 1, None
    if "below" in text:
        return 0, None
    return None, None


# ── Cluster-key composer ─────────────────────────────────────────────────


def crypto_cluster_key_composer(row: Mapping[str, Any]) -> str:
    """Compose correlation cluster key: asset_symbol|contract_family|close_bucket."""
    return "|".join(
        str(part or "unknown")
        for part in (
            row.get("asset_symbol"),
            row.get("contract_family"),
            bucket_time(row.get("close_time")),
        )
    )


# ── Model evaluators ─────────────────────────────────────────────────────


def evaluate_proxy_state_directional(
    *,
    rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    prediction_rule: Callable[[Mapping[str, Any]], tuple[int | None, float | None]],
    min_independent_labels: int,
    min_oos_labels: int,
) -> dict[str, Any]:
    """Evaluate proxy-state directional accuracy on OOS rows."""
    scored = [row for row in oos_rows if prediction_rule(row)[0] is not None]
    wins = sum(1 for row in scored if prediction_rule(row)[0] == row.get("yes_outcome"))
    from predmarket.shared_helpers import binomial_survival

    p_value = (
        binomial_survival(wins, len(scored), 0.5)
        if len(rows) >= min_independent_labels and len(scored) >= min_oos_labels
        else None
    )
    if len(rows) < min_independent_labels:
        status = "blocked_insufficient_independent_labels"
    elif len(scored) < min_oos_labels:
        status = "blocked_insufficient_oos_labels"
    else:
        status = "testable_research_candidate"
    return {
        "model_id": "proxy_state_directional_accuracy",
        "status": status,
        "independent_label_count": len(rows),
        "oos_count": len(scored),
        "oos_correct_count": wins,
        "oos_accuracy": wins / len(scored) if scored else None,
        "p_value": p_value,
        "q_value": None,
        "feature_rule": "Predict YES when proxy_state contains above; predict NO when proxy_state contains below.",
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


def evaluate_market_yes_ask_baseline(
    *,
    rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    prediction_rule: Callable[[Mapping[str, Any]], tuple[int | None, float | None]] | None = None,
    min_independent_labels: int | None = None,
    min_oos_labels: int | None = None,
) -> dict[str, Any]:
    """Evaluate market YES ask as a baseline Brier-score diagnostic."""
    from predmarket.shared_helpers import probability

    scored = [row for row in oos_rows if probability(row.get("yes_ask")) is not None]
    briers = [(float(row["yes_ask"]) - float(row["yes_outcome"])) ** 2 for row in scored]
    return {
        "model_id": "market_yes_ask_probability_baseline",
        "status": "diagnostic_baseline_only",
        "independent_label_count": len(rows),
        "oos_count": len(scored),
        "mean_market_brier": sum(briers) / len(briers) if briers else None,
        "p_value": None,
        "q_value": None,
        "feature_rule": "Market YES ask is recorded as a baseline probability diagnostic, not a model promotion.",
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


CRYPTO_MODEL_EVALUATORS: list[dict[str, Any]] = [
    {
        "model_id": "proxy_state_directional_accuracy",
        "evaluate_fn": evaluate_proxy_state_directional,
    },
    {
        "model_id": "market_yes_ask_probability_baseline",
        "evaluate_fn": evaluate_market_yes_ask_baseline,
    },
]


# ── CryptoProxyFamily singleton ──────────────────────────────────────────


def make_crypto_family(**overrides: Any) -> SignalFamily:
    """Factory that returns the canonical CryptoProxyFamily descriptor.

    Accepts optional overrides (e.g. for tests to swap the fetcher).
    """
    import dataclasses

    base = SignalFamily(
        family_id="crypto_proxy",
        status_prefix="crypto_proxy",
        classification_tag="finance_crypto",
        official_settlement_source=CRYPTO_OFFICIAL_SETTLEMENT_SOURCE,
        reference_source_registry=dict(ASSET_CONFIG),
        fetcher=None,
        feature_definitions={},
        prediction_rule=crypto_prediction_rule,
        model_evaluators=list(CRYPTO_MODEL_EVALUATORS),
        cluster_key_composer=crypto_cluster_key_composer,
    )
    if overrides:
        return dataclasses.replace(base, **overrides)
    return base
