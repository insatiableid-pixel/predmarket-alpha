"""Adaptive ensemble weight learning from historical forecast performance.

Implements Petropoulos et al. (2022) §2.5 and §2.6.1 — Variable and model
selection, and forecast combination. Currently the ensemble weights are
hardcoded. This module learns them from resolved outcomes.

Strategy:
    1. Record each component's forecast and the resolved outcome.
    2. Compute per-component Brier scores over a rolling window.
    3. Convert inverse-Brier scores to weights via softmax.
    4. Apply exponential decay so recent observations matter more.
    5. Return uniform weights until enough observations accumulate.

Usage:
    wl = WeightLearner(["bbn", "base_rate", "nlp", "market_consensus", "time_series"])

    # After each resolved forecast:
    wl.update({"bbn": 0.65, "base_rate": 0.28, ...}, outcome=1)

    # Get adaptive weights:
    weights = wl.get_weights()
    # {"bbn": 0.22, "base_rate": 0.15, "nlp": 0.18, ...}
"""

import logging

import numpy as np

logger = logging.getLogger("predmarket.weight_learner")


class WeightLearner:
    """Adaptive weight learner using inverse-Brier softmax with exponential decay.

    Attributes:
        component_names: Names of the ensemble components.
        decay_factor: Exponential decay factor for old observations (0.0–1.0).
            Higher = older observations retain more weight.
        min_observations: Minimum observations before adapting weights.
    """

    def __init__(
        self,
        component_names: list[str],
        decay_factor: float = 0.95,
        min_observations: int = 10,
        max_history: int = 500,
    ):
        self.component_names = list(component_names)
        self.decay_factor = decay_factor
        self.min_observations = min_observations
        self.max_history = max_history

        # Per-component history: list of (forecast, outcome) tuples
        self._history: dict[str, list[tuple[float, float]]] = {
            name: [] for name in self.component_names
        }
        self._n_observations = 0

    def update(self, component_forecasts: dict[str, float], outcome: float):
        """Record a new observation for each component.

        Call this after every resolved trade with each component's forecast
        and the actual binary outcome.

        Args:
            component_forecasts: Dict mapping component name to its probability
                forecast for this event. E.g. {"bbn": 0.65, "nlp": 0.72, ...}
            outcome: Actual binary outcome (0.0 or 1.0).
        """
        for name in self.component_names:
            forecast = component_forecasts.get(name)
            if forecast is None:
                continue
            self._history[name].append((float(forecast), float(outcome)))
            # Trim to max_history
            if len(self._history[name]) > self.max_history:
                self._history[name] = self._history[name][-self.max_history :]

        self._n_observations += 1
        logger.debug(
            f"WeightLearner: recorded observation #{self._n_observations}, outcome={outcome}"
        )

    def get_weights(self) -> dict[str, float]:
        """Compute current adaptive weights via softmax(inverse_brier).

        Returns uniform weights if fewer than min_observations have been recorded.
        Otherwise, computes exponentially-decayed Brier score per component
        and converts to weights via softmax over inverse Brier.

        Returns:
            Dict mapping component name to its weight (all sum to 1.0).
        """
        n = self._n_observations
        if n < self.min_observations:
            return self._uniform_weights()

        inverse_briers = []
        for name in self.component_names:
            brier = self._decayed_brier(name)
            # Inverse Brier: lower Brier = higher weight
            # Add epsilon to avoid division by zero
            inv_b = 1.0 / max(brier, 1e-6)
            inverse_briers.append(inv_b)

        weights = self._softmax(np.array(inverse_briers))
        return {name: float(w) for name, w in zip(self.component_names, weights)}

    def get_weights_with_confidence(self) -> tuple[dict[str, float], float]:
        """Compute weights and a confidence score.

        Confidence is based on the number of observations relative to
        min_observations. Reaches 1.0 after 3x min_observations.

        Returns:
            Tuple of (weights_dict, confidence_score).
        """
        weights = self.get_weights()

        if self._n_observations < self.min_observations:
            confidence = 0.0
        else:
            # Ramp from 0.0 to 1.0 over [min_obs, 3*min_obs]
            confidence = min(
                1.0,
                (self._n_observations - self.min_observations) / (2.0 * self.min_observations),
            )

        return weights, confidence

    def _decayed_brier(self, component_name: str) -> float:
        """Compute exponentially-decayed Brier score for a component.

        Recent observations are weighted more heavily. The decay factor
        determines how quickly older observations lose influence.

        Args:
            component_name: Name of the component.

        Returns:
            Decayed Brier score.
        """
        history = self._history.get(component_name, [])
        if not history:
            # No data — return poor Brier score so this component gets low weight
            return 0.5  # Worst Brier for binary events is 1.0, 0.5 is mediocre

        n = len(history)
        weights = np.array([self.decay_factor ** (n - 1 - i) for i in range(n)])
        weights /= weights.sum()

        forecasts = np.array([h[0] for h in history])
        outcomes = np.array([h[1] for h in history])

        briers = (forecasts - outcomes) ** 2
        return float(np.average(briers, weights=weights))

    def _softmax(self, x: np.ndarray, temperature: float = 1.0) -> np.ndarray:
        """Numerically stable softmax with temperature parameter.

        Lower temperature → sharper weights (winner-take-all).
        Higher temperature → more uniform weights.

        Args:
            x: Input array.
            temperature: Softmax temperature.

        Returns:
            Probability distribution over x.
        """
        scaled = x / max(temperature, 1e-6)
        shifted = scaled - np.max(scaled)  # For numerical stability
        exp_x = np.exp(shifted)
        return exp_x / exp_x.sum()

    def _uniform_weights(self) -> dict[str, float]:
        """Return equal weights for all components."""
        n = len(self.component_names)
        return {name: 1.0 / n for name in self.component_names}

    def get_component_scores(self) -> dict[str, dict[str, float]]:
        """Return detailed scores for each component.

        Useful for dashboard display and debugging.

        Returns:
            Dict mapping component name to score dict with:
                - brier: Raw Brier score
                - decayed_brier: Exponentially-decayed Brier score
                - n_observations: Number of recorded observations
                - weight: Current weight
        """
        weights = self.get_weights()
        result = {}
        for name in self.component_names:
            history = self._history.get(name, [])
            raw_brier = 0.5
            if history:
                forecasts = np.array([h[0] for h in history])
                outcomes = np.array([h[1] for h in history])
                raw_brier = float(np.mean((forecasts - outcomes) ** 2))

            result[name] = {
                "brier": raw_brier,
                "decayed_brier": self._decayed_brier(name),
                "n_observations": len(history),
                "weight": weights[name],
            }
        return result

    def reset(self):
        """Clear all observation history and return to uniform weights."""
        self._history = {name: [] for name in self.component_names}
        self._n_observations = 0
        logger.info("WeightLearner: history cleared, reverting to uniform weights")

    @property
    def n_observations(self) -> int:
        return self._n_observations


