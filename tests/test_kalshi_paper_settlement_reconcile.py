import json
from pathlib import Path

from scripts.kalshi_paper_settlement_reconcile import (
    build_paper_settlement_reconciliation,
    capture_public_paper_settlement_snapshot,
)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def safe_paper_payload(*rows: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "generated_utc": "2026-07-04T16:00:00Z",
        "status": "paper_decision_candidates_ready_with_paper_sized_rows",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "policy": {
            "paper_bankroll": 1000.0,
            "max_fraction_per_contract": 0.02,
        },
        "summary": {"candidate_count": len(rows)},
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
        },
        "candidates": list(rows),
    }


def paper_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "contract_ticker": "KXUNIT-SETTLED",
        "side": "no",
        "family_id": "microstructure_informed_flow",
        "model_id": "flow_depth_imbalance_settlement_directional",
        "signal_key": "microstructure|flow|unit",
        "cluster_key": "mlb|unit|2026-07-04T18:00Z",
        "decision_time": "2026-07-04T16:00:00Z",
        "close_time": "2026-07-04T18:00:00Z",
        "close_bucket": "2026-07-04T18:00Z",
        "paper_usable": True,
        "paper_stake": 10.0,
        "calibrated_probability": 0.75,
        "all_in_cost": 0.25,
        "predicted_outcome": 0,
        "blocker_list": [],
    }
    row.update(overrides)
    return row


def settled_snapshot(*markets: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "kalshi_public_paper_settlement_probe_ok",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
        },
        "markets": list(markets),
    }


def test_reconcile_no_side_paper_win_computes_selected_pnl(tmp_path: Path) -> None:
    paper_path = tmp_path / "paper.json"
    settled_path = tmp_path / "settled.json"
    write_json(paper_path, safe_paper_payload(paper_row()))
    write_json(
        settled_path,
        settled_snapshot(
            {
                "ticker": "KXUNIT-SETTLED",
                "status": "settled",
                "result": "no",
                "settlement_value_dollars": 0,
                "close_time": "2026-07-04T18:00:00Z",
                "settled_time": "2026-07-04T18:10:00Z",
            }
        ),
    )

    report = build_paper_settlement_reconciliation(
        paper_decisions_path=paper_path,
        settled_snapshot_path=settled_path,
        generated_utc="2026-07-04T19:00:00Z",
    )

    assert report["status"] == "paper_settlement_reconciliation_ready_with_realized_rows"
    assert report["summary"]["settled_paper_usable_count"] == 1
    assert report["summary"]["winning_paper_usable_count"] == 1
    assert report["summary"]["realized_pnl"] == 30.0
    assert report["summary"]["paper_portfolio_largest_cluster"]["key"] == (
        "mlb|unit|2026-07-04T18:00Z"
    )
    assert report["summary"]["paper_portfolio_settled_stake"] == 10.0
    assert report["portfolio_risk"]["largest_signal"]["key"] == "microstructure|flow|unit"
    assert report["portfolio_risk"]["cap_status"] == "paper_portfolio_cap_breaches_present"
    row = report["candidates"][0]
    assert row["settled_outcome"] == 0
    assert row["selected_side_outcome"] == 1
    assert row["paper_contract_count"] == 40.0
    assert row["realized_roi"] == 3.0
    assert row["execution_enabled"] is False
    assert report["safety"]["market_execution"] is False


def test_reconcile_due_unsettled_paper_rows_emit_waiting_status(tmp_path: Path) -> None:
    paper_path = tmp_path / "paper.json"
    settled_path = tmp_path / "settled.json"
    write_json(paper_path, safe_paper_payload(paper_row(contract_ticker="KXUNIT-MISSING")))
    write_json(settled_path, settled_snapshot())

    report = build_paper_settlement_reconciliation(
        paper_decisions_path=paper_path,
        settled_snapshot_path=settled_path,
        generated_utc="2026-07-04T19:00:00Z",
    )

    assert report["status"] == "paper_settlement_reconciliation_waiting_for_due_settlements"
    assert report["summary"]["due_unresolved_paper_usable_count"] == 1
    assert report["unresolved_rows"][0]["settlement_status"] == "pending_settlement_due"
    assert report["unresolved_rows"][0]["realized_pnl"] is None


def test_reconcile_waiting_rows_emit_next_unresolved_close(tmp_path: Path) -> None:
    paper_path = tmp_path / "paper.json"
    settled_path = tmp_path / "settled.json"
    write_json(
        paper_path,
        safe_paper_payload(
            paper_row(
                contract_ticker="KXUNIT-FUTURE-A",
                close_time="2026-07-04T20:00:00Z",
            ),
            paper_row(
                contract_ticker="KXUNIT-FUTURE-B",
                close_time="2026-07-04T19:30:00Z",
            ),
        ),
    )
    write_json(settled_path, settled_snapshot())

    report = build_paper_settlement_reconciliation(
        paper_decisions_path=paper_path,
        settled_snapshot_path=settled_path,
        generated_utc="2026-07-04T19:00:00Z",
    )

    assert report["status"] == "paper_settlement_reconciliation_waiting_for_close"
    assert report["summary"]["next_unresolved_close_time_utc"] == "2026-07-04T19:30:00Z"
    assert "2026-07-04T19:30:00Z" in report["next_action"]["why"]


def test_capture_public_paper_settlement_snapshot_uses_exact_tickers(
    tmp_path: Path,
) -> None:
    def fake_fetch(url: str) -> dict[str, object]:
        assert url.endswith("/markets/KXUNIT-SETTLED")
        return {
            "market": {
                "ticker": "KXUNIT-SETTLED",
                "result": "yes",
                "settlement_value_dollars": 1,
            }
        }

    latest = capture_public_paper_settlement_snapshot(
        tickers=["KXUNIT-SETTLED"],
        raw_dir=tmp_path,
        generated_utc="2026-07-04T19:00:00Z",
        fetch_json=fake_fetch,
    )

    payload = json.loads(latest.read_text())
    assert latest.name == "kalshi_paper_observed_markets_latest.json"
    assert payload["summary"]["market_count"] == 1
    assert payload["summary"]["settled_label_ready_count"] == 1
    assert payload["safety"]["market_execution"] is False


def test_makefile_target_exists() -> None:
    text = Path("Makefile").read_text(encoding="utf-8")
    assert "kalshi-paper-settlement-reconcile:" in text
    assert "scripts/kalshi_paper_settlement_reconcile.py" in text
