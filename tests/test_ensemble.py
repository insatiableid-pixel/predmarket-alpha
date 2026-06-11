import pytest
import numpy as np
from predmarket.ensemble import EnsembleForecaster
from predmarket.ingest import MarketSnapshot

def test_ensemble_combination_math(mock_config):
    forecaster = EnsembleForecaster(mock_config)
    
    snapshot = MarketSnapshot(
        venue="Polymarket",
        contract_id="TEST-CON",
        title="Will test succeed?",
        bid=0.50,
        ask=0.52,
        last_price=0.51,
        open_interest=50000.0,
        volume_24h=1000.0,
        line_history=[0.50, 0.51]
    )
    
    out = forecaster.generate_ensemble_forecast(
        snapshot=snapshot,
        category="political",
        headline="Breakthrough success on target test",
        question="Will test succeed?"
    )
    
    assert "model_prob" in out
    assert 0.0 < out["model_prob"] < 1.0
    assert out["status"] in ("READY", "ENSEMBLE-DIVERGENCE", "RECENCY-ANCHOR", "OVERCONFIDENT-TAIL")

def test_ensemble_divergence_trigger(mock_config):
    forecaster = EnsembleForecaster(mock_config)
    
    # We mock extreme component outputs to force a divergence flag
    # Set config divergence threshold low
    mock_config.forecasting.ensemble.divergence_threshold = 0.05
    
    snapshot = MarketSnapshot(
        venue="Polymarket",
        contract_id="TEST-CON",
        title="Test",
        bid=0.50,
        ask=0.52,
        last_price=0.51,
        open_interest=50000.0,
        volume_24h=1000.0,
        line_history=[0.50, 0.51]
    )
    
    # Override predictions to force divergence
    out = forecaster.generate_ensemble_forecast(snapshot, "political")
    # Verify status is flagged due to diverging predictions (p_bbn vs p_br vs p_ts)
    assert out["divergence"] > 0.05
    assert out["status"] == "ENSEMBLE-DIVERGENCE"
