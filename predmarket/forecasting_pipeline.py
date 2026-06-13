"""Unified forecasting pipeline integrating all components.

Implements Petropoulos et al. (2022) §2.6.1 — forecast combination with
all available models, adaptive weight learning, and density output.

This module is the top-level orchestrator that ties together:
  - Ensemble components (BBN, base rate, NLP, market consensus, time series)
  - Bayesian posterior model
  - ML/XGBoost signal classifier
  - Multi-platform aggregator
  - Volatility features (GARCH)
  - Adaptive weight learning from resolved outcomes
  - Density forecast combination
  - Horizon adjustment
  - Baseline comparison

All imports are lazy / behind TYPE_CHECKING to avoid circular dependencies.
"""

import logging
import time
from typing import Dict, Any, Optional, TYPE_CHECKING

import numpy as np

from predmarket.density import (
    DensityForecast,
    from_point_estimate,
    from_samples,
    combine_density_forecasts,
)
from predmarket.horizons import (
    ForecastHorizon,
    HorizonSpecificForecaster,
    HorizonWeightScheduler,
)

if TYPE_CHECKING:
    from predmarket.config import Config
    from predmarket.ensemble import EnsembleForecaster
    from predmarket.bayesian import BayesianForecaster
    from predmarket.weight_learner import AdaptiveWeightLearner
    from predmarket.volatility import VolatilityModel
    from predmarket.features import FeatureEngineer
    from predmarket.aggregator import MultiPlatformAggregator
    from predmarket.baselines import BaselineForecaster

logger = logging.getLogger("predmarket.pipeline")


class _StubForecaster:
    """Fallback when a component is not available (not installed or no data)."""

    def forecast(self, snapshot: Any, category: str) -> float:
        return 0.5

    def forecast_density(self, snapshot: Any, category: str) -> DensityForecast:
        return from_point_estimate(0.5, uncertainty=0.5)


