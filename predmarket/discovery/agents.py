"""Deterministic local agents for signal discovery."""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from typing import Any

import numpy as np

from predmarket.discovery.contracts import (
    AgenticDiscoveryConfig,
    CandidateEvaluation,
    DiscoveryTransition,
    ReflectionResult,
    SignalHypothesis,
)
from predmarket.discovery.dsl import DSLValidationError, SafeSignalDSL
from predmarket.research import (
    ResearchBacktestConfig,
    ResearchBacktester,
)

FOCUS_PRIORS = {
    "market_microstructure": (
        "market",
        "mid",
        "price",
        "spread",
        "volume",
        "interest",
        "momentum",
        "volatility",
        "liquidity",
    ),
    "semantic_event_identity": (
        "headline",
        "semantic",
        "event",
        "source",
        "doc",
        "category",
        "cat_",
        "identity",
    ),
    "news_latency": (
        "headline",
        "news",
        "source",
        "doc",
        "latency",
        "recency",
        "retrieved",
    ),
    "macro_base_rate": (
        "base",
        "rate",
        "cpi",
        "fed",
        "unemployment",
        "gdp",
        "day",
        "quarter",
        "expiry",
    ),
    "execution_cost": (
        "fee",
        "fees",
        "slippage",
        "fill",
        "spread",
        "liquidity",
        "volume",
        "cost",
    ),
}


def stable_hypothesis_id(expression: str, focus: str, parent_ids: Iterable[str] = ()) -> str:
    payload = "|".join([focus, expression, *sorted(parent_ids)])
    return "hyp-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def stable_transition_id(
    run_id: str,
    trajectory_id: str,
    from_ids: Iterable[str],
    to_id: str,
    transition_type: str,
) -> str:
    payload = "|".join([run_id, trajectory_id, transition_type, to_id, *sorted(from_ids)])
    return "trans-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class HypothesisAgent:
    """Generate candidate alpha expressions from available point-in-time features."""

    def __init__(self, dsl: SafeSignalDSL, rng: random.Random):
        self.dsl = dsl
        self.rng = rng

    def propose(
        self,
        focus: str,
        feature_catalog: Sequence[str],
        rows: Sequence[dict[str, Any]],
        limit: int,
    ) -> list[SignalHypothesis]:
        del rows
        ordered = self._ordered_features(focus, feature_catalog)
        expressions: list[tuple[str, str, float]] = []
        baseline = "p_baseline" if "p_baseline" in feature_catalog else None
        if baseline is None and "market_implied" in feature_catalog:
            baseline = "market_implied"

        for feature in ordered:
            expressions.append(
                (
                    f"clip({feature}, 0.01, 0.99)",
                    f"Direct bounded probability read from {feature}.",
                    self._prior_for(focus, feature, base=0.66),
                )
            )
            anchor = baseline or "0.5"
            expressions.append(
                (
                    f"clip({anchor} + 0.15 * zscore({feature}), 0.01, 0.99)",
                    f"Standardized {feature} tilt around the market/base-rate anchor.",
                    self._prior_for(focus, feature, base=0.58),
                )
            )
            expressions.append(
                (
                    f"rank({feature})",
                    f"Cross-sectional rank transform for {feature}.",
                    self._prior_for(focus, feature, base=0.48),
                )
            )
            expressions.append(
                (
                    f"clip(0.5 + 0.20 * momentum({feature}, 1), 0.01, 0.99)",
                    f"One-step momentum transition in {feature}.",
                    self._prior_for(focus, feature, base=0.42),
                )
            )

        for left, right in self._feature_pairs(ordered[:8]):
            expressions.append(
                (
                    f"clip(0.5 + 0.10 * zscore(interaction({left}, {right})), 0.01, 0.99)",
                    f"Pairwise regime interaction between {left} and {right}.",
                    min(self._prior_for(focus, left, 0.44), self._prior_for(focus, right, 0.44)),
                )
            )

        hypotheses: list[SignalHypothesis] = []
        seen: set[str] = set()
        for expression, rationale, prior in expressions:
            if expression in seen:
                continue
            seen.add(expression)
            try:
                complexity = self.dsl.complexity(expression)
            except DSLValidationError:
                complexity = 999
            hypotheses.append(
                SignalHypothesis(
                    hypothesis_id=stable_hypothesis_id(expression, focus),
                    name=f"{focus}:{len(hypotheses) + 1}",
                    expression=expression,
                    rationale=rationale,
                    focus=focus,
                    prior=prior,
                    complexity=complexity,
                    metadata={"agent": "hypothesis"},
                )
            )
            if len(hypotheses) >= limit:
                break
        return hypotheses

    def _ordered_features(self, focus: str, feature_catalog: Sequence[str]) -> list[str]:
        keywords = FOCUS_PRIORS.get(focus, ())
        scored = []
        for feature in feature_catalog:
            lowered = feature.lower()
            focus_hit = any(keyword in lowered for keyword in keywords)
            score = (1 if focus_hit else 0, -len(feature), feature)
            scored.append((score, feature))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [feature for _, feature in scored]

    def _prior_for(self, focus: str, feature: str, base: float) -> float:
        lowered = feature.lower()
        boost = 0.20 if any(token in lowered for token in FOCUS_PRIORS.get(focus, ())) else 0.0
        jitter = self.rng.uniform(-0.015, 0.015)
        return float(np.clip(base + boost + jitter, 0.05, 0.98))

    @staticmethod
    def _feature_pairs(features: Sequence[str]) -> list[tuple[str, str]]:
        pairs = []
        for idx, left in enumerate(features):
            for right in features[idx + 1 :]:
                pairs.append((left, right))
        return pairs


