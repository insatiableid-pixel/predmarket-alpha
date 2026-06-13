"""
Dashboard package for the PredMarket-Alpha platform.

Modules
-------
metrics   – Prometheus counter definitions (standalone, no internal deps)
server    – FastAPI application, auth, REST endpoints, /metrics
data      – Database helpers, performance metrics, staged-order approval
layout    – Dash application, styling constants, HTML layout
callbacks – Dash callbacks (registered on the app from layout)

Import order is deliberate:
  1. metrics  (no deps)
  2. server   (depends on data at runtime via lazy imports)
  3. data     (depends on metrics)
  4. layout   (depends on server for the underlying Flask/FastAPI app)
  5. callbacks (depends on layout + data, must import last so the Dash
     app is fully initialized before callbacks try to register)
"""

# Standalone – no internal dependencies
from . import metrics  # noqa: F401  (side-effect: registers Prometheus counters)

# Server layer
from .server import (  # noqa: F401
    server,
    get_staged_orders,
    approve_order_endpoint,
    ApprovalRequest,
)

# Data layer
from .data import (  # noqa: F401
    get_db_connection,
    fetch_performance_metrics,
    approve_staged_order_db,
    fetch_opportunities,
)

# Layout layer (creates the Dash app bound to the FastAPI server)
from .layout import app  # noqa: F401

# Callbacks – must be imported last so the app object exists
from . import callbacks  # noqa: F401  (side-effect: registers Dash callbacks)

# Re-export callback functions that tests import directly
from .callbacks import update_dashboard_data  # noqa: F401
