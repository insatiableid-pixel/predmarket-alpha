"""Multi-platform forecast aggregation.

Implements Petropoulos et al. (2022) §2.6.4 — The wisdom of crowds,
§2.6.1 — Forecast combination, and §3.8.5 — Elections forecasting.

Aggregates forecasts from external prediction platforms (Metaculus, Manifold,
Polymarket, etc.) using calibration-weighted linear opinion pooling.

The key insight: different platforms attract different crowds with different
biases structures. A weighted average of well-calibrated platforms outperforms
any single platform (Bates & Granger, 1969; Clemen, 1989).
"""

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from predmarket.density import DensityForecast, combine_density_forecasts, from_point_estimate

logger = logging.getLogger("predmarket.aggregator")


@dataclass
class ExternalForecast:
    """A single forecast observation from an external prediction platform.

    Attributes:
        platform: Source platform name (e.g., "metaculus", "manifold").
        contract_id: Contract/market identifier.
        probability: Crowd probability estimate (0-1).
        volume: Trading volume or participation metric (used for weighting).
        n_forecasters: Number of individual forecasters/predictors.
        timestamp: Unix timestamp of this observation.
    """

    platform: str
    contract_id: str
    probability: float
    volume: float = 0.0
    n_forecasters: int = 0
    timestamp: float = field(default_factory=time.time)


class PlatformAggregator:
    """Aggregates forecasts from multiple prediction platforms.

    Uses a linear opinion pool (§2.6.4) with calibration-adapted weights.
    Platforms that historically produce more accurate forecasts receive higher
    weight in the aggregation.

    Calibration is tracked via rolling Brier scores per platform. When a
    platform's forecast for a resolved event is available, update_calibration()
    adjusts its Brier history, which in turn affects aggregation weights.

    The decay_factor controls how much past calibration data matters:
    - decay_factor = 1.0: all history weighted equally
    - decay_factor = 0.95: recent accuracy matters more than old accuracy

    Args:
        decay_factor: Exponential decay for weighting recent vs old calibration data.
    """

    def __init__(self, decay_factor: float = 0.95):
        self.decay_factor = decay_factor
        # Per-contract forecasts: contract_id -> list of ExternalForecast
        self._forecasts: dict[str, list[ExternalForecast]] = {}
        # Per-platform calibration: platform -> list of (brier_score, timestamp)
        self._calibration: dict[str, list[tuple[float, float]]] = {}
        # Per-platform running Brier sum (exponentially decayed)
        self._brier_sum: dict[str, float] = {}
        self._brier_count: dict[str, int] = {}

    def add_forecast(self, forecast: ExternalForecast) -> None:
        """Add an external forecast observation.

        Args:
            forecast: ExternalForecast to record.
        """
        cid = forecast.contract_id
        if cid not in self._forecasts:
            self._forecasts[cid] = []
        self._forecasts[cid].append(forecast)

    def add_forecasts(self, forecasts: list[ExternalForecast]) -> None:
        """Batch add multiple external forecasts.

        Args:
            forecasts: List of ExternalForecast objects.
        """
        for f in forecasts:
            self.add_forecast(f)

    def _get_latest_forecasts(self, contract_id: str) -> list[ExternalForecast]:
        """Get the most recent forecast per platform for a contract.

        Args:
            contract_id: Contract identifier.

        Returns:
            List with at most one forecast per platform (the latest).
        """
        all_fc = self._forecasts.get(contract_id, [])
        if not all_fc:
            return []

        # Keep only the latest per platform
        latest: dict[str, ExternalForecast] = {}
        for fc in all_fc:
            if fc.platform not in latest or fc.timestamp > latest[fc.platform].timestamp:
                latest[fc.platform] = fc

        return list(latest.values())

    def update_calibration(self, platform: str, forecast_prob: float, outcome: int) -> None:
        """Update per-platform calibration with a resolved outcome.

        Args:
            platform: Platform name.
            forecast_prob: The probability the platform assigned.
            outcome: Actual binary outcome (0 or 1).
        """
        brier = (forecast_prob - outcome) ** 2
        now = time.time()

        if platform not in self._brier_sum:
            self._brier_sum[platform] = 0.0
            self._brier_count[platform] = 0

        # Apply decay to existing sum
        self._brier_sum[platform] = self.decay_factor * self._brier_sum[platform] + brier
        self._brier_count[platform] += 1

        # Also store for detailed analysis
        if platform not in self._calibration:
            self._calibration[platform] = []
        self._calibration[platform].append((brier, now))

    def get_platform_weights(self) -> dict[str, float]:
        """Return calibration-weighted aggregation weights per platform.

        Weight = 1 / mean_brier for each platform with calibration data.
        Platforms with no calibration data get equal weight.
        Weights are normalized to sum to 1.0.

        Returns:
            Dict mapping platform name to aggregation weight.
        """
        all_platforms = set()
        for forecasts in self._forecasts.values():
            for fc in forecasts:
                all_platforms.add(fc.platform)

        if not all_platforms:
            return {}

        weights: dict[str, float] = {}
        uncalibrated = []

        for platform in all_platforms:
            count = self._brier_count.get(platform, 0)
            if count > 0:
                mean_brier = self._brier_sum[platform] / count
                # Inverse Brier: lower Brier = higher weight
                weights[platform] = 1.0 / max(mean_brier, 0.001)
            else:
                uncalibrated.append(platform)

        # Assign equal weight to uncalibrated platforms (average of calibrated weights)
        if uncalibrated and weights:
            avg_weight = sum(weights.values()) / len(weights)
            for p in uncalibrated:
                weights[p] = avg_weight
        elif uncalibrated:
            for p in uncalibrated:
                weights[p] = 1.0

        # Normalize
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

        return weights

    def get_aggregated_probability(self, contract_id: str) -> float:
        """Get calibration-weighted aggregated probability for a contract.

        Uses linear opinion pool: weighted average of platform probabilities.
        Falls back to equal weights if no calibration data exists.

        Args:
            contract_id: Contract identifier.

        Returns:
            Aggregated probability estimate, or 0.5 if no data.
        """
        forecasts = self._get_latest_forecasts(contract_id)
        if not forecasts:
            return 0.5

        weights = self.get_platform_weights()
        if not weights:
            # Equal weights
            return float(np.mean([fc.probability for fc in forecasts]))

        total_weight = 0.0
        weighted_sum = 0.0
        for fc in forecasts:
            w = weights.get(fc.platform, 1.0 / len(forecasts))
            weighted_sum += w * fc.probability
            total_weight += w

        if total_weight == 0:
            return 0.5

        return float(np.clip(weighted_sum / total_weight, 0.001, 0.999))

    def get_aggregated_density(self, contract_id: str, n_samples: int = 1000) -> DensityForecast:
        """Get calibration-weighted aggregated density forecast.

        Combines density forecasts from each platform using weighted
        linear opinion pool.

        Args:
            contract_id: Contract identifier.
            n_samples: Samples per component density.

        Returns:
            Combined DensityForecast.
        """
        forecasts = self._get_latest_forecasts(contract_id)
        if not forecasts:
            return from_point_estimate(0.5, uncertainty=0.5, n_samples=n_samples)

        weights_dict = self.get_platform_weights()

        # Build density per platform
        densities = []
        weights_list = []
        for fc in forecasts:
            # Convert platform probability to density with uncertainty
            # inversely proportional to number of forecasters
            uncertainty = 0.1 if fc.n_forecasters > 100 else 0.2
            density = from_point_estimate(
                fc.probability, uncertainty=uncertainty, n_samples=n_samples
            )
            densities.append(density)
            weights_list.append(weights_dict.get(fc.platform, 1.0 / len(forecasts)))

        return combine_density_forecasts(densities, weights=weights_list)

    def aggregate_forecasts(
        self, contract_id: str, category: str = "", n_samples: int = 1000
    ) -> DensityForecast:
        """Pipeline-facing alias returning a density forecast.

        The category argument is accepted for future bucket-specific platform
        calibration and keeps this class compatible with ForecastingPipeline.
        """
        return self.get_aggregated_density(contract_id, n_samples=n_samples)

    def get_platform_prices(self, contract_id: str) -> dict[str, float]:
        """Return the latest probability seen from each external platform."""
        return {
            forecast.platform: float(forecast.probability)
            for forecast in self._get_latest_forecasts(contract_id)
        }

    def record_outcome(self, contract_id: str, outcome: int) -> None:
        """Update calibration for all latest forecasts on a resolved contract."""
        for forecast in self._get_latest_forecasts(contract_id):
            self.update_calibration(forecast.platform, forecast.probability, outcome)

    def get_platform_summary(self) -> dict[str, dict[str, any]]:
        """Return a summary of all known platforms and their calibration.

        Returns:
            Dict mapping platform name to {"mean_brier": float, "n_resolved": int}.
        """
        summary = {}
        all_platforms = set()
        for forecasts in self._forecasts.values():
            for fc in forecasts:
                all_platforms.add(fc.platform)

        for platform in sorted(all_platforms):
            count = self._brier_count.get(platform, 0)
            mean_brier = self._brier_sum.get(platform, 0.0) / count if count > 0 else None
            summary[platform] = {
                "mean_brier": mean_brier,
                "n_resolved": count,
            }

        return summary


