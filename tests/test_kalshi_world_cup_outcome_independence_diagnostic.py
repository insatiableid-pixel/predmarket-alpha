from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "kalshi_world_cup_outcome_independence_diagnostic.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_world_cup_outcome_independence_diagnostic", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def safe_packet(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "packet_type": "kalshi_world_cup_proxy_feature_labels",
        "generated_utc": "2026-07-05T00:00:00Z",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
        "rows": rows,
        "summary": {"label_row_count": len(rows)},
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }


def safe_model(research_candidate_count: int = 1) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "world_cup_proxy_feature_model_falsification_ready_with_research_candidates",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "summary": {
            "independent_contract_label_count": 6,
            "research_candidate_count": research_candidate_count,
        },
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }


def label_row(
    *,
    ticker: str,
    event_ticker: str,
    series: str,
    market_type: str,
    outcome: int = 1,
) -> dict[str, object]:
    return {
        "contract_ticker": ticker,
        "event_ticker": event_ticker,
        "series_ticker": series,
        "market_type": market_type,
        "selection_token": ticker.rsplit("-", maxsplit=1)[-1],
        "decision_time": "2026-07-04T16:00:00Z",
        "close_time": "2026-07-04T18:00:00Z",
        "yes_bid": 0.62,
        "yes_ask": 0.64,
        "yes_mid": 0.63,
        "yes_outcome": outcome,
        "market_consensus_prediction": "yes" if outcome else "no",
        "longshot_fade_prediction": None,
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


def write_fixture_inputs(tmp_path: Path) -> tuple[Path, Path]:
    rows = [
        label_row(
            ticker="KXWCGAME-26JUL04AAABBB-AAA",
            event_ticker="KXWCGAME-26JUL04AAABBB",
            series="KXWCGAME",
            market_type="game",
        ),
        label_row(
            ticker="KXWCTOTAL-26JUL04AAABBB-1",
            event_ticker="KXWCTOTAL-26JUL04AAABBB",
            series="KXWCTOTAL",
            market_type="total",
        ),
        label_row(
            ticker="KXWCTOTAL-26JUL04AAABBB-2",
            event_ticker="KXWCTOTAL-26JUL04AAABBB",
            series="KXWCTOTAL",
            market_type="total",
            outcome=0,
        ),
        label_row(
            ticker="KXWCBTTS-26JUL04AAABBB-YES",
            event_ticker="KXWCBTTS-26JUL04AAABBB",
            series="KXWCBTTS",
            market_type="both_teams_to_score",
        ),
        label_row(
            ticker="KXWC1HTOTAL-26JUL04CCCDDD-1",
            event_ticker="KXWC1HTOTAL-26JUL04CCCDDD",
            series="KXWC1HTOTAL",
            market_type="total",
        ),
        label_row(
            ticker="KXWCSPREAD-26JUL04CCCDDD-DDD2",
            event_ticker="KXWCSPREAD-26JUL04CCCDDD",
            series="KXWCSPREAD",
            market_type="spread",
            outcome=0,
        ),
    ]
    label_dir = tmp_path / "labels"
    write_json(label_dir / "labels.json", safe_packet(rows))
    model_path = write_json(tmp_path / "world_cup_model.json", safe_model())
    return label_dir, model_path


def test_diagnostic_separates_contract_labels_from_outcome_and_match_units(
    tmp_path: Path,
) -> None:
    module = load_module()
    label_dir, model_path = write_fixture_inputs(tmp_path)

    report = module.build_world_cup_outcome_independence_diagnostic(
        label_dir=label_dir,
        world_cup_model_path=model_path,
        generated_utc="2026-07-05T00:00:00Z",
        min_independent_labels=6,
        min_oos_labels=2,
    )

    assert report["status"] == (
        "world_cup_outcome_independence_diagnostic_ready_candidate_independence_review"
    )
    assert report["execution_enabled"] is False
    assert report["market_execution"] is False
    summary = report["summary"]
    assert summary["exact_contract_label_count"] == 6
    assert summary["event_market_label_count"] == 5
    assert summary["outcome_family_label_count"] == 5
    assert summary["match_cluster_count"] == 2
    assert summary["current_candidate_independence_requires_review"] is True
    assert summary["recommended_hypothesis_counting_unit"] == "match_outcome_family"
    assert summary["recommended_portfolio_cluster_unit"] == "world_cup_match"

    family_rows = {row["outcome_family"]: row for row in report["outcome_family_rows"]}
    assert family_rows["full_time_total_goals"]["contract_label_count"] == 2
    assert family_rows["full_time_total_goals"]["outcome_family_label_count"] == 1
    assert family_rows["both_teams_to_score"]["match_cluster_count"] == 1

    match_rows = {row["match_key"]: row for row in report["match_cluster_rows"]}
    assert match_rows["26JUL04AAABBB"]["outcome_family_label_count"] == 3
    assert match_rows["26JUL04AAABBB"]["portfolio_cluster_unit"] == "world_cup_match"


def test_diagnostic_ready_when_outcome_family_threshold_is_met(tmp_path: Path) -> None:
    module = load_module()
    label_dir, model_path = write_fixture_inputs(tmp_path)

    report = module.build_world_cup_outcome_independence_diagnostic(
        label_dir=label_dir,
        world_cup_model_path=model_path,
        generated_utc="2026-07-05T00:00:00Z",
        min_independent_labels=4,
        min_oos_labels=2,
    )

    assert report["status"] == (
        "world_cup_outcome_independence_diagnostic_ready_parallel_outcome_clocks"
    )
    assert report["summary"]["outcome_level_parallel_clock_supported"] is True
    assert report["summary"]["current_candidate_independence_requires_review"] is False


def test_diagnostic_temp_out_dir_does_not_mutate_macro_latest(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    macro_dir = tmp_path / "macro"
    monkeypatch.setattr(module, "MACRO_DIR", macro_dir)
    label_dir, model_path = write_fixture_inputs(tmp_path)
    report = module.build_world_cup_outcome_independence_diagnostic(
        label_dir=label_dir,
        world_cup_model_path=model_path,
        generated_utc="2026-07-05T00:00:00Z",
    )

    paths = module.write_outputs(report, out_dir=tmp_path / "out")

    assert "latest_json_path" not in paths
    assert not (macro_dir / "latest-kalshi-world-cup-outcome-independence-diagnostic.json").exists()


def test_diagnostic_makefile_target_exists() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-world-cup-outcome-independence-diagnostic" in text
    assert "scripts/kalshi_world_cup_outcome_independence_diagnostic.py" in text
