import random

import pytest

from predmarket.discovery import (
    AgenticDiscoveryConfig,
    AgenticSignalDiscoveryEngine,
    DSLValidationError,
    EvolutionAgent,
    PUCTSearch,
    RankingAgent,
    ReflectionAgent,
    SafeSignalDSL,
    SignalHypothesis,
)
from predmarket.discovery.agents import stable_hypothesis_id
from predmarket.discovery.contracts import DiscoveryArtifact, DiscoveryTransition, TrajectoryReport
from predmarket.research import PromotionGate
from predmarket.store import PointInTimeStore


def _hyp(expression, focus="unit", prior=0.5, parent_ids=None):
    return SignalHypothesis(
        hypothesis_id=stable_hypothesis_id(expression, focus, parent_ids or []),
        name=f"{focus}-hyp",
        expression=expression,
        rationale="unit test",
        focus=focus,
        prior=prior,
        parent_ids=parent_ids or [],
    )


def test_safe_dsl_evaluates_allowed_transforms_and_blocks_leakage():
    rows = [
        {"as_of_ts": 1.0, "edge": 0.1, "market_implied": 0.5, "outcome": 1},
        {"as_of_ts": 2.0, "edge": -0.2, "market_implied": 0.5, "outcome": 0},
        {"as_of_ts": 3.0, "edge": 0.3, "market_implied": 0.5, "outcome": 1},
    ]
    dsl = SafeSignalDSL(["edge", "market_implied"])

    values = dsl.evaluate("clip(market_implied + 0.1 * zscore(edge), 0.01, 0.99)", rows)

    assert len(values) == 3
    assert all(0.01 <= value <= 0.99 for value in values)
    with pytest.raises(DSLValidationError):
        dsl.evaluate("outcome", rows)
    with pytest.raises(DSLValidationError):
        dsl.evaluate("__import__(1)", rows)


def test_safe_dsl_blocks_features_not_available_at_as_of_ts():
    rows = [{"as_of_ts": 1.0, "signal": 0.7, "signal_available_ts": 2.0}]
    dsl = SafeSignalDSL(["signal"])

    with pytest.raises(DSLValidationError):
        dsl.evaluate("signal", rows)


def test_puct_selection_explores_after_exploitation_and_is_seeded():
    high = _hyp("clip(edge, 0.01, 0.99)", prior=0.9)
    low = _hyp("rank(edge)", prior=0.1)
    puct = PUCTSearch(puct_c=1.5, random_seed=123)
    puct.add_arm(high, "traj-1")
    puct.add_arm(low, "traj-1")

    assert puct.select_arm().hypothesis_id == high.hypothesis_id
    for _ in range(10):
        puct.update(high.hypothesis_id, reward=0.0)

    assert puct.select_arm().hypothesis_id == low.hypothesis_id

    a = _hyp("clip(a, 0.01, 0.99)", prior=0.5)
    b = _hyp("clip(b, 0.01, 0.99)", prior=0.5)
    first = PUCTSearch(random_seed=7)
    second = PUCTSearch(random_seed=7)
    for search in (first, second):
        search.add_arm(a, "traj-1")
        search.add_arm(b, "traj-1")

    assert first.select_arm().hypothesis_id == second.select_arm().hypothesis_id


def test_reflection_rejects_duplicate_leaky_unsupported_and_complex_hypotheses():
    rows = [
        {"as_of_ts": 1.0, "edge": 0.1, "outcome": 1},
        {"as_of_ts": 2.0, "edge": 0.2, "outcome": 0},
        {"as_of_ts": 3.0, "edge": 0.3, "outcome": 1},
    ]
    dsl = SafeSignalDSL(["edge"])
    agent = ReflectionAgent(dsl, AgenticDiscoveryConfig(min_support=2, max_complexity=12))
    seen = set()
    accepted = agent.reflect(_hyp("rank(edge)"), rows, seen)
    duplicate = agent.reflect(_hyp("rank(edge)"), rows, seen)

    assert accepted.accepted is True
    assert duplicate.accepted is False
    assert "duplicate_expression" in duplicate.reasons

    leaky = agent.reflect(_hyp("outcome"), rows, set())
    assert any(reason.startswith("dsl_validation:forbidden feature") for reason in leaky.reasons)

    unsupported = ReflectionAgent(
        dsl, AgenticDiscoveryConfig(min_support=4)
    ).reflect(_hyp("rank(edge)"), rows, set())
    assert "insufficient_sample_support" in unsupported.reasons

    complex_expr = "edge + edge + edge + edge + edge + edge + edge"
    complex_result = agent.reflect(_hyp(complex_expr), rows, set())
    assert "complexity_exceeds_limit" in complex_result.reasons


def test_elo_ranking_orders_higher_reward_candidates_first():
    ratings = RankingAgent.compute_elo({"best": 0.8, "mid": 0.3, "worst": -0.1})

    assert ratings["best"] > ratings["mid"] > ratings["worst"]


def test_evolution_preserves_parent_provenance_and_transition_records():
    dsl = SafeSignalDSL(["edge", "volume"])
    agent = EvolutionAgent(dsl, random.Random(3), AgenticDiscoveryConfig())
    parent_a = _hyp("clip(edge, 0.01, 0.99)", focus="market")
    parent_b = _hyp("rank(volume)", focus="market")

    children, transitions = agent.evolve(
        "run-1", "traj-1", "market", [parent_a, parent_b], ["edge", "volume"], limit=3
    )

    assert children
    assert all(child.parent_ids for child in children)
    assert transitions
    assert transitions[0].from_hypothesis_ids == [parent_a.hypothesis_id]
    assert transitions[0].to_hypothesis_id == children[0].hypothesis_id


