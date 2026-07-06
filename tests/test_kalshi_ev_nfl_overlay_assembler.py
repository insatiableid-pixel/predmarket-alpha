from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kalshi_ev_nfl_overlay_assembler.py"
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_assembler_module():
    spec = importlib.util.spec_from_file_location("kalshi_ev_nfl_overlay_assembler", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def safe_payload(**overrides):
    payload = {
        "research_only": True,
        "execution_enabled": False,
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }
    payload.update(overrides)
    return payload


def work_order_payload():
    return safe_payload(
        status="contract_mapping_work_order_ready",
        rows=[
            {
                "source_repo_id": "nfl_quant_glm51_greenfield",
                "source_artifact": "/tmp/fair-line-review.json",
                "source_artifact_sha256": "abc123",
                "source_row_index": 11,
                "game": "MIA@LV",
                "selection": "MIA",
                "opponent": "LV",
                "market_type": "nfl_game_moneyline",
                "model_calibrated_probability": 0.6462354523607845,
                "model_probability_source": "profile:selection_proposal_elo",
                "model_calibration_source": "platt_logit",
                "model_calibration_detail": "train_rows=749",
            }
        ],
    )


def test_nfl_overlay_assembler_blocks_without_ready_local_evidence(tmp_path: Path) -> None:
    assembler = load_assembler_module()
    scout_path = tmp_path / "scout.json"
    work_order_path = tmp_path / "work-order.json"
    write_json(
        scout_path,
        safe_payload(
            status="local_contract_evidence_blocked_no_nfl_target_snapshot",
            target_matches=[],
        ),
    )
    write_json(work_order_path, work_order_payload())

    report = assembler.build_nfl_overlay_assembler(
        scout_path=scout_path,
        work_order_path=work_order_path,
        mapping_output_dir=tmp_path / "manual/contract_mappings",
        probability_output_dir=tmp_path / "manual/probabilities",
        generated_utc="2026-07-01T00:00:00Z",
        emit_overlays=True,
    )

    assert report["status"] == "nfl_overlay_assembler_blocked_no_ready_local_contract_evidence"
    assert report["summary"]["assembled_overlay_pair_count"] == 0
    assert report["summary"]["overlays_written"] is False
    assert "mapping_overlay_path" not in report["outputs"]


def test_nfl_overlay_assembler_writes_safe_overlay_pair_from_ready_match(tmp_path: Path) -> None:
    assembler = load_assembler_module()
    assembler.CONTROL_REPO = tmp_path / "repo"
    scout_path = tmp_path / "scout.json"
    work_order_path = tmp_path / "work-order.json"
    contract_source = tmp_path / "kalshi_nfl_snapshot.json"
    write_json(contract_source, {"source": "unit test"})
    write_json(
        scout_path,
        safe_payload(
            status="local_contract_evidence_ready_for_overlay_fill",
            target_matches=[
                {
                    "target_index": 0,
                    "game": "MIA@LV",
                    "selection": "MIA",
                    "opponent": "LV",
                    "contract_ticker": "KXNFLGAME-26SEP130000MIALV-MIA",
                    "event_ticker": "KXNFLGAME-26SEP130000MIALV",
                    "match_quality": "ready_exact_local_evidence",
                    "official_terms_present": True,
                    "resolution_rule": "rules_primary: If Miami wins, this market resolves to Yes.",
                    "executable_cost_present": True,
                    "clean_timing_present": True,
                    "timing_status": "clean",
                    "yes_ask": 0.64,
                    "yes_bid": 0.61,
                    "source_path": str(contract_source),
                    "source_sha256": "def456",
                }
            ],
        ),
    )
    write_json(work_order_path, work_order_payload())

    report = assembler.build_nfl_overlay_assembler(
        scout_path=scout_path,
        work_order_path=work_order_path,
        mapping_output_dir=tmp_path / "manual/contract_mappings",
        probability_output_dir=tmp_path / "manual/probabilities",
        generated_utc="2026-07-01T00:00:00Z",
        emit_overlays=True,
    )

    assert report["status"] == "nfl_overlay_assembler_overlays_written"
    mapping_path = Path(report["outputs"]["mapping_overlay_path"])
    probability_path = Path(report["outputs"]["probability_overlay_path"])
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    probability = json.loads(probability_path.read_text(encoding="utf-8"))
    mapping_row = mapping["rows"][0]
    probability_row = probability["rows"][0]

    assert mapping["research_only"] is True
    assert mapping["generated_utc"] == "2026-07-01T00:00:00Z"
    assert mapping["safety"]["market_execution"] is False
    assert mapping_row["decision_time"] == "2026-07-01T00:00:00Z"
    assert mapping_row["quote_time"] == "2026-07-01T00:00:00Z"
    assert mapping_row["mapping_status"] == "verified_contract_mapping"
    assert mapping_row["resolution_rule_status"] == "verified_official_terms"
    assert mapping_row["timing_status"] == "clean"
    assert mapping_row["executable_price"] == 0.64
    assert probability_row["contract_ticker"] == mapping_row["contract_ticker"]
    assert probability_row["model_time"] == "2026-07-01T00:00:00Z"
    assert probability_row["calibration_status"] == "validated_calibrated_probability"
    assert probability_row["calibrated_probability"] == 0.6462354523607845

    rerun = assembler.build_nfl_overlay_assembler(
        scout_path=scout_path,
        work_order_path=work_order_path,
        mapping_output_dir=tmp_path / "manual/contract_mappings",
        probability_output_dir=tmp_path / "manual/probabilities",
        generated_utc="2026-07-01T00:05:00Z",
        emit_overlays=True,
    )

    assert rerun["outputs"]["mapping_overlay_path"] == report["outputs"]["mapping_overlay_path"]
    assert (
        rerun["outputs"]["probability_overlay_path"]
        == report["outputs"]["probability_overlay_path"]
    )
    assert len(list((tmp_path / "manual/contract_mappings").glob("*.json"))) == 1
    assert len(list((tmp_path / "manual/probabilities").glob("*.json"))) == 1


def test_nfl_overlay_assembler_dry_run_does_not_write_overlays(tmp_path: Path) -> None:
    assembler = load_assembler_module()
    assembler.CONTROL_REPO = tmp_path / "repo"
    scout_path = tmp_path / "scout.json"
    work_order_path = tmp_path / "work-order.json"
    write_json(
        scout_path,
        safe_payload(
            status="local_contract_evidence_ready_for_overlay_fill",
            target_matches=[
                {
                    "target_index": 0,
                    "contract_ticker": "KXNFLGAME-26SEP130000MIALV-MIA",
                    "event_ticker": "KXNFLGAME-26SEP130000MIALV",
                    "match_quality": "ready_exact_local_evidence",
                    "official_terms_present": True,
                    "resolution_rule": "rules_primary: If Miami wins, this market resolves to Yes.",
                    "executable_cost_present": True,
                    "clean_timing_present": True,
                    "timing_status": "clean",
                    "yes_ask": 0.64,
                }
            ],
        ),
    )
    write_json(work_order_path, work_order_payload())

    report = assembler.build_nfl_overlay_assembler(
        scout_path=scout_path,
        work_order_path=work_order_path,
        mapping_output_dir=tmp_path / "manual/contract_mappings",
        probability_output_dir=tmp_path / "manual/probabilities",
        generated_utc="2026-07-01T00:00:00Z",
        emit_overlays=False,
    )

    assert report["status"] == "nfl_overlay_assembler_ready_dry_run"
    assert not list((tmp_path / "manual").glob("**/*.json"))


def test_nfl_overlay_assembler_dedupes_duplicate_ready_matches(tmp_path: Path) -> None:
    assembler = load_assembler_module()
    assembler.CONTROL_REPO = tmp_path / "repo"
    scout_path = tmp_path / "scout.json"
    work_order_path = tmp_path / "work-order.json"
    duplicate_match = {
        "target_index": 0,
        "contract_ticker": "KXNFLGAME-26SEP130000MIALV-MIA",
        "event_ticker": "KXNFLGAME-26SEP130000MIALV",
        "match_quality": "ready_exact_local_evidence",
        "official_terms_present": True,
        "resolution_rule": "rules_primary: If Miami wins, this market resolves to Yes.",
        "executable_cost_present": True,
        "clean_timing_present": True,
        "timing_status": "clean",
        "yes_ask": 0.64,
    }
    write_json(
        scout_path,
        safe_payload(
            status="local_contract_evidence_ready_for_overlay_fill",
            target_matches=[duplicate_match, dict(duplicate_match)],
        ),
    )
    write_json(work_order_path, work_order_payload())

    report = assembler.build_nfl_overlay_assembler(
        scout_path=scout_path,
        work_order_path=work_order_path,
        mapping_output_dir=tmp_path / "manual/contract_mappings",
        probability_output_dir=tmp_path / "manual/probabilities",
        generated_utc="2026-07-01T00:00:00Z",
        limit=32,
        emit_overlays=False,
    )

    assert report["status"] == "nfl_overlay_assembler_ready_dry_run"
    assert report["summary"]["total_unique_ready_target_match_count"] == 1
    assert report["summary"]["selected_ready_target_match_count"] == 1
    assert report["summary"]["assembled_overlay_pair_count"] == 1


def test_nfl_overlay_assembler_writer_emits_latest_report(tmp_path: Path) -> None:
    assembler = load_assembler_module()
    assembler.MACRO_DIR = tmp_path / "macro"
    report = safe_payload(
        status="nfl_overlay_assembler_blocked_no_ready_local_contract_evidence",
        summary={
            "ready_target_match_count": 0,
            "assembled_overlay_pair_count": 0,
            "overlays_written": False,
        },
        gates=[],
        assembled_rows=[],
        next_action="Drop evidence.",
    )

    paths = assembler.write_assembler_report(report, out_dir=tmp_path / "out")
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["latest_json_path"]).exists()
    assert "Kalshi EV NFL Overlay Assembler" in markdown


def test_makefile_exposes_nfl_overlay_assembler_target() -> None:
    content = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-ev-nfl-overlay-assembler" in content
    assert "scripts/kalshi_ev_nfl_overlay_assembler.py" in content
