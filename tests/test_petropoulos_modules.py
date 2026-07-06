"""Tests for the 14 new Petropoulos gap-closure modules.

Each test exercises a core code path of one module, verifying that the
implementation is functional and that density/forecast outputs are
well-formed.
"""

import time

import numpy as np

# ---------------------------------------------------------------------------
# density.py
# ---------------------------------------------------------------------------
from predmarket.density import (
    DensityForecast,
    brier_score_density,
    calibration_coverage,
    combine_density_forecasts,
    crps_score,
    from_point_estimate,
)


class TestDensityForecast:
    def test_from_point_estimate(self):
        df = from_point_estimate(0.7, uncertainty=0.1)
        assert isinstance(df, DensityForecast)
        assert 0.0 < df.mean < 1.0
        assert len(df.samples) == 1000
        assert df.lower_90 < df.mean < df.upper_90
        assert df.lower_50 < df.mean < df.upper_50

    def test_combine_density_forecasts(self):
        d1 = from_point_estimate(0.6, 0.08)
        d2 = from_point_estimate(0.8, 0.08)
        combined = combine_density_forecasts([d1, d2], [0.5, 0.5])
        assert isinstance(combined, DensityForecast)
        assert 0.5 < combined.mean < 0.9
        assert combined.lower_90 < combined.upper_90

    def test_brier_score(self):
        df = from_point_estimate(0.8, 0.05)
        b = brier_score_density(df, 1)
        assert 0.0 <= b <= 1.0
        # A forecast of 0.8 when outcome=1 should have Brier ~0.04
        assert b < 0.1

    def test_crps_score(self):
        df = from_point_estimate(0.7, 0.1)
        c = crps_score(df, 1)
        assert c >= 0.0

    def test_calibration_coverage(self):
        forecasts = [from_point_estimate(0.5 + 0.4 * i / 10, 0.1) for i in range(10)]
        outcomes = [1, 0, 1, 1, 0, 1, 0, 1, 1, 0]
        cov = calibration_coverage(forecasts, outcomes, nominal_level=0.9)
        assert 0.0 <= cov <= 1.0


# ---------------------------------------------------------------------------
# baselines.py
# ---------------------------------------------------------------------------
from predmarket.baselines import (
    AlwaysFiftyBaseline,
    BaselineEnsemble,
    HistoricalMeanBaseline,
    NaiveBaseline,
)
from predmarket.ingest import MarketSnapshot


def _make_snapshot(mid=0.55, history=None):
    return MarketSnapshot(
        venue="Test",
        contract_id="TEST-1",
        title="Test contract",
        bid=mid - 0.005,
        ask=mid + 0.005,
        last_price=mid,
        open_interest=50000.0,
        volume_24h=10000.0,
        line_history=history or [0.50, 0.52, 0.53, 0.54, mid],
    )


class TestBaselines:
    def test_naive_baseline(self):
        b = NaiveBaseline()
        snap = _make_snapshot(mid=0.65)
        f = b.forecast(snap, "political")
        assert f == 0.65

    def test_always_fifty(self):
        b = AlwaysFiftyBaseline()
        f = b.forecast(_make_snapshot(), "econ")
        assert f == 0.5

    def test_historical_mean(self):
        b = HistoricalMeanBaseline()
        # Category starts at base rate (political=0.28), updates shift it
        b.update("political", 0.6)
        b.update("political", 0.4)
        snap = _make_snapshot(mid=0.55)
        f = b.forecast(snap, "political")
        assert 0.0 < f < 1.0
        # Should be between base rate 0.28 and the updates
        assert 0.3 < f < 0.5

    def test_baseline_ensemble(self):
        be = BaselineEnsemble()
        results = be.forecast_all(_make_snapshot(mid=0.6), "political")
        assert "naive" in results
        assert "always_50" in results
        assert results["naive"] == 0.6


# ---------------------------------------------------------------------------
# volatility.py
# ---------------------------------------------------------------------------
from predmarket.volatility import VolatilityModel


