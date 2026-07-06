"""Agentic signal discovery engine."""

from __future__ import annotations

import hashlib
import json
import random
import time
from collections.abc import Iterable, Sequence
from typing import Any

from predmarket.discovery.agents import (
    EvolutionAgent,
    HypothesisAgent,
    RankingAgent,
    ReflectionAgent,
)
from predmarket.discovery.contracts import (
    AgenticDiscoveryConfig,
    CandidateEvaluation,
    DiscoveryArtifact,
    DiscoveryRunReport,
    DiscoveryTransition,
    SignalHypothesis,
    TrajectoryReport,
)
from predmarket.discovery.dsl import SafeSignalDSL
from predmarket.discovery.puct import PUCTSearch
from predmarket.experiments import ExperimentProposal, ExperimentQueue
from predmarket.research import PromotionGate, ResearchBacktester

TRAJECTORY_FOCI = [
    "market_microstructure",
    "semantic_event_identity",
    "news_latency",
    "macro_base_rate",
    "execution_cost",
]


class AgenticSignalDiscoveryEngine:
    """Run deterministic, research-only signal discovery over resolved rows."""

    def __init__(
        self,
        store: Any = None,
        backtester: ResearchBacktester | None = None,
        promotion_gate: PromotionGate | None = None,
        experiment_queue: ExperimentQueue | None = None,
    ):
        self.store = store
        self.promotion_gate = promotion_gate or PromotionGate()
        self.backtester = backtester or ResearchBacktester(
            store=store, promotion_gate=self.promotion_gate
        )
        if experiment_queue is not None:
            self.experiment_queue = experiment_queue
        elif store is not None and hasattr(store, "data_dir"):
            self.experiment_queue = ExperimentQueue(store.data_dir)
        else:
            self.experiment_queue = None

    def run(
        self,
        config: AgenticDiscoveryConfig | None,
        rows: Sequence[dict[str, Any]],
        feature_catalog: Iterable[str] | None = None,
    ) -> DiscoveryRunReport:
        config = config or AgenticDiscoveryConfig()
        ordered_rows = sorted(
            [dict(row) for row in rows], key=lambda row: float(row.get("as_of_ts", 0.0))
        )
        features = sorted(
            set(feature_catalog or SafeSignalDSL.discover_feature_catalog(ordered_rows))
        )
        dsl = SafeSignalDSL(features)
        run_id = self._run_id(config, ordered_rows, features)

        all_artifacts: list[DiscoveryArtifact] = []
        all_evaluations: dict[str, CandidateEvaluation] = {}
        all_rejections: list[dict[str, Any]] = []
        all_puct_rows: list[dict[str, Any]] = []
        accepted_transitions: list[DiscoveryTransition] = []
        trajectory_reports: list[TrajectoryReport] = []
        occurrence_by_expression: dict[str, set[str]] = {}

        for trajectory_idx in range(config.n_trajectories):
            focus = TRAJECTORY_FOCI[trajectory_idx % len(TRAJECTORY_FOCI)]
            trajectory_id = f"traj-{trajectory_idx + 1}"
            seed = config.random_seed + trajectory_idx
            rng = random.Random(seed)
            hypothesis_agent = HypothesisAgent(dsl, rng)
            reflection_agent = ReflectionAgent(dsl, config)
            ranking_agent = RankingAgent(dsl, self.backtester, config)
            evolution_agent = EvolutionAgent(dsl, rng, config)
            puct = PUCTSearch(config.puct_c, seed)
            seen_canonicals: set[str] = set()
            accepted_ids: list[str] = []
            rejected_ids: list[str] = []
            evaluations: dict[str, CandidateEvaluation] = {}
            accepted_hypotheses: dict[str, SignalHypothesis] = {}
            trajectory_artifacts: list[DiscoveryArtifact] = []

            proposals = hypothesis_agent.propose(
                focus,
                features,
                ordered_rows,
                limit=max(config.iterations_per_trajectory * 2, config.top_k * 4, 12),
            )
            for hypothesis in proposals:
                self._reflect_and_record(
                    run_id,
                    trajectory_id,
                    hypothesis,
                    ordered_rows,
                    seen_canonicals,
                    reflection_agent,
                    puct,
                    accepted_ids,
                    rejected_ids,
                    accepted_hypotheses,
                    trajectory_artifacts,
                    all_rejections,
                )

            for iteration in range(config.iterations_per_trajectory):
                selected = puct.select_arm()
                if selected is None:
                    break
                if selected.hypothesis_id not in evaluations:
                    evaluation = ranking_agent.evaluate(
                        selected, ordered_rows, n_trials=max(len(evaluations) + 1, 1)
                    )
                    evaluations[selected.hypothesis_id] = evaluation
                    all_evaluations[selected.hypothesis_id] = evaluation
                    puct.update(selected.hypothesis_id, evaluation.reward)
                    eval_artifact = self._artifact(
                        run_id,
                        trajectory_id,
                        "evaluation",
                        {
                            "hypothesis": selected.to_dict(),
                            "metrics": evaluation.metrics,
                            "reward": evaluation.reward,
                            "promotion": evaluation.promotion,
                        },
                        status=evaluation.promotion.get("status", "RESEARCH_ONLY"),
                        parent_ids=[selected.hypothesis_id],
                    )
                    trajectory_artifacts.append(eval_artifact)
                    self._persist_artifact(eval_artifact)
                    try:
                        canonical = dsl.canonicalize(selected.expression)
                        occurrence_by_expression.setdefault(canonical, set()).add(trajectory_id)
                    except Exception:
                        pass
                else:
                    puct.update(selected.hypothesis_id, evaluations[selected.hypothesis_id].reward)

                should_evolve = (
                    config.evolution_interval > 0
                    and (iteration + 1) % config.evolution_interval == 0
                    and evaluations
                )
                if should_evolve:
                    ranked = self._ranked_evaluations(evaluations)
                    top_parents = [evaluation.hypothesis for evaluation in ranked[:3]]
                    children, transitions = evolution_agent.evolve(
                        run_id,
                        trajectory_id,
                        focus,
                        top_parents,
                        features,
                        limit=4,
                    )
                    for child, transition in zip(children, transitions):
                        result = self._reflect_and_record(
                            run_id,
                            trajectory_id,
                            child,
                            ordered_rows,
                            seen_canonicals,
                            reflection_agent,
                            puct,
                            accepted_ids,
                            rejected_ids,
                            accepted_hypotheses,
                            trajectory_artifacts,
                            all_rejections,
                        )
                        transition.accepted = result
                        accepted_transitions.append(transition)
                        self._persist_transition(transition)
                        transition_artifact = self._artifact(
                            run_id,
                            trajectory_id,
                            "transition",
                            transition.to_dict(),
                            status="ACCEPTED" if result else "REJECTED",
                            parent_ids=transition.from_hypothesis_ids,
                        )
                        trajectory_artifacts.append(transition_artifact)
                        self._persist_artifact(transition_artifact)

            ranked = self._ranked_evaluations(evaluations)
            summary = TrajectoryReport(
                trajectory_id=trajectory_id,
                focus=focus,
                seed=seed,
                hypotheses_tested=len(evaluations),
                accepted_ids=accepted_ids,
                rejected_ids=rejected_ids,
                top_hypothesis_ids=[
                    evaluation.hypothesis.hypothesis_id for evaluation in ranked[: config.top_k]
                ],
                summary=(
                    f"{focus} tested {len(evaluations)} candidates; "
                    f"accepted {len(accepted_ids)} and rejected {len(rejected_ids)}."
                ),
                artifacts=trajectory_artifacts,
            )
            trajectory_reports.append(summary)
            self._persist_trajectory_summary(run_id, summary)
            all_artifacts.extend(trajectory_artifacts)
            all_puct_rows.extend(puct.table())

        ranked_all = self._ranked_evaluations(all_evaluations)
        queued_ids = self._submit_top_candidates(run_id, ranked_all[: config.top_k])
        promotion_decisions = {
            evaluation.hypothesis.hypothesis_id: evaluation.promotion
            for evaluation in ranked_all[: config.top_k]
        }
        robust_ids = self._robust_ids(ranked_all, occurrence_by_expression, dsl)
        report = DiscoveryRunReport(
            run_id=run_id,
            config=config.to_dict(),
            created_ts=time.time(),
            top_hypotheses=[evaluation.to_dict() for evaluation in ranked_all[: config.top_k]],
            rejected_contrasts=all_rejections[: config.top_k],
            puct_table=all_puct_rows,
            trajectory_summaries=[summary.to_dict() for summary in trajectory_reports],
            accepted_transitions=[
                transition.to_dict() for transition in accepted_transitions if transition.accepted
            ],
            promotion_decisions=promotion_decisions,
            robust_hypothesis_ids=robust_ids,
            queued_proposal_ids=queued_ids,
            artifacts=[artifact.to_dict() for artifact in all_artifacts],
        )
        self._persist_run(run_id, config, report)
        return report

    def _reflect_and_record(
        self,
        run_id: str,
        trajectory_id: str,
        hypothesis: SignalHypothesis,
        rows: Sequence[dict[str, Any]],
        seen_canonicals: set[str],
        reflection_agent: ReflectionAgent,
        puct: PUCTSearch,
        accepted_ids: list[str],
        rejected_ids: list[str],
        accepted_hypotheses: dict[str, SignalHypothesis],
        trajectory_artifacts: list[DiscoveryArtifact],
        all_rejections: list[dict[str, Any]],
    ) -> bool:
        result = reflection_agent.reflect(hypothesis, rows, seen_canonicals)
        status = "ACCEPTED" if result.accepted else "REJECTED"
        artifact = self._artifact(
            run_id,
            trajectory_id,
            "hypothesis",
            hypothesis.to_dict(),
            status=status,
            reasons=result.reasons,
            parent_ids=hypothesis.parent_ids,
        )
        trajectory_artifacts.append(artifact)
        self._persist_artifact(artifact)
        if result.accepted:
            accepted_ids.append(hypothesis.hypothesis_id)
            accepted_hypotheses[hypothesis.hypothesis_id] = hypothesis
            puct.add_arm(hypothesis, trajectory_id=trajectory_id, status="UNEVALUATED")
        else:
            rejected_ids.append(hypothesis.hypothesis_id)
            puct.mark_rejected(hypothesis, trajectory_id, result.reasons)
            all_rejections.append(
                {
                    "hypothesis": hypothesis.to_dict(),
                    "trajectory_id": trajectory_id,
                    "reasons": result.reasons,
                }
            )
        return result.accepted

    def _submit_top_candidates(
        self, run_id: str, evaluations: Sequence[CandidateEvaluation]
    ) -> list[str]:
        if self.experiment_queue is None:
            return []
        proposal_ids: list[str] = []
        for evaluation in evaluations:
            status = evaluation.promotion.get("status", "RESEARCH_ONLY")
            proposal = ExperimentProposal(
                name=evaluation.hypothesis.name,
                hypothesis=evaluation.hypothesis.rationale,
                patch_ref=f"discovery:{run_id}:{evaluation.hypothesis.hypothesis_id}",
                experiment_config={
                    "discovery_run_id": run_id,
                    "hypothesis": evaluation.hypothesis.to_dict(),
                    "metrics": evaluation.metrics,
                    "reward": evaluation.reward,
                },
                proposer="agentic_discovery",
                status=status,
                reason_code="DISCOVERY_PROMOTED" if status == "PROMOTED" else "RESEARCH_ONLY",
            )
            proposal_ids.append(self.experiment_queue.submit(proposal))
        return proposal_ids

    @staticmethod
    def _ranked_evaluations(
        evaluations: dict[str, CandidateEvaluation],
    ) -> list[CandidateEvaluation]:
        if not evaluations:
            return []
        elo = RankingAgent.compute_elo(
            {hypothesis_id: evaluation.reward for hypothesis_id, evaluation in evaluations.items()}
        )
        for hypothesis_id, rating in elo.items():
            evaluations[hypothesis_id].elo = rating
        return sorted(
            evaluations.values(),
            key=lambda evaluation: (
                -evaluation.reward,
                -evaluation.elo,
                evaluation.hypothesis.complexity,
                evaluation.hypothesis.hypothesis_id,
            ),
        )

    @staticmethod
    def _robust_ids(
        evaluations: Sequence[CandidateEvaluation],
        occurrence_by_expression: dict[str, set[str]],
        dsl: SafeSignalDSL,
    ) -> list[str]:
        robust: list[str] = []
        for evaluation in evaluations:
            try:
                canonical = dsl.canonicalize(evaluation.hypothesis.expression)
            except Exception:
                continue
            if (
                len(occurrence_by_expression.get(canonical, set())) >= 2
                and evaluation.promotion.get("status") == "PROMOTED"
            ):
                robust.append(evaluation.hypothesis.hypothesis_id)
        return robust

    @staticmethod
    def _artifact(
        run_id: str,
        trajectory_id: str,
        artifact_type: str,
        payload: dict[str, Any],
        status: str = "RECORDED",
        reasons: list[str] | None = None,
        parent_ids: list[str] | None = None,
    ) -> DiscoveryArtifact:
        base = json.dumps(
            {
                "run_id": run_id,
                "trajectory_id": trajectory_id,
                "artifact_type": artifact_type,
                "payload": payload,
                "status": status,
            },
            sort_keys=True,
            default=str,
        )
        artifact_id = "artifact-" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
        return DiscoveryArtifact(
            artifact_id=artifact_id,
            run_id=run_id,
            trajectory_id=trajectory_id,
            artifact_type=artifact_type,
            payload=payload,
            status=status,
            reasons=list(reasons or []),
            parent_ids=list(parent_ids or []),
        )

    @staticmethod
    def _run_id(
        config: AgenticDiscoveryConfig,
        rows: Sequence[dict[str, Any]],
        feature_catalog: Sequence[str],
    ) -> str:
        row_fingerprint = [
            {
                "as_of_ts": row.get("as_of_ts"),
                "market_id": row.get("market_id"),
                "event_id": row.get("event_id"),
            }
            for row in rows[:20]
        ]
        payload = json.dumps(
            {
                "config": config.to_dict(),
                "n_rows": len(rows),
                "features": list(feature_catalog),
                "rows": row_fingerprint,
            },
            sort_keys=True,
            default=str,
        )
        return "discovery-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _persist_run(
        self,
        run_id: str,
        config: AgenticDiscoveryConfig,
        report: DiscoveryRunReport,
    ) -> None:
        if self.store is not None and hasattr(self.store, "write_discovery_run"):
            self.store.write_discovery_run(
                run_id=run_id,
                config=config.to_dict(),
                report=report.to_dict(),
                status="RESEARCH_ONLY" if config.research_only else "RECORDED",
            )

    def _persist_artifact(self, artifact: DiscoveryArtifact) -> None:
        if self.store is not None and hasattr(self.store, "write_discovery_artifact"):
            self.store.write_discovery_artifact(artifact)

    def _persist_transition(self, transition: DiscoveryTransition) -> None:
        if self.store is not None and hasattr(self.store, "write_discovery_transition"):
            self.store.write_discovery_transition(transition)

    def _persist_trajectory_summary(self, run_id: str, summary: TrajectoryReport) -> None:
        if self.store is not None and hasattr(self.store, "write_discovery_trajectory_summary"):
            self.store.write_discovery_trajectory_summary(run_id, summary)