class AdaptiveWeightLearner:
    """Category-aware wrapper around WeightLearner.

    ForecastingPipeline expects weights to be learned separately by market
    bucket. This wrapper keeps the older WeightLearner implementation intact
    while exposing that newer interface.
    """

    DEFAULT_COMPONENTS = [
        "bbn",
        "base_rate",
        "nlp",
        "market_consensus",
        "time_series",
        "ensemble_combined",
        "bayesian",
        "aggregator",
    ]

    def __init__(
        self,
        component_names: list[str] | None = None,
        decay_factor: float = 0.95,
        min_observations: int = 10,
        max_history: int = 500,
    ):
        self.component_names = list(component_names or self.DEFAULT_COMPONENTS)
        self.decay_factor = decay_factor
        self.min_observations = min_observations
        self.max_history = max_history
        self._learners: dict[str, WeightLearner] = {}
        self._component_brier: dict[str, dict[str, float]] = {}

    def _learner(self, category: str) -> WeightLearner:
        bucket = category or "default"
        if bucket not in self._learners:
            self._learners[bucket] = WeightLearner(
                component_names=self.component_names,
                decay_factor=self.decay_factor,
                min_observations=self.min_observations,
                max_history=self.max_history,
            )
        return self._learners[bucket]

    def update(
        self,
        category: str,
        component_forecasts: dict[str, float],
        outcome: float,
    ) -> None:
        learner = self._learner(category)
        learner.update(component_forecasts, outcome)
        self._component_brier[category or "default"] = {
            name: values["decayed_brier"] for name, values in learner.get_component_scores().items()
        }

    def get_weights(self, category: str = "default") -> dict[str, float]:
        return self._learner(category).get_weights()

    def get_status(self) -> dict[str, dict[str, float]]:
        return {category: learner.get_weights() for category, learner in self._learners.items()}
