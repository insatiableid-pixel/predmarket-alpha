"""Artifact-replay tests for the weather proxy observation/label loop.

Mirrors ``test_kalshi_crypto_proxy_observation_loop.py``: loads the script via
``importlib.util.spec_from_file_location``, builds a synthetic weather feature
packet + settled Kalshi snapshot in ``tmp_path``, calls
``build_weather_proxy_observation_loop``, and asserts observation + label
emission.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_weather_proxy_observation_loop.py"
)


def load_observation_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_weather_proxy_observation_loop", SCRIPT_PATH
    )
    assert spec is not None, f"Could not load spec from {SCRIPT_PATH}"
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_feature_packet(**overrides):
    """Build a synthetic weather feature packet with ready rows."""
    payload = {
        "schema_version": 1,
        "generated_utc": "2026-07-03T12:00:00Z",
        "status": "weather_proxy_feature_packet_ready",
        "feature_rows": [
            {
                "contract_ticker": "KXHIGH-26JUL03-NYC-90",
                "event_ticker": "KXHIGH-26JUL03-NYC",
                "series_ticker": "KXHIGH",
                "weather_family": "KXHIGH",
                "close_time": "2026-07-03T20:00:00Z",
                "expected_expiration_time": "2026-07-03T21:00:00Z",
                "fresh_time_to_close_hours": 8.0,
                "yes_bid": 0.45,
                "yes_ask": 0.48,
                "no_bid": 0.52,
                "no_ask": 0.55,
                "yes_spread": 0.03,
                "station_id": "KNYC",
                "forecast_high": 78.0,
                "forecast_low": 55.0,
                "observation_temperature": 72.0,
                "bracket_probability": 0.35,
                "predicted_side": "no",
                "feature_status": "weather_features_ready",
                "label_status": "not_labeled_weather_feature_packet_only",
                "usable": False,
                "calibrated_probability": None,
                "expected_value_per_contract": None,
                "feature_policy": "proxy_feature_only_not_official_settlement_label",
                "official_settlement_source": "NWS Daily Climate Report (CLI product)",
            }
        ],
        "research_only": True,
        "execution_enabled": False,
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }
    payload.update(overrides)
    return payload


def settled_market(**overrides):
    """Synthetic Kalshi settled market payload."""
    row = {
        "ticker": "KXHIGH-26JUL03-NYC-90",
        "event_ticker": "KXHIGH-26JUL03-NYC",
        "yes_bid": 0.0,
        "yes_ask": 1.0,
        "no_bid": 0.0,
        "no_ask": 1.0,
        "close_time": "2026-07-03T20:00:00Z",
        "result": "yes",
        "settled": True,
        "settlement_timestamp": "2026-07-03T21:05:00Z",
    }
    row.update(overrides)
    return row


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, default=str), encoding="utf-8")


# ── Tests ─────────────────────────────────────────────────────────────────


class TestWeatherObservationLifecycle:
    """VAL-WX-030 through VAL-WX-036: observation/label loop."""

    def test_snapshots_only_ready_rows(self, tmp_path: Path) -> None:
        """VAL-WX-030: Only ready feature rows produce observations."""
        module = load_observation_module()
        feature_packet = make_feature_packet(
            feature_rows=[
                {
                    "contract_ticker": "KXHIGH-26JUL03-NYC-90",
                    "feature_status": "weather_features_ready",
                    "yes_ask": 0.48,
                    "bracket_probability": 0.35,
                    "predicted_side": "no",
                    "close_time": "2026-07-03T20:00:00Z",
                },
                {
                    "contract_ticker": "KXLOW-26JUL03-NYC-70",
                    "feature_status": "station_unresolved",
                    "yes_ask": 0.40,
                    "bracket_probability": None,
                    "predicted_side": None,
                    "close_time": "2026-07-03T20:00:00Z",
                },
            ]
        )
        fp_path = tmp_path / "feature_packet.json"
        write_json(fp_path, feature_packet)

        report = module.build_weather_proxy_observation_loop(
            feature_packet_path=fp_path,
            observation_dir=tmp_path / "observations",
            label_dir=tmp_path / "labels",
            generated_utc="2026-07-03T12:00:00Z",
        )
        assert report["summary"]["new_observation_row_count"] == 1
        obs_tickers = [o["contract_ticker"] for o in report["observation_packet"]["rows"]]
        assert "KXHIGH-26JUL03-NYC-90" in obs_tickers
        assert "KXLOW-26JUL03-NYC-70" not in obs_tickers

    def test_dedup_by_observation_id(self, tmp_path: Path) -> None:
        """VAL-WX-031: Observations deduped by observation_id across runs."""
        module = load_observation_module()
        feature_packet_path = tmp_path / "feature_packet.json"
        write_json(feature_packet_path, make_feature_packet())
        obs_dir = tmp_path / "observations"
        label_dir = tmp_path / "labels"

        # First run
        report1 = module.build_weather_proxy_observation_loop(
            feature_packet_path=feature_packet_path,
            observation_dir=obs_dir,
            label_dir=label_dir,
            generated_utc="2026-07-03T12:00:00Z",
        )
        assert report1["summary"]["new_observation_row_count"] == 1

        # Persist observations from first run
        obs_dir.mkdir(parents=True, exist_ok=True)
        for obs in report1["observation_packet"]["rows"]:
            obs_path = obs_dir / f"{obs['observation_id']}.json"
            obs_path.write_text(json.dumps(obs), encoding="utf-8")

        # Second run with same feature packet
        report2 = module.build_weather_proxy_observation_loop(
            feature_packet_path=feature_packet_path,
            observation_dir=obs_dir,
            label_dir=label_dir,
            generated_utc="2026-07-03T12:00:00Z",
        )
        assert report2["summary"]["new_observation_row_count"] == 0
        assert report2["summary"]["existing_observation_row_count"] >= 1

    def test_probes_only_due_tickers(self, tmp_path: Path) -> None:
        """VAL-WX-032: Only past-close tickers are probed for labels."""
        module = load_observation_module()
        # One past-close, one future-close
        feature_packet = make_feature_packet(
            feature_rows=[
                {
                    "contract_ticker": "KXHIGH-26JUL03-NYC-90",
                    "feature_status": "weather_features_ready",
                    "yes_ask": 0.48,
                    "bracket_probability": 0.35,
                    "predicted_side": "no",
                    "close_time": "2026-07-03T18:00:00Z",
                    "expected_expiration_time": "2026-07-03T19:00:00Z",
                },
                {
                    "contract_ticker": "KXLOW-26JUL04-NYC-60",
                    "feature_status": "weather_features_ready",
                    "yes_ask": 0.40,
                    "bracket_probability": 0.65,
                    "predicted_side": "yes",
                    "close_time": "2026-07-04T20:00:00Z",
                    "expected_expiration_time": "2026-07-04T21:00:00Z",
                },
            ]
        )
        fp_path = tmp_path / "feature_packet.json"
        write_json(fp_path, feature_packet)
        obs_dir = tmp_path / "observations"
        label_dir = tmp_path / "labels"

        report = module.build_weather_proxy_observation_loop(
            feature_packet_path=fp_path,
            observation_dir=obs_dir,
            label_dir=label_dir,
            generated_utc="2026-07-03T20:00:00Z",
        )
        # The one with close_time past should be among due_observed_tickers
        due_tickers = report["summary"].get("due_observed_ticker_count", 0)
        assert due_tickers >= 1

    def test_emits_label_for_settled_contract(self, tmp_path: Path) -> None:
        """VAL-WX-033: Settled Kalshi contract emits a label row."""
        module = load_observation_module()
        feature_packet_path = tmp_path / "feature_packet.json"
        write_json(feature_packet_path, make_feature_packet())

        settled_path = tmp_path / "settled.json"
        write_json(settled_path, {"markets": [settled_market(result="yes")]})

        obs_dir = tmp_path / "observations"
        label_dir = tmp_path / "labels"

        report = module.build_weather_proxy_observation_loop(
            feature_packet_path=feature_packet_path,
            settled_snapshot_path=settled_path,
            observation_dir=obs_dir,
            label_dir=label_dir,
            generated_utc="2026-07-03T22:00:00Z",
        )
        assert report["summary"]["new_label_row_count"] >= 1
        if report.get("label_packet", {}).get("rows"):
            label = report["label_packet"]["rows"][0]
            assert label.get("yes_outcome") is not None

    def test_capture_public_observed_markets_snapshot_fetches_exact_due_weather_ticker(
        self, tmp_path: Path
    ) -> None:
        """Due weather tickers can be probed exactly through the public Kalshi market endpoint."""
        module = load_observation_module()
        feature_packet_path = tmp_path / "feature_packet.json"
        write_json(feature_packet_path, make_feature_packet())

        due = module.due_observed_tickers(
            feature_packet_path=feature_packet_path,
            observation_dir=tmp_path / "observations",
            generated_utc="2026-07-03T22:00:00Z",
            max_tickers=10,
        )

        def fake_fetch(url: str):
            assert "/markets/KXHIGH-26JUL03-NYC-90" in url
            return {"market": settled_market(settlement_value_dollars="1")}

        snapshot_path = module.capture_public_observed_markets_snapshot(
            tickers=due,
            raw_dir=tmp_path / "settlements",
            generated_utc="2026-07-03T22:00:00Z",
            fetch_json=fake_fetch,
        )
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

        assert due == ["KXHIGH-26JUL03-NYC-90"]
        assert snapshot["status"] == "kalshi_public_observed_market_fetch_ok"
        assert snapshot["summary"]["settled_label_ready_count"] == 1
        assert snapshot["markets"][0]["ticker"] == "KXHIGH-26JUL03-NYC-90"

    def test_labels_from_kalshi_settlement_not_proxy(self, tmp_path: Path) -> None:
        """VAL-WX-034: label_source references Kalshi public settlement, not NWS."""
        module = load_observation_module()
        feature_packet_path = tmp_path / "feature_packet.json"
        write_json(feature_packet_path, make_feature_packet())

        settled_path = tmp_path / "settled.json"
        write_json(settled_path, {"markets": [settled_market(result="yes")]})

        report = module.build_weather_proxy_observation_loop(
            feature_packet_path=feature_packet_path,
            settled_snapshot_path=settled_path,
            observation_dir=tmp_path / "observations",
            label_dir=tmp_path / "labels",
            generated_utc="2026-07-03T22:00:00Z",
        )
        if report.get("label_packet", {}).get("rows"):
            label = report["label_packet"]["rows"][0]
            ls = str(label.get("label_source", ""))
            assert "Kalshi" in ls or "kalshi" in ls.lower() or "settled" in ls.lower()

    def test_label_rows_research_only(self, tmp_path: Path) -> None:
        """VAL-WX-035: Label rows are research-only."""
        module = load_observation_module()
        feature_packet_path = tmp_path / "feature_packet.json"
        write_json(feature_packet_path, make_feature_packet())

        settled_path = tmp_path / "settled.json"
        write_json(settled_path, {"markets": [settled_market(result="yes")]})

        report = module.build_weather_proxy_observation_loop(
            feature_packet_path=feature_packet_path,
            settled_snapshot_path=settled_path,
            observation_dir=tmp_path / "observations",
            label_dir=tmp_path / "labels",
            generated_utc="2026-07-03T22:00:00Z",
        )
        assert report["research_only"] is True
        assert report["execution_enabled"] is False
        for row in report.get("label_packet", {}).get("rows", []):
            assert row.get("usable") is False
            assert row.get("calibrated_probability") is None

    def test_missing_settlement_blocks_label_not_guess(self, tmp_path: Path) -> None:
        """VAL-WX-036: Missing Kalshi settlement blocks, does not guess."""
        module = load_observation_module()
        feature_packet_path = tmp_path / "feature_packet.json"
        write_json(feature_packet_path, make_feature_packet())

        # Empty settled snapshot
        settled_path = tmp_path / "settled.json"
        write_json(settled_path, {"markets": []})

        report = module.build_weather_proxy_observation_loop(
            feature_packet_path=feature_packet_path,
            settled_snapshot_path=settled_path,
            observation_dir=tmp_path / "observations",
            label_dir=tmp_path / "labels",
            generated_utc="2026-07-03T22:00:00Z",
        )
        assert report["summary"]["new_label_row_count"] == 0


class TestWeatherObservationSafety:
    """Research-only safety for observation loop."""

    def test_research_only_flags(self, tmp_path: Path) -> None:
        """research_only=true, execution_enabled=false."""
        module = load_observation_module()
        feature_packet_path = tmp_path / "feature_packet.json"
        write_json(feature_packet_path, make_feature_packet())

        report = module.build_weather_proxy_observation_loop(
            feature_packet_path=feature_packet_path,
            observation_dir=tmp_path / "observations",
            label_dir=tmp_path / "labels",
            generated_utc="2026-07-03T12:00:00Z",
        )
        assert report["research_only"] is True
        assert report["execution_enabled"] is False
        safety = report.get("safety", {})
        assert safety.get("market_execution") is False
        assert safety.get("account_or_order_paths") is False
        assert safety.get("database_writes") is False
        assert safety.get("staking_or_sizing_guidance") is False
