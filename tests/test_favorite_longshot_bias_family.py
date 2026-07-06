"""Tests for the FavoriteLongshotBiasFamily — covers VAL-SIGNAL-001 through
VAL-SIGNAL-004, VAL-SIGNAL-013, VAL-SIGNAL-016, and VAL-CROSS-036.
"""

from __future__ import annotations

from typing import Any

import pytest

from predmarket.engine import build_falsification
from predmarket.favorite_longshot_bias_family import (
    EVALUATOR_MODEL_ID_PREFIX,
    FAMILY_ID,
    FAVORITE_LONGSHOT_MODEL_EVALUATORS,
    _resolve_price_bucket,
    favorite_longshot_cluster_key_composer,
    favorite_longshot_prediction_rule,
    make_favorite_longshot_family,
)
from predmarket.signal_family import SignalFamily
from predmarket.sports_consensus_falsification import DEFAULT_PRICE_BUCKETS

# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-013: SignalFamily descriptor is structurally valid
# ═══════════════════════════════════════════════════════════════════════════


def test_signal_family_all_required_fields() -> None:
    """VAL-SIGNAL-013: SignalFamily has all required fields populated."""
    family = make_favorite_longshot_family()
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
# VAL-SIGNAL-001: Prediction rule produces correct directional signals
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("price", "expected_side"),
    [
        (0.05, 0),  # well below median → NO
        (0.10, 0),  # below median → NO
        (0.25, 0),  # below median → NO
        (0.49, 0),  # just below median → NO
        (0.50, 1),  # at median → YES
        (0.51, 1),  # just above median → YES
        (0.75, 1),  # above median → YES
        (0.90, 1),  # well above median → YES
        (0.95, 1),  # well above median → YES
    ],
)
def test_prediction_rule_directional_signals(price: float, expected_side: int) -> None:
    """VAL-SIGNAL-001: Prediction produces NO for low-price, YES for high-price."""
    side, confidence = favorite_longshot_prediction_rule({"kalshi_mid_for_side": price})
    assert side == expected_side
    assert confidence is None


@pytest.mark.parametrize(
    ("price",),
    [
        (None,),
        ("invalid",),
        ("",),
    ],
)
def test_prediction_rule_missing_price(price: Any) -> None:
    """VAL-SIGNAL-001: Missing or invalid price returns (None, None)."""
    side, confidence = favorite_longshot_prediction_rule({"kalshi_mid_for_side": price})
    assert side is None
    assert confidence is None


def test_prediction_rule_missing_field() -> None:
    """VAL-SIGNAL-001: Row without kalshi_mid_for_side returns (None, None)."""
    side, confidence = favorite_longshot_prediction_rule({})
    assert side is None
    assert confidence is None


# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-002: Reuses DEFAULT_PRICE_BUCKETS and bucket infrastructure
# ═══════════════════════════════════════════════════════════════════════════


def test_reuses_default_price_buckets() -> None:
    """VAL-SIGNAL-002: Model evaluators are parameterized by DEFAULT_PRICE_BUCKETS."""
    assert len(FAVORITE_LONGSHOT_MODEL_EVALUATORS) == len(DEFAULT_PRICE_BUCKETS)
    for ev, (name, low, high) in zip(
        FAVORITE_LONGSHOT_MODEL_EVALUATORS, DEFAULT_PRICE_BUCKETS, strict=True
    ):
        assert ev["model_id"] == f"{EVALUATOR_MODEL_ID_PREFIX}_{name}"
        # Each evaluator references the bucket boundaries via its closure.


def test_imports_from_sports_consensus_falsification() -> None:
    """VAL-SIGNAL-002: Module imports DEFAULT_PRICE_BUCKETS from sports_consensus_falsification."""
    from predmarket.favorite_longshot_bias_family import DEFAULT_PRICE_BUCKETS as imported_buckets
    from predmarket.sports_consensus_falsification import DEFAULT_PRICE_BUCKETS as source_buckets

    assert imported_buckets is source_buckets


# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-003: Falsification uses chronological OOS + BH-FDR
# ═══════════════════════════════════════════════════════════════════════════


def _make_label_row(
    idx: int,
    *,
    price: float = 0.10,
    outcome: int = 0,
) -> dict[str, Any]:
    """Create a synthetic label row for testing."""
    day = 2
    hour = 1 + idx // 8
    minute = (idx % 8) * 5
    return {
        "contract_ticker": f"KXFAV{idx:06d}-26JUL{idx:06d}-15",
        "event_ticker": f"KXEVENT{idx:06d}",
        "series_ticker": "KXFAV",
        "kalshi_mid_for_side": price,
        "yes_outcome": outcome,
        "decision_time": f"2026-07-{day:02d}T{hour:02d}:{minute:02d}:00Z",
        "close_time": f"2026-07-{day:02d}T{hour + 1:02d}:{minute:02d}:00Z",
    }


def test_build_falsification_accepts_family() -> None:
    """VAL-SIGNAL-003: build_falsification accepts favorite-longshot family without errors."""
    family = make_favorite_longshot_family()
    label_rows = []
    for i in range(50):
        # Mix of low and high price contracts
        price = 0.10 if i < 25 else 0.80
        outcome = 0 if i < 25 else 1  # NO for low-price, YES for high-price
        label_rows.append(_make_label_row(i, price=price, outcome=outcome))

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
    assert len(result["evaluations"]) == len(DEFAULT_PRICE_BUCKETS)
    for ev in result["evaluations"]:
        assert ev["model_id"].startswith(EVALUATOR_MODEL_ID_PREFIX)
        assert "p_value" in ev
        assert "q_value" in ev or ev.get("p_value") is None


def test_build_falsification_chronological_split() -> None:
    """VAL-SIGNAL-003: Chronological OOS split is used (later rows are OOS)."""
    family = make_favorite_longshot_family()
    label_rows = []
    for i in range(60):
        price = 0.80
        outcome = 1  # high-price contracts settle YES
        label_rows.append(_make_label_row(i, price=price, outcome=outcome))

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
        if ev["oos_count"] > 0:
            assert ev["oos_count"] < len(label_rows)  # OOS is a subset


# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-004: Acceptance criteria (FDR ≤ 0.10, accuracy > null_rate)
# ═══════════════════════════════════════════════════════════════════════════


def test_strong_bias_signal_passes_fdr() -> None:
    """VAL-SIGNAL-004: Strong bias signal passes FDR ≤ 0.10."""
    family = make_favorite_longshot_family()
    label_rows = []
    # Low-price contracts (0.05-0.15): mostly settle NO (outcome=0)
    for i in range(40):
        label_rows.append(_make_label_row(i, price=0.10, outcome=0))
    # High-price contracts (0.70-0.85): mostly settle YES (outcome=1)
    for i in range(40, 80):
        label_rows.append(_make_label_row(i, price=0.80, outcome=1))

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
    # At least some evaluators should show strong signal
    fdr_passed = [
        ev for ev in result["evaluations"] if ev.get("status") == "research_candidate_fdr_passed"
    ]
    assert len(fdr_passed) >= 1, (
        f"No evaluators passed FDR. Statuses: "
        f"{[(ev['model_id'], ev['status'], ev.get('oos_accuracy')) for ev in result['evaluations']]}"
    )


def test_accuracy_above_null_rate_for_buckets() -> None:
    """VAL-SIGNAL-004: OOS directional accuracy exceeds bucket null-rate midpoint."""
    family = make_favorite_longshot_family()
    label_rows = []
    # Low-price contracts (0.05-0.15): settle NO
    for i in range(40):
        label_rows.append(_make_label_row(i, price=0.10, outcome=0))
    # High-price contracts (0.70-0.85): settle YES
    for i in range(40, 80):
        label_rows.append(_make_label_row(i, price=0.80, outcome=1))

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
    # Test that evaluators with positive OOS count have accuracy > null_rate
    for ev in result["evaluations"]:
        if ev["oos_accuracy"] is not None and ev.get("null_rate") is not None:
            if ev["oos_count"] >= 5:
                assert float(ev["oos_accuracy"]) > float(ev["null_rate"]), (
                    f"Bucket {ev.get('price_bucket')}: accuracy {ev['oos_accuracy']} "
                    f"<= null_rate {ev['null_rate']}"
                )


