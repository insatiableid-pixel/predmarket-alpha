from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "kalshi_passive_liquidity_fill_clock_diagnostic.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_passive_liquidity_fill_clock_diagnostic", SCRIPT_PATH
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


def safe_artifact(status: str = "ready", **extra):
    payload = {
        "schema_version": 1,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "summary": {},
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }
    payload.update(extra)
    return payload


def micro_row(snapshot_id: str, observed_at: str, *, ask: float = 0.56) -> dict[str, object]:
    return {
        "snapshot_id": snapshot_id,
        "contract_ticker": "KXMLBGAME-26JUL04-BOS",
        "observed_at_utc": observed_at,
        "best_yes_bid": 0.54,
        "best_yes_ask": ask,
        "best_no_bid": 0.44,
        "best_no_ask": 0.46,
        "yes_mid": 0.55,
        "research_only": True,
        "execution_enabled": False,
    }


def paper_intent(index: int, *, ttl_seconds: int = 180) -> dict[str, object]:
    return {
        "paper_intent_id": f"paper-{index}",
        "virtual_order_id": f"virtual-{index}",
        "contract_ticker": "KXMLBGAME-26JUL04-BOS",
        "side": "yes",
        "quote_price": 0.55,
        "quote_size_contracts": 1,
        "entry_snapshot_id": f"entry-{index}",
        "entry_observed_at_utc": "2026-07-04T00:00:00Z",
        "order_expires_at_utc": f"2026-07-04T00:{ttl_seconds // 60:02d}:00Z",
        "ttl_seconds": ttl_seconds,
        "research_only": True,
        "execution_enabled": False,
    }


def paper_label(index: int, *, status: str) -> dict[str, object]:
    return {
        "paper_intent_id": f"paper-{index}",
        "virtual_order_id": f"virtual-{index}",
        "contract_ticker": "KXMLBGAME-26JUL04-BOS",
        "side": "yes",
        "quote_price": 0.55,
        "entry_observed_at_utc": "2026-07-04T00:00:00Z",
        "order_expires_at_utc": "2026-07-04T00:03:00Z",
        "paper_fill_status": status,
        "paper_fill_label_utc": "2026-07-04T00:05:00Z",
        "label_snapshot_id": "late-1",
        "label_observed_at_utc": "2026-07-04T00:04:00Z",
        "label_source": "later_public_orderbook_snapshot",
        "real_exchange_fill": False,
        "research_only": True,
        "execution_enabled": False,
    }


def test_fill_clock_diagnoses_ttl_shorter_than_snapshot_cadence(tmp_path: Path) -> None:
    module = load_module()
    paper_fill = write_json(
        tmp_path / "paper-fill.json",
        safe_artifact(
            "passive_liquidity_paper_fill_loop_ready_with_paper_fill_labels",
            paper_intent_rows=[paper_intent(1, ttl_seconds=180)],
            paper_fill_label_rows=[paper_label(1, status="paper_expired_unfilled_no_public_touch")],
        ),
    )
    micro = write_json(
        tmp_path / "micro.json",
        safe_artifact(
            "sports_microstructure_observation_loop_ready",
            observation_packet={
                "rows": [
                    micro_row("entry-1", "2026-07-04T00:00:00Z", ask=0.56),
                    micro_row("late-1", "2026-07-04T00:04:00Z", ask=0.54),
                ]
            },
        ),
    )

    report = module.build_passive_liquidity_fill_clock_diagnostic(
        paper_fill_path=paper_fill,
        microstructure_path=micro,
        generated_utc="2026-07-04T00:05:00Z",
    )

    assert report["status"] == "passive_liquidity_fill_clock_diagnostic_ready_ttl_cadence_mismatch"
    assert report["execution_enabled"] is False
    assert report["account_or_order_paths"] is False
    assert report["summary"]["paper_intent_count"] == 1
    assert report["summary"]["future_snapshot_within_ttl_intent_count"] == 0
    assert report["summary"]["ttl_cadence_mismatch_count"] == 1
    assert report["summary"]["recommended_ttl_seconds"] >= 600
    row = report["diagnostic_rows"][0]
    assert row["diagnostic_reason"] == "ttl_shorter_than_snapshot_cadence"
    assert row["seconds_to_first_later_snapshot"] == 240.0


