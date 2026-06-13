"""Serializable contracts for agentic signal discovery."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SignalHypothesis:
    hypothesis_id: str
    name: str
    expression: str
    rationale: str
    focus: str
    prior: float = 0.5
    parent_ids: List[str] = field(default_factory=list)
    complexity: int = 0
    created_ts: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DiscoveryArtifact:
    artifact_id: str
    run_id: str
    trajectory_id: str
    artifact_type: str
    payload: Dict[str, Any]
    status: str = "RECORDED"
    reasons: List[str] = field(default_factory=list)
    parent_ids: List[str] = field(default_factory=list)
    created_ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DiscoveryTransition:
    transition_id: str
    run_id: str
    trajectory_id: str
    from_hypothesis_ids: List[str]
    to_hypothesis_id: str
    transition_type: str
    reason: str
    accepted: bool
    metrics: Dict[str, Any] = field(default_factory=dict)
    created_ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TrajectoryReport:
    trajectory_id: str
    focus: str
    seed: int
    hypotheses_tested: int
    accepted_ids: List[str]
    rejected_ids: List[str]
    top_hypothesis_ids: List[str]
    summary: str
    artifacts: List[DiscoveryArtifact] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["artifacts"] = [artifact.to_dict() for artifact in self.artifacts]
        return payload


@dataclass
class DiscoveryRunReport:
    run_id: str
    config: Dict[str, Any]
    created_ts: float
    top_hypotheses: List[Dict[str, Any]]
    rejected_contrasts: List[Dict[str, Any]]
    puct_table: List[Dict[str, Any]]
    trajectory_summaries: List[Dict[str, Any]]
    accepted_transitions: List[Dict[str, Any]]
    promotion_decisions: Dict[str, Dict[str, Any]]
    robust_hypothesis_ids: List[str]
    queued_proposal_ids: List[str] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReflectionResult:
    accepted: bool
    reasons: List[str] = field(default_factory=list)


@dataclass
class CandidateEvaluation:
    hypothesis: SignalHypothesis
    metrics: Dict[str, Any]
    bucket_metrics: Dict[str, Dict[str, Any]]
    promotion: Dict[str, Any]
    reward: float
    elo: float = 1000.0
    report_ref: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["hypothesis"] = self.hypothesis.to_dict()
        return payload
