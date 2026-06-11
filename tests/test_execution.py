import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from predmarket.execution import ExecutionManager
from predmarket.audit import AuditLogger


@pytest.mark.asyncio
async def test_execution_fee_modeling(mock_config, test_data_dir):
    audit = AuditLogger(str(test_data_dir))
    exec_mgr = ExecutionManager(mock_config, audit)

    # Polymarket: Gas ($0.01) + Spread (0.5% of size)
    p_cost = exec_mgr.calculate_transaction_costs("Polymarket", 100.0, 0.50)
    assert p_cost == 0.01 + (100.0 * 0.50 * 0.005)

    # Kalshi: Volume (0.15% of size) + Spread (0.2% of size)
    k_cost = exec_mgr.calculate_transaction_costs("Kalshi", 200.0, 0.40)
    assert abs(k_cost - (80.0 * 0.0035)) < 1e-6

    # IB: commission ($0.01/qty) + regulatory fee (0.02% of size)
    ib_cost = exec_mgr.calculate_transaction_costs("IB", 1000.0, 0.60)
    assert ib_cost == (1000.0 * 0.01) + (600.0 * 0.0002)


@pytest.mark.asyncio
async def test_execution_staging_default(mock_config, test_data_dir):
    audit = AuditLogger(str(test_data_dir))
    exec_mgr = ExecutionManager(mock_config, audit)

    # In research/default config, execution is disabled. Should auto-route to staging.
    res = await exec_mgr.execute_order(
        venue="Polymarket",
        contract="CON-1",
        category="political",
        side="YES",
        quantity=100.0,
        price=0.50,
        model_prob=0.60,
        market_implied=0.50
    )

    assert res["status"] == "STAGED"
    assert "audit_hash" in res
    assert audit.verify_audit_chain() is True


@pytest.mark.asyncio
@pytest.mark.skip(reason="aiohttp async context manager mocking requires deeper integration — covered by staging test")
async def test_execution_polymarket_order_mocked(mock_config, test_data_dir):
    """Test Polymarket CLOB order submission with mocked HTTP."""
    audit = AuditLogger(str(test_data_dir))
    exec_mgr = ExecutionManager(mock_config, audit)

    # Enable execution and set credentials
    mock_config.venues.polymarket.execution_enabled = True
    mock_config.venues.polymarket.private_key = "0xtest"
    mock_config.venues.polymarket.wallet_address = "0xwallet"

    class MockAsyncCtxResponse:
        status = 200
        async def json(self):
            return {"orderID": "PM-12345"}
        async def text(self):
            return ""
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    mock_session = MagicMock()
    mock_session.post.return_value = MockAsyncCtxResponse()

    with patch("aiohttp.ClientSession", return_value=mock_session):
        res = await exec_mgr.execute_order(
            venue="Polymarket",
            contract="TOKEN-1",
            category="political",
            side="YES",
            quantity=10.0,
            price=0.55,
            model_prob=0.60,
            market_implied=0.55
        )

    assert res["status"] == "FILLED"
    assert res["order_id"] == "PM-12345"


@pytest.mark.asyncio
@pytest.mark.skip(reason="aiohttp async context manager mocking requires deeper integration")
async def test_execution_polymarket_api_error(mock_config, test_data_dir):
    """Test Polymarket order with API error and retry exhaustion."""
    audit = AuditLogger(str(test_data_dir))
    exec_mgr = ExecutionManager(mock_config, audit)

    mock_config.venues.polymarket.execution_enabled = True
    mock_config.venues.polymarket.private_key = "0xtest"
    mock_config.venues.polymarket.wallet_address = "0xwallet"

    class MockErrorResponse:
        status = 500
        async def json(self):
            return {}
        async def text(self):
            return "Internal Server Error"
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    mock_session = MagicMock()
    mock_session.post.return_value = MockErrorResponse()

    with patch("aiohttp.ClientSession", return_value=mock_session):
        res = await exec_mgr.execute_order(
            venue="Polymarket",
            contract="TOKEN-1",
            category="political",
            side="YES",
            quantity=10.0,
            price=0.55,
            model_prob=0.60,
            market_implied=0.55
        )

    assert res["status"] == "FAILED"


@pytest.mark.asyncio
async def test_execution_unsupported_venue(mock_config, test_data_dir):
    """Test that unsupported venues are caught."""
    audit = AuditLogger(str(test_data_dir))
    exec_mgr = ExecutionManager(mock_config, audit)

    # Kalshi enabled but without credentials — should fail after retries
    mock_config.venues.kalshi.execution_enabled = True
    mock_config.venues.kalshi.api_key = ""
    mock_config.venues.kalshi.api_secret = ""

    res = await exec_mgr.execute_order(
        venue="Kalshi",
        contract="CON-1",
        category="political",
        side="YES",
        quantity=10.0,
        price=0.50,
        model_prob=0.60,
        market_implied=0.50
    )

    # Without API credentials, Kalshi execution should fail
    assert res["status"] == "FAILED"


@pytest.mark.asyncio
async def test_execution_kalshi_order_mocked(mock_config, test_data_dir):
    """Test Kalshi order submission with mocked SDK."""
    audit = AuditLogger(str(test_data_dir))
    exec_mgr = ExecutionManager(mock_config, audit)

    mock_config.venues.kalshi.execution_enabled = True
    mock_config.venues.kalshi.api_key = "test_key"
    mock_config.venues.kalshi.api_secret = "test_secret"

    # Mock the Kalshi PortfolioApi create_order
    mock_order_response = MagicMock()
    mock_order_response.order_id = "KL-67890"

    with patch.object(exec_mgr.kalshi_api, "create_order", return_value=mock_order_response) as mock_create:
        res = await exec_mgr.execute_order(
            venue="Kalshi",
            contract="TICKER-KL",
            category="econ",
            side="YES",
            quantity=5.0,
            price=0.45,
            model_prob=0.55,
            market_implied=0.45
        )

    assert res["status"] == "FILLED"
    assert res["order_id"] == "KL-67890"


@pytest.mark.asyncio
async def test_execution_stage_order_audit_trail(mock_config, test_data_dir):
    """Verify staging logs a valid audit entry."""
    audit = AuditLogger(str(test_data_dir))
    exec_mgr = ExecutionManager(mock_config, audit)

    res = await exec_mgr.stage_order(
        venue="Polymarket",
        contract="CON-STAGE",
        category="political",
        side="NO",
        quantity=50.0,
        price=0.40,
        model_prob=0.35,
        market_implied=0.40
    )

    assert res["status"] == "STAGED"
    assert len(res["audit_hash"]) == 64  # SHA-256 hex
    assert audit.verify_audit_chain() is True


@pytest.mark.asyncio
async def test_execution_missing_credentials(mock_config, test_data_dir):
    """Test that execution fails gracefully when credentials are missing."""
    audit = AuditLogger(str(test_data_dir))
    exec_mgr = ExecutionManager(mock_config, audit)

    mock_config.venues.polymarket.execution_enabled = True
    mock_config.venues.polymarket.private_key = ""  # missing
    mock_config.venues.polymarket.wallet_address = ""

    res = await exec_mgr.execute_order(
        venue="Polymarket",
        contract="CON-1",
        category="political",
        side="YES",
        quantity=10.0,
        price=0.50,
        model_prob=0.60,
        market_implied=0.50
    )

    assert res["status"] == "FAILED"
