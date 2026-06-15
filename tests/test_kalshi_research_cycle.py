import json

from predmarket.kalshi_live_rank import KalshiLiveRankConfig, build_live_row, rank_live_rows
from predmarket.kalshi_research_cycle import (
    KalshiPaperConfig,
    KalshiResearchCycleConfig,
    build_paper_intents,
    compute_paper_stake_usd,
    cycle_integrity,
    load_outcomes,
    load_rank_report,
    paper_promotion_readiness,
    run_kalshi_research_cycle,
    settle_paper_intents,
    stable_cycle_run_id,
    stale_open_paper_intents,
    summarize_paper_ledger,
)
from predmarket.kalshi_dataset import persist_rows
from predmarket.store import PointInTimeStore


AS_OF_TS = 1781550000.0


def _market(**overrides):
    base = {
        "ticker": "KXFED-26JUN-TARGET",
        "event_ticker": "KXFED-26JUN",
        "series_ticker": "KXFED",
        "title": "Will the Federal Reserve cut rates above 25 bps in June 2026?",
        "subtitle": "Fed target rate decision",
        "created_time": "2026-06-01T00:00:00Z",
        "updated_time": "2026-06-15T12:00:00Z",
        "open_time": "2026-06-01T00:00:00Z",
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
        "settlement_timer_seconds": 3600,
        "can_close_early": True,
        "fractional_trading_enabled": True,
        "rules_primary": "This market resolves according to the official Federal Reserve FOMC statement.",
        "rules_secondary": "Kalshi will use the official target range announcement.",
    }
    base.update(overrides)
    return base


def _orderbook():
    return {
        "orderbook_fp": {
            "yes_dollars": [["0.4200", "100.00"], ["0.3900", "200.00"]],
            "no_dollars": [["0.5500", "80.00"], ["0.5200", "120.00"]],
        }
    }


def _live_row(**market_overrides):
    return build_live_row(
        _market(**market_overrides),
        orderbook=_orderbook(),
        candlesticks=[],
        as_of_ts=AS_OF_TS,
    )


def _discovery_report(expression="clip(market_implied + 0.20, 0.01, 0.99)"):
    return {
        "run_id": "discovery-unit",
        "top_hypotheses": [
            {
                "hypothesis_id": "hyp-unit",
                "name": "unit-edge",
                "expression": expression,
                "reward": 0.25,
            }
        ],
    }


def _rank_report():
    return rank_live_rows(
        [_live_row()],
        config=KalshiLiveRankConfig(
            min_liquidity_usd=1.0,
            max_spread=0.10,
            min_fill_probability=0.10,
            min_liquidity_adjusted_edge=0.005,
        ),
        discovery_report=_discovery_report(),
    )


def test_build_paper_intents_from_unblocked_rank_report():
    rank_report = _rank_report()
    intents, blocked = build_paper_intents(
        rank_report,
        config=KalshiPaperConfig(
            min_liquidity_adjusted_edge=0.005,
            min_directional_edge=0.02,
            max_stake_usd=25.0,
            max_total_stake_usd=50.0,
        ),
        created_ts=AS_OF_TS,
    )

    assert blocked == []
    assert len(intents) == 1
    intent = intents[0]
    assert intent["status"] == "PAPER_INTENDED"
    assert intent["research_only"] is True
    assert intent["execution_enabled"] is False
    assert intent["stake_usd"] > 0
    assert intent["expected_value_usd"] > 0
    assert intent["side"] == "YES"


def test_build_paper_intents_blocks_watchlist_or_rank_blocked():
    row = _live_row()
    rank_report = rank_live_rows([row], discovery_report=None)
    intents, blocked = build_paper_intents(rank_report, created_ts=AS_OF_TS)

    assert intents == []
    assert blocked
    assert "paper_requires_discovery_hypothesis" in blocked[0]["paper_blocking_reasons"]


def test_build_paper_intents_suppresses_existing_open_intent():
    rank_report = _rank_report()
    first_intents, _ = build_paper_intents(
        rank_report,
        config=KalshiPaperConfig(min_liquidity_adjusted_edge=0.005, min_directional_edge=0.02),
        created_ts=AS_OF_TS,
    )
    second_intents, blocked = build_paper_intents(
        rank_report,
        config=KalshiPaperConfig(min_liquidity_adjusted_edge=0.005, min_directional_edge=0.02),
        existing_intents=first_intents,
        created_ts=AS_OF_TS + 60,
    )

    assert second_intents == []
    assert "paper_duplicate_open_intent" in blocked[0]["paper_blocking_reasons"]


