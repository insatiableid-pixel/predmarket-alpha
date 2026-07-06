from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_probability_breadth_scout.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_scout_module():
    spec = importlib.util.spec_from_file_location("kalshi_probability_breadth_scout", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def safe_universe(candidates):
    return {
        "schema_version": 1,
        "status": "universe_scan_ready_with_model_routes",
        "research_only": True,
        "execution_enabled": False,
        "summary": {"candidate_count": len(candidates)},
        "candidates": candidates,
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }


def candidate(**overrides):
    row = {
        "ticker": "KXBTC15M-26JUL012015-15",
        "event_ticker": "KXBTC15M-26JUL012015",
        "series_ticker": "KXBTC15M",
        "classification": "finance_crypto",
        "title": "BTC price up in next 15 mins?",
        "time_to_close_hours": 0.25,
        "yes_bid": 0.21,
        "yes_ask": 0.22,
        "yes_spread": 0.01,
        "softness_score": 0.42,
        "model_route": "soft_market_research_backlog",
    }
    row.update(overrides)
    return row


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def fake_fetch(url: str):
    if "coinbase" in url:
        return {"price": "60000.00", "time": "2026-07-01T23:59:00Z"}
    return {"error": [], "result": {"XXBTZUSD": {"c": ["60001.0", "1"]}}}


def test_probability_breadth_scout_selects_crypto_fast_route_and_keeps_proxy_caveat(
    tmp_path: Path,
) -> None:
    module = load_scout_module()
    universe_path = tmp_path / "universe.json"
    write_json(
        universe_path,
        safe_universe(
            [
                candidate(),
                candidate(
                    ticker="KXHIGHNY-26JUL01-T90", classification="weather", time_to_close_hours=4.0
                ),
                candidate(ticker="SLOW", classification="mlb", time_to_close_hours=24.0),
            ]
        ),
    )

    report = module.build_probability_breadth_scout(
        universe_scan_path=universe_path,
        max_close_hours=6,
        generated_utc="2026-07-02T00:00:00Z",
        probe_public_sources=True,
        raw_probe_dir=Path("/tmp") / f"kalshi_probability_sources_{tmp_path.name}",
        fetch_json=fake_fetch,
    )

    assert report["status"] == "probability_breadth_scout_ready_crypto_proxy_feature_route"
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["safety"]["market_execution"] is False
    assert report["summary"]["crypto_fast_candidate_count"] == 1
    assert report["summary"]["weather_fast_candidate_count"] == 1
    assert report["summary"]["available_proxy_source_count"] == 4
    assert (
        report["source_plan"]["official_settlement_source"]
        == "CF Benchmarks Real-Time Indices (RTIs)"
    )
    assert (
        report["source_plan"]["official_source_availability"]
        == "authenticated_or_licensed_required"
    )
    assert "model features only" in report["source_plan"]["proxy_policy"]
    assert report["proxy_probe"]["raw_snapshot_outside_repo"] is True
    assert all(row["usable"] is False for row in report["work_order_candidates"])
    assert all(row["calibrated_probability"] is None for row in report["work_order_candidates"])
    assert "proxy prices as official labels" in report["next_action"]["stop_condition"]


def test_probability_breadth_scout_excludes_non_crypto_finance_rows_from_crypto_route(
    tmp_path: Path,
) -> None:
    module = load_scout_module()
    universe_path = tmp_path / "universe.json"
    write_json(
        universe_path,
        safe_universe(
            [
                candidate(),
                candidate(
                    ticker="KXAAAGASD-26JUL02-3.805",
                    event_ticker="KXAAAGASD-26JUL02",
                    series_ticker="KXAAAGASD",
                    title="Will average gas prices be above $3.805?",
                    time_to_close_hours=0.5,
                ),
            ]
        ),
    )

    report = module.build_probability_breadth_scout(
        universe_scan_path=universe_path,
        max_close_hours=6,
        generated_utc="2026-07-02T00:00:00Z",
    )

    assert report["summary"]["fast_candidate_count"] == 2
    assert report["summary"]["crypto_fast_candidate_count"] == 1
    assert report["summary"]["crypto_series_counts"] == {"KXBTC15M": 1}
    assert [row["ticker"] for row in report["work_order_candidates"]] == ["KXBTC15M-26JUL012015-15"]


def test_probability_breadth_scout_can_run_without_public_probe(tmp_path: Path) -> None:
    module = load_scout_module()
    universe_path = tmp_path / "universe.json"
    write_json(universe_path, safe_universe([candidate()]))

    report = module.build_probability_breadth_scout(
        universe_scan_path=universe_path,
        max_close_hours=6,
        generated_utc="2026-07-02T00:00:00Z",
        probe_public_sources=False,
    )

    assert report["status"] == "probability_breadth_scout_ready_crypto_route_needs_proxy_probe"
    assert report["public_market_data_calls"] is False
    assert report["provider_api_calls"] is False
    assert report["proxy_probe"]["status"] == "public_proxy_probe_not_run"


def test_probability_breadth_scout_blocks_without_safe_universe_scan(tmp_path: Path) -> None:
    module = load_scout_module()
    universe_path = tmp_path / "unsafe.json"
    write_json(universe_path, {"research_only": False, "candidates": [candidate()]})

    report = module.build_probability_breadth_scout(
        universe_scan_path=universe_path,
        generated_utc="2026-07-02T00:00:00Z",
    )

    assert report["status"] == "probability_breadth_scout_blocked_missing_safe_universe_scan"


def test_probability_breadth_scout_writes_latest_artifacts(tmp_path: Path) -> None:
    module = load_scout_module()
    module.MACRO_DIR = tmp_path / "macro"
    universe_path = tmp_path / "universe.json"
    write_json(universe_path, safe_universe([candidate()]))
    report = module.build_probability_breadth_scout(
        universe_scan_path=universe_path,
        generated_utc="2026-07-02T00:00:00Z",
    )

    paths = module.write_probability_breadth_scout(report, out_dir=tmp_path / "out")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    written = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    assert written["status"] == "probability_breadth_scout_ready_crypto_route_needs_proxy_probe"


def test_makefile_exposes_probability_breadth_scout_target() -> None:
    content = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-probability-breadth-scout" in content
    assert "scripts/kalshi_probability_breadth_scout.py" in content


# ---------------------------------------------------------------------------
# Family-aware sports routing (VAL-ORCH-007..014, 027..031, 034)
# ---------------------------------------------------------------------------


def sports_candidate(**overrides):
    row = {
        "ticker": "KXMLBGAME-26JUL02-CWSBAL-PRICE",
        "event_ticker": "KXMLBGAME-26JUL02-CWSBAL",
        "series_ticker": "KXMLBGAME",
        "classification": "mlb",
        "title": "MLB game winner: CWS vs BAL",
        "time_to_close_hours": 3.0,
        "yes_bid": 0.55,
        "yes_ask": 0.57,
        "yes_spread": 0.02,
        "softness_score": 0.30,
        "model_route": "soft_market_research_backlog",
    }
    row.update(overrides)
    return row


def test_scout_routes_sports_game_winner_to_sports_route(tmp_path: Path) -> None:
    """VAL-ORCH-007: KXMLBGAME/KXKBOGAME/KXLMBGAME route to a sports route."""
    module = load_scout_module()
    universe_path = tmp_path / "universe.json"
    write_json(
        universe_path,
        safe_universe(
            [
                sports_candidate(),
                sports_candidate(series_ticker="KXKBOGAME", ticker="KXKBOGAME-26JUL02-KTWHAN"),
                sports_candidate(series_ticker="KXLMBGAME", ticker="KXLMBGAME-26JUL02-DIRMON"),
            ]
        ),
    )

    report = module.build_probability_breadth_scout(
        universe_scan_path=universe_path,
        max_close_hours=6,
        generated_utc="2026-07-02T00:00:00Z",
    )

    assert report["summary"]["selected_route"] == "sports_baseball_fast_label_route"
    assert report["status"] == "probability_breadth_scout_ready_sports_baseball_route"
    assert report["summary"]["sports_fast_candidate_count"] == 3


def test_scout_surfaces_both_crypto_and_sports_when_both_present(tmp_path: Path) -> None:
    """VAL-ORCH-008: sports candidates surface even when crypto wins selected_route."""
    module = load_scout_module()
    universe_path = tmp_path / "universe.json"
    write_json(
        universe_path,
        safe_universe(
            [
                candidate(),
                sports_candidate(),
            ]
        ),
    )

    report = module.build_probability_breadth_scout(
        universe_scan_path=universe_path,
        max_close_hours=6,
        generated_utc="2026-07-02T00:00:00Z",
    )

    assert report["summary"]["crypto_fast_candidate_count"] == 1
    assert report["summary"]["sports_fast_candidate_count"] == 1
    assert "sports_baseball" in report["summary"]["fast_classification_counts"]
    assert report["summary"]["fast_classification_counts"]["sports_baseball"] == 1
    sports_rows = [
        r for r in report["work_order_candidates"] if "sports" in (r.get("source_route") or "")
    ]
    assert len(sports_rows) == 1
    assert sports_rows[0]["ticker"] == "KXMLBGAME-26JUL02-CWSBAL-PRICE"
    crypto_rows = [
        r for r in report["work_order_candidates"] if "crypto" in (r.get("source_route") or "")
    ]
    assert len(crypto_rows) == 1


def test_scout_sports_only_universe_routes_to_sports_not_no_route(tmp_path: Path) -> None:
    """VAL-ORCH-009: empty crypto + non-empty sports -> sports route, not no-route."""
    module = load_scout_module()
    universe_path = tmp_path / "universe.json"
    write_json(universe_path, safe_universe([sports_candidate()]))

    report = module.build_probability_breadth_scout(
        universe_scan_path=universe_path,
        max_close_hours=6,
        generated_utc="2026-07-02T00:00:00Z",
    )

    assert report["summary"]["selected_route"] == "sports_baseball_fast_label_route"
    assert report["summary"]["sports_fast_candidate_count"] == 1


def test_scout_sports_source_plan_names_game_results_not_cf_benchmarks(tmp_path: Path) -> None:
    """VAL-ORCH-010: sports source plan references game results/box scores, statsapi/ESPN."""
    module = load_scout_module()
    universe_path = tmp_path / "universe.json"
    write_json(universe_path, safe_universe([sports_candidate()]))

    report = module.build_probability_breadth_scout(
        universe_scan_path=universe_path,
        max_close_hours=6,
        generated_utc="2026-07-02T00:00:00Z",
    )

    plan = report["source_plan"]
    assert plan["route"] == "sports_baseball_fast_label_route"
    assert (
        "game result" in plan["official_settlement_source"].lower()
        or "box score" in plan["official_settlement_source"].lower()
    )
    assert "CF Benchmarks" not in str(plan["official_settlement_source"])
    proxy_sources = str(plan["proxy_feature_sources"])
    assert "statsapi" in proxy_sources.lower() or "mlb stats" in proxy_sources.lower()
    assert "espn" in proxy_sources.lower()
    assert "coinbase" not in proxy_sources.lower()
    assert "label" in plan["proxy_policy"].lower()


def test_scout_all_empty_universe_returns_no_fast_route(tmp_path: Path) -> None:
    """VAL-ORCH-011: all-empty -> no_fast route, no crash, sports count == 0."""
    module = load_scout_module()
    universe_path = tmp_path / "universe.json"
    write_json(
        universe_path,
        safe_universe([candidate(ticker="SLOW", classification="mlb", time_to_close_hours=24.0)]),
    )

    report = module.build_probability_breadth_scout(
        universe_scan_path=universe_path,
        max_close_hours=6,
        generated_utc="2026-07-02T00:00:00Z",
    )

    assert report["summary"]["selected_route"] == "no_fast_probability_breadth_route"
    assert report["status"] == "probability_breadth_scout_blocked_no_fast_route"
    assert report["summary"]["sports_fast_candidate_count"] == 0
    assert all(
        "sports" not in (r.get("source_route") or "") for r in report["work_order_candidates"]
    )


def test_scout_route_selection_is_order_independent(tmp_path: Path) -> None:
    """VAL-ORCH-012: reversed row order yields same selected_route and counts."""
    module = load_scout_module()
    base_sports = [
        sports_candidate(ticker="KXMLBGAME-A"),
        sports_candidate(series_ticker="KXKBOGAME", ticker="KXKBOGAME-B"),
    ]
    base_crypto = [candidate()]
    order_a = base_crypto + base_sports
    order_b = list(reversed(order_a))

    path_a = tmp_path / "universe_a.json"
    path_b = tmp_path / "universe_b.json"
    write_json(path_a, safe_universe(order_a))
    write_json(path_b, safe_universe(order_b))

    report_a = module.build_probability_breadth_scout(
        universe_scan_path=path_a, max_close_hours=6, generated_utc="2026-07-02T00:00:00Z"
    )
    report_b = module.build_probability_breadth_scout(
        universe_scan_path=path_b, max_close_hours=6, generated_utc="2026-07-02T00:00:00Z"
    )

    assert report_a["summary"]["selected_route"] == report_b["summary"]["selected_route"]
    assert (
        report_a["summary"]["sports_fast_candidate_count"]
        == report_b["summary"]["sports_fast_candidate_count"]
    )
    tickers_a = {
        r["ticker"]
        for r in report_a["work_order_candidates"]
        if "sports" in (r.get("source_route") or "")
    }
    tickers_b = {
        r["ticker"]
        for r in report_b["work_order_candidates"]
        if "sports" in (r.get("source_route") or "")
    }
    assert tickers_a == tickers_b


def test_scout_weather_route_preserved_when_sports_absent(tmp_path: Path) -> None:
    """VAL-ORCH-013: weather-only universe still selects weather route."""
    module = load_scout_module()
    universe_path = tmp_path / "universe.json"
    write_json(
        universe_path,
        safe_universe(
            [
                candidate(
                    ticker="KXHIGHNY-26JUL01-T90", classification="weather", time_to_close_hours=4.0
                )
            ]
        ),
    )

    report = module.build_probability_breadth_scout(
        universe_scan_path=universe_path,
        max_close_hours=6,
        generated_utc="2026-07-02T00:00:00Z",
    )

    assert report["summary"]["selected_route"] == "weather_fast_reference_route"
    assert report["summary"]["sports_fast_candidate_count"] == 0


def test_scout_summary_has_explicit_sports_candidate_count_field(tmp_path: Path) -> None:
    """VAL-ORCH-014: sports_fast_candidate_count is always an int."""
    module = load_scout_module()
    universe_path = tmp_path / "universe.json"
    write_json(universe_path, safe_universe([candidate()]))

    report = module.build_probability_breadth_scout(
        universe_scan_path=universe_path,
        max_close_hours=6,
        generated_utc="2026-07-02T00:00:00Z",
    )

    assert isinstance(report["summary"]["sports_fast_candidate_count"], int)
    assert report["summary"]["sports_fast_candidate_count"] == 0


def test_scout_empty_sports_does_not_fabricate_sports_route(tmp_path: Path) -> None:
    """VAL-ORCH-031: no KX*GAME series -> sports count 0, no sports route."""
    module = load_scout_module()
    universe_path = tmp_path / "universe.json"
    write_json(
        universe_path,
        safe_universe(
            [
                candidate(),
                candidate(
                    ticker="KXHIGHNY-26JUL01-T90", classification="weather", time_to_close_hours=4.0
                ),
            ]
        ),
    )

    report = module.build_probability_breadth_scout(
        universe_scan_path=universe_path,
        max_close_hours=6,
        generated_utc="2026-07-02T00:00Z",
    )

    assert report["summary"]["sports_fast_candidate_count"] == 0
    assert "sports" not in report["summary"]["selected_route"]
    assert all(
        "sports" not in (r.get("source_route") or "") for r in report["work_order_candidates"]
    )


def test_scout_sports_classification_predicate_is_deterministic() -> None:
    """VAL-ORCH-034: sports predicate correctly classifies series tickers."""
    module = load_scout_module()

    for prefix in ("KXMLBGAME", "KXKBOGAME", "KXLMBGAME"):
        assert module.is_sports_baseball_candidate({"series_ticker": f"{prefix}-SOME-SUFFIX"})
        assert module.is_sports_baseball_candidate({"series_ticker": prefix})
    assert not module.is_sports_baseball_candidate({"series_ticker": "KXBTC15M"})
    assert not module.is_sports_baseball_candidate({"series_ticker": "KXHIGHNY"})
    assert not module.is_sports_baseball_candidate({"series_ticker": "KXMLBRUN"})
    assert not module.is_sports_baseball_candidate({"series_ticker": "KXMLBPLAYER"})
    assert module.is_sports_baseball_candidate(
        {"series_ticker": "KXMLBGAME"}
    ) == module.is_sports_baseball_candidate({"series_ticker": "KXMLBGAME"})


def test_scout_sports_route_carries_research_only_safety(tmp_path: Path) -> None:
    """VAL-ORCH-027/028: sports route is research-only, usable=false, calibrated_probability=null."""
    module = load_scout_module()
    universe_path = tmp_path / "universe.json"
    write_json(universe_path, safe_universe([sports_candidate()]))

    report = module.build_probability_breadth_scout(
        universe_scan_path=universe_path,
        max_close_hours=6,
        generated_utc="2026-07-02T00:00:00Z",
    )

    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["safety"]["market_execution"] is False
    assert report["safety"]["account_or_order_paths"] is False
    assert "label" in report["source_plan"]["proxy_policy"].lower()
    for row in report["work_order_candidates"]:
        if "sports" in (row.get("source_route") or ""):
            assert row["usable"] is False
            assert row["calibrated_probability"] is None


def test_scout_crypto_routing_preserved_when_sports_absent(tmp_path: Path) -> None:
    """VAL-ORCH-024: crypto-only -> crypto route (unchanged)."""
    module = load_scout_module()
    universe_path = tmp_path / "universe.json"
    write_json(universe_path, safe_universe([candidate()]))

    report = module.build_probability_breadth_scout(
        universe_scan_path=universe_path,
        max_close_hours=6,
        generated_utc="2026-07-02T00:00:00Z",
    )

    assert report["summary"]["selected_route"] == "crypto_proxy_fast_label_route"
