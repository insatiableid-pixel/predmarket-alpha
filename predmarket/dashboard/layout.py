"""Dash application creation, styling constants, and layout definition."""

from dash import Dash, dcc, html
import dash_bootstrap_components as dbc

from .server import server

# ---------------------------------------------------------------------------
# Premium dark-theme styling
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

app = Dash(
    __name__,
    server=server,
    routes_pathname_prefix="/",
    external_stylesheets=[
        dbc.themes.CYBORG,
        "https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap",
    ],
)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

app.layout = dbc.Container(
    [
        # ---- Header ----
        dbc.Row(
            dbc.Col(
                html.H1(
                    "PREDMARKET-ALPHA | Real-time Forecasting Platform",
                    className="text-center my-4",
                    style={"color": ACCENT_BLUE, "font-family": "Outfit, sans-serif"},
                ),
                width=12,
            )
        ),
        # ---- Alert banner ----
        dbc.Row(dbc.Col(html.Div(id="error-banner"), width=12)),
        # ---- KPI cards ----
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Brier Score", className="text-muted"),
                                html.H2(
                                    id="kpi-brier", style={"color": ACCENT_GREEN}
                                ),
                            ]
                        ),
                        style={"background-color": CARD_BG},
                    ),
                    width=3,
                ),
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Log Loss", className="text-muted"),
                                html.H2(
                                    id="kpi-logloss", style={"color": ACCENT_GREEN}
                                ),
                            ]
                        ),
                        style={"background-color": CARD_BG},
                    ),
                    width=3,
                ),
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("PnL", className="text-muted"),
                                html.H2(
                                    id="kpi-pnl", style={"color": ACCENT_BLUE}
                                ),
                            ]
                        ),
                        style={"background-color": CARD_BG},
                    ),
                    width=3,
                ),
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Max Drawdown", className="text-muted"),
                                html.H2(
                                    id="kpi-drawdown", style={"color": ACCENT_RED}
                                ),
                            ]
                        ),
                        style={"background-color": CARD_BG},
                    ),
                    width=3,
                ),
            ],
            className="mb-4",
        ),
        # ---- Charts ----
        dbc.Row(
            [
                dbc.Col(
                    dcc.Loading(
                        dcc.Graph(id="calibration-curve-plot"), type="border"
                    ),
                    width=6,
                ),
                dbc.Col(
                    dcc.Loading(
                        dcc.Graph(id="equity-history-plot"), type="border"
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
                            style={
                                "background-color": CARD_BG,
                                "color": ACCENT_BLUE,
                                "font-weight": "bold",
                            },
                        ),
                        dbc.CardBody(
                            dcc.Loading(
                                html.Div(id="opportunity-board-table"), type="border"
                            )
                        ),
                    ],
                    style={"background-color": CARD_BG},
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
                            style={
                                "background-color": CARD_BG,
                                "color": ACCENT_ORANGE,
                                "font-weight": "bold",
                            },
                        ),
                        dbc.CardBody(
                            dcc.Loading(
                                html.Div(id="position-sizing-slate"), type="border"
                            )
                        ),
                    ],
                    style={"background-color": CARD_BG},
                ),
                width=12,
            ),
            className="mb-4",
        ),
        # ---- Interval component (drives periodic refresh) ----
        dcc.Interval(id="interval-update", interval=10000, n_intervals=0),
    ],
    fluid=True,
    style={"background-color": DARK_BG, "min-height": "100vh"},
)
