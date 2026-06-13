"""Domain-specific election forecasting models.

Implements Petropoulos et al. (2022) §3.8.5 — combining fundamental
economic models, polling aggregation, and expert judgment for election
prediction markets.

The three-component approach mirrors established practice:
  - Fair (1978) fundamental model: economic conditions → incumbent success
  - Polling aggregation: recency-weighted, sample-size-adjusted
  - Expert survey aggregation: median of domain expert estimates
"""

import logging
import time
from typing import Dict, List, Optional, Any

import numpy as np
from scipy.special import expit as sigmoid

from predmarket.density import DensityForecast, from_point_estimate

logger = logging.getLogger("predmarket.elections")


class ElectionModel:
    """Three-component election forecasting model.

    Combines fundamental economic indicators, polling aggregation,
    and expert judgment to produce probabilistic election forecasts.

    Weights follow the prediction market literature (Graefe et al., 2014):
    fundamentals 20%, polls 50%, experts 30%.
    """

    def __init__(self):
        self._fundamental_weight = 0.20
        self._poll_weight = 0.50
        self._expert_weight = 0.30

    # ------------------------------------------------------------------
    # Component 1: Fundamental model (Fair 1978, simplified)
    # ------------------------------------------------------------------

    def fundamental_forecast(self, economic_data: Dict[str, float]) -> float:
        """Predict incumbent-party win probability from economic fundamentals.

        Uses a simplified Fair (1978) model:
            prob = sigmoid(0.5 + 0.3*GDP_growth - 0.2*inflation - 0.1*unemployment_change)

        Args:
            economic_data: Dict with keys:
                gdp_growth (annual %, e.g. 2.5),
                inflation (annual %, e.g. 3.0),
                unemployment_change (year-over-year change in %, e.g. -0.5).

        Returns:
            Probability of incumbent-party victory in [0, 1].
        """
        gdp = economic_data.get("gdp_growth", 2.0)
        inflation = economic_data.get("inflation", 2.5)
        unemp_change = economic_data.get("unemployment_change", 0.0)

        z = 0.5 + 0.3 * gdp - 0.2 * inflation - 0.1 * unemp_change
        return float(np.clip(sigmoid(z), 0.01, 0.99))

    # ------------------------------------------------------------------
    # Component 2: Polling aggregation
    # ------------------------------------------------------------------

    def polling_aggregate(
        self, polls: List[Dict[str, float]], decay: float = 0.9
    ) -> float:
        """Compute recency-weighted polling average.

        Each poll is weighted by decay^(days_ago) * sqrt(sample_size).

        Args:
            polls: List of dicts with keys:
                date (unix timestamp),
                yes_share (fraction supporting yes, 0-1),
                sample_size (integer).
            decay: Exponential decay per day (0.9 = 10% weight loss per day).

        Returns:
            Weighted average yes-share.

        Raises:
            ValueError: If polls is empty.
        """
        if not polls:
            raise ValueError("No polls provided for aggregation.")

        now = time.time()
        day_seconds = 86400.0

        weighted_sum = 0.0
        weight_total = 0.0

        for poll in polls:
            days_ago = max(0.0, (now - poll.get("date", now)) / day_seconds)
            sample_size = poll.get("sample_size", 500)
            weight = (decay ** days_ago) * np.sqrt(sample_size)
            weighted_sum += poll.get("yes_share", 0.5) * weight
            weight_total += weight

        if weight_total == 0:
            return 0.5
        return float(np.clip(weighted_sum / weight_total, 0.01, 0.99))

    # ------------------------------------------------------------------
    # Component 3: Expert aggregation
    # ------------------------------------------------------------------

    def expert_aggregate(self, experts: List[Dict[str, float]]) -> float:
        """Aggregate expert probability estimates via median.

        Args:
            experts: List of dicts with key 'probability' (float 0-1).

        Returns:
            Median expert estimate.

        Raises:
            ValueError: If experts is empty.
        """
        if not experts:
            raise ValueError("No expert estimates provided.")

        probs = [e.get("probability", 0.5) for e in experts]
        return float(np.clip(np.median(probs), 0.01, 0.99))

    # ------------------------------------------------------------------
    # Combined forecast
    # ------------------------------------------------------------------

    def combined_election_forecast(
        self,
        economic_data: Optional[Dict[str, float]] = None,
        polls: Optional[List[Dict[str, float]]] = None,
        experts: Optional[List[Dict[str, float]]] = None,
    ) -> DensityForecast:
        """Produce a combined density forecast from all available inputs.

        Missing components are replaced with 0.5 (uninformative) and their
        weight is redistributed proportionally.

        Args:
            economic_data: Economic fundamentals dict (or None).
            polls: List of poll dicts (or None).
            experts: List of expert dicts (or None).

        Returns:
            DensityForecast with combined probability and uncertainty.
        """
        components: Dict[str, float] = {}
        weights: Dict[str, float] = {}

        if economic_data is not None:
            components["fundamentals"] = self.fundamental_forecast(economic_data)
            weights["fundamentals"] = self._fundamental_weight
        if polls is not None and len(polls) > 0:
            components["polls"] = self.polling_aggregate(polls)
            weights["polls"] = self._poll_weight
        if experts is not None and len(experts) > 0:
            components["experts"] = self.expert_aggregate(experts)
            weights["experts"] = self._expert_weight

        # If no components available, return uninformative
        if not components:
            return from_point_estimate(0.5, uncertainty=0.5)

        # Normalize weights
        w_sum = sum(weights.values())
        if w_sum == 0:
            w_sum = 1.0
        norm_weights = {k: v / w_sum for k, v in weights.items()}

        # Weighted combination
        combined_prob = sum(
            components[k] * norm_weights[k] for k in components
        )

        # Uncertainty: wider if components disagree
        if len(components) > 1:
            probs = list(components.values())
            disagreement = float(np.std(probs))
            uncertainty = np.clip(0.05 + disagreement * 2.0, 0.05, 0.45)
        else:
            uncertainty = 0.15

        return from_point_estimate(combined_prob, uncertainty=uncertainty)


class ElectionDataIngest:
    """Stub data fetcher for election-related data sources.

    In production, these methods would connect to:
    - FiveThirtyEight / Election Graphs API
    - HuffPost Pollster API
    - FRED for economic indicators
    - Internal expert survey system
    """

    def fetch_polls(self, race_id: str) -> List[Dict]:
        """Fetch polling data for a specific race.

        Args:
            race_id: Race identifier (e.g., "2026-US-SENATE-OH").

        Returns:
            List of poll dicts (empty in stub implementation).
        """
        logger.info("Poll fetch requested for race %s — stub returning empty.", race_id)
        return []

    def fetch_fundamentals(self, race_id: str) -> Dict[str, float]:
        """Fetch economic fundamental data relevant to a race.

        Args:
            race_id: Race identifier.

        Returns:
            Dict with gdp_growth, inflation, unemployment_change (defaults).
        """
        logger.info(
            "Fundamental fetch requested for race %s — returning defaults.", race_id
        )
        return {
            "gdp_growth": 2.0,
            "inflation": 2.5,
            "unemployment_change": 0.0,
        }