def test_discovery_ledger_persists_and_reloads(tmp_path):
    store = PointInTimeStore(tmp_path)
    artifact = DiscoveryArtifact(
        artifact_id="artifact-1",
        run_id="run-1",
        trajectory_id="traj-1",
        artifact_type="hypothesis",
        payload={"x": 1},
        status="REJECTED",
        reasons=["duplicate"],
        parent_ids=["parent-1"],
    )
    transition = DiscoveryTransition(
        transition_id="trans-1",
        run_id="run-1",
        trajectory_id="traj-1",
        from_hypothesis_ids=["parent-1"],
        to_hypothesis_id="child-1",
        transition_type="mutation",
        reason="unit",
        accepted=True,
    )
    summary = TrajectoryReport(
        trajectory_id="traj-1",
        focus="unit",
        seed=1,
        hypotheses_tested=1,
        accepted_ids=[],
        rejected_ids=["artifact-1"],
        top_hypothesis_ids=[],
        summary="unit",
    )

    store.write_discovery_run("run-1", {"config": 1}, {"created_ts": 1.0}, "RESEARCH_ONLY")
    store.write_discovery_artifact(artifact)
    store.write_discovery_transition(transition)
    store.write_discovery_trajectory_summary("run-1", summary)

    assert store.load_discovery_run("run-1")["status"] == "RESEARCH_ONLY"
    assert store.load_discovery_artifacts("run-1", status="REJECTED")[0]["reasons"] == ["duplicate"]
    assert store.load_discovery_edges("run-1")
    assert store.load_discovery_transitions("run-1")[0]["accepted"] is True
    assert store.load_discovery_trajectory_summaries("run-1")[0]["focus"] == "unit"
    store.close()


def test_agentic_discovery_finds_known_synthetic_signal_and_stays_research_only_by_default(tmp_path):
    rows = []
    for idx in range(80):
        outcome = float(idx % 2 == 0)
        known_signal = 0.85 if outcome else 0.15
        rows.append(
            {
                "event_id": f"EVT-{idx}",
                "market_id": f"MKT-{idx}",
                "as_of_ts": float(idx),
                "known_signal": known_signal,
                "p_baseline": 0.5,
                "market_implied": 0.5,
                "bid_ask_spread": 0.02 + 0.001 * (idx % 5),
                "volume_24h": 1000.0 + idx,
                "outcome": outcome,
                "domain": "synthetic",
                "horizon": "7d",
                "venue": "unit",
                "liquidity_bucket": "liquid",
            }
        )
    store = PointInTimeStore(tmp_path)
    engine = AgenticSignalDiscoveryEngine(store=store)

    report = engine.run(
        AgenticDiscoveryConfig(
            n_trajectories=2,
            iterations_per_trajectory=10,
            top_k=5,
            min_support=20,
            evolution_interval=5,
        ),
        rows,
        feature_catalog=["known_signal", "p_baseline", "market_implied", "bid_ask_spread", "volume_24h"],
    )

    assert report.top_hypotheses
    assert "known_signal" in report.top_hypotheses[0]["hypothesis"]["expression"]
    assert report.top_hypotheses[0]["metrics"]["brier"] < report.top_hypotheses[0]["metrics"]["baseline_brier"]
    assert report.promotion_decisions[report.top_hypotheses[0]["hypothesis"]["hypothesis_id"]]["status"] == "RESEARCH_ONLY"
    assert report.accepted_transitions
    assert store.load_discovery_run(report.run_id) is not None
    assert store.load_discovery_artifacts(report.run_id)
    queued = engine.experiment_queue.list()
    assert queued
    assert all(row["status"] == "RESEARCH_ONLY" for row in queued if "hypothesis" in row)
    store.close()


def test_agentic_discovery_can_record_promoted_when_gate_allows_it(tmp_path):
    rows = []
    for idx in range(40):
        outcome = float(idx % 2 == 0)
        rows.append(
            {
                "event_id": f"EVT-{idx}",
                "market_id": f"MKT-{idx}",
                "as_of_ts": float(idx),
                "known_signal": 0.9 if outcome else 0.1,
                "p_baseline": 0.5,
                "market_implied": 0.5,
                "outcome": outcome,
            }
        )
    gate = PromotionGate(
        min_resolved_forecasts=20,
        max_ece=0.20,
        min_dsr=0.0,
        max_pbo=1.01,
        max_major_bucket_brier_underperformance=1.0,
    )
    store = PointInTimeStore(tmp_path)
    engine = AgenticSignalDiscoveryEngine(store=store, promotion_gate=gate)

    report = engine.run(
        AgenticDiscoveryConfig(
            n_trajectories=1,
            iterations_per_trajectory=4,
            top_k=1,
            min_support=10,
            evolution_interval=0,
        ),
        rows,
        feature_catalog=["known_signal", "p_baseline", "market_implied"],
    )

    top_id = report.top_hypotheses[0]["hypothesis"]["hypothesis_id"]
    assert report.promotion_decisions[top_id]["status"] == "PROMOTED"
    assert engine.experiment_queue.list()[0]["status"] == "PROMOTED"
    store.close()
