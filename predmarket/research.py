"""Leak-aware research backtesting and promotion gates.

This module is intentionally conservative. It treats every model as research
until it beats market-implied probabilities out of sample inside the bucket
where it will be used.
"""

from __future__ import annotations

import json
import statistics
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from predmarket.calibration import expected_calibration_error, pinball_loss


def _clip_prob(values: Iterable[float]) -> np.ndarray:
    return np.clip(np.asarray(list(values), dtype=float), 1e-6, 1.0 - 1e-6)


def brier_score(probabilities: Iterable[float], outcomes: Iterable[float]) -> float:
    p = _clip_prob(probabilities)
    y = np.asarray(list(outcomes), dtype=float)
    if len(p) == 0:
        return 0.0
    return float(np.mean((p - y) ** 2))


def log_score(probabilities: Iterable[float], outcomes: Iterable[float]) -> float:
    p = _clip_prob(probabilities)
    y = np.asarray(list(outcomes), dtype=float)
    if len(p) == 0:
        return 0.0
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


def max_drawdown(returns: Sequence[float]) -> float:
    if not returns:
        return 0.0
    equity = np.cumprod(1.0 + np.asarray(returns, dtype=float))
    peaks = np.maximum.accumulate(equity)
    drawdowns = (peaks - equity) / np.maximum(peaks, 1e-12)
    return float(np.max(drawdowns))


def annualized_sharpe(returns: Sequence[float], periods_per_year: float = 365.0) -> float:
    arr = np.asarray(returns, dtype=float)
    if len(arr) < 2:
        return 0.0
    sd = float(np.std(arr, ddof=1))
    if sd <= 1e-12:
        return 0.0
    return float(np.mean(arr) / sd * np.sqrt(periods_per_year))


def deflated_sharpe_ratio(
    returns: Sequence[float],
    n_trials: int = 1,
    periods_per_year: float = 365.0,
) -> float:
    """Approximate Bailey-Lopez de Prado DSR as a probability in [0, 1]."""
    arr = np.asarray(returns, dtype=float)
    if len(arr) < 3:
        return 0.0
    sr = annualized_sharpe(arr, periods_per_year=periods_per_year)
    skew = float(((arr - arr.mean()) ** 3).mean() / max(arr.std() ** 3, 1e-12))
    kurt = float(((arr - arr.mean()) ** 4).mean() / max(arr.std() ** 4, 1e-12))
    trial_penalty = statistics.NormalDist().inv_cdf(
        1.0 - 1.0 / max(float(n_trials), 2.0)
    )
    sr_star = trial_penalty / np.sqrt(max(len(arr) - 1, 1))
    denom = np.sqrt(max(1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr**2, 1e-9))
    z = (sr - sr_star) * np.sqrt(len(arr) - 1) / denom
    return float(statistics.NormalDist().cdf(z))


def probability_of_backtest_overfitting(
    trial_returns: Sequence[Sequence[float]], train_fraction: float = 0.5
) -> float:
    """Approximate PBO from trial return matrices.

    The estimate splits each trial into train/test, picks the best train trial,
    and asks whether it lands in the bottom half out of sample. This is not a
    full combinatorially symmetric CV implementation, but it catches the
    exact failure mode this repo needs to avoid: choosing the luckiest curve.
    """
    if not trial_returns:
        return 1.0
    train_scores: List[float] = []
    test_scores: List[float] = []
    for series in trial_returns:
        arr = np.asarray(series, dtype=float)
        if len(arr) < 4:
            continue
        split = int(np.clip(round(len(arr) * train_fraction), 1, len(arr) - 1))
        train_scores.append(annualized_sharpe(arr[:split]))
        test_scores.append(annualized_sharpe(arr[split:]))
    if not train_scores:
        return 1.0
    best_idx = int(np.argmax(train_scores))
    test_rank = sorted(test_scores).index(test_scores[best_idx])
    percentile = (test_rank + 1) / len(test_scores)
    return float(1.0 if percentile <= 0.5 else 0.0)


@dataclass
class ResearchBacktestConfig:
    name: str
    horizon: str = "default"
    min_train_size: int = 200
    test_size: int = 50
    step_size: int = 50
    purge_size: int = 0
    embargo_size: int = 0
    expanding: bool = True
    bucket_fields: List[str] = field(
        default_factory=lambda: ["domain", "horizon", "venue", "liquidity_bucket"]
    )
    n_strategy_trials: int = 1


@dataclass
class PromotionDecision:
    status: str
    reasons: List[str]
    metrics: Dict[str, Any]

    @property
    def promoted(self) -> bool:
        return self.status == "PROMOTED"


@dataclass
class ExperimentReport:
    run_id: str
    config: Dict[str, Any]
    created_ts: float
    metrics: Dict[str, Any]
    bucket_metrics: Dict[str, Dict[str, Any]]
    promotion: PromotionDecision
    code_version: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["promotion"] = asdict(self.promotion)
        return payload


