"""Full Bayesian inference for prediction market forecasting.

Implements Petropoulos et al. (2022) §2.3, §2.4 — Bayesian forecasting with
conjugate Beta-Binomial updates. No PyMC dependency required.

Replaces the toy BBN in ensemble.py with proper posterior inference that:
- Maintains a Beta posterior per contract that updates with outcomes
- Shrinks individual posteriors toward category means (hierarchical)
- Produces calibrated density forecasts with credible intervals
- Combines with NLP signals and base rates via Bayesian model averaging
"""

import logging
import time
from typing import Dict, Tuple, Optional, List

import numpy as np

from predmarket.density import DensityForecast, from_point_estimate, combine_density_forecasts

logger = logging.getLogger("predmarket.bayesian")


class BetaPosterior:
    """Conjugate Beta-Binomial posterior over P(event occurs).

    Starts with a uniform prior Beta(1, 1). Each observed outcome updates
    the posterior via the conjugate Beta-Binomial formula:

        alpha' = alpha + weight * outcome
        beta'  = beta  + weight * (1 - outcome)

    The optional weight parameter allows down-weighting stale or noisy
    observations.

    Examples:
        >>> post = BetaPosterior()
        >>> post.mean()
        0.5
        >>> post.update(1)  # observed event
        >>> post.update(1)
        >>> post.mean() > 0.5
        True
        >>> post.update(0)  # observed non-event
        >>> samples = post.sample(100)
        >>> len(samples)
        100
    """

    def __init__(self, alpha: float = 1.0, beta: float = 1.0):
        self.alpha = float(max(alpha, 0.01))
        self.beta = float(max(beta, 0.01))
        self._n_updates: int = 0

    def update(self, outcome: int, weight: float = 1.0) -> None:
        """Perform conjugate Beta-Binomial update.

        Args:
            outcome: Binary outcome (0 or 1).
            weight: Evidence strength. 1.0 = full observation,
                0.5 = half-weighted, etc.
        """
        if outcome not in (0, 1):
            logger.warning(f"Non-binary outcome {outcome} ignored in BetaPosterior update.")
            return
        w = max(weight, 0.0)
        self.alpha += w * outcome
        self.beta += w * (1.0 - outcome)
        self._n_updates += 1

    def sample(self, n: int = 1000) -> np.ndarray:
        """Draw samples from the current Beta posterior.

        Args:
            n: Number of samples.

        Returns:
            Array of shape (n,) with values in [0, 1].
        """
        rng = np.random.default_rng()
        return np.clip(rng.beta(self.alpha, self.beta, size=n), 0.0, 1.0)

    def mean(self) -> float:
        """Posterior mean = alpha / (alpha + beta)."""
        return self.alpha / (self.alpha + self.beta)

    def variance(self) -> float:
        """Posterior variance."""
        a, b = self.alpha, self.beta
        return (a * b) / ((a + b) ** 2 * (a + b + 1))

    def credible_interval(self, level: float = 0.9) -> Tuple[float, float]:
        """Equal-tailed credible interval.

        Args:
            level: Credible level (0.9 = 90% interval).

        Returns:
            (lower, upper) bounds.
        """
        tail = (1.0 - level) / 2.0
        from scipy.stats import beta as beta_dist
        lower = float(beta_dist.ppf(tail, self.alpha, self.beta))
        upper = float(beta_dist.ppf(1.0 - tail, self.alpha, self.beta))
        return lower, upper

    def to_density_forecast(self, n_samples: int = 1000) -> DensityForecast:
        """Convert posterior to a DensityForecast.

        Args:
            n_samples: Number of Monte Carlo samples.

        Returns:
            DensityForecast with full uncertainty quantification.
        """
        samples = self.sample(n_samples)
        return DensityForecast(mean=self.mean(), samples=samples)

    def __repr__(self) -> str:
        return f"BetaPosterior(alpha={self.alpha:.2f}, beta={self.beta:.2f}, mean={self.mean():.4f}, updates={self._n_updates})"


