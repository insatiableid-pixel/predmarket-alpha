from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from predmarket.sports_consensus_provider_policy import (
    DEFAULT_PROVIDER_AUDIT_TARGET_SPORTS,
    build_provider_audit,
    collect_provider_observations,
    is_anchor_provider,
    normalize_provider_id,
    provider_spec,
)

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_consensus_provider_audit.py"
)


def load_script():
    spec = importlib.util.spec_from_file_location(
        "kalshi_sports_consensus_provider_audit", SCRIPT_PATH
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_provider_aliases_classify_sharp_anchors_and_exchanges() -> None:
    assert normalize_provider_id("Pinnacle Sports") == "pinnacle"
    assert normalize_provider_id("Circa Sports") == "circa"
    assert normalize_provider_id("Betfair Exchange UK") == "betfair_exchange"
    assert normalize_provider_id("betonlineag") == "betonlineag"
    assert is_anchor_provider("pinnacle")
    assert is_anchor_provider("circa")
    assert is_anchor_provider("matchbook")
    assert not is_anchor_provider("lowvig")
    assert provider_spec("draftkings").role == "comparison_only"


def test_collects_provider_observations_from_consensus_rows_and_bookmakers() -> None:
    payload = {
        "rows": [
            {"book_id": "lowvig", "sport_key": "baseball_mlb", "market_key": "h2h"},
            {"provider_key": "Betfair Exchange UK", "sport": "tennis", "market_type": "h2h"},
            {
                "bookmakers": [
                    {
                        "key": "pinnacle",
                        "title": "Pinnacle",
                        "markets": [{"key": "h2h"}],
                    }
                ]
            },
            {"key": "spreads", "last_update": "2026-07-04T20:00:00Z"},
        ]
    }
    observations = collect_provider_observations(payload, source_id="fixture")
    provider_ids = {row.provider_id for row in observations}
    assert {"lowvig", "betfair_exchange", "pinnacle"}.issubset(provider_ids)
    assert "spreads" not in provider_ids


def test_raw_odds_api_bookmaker_inherits_parent_sport_and_market() -> None:
    payload = [
        {
            "id": "evt-1",
            "sport_key": "baseball_mlb",
            "commence_time": "2026-07-04T20:06:00Z",
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "title": "Pinnacle",
                    "markets": [{"key": "h2h", "outcomes": []}],
                }
            ],
        }
    ]

    observations = collect_provider_observations(
        payload,
        source_id="raw",
        source_kind="raw_provider_capture",
    )

    pinnacle = [row for row in observations if row.provider_id == "pinnacle"]
    assert len(pinnacle) == 1
    assert pinnacle[0].sport == "baseball_mlb"
    assert pinnacle[0].market == "h2h"


def test_raw_anchor_availability_is_reported_per_sport_before_wrapping() -> None:
    report = build_provider_audit(
        [
            {
                "source_id": "raw",
                "source_kind": "raw_provider_capture",
                "payload": [
                    {
                        "id": "evt-1",
                        "sport_key": "americanfootball_nfl",
                        "bookmakers": [
                            {
                                "key": "pinnacle",
                                "title": "Pinnacle",
                                "markets": [{"key": "h2h", "outcomes": []}],
                            }
                        ],
                    }
                ],
            }
        ],
        created_ts=1.0,
        target_sports=("nfl",),
    )

    coverage = report["sport_coverage"][0]
    assert report["status"] == "sports_consensus_provider_audit_ready_with_per_sport_gaps"
    assert coverage["sport"] == "nfl"
    assert coverage["coverage_status"] == "raw_anchor_not_wrapped"
    assert coverage["raw_anchor_providers"] == ["pinnacle"]
    assert report["summary"]["raw_anchor_provider_count"] == 1


