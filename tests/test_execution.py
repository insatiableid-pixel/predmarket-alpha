import pytest
from unittest.mock import MagicMock
from predmarket.execution import ExecutionManager
from predmarket.audit import AuditLogger


async def run_blocking_inline(func, *args, **kwargs):
    return func(*args, **kwargs)


def make_execution_manager(config, audit_logger, **overrides):
    params = {
        "api_retry_limit": 1,
        "base_throttle_seconds": 0.0,
        "retry_backoff_seconds": 0.0,
        "retry_jitter_seconds": 0.0,
        "blocking_call_runner": run_blocking_inline,
    }
    params.update(overrides)
    return ExecutionManager(config, audit_logger, **params)


@pytest.mark.asyncio
async def test_execution_fee_modeling(mock_config, test_data_dir):
    audit = AuditLogger(str(test_data_dir))
    exec_mgr = make_execution_manager(mock_config, audit)

    # Kalshi: Volume (0.15% of size) + Spread (0.2% of size)
    k_cost = exec_mgr.calculate_transaction_costs("Kalshi", 200.0, 0.40)
    assert abs(k_cost - (80.0 * 0.0035)) < 1e-6

    with pytest.raises(ValueError, match="Kalshi is the only executable venue"):
        exec_mgr.calculate_transaction_costs("Polymarket", 100.0, 0.50)

    with pytest.raises(ValueError, match="Unsupported action venue"):
        exec_mgr.calculate_transaction_costs("LegacyVenue", 1000.0, 0.60)


@pytest.mark.asyncio
async def test_execution_staging_default(mock_config, test_data_dir):
    audit = AuditLogger(str(test_data_dir))
    exec_mgr = make_execution_manager(mock_config, audit)

    # In research/default config, execution is disabled. Should auto-route to staging.
    res = await exec_mgr.execute_order(
        venue="Kalshi",
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
async def test_execution_rejects_polymarket_action(mock_config, test_data_dir):
    """Polymarket can be market context, but never an order target."""
    audit = AuditLogger(str(test_data_dir))
    exec_mgr = make_execution_manager(mock_config, audit)

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
    assert "Kalshi is the only executable venue" in res["details"]
    assert audit.verify_audit_chain() is True


@pytest.mark.asyncio
async def test_stage_order_rejects_polymarket(mock_config, test_data_dir):
    """Non-Kalshi venues cannot enter the staged approval queue."""
    audit = AuditLogger(str(test_data_dir))
    exec_mgr = make_execution_manager(mock_config, audit)

    res = await exec_mgr.stage_order(
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
    assert "Kalshi is the only executable venue" in res["details"]
    assert audit.verify_audit_chain() is True


@pytest.mark.asyncio
async def test_execution_unsupported_venue(mock_config, test_data_dir):
    """Test that unsupported venues are caught."""
    audit = AuditLogger(str(test_data_dir))
    exec_mgr = make_execution_manager(mock_config, audit)

    res = await exec_mgr.execute_order(
        venue="UnknownVenue",
        contract="CON-1",
        category="political",
        side="YES",
        quantity=10.0,
        price=0.50,
        model_prob=0.60,
        market_implied=0.50
    )

    assert res["status"] == "FAILED"
    assert "audit_hash" in res
    assert audit.verify_audit_chain() is True


@pytest.mark.asyncio
async def test_execution_kalshi_missing_credentials(mock_config, test_data_dir):
    """Kalshi execution fails fast when no API client is available."""
    audit = AuditLogger(str(test_data_dir))

    # Kalshi enabled but without credentials — should fail after retries
    mock_config.venues.kalshi.enabled = False
    mock_config.venues.kalshi.execution_enabled = True
    mock_config.venues.kalshi.api_key = ""
    mock_config.venues.kalshi.api_secret = ""
    exec_mgr = make_execution_manager(mock_config, audit)

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

    mock_config.venues.kalshi.enabled = False
    mock_config.venues.kalshi.execution_enabled = True
    exec_mgr = make_execution_manager(mock_config, audit)

    # Mock the Kalshi PortfolioApi create_order
    mock_order_response = MagicMock()
    mock_order_response.order_id = "KL-67890"
    exec_mgr.kalshi_api = MagicMock()
    exec_mgr.kalshi_api.create_order.return_value = mock_order_response

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
    exec_mgr.kalshi_api.create_order.assert_called_once()


@pytest.mark.asyncio
async def test_execution_retry_exhaustion(mock_config, test_data_dir):
    """Retry exhaustion is deterministic and does not sleep in tests."""
    audit = AuditLogger(str(test_data_dir))

    mock_config.venues.kalshi.enabled = False
    mock_config.venues.kalshi.execution_enabled = True
    exec_mgr = make_execution_manager(mock_config, audit, api_retry_limit=3)
    exec_mgr.kalshi_api = MagicMock()
    exec_mgr.kalshi_api.create_order.side_effect = RuntimeError("transient API failure")

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

    assert res["status"] == "FAILED"
    assert exec_mgr.kalshi_api.create_order.call_count == 3


@pytest.mark.asyncio
async def test_execution_stage_order_audit_trail(mock_config, test_data_dir):
    """Verify Kalshi staging logs a valid audit entry."""
    audit = AuditLogger(str(test_data_dir))
    exec_mgr = make_execution_manager(mock_config, audit)

    res = await exec_mgr.stage_order(
        venue="Kalshi",
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
async def test_execution_unknown_venue_rejected_before_staging(mock_config, test_data_dir):
    """Test that unsupported venues fail before staging."""
    audit = AuditLogger(str(test_data_dir))
    exec_mgr = make_execution_manager(mock_config, audit)

    res = await exec_mgr.execute_order(
        venue="UnknownVenue",
        contract="CON-1",
        category="political",
        side="YES",
        quantity=10.0,
        price=0.50,
        model_prob=0.60,
        market_implied=0.50
    )

    assert res["status"] == "FAILED"
    assert "Kalshi is the only executable venue" in res["details"]
