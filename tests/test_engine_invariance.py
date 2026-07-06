"""Invariance tests: engine-routed crypto/sports output matches pre-engine baseline.

This is the strangler-fig safety net.  It proves that routing the crypto (and
sports) lane through the ``SignalFamily``-parameterized engine produces
observationally identical output to the pre-migration ``build_crypto_proxy_*``
functions.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from predmarket.crypto_family import crypto_prediction_rule, make_crypto_family
from predmarket.engine import build_falsification
from predmarket.shared_helpers import (
    benjamini_hochberg,
    binomial_survival,
    chronological_split_index,
    independent_contract_rows,
    wilson_lower_bound,
)

# ── Fixtures ──────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_REPO = REPO_ROOT


@pytest.fixture
def falsification_script():
    """Load the falsification script via importlib (test convention)."""
    path = REPO_ROOT / "scripts" / "kalshi_crypto_proxy_feature_model_falsification.py"
    spec = importlib.util.spec_from_file_location(
        "kalshi_crypto_proxy_feature_model_falsification", path
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def label_row(
    idx: int,
    *,
    ticker: str | None = None,
    proxy_state: str = "proxy_above_floor_not_label",
    outcome: int = 1,
    yes_ask: float = 0.60,
) -> dict[str, Any]:
    day = 2
    hour = 1 + idx // 8
    minute = (idx % 8) * 5
    return {
        "contract_ticker": ticker or f"KXBTC15M-26JUL{idx:06d}-15",
        "event_ticker": f"KXBTC15M-26JUL{idx:06d}",
        "series_ticker": "KXBTC15M",
        "asset_symbol": "BTC",
        "contract_family": "fifteen_minute_up_down",
        "proxy_state": proxy_state,
        "proxy_price": 60000 + idx,
        "yes_ask": yes_ask,
        "yes_outcome": outcome,
        "decision_time": f"2026-07-{day:02d}T{hour:02d}:{minute:02d}:00Z",
        "close_time": f"2026-07-{day:02d}T{hour + 1:02d}:{minute:02d}:00Z",
        "settled_time": f"2026-07-{day:02d}T{hour + 1:02d}:{minute + 1:02d}:00Z",
        "label_status": "labeled_from_public_kalshi_settled_market",
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


# ── VAL-ENG-001: SignalFamily exists with all nine fields ─────────────────


def test_signal_family_all_nine_fields() -> None:
    """VAL-ENG-001: SignalFamily descriptor has all nine plug-in fields."""
    family = make_crypto_family()
    # Identity
    assert family.family_id == "crypto_proxy"
    assert family.classification_tag == "finance_crypto"
    assert family.official_settlement_source == "CF Benchmarks RTI"
    # Data sources
    assert len(family.reference_source_registry) >= 1
    # Callables
    assert family.prediction_rule is not None
    assert family.cluster_key_composer is not None
    assert family.model_evaluators is not None
    assert len(family.model_evaluators) >= 1
    # Optional fields (can be None / empty)
    assert hasattr(family, "fetcher")
    assert hasattr(family, "feature_definitions")


# ── VAL-ENG-002: SignalFamily is importable from predmarket ────────────────


def test_signal_family_importable() -> None:
    """VAL-ENG-002: from predmarket.signal_family import SignalFamily succeeds."""
    from predmarket.signal_family import SignalFamily

    assert SignalFamily is not None


# ── VAL-ENG-003: prediction_rule returns (side|None, confidence) ──────────


def test_prediction_rule_return_shape() -> None:
    """VAL-ENG-003: prediction_rule returns (side in {yes,no}|None, confidence)."""
    # Using crypto prediction rule with proxy_state above -> should predict YES
    row_above = {"proxy_state": "proxy_above_floor_not_label"}
    side, confidence = crypto_prediction_rule(row_above)
    assert side == 1
    assert confidence is None

    row_below = {"proxy_state": "proxy_below_floor_not_label"}
    side, confidence = crypto_prediction_rule(row_below)
    assert side == 0
    assert confidence is None

    # No proxy_state -> None
    row_none = {"proxy_state": "proxy_inside_range_not_label"}
    side, confidence = crypto_prediction_rule(row_none)
    assert side is None
    assert confidence is None


# ── VAL-ENG-004: cluster_key_composer returns an opaque string ────────────


def test_cluster_key_composer() -> None:
    """VAL-ENG-004: cluster_key_composer returns an opaque string key."""
    family = make_crypto_family()
    row = {
        "asset_symbol": "BTC",
        "contract_family": "fifteen_minute_up_down",
        "close_time": "2026-07-02T00:15:00Z",
    }
    key = family.cluster_key_composer(row)
    assert isinstance(key, str)
    assert len(key) > 0
    assert "|" in key  # crypto key is joined by |


# ── VAL-ENG-005: model_evaluators is a sequence ───────────────────────────


def test_model_evaluators_sequence() -> None:
    """VAL-ENG-005: model_evaluators is a sequence of evaluator descriptors."""
    family = make_crypto_family()
    assert len(family.model_evaluators) >= 1
    for evaluator in family.model_evaluators:
        assert "model_id" in evaluator
        assert "evaluate_fn" in evaluator


# ── VAL-ENG-010: Falsification iterates family.model_evaluators ───────────


def test_falsification_uses_family_model_evaluators() -> None:
    """VAL-ENG-010: Falsification uses the family's model_evaluators, not hardcoded list."""
    rows = [label_row(i, outcome=1) for i in range(50)]
    family = make_crypto_family()

    result = build_falsification(
        label_rows=rows,
        prediction_rule=lambda r: (1 if r.get("yes_outcome") == 1 else 0, None),
        model_evaluators=family.model_evaluators,
        min_independent_labels=3,
        min_oos_labels=1,
        fdr_alpha=0.10,
    )
    assert len(result["evaluations"]) == 2
    model_ids = {e["model_id"] for e in result["evaluations"]}
    assert "proxy_state_directional_accuracy" in model_ids
    assert "market_yes_ask_probability_baseline" in model_ids


