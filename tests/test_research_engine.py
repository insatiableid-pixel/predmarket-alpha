import time
from dataclasses import dataclass

import numpy as np

from predmarket.arbitrage import VenueQuote, detect_cross_venue_arbitrage
from predmarket.audit import AuditLogger
from predmarket.calibration import ConformalCalibrator
from predmarket.contracts import (
    EventSpec,
    ForecastContext,
    ForecastDistribution,
    ForecastRecord,
    SourceDocument,
)
from predmarket.events import CanonicalEventGraph
from predmarket.research import (
    PromotionGate,
    ResearchBacktestConfig,
    ResearchBacktester,
)
from predmarket.research_forecasters import (
    LLMEvidenceForecaster,
    LLMForecastOutput,
)
from predmarket.risk import RiskManager
from predmarket.store import PointInTimeStore


@dataclass
class DummySnapshot:
    venue: str = "Polymarket"
    contract_id: str = "MKT-1"
    title: str = "Will the event resolve yes?"
    bid: float = 0.48
    ask: float = 0.50
    mid: float = 0.49
    volume_24h: float = 100000.0
    open_interest: float = 200000.0
    line_history: tuple = (0.45, 0.47, 0.49)


def _rules(cutoff=1_900_000_000):
    return {
        "resolution_criteria": "official source reports yes",
        "cutoff_ts": cutoff,
        "oracle": "official",
        "payout_rule": "YES pays 1 if criteria met, otherwise 0",
    }


def test_point_in_time_store_excludes_future_documents(tmp_path):
    store = PointInTimeStore(tmp_path)
    now = time.time()
    old_doc = SourceDocument(
        source_id="old",
        source="test",
        title="Known before forecast",
        url="https://example.com/old",
        published_ts=now - 100,
        retrieved_ts=now - 90,
        text="old evidence",
    )
    future_doc = SourceDocument(
        source_id="future",
        source="test",
        title="Known after forecast",
        url="https://example.com/future",
        published_ts=now + 100,
        retrieved_ts=now + 101,
        text="future evidence",
    )
    store.write_source_document(old_doc)
    store.write_source_document(future_doc)

    context = store.load_context("EVT-1", "MKT-1", now)

    assert [doc.source_id for doc in context["source_documents"]] == ["old"]
    store.close()


def test_canonical_event_graph_rejects_mismatched_resolution_rules(tmp_path):
    store = PointInTimeStore(tmp_path)
    graph = CanonicalEventGraph(store)
    graph.upsert_event(
        EventSpec(
            event_id="EVT-1",
            title="Canonical event",
            category="political",
            resolution_rules=_rules(),
        )
    )
    graph.link_market("EVT-1", "Polymarket", "PM-1", _rules(), confidence=0.95)

    mismatched = _rules(cutoff=1_800_000_000)
    try:
        graph.link_market("EVT-1", "Kalshi", "KL-1", mismatched, confidence=0.95)
    except ValueError as exc:
        assert "rules do not match" in str(exc)
    else:
        raise AssertionError("mismatched rules should be rejected")

    assert graph.markets_are_equivalent("PM-1", "KL-1") is False
    store.close()


def test_forecast_quantiles_are_monotone_and_bounded():
    forecast = ForecastDistribution(
        p_mean=1.3,
        quantiles={0.9: 0.7, 0.1: 0.8, 0.5: -0.1},
        samples=[-0.5, 0.2, 1.5],
    )

    values = list(forecast.quantiles.values())
    assert forecast.p_mean == 1.0
    assert all(0.0 <= value <= 1.0 for value in values)
    assert values == sorted(values)
    assert forecast.samples == [0.0, 0.2, 1.0]


def test_density_samples_are_persisted_by_reference(tmp_path):
    store = PointInTimeStore(tmp_path)
    distribution = ForecastDistribution.from_samples(
        [0.25, 0.50, 0.75],
        method="unit",
        model_version="1",
    )
    record = ForecastRecord.from_distribution(
        event_id="EVT-1",
        market_id="MKT-1",
        as_of_ts=time.time(),
        horizon="1d",
        distribution=distribution,
    )

    store.write_density_samples(record.density_samples_ref, distribution.samples)

    assert store.load_density_samples(record.density_samples_ref) == [
        0.25,
        0.5,
        0.75,
    ]
    store.close()


def test_conformal_calibrator_returns_expected_interval():
    calibrator = ConformalCalibrator()
    for outcome in [0.55, 0.58, 0.62, 0.60]:
        calibrator.update("bucket", 0.60, outcome)

    lo, hi = calibrator.interval("bucket", 0.60, alpha=0.1)

    assert lo <= 0.55
    assert hi >= 0.62


