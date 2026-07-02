from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kalshi_probability_breadth_scout.py"
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


def test_probability_breadth_scout_selects_crypto_fast_route_and_keeps_proxy_caveat(tmp_path: Path) -> None:
    module = load_scout_module()
    universe_path = tmp_path / "universe.json"
    write_json(
        universe_path,
        safe_universe(
            [
                candidate(),
                candidate(ticker="KXHIGHNY-26JUL01-T90", classification="weather", time_to_close_hours=4.0),
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
    assert report["source_plan"]["official_settlement_source"] == "CF Benchmarks Real-Time Indices (RTIs)"
    assert report["source_plan"]["official_source_availability"] == "authenticated_or_licensed_required"
    assert "model features only" in report["source_plan"]["proxy_policy"]
    assert report["proxy_probe"]["raw_snapshot_outside_repo"] is True
    assert all(row["usable"] is False for row in report["work_order_candidates"])
    assert all(row["calibrated_probability"] is None for row in report["work_order_candidates"])
    assert "proxy prices as official labels" in report["next_action"]["stop_condition"]


def test_probability_breadth_scout_excludes_non_crypto_finance_rows_from_crypto_route(tmp_path: Path) -> None:
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
