from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from predmarket.sports_consensus_soccer_asian_provider import (
    build_soccer_asian_provider_diagnostic,
)

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "kalshi_sports_consensus_soccer_asian_provider_diagnostic.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_script():
    spec = importlib.util.spec_from_file_location(
        "kalshi_sports_consensus_soccer_asian_provider_diagnostic", SCRIPT_PATH
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def soccer_event(bookmakers: list[dict]) -> dict:
    return {
        "id": "evt-1",
        "sport_key": "soccer_fifa_world_cup",
        "home_team": "Brazil",
        "away_team": "Norway",
        "commence_time": "2026-07-05T20:00:00Z",
        "bookmakers": bookmakers,
    }


def bookmaker(key: str) -> dict:
    return {
        "key": key,
        "title": key,
        "markets": [{"key": "h2h", "outcomes": []}],
    }


def test_diagnostic_blocks_when_asian_targets_requested_but_unavailable() -> None:
    report = build_soccer_asian_provider_diagnostic(
        sources=[
            {
                "source_id": "soccer",
                "source_kind": "raw_provider_capture",
                "payload": [soccer_event([bookmaker("pinnacle"), bookmaker("matchbook")])],
                "meta": {
                    "created_at_utc": "2026-07-05T23:50:33Z",
                    "sport_key": "soccer_fifa_world_cup",
                    "bookmakers": ["sbobet", "singbet", "ibc"],
                    "provider_api_calls": True,
                },
            }
        ],
        created_ts=1.0,
    )

    assert report["status"] == "soccer_asian_provider_diagnostic_blocked_target_books_unavailable_in_feed"
    assert report["summary"]["requested_target_providers"] == ["ibc", "sbobet", "singbet"]
    assert report["summary"]["observed_target_provider_count"] == 0
    assert report["summary"]["missing_target_providers"] == ["ibc", "sbobet", "singbet"]
    assert report["next_action"]["name"] == "source_legal_soccer_asian_sharp_feed"
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["market_execution"] is False


def test_diagnostic_reports_ready_when_target_provider_is_observed() -> None:
    report = build_soccer_asian_provider_diagnostic(
        sources=[
            {
                "source_id": "soccer",
                "source_kind": "raw_provider_capture",
                "payload": [soccer_event([bookmaker("SBOBet"), bookmaker("pinnacle")])],
                "meta": {
                    "created_at_utc": "2026-07-05T23:50:33Z",
                    "sport_key": "soccer_fifa_world_cup",
                    "bookmakers": ["sbobet", "pinnacle"],
                },
            }
        ],
        created_ts=1.0,
    )

    assert report["status"] == "soccer_asian_provider_diagnostic_ready_with_asian_sharp_rows"
    assert report["summary"]["observed_target_providers"] == ["sbobet"]
    assert report["summary"]["missing_target_providers"] == ["ibc", "singbet"]
    assert report["target_provider_rows"][0]["provider"] == "sbobet"
    assert report["target_provider_rows"][0]["usable"] is False


def test_script_writes_temp_outputs_without_macro_latest(tmp_path: Path) -> None:
    module = load_script()
    raw = tmp_path / "soccer_fifa_world_cup_current_20260705T235033Z.json"
    meta = tmp_path / "soccer_fifa_world_cup_current_20260705T235033Z.meta.json"
    out_dir = tmp_path / "out"
    raw.write_text(json.dumps([soccer_event([bookmaker("pinnacle")])]), encoding="utf-8")
    meta.write_text(
        json.dumps(
            {
                "created_at_utc": "2026-07-05T23:50:33Z",
                "bookmakers": ["sbobet", "singbet", "ibc"],
                "provider_api_calls": True,
            }
        ),
        encoding="utf-8",
    )

    args = module.parse_args(
        [
            "--no-include-defaults",
            "--raw-provider-json",
            str(raw),
            "--raw-provider-meta-json",
            str(meta),
            "--out-dir",
            str(out_dir),
        ]
    )
    sources = module._load_sources(args)
    report = build_soccer_asian_provider_diagnostic(sources=sources, created_ts=1.0)
    paths = module.write_outputs(report, out_dir)

    loaded = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert loaded["status"] == (
        "soccer_asian_provider_diagnostic_blocked_target_books_unavailable_in_feed"
    )
    assert (out_dir / "kalshi-sports-consensus-soccer-asian-provider-diagnostic.md").is_file()
    latest = module.MACRO_DIR / "latest-kalshi-sports-consensus-soccer-asian-provider-diagnostic.json"
    assert not latest.exists() or json.loads(latest.read_text()).get("run_id") != loaded["run_id"]


def test_makefile_exposes_soccer_asian_provider_diagnostic() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-consensus-soccer-asian-provider-diagnostic" in text
    assert "KALSHI_SPORTS_CONSENSUS_SOCCER_ASIAN_PROVIDERS ?= sbobet,singbet,ibc" in text
    assert "scripts/kalshi_sports_consensus_soccer_asian_provider_diagnostic.py" in text
