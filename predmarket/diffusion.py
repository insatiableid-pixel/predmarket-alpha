"""S-curve / innovation diffusion modeling for prediction market liquidity.

Implements Petropoulos et al. (2022) §2.3.19 (innovation diffusion models)
and §2.3.20 (synchronic and diachronic competition). Models the lifecycle
of prediction market liquidity using logistic growth and Bass diffusion.

Use case: A sharp bettor needs to know whether a market is still growing
(early adopter phase), maturing, or past peak liquidity. Position sizing
must account for the fact that exiting a position in an illiquid, declining
market is costly.
"""

import logging
from typing import Any

import numpy as np
from scipy.optimize import curve_fit

logger = logging.getLogger("predmarket.diffusion")


# ---------------------------------------------------------------------------
# Logistic Growth Model (§2.3.19)
# ---------------------------------------------------------------------------


class LogisticGrowthModel:
    """Three-parameter logistic growth model: L / (1 + exp(-k * (t - t0))).

    Parameters:
        L: Carrying capacity (saturation ceiling).
        k: Growth rate.
        t0: Inflection point (time of maximum growth).

    Typical use: model open interest or volume of a prediction market
    over its lifetime.
    """

    def __init__(self):
        self.L: float = 0.0
        self.k: float = 0.0
        self.t0: float = 0.0
        self._fitted = False

    @staticmethod
    def _logistic(t: np.ndarray, L: float, k: float, t0: float) -> np.ndarray:
        """Logistic function."""
        return L / (1.0 + np.exp(-k * (t - t0)))

    def fit(
        self,
        time_points: list[float],
        values: list[float],
        p0: tuple[float, float, float] | None = None,
    ) -> None:
        """Fit logistic curve to observed data.

        Args:
            time_points: Chronological time values (e.g., days since launch).
            values: Observed metric values (e.g., open interest in USD).
            p0: Optional initial parameter guess (L, k, t0). If None,
                estimated from the data.

        Raises:
            ValueError: If fewer than 4 data points or curve_fit fails.
        """
        t = np.asarray(time_points, dtype=float)
        y = np.asarray(values, dtype=float)

        if len(t) < 4:
            raise ValueError("Need at least 4 data points to fit logistic curve.")

        if p0 is None:
            # Estimate initial parameters from data
            L_est = float(np.max(y)) * 1.2  # Ceiling slightly above observed max
            k_est = 0.1
            t0_est = float(np.median(t))
            p0 = (L_est, k_est, t0_est)

        try:
            bounds = ([0, 0, -np.inf], [np.inf, np.inf, np.inf])
            params, _ = curve_fit(self._logistic, t, y, p0=p0, bounds=bounds, maxfev=10000)
            self.L, self.k, self.t0 = float(params[0]), float(params[1]), float(params[2])
            self._fitted = True
            logger.info(
                "Logistic model fitted: L=%.2f, k=%.4f, t0=%.2f",
                self.L,
                self.k,
                self.t0,
            )
        except RuntimeError as e:
            logger.warning("Logistic curve fit failed: %s", e)
            # Fall back to simple estimates
            self.L = float(np.max(y))
            self.k = 0.01
            self.t0 = float(np.mean(t))
            self._fitted = False

    def predict(self, t: float) -> float:
        """Predict value at time t.

        Args:
            t: Time point.

        Returns:
            Predicted value. Returns 0 if model not fitted.
        """
        if not self._fitted:
            return 0.0
        return float(self._logistic(np.array([t]), self.L, self.k, self.t0)[0])

    def predict_saturation(self) -> float:
        """Return estimated ceiling (L parameter)."""
        return self.L

    def predict_time_to_percent(self, pct: float) -> float:
        """Estimate time to reach a given percentage of saturation.

        Args:
            pct: Target percentage (0-1). E.g., 0.8 for 80% saturation.

        Returns:
            Estimated time point. Returns inf if k is zero.
        """
        if self.k == 0 or not self._fitted:
            return float("inf")
        target = self.L * pct
        # L / (1 + exp(-k*(t-t0))) = target
        # 1 + exp(-k*(t-t0)) = L / target
        # -k*(t-t0) = ln(L/target - 1)
        # t = t0 - ln(L/target - 1) / k
        ratio = self.L / max(target, 1e-10) - 1.0
        if ratio <= 0:
            return self.t0
        return self.t0 - np.log(ratio) / self.k


# ---------------------------------------------------------------------------
# Bass Diffusion Model (§2.3.19 extended)
# ---------------------------------------------------------------------------