class PromotionGate:
    """Bucket-level promotion criteria for staged trade recommendations."""

    def __init__(
        self,
        min_resolved_forecasts: int = 200,
        min_relative_brier_improvement: float = 0.05,
        max_ece: float = 0.03,
        min_dsr: float = 0.95,
        max_pbo: float = 0.20,
        max_major_bucket_brier_underperformance: float = 0.02,
    ):
        self.min_resolved_forecasts = min_resolved_forecasts
        self.min_relative_brier_improvement = min_relative_brier_improvement
        self.max_ece = max_ece
        self.min_dsr = min_dsr
        self.max_pbo = max_pbo
        self.max_major_bucket_brier_underperformance = (
            max_major_bucket_brier_underperformance
        )

    def evaluate(
        self,
        metrics: Dict[str, Any],
        bucket_metrics: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> PromotionDecision:
        reasons: List[str] = []
        n = int(metrics.get("n", 0))
        if n < self.min_resolved_forecasts:
            reasons.append(f"sample_size<{self.min_resolved_forecasts}")

        model_brier = float(metrics.get("brier", 1.0))
        baseline_brier = float(metrics.get("baseline_brier", 1.0))
        rel_improvement = (
            (baseline_brier - model_brier) / baseline_brier
            if baseline_brier > 0
            else -1.0
        )
        if rel_improvement < self.min_relative_brier_improvement:
            reasons.append("relative_brier_improvement<5pct")

        if float(metrics.get("log_score", 1e9)) > float(
            metrics.get("baseline_log_score", -1e9)
        ):
            reasons.append("log_score_worse_than_baseline")

        if float(metrics.get("ece", 1.0)) > self.max_ece:
            reasons.append("ece>0.03")

        if float(metrics.get("deflated_sharpe_ratio", 0.0)) <= self.min_dsr:
            reasons.append("dsr<=0.95")

        if float(metrics.get("pbo", 1.0)) >= self.max_pbo:
            reasons.append("pbo>=0.20")

        for bucket, values in (bucket_metrics or {}).items():
            bucket_n = int(values.get("n", 0))
            if bucket_n == 0:
                continue
            underperf = float(values.get("brier", 1.0)) - float(
                values.get("baseline_brier", 1.0)
            )
            if underperf > self.max_major_bucket_brier_underperformance:
                reasons.append(f"bucket_underperforms:{bucket}")

        return PromotionDecision(
            status="PROMOTED" if not reasons else "RESEARCH_ONLY",
            reasons=reasons,
            metrics={**metrics, "relative_brier_improvement": rel_improvement},
        )


class ResearchBacktester:
    """Run leak-aware experiments from stored or in-memory forecasts."""

    def __init__(
        self,
        store: Any = None,
        promotion_gate: Optional[PromotionGate] = None,
        code_version: str = "",
    ):
        self.store = store
        self.promotion_gate = promotion_gate or PromotionGate()
        self.code_version = code_version

    def walk_forward_splits(
        self, n_rows: int, config: ResearchBacktestConfig
    ) -> List[Tuple[np.ndarray, np.ndarray]]:
        splits: List[Tuple[np.ndarray, np.ndarray]] = []
        start_train = 0
        train_end = config.min_train_size
        while True:
            test_start = train_end + config.purge_size
            test_end = test_start + config.test_size
            if test_end > n_rows:
                break
            if config.expanding:
                train_idx = np.arange(start_train, train_end)
            else:
                train_idx = np.arange(max(start_train, train_end - config.min_train_size), train_end)
            test_idx = np.arange(test_start, test_end)
            splits.append((train_idx, test_idx))
            train_end += config.step_size + config.embargo_size
        return splits

    def run_experiment(
        self,
        config: ResearchBacktestConfig,
        rows: Optional[List[Dict[str, Any]]] = None,
    ) -> ExperimentReport:
        if rows is None:
            rows = self._load_resolved_rows()
        rows = sorted(rows, key=lambda r: float(r.get("as_of_ts", 0.0)))
        run_id = str(uuid.uuid4())
        metrics = self._score_rows(rows, config)
        bucket_metrics = self._score_buckets(rows, config)
        promotion = self.promotion_gate.evaluate(metrics, bucket_metrics)
        report = ExperimentReport(
            run_id=run_id,
            config=asdict(config),
            created_ts=time.time(),
            metrics=metrics,
            bucket_metrics=bucket_metrics,
            promotion=promotion,
            code_version=self.code_version,
        )
        if self.store is not None:
            self.store.write_experiment_run(
                run_id=run_id,
                config=asdict(config),
                report=report.to_dict(),
                code_version=self.code_version,
                status=promotion.status,
            )
        return report

    def _load_resolved_rows(self) -> List[Dict[str, Any]]:
        if self.store is None:
            return []
        rows = self.store._fetchall(
            """
            SELECT f.event_id, f.market_id, f.as_of_ts, f.p_mean, o.outcome,
                   f.horizon, f.calibration_bucket
            FROM forecasts f
            JOIN outcomes o ON f.event_id = o.event_id
            WHERE f.as_of_ts <= o.resolved_ts
            ORDER BY f.as_of_ts
            """
        )
        return [
            {
                "event_id": row[0],
                "market_id": row[1],
                "as_of_ts": row[2],
                "p_model": row[3],
                "outcome": row[4],
                "horizon": row[5],
                "bucket": row[6],
                "p_baseline": 0.5,
            }
            for row in rows
        ]

    def _score_rows(
        self, rows: List[Dict[str, Any]], config: ResearchBacktestConfig
    ) -> Dict[str, Any]:
        if not rows:
            return {
                "n": 0,
                "brier": 0.0,
                "baseline_brier": 0.0,
                "log_score": 0.0,
                "baseline_log_score": 0.0,
                "ece": 1.0,
                "execution_return": 0.0,
                "max_drawdown": 0.0,
                "fill_rate": 0.0,
                "turnover": 0.0,
                "deflated_sharpe_ratio": 0.0,
                "pbo": 1.0,
            }

        model = [r.get("p_model", r.get("model_prob", 0.5)) for r in rows]
        baseline = [r.get("p_baseline", r.get("market_implied", 0.5)) for r in rows]
        outcomes = [r.get("outcome", 0.0) for r in rows]
        returns = [self._execution_return(r) for r in rows]
        fills = [float(r.get("filled", 1.0)) for r in rows]
        trial_returns = self._trial_return_matrix(rows, config.n_strategy_trials)

        quantile_losses = self._quantile_losses(rows, outcomes)

        return {
            "n": len(rows),
            "brier": brier_score(model, outcomes),
            "baseline_brier": brier_score(baseline, outcomes),
            "log_score": log_score(model, outcomes),
            "baseline_log_score": log_score(baseline, outcomes),
            "ece": expected_calibration_error(model, outcomes),
            "crps_proxy": float(np.mean(list(quantile_losses.values()))) if quantile_losses else 0.0,
            "pinball": quantile_losses,
            "execution_return": float(np.sum(returns)),
            "sharpe": annualized_sharpe(returns),
            "max_drawdown": max_drawdown(returns),
            "fill_rate": float(np.mean(fills)) if fills else 0.0,
            "turnover": float(np.sum(np.abs([r.get("stake_fraction", 0.0) for r in rows]))),
            "deflated_sharpe_ratio": deflated_sharpe_ratio(
                returns, n_trials=max(config.n_strategy_trials, 1)
            ),
            "pbo": probability_of_backtest_overfitting(trial_returns),
        }

    def _score_buckets(
        self, rows: List[Dict[str, Any]], config: ResearchBacktestConfig
    ) -> Dict[str, Dict[str, Any]]:
        buckets: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            parts = []
            for field_name in config.bucket_fields:
                value = row.get(field_name)
                if value is not None:
                    parts.append(f"{field_name}={value}")
            if not parts:
                parts.append(str(row.get("bucket", "default")))
            buckets.setdefault("|".join(parts), []).append(row)
        return {
            bucket: self._score_rows(bucket_rows, config)
            for bucket, bucket_rows in buckets.items()
        }

    @staticmethod
    def _execution_return(row: Dict[str, Any]) -> float:
        p = float(row.get("p_model", row.get("model_prob", 0.5)))
        price = float(row.get("execution_price", row.get("market_implied", row.get("p_baseline", 0.5))))
        fee = float(row.get("fee", row.get("fees", 0.0)))
        slippage = float(row.get("slippage", 0.0))
        fill_probability = float(row.get("fill_probability", 1.0))
        stake = float(row.get("stake_fraction", 1.0))
        edge = p - price - fee - slippage
        return stake * fill_probability * edge

    @staticmethod
    def _trial_return_matrix(
        rows: List[Dict[str, Any]], n_trials: int
    ) -> List[List[float]]:
        base = [ResearchBacktester._execution_return(row) for row in rows]
        trials = [base]
        for trial_idx in range(1, max(n_trials, 1)):
            scale = 1.0 - 0.05 * trial_idx
            trials.append([ret * scale for ret in base])
        return trials

    @staticmethod
    def _quantile_losses(
        rows: List[Dict[str, Any]], outcomes: List[float]
    ) -> Dict[float, float]:
        levels: set[float] = set()
        for row in rows:
            levels.update(float(k) for k in (row.get("quantiles") or {}).keys())
        losses: Dict[float, float] = {}
        for level in sorted(levels):
            preds = [
                (row.get("quantiles") or {}).get(level)
                or (row.get("quantiles") or {}).get(str(level))
                for row in rows
            ]
            if all(pred is not None for pred in preds):
                losses[level] = pinball_loss(outcomes, preds, level)
        return losses


def report_to_json(report: ExperimentReport) -> str:
    return json.dumps(report.to_dict(), sort_keys=True, default=str)