class HierarchicalEventModel:
    """Hierarchical Bayesian model with shrinkage toward category means.

    Maintains a separate BetaPosterior per (category, contract_id) pair.
    Individual contract posteriors are shrunk toward the category-level
    hyperprior, which is estimated from all contracts in that category.

    This implements the partial-pooling concept from hierarchical Bayesian
    modeling: contracts with few observations are pulled toward the category
    mean, while contracts with many observations retain their individual
    estimates.

    Args:
        default_alpha: Prior alpha for new posteriors (default: 1.0 = uniform).
        default_beta: Prior beta for new posteriors (default: 1.0 = uniform).
    """

    def __init__(self, default_alpha: float = 1.0, default_beta: float = 1.0):
        self._posteriors: Dict[str, Dict[str, BetaPosterior]] = {}
        self._default_alpha = default_alpha
        self._default_beta = default_beta

    def _key(self, category: str, contract_id: str) -> Tuple[str, str]:
        return (category, contract_id)

    def get_posterior(self, category: str, contract_id: str) -> BetaPosterior:
        """Get or create the BetaPosterior for a specific contract.

        Args:
            category: Event category (e.g., "political", "econ").
            contract_id: Unique contract identifier.

        Returns:
            BetaPosterior for this contract.
        """
        if category not in self._posteriors:
            self._posteriors[category] = {}
        if contract_id not in self._posteriors[category]:
            self._posteriors[category][contract_id] = BetaPosterior(
                alpha=self._default_alpha, beta=self._default_beta
            )
        return self._posteriors[category][contract_id]

    def update(self, category: str, contract_id: str, outcome: int,
               weight: float = 1.0) -> None:
        """Update the posterior for a specific contract with an observed outcome.

        Args:
            category: Event category.
            contract_id: Contract identifier.
            outcome: Binary outcome (0 or 1).
            weight: Optional evidence weighting.
        """
        post = self.get_posterior(category, contract_id)
        post.update(outcome, weight)

    def _category_prior(self, category: str) -> Tuple[float, float]:
        """Estimate category-level hyperprior from all contracts in the category.

        Returns the mean alpha and beta across all contracts, or the default
        if the category has no data.

        Args:
            category: Category to compute prior for.

        Returns:
            (alpha, beta) for the category-level prior.
        """
        if category not in self._posteriors:
            return self._default_alpha, self._default_beta

        posteriors = list(self._posteriors[category].values())
        if not posteriors:
            return self._default_alpha, self._default_beta

        # Average the alpha and beta across all contracts
        mean_alpha = sum(p.alpha for p in posteriors) / len(posteriors)
        mean_beta = sum(p.beta for p in posteriors) / len(posteriors)
        return mean_alpha, mean_beta

    def get_shrinkage_estimate(self, category: str, contract_id: str,
                               shrinkage_weight: float = 0.3) -> float:
        """Hierarchical shrinkage estimate for a contract.

        Blends the individual contract posterior with the category-level prior.
        Contracts with few observations are pulled more toward the category mean.

        The shrinkage weight determines the blending:
            estimate = (1 - w) * individual_mean + w * category_mean

        Where w is the shrinkage_weight scaled by 1/(1 + n_updates).

        Args:
            category: Event category.
            contract_id: Contract identifier.
            shrinkage_weight: Maximum shrinkage toward category mean (0-1).

        Returns:
            Shrinkage-adjusted probability estimate.
        """
        post = self.get_posterior(category, contract_id)
        individual_mean = post.mean()

        cat_alpha, cat_beta = self._category_prior(category)
        category_mean = cat_alpha / (cat_alpha + cat_beta)

        # Shrinkage decreases with more observations
        effective_shrinkage = shrinkage_weight / (1.0 + post._n_updates)
        blended = (1.0 - effective_shrinkage) * individual_mean + effective_shrinkage * category_mean

        return float(np.clip(blended, 0.001, 0.999))

    def get_contracts_for_category(self, category: str) -> List[str]:
        """Return all contract IDs registered under a category."""
        if category not in self._posteriors:
            return []
        return list(self._posteriors[category].keys())


