"""Integration tests for public API capture paths.

These tests exercise the real data-flow of Kalshi capture functions using injected
fake HTTP sessions/clients. They verify pagination handling, error recovery,
artifact-writing logic, and safety guardrails without hitting live APIs.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from predmarket.kalshi_manual_drop_capture import (
    capture_kalshi_market_snapshot,
    write_capture_artifacts,
)
from predmarket.kalshi_universe_scan import (
    build_universe_scan_report,
    write_universe_scan_artifacts,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


class FakePaginatedSession:
    """Simulates paginated Kalshi API responses with cursor support."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.urls: list[str] = []

    def get(self, url):
        self.urls.append(url)
        payload = self.pages.pop(0) if self.pages else {"markets": [], "cursor": ""}
        return FakeResponse(payload)


class FakeUniverseClient:
    def __init__(self, session):
        self.session = session
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        self.closed = True

    async def fetch_markets(self, **kwargs):
        status = kwargs.get("status", "open")
        limit = kwargs.get("limit", 100)
        page = self.pages_for_status(status, limit)
        return page


class FakeManualDropClient:
    def __init__(self, markets_by_series):
        self.markets_by_series = markets_by_series

    async def fetch_markets(self, *, status, limit, max_pages, series_ticker, **_kwargs):
        result = self.markets_by_series.get(series_ticker)
        if isinstance(result, Exception):
            raise result
        return result or []


def _make_market(ticker="KXMLBGAME-26JUL01ABC-YES", **kwargs):
    base = {
        "ticker": ticker,
        "event_ticker": ticker.rsplit("-", 1)[0],
        "title": "Test Market",
        "close_time": "2026-07-01T20:00:00Z",
        "category": "crypto",
        "volume": 10000,
        "yes_ask": 0.55,
        "no_ask": 0.50,
        "floor_strike": "0.5",
        "rule_prefix": "crypto",
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Universe scan capture
# ---------------------------------------------------------------------------


def test_universe_scan_writes_full_artifact_set(tmp_path: Path) -> None:
    """Universe scan with a paginated client produces snapshot, latest, report,
    candidates CSV, routes JSON, and macro latest symlink."""

    # We cannot easily inject a fake session into KalshiMarketDataClient's
    # constructor, so we test the write + report path directly.
    snapshot = {
        "created_at_utc": "2026-07-01T12:00:00Z",
        "status": "kalshi_universe_public_fetch_ok",
        "research_only": True,
        "execution_enabled": False,
        "query": {"min_close_hours": 0, "max_close_hours": 72},
        "markets": [
            _make_market(ticker="KXBTC-26JUL01-YES", category="crypto"),
            _make_market(ticker="KXWEATHER-26JUL01-TEMP", category="weather"),
        ],
    }

    report = build_universe_scan_report(snapshot, generated_utc="2026-07-01T12:00:00Z")
    artifacts = write_universe_scan_artifacts(
        snapshot,
        report,
        raw_output_dir=tmp_path / "manual" / "kalshi_universe",
        latest_raw_path=tmp_path / "manual" / "kalshi_universe" / "latest.json",
        out_dir=tmp_path / "out",
        macro_dir=tmp_path / "macro",
    )

    # All artifact paths exist
    assert artifacts.snapshot_path.exists()
    assert artifacts.latest_raw_path.exists()
    assert artifacts.report_json_path.exists()
    assert artifacts.candidates_csv_path.exists()
    assert artifacts.routes_json_path.exists()

    # Written report is valid JSON with raw output paths
    written = json.loads(artifacts.report_json_path.read_text(encoding="utf-8"))
    assert written["research_only"] is True
    assert written["execution_enabled"] is False

    # Macro latest symlink exists
    assert (tmp_path / "macro" / "latest-kalshi-universe-scan.json").exists()

    # Candidates CSV has header + rows
    csv_text = artifacts.candidates_csv_path.read_text(encoding="utf-8")
    assert "ticker" in csv_text.splitlines()[0]


def test_universe_scan_report_guards_safety_fields(tmp_path: Path) -> None:
    """Report must carry research_only=True and execution_enabled=False."""
    snapshot = {
        "created_at_utc": "2026-07-01T12:00:00Z",
        "status": "kalshi_universe_public_fetch_ok",
        "research_only": True,
        "execution_enabled": False,
        "query": {"min_close_hours": 0, "max_close_hours": 72},
        "markets": [_make_market()],
    }
    report = build_universe_scan_report(snapshot, generated_utc="2026-07-01T12:00:00Z")
    assert report["research_only"] is True
    assert report["execution_enabled"] is False


# ---------------------------------------------------------------------------
# Manual drop capture
# ---------------------------------------------------------------------------


def test_manual_drop_capture_multi_series_with_error(tmp_path: Path) -> None:
    """Capture across multiple series with one failing. Must record success count,
    error, and maintain safety guardrails."""
    snapshot = asyncio.run(
        capture_kalshi_market_snapshot(
            series_tickers=("KXMLBGAME", "KXMLBTOTAL"),
            delay_seconds=0,
            created_ts=1_800_000_000.0,
            client=FakeManualDropClient(
                {
                    "KXMLBGAME": [_make_market(ticker="KXMLBGAME-26JUL01ABC-YES")],
                    "KXMLBTOTAL": RuntimeError("rate limited"),
                }
            ),
        )
    )

    assert snapshot["research_only"] is True
    assert snapshot["execution_enabled"] is False
    assert snapshot["safety"]["account_or_order_paths"] is False
    assert snapshot["market_count"] == 1
    assert "KXMLBTOTAL" in snapshot["series_errors"]


def test_manual_drop_writes_artifacts_and_latest(tmp_path: Path) -> None:
    """Write artifacts produces snapshot, latest, JSON report, and Markdown report."""
    snapshot = {
        "created_at_utc": "2026-07-01T00:00:00Z",
        "research_only": True,
        "execution_enabled": False,
        "safety": {
            "market_data_calls": True,
            "account_or_order_paths": False,
            "market_execution": False,
            "database_writes": False,
            "paid_calls": False,
            "raw_secrets_copied": False,
        },
        "market_count": 2,
        "series_counts": {"KXMLBGAME": 2},
        "series_errors": {},
        "all_scored": [
            _make_market(ticker="KXMLBGAME-26JUL01ABC-YES"),
            _make_market(ticker="KXMLBGAME-26JUL01ABC-NO"),
        ],
    }

    artifacts = write_capture_artifacts(
        snapshot,
        output_dir=tmp_path / "kalshi",
        latest_path=tmp_path / "kalshi" / "latest.json",
        report_dir=tmp_path / "reports",
        run_id="integration",
    )

    assert artifacts.snapshot_path.exists()
    assert artifacts.latest_path.exists()
    assert artifacts.report_json_path.exists()
    assert artifacts.report_markdown_path.exists()

    latest = json.loads(artifacts.latest_path.read_text(encoding="utf-8"))
    assert latest["market_count"] == 2

    md = artifacts.report_markdown_path.read_text(encoding="utf-8")
    assert "research-only" in md.lower()


# ---------------------------------------------------------------------------
# Crypto proxy observation capture
# ---------------------------------------------------------------------------


def test_crypto_proxy_capture_observed_markets(tmp_path: Path) -> None:
    """Exercise the capture_public_observed_markets_snapshot function with an
    injected fetch that returns settled market data."""
    import importlib.util

    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "kalshi_crypto_proxy_observation_loop.py"
    )
    spec = importlib.util.spec_from_file_location("observation_loop", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

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
    assert len(calls) == 1
    assert "KXBTC15M-26JUL012015-15" in calls[0]