class MockPlatformData:
    """Placeholder data fetcher for external prediction platforms.

    Each method returns None by default. These stubs are designed to be
    overridden with real API integrations. The method signatures define
    the contract that real implementations should follow.

    Usage:
        subclass and override fetch_* methods, then pass to PlatformAggregator.
    """

    def fetch_metaculus(self, contract_id: str) -> ExternalForecast | None:
        """Fetch crowd forecast from Metaculus.

        Args:
            contract_id: Contract identifier to look up.

        Returns:
            ExternalForecast or None if unavailable.
        """
        # TODO: Implement real Metaculus API integration
        # API: https://www.metaculus.com/api2/
        return None

    def fetch_manifold(self, contract_id: str) -> ExternalForecast | None:
        """Fetch market probability from Manifold Markets.

        Args:
            contract_id: Contract identifier to look up.

        Returns:
            ExternalForecast or None if unavailable.
        """
        # TODO: Implement real Manifold API integration
        # API: https://docs.manifold.markets/
        return None

    def fetch_polymarket_depth(self, contract_id: str) -> ExternalForecast | None:
        """Fetch orderbook-implied probability from Polymarket.

        Uses the CLOB orderbook to derive a depth-weighted midpoint
        that accounts for bid/ask sizes, not just best bid/ask.

        Args:
            contract_id: Contract identifier to look up.

        Returns:
            ExternalForecast or None if unavailable.
        """
        # TODO: Implement real Polymarket CLOB depth analysis
        # API: https://clob.polymarket.com/
        return None

    def fetch_all_platforms(self, contract_id: str) -> list[ExternalForecast]:
        """Fetch from all platforms and return non-None results.

        Args:
            contract_id: Contract identifier.

        Returns:
            List of available ExternalForecast objects.
        """
        results = []
        for fetcher in [self.fetch_metaculus, self.fetch_manifold, self.fetch_polymarket_depth]:
            try:
                result = fetcher(contract_id)
                if result is not None:
                    results.append(result)
            except Exception as e:
                logger.warning(f"Platform fetch failed for {contract_id}: {e}")
        return results


MultiPlatformAggregator = PlatformAggregator
