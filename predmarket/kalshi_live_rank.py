"""Research-only live Kalshi opportunity ranking.

This module bridges offline discovery reports to current Kalshi market data.
It builds point-in-time live feature rows, applies discovered hypotheses when
available, falls back to a deterministic vulnerability watchlist score, and
writes auditable JSON/Markdown reports. It never places orders.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from predmarket.config import Config, load_config
from predmarket.discovery.dsl import DSLValidationError, SafeSignalDSL
from predmarket.kalshi_dataset import (
    KalshiMarketDataClient,
    KalshiResolvedDatasetBuilder,
    fill_probability,
    horizon_bucket,
    infer_resolution_source,
    infer_series_ticker,
    liquidity_bucket,
    _bounded_probability,
    _fp,
    _money,
    _stable_hash,
    _timestamp,
)
from predmarket.store import PointInTimeStore

logger = logging.getLogger("predmarket.kalshi_live_rank")


@dataclass
class KalshiLiveRankConfig:
    limit: int = 100
    max_pages: int = 1
    series_ticker: Optional[str] = None
    status: str = "open"
    fetch_orderbooks: bool = False
    fetch_candles: bool = False
    orderbook_depth: int = 10
    candle_lookback_hours: int = 48
    period_interval: int = 60
    top_k: int = 25
    min_liquidity_usd: float = 10_000.0
    max_spread: float = 0.12
    min_fill_probability: float = 0.20
    min_liquidity_adjusted_edge: float = 0.02
    min_time_to_close_hours: float = 1.0
    discovery_report_path: Optional[Path] = None


@dataclass
class KalshiLivePanel:
    rows: List[Dict[str, Any]]
    skipped_markets: List[Dict[str, Any]]


@dataclass
class KalshiLiveRankArtifacts:
    report: Dict[str, Any]
    json_path: Path
    markdown_path: Path


def build_live_row(
    market: Mapping[str, Any],
    *,
    orderbook: Optional[Mapping[str, Any]] = None,
    candlesticks: Optional[Sequence[Mapping[str, Any]]] = None,
    as_of_ts: Optional[float] = None,
) -> Dict[str, Any]:
    """Convert a current Kalshi market payload into discovery-compatible features."""
    ts = float(as_of_ts or time.time())
    ticker = str(market.get("ticker") or market.get("market_id") or "")
    event_id = str(market.get("event_ticker") or ticker)
    title = str(market.get("title") or market.get("yes_sub_title") or ticker)
    rules_primary = str(market.get("rules_primary") or "")
    rules_secondary = str(market.get("rules_secondary") or "")
    source = infer_resolution_source(market)
    series_ticker = infer_series_ticker(market)
    created_ts = _timestamp(market.get("created_time")) or ts
    close_ts = _timestamp(
        market.get("close_time")
        or market.get("expected_expiration_time")
        or market.get("expiration_time")
    )
    expiration_ts = _timestamp(
        market.get("expiration_time")
        or market.get("latest_expiration_time")
        or market.get("expected_expiration_time")
    )
    effective_end_ts = close_ts or expiration_ts or ts
    rules_text = " ".join(part for part in (rules_primary, rules_secondary) if part)
    liquidity = _money(market.get("liquidity_dollars")) or 0.0
    open_interest = _fp(market.get("open_interest_fp", market.get("open_interest"))) or 0.0
    volume_24h = _fp(market.get("volume_24h_fp", market.get("volume_24h"))) or 0.0
    volume_lifetime = _fp(market.get("volume_fp", market.get("volume"))) or 0.0
    quote = _live_quote_features(market, orderbook or {}, candlesticks or [])

    row: Dict[str, Any] = {
        "row_schema_version": 2,
        "venue": "Kalshi",
        "event_id": event_id,
        "market_id": ticker,
        "ticker": ticker,
        "series_ticker": series_ticker,
        "domain": str(market.get("category") or source.family or "unknown"),
        "title": title,
        "subtitle": str(market.get("subtitle") or ""),
        "rules_primary": rules_primary,
        "rules_secondary": rules_secondary,
        "rules_hash": _stable_hash({"primary": rules_primary, "secondary": rules_secondary}),
        "rules_word_count": float(len(_words(rules_text))),
        "rules_char_count": float(len(rules_text)),
        "rules_has_primary": 1.0 if rules_primary.strip() else 0.0,
        "rules_has_secondary": 1.0 if rules_secondary.strip() else 0.0,
        "rules_has_specific_source": 1.0 if _has_specific_source(rules_text) else 0.0,
        "rules_has_discretionary_terms": 1.0 if _has_discretionary_terms(rules_text) else 0.0,
        "rules_has_threshold_terms": 1.0 if _has_threshold_terms(f"{title} {rules_text}") else 0.0,
        "title_word_count": float(len(_words(title))),
        "title_has_threshold_terms": 1.0 if _has_threshold_terms(title) else 0.0,
        "resolution_source": source.family,
        "resolution_source_code": float(source.code),
        "resolution_source_confidence": float(source.confidence),
        "resolution_source_url": source.url,
        "created_ts": float(created_ts),
        "as_of_ts": ts,
        "market_age_hours": max((ts - float(created_ts)) / 3600.0, 0.0),
        "market_age_hours_at_close": max((float(effective_end_ts) - float(created_ts)) / 3600.0, 0.0),
        "time_to_close_hours": max(((close_ts or effective_end_ts) - ts) / 3600.0, 0.0),
        "time_to_expiration_hours": max(((expiration_ts or effective_end_ts) - ts) / 3600.0, 0.0),
        "horizon": horizon_bucket(max(float(effective_end_ts) - ts, 0.0)),
        "settlement_timer_hours": float(market.get("settlement_timer_seconds") or 0.0) / 3600.0,
        "can_close_early": 1.0 if bool(market.get("can_close_early")) else 0.0,
        "has_early_close_condition": 1.0 if str(market.get("early_close_condition") or "").strip() else 0.0,
        "fractional_trading_enabled": 1.0 if bool(market.get("fractional_trading_enabled")) else 0.0,
        "liquidity_dollars": liquidity,
        "open_interest": open_interest,
        "volume_24h": volume_24h,
        "volume_lifetime": volume_lifetime,
        "liquidity_bucket": liquidity_bucket(liquidity, open_interest),
        "p_baseline": 0.5,
        "filled": 0.0,
        "retrieved_ts": ts,
        "raw_market_json": json.dumps(dict(market), sort_keys=True, default=str),
        "raw_orderbook_json": json.dumps(dict(orderbook or {}), sort_keys=True, default=str),
    }
    row.update(quote)
    row["square_money_vulnerability"] = vulnerability_score(row)
    row["row_id"] = stable_live_row_id(row)
    return row


async def fetch_live_kalshi_panel(
    config: Config,
    rank_config: KalshiLiveRankConfig,
    *,
    store: Optional[PointInTimeStore] = None,
    as_of_ts: Optional[float] = None,
) -> KalshiLivePanel:
    ts = float(as_of_ts or time.time())
    rows: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    async with KalshiMarketDataClient(config) as client:
        markets = await client.fetch_markets(
            status=rank_config.status,
            limit=rank_config.limit,
            max_pages=rank_config.max_pages,
            series_ticker=rank_config.series_ticker,
        )
        for market in markets:
            ticker = str(market.get("ticker") or "")
            if not ticker:
                skipped.append({"reason": "missing_ticker", "market": dict(market)})
                continue

            orderbook: Dict[str, Any] = {}
            if rank_config.fetch_orderbooks:
                try:
                    orderbook = await client.fetch_orderbook(
                        market,
                        depth=rank_config.orderbook_depth,
                    )
                except Exception as exc:
                    skipped.append(
                        {
                            "reason": "orderbook_unavailable",
                            "ticker": ticker,
                            "error": str(exc),
                        }
                    )
                    logger.warning("Kalshi orderbook fetch failed for %s: %s", ticker, exc)

            candles: List[Dict[str, Any]] = []
            if rank_config.fetch_candles:
                try:
                    candles = await client.fetch_candlesticks(
                        market,
                        start_ts=int(ts - rank_config.candle_lookback_hours * 3600),
                        end_ts=int(ts),
                        period_interval=rank_config.period_interval,
                        historical=False,
                    )
                except Exception as exc:
                    skipped.append(
                        {
                            "reason": "candles_unavailable",
                            "ticker": ticker,
                            "error": str(exc),
                        }
                    )
                    logger.warning("Kalshi candle fetch failed for %s: %s", ticker, exc)

            row = build_live_row(
                market,
                orderbook=orderbook,
                candlesticks=candles,
                as_of_ts=ts,
            )
            rows.append(row)
            if store is not None:
                persist_live_snapshot(store, row, market=market, orderbook=orderbook)

    rows.sort(key=lambda row: (-float(row.get("volume_24h", 0.0)), row.get("market_id", "")))
    return KalshiLivePanel(rows=rows, skipped_markets=skipped)


def persist_live_snapshot(
    store: PointInTimeStore,
    row: Mapping[str, Any],
    *,
    market: Optional[Mapping[str, Any]] = None,
    orderbook: Optional[Mapping[str, Any]] = None,
) -> None:
    snapshot = SimpleNamespace(
        venue="Kalshi",
        contract_id=str(row.get("market_id", "")),
        title=str(row.get("title", "")),
        bid=float(row.get("yes_bid", 0.0)),
        ask=float(row.get("yes_ask", 0.0)),
        mid=float(row.get("mid_price", row.get("market_implied", 0.5))),
        open_interest=float(row.get("open_interest", 0.0)),
        volume_24h=float(row.get("volume_24h", 0.0)),
        line_history=[float(row.get("market_implied", 0.5))],
    )
    raw_payload = dict(market or {})
    raw_payload.update(
        {
            "venue": "Kalshi",
            "contract_id": snapshot.contract_id,
            "title": snapshot.title,
            "bid": snapshot.bid,
            "ask": snapshot.ask,
            "mid": snapshot.mid,
            "open_interest": snapshot.open_interest,
            "volume_24h": snapshot.volume_24h,
            "line_history": snapshot.line_history,
        }
    )
    raw_payload["live_rank_row"] = dict(row)
    store.write_market_snapshot(
        snapshot,
        event_id=str(row.get("event_id", row.get("market_id", ""))),
        raw_payload=raw_payload,
        as_of_ts=float(row.get("as_of_ts", time.time())),
    )
    bids, asks = orderbook_to_yes_bids_and_asks(orderbook or {})
    store.write_orderbook(
        str(row.get("market_id", "")),
        bids,
        asks,
        as_of_ts=float(row.get("as_of_ts", time.time())),
        raw_payload=dict(orderbook or {}),
    )


def load_discovery_report(
    *,
    reports_dir: Path,
    explicit_path: Optional[Path] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Path]]:
    if explicit_path is not None:
        if not explicit_path.exists():
            return None, explicit_path
        with explicit_path.open("r", encoding="utf-8") as f:
            return json.load(f), explicit_path

    candidates = sorted(
        reports_dir.glob("discovery-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None, None
    with candidates[0].open("r", encoding="utf-8") as f:
        return json.load(f), candidates[0]


def rank_live_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    config: Optional[KalshiLiveRankConfig] = None,
    discovery_report: Optional[Mapping[str, Any]] = None,
    discovery_report_path: Optional[Path] = None,
) -> Dict[str, Any]:
    rank_config = config or KalshiLiveRankConfig()
    row_dicts = [dict(row) for row in rows if str(row.get("venue", "")).lower() == "kalshi"]
    hypothesis_scores, score_meta = score_rows_with_hypotheses(row_dicts, discovery_report)
    opportunities = []

    for row, model_payload in zip(row_dicts, hypothesis_scores):
        market_prob = float(row.get("market_implied", 0.5))
        p_model = float(model_payload["p_model"])
        yes_bid = float(row.get("yes_bid", market_prob))
        yes_ask = float(row.get("yes_ask", market_prob))
        no_ask = max(1.0 - yes_bid, 0.01)
        yes_edge = p_model - yes_ask
        no_edge = (1.0 - p_model) - no_ask
        side = "YES" if yes_edge >= no_edge else "NO"
        directional_edge = max(yes_edge, no_edge)
        fill_prob = float(row.get("fill_probability", 0.0))
        costs = float(row.get("fees", 0.0)) + float(row.get("slippage", 0.0))
        liquidity_adjusted_edge = directional_edge * fill_prob - costs
        vulnerability = float(row.get("square_money_vulnerability", vulnerability_score(row)))
        used_hypotheses = model_payload.get("used_hypotheses", [])
        scoring_mode = "hypothesis_edge" if used_hypotheses else "watchlist_vulnerability"
        ranking_score = (
            liquidity_adjusted_edge + 0.02 * vulnerability
            if used_hypotheses
            else vulnerability
        )
        blocking_reasons = blocking_reasons_for_row(
            row,
            liquidity_adjusted_edge=liquidity_adjusted_edge,
            directional_edge=directional_edge,
            used_hypotheses=bool(used_hypotheses),
            config=rank_config,
        )
        opportunities.append(
            {
                "market_id": row.get("market_id"),
                "event_id": row.get("event_id"),
                "venue": row.get("venue", "Kalshi"),
                "title": row.get("title"),
                "domain": row.get("domain"),
                "horizon": row.get("horizon"),
                "side": side,
                "market_probability": market_prob,
                "model_probability": p_model,
                "yes_bid": yes_bid,
                "yes_ask": yes_ask,
                "directional_edge": directional_edge,
                "liquidity_adjusted_edge": liquidity_adjusted_edge,
                "ranking_score": ranking_score,
                "square_money_vulnerability": vulnerability,
                "fill_probability": fill_prob,
                "bid_ask_spread": float(row.get("bid_ask_spread", 0.0)),
                "liquidity_dollars": float(row.get("liquidity_dollars", 0.0)),
                "open_interest": float(row.get("open_interest", 0.0)),
                "volume_24h": float(row.get("volume_24h", 0.0)),
                "time_to_close_hours": float(row.get("time_to_close_hours", 0.0)),
                "resolution_source": row.get("resolution_source"),
                "rules_flags": {
                    "specific_source": float(row.get("rules_has_specific_source", 0.0)),
                    "threshold_terms": float(row.get("rules_has_threshold_terms", 0.0)),
                    "discretionary_terms": float(row.get("rules_has_discretionary_terms", 0.0)),
                    "secondary_rules": float(row.get("rules_has_secondary", 0.0)),
                },
                "used_hypotheses": used_hypotheses,
                "blocking_reasons": blocking_reasons,
                "candidate_status": "RESEARCH_ONLY_PASS" if not blocking_reasons else "RESEARCH_ONLY_BLOCKED",
                "scoring_mode": scoring_mode,
            }
        )

    opportunities.sort(
        key=lambda item: (
            item["candidate_status"] != "RESEARCH_ONLY_PASS",
            -float(item["ranking_score"]),
            str(item["market_id"]),
        )
    )
    selected = opportunities[: rank_config.top_k]
    return {
        "run_id": stable_live_rank_run_id(row_dicts, rank_config, discovery_report),
        "created_ts": time.time(),
        "runner_config": {
            **asdict(rank_config),
            "discovery_report_path": str(rank_config.discovery_report_path)
            if rank_config.discovery_report_path
            else None,
        },
        "input_summary": summarize_live_rows(row_dicts),
        "discovery_report_ref": {
            "path": str(discovery_report_path) if discovery_report_path else None,
            "run_id": discovery_report.get("run_id") if discovery_report else None,
            "usable_hypotheses": score_meta["usable_hypotheses"],
            "rejected_hypotheses": score_meta["rejected_hypotheses"],
        },
        "top_opportunities": selected,
        "all_opportunity_count": len(opportunities),
        "research_only": True,
        "execution_enabled": False,
    }


def score_rows_with_hypotheses(
    rows: Sequence[Mapping[str, Any]],
    discovery_report: Optional[Mapping[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not rows:
        return [], {"usable_hypotheses": 0, "rejected_hypotheses": []}
    hypotheses = list((discovery_report or {}).get("top_hypotheses", []))
    if not hypotheses:
        return [
            {"p_model": float(row.get("market_implied", 0.5)), "used_hypotheses": []}
            for row in rows
        ], {"usable_hypotheses": 0, "rejected_hypotheses": []}

    feature_catalog = KalshiResolvedDatasetBuilder.feature_catalog(rows)
    dsl = SafeSignalDSL(feature_catalog)
    weighted = np.zeros(len(rows), dtype=float)
    total_weight = np.zeros(len(rows), dtype=float)
    used_by_row: List[List[Dict[str, Any]]] = [[] for _ in rows]
    rejected: List[Dict[str, Any]] = []

    for hypothesis in hypotheses:
        expression = str(hypothesis.get("expression") or "")
        if not expression:
            rejected.append({"hypothesis_id": hypothesis.get("hypothesis_id"), "reason": "missing_expression"})
            continue
        try:
            values = np.asarray(dsl.evaluate(expression, [dict(row) for row in rows]), dtype=float)
            probabilities = _values_to_probabilities(values, rows)
        except DSLValidationError as exc:
            rejected.append(
                {
                    "hypothesis_id": hypothesis.get("hypothesis_id"),
                    "expression": expression,
                    "reason": str(exc),
                }
            )
            continue
        weight = max(float(hypothesis.get("reward") or 0.0), 0.0) + 0.01
        weighted += probabilities * weight
        total_weight += weight
        for idx in range(len(rows)):
            used_by_row[idx].append(
                {
                    "hypothesis_id": hypothesis.get("hypothesis_id"),
                    "name": hypothesis.get("name"),
                    "expression": expression,
                    "weight": weight,
                    "p": float(probabilities[idx]),
                }
            )

    out = []
    for idx, row in enumerate(rows):
        if total_weight[idx] > 0:
            p_model = float(np.clip(weighted[idx] / total_weight[idx], 0.01, 0.99))
            used = used_by_row[idx]
        else:
            p_model = float(row.get("market_implied", 0.5))
            used = []
        out.append({"p_model": p_model, "used_hypotheses": used})

    return out, {
        "usable_hypotheses": len(hypotheses) - len(rejected),
        "rejected_hypotheses": rejected[:20],
    }


def blocking_reasons_for_row(
    row: Mapping[str, Any],
    *,
    liquidity_adjusted_edge: float,
    directional_edge: float,
    used_hypotheses: bool,
    config: KalshiLiveRankConfig,
) -> List[str]:
    reasons = []
    if not used_hypotheses:
        reasons.append("watchlist_only_no_usable_discovery_hypothesis")
    if float(row.get("bid_ask_spread", 1.0)) > config.max_spread:
        reasons.append("spread_too_wide")
    if float(row.get("liquidity_dollars", 0.0)) < config.min_liquidity_usd:
        reasons.append("liquidity_below_min")
    if float(row.get("fill_probability", 0.0)) < config.min_fill_probability:
        reasons.append("fill_probability_below_min")
    if directional_edge <= 0.0:
        reasons.append("no_positive_directional_edge")
    elif liquidity_adjusted_edge < config.min_liquidity_adjusted_edge:
        reasons.append("liquidity_adjusted_edge_below_min")
    if float(row.get("time_to_close_hours", 0.0)) < config.min_time_to_close_hours:
        reasons.append("too_close_to_market_close")
    if float(row.get("orderbook_available", 0.0)) <= 0.0:
        reasons.append("orderbook_not_available")
    return reasons


def write_live_rank_report(
    report: Mapping[str, Any],
    *,
    reports_dir: Path,
) -> KalshiLiveRankArtifacts:
    reports_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(report.get("run_id") or f"live-kalshi-{int(time.time())}")
    json_path = reports_dir / f"{run_id}.json"
    markdown_path = reports_dir / f"{run_id}.md"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True, default=str)
    with markdown_path.open("w", encoding="utf-8") as f:
        f.write(render_live_rank_markdown(report))
    return KalshiLiveRankArtifacts(dict(report), json_path, markdown_path)


def render_live_rank_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("input_summary", {})
    lines = [
        f"# Live Kalshi Rank Report: {report.get('run_id', '')}",
        "",
        "## Scope",
        "",
        "- Mode: research-only",
        "- Execution enabled: false",
        f"- Markets ranked: {summary.get('n_rows', 0)}",
        f"- Domains: {summary.get('domains', {})}",
        f"- Horizons: {summary.get('horizons', {})}",
        f"- Discovery report: {report.get('discovery_report_ref', {}).get('path')}",
        "",
        "## Top Opportunities",
        "",
    ]
    top = report.get("top_opportunities", [])
    if not top:
        lines.append("No live Kalshi opportunities ranked.")
    for idx, item in enumerate(top, start=1):
        lines.extend(
            [
                f"### {idx}. {item.get('market_id', '')}",
                "",
                str(item.get("title", "")),
                "",
                f"- Status: {item.get('candidate_status', '')}",
                f"- Side: {item.get('side', '')}",
                f"- Score mode: {item.get('scoring_mode', '')}",
                f"- Market/model probability: {float(item.get('market_probability', 0.0)):.2%} / {float(item.get('model_probability', 0.0)):.2%}",
                f"- Liquidity-adjusted edge: {float(item.get('liquidity_adjusted_edge', 0.0)):.4f}",
                f"- Vulnerability: {float(item.get('square_money_vulnerability', 0.0)):.3f}",
                f"- Spread/fill: {float(item.get('bid_ask_spread', 0.0)):.4f} / {float(item.get('fill_probability', 0.0)):.2%}",
                f"- Blocking reasons: {item.get('blocking_reasons', [])}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def run_kalshi_live_rank(
    store: PointInTimeStore,
    *,
    app_config: Optional[Config] = None,
    config: Optional[KalshiLiveRankConfig] = None,
    rows: Optional[Sequence[Mapping[str, Any]]] = None,
    reports_dir: Optional[Path] = None,
) -> KalshiLiveRankArtifacts:
    app_config = app_config or load_config()
    rank_config = config or KalshiLiveRankConfig()
    out_dir = reports_dir or (store.research_dir / "reports")
    if rows is None:
        panel = asyncio.run(fetch_live_kalshi_panel(app_config, rank_config, store=store))
        live_rows = panel.rows
        skipped = panel.skipped_markets
    else:
        live_rows = [dict(row) for row in rows]
        skipped = []

    discovery_report, discovery_path = load_discovery_report(
        reports_dir=out_dir,
        explicit_path=rank_config.discovery_report_path,
    )
    report = rank_live_rows(
        live_rows,
        config=rank_config,
        discovery_report=discovery_report,
        discovery_report_path=discovery_path,
    )
    report["skipped_markets"] = skipped
    return write_live_rank_report(report, reports_dir=out_dir)


def summarize_live_rows(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    def counts(field: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for row in rows:
            key = str(row.get(field, "unknown"))
            out[key] = out.get(key, 0) + 1
        return dict(sorted(out.items(), key=lambda item: (-item[1], item[0])))

    return {
        "n_rows": len(rows),
        "n_markets": len({row.get("market_id") for row in rows}),
        "as_of_min": min((float(row.get("as_of_ts", 0.0)) for row in rows), default=None),
        "as_of_max": max((float(row.get("as_of_ts", 0.0)) for row in rows), default=None),
        "domains": counts("domain"),
        "horizons": counts("horizon"),
        "liquidity_buckets": counts("liquidity_bucket"),
    }


def vulnerability_score(row: Mapping[str, Any]) -> float:
    volume = max(float(row.get("volume_24h", 0.0)), float(row.get("volume_lifetime", 0.0)))
    narrative_attention = min(math.log1p(volume) / math.log1p(500_000.0), 1.0)
    technical_resolution = min(
        0.22 * float(row.get("rules_has_specific_source", 0.0))
        + 0.18 * float(row.get("rules_has_secondary", 0.0))
        + 0.18 * min(float(row.get("rules_word_count", 0.0)) / 180.0, 1.0)
        + 0.22 * float(row.get("rules_has_threshold_terms", 0.0))
        + 0.10 * float(row.get("has_early_close_condition", 0.0))
        + 0.10 * float(row.get("can_close_early", 0.0)),
        1.0,
    )
    price_confusion = min(
        abs(float(row.get("price_momentum_1", 0.0))) * 4.0
        + float(row.get("bid_ask_spread", 0.0)) * 2.0,
        1.0,
    )
    executability = float(row.get("fill_probability", 0.0))
    return float(
        max(
            0.0,
            min(
                1.0,
                0.35 * narrative_attention
                + 0.35 * technical_resolution
                + 0.15 * price_confusion
                + 0.15 * executability,
            ),
        )
    )


def orderbook_to_yes_bids_and_asks(
    orderbook: Mapping[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    features = _orderbook_features(orderbook)
    yes_levels = features.get("yes_levels", [])
    no_levels = features.get("no_levels", [])
    asks = [
        {"price": round(float(np.clip(1.0 - level["price"], 0.01, 0.99)), 10), "size": level["size"]}
        for level in no_levels
    ]
    asks.sort(key=lambda level: level["price"])
    return yes_levels, asks


def stable_live_row_id(row: Mapping[str, Any]) -> str:
    payload = {
        "market_id": row.get("market_id"),
        "as_of_ts": row.get("as_of_ts"),
        "schema": row.get("row_schema_version", 2),
    }
    return "kalshi-live-row-" + _stable_hash(payload)[:20]


def stable_live_rank_run_id(
    rows: Sequence[Mapping[str, Any]],
    config: KalshiLiveRankConfig,
    discovery_report: Optional[Mapping[str, Any]],
) -> str:
    payload = {
        "markets": [row.get("row_id") for row in rows[:1000]],
        "config": asdict(config),
        "discovery_run_id": (discovery_report or {}).get("run_id"),
    }
    return "live-kalshi-" + _stable_hash(payload)[:16]


def _live_quote_features(
    market: Mapping[str, Any],
    orderbook: Mapping[str, Any],
    candlesticks: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    book = _orderbook_features(orderbook)
    latest_candle = _latest_candle(candlesticks)
    candle_price = _candle_price(latest_candle)
    candle_previous = _candle_previous(latest_candle)
    last = candle_price or _money(market.get("last_price_dollars"))
    previous = candle_previous or _money(market.get("previous_price_dollars")) or last
    bid = book.get("yes_bid")
    ask = book.get("yes_ask")
    if bid is None:
        bid = _money(market.get("yes_bid_dollars"))
    if ask is None:
        ask = _money(market.get("yes_ask_dollars"))
    if last is None and bid is not None and ask is not None:
        last = (float(bid) + float(ask)) / 2.0

    implied = _bounded_probability(last, fallback=0.5)
    bid = _bounded_probability(bid, fallback=max(implied - 0.01, 0.01))
    ask = _bounded_probability(ask, fallback=min(implied + 0.01, 0.99))
    if ask < bid:
        ask = bid
    spread = max(ask - bid, 0.0)
    candle_volume = _fp((latest_candle or {}).get("volume_fp", (latest_candle or {}).get("volume"))) or 0.0
    candle_open_interest = (
        _fp((latest_candle or {}).get("open_interest_fp", (latest_candle or {}).get("open_interest")))
        or _fp(market.get("open_interest_fp", market.get("open_interest")))
        or 0.0
    )
    volume = _fp(market.get("volume_24h_fp", market.get("volume_24h"))) or candle_volume
    open_interest = _fp(market.get("open_interest_fp", market.get("open_interest"))) or candle_open_interest
    return {
        "market_implied": implied,
        "execution_price": min(ask, 0.99),
        "yes_bid": bid,
        "yes_ask": ask,
        "no_bid": _bounded_probability(book.get("no_bid"), fallback=max(1.0 - ask, 0.01)),
        "no_ask": _bounded_probability(book.get("no_ask"), fallback=min(1.0 - bid, 0.99)),
        "bid_ask_spread": spread,
        "mid_price": (bid + ask) / 2.0,
        "last_price": implied,
        "previous_price": _bounded_probability(previous, fallback=implied),
        "price_momentum_1": implied - _bounded_probability(previous, fallback=implied),
        "candle_volume": candle_volume,
        "candle_open_interest": candle_open_interest,
        "orderbook_available": 1.0 if book.get("available") else 0.0,
        "orderbook_yes_depth": float(book.get("yes_depth", 0.0)),
        "orderbook_no_depth": float(book.get("no_depth", 0.0)),
        "top_yes_bid_size": float(book.get("top_yes_bid_size", 0.0)),
        "top_no_bid_size": float(book.get("top_no_bid_size", 0.0)),
        "fees": 0.0015,
        "slippage": min(max(spread * 0.25, 0.0), 0.05),
        "fill_probability": fill_probability(spread, volume, open_interest),
        "raw_candlestick_json": json.dumps(dict(latest_candle or {}), sort_keys=True, default=str),
    }


def _orderbook_features(orderbook: Mapping[str, Any]) -> Dict[str, Any]:
    book = orderbook.get("orderbook_fp") or orderbook.get("orderbook") or orderbook
    if not isinstance(book, Mapping):
        book = {}
    yes_levels = _normalize_book_levels(
        book.get("yes_dollars")
        or book.get("yes")
        or book.get("true")
        or book.get("bids")
        or []
    )
    no_levels = _normalize_book_levels(
        book.get("no_dollars")
        or book.get("no")
        or book.get("false")
        or []
    )
    yes_bid = yes_levels[0]["price"] if yes_levels else None
    no_bid = no_levels[0]["price"] if no_levels else None
    yes_ask = round(1.0 - no_bid, 10) if no_bid is not None else None
    no_ask = round(1.0 - yes_bid, 10) if yes_bid is not None else None
    return {
        "available": bool(yes_levels or no_levels),
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "no_bid": no_bid,
        "no_ask": no_ask,
        "yes_depth": sum(level["size"] for level in yes_levels),
        "no_depth": sum(level["size"] for level in no_levels),
        "top_yes_bid_size": yes_levels[0]["size"] if yes_levels else 0.0,
        "top_no_bid_size": no_levels[0]["size"] if no_levels else 0.0,
        "yes_levels": yes_levels,
        "no_levels": no_levels,
    }


def _normalize_book_levels(levels: Any) -> List[Dict[str, float]]:
    out: List[Dict[str, float]] = []
    if not isinstance(levels, Sequence) or isinstance(levels, (str, bytes)):
        return out
    for level in levels:
        price_raw = None
        size_raw = None
        if isinstance(level, Mapping):
            price_raw = (
                level.get("price_dollars")
                or level.get("price")
                or level.get("yes_price")
                or level.get("no_price")
            )
            size_raw = level.get("size_fp") or level.get("size") or level.get("quantity")
        elif isinstance(level, Sequence) and not isinstance(level, (str, bytes)) and len(level) >= 2:
            price_raw = level[0]
            size_raw = level[1]
        price = _money(price_raw)
        size = _fp(size_raw) or 0.0
        if price is None:
            continue
        if price > 1.0:
            price = price / 100.0
        out.append(
            {
                "price": float(np.clip(price, 0.01, 0.99)),
                "size": max(float(size), 0.0),
            }
        )
    out.sort(key=lambda level: level["price"], reverse=True)
    return out


def _values_to_probabilities(values: np.ndarray, rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
    if len(values) == 0:
        return values
    if float(np.nanmin(values)) >= 0.0 and float(np.nanmax(values)) <= 1.0:
        return np.clip(values, 0.01, 0.99)
    baseline = np.asarray(
        [float(row.get("market_implied", row.get("p_baseline", 0.5))) for row in rows],
        dtype=float,
    )
    return np.clip(baseline + 0.15 * SafeSignalDSL._zscore(values), 0.01, 0.99)


def _latest_candle(candlesticks: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    valid = [
        candle
        for candle in candlesticks
        if _timestamp(candle.get("end_period_ts")) is not None
    ]
    if not valid:
        return None
    return sorted(valid, key=lambda candle: float(_timestamp(candle.get("end_period_ts")) or 0.0))[-1]


def _candle_price(candle: Optional[Mapping[str, Any]]) -> Optional[float]:
    if not candle:
        return None
    price = candle.get("price") or {}
    if not isinstance(price, Mapping):
        return None
    return _money(price.get("close_dollars", price.get("close")))


def _candle_previous(candle: Optional[Mapping[str, Any]]) -> Optional[float]:
    if not candle:
        return None
    price = candle.get("price") or {}
    if not isinstance(price, Mapping):
        return None
    return _money(price.get("previous_dollars", price.get("previous")))


def _words(text: str) -> List[str]:
    return [word for word in text.replace("/", " ").replace("-", " ").split() if word.strip()]


def _has_specific_source(text: str) -> bool:
    lowered = text.lower()
    needles = (
        "according to",
        "reported by",
        "source",
        "official",
        "bureau",
        "noaa",
        "federal reserve",
        "congress",
    )
    return any(needle in lowered for needle in needles)


def _has_discretionary_terms(text: str) -> bool:
    lowered = text.lower()
    needles = ("determined by kalshi", "sole discretion", "may be amended", "ambiguous")
    return any(needle in lowered for needle in needles)


def _has_threshold_terms(text: str) -> bool:
    lowered = text.lower()
    tokens = (
        "above",
        "below",
        "at least",
        "greater than",
        "less than",
        "between",
        "within",
        "before",
        "after",
        "%",
        "$",
    )
    return any(token in lowered for token in tokens) or any(ch.isdigit() for ch in lowered)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Rank live Kalshi markets for research-only review")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--series-ticker", default=None)
    parser.add_argument("--status", default="open")
    parser.add_argument("--orderbooks", action="store_true", help="Attempt per-market orderbook enrichment")
    parser.add_argument("--candles", action="store_true", help="Attempt per-market candlestick enrichment")
    parser.add_argument("--orderbook-depth", type=int, default=10)
    parser.add_argument("--candle-lookback-hours", type=int, default=48)
    parser.add_argument("--period-interval", type=int, default=60, choices=[1, 60, 1440])
    parser.add_argument("--top-k", type=int, default=25)
    parser.add_argument("--min-liquidity-usd", type=float, default=10_000.0)
    parser.add_argument("--max-spread", type=float, default=0.12)
    parser.add_argument("--min-fill-probability", type=float, default=0.20)
    parser.add_argument("--min-liquidity-adjusted-edge", type=float, default=0.02)
    parser.add_argument("--min-time-to-close-hours", type=float, default=1.0)
    parser.add_argument("--discovery-report", default=None)
    parser.add_argument("--reports-dir", default=None)
    args = parser.parse_args(argv)

    app_config = load_config()
    store = PointInTimeStore(app_config.global_cfg.data_dir)
    try:
        rank_config = KalshiLiveRankConfig(
            limit=args.limit,
            max_pages=args.max_pages,
            series_ticker=args.series_ticker,
            status=args.status,
            fetch_orderbooks=args.orderbooks,
            fetch_candles=args.candles,
            orderbook_depth=args.orderbook_depth,
            candle_lookback_hours=args.candle_lookback_hours,
            period_interval=args.period_interval,
            top_k=args.top_k,
            min_liquidity_usd=args.min_liquidity_usd,
            max_spread=args.max_spread,
            min_fill_probability=args.min_fill_probability,
            min_liquidity_adjusted_edge=args.min_liquidity_adjusted_edge,
            min_time_to_close_hours=args.min_time_to_close_hours,
            discovery_report_path=Path(args.discovery_report) if args.discovery_report else None,
        )
        artifacts = run_kalshi_live_rank(
            store,
            app_config=app_config,
            config=rank_config,
            reports_dir=Path(args.reports_dir) if args.reports_dir else None,
        )
    finally:
        store.close()

    print(
        json.dumps(
            {
                "run_id": artifacts.report["run_id"],
                "markets_ranked": artifacts.report["input_summary"]["n_rows"],
                "top_opportunities": len(artifacts.report["top_opportunities"]),
                "json_path": str(artifacts.json_path),
                "markdown_path": str(artifacts.markdown_path),
                "research_only": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI smoke path
    raise SystemExit(main())
