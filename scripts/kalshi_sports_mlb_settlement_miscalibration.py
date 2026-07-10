#!/usr/bin/env python3
"""Fixed-clock MLB settlement-miscalibration research program.

Phase 0-5 research-only factory:
- provenance / novelty / synthetic audit
- fixed pregame executable clocks
- calibration vs hold-to-settlement economics
- finite hypothesis registry
- event-grouped walk-forward + complete-family FDR
- untouched confirmation ledger
- negative registry + frontier + final audit

No paper stake, sizing, accounts, orders, or live execution.
"""

from __future__ import annotations

# ruff: noqa: C901
import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import (  # noqa: E402
    gate,
    gate_counts,
    manual_drop_path,
    path_is_within,
    safe_research_artifact,
    safety_flags,
    utc_now,
)
from predmarket.sports_mlb_settlement_miscalibration import (  # noqa: E402
    ANALYSIS_CONTRACT_VERSION,
    DEFAULT_CLOCKS_SECONDS,
    DEFAULT_STALENESS_SECONDS,
    FAMILY_ID,
    FDR_ALPHA,
    INFERENCE_RESAMPLES,
    INFERENCE_SEED,
    MIN_OOS_EVENTS,
    build_fixed_clock_labels,
    hypothesis_registry,
    load_observation_packets,
    load_settlement_markets,
    sha256_file,
    sha256_text,
)
from predmarket.sports_mlb_settlement_miscalibration_eval import (  # noqa: E402
    apply_fdr,
    calibration_summary,
    evaluate_confirmation,
    evaluate_hypothesis,
    family_resolution_counts,
    hard_gate_assessment,
    lifecycle_status,
    negative_registry_update,
    phase0_audit,
    power_analysis,
    research_frontier,
    resolve_spec_status,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-mlb-settlement-miscalibration-latest"
DEFAULT_MICRO_OBS = manual_drop_path(
    "kalshi_sports_microstructure_observations",
    env_vars=("KALSHI_SPORTS_MICROSTRUCTURE_OBSERVATION_DIR",),
)
DEFAULT_PROXY_OBS = manual_drop_path(
    "kalshi_sports_proxy_observations",
    env_vars=("KALSHI_SPORTS_PROXY_OBSERVATION_DIR",),
)
DEFAULT_PROXY_LABELS = manual_drop_path(
    "kalshi_sports_proxy_labels",
    env_vars=("KALSHI_SPORTS_PROXY_LABEL_DIR",),
)
DEFAULT_MICRO_SETTLE = manual_drop_path(
    "kalshi_sports_microstructure_settlements",
    env_vars=("KALSHI_SPORTS_MICROSTRUCTURE_SETTLEMENT_DIR",),
)
DEFAULT_SPORTS_SETTLE = manual_drop_path(
    "kalshi_sports_settlements",
    env_vars=("KALSHI_SPORTS_SETTLEMENT_DIR",),
)
DEFAULT_RAW_DIR = manual_drop_path(
    "kalshi_sports_mlb_settlement_miscalibration",
    env_vars=("KALSHI_SPORTS_MLB_MISCALIBRATION_RAW_DIR",),
)
KALSHI_PUBLIC_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"


def fetch_json(url: str, *, timeout: float = 30.0) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "predmarket-research-mlb-miscalibration/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object payload from {url}")
    return payload


def fetch_settled_mlb_markets(
    *,
    max_pages: int = 40,
    page_limit: int = 200,
    request_delay_seconds: float = 0.12,
) -> list[dict[str, Any]]:
    markets: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(max_pages):
        params: dict[str, str] = {
            "series_ticker": "KXMLBGAME",
            "status": "settled",
            "limit": str(page_limit),
        }
        if cursor:
            params["cursor"] = cursor
        url = f"{KALSHI_PUBLIC_BASE_URL}/markets?{urllib.parse.urlencode(params)}"
        payload = fetch_json(url)
        batch = payload.get("markets") or []
        if not isinstance(batch, list):
            break
        markets.extend([dict(row) for row in batch if isinstance(row, Mapping)])
        cursor = payload.get("cursor")
        if not cursor or not batch:
            break
        if request_delay_seconds > 0:
            time.sleep(request_delay_seconds)
    return markets


