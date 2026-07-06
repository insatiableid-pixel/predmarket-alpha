"""Artifact-replay tests for the weather proxy feature-packet builder.

Mirrors ``test_kalshi_crypto_proxy_feature_packet.py``: loads the script via
``importlib.util.spec_from_file_location``, builds synthetic Kalshi universe +
api.weather.gov fixtures in ``tmp_path``, injects a fake ``fetch_json``, calls
``build_weather_proxy_feature_packet``, and asserts report structure, status,
research-only safety, and per-row invariants.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_weather_proxy_feature_packet.py"
)


def load_weather_packet_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_weather_proxy_feature_packet", SCRIPT_PATH
    )
    assert spec is not None, f"Could not load spec from {SCRIPT_PATH}"
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


def weather_candidate(**overrides):
    """Synthetic Kalshi weather-contract candidate row."""
    row = {
        "ticker": "KXHIGH-26JUL03-NYC-90",
        "event_ticker": "KXHIGH-26JUL03-NYC",
        "series_ticker": "KXHIGH",
        "classification": "weather",
        "title": "Will high temp in NYC be >= 90F?",
        "close_time": "2026-07-03T20:00:00Z",
        "expected_expiration_time": "2026-07-03T21:00:00Z",
        "yes_bid": 0.45,
        "yes_ask": 0.48,
        "no_bid": 0.52,
        "no_ask": 0.55,
        "yes_spread": 0.03,
        "softness_score": 0.60,
        "official_rules_hash": "wx123",
        "official_rules_source": "public_kalshi_market_payload",
    }
    row.update(overrides)
    return row


def raw_market(**overrides):
    """Synthetic raw Kalshi market row for a weather contract."""
    row = {
        "ticker": "KXHIGH-26JUL03-NYC-90",
        "event_ticker": "KXHIGH-26JUL03-NYC",
        "series_ticker": "KXHIGH",
        "title": "Will high temp in NYC be >= 90F?",
        "tags": ["KXHIGH", "NYC"],
        "series_title": "NYC high temperature",
        "strike_type": "greater_or_equal",
        "floor_strike": 90.0,
        "cap_strike": None,
        "open_time": "2026-07-02T00:00:00Z",
        "close_time": "2026-07-03T20:00:00Z",
        "expected_expiration_time": "2026-07-03T21:00:00Z",
        "rules_primary": "If the high temp at NYC Central Park >= 90F, resolves Yes.",
        "settlement_sources": [{"name": "NWS", "url": "https://www.weather.gov/"}],
    }
    row.update(overrides)
    return row


def sports_candidate(**overrides):
    """Synthetic Kalshi sports contract (should be filtered out)."""
    row = {
        "ticker": "KXMLBGAME-26JUL03-CWSBAL",
        "event_ticker": "KXMLBGAME-26JUL03",
        "series_ticker": "KXMLBGAME",
        "classification": "baseball",
        "title": "CWS vs BAL game winner?",
        "close_time": "2026-07-03T20:00:00Z",
        "yes_bid": 0.45,
        "yes_ask": 0.48,
    }
    row.update(overrides)
    return row


def crypto_candidate(**overrides):
    """Synthetic Kalshi crypto contract (should be filtered out)."""
    row = {
        "ticker": "KXBTC15M-26JUL032015-15",
        "event_ticker": "KXBTC15M-26JUL032015",
        "series_ticker": "KXBTC15M",
        "classification": "finance_crypto",
        "title": "BTC price up in next 15 mins?",
        "close_time": "2026-07-03T20:15:00Z",
        "yes_bid": 0.21,
        "yes_ask": 0.22,
    }
    row.update(overrides)
    return row


def pseudo_fetch(url: str):
    """Fake fetch_json that returns synthetic NWS API responses."""
    if "/points/" in url:
        lat_lon = url.split("/points/")[1].split("?")[0].split(",")
        return {
            "properties": {
                "cwa": "OKX",
                "gridX": 50,
                "gridY": 50,
                "observationStations": "https://api.weather.gov/stations/KNYC/stations",
            }
        }
    if "/gridpoints/" in url and "/forecast" in url:
        return {
            "properties": {
                "periods": [
                    {
                        "number": 1,
                        "name": "Today",
                        "isDaytime": True,
                        "temperature": 78,
                        "temperatureUnit": "F",
                    }
                ]
            }
        }
    if "/stations/" in url and "/observations" in url:
        return {
            "features": [
                {
                    "properties": {
                        "timestamp": "2026-07-03T18:00:00Z",
                        "temperature": {"value": 75.0, "unitCode": "wmoUnit:degC"},
                    }
                }
            ]
        }
    if "kalshi.com" in url:
        return {}
    return {}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ── Tests ─────────────────────────────────────────────────────────────────


class TestWeatherFeaturePacketFilter:
    """VAL-WX-001 through VAL-WX-006: Universe filtering."""

    def test_filters_to_weather_series(self, tmp_path: Path) -> None:
        """VAL-WX-001: Only KXHIGH/KXLOW within close-time window."""
        module = load_weather_packet_module()
        universe_path = tmp_path / "universe.json"
        breadth_path = tmp_path / "breadth.json"
        raw_universe_path = tmp_path / "raw_universe.json"
        raw_proxy_dir = tmp_path / "raw_proxy"

        candidates = [
            weather_candidate(),  # in-window KXHIGH
            sports_candidate(),
            crypto_candidate(),
        ]
        raw_markets = [raw_market()]
        write_json(universe_path, {"candidates": candidates, "status": "universe_scan_ready"})
        write_json(breadth_path, safe_artifact())
        write_json(raw_universe_path, {"markets": raw_markets})

        report = module.build_weather_proxy_feature_packet(
            universe_scan_path=universe_path,
            probability_breadth_scout_path=breadth_path,
            raw_universe_path=raw_universe_path,
            raw_proxy_dir=raw_proxy_dir,
            generated_utc="2026-07-03T12:00:00Z",
            fetch_json=pseudo_fetch,
        )
        assert len(report["feature_rows"]) == 1
        assert report["feature_rows"][0]["contract_ticker"].startswith("KXHIGH")
        assert report["summary"]["feature_row_count"] == 1

    def test_resolves_current_kalshi_weather_series_city_suffixes(self, tmp_path: Path) -> None:
        """Current weather tickers encode city code in the series, e.g. KXHIGHMIA."""
        module = load_weather_packet_module()
        universe_path = tmp_path / "universe.json"
        breadth_path = tmp_path / "breadth.json"
        raw_universe_path = tmp_path / "raw_universe.json"
        raw_proxy_dir = tmp_path / "raw_proxy"

        candidates = [
            weather_candidate(
                ticker="KXHIGHMIA-26JUL03-B90.5",
                event_ticker="KXHIGHMIA-26JUL03",
                series_ticker="KXHIGHMIA",
            ),
            weather_candidate(
                ticker="KXLOWTSFO-26JUL03-B52.5",
                event_ticker="KXLOWTSFO-26JUL03",
                series_ticker="KXLOWTSFO",
                close_time="2026-07-03T21:00:00Z",
            ),
        ]
        raw_markets = [
            raw_market(
                ticker=row["ticker"],
                event_ticker=row["event_ticker"],
                series_ticker=row["series_ticker"],
            )
            for row in candidates
        ]
        write_json(universe_path, {"candidates": candidates, "status": "universe_scan_ready"})
        write_json(breadth_path, safe_artifact())
        write_json(raw_universe_path, {"markets": raw_markets})

        report = module.build_weather_proxy_feature_packet(
            universe_scan_path=universe_path,
            probability_breadth_scout_path=breadth_path,
            raw_universe_path=raw_universe_path,
            raw_proxy_dir=raw_proxy_dir,
            generated_utc="2026-07-03T12:00:00Z",
            fetch_json=pseudo_fetch,
        )

        station_by_ticker = {
            row["contract_ticker"]: row["station_id"] for row in report["feature_rows"]
        }
        assert station_by_ticker["KXHIGHMIA-26JUL03-B90.5"] == "KMIA"
        assert station_by_ticker["KXLOWTSFO-26JUL03-B52.5"] == "KSFO"

    def test_respects_close_time_window(self, tmp_path: Path) -> None:
        """VAL-WX-002: Past-close and far-future contracts excluded."""
        module = load_weather_packet_module()
        universe_path = tmp_path / "universe.json"
        breadth_path = tmp_path / "breadth.json"
        raw_universe_path = tmp_path / "raw_universe.json"
        raw_proxy_dir = tmp_path / "raw_proxy"

        candidates = [
            weather_candidate(close_time="2026-07-03T19:00:00Z"),  # in-window
            weather_candidate(
                ticker="KXHIGH-26JUL02-NYC-85",
                close_time="2026-07-02T20:00:00Z",
            ),  # past
            weather_candidate(
                ticker="KXHIGH-26JUL08-NYC-90",
                close_time="2026-07-08T20:00:00Z",
            ),  # far future
        ]
        raw_markets = [raw_market(ticker=c["ticker"]) for c in candidates]
        write_json(universe_path, {"candidates": candidates, "status": "universe_scan_ready"})
        write_json(breadth_path, safe_artifact())
        write_json(raw_universe_path, {"markets": raw_markets})

        report = module.build_weather_proxy_feature_packet(
            universe_scan_path=universe_path,
            probability_breadth_scout_path=breadth_path,
            raw_universe_path=raw_universe_path,
            raw_proxy_dir=raw_proxy_dir,
            generated_utc="2026-07-03T12:00:00Z",
            fetch_json=pseudo_fetch,
        )
        assert report["summary"]["feature_row_count"] == 1
        assert report["feature_rows"][0]["contract_ticker"] == "KXHIGH-26JUL03-NYC-90"

    def test_caps_at_max_contracts(self, tmp_path: Path) -> None:
        """VAL-WX-003: Max_contracts cap and ordering by closeness."""
        module = load_weather_packet_module()
        universe_path = tmp_path / "universe.json"
        breadth_path = tmp_path / "breadth.json"
        raw_universe_path = tmp_path / "raw_universe.json"
        raw_proxy_dir = tmp_path / "raw_proxy"

        candidates = [
            weather_candidate(
                ticker=f"KXHIGH-26JUL03-NYC-{i}", close_time=f"2026-07-03T{18 + i}:00:00Z"
            )
            for i in range(5)
        ]
        write_json(universe_path, {"candidates": candidates, "status": "universe_scan_ready"})
        write_json(breadth_path, safe_artifact())
        write_json(raw_universe_path, {"markets": []})

        report = module.build_weather_proxy_feature_packet(
            universe_scan_path=universe_path,
            probability_breadth_scout_path=breadth_path,
            raw_universe_path=raw_universe_path,
            raw_proxy_dir=raw_proxy_dir,
            generated_utc="2026-07-03T12:00:00Z",
            max_contracts=2,
            fetch_json=pseudo_fetch,
        )
        assert len(report["feature_rows"]) == 2
        t1 = report["feature_rows"][0]["fresh_time_to_close_hours"]
        t2 = report["feature_rows"][1]["fresh_time_to_close_hours"]
        assert t1 <= t2

    def test_dedup_by_contract_ticker(self, tmp_path: Path) -> None:
        """VAL-WX-004: Duplicate tickers collapse."""
        module = load_weather_packet_module()
        universe_path = tmp_path / "universe.json"
        breadth_path = tmp_path / "breadth.json"
        raw_universe_path = tmp_path / "raw_universe.json"
        raw_proxy_dir = tmp_path / "raw_proxy"

        candidates = [weather_candidate(), weather_candidate()]
        write_json(universe_path, {"candidates": candidates, "status": "universe_scan_ready"})
        write_json(breadth_path, safe_artifact())
        write_json(raw_universe_path, {"markets": []})

        report = module.build_weather_proxy_feature_packet(
            universe_scan_path=universe_path,
            probability_breadth_scout_path=breadth_path,
            raw_universe_path=raw_universe_path,
            raw_proxy_dir=raw_proxy_dir,
            generated_utc="2026-07-03T12:00:00Z",
            fetch_json=pseudo_fetch,
        )
        tickers = {r["contract_ticker"] for r in report["feature_rows"]}
        assert len(tickers) == len(report["feature_rows"])

    def test_empty_universe_blocks_gracefully(self, tmp_path: Path) -> None:
        """VAL-WX-005: Empty in-window -> blocked status, no crash."""
        module = load_weather_packet_module()
        universe_path = tmp_path / "universe.json"
        breadth_path = tmp_path / "breadth.json"
        raw_universe_path = tmp_path / "raw_universe.json"
        raw_proxy_dir = tmp_path / "raw_proxy"

        write_json(universe_path, {"candidates": [], "status": "universe_scan_ready"})
        write_json(breadth_path, safe_artifact())
        write_json(raw_universe_path, {"markets": []})

        report = module.build_weather_proxy_feature_packet(
            universe_scan_path=universe_path,
            probability_breadth_scout_path=breadth_path,
            raw_universe_path=raw_universe_path,
            raw_proxy_dir=raw_proxy_dir,
            generated_utc="2026-07-03T12:00:00Z",
            fetch_json=pseudo_fetch,
        )
        assert "blocked" in report["status"]
        assert report["summary"]["feature_row_count"] == 0

    def test_malformed_bracket_degrades(self, tmp_path: Path) -> None:
        """VAL-WX-006: Missing bracket degrades gracefully."""
        module = load_weather_packet_module()
        universe_path = tmp_path / "universe.json"
        breadth_path = tmp_path / "breadth.json"
        raw_universe_path = tmp_path / "raw_universe.json"
        raw_proxy_dir = tmp_path / "raw_proxy"

        candidates = [weather_candidate()]
        raw_markets = [raw_market(strike_type=None, floor_strike=None, cap_strike=None)]
        write_json(universe_path, {"candidates": candidates, "status": "universe_scan_ready"})
        write_json(breadth_path, safe_artifact())
        write_json(raw_universe_path, {"markets": raw_markets})

        report = module.build_weather_proxy_feature_packet(
            universe_scan_path=universe_path,
            probability_breadth_scout_path=breadth_path,
            raw_universe_path=raw_universe_path,
            raw_proxy_dir=raw_proxy_dir,
            generated_utc="2026-07-03T12:00:00Z",
            fetch_json=pseudo_fetch,
        )
        assert report["summary"]["feature_row_count"] == 1
        row = report["feature_rows"][0]
        assert row["feature_status"] is not None


class TestWeatherFeatureRowSchema:
    """VAL-WX-007 through VAL-WX-011: Feature row invariants."""

    def test_identity_fields_present(self, tmp_path: Path) -> None:
        """VAL-WX-007: Contract + station identity fields."""
        module = load_weather_packet_module()
        universe_path = tmp_path / "universe.json"
        breadth_path = tmp_path / "breadth.json"
        raw_universe_path = tmp_path / "raw_universe.json"
        raw_proxy_dir = tmp_path / "raw_proxy"

        candidates = [weather_candidate()]
        raw_markets = [raw_market()]
        write_json(universe_path, {"candidates": candidates, "status": "universe_scan_ready"})
        write_json(breadth_path, safe_artifact())
        write_json(raw_universe_path, {"markets": raw_markets})

        report = module.build_weather_proxy_feature_packet(
            universe_scan_path=universe_path,
            probability_breadth_scout_path=breadth_path,
            raw_universe_path=raw_universe_path,
            raw_proxy_dir=raw_proxy_dir,
            generated_utc="2026-07-03T12:00:00Z",
            fetch_json=pseudo_fetch,
        )
        row = report["feature_rows"][0]
        for key in (
            "contract_ticker",
            "event_ticker",
            "series_ticker",
            "close_time",
            "yes_bid",
            "yes_ask",
        ):
            assert row.get(key) is not None, f"Missing key: {key}"

    def test_research_only_invariants(self, tmp_path: Path) -> None:
        """VAL-WX-010: Every row research-only."""
        module = load_weather_packet_module()
        universe_path = tmp_path / "universe.json"
        breadth_path = tmp_path / "breadth.json"
        raw_universe_path = tmp_path / "raw_universe.json"
        raw_proxy_dir = tmp_path / "raw_proxy"

        candidates = [weather_candidate()]
        raw_markets = [raw_market()]
        write_json(universe_path, {"candidates": candidates, "status": "universe_scan_ready"})
        write_json(breadth_path, safe_artifact())
        write_json(raw_universe_path, {"markets": raw_markets})

        report = module.build_weather_proxy_feature_packet(
            universe_scan_path=universe_path,
            probability_breadth_scout_path=breadth_path,
            raw_universe_path=raw_universe_path,
            raw_proxy_dir=raw_proxy_dir,
            generated_utc="2026-07-03T12:00:00Z",
            fetch_json=pseudo_fetch,
        )
        assert report["research_only"] is True
        assert report["execution_enabled"] is False
        for row in report["feature_rows"]:
            assert row["usable"] is False
            assert row.get("calibrated_probability") is None
            assert row.get("expected_value_per_contract") is None

    def test_official_settlement_source(self, tmp_path: Path) -> None:
        """VAL-WX-011: Official settlement source is NWS Daily Climate Report."""
        module = load_weather_packet_module()
        universe_path = tmp_path / "universe.json"
        breadth_path = tmp_path / "breadth.json"
        raw_universe_path = tmp_path / "raw_universe.json"
        raw_proxy_dir = tmp_path / "raw_proxy"

        candidates = [weather_candidate()]
        raw_markets = [raw_market()]
        write_json(universe_path, {"candidates": candidates, "status": "universe_scan_ready"})
        write_json(breadth_path, safe_artifact())
        write_json(raw_universe_path, {"markets": raw_markets})

        report = module.build_weather_proxy_feature_packet(
            universe_scan_path=universe_path,
            probability_breadth_scout_path=breadth_path,
            raw_universe_path=raw_universe_path,
            raw_proxy_dir=raw_proxy_dir,
            generated_utc="2026-07-03T12:00:00Z",
            fetch_json=pseudo_fetch,
        )
        sp = report.get("source_policy", {})
        assert "NWS" in str(sp.get("official_settlement_source", ""))
        assert "Daily Climate Report" in str(sp.get("official_settlement_source", ""))


class TestWeatherFeaturePacketSafety:
    """Research-only safety and gates."""

    def test_research_only_flags(self, tmp_path: Path) -> None:
        """VAL-WX-044: research_only=true, execution_enabled=false."""
        module = load_weather_packet_module()
        universe_path = tmp_path / "universe.json"
        breadth_path = tmp_path / "breadth.json"
        raw_universe_path = tmp_path / "raw_universe.json"
        raw_proxy_dir = tmp_path / "raw_proxy"

        candidates = [weather_candidate()]
        raw_markets = [raw_market()]
        write_json(universe_path, {"candidates": candidates, "status": "universe_scan_ready"})
        write_json(breadth_path, safe_artifact())
        write_json(raw_universe_path, {"markets": raw_markets})

        report = module.build_weather_proxy_feature_packet(
            universe_scan_path=universe_path,
            probability_breadth_scout_path=breadth_path,
            raw_universe_path=raw_universe_path,
            raw_proxy_dir=raw_proxy_dir,
            generated_utc="2026-07-03T12:00:00Z",
            fetch_json=pseudo_fetch,
        )
        assert report["research_only"] is True
        assert report["execution_enabled"] is False
        safety = report.get("safety", {})
        assert safety.get("market_execution") is False
        assert safety.get("account_or_order_paths") is False
        assert safety.get("database_writes") is False

    def test_no_execution_paths(self, tmp_path: Path) -> None:
        """VAL-WX-045: No execution/account/order paths."""
        module = load_weather_packet_module()
        universe_path = tmp_path / "universe.json"
        breadth_path = tmp_path / "breadth.json"
        raw_universe_path = tmp_path / "raw_universe.json"
        raw_proxy_dir = tmp_path / "raw_proxy"

        candidates = [weather_candidate()]
        write_json(universe_path, {"candidates": candidates, "status": "universe_scan_ready"})
        write_json(breadth_path, safe_artifact())
        write_json(raw_universe_path, {"markets": []})

        report = module.build_weather_proxy_feature_packet(
            universe_scan_path=universe_path,
            probability_breadth_scout_path=breadth_path,
            raw_universe_path=raw_universe_path,
            raw_proxy_dir=raw_proxy_dir,
            generated_utc="2026-07-03T12:00:00Z",
            fetch_json=pseudo_fetch,
        )
        safety = report.get("safety", {})
        assert safety.get("staking_or_sizing_guidance") is False

    def test_gates_generated(self, tmp_path: Path) -> None:
        """Gates list is present and checkable."""
        module = load_weather_packet_module()
        universe_path = tmp_path / "universe.json"
        breadth_path = tmp_path / "breadth.json"
        raw_universe_path = tmp_path / "raw_universe.json"
        raw_proxy_dir = tmp_path / "raw_proxy"

        candidates = [weather_candidate()]
        raw_markets = [raw_market()]
        write_json(universe_path, {"candidates": candidates, "status": "universe_scan_ready"})
        write_json(breadth_path, safe_artifact())
        write_json(raw_universe_path, {"markets": raw_markets})

        report = module.build_weather_proxy_feature_packet(
            universe_scan_path=universe_path,
            probability_breadth_scout_path=breadth_path,
            raw_universe_path=raw_universe_path,
            raw_proxy_dir=raw_proxy_dir,
            generated_utc="2026-07-03T12:00:00Z",
            fetch_json=pseudo_fetch,
        )
        assert len(report.get("gates", [])) > 0
        # All gates should pass or warn (no fail on valid input)
        for g in report["gates"]:
            assert g["status"] in ("pass", "warn", "blocked")


class TestStationResolver:
    """VAL-WX-012 through VAL-WX-017: Station/gridpoint resolver."""

    def test_station_resolver_known_location(self) -> None:
        """Resolver works for known locations."""
        from predmarket.weather_family import weather_station_resolver

        result = weather_station_resolver(40.7128, -74.0060)
        assert result["status"] == "resolved"
        assert result["station_id"] is not None

    def test_station_resolver_graceful_degradation(self) -> None:
        """Unresolvable location degrades."""
        from predmarket.weather_family import weather_station_resolver

        def failing_fetch(url: str):
            raise RuntimeError("NWS outage")

        # With live fetch_json that fails
        result = weather_station_resolver(0.0, 0.0, fetch_json=failing_fetch)
        # Note: with synthetic mode (no fetch_json), it returns resolved via nearest station
        assert result["status"] == "unresolved"
        assert result["station_id"] is None


class TestBracketPrediction:
    """VAL-WX-018 through VAL-WX-021: Bracket prediction rule."""

    def test_bracket_probability_high_near_bracket(self) -> None:
        """Forecast well inside bracket -> high probability."""
        from predmarket.weather_family import compute_bracket_probability

        p = compute_bracket_probability(
            forecast_high=95.0,
            forecast_low=None,
            observation_temperature=None,
            strike=90.0,
            bracket_type="KXHIGH",
        )
        assert p is not None
        assert p > 0.8, f"Expected high probability near bracket, got {p}"

    def test_bracket_probability_low_outside_bracket(self) -> None:
        """Forecast well outside bracket -> low probability."""
        from predmarket.weather_family import compute_bracket_probability

        p = compute_bracket_probability(
            forecast_high=70.0,
            forecast_low=None,
            observation_temperature=None,
            strike=90.0,
            bracket_type="KXHIGH",
        )
        assert p is not None
        assert p < 0.3, f"Expected low probability outside bracket, got {p}"

    def test_prediction_rule_threshold(self) -> None:
        """VAL-WX-019: predicted_side from edge vs tau."""
        from predmarket.weather_family import weather_prediction_rule

        # Delta above tau -> YES
        side, conf = weather_prediction_rule(
            {
                "bracket_probability": 0.70,
                "yes_ask": 0.50,
                "prediction_tau": 0.05,
            }
        )
        assert side == 1

        # Delta below -tau -> NO
        side, conf = weather_prediction_rule(
            {
                "bracket_probability": 0.30,
                "yes_ask": 0.50,
                "prediction_tau": 0.05,
            }
        )
        assert side == 0

        # Inside band -> None
        side, conf = weather_prediction_rule(
            {
                "bracket_probability": 0.52,
                "yes_ask": 0.50,
                "prediction_tau": 0.05,
            }
        )
        assert side is None

    def test_prediction_deterministic(self) -> None:
        """VAL-WX-020: Same inputs -> same output."""
        from predmarket.weather_family import weather_prediction_rule

        row = {"bracket_probability": 0.65, "yes_ask": 0.50, "prediction_tau": 0.05}
        results = [weather_prediction_rule(dict(row)) for _ in range(5)]
        assert all(r == results[0] for r in results)