class BassDiffusionModel:
    """Bass diffusion model for adopter dynamics.

    Models the rate of new adoption as:
        n(t) = (p + q * F(t)) * (M - N(t))
    where F(t) = cumulative adoption fraction.

    Parameters:
        p: Coefficient of innovation (external influence).
        q: Coefficient of imitation (internal / word-of-mouth).
        M: Market potential (total eventual adopters).
    """

    def __init__(self):
        self.p: float = 0.0
        self.q: float = 0.0
        self.M: float = 0.0
        self._fitted = False

    @staticmethod
    def _bass_cumulative(t: np.ndarray, p: float, q: float, M: float) -> np.ndarray:
        """Cumulative adoption N(t) for the Bass model.

        N(t) = M * (1 - exp(-(p+q)*t)) / (1 + (q/p)*exp(-(p+q)*t))
        """
        if abs(p + q) < 1e-12:
            return np.full_like(t, M, dtype=float)
        exponent = np.exp(-(p + q) * t)
        numerator = M * (1.0 - exponent)
        denominator = 1.0 + (q / max(p, 1e-12)) * exponent
        return numerator / np.maximum(denominator, 1e-12)

    def fit(
        self,
        time_points: list[float],
        adopters: list[float],
        p0: tuple[float, float, float] | None = None,
    ) -> None:
        """Fit Bass model to cumulative adoption data.

        Args:
            time_points: Chronological time values.
            adopters: Cumulative adopter counts at each time point.
            p0: Optional initial guess (p, q, M).

        Raises:
            ValueError: If fewer than 4 data points.
        """
        t = np.asarray(time_points, dtype=float)
        y = np.asarray(adopters, dtype=float)

        if len(t) < 4:
            raise ValueError("Need at least 4 data points for Bass model.")

        if p0 is None:
            M_est = float(np.max(y)) * 1.5
            p_est = 0.01
            q_est = 0.3
            p0 = (p_est, q_est, M_est)

        try:
            bounds = ([0, 0, 0], [1, 1, np.inf])
            params, _ = curve_fit(self._bass_cumulative, t, y, p0=p0, bounds=bounds, maxfev=10000)
            self.p, self.q, self.M = (
                float(params[0]),
                float(params[1]),
                float(params[2]),
            )
            self._fitted = True
            logger.info(
                "Bass model fitted: p=%.4f, q=%.4f, M=%.2f",
                self.p,
                self.q,
                self.M,
            )
        except RuntimeError as e:
            logger.warning("Bass model fit failed: %s", e)
            self.M = float(np.max(y))
            self.p = 0.01
            self.q = 0.3
            self._fitted = False

    def predict(self, t: float) -> float:
        """Predict cumulative adopters at time t."""
        if not self._fitted:
            return 0.0
        return float(self._bass_cumulative(np.array([t]), self.p, self.q, self.M)[0])

    def get_params(self) -> dict[str, float]:
        """Return fitted parameters."""
        return {"p": self.p, "q": self.q, "M": self.M}


# ---------------------------------------------------------------------------
# Market Liquidity Lifecycle Model
# ---------------------------------------------------------------------------


class MarketLiquidityModel:
    """Models prediction market liquidity evolution using logistic growth.

    Fits a logistic curve to historical open interest data and classifies
    the market's lifecycle stage. Used for:
    - Position sizing (avoid entering declining markets)
    - Exit planning (estimate when liquidity will drop below threshold)
    - New market assessment (predict peak liquidity before entering)
    """

    # Lifecycle stages based on percent of saturation
    _STAGE_EARLY = (0.0, 0.2)  # Early adopter phase
    _STAGE_GROWTH = (0.2, 0.5)  # Rapid growth
    _STAGE_MATURE = (0.5, 0.8)  # Mature, stable liquidity
    _STAGE_DECLINING = (0.8, 1.5)  # Past peak or approaching ceiling

    def estimate_liquidity_trajectory(self, historical_oi: list[float]) -> dict[str, Any]:
        """Fit logistic model to open interest history and classify lifecycle stage.

        Args:
            historical_oi: Chronological list of open interest values (USD).

        Returns:
            Dict with keys:
                current_stage: One of "early", "growth", "mature", "declining".
                predicted_peak_oi: Estimated saturation ceiling (L parameter).
                time_to_80pct: Estimated time index to reach 80% of peak.
                current_pct: Current OI as fraction of predicted peak.
                model: Fitted LogisticGrowthModel instance.
                r_squared: Goodness of fit (1.0 = perfect).

        Raises:
            ValueError: If fewer than 4 data points.
        """
        if len(historical_oi) < 4:
            raise ValueError("Need at least 4 OI observations.")

        t = list(range(len(historical_oi)))
        model = LogisticGrowthModel()
        model.fit(t, historical_oi)

        current_oi = historical_oi[-1]
        peak_oi = model.predict_saturation()
        current_pct = current_oi / max(peak_oi, 1.0)

        # Classify stage
        stage = "declining"
        for name, (lo, hi) in [
            ("early", self._STAGE_EARLY),
            ("growth", self._STAGE_GROWTH),
            ("mature", self._STAGE_MATURE),
            ("declining", self._STAGE_DECLINING),
        ]:
            if lo <= current_pct < hi:
                stage = name
                break

        # Time to 80% saturation (from current time index)
        t_now = float(len(historical_oi) - 1)
        t_80 = model.predict_time_to_percent(0.8)
        time_to_80 = max(0.0, t_80 - t_now)

        # Compute R-squared
        predicted = [model.predict(float(i)) for i in t]
        ss_res = sum((o - p) ** 2 for o, p in zip(historical_oi, predicted))
        ss_tot = sum((o - np.mean(historical_oi)) ** 2 for o in historical_oi)
        r_squared = 1.0 - ss_res / max(ss_tot, 1e-10)

        return {
            "current_stage": stage,
            "predicted_peak_oi": peak_oi,
            "time_to_80pct": time_to_80,
            "current_pct": current_pct,
            "model": model,
            "r_squared": r_squared,
        }

    def is_market_mature(
        self,
        current_oi: float,
        predicted_peak: float,
        threshold: float = 0.8,
    ) -> bool:
        """Check whether a market has reached maturity.

        Args:
            current_oi: Current open interest.
            predicted_peak: Estimated peak open interest from logistic model.
            threshold: Fraction of peak to consider "mature" (default 80%).

        Returns:
            True if current OI >= threshold * predicted_peak.
        """
        if predicted_peak <= 0:
            return False
        return current_oi >= threshold * predicted_peak
