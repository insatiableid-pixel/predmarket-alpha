import asyncio
import json

from predmarket.kalshi_manual_drop_capture import (
    build_capture_report,
    capture_kalshi_market_snapshot,
    render_capture_report_markdown,
    write_capture_artifacts,
)


class FakeKalshiClient:
    def __init__(self, markets_by_series):
        self.markets_by_series = markets_by_series

    async def fetch_markets(self, *, status, limit, max_pages, series_ticker, **_kwargs):
        if isinstance(self.markets_by_series.get(series_ticker), Exception):
            raise self.markets_by_series[series_ticker]
        return self.markets_by_series.get(series_ticker, [])


def test_capture_kalshi_market_snapshot_records_counts_and_errors():
    snapshot = asyncio.run(capture_kalshi_market_snapshot(
        series_tickers=("KXMLBGAME", "KXMLBTOTAL"),
        delay_seconds=0,
        created_ts=1_800_000_000.0,
        client=FakeKalshiClient(
            {
                "KXMLBGAME": [
                    {
                        "ticker": "KXMLBGAME-26JUN291905ABCXYZ-ABC",
                        "event_ticker": "KXMLBGAME-26JUN291905ABCXYZ",
                        "title": "ABC vs XYZ Winner?",
                    }
                ],
                "KXMLBTOTAL": RuntimeError("rate limited"),
            }
        ),
    ))

    assert snapshot["research_only"] is True
    assert snapshot["execution_enabled"] is False
    assert snapshot["safety"]["account_or_order_paths"] is False
    assert snapshot["market_count"] == 1
    assert snapshot["series_counts"] == {"KXMLBGAME": 1, "KXMLBTOTAL": 0}
    assert "KXMLBTOTAL" in snapshot["series_errors"]


def test_write_capture_artifacts_writes_snapshot_latest_and_report(tmp_path):
    snapshot = {
        "created_at_utc": "2026-06-29T00:00:00Z",
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
        "market_count": 1,
        "series_counts": {"KXMLBGAME": 1},
        "series_errors": {},
        "all_scored": [{"ticker": "KXMLBGAME-26JUN291905ABCXYZ-ABC"}],
    }

    artifacts = write_capture_artifacts(
        snapshot,
        output_dir=tmp_path / "kalshi",
        latest_path=tmp_path / "kalshi" / "latest.json",
        report_dir=tmp_path / "reports",
        run_id="unit",
    )

    assert artifacts.snapshot_path.exists()
    assert artifacts.latest_path.exists()
    assert artifacts.report_json_path.exists()
    assert artifacts.report_markdown_path.exists()
    assert json.loads(artifacts.latest_path.read_text())["market_count"] == 1


def test_capture_report_markdown_keeps_guardrails():
    report = build_capture_report(
        {
            "created_at_utc": "2026-06-29T00:00:00Z",
            "market_count": 0,
            "safety": {"account_or_order_paths": False},
            "series_counts": {},
            "series_errors": {},
        }
    )
    markdown = render_capture_report_markdown(report)

    assert "research-only market data" in markdown
    assert "does not authorize execution or account activity" in markdown
    forbidden = ["Kelly", "bankroll", "stake", "place a bet", "wager"]
    assert not any(term in markdown for term in forbidden)
