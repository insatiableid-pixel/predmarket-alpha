"""Tests for kalshi_sports_proxy_feature_model_falsification.py.

TDD: synthetic sports labels in tmp_path, assert promotion AND block branches.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "kalshi_sports_proxy_feature_model_falsification.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_model_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_sports_proxy_feature_model_falsification", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def safe_packet(rows=None, **overrides):
    payload = {
        "schema_version": 1,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "rows": rows or [],
        "safety": {
            "research_only": True,
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
            "staking_or_sizing_guidance": False,
        },
    }
    payload.update(overrides)
    return payload


def sports_label_row(
    idx: int,
    *,
    ticker: str | None = None,
    predicted_side: str = "yes",
    mlb_platform_predicted_side: str | None = None,
    mlb_platform_model_probability: float | None = None,
    outcome: int = 1,
    league: str = "MLB",
):
    hour = 1 + idx // 8
    minute = (idx % 8) * 5
    return {
        "contract_ticker": ticker or f"KXMLBGAME-26JUL02{idx:04d}-CWSNYY",
        "event_ticker": f"KXMLBGAME-26JUL02{idx:04d}",
        "series_ticker": "KXMLBGAME",
        "league": league,
        "home_code": "NYY",
        "away_code": "CWS",
        "selected_code": "NYY",
        "win_probability": 0.65,
        "predicted_side": predicted_side,
        "mlb_platform_model_probability": mlb_platform_model_probability,
        "mlb_platform_predicted_side": mlb_platform_predicted_side,
        "mlb_platform_model_status": "mlb_platform_model_ready"
        if mlb_platform_predicted_side
        else "mlb_platform_model_not_matched",
        "mlb_platform_model_id": "mlb_platform_slate_v1" if mlb_platform_predicted_side else None,
        "yes_ask": 0.55,
        "yes_bid": 0.45,
        "yes_outcome": outcome,
        "decision_time": f"2026-07-02T{hour:02d}:{minute:02d}:00Z",
        "close_time": f"2026-07-02T{hour + 1:02d}:{minute:02d}:00Z",
        "settled_time": f"2026-07-02T{hour + 1:02d}:{minute + 1:02d}:00Z",
        "label_status": "labeled_from_public_kalshi_settled_market",
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


# ---- VAL-SGATE-001: Harness accepts family model-evaluator list + prediction rule ----


def test_falsification_accepts_sports_family_descriptor(tmp_path: Path) -> None:
    """Sports falsification runs sports-specific model evaluators through generic evaluate_models."""
    module = load_model_module()
    label_dir = tmp_path / "labels"
    rows = [sports_label_row(idx, predicted_side="yes", outcome=1) for idx in range(20)]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))

    report = module.build_sports_proxy_feature_model_falsification(
        label_dir=label_dir,
        generated_utc="2026-07-02T01:30:00Z",
        min_independent_labels=12,
        min_oos_labels=5,
        fdr_alpha=0.10,
    )

    # The evaluations should contain the sports strength model evaluator
    evaluator_ids = {item["model_id"] for item in report["evaluations"]}
    assert "strength_win_prob_directional_accuracy" in evaluator_ids, (
        f"Expected strength_win_prob_directional_accuracy in evaluations, got {evaluator_ids}"
    )
    assert "mlb_platform_model_directional_accuracy" in evaluator_ids
    # Verify it runs through the generic evaluate_models flow (has OOS scoring)
    strength_eval = next(
        item
        for item in report["evaluations"]
        if item["model_id"] == "strength_win_prob_directional_accuracy"
    )
    assert strength_eval["oos_count"] > 0


def test_falsification_evaluates_mlb_platform_model_as_separate_candidate(
    tmp_path: Path,
) -> None:
    """The optional MLB-platform model competes beside the greenfield strength model."""
    module = load_model_module()
    label_dir = tmp_path / "labels"
    rows = [
        sports_label_row(
            idx,
            predicted_side="no",
            mlb_platform_predicted_side="yes",
            mlb_platform_model_probability=0.72,
            outcome=1,
        )
        for idx in range(20)
    ]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))

    report = module.build_sports_proxy_feature_model_falsification(
        label_dir=label_dir,
        generated_utc="2026-07-02T01:30:00Z",
        min_independent_labels=12,
        min_oos_labels=5,
        fdr_alpha=0.10,
    )

    strength_eval = next(
        item
        for item in report["evaluations"]
        if item["model_id"] == "strength_win_prob_directional_accuracy"
    )
    mlb_eval = next(
        item
        for item in report["evaluations"]
        if item["model_id"] == "mlb_platform_model_directional_accuracy"
    )
    assert strength_eval["oos_accuracy"] == 0.0
    assert mlb_eval["oos_accuracy"] == 1.0
    assert mlb_eval["status"] == "research_candidate_fdr_passed"


# ---- VAL-SGATE-002: Collapse by contract_ticker ----


def test_falsification_collapses_duplicate_contract_labels(tmp_path: Path) -> None:
    """Sports labels collapse repeats by contract_ticker, keeping earliest decision_time."""
    module = load_model_module()
    label_dir = tmp_path / "labels"
    rows = [
        sports_label_row(0, ticker="KXMLBGAME-26JUL020000-CWSNYY", predicted_side="yes", outcome=1),
        sports_label_row(1, ticker="KXMLBGAME-26JUL020000-CWSNYY", predicted_side="no", outcome=0),
        sports_label_row(2, ticker="KXMLBGAME-26JUL020001-BOSNYY", predicted_side="yes", outcome=1),
    ]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))

    report = module.build_sports_proxy_feature_model_falsification(
        label_dir=label_dir,
        generated_utc="2026-07-02T01:30:00Z",
        min_independent_labels=3,
        min_oos_labels=1,
    )

    assert report["summary"]["valid_label_row_count"] == 3
    assert report["summary"]["independent_contract_label_count"] == 2
    assert report["summary"]["duplicate_label_row_count"] == 1
    assert (
        report["status"]
        == "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels"
    )


# ---- VAL-SGATE-003: Chronological OOS split ----


def test_falsification_chronological_oos_split(tmp_path: Path) -> None:
    """Chronological OOS split with test_fraction=0.30 applied to sports labels."""
    module = load_model_module()
    label_dir = tmp_path / "labels"
    rows = [sports_label_row(idx, predicted_side="yes", outcome=1) for idx in range(20)]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))

    report = module.build_sports_proxy_feature_model_falsification(
        label_dir=label_dir,
        generated_utc="2026-07-02T01:30:00Z",
        min_independent_labels=12,
        min_oos_labels=5,
        test_fraction=0.30,
        fdr_alpha=0.10,
    )

    strength_eval = next(
        item
        for item in report["evaluations"]
        if item["model_id"] == "strength_win_prob_directional_accuracy"
    )
    # With 20 independent rows and test_fraction=0.30: oos_count = max(1, ceil(20*0.30)) = 6
    assert strength_eval["oos_count"] == 6
    assert strength_eval["independent_label_count"] == 20


# ---- VAL-SGATE-004: Directional OOS accuracy ----


def test_falsification_directional_oos_accuracy(tmp_path: Path) -> None:
    """Directional OOS accuracy computed against sports prediction rule."""
    module = load_model_module()
    label_dir = tmp_path / "labels"
    # All predictions correct (predicted_side matches outcome)
    rows = [sports_label_row(idx, predicted_side="yes", outcome=1) for idx in range(20)]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))

    report = module.build_sports_proxy_feature_model_falsification(
        label_dir=label_dir,
        generated_utc="2026-07-02T01:30:00Z",
        min_independent_labels=12,
        min_oos_labels=5,
        fdr_alpha=0.10,
    )

    strength_eval = next(
        item
        for item in report["evaluations"]
        if item["model_id"] == "strength_win_prob_directional_accuracy"
    )
    assert strength_eval["oos_accuracy"] == 1.0
    assert strength_eval["oos_correct_count"] == strength_eval["oos_count"]


# ---- VAL-SGATE-005: Binomial survival unchanged ----


def test_binomial_survival_unchanged(tmp_path: Path) -> None:
    """binomial_survival is the generic shared helper, producing identical values."""
    module = load_model_module()
    # Access the shared module through the loaded module's sys.path
    import sys as _sys

    _sys.path.insert(0, str(Path(SCRIPT_PATH).parents[1] / "scripts"))
    from kalshi_falsification_replay_shared import binomial_survival

    # Characterization: wins=12/trials=12 -> tiny p; wins=3/trials=10 -> p well above 0.10
    p_all_correct = binomial_survival(12, 12, 0.5)
    assert 0 < p_all_correct < 0.001, f"Expected tiny p for 12/12, got {p_all_correct}"

    p_mediocre = binomial_survival(3, 10, 0.5)
    assert p_mediocre > 0.10, f"Expected p > 0.10 for 3/10, got {p_mediocre}"


# ---- VAL-SGATE-006: Benjamini-Hochberg unchanged ----


def test_benjamini_hochberg_unchanged(tmp_path: Path) -> None:
    """Benjamini-Hochberg is the generic shared helper."""
    module = load_model_module()
    import sys as _sys

    _sys.path.insert(0, str(Path(SCRIPT_PATH).parents[1] / "scripts"))
    from kalshi_falsification_replay_shared import benjamini_hochberg

    indexed = [(0, 0.001), (1, 0.03), (2, 0.12)]
    result = benjamini_hochberg(indexed)
    # Smallest rank gets corrected p*count/rank
    assert result[0] <= 0.003
    assert result[2] > result[0]


# ---- VAL-SGATE-007: Threshold constants are shared ----


def test_threshold_constants_shared(tmp_path: Path) -> None:
    """Shared defaults: min_independent_labels=30, min_oos_labels=10, test_fraction=0.30, fdr_alpha=0.10."""
    module = load_model_module()
    assert module.DEFAULT_MIN_INDEPENDENT_LABELS == 30
    assert module.DEFAULT_MIN_OOS_LABELS == 10
    assert module.DEFAULT_TEST_FRACTION == 0.30
    assert module.DEFAULT_FDR_ALPHA == 0.10
    # 29 independent labels blocks
    label_dir = tmp_path / "labels"
    rows = [sports_label_row(idx, predicted_side="yes", outcome=1) for idx in range(29)]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))

    report = module.build_sports_proxy_feature_model_falsification(
        label_dir=label_dir,
        generated_utc="2026-07-02T01:30:00Z",
        min_independent_labels=30,
    )

    assert (
        report["status"]
        == "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels"
    )
    gates = {g["name"]: g for g in report["gates"]}
    assert gates["independent_label_minimum"]["status"] == "blocked"


# ---- VAL-SGATE-008: Significant sports model promoted ----


def test_significant_sports_model_promoted(tmp_path: Path) -> None:
    """Statistically significant sports model promoted to research_candidate_fdr_passed."""
    module = load_model_module()
    label_dir = tmp_path / "labels"
    # All correct predictions -> strong significance
    rows = [sports_label_row(idx, predicted_side="yes", outcome=1) for idx in range(40)]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))

    report = module.build_sports_proxy_feature_model_falsification(
        label_dir=label_dir,
        generated_utc="2026-07-02T01:30:00Z",
        min_independent_labels=30,
        min_oos_labels=10,
        fdr_alpha=0.10,
    )

    assert report["summary"]["research_candidate_count"] == 1
    assert (
        report["status"]
        == "sports_proxy_feature_model_falsification_ready_with_research_candidates"
    )
    strength_eval = next(
        item
        for item in report["evaluations"]
        if item["model_id"] == "strength_win_prob_directional_accuracy"
    )
    assert strength_eval["status"] == "research_candidate_fdr_passed"
    assert strength_eval["q_value"] <= 0.10
    assert strength_eval["oos_accuracy"] > 0.5


# ---- VAL-SGATE-009: Below-random model NOT promoted ----


def test_below_random_sports_model_not_promoted(tmp_path: Path) -> None:
    """Below-random sports model is NOT promoted."""
    module = load_model_module()
    label_dir = tmp_path / "labels"
    # All predictions wrong -> below random
    rows = [sports_label_row(idx, predicted_side="yes", outcome=0) for idx in range(40)]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))

    report = module.build_sports_proxy_feature_model_falsification(
        label_dir=label_dir,
        generated_utc="2026-07-02T01:30:00Z",
        min_independent_labels=30,
        min_oos_labels=10,
        fdr_alpha=0.10,
    )

    assert report["summary"]["research_candidate_count"] == 0
    assert (
        report["status"] == "sports_proxy_feature_model_falsification_ready_no_research_candidates"
    )
    strength_eval = next(
        item
        for item in report["evaluations"]
        if item["model_id"] == "strength_win_prob_directional_accuracy"
    )
    assert strength_eval["status"] != "research_candidate_fdr_passed"


# ---- VAL-SGATE-010: Promoted row stays research-only ----


def test_promoted_evaluation_row_research_only(tmp_path: Path) -> None:
    """Promoted sports evaluation row keeps usable=False, calibrated_probability=None, EV=None."""
    module = load_model_module()
    label_dir = tmp_path / "labels"
    rows = [sports_label_row(idx, predicted_side="yes", outcome=1) for idx in range(40)]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))

    report = module.build_sports_proxy_feature_model_falsification(
        label_dir=label_dir,
        generated_utc="2026-07-02T01:30:00Z",
        min_independent_labels=30,
        min_oos_labels=10,
        fdr_alpha=0.10,
    )

    strength_eval = next(
        item
        for item in report["evaluations"]
        if item["model_id"] == "strength_win_prob_directional_accuracy"
    )
    assert strength_eval["usable"] is False
    assert strength_eval["calibrated_probability"] is None
    assert strength_eval["expected_value_per_contract"] is None
    gates = {g["name"]: g for g in report["gates"]}
    assert gates["no_probability_ev_or_execution_claims"]["status"] == "pass"


# ---- Writer emits latest outputs ----


def test_sports_falsification_writer_emits_latest(tmp_path: Path) -> None:
    """Writer emits latest-kalshi-sports-proxy-feature-model-falsification.* pointers."""
    module = load_model_module()
    module.MACRO_DIR = tmp_path / "macro"
    label_dir = tmp_path / "labels"
    write_json(label_dir / "labels.json", safe_packet(rows=[sports_label_row(0)]))
    report = module.build_sports_proxy_feature_model_falsification(
        label_dir=label_dir,
        generated_utc="2026-07-02T01:30:00Z",
    )

    paths = module.write_sports_proxy_feature_model_falsification(report, out_dir=tmp_path / "out")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    assert Path(paths["latest_json_path"]).exists()
    assert "Kalshi Sports Proxy Feature Model Falsification" in Path(
        paths["markdown_path"]
    ).read_text(encoding="utf-8")


# ---- Makefile target ----


def test_sports_falsification_makefile_target_exists() -> None:
    """Makefile has kalshi-sports-proxy-feature-model-falsification target."""
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    assert "kalshi-sports-proxy-feature-model-falsification" in makefile
    assert "scripts/kalshi_sports_proxy_feature_model_falsification.py" in makefile


# ---- Edge: Labels missing ----


def test_falsification_blocks_when_labels_missing(tmp_path: Path) -> None:
    """Blocked status when labels directory is missing."""
    module = load_model_module()
    report = module.build_sports_proxy_feature_model_falsification(
        label_dir=tmp_path / "missing-labels",
        generated_utc="2026-07-02T01:30:00Z",
    )
    assert report["status"] == "sports_proxy_feature_model_falsification_blocked_missing_labels"
    assert report["summary"]["independent_contract_label_count"] == 0
    assert report["safety"]["market_execution"] is False
    assert report["research_only"] is True
    assert report["execution_enabled"] is False


# ---- Research-only safety ----


def test_falsification_report_safety_flags(tmp_path: Path) -> None:
    """Falsification report carries research_only=true, execution_enabled=false, etc."""
    module = load_model_module()
    label_dir = tmp_path / "labels"
    rows = [sports_label_row(0)]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))

    report = module.build_sports_proxy_feature_model_falsification(
        label_dir=label_dir,
        generated_utc="2026-07-02T01:30:00Z",
    )

    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["market_execution"] is False
    assert report["account_or_order_paths"] is False
    assert report["database_writes"] is False
