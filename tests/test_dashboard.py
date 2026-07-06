import sqlite3

import pytest
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

import predmarket.dashboard.data as db_module
from predmarket.dashboard import (
    ApprovalRequest,
    app,
    approve_order_endpoint,
    fetch_performance_metrics,
    get_staged_orders,
    update_dashboard_data,
)


def make_request(path="/api/staged", method="GET", headers=None):
    raw_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": raw_headers,
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return StarletteRequest(scope, receive)


@pytest.fixture
def setup_dashboard_db(test_data_dir, monkeypatch):
    # Setup database file
    db_path = test_data_dir / "database.sqlite"

    # Patch get_db_connection in dashboard.data module to use our test DB
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


@pytest.mark.asyncio
async def test_dashboard_callback_update(setup_dashboard_db):
    res = await update_dashboard_data(0)
    assert len(res) == 9  # 9 outputs returned
    brier, logloss, pnl, drawdown, cal_fig, eq_fig, opp_table, slate, err = res
    assert brier is not None
    assert logloss is not None
    assert pnl is not None
    assert drawdown is not None
    assert err is None  # no errors


@pytest.mark.asyncio
async def test_fastapi_endpoints(setup_dashboard_db, mock_config, monkeypatch):
    import predmarket.config as config_module

    monkeypatch.setattr(config_module, "load_config", lambda: mock_config)

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

    # 1. Test get_staged_orders function (slowapi requires a Request object)
    mock_req = make_request()
    staged_list = get_staged_orders(request=mock_req, api_key="test-token")
    assert len(staged_list) == 1
    assert staged_list[0]["contract"] == "CON-2"
    staged_id = staged_list[0]["id"]

    # 2. Test approve_order_endpoint function
    res_json = await approve_order_endpoint(
        request=mock_req, body=ApprovalRequest(id=staged_id), api_key="test-token"
    )
    assert "status" in res_json


def test_api_key_authentication_routing(setup_dashboard_db):
    from fastapi import HTTPException

    from predmarket.dashboard.server import get_api_key

    with pytest.raises(HTTPException) as missing:
        get_api_key(None)
    assert missing.value.status_code == 401
    assert missing.value.detail == "Could not validate credentials"

    with pytest.raises(HTTPException) as invalid:
        get_api_key("wrong_key")
    assert invalid.value.status_code == 401

    assert get_api_key("test-token") == "test-token"
    staged = get_staged_orders(
        request=make_request(headers={"X-API-Key": "test-token"}),
        api_key="test-token",
    )
    assert staged == []


@pytest.mark.asyncio
async def test_basic_auth_middleware(setup_dashboard_db):
    from predmarket.dashboard.server import dashboard_auth_middleware

    async def call_next(_request):
        return Response(status_code=200)

    # 1. Request without Authorization header should return 401
    response = await dashboard_auth_middleware(make_request(path="/"), call_next)
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers

    # 2. Request with invalid Basic credentials should return 401
    import base64

    invalid_token = base64.b64encode(b"admin:wrong_password").decode("utf-8")
    response = await dashboard_auth_middleware(
        make_request(path="/", headers={"Authorization": f"Basic {invalid_token}"}),
        call_next,
    )
    assert response.status_code == 401

    # 3. Request with valid Basic credentials should bypass middleware
    valid_token = base64.b64encode(b"admin:test-token").decode("utf-8")
    response = await dashboard_auth_middleware(
        make_request(path="/", headers={"Authorization": f"Basic {valid_token}"}),
        call_next,
    )
    assert response.status_code == 200
    assert "dashboard_auth=" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_dashboard_auth_cookie_allows_dash_runtime_requests(setup_dashboard_db):
    from predmarket.dashboard.server import (
        dashboard_auth_middleware,
        generate_dashboard_auth_token,
    )

    async def call_next(_request):
        return Response(status_code=200)

    response = await dashboard_auth_middleware(
        make_request(
            path="/_dash-layout",
            headers={"Cookie": f"dashboard_auth={generate_dashboard_auth_token()}"},
        ),
        call_next,
    )

    assert response.status_code == 200
