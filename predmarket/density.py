"""Density forecast infrastructure for probabilistic predictions.

Implements Petropoulos et al. (2022) §2.6.2 — Density forecast combinations.
Provides prediction intervals, CRPS scoring, and calibration coverage metrics.

The existing ensemble outputs a single float `model_prob`. This module wraps
that into a full probabilistic forecast with uncertainty quantification.
"""

from dataclasses import dataclass, field

import numpy as np


@dataclass
class DensityForecast:
    """Probabilistic forecast with full density representation.

    Attributes:
        mean: Expected value (point estimate).
        samples: 1000 posterior samples from the predictive distribution.
        lower_90: 5th percentile (lower bound of 90% prediction interval).
        upper_90: 95th percentile (upper bound of 90% prediction interval).
        lower_50: 25th percentile (lower bound of 50% prediction interval).
        upper_50: 75th percentile (upper bound of 50% prediction interval).
        crps: Continuous Ranked Probability Score (set after evaluation).
    """

    mean: float
    samples: np.ndarray = field(default_factory=lambda: np.array([]))
    lower_90: float = 0.0
    upper_90: float = 1.0
    lower_50: float = 0.0
    upper_50: float = 1.0
    crps: float = 0.0

    def __post_init__(self):
        if self.samples.size > 0:
            self.lower_90 = float(np.percentile(self.samples, 5))
            self.upper_90 = float(np.percentile(self.samples, 95))
            self.lower_50 = float(np.percentile(self.samples, 25))
            self.upper_50 = float(np.percentile(self.samples, 75))
            self.mean = float(np.mean(self.samples))


def from_point_estimate(
    point_estimate: float,
    uncertainty: float = 0.1,
    n_samples: int = 1000,
    rng: np.random.Generator | None = None,
) -> DensityForecast:
    """Create a DensityForecast from a point estimate by sampling Beta distribution.

    Uses a Beta distribution parameterized so that its mean equals the point
    estimate and its concentration is inversely proportional to uncertainty.

    Args:
        point_estimate: Central probability estimate in [0, 1].
        uncertainty: Spread parameter. Lower = more confident. Range (0, 1).
        n_samples: Number of Monte Carlo samples.
        rng: Optional numpy random generator for reproducibility.

    Returns:
        DensityForecast with samples from the Beta posterior.
    """
    if rng is None:
        rng = np.random.default_rng()

    # Map point estimate + uncertainty to Beta parameters
    # kappa = concentration; higher kappa = narrower distribution
    kappa = max(2.0, 1.0 / max(uncertainty, 1e-6))
    p = np.clip(point_estimate, 1e-6, 1.0 - 1e-6)
    alpha = p * kappa
    beta_param = (1.0 - p) * kappa

    samples = rng.beta(max(alpha, 1e-6), max(beta_param, 1e-6), size=n_samples)
    samples = np.clip(samples, 0.0, 1.0)

    return DensityForecast(mean=float(np.mean(samples)), samples=samples)


def from_samples(samples: np.ndarray) -> DensityForecast:
    """Create a DensityForecast directly from an array of samples.

    Args:
        samples: Array of probability samples in [0, 1].

    Returns:
        DensityForecast with intervals computed from samples.
    """
    samples = np.clip(np.asarray(samples, dtype=float), 0.0, 1.0)
    return DensityForecast(mean=float(np.mean(samples)), samples=samples)


def combine_density_forecasts(
    density_list: list[DensityForecast],
    weights: list[float] | None = None,
) -> DensityForecast:
    """Combine multiple density forecasts via linear opinion pool.

    Implements the standard approach from §2.6.2: average the CDFs weighted
    by component reliability. With equal weights this reduces to mixing samples
    uniformly across components.

    Args:
        density_list: List of DensityForecast objects to combine.
        weights: Optional weights per component. Must sum to ~1.0.
            Defaults to uniform weights.

    Returns:
        Combined DensityForecast with weighted mixture of all samples.
    """
    if not density_list:
        return from_point_estimate(0.5, uncertainty=0.5)

    n = len(density_list)
    if weights is None:
        weights = [1.0 / n] * n
    else:
        w_sum = sum(weights)
        weights = [w / w_sum for w in weights]

    # Sample from mixture: pick component i with probability weights[i],
    # then draw from that component's samples.
    n_combined = 1000
    rng = np.random.default_rng()
    combined_samples = np.empty(n_combined)

    # Count how many samples to draw from each component
    counts = rng.multinomial(n_combined, weights)

    idx = 0
    for i, density in enumerate(density_list):
        count = int(counts[i])
        if count <= 0:
            continue
        if density.samples.size > 0:
            choices = rng.choice(density.samples, size=count, replace=True)
        else:
            # Fallback: sample from Beta around the mean
            fallback = from_point_estimate(density.mean, uncertainty=0.1, n_samples=count, rng=rng)
            choices = fallback.samples
        combined_samples[idx : idx + count] = choices
        idx += count

    combined_samples = np.clip(combined_samples[:idx], 0.0, 1.0)
    return from_samples(combined_samples)


