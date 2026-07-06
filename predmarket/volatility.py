"""GARCH volatility modeling for prediction market prices.

Implements Petropoulos et al. (2022) §2.3.14 — ARCH/GARCH models.
Models the variance of market price series to detect regime changes
and extract volatility features for the ensemble.

The existing ensemble ignores volatility entirely — it uses line_history
only for a simple trend check. This module provides proper volatility
modeling that feeds into both the ensemble and risk management.
"""

import logging

import numpy as np

logger = logging.getLogger("predmarket.volatility")


class VolatilityModel:
    """GARCH(1,1) volatility model for prediction market price series.

    Fits a GARCH(1,1) model to price returns using the `arch` package.
    Provides conditional volatility forecasts, regime change detection,
    and volatility feature extraction for the ensemble.

    Usage:
        vm = VolatilityModel()
        vm.fit(line_history)
        cond_vol, ann_vol = vm.forecast_volatility(horizon=1)
        features = vm.get_volatility_features(line_history)
    """

    def __init__(self):
        self._fitted = False
        self._residual_variance: float = 0.0
        self._conditional_volatility: float = 0.0
        self._params: dict[str, float] = {}
        self._last_returns: np.ndarray | None = None

    def fit(self, line_history: list[float]) -> "VolatilityModel":
        """Fit GARCH(1,1) to a price series.

        Converts prices to log-returns, then fits a GARCH(1,1) model.
        Falls back to simple rolling volatility if the series is too short
        or the arch package fails.

        Args:
            line_history: List of historical mid-prices.

        Returns:
            self (for chaining).
        """
        if len(line_history) < 3:
            self._fallback_fit(line_history)
            return self

        prices = np.array(line_history, dtype=float)
        # Compute log-returns; prediction markets are bounded [0,1],
        # so use simple returns instead to avoid log(0) issues
        returns = np.diff(prices)
        returns = returns[np.isfinite(returns)]

        if len(returns) < 2:
            self._fallback_fit(line_history)
            return self

        try:
            from arch import arch_model

            # Scale returns by 100 for numerical stability (standard practice)
            scaled_returns = returns * 100.0
            am = arch_model(scaled_returns, vol="Garch", p=1, q=1, mean="Zero", dist="normal")
            res = am.fit(disp="off", show_warning=False)

            self._params = {
                "omega": float(res.params.get("omega", 0.1)),
                "alpha": float(res.params.get("alpha[1]", 0.1)),
                "beta": float(res.params.get("beta[1]", 0.85)),
            }

            # Conditional volatility at the end of the sample (unscale back)
            self._conditional_volatility = float(res.conditional_volatility[-1] / 100.0)
            self._residual_variance = float(np.var(res.resid / 100.0))
            self._last_returns = returns
            self._fitted = True

            logger.debug(
                f"GARCH(1,1) fitted: omega={self._params['omega']:.6f}, "
                f"alpha={self._params['alpha']:.4f}, beta={self._params['beta']:.4f}, "
                f"cond_vol={self._conditional_volatility:.6f}"
            )

        except Exception as e:
            logger.debug(f"GARCH fit failed ({e}), falling back to rolling volatility")
            self._fallback_fit(line_history)

        return self

    def _fallback_fit(self, line_history: list[float]):
        """Fallback: use simple rolling standard deviation as volatility estimate."""
        prices = np.array(line_history, dtype=float)
        if len(prices) < 2:
            self._conditional_volatility = 0.02
            self._residual_variance = 0.0004
        else:
            returns = np.diff(prices)
            self._conditional_volatility = float(np.std(returns)) if len(returns) > 1 else 0.02
            self._residual_variance = float(np.var(returns)) if len(returns) > 1 else 0.0004
        self._params = {"omega": 0.1, "alpha": 0.1, "beta": 0.85}
        self._last_returns = np.diff(prices) if len(prices) >= 2 else np.array([0.0])
        self._fitted = True

    def forecast_volatility(self, horizon: int = 1) -> tuple[float, float]:
        """Forecast conditional volatility at the given horizon.

        Uses the GARCH(1,1) recursion:
            sigma^2_t = omega + alpha * r^2_{t-1} + beta * sigma^2_{t-1}

        For multi-step forecasts, the expected return is replaced by
        the unconditional variance in the recursion.

        Args:
            horizon: Number of steps ahead to forecast.

        Returns:
            Tuple of (conditional_volatility, annualized_volatility).
            For prediction markets, "annualized" means scaled by sqrt(8760)
            assuming hourly updates.
        """
        if not self._fitted:
            return 0.02, 0.02 * np.sqrt(8760)

        omega = self._params.get("omega", 0.1)
        alpha = self._params.get("alpha", 0.1)
        beta = self._params.get("beta", 0.85)

        # Start from last known conditional variance
        cond_var = (self._conditional_volatility * 100.0) ** 2
        uncond_var = omega / (1.0 - alpha - beta) if (alpha + beta) < 1.0 else cond_var

        for _ in range(horizon):
            # For multi-step, expected squared return = unconditional variance
            cond_var = omega + alpha * uncond_var + beta * cond_var

        cond_vol = np.sqrt(cond_var) / 100.0  # Unscale
        # Annualize assuming ~8760 hourly observations per year
        annualized_vol = cond_vol * np.sqrt(8760)

        return float(cond_vol), float(annualized_vol)

    def detect_regime_change(
        self,
        line_history: list[float],
        window: int = 10,
        threshold: float = 2.0,
    ) -> bool:
        """Detect if recent volatility indicates a regime change.

        Compares recent rolling volatility (last `window` periods) against
        the preceding period's volatility. If recent vol exceeds threshold *
        the baseline (pre-recent) volatility, a regime change is flagged.

        This compares recent vs. prior volatility rather than recent vs. full-sample,
        so it correctly detects spikes even when the full sample is dominated by
        the volatile period.

        Args:
            line_history: Historical price series.
            window: Number of recent periods to check.
            threshold: Multiplier over baseline volatility that triggers detection.

        Returns:
            True if regime change detected, False otherwise.
        """
        prices = np.array(line_history, dtype=float)
        if len(prices) < window + 2:
            return False

        returns = np.diff(prices)
        if len(returns) < window + 1:
            return False

        # Baseline: volatility of everything BEFORE the recent window
        baseline_returns = returns[:-window]
        recent_returns = returns[-window:]

        if len(baseline_returns) < 2:
            return False

        baseline_vol = float(np.std(baseline_returns))
        if baseline_vol < 1e-8:
            # Flat market followed by movement → likely regime change
            return float(np.std(recent_returns)) > 1e-4

        recent_vol = float(np.std(recent_returns))
        ratio = recent_vol / baseline_vol

        return ratio > threshold

    def get_volatility_features(self, line_history: list[float]) -> dict[str, float]:
        """Extract volatility features from a price series.

        Computes multiple volatility estimators that capture different
        aspects of price dynamics. These features can be fed into the
        ensemble or ML models as additional signals.

        Args:
            line_history: Historical price series.

        Returns:
            Dict with volatility features:
                - realized_vol: Standard deviation of returns
                - parkinson_vol: Parkinson (1980) range-based estimator
                - garman_klass_vol: Garman-Klass (1980) OHLC estimator
                  (approximated from consecutive price pairs)
                - rolling_std_5: Rolling 5-period std of returns
                - rolling_std_10: Rolling 10-period std of returns
        """
        prices = np.array(line_history, dtype=float)
        features = {
            "realized_vol": 0.0,
            "parkinson_vol": 0.0,
            "garman_klass_vol": 0.0,
            "rolling_std_5": 0.0,
            "rolling_std_10": 0.0,
        }

        if len(prices) < 2:
            return features

        returns = np.diff(prices)

        # 1. Realized volatility (standard deviation of returns)
        features["realized_vol"] = float(np.std(returns)) if len(returns) > 1 else 0.0

        # 2. Parkinson volatility using consecutive high-low pairs
        # For prediction markets, use rolling windows as pseudo-bars
        window = min(5, len(prices) - 1)
        if window >= 2:
            parkinson_vals = []
            for i in range(0, len(prices) - window, window):
                chunk = prices[i : i + window + 1]
                hi = np.max(chunk)
                lo = np.min(chunk)
                if hi > 0:
                    parkinson_vals.append((np.log(hi) - np.log(max(lo, 1e-6))) ** 2)
            if parkinson_vals:
                # Parkinson vol = sqrt(1/(4*n*ln(2)) * sum(ln(H/L)^2))
                features["parkinson_vol"] = float(
                    np.sqrt(np.mean(parkinson_vals) / (4.0 * np.log(2.0)))
                )

        # 3. Garman-Klass volatility (approximated)
        # Uses rolling window high/low/open/close
        window_gk = min(5, len(prices) - 1)
        if window_gk >= 2:
            gk_vals = []
            for i in range(0, len(prices) - window_gk, window_gk):
                chunk = prices[i : i + window_gk + 1]
                o = chunk[0]
                c = chunk[-1]
                h = np.max(chunk)
                l = np.min(chunk)
                if o > 0 and l > 0:
                    log_hl = np.log(h / max(l, 1e-6))
                    log_co = np.log(c / max(o, 1e-6))
                    gk_vals.append(0.5 * log_hl**2 - (2 * np.log(2) - 1) * log_co**2)
            if gk_vals:
                val = np.mean(gk_vals)
                features["garman_klass_vol"] = float(np.sqrt(max(val, 0.0)))

        # 4. Rolling standard deviations
        if len(returns) >= 5:
            features["rolling_std_5"] = float(np.std(returns[-5:]))
        else:
            features["rolling_std_5"] = features["realized_vol"]

        if len(returns) >= 10:
            features["rolling_std_10"] = float(np.std(returns[-10:]))
        else:
            features["rolling_std_10"] = features["realized_vol"]

        return features

    def analyze(self, line_history: list[float]) -> dict[str, float]:
        """Fit/update volatility state and return pipeline-facing features."""
        self.fit(line_history)
        conditional_vol, annualized_vol = self.forecast_volatility(horizon=1)
        features = self.get_volatility_features(line_history)
        features.update(
            {
                "conditional_vol": conditional_vol,
                "annualized_vol": annualized_vol,
                "regime_change": 1.0 if self.detect_regime_change(line_history) else 0.0,
            }
        )
        return features

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    @property
    def conditional_volatility(self) -> float:
        return self._conditional_volatility

    @property
    def params(self) -> dict[str, float]:
        return dict(self._params)
