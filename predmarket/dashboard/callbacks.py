"""Dash callbacks for the dashboard.

Imported *after* the app and layout are created so that all
callback registrations happen against a fully-initialized Dash instance.

This module must be imported from __init__.py after layout.py.

Remediation notes:
  B8 — Adaptive calibration binning (n_bins scales with trade count).
  F2 — Monolithic callback decomposed into data-fetch + render callbacks via dcc.Store.
  F4 — Per-component error states on KPI cards.
  F5 — Removed hardcoded fallback opportunities; shows "no data" message.
"""

import json
import logging

import numpy as np
import pandas as pd
from dash import Input, Output, State, callback_context, ALL, html, dcc
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
from sklearn.calibration import calibration_curve

from .layout import app, DARK_BG, CARD_BG, ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_ORANGE
from .data import fetch_performance_metrics, get_db_connection, approve_staged_order_db, fetch_opportunities

logger = logging.getLogger("predmarket.dashboard")


def _empty_fig() -> go.Figure:
    """Return a dark-themed empty figure."""
    fig = go.Figure()
    fig.update_layout(template="plotly_dark", plot_bgcolor=CARD_BG, paper_bgcolor=DARK_BG)
    return fig


# ===========================================================================
# F2: Decomposed callback architecture
#
# The interval tick triggers a data fetch → dcc.Store. Child callbacks
# read from the store and render their own sections. This replaces the
# original single 180-line monolithic callback.
# ===========================================================================


@app.callback(
    Output("metrics-store", "data"),
    Output("error-banner", "children"),
    Input("interval-update", "n_intervals"),
)
async def fetch_metrics_callback(n):
    """Fetch performance metrics from the database and store as JSON."""
    try:
        metrics = fetch_performance_metrics()
        return metrics, None
    except Exception as e:
        return {}, dbc.Alert(
            f"Data refresh error: {e}", color="danger", dismissable=True
        )


@app.callback(
    [
        Output("kpi-brier", "children"),
        Output("kpi-logloss", "children"),
        Output("kpi-pnl", "children"),
        Output("kpi-drawdown", "children"),
    ],
    Input("metrics-store", "data"),
)
def render_kpi_cards(metrics):
    """Render KPI card values from stored metrics. (F4: per-component errors)"""
    if not metrics:
        err = html.Span("— Error —", className="kpi-error")
        return err, err, err, err

    brier_str = f"{metrics['brier_score']:.4f}"
    logloss_str = f"{metrics['log_score']:.4f}"
    pnl_str = f"${metrics['pnl']:.2f}"
    drawdown_str = f"{metrics['drawdown_peak']:.2%}"
    return brier_str, logloss_str, pnl_str, drawdown_str


