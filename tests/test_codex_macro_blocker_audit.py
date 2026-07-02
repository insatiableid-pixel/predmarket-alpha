import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "codex_macro_blocker_audit.py"
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_blocker_audit_module():
    spec = importlib.util.spec_from_file_location("codex_macro_blocker_audit", SCRIPT_PATH)
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


def write_common_inputs(macro: Path, lanes: list[dict]) -> None:
    write_json(macro / "latest-status.json", {"schema_version": 1, "repos": []})
    write_json(
        macro / "latest-decision.json",
        {
            "schema_version": 1,
            "recommended_repo_id": "predmarket-alpha",
            "all_lanes_parked": False,
            "ranked_repos": [
                {"repo_id": lane["repo_id"], "status": lane["status"], "priority": -1}
                for lane in lanes
            ],
        },
    )
    write_json(
        macro / "latest-unlock-scout.json",
        safe_payload(schema_version=1, lanes=lanes),
    )
    write_json(
        macro / "latest-kalshi-contract-ev-ledger.json",
        safe_payload(status="kalshi_ev_ledger_candidates_present_but_not_usable", summary={"usable_row_count": 0}),
    )
    write_json(
        macro / "latest-kalshi-ev-local-contract-evidence-scout.json",
        safe_payload(status="local_contract_evidence_blocked_no_nfl_target_snapshot", summary={"ready_target_match_count": 0}),
    )
    write_json(
        macro / "latest-kalshi-ev-nfl-overlay-assembler.json",
        safe_payload(
            status="nfl_overlay_assembler_blocked_no_ready_local_contract_evidence",
            summary={"overlays_written": False},
        ),
    )


def exact_lanes() -> list[dict]:
    return [
        {
            "repo_id": "predmarket-alpha",
            "status": "local_contract_evidence_blocked_no_nfl_target_snapshot",
            "blocked": True,
            "missing_input": "Local Kalshi NFL contract snapshot with exact ticker, official terms, clean timing, and executable cost.",
            "next_local_command": "make kalshi-ev-local-contract-evidence-scout",
            "what_exists": "ready_target_matches=0",
        },
        {
            "repo_id": "mlb-platform",
            "status": "betexplorer_market_closing_comparison_ready_no_policy_change",
            "blocked": True,
            "missing_input": "Independent clean slate or stronger true closing-line validation evidence.",
            "next_local_command": "cd /home/mrwatson/projects/mlb-platform && make macro-status",
            "what_exists": "current_threshold_count=0",
        },
        {
            "repo_id": "atp-oracle",
            "status": "blocked_g1g2_model_quality_evidence",
            "blocked": True,
            "missing_input": "Fresh validation and D3/G5/P5 external proof evidence.",
            "next_local_command": "cd /home/mrwatson/projects/atp-oracle && make type2-g1g2-diagnostic",
            "what_exists": "vision_score=93",
        },
        {
            "repo_id": "nba-analytics-platform",
            "status": "macro_partial_truth_shrinkage_clipped_residual_market_parity",
            "blocked": True,
            "missing_input": "New source-backed NBA signal or market dataset that can beat market parity.",
            "next_local_command": "cd /home/mrwatson/projects/nba-analytics-platform && make macro-status",
            "what_exists": "market parity",
        },
        {
            "repo_id": "nfl_quant_glm51_greenfield",
            "status": "line_readiness_profiled_slate_forward_context_not_yet_due_research_only",
            "blocked": True,
            "missing_input": "Forward-context evidence when due: injuries, weather, official starting QBs, and closing reference lines.",
            "next_local_command": "cd /home/mrwatson/projects/nfl_quant_glm51_greenfield && make forward-context-availability && make macro-status",
            "what_exists": "not yet due",
        },
    ]


def test_blocker_audit_passes_when_every_lane_has_exact_blocker(tmp_path: Path) -> None:
    module = load_blocker_audit_module()
    macro = tmp_path / "macro"
    write_common_inputs(macro, exact_lanes())

    report = module.build_blocker_audit(
        macro_dir=macro,
        generated_utc="2026-07-01T00:00:00Z",
    )

    assert report["status"] == "macro_blocker_audit_all_lanes_blocked_with_exact_inputs"
    assert report["summary"]["blocked_lane_count"] == 5
    assert report["summary"]["specific_missing_input_lane_count"] == 5
    assert all(lane["proof_status"] == "pass" for lane in report["lane_audits"])
    assert report["safety"]["market_execution"] is False


def test_blocker_audit_fails_generic_missing_input(tmp_path: Path) -> None:
    module = load_blocker_audit_module()
    macro = tmp_path / "macro"
    lanes = exact_lanes()
    lanes[3]["missing_input"] = "No immediate local unlock from scout; see latest macro decision ranking."
    write_common_inputs(macro, lanes)

    report = module.build_blocker_audit(
        macro_dir=macro,
        generated_utc="2026-07-01T00:00:00Z",
    )

    assert report["status"] == "macro_blocker_audit_incomplete"
    nba = next(lane for lane in report["lane_audits"] if lane["repo_id"] == "nba-analytics-platform")
    assert nba["missing_input_specific"] is False
    assert nba["proof_status"] == "blocked"


def test_blocker_audit_writer_emits_latest_files(tmp_path: Path) -> None:
    module = load_blocker_audit_module()
    module.MACRO_DIR = tmp_path / "macro"
    report = safe_payload(
        status="macro_blocker_audit_incomplete",
        summary={
            "lane_count": 0,
            "blocked_lane_count": 0,
            "specific_missing_input_lane_count": 0,
            "usable_ev_row_count": 0,
        },
        gates=[],
        lane_audits=[],
        next_action="Refresh macro artifacts.",
    )

    paths = module.write_blocker_audit(report, out_dir=tmp_path / "out")
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["latest_json_path"]).exists()
    assert "Macro Blocker Audit" in markdown


def test_makefile_exposes_macro_blocker_audit_target() -> None:
    content = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "macro-blocker-audit" in content
    assert "scripts/codex_macro_blocker_audit.py" in content
