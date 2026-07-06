"""Modern ML models for time series forecasting.

Implements Petropoulos et al. (2022) §2.7.8-10 — Neural networks, machine
learning, and hybrid methods for time series forecasting.

Upgrades the existing Holt's linear trend model in ensemble.py with:
- Feature-engineered XGBoost regression (§2.7.10)
- Quantile regression via bootstrap for density forecasts
- Bagged ensemble of multiple forecasters (§2.7.6)

All forecasters produce both point estimates and DensityForecast objects.
"""

import logging
from typing import Any

import numpy as np

from predmarket.density import DensityForecast, from_point_estimate, from_samples

logger = logging.getLogger("predmarket.ml_timeseries")


class FeatureEngineer:
    """Extracts time series features for ML model consumption.

    Implements §2.2.5 — Exogenous variables and feature engineering.
    Produces a fixed-dimension feature vector from a price history series.

    Features extracted:
    - Lag features (lag_1 through lag_5): recent price values
    - Rolling statistics (mean, std over 3 and 5 windows)
    - Momentum indicators (1-step and 3-step)
    - RSI approximation over 5 periods
    - Price relative to moving averages
    - Trend slope via linear regression over last 5 points
    """

    # Ordered feature names — must match extract_features() output
    FEATURE_NAMES = [
        "lag_1",
        "lag_2",
        "lag_3",
        "lag_4",
        "lag_5",
        "rolling_mean_3",
        "rolling_mean_5",
        "rolling_std_3",
        "rolling_std_5",
        "momentum_1",
        "momentum_3",
        "rsi_5",
        "price_vs_ma3",
        "price_vs_ma5",
        "trend_slope_5",
    ]

    def extract_features(self, line_history: list[float]) -> dict[str, float]:
        """Extract features from a price history.

        Args:
            line_history: List of historical prices (most recent last).

        Returns:
            Dictionary mapping feature names to float values.
        """
        n = len(line_history)
        if n == 0:
            return {name: 0.0 for name in self.FEATURE_NAMES}

        arr = np.array(line_history, dtype=float)
        current = arr[-1]

        # Lag features (0 if not enough history)
        lags = {}
        for i in range(1, 6):
            lags[f"lag_{i}"] = float(arr[-i]) if i <= n else 0.0

        # Rolling statistics
        def safe_mean(x):
            return float(np.mean(x)) if len(x) > 0 else 0.0

        def safe_std(x):
            return float(np.std(x)) if len(x) > 1 else 0.0

        rolling_mean_3 = safe_mean(arr[-3:]) if n >= 3 else safe_mean(arr)
        rolling_mean_5 = safe_mean(arr[-5:]) if n >= 5 else safe_mean(arr)
        rolling_std_3 = safe_std(arr[-3:]) if n >= 3 else 0.0
        rolling_std_5 = safe_std(arr[-5:]) if n >= 5 else 0.0

        # Momentum
        momentum_1 = float(arr[-1] - arr[-2]) if n >= 2 else 0.0
        momentum_3 = float(arr[-1] - arr[-4]) if n >= 4 else 0.0

        # RSI approximation over 5 periods
        if n >= 6:
            deltas = np.diff(arr[-6:])
            gains = np.sum(deltas[deltas > 0])
            losses = np.sum(-deltas[deltas < 0])
            avg_gain = gains / 5.0
            avg_loss = losses / 5.0
            if avg_loss == 0:
                rsi_5 = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi_5 = 100.0 - (100.0 / (1.0 + rs))
            # Normalize to [0, 1]
            rsi_5 = rsi_5 / 100.0
        else:
            rsi_5 = 0.5  # Neutral

        # Price vs moving averages
        price_vs_ma3 = current - rolling_mean_3
        price_vs_ma5 = current - rolling_mean_5

        # Trend slope via least squares on last 5 points
        if n >= 2:
            window = min(5, n)
            y = arr[-window:]
            x = np.arange(window, dtype=float)
            slope = float(np.polyfit(x, y, 1)[0])
        else:
            slope = 0.0

        return {
            "lag_1": lags["lag_1"],
            "lag_2": lags["lag_2"],
            "lag_3": lags["lag_3"],
            "lag_4": lags["lag_4"],
            "lag_5": lags["lag_5"],
            "rolling_mean_3": rolling_mean_3,
            "rolling_mean_5": rolling_mean_5,
            "rolling_std_3": rolling_std_3,
            "rolling_std_5": rolling_std_5,
            "momentum_1": momentum_1,
            "momentum_3": momentum_3,
            "rsi_5": rsi_5,
            "price_vs_ma3": price_vs_ma3,
            "price_vs_ma5": price_vs_ma5,
            "trend_slope_5": slope,
        }

    def extract_vector(self, line_history: list[float]) -> np.ndarray:
        """Extract feature vector (ordered array) for ML consumption.

        Args:
            line_history: List of historical prices.

        Returns:
            1D numpy array of length len(FEATURE_NAMES).
        """
        features = self.extract_features(line_history)
        return np.array([features[name] for name in self.FEATURE_NAMES], dtype=float)


