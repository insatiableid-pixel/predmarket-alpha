"""Tests for kalshi_sports_proxy_research_candidate_replay.py.

TDD: synthetic sports labels in tmp_path, assert calibration + replay math.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "kalshi_sports_proxy_research_candidate_replay.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_replay_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_sports_proxy_research_candidate_replay", SCRIPT_PATH
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


def model_report(*, research_candidate: bool = True, include_mlb_candidate: bool = False):
    status = (
        "research_candidate_fdr_passed" if research_candidate else "testable_research_candidate"
    )
    evaluations = [
        {
            "model_id": "strength_win_prob_directional_accuracy",
            "status": status,
            "independent_label_count": 40,
            "oos_count": 12,
            "oos_correct_count": 12 if research_candidate else 6,
            "oos_accuracy": 1.0 if research_candidate else 0.5,
            "p_value": 0.001,
            "q_value": 0.001,
            "usable": False,
            "calibrated_probability": None,
            "expected_value_per_contract": None,
        }
    ]
    if include_mlb_candidate:
        evaluations.append(
            {
                "model_id": "mlb_platform_model_directional_accuracy",
                "status": "research_candidate_fdr_passed",
                "independent_label_count": 40,
                "oos_count": 12,
                "oos_correct_count": 12,
                "oos_accuracy": 1.0,
                "p_value": 0.0001,
                "q_value": 0.0001,
                "usable": False,
                "calibrated_probability": None,
                "expected_value_per_contract": None,
            }
        )
    return safe_packet(
        status="sports_proxy_feature_model_falsification_ready_with_research_candidates"
        if research_candidate
        else "sports_proxy_feature_model_falsification_ready_no_research_candidates",
        method={"test_fraction": 0.30},
        summary={"research_candidate_count": 1 if research_candidate else 0},
        evaluations=evaluations,
    )


def sports_label_row(
    idx: int,
    *,
    predicted_side: str = "yes",
    mlb_platform_predicted_side: str | None = None,
    mlb_platform_model_probability: float | None = None,
    outcome: int = 1,
    league: str = "MLB",
):
    hour = 1 + idx // 12
    minute = (idx % 12) * 4
    return {
        "contract_ticker": f"KXMLBGAME-26JUL02{idx:04d}-CWSNYY",
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
        "mlb_platform_match_key": f"contract:KXMLBGAME-26JUL02{idx:04d}-CWSNYY"
        if mlb_platform_predicted_side
        else None,
        "yes_bid": 0.10 if predicted_side == "no" else 0.80,
        "yes_ask": 0.90 if predicted_side == "no" else 0.20,
        "yes_outcome": outcome,
        "decision_time": f"2026-07-02T{hour:02d}:{minute:02d}:00Z",
        "close_time": f"2026-07-02T{hour:02d}:{minute + 1:02d}:00Z",
        "settled_time": f"2026-07-02T{hour:02d}:{minute + 2:02d}:00Z",
        "label_status": "labeled_from_public_kalshi_settled_market",
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


# ---- VAL-SGATE-011: Wilson lower-bound calibration ----


def test_replay_uses_wilson_lower_bound(tmp_path: Path) -> None:
    """Replay uses Wilson lower-bound as conservative_calibrated_side_probability."""
    module = load_replay_module()
    label_dir = tmp_path / "labels"
    model_path = tmp_path / "model.json"
    rows = [sports_label_row(idx, predicted_side="yes", outcome=1) for idx in range(40)]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))
    write_json(model_path, model_report())

    report = module.build_sports_proxy_research_candidate_replay(
        label_dir=label_dir,
        model_falsification_path=model_path,
        generated_utc="2026-07-02T02:30:00Z",
        min_side_oos_labels=3,
        min_decay_buckets=2,
        min_decay_labels=10,
    )

    cal = report["calibration"]
    assert cal["confidence_z"] == 1.6448536269514722
    # With all correct OOS predictions, Wilson lower bound should be > 0.5
    assert cal["conservative_calibrated_side_probability"] is not None
    assert cal["conservative_calibrated_side_probability"] > 0.5
    assert cal["status"] == "research_only_conservative_probability_ready"


def test_replay_auto_selects_best_fdr_passed_mlb_platform_candidate(tmp_path: Path) -> None:
    """Replay calibrates the lowest-q passed sports evaluator, including MLB-platform."""
    module = load_replay_module()
    label_dir = tmp_path / "labels"
    model_path = tmp_path / "model.json"
    rows = [
        sports_label_row(
            idx,
            predicted_side="no",
            mlb_platform_predicted_side="yes",
            mlb_platform_model_probability=0.74,
            outcome=1,
        )
        for idx in range(40)
    ]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))
    write_json(model_path, model_report(include_mlb_candidate=True))

    report = module.build_sports_proxy_research_candidate_replay(
        label_dir=label_dir,
        model_falsification_path=model_path,
        generated_utc="2026-07-02T02:30:00Z",
        min_side_oos_labels=3,
        min_decay_buckets=2,
        min_decay_labels=10,
    )

    assert (
        report["summary"]["selected_replay_model_id"] == "mlb_platform_model_directional_accuracy"
    )
    assert report["calibration"]["model_id"] == "mlb_platform_model_directional_accuracy"
    assert report["replay_rows"]
    assert {row["source_model_id"] for row in report["replay_rows"]} == {
        "mlb_platform_model_directional_accuracy"
    }
    assert report["replay_rows"][0]["source_model_probability"] == 0.74


# ---- VAL-SGATE-012: Conservative probability <= raw OOS accuracy ----


def test_conservative_probability_never_exceeds_raw_oos_accuracy(tmp_path: Path) -> None:
    """conservative_calibrated_side_probability <= raw_oos_accuracy always."""
    module = load_replay_module()
    label_dir = tmp_path / "labels"
    model_path = tmp_path / "model.json"
    rows = [sports_label_row(idx, predicted_side="yes", outcome=1) for idx in range(40)]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))
    write_json(model_path, model_report())

    report = module.build_sports_proxy_research_candidate_replay(
        label_dir=label_dir,
        model_falsification_path=model_path,
        generated_utc="2026-07-02T02:30:00Z",
        min_side_oos_labels=3,
        min_decay_buckets=2,
        min_decay_labels=10,
    )

    cal = report["calibration"]
    assert cal["conservative_calibrated_side_probability"] <= cal["raw_oos_accuracy"] + 1e-10


# ---- VAL-SGATE-013: confidence_z is shared crypto constant ----


def test_confidence_z_is_shared_constant(tmp_path: Path) -> None:
    """confidence_z = 1.6448536269514722 identical for sports and crypto."""
    module = load_replay_module()
    assert module.DEFAULT_CONFIDENCE_Z == 1.6448536269514722


# ---- VAL-SGATE-014: Replay blocks when conservative probability not above random ----


def test_replay_blocks_when_conservative_prob_not_above_random(tmp_path: Path) -> None:
    """Replay blocks when Wilson bound <= 0.5."""
    module = load_replay_module()
    label_dir = tmp_path / "labels"
    model_path = tmp_path / "model.json"
    # Mediocre accuracy: ~50% correct -> Wilson bound will be <= 0.5
    rows = []
    for idx in range(40):
        outcome = 1 if idx % 2 == 0 else 0  # ~50% correct
        rows.append(sports_label_row(idx, predicted_side="yes", outcome=outcome))
    write_json(label_dir / "labels.json", safe_packet(rows=rows))
    write_json(model_path, model_report())

    report = module.build_sports_proxy_research_candidate_replay(
        label_dir=label_dir,
        model_falsification_path=model_path,
        generated_utc="2026-07-02T02:30:00Z",
        min_side_oos_labels=3,
        min_decay_buckets=2,
        min_decay_labels=10,
    )

    cal = report["calibration"]
    assert cal["status"] == "blocked_conservative_probability_not_above_random"
    gates = {g["name"]: g for g in report["gates"]}
    assert gates["conservative_probability_preflight"]["status"] == "blocked"


# ---- VAL-SGATE-015: All-in cost via kalshi_execution_cost ----


def test_replay_uses_kalshi_execution_cost(tmp_path: Path) -> None:
    """All-in cost computed via normalize_kalshi_execution_cost (Kalshi-generic)."""
    module = load_replay_module()
    label_dir = tmp_path / "labels"
    model_path = tmp_path / "model.json"
    rows = [sports_label_row(idx, predicted_side="yes", outcome=1) for idx in range(40)]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))
    write_json(model_path, model_report())

    report = module.build_sports_proxy_research_candidate_replay(
        label_dir=label_dir,
        model_falsification_path=model_path,
        generated_utc="2026-07-02T02:30:00Z",
        min_side_oos_labels=3,
        min_decay_buckets=2,
        min_decay_labels=10,
    )

    for row in report["replay_rows"]:
        assert row["all_in_cost"] is not None
        assert row["all_in_break_even_probability"] is not None
        assert row["cost_quality"] is not None
        # Sports ticker should NOT be misclassified as index-fee
        assert "INX" not in (row.get("contract_ticker") or "")
        break


# ---- VAL-SGATE-016: margin = calibrated - break_even, EV = calibrated - all_in_cost ----


def test_replay_margin_and_expected_value_math(tmp_path: Path) -> None:
    """margin_probability = calibrated - break_even, expected_value = calibrated - all_in_cost."""
    module = load_replay_module()
    label_dir = tmp_path / "labels"
    model_path = tmp_path / "model.json"
    rows = [sports_label_row(idx, predicted_side="yes", outcome=1) for idx in range(40)]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))
    write_json(model_path, model_report())

    report = module.build_sports_proxy_research_candidate_replay(
        label_dir=label_dir,
        model_falsification_path=model_path,
        generated_utc="2026-07-02T02:30:00Z",
        min_side_oos_labels=3,
        min_decay_buckets=2,
        min_decay_labels=10,
    )

    for row in report["replay_rows"]:
        calibrated = row["conservative_calibrated_side_probability"]
        break_even = row["all_in_break_even_probability"]
        all_in_cost = row["all_in_cost"]
        margin = row["margin_probability"]
        ev = row["expected_value_per_contract"]
        if calibrated is not None and break_even is not None:
            assert abs(margin - (calibrated - break_even)) < 1e-10
        if calibrated is not None and all_in_cost is not None:
            assert abs(ev - (calibrated - all_in_cost)) < 1e-10


# ---- VAL-SGATE-017: YES/NO side price derivation ----


def test_replay_side_price_derivation(tmp_path: Path) -> None:
    """YES side price = yes_ask; NO side price = 1 - yes_bid."""
    module = load_replay_module()
    label_dir = tmp_path / "labels"
    model_path = tmp_path / "model.json"
    rows = [
        sports_label_row(0, predicted_side="yes", outcome=1),
        sports_label_row(1, predicted_side="no", outcome=0),
    ]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))
    write_json(model_path, model_report())

    report = module.build_sports_proxy_research_candidate_replay(
        label_dir=label_dir,
        model_falsification_path=model_path,
        generated_utc="2026-07-02T02:30:00Z",
        min_side_oos_labels=2,
        min_decay_buckets=1,
        min_decay_labels=2,
    )

    for row in report["replay_rows"]:
        if row["predicted_side"] == "yes":
            assert row["selected_side_executable_price"] == row["yes_ask"]
        elif row["predicted_side"] == "no":
            assert row["selected_side_executable_price"] == 1.0 - row["yes_bid"]
        assert row["all_in_break_even_probability"] > row["selected_side_executable_price"]


# ---- VAL-SGATE-018: Cost math helper reusable unchanged ----


def test_cost_math_helper_reusable(tmp_path: Path) -> None:
    """kalshi_execution_cost imported from predmarket (not forked)."""
    module = load_replay_module()
    from predmarket.kalshi_execution_cost import normalize_kalshi_execution_cost

    assert hasattr(module, "normalize_kalshi_execution_cost")
    assert module.normalize_kalshi_execution_cost is normalize_kalshi_execution_cost


# ---- Writer emits latest outputs ----


def test_replay_writer_emits_latest(tmp_path: Path) -> None:
    """Writer emits latest-kalshi-sports-proxy-research-candidate-replay.* pointers."""
    module = load_replay_module()
    module.MACRO_DIR = tmp_path / "macro"
    label_dir = tmp_path / "labels"
    model_path = tmp_path / "model.json"
    write_json(
        label_dir / "labels.json", safe_packet(rows=[sports_label_row(idx) for idx in range(40)])
    )
    write_json(model_path, model_report())
    report = module.build_sports_proxy_research_candidate_replay(
        label_dir=label_dir,
        model_falsification_path=model_path,
        generated_utc="2026-07-02T02:30:00Z",
        min_side_oos_labels=3,
        min_decay_buckets=2,
        min_decay_labels=10,
    )

    paths = module.write_sports_proxy_research_candidate_replay(report, out_dir=tmp_path / "out")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    assert Path(paths["latest_json_path"]).exists()
    assert "Kalshi Sports Proxy Research Candidate Replay" in Path(
        paths["markdown_path"]
    ).read_text(encoding="utf-8")


# ---- Test blocks without research candidate ----


def test_replay_blocks_without_research_candidate(tmp_path: Path) -> None:
    """Replay blocks when no research candidate present."""
    module = load_replay_module()
    label_dir = tmp_path / "labels"
    model_path = tmp_path / "model.json"
    write_json(
        label_dir / "labels.json", safe_packet(rows=[sports_label_row(idx) for idx in range(12)])
    )
    write_json(model_path, model_report(research_candidate=False))

    report = module.build_sports_proxy_research_candidate_replay(
        label_dir=label_dir,
        model_falsification_path=model_path,
        generated_utc="2026-07-02T02:30:00Z",
        min_side_oos_labels=3,
        min_decay_buckets=2,
        min_decay_labels=10,
    )

    assert (
        report["status"]
        == "sports_proxy_research_candidate_replay_blocked_missing_research_candidate"
    )
    assert report["summary"]["candidate_research_model_present"] is False
    assert report["safety"]["market_execution"] is False


# ---- Test every row usable=false ----


def test_replay_every_row_usable_false(tmp_path: Path) -> None:
    """Every replay row has usable=False."""
    module = load_replay_module()
    label_dir = tmp_path / "labels"
    model_path = tmp_path / "model.json"
    rows = [sports_label_row(idx, predicted_side="yes", outcome=1) for idx in range(40)]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))
    write_json(model_path, model_report())

    report = module.build_sports_proxy_research_candidate_replay(
        label_dir=label_dir,
        model_falsification_path=model_path,
        generated_utc="2026-07-02T02:30:00Z",
        min_side_oos_labels=3,
        min_decay_buckets=2,
        min_decay_labels=10,
    )

    for row in report["replay_rows"]:
        assert row["usable"] is False
    assert report["summary"]["usable_row_count"] == 0


# ---- Test cluster key ----


def test_replay_cluster_key_sports_format(tmp_path: Path) -> None:
    """Sports cluster key is league|game_winner|date."""
    module = load_replay_module()
    label_dir = tmp_path / "labels"
    model_path = tmp_path / "model.json"
    rows = [
        sports_label_row(idx, predicted_side="yes", outcome=1, league="MLB") for idx in range(40)
    ]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))
    write_json(model_path, model_report())

    report = module.build_sports_proxy_research_candidate_replay(
        label_dir=label_dir,
        model_falsification_path=model_path,
        generated_utc="2026-07-02T02:30:00Z",
        min_side_oos_labels=3,
        min_decay_buckets=2,
        min_decay_labels=10,
    )

    for row in report["replay_rows"]:
        key = row["correlation_cluster_key"]
        assert "|" in key
        parts = key.split("|")
        assert len(parts) >= 3


# ---- Makefile target ----


def test_replay_makefile_target_exists() -> None:
    """Makefile has kalshi-sports-proxy-research-candidate-replay target."""
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    assert "kalshi-sports-proxy-research-candidate-replay" in makefile
    assert "scripts/kalshi_sports_proxy_research_candidate_replay.py" in makefile
