"""Automated feature engineering from exogenous data.

Implements Petropoulos et al. (2022) §2.2.5 — Exogenous variables and
feature engineering, and §2.3.9 — Forecasting with many variables.

Provides a unified feature extraction layer that combines:
- Macro indicators (CPI, Fed Funds, unemployment, GDP growth)
- Temporal features (time of day, day of week, seasonality)
- Market microstructure features (spread, momentum, volatility)
- Contract metadata (category encoding)

These features feed into the ML timeseries models and signal classifiers,
replacing the current ad-hoc feature extraction scattered across modules.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger("predmarket.features")


class FeatureStore:
    """Unified feature extraction for prediction market contracts.

    Combines macro, temporal, and market features into a single ordered
    vector suitable for ML model consumption.

    The feature vector is deterministic: given the same inputs, it always
    produces the same output in the same order. Feature names are available
    via get_feature_names() for interpretability and SHAP analysis.

    Args:
        cache_dir: Optional directory for caching feature values.
            Currently unused but reserved for future persistence.
    """

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir
        self._macro_cache: Dict[str, float] = {}
        self._macro_cache_time: float = 0.0
        self._macro_ttl: float = 3600.0  # 1 hour cache

    def get_macro_features(self) -> Dict[str, float]:
        """Fetch macroeconomic indicator features.

        Returns:
            Dict with keys: cpi_yoy, fed_funds_rate, unemployment_rate, gdp_growth.
            Values come from FRED API (via signals.MacroSignalExtractor) or
            hardcoded defaults when the API is unavailable.
        """
        now = time.time()
        if self._macro_cache and (now - self._macro_cache_time) < self._macro_ttl:
            return dict(self._macro_cache)

        try:
            from predmarket.signals import MacroSignalExtractor
            extractor = MacroSignalExtractor()
            self._macro_cache = {
                "cpi_yoy": extractor.fetch_fred_rate("CPIAUCSNS"),
                "fed_funds_rate": extractor.fetch_fred_rate("FEDFUNDS"),
                "unemployment_rate": extractor.fetch_fred_rate("UNRATE"),
                "gdp_growth": 2.1,  # GDP is quarterly, use recent estimate
            }
            self._macro_cache_time = now
        except Exception as e:
            logger.warning(f"Failed to fetch macro features: {e}. Using defaults.")
            self._macro_cache = {
                "cpi_yoy": 3.1,
                "fed_funds_rate": 5.25,
                "unemployment_rate": 3.9,
                "gdp_growth": 2.1,
            }
            self._macro_cache_time = now

        return dict(self._macro_cache)

    def get_temporal_features(self, timestamp: float) -> Dict[str, float]:
        """Extract time-based features from a Unix timestamp.

        Args:
            timestamp: Unix timestamp (seconds since epoch).

        Returns:
            Dict with keys: day_of_week (0-6), hour_of_day (0-23),
            is_weekend (0/1), days_to_expiry_estimate (0-365), quarter (1-4).
        """
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)

        return {
            "day_of_week": float(dt.weekday()),
            "hour_of_day": float(dt.hour),
            "is_weekend": 1.0 if dt.weekday() >= 5 else 0.0,
            # Estimate: elections/major events cluster around Nov, so days
            # to expiry can be approximated from time-of-year
            "days_to_expiry_estimate": float((365 - dt.timetuple().tm_yday) % 365),
            "quarter": float((dt.month - 1) // 3 + 1),
        }

    def get_market_features(self, snapshot: object) -> Dict[str, float]:
        """Extract market microstructure features from a snapshot.

        Args:
            snapshot: MarketSnapshot-like object with bid, ask, mid,
                volume_24h, open_interest, line_history attributes.

        Returns:
            Dict with keys: bid_ask_spread, mid_price, log_volume,
            volume_24h, open_interest, price_momentum_1h, volatility_5.
        """
        bid = getattr(snapshot, "bid", 0.0)
        ask = getattr(snapshot, "ask", 0.0)
        mid = getattr(snapshot, "mid", 0.5)
        volume = getattr(snapshot, "volume_24h", 0.0)
        oi = getattr(snapshot, "open_interest", 0.0)
        line_history = getattr(snapshot, "line_history", [])

        spread = ask - bid

        # Price momentum: (last - first) / first over available history
        if line_history and len(line_history) >= 2 and line_history[0] > 0:
            momentum_1h = (line_history[-1] - line_history[0]) / line_history[0]
        else:
            momentum_1h = 0.0

        # Volatility: std of returns over last 5 periods
        if line_history and len(line_history) >= 3:
            returns = np.diff(line_history[-6:]) if len(line_history) >= 6 else np.diff(line_history)
            volatility_5 = float(np.std(returns)) if len(returns) > 1 else 0.0
        else:
            volatility_5 = 0.0

        # Log volume (clipped to avoid log(0))
        log_vol = float(np.log(max(volume, 1.0)))

        return {
            "bid_ask_spread": float(spread),
            "mid_price": float(mid),
            "log_volume": log_vol,
            "volume_24h": float(volume),
            "open_interest": float(oi),
            "price_momentum_1h": float(momentum_1h),
            "volatility_5": volatility_5,
        }

    def _category_encode(self, category: str) -> Dict[str, float]:
        """One-hot encode category for ML consumption.

        Args:
            category: Category string (e.g., "political", "econ", "sports").

        Returns:
            Dict with cat_political, cat_econ, cat_sports, cat_other keys.
        """
        categories = ["political", "econ", "sports"]
        encoded = {f"cat_{c}": 0.0 for c in categories}
        encoded["cat_other"] = 0.0

        if category in categories:
            encoded[f"cat_{category}"] = 1.0
        else:
            encoded["cat_other"] = 1.0

        return encoded

    def get_all_features(self, snapshot: object, timestamp: float,
                         category: str) -> Dict[str, float]:
        """Combine all feature sources into one dict.

        Args:
            snapshot: MarketSnapshot-like object.
            timestamp: Unix timestamp.
            category: Event category string.

        Returns:
            Merged dictionary of all features.
        """
        features = {}
        features.update(self.get_macro_features())
        features.update(self.get_temporal_features(timestamp))
        features.update(self.get_market_features(snapshot))
        features.update(self._category_encode(category))
        return features

    def get_feature_names(self) -> List[str]:
        """Return ordered feature names matching get_feature_vector().

        Returns:
            List of feature name strings in the exact order produced by
            get_feature_vector().
        """
        return [
            # Macro (4)
            "cpi_yoy", "fed_funds_rate", "unemployment_rate", "gdp_growth",
            # Temporal (5)
            "day_of_week", "hour_of_day", "is_weekend",
            "days_to_expiry_estimate", "quarter",
            # Market (7)
            "bid_ask_spread", "mid_price", "log_volume",
            "volume_24h", "open_interest", "price_momentum_1h", "volatility_5",
            # Category one-hot (4)
            "cat_political", "cat_econ", "cat_sports", "cat_other",
        ]

    def get_feature_vector(self, snapshot: object, timestamp: float,
                           category: str) -> np.ndarray:
        """Produce ordered numpy feature vector for ML consumption.

        Args:
            snapshot: MarketSnapshot-like object.
            timestamp: Unix timestamp.
            category: Event category string.

        Returns:
            1D numpy array of length len(get_feature_names()).
        """
        all_features = self.get_all_features(snapshot, timestamp, category)
        names = self.get_feature_names()
        return np.array([all_features.get(name, 0.0) for name in names], dtype=float)


class FeatureEngineer(FeatureStore):
    """Point-in-time feature extractor used by the unified pipeline."""

    def extract_features(
        self,
        snapshot: object,
        category: str,
        headline: str = "",
        as_of_ts: Optional[float] = None,
        source_documents: Optional[List[object]] = None,
    ) -> Dict[str, float]:
        ts = float(as_of_ts or getattr(snapshot, "timestamp", time.time()))
        for doc in source_documents or []:
            if hasattr(doc, "validate_as_of"):
                doc.validate_as_of(ts)
            else:
                published = float(getattr(doc, "published_ts", 0.0))
                retrieved = float(getattr(doc, "retrieved_ts", 0.0))
                if published > ts or retrieved > ts:
                    raise ValueError("feature source document is after as_of_ts")

        features = self.get_all_features(snapshot, ts, category)
        text = headline.lower()
        positive_terms = ("pass", "approve", "win", "surge", "beat", "agreement")
        negative_terms = ("fail", "reject", "lose", "delay", "block", "miss")
        features.update(
            {
                "headline_length": float(len(headline)),
                "headline_positive_terms": float(
                    sum(1 for term in positive_terms if term in text)
                ),
                "headline_negative_terms": float(
                    sum(1 for term in negative_terms if term in text)
                ),
                "source_doc_count": float(len(source_documents or [])),
            }
        )
        return features