def brier_score(forecast_prob: float, outcome: float) -> float:
    """Compute Brier score for a point probability forecast.

    Args:
        forecast_prob: Predicted probability in [0, 1].
        outcome: Actual binary outcome (0 or 1).

    Returns:
        Brier score: (forecast - outcome)^2. Lower is better.
    """
    return (forecast_prob - outcome) ** 2


def brier_score_density(forecast: DensityForecast, outcome: float) -> float:
    """Compute Brier score from a density forecast vs binary outcome.

    Uses the mean of the density as the point estimate.

    Args:
        forecast: DensityForecast object.
        outcome: Actual binary outcome (0 or 1).

    Returns:
        Brier score.
    """
    return brier_score(forecast.mean, outcome)


def crps_score(forecast: DensityForecast, outcome: float) -> float:
    """Compute Continuous Ranked Probability Score.

    CRPS generalizes MAE to probabilistic forecasts. For a discrete
    approximation from samples:

        CRPS = (1/N) * sum |sample_i - outcome|
               - (1/(2*N^2)) * sum_j sum_k |sample_j - sample_k|

    Lower is better. A perfect deterministic forecast has CRPS = 0.

    Args:
        forecast: DensityForecast with samples.
        outcome: Actual binary outcome (0 or 1).

    Returns:
        CRPS value.
    """
    if forecast.samples.size == 0:
        return abs(forecast.mean - outcome)

    samples = forecast.samples
    n = len(samples)

    # First term: mean absolute error of samples vs outcome
    term1 = np.mean(np.abs(samples - outcome))

    # Second term: Gini mean difference (expected absolute difference between pairs)
    # Efficient computation using sorted samples
    sorted_samples = np.sort(samples)
    term2 = 0.0
    for i in range(n):
        term2 += (2 * i - n + 1) * sorted_samples[i]
    term2 /= n * n

    return float(term1 - term2)


def crps_score_fast(forecast: DensityForecast, outcome: float) -> float:
    """Fast CRPS computation using numerical integration of the CDF.

    For binary outcomes, this uses the exact formula:
        CRPS = integral of (F(x) - 1{x >= outcome})^2 dx
    approximated over a grid.

    Args:
        forecast: DensityForecast with samples.
        outcome: Actual binary outcome (0 or 1).

    Returns:
        CRPS value.
    """
    if forecast.samples.size == 0:
        return abs(forecast.mean - outcome)

    # Build empirical CDF on a fine grid
    grid = np.linspace(0.0, 1.0, 200)
    sorted_samples = np.sort(forecast.samples)
    n = len(sorted_samples)

    # F(x) = fraction of samples <= x
    cdf_values = np.searchsorted(sorted_samples, grid, side="right") / n

    # Indicator: 1 if grid >= outcome
    indicator = (grid >= outcome).astype(float)

    # CRPS = integral of (F(x) - indicator(x))^2 dx
    integrand = (cdf_values - indicator) ** 2
    dx = grid[1] - grid[0]

    return float(np.sum(integrand) * dx)


def calibration_coverage(
    forecasts: list[DensityForecast],
    outcomes: list[float],
    nominal_level: float = 0.9,
) -> float:
    """Compute the empirical coverage of prediction intervals.

    Measures what fraction of actual outcomes fell within the nominal
    prediction interval. A well-calibrated forecast should match the
    nominal level (e.g., 90% of outcomes within the 90% PI).

    Args:
        forecasts: List of DensityForecast objects.
        outcomes: Corresponding binary outcomes.
        nominal_level: Expected coverage level (e.g. 0.9 for 90% PI).

    Returns:
        Empirical coverage fraction. Values near nominal_level = good calibration.
    """
    if len(forecasts) != len(outcomes) or len(forecasts) == 0:
        return 0.0

    # Select the appropriate interval based on nominal level
    if nominal_level >= 0.8:
        lower_key, upper_key = "lower_90", "upper_90"
    else:
        lower_key, upper_key = "lower_50", "upper_50"

    within = 0
    for fc, obs in zip(forecasts, outcomes):
        lo = getattr(fc, lower_key, 0.0)
        hi = getattr(fc, upper_key, 1.0)
        if lo <= obs <= hi:
            within += 1

    return within / len(forecasts)


def pit_histogram(
    forecasts: list[DensityForecast],
    outcomes: list[float],
    n_bins: int = 10,
) -> np.ndarray:
    """Compute Probability Integral Transform histogram for calibration assessment.

    Well-calibrated forecasts produce a uniform PIT histogram.
    U-shaped = underconfident. Inverted-U = overconfident.

    Args:
        forecasts: List of DensityForecast objects.
        outcomes: Corresponding binary outcomes.
        n_bins: Number of histogram bins.

    Returns:
        Normalized histogram counts (sums to 1.0).
    """
    if len(forecasts) != len(outcomes) or len(forecasts) == 0:
        return np.ones(n_bins) / n_bins

    pit_values = []
    for fc, obs in zip(forecasts, outcomes):
        if fc.samples.size == 0:
            pit_values.append(fc.mean)
        else:
            # PIT = F(obs) = fraction of samples <= obs
            pit_values.append(float(np.mean(fc.samples <= obs)))

    hist, _ = np.histogram(pit_values, bins=n_bins, range=(0.0, 1.0))
    return hist / max(hist.sum(), 1)
