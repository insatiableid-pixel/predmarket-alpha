"""Flat PUCT search over candidate signal hypotheses."""

from __future__ import annotations

import math
import random
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field

from predmarket.discovery.contracts import SignalHypothesis


@dataclass
class PUCTArmStats:
    hypothesis_id: str
    trajectory_id: str
    prior: float
    visits: int = 0
    total_value: float = 0.0
    max_value: float = 0.0
    status: str = "UNEVALUATED"
    rejection_reasons: list[str] = field(default_factory=list)

    @property
    def q_value(self) -> float:
        return self.total_value / self.visits if self.visits else 0.0

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["q_value"] = self.q_value
        return payload


class PUCTSearch:
    """A deterministic flat PUCT selector for discovery arms."""

    def __init__(self, puct_c: float = 1.5, random_seed: int = 42):
        self.puct_c = float(puct_c)
        self.rng = random.Random(random_seed)
        self.arms: dict[str, SignalHypothesis] = {}
        self.stats: dict[str, PUCTArmStats] = {}

    def add_arm(
        self,
        hypothesis: SignalHypothesis,
        trajectory_id: str,
        status: str = "UNEVALUATED",
        rejection_reasons: Iterable[str] | None = None,
    ) -> None:
        self.arms[hypothesis.hypothesis_id] = hypothesis
        if hypothesis.hypothesis_id not in self.stats:
            self.stats[hypothesis.hypothesis_id] = PUCTArmStats(
                hypothesis_id=hypothesis.hypothesis_id,
                trajectory_id=trajectory_id,
                prior=max(float(hypothesis.prior), 1e-6),
                status=status,
                rejection_reasons=list(rejection_reasons or []),
            )
        else:
            self.stats[hypothesis.hypothesis_id].status = status
            self.stats[hypothesis.hypothesis_id].rejection_reasons = list(rejection_reasons or [])

    def select_arm(self) -> SignalHypothesis | None:
        eligible = [
            (hypothesis_id, stats)
            for hypothesis_id, stats in self.stats.items()
            if stats.status != "REJECTED"
        ]
        if not eligible:
            return None

        total_visits = max(sum(stats.visits for _, stats in eligible), 1)
        scored = []
        for hypothesis_id, stats in eligible:
            exploration = (
                self.puct_c * stats.prior * math.sqrt(float(total_visits)) / (1.0 + stats.visits)
            )
            scored.append((stats.q_value + exploration, stats.prior, hypothesis_id))
        best_score = max(score for score, _, _ in scored)
        tied = [item for item in scored if abs(item[0] - best_score) <= 1e-12]
        tied.sort(key=lambda item: item[2])
        _, _, hypothesis_id = self.rng.choice(tied)
        return self.arms[hypothesis_id]

    def update(self, hypothesis_id: str, reward: float, status: str = "EVALUATED") -> None:
        stats = self.stats[hypothesis_id]
        stats.visits += 1
        stats.total_value += float(reward)
        stats.max_value = max(stats.max_value, float(reward))
        stats.status = status

    def mark_rejected(
        self, hypothesis: SignalHypothesis, trajectory_id: str, reasons: list[str]
    ) -> None:
        self.add_arm(
            hypothesis,
            trajectory_id=trajectory_id,
            status="REJECTED",
            rejection_reasons=reasons,
        )

    def table(self) -> list[dict[str, object]]:
        rows = [stats.to_dict() for stats in self.stats.values()]
        return sorted(
            rows,
            key=lambda row: (
                str(row.get("trajectory_id", "")),
                -int(row.get("visits", 0)),
                -float(row.get("q_value", 0.0)),
                str(row.get("hypothesis_id", "")),
            ),
        )