def test_current_shape_strict_secondary_with_donor_exchange_reports_gap() -> None:
    report = build_provider_audit(
        [
            {
                "source_id": "strict",
                "source_kind": "strict_consensus",
                "source_path": "/tmp/strict.json",
                "payload": {
                    "rows": [
                        {"book_id": "lowvig", "sport_key": "baseball_mlb", "market_key": "h2h"},
                        {
                            "book_id": "betonlineag",
                            "sport_key": "baseball_mlb",
                            "market_key": "h2h",
                        },
                    ]
                },
            },
            {
                "source_id": "atp",
                "source_kind": "donor_consensus",
                "source_path": "/tmp/atp.jsonl",
                "payload": {
                    "rows": [
                        {
                            "provider_key": "matchbook",
                            "provider": "Matchbook Exchange",
                            "sport": "tennis",
                            "market_type": "match_winner",
                        }
                    ]
                },
            },
        ],
        run_id="unit",
        created_ts=1.0,
    )
    assert report["status"] == "sports_consensus_provider_audit_ready_with_per_sport_gaps"
    assert report["summary"]["strict_anchor_provider_count"] == 0
    assert report["summary"]["donor_anchor_provider_count"] == 1
    assert report["summary"]["sport_covered_count"] == 0
    reasons = {gap["reason"] for gap in report["coverage_gaps"]}
    assert "strict_consensus_missing_anchor_provider" in reasons
    assert "sharp_donor_provider_not_adapted" in reasons
    assert "mlb_strict_consensus_not_mature" in reasons
    assert "tennis_strict_consensus_not_mature" in reasons


def test_strict_pinnacle_and_circa_feed_is_anchor_present() -> None:
    report = build_provider_audit(
        [
            {
                "source_id": "strict",
                "source_kind": "strict_consensus",
                "payload": {
                    "rows": [
                        {"book_id": "pinnacle", "sport_key": "tennis", "market_key": "h2h"},
                        {"book_id": "matchbook", "sport_key": "tennis", "market_key": "h2h"},
                        {"book_id": "pinnacle", "sport_key": "baseball_mlb", "market_key": "h2h"},
                        {"book_id": "circa", "sport_key": "baseball_mlb", "market_key": "h2h"},
                    ]
                },
            }
        ],
        created_ts=1.0,
    )
    assert (
        report["status"] == "sports_consensus_provider_audit_ready_all_target_sports_anchor_covered"
    )
    assert report["summary"]["strict_anchor_provider_count"] == 3
    assert report["summary"]["sport_covered_count"] == 2
    assert all(
        gap["reason"] != "strict_consensus_missing_anchor_provider"
        for gap in report["coverage_gaps"]
    )


def test_soft_books_are_comparison_only_not_anchor() -> None:
    report = build_provider_audit(
        [
            {
                "source_id": "strict",
                "source_kind": "strict_consensus",
                "payload": {
                    "rows": [
                        {"book_id": "draftkings", "sport_key": "nfl", "market_key": "h2h"},
                        {"book_id": "fanduel", "sport_key": "nfl", "market_key": "h2h"},
                    ]
                },
            }
        ],
        created_ts=1.0,
    )
    assert report["status"] == "sports_consensus_provider_audit_ready_with_per_sport_gaps"
    roles = {row["provider_id"]: row["role"] for row in report["providers"]}
    assert roles == {"draftkings": "comparison_only", "fanduel": "comparison_only"}
    assert report["summary"]["strict_anchor_provider_count"] == 0
    assert report["sport_coverage"][0]["coverage_status"] == "secondary_only"


def test_target_sport_coverage_prevents_atp_masking_other_sports() -> None:
    report = build_provider_audit(
        [
            {
                "source_id": "strict",
                "source_kind": "strict_consensus",
                "payload": {
                    "rows": [
                        {"book_id": "pinnacle", "sport_key": "tennis_atp", "market_key": "h2h"},
                        {"book_id": "matchbook", "sport_key": "tennis_atp", "market_key": "h2h"},
                    ]
                },
            }
        ],
        created_ts=1.0,
        target_sports=DEFAULT_PROVIDER_AUDIT_TARGET_SPORTS,
    )

    assert report["status"] == "sports_consensus_provider_audit_ready_with_per_sport_gaps"
    coverage = {row["sport"]: row["coverage_status"] for row in report["sport_coverage"]}
    assert coverage["tennis"] == "covered"
    assert coverage["mlb"] == "missing_strict_consensus"
    assert coverage["soccer"] == "missing_asian_sharp_reference"
    assert coverage["nfl"] == "missing_strict_consensus"
    assert coverage["nba"] == "missing_strict_consensus"
    assert report["summary"]["sport_covered_count"] == 1
    assert report["summary"]["sport_gap_count"] == 4