def test_fill_clock_reports_paper_touch_fill_when_snapshot_lands_inside_ttl(
    tmp_path: Path,
) -> None:
    module = load_module()
    paper_fill = write_json(
        tmp_path / "paper-fill.json",
        safe_artifact(
            "passive_liquidity_paper_fill_loop_ready_with_paper_fill_labels",
            paper_intent_rows=[paper_intent(1, ttl_seconds=600)],
            paper_fill_label_rows=[paper_label(1, status="paper_filled_from_later_public_touch")],
        ),
    )
    micro = write_json(
        tmp_path / "micro.json",
        safe_artifact(
            "sports_microstructure_observation_loop_ready",
            observation_packet={
                "rows": [
                    micro_row("entry-1", "2026-07-04T00:00:00Z", ask=0.56),
                    micro_row("late-1", "2026-07-04T00:04:00Z", ask=0.54),
                ]
            },
        ),
    )

    report = module.build_passive_liquidity_fill_clock_diagnostic(
        paper_fill_path=paper_fill,
        microstructure_path=micro,
        generated_utc="2026-07-04T00:05:00Z",
    )

    assert report["status"] == "passive_liquidity_fill_clock_diagnostic_ready_with_paper_fills"
    assert report["summary"]["paper_filled_count"] == 1
    assert report["summary"]["future_snapshot_within_ttl_intent_count"] == 1
    assert report["diagnostic_rows"][0]["diagnostic_reason"] == "paper_touch_fill_observed"
    assert report["diagnostic_rows"][0]["first_touch_utc"] == "2026-07-04T00:04:00Z"


def test_fill_clock_separates_historical_ttl_mismatch_from_current_clock(
    tmp_path: Path,
) -> None:
    module = load_module()
    aligned_intent = paper_intent(2, ttl_seconds=600)
    aligned_intent["ttl_seconds"] = 43200
    aligned_intent["order_expires_at_utc"] = "2026-07-04T12:00:00Z"
    paper_fill = write_json(
        tmp_path / "paper-fill.json",
        safe_artifact(
            "passive_liquidity_paper_fill_loop_ready_with_paper_fill_labels",
            paper_intent_rows=[
                paper_intent(1, ttl_seconds=180),
                aligned_intent,
            ],
            paper_fill_label_rows=[
                paper_label(1, status="paper_expired_unfilled_no_public_touch"),
                paper_label(2, status="paper_filled_from_later_public_touch"),
            ],
        ),
    )
    micro = write_json(
        tmp_path / "micro.json",
        safe_artifact(
            "sports_microstructure_observation_loop_ready",
            observation_packet={
                "rows": [
                    micro_row("entry-1", "2026-07-04T00:00:00Z", ask=0.56),
                    micro_row("late-1", "2026-07-04T00:04:00Z", ask=0.54),
                ]
            },
        ),
    )

    report = module.build_passive_liquidity_fill_clock_diagnostic(
        paper_fill_path=paper_fill,
        microstructure_path=micro,
        generated_utc="2026-07-04T00:05:00Z",
    )

    assert report["status"] == "passive_liquidity_fill_clock_diagnostic_ready_with_paper_fills"
    assert report["summary"]["ttl_cadence_mismatch_count"] == 1
    assert report["summary"]["active_ttl_cadence_mismatch_count"] == 0
    assert report["summary"]["current_ttl_cadence_aligned"] is True
    assert report["summary"]["max_ttl_seconds"] == 43200
    assert report["summary"]["fill_clock_primary_bottleneck"] != (
        "ttl_shorter_than_snapshot_cadence"
    )


def test_fill_clock_temp_out_dir_does_not_mutate_macro_latest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    macro_dir = tmp_path / "macro"
    monkeypatch.setattr(module, "MACRO_DIR", macro_dir)
    paper_fill = write_json(
        tmp_path / "paper-fill.json",
        safe_artifact(paper_intent_rows=[paper_intent(1)], paper_fill_label_rows=[]),
    )
    micro = write_json(tmp_path / "micro.json", safe_artifact(observation_packet={"rows": []}))
    report = module.build_passive_liquidity_fill_clock_diagnostic(
        paper_fill_path=paper_fill,
        microstructure_path=micro,
        generated_utc="2026-07-04T00:05:00Z",
    )

    paths = module.write_outputs(report, out_dir=tmp_path / "out")

    assert "latest_json_path" not in paths
    assert not (macro_dir / "latest-kalshi-passive-liquidity-fill-clock-diagnostic.json").exists()


def test_fill_clock_makefile_target_exists() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-passive-liquidity-fill-clock-diagnostic" in text
    assert "scripts/kalshi_passive_liquidity_fill_clock_diagnostic.py" in text
    assert "KALSHI_PASSIVE_LIQUIDITY_TTL_SECONDS ?= 43200" in text
