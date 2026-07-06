"""Read-only WebSocket market data client for Kalshi.

Provides real-time market data streaming via the Kalshi WebSocket API.
Supports multiplexed subscriptions over pooled connections (capped at 5
per account). Auto-reconnect with exponential backoff. Order placement
remains REST-only (:mod:`predmarket.kalshi_live_client`).

Typical usage::

    async with KalshiWebSocketClient(config) as client:
        await client.subscribe(["KXBTCD-24H", "KXETH-24H"])
        async for event in client.messages():
            print(event.ticker, event.yes_bid, event.yes_ask)
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

import websockets
import websockets.asyncio.client
from websockets.asyncio.client import ClientConnection

from predmarket.kalshi_live_client import (
    KalshiTradingClientConfig,
    load_private_key,
    sign_pss_text,
    signing_message,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ConnectionLimitExceeded(RuntimeError):  # noqa: N818
    """Raised when attempting to open more than the max allowed connections."""


class WebSocketPermanentFailure(RuntimeError):  # noqa: N818
    """Raised after max reconnect attempts have been exhausted."""


class WebSocketClientClosed(RuntimeError):  # noqa: N818
    """Raised when an operation is attempted on a disconnected/closed client."""


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarketDataEvent:
    """A parsed ticker event from the Kalshi WebSocket API."""

    ticker: str
    yes_bid: float
    yes_ask: float
    last_price: float
    timestamp: int  # Unix milliseconds


# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------


class _ConnectionState(Enum):
    INITIAL = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    RECONNECTING = auto()
    DISCONNECTED = auto()  # Terminal: all reconnect attempts exhausted
    CLOSED = auto()  # Intentional: user called disconnect()


# Module-level connection counter (shared across client instances, per process).
_connection_count: int = 0
_connection_lock: asyncio.Lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Message parsing
# ---------------------------------------------------------------------------


def _parse_ticker_message(raw: str) -> MarketDataEvent | None:
    """Parse a raw WebSocket text message into a ``MarketDataEvent``.

    Returns ``None`` for non-ticker messages (subscribed, error, etc.) or
    malformed payloads.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("ws_unparseable_message raw=%.200r", raw)
        return None

    if not isinstance(data, dict):
        return None

    msg_type = data.get("type")
    if msg_type != "ticker":
        return None

    msg: dict[str, Any] | None = data.get("msg")
    if not isinstance(msg, dict):
        return None

    ticker: str | None = msg.get("market_ticker")
    yes_bid_raw: Any = msg.get("yes_bid_dollars")
    yes_ask_raw: Any = msg.get("yes_ask_dollars")
    price_raw: Any = msg.get("price_dollars")
    ts_ms: Any = msg.get("ts_ms")

    if not all([ticker, yes_bid_raw, yes_ask_raw, price_raw, ts_ms is not None]):
        logger.debug("ws_ticker_missing_fields ticker=%s", ticker)
        return None

    try:
        yes_bid = float(yes_bid_raw)
        yes_ask = float(yes_ask_raw)
        last_price = float(price_raw)
        timestamp = int(ts_ms)
    except (TypeError, ValueError):
        logger.debug("ws_ticker_parse_failure ticker=%s", ticker)
        return None

    return MarketDataEvent(
        ticker=str(ticker),
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        last_price=last_price,
        timestamp=timestamp,
    )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class KalshiWebSocketClient:
    """Read-only WebSocket market data client for Kalshi.

    Manages a single authenticated WebSocket connection (one of up to
    ``MAX_CONNECTIONS`` pooled per process) and provides an async iterator
    of :class:`MarketDataEvent` objects.

    Parameters
    ----------
    config:
        Kalshi API client configuration (base URL, credentials).
    _immediate_fail:
        Test-only flag: if ``True``, all connect attempts raise
        :class:`OSError` so that the reconnect loop can be exercised.
    """

    MAX_CONNECTIONS: int = 5
    BASE_BACKOFF: float = 1.0
    MAX_BACKOFF: float = 30.0
    MAX_RECONNECT_ATTEMPTS: int = 10
    PING_INTERVAL: int = 10
    PING_TIMEOUT: int = 5

    def __init__(
        self,
        config: KalshiTradingClientConfig,
        *,
        _immediate_fail: bool = False,
    ) -> None:
        self._config = config
        self._private_key = load_private_key(config.private_key_pem_or_path)
        self._test_immediate_fail = _immediate_fail

        # Configurable backoff (overridable for tests).
        self._base_backoff: float = self.BASE_BACKOFF
        self._max_backoff: float = self.MAX_BACKOFF
        self._max_reconnect_attempts: int = self.MAX_RECONNECT_ATTEMPTS

        # Ticker subscriptions managed by this client.
        self._subscribed_tickers: set[str] = set()
        # Monotonically increasing message id for subscription commands.
        self._msg_id: int = 1
        # The active WebSocket connection (None when disconnected/initial).
        self._ws: ClientConnection | None = None
        # Connection state machine.
        self._state: _ConnectionState = _ConnectionState.INITIAL
        # Internal event to signal consumers to stop.
        self._closed_event: asyncio.Event = asyncio.Event()
        # Reconnect attempt counter (unused but kept for interface).
        self._reconnect_attempts: int = 0

        self._acquire_pool_slot()

    # ------------------------------------------------------------------
    # Pool management
    # ------------------------------------------------------------------

    def _acquire_pool_slot(self) -> None:
        global _connection_count
        if _connection_count >= self.MAX_CONNECTIONS:
            raise ConnectionLimitExceeded(
                f"Maximum of {self.MAX_CONNECTIONS} concurrent WebSocket "
                f"connections reached. Close an existing connection first."
            )
        _connection_count += 1

    def _release_pool_slot(self) -> None:
        global _connection_count
        if _connection_count > 0:
            _connection_count -= 1

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _ws_auth_headers(self) -> dict[str, str]:
        """Generate the same RSA-PSS auth headers used by the REST client.

        The WebSocket handshake uses::

            timestamp + "GET" + "/trade-api/ws/v2"
        """
        import time

        timestamp = str(int(time.time() * 1000))
        message = signing_message(
            timestamp=timestamp,
            method="GET",
            api_prefix="/trade-api",
            endpoint_path="/ws/v2",
        )
        return {
            "KALSHI-ACCESS-KEY": self._config.api_key,
            "KALSHI-ACCESS-SIGNATURE": sign_pss_text(self._private_key, message),
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
        }

    @staticmethod
    def _ws_url(base_url: str) -> str:
        """Derive the WebSocket URL from a REST base URL."""
        rest_host = base_url.replace("https://", "").split("/")[0]
        ws_host = rest_host.replace("api.", "api-ws.", 1)
        return f"wss://{ws_host}/trade-api/ws/v2"

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def _connect(self) -> ClientConnection:
        """Open a new authenticated WebSocket connection."""
        url = self._ws_url(self._config.base_url)
        headers = self._ws_auth_headers()

        if self._test_immediate_fail:
            raise OSError("Simulated connection failure (test mode)")

        ws = await websockets.asyncio.client.connect(
            url,
            additional_headers=headers,
            ping_interval=self.PING_INTERVAL,
            ping_timeout=self.PING_TIMEOUT,
            close_timeout=5,
        )
        return ws

    async def _resubscribe(self) -> None:
        """Re-issue all active subscriptions after a reconnect."""
        if self._subscribed_tickers:
            await self._send_subscribe(list(self._subscribed_tickers))

    async def _send_subscribe(self, tickers: list[str]) -> None:
        """Send a subscribe command for the ticker channel."""
        if not self._ws:
            return
        msg_id = self._msg_id
        self._msg_id += 1
        payload = {
            "id": msg_id,
            "cmd": "subscribe",
            "params": {
                "channels": ["ticker"],
                "market_tickers": tickers,
            },
        }
        await self._ws.send(json.dumps(payload))

    async def _send_unsubscribe(self, tickers: list[str]) -> None:
        """Send an unsubscribe command for specific tickers."""
        if not self._ws:
            return
        msg_id = self._msg_id
        self._msg_id += 1
        payload = {
            "id": msg_id,
            "cmd": "unsubscribe",
            "params": {
                "channels": ["ticker"],
                "market_tickers": tickers,
            },
        }
        await self._ws.send(json.dumps(payload))

    async def _reconnect(self) -> None:
        """Attempt reconnection with exponential backoff.

        After ``MAX_RECONNECT_ATTEMPTS`` consecutive failures the client
        enters the terminal ``DISCONNECTED`` state and raises
        :class:`WebSocketPermanentFailure`.
        """
        self._state = _ConnectionState.RECONNECTING
        attempt = 0
        while attempt < self._max_reconnect_attempts:
            if self._closed_event.is_set():
                return

            delay = min(self._base_backoff * (2**attempt), self._max_backoff)
            logger.info(
                "ws_reconnect_attempt attempt=%d delay=%.1f",
                attempt + 1,
                delay,
            )
            await asyncio.sleep(delay)

            try:
                self._ws = await self._connect()
            except OSError:
                logger.warning("ws_reconnect_failed attempt=%d", attempt + 1)
                attempt += 1
                continue

            self._reconnect_attempts = 0
            self._state = _ConnectionState.CONNECTED
            logger.info("ws_reconnected")

            try:
                await self._resubscribe()
            except Exception:
                logger.exception("ws_resubscribe_failed")
            return

        self._state = _ConnectionState.DISCONNECTED
        self._ws = None
        raise WebSocketPermanentFailure(
            f"Failed to reconnect after {self._max_reconnect_attempts} attempts"
        )

    # ------------------------------------------------------------------
    # Connection setup helper (extracted for complexity)
    # ------------------------------------------------------------------

    async def _ensure_connected(self) -> None:
        """Open initial connection if not yet connected."""
        if self._ws is not None or self._state != _ConnectionState.INITIAL:
            return
        self._state = _ConnectionState.CONNECTING
        try:
            self._ws = await self._connect()
            self._state = _ConnectionState.CONNECTED
            await self._resubscribe()
        except OSError:
            await self._reconnect()
            if self._state is _ConnectionState.DISCONNECTED:
                raise WebSocketPermanentFailure("Initial connection failed") from None

    # ------------------------------------------------------------------
    # Message receive helper (extracted for complexity)
    # ------------------------------------------------------------------

    async def _recv_with_reconnect(self) -> str | None:
        """Receive one message, handling reconnect on disconnect.

        Returns ``None`` on graceful timeout (keep looping).
        """
        assert self._ws is not None

        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=30)
        except TimeoutError:
            return None
        except websockets.ConnectionClosed:
            logger.warning("ws_connection_closed")
            self._ws = None
            self._state = _ConnectionState.RECONNECTING
            await self._reconnect()
            # Reconnected: caller should loop to receive next message.
            return None

        return raw if isinstance(raw, str) else None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def subscribe(self, tickers: list[str]) -> None:
        """Subscribe to ticker updates for the given market tickers.

        Multiple calls are additive. All tickers are multiplexed over the
        same underlying WebSocket connection.
        """
        if self._state is _ConnectionState.CLOSED:
            raise WebSocketClientClosed("Client is closed")
        if self._state is _ConnectionState.DISCONNECTED:
            raise WebSocketPermanentFailure("Client is in terminal disconnected state")

        new_tickers = [t for t in tickers if t not in self._subscribed_tickers]
        if not new_tickers:
            return

        self._subscribed_tickers.update(new_tickers)

        if self._ws is not None:
            try:
                await self._send_subscribe(new_tickers)
            except websockets.ConnectionClosed:
                logger.info("ws_subscribe_connection_closed tickers=%s", new_tickers)

    async def unsubscribe(self, tickers: list[str]) -> None:
        """Unsubscribe from ticker updates for the given market tickers."""
        if self._state is _ConnectionState.CLOSED:
            raise WebSocketClientClosed("Client is closed")

        known = [t for t in tickers if t in self._subscribed_tickers]
        if not known:
            return

        self._subscribed_tickers.difference_update(known)

        if self._ws is not None:
            try:
                await self._send_unsubscribe(known)
            except websockets.ConnectionClosed:
                pass

    async def messages(self) -> AsyncIterator[MarketDataEvent]:
        """Async generator yielding parsed :class:`MarketDataEvent` objects.

        On unexpected disconnect the generator will attempt to reconnect
        with exponential backoff. If reconnection fails permanently it
        raises :class:`WebSocketPermanentFailure`.
        """
        if self._state is _ConnectionState.CLOSED:
            raise WebSocketClientClosed("Client is closed")

        await self._ensure_connected()

        while not self._closed_event.is_set():
            if self._state is _ConnectionState.DISCONNECTED:
                raise WebSocketPermanentFailure("Client is in terminal disconnected state")
            # CLOSED check: if disconnect() was called from another task.
            if self._state.value == _ConnectionState.CLOSED.value:
                return

            raw = await self._recv_with_reconnect()
            if raw is None:
                continue

            event = _parse_ticker_message(raw)
            if event is not None:
                yield event

    async def disconnect(self) -> None:
        """Close the WebSocket connection and release pool resources.

        Safe to call multiple times.
        """
        if self._state in (_ConnectionState.CLOSED, _ConnectionState.DISCONNECTED):
            return

        self._closed_event.set()
        self._state = _ConnectionState.CLOSED

        ws = self._ws
        self._ws = None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                logger.debug("ws_close_ignored", exc_info=True)

        self._release_pool_slot()

    async def __aenter__(self) -> KalshiWebSocketClient:
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc_val: object,
        exc_tb: object,
    ) -> None:
        await self.disconnect()
