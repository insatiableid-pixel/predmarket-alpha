"""Walk-forward backtesting engine for forecast evaluation.

Implements Petropoulos et al. (2022) §2.12.6-7 — systematic backtesting
with rolling/expanding windows, baseline comparison, and overfit detection.

Usage:
    backtester = Backtester(forecast_history)
    results = backtester.run_walk_forward(train_window=30, test_window=7)
    print(backtester.summary())
"""

import logging
import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any

import numpy as np

from predmarket.density import (
    DensityForecast,
    from_point_estimate,
    crps_score_fast,
    brier_score,
)

logger = logging.getLogger("predmarket.backtester")


@dataclass
class BacktestResult:
    """Evaluation metrics for a single walk-forward window.

    Attributes:
        brier_mean: Mean Brier score over the window.
        brier_std: Standard deviation of Brier scores.
        crps_mean: Mean CRPS across resolved forecasts.
        log_score_mean: Mean logarithmic score.
        hit_rate: Fraction of forecasts where direction was correct.
        total_pnl: Simulated profit and loss (USD).
        sharpe_ratio: Annualized Sharpe ratio of returns.
        max_drawdown: Maximum peak-to-trough drawdown.
        calibration_error: Mean absolute calibration error.
        n_trades: Number of trades evaluated.
        horizon: Window label (e.g., "train=30/test=7").
    """

    brier_mean: float = 0.0
    brier_std: float = 0.0
    crps_mean: float = 0.0
    log_score_mean: float = 0.0
    hit_rate: float = 0.0
    total_pnl: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    calibration_error: float = 0.0
    n_trades: int = 0
    horizon: str = ""


def _log_score(prob: float, outcome: float, eps: float = 1e-15) -> float:
    """Compute log score: -[o*log(f) + (1-o)*log(1-f)]."""
    p = np.clip(prob, eps, 1.0 - eps)
    o = outcome
    return -(o * np.log(p) + (1.0 - o) * np.log(1.0 - p))


