from __future__ import annotations

import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable, Awaitable

try:
    import aiohttp
except ImportError:  # pragma: no cover - exercised in minimal test envs
    aiohttp = None

try:
    from ib_insync import IB, Contract as IBContract
except ImportError:  # pragma: no cover - exercised in minimal test envs
    IB = None
    IBContract = None

try:
    import kalshi_python
except ImportError:  # pragma: no cover - exercised in minimal test envs
    kalshi_python = None

from predmarket.config import Config

logger = logging.getLogger("predmarket.ingest")

class MarketSnapshot:
    def __init__(
        self,
        venue: str,
        contract_id: str,
        title: str,
        bid: float,
        ask: float,
        last_price: float,
        open_interest: float,
        volume_24h: float,
        line_history: List[float] = None
    ):
        self.venue = venue
        self.contract_id = contract_id
        self.title = title
        self.bid = bid
        self.ask = ask
        self.mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else last_price
        self.last_price = last_price
        self.open_interest = open_interest
        self.volume_24h = volume_24h
        self.line_history = line_history or [last_price]

class MarketIngestManager:
    def __init__(
        self,
        config: Config,
        blocking_call_runner: Optional[Callable[..., Awaitable[Any]]] = None,
    ):
        self.config = config
        self.blocking_call_runner = blocking_call_runner or asyncio.to_thread
        self.ib: Optional[IB] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.polymarket_connected = False
        self.kalshi_connected = False
        self.ib_connected = False
        self.mock_db: Dict[str, MarketSnapshot] = {}
        self._init_mock_data()

    def _init_mock_data(self):
        # Default mock data for paper/fallback mode
        self.mock_db = {
            "PM-US-ELECTION-2026": MarketSnapshot(
                venue="Polymarket",
                contract_id="PM-US-ELECTION-2026",
                title="Will the US Congress pass tax reform in 2026?",
                bid=0.58,
                ask=0.59,
                last_price=0.585,
                open_interest=500000.0,
                volume_24h=120000.0,
                line_history=[0.52, 0.54, 0.55, 0.57, 0.58, 0.585]
            ),
            "KL-FED-RATE-2026": MarketSnapshot(
                venue="Kalshi",
                contract_id="KL-FED-RATE-2026",
                title="Will the FOMC lower target interest rate in Q3 2026?",
                bid=0.42,
                ask=0.43,
                last_price=0.425,
                open_interest=150000.0,
                volume_24h=35000.0,
                line_history=[0.48, 0.46, 0.45, 0.44, 0.43, 0.425]
            ),
            "IB-CPI-JUNE-2026": MarketSnapshot(
                venue="IB",
                contract_id="IB-CPI-JUNE-2026",
                title="US CPI YoY growth for June 2026 exceeds 2.8%",
                bid=0.61,
                ask=0.63,
                last_price=0.62,
                open_interest=25000.0,
                volume_24h=8000.0,
                line_history=[0.58, 0.59, 0.60, 0.61, 0.62]
            )
        }

    async def initialize(self):
        if aiohttp is not None:
            self.session = aiohttp.ClientSession()
        else:
            self.session = None
            logger.warning("aiohttp is not installed. Network venue ingestion is disabled.")
        
        # 1. Polymarket Init
        if self.config.venues.polymarket.enabled:
            await self._connect_polymarket()

        # 2. Kalshi Init
        if self.config.venues.kalshi.enabled:
            await self._connect_kalshi()

        # 3. Interactive Brokers Init
        if self.config.venues.interactive_brokers.enabled:
            await self._connect_ib()

    async def close(self):
        if self.session:
            await self.session.close()
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()

    async def _connect_polymarket(self):
        p_cfg = self.config.venues.polymarket
        if self.session is None:
            logger.warning("Polymarket: HTTP session unavailable. Running in mock/fallback mode.")
            self.polymarket_connected = False
            return
        if not p_cfg.private_key:
            logger.warning("Polymarket: POLYMARKET_PRIVATE_KEY not configured. Running Polymarket in mock/fallback mode.")
            self.polymarket_connected = False
            return
        
        # In a real environment, we would initialize the py-clob-client
        # For this implementation, we check the REST endpoint to confirm network connectivity
        try:
            async with self.session.get(f"{p_cfg.clob_api_url}/markets/health") as resp:
                if resp.status == 200:
                    logger.info("Polymarket CLOB API connection operational.")
                    self.polymarket_connected = True
                else:
                    logger.warning(f"Polymarket API healthcheck returned status {resp.status}. Falling back.")
                    self.polymarket_connected = False
        except Exception as e:
            logger.warning(f"Polymarket CLOB connection failed: {e}. Falling back.")
            self.polymarket_connected = False

    async def _connect_kalshi(self):
        k_cfg = self.config.venues.kalshi
        if kalshi_python is None:
            logger.warning("Kalshi SDK is not installed. Running Kalshi in mock/fallback mode.")
            self.kalshi_connected = False
            return
        if not k_cfg.api_key or not k_cfg.api_secret:
            logger.warning("Kalshi: KALSHI_API_KEY/SECRET not configured. Running Kalshi in mock/fallback mode.")
            self.kalshi_connected = False
            return

        # Attempt to run authentication check against Kalshi API
        try:
            config_kalshi = kalshi_python.Configuration()
            config_kalshi.host = k_cfg.api_url
            config_kalshi.api_key = k_cfg.api_key
            config_kalshi.api_secret = k_cfg.api_secret
            self.kalshi_api = kalshi_python.MarketsApi(kalshi_python.ApiClient(config_kalshi))
            
            # Verify connectivity by performing a test call
            exchange_api = kalshi_python.ExchangeApi(kalshi_python.ApiClient(config_kalshi))
            status = await self.blocking_call_runner(exchange_api.get_exchange_status)
            if status:
                logger.info("Kalshi API v2 client initialized successfully and connected.")
                self.kalshi_connected = True
        except Exception as e:
            logger.warning(f"Kalshi API connection failed: {e}. Falling back.")
            self.kalshi_connected = False

    async def _connect_ib(self):
        ib_cfg = self.config.venues.interactive_brokers
        if IB is None:
            logger.warning("ib_insync is not installed. Running IB in mock/fallback mode.")
            self.ib_connected = False
            return
        self.ib = IB()
        try:
            # We use a short timeout for connection checks to prevent freezing the application
            await asyncio.wait_for(
                self.ib.connectAsync(ib_cfg.host, ib_cfg.port, clientId=ib_cfg.client_id),
                timeout=2.0
            )
            if self.ib.isConnected():
                logger.info(f"Connected to IB Gateway at {ib_cfg.host}:{ib_cfg.port}")
                self.ib_connected = True
                if ib_cfg.live_trading_enabled and ib_cfg.live_confirmed:
                    logger.warning("=== LIVE IB TRADING ACTIVE ===")
                else:
                    logger.info("=== PAPER-MODE-ACTIVE (IB Gateway on Paper Port) ===")
        except Exception as e:
            # Under WSL2, IB Gateway must be running on the host or in WSL.
            # We log a warning with instructions and fallback to mock data
            logger.warning(f"IB-CONNECT-WARNING: Could not connect to IB Gateway at {ib_cfg.host}:{ib_cfg.port} ({e})")
            logger.warning("To connect IB Gateway, ensure TWS/Gateway is running and 'Enable ActiveX and Socket Clients' is enabled on port 4002.")
            self.ib_connected = False

    async def get_market_snapshot(self, contract_id: str) -> MarketSnapshot:
        # If real venue connection is available, query real endpoints; otherwise return mock
        snapshot = self.mock_db.get(contract_id)
        if not snapshot:
            raise ValueError(f"Unknown contract_id: {contract_id}")
        
        # Real connection update logic
        if snapshot.venue == "Polymarket" and self.polymarket_connected:
            try:
                # Query Polymarket CLOB book API
                url = f"{self.config.venues.polymarket.clob_api_url}/book?token_id={contract_id}"
                async with self.session.get(url) as resp:
                    if resp.status == 200:
                        book = await resp.json()
                        bids = book.get("bids", [])
                        asks = book.get("asks", [])
                        if bids:
                            snapshot.bid = float(bids[0].get("price", snapshot.bid))
                        if asks:
                            snapshot.ask = float(asks[0].get("price", snapshot.ask))
                        if bids or asks:
                            snapshot.mid = (snapshot.bid + snapshot.ask) / 2.0
                            snapshot.last_price = snapshot.mid
            except Exception as e:
                logger.warning(f"Failed to fetch live Polymarket book for {contract_id}: {e}")
                
        elif snapshot.venue == "Kalshi" and self.kalshi_connected:
            try:
                # Query Kalshi market orderbook
                book_resp = await self.blocking_call_runner(self.kalshi_api.get_market_orderbook, contract_id)
                book = book_resp.orderbook
                best_bid_yes = None
                best_bid_no = None
                
                if book.true:
                    best_bid_yes = max(level.price for level in book.true)
                if book.false:
                    best_bid_no = max(level.price for level in book.false)
                
                if best_bid_yes is not None:
                    snapshot.bid = float(best_bid_yes) / 100.0
                if best_bid_no is not None:
                    snapshot.ask = float(100 - best_bid_no) / 100.0
                
                if best_bid_yes is not None or best_bid_no is not None:
                    if snapshot.bid == 0 and snapshot.ask > 0:
                        snapshot.bid = snapshot.ask - 0.01
                    elif snapshot.ask == 0 and snapshot.bid > 0:
                        snapshot.ask = snapshot.bid + 0.01
                    snapshot.mid = (snapshot.bid + snapshot.ask) / 2.0
                    snapshot.last_price = snapshot.mid
                    
                market_resp = await self.blocking_call_runner(self.kalshi_api.get_market, contract_id)
                market = market_resp.market
                if market:
                    snapshot.volume_24h = float(getattr(market, "volume24h", getattr(market, "volume", snapshot.volume_24h)))
                    snapshot.open_interest = float(getattr(market, "open_interest", snapshot.open_interest))
            except Exception as e:
                logger.warning(f"Failed to fetch live Kalshi book for {contract_id}: {e}")
                
        elif snapshot.venue == "IB" and self.ib_connected:
            try:
                ib_contract = IBContract()
                if contract_id.isdigit():
                    ib_contract.conId = int(contract_id)
                else:
                    ib_contract.symbol = contract_id
                    ib_contract.secType = "WAR"
                    ib_contract.exchange = "FORECASTEX"
                
                await self.ib.qualifyContractsAsync(ib_contract)
                ticker = self.ib.reqMktData(ib_contract, '', False, False)
                await asyncio.sleep(0.5)
                
                if ticker.bid is not None and ticker.bid > 0:
                    snapshot.bid = ticker.bid
                if ticker.ask is not None and ticker.ask > 0:
                    snapshot.ask = ticker.ask
                if ticker.last is not None and ticker.last > 0:
                    snapshot.last_price = ticker.last
                if snapshot.bid > 0 and snapshot.ask > 0:
                    snapshot.mid = (snapshot.bid + snapshot.ask) / 2.0
                
                self.ib.cancelMktData(ib_contract)
            except Exception as e:
                logger.warning(f"Failed to fetch live IB data for {contract_id}: {e}")

        return snapshot

    async def get_all_snapshots(self) -> List[MarketSnapshot]:
        snapshots = []
        for cid in self.mock_db.keys():
            snapshot = await self.get_market_snapshot(cid)
            snapshots.append(snapshot)
        return snapshots

    # ------------------------------------------------------------------
    # Dynamic contract discovery (B5 remediation)
    # ------------------------------------------------------------------

    async def discover_contracts(self) -> List[MarketSnapshot]:
        """Fetch active markets from connected venues and merge into the snapshot DB.

        For each connected venue, queries the venue's market-list endpoint and
        creates/updates MarketSnapshot entries. Hardcoded mock data is preserved
        as fallback when no live data is available.
        """
        discovered = []

        # --- Polymarket ---
        if self.polymarket_connected and self.session:
            try:
                url = f"{self.config.venues.polymarket.clob_api_url}/markets?limit=20&active=true"
                async with self.session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for m in data.get("data", data if isinstance(data, list) else []):
                            cid = m.get("condition_id", m.get("id", ""))
                            if not cid or cid in self.mock_db:
                                continue
                            question = m.get("question", m.get("title", cid))
                            # Approximate mid from tokens if available
                            tokens = m.get("tokens", [])
                            if tokens:
                                bid = float(tokens[0].get("price", 0.5))
                                ask = bid + 0.01
                            else:
                                bid, ask = 0.50, 0.51
                            snap = MarketSnapshot(
                                venue="Polymarket",
                                contract_id=cid,
                                title=question,
                                bid=bid, ask=ask, last_price=(bid + ask) / 2,
                                open_interest=0.0, volume_24h=0.0,
                            )
                            self.mock_db[cid] = snap
                            discovered.append(snap)
                logger.info(f"Polymarket discovery: {len(discovered)} new contracts")
            except Exception as e:
                logger.warning(f"Polymarket contract discovery failed: {e}")

        # --- Kalshi ---
        if self.kalshi_connected and hasattr(self, "kalshi_api"):
            try:
                resp = await self.blocking_call_runner(self.kalshi_api.get_markets)
                markets = getattr(resp, "markets", [])
                kalshi_count = 0
                for m in markets[:20]:
                    ticker = getattr(m, "ticker", getattr(m, "id", ""))
                    if not ticker or ticker in self.mock_db:
                        continue
                    title = getattr(m, "title", ticker)
                    last = float(getattr(m, "last_price", 0.5))
                    if last <= 0:
                        last = 0.50
                    snap = MarketSnapshot(
                        venue="Kalshi",
                        contract_id=ticker,
                        title=title,
                        bid=last - 0.005, ask=last + 0.005, last_price=last,
                        open_interest=float(getattr(m, "open_interest", 0)),
                        volume_24h=float(getattr(m, "volume24h", getattr(m, "volume", 0))),
                    )
                    self.mock_db[ticker] = snap
                    discovered.append(snap)
                    kalshi_count += 1
                logger.info(f"Kalshi discovery: {kalshi_count} new contracts")
            except Exception as e:
                logger.warning(f"Kalshi contract discovery failed: {e}")

        if discovered:
            logger.info(f"Contract discovery total: {len(discovered)} new contracts merged into snapshot DB")
        else:
            logger.info("Contract discovery: no new contracts found; using existing mock/fallback data")

        return discovered
