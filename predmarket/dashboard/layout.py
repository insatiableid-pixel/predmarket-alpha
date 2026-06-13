"""Dash application creation, styling constants, and layout definition.

F1 remediation: ARIA labels and roles added for accessibility.
F3 remediation: KPI cards wrapped in dcc.Loading for loading states.
F6 remediation: External Google Fonts replaced with local @font-face.
F8 remediation: Inline styles replaced with CSS classes where possible.
"""

from dash import Dash, dcc, html
import dash_bootstrap_components as dbc

from .server import server

# ---------------------------------------------------------------------------
# Premium dark-theme styling constants (retained for programmatic use in callbacks)
# ---------------------------------------------------------------------------

DARK_BG = "#0B0E14"
CARD_BG = "#161B22"
ACCENT_BLUE = "#58A6FF"
ACCENT_GREEN = "#3FB950"
ACCENT_RED = "#F85149"
ACCENT_ORANGE = "#F0883E"

# ---------------------------------------------------------------------------
# Dash application
# ---------------------------------------------------------------------------

from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
assets_dir = project_root / "assets"

app = Dash(
    __name__,
    server=server,
    routes_pathname_prefix="/",
    assets_folder=str(assets_dir),
    title="Big Two PredMarket Alpha",
    external_stylesheets=[
        dbc.themes.CYBORG,
        # F6: Outfit font is now served locally via assets/custom.css @font-face.
        # If the local font file is missing, the browser falls back to sans-serif.
    ],
)

# ---------------------------------------------------------------------------
# Layout  (F1: accessibility attributes, F3: loading wrappers, F8: CSS classes)
# ---------------------------------------------------------------------------

# --- Skip-nav link for keyboard accessibility ---
skip_nav = html.A(
    "Skip to main content",
    href="#main-content",
    className="skip-nav",
    style={
        "position": "absolute", "top": "-40px", "left": "0",
        "background": ACCENT_BLUE, "color": "#000", "padding": "8px",
        "z-index": "1000", "font-weight": "bold",
    },
)

app.layout = dbc.Container(
    [
        skip_nav,
        # ---- Header ----
        html.Header(
            dbc.Row(
                dbc.Col(
                    html.H1(
                        "BIG TWO PREDMARKET ALPHA | Kalshi + Polymarket",
                        className="text-center my-4",
                        style={"color": ACCENT_BLUE, "font-family": "Outfit, sans-serif"},
                    ),
                    width=12,
                ),
            ),
            role="banner",
        ),
        # ---- Alert banner (live region) ----
        dbc.Row(
            dbc.Col(
                html.Div(id="error-banner", role="alert", **{"aria-live": "polite"}),
                width=12,
            )
        ),
        # ---- KPI cards (F1: aria-label, role=status; F3: dcc.Loading wrappers) ----
        html.Div(
            dbc.Row(
                [
                    dbc.Col(
                        dcc.Loading(
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        html.H5("Brier Score", className="text-muted"),
                                        html.H2(
                                            id="kpi-brier",
                                            style={"color": ACCENT_GREEN},
                                            **{"aria-label": "Brier Score", "role": "status"},
                                        ),
                                    ]
                                ),
                                className="card-bg",
                            ),
                            type="border",
                        ),
                        width=3,
                    ),
                    dbc.Col(
                        dcc.Loading(
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        html.H5("Log Loss", className="text-muted"),
                                        html.H2(
                                            id="kpi-logloss",
                                            style={"color": ACCENT_GREEN},
                                            **{"aria-label": "Log Loss", "role": "status"},
                                        ),
                                    ]
                                ),
                                className="card-bg",
                            ),
                            type="border",
                        ),
                        width=3,
                    ),
                    dbc.Col(
                        dcc.Loading(
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        html.H5("PnL", className="text-muted"),
                                        html.H2(
                                            id="kpi-pnl",
                                            style={"color": ACCENT_BLUE},
                                            **{"aria-label": "Profit and Loss", "role": "status"},
                                        ),
                                    ]
                                ),
                                className="card-bg",
                            ),
                            type="border",
                        ),
                        width=3,
                    ),
                    dbc.Col(
                        dcc.Loading(
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        html.H5("Max Drawdown", className="text-muted"),
                                        html.H2(
                                            id="kpi-drawdown",
                                            style={"color": ACCENT_RED},
                                            **{"aria-label": "Maximum Drawdown", "role": "status"},
                                        ),
                                    ]
                                ),
                                className="card-bg",
                            ),
                            type="border",
                        ),
                        width=3,
                    ),
                ],
                className="mb-4",
            ),
            id="main-content",
            role="main",
            tabIndex=-1,
        ),
        # ---- Charts ----
        dbc.Row(
            [
                dbc.Col(
                    dcc.Loading(
                        dcc.Graph(
                            id="calibration-curve-plot",
                            config={"displayModeBar": True},
                        ),
                        type="border",
                    ),
                    width=6,
                ),
                dbc.Col(
                    dcc.Loading(
                        dcc.Graph(
                            id="equity-history-plot",
                            config={"displayModeBar": True},
                        ),
                        type="border",
                    ),
                    width=6,
                ),
            ],
            className="mb-4",
        ),
        # ---- Opportunity Board ----
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader(
                            "Market Opportunity Board",
                            className="section-header-blue",
                        ),
                        dbc.CardBody(
                            dcc.Loading(
                                html.Div(id="opportunity-board-table", role="region", **{"aria-label": "Market opportunities"}),
                                type="border",
                            )
                        ),
                    ],
                    className="card-bg",
                ),
                width=12,
            ),
            className="mb-4",
        ),
        # ---- Position Sizing Slate ----
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader(
                            "Kelly Position Sizing Slate",
                            className="section-header-orange",
                        ),
                        dbc.CardBody(
                            dcc.Loading(
                                html.Div(id="position-sizing-slate", role="region", **{"aria-label": "Position sizing recommendations"}),
                                type="border",
                            )
                        ),
                    ],
                    className="card-bg",
                ),
                width=12,
            ),
            className="mb-4",
        ),
        # ---- Shared data store for decomposed callbacks (F2) ----
        dcc.Store(id="metrics-store"),
        # ---- Interval component (drives periodic refresh) ----
        dcc.Interval(id="interval-update", interval=10000, n_intervals=0),
    ],
    fluid=True,
    className="dark-bg",
)