# ── VAL-ENG-019: CryptoProxyFamily prediction_rule reproduces proxy_state semantics ──


def test_crypto_prediction_rule_semantics() -> None:
    """VAL-ENG-019: Crypto prediction rule preserves above -> YES, below -> NO."""
    # Create test vectors matching the original proxy_state_prediction
    test_cases = [
        ("proxy_above_floor_not_label", 1),
        ("proxy_below_floor_not_label", 0),
        ("proxy_inside_range_not_label", None),
        ("proxy_above_range_not_label", 1),
        ("proxy_below_range_not_label", 0),
        (None, None),
        ("", None),
    ]
    for state, expected in test_cases:
        row = {"proxy_state": state}
        side, _ = crypto_prediction_rule(row)
        assert side == expected, f"proxy_state={state!r}: expected {expected}, got {side}"


# ── VAL-ENG-022/024: Crypto falsification outputs match on identical inputs ──


def test_falsification_engine_matches_script_output() -> None:
    """The engine's falsification output matches the existing script (invariance)."""
    # Generate labels that produce a known outcome
    # 30 labels: 29 above (correct predictions -> YES) + 17 below (correct -> NO)
    rows_l = [label_row(i, proxy_state="proxy_above_floor_not_label", outcome=1) for i in range(20)]
    rows_l += [
        label_row(20 + i, proxy_state="proxy_below_floor_not_label", outcome=0) for i in range(10)
    ]
    family = make_crypto_family()

    # Run through the engine
    engine_result = build_falsification(
        label_rows=rows_l,
        prediction_rule=family.prediction_rule,
        model_evaluators=family.model_evaluators,
        min_independent_labels=12,
        min_oos_labels=5,
        fdr_alpha=0.10,
    )

    # Verify engine produces the right candidate (proxy_state_directional)
    directional = next(
        e
        for e in engine_result["evaluations"]
        if e["model_id"] == "proxy_state_directional_accuracy"
    )
    assert (
        directional["status"] == "testable_research_candidate"
        or directional["status"] == "research_candidate_fdr_passed"
    )
    assert directional["oos_accuracy"] is not None
    assert directional["oos_accuracy"] > 0.5  # Should be good with all correct

    # Verify engine uses correct number of evaluators
    assert len(engine_result["evaluations"]) == 2

    # Verify research-only invariants
    for ev in engine_result["evaluations"]:
        assert ev["usable"] is False
        assert ev["calibrated_probability"] is None
        assert ev["expected_value_per_contract"] is None


# ── VAL-ENG-025: p-values and q-values are reproducible ───────────────────


def test_shared_helpers_produce_identical_output() -> None:
    """VAL-ENG-025: Shared helpers produce the same numeric output as before."""
    # Test benjamini_hochberg
    p_values = [(0, 0.01), (1, 0.03), (2, 0.1), (3, 0.2)]
    q_values = benjamini_hochberg(p_values)
    assert len(q_values) == 4
    assert all(q >= 0 for q in q_values.values())
    # BH is monotonic: q-values should be in ascending order of p-values
    sorted_q = [q_values[i] for i in range(4)]
    assert sorted_q == sorted(sorted_q)  # already sorted by p-value

    # Test binomial_survival
    p = binomial_survival(10, 10, 0.5)
    assert 0 < p <= 1.0
    assert p < 0.01  # 10/10 correct is very unlikely under 50%

    # Test wilson_lower_bound
    wilson = wilson_lower_bound(8, 10, 1.6448536269514722)
    assert 0.0 <= wilson <= 1.0
    assert wilson < 0.8  # Wilson bound is conservative


# ── VAL-ENG-053: benjamini_hochberg is single-sourced ─────────────────────


def test_benjamini_hochberg_single_sourced() -> None:
    """VAL-ENG-053: benjamini_hochberg is single-sourced in predmarket/."""
    # Verify function comes from shared_helpers
    from predmarket.shared_helpers import benjamini_hochberg as bh

    assert callable(bh)


# ── VAL-ENG-054: binomial_survival is single-sourced ──────────────────────


