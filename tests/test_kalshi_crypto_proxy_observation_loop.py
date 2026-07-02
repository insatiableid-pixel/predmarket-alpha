from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kalshi_crypto_proxy_observation_loop.py"
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_loop_module():
    spec = importlib.util.spec_from_file_location("kalshi_crypto_proxy_observation_loop", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def safe_feature_packet(**overrides):
    payload = {
        "schema_version": 1,
        "generated_utc": "2026-07-02T00:05:00Z",
        "status": "crypto_proxy_feature_packet_ready",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "summary": {"feature_row_count": 1, "feature_ready_count": 1},
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
        "feature_rows": [feature_row()],
    }
    payload.update(overrides)
    return payload


def feature_row(**overrides):
    row = {
        "contract_ticker": "KXBTC15M-26JUL012015-15",
        "event_ticker": "KXBTC15M-26JUL012015",
        "series_ticker": "KXBTC15M",
        "side": "yes",
        "asset_symbol": "BTC",
        "contract_family": "fifteen_minute_up_down",
        "contract_side": "above_floor",
        "close_time": "2026-07-02T00:15:00Z",
        "expected_expiration_time": "2026-07-02T00:20:00Z",
        "yes_bid": 0.21,
        "yes_ask": 0.22,
        "yes_spread": 0.01,
        "proxy_source": "coinbase_exchange_public",
        "proxy_product_id": "BTC-USD",
        "proxy_price": 60000.0,
        "proxy_observed_at_utc": "2026-07-02T00:05:00Z",
        "proxy_return_5m": 0.001,
        "proxy_return_15m": 0.002,
        "proxy_return_60m": -0.003,
        "proxy_realized_vol_15m": 0.12,
        "proxy_realized_vol_60m": 0.19,
        "proxy_distance_to_floor": 31.59,
        "proxy_distance_to_cap": None,
        "proxy_state": "proxy_above_floor_not_label",
        "feature_status": "proxy_features_ready",
        "calibrated_probability": None,
        "expected_value_per_contract": None,
        "usable": False,
    }
    row.update(overrides)
    return row


def settled_snapshot(**overrides):
    payload = {
        "schema_version": 1,
        "created_at_utc": "2026-07-02T00:30:00Z",
        "status": "kalshi_public_settled_fetch_ok",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
        "markets": [
            {
                "ticker": "KXBTC15M-26JUL012015-15",
                "event_ticker": "KXBTC15M-26JUL012015",
                "series_ticker": "KXBTC15M",
                "result": "yes",
                "settlement_value_dollars": "1.0000",
                "close_time": "2026-07-02T00:15:00Z",
                "settlement_ts": "2026-07-02T00:20:00Z",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_crypto_proxy_observation_loop_records_feature_rows_without_ev_or_probability_claims(
    tmp_path: Path,
) -> None:
    module = load_loop_module()
    feature_path = tmp_path / "feature.json"
    settled_path = tmp_path / "missing-settled.json"
    write_json(feature_path, safe_feature_packet())

    report = module.build_crypto_proxy_observation_loop(
        feature_packet_path=feature_path,
        settled_snapshot_path=settled_path,
        observation_dir=tmp_path / "observations",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-02T00:06:00Z",
    )

    assert report["status"] == "crypto_proxy_observation_loop_ready_waiting_settlement"
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["summary"]["new_observation_row_count"] == 1
    assert report["summary"]["label_row_count"] == 0
    assert report["summary"]["next_expected_expiration_utc"] == "2026-07-02T00:20:00Z"
    assert report["summary"]["due_observation_row_count"] == 0
    row = report["observation_packet"]["rows"][0]
    assert row["contract_ticker"] == "KXBTC15M-26JUL012015-15"
    assert row["label_status"] == "pending_settled_kalshi_outcome"
    assert row["calibrated_probability"] is None
    assert row["expected_value_per_contract"] is None
    assert row["usable"] is False
    assert report["safety"]["market_execution"] is False


def test_crypto_proxy_observation_loop_labels_exact_ticker_from_public_settlement(
    tmp_path: Path,
) -> None:
    module = load_loop_module()
    feature_path = tmp_path / "feature.json"
    settled_path = tmp_path / "settled.json"
    write_json(feature_path, safe_feature_packet())
    write_json(settled_path, settled_snapshot())

    report = module.build_crypto_proxy_observation_loop(
        feature_packet_path=feature_path,
        settled_snapshot_path=settled_path,
        observation_dir=tmp_path / "observations",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-02T00:30:00Z",
    )

    assert report["status"] == "crypto_proxy_observation_loop_label_rows_ready"
    assert report["summary"]["label_row_count"] == 1
    assert report["summary"]["due_observation_row_count"] == 1
    assert report["summary"]["due_distinct_contract_count"] == 1
    assert report["summary"]["next_public_label_probe_utc"] == "2026-07-02T00:30:00Z"
    assert report["summary"]["blocked_label_row_count"] == 0
    label = report["label_packet"]["rows"][0]
    assert label["label_status"] == "labeled_from_public_kalshi_settled_market"
    assert label["yes_outcome"] == 1
    assert label["label_source"] == "public_kalshi_settled_market_payload"
    assert label["calibrated_probability"] is None
    assert label["expected_value_per_contract"] is None
    assert label["usable"] is False


def test_crypto_proxy_observation_loop_does_not_reemit_existing_observations_or_labels(
    tmp_path: Path,
) -> None:
    module = load_loop_module()
    feature_path = tmp_path / "feature.json"
    settled_path = tmp_path / "settled.json"
    observation_dir = tmp_path / "observations"
    label_dir = tmp_path / "labels"
    write_json(feature_path, safe_feature_packet())
    write_json(settled_path, settled_snapshot())
    first = module.build_crypto_proxy_observation_loop(
        feature_packet_path=feature_path,
        settled_snapshot_path=settled_path,
        observation_dir=observation_dir,
        label_dir=label_dir,
        generated_utc="2026-07-02T00:30:00Z",
    )
    write_json(observation_dir / "observations.json", first["observation_packet"])
    write_json(label_dir / "labels.json", first["label_packet"])

    second = module.build_crypto_proxy_observation_loop(
        feature_packet_path=feature_path,
        settled_snapshot_path=settled_path,
        observation_dir=observation_dir,
        label_dir=label_dir,
        generated_utc="2026-07-02T00:31:00Z",
    )

    assert second["summary"]["existing_observation_row_count"] == 1
    assert second["summary"]["new_observation_row_count"] == 0
    assert second["summary"]["existing_label_row_count"] == 1
    assert second["summary"]["new_label_row_count"] == 0
    assert second["summary"]["label_row_count"] == 1
    assert second["observation_packet"]["rows"] == []
    assert second["label_packet"]["rows"] == []


def test_crypto_proxy_observation_loop_blocks_missing_or_unsafe_feature_packet(
    tmp_path: Path,
) -> None:
    module = load_loop_module()
    feature_path = tmp_path / "unsafe-feature.json"
    write_json(feature_path, safe_feature_packet(execution_enabled=True))

    report = module.build_crypto_proxy_observation_loop(
        feature_packet_path=feature_path,
        settled_snapshot_path=tmp_path / "settled.json",
        observation_dir=tmp_path / "observations",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-02T00:06:00Z",
    )

    assert report["status"] == "crypto_proxy_observation_loop_blocked_missing_feature_packet"
    assert report["summary"]["feature_packet_safe"] is False
    gates = {item["name"]: item for item in report["gates"]}
    assert gates["crypto_proxy_feature_packet_safe"]["status"] == "blocked"


def test_crypto_proxy_observation_loop_writes_latest_repo_artifacts_and_outside_packets(
    tmp_path: Path,
) -> None:
    module = load_loop_module()
    module.MACRO_DIR = tmp_path / "macro"
    feature_path = tmp_path / "feature.json"
    settled_path = tmp_path / "settled.json"
    observation_dir = tmp_path / "manual" / "observations"
    label_dir = tmp_path / "manual" / "labels"
    write_json(feature_path, safe_feature_packet())
    write_json(settled_path, settled_snapshot())
    report = module.build_crypto_proxy_observation_loop(
        feature_packet_path=feature_path,
        settled_snapshot_path=settled_path,
        observation_dir=observation_dir,
        label_dir=label_dir,
        generated_utc="2026-07-02T00:30:00Z",
    )

    paths = module.write_crypto_proxy_observation_outputs(
        report,
        out_dir=tmp_path / "out",
        observation_dir=observation_dir,
        label_dir=label_dir,
    )

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    assert Path(paths["schedule_template_path"]).exists()
    assert Path(paths["latest_json_path"]).exists()
    assert Path(paths["observation_packet_latest_path"]).exists()
    assert Path(paths["label_packet_latest_path"]).exists()
    latest = json.loads(Path(paths["latest_json_path"]).read_text(encoding="utf-8"))
    assert latest["summary"]["label_row_count"] == 1
    assert "Kalshi Crypto Proxy Observation Loop" in Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert "OnUnitActiveSec=10min" in Path(paths["schedule_template_path"]).read_text(encoding="utf-8")


def test_due_observed_tickers_only_includes_past_expected_expiration(tmp_path: Path) -> None:
    module = load_loop_module()
    feature_path = tmp_path / "feature.json"
    write_json(
        feature_path,
        safe_feature_packet(
            feature_rows=[
                feature_row(
                    contract_ticker="KXBTC15M-26JUL012015-15",
                    expected_expiration_time="2026-07-02T00:20:00Z",
                ),
                feature_row(
                    contract_ticker="KXETH15M-26JUL012145-15",
                    event_ticker="KXETH15M-26JUL012145",
                    series_ticker="KXETH15M",
                    asset_symbol="ETH",
                    expected_expiration_time="2026-07-02T01:45:00Z",
                ),
            ],
        ),
    )

    tickers = module.due_observed_tickers(
        feature_packet_path=feature_path,
        observation_dir=tmp_path / "observations",
        generated_utc="2026-07-02T00:30:00Z",
        max_tickers=10,
    )

    assert tickers == ["KXBTC15M-26JUL012015-15"]


def test_observation_due_summary_reports_next_probe_time() -> None:
    module = load_loop_module()

    summary = module.observation_due_summary(
        [
            feature_row(
                contract_ticker="KXBTC15M-26JUL012015-15",
                expected_expiration_time="2026-07-02T00:20:00Z",
            ),
            feature_row(
                contract_ticker="KXETH15M-26JUL012145-15",
                expected_expiration_time="2026-07-02T01:45:00Z",
            ),
        ],
        generated_utc="2026-07-02T00:30:00Z",
    )

    assert summary["due_observation_row_count"] == 1
    assert summary["due_distinct_contract_count"] == 1
    assert summary["not_due_distinct_contract_count"] == 1
    assert summary["oldest_due_expected_expiration_utc"] == "2026-07-02T00:20:00Z"
    assert summary["next_expected_expiration_utc"] == "2026-07-02T01:45:00Z"
    assert summary["next_public_label_probe_utc"] == "2026-07-02T00:30:00Z"


def test_capture_public_observed_markets_snapshot_fetches_exact_tickers(tmp_path: Path) -> None:
    module = load_loop_module()
    calls: list[str] = []

    def fake_fetch(url: str):
        calls.append(url)
        return {
            "market": {
                "ticker": "KXBTC15M-26JUL012015-15",
                "result": "no",
                "settlement_value_dollars": "0.0000",
                "close_time": "2026-07-02T00:15:00Z",
                "settlement_ts": "2026-07-02T00:20:00Z",
            }
        }

    latest_path = module.capture_public_observed_markets_snapshot(
        tickers=["KXBTC15M-26JUL012015-15"],
        raw_dir=tmp_path / "settled",
        generated_utc="2026-07-02T00:30:00Z",
        fetch_json=fake_fetch,
    )
    payload = json.loads(latest_path.read_text(encoding="utf-8"))

    assert payload["status"] == "kalshi_public_observed_market_fetch_ok"
    assert payload["summary"]["observed_ticker_count"] == 1
    assert payload["summary"]["settled_label_ready_count"] == 1
    assert payload["markets"][0]["ticker"] == "KXBTC15M-26JUL012015-15"
    assert calls == ["https://external-api.kalshi.com/trade-api/v2/markets/KXBTC15M-26JUL012015-15"]


def test_crypto_proxy_observation_makefile_targets_are_registered() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-crypto-proxy-observation-loop" in text
    assert "kalshi-crypto-proxy-observation-watch-once" in text
    assert "KALSHI_CRYPTO_PROXY_OBSERVATION_CAPTURE_SETTLED" in text
    assert "KALSHI_CRYPTO_PROXY_OBSERVATION_PROBE_OBSERVED" in text