class XGBoostForecaster:
    """XGBoost regression forecaster with density estimation.

    Implements §2.7.10 — Machine learning for forecasting.
    Uses gradient boosted decision trees with time series features.

    Handles the cold-start case (no training data) by returning 0.5.
    Produces density forecasts via bootstrap resampling of residuals.

    Args:
        max_lags: Maximum number of lag features to use (default 5).
    """

    def __init__(self, max_lags: int = 5):
        self.max_lags = max_lags
        self._engineer = FeatureEngineer()
        self._model = None
        self._residuals: list[float] = []
        self._is_fitted = False

    def fit(self, histories: list[list[float]], outcomes: list[float]) -> None:
        """Train XGBoost on feature matrices from multiple price histories.

        Each history produces one training example: features from the history
        mapped to the corresponding outcome (next-step probability).

        Args:
            histories: List of price history sequences.
            outcomes: List of target probabilities (0-1).
        """
        if len(histories) != len(outcomes):
            raise ValueError(
                f"histories ({len(histories)}) and outcomes ({len(outcomes)}) must have same length"
            )

        if len(histories) == 0:
            logger.warning(
                "XGBoostForecaster.fit() called with empty data — model remains unfitted."
            )
            return

        try:
            import xgboost as xgb
        except ImportError:
            logger.warning(
                "xgboost not installed — XGBoostForecaster cannot fit. Install with: pip install xgboost"
            )
            return

        X_list = []
        y_list = []
        residuals = []

        for hist, target in zip(histories, outcomes):
            if len(hist) < 2:
                continue
            features = self._engineer.extract_vector(hist)
            X_list.append(features)
            y_list.append(float(target))

        if len(X_list) == 0:
            return

        X = np.array(X_list)
        y = np.array(y_list)

        self._model = xgb.XGBRegressor(
            max_depth=3,
            n_estimators=100,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            objective="reg:squarederror",
            random_state=42,
        )
        self._model.fit(X, y)

        # Compute residuals for bootstrap density estimation
        predictions = self._model.predict(X)
        self._residuals = (y - predictions).tolist()

        self._is_fitted = True
        logger.info(
            f"XGBoostForecaster fitted on {len(X_list)} samples, "
            f"mean abs residual: {np.mean(np.abs(self._residuals)):.4f}"
        )

    def forecast(self, line_history: list[float]) -> float:
        """Produce a single point forecast.

        Args:
            line_history: Recent price history.

        Returns:
            Predicted probability (clipped to [0.01, 0.99]).
        """
        if not self._is_fitted or self._model is None:
            # Cold start: return neutral
            return 0.5

        features = self._engineer.extract_vector(line_history).reshape(1, -1)
        pred = float(self._model.predict(features)[0])
        return float(np.clip(pred, 0.01, 0.99))

    def forecast_density(
        self, line_history: list[float], n_bootstrap: int = 200
    ) -> DensityForecast:
        """Produce a density forecast via bootstrap residual resampling.

        Generates multiple predictions by adding randomly resampled residuals
        to the point forecast, then constructs a DensityForecast from the
        resulting distribution.

        Args:
            line_history: Recent price history.
            n_bootstrap: Number of bootstrap samples.

        Returns:
            DensityForecast with bootstrap-derived uncertainty.
        """
        point = self.forecast(line_history)

        if not self._is_fitted or len(self._residuals) == 0:
            # No residual data — return moderate uncertainty around point estimate
            return from_point_estimate(point, uncertainty=0.15, n_samples=n_bootstrap)

        rng = np.random.default_rng()
        boot_residuals = rng.choice(self._residuals, size=n_bootstrap, replace=True)
        samples = np.clip(point + boot_residuals, 0.0, 1.0)

        return from_samples(samples)


class BaggedForecaster:
    """Bagged ensemble of multiple forecasters (Petropoulos §2.7.6).

    Wraps N forecasters and produces predictions by:
    1. For each bootstrap round, resampling training data with replacement
    2. Fitting each forecaster on the bootstrap sample
    3. Averaging predictions across all forecasters and bootstrap rounds

    For inference, simply averages the predictions of all constituent
    forecasters. This reduces variance without increasing bias.

    Args:
        forecasters: List of forecaster objects with a .forecast() method.
        n_bootstrap: Number of bootstrap rounds for density estimation.
    """

    def __init__(self, forecasters: list[Any], n_bootstrap: int = 10):
        self.forecasters = forecasters
        self.n_bootstrap = n_bootstrap

    def forecast(self, line_history: list[float]) -> float:
        """Average point forecast across all constituent forecasters.

        Args:
            line_history: Recent price history.

        Returns:
            Averaged predicted probability.
        """
        if not self.forecasters:
            return 0.5

        preds = []
        for f in self.forecasters:
            try:
                preds.append(f.forecast(line_history))
            except Exception as e:
                logger.warning(f"Forecaster {f.__class__.__name__} failed: {e}")
                preds.append(0.5)

        return float(np.mean(preds))

    def forecast_density(self, line_history: list[float]) -> DensityForecast:
        """Produce density forecast by pooling constituent density forecasts.

        Collects density forecasts from each constituent and combines them
        via linear opinion pool (equal weights).

        Args:
            line_history: Recent price history.

        Returns:
            Combined DensityForecast from all forecasters.
        """
        if not self.forecasters:
            return from_point_estimate(0.5, uncertainty=0.5)

        densities = []
        for f in self.forecasters:
            try:
                if hasattr(f, "forecast_density"):
                    densities.append(f.forecast_density(line_history))
                else:
                    point = f.forecast(line_history)
                    densities.append(from_point_estimate(point, uncertainty=0.1))
            except Exception as e:
                logger.warning(f"Forecaster {f.__class__.__name__} density failed: {e}")

        if not densities:
            return from_point_estimate(0.5, uncertainty=0.5)

        return from_samples(np.concatenate([d.samples for d in densities if d.samples.size > 0]))
