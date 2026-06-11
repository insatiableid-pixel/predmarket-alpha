import pytest
import sqlite3
import json
from predmarket.audit import AuditLogger

def test_audit_cryptographic_chain(test_data_dir):
    logger = AuditLogger(data_dir=str(test_data_dir))
    
    # Write initial intent
    h1 = logger.log_trade_intent(
        venue="Polymarket",
        contract="CON-1",
        category="political",
        side="YES",
        size=100.0,
        price=0.55,
        model_prob=0.60,
        market_implied=0.55,
        net_edge=0.04,
        status="STAGED"
    )
    
    # Write second intent
    h2 = logger.log_trade_intent(
        venue="Kalshi",
        contract="CON-2",
        category="econ",
        side="NO",
        size=200.0,
        price=0.45,
        model_prob=0.35,
        market_implied=0.45,
        net_edge=-0.09,
        status="STAGED"
    )
    
    assert h1 != h2
    assert logger.verify_audit_chain() is True

def test_audit_tampering_detection(test_data_dir):
    logger = AuditLogger(data_dir=str(test_data_dir))
    
    logger.log_trade_intent("Polymarket", "CON-1", "political", "YES", 100, 0.5, 0.6, 0.5, 0.09, "STAGED")
    logger.log_trade_intent("Kalshi", "CON-2", "econ", "NO", 200, 0.45, 0.35, 0.45, -0.09, "STAGED")
    
    # Tamper with the SQLite database content directly
    conn = sqlite3.connect(str(test_data_dir / "database.sqlite"))
    cursor = conn.cursor()
    cursor.execute("UPDATE audit_trail SET price = 0.99 WHERE id = 1")
    conn.commit()
    conn.close()
    
    # The hash validation must catch the modification and return False
    assert logger.verify_audit_chain() is False
