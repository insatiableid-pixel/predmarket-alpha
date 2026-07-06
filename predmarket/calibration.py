"""Probabilistic calibration and scoring helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np


def pinball_loss(y_true: Iterable[float], y_pred: Iterable[float], quantile: float) -> float:
    y = np.asarray(list(y_true), dtype=float)
    p = np.asarray(list(y_pred), dtype=float)
    if len(y) == 0:
        return 0.0
    err = y - p
    return float(np.mean(np.where(err >= 0, quantile * err, (quantile - 1.0) * err)))


def expected_calibration_error(
    probabilities: Iterable[float], outcomes: Iterable[float], n_bins: int = 10
) -> float:
    probs = np.asarray(list(probabilities), dtype=float)
    outs = np.asarray(list(outcomes), dtype=float)
    if len(probs) == 0:
        return 0.0
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    weighted_error = 0.0
    total = 0
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        if i == n_bins - 1:
            mask = (probs >= lo) & (probs <= hi)
        else:
            mask = (probs >= lo) & (probs < hi)
        if not np.any(mask):
            continue
        count = int(np.sum(mask))
        weighted_error += count * abs(float(np.mean(probs[mask]) - np.mean(outs[mask])))
        total += count
    return float(weighted_error / max(total, 1))


@dataclass
class ConformalCalibrator:
    """Symmetric residual conformal calibrator for bounded probabilities."""

    residuals_by_bucket: dict[str, list[float]] = field(default_factory=dict)

    def update(self, bucket: str, predicted_prob: float, outcome: float) -> None:
        self.residuals_by_bucket.setdefault(bucket, []).append(
            abs(float(predicted_prob) - float(outcome))
        )

    def interval(
        self, bucket: str, predicted_prob: float, alpha: float = 0.1
    ) -> tuple[float, float]:
        residuals = self.residuals_by_bucket.get(bucket, [])
        if not residuals:
            radius = 0.25
        else:
            q = min(max(1.0 - alpha, 0.0), 1.0)
            radius = float(np.quantile(np.asarray(residuals, dtype=float), q, method="higher"))
        lo = max(0.0, float(predicted_prob) - radius)
        hi = min(1.0, float(predicted_prob) + radius)
        return lo, hi

    def quantiles(
        self, bucket: str, predicted_prob: float, levels: list[float] | None = None
    ) -> dict[float, float]:
        levels = levels or [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]
        residuals = self.residuals_by_bucket.get(bucket, [])
        if not residuals:
            spread = 0.20
            values = [predicted_prob + (level - 0.5) * 2.0 * spread for level in levels]
        else:
            arr = np.asarray(residuals, dtype=float)
            values = []
            for level in levels:
                signed = -1.0 if level < 0.5 else 1.0
                radius = float(np.quantile(arr, abs(level - 0.5) * 2.0))
                values.append(predicted_prob + signed * radius)
        clipped = np.maximum.accumulate(np.clip(values, 0.0, 1.0))
        return {float(level): float(value) for level, value in zip(levels, clipped)}


def quantiles_from_samples(samples: Iterable[float]) -> dict[float, float]:
    arr = np.clip(np.asarray(list(samples), dtype=float), 0.0, 1.0)
    if len(arr) == 0:
        arr = np.asarray([0.5])
    levels = [0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.975]
    values = np.maximum.accumulate([np.quantile(arr, q) for q in levels])
    return {q: float(v) for q, v in zip(levels, values)}