class TestVolatility:
    def test_garch_fit_and_forecast(self):
        np.random.seed(42)
        prices = np.cumsum(np.random.randn(100) * 0.01) + 0.5
        vm = VolatilityModel()
        vm.fit(prices.tolist())
        cond_vol, ann_vol = vm.forecast_volatility(horizon=1)
        assert cond_vol > 0
        assert ann_vol > 0

    def test_regime_change_detection(self):
        # Stable series then spike
        stable = [0.5] * 50 + [0.7, 0.3, 0.8, 0.2, 0.9]
        vm = VolatilityModel()
        assert vm.detect_regime_change(stable, window=5, threshold=1.5) is True

    def test_stable_no_regime(self):
        stable = [0.50 + 0.001 * i for i in range(20)]
        vm = VolatilityModel()
        assert vm.detect_regime_change(stable, window=5, threshold=3.0) is False

    def test_volatility_features(self):
        prices = [0.5, 0.51, 0.52, 0.53, 0.54, 0.55, 0.56, 0.57, 0.58, 0.59]
        vm = VolatilityModel()
        features = vm.get_volatility_features(prices)
        assert "realized_vol" in features
        assert "parkinson_vol" in features
        assert features["realized_vol"] > 0


# ---------------------------------------------------------------------------
# weight_learner.py
# ---------------------------------------------------------------------------
from predmarket.weight_learner import WeightLearner


class TestWeightLearner:
    def test_uniform_before_min_observations(self):
        wl = WeightLearner(["a", "b", "c"], min_observations=5)
        w = wl.get_weights()
        assert abs(w["a"] - 1 / 3) < 0.01

    def test_adapts_after_observations(self):
        wl = WeightLearner(["good", "bad"], min_observations=3)
        # "good" component is accurate, "bad" is not
        for _ in range(5):
            wl.update({"good": 0.9, "bad": 0.1}, outcome=1)
            wl.update({"good": 0.1, "bad": 0.9}, outcome=0)
        w = wl.get_weights()
        assert w["good"] > w["bad"]

    def test_confidence_increases(self):
        wl = WeightLearner(["a"], min_observations=2)
        wl.update({"a": 0.6}, 1)
        _, c1 = wl.get_weights_with_confidence()
        wl.update({"a": 0.7}, 1)
        _, c2 = wl.get_weights_with_confidence()
        assert c2 >= c1


# ---------------------------------------------------------------------------
# bayesian.py
# ---------------------------------------------------------------------------
from predmarket.bayesian import BayesianForecaster, BetaPosterior, HierarchicalEventModel


class TestBayesian:
    def test_beta_posterior_update(self):
        bp = BetaPosterior(alpha=1.0, beta=1.0)
        assert abs(bp.mean() - 0.5) < 0.01
        bp.update(1)
        assert bp.mean() > 0.5
        bp.update(0)
        assert bp.mean() < 1.0

    def test_credible_interval(self):
        bp = BetaPosterior(alpha=10, beta=10)
        lo, hi = bp.credible_interval(0.9)
        assert lo < 0.5 < hi
        assert hi - lo < 0.6

    def test_to_density_forecast(self):
        bp = BetaPosterior(alpha=5, beta=3)
        df = bp.to_density_forecast()
        assert isinstance(df, DensityForecast)
        assert len(df.samples) == 1000

    def test_hierarchical_shrinkage(self):
        hem = HierarchicalEventModel()
        # Add lots of outcomes for one contract
        for _ in range(20):
            hem.update("political", "CON-1", outcome=1, weight=0.5)
        # New contract should shrink toward category mean
        est = hem.get_shrinkage_estimate("political", "CON-NEW")
        assert 0.0 < est < 1.0

    def test_bayesian_forecaster(self):
        bf = BayesianForecaster()
        snap = _make_snapshot(mid=0.6)
        df = bf.forecast(snap, "political", nlp_signal=0.7, base_rate=0.3)
        assert isinstance(df, DensityForecast)
        assert 0.0 < df.mean < 1.0


# ---------------------------------------------------------------------------
# ml_timeseries.py
# ---------------------------------------------------------------------------
from predmarket.ml_timeseries import BaggedForecaster, FeatureEngineer, XGBoostForecaster


