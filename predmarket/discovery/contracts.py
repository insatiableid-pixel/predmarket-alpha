"""Serializable contracts for agentic signal discovery."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AgenticDiscoveryConfig:
    n_trajectories: int = 4
    iterations_per_trajectory: int = 32
    puct_c: float = 1.5
    top_k: int = 10
    random_seed: int = 42
    research_only: bool = True
    min_support: int = 20
    max_complexity: int = 48
    evolution_interval: int = 8
    backtest_min_train_size: int = 20
    backtest_test_size: int = 10
    backtest_step_size: int = 10

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SignalHypothesis:
    hypothesis_id: str
    name: str
    expression: str
    rationale: str
    focus: str
    prior: float = 0.5
    parent_ids: list[str] = field(default_factory=list)
    complexity: int = 0
    created_ts: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiscoveryArtifact:
    artifact_id: str
    run_id: str
    trajectory_id: str
    artifact_type: str
    payload: dict[str, Any]
    status: str = "RECORDED"
    reasons: list[str] = field(default_factory=list)
    parent_ids: list[str] = field(default_factory=list)
    created_ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiscoveryTransition:
    transition_id: str
    run_id: str
    trajectory_id: str
    from_hypothesis_ids: list[str]
    to_hypothesis_id: str
    transition_type: str
    reason: str
    accepted: bool
    metrics: dict[str, Any] = field(default_factory=dict)
    created_ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TrajectoryReport:
    trajectory_id: str
    focus: str
    seed: int
    hypotheses_tested: int
    accepted_ids: list[str]
    rejected_ids: list[str]
    top_hypothesis_ids: list[str]
    summary: str
    artifacts: list[DiscoveryArtifact] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["artifacts"] = [artifact.to_dict() for artifact in self.artifacts]
        return payload


@dataclass
class DiscoveryRunReport:
    run_id: str
    config: dict[str, Any]
    created_ts: float
    top_hypotheses: list[dict[str, Any]]
    rejected_contrasts: list[dict[str, Any]]
    puct_table: list[dict[str, Any]]
    trajectory_summaries: list[dict[str, Any]]
    accepted_transitions: list[dict[str, Any]]
    promotion_decisions: dict[str, dict[str, Any]]
    robust_hypothesis_ids: list[str]
    queued_proposal_ids: list[str] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReflectionResult:
    accepted: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class CandidateEvaluation:
    hypothesis: SignalHypothesis
    metrics: dict[str, Any]
    bucket_metrics: dict[str, dict[str, Any]]
    promotion: dict[str, Any]
    reward: float
    elo: float = 1000.0
    report_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["hypothesis"] = self.hypothesis.to_dict()
        return payload
