from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kalshi_tick_recorder.py"


def load_module():
    spec = importlib.util.spec_from_file_location("kalshi_tick_recorder", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_select_sports_tickers_from_universe() -> None:
    module = load_module()
    universe = {
        "markets": [
            {"ticker": "KXMLBGAME-26JUL04-AAA", "classification": "mlb"},
            {"ticker": "KXATPMATCH-26JUL04-BBB", "series_ticker": "KXATPMATCH"},
            {"ticker": "KXFED-26JUL", "classification": "macro_econ"},
            {"contract_ticker": "KXWC-26JUL04-CCC", "classification": "other_sports"},
        ]
    }

    tickers = module.select_sports_tickers(universe, max_tickers=10)

    assert tickers == [
        "KXMLBGAME-26JUL04-AAA",
        "KXATPMATCH-26JUL04-BBB",
        "KXWC-26JUL04-CCC",
    ]


def test_append_message_writes_replayable_jsonl_and_gap_stats(tmp_path: Path) -> None:
    module = load_module()
    path = tmp_path / "ticks.jsonl"
    stats = module.RecorderStats()
    message = {
        "received_at_utc": "2026-07-06T00:00:00.000Z",
        "text": '{"type":"ticker","msg":{"market_ticker":"KXMLBGAME"}}',
        "payload": {"type": "ticker", "msg": {"market_ticker": "KXMLBGAME"}},
    }

    module.append_message(path, message, stats=stats, max_gap_seconds=0.001)
    time.sleep(0.002)
    module.append_message(
        path,
        {**message, "received_at_utc": "2026-07-06T00:00:01.000Z"},
        stats=stats,
        max_gap_seconds=0.001,
    )
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert len(rows) == 2
    assert rows[0]["type"] == "ticker"
    assert rows[0]["raw_text_sha256"]
    assert rows[0]["raw_text"].startswith('{"type":"ticker"')
    assert stats.line_count == 2
    assert stats.gap_count >= 1


def test_recorder_report_is_research_only(tmp_path: Path) -> None:
    module = load_module()
    report = module.recorder_report(
        generated_utc="2026-07-06T00:00:00Z",
        status="kalshi_tick_recorder_ready",
        tickers=["KXMLBGAME-26JUL04-AAA"],
        channels=["ticker", "orderbook_delta"],
        jsonl_path=tmp_path / "ticks.jsonl",
        stats=module.RecorderStats(line_count=3),
        authenticated=True,
        error=None,
    )

    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["account_or_order_paths"] is False
    assert report["market_execution"] is False
    assert report["summary"]["recorded_line_count"] == 3


def test_makefile_wires_tick_recorder_target() -> None:
    text = (Path(__file__).resolve().parents[1] / "Makefile").read_text(encoding="utf-8")

    assert "kalshi-tick-recorder:" in text
    assert "scripts/kalshi_tick_recorder.py" in text
    assert "KALSHI_TICK_RECORDER_CHANNELS ?= ticker,orderbook_delta" in text