def test_deferred_target_sport_stays_visible_without_actionable_gap() -> None:
    report = build_provider_audit(
        [
            {
                "source_id": "strict",
                "source_kind": "strict_consensus",
                "payload": {
                    "rows": [
                        {"book_id": "pinnacle", "sport_key": "tennis_atp", "market_key": "h2h"},
                        {"book_id": "matchbook", "sport_key": "tennis_atp", "market_key": "h2h"},
                    ]
                },
            }
        ],
        created_ts=1.0,
        target_sports=("tennis", "nba"),
        deferred_sports=("nba",),
    )

    coverage = {row["sport"]: row for row in report["sport_coverage"]}
    assert coverage["tennis"]["coverage_status"] == "covered"
    assert coverage["nba"]["coverage_status"] == "deferred_no_current_rows"
    assert report["status"] == "sports_consensus_provider_audit_ready_with_deferred_target_sports"
    assert report["summary"]["sport_target_count"] == 2
    assert report["summary"]["sport_covered_count"] == 1
    assert report["summary"]["sport_deferred_count"] == 1
    assert report["summary"]["sport_gap_count"] == 0
    assert report["summary"]["deferred_sports"] == ["nba"]
    assert report["summary"]["actionable_gap_sports"] == []
    assert all("nba_" not in gap["reason"] for gap in report["coverage_gaps"])


def test_incompatible_market_sport_stays_visible_without_actionable_gap() -> None:
    report = build_provider_audit(
        [
            {
                "source_id": "raw_atp",
                "source_kind": "raw_provider_capture",
                "payload": {
                    "sport_key": "tennis_atp_wimbledon",
                    "bookmakers": [
                        {"key": "pinnacle", "title": "Pinnacle", "markets": [{"key": "h2h"}]},
                        {
                            "key": "matchbook",
                            "title": "Matchbook Exchange",
                            "markets": [{"key": "h2h"}],
                        },
                    ],
                },
            }
        ],
        created_ts=1.0,
        target_sports=("tennis", "soccer"),
        incompatible_market_sports=("tennis",),
    )

    coverage = {row["sport"]: row for row in report["sport_coverage"]}
    assert coverage["tennis"]["coverage_status"] == "deferred_no_compatible_current_market"
    assert coverage["soccer"]["coverage_status"] == "missing_asian_sharp_reference"
    assert report["status"] == "sports_consensus_provider_audit_ready_with_per_sport_gaps"
    assert report["summary"]["deferred_sports"] == ["tennis"]
    assert report["summary"]["actionable_gap_sports"] == ["soccer"]
    assert all(gap.get("sport") != "tennis" for gap in report["coverage_gaps"])


def test_soccer_fifa_world_cup_strict_rows_are_counted_but_need_asian_sharp() -> None:
    report = build_provider_audit(
        [
            {
                "source_id": "strict",
                "source_kind": "strict_consensus",
                "payload": {
                    "rows": [
                        {
                            "book_id": "pinnacle",
                            "sport_key": "soccer_fifa_world_cup",
                            "market_key": "h2h",
                        },
                        {
                            "book_id": "matchbook",
                            "sport_key": "soccer_fifa_world_cup",
                            "market_key": "h2h",
                        },
                    ]
                },
            }
        ],
        created_ts=1.0,
        target_sports=DEFAULT_PROVIDER_AUDIT_TARGET_SPORTS,
    )

    coverage = {row["sport"]: row for row in report["sport_coverage"]}
    assert coverage["soccer"]["strict_provider_count"] == 2
    assert coverage["soccer"]["strict_anchor_providers"] == ["matchbook", "pinnacle"]
    assert coverage["soccer"]["coverage_status"] == "missing_asian_sharp_reference"
    assert report["summary"]["strict_consensus_sports"] == ["soccer"]
    assert report["summary"]["strict_consensus_sport_count"] == 1
    assert report["summary"]["sport_covered_count"] == 0