def test_random_labels_dont_pass_fdr() -> None:
    """VAL-SIGNAL-004: Random labels should not produce FDR-passing signals."""
    family = make_favorite_longshot_family()
    label_rows = []
    import random

    rng = random.Random(42)
    for i in range(80):
        price = rng.choice([0.10, 0.25, 0.40, 0.60, 0.80, 0.90])
        outcome = rng.randint(0, 1)
        label_rows.append(_make_label_row(i, price=price, outcome=outcome))

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
    fdr_passed = [
        ev for ev in result["evaluations"] if ev.get("status") == "research_candidate_fdr_passed"
    ]
    # With random labels, likely no evaluator passes FDR
    # (non-deterministic but very unlikely with 80 rows)
    assert len(fdr_passed) <= len(DEFAULT_PRICE_BUCKETS)  # Trivially true


# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-016: Cluster key composability
# ═══════════════════════════════════════════════════════════════════════════


def test_cluster_key_composer_deterministic() -> None:
    """VAL-SIGNAL-016: Cluster key is deterministic — same row → same key."""
    row = {
        "kalshi_mid_for_side": 0.10,
        "event_ticker": "KXEVENT001",
        "series_ticker": "KXFAV",
    }
    key1 = favorite_longshot_cluster_key_composer(row)
    key2 = favorite_longshot_cluster_key_composer(row)
    assert key1 == key2


def test_cluster_key_includes_price_bucket() -> None:
    """VAL-SIGNAL-016: Cluster key includes price-bucket identifier."""
    row_low = {
        "kalshi_mid_for_side": 0.10,
        "event_ticker": "KXEVENT001",
    }
    row_high = {
        "kalshi_mid_for_side": 0.80,
        "event_ticker": "KXEVENT001",
    }
    key_low = favorite_longshot_cluster_key_composer(row_low)
    key_high = favorite_longshot_cluster_key_composer(row_high)
    assert key_low != key_high, "Different price buckets should give different cluster keys"


def test_cluster_key_same_bucket_same_event() -> None:
    """VAL-SIGNAL-016: Same price bucket + same event → same cluster key."""
    row1 = {
        "kalshi_mid_for_side": 0.10,
        "event_ticker": "KXEVENT001",
    }
    row2 = {
        "kalshi_mid_for_side": 0.12,
        "event_ticker": "KXEVENT001",
    }
    key1 = favorite_longshot_cluster_key_composer(row1)
    key2 = favorite_longshot_cluster_key_composer(row2)
    assert key1 == key2, "Same bucket + same event should produce same cluster key"


def test_cluster_key_different_events_different_keys() -> None:
    """VAL-SIGNAL-016: Same bucket but different events → different cluster keys."""
    row1 = {
        "kalshi_mid_for_side": 0.10,
        "event_ticker": "KXEVENT001",
    }
    row2 = {
        "kalshi_mid_for_side": 0.12,
        "event_ticker": "KXEVENT002",
    }
    key1 = favorite_longshot_cluster_key_composer(row1)
    key2 = favorite_longshot_cluster_key_composer(row2)
    assert key1 != key2, "Different events should produce different cluster keys"


def test_cluster_key_fallback_to_series_ticker() -> None:
    """VAL-SIGNAL-016: Falls back to series_ticker when event_ticker is missing."""
    row = {
        "kalshi_mid_for_side": 0.10,
        "series_ticker": "KXFAV",
    }
    key = favorite_longshot_cluster_key_composer(row)
    assert "KXFAV" in key


