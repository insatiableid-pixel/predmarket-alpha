from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from predmarket.kalshi_execution_cost import kalshi_trade_fee


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kalshi_ev_queue_robustness.py"
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_robustness_module():
    spec = importlib.util.spec_from_file_location("kalshi_ev_queue_robustness", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def queue_payload(*rows):
    return {
        "schema_version": 1,
        "generated_utc": "2026-07-01T22:00:00Z",
        "status": "kalshi_ev_review_queue_positive_candidates_need_robustness",
        "research_only": True,
        "execution_enabled": False,
        "rows": list(rows),
    }


def queue_row(**overrides):
    row = {
        "queue_rank": 1,
        "contract_ticker": "KXNFLGAME-26SEP13MIALV-MIA",
        "side": "yes",
        "selection": "MIA",
        "source_repo_id": "nfl_quant_glm51_greenfield",
        "calibrated_probability": 0.65,
        "cost_quality": "estimated_fee_from_executable_price",
    }
    row.update(overrides)
    return row


def snapshot_payload(*, created_at: str, ask: float, bid: float = 0.38):
    return {
        "schema_version": 1,
        "created_at_utc": created_at,
        "series_tickers": ["KXNFLGAME"],
        "research_only": True,
        "execution_enabled": False,
        "all_scored": [
            {
                "ticker": "KXNFLGAME-26SEP13MIALV-MIA",
                "yes_bid_dollars": f"{bid:.4f}",
                "yes_ask_dollars": f"{ask:.4f}",
                "title": "Will Miami win?",
                "subtitle": "MIA",
            }
        ],
    }


def test_queue_robustness_marks_repeat_positive_as_cost_caveated(tmp_path: Path) -> None:
    robustness = load_robustness_module()
    queue_path = tmp_path / "queue.json"
    snapshot_dir = tmp_path / "snapshots"
    write_json(queue_path, queue_payload(queue_row()))
    write_json(snapshot_dir / "snapshot-1.json", snapshot_payload(created_at="2026-07-01T20:00:00Z", ask=0.40))
    write_json(snapshot_dir / "snapshot-2.json", snapshot_payload(created_at="2026-07-01T22:00:00Z", ask=0.41))

    report = robustness.build_queue_robustness(
        queue_path=queue_path,
        snapshot_dir=snapshot_dir,
        generated_utc="2026-07-01T22:05:00Z",
        min_robust_margin=0.02,
    )

    expected_latest_break_even = 0.41 + kalshi_trade_fee(price=0.41)
    assert report["status"] == "kalshi_ev_queue_robustness_repeat_positive_cost_caveated"
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["provider_api_calls"] is False
    assert report["summary"]["distinct_snapshot_count"] == 2
    assert report["summary"]["repeat_positive_row_count"] == 1
    assert report["summary"]["robust_candidate_count"] == 0
    row = report["rows"][0]
    assert row["snapshot_count"] == 2
    assert row["positive_snapshot_count"] == 2
    assert row["disposition"] == "repeat_positive_cost_caveated"
    assert abs(row["latest_all_in_break_even"] - expected_latest_break_even) < 1e-12
    assert "fee is estimated from executable price" in row["robustness_reasons"]


def test_queue_robustness_dedupes_latest_snapshot_by_created_at(tmp_path: Path) -> None:
    robustness = load_robustness_module()
    queue_path = tmp_path / "queue.json"
    snapshot_dir = tmp_path / "snapshots"
    write_json(queue_path, queue_payload(queue_row()))
    write_json(
        snapshot_dir / "kalshi_mlb_game_series_20260701T220000Z.json",
        snapshot_payload(created_at="2026-07-01T22:00:00Z", ask=0.41),
    )
    write_json(
        snapshot_dir / "kalshi_nfl_game_series_latest.json",
        snapshot_payload(created_at="2026-07-01T22:00:00Z", ask=0.42),
    )

    report = robustness.build_queue_robustness(
        queue_path=queue_path,
        snapshot_dir=snapshot_dir,
        generated_utc="2026-07-01T22:05:00Z",
    )

    assert report["summary"]["distinct_snapshot_count"] == 1
    assert report["rows"][0]["latest_all_in_break_even"] == 0.41 + kalshi_trade_fee(price=0.41)
    assert "kalshi_mlb_game_series_20260701T220000Z.json" in report["snapshots"][0]["path"]


def test_queue_robustness_blocks_when_positive_margin_does_not_repeat(tmp_path: Path) -> None:
    robustness = load_robustness_module()
    queue_path = tmp_path / "queue.json"
    snapshot_dir = tmp_path / "snapshots"
    write_json(queue_path, queue_payload(queue_row(calibrated_probability=0.43)))
    write_json(snapshot_dir / "snapshot-1.json", snapshot_payload(created_at="2026-07-01T20:00:00Z", ask=0.40))
    write_json(snapshot_dir / "snapshot-2.json", snapshot_payload(created_at="2026-07-01T22:00:00Z", ask=0.45))

    report = robustness.build_queue_robustness(
        queue_path=queue_path,
        snapshot_dir=snapshot_dir,
        generated_utc="2026-07-01T22:05:00Z",
        min_robust_margin=0.02,
    )

    assert report["status"] == "kalshi_ev_queue_robustness_observed_not_repeat_positive"
    assert report["summary"]["repeat_positive_row_count"] == 0
    row = report["rows"][0]
    assert row["disposition"] == "not_repeat_positive_watch"
    assert "positive margin did not repeat across two snapshots" in row["robustness_reasons"]


def test_queue_robustness_writer_emits_json_markdown_and_csv(tmp_path: Path) -> None:
    robustness = load_robustness_module()
    robustness.MACRO_DIR = tmp_path / "macro"
    queue_path = tmp_path / "queue.json"
    snapshot_dir = tmp_path / "snapshots"
    write_json(queue_path, queue_payload(queue_row()))
    write_json(snapshot_dir / "snapshot-1.json", snapshot_payload(created_at="2026-07-01T20:00:00Z", ask=0.40))

    report = robustness.build_queue_robustness(
        queue_path=queue_path,
        snapshot_dir=snapshot_dir,
        generated_utc="2026-07-01T22:05:00Z",
    )
    paths = robustness.write_queue_robustness(report, out_dir=tmp_path / "out")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    assert Path(paths["latest_json_path"]).exists()
    assert "Kalshi EV Queue Robustness" in Path(paths["markdown_path"]).read_text(encoding="utf-8")


def test_makefile_exposes_queue_robustness_target() -> None:
    content = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-ev-queue-robustness" in content
    assert "scripts/kalshi_ev_queue_robustness.py" in content