def test_build_paper_intents_counts_existing_open_exposure_against_caps():
    rank_report = rank_live_rows(
        [_live_row(ticker="KXFED-26JUN-OTHER")],
        config=KalshiLiveRankConfig(
            min_liquidity_usd=1.0,
            max_spread=0.10,
            min_fill_probability=0.10,
            min_liquidity_adjusted_edge=0.005,
        ),
        discovery_report=_discovery_report(),
    )
    existing = [
        {
            "intent_id": "existing",
            "market_id": "KXFED-26JUN-TARGET",
            "event_id": "KXFED-26JUN",
            "side": "YES",
            "status": "PAPER_INTENDED",
            "stake_usd": 50.0,
        }
    ]
    intents, blocked = build_paper_intents(
        rank_report,
        config=KalshiPaperConfig(
            min_liquidity_adjusted_edge=0.005,
            min_directional_edge=0.02,
            max_event_stake_usd=50.0,
        ),
        existing_intents=existing,
        created_ts=AS_OF_TS,
    )

    assert intents == []
    assert "stake_below_minimum" in blocked[0]["paper_blocking_reasons"]


def test_build_paper_intents_blocks_stale_rank_report():
    rank_report = dict(_rank_report())
    rank_report["created_ts"] = AS_OF_TS - 7 * 3600
    intents, blocked = build_paper_intents(
        rank_report,
        config=KalshiPaperConfig(
            min_liquidity_adjusted_edge=0.005,
            min_directional_edge=0.02,
            max_rank_report_age_hours=6.0,
        ),
        created_ts=AS_OF_TS,
    )

    assert intents == []
    assert "paper_rank_report_stale" in blocked[0]["paper_blocking_reasons"]


def test_build_paper_intents_blocks_rank_report_without_created_ts():
    rank_report = dict(_rank_report())
    rank_report.pop("created_ts", None)
    intents, blocked = build_paper_intents(
        rank_report,
        config=KalshiPaperConfig(
            min_liquidity_adjusted_edge=0.005,
            min_directional_edge=0.02,
        ),
        created_ts=AS_OF_TS,
    )

    assert intents == []
    assert "paper_rank_report_missing_created_ts" in blocked[0]["paper_blocking_reasons"]


def test_build_paper_intents_blocks_non_research_only_rank_report():
    rank_report = dict(_rank_report())
    rank_report["research_only"] = False
    rank_report["execution_enabled"] = True
    intents, blocked = build_paper_intents(
        rank_report,
        config=KalshiPaperConfig(
            min_liquidity_adjusted_edge=0.005,
            min_directional_edge=0.02,
        ),
        created_ts=float(rank_report["created_ts"]),
    )

    assert intents == []
    assert "paper_rank_report_not_research_only" in blocked[0]["paper_blocking_reasons"]


def test_build_paper_intents_blocks_non_kalshi_opportunity():
    rank_report = dict(_rank_report())
    rank_report["created_ts"] = AS_OF_TS
    rank_report["top_opportunities"] = [dict(rank_report["top_opportunities"][0], venue="Polymarket")]
    intents, blocked = build_paper_intents(
        rank_report,
        config=KalshiPaperConfig(
            min_liquidity_adjusted_edge=0.005,
            min_directional_edge=0.02,
        ),
        created_ts=AS_OF_TS,
    )

    assert intents == []
    assert "paper_non_kalshi_opportunity" in blocked[0]["paper_blocking_reasons"]


def test_compute_paper_stake_respects_caps():
    opportunity = {
        "liquidity_adjusted_edge": 0.10,
        "directional_edge": 0.20,
        "fill_probability": 1.0,
    }
    stake = compute_paper_stake_usd(
        opportunity,
        config=KalshiPaperConfig(bankroll_usd=100_000.0, max_stake_usd=12.0),
        remaining_total=100.0,
        remaining_event=100.0,
    )

    assert stake == 12.0


def test_store_roundtrips_paper_intents(tmp_path):
    intents, _ = build_paper_intents(
        _rank_report(),
        config=KalshiPaperConfig(min_liquidity_adjusted_edge=0.005, min_directional_edge=0.02),
        created_ts=AS_OF_TS,
    )
    store = PointInTimeStore(tmp_path)
    try:
        store.write_kalshi_paper_intents(intents)
        loaded = store.load_kalshi_paper_intents(status="PAPER_INTENDED")
    finally:
        store.close()

    assert [item["intent_id"] for item in loaded] == [item["intent_id"] for item in intents]
    assert loaded[0]["market_id"] == "KXFED-26JUN-TARGET"


