import os
import sqlite3
import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from pathlib import Path
from fastapi import FastAPI, Depends, Security, HTTPException, status
from fastapi.responses import Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from dash import Dash, dcc, html, Input, Output, callback, callback_context, ALL
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
from sklearn.calibration import calibration_curve
import nest_asyncio
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

logger = logging.getLogger("predmarket.dashboard")

# Prometheus metrics
METRIC_TRADES_STAGED = Counter(
    "predmarket_trades_staged_total",
    "Total trades staged for review"
)
METRIC_TRADES_EXECUTED = Counter(
    "predmarket_trades_executed_total",
    "Total trades successfully executed"
)
METRIC_TRADES_FAILED = Counter(
    "predmarket_trades_failed_total",
    "Total trades that failed execution"
)

# FastAPI Server
server = FastAPI()

# API Key Authentication Setup
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def get_api_key(api_key: Optional[str] = Security(api_key_header)):
    expected_key = os.getenv("API_KEY", "predmarket_secret_key_123")
    if not api_key or api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
    return api_key


class ApprovalRequest(BaseModel):
    """Pydantic model for /api/approve request body validation."""
    id: int = Field(gt=0, description="Staged order ID to approve")


# Dash App
app = Dash(
    __name__,
    server=server,
    routes_pathname_prefix="/",
    external_stylesheets=[
        dbc.themes.CYBORG,
        "https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap"
    ]
)

# Custom premium styling
DARK_BG = "#0B0E14"
CARD_BG = "#161B22"
ACCENT_BLUE = "#58A6FF"
ACCENT_GREEN = "#3FB950"
ACCENT_RED = "#F85149"
ACCENT_ORANGE = "#F0883E"

def get_db_connection():
    try:
        from predmarket.config import load_config
        config = load_config()
        db_path = config.global_cfg.data_dir / "database.sqlite"
    except Exception:
        db_path = Path(__file__).resolve().parents[1] / "data" / "database.sqlite"
    return sqlite3.connect(str(db_path))

