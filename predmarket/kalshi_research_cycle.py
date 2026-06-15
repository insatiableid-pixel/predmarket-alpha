"""Closed-loop Kalshi research cycle.

The cycle converts live Kalshi rankings into research-only paper trade intents,
persists a paper ledger, optionally settles existing intents from resolved rows,
and writes an audit report. It deliberately stays outside the execution and
human-approval order paths.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from predmarket.config import Config, load_config
from predmarket.kalshi_live_rank import (
    KalshiLiveRankArtifacts,
    KalshiLiveRankConfig,
    run_kalshi_live_rank,
)
from predmarket.kalshi_dataset import _stable_hash
from predmarket.store import PointInTimeStore


@dataclass
class KalshiPaperConfig:
    bankroll_usd: float = 10_000.0
    max_intents: int = 10
    max_stake_usd: float = 25.0
    max_total_stake_usd: float = 100.0
    max_event_stake_usd: float = 50.0
    max_position_fraction: float = 0.0025
    min_stake_usd: float = 1.0
    min_liquidity_adjusted_edge: float = 0.02
    min_directional_edge: float = 0.03
    min_fill_probability: float = 0.20
    max_spread: float = 0.12
    allow_blocked_opportunities: bool = False
    suppress_duplicate_open_intents: bool = True
    settle_existing: bool = True
    min_settled_for_promotion_review: int = 30
    max_brier_for_promotion_review: float = 0.20
    min_win_rate_for_promotion_review: float = 0.55
    min_pnl_for_promotion_review: float = 0.0


@dataclass
class KalshiResearchCycleConfig:
    live_rank: KalshiLiveRankConfig = field(default_factory=KalshiLiveRankConfig)
    paper: KalshiPaperConfig = field(default_factory=KalshiPaperConfig)


@dataclass
class KalshiResearchCycleArtifacts:
    report: Dict[str, Any]
    json_path: Path
    markdown_path: Path
    live_rank_artifacts: Optional[KalshiLiveRankArtifacts] = None


def build_paper_intents(
    rank_report: Mapping[str, Any],
    *,
    config: Optional[KalshiPaperConfig] = None,
    existing_intents: Sequence[Mapping[str, Any]] = (),
    created_ts: Optional[float] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    paper_config = config or KalshiPaperConfig()
    ts = float(created_ts or time.time())
    intents: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    event_stakes: Dict[str, float] = {}
    total_stake = 0.0
    rank_run_id = str(rank_report.get("run_id") or "")
    open_pairs = {
        (str(intent.get("market_id") or ""), str(intent.get("side") or "").upper())
        for intent in existing_intents
        if str(intent.get("status", "PAPER_INTENDED")) == "PAPER_INTENDED"
    }

    for opportunity in rank_report.get("top_opportunities", []):
        opp = dict(opportunity)
        side = str(opp.get("side") or "YES").upper()
        market_id = str(opp.get("market_id") or "")
        reasons = paper_blocking_reasons(opp, config=paper_config)
        if paper_config.suppress_duplicate_open_intents and (market_id, side) in open_pairs:
            reasons.append("paper_duplicate_open_intent")
        event_id = str(opp.get("event_id") or opp.get("market_id") or "")
        if reasons and not paper_config.allow_blocked_opportunities:
            blocked.append({**opp, "paper_blocking_reasons": reasons})
            continue
        if len(intents) >= paper_config.max_intents:
            blocked.append({**opp, "paper_blocking_reasons": ["paper_intent_limit_reached"]})
            continue

        stake = compute_paper_stake_usd(
            opp,
            config=paper_config,
            remaining_total=max(paper_config.max_total_stake_usd - total_stake, 0.0),
            remaining_event=max(paper_config.max_event_stake_usd - event_stakes.get(event_id, 0.0), 0.0),
        )
        if stake < paper_config.min_stake_usd:
            blocked.append({**opp, "paper_blocking_reasons": [*reasons, "stake_below_minimum"]})
            continue

        yes_ask = float(opp.get("yes_ask", opp.get("market_probability", 0.5)))
        yes_bid = float(opp.get("yes_bid", opp.get("market_probability", 0.5)))
        entry_price = yes_ask if side == "YES" else max(1.0 - yes_bid, 0.01)
        contracts = stake / max(entry_price, 0.01)
        model_prob = float(opp.get("model_probability", 0.5))
        side_prob = model_prob if side == "YES" else 1.0 - model_prob
        expected_value_usd = contracts * (side_prob - entry_price)
        intent = {
            "intent_id": stable_paper_intent_id(opp, rank_run_id, ts),
            "created_ts": ts,
            "source_run_id": rank_run_id,
            "market_id": opp.get("market_id"),
            "event_id": event_id,
            "title": opp.get("title"),
            "side": side,
            "status": "PAPER_INTENDED",
            "research_only": True,
            "execution_enabled": False,
            "as_of_ts": rank_report.get("created_ts", ts),
            "entry_price": entry_price,
            "market_probability": float(opp.get("market_probability", 0.5)),
            "model_probability": model_prob,
            "side_probability": side_prob,
            "directional_edge": float(opp.get("directional_edge", 0.0)),
            "liquidity_adjusted_edge": float(opp.get("liquidity_adjusted_edge", 0.0)),
            "ranking_score": float(opp.get("ranking_score", 0.0)),
            "stake_usd": stake,
            "max_loss_usd": stake,
            "contracts": contracts,
            "expected_value_usd": expected_value_usd,
            "blocking_reasons": list(opp.get("blocking_reasons", [])),
            "paper_blocking_reasons": reasons,
            "source_opportunity": opp,
        }
        intents.append(intent)
        open_pairs.add((market_id, side))
        total_stake += stake
        event_stakes[event_id] = event_stakes.get(event_id, 0.0) + stake

    return intents, blocked


def paper_blocking_reasons(
    opportunity: Mapping[str, Any],
    *,
    config: KalshiPaperConfig,
) -> List[str]:
    reasons = list(opportunity.get("blocking_reasons", []))
    if str(opportunity.get("candidate_status", "")) != "RESEARCH_ONLY_PASS":
        reasons.append("rank_status_not_pass")
    if float(opportunity.get("liquidity_adjusted_edge", 0.0)) < config.min_liquidity_adjusted_edge:
        reasons.append("paper_liquidity_adjusted_edge_below_min")
    if float(opportunity.get("directional_edge", 0.0)) < config.min_directional_edge:
        reasons.append("paper_directional_edge_below_min")
    if float(opportunity.get("fill_probability", 0.0)) < config.min_fill_probability:
        reasons.append("paper_fill_probability_below_min")
    if float(opportunity.get("bid_ask_spread", 1.0)) > config.max_spread:
        reasons.append("paper_spread_too_wide")
    if not opportunity.get("used_hypotheses"):
        reasons.append("paper_requires_discovery_hypothesis")
    return sorted(set(reasons))


def compute_paper_stake_usd(
    opportunity: Mapping[str, Any],
    *,
    config: KalshiPaperConfig,
    remaining_total: float,
    remaining_event: float,
) -> float:
    edge = max(float(opportunity.get("liquidity_adjusted_edge", 0.0)), 0.0)
    directional_edge = max(float(opportunity.get("directional_edge", 0.0)), 0.0)
    fill = max(min(float(opportunity.get("fill_probability", 0.0)), 1.0), 0.0)
    base_cap = min(
        config.max_stake_usd,
        config.bankroll_usd * config.max_position_fraction,
        remaining_total,
        remaining_event,
    )
    if base_cap <= 0:
        return 0.0
    edge_multiplier = min(edge / max(config.min_liquidity_adjusted_edge, 1e-9), 2.0) / 2.0
    directional_multiplier = min(directional_edge / max(config.min_directional_edge, 1e-9), 2.0) / 2.0
    stake = base_cap * min(edge_multiplier, directional_multiplier) * fill
    return float(round(max(stake, 0.0), 2))


def settle_paper_intents(
    intents: Sequence[Mapping[str, Any]],
    *,
    resolved_rows: Sequence[Mapping[str, Any]] = (),
    outcomes: Optional[Mapping[str, int]] = None,
    settled_ts: Optional[float] = None,
) -> List[Dict[str, Any]]:
    outcome_by_market: Dict[str, int] = {}
    for row in resolved_rows:
        market_id = str(row.get("market_id") or "")
        if market_id and "outcome" in row:
            outcome_by_market[market_id] = int(row.get("outcome", 0))
    if outcomes:
        outcome_by_market.update({str(k): int(v) for k, v in outcomes.items()})

    settled: List[Dict[str, Any]] = []
    ts = float(settled_ts or time.time())
    for intent in intents:
        market_id = str(intent.get("market_id") or "")
        if market_id not in outcome_by_market:
            continue
        outcome_yes = int(outcome_by_market[market_id])
        side = str(intent.get("side", "YES")).upper()
        side_outcome = outcome_yes if side == "YES" else 1 - outcome_yes
        entry_price = float(intent.get("entry_price", 0.5))
        contracts = float(intent.get("contracts", 0.0))
        pnl_usd = contracts * (float(side_outcome) - entry_price)
        settled.append(
            {
                **dict(intent),
                "status": "SETTLED",
                "settled_ts": ts,
                "outcome_yes": outcome_yes,
                "side_outcome": side_outcome,
                "pnl_usd": float(round(pnl_usd, 4)),
                "return_on_stake": float(round(pnl_usd / max(float(intent.get("stake_usd", 0.0)), 1e-9), 6)),
            }
        )
    return settled


def run_kalshi_research_cycle(
    store: PointInTimeStore,
    *,
    app_config: Optional[Config] = None,
    config: Optional[KalshiResearchCycleConfig] = None,
    rows: Optional[Sequence[Mapping[str, Any]]] = None,
    rank_report: Optional[Mapping[str, Any]] = None,
    outcomes: Optional[Mapping[str, int]] = None,
    reports_dir: Optional[Path] = None,
) -> KalshiResearchCycleArtifacts:
    app_config = app_config or load_config()
    cycle_config = config or KalshiResearchCycleConfig()
    out_dir = reports_dir or (store.research_dir / "reports")
    live_rank_artifacts: Optional[KalshiLiveRankArtifacts] = None

    if rank_report is None:
        live_rank_artifacts = run_kalshi_live_rank(
            store,
            app_config=app_config,
            config=cycle_config.live_rank,
            rows=rows,
            reports_dir=out_dir,
        )
        rank_payload = live_rank_artifacts.report
    else:
        rank_payload = dict(rank_report)

    existing_open_intents = store.load_kalshi_paper_intents(status="PAPER_INTENDED")
    paper_intents, paper_blocked = build_paper_intents(
        rank_payload,
        config=cycle_config.paper,
        existing_intents=existing_open_intents,
    )
    if paper_intents:
        store.write_kalshi_paper_intents(paper_intents)

    settled: List[Dict[str, Any]] = []
    if cycle_config.paper.settle_existing:
        open_intents = store.load_kalshi_paper_intents(status="PAPER_INTENDED")
        resolved_rows = store.load_kalshi_resolved_rows()
        settled = settle_paper_intents(
            open_intents,
            resolved_rows=resolved_rows,
            outcomes=outcomes,
        )
        if settled:
            store.write_kalshi_paper_intents(settled)

    ledger = store.load_kalshi_paper_intents()
    report = build_cycle_report(
        rank_payload,
        paper_intents=paper_intents,
        paper_blocked=paper_blocked,
        settled=settled,
        ledger=ledger,
        config=cycle_config,
        live_rank_artifacts=live_rank_artifacts,
    )
    artifacts = write_cycle_report(report, reports_dir=out_dir)
    artifacts.live_rank_artifacts = live_rank_artifacts
    return artifacts


def build_cycle_report(
    rank_report: Mapping[str, Any],
    *,
    paper_intents: Sequence[Mapping[str, Any]],
    paper_blocked: Sequence[Mapping[str, Any]],
    settled: Sequence[Mapping[str, Any]],
    ledger: Sequence[Mapping[str, Any]],
    config: KalshiResearchCycleConfig,
    live_rank_artifacts: Optional[KalshiLiveRankArtifacts] = None,
) -> Dict[str, Any]:
    ledger_summary = summarize_paper_ledger(ledger)
    return {
        "run_id": stable_cycle_run_id(rank_report, paper_intents, config),
        "created_ts": time.time(),
        "research_only": True,
        "execution_enabled": False,
        "cycle_config": {
            "live_rank": asdict(config.live_rank),
            "paper": asdict(config.paper),
        },
        "live_rank_ref": {
            "run_id": rank_report.get("run_id"),
            "json_path": str(live_rank_artifacts.json_path) if live_rank_artifacts else None,
            "markdown_path": str(live_rank_artifacts.markdown_path) if live_rank_artifacts else None,
        },
        "ranked": {
            "markets_ranked": rank_report.get("input_summary", {}).get("n_rows", 0),
            "top_opportunities": len(rank_report.get("top_opportunities", [])),
            "research_only_pass": sum(
                1
                for item in rank_report.get("top_opportunities", [])
                if item.get("candidate_status") == "RESEARCH_ONLY_PASS"
            ),
            "blocked": sum(
                1
                for item in rank_report.get("top_opportunities", [])
                if item.get("candidate_status") != "RESEARCH_ONLY_PASS"
            ),
            "watchlist": sum(
                1
                for item in rank_report.get("top_opportunities", [])
                if item.get("scoring_mode") == "watchlist_vulnerability"
            ),
        },
        "paper": {
            "intended_count": len(paper_intents),
            "blocked_count": len(paper_blocked),
            "total_stake_usd": round(sum(float(item.get("stake_usd", 0.0)) for item in paper_intents), 2),
            "intents": list(paper_intents),
            "blocked": list(paper_blocked),
        },
        "settlement": {
            "settled_count": len(settled),
            "pnl_usd": round(sum(float(item.get("pnl_usd", 0.0)) for item in settled), 4),
            "settled": list(settled),
        },
        "ledger": {
            "count": len(ledger),
            **ledger_summary,
        },
        "promotion_readiness": paper_promotion_readiness(ledger_summary, config.paper),
    }


def summarize_paper_ledger(ledger: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    status_counts: Dict[str, int] = {}
    event_exposure: Dict[str, float] = {}
    settled = []
    open_stake = 0.0
    total_stake = 0.0
    total_expected_value = 0.0

    for item in ledger:
        status = str(item.get("status", "UNKNOWN"))
        status_counts[status] = status_counts.get(status, 0) + 1
        stake = float(item.get("stake_usd", 0.0))
        total_stake += stake
        total_expected_value += float(item.get("expected_value_usd", 0.0))
        event_id = str(item.get("event_id") or item.get("market_id") or "unknown")
        if status == "PAPER_INTENDED":
            open_stake += stake
            event_exposure[event_id] = event_exposure.get(event_id, 0.0) + stake
        if status == "SETTLED":
            settled.append(item)

    pnl = sum(float(item.get("pnl_usd", 0.0)) for item in settled)
    wins = sum(1 for item in settled if float(item.get("pnl_usd", 0.0)) > 0)
    brier_values = []
    for item in settled:
        if "side_outcome" not in item:
            continue
        p = float(item.get("side_probability", item.get("model_probability", 0.5)))
        outcome = float(item.get("side_outcome", 0.0))
        brier_values.append((p - outcome) ** 2)

    return {
        "status_counts": dict(sorted(status_counts.items())),
        "total_stake_usd": round(total_stake, 2),
        "open_stake_usd": round(open_stake, 2),
        "settled_stake_usd": round(sum(float(item.get("stake_usd", 0.0)) for item in settled), 2),
        "settled_pnl_usd": round(pnl, 4),
        "settled_expected_value_usd": round(
            sum(float(item.get("expected_value_usd", 0.0)) for item in settled),
            4,
        ),
        "total_expected_value_usd": round(total_expected_value, 4),
        "settled_count": len(settled),
        "win_rate": round(wins / len(settled), 6) if settled else None,
        "brier_score": round(sum(brier_values) / len(brier_values), 6) if brier_values else None,
        "open_event_exposure_usd": dict(
            sorted(
                ((event_id, round(value, 2)) for event_id, value in event_exposure.items()),
                key=lambda item: (-item[1], item[0]),
            )
        ),
    }


def paper_promotion_readiness(
    ledger_summary: Mapping[str, Any],
    config: KalshiPaperConfig,
) -> Dict[str, Any]:
    reasons = []
    settled_count = int(ledger_summary.get("settled_count", 0) or 0)
    brier = ledger_summary.get("brier_score")
    win_rate = ledger_summary.get("win_rate")
    pnl = float(ledger_summary.get("settled_pnl_usd", 0.0) or 0.0)

    if settled_count < config.min_settled_for_promotion_review:
        reasons.append("insufficient_settled_sample")
    if brier is None:
        reasons.append("missing_brier_score")
    elif float(brier) > config.max_brier_for_promotion_review:
        reasons.append("brier_score_above_threshold")
    if win_rate is None:
        reasons.append("missing_win_rate")
    elif float(win_rate) < config.min_win_rate_for_promotion_review:
        reasons.append("win_rate_below_threshold")
    if pnl < config.min_pnl_for_promotion_review:
        reasons.append("settled_pnl_below_threshold")

    return {
        "status": "REVIEW_READY" if not reasons else "INSUFFICIENT_EVIDENCE",
        "reasons": reasons,
        "thresholds": {
            "min_settled": config.min_settled_for_promotion_review,
            "max_brier": config.max_brier_for_promotion_review,
            "min_win_rate": config.min_win_rate_for_promotion_review,
            "min_pnl_usd": config.min_pnl_for_promotion_review,
        },
        "observed": {
            "settled_count": settled_count,
            "brier_score": brier,
            "win_rate": win_rate,
            "settled_pnl_usd": pnl,
        },
    }


def write_cycle_report(
    report: Mapping[str, Any],
    *,
    reports_dir: Path,
) -> KalshiResearchCycleArtifacts:
    reports_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(report.get("run_id") or f"kalshi-cycle-{int(time.time())}")
    json_path = reports_dir / f"{run_id}.json"
    markdown_path = reports_dir / f"{run_id}.md"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True, default=str)
    with markdown_path.open("w", encoding="utf-8") as f:
        f.write(render_cycle_markdown(report))
    return KalshiResearchCycleArtifacts(dict(report), json_path, markdown_path)


def load_rank_report(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError("rank report must be a JSON object")
    if "top_opportunities" not in payload:
        raise ValueError("rank report is missing top_opportunities")
    return payload


def load_outcomes(path: Path) -> Dict[str, int]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    outcomes: Dict[str, int] = {}
    if isinstance(payload, dict):
        source = payload.get("outcomes", payload)
        if isinstance(source, dict):
            for market_id, outcome in source.items():
                outcomes[str(market_id)] = int(outcome)
        elif isinstance(source, list):
            outcomes.update(_outcomes_from_rows(source))
        else:
            raise ValueError("outcomes JSON object must contain a dict or list")
    elif isinstance(payload, list):
        outcomes.update(_outcomes_from_rows(payload))
    else:
        raise ValueError("outcomes JSON must be an object or list")
    for market_id, outcome in outcomes.items():
        if outcome not in {0, 1}:
            raise ValueError(f"outcome for {market_id} must be 0 or 1")
    return outcomes


def _outcomes_from_rows(rows: Sequence[Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        market_id = str(row.get("market_id") or row.get("ticker") or "")
        if not market_id or "outcome" not in row:
            continue
        out[market_id] = int(row.get("outcome", 0))
    return out


def render_cycle_markdown(report: Mapping[str, Any]) -> str:
    ranked = report.get("ranked", {})
    paper = report.get("paper", {})
    settlement = report.get("settlement", {})
    ledger = report.get("ledger", {})
    readiness = report.get("promotion_readiness", {})
    lines = [
        f"# Kalshi Research Cycle: {report.get('run_id', '')}",
        "",
        "## Scope",
        "",
        "- Mode: research-only",
        "- Execution enabled: false",
        f"- Live rank run: {report.get('live_rank_ref', {}).get('run_id')}",
        "",
        "## Rank Summary",
        "",
        f"- Markets ranked: {ranked.get('markets_ranked', 0)}",
        f"- Top opportunities: {ranked.get('top_opportunities', 0)}",
        f"- Passed / blocked / watchlist: {ranked.get('research_only_pass', 0)} / {ranked.get('blocked', 0)} / {ranked.get('watchlist', 0)}",
        "",
        "## Paper Intents",
        "",
        f"- Intended: {paper.get('intended_count', 0)}",
        f"- Blocked: {paper.get('blocked_count', 0)}",
        f"- Total stake: ${float(paper.get('total_stake_usd', 0.0)):.2f}",
        "",
    ]
    for idx, intent in enumerate(paper.get("intents", []), start=1):
        lines.extend(
            [
                f"### {idx}. {intent.get('market_id', '')}",
                "",
                str(intent.get("title", "")),
                "",
                f"- Side: {intent.get('side', '')}",
                f"- Stake: ${float(intent.get('stake_usd', 0.0)):.2f}",
                f"- Entry/model: {float(intent.get('entry_price', 0.0)):.2%} / {float(intent.get('side_probability', 0.0)):.2%}",
                f"- Expected value: ${float(intent.get('expected_value_usd', 0.0)):.2f}",
                "",
            ]
        )
    lines.extend(
        [
            "## Settlement",
            "",
            f"- Settled: {settlement.get('settled_count', 0)}",
            f"- PnL: ${float(settlement.get('pnl_usd', 0.0)):.2f}",
            "",
            "## Ledger Audit",
            "",
            f"- Ledger count: {ledger.get('count', 0)}",
            f"- Open stake: ${float(ledger.get('open_stake_usd', 0.0)):.2f}",
            f"- Settled PnL: ${float(ledger.get('settled_pnl_usd', 0.0)):.2f}",
            f"- Win rate: {ledger.get('win_rate')}",
            f"- Brier score: {ledger.get('brier_score')}",
            f"- Open event exposure: {ledger.get('open_event_exposure_usd', {})}",
            "",
            "## Promotion Readiness",
            "",
            f"- Status: {readiness.get('status', '')}",
            f"- Reasons: {readiness.get('reasons', [])}",
            f"- Observed: {readiness.get('observed', {})}",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def stable_paper_intent_id(opportunity: Mapping[str, Any], rank_run_id: str, created_ts: float) -> str:
    payload = {
        "market_id": opportunity.get("market_id"),
        "side": opportunity.get("side"),
        "rank_run_id": rank_run_id,
        "created_ts": created_ts,
    }
    return "kalshi-paper-" + _stable_hash(payload)[:20]


def stable_cycle_run_id(
    rank_report: Mapping[str, Any],
    paper_intents: Sequence[Mapping[str, Any]],
    config: KalshiResearchCycleConfig,
) -> str:
    payload = {
        "rank_run_id": rank_report.get("run_id"),
        "intents": [intent.get("intent_id") for intent in paper_intents],
        "config": {
            "live_rank": asdict(config.live_rank),
            "paper": asdict(config.paper),
        },
    }
    return "kalshi-cycle-" + _stable_hash(payload)[:16]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the closed-loop Kalshi research cycle")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--series-ticker", default=None)
    parser.add_argument("--status", default="open")
    parser.add_argument("--orderbooks", action="store_true", help="Attempt per-market orderbook enrichment")
    parser.add_argument("--candles", action="store_true", help="Attempt per-market candlestick enrichment")
    parser.add_argument("--top-k", type=int, default=25)
    parser.add_argument("--bankroll-usd", type=float, default=10_000.0)
    parser.add_argument("--max-intents", type=int, default=10)
    parser.add_argument("--max-stake-usd", type=float, default=25.0)
    parser.add_argument("--max-total-stake-usd", type=float, default=100.0)
    parser.add_argument("--max-event-stake-usd", type=float, default=50.0)
    parser.add_argument("--min-liquidity-adjusted-edge", type=float, default=0.02)
    parser.add_argument("--min-directional-edge", type=float, default=0.03)
    parser.add_argument("--no-settle-existing", action="store_true")
    parser.add_argument("--rank-report", default=None, help="Replay from a saved live rank JSON report instead of fetching live")
    parser.add_argument("--outcomes-json", default=None, help="Optional market_id -> outcome JSON for paper settlement")
    parser.add_argument("--discovery-report", default=None)
    parser.add_argument("--reports-dir", default=None)
    args = parser.parse_args(argv)

    app_config = load_config()
    store = PointInTimeStore(app_config.global_cfg.data_dir)
    try:
        live_rank_config = KalshiLiveRankConfig(
            limit=args.limit,
            max_pages=args.max_pages,
            series_ticker=args.series_ticker,
            status=args.status,
            fetch_orderbooks=args.orderbooks,
            fetch_candles=args.candles,
            top_k=args.top_k,
            discovery_report_path=Path(args.discovery_report) if args.discovery_report else None,
        )
        paper_config = KalshiPaperConfig(
            bankroll_usd=args.bankroll_usd,
            max_intents=args.max_intents,
            max_stake_usd=args.max_stake_usd,
            max_total_stake_usd=args.max_total_stake_usd,
            max_event_stake_usd=args.max_event_stake_usd,
            min_liquidity_adjusted_edge=args.min_liquidity_adjusted_edge,
            min_directional_edge=args.min_directional_edge,
            settle_existing=not args.no_settle_existing,
        )
        artifacts = run_kalshi_research_cycle(
            store,
            app_config=app_config,
            config=KalshiResearchCycleConfig(live_rank=live_rank_config, paper=paper_config),
            rank_report=load_rank_report(Path(args.rank_report)) if args.rank_report else None,
            outcomes=load_outcomes(Path(args.outcomes_json)) if args.outcomes_json else None,
            reports_dir=Path(args.reports_dir) if args.reports_dir else None,
        )
    finally:
        store.close()

    print(
        json.dumps(
            {
                "run_id": artifacts.report["run_id"],
                "markets_ranked": artifacts.report["ranked"]["markets_ranked"],
                "paper_intents": artifacts.report["paper"]["intended_count"],
                "paper_blocked": artifacts.report["paper"]["blocked_count"],
                "settled": artifacts.report["settlement"]["settled_count"],
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