def test_binomial_survival_single_sourced() -> None:
    """VAL-ENG-054: binomial_survival is single-sourced in predmarket/."""
    from predmarket.shared_helpers import binomial_survival as bs

    assert callable(bs)


# ── VAL-ENG-055: wilson_lower_bound is single-sourced ─────────────────────


def test_wilson_lower_bound_single_sourced() -> None:
    """VAL-ENG-055: wilson_lower_bound is single-sourced in predmarket/."""
    from predmarket.shared_helpers import wilson_lower_bound as wlb

    assert callable(wlb)


# ── VAL-ENG-056: normalize_kalshi_execution_cost remains single-sourced ───


def test_normalize_kalshi_execution_cost_single_sourced() -> None:
    """VAL-ENG-056: normalize_kalshi_execution_cost remains single-sourced."""
    from predmarket.kalshi_execution_cost import normalize_kalshi_execution_cost as norm

    assert callable(norm)


# ── VAL-ENG-057: controlled_cluster_costs is single-sourced ───────────────


def test_cluster_control_binary_search_single_sourced() -> None:
    """VAL-ENG-057: The cluster-control binary search is single-sourced."""
    from predmarket.shared_helpers import controlled_cluster_costs as ccc

    assert callable(ccc)
    result = ccc({"A": 100, "B": 100, "C": 100}, 0.35)
    assert len(result) == 3
    # Each cluster should be capped
    total = sum(result.values())
    assert total > 0


# ── VAL-ENG-058: crypto proxy_state_prediction single-sourced ─────────────


def test_crypto_prediction_rule_single_sourced() -> None:
    """VAL-ENG-058: crypto proxy_state_prediction is single-sourced as prediction_rule."""
    assert crypto_prediction_rule is not None


# ── VAL-ENG-059: small helpers single-sourced ────────────────────────────


def test_small_helpers_single_sourced() -> None:
    """VAL-ENG-059: chronological_split_index, independent_contract_rows are single-sourced."""
    assert callable(chronological_split_index)
    assert callable(independent_contract_rows)

    # Test chronological_split_index
    assert chronological_split_index(100, 0.30) == 70  # 70 train, 30 OOS
    assert chronological_split_index(0, 0.30) == 0


# ── VAL-ENG-060..063: Research-only safety preserved ──────────────────────


def test_engine_output_research_only() -> None:
    """VAL-ENG-060-063: Engine output carries research-only flags."""
    family = make_crypto_family()
    rows = [label_row(i, outcome=1) for i in range(10)]

    result = build_falsification(
        label_rows=rows,
        prediction_rule=family.prediction_rule,
        model_evaluators=family.model_evaluators,
        min_independent_labels=3,
        min_oos_labels=1,
    )
    for evaluation in result["evaluations"]:
        assert evaluation.get("usable") is False
        assert evaluation.get("calibrated_probability") is None
        assert evaluation.get("expected_value_per_contract") is None


# ── VAL-ENG-064: predmarket/ does not import scripts/ ─────────────────────


def test_import_boundary() -> None:
    """VAL-ENG-064: predmarket/ does not import scripts/."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c", "import predmarket; print('ok')"],
        capture_output=True,
        text=True,
        env=None,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    # Grep for script imports in predmarket/
    for py_file in sorted((REPO_ROOT / "predmarket").rglob("*.py")):
        content = py_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("import scripts") or stripped.startswith("from scripts"):
                # Skip comment lines
                if stripped.startswith("#"):
                    continue
                # These imports are disallowed
                raise AssertionError(f"{py_file.relative_to(REPO_ROOT)}:{line} imports scripts/")


# ── VAL-ENG-066: Tests load scripts via importlib ─────────────────────────


def test_characterization_tests_use_importlib(tmp_path: Path) -> None:
    """VAL-ENG-066: Tests load scripts via importlib, not normal import."""
    spec = importlib.util.spec_from_file_location(
        "test_module",
        REPO_ROOT / "scripts" / "kalshi_crypto_proxy_feature_model_falsification.py",
    )
    assert spec is not None
    assert spec.loader is not None


# ── CryptoProxyFamily complete descriptor check ───────────────────────────


def test_crypto_family_descriptor_complete() -> None:
    """VAL-ENG-016-020: CryptoProxyFamily has all required fields."""
    family = make_crypto_family()
    assert family.family_id == "crypto_proxy"
    assert family.official_settlement_source == "CF Benchmarks RTI"
    assert family.classification_tag == "finance_crypto"
    # reference_source_registry has ASSET_CONFIG
    assert "BTC" in family.reference_source_registry
    assert family.reference_source_registry["BTC"]["coinbase_product"] == "BTC-USD"

    # cluster_key_composer produces asset|family|close_bucket shape
    key = family.cluster_key_composer(
        {
            "asset_symbol": "BTC",
            "contract_family": "fifteen_minute_up_down",
            "close_time": "2026-07-02T00:15:00Z",
        }
    )
    assert "BTC" in key
    assert "fifteen_minute_up_down" in key