def test_promotion_gate_can_promote_bucket_level_edge():
    rows = []
    for idx in range(20):
        outcome = float(idx % 2)
        rows.append(
            {
                "as_of_ts": idx,
                "p_model": 0.9 if outcome else 0.1,
                "p_baseline": 0.5,
                "outcome": outcome,
                "domain": "political",
                "horizon": "7d",
                "venue": "Polymarket",
                "liquidity_bucket": "liquid",
                "stake_fraction": 0.01,
                "market_implied": 0.5,
                "filled": 1.0,
            }
        )
    gate = PromotionGate(
        min_resolved_forecasts=5,
        max_ece=0.12,
        min_dsr=0.0,
        max_pbo=0.99,
    )
    report = ResearchBacktester(promotion_gate=gate).run_experiment(
        ResearchBacktestConfig(name="unit", min_train_size=5, test_size=5),
        rows=rows,
    )

    assert report.promotion.status == "PROMOTED"
    assert report.metrics["brier"] < report.metrics["baseline_brier"]


def test_execution_aware_sizing_accounts_for_costs_and_promotion(mock_config, test_data_dir):
    risk = RiskManager(mock_config, AuditLogger(str(test_data_dir)))
    density = ForecastDistribution.from_samples(
        [0.70] * 50,
        method="unit",
        model_version="1",
    )
    promoted = {
        "contract_id": "MKT-1",
        "title": "Promoted event",
        "category": "political",
        "event_id": "EVT-1",
        "model_prob": 0.70,
        "market_implied": 0.50,
        "density_forecast": type("Density", (), {"samples": np.asarray(density.samples)})(),
        "fees": 0.02,
        "slippage": 0.01,
        "fill_probability": 0.5,
        "capital_lockup_days": 4.0,
        "status": "READY",
        "promotion_status": "PROMOTED",
        "base_rate_reference": "",
        "base_rate_prob": 0.5,
    }
    research_only = {**promoted, "contract_id": "MKT-2", "promotion_status": "RESEARCH_ONLY"}

    slate = risk.optimize_execution_aware([promoted, research_only], cash_balance=10_000)

    assert slate[0]["execution_assumptions"]["fees"] == 0.02
    assert slate[0]["net_edge"] < slate[0]["posterior_edge"]
    assert slate[1]["recommended_fraction"] == 0.0
    assert slate[1]["status"] == "RESEARCH-ONLY"


def test_cross_venue_arbitrage_requires_fees_and_semantic_confidence():
    quotes = [
        VenueQuote(
            "Polymarket", "PM-1", bid=0.40, ask=0.45, yes_fee=0.01, semantic_confidence=0.95
        ),
        VenueQuote(
            "Kalshi", "KL-1", bid=0.44, ask=0.80, no_ask=0.48, no_fee=0.01, semantic_confidence=0.95
        ),
        VenueQuote("Manifold", "MF-1", bid=0.30, ask=0.40, no_fee=0.01, semantic_confidence=0.40),
    ]

    opportunities = detect_cross_venue_arbitrage("EVT-1", quotes, min_net_edge=0.01)

    assert len(opportunities) == 1
    assert abs(opportunities[0].net_edge - 0.05) < 1e-9
    assert opportunities[0].long_no.venue == "Kalshi"


def _forecast_context_with_doc():
    now = time.time()
    return ForecastContext(
        event_id="EVT-1",
        market_id="MKT-1",
        as_of_ts=now,
        category="political",
        snapshot=DummySnapshot(),
        market_history=[0.45, 0.47, 0.49],
        source_documents=[
            SourceDocument(
                source_id="doc-1",
                source="test",
                title="Agreement reached on bill",
                url="https://example.com/doc-1",
                published_ts=now - 60,
                retrieved_ts=now - 30,
                text="Leaders say an agreement makes passage more likely.",
            )
        ],
        features={"bid_ask_spread": 0.02},
    )


def test_llm_forecaster_disabled_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    forecaster = LLMEvidenceForecaster()

    forecast = forecaster.forecast(_forecast_context_with_doc())

    assert forecast.p_mean == 0.5
    assert "LLM_DISABLED" in forecast.status_flags
    assert "RESEARCH_ONLY" in forecast.status_flags


def test_llm_forecaster_uses_structured_openai_client(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class FakeResponses:
        def __init__(self):
            self.calls = []

        def parse(self, **kwargs):
            self.calls.append(kwargs)
            assert kwargs["text_format"] is LLMForecastOutput
            return type(
                "Response",
                (),
                {
                    "output_parsed": LLMForecastOutput(
                        probability=0.64,
                        confidence=0.70,
                        uncertainty=0.25,
                        base_rate_anchor=0.28,
                        market_price_anchor=0.49,
                        reasoning="Base rate is low, but cited evidence improves odds.",
                        key_factors=["agreement"],
                        downside_factors=["resolution uncertainty"],
                        cruxes=["whether the compromise holds"],
                        citations=["doc-1"],
                    )
                },
            )()

    class FakeClient:
        def __init__(self):
            self.responses = FakeResponses()

    client = FakeClient()
    forecaster = LLMEvidenceForecaster(client=client, model="gpt-test")

    forecast = forecaster.forecast(_forecast_context_with_doc())

    assert client.responses.calls[0]["model"] == "gpt-test"
    assert "LLM_API" in forecast.status_flags
    assert "RESEARCH_ONLY" in forecast.status_flags
    assert forecast.evidence_refs == ["doc-1"]
    assert 0.45 < forecast.p_mean < 0.80
    assert forecast.reasoning.startswith("Base rate")