class Backtester:
    """Walk-forward backtesting engine.

    Replays historical forecasts against resolved binary outcomes to
    produce Brier scores, CRPS, PnL, Sharpe, and calibration metrics.

    Args:
        forecast_history: List of dicts with keys:
            timestamp, contract_id, model_prob, market_implied,
            category, status, outcome (0/1 or None for unresolved).
        equity_history: Optional list of equity values (chronological).
    """

    def __init__(
        self,
        forecast_history: List[Dict[str, Any]],
        equity_history: Optional[List[float]] = None,
    ):
        self.forecasts = sorted(
            forecast_history, key=lambda x: x.get("timestamp", 0)
        )
        self.equity_history = equity_history or []

    # ------------------------------------------------------------------
    # Core walk-forward
    # ------------------------------------------------------------------

    def run_walk_forward(
        self,
        train_window: int = 30,
        test_window: int = 7,
        step: int = 1,
    ) -> List[BacktestResult]:
        """Split forecast history chronologically and evaluate each test window.

        Args:
            train_window: Number of resolved forecasts in the training lookback.
            test_window: Number of resolved forecasts to evaluate per fold.
            step: Stride between fold starts.

        Returns:
            List of BacktestResult, one per test fold.
        """
        resolved = [f for f in self.forecasts if f.get("outcome") is not None]
        if len(resolved) < train_window + test_window:
            logger.warning(
                "Insufficient resolved forecasts for walk-forward: %d resolved, "
                "need at least %d.",
                len(resolved),
                train_window + test_window,
            )
            return []

        results: List[BacktestResult] = []
        n = len(resolved)

        for start in range(train_window, n - test_window + 1, step):
            test_slice = resolved[start : start + test_window]
            result = self._evaluate_window(test_slice)
            result.horizon = f"train={train_window}/test={test_window}"
            results.append(result)

        return results

    # ------------------------------------------------------------------
    # Rolling metrics
    # ------------------------------------------------------------------

    def compute_rolling_brier(
        self, window: int = 20
    ) -> List[Tuple[float, float]]:
        """Compute rolling Brier score over resolved forecasts.

        Returns:
            List of (timestamp, rolling_brier) pairs.
        """
        resolved = [f for f in self.forecasts if f.get("outcome") is not None]
        if len(resolved) < window:
            return []

        pairs: List[Tuple[float, float]] = []
        for i in range(window, len(resolved) + 1):
            batch = resolved[i - window : i]
            scores = [
                brier_score(f["model_prob"], f["outcome"])
                for f in batch
            ]
            ts = batch[-1].get("timestamp", 0)
            pairs.append((ts, float(np.mean(scores))))
        return pairs

    def compute_cumulative_pnl(self) -> List[Tuple[float, float]]:
        """Simulate cumulative PnL using resolved outcomes.

        Assumes a fixed $100 notional per trade. A correct YES prediction
        (prob > 0.5, outcome=1) or NO prediction (prob < 0.5, outcome=0)
        earns (1/price - 1). An incorrect trade loses the notional.

        Returns:
            List of (timestamp, cumulative_pnl) pairs.
        """
        resolved = [f for f in self.forecasts if f.get("outcome") is not None]
        if not resolved:
            return []

        pairs: List[Tuple[float, float]] = []
        cum_pnl = 0.0
        for f in resolved:
            outcome = f["outcome"]
            prob = f["model_prob"]
            price = f.get("market_implied", 0.5)
            notional = 100.0

            predicted_yes = prob > 0.5
            actual_yes = outcome == 1

            if predicted_yes == actual_yes:
                # Win: earn edge
                if price > 0:
                    cum_pnl += notional * (1.0 / max(price, 0.01) - 1.0)
                else:
                    cum_pnl += notional
            else:
                cum_pnl -= notional

            ts = f.get("timestamp", 0)
            pairs.append((ts, cum_pnl))
        return pairs

    # ------------------------------------------------------------------
    # Baseline comparison
    # ------------------------------------------------------------------

    def compare_to_baselines(
        self, baselines: Dict[str, List[float]]
    ) -> Dict[str, BacktestResult]:
        """Compare model forecasts against baseline forecasts.

        Args:
            baselines: Dict mapping baseline name to list of probability
                forecasts aligned with resolved outcomes in self.forecasts.

        Returns:
            Dict mapping baseline name to its BacktestResult.
        """
        resolved = [f for f in self.forecasts if f.get("outcome") is not None]
        results: Dict[str, BacktestResult] = {}

        for name, probs in baselines.items():
            n = min(len(resolved), len(probs))
            if n == 0:
                continue
            synthetic = []
            for i in range(n):
                entry = dict(resolved[i])
                entry["model_prob"] = probs[i]
                synthetic.append(entry)
            results[name] = self._evaluate_window(synthetic)

        # Add model itself
        results["model"] = self._evaluate_window(resolved)
        return results

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """Return formatted summary of all resolved forecasts."""
        resolved = [f for f in self.forecasts if f.get("outcome") is not None]
        if not resolved:
            return "No resolved forecasts available for backtesting."

        result = self._evaluate_window(resolved)
        lines = [
            "=== Backtest Summary ===",
            f"  Resolved forecasts : {result.n_trades}",
            f"  Mean Brier score   : {result.brier_mean:.4f} (std {result.brier_std:.4f})",
            f"  Mean CRPS          : {result.crps_mean:.4f}",
            f"  Mean Log Score     : {result.log_score_mean:.4f}",
            f"  Hit Rate           : {result.hit_rate:.1%}",
            f"  Simulated PnL      : ${result.total_pnl:,.2f}",
            f"  Sharpe Ratio       : {result.sharpe_ratio:.3f}",
            f"  Max Drawdown       : {result.max_drawdown:.2%}",
            f"  Calibration Error  : {result.calibration_error:.4f}",
        ]

        # Baseline comparison
        n = len(resolved)
        baselines = {
            "random_walk": [resolved[i].get("market_implied", 0.5) for i in range(n)],
            "always_50": [0.5] * n,
            "historical_mean": [float(np.mean([r["outcome"] for r in resolved[: i + 1]])) for i in range(n)],
        }
        comparisons = self.compare_to_baselines(baselines)
        lines.append("")
        lines.append("  --- Baseline Comparison ---")
        for name, res in sorted(comparisons.items(), key=lambda x: x[1].brier_mean):
            lines.append(f"  {name:>20s}: Brier={res.brier_mean:.4f}  HitRate={res.hit_rate:.1%}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evaluate_window(self, window: List[Dict[str, Any]]) -> BacktestResult:
        """Evaluate a slice of resolved forecasts."""
        briers: List[float] = []
        crpss: List[float] = []
        log_scores: List[float] = []
        pnls: List[float] = []
        hits = 0

        for f in window:
            outcome = f["outcome"]
            prob = f["model_prob"]
            price = f.get("market_implied", 0.5)
            notional = 100.0

            # Brier
            briers.append(brier_score(prob, outcome))

            # CRPS (using density around point estimate)
            density = from_point_estimate(prob, uncertainty=0.1)
            crpss.append(crps_score_fast(density, outcome))

            # Log score
            log_scores.append(_log_score(prob, outcome))

            # Hit rate
            predicted_yes = prob > 0.5
            actual_yes = outcome == 1
            if predicted_yes == actual_yes:
                hits += 1
                pnls.append(notional * (1.0 / max(price, 0.01) - 1.0))
            else:
                pnls.append(-notional)

        # Sharpe ratio
        sharpe = 0.0
        if len(pnls) > 1:
            mean_ret = np.mean(pnls)
            std_ret = np.std(pnls)
            if std_ret > 0:
                sharpe = float(mean_ret / std_ret * np.sqrt(252))

        # Max drawdown
        cum = np.cumsum(pnls)
        peak = np.maximum.accumulate(cum)
        drawdowns = (peak - cum) / np.where(peak != 0, np.abs(peak), 1.0)
        max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

        # Calibration error (mean absolute difference between forecast prob and
        # outcome frequency in bins)
        cal_err = self._calibration_error(window)

        return BacktestResult(
            brier_mean=float(np.mean(briers)),
            brier_std=float(np.std(briers)),
            crps_mean=float(np.mean(crpss)),
            log_score_mean=float(np.mean(log_scores)),
            hit_rate=hits / max(len(window), 1),
            total_pnl=float(sum(pnls)),
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            calibration_error=cal_err,
            n_trades=len(window),
        )

    @staticmethod
    def _calibration_error(forecasts: List[Dict[str, Any]], n_bins: int = 5) -> float:
        """Compute mean absolute calibration error across bins."""
        if not forecasts:
            return 0.0
        bins = np.linspace(0.0, 1.0, n_bins + 1)
        errors = []
        for i in range(n_bins):
            lo, hi = bins[i], bins[i + 1]
            in_bin = [f for f in forecasts if lo <= f["model_prob"] < hi]
            if not in_bin:
                continue
            mean_prob = np.mean([f["model_prob"] for f in in_bin])
            actual_freq = np.mean([f["outcome"] for f in in_bin])
            errors.append(abs(mean_prob - actual_freq))
        return float(np.mean(errors)) if errors else 0.0
