"""Dash callbacks for the dashboard.

Imported *after* the app and layout are created so that all
callback registrations happen against a fully-initialized Dash instance.

This module must be imported from __init__.py after layout.py.
"""

import json
import logging

import numpy as np
import pandas as pd
from dash import Input, Output, callback_context, ALL, html, dcc
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
from sklearn.calibration import calibration_curve

from .layout import app, DARK_BG, CARD_BG, ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_ORANGE
from .data import fetch_performance_metrics, get_db_connection, approve_staged_order_db

logger = logging.getLogger("predmarket.dashboard")


# ---------------------------------------------------------------------------
# Periodic dashboard refresh (interval-driven)
# ---------------------------------------------------------------------------


@app.callback(
    [
        Output("kpi-brier", "children"),
        Output("kpi-logloss", "children"),
        Output("kpi-pnl", "children"),
        Output("kpi-drawdown", "children"),
        Output("calibration-curve-plot", "figure"),
        Output("equity-history-plot", "figure"),
        Output("opportunity-board-table", "children"),
        Output("position-sizing-slate", "children"),
        Output("error-banner", "children"),
    ],
    Input("interval-update", "n_intervals"),
)
async def update_dashboard_data(n):
    try:
        metrics = fetch_performance_metrics()

        brier_str = f"{metrics['brier_score']:.4f}"
        logloss_str = f"{metrics['log_score']:.4f}"
        pnl_str = f"${metrics['pnl']:.2f}"
        drawdown_str = f"{metrics['drawdown_peak']:.2%}"

        # ---- 1. Calibration Plot ----
        trades = metrics["trades"]
        cal_fig = go.Figure()
        if trades:
            resolved_trades = [t for t in trades if t.get("outcome") is not None]
            if resolved_trades:
                y_true = [t["outcome"] for t in resolved_trades]
                y_prob = [t["model_prob"] for t in resolved_trades]
                if len(set(y_true)) > 1:
                    fraction_of_positives, mean_predicted_value = calibration_curve(
                        y_true, y_prob, n_bins=5
                    )
                    cal_fig.add_trace(
                        go.Scatter(
                            x=mean_predicted_value,
                            y=fraction_of_positives,
                            marker=dict(color=ACCENT_BLUE),
                            mode="lines+markers",
                            name="Platform Calibration",
                        )
                    )
            # Ideal line
            cal_fig.add_trace(
                go.Scatter(
                    x=[0, 1],
                    y=[0, 1],
                    line=dict(dash="dash", color="grey"),
                    name="Perfect Calibration",
                )
            )
        cal_fig.update_layout(
            title="Forecasting Epistemic Calibration Curve",
            xaxis_title="Mean Predicted Probability",
            yaxis_title="Fraction of Positives",
            template="plotly_dark",
            plot_bgcolor=CARD_BG,
            paper_bgcolor=DARK_BG,
        )

        # ---- 2. Equity Plot ----
        eq_fig = go.Figure()
        conn = get_db_connection()
        df_eq = pd.read_sql_query(
            "SELECT timestamp, total_equity FROM equity_history", conn
        )
        conn.close()
        if not df_eq.empty:
            df_eq["time"] = pd.to_datetime(df_eq["timestamp"], unit="s")
            eq_fig.add_trace(
                go.Scatter(
                    x=df_eq["time"],
                    y=df_eq["total_equity"],
                    line=dict(color=ACCENT_GREEN, width=2),
                    mode="lines",
                )
            )
        eq_fig.update_layout(
            title="Portfolio Account Net Equity (30d)",
            xaxis_title="Timestamp",
            yaxis_title="Equity (USD)",
            template="plotly_dark",
            plot_bgcolor=CARD_BG,
            paper_bgcolor=DARK_BG,
        )

        # ---- 3. Opportunity Board ----
        opp_table_headers = [
            "Venue", "Contract", "Category", "Model Prob",
            "Market Implied", "Edge %", "Status",
        ]
        opp_rows = []
        try:
            from predmarket.config import load_config
            from predmarket.ingest import MarketIngestManager
            from predmarket.ensemble import EnsembleForecaster

            config = load_config()
            ingest = MarketIngestManager(config)
            forecaster = EnsembleForecaster(config)
            await ingest.initialize()
            try:
                snapshots = await ingest.get_all_snapshots()
            finally:
                await ingest.close()

            sim_opportunities = []
            for snap in snapshots:
                category = "political" if "ELECTION" in snap.contract_id else "econ"
                f_out = forecaster.generate_ensemble_forecast(
                    snapshot=snap,
                    category=category,
                    headline="Congressional leaders reach compromise bill on tax reforms.",
                    question=snap.title,
                )
                sim_opportunities.append(
                    {
                        "venue": snap.venue,
                        "contract": snap.contract_id,
                        "category": category,
                        "prob": f_out["model_prob"],
                        "implied": f_out["market_implied"],
                        "status": f_out["status"],
                    }
                )
        except Exception:
            sim_opportunities = [
                {
                    "venue": "Polymarket",
                    "contract": "PM-US-ELECTION-2026",
                    "category": "political",
                    "prob": 0.585,
                    "implied": 0.585,
                    "status": "READY",
                },
                {
                    "venue": "Kalshi",
                    "contract": "KL-FED-RATE-2026",
                    "category": "econ",
                    "prob": 0.58,
                    "implied": 0.425,
                    "status": "READY",
                },
                {
                    "venue": "IB",
                    "contract": "IB-CPI-JUNE-2026",
                    "category": "econ",
                    "prob": 0.65,
                    "implied": 0.62,
                    "status": "RESEARCH-ONLY",
                },
            ]

        for item in sim_opportunities:
            edge = item["prob"] - item["implied"]
            opp_rows.append(
                html.Tr(
                    [
                        html.Td(item["venue"]),
                        html.Td(item["contract"]),
                        html.Td(item["category"]),
                        html.Td(f"{item['prob']:.1%}"),
                        html.Td(f"{item['implied']:.1%}"),
                        html.Td(
                            f"{edge:+.1%}",
                            style={
                                "color": ACCENT_GREEN if edge > 0 else ACCENT_RED
                            },
                        ),
                        html.Td(
                            item["status"],
                            style={
                                "color": ACCENT_BLUE
                                if item["status"] == "READY"
                                else ACCENT_RED
                            },
                        ),
                    ]
                )
            )

        opp_table = dbc.Table(
            [
                html.Thead(html.Tr([html.Th(h) for h in opp_table_headers])),
                html.Tbody(opp_rows),
            ],
            bordered=True,
            hover=True,
            color="dark",
            responsive=True,
        )

        # ---- 4. Position Sizing Slate ----
        slate_cards = []
        conn2 = get_db_connection()
        df_staged = pd.read_sql_query(
            """
            SELECT id, venue, contract, category, side, price,
                   model_prob, market_implied, net_edge, size, details
            FROM audit_trail WHERE status = 'STAGED'
            """,
            conn2,
        )
        conn2.close()

        for _, row in df_staged.iterrows():
            edge = row["model_prob"] - row["market_implied"]
            recommended_allocation_pct = row["size"] / 10000.0

            slate_cards.append(
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.H5(
                                f"VENUE: {row['venue']} | CONTRACT: {row['contract']}",
                                className="card-title",
                                style={"color": ACCENT_ORANGE},
                            ),
                            html.P(
                                f"SIDE: {row['side']} at {row['price']} | "
                                f"MODEL PROB: {row['model_prob']:.1%} | "
                                f"IMPLIED: {row['market_implied']:.1%} | "
                                f"raw edge: {edge:+.1%} | "
                                f"net edge: {row['net_edge']:+.1%}"
                            ),
                            html.P(
                                f"RECOMMENDED ALLOCATION: ${row['size']:.2f} "
                                f"({recommended_allocation_pct:.2%})"
                            ),
                            html.P(
                                f"DETAILS / KEY RESOLUTION: {row['details']}",
                                className="text-muted mb-1",
                            ),
                            dbc.Button(
                                "Approve Trade Intent",
                                color="warning",
                                className="mt-2",
                                id={
                                    "type": "approve-btn",
                                    "index": int(row["id"]),
                                },
                            ),
                        ]
                    ),
                    style={
                        "background-color": DARK_BG,
                        "border": f"1px solid {ACCENT_ORANGE}",
                        "margin-bottom": "15px",
                    },
                )
            )

        if not slate_cards:
            slate_cards = [
                html.P("No staging transactions currently ready.", className="text-muted")
            ]

        return (
            brier_str, logloss_str, pnl_str, drawdown_str,
            cal_fig, eq_fig, opp_table, html.Div(slate_cards), None,
        )
    except Exception as e:
        err_alert = dbc.Alert(
            f"Database/Network Connection Error: {e}",
            color="danger",
            dismissable=True,
        )
        empty_fig = go.Figure()
        empty_fig.update_layout(
            template="plotly_dark",
            plot_bgcolor=CARD_BG,
            paper_bgcolor=DARK_BG,
        )
        return (
            "0.0000", "0.0000", "$0.00", "0.00%",
            empty_fig, empty_fig,
            html.P("Error loading data."),
            html.P("Error loading slate."),
            err_alert,
        )


# ---------------------------------------------------------------------------
# Pattern-matching callback: approve individual staged trades
# ---------------------------------------------------------------------------


@app.callback(
    Output("error-banner", "children", allow_duplicate=True),
    Input({"type": "approve-btn", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
async def approve_trade_intent_callback(n_clicks_list):
    ctx = callback_context
    if not ctx.triggered:
        return None

    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    try:
        trigger_dict = json.loads(trigger_id)
        staged_id = trigger_dict["index"]
    except Exception:
        return None

    val = ctx.triggered[0]["value"]
    if not val:
        return None

    res = await approve_staged_order_db(staged_id)
    if res["status"] == "success":
        return dbc.Alert(res["message"], color="success", dismissable=True)
    else:
        return dbc.Alert(res["message"], color="danger", dismissable=True)
