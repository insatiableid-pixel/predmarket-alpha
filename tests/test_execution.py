import pytest
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
