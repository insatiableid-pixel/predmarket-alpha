"""Multi-resolution forecasting for different time horizons.

Implements Petropoulos et al. (2022) §2.10.2 (temporal aggregation) and
§2.7.7 (multi-step ahead forecasting). Adjusts forecast uncertainty
based on distance-to-resolution, producing wider prediction intervals
for longer horizons.
"""

import logging
from enum import Enum
from typing import Any

import numpy as np

from predmarket.density import DensityForecast, from_point_estimate

logger = logging.getLogger("predmarket.horizons")


class ForecastHorizon(Enum):
    """Standard forecast horizons aligned with prediction market resolution times."""

    INTRADAY = "1h"  # ~1 hour to resolution
    SHORT = "1d"  # ~1 day
    MEDIUM = "7d"  # ~1 week
    LONG = "30d"  # ~1 month


# Multipliers applied to base uncertainty for each horizon.
# Longer horizons are inherently less certain.
_HORIZON_UNCERTAINTY_SCALE: dict[ForecastHorizon, float] = {
    ForecastHorizon.INTRADAY: 0.5,
    ForecastHorizon.SHORT: 1.0,
    ForecastHorizon.MEDIUM: 2.0,
    ForecastHorizon.LONG: 4.0,
}

# Seconds per horizon (used for automatic mapping)
_HORIZON_SECONDS: dict[ForecastHorizon, float] = {
    ForecastHorizon.INTRADAY: 3600.0,
    ForecastHorizon.SHORT: 86400.0,
    ForecastHorizon.MEDIUM: 604800.0,
    ForecastHorizon.LONG: 2592000.0,
}


class HorizonSpecificForecaster:
    """Wraps a base forecaster to produce horizon-adjusted density forecasts.

    The base forecaster provides a point estimate. This layer adds
    uncertainty that scales with the forecast horizon, converting a
    single probability into a calibrated DensityForecast with
    prediction intervals.

    Args:
        base_forecaster: Any object with a callable
            ``forecast(snapshot, category) -> float`` method that
            returns a probability in [0, 1].
    """

    def __init__(self, base_forecaster: Any):
        self.base_forecaster = base_forecaster

    def forecast_with_horizon(
        self,
        snapshot: Any,
        category: str,
        horizon: ForecastHorizon,
        base_uncertainty: float = 0.1,
    ) -> DensityForecast:
        """Generate a density forecast adjusted for the given horizon.

        Args:
            snapshot: MarketSnapshot or compatible object.
            category: Market category string.
            horizon: Target forecast horizon.
            base_uncertainty: Baseline uncertainty at SHORT horizon.

        Returns:
            DensityForecast with horizon-scaled uncertainty.
        """
        point = self.base_forecaster.forecast(snapshot, category)
        return self._apply_horizon_adjustment(point, horizon, base_uncertainty)

    def _apply_horizon_adjustment(
        self,
        point_forecast: float,
        horizon: ForecastHorizon,
        base_uncertainty: float = 0.1,
    ) -> DensityForecast:
        """Scale uncertainty based on horizon distance.

        Intraday: 0.5x base uncertainty (tighter intervals).
        Short:    1.0x (baseline).
        Medium:   2.0x (wider).
        Long:     4.0x (widest).

        The scaling is applied to the Beta concentration parameter,
        which inversely controls spread.

        Args:
            point_forecast: Central probability estimate.
            horizon: Target horizon.
            base_uncertainty: Baseline uncertainty at SHORT horizon.

        Returns:
            DensityForecast with appropriately scaled intervals.
        """
        scale = _HORIZON_UNCERTAINTY_SCALE[horizon]
        adjusted_uncertainty = np.clip(base_uncertainty * scale, 0.01, 0.45)
        return from_point_estimate(point_forecast, uncertainty=adjusted_uncertainty)

    def forecast_all_horizons(
        self,
        snapshot: Any,
        category: str,
        base_uncertainty: float = 0.1,
    ) -> dict[ForecastHorizon, DensityForecast]:
        """Generate forecasts at all four standard horizons.

        Returns:
            Dict mapping each ForecastHorizon to its DensityForecast.
        """
        point = self.base_forecaster.forecast(snapshot, category)
        return {
            h: self._apply_horizon_adjustment(point, h, base_uncertainty) for h in ForecastHorizon
        }


class HorizonWeightScheduler:
    """Determines which horizon(s) to weight most based on time-to-resolution.

    Uses a softmax over horizon distances to produce smooth blending
    weights that peak at the nearest appropriate horizon.
    """

    @staticmethod
    def get_recommended_horizon(time_to_resolution: float) -> ForecastHorizon:
        """Select the single best horizon for a given time-to-resolution.

        Args:
            time_to_resolution: Seconds until the market resolves.

        Returns:
            The closest ForecastHorizon.
        """
        best = ForecastHorizon.SHORT
        best_dist = float("inf")
        for h, secs in _HORIZON_SECONDS.items():
            dist = abs(time_to_resolution - secs)
            if dist < best_dist:
                best_dist = dist
                best = h
        return best

    @staticmethod
    def get_horizon_weights(
        time_to_resolution: float, temperature: float = 1.0
    ) -> dict[ForecastHorizon, float]:
        """Compute softmax weights over horizons based on time-to-resolution.

        The closer a horizon's typical duration is to the actual
        time-to-resolution, the higher its weight.

        Args:
            time_to_resolution: Seconds until market resolution.
            temperature: Softmax temperature. Lower = sharper selection.
                Default 1.0 gives moderate blending.

        Returns:
            Dict mapping each ForecastHorizon to its weight (sums to 1.0).
        """
        if temperature <= 0:
            temperature = 0.1

        # Compute negative log-distance for each horizon
        log_scores: dict[ForecastHorizon, float] = {}
        for h, secs in _HORIZON_SECONDS.items():
            ratio = max(time_to_resolution, 1.0) / max(secs, 1.0)
            # Score peaks when ratio=1 (exact match), falls off smoothly
            log_scores[h] = -abs(np.log(ratio))

        # Softmax
        max_score = max(log_scores.values())
        exp_scores = {h: np.exp((s - max_score) / temperature) for h, s in log_scores.items()}
        total = sum(exp_scores.values())
        return {h: s / total for h, s in exp_scores.items()}
