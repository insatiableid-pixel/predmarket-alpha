import os
import logging
import numpy as np
from typing import Dict, Any, List, Tuple
from scipy.optimize import minimize
from predmarket.config import Config
from predmarket.audit import AuditLogger

logger = logging.getLogger("predmarket.risk")

class RiskManager:
    def __init__(self, config: Config, audit_logger: AuditLogger):
        self.config = config
        self.audit_logger = audit_logger

    def check_drawdown_circuit_breaker(self) -> Tuple[bool, float]:
        """
        Calculates the 30-day rolling drawdown.
        Returns: (is_halted, current_drawdown_pct)
        """
        # Fetch rolling 30-day equity history from audit logger
        # (30 days = 30 * 24 * 3600 seconds)
        thirty_days = 30 * 24 * 3600
        history = self.audit_logger.get_equity_history(thirty_days)
        
        if not history:
            return False, 0.0

        equities = [item["total_equity"] for item in history]
        if not equities:
            return False, 0.0

        current_val = equities[-1]
        peak_val = max(equities)

        if peak_val <= 0:
            return False, 0.0

        drawdown = (peak_val - current_val) / peak_val
        limit = self.config.portfolio.risk_controls.max_drawdown_limit

        if drawdown >= limit:
            # Check for drawdown bypass override environment variable
            override = os.getenv("OVERRIDE_DRAWDOWN_HALT", "false").lower()
            if override == "true":
                logger.warning(f"DRAWDOWN-ALERT: Current drawdown ({drawdown:.2%}) exceeds limit ({limit:.2%}). BYPASSED via OVERRIDE_DRAWDOWN_HALT=true.")
                return False, drawdown
            else:
                logger.error(f"DRAWDOWN-HALT: Current drawdown ({drawdown:.2%}) exceeds limit ({limit:.2%}). All position sizing locked.")
                return True, drawdown

        return False, drawdown

    def check_market_filters(
        self,
        snapshot_mid: float,
        volume_24h: float,
        open_interest: float,
        line_history: List[float]
    ) -> str:
        """
        Validates liquidity, line movement, and bid-ask spread limits.
        Returns status: READY / ILLIQUID / SHARP-MOVE
        """
        # 1. Liquidity check
        if open_interest < self.config.venues.polymarket.min_liquidity_usd:
            return "ILLIQUID"

        # 2. Sharp line movement check (> 5pp in last 30 mins)
        # We assume line_history represents regular time intervals
        if len(line_history) >= 2:
            initial = line_history[0]
            current = line_history[-1]
            shift = abs(current - initial)
            if shift > self.config.portfolio.risk_controls.line_movement_threshold_pct:
                logger.warning(f"SHARP-MOVE detected. Contract shifted {shift:.2%} within history window. Sizing suspended.")
                return "SHARP-MOVE"

        return "READY"

    def optimize_portfolio_kelly(
        self,
        forecasts: List[Dict[str, Any]],
        cash_balance: float
    ) -> List[Dict[str, Any]]:
        """
        Computes correlation-adjusted fractional Kelly sizes across multiple contracts.
        Solves: max_f (f^T g - 0.5 * f^T Sigma f)
        """
        if not forecasts:
            return []

        n_contracts = len(forecasts)
        
        # 1. Extract Edges (g_i = model_prob - market_implied - tx_costs)
        edges = []
        for f in forecasts:
            raw_edge = f["model_prob"] - f["market_implied"]
            # Estimate transaction cost based on venue (spread + commission)
            tx_cost = 0.01 # Simulated transaction fee
            net_edge = raw_edge - tx_cost
            edges.append(net_edge)
        
        g = np.array(edges)

        # 2. Build Covariance Matrix Sigma
        # In a real environment, this is calculated from historical return correlations.
        # Here, we initialize it using a generic category-based block correlation model.
        Sigma = np.eye(n_contracts) * 0.25 # Assume standard asset variance is 0.25 for binary events
        for i in range(n_contracts):
            for j in range(i + 1, n_contracts):
                # If contracts share the same category/topic, assume 0.50 correlation
                if forecasts[i]["category"] == forecasts[j]["category"]:
                    Sigma[i, j] = 0.125 # Covariance = corr * std_i * std_j = 0.50 * 0.50 * 0.50
                    Sigma[j, i] = 0.125

        # 3. Define the Quadratic Optimization Problem
        # Objective function (negative expected log growth for minimization)
        def objective(f):
            return -(np.dot(f, g) - 0.5 * np.dot(f, np.dot(Sigma, f)))

        # Bounds: 0 <= f_i <= max_single_position_pct
        max_single = self.config.portfolio.kelly.max_single_position_pct
        bounds = [(0, max_single) for _ in range(n_contracts)]

        # Constraints:
        # Sum of exposures <= leverage_cap
        # Correlated exposures (same category) <= max_correlated_exposure_pct
        constraints = []
        
        # Leverage constraint
        leverage_cap = self.config.portfolio.kelly.leverage_cap
        constraints.append({
            "type": "ineq",
            "fun": lambda f: leverage_cap - np.sum(np.abs(f))
        })

        # Category correlation constraints
        categories = list(set([f["category"] for f in forecasts]))
        max_corr = self.config.portfolio.kelly.max_correlated_exposure_pct
        for cat in categories:
            indices = [idx for idx, f in enumerate(forecasts) if f["category"] == cat]
            constraints.append({
                "type": "ineq",
                "fun": lambda f, idxs=indices: max_corr - np.sum(np.abs(f[idxs]))
            })

        # Solve QP
        initial_f = np.zeros(n_contracts)
        res = minimize(objective, initial_f, method="SLSQP", bounds=bounds, constraints=constraints)

        results = []
        if res.success:
            # Apply fractional Kelly multiplier (e.g. quarter Kelly)
            fraction = self.config.portfolio.kelly.fraction
            f_opt = res.x * fraction
            
            for idx, f_val in enumerate(f_opt):
                raw_edge = edges[idx] + 0.01 # reconstruct raw edge
                net_edge = edges[idx]
                
                # Sizing status check
                status = forecasts[idx]["status"]
                if status == "READY":
                    if net_edge < self.config.portfolio.kelly.min_edge:
                        status = "RESEARCH-ONLY" # Edge below threshold
                    elif f_val <= 0.0001:
                        status = "RESEARCH-ONLY" # Sized to zero
                
                results.append({
                    "contract_id": forecasts[idx]["contract_id"],
                    "title": forecasts[idx]["title"],
                    "category": forecasts[idx]["category"],
                    "model_prob": forecasts[idx]["model_prob"],
                    "market_implied": forecasts[idx]["market_implied"],
                    "raw_edge": raw_edge,
                    "net_edge": net_edge,
                    "kelly_full": float(res.x[idx]),
                    "kelly_quarter": float(res.x[idx] * 0.25),
                    "recommended_fraction": float(f_val),
                    "recommended_usd": float(f_val * cash_balance),
                    "status": status,
                    "base_rate_reference": forecasts[idx]["base_rate_reference"],
                    "base_rate_prob": forecasts[idx]["base_rate_prob"]
                })
        else:
            logger.error(f"Sizing optimization failed: {res.message}")
            for item in forecasts:
                results.append({
                    **item,
                    "raw_edge": item["model_prob"] - item["market_implied"],
                    "net_edge": item["model_prob"] - item["market_implied"] - 0.01,
                    "kelly_full": 0.0,
                    "kelly_quarter": 0.0,
                    "recommended_fraction": 0.0,
                    "recommended_usd": 0.0,
                    "status": "RESEARCH-ONLY"
                })

        return results