def test_basketball_nba_strict_rows_can_cover_nba_target_sport() -> None:
    report = build_provider_audit(
        [
            {
                "source_id": "strict",
                "source_kind": "strict_consensus",
                "payload": {
                    "rows": [
                        {"book_id": "pinnacle", "sport_key": "basketball_nba", "market_key": "h2h"},
                        {"book_id": "circa", "sport_key": "basketball_nba", "market_key": "h2h"},
                    ]
                },
            }
        ],
        created_ts=1.0,
        target_sports=("nba",),
    )

    coverage = report["sport_coverage"][0]
    assert coverage["sport"] == "nba"
    assert coverage["coverage_status"] == "covered"
    assert coverage["strict_provider_count"] == 2
    assert coverage["strict_anchor_providers"] == ["circa", "pinnacle"]
    assert report["summary"]["sport_covered_count"] == 1


def test_script_writes_temp_outputs_without_mutating_macro_latest(tmp_path: Path) -> None:
    module = load_script()
    strict = tmp_path / "strict.json"
    strict.write_text(
        json.dumps(
            {
                "rows": [
                    {"book_id": "lowvig", "sport_key": "baseball_mlb", "market_key": "h2h"},
                    {
                        "book_id": "betonlineag",
                        "sport_key": "baseball_mlb",
                        "market_key": "h2h",
                    },
                ]
            }
        )
    )
    out_dir = tmp_path / "out"
    report = module.build_provider_audit(
        [
            {
                "source_id": "strict",
                "source_kind": "strict_consensus",
                "source_path": str(strict),
                "payload": json.loads(strict.read_text()),
            }
        ],
        run_id="temp",
        created_ts=1.0,
    )
    paths = module.write_outputs(report, out_dir)
    loaded = json.loads(paths["json"].read_text())
    assert loaded["status"] == "sports_consensus_provider_audit_ready_with_per_sport_gaps"
    latest = module.MACRO_DIR / "latest-kalshi-sports-consensus-provider-audit.json"
    assert not latest.exists() or json.loads(latest.read_text()).get("run_id") != "temp"


def test_script_default_source_loader_accepts_local_json_and_jsonl(tmp_path: Path) -> None:
    module = load_script()
    strict = tmp_path / "strict.json"
    donor = tmp_path / "donor.jsonl"
    strict.write_text(json.dumps({"rows": [{"book_id": "lowvig"}]}))
    donor.write_text(json.dumps({"provider_key": "Betfair Exchange UK", "sport": "tennis"}) + "\n")
    args = module.parse_args(
        [
            "--no-include-defaults",
            "--strict-consensus-json",
            str(strict),
            "--donor-jsonl",
            str(donor),
        ]
    )
    sources = module._load_sources(args)
    report = build_provider_audit(sources, created_ts=1.0)
    assert report["summary"]["strict_consensus_provider_count"] == 1
    assert report["summary"]["donor_anchor_provider_count"] == 1


def test_makefile_wires_nba_as_deferred_provider_audit_target() -> None:
    text = Path("Makefile").read_text(encoding="utf-8")
    assert "KALSHI_SPORTS_CONSENSUS_PROVIDER_AUDIT_DEFERRED_SPORTS ?= nba" in text
    assert "--deferred-target-sports $(KALSHI_SPORTS_CONSENSUS_PROVIDER_AUDIT_DEFERRED_SPORTS)" in text
    assert "kalshi-sports-consensus-soccer-asian-provider-diagnostic" in text
