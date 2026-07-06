"""Prometheus metric definitions for the dashboard.

Isolated in its own module to avoid circular imports between
server (REST endpoints) and data (order-approval logic).
"""

from prometheus_client import Counter

METRIC_TRADES_STAGED = Counter("predmarket_trades_staged_total", "Total trades staged for review")

METRIC_TRADES_EXECUTED = Counter(
    "predmarket_trades_executed_total", "Total trades successfully executed"
)

METRIC_TRADES_FAILED = Counter(
    "predmarket_trades_failed_total", "Total trades that failed execution"
)
