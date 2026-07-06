from unittest.mock import AsyncMock, MagicMock

import pytest

from predmarket.ingest import MarketIngestManager, MarketSnapshot


@pytest.mark.asyncio
async def test_ingest_mock_fallback(mock_config):
    manager = MarketIngestManager(mock_config)
    await manager.initialize()

    snapshots = await manager.get_all_snapshots()
    assert len(snapshots) == 2

    pm_snap = await manager.get_market_snapshot("PM-US-ELECTION-2026")
    assert isinstance(pm_snap, MarketSnapshot)
    assert pm_snap.venue == "Polymarket"
    assert pm_snap.bid == 0.58
    assert pm_snap.ask == 0.59
    assert pm_snap.mid == 0.585

    await manager.close()


@pytest.mark.asyncio
async def test_ingest_polymarket_live_fetch(mock_config):
    """Test live Polymarket book fetch with mocked HTTP."""
    manager = MarketIngestManager(mock_config)
    await manager.initialize()

    # Simulate a connected Polymarket client
    manager.polymarket_connected = True

    class MockResponse:
        status = 200

        async def json(self):
            return {
                "bids": [{"price": "0.60", "size": "1000"}],
                "asks": [{"price": "0.62", "size": "800"}],
            }

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    mock_session = MagicMock()
    mock_session.get.return_value = MockResponse()
    mock_session.close = AsyncMock()
    manager.session = mock_session

    snap = await manager.get_market_snapshot("PM-US-ELECTION-2026")

    assert snap.bid == 0.60
    assert snap.ask == 0.62
    assert snap.mid == 0.61
    mock_session.get.assert_called_once()

    await manager.close()


@pytest.mark.asyncio
async def test_ingest_kalshi_live_fetch_mocked(mock_config):
    """Test Kalshi fallback when API is not fully connected."""
    manager = MarketIngestManager(mock_config)
    await manager.initialize()

    # Connected flag set but without real API — falls back to mock
    manager.kalshi_connected = True

    snap = await manager.get_market_snapshot("KL-FED-RATE-2026")

    # Should return mock data since no live API client is available
    assert snap.venue == "Kalshi"
    assert snap.contract_id == "KL-FED-RATE-2026"
    assert 0 < snap.mid < 1

    await manager.close()


@pytest.mark.asyncio
async def test_ingest_unknown_contract(mock_config):
    """Test that unknown contract IDs raise ValueError."""
    manager = MarketIngestManager(mock_config)
    await manager.initialize()

    with pytest.raises(ValueError, match="Unknown contract_id"):
        await manager.get_market_snapshot("NONEXISTENT-CONTRACT")

    await manager.close()


@pytest.mark.asyncio
async def test_ingest_polymarket_api_error_graceful(mock_config):
    """Test that Polymarket API errors fall back to mock data."""
    manager = MarketIngestManager(mock_config)
    await manager.initialize()
    manager.polymarket_connected = True

    class MockErrorResponse:
        status = 503

        async def json(self):
            return {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    mock_session = MagicMock()
    mock_session.get.return_value = MockErrorResponse()
    mock_session.close = AsyncMock()
    manager.session = mock_session

    snap = await manager.get_market_snapshot("PM-US-ELECTION-2026")

    # Should still return the mock snapshot since API failed
    assert snap.bid == 0.58  # original mock value
    assert snap.ask == 0.59
    assert snap.venue == "Polymarket"

    await manager.close()


def test_ingest_snapshot_mid_calculation():
    """Test MarketSnapshot mid-price calculation edge cases."""
    # bid/ask both > 0
    snap = MarketSnapshot(
        "Test",
        "C-1",
        "Title",
        bid=0.50,
        ask=0.52,
        last_price=0.49,
        open_interest=1000,
        volume_24h=100,
    )
    assert snap.mid == 0.51

    # bid=0, should use last_price
    snap2 = MarketSnapshot(
        "Test",
        "C-2",
        "Title",
        bid=0.0,
        ask=0.0,
        last_price=0.60,
        open_interest=1000,
        volume_24h=100,
    )
    assert snap2.mid == 0.60

    # line_history default
    snap3 = MarketSnapshot(
        "Test",
        "C-3",
        "Title",
        bid=0.50,
        ask=0.52,
        last_price=0.51,
        open_interest=1000,
        volume_24h=100,
    )
    assert snap3.line_history == [0.51]
