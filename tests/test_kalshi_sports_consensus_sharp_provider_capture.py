from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from predmarket.sports_consensus_sharp_provider_capture import (
    build_sharp_provider_capture_report,
    capture_sharp_provider_sources,
)

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "kalshi_sports_consensus_sharp_provider_capture.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_script():
    spec = importlib.util.spec_from_file_location(
        "kalshi_sports_consensus_sharp_provider_capture", SCRIPT_PATH
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def odds_event(sport_key: str, providers: list[str]) -> dict:
    return {
        "id": f"{sport_key}-event",
        "sport_key": sport_key,
        "commence_time": "2026-07-07T20:00:00Z",
        "home_team": "Home",
        "away_team": "Away",
        "bookmakers": [
            {
                "key": provider,
                "title": provider,
                "last_update": "2026-07-07T17:00:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": "2026-07-07T17:00:00Z",
                        "outcomes": [
                            {"name": "Away", "price": 105},
                            {"name": "Home", "price": -125},
                        ],
                    }
                ],
            }
            for provider in providers
        ],
    }


def test_capture_report_audits_multi_sport_providers_without_exact_mapping() -> None:
    report = build_sharp_provider_capture_report(
        captures=[
            {
                "sport_key": "baseball_mlb",
                "payload": [odds_event("baseball_mlb", ["pinnacle", "smarkets"])],
                "meta": {"sport_key": "baseball_mlb", "status": "odds_api_current_capture_written"},
                "raw_path": None,
                "error": None,
            },
            {
                "sport_key": "soccer_fifa_world_cup",
                "payload": [odds_event("soccer_fifa_world_cup", ["pinnacle", "matchbook"])],
                "meta": {
                    "sport_key": "soccer_fifa_world_cup",
                    "status": "odds_api_current_capture_written",
                },
                "raw_path": None,
                "error": None,
            },
        ],
        requested_sport_keys=("baseball_mlb", "soccer_fifa_world_cup"),
        requested_bookmakers=("pinnacle", "smarkets", "matchbook"),
        created_ts=1.0,
    )

    assert report["status"] == "sports_consensus_sharp_provider_capture_ready"
    assert report["summary"]["sport_count"] == 2
    assert report["summary"]["provider_count"] == 3
    assert report["summary"]["anchor_provider_count"] == 3
    assert report["summary"]["sports_with_provider_rows"] == [
        "baseball_mlb",
        "soccer_fifa_world_cup",
    ]
    assert all(row["usable"] is False for row in report["sport_rows"])
    assert report["safety"]["probabilities_computed"] is False
    assert report["safety"]["paper_or_live_stakes_computed"] is False


def test_capture_sources_preserves_per_sport_errors(tmp_path: Path) -> None:
    def fake_capture(**kwargs):
        sport_key = kwargs["sport_key"]
        if sport_key == "soccer_fifa_world_cup":
            raise OSError("provider unavailable")
        return (
            [odds_event(sport_key, ["pinnacle"])],
            {"sport_key": sport_key, "status": "odds_api_current_capture_written"},
            tmp_path / f"{sport_key}.json",
        )

    captures = capture_sharp_provider_sources(
        api_key="secret",
        sport_keys=("baseball_mlb", "soccer_fifa_world_cup"),
        raw_output_dir=tmp_path,
        capture_current=fake_capture,
    )
    report = build_sharp_provider_capture_report(
        captures=captures,
        requested_sport_keys=("baseball_mlb", "soccer_fifa_world_cup"),
        created_ts=1.0,
    )

    assert report["status"] == "sports_consensus_sharp_provider_capture_ready_with_capture_errors"
    assert report["summary"]["capture_error_count"] == 1
    assert report["summary"]["sports_with_capture_errors"] == ["soccer_fifa_world_cup"]
    assert "secret" not in json.dumps(report)


def test_script_writes_raw_provider_capture_report(tmp_path: Path) -> None:
    module = load_script()
    raw = tmp_path / "soccer_fifa_world_cup_current.json"
    meta = tmp_path / "soccer_fifa_world_cup_current.meta.json"
    out_dir = tmp_path / "out"
    raw.write_text(json.dumps([odds_event("soccer_fifa_world_cup", ["pinnacle"])]), encoding="utf-8")
    meta.write_text(
        json.dumps(
            {
                "sport_key": "soccer_fifa_world_cup",
                "created_at_utc": "2026-07-07T17:00:00Z",
                "quota_headers": {"x-requests-remaining": "123"},
            }
        ),
        encoding="utf-8",
    )

    report = module.run_sharp_provider_capture(
        out_dir=out_dir,
        raw_provider_json=(raw,),
        sport_keys=("soccer_fifa_world_cup",),
        bookmakers=("pinnacle",),
        write=True,
    )

    assert report["status"] == "sports_consensus_sharp_provider_capture_ready"
    assert (out_dir / "kalshi-sports-consensus-sharp-provider-capture.json").is_file()
    latest = out_dir.parent / "latest-kalshi-sports-consensus-sharp-provider-capture.json"
    assert json.loads(latest.read_text(encoding="utf-8"))["summary"]["provider_count"] == 1


def test_makefile_capture_target_uses_dedicated_provider_capture_script() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")
    target = text.split("kalshi-sports-consensus-sharp-provider-capture:", 1)[1].split(
        "\n\n", 1
    )[0]

    assert "scripts/kalshi_sports_consensus_sharp_provider_capture.py" in target
    assert "scripts/kalshi_sports_consensus_reference_build.py" not in target
    assert "--kalshi-json" not in target
    assert "--reference-json" not in target
