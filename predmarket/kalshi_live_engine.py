"""Live-autonomous Kalshi eligibility, risk, ledger, and trade-loop helpers."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from predmarket.config import Config, load_config
from predmarket.kalshi_execution_cost import (
    GENERAL_MAKER_FEE_RATE,
    kalshi_net_fee,
    kalshi_trade_fee,
)
from predmarket.kalshi_live_client import (
    KalshiAPIError,
    KalshiTradingClient,
    stable_client_order_id,
)
from predmarket.shared_helpers import (
    iso_from_timestamp,
    optional_float,
    price_probability,
    read_json_or_empty,
    timestamp,
    utc_now,
)

TERMINAL_ORDER_STATUSES = {
    "canceled",
    "cancelled",
    "executed",
    "failed",
    "filled",
    "rejected",
}
ARMING_ENV = "KALSHI_LIVE_TRADING_ENABLED"
PRODUCTION_CONFIRM_ENV = "KALSHI_CONFIRM_PRODUCTION_LIVE"
PRODUCTION_CONFIRM_VALUE = "I_UNDERSTAND_KALSHI_LIVE_RISK"
INTERNAL_CONTROL_SOURCE_REPO_ID = "predmarket-alpha"


@dataclass(frozen=True, slots=True)
class LiveRiskLimits:
    execution_strategy: str = "maker_first"
    max_open_exposure_usd: float = 250.0
    max_per_contract_usd: float = 25.0
    max_per_family_usd: float = 100.0
    max_per_cluster_usd: float = 50.0
    max_daily_gross_buy_usd: float = 100.0
    max_daily_loss_usd: float = 50.0
    min_edge: float = 0.03
    no_new_entry_seconds: int = 300
    passive_order_ttl_seconds: int = 180
    passive_price_improvement: float = 0.01
    unreconciled_order_timeout_seconds: int = 60
    max_orders_per_run: int = 5

    @classmethod
    def from_config(cls, config: Config | None = None) -> LiveRiskLimits:
        cfg = config or load_config()
        live_cfg = getattr(cfg, "kalshi_live", None)
        return cls(
            execution_strategy=str(getattr(live_cfg, "execution_strategy", "maker_first")),
            max_open_exposure_usd=float(getattr(live_cfg, "max_open_exposure_usd", 250.0)),
            max_per_contract_usd=float(getattr(live_cfg, "max_per_contract_usd", 25.0)),
            max_per_family_usd=float(getattr(live_cfg, "max_per_family_usd", 100.0)),
            max_per_cluster_usd=float(getattr(live_cfg, "max_per_cluster_usd", 50.0)),
            max_daily_gross_buy_usd=float(getattr(live_cfg, "max_daily_gross_buy_usd", 100.0)),
            max_daily_loss_usd=float(getattr(live_cfg, "max_daily_loss_usd", 50.0)),
            min_edge=float(getattr(cfg.portfolio.kelly, "min_edge", 0.03)),
            no_new_entry_seconds=int(getattr(live_cfg, "no_new_entry_seconds", 300)),
            passive_order_ttl_seconds=int(getattr(live_cfg, "passive_order_ttl_seconds", 180)),
            passive_price_improvement=float(getattr(live_cfg, "passive_price_improvement", 0.01)),
            unreconciled_order_timeout_seconds=int(
                getattr(live_cfg, "unreconciled_order_timeout_seconds", 60)
            ),
            max_orders_per_run=int(getattr(live_cfg, "max_orders_per_run", 5)),
        )


@dataclass(frozen=True, slots=True)
class LiveArmingState:
    execution_mode: str
    armed: bool
    blockers: tuple[str, ...]
    production: bool


@dataclass(frozen=True, slots=True)
class LiveEligibleDecision:
    contract_ticker: str
    side: str
    source_repo_id: str
    family_id: str
    model_id: str
    signal_key: str
    signal_formula_key: str
    cluster_key: str
    close_time: str | None
    calibrated_probability: float | None
    market_probability: float | None
    all_in_cost: float | None
    expected_value_per_contract: float | None
    current_ask_price: float | None
    current_ask_size: float | None
    limit_price: float | None
    modeled_limit_price: float | None
    execution_strategy: str
    fee_mode: str
    taker_fee_estimate: float | None
    maker_fee_estimate: float | None
    maker_fee_savings: float | None
    time_in_force: str
    post_only: bool
    order_expiration_time: int | None
    order_count: int
    live_stake: float
    client_order_id: str | None
    live_eligible: bool
    blocker_list: tuple[str, ...]

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["blocker_list"] = list(self.blocker_list)
        row["execution_enabled"] = self.live_eligible
        row["market_execution"] = self.live_eligible
        row["research_only"] = not self.live_eligible
        row["paper_source_only"] = False
        return row


class LiveStateStore:
    """Small JSON state store for restart-safe order reconciliation."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.path = self.root / "kalshi-live-state.json"

    def load(self) -> dict[str, Any]:
        state = read_json_or_empty(self.path)
        return state if state else empty_live_state()

    def write(self, state: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def upsert(self, section: str, key_field: str, row: Mapping[str, Any]) -> None:
        state = self.load()
        rows = list_rows(state, section)
        key = str(row.get(key_field) or "")
        rows = [existing for existing in rows if str(existing.get(key_field) or "") != key]
        rows.append(dict(row))
        rows.sort(key=lambda item: (float(item.get("created_ts") or 0.0), str(item.get(key_field))))
        state[section] = rows
        self.write(state)

    def append_unique(self, section: str, key_field: str, row: Mapping[str, Any]) -> None:
        state = self.load()
        rows = list_rows(state, section)
        key = str(row.get(key_field) or "")
        if not any(str(existing.get(key_field) or "") == key for existing in rows):
            rows.append(dict(row))
        state[section] = rows
        self.write(state)


def empty_live_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "orders": [],
        "intents": [],
        "fills": [],
        "risk_snapshots": [],
        "kill_switch_events": [],
    }