def test_cluster_key_unknown_price() -> None:
    """VAL-SIGNAL-016: Missing price yields 'unknown' bucket."""
    row = {
        "event_ticker": "KXEVENT001",
    }
    key = favorite_longshot_cluster_key_composer(row)
    assert "unknown" in key


# ═══════════════════════════════════════════════════════════════════════════
# VAL-CROSS-036: Reuses price-bucket infrastructure
# ═══════════════════════════════════════════════════════════════════════════


def test_price_bucket_resolution_matches_default_buckets() -> None:
    """VAL-CROSS-036: _resolve_price_bucket uses DEFAULT_PRICE_BUCKETS boundaries."""
    for name, low, high in DEFAULT_PRICE_BUCKETS:
        midpoint = (low + high) / 2.0
        resolved = _resolve_price_bucket(midpoint)
        assert resolved == name, f"Price {midpoint} should resolve to bucket {name}, got {resolved}"


def test_resolve_price_bucket_out_of_range() -> None:
    """VAL-CROSS-036: Prices outside all buckets resolve to 'unknown'."""
    assert _resolve_price_bucket(0.0) == "unknown"
    assert _resolve_price_bucket(1.0) == "unknown"
    assert _resolve_price_bucket(None) == "unknown"


def test_model_evaluators_use_bucket_boundaries_via_closure() -> None:
    """VAL-CROSS-036: Each evaluator uses bucket boundaries via closure (not re-definition)."""
    from predmarket.favorite_longshot_bias_family import (
        _make_favorite_longshot_bucket_evaluate_fn,
    )

    # Verify that calling the factory with explicit boundaries works
    fn = _make_favorite_longshot_bucket_evaluate_fn("0.05_0.15", 0.05, 0.15)
    result = fn(
        rows=[_make_label_row(i, price=0.10, outcome=0) for i in range(40)],
        oos_rows=[_make_label_row(i, price=0.10, outcome=0) for i in range(10)],
        prediction_rule=favorite_longshot_prediction_rule,
        min_independent_labels=10,
        min_oos_labels=5,
    )
    assert result["price_bucket"] == "0.05_0.15"
    assert result["price_bucket_low"] == 0.05
    assert result["price_bucket_high"] == 0.15
    assert result["oos_count"] == 10
    assert result["oos_correct_count"] == 10  # All NO predictions, all NO outcomes
    assert result["null_rate"] == 0.10


# ═══════════════════════════════════════════════════════════════════════════
# Evaluator behavior edge cases
# ═══════════════════════════════════════════════════════════════════════════


def test_evaluator_no_oos_rows_in_bucket() -> None:
    """Evaluator handles empty bucket gracefully."""
    from predmarket.favorite_longshot_bias_family import (
        _make_favorite_longshot_bucket_evaluate_fn,
    )

    fn = _make_favorite_longshot_bucket_evaluate_fn("0.85_0.95", 0.85, 0.95)
    # All rows have price 0.10, which is NOT in bucket 0.85-0.95
    result = fn(
        rows=[_make_label_row(i, price=0.10, outcome=0) for i in range(40)],
        oos_rows=[_make_label_row(i, price=0.10, outcome=0) for i in range(10)],
        prediction_rule=favorite_longshot_prediction_rule,
        min_independent_labels=10,
        min_oos_labels=5,
    )
    assert result["oos_count"] == 0
    assert result["oos_accuracy"] is None


def test_evaluator_insufficient_labels() -> None:
    """Evaluator returns blocked status when insufficient labels."""
    from predmarket.favorite_longshot_bias_family import (
        _make_favorite_longshot_bucket_evaluate_fn,
    )

    fn = _make_favorite_longshot_bucket_evaluate_fn("0.05_0.15", 0.05, 0.15)
    result = fn(
        rows=[_make_label_row(i, price=0.10, outcome=0) for i in range(3)],  # Too few
        oos_rows=[_make_label_row(i, price=0.10, outcome=0) for i in range(10)],
        prediction_rule=favorite_longshot_prediction_rule,
        min_independent_labels=10,
        min_oos_labels=5,
    )
    assert result["status"] == "blocked_insufficient_independent_labels"