class TestMLTimeseries:
    def test_feature_engineer(self):
        fe = FeatureEngineer()
        features = fe.extract_features([0.5, 0.51, 0.52, 0.53, 0.54, 0.55])
        assert "lag_1" in features
        assert "rolling_mean_3" in features
        assert "momentum_1" in features
        assert len(features) >= 10

    def test_xgboost_cold_start(self):
        xgb = XGBoostForecaster()
        # No training data -> returns 0.5
        f = xgb.forecast([0.5, 0.51, 0.52])
        assert f == 0.5

    def test_xgboost_forecast_density(self):
        xgb = XGBoostForecaster()
        # Train on simple data
        histories = [[float(i) / 100 for i in range(10)] for _ in range(5)]
        outcomes = [0.1, 0.1, 0.1, 0.1, 0.1]
        xgb.fit(histories, outcomes)
        df = xgb.forecast_density([0.05, 0.06, 0.07, 0.08, 0.09])
        assert isinstance(df, DensityForecast)

    def test_bagged_forecaster(self):
        from predmarket.baselines import HistoricalMeanBaseline, NaiveBaseline

        bf = BaggedForecaster([NaiveBaseline(), HistoricalMeanBaseline()])
        snap = _make_snapshot(mid=0.6)
        f = bf.forecast(snap.line_history)
        assert 0.0 < f < 1.0


# ---------------------------------------------------------------------------
# aggregator.py
# ---------------------------------------------------------------------------
from predmarket.aggregator import ExternalForecast, PlatformAggregator


class TestAggregator:
    def test_add_and_aggregate(self):
        pa = PlatformAggregator()
        pa.add_forecast(ExternalForecast("Metaculus", "CON-1", 0.65, 1000, 50, time.time()))
        pa.add_forecast(ExternalForecast("Manifold", "CON-1", 0.70, 500, 30, time.time()))
        prob = pa.get_aggregated_probability("CON-1")
        assert 0.6 < prob < 0.8

    def test_calibration_updates(self):
        pa = PlatformAggregator()
        pa.update_calibration("Metaculus", 0.6, 1)
        pa.update_calibration("Metaculus", 0.8, 0)
        # Weights may be empty until forecasts are added; verify no crash
        weights = pa.get_platform_weights()
        assert isinstance(weights, dict)

    def test_aggregated_density(self):
        pa = PlatformAggregator()
        pa.add_forecast(ExternalForecast("Metaculus", "CON-1", 0.6, 1000, 50, time.time()))
        df = pa.get_aggregated_density("CON-1")
        assert isinstance(df, DensityForecast)


# ---------------------------------------------------------------------------
# features.py
# ---------------------------------------------------------------------------
from predmarket.features import FeatureStore


class TestFeatures:
    def test_temporal_features(self):
        fs = FeatureStore()
        features = fs.get_temporal_features(time.time())
        assert "day_of_week" in features
        assert "is_weekend" in features
        assert 0 <= features["day_of_week"] <= 6

    def test_market_features(self):
        fs = FeatureStore()
        snap = _make_snapshot(mid=0.6)
        features = fs.get_market_features(snap)
        assert "bid_ask_spread" in features
        assert "volatility_5" in features

    def test_full_feature_vector(self):
        fs = FeatureStore()
        snap = _make_snapshot(mid=0.6)
        vec = fs.get_feature_vector(snap, time.time(), "political")
        names = fs.get_feature_names()
        assert len(vec) == len(names)
        assert len(vec) >= 15


# ---------------------------------------------------------------------------
# backtester.py
# ---------------------------------------------------------------------------
from predmarket.backtester import Backtester