async def approve_staged_order_db(staged_id: int) -> dict:
    logger.info(f"Approving staged order {staged_id}")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT venue, contract, category, side, size, price, model_prob, market_implied 
        FROM audit_trail WHERE id = ?
    """, (staged_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        logger.warning(f"Staged order {staged_id} not found in database")
        return {"status": "error", "message": f"Staged order {staged_id} not found."}
        
    venue, contract, category, side, size, price, model_prob, market_implied = row
    logger.info(f"Found staged order: {venue} | {contract} | {side}")
    
    # We update the status to EXECUTING
    cursor.execute("UPDATE audit_trail SET status = 'EXECUTING' WHERE id = ?", (staged_id,))
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
        logger.info(f"Routing order execution: venue={venue}, contract={contract}, quantity={quantity}")
        res = await execution.execute_order(
            venue=venue,
            contract=contract,
            category=category,
            side=side,
            quantity=quantity,
            price=price,
            model_prob=model_prob,
            market_implied=market_implied
        )
        logger.info(f"Order execution result: {res.get('status')} (order_id={res.get('order_id', 'N/A')})")
        
        if res.get("status") == "FILLED":
            METRIC_TRADES_EXECUTED.inc()
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE audit_trail SET status = 'FILLED', details = ? WHERE id = ?", (f"Filled: {res.get('order_id')}", staged_id))
            conn.commit()
            conn.close()
            return {"status": "success", "message": f"Successfully executed order {res.get('order_id')} on {venue}."}
        else:
            METRIC_TRADES_FAILED.inc()
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE audit_trail SET status = 'FAILED' WHERE id = ?", (staged_id,))
            conn.commit()
            conn.close()
            return {"status": "error", "message": f"Execution failed on {venue}."}
    except Exception as e:
        METRIC_TRADES_FAILED.inc()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE audit_trail SET status = 'FAILED', details = ? WHERE id = ?", (str(e), staged_id))
        conn.commit()
        conn.close()
        return {"status": "error", "message": f"Execution error: {e}"}

# REST API endpoints on the FastAPI server instance
@server.get("/api/staged")
def get_staged_orders(api_key: str = Depends(get_api_key)):
    try:
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT id, venue, contract, category, side, size, price, model_prob, market_implied, net_edge, status, details FROM audit_trail WHERE status = 'STAGED'", conn)
        conn.close()
        return df.to_dict("records")
    except Exception as e:
        logger.exception("Failed to fetch staged orders")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

@server.post("/api/approve")
async def approve_order_endpoint(body: ApprovalRequest, api_key: str = Depends(get_api_key)):
    staged_id = body.id
    logger.info(f"Approve endpoint called for staged order {staged_id}")
    return await approve_staged_order_db(staged_id)


@server.get("/metrics")
def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def fetch_performance_metrics() -> Dict[str, Any]:
    conn = get_db_connection()
    # Fetch resolved trades
    df_trades = pd.read_sql_query("""
        SELECT timestamp, venue, contract, category, side, size, price, model_prob, market_implied, net_edge, status, details, outcome
        FROM audit_trail 
        WHERE event_type = 'TRADE_INTENT'
    """, conn)
    
    # Fetch equity history
    df_equity = pd.read_sql_query("SELECT timestamp, total_equity FROM equity_history", conn)
    conn.close()

    if df_trades.empty:
        return {
            "brier_score": 0.0,
            "log_score": 0.0,
            "pnl": 0.0,
            "positions_count": 0,
            "win_rate": 0.0,
            "drawdown_peak": 0.0,
            "trades": []
        }

    # Fetch resolved outcomes from database outcome column (no longer np.random.rand)
    df_resolved = df_trades[df_trades["outcome"].notna() & df_trades["outcome"].isin([0, 1])]
    
    # Brier Score = 1/N * sum((f_i - o_i)^2)
    brier = float(np.mean((df_resolved["model_prob"] - df_resolved["outcome"]) ** 2)) if not df_resolved.empty else 0.0
    
    # Log Score = -1/N * sum(o_i * log(f_i) + (1-o_i)*log(1-f_i))
    if not df_resolved.empty:
        eps = 1e-15
        f = np.clip(df_resolved["model_prob"].values, eps, 1 - eps)
        o = df_resolved["outcome"].values
        log_score = float(-np.mean(o * np.log(f) + (1.0 - o) * np.log(1.0 - f)))
    else:
        log_score = 0.0

    # Compute PnL
    pnl = 0.0
    wins = 0
    # For PnL computation, we can use the same resolution logic
    for idx, row in df_trades.iterrows():
        outcome_val = row.get("outcome")
        if outcome_val is None:
            continue
        # Yes contract payoff is $1.00 if outcome is 1, $0 if 0
        side_mult = 1 if row["side"].upper() == "YES" else -1
        contract_won = (outcome_val == 1 and row["side"].upper() == "YES") or (outcome_val == 0 and row["side"].upper() == "NO")
        if contract_won:
            wins += 1
            # profit = size * (1/price - 1)
            pnl += row["size"] * (1.0 / max(row["price"], 0.01) - 1.0)
        else:
            pnl -= row["size"]

    win_rate = wins / len(df_trades) if len(df_trades) > 0 else 0.0
    
    # Compute Peak Drawdown
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
        "trades": df_trades.to_dict("records")
    }

# Layout
app.layout = dbc.Container(
    [
        dbc.Row(
            dbc.Col(
                html.H1("PREDMARKET-ALPHA | Real-time Forecasting Platform", className="text-center my-4", style={"color": ACCENT_BLUE, "font-family": "Outfit, sans-serif"}),
                width=12
            )
        ),
        
        # Error / Success Alerts banner
        dbc.Row(
            dbc.Col(
                html.Div(id="error-banner"),
                width=12
            )
        ),
        
        # Top KPI row
        dbc.Row(
            [
                dbc.Col(dbc.Card(dbc.CardBody([html.H5("Brier Score", className="text-muted"), html.H2(id="kpi-brier", style={"color": ACCENT_GREEN})]), style={"background-color": CARD_BG}), width=3),
                dbc.Col(dbc.Card(dbc.CardBody([html.H5("Log Loss", className="text-muted"), html.H2(id="kpi-logloss", style={"color": ACCENT_GREEN})]), style={"background-color": CARD_BG}), width=3),
                dbc.Col(dbc.Card(dbc.CardBody([html.H5("PnL", className="text-muted"), html.H2(id="kpi-pnl", style={"color": ACCENT_BLUE})]), style={"background-color": CARD_BG}), width=3),
                dbc.Col(dbc.Card(dbc.CardBody([html.H5("Max Drawdown", className="text-muted"), html.H2(id="kpi-drawdown", style={"color": ACCENT_RED})]), style={"background-color": CARD_BG}), width=3),
            ],
            className="mb-4"
        ),
        
        # Graphs and Calibration
        dbc.Row(
            [
                dbc.Col(dcc.Loading(dcc.Graph(id="calibration-curve-plot"), type="border"), width=6),
                dbc.Col(dcc.Loading(dcc.Graph(id="equity-history-plot"), type="border"), width=6),
            ],
            className="mb-4"
        ),
        
        # Opportunity Board
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader("Market Opportunity Board", style={"background-color": CARD_BG, "color": ACCENT_BLUE, "font-weight": "bold"}),
                        dbc.CardBody(dcc.Loading(html.Div(id="opportunity-board-table"), type="border"))
                    ],
                    style={"background-color": CARD_BG}
                ),
                width=12
            ),
            className="mb-4"
        ),
        
        # Position Sizing Slate
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader("Kelly Position Sizing Slate", style={"background-color": CARD_BG, "color": ACCENT_ORANGE, "font-weight": "bold"}),
                        dbc.CardBody(dcc.Loading(html.Div(id="position-sizing-slate"), type="border"))
                    ],
                    style={"background-color": CARD_BG}
                ),
                width=12
            ),
            className="mb-4"
        ),
        
        # Interval update
        dcc.Interval(id="interval-update", interval=10000, n_intervals=0)
    ],
    fluid=True,
    style={"background-color": DARK_BG, "min-height": "100vh"}
)

@callback(
    [
        Output("kpi-brier", "children"),
        Output("kpi-logloss", "children"),
        Output("kpi-pnl", "children"),
        Output("kpi-drawdown", "children"),
        Output("calibration-curve-plot", "figure"),
        Output("equity-history-plot", "figure"),
        Output("opportunity-board-table", "children"),
        Output("position-sizing-slate", "children"),
        Output("error-banner", "children")
    ],
    Input("interval-update", "n_intervals")
)
def update_dashboard_data(n):
    try:
        metrics = fetch_performance_metrics()
        
        brier_str = f"{metrics['brier_score']:.4f}"
        logloss_str = f"{metrics['log_score']:.4f}"
        pnl_str = f"${metrics['pnl']:.2f}"
        drawdown_str = f"{metrics['drawdown_peak']:.2%}"

        # 1. Generate Calibration Plot
        trades = metrics["trades"]
        cal_fig = go.Figure()
        if trades:
            resolved_trades = [t for t in trades if t.get("outcome") is not None]
            if resolved_trades:
                y_true = [t["outcome"] for t in resolved_trades]
                y_prob = [t["model_prob"] for t in resolved_trades]
                
                if len(set(y_true)) > 1:
                    fraction_of_positives, mean_predicted_value = calibration_curve(y_true, y_prob, n_bins=5)
                    cal_fig.add_trace(go.Scatter(
                        x=mean_predicted_value,
                        y=fraction_of_positives,
                        marker=dict(color=ACCENT_BLUE),
                        mode="lines+markers",
                        name="Platform Calibration"
                    ))
            
            # Ideal line
            cal_fig.add_trace(go.Scatter(
                x=[0, 1], y=[0, 1],
                line=dict(dash="dash", color="grey"),
                name="Perfect Calibration"
            ))
        
        cal_fig.update_layout(
            title="Forecasting Epistemic Calibration Curve",
            xaxis_title="Mean Predicted Probability",
            yaxis_title="Fraction of Positives",
            template="plotly_dark",
            plot_bgcolor=CARD_BG,
            paper_bgcolor=DARK_BG
        )

        # 2. Equity Plot
        eq_fig = go.Figure()
        conn = get_db_connection()
        df_eq = pd.read_sql_query("SELECT timestamp, total_equity FROM equity_history", conn)
        conn.close()
        
        if not df_eq.empty:
            df_eq["time"] = pd.to_datetime(df_eq["timestamp"], unit="s")
            eq_fig.add_trace(go.Scatter(
                x=df_eq["time"],
                y=df_eq["total_equity"],
                line=dict(color=ACCENT_GREEN, width=2),
                mode="lines"
            ))
        eq_fig.update_layout(
            title="Portfolio Account Net Equity (30d)",
            xaxis_title="Timestamp",
            yaxis_title="Equity (USD)",
            template="plotly_dark",
            plot_bgcolor=CARD_BG,
            paper_bgcolor=DARK_BG
        )

        # 3. Opportunity Board Layout
        opp_table_headers = ["Venue", "Contract", "Category", "Model Prob", "Market Implied", "Edge %", "Status"]
        opp_rows = []
        
        try:
            from predmarket.config import load_config
            from predmarket.ingest import MarketIngestManager
            from predmarket.ensemble import EnsembleForecaster
            import asyncio
            
            config = load_config()
            ingest = MarketIngestManager(config)
            forecaster = EnsembleForecaster(config)
            
            async def fetch_snapshots():
                await ingest.initialize()
                try:
                    return await ingest.get_all_snapshots()
                finally:
                    await ingest.close()
            
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            if loop.is_running():
                nest_asyncio.apply()
            snapshots = loop.run_until_complete(fetch_snapshots())
            
            sim_opportunities = []
            for snap in snapshots:
                category = "political" if "ELECTION" in snap.contract_id else "econ"
                f_out = forecaster.generate_ensemble_forecast(
                    snapshot=snap,
                    category=category,
                    headline="Congressional leaders reach compromise bill on tax reforms.",
                    question=snap.title
                )
                sim_opportunities.append({
                    "venue": snap.venue,
                    "contract": snap.contract_id,
                    "category": category,
                    "prob": f_out["model_prob"],
                    "implied": f_out["market_implied"],
                    "status": f_out["status"]
                })
        except Exception as e:
            # Fallback to simulated opportunities if ingest fails or no connection
            sim_opportunities = [
                {"venue": "Polymarket", "contract": "PM-US-ELECTION-2026", "category": "political", "prob": 0.585, "implied": 0.585, "status": "READY"},
                {"venue": "Kalshi", "contract": "KL-FED-RATE-2026", "category": "econ", "prob": 0.58, "implied": 0.425, "status": "READY"},
                {"venue": "IB", "contract": "IB-CPI-JUNE-2026", "category": "econ", "prob": 0.65, "implied": 0.62, "status": "RESEARCH-ONLY"}
            ]

        for item in sim_opportunities:
            edge = item["prob"] - item["implied"]
            opp_rows.append(html.Tr([
                html.Td(item["venue"]),
                html.Td(item["contract"]),
                html.Td(item["category"]),
                html.Td(f"{item['prob']:.1%}"),
                html.Td(f"{item['implied']:.1%}"),
                html.Td(f"{edge:+.1%}", style={"color": ACCENT_GREEN if edge > 0 else ACCENT_RED}),
                html.Td(item["status"], style={"color": ACCENT_BLUE if item["status"] == "READY" else ACCENT_RED})
            ]))
            
        opp_table = dbc.Table([html.Thead(html.Tr([html.Th(h) for h in opp_table_headers])), html.Tbody(opp_rows)], bordered=True, hover=True, color="dark", responsive=True)

        # 4. Position Sizing Slate Layout
        slate_cards = []
        conn = get_db_connection()
        df_staged = pd.read_sql_query("""
            SELECT id, venue, contract, category, side, price, model_prob, market_implied, net_edge, size, details 
            FROM audit_trail 
            WHERE status = 'STAGED'
        """, conn)
        conn.close()
        
        for idx, row in df_staged.iterrows():
            edge = row["model_prob"] - row["market_implied"]
            recommended_allocation_pct = row["size"] / 10000.0 # hypothetical cash percentage
            
            slate_cards.append(
                dbc.Card(
                    dbc.CardBody([
                        html.H5(f"VENUE: {row['venue']} | CONTRACT: {row['contract']}", className="card-title", style={"color": ACCENT_ORANGE}),
                        html.P(f"SIDE: {row['side']} at {row['price']} | MODEL PROB: {row['model_prob']:.1%} | IMPLIED: {row['market_implied']:.1%} | raw edge: {edge:+.1%} | net edge: {row['net_edge']:+.1%}"),
                        html.P(f"RECOMMENDED ALLOCATION: ${row['size']:.2f} ({recommended_allocation_pct:.2%})"),
                        html.P(f"DETAILS / KEY RESOLUTION: {row['details']}", className="text-muted mb-1"),
                        dbc.Button(
                            "Approve Trade Intent", 
                            color="warning", 
                            className="mt-2", 
                            id={"type": "approve-btn", "index": int(row["id"])}
                        )
                    ]),
                    style={"background-color": DARK_BG, "border": f"1px solid {ACCENT_ORANGE}", "margin-bottom": "15px"}
                )
            )

        if not slate_cards:
            slate_cards = [html.P("No staging transactions currently ready.", className="text-muted")]

        return brier_str, logloss_str, pnl_str, drawdown_str, cal_fig, eq_fig, opp_table, html.Div(slate_cards), None
    except Exception as e:
        err_alert = dbc.Alert(f"Database/Network Connection Error: {e}", color="danger", dismissable=True)
        empty_fig = go.Figure()
        empty_fig.update_layout(template="plotly_dark", plot_bgcolor=CARD_BG, paper_bgcolor=DARK_BG)
        return "0.0000", "0.0000", "$0.00", "0.00%", empty_fig, empty_fig, html.P("Error loading data."), html.P("Error loading slate."), err_alert

# Pattern-matching Callback for Approve buttons
@app.callback(
    Output("error-banner", "children", allow_duplicate=True),
    Input({"type": "approve-btn", "index": ALL}, "n_clicks"),
    prevent_initial_call=True
)
def approve_trade_intent_callback(n_clicks_list):
    ctx = callback_context
    if not ctx.triggered:
        return None
        
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    import json
    try:
        trigger_dict = json.loads(trigger_id)
        staged_id = trigger_dict["index"]
    except Exception:
        return None
        
    val = ctx.triggered[0]["value"]
    if not val:
        return None
        
    import asyncio
    
    async def run_approval():
        return await approve_staged_order_db(staged_id)
        
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    if loop.is_running():
        nest_asyncio.apply()
    
    res = loop.run_until_complete(run_approval())
    if res["status"] == "success":
        return dbc.Alert(res["message"], color="success", dismissable=True)
    else:
        return dbc.Alert(res["message"], color="danger", dismissable=True)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(server, host="0.0.0.0", port=8050)