def build_live_preflight_report(
    *,
    paper_decisions_path: Path,
    external_preflight_path: Path,
    retirement_path: Path,
    state_path: Path,
    market_snapshots: Mapping[str, Mapping[str, Any]] | None = None,
    account_balance_usd: float | None = None,
    execution_mode: str | None = None,
    generated_utc: str | None = None,
    config: Config | None = None,
) -> dict[str, Any]:
    cfg = config or load_config()
    state = LiveStateStore(state_path).load()
    return build_live_decision_report(
        paper_report=read_json_or_empty(paper_decisions_path),
        external_preflight=read_json_or_empty(external_preflight_path),
        retirement_ledger=read_json_or_empty(retirement_path),
        state=state,
        market_snapshots=market_snapshots or {},
        account_balance_usd=account_balance_usd,
        execution_mode=execution_mode or configured_execution_mode(cfg),
        generated_utc=generated_utc,
        config=cfg,
    )


def build_live_decision_report(
    *,
    paper_report: Mapping[str, Any],
    external_preflight: Mapping[str, Any],
    retirement_ledger: Mapping[str, Any],
    state: Mapping[str, Any],
    market_snapshots: Mapping[str, Mapping[str, Any]],
    account_balance_usd: float | None,
    execution_mode: str,
    generated_utc: str | None = None,
    config: Config | None = None,
) -> dict[str, Any]:
    cfg = config or load_config()
    generated = generated_utc or utc_now()
    limits = LiveRiskLimits.from_config(cfg)
    arming = live_arming_state(cfg, execution_mode)
    risk_snapshot = build_live_risk_snapshot(
        state=state,
        account_balance_usd=account_balance_usd,
        limits=limits,
        generated_utc=generated,
    )
    global_blockers = global_live_blockers(arming, risk_snapshot)
    safe_sources = safe_preflight_sources(external_preflight)
    retired = retired_signal_keys(retirement_ledger)
    candidates = (
        paper_report.get("candidates") if isinstance(paper_report.get("candidates"), list) else []
    )
    decisions = rank_decisions(
        [
            live_decision_from_candidate(
                candidate,
                market=market_snapshots.get(str(candidate.get("contract_ticker") or ""), {}),
                safe_sources=safe_sources,
                retired_signal_keys=retired,
                limits=limits,
                risk_snapshot=risk_snapshot,
                global_blockers=global_blockers,
                generated_utc=generated,
            )
            for candidate in candidates
            if isinstance(candidate, Mapping)
        ]
    )
    return live_report(
        generated_utc=generated,
        execution_mode=arming.execution_mode,
        armed=arming.armed,
        limits=limits,
        decisions=decisions,
        risk_snapshot=risk_snapshot,
        paper_report=paper_report,
        external_preflight=external_preflight,
    )


def live_decision_from_candidate(
    candidate: Mapping[str, Any],
    *,
    market: Mapping[str, Any],
    safe_sources: set[str],
    retired_signal_keys: set[str],
    limits: LiveRiskLimits,
    risk_snapshot: Mapping[str, Any],
    global_blockers: Sequence[str],
    generated_utc: str,
) -> LiveEligibleDecision:
    blockers = list(global_blockers)
    blockers.extend(candidate_live_blockers(candidate, safe_sources, retired_signal_keys))
    side = str(candidate.get("side") or "").lower()
    current_ask, current_size = side_ask(market, side)
    blockers.extend(
        market_live_blockers(candidate, market, current_ask, current_size, limits, generated_utc)
    )
    execution_plan = live_execution_plan(
        candidate=candidate,
        current_ask=current_ask,
        limits=limits,
        generated_utc=generated_utc,
    )
    blockers.extend(execution_plan["blockers"])
    order_price = execution_plan["limit_price"]
    modeled_limit_price = price_probability(candidate.get("all_in_cost"))
    order_count, stake, sizing_blockers = live_order_size(
        candidate=candidate,
        limit_price=order_price,
        current_ask=current_ask,
        limits=limits,
        risk_snapshot=risk_snapshot,
    )
    blockers.extend(sizing_blockers)
    client_order_id = None
    if not blockers and order_price is not None and order_count > 0:
        client_order_id = stable_client_order_id(
            candidate.get("signal_key"),
            candidate.get("contract_ticker"),
            side,
            order_price,
            order_count,
            candidate.get("close_time"),
        )
    return LiveEligibleDecision(
        contract_ticker=str(candidate.get("contract_ticker") or ""),
        side=side,
        source_repo_id=str(candidate.get("source_repo_id") or ""),
        family_id=str(candidate.get("family_id") or ""),
        model_id=str(candidate.get("model_id") or ""),
        signal_key=str(candidate.get("signal_key") or ""),
        signal_formula_key=str(candidate.get("signal_formula_key") or ""),
        cluster_key=str(candidate.get("cluster_key") or ""),
        close_time=str(candidate.get("close_time") or "") or None,
        calibrated_probability=price_probability(candidate.get("calibrated_probability")),
        market_probability=price_probability(candidate.get("market_probability")),
        all_in_cost=modeled_limit_price,
        expected_value_per_contract=optional_float(candidate.get("expected_value_per_contract")),
        current_ask_price=current_ask,
        current_ask_size=current_size,
        limit_price=order_price,
        modeled_limit_price=modeled_limit_price,
        execution_strategy=str(execution_plan["execution_strategy"]),
        fee_mode=str(execution_plan["fee_mode"]),
        taker_fee_estimate=execution_plan["taker_fee_estimate"],
        maker_fee_estimate=execution_plan["maker_fee_estimate"],
        maker_fee_savings=execution_plan["maker_fee_savings"],
        time_in_force=str(execution_plan["time_in_force"]),
        post_only=bool(execution_plan["post_only"]),
        order_expiration_time=execution_plan["order_expiration_time"],
        order_count=order_count if not blockers else 0,
        live_stake=round(stake if not blockers else 0.0, 6),
        client_order_id=client_order_id if not blockers else None,
        live_eligible=not blockers,
        blocker_list=tuple(dict.fromkeys(blockers)),
    )


