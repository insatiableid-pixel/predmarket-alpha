import pytest
from predmarket.ingest import MarketIngestManager, MarketSnapshot

@pytest.mark.asyncio
async def test_ingest_mock_fallback(mock_config):
    manager = MarketIngestManager(mock_config)
    await manager.initialize()
    
    # Check mock data population
    snapshots = await manager.get_all_snapshots()
    assert len(snapshots) == 3
    
    pm_snap = await manager.get_market_snapshot("PM-US-ELECTION-2026")
    assert isinstance(pm_snap, MarketSnapshot)
    assert pm_snap.venue == "Polymarket"
    assert pm_snap.bid == 0.58
    assert pm_snap.ask == 0.59
    assert pm_snap.mid == 0.585
    
    await manager.close()