class ReflectionAgent:
    """Reject duplicates, leakage, unsupported, complex, or untestable candidates."""

    def __init__(self, dsl: SafeSignalDSL, config: AgenticDiscoveryConfig):
        self.dsl = dsl
        self.config = config

    def reflect(
        self,
        hypothesis: SignalHypothesis,
        rows: Sequence[dict[str, Any]],
        seen_canonicals: set[str],
    ) -> ReflectionResult:
        reasons: list[str] = []
        if not rows:
            reasons.append("no_rows")
        if not any("outcome" in row for row in rows):
            reasons.append("missing_resolved_outcomes")

        try:
            canonical = self.dsl.canonicalize(hypothesis.expression)
            if canonical in seen_canonicals:
                reasons.append("duplicate_expression")
            if self.dsl.complexity(hypothesis.expression) > self.config.max_complexity:
                reasons.append("complexity_exceeds_limit")
            features = self.dsl.validate(hypothesis.expression, rows)
            support = (
                min(
                    sum(
                        1
                        for row in rows
                        if feature in row and isinstance(row.get(feature), (int, float, bool))
                    )
                    for feature in features
                )
                if features
                else len(rows)
            )
            if support < self.config.min_support:
                reasons.append("insufficient_sample_support")
            values = np.asarray(self.dsl.evaluate(hypothesis.expression, rows), dtype=float)
            if len(values) and float(np.std(values)) <= 1e-12:
                reasons.append("zero_variance_signal")
        except DSLValidationError as exc:
            reasons.append(f"dsl_validation:{exc}")

        accepted = not reasons
        if accepted:
            seen_canonicals.add(self.dsl.canonicalize(hypothesis.expression))
        return ReflectionResult(accepted=accepted, reasons=reasons)