class BayesianForecaster:
    """Produces density forecasts using Bayesian model averaging.

    Combines three information sources:
    1. Hierarchical posterior from observed outcomes (weight: posterior_weight)
    2. NLP signal from text analysis (weight: nlp_weight)
    3. Superforecaster base rate (weight: base_rate_weight)

    The hierarchical posterior provides the data-driven component. NLP signals
    and base rates provide complementary evidence when outcome data is sparse.

    Args:
        model: HierarchicalEventModel instance.
        posterior_weight: Weight for the hierarchical posterior component.
        nlp_weight: Weight for the NLP signal component.
        base_rate_weight: Weight for the base rate component.
    """

    def __init__(
        self,
        model: Optional[HierarchicalEventModel] = None,
        posterior_weight: float = 0.50,
        nlp_weight: float = 0.25,
        base_rate_weight: float = 0.25,
    ):
        self.model = model or HierarchicalEventModel()
        self.posterior_weight = posterior_weight
        self.nlp_weight = nlp_weight
        self.base_rate_weight = base_rate_weight

        # Normalize weights
        total = self.posterior_weight + self.nlp_weight + self.base_rate_weight
        if total > 0:
            self.posterior_weight /= total
            self.nlp_weight /= total
            self.base_rate_weight /= total

    def forecast(
        self,
        snapshot: object,
        category: str,
        nlp_signal: float = 0.5,
        base_rate: float = 0.5,
        n_samples: int = 1000,
    ) -> DensityForecast:
        """Produce a density forecast via Bayesian model averaging.

        Args:
            snapshot: MarketSnapshot-like object with contract_id attribute.
            category: Event category (e.g., "political").
            nlp_signal: Probability from NLP text analysis (0-1).
            base_rate: Superforecaster-calibrated base rate (0-1).
            n_samples: Number of Monte Carlo samples for each component.

        Returns:
            Combined DensityForecast from Bayesian model averaging.
        """
        contract_id = getattr(snapshot, "contract_id", "unknown")

        # Component 1: Hierarchical posterior
        shrinkage_est = self.model.get_shrinkage_estimate(category, contract_id)
        post = self.model.get_posterior(category, contract_id)

        # Use the posterior samples if we have updates, otherwise sample from
        # the shrinkage estimate with high uncertainty
        if post._n_updates > 0:
            density_posterior = post.to_density_forecast(n_samples=n_samples)
        else:
            # Cold start: use shrinkage estimate with moderate uncertainty
            uncertainty = max(0.1, 1.0 / (1.0 + len(self.model.get_contracts_for_category(category))))
            density_posterior = from_point_estimate(shrinkage_est, uncertainty=uncertainty, n_samples=n_samples)

        # Component 2: NLP signal as density
        nlp_uncertainty = 0.15  # NLP is somewhat noisy
        density_nlp = from_point_estimate(
            np.clip(nlp_signal, 0.01, 0.99),
            uncertainty=nlp_uncertainty,
            n_samples=n_samples,
        )

        # Component 3: Base rate as density
        base_rate_uncertainty = 0.08  # Base rates are relatively stable
        density_base_rate = from_point_estimate(
            np.clip(base_rate, 0.01, 0.99),
            uncertainty=base_rate_uncertainty,
            n_samples=n_samples,
        )

        # Combine via weighted linear opinion pool
        combined = combine_density_forecasts(
            [density_posterior, density_nlp, density_base_rate],
            weights=[self.posterior_weight, self.nlp_weight, self.base_rate_weight],
        )

        logger.debug(
            f"Bayesian forecast for {contract_id}: "
            f"posterior={density_posterior.mean:.3f}, "
            f"nlp={density_nlp.mean:.3f}, base_rate={density_base_rate.mean:.3f} -> "
            f"combined={combined.mean:.3f} "
            f"90% CI=[{combined.lower_90:.3f}, {combined.upper_90:.3f}]"
        )

        return combined

    def forecast_density(
        self,
        snapshot: object,
        category: str,
        nlp_signal: float = 0.5,
        base_rate: float = 0.5,
        n_samples: int = 1000,
    ) -> DensityForecast:
        """Pipeline-facing alias for density output."""
        return self.forecast(
            snapshot=snapshot,
            category=category,
            nlp_signal=nlp_signal,
            base_rate=base_rate,
            n_samples=n_samples,
        )

    def update_outcome(self, category: str, contract_id: str,
                       outcome: int, weight: float = 1.0) -> None:
        """Convenience method to update the model with a resolved outcome.

        Args:
            category: Event category.
            contract_id: Contract identifier.
            outcome: Binary outcome (0 or 1).
            weight: Optional evidence weighting.
        """
        self.model.update(category, contract_id, outcome, weight)

    def update_posterior(
        self, category: str, outcome: int, contract_id: str = "__category__"
    ) -> None:
        """Pipeline-facing posterior update for resolved category outcomes."""
        self.update_outcome(category, contract_id, outcome)
