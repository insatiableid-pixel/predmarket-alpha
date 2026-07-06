from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_ev_local_contract_evidence_scout.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_scout_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_ev_local_contract_evidence_scout", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_work_order(path: Path) -> None:
    write_json(
        path,
        {
            "status": "contract_mapping_work_order_ready",
            "research_only": True,
            "execution_enabled": False,
            "rows": [
                {
                    "game": "MIA@LV",
                    "selection": "MIA",
                    "opponent": "LV",
                    "market_type": "nfl_game_moneyline",
                    "model_calibrated_probability": 0.64,
                }
            ],
        },
    )


def test_local_contract_evidence_scout_finds_ready_nfl_target(tmp_path: Path) -> None:
    scout = load_scout_module()
    work_order = tmp_path / "macro/latest-kalshi-ev-contract-mapping-work-order.json"
    search_dir = tmp_path / "manual_drops/kalshi"
    write_work_order(work_order)
    write_json(
        search_dir / "kalshi_nfl_snapshot.json",
        {
            "markets": [
                {
                    "ticker": "KXNFLGAME-26SEP130000MIALV-MIA",
                    "event_ticker": "KXNFLGAME-26SEP130000MIALV",
                    "title": "Miami Dolphins vs Las Vegas Raiders",
                    "rules_primary": "If Miami wins the football game, this market resolves to Yes.",
                    "rules_secondary": "Official league scoring determines the winner.",
                    "yes_bid_dollars": "0.6100",
                    "yes_ask_dollars": "0.6400",
                    "timing_status": "clean",
                    "status": "active",
                }
            ]
        },
    )

    report = scout.build_local_contract_evidence_scout(
        work_order_path=work_order,
        search_paths=[search_dir],
        generated_utc="2026-07-01T00:00:00Z",
    )

    assert report["status"] == "local_contract_evidence_ready_for_overlay_fill"
    assert report["research_only"] is True
    assert report["safety"]["market_execution"] is False
    assert report["summary"]["nfl_contract_evidence_row_count"] == 1
    assert report["summary"]["clean_timing_row_count"] == 1
    assert report["summary"]["ready_target_match_count"] == 1
    match = report["target_matches"][0]
    assert match["contract_ticker"] == "KXNFLGAME-26SEP130000MIALV-MIA"
    assert match["match_quality"] == "ready_exact_local_evidence"
    assert match["yes_ask"] == 0.64
    assert match["timing_status"] == "clean"
    assert "rules_primary" in match["resolution_rule"]


def test_local_contract_evidence_scout_blocks_when_only_mlb_snapshots_exist(tmp_path: Path) -> None:
    scout = load_scout_module()
    work_order = tmp_path / "macro/latest-kalshi-ev-contract-mapping-work-order.json"
    search_dir = tmp_path / "manual_drops/kalshi"
    write_work_order(work_order)
    write_json(
        search_dir / "kalshi_mlb_snapshot.json",
        {
            "all_scored": [
                {
                    "ticker": "KXMLBGAME-26JUN291835CWSBAL-BAL",
                    "event_ticker": "KXMLBGAME-26JUN291835CWSBAL",
                    "title": "Chicago WS vs Baltimore",
                    "rules_primary": "If Baltimore wins the baseball game, this market resolves to Yes.",
                    "yes_ask_dollars": "0.6200",
                }
            ]
        },
    )

    report = scout.build_local_contract_evidence_scout(
        work_order_path=work_order,
        search_paths=[search_dir],
        generated_utc="2026-07-01T00:00:00Z",
    )

    assert report["status"] == "local_contract_evidence_blocked_no_nfl_target_snapshot"
    assert report["summary"]["contract_evidence_row_count"] == 1
    assert report["summary"]["nfl_contract_evidence_row_count"] == 0
    assert report["summary"]["ready_target_match_count"] == 0
    assert "Drop a local Kalshi NFL contract snapshot" in report["next_action"]
    sample = report["contract_evidence_samples"][0]
    assert "rules_primary" not in sample
    assert sample["official_terms_present"] is True


def test_local_contract_evidence_scout_requires_clean_timing_for_ready_match(
    tmp_path: Path,
) -> None:
    scout = load_scout_module()
    work_order = tmp_path / "macro/latest-kalshi-ev-contract-mapping-work-order.json"
    search_dir = tmp_path / "manual_drops/kalshi"
    write_work_order(work_order)
    write_json(
        search_dir / "kalshi_nfl_snapshot.json",
        {
            "markets": [
                {
                    "ticker": "KXNFLGAME-26SEP130000MIALV-MIA",
                    "event_ticker": "KXNFLGAME-26SEP130000MIALV",
                    "title": "Miami Dolphins vs Las Vegas Raiders",
                    "rules_primary": "If Miami wins the football game, this market resolves to Yes.",
                    "yes_ask_dollars": "0.6400",
                    "status": "active",
                }
            ]
        },
    )

    report = scout.build_local_contract_evidence_scout(
        work_order_path=work_order,
        search_paths=[search_dir],
        generated_utc="2026-07-01T00:00:00Z",
    )

    assert report["status"] == "local_contract_evidence_blocked_no_ready_target_match"
    assert report["summary"]["possible_target_match_count"] == 1
    assert report["summary"]["ready_target_match_count"] == 0
    match = report["target_matches"][0]
    assert match["match_quality"] == "possible_text_match"
    assert match["clean_timing_present"] is False


