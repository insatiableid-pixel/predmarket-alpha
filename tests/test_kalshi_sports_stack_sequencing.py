from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_stack_sequencing.py"
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_module():
    spec = importlib.util.spec_from_file_location("kalshi_sports_stack_sequencing", SCRIPT_PATH)
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
        "status": "ready",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "summary": {},
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }
    payload.update(overrides)
    return payload


def safe_universe() -> dict[str, object]:
    base = {
        "schema_version": 1,
        "status": "ready",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }
    rows = [
        ("KXWCGAME-26JUL04-USA", "other_sports", "KXWCGAME"),
        ("KXMLBGAME-26JUL04-CHC", "mlb", "KXMLBGAME"),
        ("KXATPMATCH-26JUL04-DJO", "atp", "KXATPMATCH"),
        ("KXNFLGAME-26AUG03-DAL", "nfl", "KXNFLGAME"),
        ("KXNBA-26JUL04-BOS", "nba", "KXNBA"),
        ("KXCPI-26JUL15-HIGH", "macro_econ", "KXCPI"),
        ("KXELECTION-26NOV03-YES", "politics_policy", "KXELECTION"),
    ]
    base["candidates"] = [
        {
            "ticker": ticker,
            "event_ticker": ticker.rsplit("-", maxsplit=1)[0],
            "classification": classification,
            "series_ticker": series,
            "gate_status": "pass",
            "settlement_time": "2026-07-04T20:00:00Z",
        }
        for ticker, classification, series in rows
    ]
    return base


def test_sports_stack_sequences_current_surfaces_without_feature_layer_merging(
    tmp_path: Path,
) -> None:
    module = load_module()
    universe_path = tmp_path / "universe.json"
    ghost_path = tmp_path / "ghost.json"
    write_json(universe_path, safe_universe())
    write_json(
        ghost_path,
        safe_artifact(
            status="ghost_listing_depth_diagnostic_current_depth_ready",
            summary={"cap_i_lock_allowed": True},
        ),
    )

    report = module.build_sports_stack_sequencing(
        universe_scan_path=universe_path,
        ghost_depth_path=ghost_path,
        generated_utc="2026-07-03T20:00:00Z",
    )

    rows = report["sequence_rows"]
    assert report["status"] == "sports_stack_sequencing_ready_current_depth_passed"
    assert [row["surface_id"] for row in rows[:3]] == ["world_cup_soccer", "mlb", "atp"]
    assert rows[-1]["surface_id"] == "nba"
    assert all(row["adaptation_layer"] == "output_layer_only" for row in rows)
    assert all("feature" in row["feature_layer_action"].lower() for row in rows)
    assert report["summary"]["cap_i_lock_allowed"] is True
    assert report["safety"]["market_execution"] is False
    blocker_rows = report["paper_decision_blocker_rows"]
    assert {row["family_id"] for row in blocker_rows} >= {
        "world_cup_soccer",
        "mlb_sports",
        "atp_tennis",
    }
    assert all(row["usable"] is False for row in blocker_rows)
    assert all(row["execution_enabled"] is False for row in blocker_rows)
    assert any("EV ledger promotion" in "; ".join(row["blocker_list"]) for row in blocker_rows)


def test_sports_stack_blocks_cap_lock_when_ghost_depth_is_missing(tmp_path: Path) -> None:
    module = load_module()
    universe_path = tmp_path / "universe.json"
    write_json(universe_path, safe_universe())

    report = module.build_sports_stack_sequencing(
        universe_scan_path=universe_path,
        ghost_depth_path=tmp_path / "missing-ghost.json",
        generated_utc="2026-07-03T20:00:00Z",
    )

    assert report["status"] == "sports_stack_sequencing_ready_cap_i_lock_blocked"
    assert report["summary"]["cap_i_lock_allowed"] is False
    assert any(
        gate["name"] == "ghost_listing_depth_before_cap_i" and gate["status"] == "blocked"
        for gate in report["gates"]
    )


def test_medium_term_families_are_not_directional_signal_bar() -> None:
    module = load_module()

    families = {row["family_id"]: row for row in module.medium_term_families()}

    assert set(families) == {"near_resolution_informed_flow", "passive_liquidity_provision"}
    assert families["near_resolution_informed_flow"]["acceptance_metric"] == (
        "pre_close_flow_lead_lag_survival"
    )
    assert families["passive_liquidity_provision"]["acceptance_metric"] == (
        "maker_fill_net_ev_after_adverse_selection"
    )
    assert all("not_directional_signal_bar" in row["graded_against"] for row in families.values())


def test_sports_stack_makefile_target_exists() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-stack-sequencing" in makefile
    assert "scripts/kalshi_sports_stack_sequencing.py" in makefile