class RankingAgent:
    """Evaluate candidates through ResearchBacktester and rank them conservatively."""

    def __init__(
        self,
        dsl: SafeSignalDSL,
        backtester: ResearchBacktester,
        config: AgenticDiscoveryConfig,
    ):
        self.dsl = dsl
        self.backtester = backtester
        self.config = config

    def evaluate(
        self,
        hypothesis: SignalHypothesis,
        rows: Sequence[dict[str, Any]],
        n_trials: int,
    ) -> CandidateEvaluation:
        candidate_rows = self._candidate_rows(hypothesis, rows)
        bt_config = ResearchBacktestConfig(
            name=hypothesis.name,
            min_train_size=min(
                self.config.backtest_min_train_size, max(len(candidate_rows) // 2, 1)
            ),
            test_size=min(self.config.backtest_test_size, max(len(candidate_rows) // 4, 1)),
            step_size=max(1, min(self.config.backtest_step_size, max(len(candidate_rows) // 4, 1))),
            n_strategy_trials=max(n_trials, 1),
        )
        report = self.backtester.run_experiment(bt_config, rows=candidate_rows)
        reward = self.reward(report.metrics, report.promotion.status, hypothesis.complexity)
        return CandidateEvaluation(
            hypothesis=hypothesis,
            metrics=report.metrics,
            bucket_metrics=report.bucket_metrics,
            promotion=asdict(report.promotion),
            reward=reward,
            report_ref=report.run_id,
        )

    def _candidate_rows(
        self, hypothesis: SignalHypothesis, rows: Sequence[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        values = np.asarray(self.dsl.evaluate(hypothesis.expression, rows), dtype=float)
        if len(values) == 0:
            return []
        if float(np.nanmin(values)) >= 0.0 and float(np.nanmax(values)) <= 1.0:
            probabilities = values
        else:
            probabilities = np.asarray(
                [float(row.get("p_baseline", row.get("market_implied", 0.5))) for row in rows],
                dtype=float,
            ) + 0.15 * SafeSignalDSL._zscore(values)
            probabilities = np.clip(probabilities, 0.01, 0.99)

        out: list[dict[str, Any]] = []
        for row, probability in zip(rows, probabilities):
            candidate = dict(row)
            p_model = float(np.clip(probability, 0.01, 0.99))
            price = float(
                candidate.get(
                    "execution_price",
                    candidate.get("market_implied", candidate.get("p_baseline", 0.5)),
                )
            )
            candidate["p_model"] = p_model
            candidate["model_prob"] = p_model
            candidate["stake_fraction"] = 0.01 if p_model >= price else -0.01
            candidate.setdefault("filled", 1.0)
            candidate.setdefault("fill_probability", 1.0)
            out.append(candidate)
        return out

    @staticmethod
    def reward(metrics: dict[str, Any], promotion_status: str, complexity: int) -> float:
        baseline_brier = float(metrics.get("baseline_brier", 0.0))
        brier = float(metrics.get("brier", 1.0))
        brier_improvement = (
            (baseline_brier - brier) / baseline_brier if baseline_brier > 1e-12 else 0.0
        )
        baseline_log = float(metrics.get("baseline_log_score", 0.0))
        log_score = float(metrics.get("log_score", 1.0))
        log_improvement = (baseline_log - log_score) / baseline_log if baseline_log > 1e-12 else 0.0
        calibration = 1.0 - min(float(metrics.get("ece", 1.0)) / 0.20, 1.0)
        dsr = float(metrics.get("deflated_sharpe_ratio", 0.0))
        pbo_score = 1.0 - float(metrics.get("pbo", 1.0))
        n = max(int(metrics.get("n", 0)), 1)
        net_edge = math.tanh(float(metrics.get("execution_return", 0.0)) / n * 100.0)
        support = min(n / 200.0, 1.0)
        promotion_bonus = 0.10 if promotion_status == "PROMOTED" else 0.0
        complexity_penalty = min(float(complexity) / 500.0, 0.12)
        score = (
            0.35 * brier_improvement
            + 0.15 * log_improvement
            + 0.10 * calibration
            + 0.10 * dsr
            + 0.10 * pbo_score
            + 0.10 * net_edge
            + 0.05 * support
            + promotion_bonus
            - complexity_penalty
        )
        return float(score)

    @staticmethod
    def compute_elo(scores: dict[str, float], k_factor: float = 24.0) -> dict[str, float]:
        ratings = {hypothesis_id: 1000.0 for hypothesis_id in scores}
        ids = sorted(scores)
        for left_idx, left in enumerate(ids):
            for right in ids[left_idx + 1 :]:
                if scores[left] == scores[right]:
                    actual_left = 0.5
                else:
                    actual_left = 1.0 if scores[left] > scores[right] else 0.0
                expected_left = 1.0 / (1.0 + 10.0 ** ((ratings[right] - ratings[left]) / 400.0))
                delta = k_factor * (actual_left - expected_left)
                ratings[left] += delta
                ratings[right] -= delta
        return ratings


class EvolutionAgent:
    """Mutate and recombine top candidates while preserving parent provenance."""

    def __init__(
        self,
        dsl: SafeSignalDSL,
        rng: random.Random,
        config: AgenticDiscoveryConfig,
    ):
        self.dsl = dsl
        self.rng = rng
        self.config = config

    def evolve(
        self,
        run_id: str,
        trajectory_id: str,
        focus: str,
        top_hypotheses: Sequence[SignalHypothesis],
        feature_catalog: Sequence[str],
        limit: int = 4,
    ) -> tuple[list[SignalHypothesis], list[DiscoveryTransition]]:
        children: list[SignalHypothesis] = []
        transitions: list[DiscoveryTransition] = []
        if not top_hypotheses:
            return children, transitions

        supporting_features = [
            feature
            for feature in feature_catalog
            if feature not in {"p_baseline", "market_implied"}
        ]
        if not supporting_features:
            supporting_features = list(feature_catalog)

        for parent in top_hypotheses[: max(1, min(3, len(top_hypotheses)))]:
            feature = supporting_features[len(children) % len(supporting_features)]
            expression = f"clip(({parent.expression}) + 0.05 * zscore({feature}), 0.01, 0.99)"
            child = self._child(
                expression=expression,
                focus=focus,
                parent_ids=[parent.hypothesis_id],
                rationale=f"Regime transition: add {feature} context to {parent.name}.",
                mutation_type="context_tilt",
            )
            children.append(child)
            transitions.append(
                self._transition(
                    run_id,
                    trajectory_id,
                    [parent.hypothesis_id],
                    child.hypothesis_id,
                    "mutation",
                    child.rationale,
                )
            )
            if len(children) >= limit:
                return children, transitions

        if len(top_hypotheses) >= 2:
            left, right = top_hypotheses[0], top_hypotheses[1]
            expression = f"clip(0.5 * ({left.expression}) + 0.5 * ({right.expression}), 0.01, 0.99)"
            child = self._child(
                expression=expression,
                focus=focus,
                parent_ids=[left.hypothesis_id, right.hypothesis_id],
                rationale=f"Recombine {left.name} and {right.name} into an ensemble regime.",
                mutation_type="recombination",
            )
            children.append(child)
            transitions.append(
                self._transition(
                    run_id,
                    trajectory_id,
                    [left.hypothesis_id, right.hypothesis_id],
                    child.hypothesis_id,
                    "recombination",
                    child.rationale,
                )
            )
        return children[:limit], transitions[:limit]

    def _child(
        self,
        expression: str,
        focus: str,
        parent_ids: list[str],
        rationale: str,
        mutation_type: str,
    ) -> SignalHypothesis:
        try:
            complexity = self.dsl.complexity(expression)
        except DSLValidationError:
            complexity = 999
        return SignalHypothesis(
            hypothesis_id=stable_hypothesis_id(expression, focus, parent_ids),
            name=f"{focus}:{mutation_type}:{len(parent_ids)}",
            expression=expression,
            rationale=rationale,
            focus=focus,
            prior=0.50 + self.rng.uniform(-0.02, 0.02),
            parent_ids=parent_ids,
            complexity=complexity,
            metadata={"agent": "evolution", "mutation_type": mutation_type},
        )

    @staticmethod
    def _transition(
        run_id: str,
        trajectory_id: str,
        parent_ids: list[str],
        child_id: str,
        transition_type: str,
        reason: str,
    ) -> DiscoveryTransition:
        return DiscoveryTransition(
            transition_id=stable_transition_id(
                run_id, trajectory_id, parent_ids, child_id, transition_type
            ),
            run_id=run_id,
            trajectory_id=trajectory_id,
            from_hypothesis_ids=parent_ids,
            to_hypothesis_id=child_id,
            transition_type=transition_type,
            reason=reason,
            accepted=True,
        )