class TestBacktester:
    def test_walk_forward(self):
        history = []
        now = time.time()
        for i in range(60):
            history.append(
                {
                    "timestamp": now - (60 - i) * 86400,
                    "contract_id": "CON-1",
                    "model_prob": 0.6 + 0.01 * (i % 5),
                    "market_implied": 0.55,
                    "category": "political",
                    "status": "READY",
                    "outcome": 1 if i % 3 == 0 else 0,
                }
            )
        bt = Backtester(history)
        results = bt.run_walk_forward(train_window=20, test_window=5, step=5)
        assert len(results) > 0
        assert results[0].brier_mean >= 0

    def test_rolling_brier(self):
        history = [
            {
                "timestamp": i * 100,
                "contract_id": "C",
                "model_prob": 0.7,
                "market_implied": 0.5,
                "category": "econ",
                "status": "READY",
                "outcome": 1,
            }
            for i in range(30)
        ]
        bt = Backtester(history)
        rb = bt.compute_rolling_brier(window=10)
        assert len(rb) > 0

    def test_summary(self):
        history = [
            {
                "timestamp": i,
                "contract_id": "C",
                "model_prob": 0.6,
                "market_implied": 0.5,
                "category": "econ",
                "status": "READY",
                "outcome": 1,
            }
            for i in range(20)
        ]
        bt = Backtester(history)
        s = bt.summary()
        assert isinstance(s, str)
        assert "Brier" in s


# ---------------------------------------------------------------------------
# judgment.py
# ---------------------------------------------------------------------------
from predmarket.judgment import JudgmentResponse, JudgmentTracker, StructuredJudgmentProtocol


class TestJudgment:
    def test_create_request(self):
        sjp = StructuredJudgmentProtocol()
        req = sjp.create_judgment_request(
            {
                "contract_id": "CON-1",
                "model_prob": 0.8,
                "market_implied": 0.5,
                "category": "political",
                "venue": "Polymarket",
                "edge": 0.3,
            }
        )
        assert len(req.structured_questions) > 0

    def test_validate_response(self):
        sjp = StructuredJudgmentProtocol()
        resp = JudgmentResponse(
            contract_id="CON-1",
            approved=True,
            confidence=0.8,
            reasoning="Model shows consistent edge over 30 days.",
            concerns=["Liquidity may be insufficient"],
            override_probability=None,
            analyst_id="A1",
            timestamp=time.time(),
        )
        assert sjp.validate_response(resp) is True

    def test_invalid_response_empty_reasoning(self):
        sjp = StructuredJudgmentProtocol()
        resp = JudgmentResponse(
            contract_id="CON-1",
            approved=True,
            confidence=0.8,
            reasoning="",
            concerns=[],
            override_probability=None,
            analyst_id="A1",
            timestamp=time.time(),
        )
        assert sjp.validate_response(resp) is False

    def test_judgment_tracker(self, tmp_path):
        jt = JudgmentTracker(db_path=str(tmp_path / "judgment.db"))
        resp = JudgmentResponse(
            contract_id="CON-1",
            approved=True,
            confidence=0.8,
            reasoning="Good edge",
            concerns=[],
            override_probability=None,
            analyst_id="A1",
            timestamp=time.time(),
        )
        jt.record(resp, actual_outcome=1)
        cal = jt.get_analyst_calibration("A1")
        assert "brier_score" in cal


# ---------------------------------------------------------------------------
# horizons.py
# ---------------------------------------------------------------------------
from predmarket.horizons import ForecastHorizon, HorizonSpecificForecaster, HorizonWeightScheduler


class TestHorizons:
    def test_horizon_forecast(self):
        from predmarket.baselines import NaiveBaseline

        hf = HorizonSpecificForecaster(NaiveBaseline())
        snap = _make_snapshot(mid=0.6)
        df = hf.forecast_with_horizon(snap, "political", ForecastHorizon.SHORT)
        assert isinstance(df, DensityForecast)
        # Long horizon should have wider interval than short
        df_short = hf.forecast_with_horizon(snap, "political", ForecastHorizon.INTRADAY)
        df_long = hf.forecast_with_horizon(snap, "political", ForecastHorizon.LONG)
        assert (df_long.upper_90 - df_long.lower_90) > (df_short.upper_90 - df_short.lower_90)

    def test_all_horizons(self):
        from predmarket.baselines import NaiveBaseline

        hf = HorizonSpecificForecaster(NaiveBaseline())
        results = hf.forecast_all_horizons(_make_snapshot(), "political")
        assert len(results) == 4
        assert ForecastHorizon.INTRADAY in results

    def test_scheduler(self):
        hws = HorizonWeightScheduler()
        h = hws.get_recommended_horizon(3600)  # 1 hour
        assert h == ForecastHorizon.INTRADAY
        h = hws.get_recommended_horizon(86400 * 30)  # 30 days
        assert h == ForecastHorizon.LONG


