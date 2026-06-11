import pytest
import sqlite3
from fastapi.testclient import TestClient
from predmarket.dashboard import app, server, get_db_connection, fetch_performance_metrics, update_dashboard_data, approve_staged_order_db, get_staged_orders, approve_order_endpoint, ApprovalRequest
import predmarket.dashboard as db_module

@pytest.fixture
def setup_dashboard_db(test_data_dir, monkeypatch):
    # Setup database file
    db_path = test_data_dir / "database.sqlite"
    
    # Patch get_db_connection in dashboard module to use our test DB
    def mock_get_db_connection():
        return sqlite3.connect(str(db_path))
    monkeypatch.setattr(db_module, "get_db_connection", mock_get_db_connection)
    
    # Initialize DB tables
    conn = mock_get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_trail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            event_type TEXT NOT NULL,
            venue TEXT,
            contract TEXT,
            category TEXT,
            side TEXT,
            size REAL,
            price REAL,
            model_prob REAL,
            market_implied REAL,
            net_edge REAL,
            status TEXT,
            details TEXT,
            prev_hash TEXT NOT NULL,
            entry_hash TEXT NOT NULL,
            outcome INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS equity_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            total_equity REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    return db_path

def test_dashboard_layout():
    # Verify layout contains essential component IDs and types
    assert app.layout is not None
    layout_str = str(app.layout)
    assert "calibration-curve-plot" in layout_str
    assert "equity-history-plot" in layout_str
    assert "opportunity-board-table" in layout_str
    assert "position-sizing-slate" in layout_str
    assert "error-banner" in layout_str

def test_performance_metrics_empty(setup_dashboard_db):
    metrics = fetch_performance_metrics()
    assert metrics["brier_score"] == 0.0
    assert metrics["pnl"] == 0.0
    assert metrics["win_rate"] == 0.0

def test_performance_metrics_with_data(setup_dashboard_db):
    # Seed mock resolved trades
    conn = db_module.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO audit_trail (
            timestamp, event_type, venue, contract, category, side, size, price,
            model_prob, market_implied, net_edge, status, details, prev_hash, entry_hash, outcome
        ) VALUES (123456.0, 'TRADE_INTENT', 'Polymarket', 'CON-1', 'political', 'YES', 100.0, 0.55, 0.60, 0.55, 0.04, 'FILLED', 'detail', 'h1', 'h2', 1)
    """)
    cursor.execute("""
        INSERT INTO equity_history (timestamp, total_equity) VALUES (123456.0, 10000.0)
    """)
    conn.commit()
    conn.close()
    
    metrics = fetch_performance_metrics()
    # model_prob = 0.60, outcome = 1 -> Brier score = (0.60 - 1.0)^2 = 0.16
    assert abs(metrics["brier_score"] - 0.16) < 1e-5
    assert metrics["pnl"] > 0
    assert metrics["win_rate"] == 1.0

def test_dashboard_callback_update(setup_dashboard_db):
    res = update_dashboard_data(0)
    assert len(res) == 9 # 9 outputs returned
    brier, logloss, pnl, drawdown, cal_fig, eq_fig, opp_table, slate, err = res
    assert brier is not None
    assert logloss is not None
    assert pnl is not None
    assert drawdown is not None
    assert err is None # no errors

@pytest.mark.asyncio
async def test_fastapi_endpoints(setup_dashboard_db):
    # Seed a staged trade
    conn = db_module.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO audit_trail (
            timestamp, event_type, venue, contract, category, side, size, price,
            model_prob, market_implied, net_edge, status, details, prev_hash, entry_hash, outcome
        ) VALUES (123456.0, 'TRADE_INTENT', 'Kalshi', 'CON-2', 'econ', 'YES', 100.0, 0.45, 0.55, 0.45, 0.09, 'STAGED', 'detail', 'h1', 'h2', NULL)
    """)
    conn.commit()
    conn.close()
    
    # 1. Test get_staged_orders function
    staged_list = get_staged_orders(api_key="predmarket_secret_key_123")
    assert len(staged_list) == 1
    assert staged_list[0]["contract"] == "CON-2"
    staged_id = staged_list[0]["id"]
    
    # 2. Test approve_order_endpoint function
    # Since we are using mock execution (execution disabled by default on Kalshi),
    # approving should route to stage_order and return success or execute order.
    res_json = await approve_order_endpoint(ApprovalRequest(id=staged_id), api_key="predmarket_secret_key_123")
    assert "status" in res_json

def test_api_key_authentication_routing(setup_dashboard_db):
    client = TestClient(server)
    
    # 1. Request without X-API-Key header should return 401 Unauthorized
    response = client.get("/api/staged")
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"
    
    # 2. Request with invalid key should return 401 Unauthorized
    response = client.get("/api/staged", headers={"X-API-Key": "wrong_key"})
    assert response.status_code == 401
    
    # 3. Request with valid key should succeed and return 200 OK
    response = client.get("/api/staged", headers={"X-API-Key": "predmarket_secret_key_123"})
    assert response.status_code == 200