@app.callback(
    Output("calibration-curve-plot", "figure"),
    Input("metrics-store", "data"),
)
def render_calibration_plot(metrics):
    """Render the calibration curve. (B8: adaptive binning)"""
    cal_fig = go.Figure()
    if not metrics:
        return cal_fig

    trades = metrics.get("trades", [])
    if trades:
        resolved_trades = [t for t in trades if t.get("outcome") is not None]
        if resolved_trades:
            n_resolved = len(resolved_trades)
            if n_resolved < 10:
                cal_fig.add_annotation(
                    text=f"Insufficient data for calibration ({n_resolved} trades, need ≥10)",
                    xref="paper", yref="paper", x=0.5, y=0.5,
                    showarrow=False, font=dict(size=14, color="#8B949E"),
                )
            else:
                y_true = [t["outcome"] for t in resolved_trades]
                y_prob = [t["model_prob"] for t in resolved_trades]
                n_bins = max(2, min(10, n_resolved // 5))
                if len(set(y_true)) > 1:
                    fraction_of_positives, mean_predicted_value = calibration_curve(
                        y_true, y_prob, n_bins=n_bins
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
        cal_fig.add_trace(
            go.Scatter(
                x=[0, 1], y=[0, 1],
                line=dict(dash="dash", color="grey"),
                name="Perfect Calibration",
            )
        )
    cal_fig.update_layout(
        title="Forecasting Epistemic Calibration Curve",
        xaxis_title="Mean Predicted Probability",
        yaxis_title="Fraction of Positives",
        template="plotly_dark", plot_bgcolor=CARD_BG, paper_bgcolor=DARK_BG,
    )
    return cal_fig


@app.callback(
    Output("equity-history-plot", "figure"),
    Input("metrics-store", "data"),
)
def render_equity_plot(metrics):
    """Render the equity history chart."""
    eq_fig = go.Figure()
    try:
        conn = get_db_connection()
        df_eq = pd.read_sql_query(
            "SELECT timestamp, total_equity FROM equity_history", conn
        )
        conn.close()
        if not df_eq.empty:
            df_eq["time"] = pd.to_datetime(df_eq["timestamp"], unit="s")
            eq_fig.add_trace(
                go.Scatter(
                    x=df_eq["time"], y=df_eq["total_equity"],
                    line=dict(color=ACCENT_GREEN, width=2), mode="lines",
                )
            )
    except Exception:
        pass
    eq_fig.update_layout(
        title="Portfolio Account Net Equity (30d)",
        xaxis_title="Timestamp", yaxis_title="Equity (USD)",
        template="plotly_dark", plot_bgcolor=CARD_BG, paper_bgcolor=DARK_BG,
    )
    return eq_fig


@app.callback(
    Output("opportunity-board-table", "children"),
    Input("metrics-store", "data"),
)
def render_opportunity_board(metrics):
    """Render the opportunity board table. (F5: no hardcoded fallback)"""
    sim_opportunities = fetch_opportunities()

    if not sim_opportunities:
        return html.P(
            "No live opportunities detected. Awaiting market data.",
            className="text-muted",
        )

    opp_table_headers = [
        "Venue", "Contract", "Category", "Model Prob",
        "Market Implied", "Edge %", "Status",
    ]
    opp_rows = []
    for item in sim_opportunities:
        edge = item["prob"] - item["implied"]
        opp_rows.append(
            html.Tr([
                html.Td(item["venue"]),
                html.Td(item["contract"]),
                html.Td(item["category"]),
                html.Td(f"{item['prob']:.1%}"),
                html.Td(f"{item['implied']:.1%}"),
                html.Td(
                    f"{edge:+.1%}",
                    style={"color": ACCENT_GREEN if edge > 0 else ACCENT_RED},
                ),
                html.Td(
                    item["status"],
                    style={"color": ACCENT_BLUE if item["status"] == "READY" else ACCENT_RED},
                ),
            ])
        )
    return dbc.Table(
        [html.Thead(html.Tr([html.Th(h) for h in opp_table_headers])), html.Tbody(opp_rows)],
        bordered=True, hover=True, color="dark", responsive=True,
    )


@app.callback(
    Output("position-sizing-slate", "children"),
    Input("metrics-store", "data"),
)
def render_position_sizing_slate(metrics):
    """Render the Kelly position sizing approval cards."""
    slate_cards = []
    try:
        conn = get_db_connection()
        df_staged = pd.read_sql_query(
            """
            SELECT id, venue, contract, category, side, price,
                   model_prob, market_implied, net_edge, size, details
            FROM audit_trail WHERE status = 'STAGED'
            """,
            conn,
        )
        conn.close()

        for _, row in df_staged.iterrows():
            edge = row["model_prob"] - row["market_implied"]
            recommended_allocation_pct = row["size"] / 10000.0
            slate_cards.append(
                dbc.Card(
                    dbc.CardBody([
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
                            id={"type": "approve-btn", "index": int(row["id"])},
                            title=f"Approve trade {row['contract']} on {row['venue']}",
                        ),
                    ]),
                    className="approval-card",
                )
            )
    except Exception:
        pass

    if not slate_cards:
        slate_cards = [html.P("No staging transactions currently ready.", className="text-muted")]

    return html.Div(slate_cards)


# ---------------------------------------------------------------------------
# Backward-compatible wrapper for tests that import update_dashboard_data
# ---------------------------------------------------------------------------


async def update_dashboard_data(n):
    """Backward-compatible wrapper used by tests.

    The F2 decomposition split this into fetch_metrics_callback + render callbacks,
    but this function is preserved for test compatibility. It replicates the
    original single-callback behavior.
    """
    try:
        metrics = fetch_performance_metrics()

        brier_str = f"{metrics['brier_score']:.4f}"
        logloss_str = f"{metrics['log_score']:.4f}"
        pnl_str = f"${metrics['pnl']:.2f}"
        drawdown_str = f"{metrics['drawdown_peak']:.2%}"

        cal_fig = render_calibration_plot(metrics)
        eq_fig = render_equity_plot(metrics)
        opp_table = render_opportunity_board(metrics)
        slate = render_position_sizing_slate(metrics)

        return (
            brier_str, logloss_str, pnl_str, drawdown_str,
            cal_fig, eq_fig, opp_table, slate, None,
        )
    except Exception as e:
        err_alert = dbc.Alert(
            f"Data refresh error: {e}",
            color="danger",
            dismissable=True,
        )
        kpi_err = html.Span("— Error —", className="kpi-error")
        return (
            kpi_err, kpi_err, kpi_err, kpi_err,
            _empty_fig(), _empty_fig(),
            html.P("Error loading opportunities.", className="text-danger"),
            html.P("Error loading slate.", className="text-danger"),
            err_alert,
        )


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