def _dollar_price(value: Any) -> float | None:
    if isinstance(value, Mapping):
        for key in ("close_dollars", "close", "price_dollars"):
            if value.get(key) is not None:
                try:
                    return float(value[key])
                except (TypeError, ValueError):
                    return None
        return None
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def candle_to_observation(
    market: Mapping[str, Any], candle: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Convert a public candlestick into an explicit candle-sourced book row.

    entry_source is always candlestick_yes_ask_close so promotion can require
    denser orderbook truth. Never silent midpoint substitution.
    """
    from predmarket.shared_helpers import iso_from_timestamp, timestamp
    from predmarket.sports_mlb_settlement_miscalibration import (
        derive_event_ticker,
        series_from_ticker,
    )

    ticker = str(market.get("ticker") or market.get("contract_ticker") or "").strip()
    if not ticker.startswith("KXMLBGAME"):
        return None
    end_ts = timestamp(candle.get("end_period_ts") or candle.get("ts") or candle.get("time"))
    if end_ts is None:
        return None
    yes_ask = _dollar_price(candle.get("yes_ask"))
    yes_bid = _dollar_price(candle.get("yes_bid"))
    if yes_ask is None and yes_bid is None:
        return None
    observed = iso_from_timestamp(end_ts)
    mid = None
    if yes_bid is not None and yes_ask is not None:
        mid = (float(yes_bid) + float(yes_ask)) / 2.0
    return {
        "snapshot_id": f"candle|{ticker}|{int(end_ts)}",
        "contract_ticker": ticker,
        "event_ticker": market.get("event_ticker") or derive_event_ticker(ticker),
        "series_ticker": market.get("series_ticker") or series_from_ticker(ticker),
        "observed_at_utc": observed,
        "best_yes_bid": yes_bid,
        "best_yes_ask": yes_ask,
        "best_no_bid": None,
        "best_no_ask": None,
        "yes_mid": mid,
        "yes_spread": (
            None if yes_bid is None or yes_ask is None else float(yes_ask) - float(yes_bid)
        ),
        "open_time": market.get("open_time"),
        "created_time": market.get("created_time"),
        "settlement_time": market.get("settlement_ts") or market.get("close_time"),
        "entry_source": "candlestick_yes_ask_close",
        "usable": False,
        "research_only": True,
        "execution_enabled": False,
    }


def fetch_candle_observations_for_markets(
    markets: Sequence[Mapping[str, Any]],
    *,
    max_markets: int = 400,
    period_interval: int = 60,
    request_delay_seconds: float = 0.08,
    raw_dir: Path | None = None,
    generated_utc: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch public candlesticks for recent settled MLB markets and map to books."""
    from predmarket.shared_helpers import timestamp

    generated = generated_utc or utc_now()
    selected: list[Mapping[str, Any]] = []
    for market in markets:
        if str(market.get("result") or "").lower() not in {"yes", "no"}:
            continue
        if timestamp(market.get("occurrence_datetime") or market.get("open_time")) is None:
            continue
        selected.append(market)
        if len(selected) >= max_markets:
            break

    observations: list[dict[str, Any]] = []
    candles_by_ticker: dict[str, list[dict[str, Any]]] = {}
    for market in selected:
        ticker = str(market.get("ticker") or "").strip()
        series = str(market.get("series_ticker") or "KXMLBGAME")
        start_ts = int(timestamp(market.get("open_time") or market.get("created_time")) or 0)
        end_ts = int(
            timestamp(
                market.get("close_time")
                or market.get("settlement_ts")
                or market.get("expected_expiration_time")
            )
            or time.time()
        )
        if start_ts <= 0 or end_ts <= start_ts:
            continue
        path = (
            f"/series/{urllib.parse.quote(series, safe='')}"
            f"/markets/{urllib.parse.quote(ticker, safe='')}/candlesticks"
        )
        params = urllib.parse.urlencode(
            {
                "start_ts": str(start_ts),
                "end_ts": str(end_ts),
                "period_interval": str(period_interval),
            }
        )
        try:
            payload = fetch_json(f"{KALSHI_PUBLIC_BASE_URL}{path}?{params}")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
            continue
        candles = payload.get("candlesticks") or []
        if not isinstance(candles, list):
            continue
        candles_by_ticker[ticker] = [dict(row) for row in candles if isinstance(row, Mapping)]
        # Subsample candles near clocks to bound memory: keep up to 1 per 15 minutes.
        last_kept = None
        for candle in candles_by_ticker[ticker]:
            ts = timestamp(candle.get("end_period_ts"))
            if ts is None:
                continue
            if last_kept is not None and ts - last_kept < 900:
                continue
            row = candle_to_observation(market, candle)
            if row is not None:
                observations.append(row)
                last_kept = ts
        if request_delay_seconds > 0:
            time.sleep(request_delay_seconds)

    if raw_dir is not None:
        raw_dir.mkdir(parents=True, exist_ok=True)
        stamp = generated.replace(":", "").replace("-", "")
        path = raw_dir / f"kalshi_mlb_candlesticks_{stamp}.json"
        write_json(
            path,
            {
                "generated_utc": generated,
                "research_only": True,
                "execution_enabled": False,
                "market_execution": False,
                "account_or_order_paths": False,
                "candlesticks_by_ticker": candles_by_ticker,
                "observation_count": len(observations),
                "market_count": len(candles_by_ticker),
            },
        )
        write_json(raw_dir / "kalshi_mlb_candlesticks_latest.json", json.loads(path.read_text()))
    return observations


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    resolution = report.get("resolution_counts") or summary.get("resolution_counts") or {}
    capture = report.get("capture_readiness") or {}
    lines = [
        "# Kalshi Sports MLB Settlement Miscalibration",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Family status: `{report.get('family_status')}`",
        f"- Family: `{FAMILY_ID}`",
        f"- Schema: `{report.get('schema_version')}` (`{report.get('analysis_contract_version')}`)",
        f"- Observations: `{summary.get('observation_row_count')}`",
        f"- Settlement tickers: `{summary.get('settlement_ticker_count')}`",
        f"- Labeled rows: `{summary.get('labeled_row_count')}`",
        f"- Distinct events: `{summary.get('distinct_event_count')}`",
        f"- Pre-registered candidates: `{summary.get('registry_count')}`",
        f"- Powered novel: `{resolution.get('powered_count')}`",
        f"- Underpowered novel: `{resolution.get('underpowered_count')}`",
        f"- Powered falsified: `{resolution.get('powered_falsified_count')}`",
        f"- Frozen multi-slate confirmation: `{resolution.get('frozen_waiting_multi_slate_count')}`",
        f"- FDR survivors (incl. frozen/pending): `{summary.get('fdr_survivor_count')}`",
        f"- Research-ready survivors: `{summary.get('research_ready_count')}`",
        f"- Historical discovery data cutoff: `{report.get('historical_discovery_data_cutoff_utc')}`",
        f"- Cutoff provenance: `{report.get('discovery_cutoff_provenance')}`",
        f"- Forward confirmation registered at: `{report.get('forward_confirmation_registered_at_utc')}`",
        f"- Capture infrastructure ready: `{capture.get('capture_infrastructure_ready')}`",
        f"- Evidence panel ready: `{capture.get('evidence_panel_ready')}`",
        f"- Capture/panel status: `{capture.get('status')}`",
        f"- Public market fetches: `{report.get('public_market_data_calls')}`",
        "",
        "## Decision",
        "",
        str(report.get("decision") or ""),
        "",
        "## Power (per-specification)",
        "",
        f"- Panel event coverage met: `{((report.get('power') or {}).get('panel_event_coverage_met'))}`",
        f"- Family-wide discovery power met: `{((report.get('power') or {}).get('discovery_power_met'))}`",
        f"- Events by clock: `{(report.get('power') or {}).get('events_by_clock')}`",
        f"- Slates by clock: `{(report.get('power') or {}).get('slates_by_clock')}`",
        f"- Powered novel count: `{(report.get('power') or {}).get('powered_novel_count')}`",
        f"- Underpowered novel count: `{(report.get('power') or {}).get('underpowered_novel_count')}`",
        "",
        "## Calibration",
        "",
    ]
    calib = report.get("calibration") or {}
    for clock_name, clock in (calib.get("by_clock") or {}).items():
        lines.append(
            f"- `{clock_name}` n=`{clock.get('n')}` events=`{clock.get('distinct_events')}` "
            f"mean_residual=`{clock.get('mean_residual')}` mean_brier=`{clock.get('mean_brier')}`"
        )
    lines.extend(["", "## Evaluations", ""])
    for row in report.get("evaluations") or []:
        lines.append(
            f"- `{row.get('model_id')}` status=`{row.get('status')}` "
            f"oos_events=`{row.get('oos_event_count')}` oos_slates=`{row.get('oos_slate_count')}` "
            f"mean_net=`{row.get('oos_mean_net_return')}` "
            f"mean_resid=`{row.get('oos_mean_calibration_residual')}` "
            f"p_econ=`{row.get('p_economic')}` p_cal=`{row.get('p_calibration')}` "
            f"p_joint=`{row.get('p_joint')}` q=`{row.get('q_value')}` "
            f"slate_share=`{row.get('largest_slate_cluster_share')}` "
            f"negctrl=`{row.get('negative_control')}` baseline=`{row.get('baseline_only')}`"
        )
    frozen = report.get("frozen_candidates") or []
    if frozen:
        lines.extend(["", "## Frozen candidates (exact; do not retune)", ""])
        for row in frozen:
            lines.append(
                f"- `{row.get('model_id')}` formula_hash=`{row.get('formula_hash')}` "
                f"clock=`{row.get('clock_name')}` side=`{row.get('side')}` "
                f"registered=`{row.get('forward_confirmation_registered_at_utc')}`"
            )
    lines.extend(["", "## Confirmation", ""])
    for row in report.get("confirmation_ledger") or []:
        lines.append(
            f"- `{row.get('model_id')}` status=`{row.get('status')}` "
            f"events=`{row.get('event_count')}` slates=`{row.get('slate_count')}` "
            f"mean_net=`{row.get('mean_net_return')}`"
        )
    lines.extend(["", "## Frontier", ""])
    for row in report.get("frontier") or []:
        lines.append(
            f"- rank `{row.get('rank')}` `{row.get('lane')}` status=`{row.get('status')}` "
            f"next=`{row.get('next_action')}`"
        )
    lines.extend(
        [
            "",
            "Research-only. No paper stake, sizing, accounts, orders, or live execution.",
            "",
        ]
    )
    return "\n".join(lines)


def build_report(
    *,
    observation_dirs: Sequence[Path],
    settlement_dirs: Sequence[Path],
    proxy_label_dir: Path,
    raw_dir: Path,
    discovery_cutoff_utc: str | None,
    fetch_public_settlements: bool,
    fdr_alpha: float,
    min_oos_events: int,
) -> dict[str, Any]:
    generated = utc_now()
    cutoff = discovery_cutoff_utc or generated
    public_calls = False

    observations = load_observation_packets(list(observation_dirs))
    settlement_paths: list[Path] = []
    for directory in settlement_dirs:
        if directory.is_dir():
            settlement_paths.extend(sorted(directory.glob("*.json")))
        elif directory.is_file():
            settlement_paths.append(directory)
    if proxy_label_dir.is_dir():
        settlement_paths.extend(sorted(proxy_label_dir.glob("*.json")))

    fetched_path = None
    markets: list[dict[str, Any]] = []
    if fetch_public_settlements:
        raw_dir.mkdir(parents=True, exist_ok=True)
        markets = fetch_settled_mlb_markets()
        public_calls = True
        stamp = generated.replace(":", "").replace("-", "")
        fetched_path = raw_dir / f"kalshi_mlb_settled_markets_{stamp}.json"
        write_json(
            fetched_path,
            {
                "generated_utc": generated,
                "research_only": True,
                "execution_enabled": False,
                "market_execution": False,
                "account_or_order_paths": False,
                "series_ticker": "KXMLBGAME",
                "markets": markets,
                "count": len(markets),
            },
        )
        latest = raw_dir / "kalshi_mlb_settled_markets_latest.json"
        write_json(latest, json.loads(fetched_path.read_text(encoding="utf-8")))
        settlement_paths.append(fetched_path)
        # Explicit candlestick books expand fixed-clock coverage. Provenance is
        # entry_source=candlestick_yes_ask_close (not silent mid substitution).
        candle_obs = fetch_candle_observations_for_markets(
            markets,
            max_markets=350,
            raw_dir=raw_dir,
            generated_utc=generated,
        )
        if candle_obs:
            public_calls = True
            # Write a temporary observation packet and reload through the normalizer.
            candle_packet = raw_dir / f"kalshi_mlb_candle_observations_{stamp}.json"
            write_json(
                candle_packet,
                {
                    "generated_utc": generated,
                    "research_only": True,
                    "execution_enabled": False,
                    "packet_type": "kalshi_mlb_candle_fixed_clock_observations",
                    "rows": candle_obs,
                },
            )
            write_json(
                raw_dir / "kalshi_mlb_candle_observations_latest.json",
                json.loads(candle_packet.read_text(encoding="utf-8")),
            )
            observations = load_observation_packets([*list(observation_dirs), raw_dir])

    settlements = load_settlement_markets(settlement_paths)
    audit = phase0_audit(
        observations=observations,
        settlements=settlements,
        observation_dirs=list(observation_dirs),
        settlement_paths=settlement_paths[-20:],
    )
    if fetched_path is not None:
        audit["fetched_settlements_path"] = str(fetched_path)
        audit["fetched_settlements_sha256"] = sha256_file(fetched_path)

    # Discovery labels use pre-cutoff clocks only.
    discovery_labels, discovery_summary = build_fixed_clock_labels(
        observations,
        settlements,
        discovery_cutoff_utc=cutoff,
    )
    # Full labels (including post-cutoff) for confirmation ledger.
    all_labels, all_summary = build_fixed_clock_labels(
        observations,
        settlements,
        discovery_cutoff_utc=None,
    )
    calib = calibration_summary(all_labels)
    registry = hypothesis_registry()

    evaluations = [
        evaluate_hypothesis(
            discovery_labels,
            spec,
            min_oos_labels=min_oos_events,
            min_events=min_oos_events,
        )
        for spec in registry
    ]
    evaluations = apply_fdr(evaluations, alpha=fdr_alpha)

    # Honest timestamps: runtime cutoff censors historical discovery but is NOT a
    # pre-outcome preregistration. Forward confirmation freezes only when a candidate
    # is actually frozen for future evaluation.
    historical_cutoff = cutoff
    forward_registration = generated  # freeze time for any confirmation-pending candidates
    confirmation_ledger = [
        evaluate_confirmation(
            all_labels,
            spec,
            cutoff_utc=historical_cutoff,
            registration_utc=None,  # no candidate frozen until after resolution pass
        )
        for spec in registry
    ]
    confirmation_by_id = {row["model_id"]: row for row in confirmation_ledger}

    gated: list[dict[str, Any]] = []
    frozen_candidates: list[dict[str, Any]] = []
    for row in evaluations:
        conf = confirmation_by_id.get(str(row.get("model_id")))
        assessment = hard_gate_assessment(
            row,
            min_oos=min_oos_events,
            confirmation=conf,
        )
        resolved = resolve_spec_status(row, assessment, confirmation=conf)
        resolved["hard_gates"] = assessment
        if resolved.get("status") == "frozen_candidate_waiting_multi_slate_confirmation":
            freeze = {
                "model_id": resolved.get("model_id"),
                "formula_hash": resolved.get("formula_hash"),
                "side": resolved.get("side"),
                "clock_name": resolved.get("clock_name"),
                "feature": resolved.get("feature"),
                "direction": resolved.get("direction"),
                "threshold": resolved.get("threshold"),
                "range": resolved.get("range"),
                "p_threshold": resolved.get("p_threshold") if "p_threshold" in resolved else None,
                "spread_max": resolved.get("spread_max") if "spread_max" in resolved else None,
                "fee_rule": "executable_ask_plus_series_resolved_taker_entry_fee",
                "as_of_rule": "strict_latest_book_at_or_before_clock_within_staleness",
                "split_rule": "event_grouped_walk_forward_or_chronological_30pct_holdout",
                "inference_contract": {
                    "version": ANALYSIS_CONTRACT_VERSION,
                    "p_economic": "slate_cluster_sign_flip mean fee-adjusted net > 0",
                    "p_calibration": "slate_cluster_sign_flip mean side residual > 0",
                    "p_joint": "max(p_economic, p_calibration)",
                    "fdr": f"BH on p_joint novel family alpha={fdr_alpha}",
                    "seed": INFERENCE_SEED,
                    "n_resamples": INFERENCE_RESAMPLES,
                },
                "historical_discovery_data_cutoff_utc": historical_cutoff,
                "forward_confirmation_registered_at_utc": forward_registration,
                "analysis_contract_version": ANALYSIS_CONTRACT_VERSION,
                "registry_hash": None,  # filled below
                "code_sha_placeholder": "filled_at_write_time",
                "p_economic": resolved.get("p_economic"),
                "p_calibration": resolved.get("p_calibration"),
                "p_joint": resolved.get("p_joint"),
                "q_value": resolved.get("q_value"),
                "oos_event_count": resolved.get("oos_event_count"),
                "oos_slate_count": resolved.get("oos_slate_count"),
                "largest_slate_cluster_share": resolved.get("largest_slate_cluster_share"),
            }
            frozen_candidates.append(freeze)
            resolved["freeze_record"] = freeze
        gated.append(resolved)

    registry_hash = sha256_text(str(registry))
    for freeze in frozen_candidates:
        freeze["registry_hash"] = registry_hash

    # Re-run confirmation ledger with registration boundary for frozen candidates only.
    frozen_ids = {item["model_id"] for item in frozen_candidates}
    confirmation_ledger = []
    for spec in registry:
        reg_ts = forward_registration if spec["model_id"] in frozen_ids else None
        confirmation_ledger.append(
            evaluate_confirmation(
                all_labels,
                spec,
                cutoff_utc=historical_cutoff,
                registration_utc=reg_ts,
            )
        )
    confirmation_by_id = {row["model_id"]: row for row in confirmation_ledger}
    for row in gated:
        conf = confirmation_by_id.get(str(row.get("model_id")))
        if conf is not None:
            row["confirmation"] = conf
            # If already confirmation_pending with powered confirmation sample, leave
            # evaluation to a single preregistered confirmation pass (not continuous).
            if (
                row.get("status") == "confirmation_pending"
                and conf.get("status") == "confirmation_ready"
            ):
                conf_mean = conf.get("mean_net_return")
                if conf_mean is not None and float(conf_mean) > 0:
                    row["status"] = "research_ready_survivor"
                    row["resolution"] = "research_ready_survivor"
                elif conf_mean is not None:
                    row["status"] = "confirmation_failed"
                    row["resolution"] = "confirmation_failed"

    family_status = lifecycle_status(gated)
    resolution_counts = family_resolution_counts(gated)
    power = power_analysis(all_summary, gated)
    neg = negative_registry_update(gated, family_status=family_status)
    frontier = research_frontier(family_status, all_summary)

    novel = [
        row for row in gated if not row.get("negative_control") and not row.get("baseline_only")
    ]
    powered_novel = [row for row in novel if row.get("power_met")]
    testable_count = sum(1 for row in novel if row.get("power_met"))
    fdr_survivor_count = sum(
        1
        for row in novel
        if row.get("status")
        in {
            "research_candidate_fdr_passed",
            "confirmation_pending",
            "research_ready_survivor",
            "frozen_candidate_waiting_multi_slate_confirmation",
        }
    )
    research_ready_count = sum(1 for row in novel if row.get("status") == "research_ready_survivor")

    if family_status == "research_ready":
        status = "mlb_settlement_miscalibration_research_ready"
        decision = (
            "Outcome A: at least one pre-registered candidate passed discovery gates and "
            "untouched confirmation. Research-ready packet only; no sizing/execution."
        )
    elif family_status == "falsified":
        status = "mlb_settlement_miscalibration_family_falsified"
        decision = (
            "Outcome B: every preregistered novel member is resolved without a survivor. "
            "Record negative evidence and do not retune cosmetically."
        )
    elif family_status == "confirmation_pending":
        status = "mlb_settlement_miscalibration_confirmation_pending"
        decision = (
            "Corrected discovery inference produced frozen/confirmation-pending candidate(s). "
            "Hold formulas fixed; accumulate multi-slate dense panel for independent confirmation."
        )
    else:
        status = "mlb_settlement_miscalibration_evidence_incomplete"
        decision = (
            "Evidence incomplete: one or more novel members remain underpowered or unresolved. "
            "Do not declare Outcome B; continue dense multi-slate capture without retuning."
        )

    gates = [
        gate(
            "phase0_synthetic_suite",
            "pass"
            if all(item.get("passed") for item in audit.get("synthetic_tests") or [])
            else "blocked",
            f"{sum(1 for item in audit.get('synthetic_tests') or [] if item.get('passed'))}/"
            f"{len(audit.get('synthetic_tests') or [])} synthetic tests passed",
        ),
        gate(
            "fixed_clocks_frozen",
            "pass",
            f"clocks={list(DEFAULT_CLOCKS_SECONDS)} staleness={DEFAULT_STALENESS_SECONDS}",
        ),
        gate(
            "settlement_labels_present",
            "pass" if settlements else "blocked",
            f"{len(settlements)} exact public Kalshi settlement ticker(s)",
        ),
        gate(
            "labeled_fixed_clock_rows",
            "pass" if int(all_summary.get("labeled_row_count") or 0) > 0 else "blocked",
            f"{all_summary.get('labeled_row_count')} labeled rows",
        ),
        gate(
            "per_spec_power_accounting",
            "pass" if resolution_counts.get("novel_count", 0) > 0 else "blocked",
            (
                f"powered={resolution_counts.get('powered_count')} "
                f"underpowered={resolution_counts.get('underpowered_count')} "
                f"falsified={resolution_counts.get('powered_falsified_count')} "
                f"frozen={resolution_counts.get('frozen_waiting_multi_slate_count')}"
            ),
        ),
        gate(
            "research_only_boundary",
            "pass",
            "usable=false; no paper stake, sizing, accounts, orders, or live execution",
        ),
        gate(
            "honest_family_outcome",
            "pass"
            if not (
                family_status == "falsified"
                and int(resolution_counts.get("underpowered_count") or 0) > 0
            )
            else "blocked",
            f"family_status={family_status}; underpowered members cannot yield Outcome B",
        ),
    ]

    # Collector can run; panel breadth/independence gates are not yet met on sparse history.
    panel_slates = max((all_summary.get("slates_by_clock") or {}).values() or [0])
    panel_events = int(all_summary.get("distinct_event_count") or 0)
    evidence_panel_ready = False  # hard multi-slate panel gates not claimed in v1 repair
    capture_infrastructure_ready = True
    capture_readiness = {
        "capture_infrastructure_ready": capture_infrastructure_ready,
        "evidence_panel_ready": evidence_panel_ready,
        "status": (
            "capture_infrastructure_ready_panel_insufficient_slate_breadth"
            if capture_infrastructure_ready and not evidence_panel_ready
            else (
                "evidence_panel_ready"
                if evidence_panel_ready
                else "capture_infrastructure_not_ready"
            )
        ),
        "clocks": DEFAULT_CLOCKS_SECONDS,
        "staleness_seconds": DEFAULT_STALENESS_SECONDS,
        "observation_dirs": [str(path) for path in observation_dirs],
        "observation_row_count": len(observations),
        "clock_coverage": all_summary.get("clock_coverage"),
        "events_by_clock": all_summary.get("events_by_clock"),
        "slates_by_clock": all_summary.get("slates_by_clock"),
        "panel_distinct_events": panel_events,
        "panel_max_slates_any_clock": panel_slates,
        "dense_capture_note": (
            "Dense read-only MLB moneyline books remain mandatory input-quality work; "
            "collector readiness is not evidence-panel readiness."
        ),
    }

    summary = {
        **all_summary,
        "discovery_labeled_row_count": discovery_summary.get("labeled_row_count"),
        "registry_count": len(registry),
        "testable_count": testable_count,
        "fdr_survivor_count": fdr_survivor_count,
        "research_ready_count": research_ready_count,
        "gate_counts": gate_counts(gates),
        "family_status": family_status,
        "resolution_counts": resolution_counts,
    }

    return {
        "schema_version": 2,
        "schema_migration_note": (
            "v2: slate-clustered mean-net economic test; inferential calibration; "
            "p_joint=max(p_economic,p_calibration); BH on novel family only; "
            "per-spec power; frozen multi-slate confirmation; honest discovery vs "
            "forward-registration timestamps; fee provenance; capture vs panel readiness."
        ),
        "generated_utc": generated,
        "status": status,
        "family_id": FAMILY_ID,
        "family_status": family_status,
        "decision": decision,
        "discovery_cutoff_utc": historical_cutoff,
        "historical_discovery_data_cutoff_utc": historical_cutoff,
        "forward_confirmation_registered_at_utc": (
            forward_registration if frozen_candidates else None
        ),
        "discovery_cutoff_provenance": (
            "runtime_censor_of_historical_labels_not_pre_outcome_preregistration"
        ),
        "analysis_contract_version": ANALYSIS_CONTRACT_VERSION,
        "registry_hash": registry_hash,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "public_market_data_calls": public_calls,
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "inputs": {
            "observation_dirs": [str(path) for path in observation_dirs],
            "settlement_dirs": [str(path) for path in settlement_dirs],
            "proxy_label_dir": str(proxy_label_dir),
            "fetched_settlements_path": str(fetched_path) if fetched_path else None,
            "fetched_settlements_sha256": sha256_file(fetched_path) if fetched_path else None,
        },
        "method": {
            "clocks": DEFAULT_CLOCKS_SECONDS,
            "staleness_seconds": DEFAULT_STALENESS_SECONDS,
            "join_rule": "strict as-of latest book at or before clock within staleness",
            "label_rule": "exact public Kalshi settlement by contract_ticker",
            "calibration_estimator": "microprice if available else two-sided mid",
            "economics": (
                "hold-to-settlement: payoff - executable_ask - series-resolved taker entry fee"
            ),
            "independence_unit": "event_ticker",
            "cluster_unit": "mlb_slate_date_utc",
            "economic_null": "E[fee-adjusted net payoff] <= 0",
            "calibration_null": "E[direction-adjusted settlement residual] <= 0",
            "p_joint": "max(p_economic, p_calibration)",
            "fdr_family": "novel_discovery_only",
            "fdr_alpha": fdr_alpha,
            "inference_seed": INFERENCE_SEED,
            "inference_resamples": INFERENCE_RESAMPLES,
            "min_oos_events": min_oos_events,
            "analysis_contract_version": ANALYSIS_CONTRACT_VERSION,
        },
        "summary": summary,
        "gates": gates,
        "phase0_audit": audit,
        "power": power,
        "resolution_counts": resolution_counts,
        "frozen_candidates": frozen_candidates,
        "capture_readiness": capture_readiness,
        "hypothesis_registry": registry,
        "calibration": calib,
        "label_manifest": {
            "discovery_summary": discovery_summary,
            "full_summary": all_summary,
            "historical_discovery_data_cutoff_utc": historical_cutoff,
            "labeled_sample": [row for row in all_labels if row.get("label_status") == "labeled"][
                :50
            ],
        },
        "evaluations": gated,
        "confirmation_ledger": confirmation_ledger,
        "negative_result_registry": neg,
        "frontier": frontier,
        "final_audit": {
            "family_status": family_status,
            "research_ready_count": research_ready_count,
            "fdr_survivor_count": fdr_survivor_count,
            "powered_novel_count": len(powered_novel),
            "underpowered_novel_count": resolution_counts.get("underpowered_count"),
            "powered_falsified_count": resolution_counts.get("powered_falsified_count"),
            "frozen_waiting_multi_slate_count": resolution_counts.get(
                "frozen_waiting_multi_slate_count"
            ),
            "resolution_counts": resolution_counts,
            "synthetic_tests_passed": all(
                item.get("passed") for item in audit.get("synthetic_tests") or []
            ),
            "no_paper_stake": True,
            "no_sizing": True,
            "no_accounts_orders_live": True,
            "outcome_b_claimed": family_status == "falsified",
            "evidence_incomplete": family_status == "evidence_incomplete",
        },
        "next_action": frontier[0]["next_action"] if frontier else None,
        "safety": safety_flags(public_market_data_calls=public_calls),
        "rows": safe_research_artifact(
            [
                {
                    "model_id": row.get("model_id"),
                    "status": row.get("status"),
                    "oos_event_count": row.get("oos_event_count"),
                    "oos_slate_count": row.get("oos_slate_count"),
                    "oos_mean_net_return": row.get("oos_mean_net_return"),
                    "oos_mean_calibration_residual": row.get("oos_mean_calibration_residual"),
                    "p_economic": row.get("p_economic"),
                    "p_calibration": row.get("p_calibration"),
                    "p_joint": row.get("p_joint"),
                    "q_value": row.get("q_value"),
                    "power_state": row.get("power_state"),
                    "formula_hash": row.get("formula_hash"),
                    "negative_control": row.get("negative_control"),
                    "baseline_only": row.get("baseline_only"),
                    "usable": False,
                    "research_only": True,
                    "execution_enabled": False,
                }
                for row in gated
            ]
        ),
    }


def write_outputs(report: Mapping[str, Any], *, out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = "kalshi-sports-mlb-settlement-miscalibration"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    csv_path = out_dir / f"{stem}.csv"
    write_json(json_path, report)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(
        csv_path,
        list(report.get("evaluations") or []),
        [
            "model_id",
            "status",
            "clock_name",
            "side",
            "feature",
            "oos_event_count",
            "oos_slate_count",
            "oos_mean_net_return",
            "oos_mean_calibration_residual",
            "p_economic",
            "p_calibration",
            "p_joint",
            "q_value",
            "bootstrap_mean_net_lower_95",
            "power_state",
            "largest_slate_cluster_share",
            "negative_control",
            "baseline_only",
        ],
    )

    # Durable latest entry points required by the directive.
    pointers = {
        "truth-leakage-audit": report.get("phase0_audit"),
        "fixed-clock-capture-readiness": report.get("capture_readiness"),
        "hypothesis-registry": report.get("hypothesis_registry"),
        "calibration-economic-label-manifest": report.get("label_manifest"),
        "walk-forward-fdr-results": report.get("evaluations"),
        "untouched-confirmation-ledger": report.get("confirmation_ledger"),
        "negative-result-registry": report.get("negative_result_registry"),
        "research-frontier": report.get("frontier"),
        "final-audit": report.get("final_audit"),
    }
    written = {
        "json": str(json_path),
        "md": str(md_path),
        "csv": str(csv_path),
    }
    for name, payload in pointers.items():
        path = out_dir / f"kalshi-sports-mlb-miscalibration-{name}.json"
        write_json(
            path,
            {
                "generated_utc": report.get("generated_utc"),
                "family_id": FAMILY_ID,
                "family_status": report.get("family_status"),
                "status": report.get("status"),
                "research_only": True,
                "execution_enabled": False,
                "payload": payload,
            },
        )
        written[name] = str(path)

    if path_is_within(out_dir, MACRO_DIR):
        latest_prefix = MACRO_DIR / "latest-kalshi-sports-mlb-settlement-miscalibration"
        for suffix, path in (("json", json_path), ("md", md_path), ("csv", csv_path)):
            target = Path(f"{latest_prefix}.{suffix}")
            target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            written[f"latest_{suffix}"] = str(target)
        for name in pointers:
            src = out_dir / f"kalshi-sports-mlb-miscalibration-{name}.json"
            dst = MACRO_DIR / f"latest-kalshi-sports-mlb-miscalibration-{name}.json"
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            written[f"latest_{name}"] = str(dst)
        # Keep global sports negative registry / frontier pointers updated without
        # erasing prior short-horizon falsifications (payload already merges them).
        (MACRO_DIR / "latest-kalshi-sports-negative-result-registry.json").write_text(
            json.dumps(report.get("negative_result_registry"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (MACRO_DIR / "latest-kalshi-sports-research-frontier.json").write_text(
            json.dumps(report.get("frontier"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return written


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--observation-dir",
        type=Path,
        action="append",
        default=None,
        help="Observation packet directory (repeatable).",
    )
    parser.add_argument(
        "--settlement-dir",
        type=Path,
        action="append",
        default=None,
        help="Settlement packet directory (repeatable).",
    )
    parser.add_argument("--proxy-label-dir", type=Path, default=DEFAULT_PROXY_LABELS)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--discovery-cutoff-utc", default=None)
    parser.add_argument(
        "--fetch-public-settlements",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--fdr-alpha", type=float, default=FDR_ALPHA)
    parser.add_argument("--min-oos-events", type=int, default=MIN_OOS_EVENTS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    observation_dirs = args.observation_dir or [DEFAULT_MICRO_OBS, DEFAULT_PROXY_OBS]
    settlement_dirs = args.settlement_dir or [DEFAULT_MICRO_SETTLE, DEFAULT_SPORTS_SETTLE]
    try:
        report = build_report(
            observation_dirs=observation_dirs,
            settlement_dirs=settlement_dirs,
            proxy_label_dir=args.proxy_label_dir,
            raw_dir=args.raw_dir,
            discovery_cutoff_utc=args.discovery_cutoff_utc,
            fetch_public_settlements=bool(args.fetch_public_settlements),
            fdr_alpha=float(args.fdr_alpha),
            min_oos_events=int(args.min_oos_events),
        )
    except (
        OSError,
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    written = write_outputs(report, out_dir=args.out_dir)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "family_status": report.get("family_status"),
                "labeled_row_count": (report.get("summary") or {}).get("labeled_row_count"),
                "distinct_event_count": (report.get("summary") or {}).get("distinct_event_count"),
                "fdr_survivor_count": (report.get("summary") or {}).get("fdr_survivor_count"),
                "research_ready_count": (report.get("summary") or {}).get("research_ready_count"),
                "written": written,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
