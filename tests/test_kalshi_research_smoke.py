import json
from pathlib import Path

from predmarket.kalshi_research_smoke import build_smoke_rank_report, run_kalshi_research_smoke


def test_build_smoke_rank_report_has_research_opportunity():
    report = build_smoke_rank_report(as_of_ts=1781550000.0)

    assert report["input_summary"]["n_rows"] == 1
    assert report["top_opportunities"][0]["market_id"] == "KXSMOKE-26JUN-TARGET"
    assert report["top_opportunities"][0]["candidate_status"] == "RESEARCH_ONLY_PASS"


def test_run_kalshi_research_smoke_writes_cycle_and_ledger_artifacts(tmp_path):
    report = run_kalshi_research_smoke(
        data_dir=tmp_path / "data",
        reports_dir=tmp_path / "reports",
        as_of_ts=1781550000.0,
    )

    cycle_json = Path(report["cycle"]["json_path"])
    cycle_md = Path(report["cycle"]["markdown_path"])
    ledger_json = Path(report["ledger"]["json_path"])
    ledger_md = Path(report["ledger"]["markdown_path"])

    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["cycle"]["paper_intents"] == 1
    assert report["cycle"]["settled"] == 1
    assert report["cycle"]["events"] == 2
    assert report["ledger"]["count"] == 1
    assert report["ledger"]["events"] == 2
    assert cycle_json.exists()
    assert cycle_md.exists()
    assert ledger_json.exists()
    assert ledger_md.exists()
    assert json.loads(cycle_json.read_text())["research_only"] is True
    assert "# Kalshi Research Cycle" in cycle_md.read_text()
    assert "# Kalshi Paper Ledger" in ledger_md.read_text()
