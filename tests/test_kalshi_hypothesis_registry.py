from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kalshi_hypothesis_registry.py"
SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "codex"
    / "macro"
    / "kalshi-hypothesis-candidate.schema.json"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_registry_module():
    spec = importlib.util.spec_from_file_location("kalshi_hypothesis_registry", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def safe_artifact(**overrides):
    payload = {
        "schema_version": 1,
        "research_only": True,
        "execution_enabled": False,
        "status": "ready",
        "summary": {},
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }
    payload.update(overrides)
    return payload


def test_registry_generates_versioned_unvalidated_hypotheses(tmp_path: Path) -> None:
    module = load_registry_module()
    universe_path = tmp_path / "universe.json"
    ledger_path = tmp_path / "ledger.json"
    write_json(
        universe_path,
        safe_artifact(
            summary={"candidate_count": 2},
            candidates=[
                {
                    "ticker": "KXRAINNYC-26JUL01-T0",
                    "event_ticker": "KXRAINNYC-26JUL01",
                    "title": "Will it rain in New York City?",
                    "classification": "weather",
                    "model_route": "soft_market_research_backlog",
                    "softness_reasons": [
                        "wide spread >= 10pp",
                        "settles within 6h",
                        "likely external reference data exists",
                    ],
                    "yes_ask": 0.48,
                    "no_ask": 0.7,
                    "time_to_close_hours": 5.0,
                    "softness_score": 1.0,
                },
                {
                    "ticker": "KXMLBGAME-26JUL01-CHC",
                    "event_ticker": "KXMLBGAME-26JUL01",
                    "title": "Will Chicago win?",
                    "classification": "mlb",
                    "model_route": "mlb-platform",
                    "softness_reasons": ["metadata stale >= 24h", "low displayed liquidity"],
                    "yes_ask": 0.41,
                    "no_ask": 0.63,
                    "time_to_close_hours": 10.0,
                    "softness_score": 0.6,
                },
            ],
        ),
    )
    write_json(
        ledger_path,
        safe_artifact(
            summary={"row_count": 1},
            rows=[
                {
                    "source_repo_id": "nfl_quant_glm51_greenfield",
                    "market_type": "nfl_game_moneyline",
                    "contract_ticker": "KXNFLGAME-26SEP13MIALV-MIA",
                    "side": "YES",
                    "title": "Miami to win?",
                    "calibrated_probability": 0.64,
                    "all_in_break_even_probability": 0.40,
                    "margin_probability": 0.24,
                    "gate_status": "pass",
                    "usable": True,
                }
            ],
        ),
    )

    report = module.build_hypothesis_registry(
        universe_scan_path=universe_path,
        ev_ledger_path=ledger_path,
        generated_utc="2026-07-01T23:30:00Z",
    )

    assert (
        report["status"]
        == "hypothesis_registry_ready_falsification_blocked_missing_labeled_oos_evidence"
    )
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["safety"]["market_execution"] is False
    assert report["summary"]["hypothesis_count"] >= 4
    assert (
        report["summary"]["multiple_testing_family_count"] == report["summary"]["hypothesis_count"]
    )
    assert (
        report["falsification_gate"]["status"]
        == "falsification_gate_blocked_missing_labeled_oos_evidence"
    )
    assert report["falsification_gate"]["tested_hypothesis_count"] == 0
    assert report["falsification_gate"]["promoted_hypothesis_count"] == 0
    ids = [row["hypothesis_id"] for row in report["hypotheses"]]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))
    assert all(row["schema_version"] == "HypothesisCandidateV1" for row in report["hypotheses"])
    assert all(row["status"] == "candidate_unvalidated" for row in report["hypotheses"])
    assert all(row["usable"] is False for row in report["hypotheses"])
    assert all(row["safety"]["account_or_order_paths"] is False for row in report["hypotheses"])


def test_registry_blocks_without_safe_universe(tmp_path: Path) -> None:
    module = load_registry_module()

    report = module.build_hypothesis_registry(
        universe_scan_path=tmp_path / "missing-universe.json",
        ev_ledger_path=tmp_path / "missing-ledger.json",
        generated_utc="2026-07-01T23:30:00Z",
    )

    assert report["status"] == "hypothesis_registry_blocked_missing_universe_inventory"
    assert report["summary"]["hypothesis_count"] == 0
    assert report["falsification_gate"]["status"] == "falsification_gate_blocked_missing_hypotheses"


def test_writer_emits_registry_gate_latest_json_markdown_and_csv(tmp_path: Path) -> None:
    module = load_registry_module()
    module.MACRO_DIR = tmp_path / "macro"
    universe_path = tmp_path / "universe.json"
    write_json(
        universe_path,
        safe_artifact(
            summary={"candidate_count": 1},
            candidates=[
                {
                    "ticker": "KXRAINNYC-26JUL01-T0",
                    "classification": "weather",
                    "model_route": "soft_market_research_backlog",
                    "softness_reasons": ["wide spread >= 10pp"],
                }
            ],
        ),
    )
    report = module.build_hypothesis_registry(
        universe_scan_path=universe_path,
        ev_ledger_path=tmp_path / "missing-ledger.json",
        generated_utc="2026-07-01T23:30:00Z",
    )

    paths = module.write_hypothesis_registry(report, out_dir=tmp_path / "out")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    assert Path(paths["falsification_gate_json_path"]).exists()
    assert Path(paths["latest_json_path"]).exists()
    assert Path(paths["latest_falsification_gate_json_path"]).exists()
    assert "Kalshi Hypothesis Registry" in Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert "Kalshi Falsification Gate" in Path(paths["falsification_gate_markdown_path"]).read_text(
        encoding="utf-8"
    )


def test_registry_registers_flow_and_passive_liquidity_with_own_acceptance_policy(
    tmp_path: Path,
) -> None:
    module = load_registry_module()
    universe_path = tmp_path / "universe.json"
    write_json(
        universe_path,
        safe_artifact(
            summary={"candidate_count": 1},
            candidates=[
                {
                    "ticker": "KXMLBGAME-26JUL01-CHC",
                    "event_ticker": "KXMLBGAME-26JUL01",
                    "title": "Will Chicago win?",
                    "classification": "mlb",
                    "model_route": "mlb-platform",
                    "softness_reasons": [
                        "settles within 2h",
                        "low displayed liquidity",
                    ],
                }
            ],
        ),
    )

    report = module.build_hypothesis_registry(
        universe_scan_path=universe_path,
        ev_ledger_path=tmp_path / "missing-ledger.json",
        generated_utc="2026-07-01T23:30:00Z",
    )

    by_family = {row["feature_family"]: row for row in report["hypotheses"]}
    flow = by_family["near_resolution_informed_flow"]
    passive = by_family["passive_liquidity_provision"]
    assert flow["primary_metric"] == "pre_close_flow_lead_lag_survival"
    assert passive["primary_metric"] == "maker_fill_net_ev_after_adverse_selection"
    assert "generic directional" in flow["acceptance_criteria"]
    assert "generic directional" in passive["acceptance_criteria"]
    assert "adverse-selection" in passive["promotion_rule"]


def test_schema_and_makefile_target_exist() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert schema["title"] == "HypothesisCandidateV1"
    assert "hypothesis_id" in schema["required"]
    assert "kalshi-hypothesis-registry" in makefile
    assert "scripts/kalshi_hypothesis_registry.py" in makefile
