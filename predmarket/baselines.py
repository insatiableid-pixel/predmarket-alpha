"""Baseline forecasting models for benchmarking.

Implements Petropoulos et al. (2022) §2.12.7 — Forecasting competitions.
A sharp bettor must verify their model beats these naive baselines before
trusting it with real money.

Each baseline provides both point forecasts and density forecasts for
fair comparison against the ensemble.
"""

import logging

import numpy as np

from predmarket.density import DensityForecast, from_point_estimate

logger = logging.getLogger("predmarket.baselines")


class NaiveBaseline:
    """Returns the last known price as the forecast.

    The simplest possible baseline. If your model can't beat this,
    it has no predictive value beyond what the market already knows.
    """

    name = "naive"

    def forecast(self, snapshot, category: str = "") -> float:
        """Return last known mid-price as point forecast.

        Args:
            snapshot: MarketSnapshot with mid, last_price fields.
            category: Ignored for this baseline.

        Returns:
            Last known price.
        """
        return float(snapshot.mid if hasattr(snapshot, "mid") and snapshot.mid > 0 else 0.5)

    def forecast_density(
        self, snapshot, category: str = "", n_samples: int = 1000
    ) -> DensityForecast:
        """Return density forecast centered on last price with moderate uncertainty."""
        point = self.forecast(snapshot, category)
        return from_point_estimate(point, uncertainty=0.15, n_samples=n_samples)


class HistoricalMeanBaseline:
    """Returns the historical average outcome for a category.

    Uses stored resolved outcome statistics per category. Falls back
    to 0.50 for unknown categories.
    """

    name = "historical_mean"

    def __init__(self):
        self.category_means: dict[str, float] = {
            "political": 0.28,  # From BaseRateModel reference classes
            "econ": 0.45,
            "sports": 0.50,
            "other": 0.38,
        }
        self._category_counts: dict[str, int] = {}

    def update(self, category: str, outcome: float):
        """Update the running mean for a category with a new resolved outcome.

        Args:
            category: Event category string.
            outcome: Binary outcome (0 or 1).
        """
        if category not in self.category_means:
            self.category_means[category] = outcome
            self._category_counts[category] = 1
        else:
            n = self._category_counts.get(category, 1)
            old_mean = self.category_means[category]
            self.category_means[category] = (old_mean * n + outcome) / (n + 1)
            self._category_counts[category] = n + 1

    def forecast(self, snapshot, category: str = "") -> float:
        """Return historical mean for the category.

        Args:
            snapshot: MarketSnapshot (used only for category extraction).
            category: Event category.

        Returns:
            Historical mean outcome probability.
        """
        return self.category_means.get(category, 0.50)

    def forecast_density(
        self, snapshot, category: str = "", n_samples: int = 1000
    ) -> DensityForecast:
        """Return density forecast centered on category mean.

        Uncertainty is higher for categories with fewer observations.
        """
        point = self.forecast(snapshot, category)
        n = self._category_counts.get(category, 0)
        # More observations → lower uncertainty
        uncertainty = max(0.05, 0.30 / (1.0 + np.sqrt(max(n, 1))))
        return from_point_estimate(point, uncertainty=uncertainty, n_samples=n_samples)


class AlwaysFiftyBaseline:
    """Returns 0.50 for everything — pure coin flip.

    This is the hardest baseline to beat on Brier score for balanced
    datasets. Any model that can't beat this is worse than guessing.
    """

    name = "always_50"

    def forecast(self, snapshot, category: str = "") -> float:
        return 0.50

    def forecast_density(
        self, snapshot, category: str = "", n_samples: int = 1000
    ) -> DensityForecast:
        return from_point_estimate(0.50, uncertainty=0.29, n_samples=n_samples)


class RandomWalkBaseline:
    """Random walk with drift estimated from line history.

    Uses the mean return of the price series as drift, then projects
    forward. Respects that prediction market prices are bounded in [0, 1].
    """

    name = "random_walk"

    def forecast(self, snapshot, category: str = "") -> float:
        """Project price forward using random walk with drift.

        Args:
            snapshot: MarketSnapshot with line_history field.

        Returns:
            Drift-adjusted last price, clipped to [0.01, 0.99].
        """
        history = getattr(snapshot, "line_history", []) or []
        if len(history) < 2:
            return float(getattr(snapshot, "mid", 0.5))

        returns = np.diff(history)
        drift = float(np.mean(returns)) if len(returns) > 0 else 0.0
        projected = history[-1] + drift

        return float(np.clip(projected, 0.01, 0.99))

    def forecast_density(
        self, snapshot, category: str = "", n_samples: int = 1000
    ) -> DensityForecast:
        """Return density forecast using random walk with drift + noise."""
        history = getattr(snapshot, "line_history", []) or []
        if len(history) < 2:
            point = float(getattr(snapshot, "mid", 0.5))
            return from_point_estimate(point, uncertainty=0.15, n_samples=n_samples)

        returns = np.diff(history)
        drift = float(np.mean(returns))
        vol = float(np.std(returns)) if len(returns) > 1 else 0.02

        rng = np.random.default_rng()
        # Project one step: last_price + drift + noise
        noise = rng.normal(0, max(vol, 0.005), size=n_samples)
        samples = np.clip(history[-1] + drift + noise, 0.0, 1.0)

        return DensityForecast(mean=float(np.mean(samples)), samples=samples)