def test_local_contract_evidence_scout_derives_clean_timing_from_future_public_snapshot(
    tmp_path: Path,
) -> None:
    scout = load_scout_module()
    work_order = tmp_path / "macro/latest-kalshi-ev-contract-mapping-work-order.json"
    search_dir = tmp_path / "manual_drops/kalshi"
    write_work_order(work_order)
    write_json(
        search_dir / "kalshi_nfl_snapshot.json",
        {
            "created_at_utc": "2026-07-01T18:57:56Z",
            "all_scored": [
                {
                    "ticker": "KXNFLGAME-26SEP130000MIALV-MIA",
                    "event_ticker": "KXNFLGAME-26SEP130000MIALV",
                    "title": "Will Miami win the Miami vs Las Vegas Pro Football game?",
                    "yes_sub_title": "Miami",
                    "rules_primary": "If Miami wins the football game, this market resolves to Yes.",
                    "rules_secondary": "Official league scoring determines the winner.",
                    "yes_bid_dollars": "0.6100",
                    "yes_ask_dollars": "0.6400",
                    "expected_expiration_time": "2026-09-13T23:25:00Z",
                    "status": "active",
                }
            ],
        },
    )

    report = scout.build_local_contract_evidence_scout(
        work_order_path=work_order,
        search_paths=[search_dir],
        generated_utc="2026-07-01T19:00:00Z",
    )

    assert report["status"] == "local_contract_evidence_ready_for_overlay_fill"
    assert report["summary"]["clean_timing_row_count"] == 1
    match = report["target_matches"][0]
    assert match["match_quality"] == "ready_exact_local_evidence"
    assert match["timing_status"] == "pregame_clean"


def test_local_contract_evidence_scout_rejects_wrong_contract_side(tmp_path: Path) -> None:
    scout = load_scout_module()
    work_order = tmp_path / "macro/latest-kalshi-ev-contract-mapping-work-order.json"
    search_dir = tmp_path / "manual_drops/kalshi"
    write_work_order(work_order)
    write_json(
        search_dir / "kalshi_nfl_snapshot.json",
        {
            "created_at_utc": "2026-07-01T18:57:56Z",
            "all_scored": [
                {
                    "ticker": "KXNFLGAME-26SEP130000MIALV-LV",
                    "event_ticker": "KXNFLGAME-26SEP130000MIALV",
                    "title": "Will Las Vegas win the Miami vs Las Vegas Pro Football game?",
                    "yes_sub_title": "Las Vegas",
                    "rules_primary": "If Las Vegas wins the football game, this market resolves to Yes.",
                    "rules_secondary": "Official league scoring determines the winner.",
                    "yes_bid_dollars": "0.3600",
                    "yes_ask_dollars": "0.3900",
                    "expected_expiration_time": "2026-09-13T23:25:00Z",
                    "status": "active",
                }
            ],
        },
    )

    report = scout.build_local_contract_evidence_scout(
        work_order_path=work_order,
        search_paths=[search_dir],
        generated_utc="2026-07-01T19:00:00Z",
    )

    assert report["status"] == "local_contract_evidence_blocked_no_ready_target_match"
    assert report["summary"]["possible_target_match_count"] == 0
    assert report["summary"]["ready_target_match_count"] == 0


def test_local_contract_evidence_scout_writer_emits_latest_files(tmp_path: Path) -> None:
    scout = load_scout_module()
    scout.MACRO_DIR = tmp_path / "macro"
    report = {
        "status": "local_contract_evidence_blocked_no_contract_snapshots",
        "research_only": True,
        "summary": {
            "json_file_count": 0,
            "contract_evidence_row_count": 0,
            "nfl_contract_evidence_row_count": 0,
            "target_contract_side_count": 0,
            "possible_target_match_count": 0,
            "ready_target_match_count": 0,
        },
        "gates": [],
        "next_action": "Refresh the work order.",
    }

    paths = scout.write_local_contract_evidence_scout(report, out_dir=tmp_path / "out")
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["latest_json_path"]).exists()
    assert "Kalshi EV Local Contract Evidence Scout" in markdown


def test_makefile_exposes_local_contract_evidence_scout_target() -> None:
    content = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-ev-local-contract-evidence-scout" in content
    assert "scripts/kalshi_ev_local_contract_evidence_scout.py" in content
