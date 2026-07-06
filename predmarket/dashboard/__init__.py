"""
Dashboard package for the Kalshi Action Alpha platform.

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
# Callbacks – must be imported last so the app object exists
from . import (
    callbacks,  # noqa: F401  (side-effect: registers Dash callbacks)
    metrics,  # noqa: F401  (side-effect: registers Prometheus counters)
)

# Re-export callback functions that tests import directly
from .callbacks import update_dashboard_data  # noqa: F401

# Data layer
from .data import (  # noqa: F401
    approve_staged_order_db,
    fetch_opportunities,
    fetch_performance_metrics,
    get_db_connection,
)

# Layout layer (creates the Dash app bound to the FastAPI server)
from .layout import app  # noqa: F401

# Server layer
from .server import (  # noqa: F401
    ApprovalRequest,
    approve_order_endpoint,
    get_staged_orders,
    server,
)