def candidate_live_blockers(
    candidate: Mapping[str, Any], safe_sources: set[str], retired_signal_keys: set[str]
) -> list[str]:
    blockers: list[str] = []
    if candidate.get("paper_usable") is not True:
        blockers.append("paper candidate is not usable")
    if not str(candidate.get("contract_ticker") or ""):
        blockers.append("exact Kalshi contract ticker missing")
    if str(candidate.get("side") or "").lower() not in {"yes", "no"}:
        blockers.append("side must be yes or no")
    source_repo_id = str(candidate.get("source_repo_id") or "")
    if not source_repo_id:
        blockers.append("source repo provenance missing")
    elif not source_repo_is_live_safe(source_repo_id, safe_sources):
        blockers.append("source repo artifact did not pass external preflight")
    if not str(candidate.get("signal_key") or ""):
        blockers.append("signal key missing")
    if not str(candidate.get("cluster_key") or ""):
        blockers.append("correlation cluster key missing")
    if str(candidate.get("signal_key") or "") in retired_signal_keys:
        blockers.append("signal is retired")
    edge = optional_float(candidate.get("expected_value_per_contract"))
    if edge is None or edge <= 0:
        blockers.append("expected value missing or non-positive")
    return blockers


def market_live_blockers(
    candidate: Mapping[str, Any],
    market: Mapping[str, Any],
    current_ask: float | None,
    current_size: float | None,
    limits: LiveRiskLimits,
    generated_utc: str,
) -> list[str]:
    blockers: list[str] = []
    if not market:
        return ["current market snapshot missing"]
    if market_is_closed_or_paused(market):
        blockers.append("market is not currently open and tradable")
    close_ts = timestamp(candidate.get("close_time") or market.get("close_time"))
    now_ts = timestamp(generated_utc) or time.time()
    if close_ts is not None and close_ts - now_ts <= limits.no_new_entry_seconds:
        blockers.append("market is inside no-new-entry buffer")
    limit_price = price_probability(candidate.get("all_in_cost"))
    if current_ask is None:
        blockers.append("current side ask price missing")
    elif (
        execution_strategy_is_taker(limits.execution_strategy)
        and limit_price is not None
        and current_ask > limit_price + 1e-9
    ):
        blockers.append("current side ask exceeds modeled limit price")
    if current_size is None or current_size <= 0:
        blockers.append("current side ask size missing")
    return blockers


def live_execution_plan(
    *,
    candidate: Mapping[str, Any],
    current_ask: float | None,
    limits: LiveRiskLimits,
    generated_utc: str,
) -> dict[str, Any]:
    modeled_limit = price_probability(candidate.get("all_in_cost"))
    strategy = normalize_execution_strategy(limits.execution_strategy)
    taker_fee = kalshi_trade_fee(price=modeled_limit) if modeled_limit is not None else None
    maker_fee = (
        kalshi_trade_fee(price=modeled_limit, fee_rate=GENERAL_MAKER_FEE_RATE)
        if modeled_limit is not None
        else None
    )
    fee_savings = (
        round(taker_fee - maker_fee, 10)
        if taker_fee is not None and maker_fee is not None
        else None
    )
    base = {
        "execution_strategy": strategy,
        "fee_mode": "maker",
        "taker_fee_estimate": taker_fee,
        "maker_fee_estimate": maker_fee,
        "maker_fee_savings": fee_savings,
        "time_in_force": "good_till_canceled",
        "post_only": True,
        "order_expiration_time": None,
        "limit_price": None,
        "blockers": [],
    }
    if modeled_limit is None:
        return {**base, "blockers": ["modeled limit price missing"]}
    if strategy == "maker_first":
        price = passive_order_price(
            modeled_limit=modeled_limit,
            current_ask=current_ask,
            passive_price_improvement=limits.passive_price_improvement,
        )
        expiration = passive_order_expiration(
            generated_utc=generated_utc,
            close_time=str(candidate.get("close_time") or ""),
            limits=limits,
        )
        blockers = []
        if price is None:
            blockers.append("passive post-only limit price is not safely below the current ask")
        if expiration is None:
            blockers.append("passive order expiration cannot be set before stale-entry buffer")
        return {
            **base,
            "limit_price": price,
            "order_expiration_time": expiration,
            "blockers": blockers,
        }
    if strategy == "taker_cross":
        return {
            **base,
            "fee_mode": "taker",
            "time_in_force": "immediate_or_cancel",
            "post_only": False,
            "limit_price": modeled_limit,
        }
    if strategy == "taker_if_decay_justifies":
        decay_rate = optional_float(
            candidate.get("edge_decay_probability_per_second")
            or candidate.get("edge_decay_per_second")
        )
        threshold = (
            fee_savings / max(float(limits.passive_order_ttl_seconds), 1.0)
            if fee_savings is not None
            else None
        )
        blockers = []
        if decay_rate is None:
            blockers.append("edge decay rate missing for taker-cross decision")
        elif threshold is not None and decay_rate < threshold:
            blockers.append("edge decay rate does not justify taker fee penalty")
        return {
            **base,
            "execution_strategy": strategy,
            "fee_mode": "taker" if not blockers else "maker",
            "time_in_force": "immediate_or_cancel" if not blockers else "good_till_canceled",
            "post_only": bool(blockers),
            "limit_price": modeled_limit if not blockers else None,
            "blockers": blockers,
        }
    return {**base, "blockers": [f"unsupported execution strategy: {strategy}"]}