class SeasonalNaiveBaseline:
    """Seasonal naive baseline — repeats the last seasonal pattern.

    For prediction markets, this means using a windowed average of
    recent prices as the forecast. Captures mean-reversion tendency.
    """

    name = "seasonal_naive"

    def __init__(self, window: int = 5):
        self.window = window

    def forecast(self, snapshot, category: str = "") -> float:
        """Return the average of the last `window` prices.

        Args:
            snapshot: MarketSnapshot with line_history.

        Returns:
            Windowed average of recent prices.
        """
        history = getattr(snapshot, "line_history", []) or []
        if not history:
            return float(getattr(snapshot, "mid", 0.5))
        recent = history[-self.window :]
        return float(np.clip(np.mean(recent), 0.01, 0.99))

    def forecast_density(
        self, snapshot, category: str = "", n_samples: int = 1000
    ) -> DensityForecast:
        """Return density centered on windowed average."""
        point = self.forecast(snapshot, category)
        history = getattr(snapshot, "line_history", []) or []
        vol = float(np.std(history[-self.window :])) if len(history) >= 2 else 0.05
        return from_point_estimate(point, uncertainty=max(vol, 0.02), n_samples=n_samples)


class BaselineEnsemble:
    """Runs all baselines and returns their forecasts as a dict.

    Provides a convenient interface for benchmarking the main ensemble
    against every baseline simultaneously.

    Usage:
        be = BaselineEnsemble()
        results = be.forecast_all(snapshot, category="political")
        # results = {"naive": 0.585, "historical_mean": 0.28, ...}
    """

    def __init__(self):
        self.baselines = [
            NaiveBaseline(),
            HistoricalMeanBaseline(),
            AlwaysFiftyBaseline(),
            RandomWalkBaseline(),
            SeasonalNaiveBaseline(),
        ]

    def forecast_all(self, snapshot, category: str = "") -> dict[str, float]:
        """Run all baselines and return point forecasts.

        Args:
            snapshot: MarketSnapshot object.
            category: Event category string.

        Returns:
            Dict mapping baseline name to point forecast.
        """
        return {b.name: b.forecast(snapshot, category) for b in self.baselines}

    def forecast_all_density(
        self, snapshot, category: str = "", n_samples: int = 1000
    ) -> dict[str, DensityForecast]:
        """Run all baselines and return density forecasts.

        Args:
            snapshot: MarketSnapshot object.
            category: Event category string.
            n_samples: Number of Monte Carlo samples per baseline.

        Returns:
            Dict mapping baseline name to DensityForecast.
        """
        return {
            b.name: b.forecast_density(snapshot, category, n_samples=n_samples)
            for b in self.baselines
        }

    def update_historical(self, category: str, outcome: float):
        """Update the historical mean baseline with a new resolved outcome.

        Args:
            category: Event category.
            outcome: Binary outcome (0 or 1).
        """
        for b in self.baselines:
            if isinstance(b, HistoricalMeanBaseline):
                b.update(category, outcome)


class BaselineForecaster(BaselineEnsemble):
    """Pipeline-facing baseline comparator.

    Market-implied and naive baselines are mandatory comparators for every
    promoted model. This wrapper returns both absolute baseline forecasts and
    the model's edge against them.
    """

    def compare_all(
        self, snapshot, category: str = "", model_prob: float | None = None
    ) -> dict[str, float]:
        forecasts = self.forecast_all(snapshot, category)
        model = float(model_prob if model_prob is not None else 0.5)
        comparison: dict[str, float] = {}
        for name, prob in forecasts.items():
            comparison[name] = float(prob)
            comparison[f"{name}_edge"] = float(model - prob)
        market_implied = float(getattr(snapshot, "mid", forecasts.get("naive", 0.5)))
        comparison["market_implied"] = market_implied
        comparison["market_implied_edge"] = float(model - market_implied)
        return comparison
