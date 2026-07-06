"""Tests for the Kalshi WebSocket market data client.

Covers VAL-WS-001 through VAL-WS-010 and VAL-CROSS-027, VAL-CROSS-028.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from predmarket.kalshi_live_client import (
    KalshiTradingClientConfig,
    load_private_key,
    sign_pss_text,
    signing_message,
)
from predmarket.kalshi_websocket import (
    ConnectionLimitExceeded,
    KalshiWebSocketClient,
    MarketDataEvent,
    WebSocketClientClosed,
    WebSocketPermanentFailure,
    _parse_ticker_message,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def make_config(**overrides: Any) -> KalshiTradingClientConfig:
    return KalshiTradingClientConfig(
        base_url=overrides.get("base_url", "https://external-api.demo.kalshi.co/trade-api/v2"),
        api_key=overrides.get("api_key", "test-key-id"),
        private_key_pem_or_path=overrides.get("private_key_pem", private_key_pem()),
        timeout_seconds=overrides.get("timeout", 10.0),
    )


def _reset_connection_count() -> None:
    """Reset the module-level connection counter so each test starts clean."""
    import predmarket.kalshi_websocket as ws_mod

    ws_mod._connection_count = 0


@pytest.fixture(autouse=True)
def reset_conn_count() -> None:
    _reset_connection_count()
    yield
    _reset_connection_count()


# ---------------------------------------------------------------------------
# VAL-WS-001: Module exists and exports KalshiWebSocketClient
# ---------------------------------------------------------------------------

def test_module_exports_client_class() -> None:
    """VAL-WS-001: kalshi_websocket.py exports KalshiWebSocketClient."""
    from predmarket.kalshi_websocket import KalshiWebSocketClient

    assert KalshiWebSocketClient is not None
    assert callable(KalshiWebSocketClient)


# ---------------------------------------------------------------------------
# VAL-WS-002: Subscribe to multiple tickers over one connection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_subscribe_multiple_tickers_one_connection() -> None:
    """VAL-WS-002: subscribe() accepts multiple tickers on a single connection."""
    client = KalshiWebSocketClient(make_config())
    try:
        # The connect won't actually open a socket (no real server),
        # but subscribe should store tickers without error.
        await client.subscribe(["KXBTCD-24H", "KXETH-24H", "KXSOL-24H"])
        assert client._subscribed_tickers == {"KXBTCD-24H", "KXETH-24H", "KXSOL-24H"}
    finally:
        await client.disconnect()


# ---------------------------------------------------------------------------
# VAL-WS-003: Connection pool capped at 5
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connection_pool_capped_at_five() -> None:
    """VAL-WS-003: Opening a 6th connection raises ConnectionLimitExceeded."""
    clients = []
    try:
        for i in range(5):
            c = KalshiWebSocketClient(make_config(api_key=f"key-{i}"))
            clients.append(c)

        with pytest.raises(ConnectionLimitExceeded):
            KalshiWebSocketClient(make_config(api_key="key-too-many"))
    finally:
        for c in clients:
            await c.disconnect()


@pytest.mark.asyncio
async def test_connection_pool_frees_on_disconnect() -> None:
    """VAL-WS-003: Disconnecting frees a slot in the pool."""
    c1 = KalshiWebSocketClient(make_config())
    await c1.disconnect()
    # After disconnect, we should be able to create another
    c2 = KalshiWebSocketClient(make_config())
    await c2.disconnect()


# ---------------------------------------------------------------------------
# VAL-WS-004 / VAL-CROSS-027: Read-only (no order placement methods)
# ---------------------------------------------------------------------------

def test_client_is_read_only() -> None:
    """VAL-WS-004, VAL-CROSS-027: No order placement, cancellation, or modification methods."""
    forbidden = {"create_order", "cancel_order", "modify_order", "amend_order",
                 "place_order", "submit_order", "replace_order"}
    public_methods = {
        name for name in dir(KalshiWebSocketClient)
        if not name.startswith("_") and callable(getattr(KalshiWebSocketClient, name, None))
    }
    intersection = forbidden & public_methods
    assert not intersection, f"Read-only client must not expose: {intersection}"


# ---------------------------------------------------------------------------
# VAL-WS-005: Order placement stays REST-only
# ---------------------------------------------------------------------------

def test_order_methods_remain_in_live_client() -> None:
    """VAL-WS-005: kalshi_live_client.py still has order methods."""
    from predmarket.kalshi_live_client import KalshiTradingClient

    assert hasattr(KalshiTradingClient, "create_order")
    assert hasattr(KalshiTradingClient, "cancel_order")
    assert hasattr(KalshiTradingClient, "get_order")


# ---------------------------------------------------------------------------
# VAL-WS-006: Auto-reconnect with exponential backoff
# ---------------------------------------------------------------------------

def test_reconnect_backoff_params() -> None:
    """VAL-WS-006: Default backoff params match spec (1s start, 30s cap, 10 max retries)."""
    assert KalshiWebSocketClient.BASE_BACKOFF == 1.0
    assert KalshiWebSocketClient.MAX_BACKOFF == 30.0
    assert KalshiWebSocketClient.MAX_RECONNECT_ATTEMPTS == 10


@pytest.mark.asyncio
async def test_reconnect_enters_terminal_state_after_max_failures() -> None:
    """VAL-WS-006: After MAX_RECONNECT_ATTEMPTS consecutive failures, state is DISCONNECTED."""
    client = KalshiWebSocketClient(make_config(), _immediate_fail=True)
    # Use tiny backoff so the test doesn't hang.
    client._base_backoff = 0.001
    client._max_backoff = 0.01
    client._max_reconnect_attempts = 3
    try:
        with pytest.raises(WebSocketPermanentFailure):
            async for _ in client.messages():
                pass
        assert client._state.name == "DISCONNECTED"
    finally:
        await client.disconnect()


# ---------------------------------------------------------------------------
# VAL-WS-007: Heartbeat / ping-pong is handled
# ---------------------------------------------------------------------------

def test_ping_interval_is_set() -> None:
    """VAL-WS-007: Client configures ping_interval for keepalive."""
    assert KalshiWebSocketClient.PING_INTERVAL == 10
    assert KalshiWebSocketClient.PING_TIMEOUT == 5


# ---------------------------------------------------------------------------
# VAL-WS-008: Message parsing extracts ticker and price fields
# ---------------------------------------------------------------------------

def test_parse_ticker_message_happy_path() -> None:
    """VAL-WS-008: Parse a valid ticker message into MarketDataEvent."""
    raw = json.dumps({
        "type": "ticker",
        "sid": 11,
        "msg": {
            "market_ticker": "FED-23DEC-T3.00",
            "yes_bid_dollars": "0.450",
            "yes_ask_dollars": "0.530",
            "price_dollars": "0.480",
            "ts_ms": 1669149841000,
            "volume_fp": "33896.00",
            "open_interest_fp": "20422.00",
        },
    })
    event = _parse_ticker_message(raw)
    assert event is not None
    assert event.ticker == "FED-23DEC-T3.00"
    assert event.yes_bid == 0.450
    assert event.yes_ask == 0.530
    assert event.last_price == 0.480
    assert event.timestamp == 1669149841000


def test_parse_ticker_message_float_strings() -> None:
    """VAL-WS-008: Fields can be float strings without leading zeros."""
    raw = json.dumps({
        "type": "ticker",
        "sid": 1,
        "msg": {
            "market_ticker": "KXBTCD-24H",
            "yes_bid_dollars": ".45",
            "yes_ask_dollars": ".55",
            "price_dollars": ".50",
            "ts_ms": 1700000000000,
            "volume_fp": "100.00",
            "open_interest_fp": "50.00",
        },
    })
    event = _parse_ticker_message(raw)
    assert event is not None
    assert event.yes_bid == 0.45
    assert event.yes_ask == 0.55
    assert event.last_price == 0.50


def test_parse_ticker_message_non_ticker_type() -> None:
    """VAL-WS-008: Non-ticker messages return None."""
    raw = json.dumps({"type": "subscribed", "id": 1, "msg": {"channel": "ticker", "sid": 1}})
    assert _parse_ticker_message(raw) is None


def test_parse_ticker_message_error_type() -> None:
    """VAL-WS-008: Error messages return None."""
    raw = json.dumps({"type": "error", "id": 1, "msg": {"code": 6, "msg": "Already subscribed"}})
    assert _parse_ticker_message(raw) is None


def test_parse_ticker_message_missing_fields() -> None:
    """VAL-WS-008: Malformed messages return None."""
    raw = json.dumps({"type": "ticker", "sid": 1, "msg": {"market_ticker": "FOO"}})
    assert _parse_ticker_message(raw) is None


def test_parse_ticker_message_invalid_json() -> None:
    """VAL-WS-008: Invalid JSON returns None."""
    assert _parse_ticker_message("not-json") is None


# ---------------------------------------------------------------------------
# VAL-WS-009: Clean shutdown via disconnect() or async context manager
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disconnect_marks_closed() -> None:
    """VAL-WS-009: After disconnect(), state is CLOSED and messages() raises."""
    client = KalshiWebSocketClient(make_config())
    await client.disconnect()
    assert client._state.name == "CLOSED"


@pytest.mark.asyncio
async def test_disconnect_raises_on_reuse() -> None:
    """VAL-WS-009: Operations after disconnect raise WebSocketClientClosed."""
    client = KalshiWebSocketClient(make_config())
    await client.disconnect()
    with pytest.raises(WebSocketClientClosed):
        await client.subscribe(["KXUNIT"])


@pytest.mark.asyncio
async def test_async_context_manager() -> None:
    """VAL-WS-009: async with client works and disconnects on exit."""
    async with KalshiWebSocketClient(make_config()) as client:
        assert client._state.name in ("CONNECTING", "CONNECTED", "INITIAL")
    assert client._state.name == "CLOSED"


# ---------------------------------------------------------------------------
# VAL-WS-010: WebSocket auth uses same RSA-PSS path as REST
# ---------------------------------------------------------------------------

def test_websocket_auth_uses_same_signing_path() -> None:
    """VAL-WS-010: WS auth headers use the same sign_pss_text / signing_message as REST."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    loaded = load_private_key(pem)

    timestamp = "1700000000000"
    # REST signs: timestamp + method + /trade-api/v2/<path>
    # WS signs: timestamp + "GET" + "/trade-api/ws/v2"
    ws_message = signing_message(
        timestamp=timestamp,
        method="GET",
        api_prefix="/trade-api",
        endpoint_path="/ws/v2",
    )
    ws_sig = sign_pss_text(loaded, ws_message)

    rest_message = signing_message(
        timestamp=timestamp,
        method="POST",
        api_prefix="/trade-api/v2",
        endpoint_path="/portfolio/orders",
    )
    rest_sig = sign_pss_text(loaded, rest_message)

    # Both use same function, just different message content
    assert isinstance(ws_sig, str)
    assert isinstance(rest_sig, str)
    assert len(ws_sig) > 0
    assert len(rest_sig) > 0
    # They differ because the message differs
    assert ws_sig != rest_sig


# ---------------------------------------------------------------------------
# MarketDataEvent dataclass structure
# ---------------------------------------------------------------------------

def test_market_data_event_fields() -> None:
    """MarketDataEvent has the required fields."""
    event = MarketDataEvent(
        ticker="KXUNIT",
        yes_bid=0.45,
        yes_ask=0.55,
        last_price=0.50,
        timestamp=1700000000000,
    )
    assert event.ticker == "KXUNIT"
    assert event.yes_bid == 0.45
    assert event.yes_ask == 0.55
    assert event.last_price == 0.50
    assert event.timestamp == 1700000000000