def normalize_execution_strategy(value: str) -> str:
    strategy = str(value or "maker_first").strip().lower()
    aliases = {"maker": "maker_first", "passive": "maker_first", "cross": "taker_cross"}
    return aliases.get(strategy, strategy)


def execution_strategy_is_taker(value: str) -> bool:
    return normalize_execution_strategy(value) in {"taker_cross", "taker_if_decay_justifies"}


def passive_order_price(
    *,
    modeled_limit: float,
    current_ask: float | None,
    passive_price_improvement: float,
) -> float | None:
    if current_ask is None:
        return None
    improvement = max(0.0001, float(passive_price_improvement or 0.0))
    price = min(float(modeled_limit), float(current_ask) - improvement)
    if price <= 0.0 or price >= 1.0:
        return None
    return round(price, 4)


def passive_order_expiration(
    *,
    generated_utc: str,
    close_time: str,
    limits: LiveRiskLimits,
) -> int | None:
    now_ts = timestamp(generated_utc) or time.time()
    expiration = now_ts + max(float(limits.passive_order_ttl_seconds), 1.0)
    close_ts = timestamp(close_time)
    if close_ts is not None:
        expiration = min(expiration, close_ts - float(limits.no_new_entry_seconds))
    if expiration <= now_ts:
        return None
    return int(expiration)


def live_order_size(
    *,
    candidate: Mapping[str, Any],
    limit_price: float | None,
    current_ask: float | None,
    limits: LiveRiskLimits,
    risk_snapshot: Mapping[str, Any],
) -> tuple[int, float, list[str]]:
    blockers: list[str] = []
    edge = optional_float(candidate.get("expected_value_per_contract"))
    # Compute price-dependent minimum edge from canonical fee engine
    market_prob = price_probability(candidate.get("market_probability"))
    fee_mode = str(candidate.get("fee_mode", "maker")).lower().strip()
    effective_min_edge = (
        kalshi_net_fee(price=market_prob, contract_count=1.0, fee_mode=fee_mode)
        if market_prob is not None
        else limits.min_edge
    )
    if edge is None or edge < effective_min_edge:
        blockers.append("edge below live minimum")
    if limit_price is None or not (0.0 < limit_price < 1.0):
        blockers.append("limit price missing or invalid")
    if current_ask is None or current_ask <= 0:
        blockers.append("current ask missing for sizing")
    if blockers:
        return 0, 0.0, blockers
    if risk_snapshot.get("account_balance_usd") is None:
        return 0, 0.0, blockers
    price = float(limit_price)
    cap = live_remaining_cap(candidate, limits, risk_snapshot)
    requested = min(float(candidate.get("paper_stake") or 0.0), cap)
    count = math.floor(requested / price)
    stake = count * price
    if count < 1:
        blockers.append("live stake rounds down below one contract")
    return int(count), float(stake), blockers


def live_remaining_cap(
    candidate: Mapping[str, Any], limits: LiveRiskLimits, risk_snapshot: Mapping[str, Any]
) -> float:
    by_family = as_float_map(risk_snapshot.get("open_exposure_by_family"))
    by_cluster = as_float_map(risk_snapshot.get("open_exposure_by_cluster"))
    by_contract = as_float_map(risk_snapshot.get("open_exposure_by_contract"))
    family = str(candidate.get("family_id") or "")
    cluster = str(candidate.get("cluster_key") or "")
    contract = str(candidate.get("contract_ticker") or "")
    caps = [
        limits.max_open_exposure_usd - float(risk_snapshot.get("open_exposure_usd") or 0.0),
        limits.max_daily_gross_buy_usd - float(risk_snapshot.get("daily_gross_buy_usd") or 0.0),
        limits.max_per_family_usd - by_family.get(family, 0.0),
        limits.max_per_cluster_usd - by_cluster.get(cluster, 0.0),
        limits.max_per_contract_usd - by_contract.get(contract, 0.0),
        float(risk_snapshot.get("account_balance_usd") or 0.0),
    ]
    return max(0.0, min(caps))