def test_settle_paper_intents_calculates_pnl():
    intents, _ = build_paper_intents(
        _rank_report(),
        config=KalshiPaperConfig(min_liquidity_adjusted_edge=0.005, min_directional_edge=0.02),
        created_ts=AS_OF_TS,
    )
    settled = settle_paper_intents(
        intents,
        outcomes={"KXFED-26JUN-TARGET": 1},
        settled_ts=AS_OF_TS + 3600,
    )

    assert settled[0]["status"] == "SETTLED"
    assert settled[0]["pnl_usd"] > 0
    assert settled[0]["outcome_yes"] == 1


def test_research_cycle_writes_audit_report_and_ledger(tmp_path, mock_config):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "discovery-unit.json").write_text(json.dumps(_discovery_report()))
    store = PointInTimeStore(tmp_path / "data")
    try:
        artifacts = run_kalshi_research_cycle(
            store,
            app_config=mock_config,
            config=KalshiResearchCycleConfig(
                live_rank=KalshiLiveRankConfig(
                    min_liquidity_usd=1.0,
                    max_spread=0.10,
                    min_fill_probability=0.10,
                    min_liquidity_adjusted_edge=0.005,
                ),
                paper=KalshiPaperConfig(
                    min_liquidity_adjusted_edge=0.005,
                    min_directional_edge=0.02,
                    settle_existing=False,
                ),
            ),
            rows=[_live_row()],
            reports_dir=reports_dir,
        )
        ledger = store.load_kalshi_paper_intents()
    finally:
        store.close()

    assert artifacts.json_path.exists()
    assert artifacts.markdown_path.exists()
    assert artifacts.report["paper"]["intended_count"] == 1
    assert artifacts.report["ranked"]["markets_ranked"] == 1
    assert artifacts.report["ranked"]["rank_report_age_hours"] >= 0
    assert artifacts.report["ranked"]["rank_report_research_only"] is True
    assert artifacts.report["ranked"]["rank_report_execution_enabled"] is False
    assert artifacts.report["events"]["count"] == 1
    assert artifacts.report["events"]["status_counts"] == {"PAPER_INTENDED": 1}
    assert ledger[0]["status"] == "PAPER_INTENDED"
    assert "# Kalshi Research Cycle" in artifacts.markdown_path.read_text()


def test_research_cycle_settles_existing_from_resolved_rows(tmp_path, mock_config):
    rank_report = _rank_report()
    intents, _ = build_paper_intents(
        rank_report,
        config=KalshiPaperConfig(min_liquidity_adjusted_edge=0.005, min_directional_edge=0.02),
        created_ts=AS_OF_TS,
    )
    store = PointInTimeStore(tmp_path / "data")
    try:
        store.write_kalshi_paper_intents(intents)
        resolved = {
            "row_id": "resolved-1",
            "venue": "Kalshi",
            "market_id": "KXFED-26JUN-TARGET",
            "event_id": "KXFED-26JUN",
            "as_of_ts": AS_OF_TS - 3600,
            "resolved_ts": AS_OF_TS + 3600,
            "outcome": 1,
        }
        persist_rows(store, [resolved])
        artifacts = run_kalshi_research_cycle(
            store,
            app_config=mock_config,
            rank_report=rank_report,
            config=KalshiResearchCycleConfig(
                paper=KalshiPaperConfig(
                    min_liquidity_adjusted_edge=0.005,
                    min_directional_edge=0.02,
                    settle_existing=True,
                )
            ),
            reports_dir=tmp_path / "reports",
        )
        settled = store.load_kalshi_paper_intents(status="SETTLED")
    finally:
        store.close()

    assert artifacts.report["settlement"]["settled_count"] >= 1
    assert settled


def test_load_rank_report_and_outcomes_json(tmp_path):
    rank_path = tmp_path / "rank.json"
    outcomes_path = tmp_path / "outcomes.json"
    rank_payload = _rank_report()
    rank_path.write_text(json.dumps(rank_payload))
    outcomes_path.write_text(json.dumps({"outcomes": {"KXFED-26JUN-TARGET": 1}}))

    assert load_rank_report(rank_path)["run_id"] == rank_payload["run_id"]
    assert load_outcomes(outcomes_path) == {"KXFED-26JUN-TARGET": 1}


