import json

from predmarket.kalshi_live_rank import KalshiLiveRankConfig, build_live_row, rank_live_rows
from predmarket.kalshi_paper_ledger import (
    build_paper_ledger_report,
    run_paper_ledger_audit,
    stable_ledger_report_id,
    write_paper_ledger_report,
)
from predmarket.kalshi_research_cycle import (
    KalshiPaperConfig,
    build_paper_intents,
    settle_paper_intents,
)
from predmarket.store import PointInTimeStore


AS_OF_TS = 1781550000.0


def _market():
    return {
        "ticker": "KXFED-26JUN-TARGET",
        "event_ticker": "KXFED-26JUN",
        "series_ticker": "KXFED",
        "title": "Will the Federal Reserve cut rates above 25 bps in June 2026?",
        "created_time": "2026-06-01T00:00:00Z",
        "close_time": "2026-06-20T16:00:00Z",
        "expiration_time": "2026-06-20T18:00:00Z",
        "yes_bid_dollars": "0.4100",
        "yes_ask_dollars": "0.4600",
        "last_price_dollars": "0.4400",
        "previous_price_dollars": "0.4000",
        "volume_fp": "100000.00",
        "volume_24h_fp": "25000.00",
        "open_interest_fp": "120000.00",
        "liquidity_dollars": "125000.0000",
        "rules_primary": "This market resolves according to the official Federal Reserve FOMC statement.",
        "rules_secondary": "Kalshi will use the official target range announcement.",
    }


def _orderbook():
    return {
        "orderbook_fp": {
            "yes_dollars": [["0.4200", "100.00"]],
            "no_dollars": [["0.5500", "80.00"]],
        }
    }


def _ledger_items():
    row = build_live_row(_market(), orderbook=_orderbook(), as_of_ts=AS_OF_TS)
    rank_report = rank_live_rows(
        [row],
        config=KalshiLiveRankConfig(
            min_liquidity_usd=1.0,
            max_spread=0.10,
            min_fill_probability=0.10,
            min_liquidity_adjusted_edge=0.005,
        ),
        discovery_report={
            "run_id": "discovery-unit",
            "top_hypotheses": [
                {
                    "hypothesis_id": "hyp-unit",
                    "name": "unit-edge",
                    "expression": "clip(market_implied + 0.20, 0.01, 0.99)",
                    "reward": 0.25,
                }
            ],
        },
    )
    intents, _ = build_paper_intents(
        rank_report,
        config=KalshiPaperConfig(min_liquidity_adjusted_edge=0.005, min_directional_edge=0.02),
        created_ts=AS_OF_TS,
    )
    settled = settle_paper_intents(
        intents,
        outcomes={"KXFED-26JUN-TARGET": 1},
        settled_ts=AS_OF_TS + 3600,
    )
    return [*intents, *settled]


def test_build_paper_ledger_report_summarizes_store_rows():
    report = build_paper_ledger_report(_ledger_items(), events=_ledger_items())

    assert report["ledger"]["count"] == 2
    assert report["ledger"]["stale_open_count"] == 0
    assert report["ledger"]["status_counts"]["PAPER_INTENDED"] == 1
    assert report["ledger"]["status_counts"]["SETTLED"] == 1
    assert report["ledger"]["settled_pnl_usd"] > 0
    assert report["events"]["count"] == 2
    assert len(report["integrity"]["ledger_hash"]) == 64
    assert len(report["integrity"]["events_hash"]) == 64


def test_build_paper_ledger_report_flags_stale_open_intents():
    intent = _ledger_items()[0]
    intent["as_of_ts"] = AS_OF_TS
    intent["source_opportunity"]["time_to_close_hours"] = 1.0
    report = build_paper_ledger_report(
        [intent],
        config=KalshiPaperConfig(stale_open_grace_hours=24.0),
        created_ts=AS_OF_TS + 26 * 3600,
    )

    assert report["ledger"]["stale_open_count"] == 1
    assert report["stale_open_intents"][0]["market_id"] == "KXFED-26JUN-TARGET"
    assert report["stale_open_intents"][0]["hours_past_stale"] == 1.0
    assert "stale_open_intents_present" in report["promotion_readiness"]["reasons"]


def test_stable_ledger_report_id_changes_with_event_history():
    ledger = _ledger_items()
    config = KalshiPaperConfig()

    without_events = stable_ledger_report_id(ledger, [], config)
    with_events = stable_ledger_report_id(ledger, ledger, config)

    assert without_events != with_events


def test_write_paper_ledger_report_outputs_json_and_markdown(tmp_path):
    report = build_paper_ledger_report(_ledger_items())
    artifacts = write_paper_ledger_report(report, reports_dir=tmp_path)

    assert artifacts.json_path.exists()
    assert artifacts.markdown_path.exists()
    assert json.loads(artifacts.json_path.read_text())["run_id"] == report["run_id"]
    assert "# Kalshi Paper Ledger" in artifacts.markdown_path.read_text()
    assert "## Stale Open Intents" in artifacts.markdown_path.read_text()


def test_run_paper_ledger_audit_loads_store(tmp_path):
    store = PointInTimeStore(tmp_path / "data")
    try:
        store.write_kalshi_paper_intents(_ledger_items())
        artifacts = run_paper_ledger_audit(store, reports_dir=tmp_path / "reports")
        events = store.load_kalshi_paper_events()
    finally:
        store.close()

    assert artifacts.report["ledger"]["count"] == 1
    assert artifacts.report["ledger"]["status_counts"]["SETTLED"] == 1
    assert artifacts.report["events"]["count"] == 2
    assert {event["status"] for event in events} == {"PAPER_INTENDED", "SETTLED"}
    assert all(event["paper_event_id"].startswith("kalshi-paper-event-") for event in events)
    assert {event["paper_event_type"] for event in events} == {"PAPER_INTENDED", "SETTLED"}
    assert all(event["paper_event_ts"] > 0 for event in events)
    assert artifacts.report["research_only"] is True
    assert artifacts.report["execution_enabled"] is False
