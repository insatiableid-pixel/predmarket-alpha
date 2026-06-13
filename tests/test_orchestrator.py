import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from main import platform_loop, seed_historical_data
from predmarket.config import Config, GlobalConfig
from predmarket.ingest import MarketSnapshot

@pytest.fixture
def mock_platform_components():
    config = MagicMock(spec=Config)
    
    ingest = AsyncMock()
    # Mocking get_all_snapshots to return one snapshot
    ingest.get_all_snapshots.return_value = [
        MarketSnapshot(
            venue="Kalshi",
            contract_id="CON-1",
            title="Will event X happen?",
            bid=0.55,
            ask=0.57,
            last_price=0.56,
            open_interest=10000.0,
            volume_24h=2000.0,
            line_history=[0.56]
        )
    ]
    
    forecaster = MagicMock()
    forecaster.generate_ensemble_forecast.return_value = {
        "contract_id": "CON-1",
        "model_prob": 0.65,
        "market_implied": 0.56,
        "status": "READY"
    }
    
    risk = MagicMock()
    risk.check_drawdown_circuit_breaker.return_value = (False, 0.0)
    risk.check_market_filters.return_value = "READY"
    risk.optimize_portfolio_kelly.return_value = [
        {
            "venue": "Kalshi",
            "contract_id": "CON-1",
            "category": "political",
            "status": "READY",
            "recommended_fraction": 0.05,
            "recommended_usd": 500.0,
            "market_implied": 0.56,
            "model_prob": 0.65
        }
    ]
    
    execution = AsyncMock()
    execution.execute_order.return_value = {"status": "FILLED"}
    
    audit = MagicMock()
    
    return config, ingest, forecaster, risk, execution, audit

@pytest.mark.asyncio
async def test_platform_loop_single_iteration(mock_platform_components, monkeypatch):
    config, ingest, forecaster, risk, execution, audit = mock_platform_components
    
    # We patch asyncio.sleep to raise a KeyboardInterrupt to break the infinite while loop
    # after the first successful iteration.
    sleep_calls = []
    async def mock_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 1:
            raise KeyboardInterrupt("Stop loop")
    monkeypatch.setattr(asyncio, "sleep", mock_sleep)
    
    # Run loop
    with pytest.raises(KeyboardInterrupt, match="Stop loop"):
        await platform_loop(config, ingest, forecaster, risk, execution, audit)
        
    # Verify method calls
    risk.check_drawdown_circuit_breaker.assert_called_once()
    ingest.get_all_snapshots.assert_called_once()
    risk.check_market_filters.assert_called_once()
    forecaster.generate_ensemble_forecast.assert_called_once()
    risk.optimize_portfolio_kelly.assert_called_once()
    execution.execute_order.assert_called_once()
    audit.log_equity.assert_called_once()

@pytest.mark.asyncio
async def test_platform_loop_circuit_breaker_halt(mock_platform_components, monkeypatch):
    config, ingest, forecaster, risk, execution, audit = mock_platform_components
    
    # Trigger circuit breaker
    risk.check_drawdown_circuit_breaker.return_value = (True, 0.25)
    
    sleep_calls = []
    async def mock_sleep(seconds):
        sleep_calls.append(seconds)
        raise KeyboardInterrupt("Stop loop")
    monkeypatch.setattr(asyncio, "sleep", mock_sleep)
    
    with pytest.raises(KeyboardInterrupt, match="Stop loop"):
        await platform_loop(config, ingest, forecaster, risk, execution, audit)
        
    # Verify that ingest and downstream calls were skipped during halt
    ingest.get_all_snapshots.assert_not_called()
    execution.execute_order.assert_not_called()