def test_research_cycle_replays_rank_report_and_supplied_outcomes(tmp_path, mock_config):
    rank_report = _rank_report()
    store = PointInTimeStore(tmp_path / "data")
    try:
        artifacts = run_kalshi_research_cycle(
            store,
            app_config=mock_config,
            rank_report=rank_report,
            outcomes={"KXFED-26JUN-TARGET": 1},
            config=KalshiResearchCycleConfig(
                paper=KalshiPaperConfig(
                    min_liquidity_adjusted_edge=0.005,
                    min_directional_edge=0.02,
                    settle_existing=True,
                )
            ),
            reports_dir=tmp_path / "reports",
        )
        settled = store.load_kalshi_paper_intents(status="SETTLED")
    finally:
        store.close()

    assert artifacts.report["live_rank_ref"]["run_id"] == rank_report["run_id"]
    assert artifacts.report["paper"]["intended_count"] == 1
    assert artifacts.report["settlement"]["settled_count"] == 1
    assert settled[0]["pnl_usd"] > 0


def test_research_cycle_does_not_duplicate_open_intents(tmp_path, mock_config):
    rank_report = _rank_report()
    store = PointInTimeStore(tmp_path / "data")
    try:
        first = run_kalshi_research_cycle(
            store,
            app_config=mock_config,
            rank_report=rank_report,
            config=KalshiResearchCycleConfig(
                paper=KalshiPaperConfig(
                    min_liquidity_adjusted_edge=0.005,
                    min_directional_edge=0.02,
                    settle_existing=False,
                )
            ),
            reports_dir=tmp_path / "reports",
        )
        second = run_kalshi_research_cycle(
            store,
            app_config=mock_config,
            rank_report=rank_report,
            config=KalshiResearchCycleConfig(
                paper=KalshiPaperConfig(
                    min_liquidity_adjusted_edge=0.005,
                    min_directional_edge=0.02,
                    settle_existing=False,
                )
            ),
            reports_dir=tmp_path / "reports",
        )
        open_intents = store.load_kalshi_paper_intents(status="PAPER_INTENDED")
    finally:
        store.close()

    assert first.report["paper"]["intended_count"] == 1
    assert second.report["paper"]["intended_count"] == 0
    assert second.report["paper"]["blocked"][0]["paper_blocking_reasons"] == ["paper_duplicate_open_intent"]
    assert second.report["paper"]["blocking_reason_counts"] == {"paper_duplicate_open_intent": 1}
    assert len(open_intents) == 1


def test_summarize_paper_ledger_reports_exposure_and_quality():
    intents, _ = build_paper_intents(
        _rank_report(),
        config=KalshiPaperConfig(min_liquidity_adjusted_edge=0.005, min_directional_edge=0.02),
        created_ts=AS_OF_TS,
    )
    settled = settle_paper_intents(
        intents,
        outcomes={"KXFED-26JUN-TARGET": 1},
        settled_ts=AS_OF_TS + 3600,
    )
    summary = summarize_paper_ledger([*intents, *settled])

    assert summary["status_counts"]["PAPER_INTENDED"] == 1
    assert summary["status_counts"]["SETTLED"] == 1
    assert summary["open_stake_usd"] > 0
    assert summary["settled_pnl_usd"] > 0
    assert summary["win_rate"] == 1.0
    assert summary["brier_score"] is not None
    assert summary["open_event_exposure_usd"]["KXFED-26JUN"] > 0


def test_stale_open_paper_intents_flags_intents_after_close_grace():
    stale = stale_open_paper_intents(
        [
            {
                "intent_id": "intent-1",
                "market_id": "KXFED-26JUN-TARGET",
                "event_id": "KXFED-26JUN",
                "side": "YES",
                "status": "PAPER_INTENDED",
                "stake_usd": 5.0,
                "as_of_ts": AS_OF_TS,
                "source_opportunity": {"time_to_close_hours": 1.0},
            }
        ],
        now_ts=AS_OF_TS + 26 * 3600,
        grace_hours=24.0,
    )

    assert len(stale) == 1
    assert stale[0]["market_id"] == "KXFED-26JUN-TARGET"
    assert stale[0]["hours_past_stale"] == 1.0


