import logging
import asyncio
import time
from typing import Dict, Any, Optional, Callable, Awaitable
import kalshi_python
from predmarket.config import Config
from predmarket.audit import AuditLogger


logger = logging.getLogger("predmarket.execution")
ACTION_VENUE = "kalshi"

class ExecutionManager:
    def __init__(
        self,
        config: Config,
        audit_logger: AuditLogger,
        api_retry_limit: int = 3,
        base_throttle_seconds: float = 0.1,
        retry_backoff_seconds: float = 1.0,
        retry_jitter_seconds: float = 0.5,
        blocking_call_runner: Optional[Callable[..., Awaitable[Any]]] = None,
    ):
        self.config = config
        self.audit_logger = audit_logger
        self.api_retry_limit = api_retry_limit
        self.base_throttle_seconds = base_throttle_seconds
        self.retry_backoff_seconds = retry_backoff_seconds
        self.retry_jitter_seconds = retry_jitter_seconds
        self.blocking_call_runner = blocking_call_runner or asyncio.to_thread
        
        # Instantiate Kalshi PortfolioApi if kalshi is enabled
        self.kalshi_api = None
        if self.config.venues.kalshi.enabled:
            k_cfg = self.config.venues.kalshi
            if k_cfg.api_key and k_cfg.api_secret:
                config_kalshi = kalshi_python.Configuration()
                config_kalshi.host = k_cfg.effective_api_url
                config_kalshi.api_key = k_cfg.api_key
                config_kalshi.api_secret = k_cfg.api_secret
                self.kalshi_api = kalshi_python.PortfolioApi(kalshi_python.ApiClient(config_kalshi))

    def _record_failed_order(
        self,
        *,
        venue: str,
        contract: str,
        category: str,
        side: str,
        quantity: float,
        price: float,
        model_prob: float,
        market_implied: float,
        details: str,
    ) -> Dict[str, Any]:
        net_edge = model_prob - market_implied - 0.01
        entry_hash = self.audit_logger.log_trade_intent(
            venue=venue,
            contract=contract,
            category=category,
            side=side,
            size=quantity * price,
            price=price,
            model_prob=model_prob,
            market_implied=market_implied,
            net_edge=net_edge,
            status="FAILED",
            details=details,
        )
        logger.warning("ORDER-REJECTED: %s | %s | %s", venue, contract, details)
        return {
            "status": "FAILED",
            "audit_hash": entry_hash,
            "venue": venue,
            "contract": contract,
            "side": side,
            "quantity": quantity,
            "price": price,
            "details": details,
        }

    def calculate_transaction_costs(self, venue: str, quantity: float, price: float) -> float:
        """
        Explicit transaction cost model for executable venues.
        """
        size_usd = quantity * price

        if venue.lower() == ACTION_VENUE:
            # Volume-based exchange fee (approx 0.1%) + spread
            volume_fee = size_usd * 0.0015
            spread_slippage = size_usd * 0.002
            return volume_fee + spread_slippage

        raise ValueError(f"Unsupported action venue for transaction costs: {venue}. Kalshi is the only executable venue.")

    async def stage_order(
        self,
        venue: str,
        contract: str,
        category: str,
        side: str,
        quantity: float,
        price: float,
        model_prob: float,
        market_implied: float
    ) -> Dict[str, Any]:
        """
        Stages a trade intent for review or paper trading logs.
        """
        if venue.lower() != ACTION_VENUE:
            return self._record_failed_order(
                venue=venue,
                contract=contract,
                category=category,
                side=side,
                quantity=quantity,
                price=price,
                model_prob=model_prob,
                market_implied=market_implied,
                details=f"Non-action venue: {venue}. Kalshi is the only executable venue.",
            )

        net_edge = model_prob - market_implied - 0.01
        
        # Log to immutable audit database
        entry_hash = self.audit_logger.log_trade_intent(
            venue=venue,
            contract=contract,
            category=category,
            side=side,
            size=quantity * price,
            price=price,
            model_prob=model_prob,
            market_implied=market_implied,
            net_edge=net_edge,
            status="STAGED",
            details="Staged for human approval queue or paper verification."
        )
        
        logger.info(f"ORDER-STAGED: {venue} | {contract} | {side} {quantity} @ {price} | Hash: {entry_hash[:8]}")
        return {
            "status": "STAGED",
            "audit_hash": entry_hash,
            "venue": venue,
            "contract": contract,
            "side": side,
            "quantity": quantity,
            "price": price
        }

    async def execute_order(
        self,
        venue: str,
        contract: str,
        category: str,
        side: str,
        quantity: float,
        price: float,
        model_prob: float,
        market_implied: float
    ) -> Dict[str, Any]:
        """
        Executes a trade on the venue's API.
        Enforces execution_enabled flags and rate limits.
        """
        venue_lower = venue.lower()
        net_edge = model_prob - market_implied - 0.01
        if venue_lower != ACTION_VENUE:
            return self._record_failed_order(
                venue=venue,
                contract=contract,
                category=category,
                side=side,
                quantity=quantity,
                price=price,
                model_prob=model_prob,
                market_implied=market_implied,
                details=f"Non-action venue: {venue}. Kalshi is the only executable venue.",
            )

        execution_enabled = self.config.venues.kalshi.execution_enabled
        if not execution_enabled:
            # Fall back to staging if execution is disabled (Research Mode)
            logger.info(f"Execution disabled for {venue}. Routing to stage_order instead.")
            return await self.stage_order(
                venue=venue,
                contract=contract,
                category=category,
                side=side,
                quantity=quantity,
                price=price,
                model_prob=model_prob,
                market_implied=market_implied
            )

        # Log intent to audit database PRIOR to execution to establish complete audit trail
        entry_hash = self.audit_logger.log_trade_intent(
            venue=venue,
            contract=contract,
            category=category,
            side=side,
            size=quantity * price,
            price=price,
            model_prob=model_prob,
            market_implied=market_implied,
            net_edge=net_edge,
            status="EXECUTING",
            details="Routing order to API client."
        )

        logger.info(f"ORDER-ROUTED: {venue} | {contract} | {side} {quantity} @ {price} | Pre-exec Hash: {entry_hash[:8]}")

        # Execute order on the APIs
        retries = 0
        backoff = self.retry_backoff_seconds
        while retries < self.api_retry_limit:
            try:
                # Enforce API rate limits with exponential backoff + jitter
                if self.base_throttle_seconds > 0:
                    await asyncio.sleep(self.base_throttle_seconds)
                
                if not self.kalshi_api:
                    raise ValueError("Kalshi API not initialized.")

                # For Kalshi: specify side as yes/no and action as buy/sell.
                order_req = kalshi_python.CreateOrderRequest(
                    ticker=contract,
                    side=side.lower(),
                    action="buy",
                    count=int(max(quantity, 1)),
                    type="limit",
                    yes_price=int(price * 100) if side.lower() == "yes" else None,
                    no_price=int(price * 100) if side.lower() == "no" else None
                )

                resp = await self.blocking_call_runner(self.kalshi_api.create_order, create_order_request=order_req)
                order_id = getattr(resp, "order_id", f"KL-{int(time.time())}")
                
                # Log success completion
                self.audit_logger.log_system_event(
                    "TRADE_COMPLETED",
                    f"Successfully filled order {order_id} on {venue}. Fill Qty: {quantity} @ {price}."
                )
                
                logger.info(f"ORDER-FILLED: {venue} | ID: {order_id} | Qty: {quantity} @ {price}")
                return {
                    "status": "FILLED",
                    "order_id": order_id,
                    "audit_hash": entry_hash,
                    "venue": venue,
                    "contract": contract,
                    "side": side,
                    "quantity": quantity,
                    "price": price
                }
            except Exception as e:
                # Handle exceptions with backoff + jitter
                retries += 1
                jitter = time.time() % self.retry_jitter_seconds if self.retry_jitter_seconds > 0 else 0.0
                sleep_time = backoff + jitter
                logger.warning(f"API-ERROR: Order submission to {venue} failed: {e}. Retrying in {sleep_time:.2f}s (Attempt {retries}/{self.api_retry_limit}).")
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                backoff *= 2.0

        # Halt order and mark as failed
        self.audit_logger.log_system_event(
            "TRADE_FAILED",
            f"Execution failed on {venue} for contract {contract} after {self.api_retry_limit} attempts."
        )
        return {
            "status": "FAILED",
            "audit_hash": entry_hash,
            "venue": venue,
            "contract": contract,
            "side": side,
            "quantity": quantity,
            "price": price
        }