# ---------------------------------------------------------------------------
# elections.py
# ---------------------------------------------------------------------------
from predmarket.elections import ElectionModel


class TestElections:
    def test_fundamental_forecast(self):
        em = ElectionModel()
        prob = em.fundamental_forecast(
            {
                "gdp_growth": 2.5,
                "inflation": 2.0,
                "unemployment_change": -0.5,
            }
        )
        assert 0.0 < prob < 1.0

    def test_polling_aggregate(self):
        em = ElectionModel()
        polls = [
            {"date": time.time() - 86400, "yes_share": 0.55, "sample_size": 1000},
            {"date": time.time() - 86400 * 5, "yes_share": 0.50, "sample_size": 800},
            {"date": time.time() - 86400 * 10, "yes_share": 0.48, "sample_size": 600},
        ]
        prob = em.polling_aggregate(polls)
        assert 0.4 < prob < 0.7

    def test_expert_aggregate(self):
        em = ElectionModel()
        experts = [{"probability": p} for p in [0.5, 0.6, 0.7, 0.55, 0.65]]
        prob = em.expert_aggregate(experts)
        assert abs(prob - 0.6) < 0.05

    def test_combined_forecast(self):
        em = ElectionModel()
        df = em.combined_election_forecast(
            economic_data={"gdp_growth": 2.0, "inflation": 3.0, "unemployment_change": 0.5},
            polls=[{"date": time.time() - 86400, "yes_share": 0.6, "sample_size": 1000}],
            experts=[{"probability": 0.55}],
        )
        assert isinstance(df, DensityForecast)


# ---------------------------------------------------------------------------
# diffusion.py
# ---------------------------------------------------------------------------
from predmarket.diffusion import LogisticGrowthModel, MarketLiquidityModel


class TestDiffusion:
    def test_logistic_fit(self):
        t = np.linspace(0, 20, 50)
        y = 1000 / (1 + np.exp(-0.5 * (t - 10)))
        lgm = LogisticGrowthModel()
        lgm.fit(t.tolist(), y.tolist())
        sat = lgm.predict_saturation()
        assert 800 < sat < 1200

    def test_logistic_time_to_percent(self):
        t = np.linspace(0, 20, 50)
        y = 1000 / (1 + np.exp(-0.5 * (t - 10)))
        lgm = LogisticGrowthModel()
        lgm.fit(t.tolist(), y.tolist())
        t80 = lgm.predict_time_to_percent(0.8)
        assert t80 > 0

    def test_market_liquidity(self):
        oi_history = [100 * (i + 1) for i in range(20)] + [2000 + 100 * i for i in range(10)]
        mlm = MarketLiquidityModel()
        result = mlm.estimate_liquidity_trajectory(oi_history)
        assert "current_stage" in result
        assert result["predicted_peak_oi"] > 0


# ---------------------------------------------------------------------------
# forecasting_pipeline.py
# ---------------------------------------------------------------------------
from predmarket.config import load_config
from predmarket.forecasting_pipeline import ForecastingPipeline


class TestForecastingPipeline:
    def test_generate_forecast(self):
        config = load_config()
        pipeline = ForecastingPipeline(config)
        snap = _make_snapshot(mid=0.6)
        result = pipeline.generate_forecast(
            snapshot=snap,
            category="political",
            headline="Congress passes new legislation",
            question="Will the bill become law?",
            timestamp=time.time(),
        )
        assert "point_forecast" in result
        assert "density_forecast" in result
        assert "all_components" in result
        assert "weights" in result
        assert "baseline_comparison" in result
        assert 0.0 < result["point_forecast"] < 1.0
        assert isinstance(result["density_forecast"], DensityForecast)

    def test_pipeline_status(self):
        config = load_config()
        pipeline = ForecastingPipeline(config)
        status = pipeline.get_status()
        assert isinstance(status, dict)
        # Verify at least one component is present
        assert len(status) > 0
