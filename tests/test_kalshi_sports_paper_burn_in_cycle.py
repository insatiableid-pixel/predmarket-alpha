from pathlib import Path

from scripts.kalshi_sports_paper_burn_in_cycle import (
    build_sports_paper_burn_in_report,
)


def settlement_artifact(
    *,
    status: str = "paper_settlement_reconciliation_waiting_for_close",
    paper_usable_count: int = 1,
    due_unresolved: int = 0,
    settled: int = 0,
    close_time: str = "2026-07-04T18:05:00Z",
) -> dict[str, object]:
    return {
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "summary": {
            "paper_usable_count": paper_usable_count,
            "due_unresolved_paper_usable_count": due_unresolved,
            "next_unresolved_close_time_utc": close_time if not settled else None,
            "settled_paper_usable_count": settled,
            "unresolved_paper_usable_count": paper_usable_count - settled,
            "total_paper_stake": 10.0,
            "paper_portfolio_cap_status": "paper_portfolio_caps_observed",
            "paper_portfolio_cap_breach_count": 0,
            "paper_portfolio_unresolved_stake": 0.0 if settled else 10.0,
            "paper_portfolio_settled_stake": 10.0 if settled else 0.0,
            "paper_portfolio_largest_cluster": {
                "key": "mlb|unit|2026-07-04T18:00Z",
                "paper_stake": 10.0,
                "stake_share": 1.0,
            },
            "realized_pnl": 12.5 if settled else 0,
            "hit_rate": 1.0 if settled else None,
        },
        "candidates": [
            {
                "paper_usable": True,
                "contract_ticker": "KXUNIT-PAPER",
                "close_time": close_time,
            }
        ],
    }


def retirement_artifact() -> dict[str, object]:
    return {
        "status": "signal_decay_retirement_ledger_ready",
        "summary": {"active_signal_count": 1, "retired_signal_count": 0},
    }


def evidence_artifact() -> dict[str, object]:
    return {
        "status": "sports_evidence_cycle_ready_with_label_progress",
        "summary": {"live_eligible_count": 0},
    }


def label_artifact() -> dict[str, object]:
    return {
        "status": "sports_label_accumulation_oos_fdr_research_candidates_ready",
        "summary": {
            "total_exact_label_count": 324,
            "total_independent_label_count": 78,
            "total_label_deficit": 12,
            "oos_fdr_candidate_family_count": 1,
        },
        "family_rows": [
            {
                "family_id": "mlb",
                "status": "waiting_more_independent_exact_labels",
                "label_deficit": 4,
                "next_public_label_probe_utc": "2026-07-04T07:25:05Z",
            },
            {
                "family_id": "world_cup_soccer",
                "status": "oos_fdr_candidate_ready",
                "label_deficit": 0,
                "next_public_label_probe_utc": "2026-07-04T07:25:29Z",
            },
            {
                "family_id": "atp",
                "status": "waiting_exact_labels",
                "label_deficit": 8,
                "next_public_label_probe_utc": "2026-07-04T07:25:16Z",
            },
        ],
    }


def build_report(**overrides):
    kwargs = {
        "generated_utc": "2026-07-04T17:12:00Z",
        "paper_decisions_path": Path("paper.json"),
        "settlement_snapshot_path": Path("settled.json"),
        "fetched_snapshot_path": None,
        "due_tickers_before_fetch": [],
        "settlement": settlement_artifact(),
        "retirement": retirement_artifact(),
        "evidence": evidence_artifact(),
        "label": label_artifact(),
    }
    kwargs.update(overrides)
    return build_sports_paper_burn_in_report(**kwargs)


def test_burn_in_reports_next_close_when_paper_rows_not_due() -> None:
    report = build_report()

    assert report["status"] == "sports_paper_burn_in_waiting_for_next_close"
    assert report["summary"]["next_paper_close_time_utc"] == "2026-07-04T18:05:00Z"
    assert report["summary"]["due_after_fetch_count"] == 0
    assert report["summary"]["paper_portfolio_cap_status"] == "paper_portfolio_caps_observed"
    assert report["summary"]["paper_portfolio_largest_cluster"]["key"] == (
        "mlb|unit|2026-07-04T18:00Z"
    )
    assert report["next_action"]["name"] == "kalshi_paper_lifecycle_wait"
    assert report["execution_enabled"] is False
    assert report["safety"]["market_execution"] is False


def test_burn_in_prefers_settlement_summary_next_close() -> None:
    settlement = settlement_artifact(close_time="2026-07-04T18:05:00Z")
    settlement["summary"]["next_unresolved_close_time_utc"] = "2026-07-04T17:45:00Z"

    report = build_report(settlement=settlement)

    assert report["summary"]["next_paper_close_time_utc"] == "2026-07-04T17:45:00Z"


def test_burn_in_reports_due_public_settlement_probe_needed() -> None:
    settlement = settlement_artifact(
        status="paper_settlement_reconciliation_waiting_for_due_settlements",
        due_unresolved=1,
        close_time="2026-07-04T16:00:00Z",
    )

    report = build_report(
        generated_utc="2026-07-04T17:12:00Z",
        due_tickers_before_fetch=["KXUNIT-PAPER"],
        settlement=settlement,
    )

    assert report["status"] == "sports_paper_burn_in_waiting_for_public_settlement"
    assert report["summary"]["due_before_fetch_count"] == 1
    assert report["summary"]["due_after_fetch_count"] == 1
    assert "KALSHI_SPORTS_PAPER_BURN_IN_FETCH=1" in report["next_action"]["command"]


def test_burn_in_reports_realized_paper_rows_for_retirement_review() -> None:
    settlement = settlement_artifact(
        status="paper_settlement_reconciliation_ready_with_realized_rows",
        paper_usable_count=1,
        due_unresolved=0,
        settled=1,
        close_time="2026-07-04T16:00:00Z",
    )

    report = build_report(
        generated_utc="2026-07-04T17:12:00Z",
        settlement=settlement,
    )

    assert report["status"] == "sports_paper_burn_in_ready_with_realized_paper_rows"
    assert report["summary"]["settled_paper_usable_count"] == 1
    assert report["summary"]["paper_realized_pnl"] == 12.5
    assert report["next_action"]["name"] == "kalshi_sports_paper_outcome_audit"


def test_makefile_target_exists() -> None:
    text = Path("Makefile").read_text(encoding="utf-8")

    assert "kalshi-sports-paper-burn-in-cycle:" in text
    assert "kalshi-sports-label-accumulation-cycle" in text
    assert "scripts/kalshi_sports_paper_burn_in_cycle.py" in text
    assert "KALSHI_SPORTS_PAPER_BURN_IN_FETCH" in text
