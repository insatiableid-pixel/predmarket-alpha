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


def test_script_auto_captures_when_target_books_were_not_requested(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_script()
    raw = tmp_path / "soccer_fifa_world_cup_current_20260705T235033Z.json"
    meta = tmp_path / "soccer_fifa_world_cup_current_20260705T235033Z.meta.json"
    key_file = tmp_path / "the_odds_api_key.txt"
    captured_raw = tmp_path / "soccer_fifa_world_cup_current_20260706T000000Z.json"
    raw.write_text(json.dumps([soccer_event([bookmaker("pinnacle")])]), encoding="utf-8")
    meta.write_text(
        json.dumps(
            {
                "created_at_utc": "2026-07-05T23:50:33Z",
                "bookmakers": ["pinnacle", "matchbook"],
                "provider_api_calls": True,
            }
        ),
        encoding="utf-8",
    )
    key_file.write_text("test-key", encoding="utf-8")
    calls: list[tuple[str, ...]] = []

    def fake_capture(**kwargs):
        calls.append(tuple(kwargs["bookmakers"]))
        captured_raw.write_text("[]", encoding="utf-8")
        return (
            [soccer_event([bookmaker("pinnacle")])],
            {
                "created_at_utc": "2026-07-06T00:00:00Z",
                "sport_key": "soccer_fifa_world_cup",
                "bookmakers": list(kwargs["bookmakers"]),
                "provider_api_calls": True,
            },
            captured_raw,
        )

    monkeypatch.setattr(module, "capture_the_odds_api_current", fake_capture)
    args = module.parse_args(
        [
            "--no-include-defaults",
            "--raw-provider-json",
            str(raw),
            "--raw-provider-meta-json",
            str(meta),
            "--capture-current-if-needed",
            "--api-key-file",
            str(key_file),
        ]
    )

    sources = module._load_sources(args)
    report = build_soccer_asian_provider_diagnostic(sources=sources, created_ts=1.0)

    assert calls == [("sbobet", "singbet", "ibc")]
    assert len(sources) == 2
    assert report["status"] == (
        "soccer_asian_provider_diagnostic_blocked_target_books_unavailable_in_feed"
    )
    assert report["summary"]["requested_target_providers"] == ["ibc", "sbobet", "singbet"]


def test_script_auto_capture_skips_when_target_books_were_already_requested(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_script()
    raw = tmp_path / "soccer_fifa_world_cup_current_20260705T235033Z.json"
    meta = tmp_path / "soccer_fifa_world_cup_current_20260705T235033Z.meta.json"
    key_file = tmp_path / "the_odds_api_key.txt"
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
    key_file.write_text("test-key", encoding="utf-8")

    def fail_capture(**kwargs):
        raise AssertionError("auto-capture should reuse explicit target-provider probes")

    monkeypatch.setattr(module, "capture_the_odds_api_current", fail_capture)
    args = module.parse_args(
        [
            "--no-include-defaults",
            "--raw-provider-json",
            str(raw),
            "--raw-provider-meta-json",
            str(meta),
            "--capture-current-if-needed",
            "--api-key-file",
            str(key_file),
        ]
    )

    sources = module._load_sources(args)
    report = build_soccer_asian_provider_diagnostic(sources=sources, created_ts=1.0)

    assert len(sources) == 1
    assert report["summary"]["requested_target_providers"] == ["ibc", "sbobet", "singbet"]


def test_makefile_exposes_soccer_asian_provider_diagnostic() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-consensus-soccer-asian-provider-diagnostic" in text
    assert "KALSHI_SPORTS_CONSENSUS_SOCCER_ASIAN_PROVIDERS ?= sbobet,singbet,ibc" in text
    assert "--capture-current-if-needed" in text
    assert "scripts/kalshi_sports_consensus_soccer_asian_provider_diagnostic.py" in text
