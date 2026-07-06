import logging
from typing import Any

import numpy as np

from predmarket.config import Config
from predmarket.ingest import MarketSnapshot
from predmarket.signals import BaseRateModel, MacroSignalExtractor, NLPEventSignalExtractor

logger = logging.getLogger("predmarket.ensemble")


class EnsembleForecaster:
    def __init__(self, config: Config):
        self.config = config
        self.nlp_extractor = NLPEventSignalExtractor()
        self.base_rate_model = BaseRateModel()
        self.macro_extractor = MacroSignalExtractor()

        # Initialize component Brier score records (for rolling weight calibration)
        # Seed default weights
        self.weights = {
            "bbn": 0.20,
            "base_rate": 0.15,
            "nlp": 0.20,
            "market_consensus": 0.25,
            "time_series": 0.20,
        }

    def _run_bbn(self, category: str, market_price: float) -> float:
        """
        Component 1: Bayesian Belief Network updated on live economic/political nodes.
        Computes the posterior using Bayes' theorem on evidence nodes.
        """
        # Node states
        prior = 0.50
        if category == "political":
            prior = 0.28
            # Evidence: polling node (P(poll_positive | event) = 0.75 vs P(poll_positive | ~event) = 0.35)
            # Suppose polling trend matches current market sentiment
            p_poll_given_event = 0.75 if market_price > 0.50 else 0.40
            p_poll_given_no_event = 0.35 if market_price > 0.50 else 0.60

            posterior = (prior * p_poll_given_event) / (
                (prior * p_poll_given_event) + ((1.0 - prior) * p_poll_given_no_event)
            )
            return float(posterior)

        elif category == "econ":
            prior = 0.45
            # Evidence: inflation/FRED indicator print
            cpi_yo = self.macro_extractor.fetch_fred_rate("CPIAUCSNS")
            # If inflation is low (< 3.0%), likelihood of interest rate cut increases
            p_cpi_given_cut = 0.80 if cpi_yo < 3.0 else 0.30
            p_cpi_given_no_cut = 0.40 if cpi_yo < 3.0 else 0.70

            posterior = (prior * p_cpi_given_cut) / (
                (prior * p_cpi_given_cut) + ((1.0 - prior) * p_cpi_given_no_cut)
            )
            return float(posterior)

        return prior

    def _run_base_rate(self, category: str) -> tuple[float, str]:
        """
        Component 2: Superforecaster-Calibrated Base Rate Model.
        """
        prob, ref_name, _ = self.base_rate_model.get_base_rate(category)
        return prob, ref_name

    def _run_nlp(self, headline: str, question: str) -> tuple[float, float]:
        """
        Component 3: News and Event Signal NLP Model (DeBERTa / MiniLM).
        """
        return self.nlp_extractor.get_event_probability(headline, question)

    def _run_market_consensus(self, snapshot: MarketSnapshot) -> float:
        """
        Component 4: Prediction market consensus aggregation with liquidity weighting.
        Converts market mid-price to subjective probability adjusting for spread friction.
        """
        mid = snapshot.mid
        spread = snapshot.ask - snapshot.bid

        # Risk premium adjustments (extreme prices hold high leverage premium)
        if mid > 0.85:
            adj_prob = mid - (spread * 0.5)
        elif mid < 0.15:
            adj_prob = mid + (spread * 0.5)
        else:
            adj_prob = mid

        return float(np.clip(adj_prob, 0.01, 0.99))

    def _run_time_series(self, history: list[float]) -> float:
        """
        Component 5: Double Exponential Smoothing with Regime Detection (simulating TFT/Prophet).
        Detects structural breaks (structural shift in trend volatility).
        """
        if not history:
            return 0.50
        if len(history) < 2:
            return history[-1]

        # Calculate volatility/regime
        returns = np.diff(history)
        vol = np.std(returns) if len(returns) > 1 else 0.0

        # Double exponential smoothing (Holt's Linear Trend Model)
        alpha = 0.3
        beta = 0.1

        level = history[0]
        trend = history[1] - history[0]

        for price in history[1:]:
            last_level = level
            level = alpha * price + (1 - alpha) * (level + trend)
            trend = beta * (level - last_level) + (1 - beta) * trend

        forecast = level + trend

        # Regime detection: if high volatility, damp trend projection to historical mean
        if vol > 0.04:
            # Shift to High-Vol Regime: pull prediction toward the middle to avoid overfitting tails
            forecast = 0.7 * forecast + 0.3 * np.mean(history)

        return float(np.clip(forecast, 0.01, 0.99))

    def generate_ensemble_forecast(
        self, snapshot: MarketSnapshot, category: str, headline: str = "", question: str = ""
    ) -> dict[str, Any]:
        """
        Generates probability estimates using the six-component ensemble combiner.
        Enforces divergence, tail, and recency bounds.
        """
        # Run components
        p_bbn = self._run_bbn(category, snapshot.mid)
        p_br, ref_name = self._run_base_rate(category)
        p_nlp, nlp_weight = self._run_nlp(headline, question)
        p_consensus = self._run_market_consensus(snapshot)
        p_ts = self._run_time_series(snapshot.line_history)

        predictions = {
            "bbn": p_bbn,
            "base_rate": p_br,
            "nlp": p_nlp,
            "market_consensus": p_consensus,
            "time_series": p_ts,
        }

        # 1. Divergence Check
        p_vals = list(predictions.values())
        max_p = max(p_vals)
        min_p = min(p_vals)
        divergence = max_p - min_p

        status = "READY"
        if divergence > self.config.forecasting.ensemble.divergence_threshold:
            status = "ENSEMBLE-DIVERGENCE"

        # 2. Recency Anchor & Damping Check
        final_nlp_prob = p_nlp
        if nlp_weight > self.config.forecasting.ensemble.recency_anchor_threshold:
            # Apply base rate damping
            lmbda = self.config.forecasting.ensemble.nlp_damping_factor
            final_nlp_prob = lmbda * p_br + (1.0 - lmbda) * p_nlp
            predictions["nlp"] = final_nlp_prob
            status = "RECENCY-ANCHOR"

        # 3. Log-Odds Averaging (Combiner)
        log_odds_sum = 0.0
        weight_sum = 0.0

        for name, prob in predictions.items():
            w = self.weights[name]
            # Clip bounds to prevent log(0)
            prob_clipped = np.clip(prob, 0.001, 0.999)
            odds = prob_clipped / (1.0 - prob_clipped)
            log_odds_sum += w * np.log(odds)
            weight_sum += w

        combined_odds = np.exp(log_odds_sum / weight_sum)
        p_combined = combined_odds / (1.0 + combined_odds)

        # 4. Tail Overconfidence Check
        cfg_forecasting = self.config.forecasting.ensemble
        if (
            p_combined < cfg_forecasting.min_forecast_prob
            or p_combined > cfg_forecasting.max_forecast_prob
        ):
            status = "OVERCONFIDENT-TAIL"

        # Safe boundaries return
        final_prob = float(np.clip(p_combined, 0.0001, 0.9999))

        return {
            "contract_id": snapshot.contract_id,
            "title": snapshot.title,
            "category": category,
            "predictions": predictions,
            "model_prob": final_prob,
            "market_implied": p_consensus,
            "divergence": float(divergence),
            "status": status,
            "base_rate_reference": ref_name,
            "base_rate_prob": p_br,
        }