class ForecastingPipeline:
    """Unified pipeline combining all forecasting components.

    This is the main entry point for generating production forecasts. It
    runs every available component, combines their density outputs with
    adaptive weights, and returns a comprehensive result.

    Args:
        config: Platform configuration object.
        ensemble: Optional pre-built EnsembleForecaster.
        bayesian: Optional pre-built BayesianForecaster.
        weight_learner: Optional pre-built AdaptiveWeightLearner.
        aggregator: Optional pre-built MultiPlatformAggregator.
        feature_engineer: Optional pre-built FeatureEngineer.
        volatility_model: Optional pre-built VolatilityModel.
    """

    def __init__(
        self,
        config: Any,
        ensemble: Optional[Any] = None,
        bayesian: Optional[Any] = None,
        weight_learner: Optional[Any] = None,
        aggregator: Optional[Any] = None,
        feature_engineer: Optional[Any] = None,
        volatility_model: Optional[Any] = None,
        research_registry: Optional[Any] = None,
    ):
        self.config = config
        self._ensemble = ensemble or self._build_default_ensemble()
        self._bayesian = bayesian or self._build_default_bayesian()
        self._weight_learner = weight_learner
        self._aggregator = aggregator
        self._feature_engineer = feature_engineer
        self._volatility_model = volatility_model
        self._research_registry = research_registry

        # Try to initialize components from config if not provided
        self._init_components()

        # Baseline always available
        try:
            from predmarket.baselines import BaselineForecaster
            self._baselines = BaselineForecaster()
        except ImportError:
            self._baselines = None

        # Horizon forecaster wraps whatever ensemble we have
        self._horizon_forecaster = HorizonSpecificForecaster(
            base_forecaster=self._ensemble
        )

    def _build_default_ensemble(self) -> Any:
        try:
            from predmarket.ensemble import EnsembleForecaster

            return EnsembleForecaster(self.config)
        except Exception as exc:
            logger.debug("EnsembleForecaster not available: %s", exc)
            return _StubForecaster()

    def _build_default_bayesian(self) -> Any:
        try:
            from predmarket.bayesian import BayesianForecaster

            return BayesianForecaster()
        except Exception as exc:
            logger.debug("BayesianForecaster not available: %s", exc)
            return _StubForecaster()

    def _init_components(self):
        """Attempt to initialize components that weren't passed in."""
        if self._weight_learner is None:
            try:
                from predmarket.weight_learner import AdaptiveWeightLearner
                self._weight_learner = AdaptiveWeightLearner()
            except ImportError:
                logger.debug("AdaptiveWeightLearner not available.")
                self._weight_learner = None

        if self._volatility_model is None:
            try:
                from predmarket.volatility import VolatilityModel
                self._volatility_model = VolatilityModel()
            except ImportError:
                logger.debug("VolatilityModel not available.")
                self._volatility_model = None

        if self._aggregator is None:
            try:
                from predmarket.aggregator import MultiPlatformAggregator
                self._aggregator = MultiPlatformAggregator()
            except ImportError:
                logger.debug("MultiPlatformAggregator not available.")
                self._aggregator = None

        if self._feature_engineer is None:
            try:
                from predmarket.features import FeatureEngineer
                self._feature_engineer = FeatureEngineer()
            except ImportError:
                logger.debug("FeatureEngineer not available.")
                self._feature_engineer = None

        if self._research_registry is None:
            try:
                from predmarket.research_forecasters import ForecasterRegistry

                self._research_registry = ForecasterRegistry.default()
            except Exception as exc:
                logger.debug("Research forecaster registry not available: %s", exc)
                self._research_registry = None

    # ------------------------------------------------------------------
    # Main forecast interface
    # ------------------------------------------------------------------

    def generate_forecast(
        self,
        snapshot: Any,
        category: str,
        headline: str = "",
        question: str = "",
        timestamp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Run full pipeline and produce comprehensive forecast.

        Steps:
            1. Run all individual forecasters → point estimates + densities.
            2. Fetch multi-platform prices via aggregator.
            3. Compute volatility features.
            4. Get adaptive weights from weight learner.
            5. Combine density forecasts.
            6. Add horizon-adjusted versions.
            7. Compare against baselines.
            8. Return comprehensive result.

        Args:
            snapshot: MarketSnapshot with current market data.
            category: Market category string.
            headline: News headline for NLP signal.
            question: Market question text.
            timestamp: Optional explicit timestamp.

        Returns:
            Dict with keys:
                point_forecast, density_forecast, all_components, weights,
                volatility_features, baseline_comparison, confidence,
                horizon_forecasts, platform_prices.
        """
        ts = timestamp or time.time()
        all_components: Dict[str, float] = {}
        all_densities: Dict[str, DensityForecast] = {}

        # --- 1. Run all available forecasters ---

        # Ensemble components (if the ensemble has the standard interface)
        try:
            ensemble_result = self._ensemble.generate_ensemble_forecast(
                snapshot=snapshot, category=category,
                headline=headline, question=question,
            )
            for comp_name in ["bbn", "base_rate", "nlp", "market_consensus", "time_series"]:
                if comp_name in ensemble_result.get("predictions", {}):
                    all_components[comp_name] = ensemble_result["predictions"][comp_name]
            all_components["ensemble_combined"] = ensemble_result.get("model_prob", 0.5)
        except Exception as e:
            logger.debug("Ensemble forecast failed: %s", e)
            try:
                point = self._ensemble.forecast(snapshot, category)
                all_components["ensemble"] = point
            except Exception:
                all_components["ensemble"] = 0.5

        # Bayesian posterior
        try:
            bayesian_density = self._bayesian.forecast_density(snapshot, category)
            all_components["bayesian"] = bayesian_density.mean
            all_densities["bayesian"] = bayesian_density
        except Exception as e:
            logger.debug("Bayesian forecast failed: %s", e)
            all_components["bayesian"] = 0.5

        # Multi-platform aggregator
        platform_prices: Dict[str, float] = {}
        if self._aggregator is not None:
            try:
                agg_result = self._aggregator.aggregate_forecasts(
                    snapshot.contract_id, category
                )
                all_components["aggregator"] = agg_result.mean
                all_densities["aggregator"] = agg_result
                platform_prices = self._aggregator.get_platform_prices(
                    snapshot.contract_id
                )
            except Exception as e:
                logger.debug("Aggregator failed: %s", e)

        # --- 2. Volatility features ---
        volatility_features: Dict[str, Any] = {}
        if self._volatility_model is not None and snapshot.line_history:
            try:
                vol_result = self._volatility_model.analyze(snapshot.line_history)
                volatility_features = vol_result
            except Exception as e:
                logger.debug("Volatility analysis failed: %s", e)

        # --- 3. Feature engineering ---
        engineered_features: Dict[str, float] = {}
        if self._feature_engineer is not None:
            try:
                engineered_features = self._feature_engineer.extract_features(
                    snapshot, category, headline, as_of_ts=ts
                )
            except Exception as e:
                logger.debug("Feature engineering failed: %s", e)

        # --- 3b. Research forecaster registry ---
        research_forecasts: Dict[str, Any] = {}
        if self._research_registry is not None:
            try:
                from predmarket.contracts import ForecastContext

                context = ForecastContext(
                    event_id=getattr(snapshot, "event_id", getattr(snapshot, "contract_id", "")),
                    market_id=getattr(snapshot, "contract_id", ""),
                    as_of_ts=ts,
                    category=category,
                    snapshot=snapshot,
                    market_history=list(getattr(snapshot, "line_history", []) or []),
                    source_documents=[],
                    features=engineered_features,
                )
                research_forecasts = self._research_registry.forecast_all(context)
                for name, dist in research_forecasts.items():
                    all_components[name] = dist.p_mean
                    if dist.samples:
                        all_densities[name] = from_samples(np.asarray(dist.samples))
                    else:
                        all_densities[name] = from_point_estimate(dist.p_mean, uncertainty=0.20)
            except Exception as e:
                logger.debug("Research forecasters failed: %s", e)

        # --- 4. Adaptive weights ---
        if self._weight_learner is not None:
            try:
                weights_dict = self._weight_learner.get_weights(category)
            except Exception:
                weights_dict = {}
        else:
            weights_dict = {}

        # Fill missing weights with uniform
        n_comp = len(all_components)
        uniform_w = 1.0 / max(n_comp, 1)
        for name in all_components:
            if name not in weights_dict:
                weights_dict[name] = uniform_w

        # Normalize
        w_sum = sum(weights_dict.values())
        if w_sum > 0:
            weights_dict = {k: v / w_sum for k, v in weights_dict.items()}

        # --- 5. Density combination ---
        density_list = list(all_densities.values())
        if not density_list:
            # Create densities from point estimates
            for name, prob in all_components.items():
                density_list.append(from_point_estimate(prob, uncertainty=0.1))

        weights_list = [weights_dict.get(name, uniform_w) for name in all_densities]
        if not weights_list or sum(weights_list) == 0:
            weights_list = None

        combined_density = combine_density_forecasts(density_list, weights_list)

        # --- 6. Horizon forecasts ---
        horizon_forecasts: Dict[str, DensityForecast] = {}
        try:
            all_horizons = self._horizon_forecaster.forecast_all_horizons(
                snapshot, category
            )
            horizon_forecasts = {
                h.value: d for h, d in all_horizons.items()
            }
        except Exception:
            pass

        # --- 7. Baseline comparison ---
        baseline_comparison: Dict[str, float] = {}
        if self._baselines is not None:
            try:
                baseline_comparison = self._baselines.compare_all(
                    snapshot, category, combined_density.mean
                )
            except Exception:
                pass

        # --- 8. Confidence score ---
        # Derived from density width (narrower = more confident)
        pi_width = combined_density.upper_90 - combined_density.lower_90
        confidence = float(np.clip(1.0 - pi_width, 0.0, 1.0))
        market_implied = float(getattr(snapshot, "mid", 0.5))
        status_flags = sorted(
            {
                flag
                for dist in research_forecasts.values()
                for flag in getattr(dist, "status_flags", [])
            }
        )
        status = "RESEARCH-ONLY" if "RESEARCH_ONLY" in status_flags else "READY"

        return {
            "point_forecast": combined_density.mean,
            "density_forecast": combined_density,
            "all_components": all_components,
            "weights": weights_dict,
            "volatility_features": volatility_features,
            "engineered_features": engineered_features,
            "baseline_comparison": baseline_comparison,
            "confidence": confidence,
            "horizon_forecasts": horizon_forecasts,
            "platform_prices": platform_prices,
            "timestamp": ts,
            "contract_id": getattr(snapshot, "contract_id", ""),
            "title": getattr(snapshot, "title", ""),
            "category": category,
            "model_prob": combined_density.mean,
            "market_implied": market_implied,
            "predictions": all_components,
            "status": status,
            "base_rate_reference": "research_registry:base_rate",
            "base_rate_prob": all_components.get("base_rate", 0.5),
            "research_forecasts": research_forecasts,
            "status_flags": status_flags,
            "promotion_status": "RESEARCH_ONLY",
        }

    # ------------------------------------------------------------------
    # Outcome feedback
    # ------------------------------------------------------------------

    def update_with_outcome(
        self,
        contract_id: str,
        category: str,
        outcome: int,
        component_forecasts: Dict[str, float],
    ) -> None:
        """Feed resolved outcome back to adaptive components.

        Updates the weight learner, Bayesian posterior, and aggregator
        with the actual binary outcome so future forecasts improve.

        Args:
            contract_id: Market contract identifier.
            category: Market category.
            outcome: Binary outcome (0 or 1).
            component_forecasts: Dict mapping component name to its
                forecast probability for this contract.
        """
        # Weight learner
        if self._weight_learner is not None:
            try:
                self._weight_learner.update(category, component_forecasts, outcome)
            except Exception as e:
                logger.warning("Weight learner update failed: %s", e)

        # Bayesian posterior
        if self._bayesian is not None:
            try:
                self._bayesian.update_posterior(category, outcome)
            except Exception as e:
                logger.debug("Bayesian update failed: %s", e)

        # Aggregator calibration
        if self._aggregator is not None:
            try:
                self._aggregator.record_outcome(contract_id, outcome)
            except Exception as e:
                logger.debug("Aggregator outcome recording failed: %s", e)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Return current state of all pipeline components.

        Returns:
            Dict with component names and their status (weights, observation
            counts, etc.).
        """
        status: Dict[str, Any] = {}

        if self._weight_learner is not None:
            try:
                if hasattr(self._weight_learner, "get_status"):
                    status["weight_learner"] = self._weight_learner.get_status()
                else:
                    status["weight_learner"] = "available"
            except Exception:
                status["weight_learner"] = "error"

        if self._volatility_model is not None:
            status["volatility_model"] = "available"

        if self._aggregator is not None:
            status["aggregator"] = "available"

        if self._feature_engineer is not None:
            status["feature_engineer"] = "available"

        if self._baselines is not None:
            status["baselines"] = "available"

        if self._research_registry is not None:
            status["research_registry"] = "available"

        return status