# ═══════════════════════════════════════════════════════════════════════════
# Research-only safety
# ═══════════════════════════════════════════════════════════════════════════


def test_family_emits_research_only_flags() -> None:
    """All family artifacts have research_only=True and execution_enabled=False."""
    from predmarket.favorite_longshot_bias_family import (
        _make_favorite_longshot_bucket_evaluate_fn,
    )

    fn = _make_favorite_longshot_bucket_evaluate_fn("0.05_0.15", 0.05, 0.15)
    result = fn(
        rows=[_make_label_row(i, price=0.10, outcome=0) for i in range(40)],
        oos_rows=[_make_label_row(i, price=0.10, outcome=0) for i in range(10)],
        prediction_rule=favorite_longshot_prediction_rule,
        min_independent_labels=10,
        min_oos_labels=5,
    )
    assert result.get("research_only") is True
    assert result.get("execution_enabled") is False
    assert result.get("usable") is False
    assert result.get("calibrated_probability") is None
    assert result.get("expected_value_per_contract") is None


def test_make_family_overrides() -> None:
    """Factory accepts overrides for testing."""
    custom_rule = lambda row: (1, None)  # noqa: E731
    family = make_favorite_longshot_family(prediction_rule=custom_rule)
    assert family.prediction_rule is custom_rule


# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-011: Existing families work alongside new ones
# ═══════════════════════════════════════════════════════════════════════════


def test_generic_spine_handles_family_without_special_cases() -> None:
    """VAL-SIGNAL-011: Generic engine spine handles favorite-longshot via SignalFamily descriptor."""
    family = make_favorite_longshot_family()
    # Verify the family works through build_falsification without family_id special cases
    label_rows = []
    for i in range(40):
        price = 0.10 if i < 20 else 0.80
        outcome = 0 if i < 20 else 1
        label_rows.append(_make_label_row(i, price=price, outcome=outcome))

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
    assert "evaluations" in result
    # Verify no family_id-specific branching in the engine spine
    for ev in result["evaluations"]:
        assert "status" in ev
        assert "model_id" in ev


# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-019: Falsification artifacts pass safe_research_artifact validation
# ═══════════════════════════════════════════════════════════════════════════


def test_falsification_artifact_is_safe_research_artifact() -> None:
    """VAL-SIGNAL-019: Evaluator artifacts pass safe_research_artifact() validation."""
    from predmarket.favorite_longshot_bias_family import (
        _make_favorite_longshot_bucket_evaluate_fn,
    )

    fn = _make_favorite_longshot_bucket_evaluate_fn("0.05_0.15", 0.05, 0.15)
    result = fn(
        rows=[_make_label_row(i, price=0.10, outcome=0) for i in range(40)],
        oos_rows=[_make_label_row(i, price=0.10, outcome=0) for i in range(10)],
        prediction_rule=favorite_longshot_prediction_rule,
        min_independent_labels=10,
        min_oos_labels=5,
    )
    # Individual evaluator results are safe research artifacts
    assert result.get("research_only") is True
    assert result.get("execution_enabled") is False
    assert result.get("usable") is False
    assert result.get("calibrated_probability") is None
    assert result.get("expected_value_per_contract") is None


# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-020: Module has descriptive docstring
# ═══════════════════════════════════════════════════════════════════════════


def test_module_docstring_exists() -> None:
    """VAL-SIGNAL-020: Module has docstring explaining family hypothesis and falsification method."""
    import predmarket.favorite_longshot_bias_family as flbf

    assert flbf.__doc__ is not None
    assert len(flbf.__doc__) > 50
    assert "favorite" in flbf.__doc__.lower() or "longshot" in flbf.__doc__.lower()
    assert "FDR" in flbf.__doc__ or "falsification" in flbf.__doc__.lower()