def build_live_risk_snapshot(
    *,
    state: Mapping[str, Any],
    account_balance_usd: float | None,
    limits: LiveRiskLimits,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    now_ts = timestamp(generated) or time.time()
    open_orders = [row for row in list_rows(state, "orders") if not order_is_terminal(row)]
    exposures = exposure_maps(open_orders)
    daily_gross = daily_gross_buy_notional(list_rows(state, "orders"), now_ts)
    stale_orders = stale_unreconciled_orders(
        open_orders, now_ts, limits.unreconciled_order_timeout_seconds
    )
    daily_loss = float(state.get("daily_loss_usd") or 0.0)
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "account_balance_usd": account_balance_usd,
        "open_order_count": len(open_orders),
        "stale_unreconciled_order_count": len(stale_orders),
        "stale_unreconciled_client_order_ids": [
            str(row.get("client_order_id") or "") for row in stale_orders
        ],
        "open_exposure_usd": round(sum(exposures["contract"].values()), 6),
        "open_exposure_by_contract": round_map(exposures["contract"]),
        "open_exposure_by_family": round_map(exposures["family"]),
        "open_exposure_by_cluster": round_map(exposures["cluster"]),
        "daily_gross_buy_usd": round(daily_gross, 6),
        "daily_loss_usd": round(daily_loss, 6),
        "limits": asdict(limits),
        "kill_switch_reasons": risk_kill_switches(
            daily_loss, daily_gross, exposures, stale_orders, limits
        ),
    }


def risk_kill_switches(
    daily_loss: float,
    daily_gross: float,
    exposures: Mapping[str, Mapping[str, float]],
    stale_orders: Sequence[Mapping[str, Any]],
    limits: LiveRiskLimits,
) -> list[str]:
    reasons: list[str] = []
    if stale_orders:
        reasons.append("unreconciled live order timeout")
    if sum(exposures["contract"].values()) > limits.max_open_exposure_usd:
        reasons.append("max open exposure breached")
    if daily_gross > limits.max_daily_gross_buy_usd:
        reasons.append("max daily gross buy breached")
    if daily_loss > limits.max_daily_loss_usd:
        reasons.append("max daily loss breached")
    return reasons


def run_live_trader_once(
    *,
    client: KalshiTradingClient,
    state_store: LiveStateStore,
    paper_decisions_path: Path,
    external_preflight_path: Path,
    retirement_path: Path,
    execution_mode: str,
    dry_run: bool = False,
    config: Config | None = None,
) -> dict[str, Any]:
    cfg = config or load_config()
    state = state_store.load()
    reconciled = reconcile_live_orders(client=client, state_store=state_store, state=state)
    state = state_store.load()
    account_balance = account_balance_from_payload(client.get_balance())
    paper_report = read_json_or_empty(paper_decisions_path)
    market_snapshots = fetch_candidate_markets(client, paper_report)
    report = build_live_decision_report(
        paper_report=paper_report,
        external_preflight=read_json_or_empty(external_preflight_path),
        retirement_ledger=read_json_or_empty(retirement_path),
        state=state,
        market_snapshots=market_snapshots,
        account_balance_usd=account_balance,
        execution_mode=execution_mode,
        config=cfg,
    )
    submitted = submit_live_orders(
        client=client,
        state_store=state_store,
        report=report,
        dry_run=dry_run,
    )
    report["reconciliation"] = reconciled
    report["submitted_orders"] = submitted
    return report


def submit_live_orders(
    *,
    client: KalshiTradingClient,
    state_store: LiveStateStore,
    report: Mapping[str, Any],
    dry_run: bool,
) -> list[dict[str, Any]]:
    if dry_run or report.get("armed") is not True:
        return []
    submitted: list[dict[str, Any]] = []
    for decision in eligible_decision_rows(report)[: int(report["limits"]["max_orders_per_run"])]:
        intent = live_order_intent(decision)
        state_store.upsert("intents", "intent_id", intent)
        try:
            response = client.create_order(
                ticker=str(decision["contract_ticker"]),
                outcome_side=str(decision["side"]),
                count=float(decision["order_count"]),
                price=float(decision["limit_price"]),
                client_order_id=str(decision["client_order_id"]),
                time_in_force=str(decision.get("time_in_force") or "good_till_canceled"),
                post_only=bool(decision.get("post_only")),
                expiration_time=optional_int(decision.get("order_expiration_time")),
            )
        except KalshiAPIError as exc:
            kill = kill_switch_event("kalshi_api_error", str(exc), intent)
            state_store.append_unique("kill_switch_events", "event_id", kill)
            submitted.append({"status": "blocked_after_api_error", "error": str(exc)})
            break
        order = live_order_record(decision, response)
        state_store.upsert("orders", "client_order_id", order)
        maybe_record_fill(state_store, decision, response)
        submitted.append(order)
    return submitted


