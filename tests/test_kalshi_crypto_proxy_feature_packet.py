from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kalshi_crypto_proxy_feature_packet.py"
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_packet_module():
    spec = importlib.util.spec_from_file_location("kalshi_crypto_proxy_feature_packet", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def safe_artifact(**overrides):
    payload = {
        "schema_version": 1,
        "research_only": True,
        "execution_enabled": False,
        "status": "ready",
        "summary": {},
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }
    payload.update(overrides)
    return payload


def candidate(**overrides):
    row = {
        "ticker": "KXBTC15M-26JUL012015-15",
        "event_ticker": "KXBTC15M-26JUL012015",
        "series_ticker": "KXBTC15M",
        "classification": "finance_crypto",
        "title": "BTC price up in next 15 mins?",
        "close_time": "2026-07-02T00:15:00Z",
        "expected_expiration_time": "2026-07-02T00:20:00Z",
        "yes_bid": 0.21,
        "yes_ask": 0.22,
        "no_bid": 0.78,
        "no_ask": 0.79,
        "yes_spread": 0.01,
        "softness_score": 0.58,
        "official_rules_hash": "abc",
        "official_rules_source": "public_kalshi_market_payload",
    }
    row.update(overrides)
    return row


def raw_market(**overrides):
    row = {
        "ticker": "KXBTC15M-26JUL012015-15",
        "event_ticker": "KXBTC15M-26JUL012015",
        "series_ticker": "KXBTC15M",
        "title": "BTC price up in next 15 mins?",
        "tags": ["BTC", "15 min"],
        "series_title": "Bitcoin price up down",
        "strike_type": "greater_or_equal",
        "floor_strike": 59968.41,
        "cap_strike": None,
        "open_time": "2026-07-02T00:00:00Z",
        "close_time": "2026-07-02T00:15:00Z",
        "expected_expiration_time": "2026-07-02T00:20:00Z",
        "rules_primary": "If the simple average of CF Benchmarks BRTI is up, resolves Yes.",
        "settlement_sources": [{"name": "CF Benchmarks", "url": "https://www.cfbenchmarks.com/"}],
    }
    row.update(overrides)
    return row


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def fake_fetch(url: str):
    if url.endswith("/ticker"):
        return {"price": "60000.00", "time": "2026-07-02T00:05:00Z"}
    candles = []
    base_ts = 1782950000
    for idx in range(70):
        close = 59900 + idx
        candles.append([base_ts + idx * 60, close - 2, close + 2, close - 1, close, 10 + idx])
    return list(reversed(candles))


def test_crypto_proxy_feature_packet_builds_contract_keyed_rows_without_ev_or_labels(tmp_path: Path) -> None:
    module = load_packet_module()
    universe_path = tmp_path / "universe.json"
    breadth_path = tmp_path / "breadth.json"
    raw_path = tmp_path / "raw_universe.json"
    write_json(
        universe_path,
        safe_artifact(
            status="universe_scan_ready_with_model_routes",
            candidates=[candidate()],
        ),
    )
    write_json(
        breadth_path,
        safe_artifact(status="probability_breadth_scout_ready_crypto_proxy_feature_route"),
    )
    write_json(raw_path, {"markets": [raw_market()]})

    report = module.build_crypto_proxy_feature_packet(
        universe_scan_path=universe_path,
        probability_breadth_scout_path=breadth_path,
        raw_universe_path=raw_path,
        raw_proxy_dir=Path("/tmp") / f"kalshi_crypto_proxy_features_{tmp_path.name}",
        max_close_hours=6,
        generated_utc="2026-07-02T00:05:00Z",
        capture_public_proxy=True,
        fetch_json=fake_fetch,
    )

    assert report["status"] == "crypto_proxy_feature_packet_ready"
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["safety"]["market_execution"] is False
    assert report["proxy_capture"]["raw_snapshot_outside_repo"] is True
    assert report["summary"]["feature_row_count"] == 1
    assert report["summary"]["feature_ready_count"] == 1
    row = report["feature_rows"][0]
    assert row["contract_ticker"] == "KXBTC15M-26JUL012015-15"
    assert row["asset_symbol"] == "BTC"
    assert row["contract_family"] == "fifteen_minute_up_down"
    assert row["official_settlement_source"] == "CF Benchmarks RTI"
    assert row["proxy_source"] == "coinbase_exchange_public"
    assert row["proxy_product_id"] == "BTC-USD"
    assert row["proxy_price"] == 60000.0
    assert row["proxy_distance_to_floor"] == 31.59
    assert row["proxy_state"] == "proxy_above_floor_not_label"
    assert row["feature_policy"] == "proxy_feature_only_not_official_settlement_label"
    assert row["label_status"] == "not_labeled_proxy_feature_packet_only"
    assert row["calibrated_probability"] is None
    assert row["expected_value_per_contract"] is None
    assert row["usable"] is False


def test_crypto_proxy_feature_packet_skips_closed_contracts(tmp_path: Path) -> None:
    module = load_packet_module()
    universe_path = tmp_path / "universe.json"
    breadth_path = tmp_path / "breadth.json"
    raw_path = tmp_path / "raw_universe.json"
    write_json(universe_path, safe_artifact(candidates=[candidate()]))
    write_json(breadth_path, safe_artifact(status="probability_breadth_scout_ready_crypto_proxy_feature_route"))
    write_json(raw_path, {"markets": [raw_market()]})

    report = module.build_crypto_proxy_feature_packet(
        universe_scan_path=universe_path,
        probability_breadth_scout_path=breadth_path,
        raw_universe_path=raw_path,
        generated_utc="2026-07-02T00:16:00Z",
        capture_public_proxy=False,
    )

    assert report["status"] == "crypto_proxy_feature_packet_blocked_no_open_fast_crypto_contracts"
    assert report["summary"]["feature_row_count"] == 0


def test_crypto_proxy_feature_packet_skips_finance_rows_without_configured_crypto_asset(tmp_path: Path) -> None:
    module = load_packet_module()
    universe_path = tmp_path / "universe.json"
    breadth_path = tmp_path / "breadth.json"
    raw_path = tmp_path / "raw_universe.json"
    gas_candidate = candidate(
        ticker="KXAAAGASD-26JUL02-3.805",
        event_ticker="KXAAAGASD-26JUL02",
        series_ticker="KXAAAGASD",
        title="Will average gas prices be above $3.805?",
        close_time="2026-07-02T00:25:00Z",
        expected_expiration_time="2026-07-02T00:30:00Z",
    )
    gas_raw = raw_market(
        ticker="KXAAAGASD-26JUL02-3.805",
        event_ticker="KXAAAGASD-26JUL02",
        series_ticker="KXAAAGASD",
        title="Will average gas prices be above $3.805?",
        tags=["Oil & Gas", "Econ Daily"],
        series_title="US gas price up",
        floor_strike=3.805,
        close_time="2026-07-02T00:25:00Z",
        expected_expiration_time="2026-07-02T00:30:00Z",
    )
    write_json(universe_path, safe_artifact(candidates=[candidate(), gas_candidate]))
    write_json(breadth_path, safe_artifact(status="probability_breadth_scout_ready_crypto_proxy_feature_route"))
    write_json(raw_path, {"markets": [raw_market(), gas_raw]})

    report = module.build_crypto_proxy_feature_packet(
        universe_scan_path=universe_path,
        probability_breadth_scout_path=breadth_path,
        raw_universe_path=raw_path,
        raw_proxy_dir=Path("/tmp") / f"kalshi_crypto_proxy_features_filter_{tmp_path.name}",
        generated_utc="2026-07-02T00:05:00Z",
        capture_public_proxy=True,
        fetch_json=fake_fetch,
    )

    assert report["status"] == "crypto_proxy_feature_packet_ready"
    assert report["summary"]["feature_row_count"] == 1
    assert report["feature_rows"][0]["contract_ticker"] == "KXBTC15M-26JUL012015-15"


def test_crypto_proxy_feature_packet_writes_latest_artifacts(tmp_path: Path) -> None:
    module = load_packet_module()
    module.MACRO_DIR = tmp_path / "macro"
    universe_path = tmp_path / "universe.json"
    breadth_path = tmp_path / "breadth.json"
    raw_path = tmp_path / "raw_universe.json"
    write_json(universe_path, safe_artifact(candidates=[candidate()]))
    write_json(breadth_path, safe_artifact(status="probability_breadth_scout_ready_crypto_proxy_feature_route"))
    write_json(raw_path, {"markets": [raw_market()]})
    report = module.build_crypto_proxy_feature_packet(
        universe_scan_path=universe_path,
        probability_breadth_scout_path=breadth_path,
        raw_universe_path=raw_path,
        raw_proxy_dir=Path("/tmp") / f"kalshi_crypto_proxy_features_write_{tmp_path.name}",
        generated_utc="2026-07-02T00:05:00Z",
        capture_public_proxy=True,
        fetch_json=fake_fetch,
    )

    paths = module.write_crypto_proxy_feature_packet(report, out_dir=tmp_path / "out")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    assert (tmp_path / "macro" / "latest-kalshi-crypto-proxy-feature-packet.json").exists()


def test_makefile_exposes_crypto_proxy_feature_packet_target() -> None:
    content = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-crypto-proxy-feature-packet" in content
    assert "scripts/kalshi_crypto_proxy_feature_packet.py" in content
