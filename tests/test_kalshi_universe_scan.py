from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from predmarket.kalshi_dataset import KalshiMarketDataClient
from predmarket.kalshi_universe_scan import (
    build_universe_scan_report,
    capture_kalshi_universe_snapshot,
    classify_market,
    write_universe_scan_artifacts,
)


MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"
SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "codex"
    / "macro"
    / "kalshi-universe-candidate.schema.json"
)


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def json(self):
        return self.payload

    async def text(self):
        return json.dumps(self.payload)


class FakeSession:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return FakeResponse(self.payloads.pop(0))


class FakeUniverseClient:
    def __init__(self, markets):
        self.markets = markets
        self.calls = []

    async def fetch_series_list(self, **_kwargs):
        return [
            {
                "ticker": "KXNFLGAME",
                "title": "NFL games",
                "category": "Sports",
                "tags": ["football"],
            },
            {
                "ticker": "KXHIGHNY",
                "title": "NYC weather",
                "category": "Climate",
                "tags": ["weather"],
            },
        ]

    async def fetch_markets(self, **kwargs):
        self.calls.append(kwargs)
        return self.markets


def dt(hours: float) -> str:
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    return (base + timedelta(hours=hours)).isoformat(timespec="seconds").replace("+00:00", "Z")


def market(**overrides):
    row = {
        "ticker": "KXNFLGAME-26SEP13MIALV-MIA",
        "event_ticker": "KXNFLGAME-26SEP13MIALV",
        "series_ticker": "KXNFLGAME",
        "title": "Will Miami win the Miami vs Las Vegas Pro Football game?",
        "subtitle": "Miami",
        "status": "active",
        "close_time": dt(24),
        "yes_bid_dollars": "0.3900",
        "yes_ask_dollars": "0.4100",
        "no_bid_dollars": "0.5800",
        "no_ask_dollars": "0.6000",
        "volume_fp": "125.00",
        "volume_24h_fp": "8.00",
        "open_interest_fp": "12.00",
        "liquidity_dollars": "50.0000",
        "updated_time": dt(-8),
        "rules_primary": "If Miami wins, then the market resolves to Yes.",
        "rules_secondary": "If the game ties, settlement is split.",
    }
    row.update(overrides)
    return row


def test_client_fetch_markets_paginates_until_cursor_empty() -> None:
    session = FakeSession(
        [
            {"markets": [{"ticker": "A"}], "cursor": "next"},
            {"markets": [{"ticker": "B"}], "cursor": ""},
        ]
    )
    config = SimpleNamespace(
        venues=SimpleNamespace(kalshi=SimpleNamespace(effective_api_url="https://example.test"))
    )
    client = KalshiMarketDataClient(config, session=session)

    rows = asyncio.run(
        client.fetch_markets(
            status="open",
            limit=1000,
            max_pages=5,
            min_close_ts=1,
            max_close_ts=2,
            mve_filter="exclude",
        )
    )

    assert [row["ticker"] for row in rows] == ["A", "B"]
    first_query = parse_qs(urlparse(session.urls[0]).query)
    second_query = parse_qs(urlparse(session.urls[1]).query)
    assert first_query["status"] == ["open"]
    assert first_query["limit"] == ["1000"]
    assert first_query["min_close_ts"] == ["1"]
    assert first_query["max_close_ts"] == ["2"]
    assert second_query["cursor"] == ["next"]


def test_universe_scan_filters_window_and_routes_model_candidates() -> None:
    markets = [
        market(),
        market(
            ticker="KXHIGHNY-26JUL01-T90",
            event_ticker="KXHIGHNY-26JUL01",
            series_ticker="KXHIGHNY",
            title="Will the high temperature in NYC be above 90?",
            subtitle="Weather",
            close_time=dt(6),
        ),
        market(ticker="OUTSIDE", close_time=dt(96)),
    ]
    snapshot = asyncio.run(
        capture_kalshi_universe_snapshot(
            max_close_hours=72,
            created_ts=datetime(2026, 7, 1, tzinfo=timezone.utc).timestamp(),
            client=FakeUniverseClient(markets),
        )
    )

    report = build_universe_scan_report(snapshot, generated_utc="2026-07-01T00:00:00Z")

    assert report["status"] == "universe_scan_ready_with_model_routes"
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["safety"]["authenticated_api_calls"] is False
    assert report["safety"]["account_or_order_paths"] is False
    assert report["safety"]["market_execution"] is False
    assert report["summary"]["candidate_count"] == 2
    assert report["summary"]["classification_counts"]["nfl"] == 1
    assert report["summary"]["classification_counts"]["weather"] == 1
    nfl = next(row for row in report["candidates"] if row["classification"] == "nfl")
    assert nfl["model_route"] == "nfl_quant_glm51_greenfield"
    assert nfl["usable"] is False
    assert nfl["edge_probability"] is None
    assert nfl["ev_status"] == "not_evaluated_universe_inventory_only"