def reconcile_live_orders(
    *,
    client: KalshiTradingClient,
    state_store: LiveStateStore,
    state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    current_state = state or state_store.load()
    open_orders = [row for row in list_rows(current_state, "orders") if not order_is_terminal(row)]
    updated: list[dict[str, Any]] = []
    for order in open_orders:
        exchange_id = str(order.get("exchange_order_id") or "")
        if not exchange_id:
            continue
        try:
            payload = client.get_order(exchange_id)
        except KalshiAPIError as exc:
            kill = kill_switch_event("kalshi_api_error", str(exc), order)
            state_store.append_unique("kill_switch_events", "event_id", kill)
            continue
        merged = reconcile_order_record(order, payload)
        state_store.upsert("orders", "client_order_id", merged)
        maybe_record_fill(state_store, merged, payload)
        updated.append(merged)
    return {
        "status": "live_reconcile_ready",
        "open_order_count": len(open_orders),
        "updated_order_count": len(updated),
        "updated_orders": updated,
    }


def live_report(
    *,
    generated_utc: str,
    execution_mode: str,
    armed: bool,
    limits: LiveRiskLimits,
    decisions: Sequence[LiveEligibleDecision],
    risk_snapshot: Mapping[str, Any],
    paper_report: Mapping[str, Any],
    external_preflight: Mapping[str, Any],
) -> dict[str, Any]:
    rows = [decision.to_row() for decision in decisions]
    eligible = [row for row in rows if row["live_eligible"]]
    return {
        "schema_version": 1,
        "generated_utc": generated_utc,
        "status": "kalshi_live_ready_with_eligible_orders" if eligible else "kalshi_live_blocked",
        "execution_mode": execution_mode,
        "armed": armed,
        "research_only": not armed,
        "execution_enabled": armed,
        "market_execution": armed,
        "limits": asdict(limits),
        "summary": {
            "paper_candidate_count": paper_report.get("summary", {}).get("candidate_count"),
            "live_decision_count": len(rows),
            "live_eligible_count": len(eligible),
            "blocked_decision_count": len(rows) - len(eligible),
            "total_live_stake": round(sum(float(row["live_stake"]) for row in eligible), 6),
            "maker_first_decision_count": sum(
                1 for row in rows if row.get("execution_strategy") == "maker_first"
            ),
            "post_only_decision_count": sum(1 for row in rows if row.get("post_only") is True),
            "external_safe_artifact_count": external_preflight.get("summary", {}).get(
                "safe_artifact_count"
            ),
        },
        "risk_snapshot": dict(risk_snapshot),
        "decisions": rows,
        "safety": {
            "production_requires_env_arm": True,
            "manual_approval_queue": False,
            "market_orders": False,
            "buy_only_initial_tranche": True,
            "default_execution_strategy": limits.execution_strategy,
            "post_only_default": normalize_execution_strategy(limits.execution_strategy)
            == "maker_first",
            "kill_switch_halts_new_buys": True,
        },
    }


def live_arming_state(config: Config, execution_mode: str | None = None) -> LiveArmingState:
    mode = (execution_mode or configured_execution_mode(config)).strip().lower()
    blockers: list[str] = []
    if mode not in {"disabled", "demo", "live"}:
        blockers.append("invalid execution mode")
    if mode == "disabled":
        blockers.append("live execution mode is disabled")
    if config.venues.kalshi.execution_enabled is not True:
        blockers.append("config venues.kalshi.execution_enabled is false")
    if os.getenv(ARMING_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}:
        blockers.append(f"{ARMING_ENV} is not armed")
    if mode == "live" and os.getenv(PRODUCTION_CONFIRM_ENV) != PRODUCTION_CONFIRM_VALUE:
        blockers.append(f"{PRODUCTION_CONFIRM_ENV} production confirmation missing")
    if mode == "demo" and config.venues.kalshi.use_demo is not True:
        blockers.append("demo mode requires venues.kalshi.use_demo=true")
    return LiveArmingState(
        execution_mode=mode,
        armed=not blockers,
        blockers=tuple(blockers),
        production=mode == "live",
    )


def configured_execution_mode(config: Config) -> str:
    live_cfg = getattr(config, "kalshi_live", None)
    env_mode = os.getenv("KALSHI_LIVE_EXECUTION_MODE")
    return str(env_mode or getattr(live_cfg, "execution_mode", "disabled"))


def global_live_blockers(arming: LiveArmingState, risk_snapshot: Mapping[str, Any]) -> list[str]:
    blockers = list(arming.blockers)
    blockers.extend(str(item) for item in risk_snapshot.get("kill_switch_reasons") or [])
    if risk_snapshot.get("account_balance_usd") is None:
        blockers.append("account balance missing")
    return blockers


def safe_preflight_sources(report: Mapping[str, Any]) -> set[str]:
    rows = report.get("artifacts") if isinstance(report.get("artifacts"), list) else []
    return {
        str(row.get("source_repo_id") or "")
        for row in rows
        if isinstance(row, Mapping) and row.get("safe") is True
    }


def source_repo_is_live_safe(source_repo_id: str, safe_sources: set[str]) -> bool:
    """Return whether a candidate's source provenance is admissible for live preflight.

    External donor repos must pass the strict external-artifact bridge. The
    control repo's own generated evidence is not a donor artifact; it is
    admissible only under the canonical internal repo id and still has to pass
    every paper, market, arming, sizing, and risk gate downstream.
    """
    return source_repo_id == INTERNAL_CONTROL_SOURCE_REPO_ID or source_repo_id in safe_sources


def retired_signal_keys(report: Mapping[str, Any]) -> set[str]:
    rows = report.get("signals") if isinstance(report.get("signals"), list) else []
    return {
        str(row.get("signal_key") or "")
        for row in rows
        if isinstance(row, Mapping) and row.get("retirement_status") == "retired"
    }


def side_ask(market: Mapping[str, Any], side: str) -> tuple[float | None, float | None]:
    if not market:
        return None, None
    raw = market.get("market") if isinstance(market.get("market"), Mapping) else market
    prefix = "yes" if side == "yes" else "no" if side == "no" else ""
    if not prefix:
        return None, None
    ask = price_probability(raw.get(f"{prefix}_ask_dollars") or raw.get(f"{prefix}_ask"))
    size = optional_float(raw.get(f"{prefix}_ask_size_fp") or raw.get(f"{prefix}_ask_size"))
    return ask, size


def market_is_closed_or_paused(market: Mapping[str, Any]) -> bool:
    raw = market.get("market") if isinstance(market.get("market"), Mapping) else market
    status = str(raw.get("status") or raw.get("market_status") or "open").lower()
    trading_status = str(raw.get("trading_status") or "").lower()
    return (
        status in {"closed", "settled", "expired", "paused", "halted"}
        or trading_status in {"paused", "halted", "closed"}
        or raw.get("is_paused") is True
    )


def rank_decisions(decisions: Sequence[LiveEligibleDecision]) -> list[LiveEligibleDecision]:
    return sorted(
        decisions,
        key=lambda row: (
            not row.live_eligible,
            -(row.expected_value_per_contract or -999.0),
            row.contract_ticker,
        ),
    )


def eligible_decision_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("decisions") if isinstance(report.get("decisions"), list) else []
    return [dict(row) for row in rows if isinstance(row, Mapping) and row.get("live_eligible")]


def fetch_candidate_markets(
    client: KalshiTradingClient, paper_report: Mapping[str, Any]
) -> dict[str, Mapping[str, Any]]:
    tickers = paper_usable_tickers(paper_report)
    return {ticker: client.get_market(ticker) for ticker in sorted(tickers) if ticker}


def paper_usable_tickers(paper_report: Mapping[str, Any]) -> set[str]:
    candidates = (
        paper_report.get("candidates") if isinstance(paper_report.get("candidates"), list) else []
    )
    tickers: set[str] = set()
    for row in candidates:
        if not isinstance(row, Mapping) or row.get("paper_usable") is not True:
            continue
        ticker = str(row.get("contract_ticker") or "")
        if ticker:
            tickers.add(ticker)
    return tickers


def normalize_market_snapshot_index(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Index live-preflight market snapshots by exact Kalshi contract ticker."""
    direct = report.get("market_snapshots")
    if isinstance(direct, Mapping):
        return {
            str(ticker): dict(payload)
            for ticker, payload in direct.items()
            if str(ticker) and isinstance(payload, Mapping)
        }
    rows: list[Any] = []
    for key in ("markets", "snapshots"):
        value = report.get(key)
        if isinstance(value, list):
            rows.extend(value)
    if isinstance(report.get("market"), Mapping):
        rows.append(report)
    index: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), Mapping) else row
        market = payload.get("market") if isinstance(payload.get("market"), Mapping) else payload
        ticker = str(row.get("ticker") or market.get("ticker") or "")
        if ticker:
            index[ticker] = dict(payload)
    return index


def account_balance_from_payload(payload: Mapping[str, Any]) -> float | None:
    for key in ("balance", "portfolio_value", "available_balance", "cash_balance"):
        value = optional_float(payload.get(key))
        if value is not None:
            return value / 100.0 if value > 10_000 else value
    return None


def live_order_intent(decision: Mapping[str, Any]) -> dict[str, Any]:
    created_ts = time.time()
    payload = {
        "intent_id": stable_hash("intent", decision),
        "created_ts": created_ts,
        "created_utc": iso_from_timestamp(created_ts),
        "client_order_id": decision.get("client_order_id"),
        "contract_ticker": decision.get("contract_ticker"),
        "side": decision.get("side"),
        "family_id": decision.get("family_id"),
        "cluster_key": decision.get("cluster_key"),
        "limit_price": decision.get("limit_price"),
        "modeled_limit_price": decision.get("modeled_limit_price"),
        "execution_strategy": decision.get("execution_strategy"),
        "fee_mode": decision.get("fee_mode"),
        "time_in_force": decision.get("time_in_force"),
        "post_only": decision.get("post_only"),
        "order_expiration_time": decision.get("order_expiration_time"),
        "taker_fee_estimate": decision.get("taker_fee_estimate"),
        "maker_fee_estimate": decision.get("maker_fee_estimate"),
        "maker_fee_savings": decision.get("maker_fee_savings"),
        "order_count": decision.get("order_count"),
        "notional_usd": decision.get("live_stake"),
        "status": "INTENDED",
        "decision": dict(decision),
    }
    payload["payload_hash"] = stable_hash("payload", payload)
    return payload


def live_order_record(decision: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, Any]:
    created_ts = time.time()
    fill_count = optional_float(response.get("fill_count") or response.get("fill_count_fp")) or 0.0
    remaining = optional_float(
        response.get("remaining_count") or response.get("remaining_count_fp")
    )
    status = "FILLED" if remaining == 0 else "PARTIAL" if fill_count > 0 else "SUBMITTED"
    return {
        "created_ts": created_ts,
        "created_utc": iso_from_timestamp(created_ts),
        "client_order_id": decision.get("client_order_id"),
        "exchange_order_id": response.get("order_id"),
        "contract_ticker": decision.get("contract_ticker"),
        "side": decision.get("side"),
        "family_id": decision.get("family_id"),
        "cluster_key": decision.get("cluster_key"),
        "limit_price": decision.get("limit_price"),
        "modeled_limit_price": decision.get("modeled_limit_price"),
        "execution_strategy": decision.get("execution_strategy"),
        "fee_mode": decision.get("fee_mode"),
        "time_in_force": decision.get("time_in_force"),
        "post_only": decision.get("post_only"),
        "order_expiration_time": decision.get("order_expiration_time"),
        "taker_fee_estimate": decision.get("taker_fee_estimate"),
        "maker_fee_estimate": decision.get("maker_fee_estimate"),
        "maker_fee_savings": decision.get("maker_fee_savings"),
        "order_count": decision.get("order_count"),
        "notional_usd": decision.get("live_stake"),
        "fill_count": fill_count,
        "remaining_count": remaining,
        "status": status,
        "request_payload_hash": stable_hash("request", decision),
        "response_payload_hash": stable_hash("response", response),
        "response": dict(response),
    }


def reconcile_order_record(order: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    raw_order = payload.get("order") if isinstance(payload.get("order"), Mapping) else payload
    merged = dict(order)
    fill_count = (
        optional_float(raw_order.get("fill_count_fp") or raw_order.get("fill_count")) or 0.0
    )
    remaining = optional_float(
        raw_order.get("remaining_count_fp") or raw_order.get("remaining_count")
    )
    status = str(raw_order.get("status") or merged.get("status") or "").upper()
    if remaining == 0:
        status = "FILLED"
    elif status.lower() in TERMINAL_ORDER_STATUSES:
        status = status.upper()
    elif fill_count > 0:
        status = "PARTIAL"
    merged.update(
        {
            "last_reconciled_ts": time.time(),
            "fill_count": fill_count,
            "remaining_count": remaining,
            "status": status,
            "reconcile_payload_hash": stable_hash("reconcile", payload),
        }
    )
    return merged


def maybe_record_fill(
    state_store: LiveStateStore, decision_or_order: Mapping[str, Any], response: Mapping[str, Any]
) -> None:
    raw = response.get("order") if isinstance(response.get("order"), Mapping) else response
    fill_count = optional_float(raw.get("fill_count") or raw.get("fill_count_fp")) or 0.0
    if fill_count <= 0:
        return
    fill = {
        "fill_id": stable_hash("fill", decision_or_order, response),
        "created_ts": time.time(),
        "client_order_id": decision_or_order.get("client_order_id"),
        "exchange_order_id": raw.get("order_id") or decision_or_order.get("exchange_order_id"),
        "contract_ticker": decision_or_order.get("contract_ticker"),
        "side": decision_or_order.get("side"),
        "fill_count": fill_count,
        "price": decision_or_order.get("limit_price"),
        "fees": raw.get("fees") or raw.get("fees_dollars"),
        "response": dict(response),
    }
    state_store.append_unique("fills", "fill_id", fill)


def optional_int(value: object) -> int | None:
    number = optional_float(value)
    return None if number is None else int(number)


def kill_switch_event(reason: str, detail: str, context: Mapping[str, Any]) -> dict[str, Any]:
    created_ts = time.time()
    return {
        "event_id": stable_hash(reason, detail, context, created_ts),
        "created_ts": created_ts,
        "created_utc": iso_from_timestamp(created_ts),
        "reason": reason,
        "detail": detail,
        "blocks_new_buys": True,
        "context": dict(context),
    }


def order_is_terminal(row: Mapping[str, Any]) -> bool:
    return str(row.get("status") or "").strip().lower() in TERMINAL_ORDER_STATUSES


def stale_unreconciled_orders(
    orders: Sequence[Mapping[str, Any]], now_ts: float, timeout_seconds: int
) -> list[Mapping[str, Any]]:
    return [
        row
        for row in orders
        if now_ts - float(row.get("created_ts") or 0.0) > float(timeout_seconds)
    ]


def exposure_maps(orders: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    output: dict[str, dict[str, float]] = {
        "contract": defaultdict(float),
        "family": defaultdict(float),
        "cluster": defaultdict(float),
    }
    for row in orders:
        notional = optional_float(row.get("notional_usd")) or 0.0
        output["contract"][str(row.get("contract_ticker") or "")] += notional
        output["family"][str(row.get("family_id") or "")] += notional
        output["cluster"][str(row.get("cluster_key") or "")] += notional
    return {name: dict(values) for name, values in output.items()}


def daily_gross_buy_notional(orders: Sequence[Mapping[str, Any]], now_ts: float) -> float:
    day_start = now_ts - (now_ts % 86_400)
    return sum(
        optional_float(row.get("notional_usd")) or 0.0
        for row in orders
        if float(row.get("created_ts") or 0.0) >= day_start
    )


def list_rows(state: Mapping[str, Any], section: str) -> list[dict[str, Any]]:
    rows = state.get(section) if isinstance(state.get(section), list) else []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def as_float_map(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): float(raw or 0.0) for key, raw in value.items()}


def round_map(values: Mapping[str, float]) -> dict[str, float]:
    return {key: round(value, 6) for key, value in sorted(values.items()) if key}


def stable_hash(*parts: object) -> str:
    text = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
