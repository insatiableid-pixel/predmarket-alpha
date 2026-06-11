"""Database helpers, performance metrics, and staged-order approval logic."""

import sqlite3
import logging
from typing import Dict, Any
from pathlib import Path

import numpy as np
import pandas as pd

from .metrics import METRIC_TRADES_STAGED, METRIC_TRADES_EXECUTED, METRIC_TRADES_FAILED

logger = logging.getLogger("predmarket.dashboard")


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------


def get_db_connection() -> sqlite3.Connection:
    try:
        from predmarket.config import load_config

        config = load_config()
        db_path = config.global_cfg.data_dir / "database.sqlite"
    except Exception:
        db_path = Path(__file__).resolve().parents[1] / "data" / "database.sqlite"
    return sqlite3.connect(str(db_path))


# ---------------------------------------------------------------------------
# Performance metrics
# ---------------------------------------------------------------------------


def fetch_performance_metrics() -> Dict[str, Any]:
    conn = get_db_connection()
    df_trades = pd.read_sql_query(
        """
        SELECT timestamp, venue, contract, category, side, size, price,
               model_prob, market_implied, net_edge, status, details, outcome
        FROM audit_trail
        WHERE event_type = 'TRADE_INTENT'
        """,
        conn,
    )
    df_equity = pd.read_sql_query(
        "SELECT timestamp, total_equity FROM equity_history", conn
    )
    conn.close()

    if df_trades.empty:
        return {
            "brier_score": 0.0,
            "log_score": 0.0,
            "pnl": 0.0,
            "positions_count": 0,
            "win_rate": 0.0,
            "drawdown_peak": 0.0,
            "trades": [],
        }

    # Resolved trades: those with known binary outcomes
    df_resolved = df_trades[
        df_trades["outcome"].notna() & df_trades["outcome"].isin([0, 1])
    ]

    # Brier Score = 1/N * sum((f_i - o_i)^2)
    brier = (
        float(np.mean((df_resolved["model_prob"] - df_resolved["outcome"]) ** 2))
        if not df_resolved.empty
        else 0.0
    )

    # Log Score = -1/N * sum(o_i * log(f_i) + (1-o_i)*log(1-f_i))
    if not df_resolved.empty:
        eps = 1e-15
        f = np.clip(df_resolved["model_prob"].values, eps, 1 - eps)
        o = df_resolved["outcome"].values
        log_score = float(-np.mean(o * np.log(f) + (1.0 - o) * np.log(1.0 - f)))
    else:
        log_score = 0.0

    # PnL and win rate
    pnl = 0.0
    wins = 0
    for _, row in df_trades.iterrows():
        outcome_val = row.get("outcome")
        if outcome_val is None:
            continue
        contract_won = (
            outcome_val == 1 and str(row["side"]).upper() == "YES"
        ) or (outcome_val == 0 and str(row["side"]).upper() == "NO")
        if contract_won:
            wins += 1
            pnl += row["size"] * (1.0 / max(row["price"], 0.01) - 1.0)
        else:
            pnl -= row["size"]

    win_rate = wins / len(df_trades) if len(df_trades) > 0 else 0.0

    # Peak drawdown from equity history
    drawdown_peak = 0.0
    if not df_equity.empty:
        eq_vals = df_equity["total_equity"].values
        hwm = eq_vals[0]
        for v in eq_vals:
            if v > hwm:
                hwm = v
            dd = (hwm - v) / hwm if hwm > 0 else 0.0
            if dd > drawdown_peak:
                drawdown_peak = dd

    return {
        "brier_score": brier,
        "log_score": log_score,
        "pnl": pnl,
        "positions_count": len(df_trades),
        "win_rate": win_rate,
        "drawdown_peak": drawdown_peak,
        "trades": df_trades.to_dict("records"),
    }


# ---------------------------------------------------------------------------
# Staged-order approval
# ---------------------------------------------------------------------------


async def approve_staged_order_db(staged_id: int) -> dict:
    logger.info(f"Approving staged order {staged_id}")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT venue, contract, category, side, size, price, model_prob, market_implied
        FROM audit_trail WHERE id = ?
        """,
        (staged_id,),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        logger.warning(f"Staged order {staged_id} not found in database")
        return {"status": "error", "message": f"Staged order {staged_id} not found."}

    venue, contract, category, side, size, price, model_prob, market_implied = row
    logger.info(f"Found staged order: {venue} | {contract} | {side}")

    cursor.execute(
        "UPDATE audit_trail SET status = 'EXECUTING' WHERE id = ?", (staged_id,)
    )
    conn.commit()
    conn.close()
    logger.info(f"Updated staged order {staged_id} status to EXECUTING")

    try:
        from predmarket.config import load_config
        from predmarket.audit import AuditLogger
        from predmarket.execution import ExecutionManager

        config = load_config()
        audit_logger = AuditLogger(data_dir=str(config.global_cfg.data_dir))
        execution = ExecutionManager(config, audit_logger)

        quantity = size / price if price > 0 else 0
        logger.info(
            f"Routing order execution: venue={venue}, contract={contract}, "
            f"quantity={quantity}"
        )
        res = await execution.execute_order(
            venue=venue,
            contract=contract,
            category=category,
            side=side,
            quantity=quantity,
            price=price,
            model_prob=model_prob,
            market_implied=market_implied,
        )
        logger.info(
            f"Order execution result: {res.get('status')} "
            f"(order_id={res.get('order_id', 'N/A')})"
        )

        if res.get("status") == "FILLED":
            METRIC_TRADES_EXECUTED.inc()
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE audit_trail SET status = 'FILLED', details = ? WHERE id = ?",
                (f"Filled: {res.get('order_id')}", staged_id),
            )
            conn.commit()
            conn.close()
            return {
                "status": "success",
                "message": f"Successfully executed order {res.get('order_id')} on {venue}.",
            }
        else:
            METRIC_TRADES_FAILED.inc()
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE audit_trail SET status = 'FAILED' WHERE id = ?", (staged_id,)
            )
            conn.commit()
            conn.close()
            return {"status": "error", "message": f"Execution failed on {venue}."}
    except Exception as e:
        METRIC_TRADES_FAILED.inc()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE audit_trail SET status = 'FAILED', details = ? WHERE id = ?",
            (str(e), staged_id),
        )
        conn.commit()
        conn.close()
        return {"status": "error", "message": f"Execution error: {e}"}
