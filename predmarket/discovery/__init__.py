"""Agentic signal discovery for prediction-market alpha research."""

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
from predmarket.discovery.dsl import DSLValidationError, SafeSignalDSL
from predmarket.discovery.engine import AgenticSignalDiscoveryEngine
from predmarket.discovery.puct import PUCTArmStats, PUCTSearch

__all__ = [
    "AgenticDiscoveryConfig",
    "AgenticSignalDiscoveryEngine",
    "CandidateEvaluation",
    "DiscoveryArtifact",
    "DiscoveryRunReport",
    "DiscoveryTransition",
    "DSLValidationError",
    "EvolutionAgent",
    "HypothesisAgent",
    "PUCTArmStats",
    "PUCTSearch",
    "RankingAgent",
    "ReflectionAgent",
    "SafeSignalDSL",
    "SignalHypothesis",
    "TrajectoryReport",
]