def test_close_time_fallback_uses_expected_then_expiration() -> None:
    snapshot = {
        "created_at_utc": "2026-07-01T00:00:00Z",
        "status": "kalshi_universe_public_fetch_ok",
        "research_only": True,
        "execution_enabled": False,
        "query": {"min_close_hours": 0, "max_close_hours": 72},
        "markets": [
            market(ticker="EXPECTED", close_time=None, expected_expiration_time=dt(12)),
            market(ticker="EXPIRATION", close_time=None, expected_expiration_time=None, expiration_time=dt(18)),
            market(ticker="MISSING", close_time=None, expected_expiration_time=None, expiration_time=None),
        ],
    }

    report = build_universe_scan_report(snapshot, generated_utc="2026-07-01T00:00:00Z")

    tickers = {row["ticker"] for row in report["candidates"]}
    assert tickers == {"EXPECTED", "EXPIRATION"}
    assert report["summary"]["skipped_count"] == 1


def test_classification_covers_core_and_soft_routes() -> None:
    assert classify_market(market(series_ticker="KXMLBGAME", title="Baseball game")) == "mlb"
    assert classify_market(market(series_ticker="KXNBA", title="NBA basketball")) == "nba"
    assert classify_market(market(series_ticker="KXTENNIS", title="Wimbledon tennis match")) == "atp"
    assert classify_market(market(series_ticker="KXCPI", title="Will CPI inflation exceed forecast?")) == "macro_econ"
    assert classify_market(market(series_ticker="KXHORMUZ", title="Will Hormuz traffic return to normal?")) == "geopolitics"
    assert classify_market(market(series_ticker="KXWEIRD", title="An unusual unresolved thing")) == "unknown_soft_watch"


def test_write_universe_scan_artifacts_outputs_inventory_files(tmp_path: Path) -> None:
    snapshot = {
        "created_at_utc": "2026-07-01T00:00:00Z",
        "status": "kalshi_universe_public_fetch_ok",
        "research_only": True,
        "execution_enabled": False,
        "query": {"min_close_hours": 0, "max_close_hours": 72},
        "markets": [market()],
    }
    report = build_universe_scan_report(snapshot, generated_utc="2026-07-01T00:00:00Z")

    artifacts = write_universe_scan_artifacts(
        snapshot,
        report,
        raw_output_dir=tmp_path / "manual" / "kalshi_universe",
        latest_raw_path=tmp_path / "manual" / "kalshi_universe" / "latest.json",
        out_dir=tmp_path / "out",
        macro_dir=tmp_path / "macro",
    )

    assert artifacts.snapshot_path.exists()
    assert artifacts.latest_raw_path.exists()
    assert artifacts.report_json_path.exists()
    assert artifacts.candidates_csv_path.exists()
    assert artifacts.routes_json_path.exists()
    assert artifacts.soft_watch_markdown_path.exists()
    assert artifacts.schedule_template_path.exists()
    assert "OnUnitActiveSec=10min" in artifacts.schedule_template_path.read_text(encoding="utf-8")
    written = json.loads(artifacts.report_json_path.read_text(encoding="utf-8"))
    assert written["raw_outputs"]["snapshot_path"].startswith(str(tmp_path))
    assert (tmp_path / "macro" / "latest-kalshi-universe-scan.json").exists()


def test_makefile_exposes_universe_scan_targets() -> None:
    content = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-universe-scan" in content
    assert "kalshi-universe-watch-once" in content
    assert "predmarket.kalshi_universe_scan" in content


def test_universe_candidate_schema_loads() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["title"] == "KalshiUniverseCandidateV1"
    assert "ticker" in schema["required"]
    assert schema["properties"]["usable"]["const"] is False