def test_research_cycle_report_includes_ledger_audit(tmp_path, mock_config):
    rank_report = _rank_report()
    store = PointInTimeStore(tmp_path / "data")
    try:
        artifacts = run_kalshi_research_cycle(
            store,
            app_config=mock_config,
            rank_report=rank_report,
            outcomes={"KXFED-26JUN-TARGET": 1},
            config=KalshiResearchCycleConfig(
                paper=KalshiPaperConfig(
                    min_liquidity_adjusted_edge=0.005,
                    min_directional_edge=0.02,
                    settle_existing=True,
                )
            ),
            reports_dir=tmp_path / "reports",
        )
    finally:
        store.close()

    ledger = artifacts.report["ledger"]
    assert ledger["settled_pnl_usd"] > 0
    assert ledger["brier_score"] is not None
    assert ledger["stale_open_count"] == 0
    assert artifacts.report["events"]["count"] == 2
    assert artifacts.report["events"]["status_counts"] == {"PAPER_INTENDED": 1, "SETTLED": 1}
    assert "## Ledger Audit" in artifacts.markdown_path.read_text()
    assert "## Stale Open Intents" in artifacts.markdown_path.read_text()
    assert "## Event History" in artifacts.markdown_path.read_text()
    assert "Paper blocking reasons" in artifacts.markdown_path.read_text()
    assert artifacts.report["promotion_readiness"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert len(artifacts.report["integrity"]["ledger_hash"]) == 64
    assert len(artifacts.report["integrity"]["paper_events_hash"]) == 64
    assert "## Integrity" in artifacts.markdown_path.read_text()


def test_paper_promotion_readiness_requires_enough_settled_evidence():
    readiness = paper_promotion_readiness(
        {
            "settled_count": 2,
            "brier_score": 0.05,
            "win_rate": 1.0,
            "settled_pnl_usd": 10.0,
        },
        KalshiPaperConfig(min_settled_for_promotion_review=30),
    )

    assert readiness["status"] == "INSUFFICIENT_EVIDENCE"
    assert "insufficient_settled_sample" in readiness["reasons"]


def test_paper_promotion_readiness_can_be_review_ready():
    readiness = paper_promotion_readiness(
        {
            "settled_count": 30,
            "brier_score": 0.12,
            "win_rate": 0.60,
            "settled_pnl_usd": 25.0,
        },
        KalshiPaperConfig(
            min_settled_for_promotion_review=30,
            max_brier_for_promotion_review=0.20,
            min_win_rate_for_promotion_review=0.55,
            min_pnl_for_promotion_review=0.0,
        ),
    )

    assert readiness["status"] == "REVIEW_READY"
    assert readiness["reasons"] == []


def test_paper_promotion_readiness_blocks_stale_open_intents():
    readiness = paper_promotion_readiness(
        {
            "settled_count": 30,
            "brier_score": 0.12,
            "win_rate": 0.60,
            "settled_pnl_usd": 25.0,
        },
        KalshiPaperConfig(
            min_settled_for_promotion_review=30,
            max_brier_for_promotion_review=0.20,
            min_win_rate_for_promotion_review=0.55,
            min_pnl_for_promotion_review=0.0,
        ),
        stale_open_count=1,
    )

    assert readiness["status"] == "INSUFFICIENT_EVIDENCE"
    assert readiness["reasons"] == ["stale_open_intents_present"]
    assert readiness["observed"]["stale_open_count"] == 1


def test_cycle_integrity_hashes_are_stable():
    rank_report = _rank_report()
    intents, blocked = build_paper_intents(
        rank_report,
        config=KalshiPaperConfig(min_liquidity_adjusted_edge=0.005, min_directional_edge=0.02),
        created_ts=AS_OF_TS,
    )
    config = KalshiResearchCycleConfig()
    left = cycle_integrity(
        rank_report=rank_report,
        paper_intents=intents,
        paper_blocked=blocked,
        settled=[],
        ledger=intents,
        config=config,
    )
    right = cycle_integrity(
        rank_report=rank_report,
        paper_intents=intents,
        paper_blocked=blocked,
        settled=[],
        ledger=intents,
        config=config,
    )

    assert left == right
    assert left["artifact_schema_version"] == 2
    assert len(left["rank_report_hash"]) == 64
    assert len(left["paper_events_hash"]) == 64


def test_stable_cycle_run_id_changes_with_settlement_state():
    rank_report = _rank_report()
    intents, blocked = build_paper_intents(
        rank_report,
        config=KalshiPaperConfig(min_liquidity_adjusted_edge=0.005, min_directional_edge=0.02),
        created_ts=AS_OF_TS,
    )
    settled = settle_paper_intents(
        intents,
        outcomes={"KXFED-26JUN-TARGET": 1},
        settled_ts=AS_OF_TS + 3600,
    )
    config = KalshiResearchCycleConfig()

    before = stable_cycle_run_id(rank_report, intents, blocked, [], config)
    after = stable_cycle_run_id(rank_report, intents, blocked, settled, config)

    assert before != after
