#!/usr/bin/env python3
"""Federated Kalshi contract EV ledger.

The macro router decides which repo to work on. This script asks the sharper
question: for every active repo, can it produce contract-level Kalshi EV rows?

It is read-only by default and never calls providers, writes databases, or
touches execution paths. ATP is treated as read-only input; the ledger is
written only in the command-center repo when --write is supplied.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.feature_flags import FeatureFlag, is_enabled  # noqa: E402
from predmarket.kalshi_execution_cost import normalize_kalshi_execution_cost  # noqa: E402

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
ACTIVE_UNIVERSE_PATH = MACRO_DIR / "active-universe.json"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-contract-ev-ledger-latest"
DEFAULT_OVERLAY_PREFLIGHT_OUT_DIR = MACRO_DIR / "kalshi-ev-overlay-preflight-latest"
DEFAULT_CALIBRATION_WORK_ORDER_OUT_DIR = MACRO_DIR / "kalshi-ev-calibration-work-order-latest"
DEFAULT_CONTRACT_MAPPING_WORK_ORDER_OUT_DIR = MACRO_DIR / "kalshi-ev-contract-mapping-work-order-latest"
DEFAULT_NFL_FAIR_LINE_REVIEW_PATH = (
    Path("/home/mrwatson/projects/nfl_quant_glm51_greenfield")
    / "docs/codex/artifacts/nfl-line-readiness-latest/fair-line-review.json"
)
DEFAULT_NFL_HISTORICAL_LINE_BACKTEST_PATH = (
    Path("/home/mrwatson/projects/nfl_quant_glm51_greenfield")
    / "docs/codex/artifacts/nfl-historical-line-backtest-latest/historical-line-backtest.json"
)
DEFAULT_NFL_HISTORICAL_LINE_VALIDATION_PATH = (
    Path("/home/mrwatson/projects/nfl_quant_glm51_greenfield")
    / "docs/codex/artifacts/nfl-historical-line-validation-latest/historical-line-validation-summary.json"
)

LEDGER_SCHEMA_VERSION = 1
DEFAULT_BINARY_PAYOUT = 1.0
MIN_VALID_PAYOUT_MULTIPLE = 1.0
OFFICIAL_TERMS_SNAPSHOT_PATHS = (
    Path("/home/mrwatson/manual_drops/kalshi"),
    CONTROL_REPO / "data",
)
CALIBRATED_PROBABILITY_OVERLAY_PATHS = (
    Path("/home/mrwatson/manual_drops/kalshi_ev_probabilities"),
)
CONTRACT_MAPPING_OVERLAY_PATHS = (
    Path("/home/mrwatson/manual_drops/kalshi_ev_contract_mappings"),
)
OFFICIAL_TERMS_FILENAME_PREFIXES = (
    "kalshi_mlb_game_series",
    "kalshi_scored",
)
VALID_CALIBRATION_STATUSES = {
    "validated_calibrated_probability",
    "review_only_calibrated_probability",
}
VALID_CONTRACT_MAPPING_STATUSES = {
    "verified_contract_mapping",
    "review_only_contract_mapping",
}
KALSHI_PAYOUT_MULTIPLE_KEYS = (
    "kalshi_payout_multiple",
    "ticket_payout_multiple",
    "displayed_payout_multiple",
    "payout_multiple",
    "yes_payout_multiple",
    "payout_x",
)
ALL_IN_PAYOUT_MULTIPLE_KEYS = (
    "all_in_payout_multiple",
    "fee_inclusive_payout_multiple",
    "net_payout_multiple",
    "order_ticket_all_in_payout_multiple",
    "ticket_all_in_payout_multiple",
)
EXPLICIT_ALL_IN_COST_KEYS = (
    "all_in_cost",
    "execution_cost",
    "order_ticket_cost",
    "ticket_cost",
    "cost_to_settle_1",
    "cost_to_win_1",
)


OfficialKalshiTerms = dict[str, str | None]
CalibratedProbability = dict[str, Any]
ContractMapping = dict[str, Any]


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_active_universe(path: Path = ACTIVE_UNIVERSE_PATH) -> list[dict[str, Any]]:
    raw = read_json(path)
    repos = raw.get("repos") if isinstance(raw, dict) else None
    if not isinstance(repos, list):
        raise ValueError(f"active universe missing repos list: {path}")
    return [repo for repo in repos if isinstance(repo, dict)]


def build_ledger(
    *,
    active_universe_path: Path = ACTIVE_UNIVERSE_PATH,
    max_rows_per_repo: int = 500,
    generated_utc: str | None = None,
    official_terms_paths: list[Path] | None = None,
    calibrated_probability_paths: list[Path] | None = None,
    contract_mapping_paths: list[Path] | None = None,
) -> dict[str, Any]:
    repos = load_active_universe(active_universe_path)
    generated = generated_utc or utc_now()
    official_terms = load_official_terms_index(paths=official_terms_paths)
    calibrated_probabilities = load_calibrated_probability_index(paths=calibrated_probability_paths)
    contract_mappings = load_contract_mapping_index(paths=contract_mapping_paths)

    # Feature flag: EV calibrated probability overlay enrichment. When enabled,
    # each row gets an additional calibration cross-check comparing the overlay
    # probability against break-even math. Disabled (default) = base overlay only.
    overlay_enabled = is_enabled(FeatureFlag.EV_CALIBRATED_OVERLAY)
    rows: list[dict[str, Any]] = []
    feeds: list[dict[str, Any]] = []
    for repo in repos:
        repo_id = str(repo.get("repo_id") or "")
        repo_path = Path(str(repo.get("path") or "")).expanduser()
        feed = adapt_repo(
            repo_id=repo_id,
            repo_path=repo_path,
            max_rows=max_rows_per_repo,
            official_terms=official_terms,
            calibrated_probabilities=calibrated_probabilities,
            contract_mappings=contract_mappings,
        )
        feeds.append(feed["feed"])
        rows.extend(feed["rows"])

    usable_rows = [row for row in rows if row.get("usable") is True]
    positive_rows = [
        row
        for row in rows
        if row.get("edge_probability") is not None and float(row["edge_probability"]) > 0.0
    ]
    blocked_feeds = [feed for feed in feeds if feed.get("status", "").startswith("blocked")]
    if usable_rows:
        status = "kalshi_ev_ledger_ready_with_usable_contract_edges"
    elif rows:
        status = "kalshi_ev_ledger_candidates_present_but_not_usable"
    else:
        status = "kalshi_ev_ledger_blocked_no_contract_rows"

    gate_counts: dict[str, int] = {"pass": 0, "warn": 0, "blocked": 0, "fail": 0}
    for row in rows:
        gate = str(row.get("gate_status") or "blocked")
        gate_counts[gate] = gate_counts.get(gate, 0) + 1
    for feed in feeds:
        gate = str(feed.get("gate_status") or "blocked")
        gate_counts[gate] = gate_counts.get(gate, 0) + 1

    # Feature flag enrichment: cross-check calibrated probability against break-even.
    overlay_cross_checks: list[dict[str, Any]] = []
    if overlay_enabled:
        for row in rows:
            cal_prob = row.get("calibrated_probability")
            break_even = row.get("all_in_break_even_probability")
            ticker = row.get("contract_ticker", "")
            if cal_prob is not None and break_even is not None:
                overlay_cross_checks.append({
                    "contract_ticker": ticker,
                    "calibrated_probability": cal_prob,
                    "break_even_probability": break_even,
                    "margin": float(cal_prob) - float(break_even),
                    "overlay_confirms_edge": float(cal_prob) > float(break_even),
                })

    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "live_calls_made": False,
        "provider_api_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "summary": {
            "repo_count": len(feeds),
            "repo_feed_count": len(feeds),
            "row_count": len(rows),
            "usable_row_count": len(usable_rows),
            "positive_edge_row_count": len(positive_rows),
            "blocked_feed_count": len(blocked_feeds),
            "gate_counts": gate_counts,
            "verified_resolution_rule_row_count": sum(
                1 for row in rows if row.get("resolution_rule_status") == "verified_official_terms"
            ),
            "inferred_resolution_rule_row_count": sum(
                1 for row in rows if row.get("resolution_rule_status") != "verified_official_terms"
            ),
            "missing_calibrated_probability_row_count": sum(
                1 for row in rows if row.get("calibrated_probability") is None
            ),
            "blocked_row_reason_counts": gate_reason_counts(rows),
            "top_blocked_row_reasons": top_gate_reasons(rows),
            "calibrated_probability_overlay_row_count": len(calibrated_probabilities),
            "contract_mapping_overlay_row_count": sum(len(rows) for rows in contract_mappings.values()),
        },
        "contract_math": {
            "contract_price_break_even_probability": "executable_price",
            "displayed_price_break_even_probability": "display_price",
            "all_in_break_even_probability": (
                "explicit all-in execution cost, else 1 / fee-inclusive payout multiple, else "
                "1 / ticket/order payout multiple plus explicit or official fee estimate and slippage_buffer, else "
                "executable_price plus explicit or official fee estimate and slippage_buffer"
            ),
            "break_even_probability": "alias for all_in_break_even_probability",
            "payout_implied_break_even_probability": "1 / kalshi_payout_multiple when present",
            "all_in_cost": (
                "explicit all-in execution cost, else payout_if_correct / fee-inclusive payout multiple, else "
                "payout_if_correct / kalshi_payout_multiple plus explicit or official fee estimate and "
                "slippage_buffer, else executable_price plus explicit or official fee estimate and slippage_buffer"
            ),
            "effective_hold_probability": "all_in_break_even_probability - display_price",
            "margin_probability": "calibrated_probability - all_in_break_even_probability",
            "ev_calibrated_overlay_enabled": overlay_enabled,
            "expected_value_per_contract": "calibrated_probability * payout_if_correct - all_in_cost",
            "expected_roi": "expected_value_per_contract / all_in_cost",
            "cost_basis_policy": (
                "Usable EV rows use the actual execution cost basis as the hurdle: explicit all-in cost first, "
                "fee-inclusive payout multiplier second, ticket/order payout multiplier plus explicit or official "
                "fee estimates third, executable price plus explicit or official fee estimates as fallback."
            ),
            "fee_policy": (
                "Kalshi trading fees are part of the all-in hurdle. Generic ticket/order payout multipliers are "
                "treated as gross price unless marked fee-inclusive; explicit all-in cost and fee-inclusive payout "
                "multipliers are not charged another fee."
            ),
            "resolution_policy": (
                "Rows must emit a resolution rule, source, and status. Usable rows require "
                "resolution_rule_status=verified_official_terms; inferred/unverified terms are review-only blockers."
            ),
            "binary_payout_default": DEFAULT_BINARY_PAYOUT,
        },
        "repo_feeds": feeds,
        "rows": rows,
        "overlay_cross_checks": overlay_cross_checks if overlay_enabled else None,
        "next_action": next_action(feeds, rows),
        "safety": {
            "research_only": True,
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "raw_payloads_copied_to_repo": False,
        },
    }


def adapt_repo(
    *,
    repo_id: str,
    repo_path: Path,
    max_rows: int,
    official_terms: dict[str, OfficialKalshiTerms],
    calibrated_probabilities: dict[tuple[str, str], CalibratedProbability],
    contract_mappings: dict[str, list[ContractMapping]],
) -> dict[str, Any]:
    if repo_id == "predmarket-alpha":
        return adapt_predmarket(
            repo_id=repo_id,
            repo_path=repo_path,
            max_rows=max_rows,
            official_terms=official_terms,
            calibrated_probabilities=calibrated_probabilities,
            contract_mappings=contract_mappings.get(repo_id, []),
        )
    if repo_id == "mlb-platform":
        return adapt_mlb(
            repo_id=repo_id,
            repo_path=repo_path,
            max_rows=max_rows,
            official_terms=official_terms,
            calibrated_probabilities=calibrated_probabilities,
            contract_mappings=contract_mappings.get(repo_id, []),
        )
    if repo_id == "nfl_quant_glm51_greenfield":
        mapped = adapt_contract_mapping_overlay(
            repo_id=repo_id,
            repo_path=repo_path,
            mappings=contract_mappings.get(repo_id, []),
            calibrated_probabilities=calibrated_probabilities,
        )
        if mapped is not None:
            return mapped
        return blocked_feed(
            repo_id=repo_id,
            repo_path=repo_path,
            status="blocked_no_kalshi_contract_mapping",
            blockers=[
                "NFL repo emits model fair lines and consensus market references, not Kalshi tickers.",
                "No executable Kalshi contract price, side, or resolution mapping is available.",
            ],
            source_artifacts=[
                str(repo_path / "docs/codex/artifacts/nfl-line-readiness-latest/fair-line-review.json"),
                str(repo_path / "docs/codex/artifacts/nfl-consensus-market-latest/consensus-market-reference.json"),
            ],
            ev_readiness={
                "contract_mapping_status": "missing_exact_kalshi_contract_mapping",
                "official_terms_status": "blocked_until_contract_mapping",
                "execution_cost_status": "blocked_until_kalshi_quote",
                "calibrated_probability_status": "available_model_probability_not_contract_mapped",
                "row_gate_status": "blocked_no_contract_rows",
                "exact_next_input": (
                    "A local Kalshi NFL market snapshot or manual mapping with ticker, side, official rules, "
                    "YES/NO outcome mapping, and executable quote for the profiled Week 1 games."
                ),
                "next_local_command": "cd /home/mrwatson/projects/nfl_quant_glm51_greenfield && make macro-status",
            },
        )
    if repo_id == "nba-analytics-platform":
        mapped = adapt_contract_mapping_overlay(
            repo_id=repo_id,
            repo_path=repo_path,
            mappings=contract_mappings.get(repo_id, []),
            calibrated_probabilities=calibrated_probabilities,
        )
        if mapped is not None:
            return mapped
        return blocked_feed(
            repo_id=repo_id,
            repo_path=repo_path,
            status="blocked_no_kalshi_contract_mapping",
            blockers=[
                "NBA repo currently emits market-readiness and residual diagnostics, not Kalshi tickers.",
                "No executable Kalshi contract price, side, or calibrated contract probability is available.",
            ],
            source_artifacts=[
                str(repo_path / "docs/codex/artifacts/nba-market-claim-gate-latest/nba-market-claim-gate.json")
            ],
            ev_readiness={
                "contract_mapping_status": "missing_exact_kalshi_contract_mapping",
                "official_terms_status": "blocked_until_contract_mapping",
                "execution_cost_status": "blocked_until_kalshi_quote",
                "calibrated_probability_status": "blocked_market_parity_no_current_contract_model",
                "row_gate_status": "blocked_no_contract_rows",
                "exact_next_input": (
                    "A new source-backed NBA signal or market dataset plus exact Kalshi ticker/side/rules/quote "
                    "mapping for the target contract class."
                ),
                "next_local_command": "cd /home/mrwatson/projects/nba-analytics-platform && make macro-status",
            },
        )
    if repo_id == "atp-oracle":
        mapped = adapt_contract_mapping_overlay(
            repo_id=repo_id,
            repo_path=repo_path,
            mappings=contract_mappings.get(repo_id, []),
            calibrated_probabilities=calibrated_probabilities,
        )
        if mapped is not None:
            return mapped
        return blocked_feed(
            repo_id=repo_id,
            repo_path=repo_path,
            status="blocked_read_only_atp_no_kalshi_ev_rows",
            blockers=[
                "ATP repo was inspected read-only because another worker is active there.",
                "ATP diagnostics are not yet mapped to executable Kalshi tickers with calibrated probabilities.",
            ],
            source_artifacts=[
                str(repo_path / "docs/codex/artifacts/type2-g1g2-diagnostic-latest/type2-g1g2-diagnostic.json"),
                str(repo_path / "docs/codex/artifacts/type2-readiness-latest/type2-readiness.json"),
            ],
            ev_readiness={
                "contract_mapping_status": "missing_exact_kalshi_contract_mapping",
                "official_terms_status": "blocked_until_contract_mapping",
                "execution_cost_status": "blocked_until_kalshi_quote",
                "calibrated_probability_status": "blocked_fresh_validation_and_external_evidence_missing",
                "row_gate_status": "blocked_no_contract_rows",
                "exact_next_input": (
                    "Fresh ATP validation/promotion evidence plus D3/G5/P5 external proof and exact Kalshi "
                    "ticker/side/rules/quote mapping."
                ),
                "next_local_command": "cd /home/mrwatson/projects/atp-oracle && make type2-g1g2-diagnostic",
            },
        )
    return blocked_feed(
        repo_id=repo_id,
        repo_path=repo_path,
        status="blocked_unknown_repo_adapter",
        blockers=[f"No Kalshi EV adapter is defined for repo_id={repo_id}."],
        source_artifacts=[],
    )


def adapt_predmarket(
    *,
    repo_id: str,
    repo_path: Path,
    max_rows: int,
    official_terms: dict[str, OfficialKalshiTerms],
    calibrated_probabilities: dict[tuple[str, str], CalibratedProbability],
    contract_mappings: list[ContractMapping],
) -> dict[str, Any]:
    matcher_path = repo_path / "docs/codex/artifacts/type2-paper-matcher-latest/type2-paper-matcher-latest.json"
    disposition_path = (
        repo_path
        / "docs/codex/artifacts/type2-candidate-disposition-latest/type2-candidate-disposition-latest.json"
    )
    matcher = read_json_or_none(matcher_path)
    if not matcher:
        return blocked_feed(
            repo_id=repo_id,
            repo_path=repo_path,
            status="blocked_missing_predmarket_type2_matcher",
            blockers=["Predmarket Type 2 matcher artifact is missing."],
            source_artifacts=[str(matcher_path)],
        )
    dispositions = read_json_or_none(disposition_path) or {}
    disposition_by_key = {
        disposition_key(row): row
        for row in dispositions.get("dispositions", [])
        if isinstance(row, dict)
    }
    rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(matcher.get("candidates", [])[:max_rows]):
        if not isinstance(candidate, dict):
            continue
        disposition = disposition_by_key.get(disposition_key(candidate), {})
        gate_status, reasons = predmarket_gate(candidate, disposition)
        contract_ticker = str(candidate.get("kalshi_ticker") or "")
        resolution = resolution_rule_fields(
            contract_ticker=contract_ticker,
            inferred_rule=predmarket_resolution_rule(candidate),
            inferred_source="inferred_from_kalshi_ticker_and_title",
            official_terms=official_terms,
        )
        probability = calibrated_probability_fields(
            contract_ticker=contract_ticker,
            side="yes",
            calibrated_probabilities=calibrated_probabilities,
        )
        reasons = probability_adjusted_gate_reasons(reasons, probability)
        rows.append(
            make_ev_row(
                source_repo_id=repo_id,
                source_artifact=matcher_path,
                source_row_index=index,
                contract_ticker=contract_ticker,
                event_ticker=str(candidate.get("event_ticker") or ""),
                market_ticker=str(candidate.get("event_ticker") or candidate.get("kalshi_ticker") or ""),
                side="yes",
                selection=predmarket_selection(candidate),
                market_type="mlb_type2_predmarket_reference",
                title=str(candidate.get("title") or ""),
                resolution_rule=resolution["resolution_rule"],
                resolution_rule_source=resolution["resolution_rule_source"],
                resolution_rule_status=resolution["resolution_rule_status"],
                display_price=optional_float(candidate.get("kalshi_ask")),
                display_price_source="kalshi_ask",
                executable_price_source="kalshi_ask",
                fee_estimate=optional_float(candidate.get("fee_estimate")),
                slippage_buffer=optional_float(candidate.get("slippage_buffer")),
                explicit_all_in_cost=extract_explicit_all_in_cost(candidate),
                all_in_payout_multiple=extract_all_in_payout_multiple(candidate),
                kalshi_payout_multiple=extract_kalshi_payout_multiple(candidate),
                calibrated_probability=probability["calibrated_probability"],
                calibrated_probability_source=probability["calibrated_probability_source"],
                calibration_status=probability["calibration_status"],
                calibrated_probability_source_artifact=probability["source_artifact"],
                calibrated_probability_source_sha256=probability["source_sha256"],
                reference_probability=optional_float(candidate.get("sportsbook_no_vig_yes")),
                reference_probability_source="sportsbook_no_vig_reference_not_platform_calibrated_model",
                probability_uncertainty=probability["probability_uncertainty"]
                if probability["probability_uncertainty"] is not None
                else optional_float(candidate.get("uncertainty_buffer")),
                kalshi_bid=optional_float(candidate.get("kalshi_bid")),
                kalshi_ask=optional_float(candidate.get("kalshi_ask")),
                kalshi_midpoint=optional_float(candidate.get("kalshi_midpoint")),
                gate_status=gate_status,
                gate_reasons=reasons,
                review_status=str(candidate.get("review_status") or ""),
                timing_status=str(disposition.get("disposition") or "unknown"),
                mapping_confidence="medium",
                resolution_rule_source_artifact=resolution["resolution_rule_source_artifact"],
                resolution_rule_source_sha256=resolution["resolution_rule_source_sha256"],
            )
        )
    return rows_feed(
        repo_id=repo_id,
        repo_path=repo_path,
        rows=rows,
        status=feed_status(rows, "predmarket_type2_candidates_loaded"),
        blockers=[] if rows else ["Predmarket matcher has no candidates."],
        source_artifacts=[
            str(matcher_path),
            str(disposition_path),
            *resolution_source_artifacts(rows),
        ],
    )


def adapt_mlb(
    *,
    repo_id: str,
    repo_path: Path,
    max_rows: int,
    official_terms: dict[str, OfficialKalshiTerms],
    calibrated_probabilities: dict[tuple[str, str], CalibratedProbability],
    contract_mappings: list[ContractMapping],
) -> dict[str, Any]:
    evidence_path = latest_mlb_type2_evidence(repo_path)
    repeatability_path = repo_path / "docs/codex/artifacts/type2-repeatability-ledger-latest/type2-repeatability-ledger.json"
    settled_path = repo_path / "docs/codex/artifacts/type2-settled-outcome-validation-latest/type2-settled-outcome-validation.json"
    evidence = read_json_or_none(evidence_path) if evidence_path else None
    if not evidence:
        return blocked_feed(
            repo_id=repo_id,
            repo_path=repo_path,
            status="blocked_missing_mlb_type2_evidence",
            blockers=["MLB Type 2 evidence artifact is missing."],
            source_artifacts=[] if evidence_path is None else [str(evidence_path)],
        )
    repeatability = read_json_or_none(repeatability_path) or {}
    settled = read_json_or_none(settled_path) or {}
    repo_reasons = mlb_global_reasons(repeatability, settled)
    rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(evidence.get("candidates", [])[:max_rows]):
        if not isinstance(candidate, dict):
            continue
        gate_status, reasons = mlb_gate(candidate, repo_reasons)
        contract_ticker = str(candidate.get("exchange_market_id") or "")
        resolution = resolution_rule_fields(
            contract_ticker=contract_ticker,
            inferred_rule=mlb_resolution_rule(candidate),
            inferred_source="inferred_from_mlb_type2_evidence",
            official_terms=official_terms,
        )
        probability = calibrated_probability_fields(
            contract_ticker=contract_ticker,
            side="yes",
            calibrated_probabilities=calibrated_probabilities,
        )
        reasons = probability_adjusted_gate_reasons(reasons, probability)
        rows.append(
            make_ev_row(
                source_repo_id=repo_id,
                source_artifact=evidence_path,
                source_row_index=index,
                contract_ticker=contract_ticker,
                event_ticker=event_from_contract(contract_ticker),
                market_ticker=str(candidate.get("game_id") or candidate.get("exchange_market_id") or ""),
                side="yes",
                selection=str(candidate.get("selection") or ""),
                market_type=str(candidate.get("market") or "unknown"),
                title="",
                resolution_rule=resolution["resolution_rule"],
                resolution_rule_source=resolution["resolution_rule_source"],
                resolution_rule_status=resolution["resolution_rule_status"],
                display_price=optional_float(candidate.get("exchange_ask")),
                display_price_source="exchange_ask",
                executable_price_source="exchange_ask",
                fee_estimate=optional_float(candidate.get("fee_estimate")),
                slippage_buffer=optional_float(candidate.get("slippage_buffer")),
                explicit_all_in_cost=extract_explicit_all_in_cost(candidate),
                all_in_payout_multiple=extract_all_in_payout_multiple(candidate),
                kalshi_payout_multiple=extract_kalshi_payout_multiple(candidate),
                calibrated_probability=probability["calibrated_probability"],
                calibrated_probability_source=probability["calibrated_probability_source"],
                calibration_status=probability["calibration_status"],
                calibrated_probability_source_artifact=probability["source_artifact"],
                calibrated_probability_source_sha256=probability["source_sha256"],
                reference_probability=optional_float(candidate.get("sportsbook_prob")),
                reference_probability_source="sportsbook_no_vig_reference_not_platform_calibrated_model",
                probability_uncertainty=probability["probability_uncertainty"]
                if probability["probability_uncertainty"] is not None
                else optional_float(candidate.get("friction_prob")),
                kalshi_bid=optional_float(candidate.get("exchange_bid")),
                kalshi_ask=optional_float(candidate.get("exchange_ask")),
                kalshi_midpoint=optional_float(candidate.get("exchange_prob")),
                gate_status=gate_status,
                gate_reasons=reasons,
                review_status=str(candidate.get("status") or ""),
                timing_status=str(candidate.get("source_snapshot_role") or "unknown"),
                mapping_confidence=mapping_confidence(candidate),
                resolution_rule_source_artifact=resolution["resolution_rule_source_artifact"],
                resolution_rule_source_sha256=resolution["resolution_rule_source_sha256"],
            )
        )
    return rows_feed(
        repo_id=repo_id,
        repo_path=repo_path,
        rows=rows,
        status=feed_status(rows, "mlb_type2_candidates_loaded"),
        blockers=repo_reasons if not rows else [],
        source_artifacts=[
            str(path)
            for path in (evidence_path, repeatability_path, settled_path)
            if path is not None
        ]
        + resolution_source_artifacts(rows),
    )


def adapt_contract_mapping_overlay(
    *,
    repo_id: str,
    repo_path: Path,
    mappings: list[ContractMapping],
    calibrated_probabilities: dict[tuple[str, str], CalibratedProbability],
) -> dict[str, Any] | None:
    if not mappings:
        return None
    rows: list[dict[str, Any]] = []
    source_artifacts: set[str] = set()
    for index, mapping in enumerate(mappings):
        contract_ticker = str(mapping.get("contract_ticker") or "").strip()
        side = normalize_side(mapping.get("side"))
        probability = calibrated_probability_fields(
            contract_ticker=contract_ticker,
            side=side,
            calibrated_probabilities=calibrated_probabilities,
        )
        gate_status, reasons = contract_mapping_gate(mapping)
        reasons = probability_adjusted_gate_reasons(reasons, probability)
        source_artifact = Path(str(mapping.get("source_artifact") or ""))
        if source_artifact:
            source_artifacts.add(str(source_artifact))
        rows.append(
            make_ev_row(
                source_repo_id=repo_id,
                source_artifact=source_artifact,
                source_row_index=int(mapping.get("source_row_index") or index),
                contract_ticker=contract_ticker,
                event_ticker=str(mapping.get("event_ticker") or event_from_contract(contract_ticker)),
                market_ticker=str(mapping.get("market_ticker") or mapping.get("event_ticker") or contract_ticker),
                side=side,
                selection=str(mapping.get("selection") or contract_selection(contract_ticker)),
                market_type=str(mapping.get("market_type") or "contract_mapping_overlay"),
                title=str(mapping.get("title") or ""),
                resolution_rule=str(mapping.get("resolution_rule") or ""),
                resolution_rule_source=str(mapping.get("resolution_rule_source") or "local_contract_mapping_overlay"),
                resolution_rule_status=str(mapping.get("resolution_rule_status") or ""),
                display_price=overlay_display_price(mapping),
                display_price_source=str(mapping.get("display_price_source") or "contract_mapping_overlay"),
                executable_price_source=str(mapping.get("executable_price_source") or "contract_mapping_overlay"),
                fee_estimate=optional_float(mapping.get("fee_estimate")),
                slippage_buffer=optional_float(mapping.get("slippage_buffer")),
                explicit_all_in_cost=extract_explicit_all_in_cost(mapping),
                all_in_payout_multiple=extract_all_in_payout_multiple(mapping),
                kalshi_payout_multiple=extract_kalshi_payout_multiple(mapping),
                calibrated_probability=probability["calibrated_probability"],
                calibrated_probability_source=probability["calibrated_probability_source"],
                calibration_status=probability["calibration_status"],
                calibrated_probability_source_artifact=probability["source_artifact"],
                calibrated_probability_source_sha256=probability["source_sha256"],
                reference_probability=optional_float(mapping.get("reference_probability")),
                reference_probability_source=str(mapping.get("reference_probability_source") or ""),
                probability_uncertainty=probability["probability_uncertainty"]
                if probability["probability_uncertainty"] is not None
                else optional_float(mapping.get("probability_uncertainty")),
                kalshi_bid=optional_float(mapping.get("kalshi_bid")),
                kalshi_ask=optional_float(mapping.get("kalshi_ask")),
                kalshi_midpoint=optional_float(mapping.get("kalshi_midpoint")),
                gate_status=gate_status,
                gate_reasons=reasons,
                review_status=str(mapping.get("mapping_status") or ""),
                timing_status=str(mapping.get("timing_status") or "unknown"),
                mapping_confidence=str(mapping.get("mapping_confidence") or "manual_overlay"),
                resolution_rule_source_artifact=str(mapping.get("source_artifact") or ""),
                resolution_rule_source_sha256=str(mapping.get("source_sha256") or ""),
            )
        )
    return rows_feed(
        repo_id=repo_id,
        repo_path=repo_path,
        rows=rows,
        status=feed_status(rows, f"{repo_id}_contract_mapping_overlay"),
        blockers=[],
        source_artifacts=sorted(source_artifacts),
    )


def predmarket_gate(candidate: dict[str, Any], disposition: dict[str, Any]) -> tuple[str, list[str]]:
    reasons = [
        "probability source is sportsbook no-vig reference, not a calibrated platform model",
        "calibrated contract probability is missing",
    ]
    review_status = str(candidate.get("review_status") or "")
    if review_status not in {"REVIEW_READY", "REVIEW_ONLY_PASS"}:
        reasons.append(f"review status is {review_status or 'unknown'}")
    disposition_status = str(disposition.get("disposition") or "")
    if disposition_status:
        reasons.append(f"candidate disposition is {disposition_status}")
    if "TEMPORAL_MISMATCH" in disposition_status:
        reasons.append("timing mismatch blocks usable EV")
    if not contract_cost_basis_available(
        display_price=optional_float(candidate.get("kalshi_ask")),
        explicit_all_in_cost=extract_explicit_all_in_cost(candidate),
        all_in_payout_multiple=extract_all_in_payout_multiple(candidate),
        kalshi_payout_multiple=extract_kalshi_payout_multiple(candidate),
    ):
        reasons.append("Kalshi contract cost basis is missing")
    if optional_float(candidate.get("sportsbook_no_vig_yes")) is None:
        reasons.append("reference probability is missing")
    return "blocked", reasons


def mlb_gate(candidate: dict[str, Any], repo_reasons: list[str]) -> tuple[str, list[str]]:
    reasons = [
        "probability source is sportsbook no-vig reference, not a calibrated platform model",
        "calibrated contract probability is missing",
        *repo_reasons,
    ]
    status = str(candidate.get("status") or "")
    if status != "review_ready":
        reasons.append(f"candidate status is {status or 'unknown'}")
    if not contract_cost_basis_available(
        display_price=optional_float(candidate.get("exchange_ask")),
        explicit_all_in_cost=extract_explicit_all_in_cost(candidate),
        all_in_payout_multiple=extract_all_in_payout_multiple(candidate),
        kalshi_payout_multiple=extract_kalshi_payout_multiple(candidate),
    ):
        reasons.append("exchange contract cost basis is missing")
    if optional_float(candidate.get("sportsbook_prob")) is None:
        reasons.append("reference probability is missing")
    return "blocked", dedupe(reasons)


def mlb_global_reasons(repeatability: dict[str, Any], settled: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    repeatability_status = str(repeatability.get("status") or "")
    if repeatability_status:
        reasons.append(f"repeatability status is {repeatability_status}")
    if repeatability_status in {
        "repeatability_no_signal_clean_packets",
        "repeatability_insufficient_one_clean_packet",
    }:
        reasons.append("repeatability evidence does not support usable contract edges")
    settled_status = str(settled.get("status") or "")
    if settled_status:
        reasons.append(f"settled validation status is {settled_status}")
    if "no_policy_change" in settled_status:
        reasons.append("settled validation does not support a policy change")
    return reasons


def make_ev_row(
    *,
    source_repo_id: str,
    source_artifact: Path,
    source_row_index: int,
    contract_ticker: str,
    event_ticker: str,
    market_ticker: str,
    side: str,
    selection: str,
    market_type: str,
    title: str,
    resolution_rule: str,
    resolution_rule_source: str,
    resolution_rule_status: str,
    display_price: float | None,
    display_price_source: str,
    executable_price_source: str,
    fee_estimate: float | None,
    slippage_buffer: float | None,
    explicit_all_in_cost: float | None,
    all_in_payout_multiple: float | None,
    kalshi_payout_multiple: float | None,
    calibrated_probability: float | None,
    calibrated_probability_source: str,
    calibration_status: str,
    calibrated_probability_source_artifact: str | None,
    calibrated_probability_source_sha256: str | None,
    reference_probability: float | None,
    reference_probability_source: str,
    probability_uncertainty: float | None,
    kalshi_bid: float | None,
    kalshi_ask: float | None,
    kalshi_midpoint: float | None,
    gate_status: str,
    gate_reasons: list[str],
    review_status: str,
    timing_status: str,
    mapping_confidence: str,
    resolution_rule_source_artifact: str | None = None,
    resolution_rule_source_sha256: str | None = None,
) -> dict[str, Any]:
    payout = DEFAULT_BINARY_PAYOUT
    executable_price = display_price
    execution_cost = normalize_kalshi_execution_cost(
        display_price=display_price,
        executable_price=executable_price,
        executable_price_source=executable_price_source,
        explicit_all_in_cost=explicit_all_in_cost,
        fee_inclusive_payout_multiple=all_in_payout_multiple,
        gross_payout_multiple=kalshi_payout_multiple,
        explicit_fee_estimate=fee_estimate,
        slippage_buffer=slippage_buffer,
        payout_if_correct=payout,
        ticker=contract_ticker or event_ticker or market_ticker,
    )
    all_in_cost = execution_cost.all_in_cost
    break_even = execution_cost.break_even_probability
    payout_multiplier_discrepancy = (
        execution_cost.gross_payout_break_even - execution_cost.contract_price_break_even
        if (
            execution_cost.gross_payout_break_even is not None
            and execution_cost.contract_price_break_even is not None
        )
        else None
    )
    effective_hold = (
        break_even - display_price
        if break_even is not None and display_price is not None
        else None
    )
    edge = (
        calibrated_probability - break_even
        if calibrated_probability is not None and break_even is not None
        else None
    )
    expected_value = (
        calibrated_probability * payout - all_in_cost
        if calibrated_probability is not None and all_in_cost is not None
        else None
    )
    expected_roi = safe_divide(expected_value, all_in_cost)
    automatic_reasons = automatic_ev_gate_reasons(
        all_in_break_even=break_even,
        calibrated_probability=calibrated_probability,
        expected_value=expected_value,
        cost_gate_reasons=list(execution_cost.gate_reasons),
        resolution_rule=resolution_rule,
        resolution_rule_status=resolution_rule_status,
    )
    effective_gate_status = ev_gate_status(
        input_gate_status=gate_status,
        automatic_reasons=automatic_reasons,
        edge=edge,
        expected_value=expected_value,
    )
    usable = (
        effective_gate_status == "pass"
        and edge is not None
        and edge > 0.0
        and expected_value is not None
        and expected_value > 0.0
    )
    row_id = stable_id(
        source_repo_id,
        str(source_artifact),
        str(source_row_index),
        contract_ticker,
        side,
    )
    return {
        "row_id": row_id,
        "source_repo_id": source_repo_id,
        "source_artifact": str(source_artifact),
        "source_artifact_sha256": sha256_file(source_artifact),
        "source_row_index": source_row_index,
        "market_ticker": market_ticker or None,
        "event_ticker": event_ticker or None,
        "contract_ticker": contract_ticker or None,
        "side": side,
        "selection": selection or None,
        "market_type": market_type or None,
        "title": title or None,
        "resolution_rule": resolution_rule or None,
        "resolution_rule_source": resolution_rule_source or None,
        "resolution_rule_status": resolution_rule_status or None,
        "resolution_rule_source_artifact": resolution_rule_source_artifact,
        "resolution_rule_source_sha256": resolution_rule_source_sha256,
        "display_price": json_float(display_price),
        "display_price_source": display_price_source,
        "executable_price": json_float(executable_price),
        "executable_price_source": executable_price_source,
        "fee_estimate": json_float(execution_cost.fee_estimate),
        "fee_source": execution_cost.fee_source,
        "fee_rate": json_float(execution_cost.fee_rate),
        "fee_mode": execution_cost.fee_mode,
        "slippage_buffer": json_float(slippage_buffer),
        "all_in_cost": json_float(all_in_cost),
        "gross_execution_cost": json_float(execution_cost.gross_execution_cost),
        "cost_basis_source": execution_cost.cost_basis_source,
        "cost_quality": execution_cost.cost_quality,
        "payout_if_correct": payout,
        "payout_multiple": json_float(kalshi_payout_multiple),
        "kalshi_payout_multiple": json_float(kalshi_payout_multiple),
        "all_in_payout_multiple": json_float(all_in_payout_multiple),
        "payout_multiple_source": payout_multiple_source(
            all_in_payout_multiple=all_in_payout_multiple,
            kalshi_payout_multiple=kalshi_payout_multiple,
        ),
        "contract_price_break_even_probability": json_float(execution_cost.contract_price_break_even),
        "displayed_price_break_even_probability": json_float(execution_cost.display_price_break_even),
        "all_in_break_even_probability": json_float(break_even),
        "payout_implied_break_even_probability": json_float(execution_cost.payout_implied_break_even),
        "gross_payout_implied_break_even_probability": json_float(execution_cost.gross_payout_break_even),
        "fee_inclusive_payout_implied_break_even_probability": json_float(
            execution_cost.fee_inclusive_payout_break_even
        ),
        "payout_multiplier_discrepancy_probability": json_float(payout_multiplier_discrepancy),
        "break_even_probability": json_float(break_even),
        "break_even_source": execution_cost.break_even_source,
        "effective_hold_probability": json_float(effective_hold),
        "calibrated_probability": json_float(calibrated_probability),
        "calibrated_probability_source": calibrated_probability_source,
        "calibration_status": calibration_status,
        "calibrated_probability_source_artifact": calibrated_probability_source_artifact,
        "calibrated_probability_source_sha256": calibrated_probability_source_sha256,
        "estimated_probability": json_float(calibrated_probability),
        "estimated_probability_source": calibrated_probability_source,
        "reference_probability": json_float(reference_probability),
        "reference_probability_source": reference_probability_source,
        "probability_uncertainty": json_float(probability_uncertainty),
        "edge_probability": json_float(edge),
        "margin_probability": json_float(edge),
        "expected_value_per_contract": json_float(expected_value),
        "expected_roi": json_float(expected_roi),
        "kalshi_bid": json_float(kalshi_bid),
        "kalshi_ask": json_float(kalshi_ask),
        "kalshi_midpoint": json_float(kalshi_midpoint),
        "mapping_confidence": mapping_confidence,
        "timing_status": timing_status,
        "review_status": review_status,
        "source_gate_status": gate_status,
        "gate_status": effective_gate_status,
        "gate_reasons": dedupe([*gate_reasons, *automatic_reasons]),
        "usable": usable,
        "research_only": True,
        "execution_enabled": False,
    }


def automatic_ev_gate_reasons(
    *,
    all_in_break_even: float | None,
    calibrated_probability: float | None,
    expected_value: float | None,
    cost_gate_reasons: list[str],
    resolution_rule: str,
    resolution_rule_status: str,
) -> list[str]:
    reasons: list[str] = list(cost_gate_reasons)
    if all_in_break_even is None:
        reasons.append("execution cost basis is missing")
    if not resolution_rule:
        reasons.append("resolution rule is missing")
    elif resolution_rule_status != "verified_official_terms":
        reasons.append("resolution rule is not independently verified")
    if calibrated_probability is None:
        reasons.append("calibrated contract probability is missing")
    elif all_in_break_even is not None and calibrated_probability <= all_in_break_even:
        reasons.append("calibrated probability does not clear execution cost basis")
    if expected_value is not None and expected_value <= 0.0:
        reasons.append("expected value per contract is not positive after all-in cost")
    return reasons


def ev_gate_status(
    *,
    input_gate_status: str,
    automatic_reasons: list[str],
    edge: float | None,
    expected_value: float | None,
) -> str:
    normalized = input_gate_status if input_gate_status in {"pass", "warn", "blocked", "fail"} else "blocked"
    if normalized in {"blocked", "fail"}:
        return normalized
    hard_blockers = {
        "execution cost basis is missing",
        "resolution rule is missing",
        "resolution rule is not independently verified",
        "calibrated contract probability is missing",
    }
    if any(reason in hard_blockers for reason in automatic_reasons):
        return "blocked"
    if any(str(reason).startswith("calibrated probability status is ") for reason in automatic_reasons):
        return "blocked"
    if edge is None or expected_value is None or edge <= 0.0 or expected_value <= 0.0:
        return "warn"
    return normalized


def blocked_feed(
    *,
    repo_id: str,
    repo_path: Path,
    status: str,
    blockers: list[str],
    source_artifacts: list[str],
    ev_readiness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing_sources = [path for path in source_artifacts if Path(path).exists()]
    feed = {
        "repo_id": repo_id,
        "repo_path": str(repo_path),
        "status": status,
        "gate_status": "blocked",
        "row_count": 0,
        "usable_row_count": 0,
        "positive_edge_row_count": 0,
        "blockers": blockers,
        "source_artifacts": existing_sources,
        "source_hashes": {path: sha256_file(Path(path)) for path in existing_sources},
        "ev_readiness": ev_readiness or default_blocked_ev_readiness(repo_id),
        "research_only": True,
        "execution_enabled": False,
    }
    return {"feed": feed, "rows": []}


def rows_feed(
    *,
    repo_id: str,
    repo_path: Path,
    rows: list[dict[str, Any]],
    status: str,
    blockers: list[str],
    source_artifacts: list[str],
) -> dict[str, Any]:
    existing_sources = [path for path in source_artifacts if Path(path).exists()]
    usable_count = sum(1 for row in rows if row.get("usable") is True)
    positive_count = sum(
        1
        for row in rows
        if row.get("edge_probability") is not None and float(row["edge_probability"]) > 0
    )
    gate_status = "pass" if usable_count else "warn" if rows else "blocked"
    feed = {
        "repo_id": repo_id,
        "repo_path": str(repo_path),
        "status": status,
        "gate_status": gate_status,
        "row_count": len(rows),
        "usable_row_count": usable_count,
        "positive_edge_row_count": positive_count,
        "blockers": blockers,
        "source_artifacts": existing_sources,
        "source_hashes": {path: sha256_file(Path(path)) for path in existing_sources},
        "ev_readiness": row_feed_ev_readiness(repo_id=repo_id, rows=rows),
        "research_only": True,
        "execution_enabled": False,
    }
    return {"feed": feed, "rows": rows}


def feed_status(rows: list[dict[str, Any]], prefix: str) -> str:
    if not rows:
        return f"blocked_{prefix}_no_rows"
    if any(row.get("usable") is True for row in rows):
        return f"{prefix}_usable_ev_rows"
    return f"{prefix}_rows_blocked_not_usable"


def row_feed_ev_readiness(*, repo_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    mapped_count = sum(1 for row in rows if row.get("contract_ticker") and row.get("side"))
    verified_terms_count = sum(
        1 for row in rows if row.get("resolution_rule_status") == "verified_official_terms"
    )
    cost_count = sum(1 for row in rows if row.get("all_in_cost") is not None)
    calibrated_count = sum(1 for row in rows if row.get("calibrated_probability") is not None)
    usable_count = sum(1 for row in rows if row.get("usable") is True)
    row_count = len(rows)
    return {
        "contract_mapping_status": (
            "exact_kalshi_contract_rows_present"
            if row_count and mapped_count == row_count
            else "partial_or_missing_contract_mapping"
        ),
        "official_terms_status": (
            "verified_official_terms"
            if row_count and verified_terms_count == row_count
            else "partial_or_missing_official_terms"
        ),
        "execution_cost_status": (
            "fee_aware_all_in_cost_present"
            if row_count and cost_count == row_count
            else "partial_or_missing_execution_cost"
        ),
        "calibrated_probability_status": (
            "calibrated_contract_probabilities_present"
            if row_count and calibrated_count == row_count
            else "missing_calibrated_contract_probability"
        ),
        "row_gate_status": (
            "usable_rows_present"
            if usable_count
            else "blocked_no_usable_rows"
            if row_count
            else "blocked_no_rows"
        ),
        "row_count": row_count,
        "contract_mapped_row_count": mapped_count,
        "verified_official_terms_row_count": verified_terms_count,
        "fee_aware_cost_row_count": cost_count,
        "calibrated_probability_row_count": calibrated_count,
        "usable_row_count": usable_count,
        "exact_next_input": row_feed_exact_next_input(repo_id),
        "next_local_command": row_feed_next_command(repo_id),
    }


def row_feed_exact_next_input(repo_id: str) -> str:
    if repo_id == "predmarket-alpha":
        return (
            "A validated calibrated probability artifact keyed by exact Kalshi ticker/side for the current "
            "Type 2 Predmarket rows, not a sportsbook no-vig reference probability."
        )
    if repo_id == "mlb-platform":
        return (
            "A model-calibrated probability artifact keyed by exact exchange_market_id/side for MLB Type 2 rows, "
            "with timing/mapping gates clean at the row level."
        )
    return "A calibrated probability artifact keyed by exact Kalshi ticker/side."


def row_feed_next_command(repo_id: str) -> str:
    if repo_id == "predmarket-alpha":
        return "cd /home/mrwatson/projects/predmarket-alpha && make kalshi-ev-ledger"
    if repo_id == "mlb-platform":
        return "cd /home/mrwatson/projects/mlb-platform && make macro-status"
    return "make macro-status"


def default_blocked_ev_readiness(repo_id: str) -> dict[str, Any]:
    return {
        "contract_mapping_status": "missing_exact_kalshi_contract_mapping",
        "official_terms_status": "blocked_until_contract_mapping",
        "execution_cost_status": "blocked_until_kalshi_quote",
        "calibrated_probability_status": "missing_or_unmapped_calibrated_probability",
        "row_gate_status": "blocked_no_contract_rows",
        "row_count": 0,
        "contract_mapped_row_count": 0,
        "verified_official_terms_row_count": 0,
        "fee_aware_cost_row_count": 0,
        "calibrated_probability_row_count": 0,
        "usable_row_count": 0,
        "exact_next_input": f"Exact Kalshi ticker/side/rules/quote mapping for {repo_id}.",
        "next_local_command": "make macro-status",
    }


def latest_mlb_type2_evidence(repo_path: Path) -> Path | None:
    artifact_root = repo_path / "docs/codex/artifacts"
    paths = sorted(artifact_root.glob("*/type2-evidence.json"), key=lambda p: (p.stat().st_mtime, str(p)))
    return paths[-1] if paths else None


def load_official_terms_index(paths: list[Path] | None = None) -> dict[str, OfficialKalshiTerms]:
    terms: dict[str, OfficialKalshiTerms] = {}
    for path in official_terms_files(paths):
        raw = read_json_or_none(path)
        if raw is None:
            continue
        path_hash = sha256_file(path)
        for record in iter_kalshi_market_records(raw):
            ticker = str(record.get("ticker") or "").strip()
            resolution_rule = official_resolution_rule(record)
            if not ticker or not resolution_rule:
                continue
            terms[ticker] = {
                "ticker": ticker,
                "event_ticker": str(record.get("event_ticker") or ""),
                "resolution_rule": resolution_rule,
                "source_artifact": str(path),
                "source_sha256": path_hash,
            }
    return terms


def official_terms_files(paths: list[Path] | None = None) -> list[Path]:
    candidates = paths if paths is not None else list(OFFICIAL_TERMS_SNAPSHOT_PATHS)
    files: list[Path] = []
    for candidate in candidates:
        path = candidate.expanduser()
        if path.is_file() and is_official_terms_candidate(path):
            files.append(path)
        elif path.is_dir():
            files.extend(
                file
                for file in path.glob("*.json")
                if file.is_file() and is_official_terms_candidate(file)
            )
    return sorted({file.resolve() for file in files}, key=lambda file: str(file))


def is_official_terms_candidate(path: Path) -> bool:
    name = path.name
    return name.endswith(".json") and any(
        name.startswith(prefix) for prefix in OFFICIAL_TERMS_FILENAME_PREFIXES
    )


def iter_kalshi_market_records(raw: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    stack = [raw]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(reversed(item))
            continue
        if not isinstance(item, dict):
            continue
        if item.get("ticker") and (item.get("rules_primary") or item.get("rules_secondary")):
            records.append(item)
        for key in ("all_scored", "markets", "market_data", "contracts", "data", "results"):
            child = item.get(key)
            if isinstance(child, (dict, list)):
                stack.append(child)
    return records


def official_resolution_rule(record: dict[str, Any]) -> str:
    primary = str(record.get("rules_primary") or "").strip()
    secondary = str(record.get("rules_secondary") or "").strip()
    parts = [part for part in (primary, secondary) if part]
    return " ".join(parts)


def resolution_rule_fields(
    *,
    contract_ticker: str,
    inferred_rule: str,
    inferred_source: str,
    official_terms: dict[str, OfficialKalshiTerms],
) -> dict[str, str | None]:
    terms = official_terms.get(contract_ticker)
    if terms is not None:
        return {
            "resolution_rule": terms["resolution_rule"],
            "resolution_rule_source": "official_kalshi_local_market_snapshot",
            "resolution_rule_status": "verified_official_terms",
            "resolution_rule_source_artifact": terms["source_artifact"],
            "resolution_rule_source_sha256": terms["source_sha256"],
        }
    return {
        "resolution_rule": inferred_rule,
        "resolution_rule_source": inferred_source,
        "resolution_rule_status": "inferred_unverified_official_terms",
        "resolution_rule_source_artifact": None,
        "resolution_rule_source_sha256": None,
    }


def resolution_source_artifacts(rows: list[dict[str, Any]]) -> list[str]:
    artifacts = {
        str(row.get("resolution_rule_source_artifact"))
        for row in rows
        if row.get("resolution_rule_source_artifact")
    }
    return sorted(artifacts)


def load_calibrated_probability_index(
    paths: list[Path] | None = None,
) -> dict[tuple[str, str], CalibratedProbability]:
    overlays: dict[tuple[str, str], CalibratedProbability] = {}
    for path in calibrated_probability_files(paths):
        raw = read_json_or_none(path)
        if raw is None or not safe_probability_overlay(raw):
            continue
        path_hash = sha256_file(path)
        for record in iter_calibrated_probability_records(raw):
            ticker = str(record.get("contract_ticker") or record.get("ticker") or "").strip()
            side = normalize_side(record.get("side"))
            probability = optional_float(record.get("calibrated_probability"))
            calibration_status = str(record.get("calibration_status") or "").strip()
            if (
                not ticker
                or side not in {"yes", "no"}
                or probability is None
                or not 0.0 <= probability <= 1.0
                or calibration_status not in VALID_CALIBRATION_STATUSES
            ):
                continue
            overlays[(ticker, side)] = {
                "contract_ticker": ticker,
                "side": side,
                "calibrated_probability": probability,
                "calibrated_probability_source": str(
                    record.get("calibrated_probability_source")
                    or record.get("model_name")
                    or "local_calibrated_probability_overlay"
                ),
                "calibration_status": calibration_status,
                "probability_uncertainty": optional_float(record.get("probability_uncertainty")),
                "source_artifact": str(path),
                "source_sha256": path_hash,
            }
    return overlays


def load_contract_mapping_index(
    paths: list[Path] | None = None,
) -> dict[str, list[ContractMapping]]:
    mappings_by_key: dict[tuple[str, str, str], ContractMapping] = {}
    for path in contract_mapping_files(paths):
        raw = read_json_or_none(path)
        if raw is None or not safe_probability_overlay(raw):
            continue
        path_hash = sha256_file(path)
        for index, record in enumerate(iter_contract_mapping_records(raw)):
            repo_id = str(record.get("source_repo_id") or record.get("repo_id") or "").strip()
            ticker = str(record.get("contract_ticker") or record.get("ticker") or "").strip()
            side = normalize_side(record.get("side"))
            mapping_status = str(record.get("mapping_status") or "").strip()
            resolution_status = str(record.get("resolution_rule_status") or "").strip()
            if (
                not repo_id
                or not ticker
                or side not in {"yes", "no"}
                or mapping_status not in VALID_CONTRACT_MAPPING_STATUSES
                or resolution_status != "verified_official_terms"
            ):
                continue
            mapping = dict(record)
            mapping["source_repo_id"] = repo_id
            mapping["contract_ticker"] = ticker
            mapping["side"] = side
            mapping["source_artifact"] = str(path)
            mapping["source_sha256"] = path_hash
            mapping["source_row_index"] = index
            mappings_by_key[(repo_id, ticker, side)] = mapping
    mappings: dict[str, list[ContractMapping]] = {}
    for (repo_id, _, _), mapping in sorted(mappings_by_key.items()):
        mappings.setdefault(repo_id, []).append(mapping)
    return mappings


def contract_mapping_files(paths: list[Path] | None = None) -> list[Path]:
    candidates = paths if paths is not None else list(CONTRACT_MAPPING_OVERLAY_PATHS)
    files: list[Path] = []
    for candidate in candidates:
        path = candidate.expanduser()
        if path.is_file() and path.suffix == ".json":
            files.append(path)
        elif path.is_dir():
            files.extend(file for file in path.glob("*.json") if file.is_file())
    return sorted({file.resolve() for file in files}, key=lambda file: str(file))


def iter_contract_mapping_records(raw: dict[str, Any]) -> list[dict[str, Any]]:
    records = raw.get("rows") or raw.get("mappings") or raw.get("contracts") or []
    return [record for record in records if isinstance(record, dict)]


def calibrated_probability_files(paths: list[Path] | None = None) -> list[Path]:
    candidates = paths if paths is not None else list(CALIBRATED_PROBABILITY_OVERLAY_PATHS)
    files: list[Path] = []
    for candidate in candidates:
        path = candidate.expanduser()
        if path.is_file() and path.suffix == ".json":
            files.append(path)
        elif path.is_dir():
            files.extend(file for file in path.glob("*.json") if file.is_file())
    return sorted({file.resolve() for file in files}, key=lambda file: str(file))


def safe_probability_overlay(raw: dict[str, Any]) -> bool:
    safety = raw.get("safety") if isinstance(raw.get("safety"), dict) else {}
    return (
        raw.get("research_only") is True
        and raw.get("execution_enabled") is False
        and safety.get("market_execution") is False
        and safety.get("account_or_order_paths") is False
    )


def safe_research_artifact(raw: dict[str, Any] | None) -> bool:
    if not isinstance(raw, dict):
        return False
    safety = raw.get("safety") if isinstance(raw.get("safety"), dict) else {}
    return (
        (raw.get("research_only") is True or safety.get("research_only") is True)
        and safety.get("provider_api_calls") is False
        and safety.get("paid_calls") is False
        and safety.get("database_writes") is False
        and safety.get("market_execution") is False
        and safety.get("account_or_order_paths") is False
    )


def iter_calibrated_probability_records(raw: dict[str, Any]) -> list[dict[str, Any]]:
    records = raw.get("rows") or raw.get("probabilities") or raw.get("contracts") or []
    return [record for record in records if isinstance(record, dict)]


def calibrated_probability_fields(
    *,
    contract_ticker: str,
    side: str,
    calibrated_probabilities: dict[tuple[str, str], CalibratedProbability],
) -> dict[str, Any]:
    overlay = calibrated_probabilities.get((contract_ticker, normalize_side(side)))
    if overlay is None:
        return {
            "calibrated_probability": None,
            "calibrated_probability_source": "missing_calibrated_contract_probability",
            "calibration_status": "missing",
            "probability_uncertainty": None,
            "source_artifact": None,
            "source_sha256": None,
        }
    source = overlay["calibrated_probability_source"]
    return {
        "calibrated_probability": overlay["calibrated_probability"],
        "calibrated_probability_source": f"local_overlay:{source}",
        "calibration_status": overlay["calibration_status"],
        "probability_uncertainty": overlay["probability_uncertainty"],
        "source_artifact": overlay["source_artifact"],
        "source_sha256": overlay["source_sha256"],
    }


def probability_adjusted_gate_reasons(
    reasons: list[str],
    probability: dict[str, Any],
) -> list[str]:
    if probability.get("calibrated_probability") is None:
        return reasons
    filtered = [
        reason
        for reason in reasons
        if reason
        not in {
            "calibrated contract probability is missing",
            "probability source is sportsbook no-vig reference, not a calibrated platform model",
        }
    ]
    if probability.get("calibration_status") != "validated_calibrated_probability":
        filtered.append(f"calibrated probability status is {probability.get('calibration_status')}")
    return dedupe(filtered)


def normalize_side(value: Any) -> str:
    side = str(value or "").strip().lower()
    if side in {"yes", "y"}:
        return "yes"
    if side in {"no", "n"}:
        return "no"
    return side


def overlay_display_price(mapping: dict[str, Any]) -> float | None:
    for key in ("executable_price", "kalshi_ask", "display_price", "contract_price"):
        price = optional_price_token(mapping.get(key))
        if price is not None and 0.0 < price <= DEFAULT_BINARY_PAYOUT:
            return price
    return None


def contract_mapping_gate(mapping: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    mapping_status = str(mapping.get("mapping_status") or "")
    if mapping_status != "verified_contract_mapping":
        reasons.append(f"contract mapping status is {mapping_status or 'missing'}")
    if str(mapping.get("resolution_rule_status") or "") != "verified_official_terms":
        reasons.append("resolution rule is not independently verified")
    if not mapping.get("resolution_rule"):
        reasons.append("resolution rule is missing")
    if overlay_display_price(mapping) is None and not contract_cost_basis_available(
        display_price=None,
        explicit_all_in_cost=extract_explicit_all_in_cost(mapping),
        all_in_payout_multiple=extract_all_in_payout_multiple(mapping),
        kalshi_payout_multiple=extract_kalshi_payout_multiple(mapping),
    ):
        reasons.append("execution cost basis is missing")
    timing_status = str(mapping.get("timing_status") or "")
    if timing_status and timing_status not in {"clean", "not_applicable", "pregame_clean"}:
        reasons.append(f"timing status is {timing_status}")
    gate_status = "pass" if not reasons else "blocked"
    return gate_status, reasons


def build_overlay_preflight(
    *,
    generated_utc: str | None = None,
    calibrated_probability_paths: list[Path] | None = None,
    contract_mapping_paths: list[Path] | None = None,
    active_universe_path: Path = ACTIVE_UNIVERSE_PATH,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    probability_files = calibrated_probability_files(calibrated_probability_paths)
    mapping_files = contract_mapping_files(contract_mapping_paths)
    probabilities = load_calibrated_probability_index(paths=calibrated_probability_paths)
    mappings = load_contract_mapping_index(paths=contract_mapping_paths)
    mapping_rows = [row for rows in mappings.values() for row in rows]
    mapping_keys = {
        (str(row.get("contract_ticker") or ""), normalize_side(row.get("side")))
        for row in mapping_rows
    }
    probability_keys = set(probabilities)
    joined_keys = sorted(mapping_keys & probability_keys)
    ledger = build_ledger(
        active_universe_path=active_universe_path,
        calibrated_probability_paths=calibrated_probability_paths,
        contract_mapping_paths=contract_mapping_paths,
    )
    mapping_source_paths = {str(row.get("source_artifact") or "") for row in mapping_rows}
    overlay_rows = [
        row
        for row in ledger.get("rows", [])
        if row.get("source_artifact") in mapping_source_paths
    ]
    usable_overlay_rows = [row for row in overlay_rows if row.get("usable") is True]
    gates = overlay_preflight_gates(
        probability_files=probability_files,
        mapping_files=mapping_files,
        probability_count=len(probabilities),
        mapping_count=len(mapping_rows),
        joined_count=len(joined_keys),
        usable_count=len(usable_overlay_rows),
    )
    blocked_gates = [gate for gate in gates if gate["status"] == "blocked"]
    warn_gates = [gate for gate in gates if gate["status"] == "warn"]
    if usable_overlay_rows:
        status = "overlay_preflight_usable_ev_rows_present"
    elif joined_keys:
        status = "overlay_preflight_joined_rows_not_usable"
    elif blocked_gates:
        status = "overlay_preflight_blocked_missing_or_unjoined_inputs"
    elif warn_gates:
        status = "overlay_preflight_warn_only"
    else:
        status = "overlay_preflight_ready"
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "summary": {
            "contract_mapping_file_count": len(mapping_files),
            "calibrated_probability_file_count": len(probability_files),
            "valid_contract_mapping_row_count": len(mapping_rows),
            "valid_calibrated_probability_row_count": len(probabilities),
            "exact_join_row_count": len(joined_keys),
            "overlay_ev_row_count": len(overlay_rows),
            "usable_overlay_ev_row_count": len(usable_overlay_rows),
        },
        "gates": gates,
        "joined_keys": [
            {"contract_ticker": ticker, "side": side}
            for ticker, side in joined_keys[:100]
        ],
        "source_artifacts": {
            "contract_mapping_files": [str(path) for path in mapping_files],
            "calibrated_probability_files": [str(path) for path in probability_files],
        },
        "next_action": overlay_preflight_next_action(
            mapping_count=len(mapping_rows),
            probability_count=len(probabilities),
            joined_count=len(joined_keys),
            usable_count=len(usable_overlay_rows),
        ),
        "safety": {
            "research_only": True,
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "raw_payloads_copied_to_repo": False,
        },
    }


def build_calibration_work_order(
    *,
    generated_utc: str | None = None,
    active_universe_path: Path = ACTIVE_UNIVERSE_PATH,
    max_rows_per_repo: int = 500,
    limit: int = 25,
    calibrated_probability_paths: list[Path] | None = None,
    contract_mapping_paths: list[Path] | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    ledger = build_ledger(
        active_universe_path=active_universe_path,
        max_rows_per_repo=max_rows_per_repo,
        calibrated_probability_paths=calibrated_probability_paths,
        contract_mapping_paths=contract_mapping_paths,
    )
    candidates = [
        calibration_work_order_row(row)
        for row in ledger.get("rows", [])
        if calibration_work_order_candidate(row)
    ]
    candidates.sort(key=calibration_work_order_sort_key)
    selected = candidates[: max(0, limit)]
    direct_pass_ready = [row for row in candidates if calibration_candidate_direct_pass_ready(row)]
    template_rows = [
        {
            "contract_ticker": row["contract_ticker"],
            "side": row["side"],
            "calibrated_probability": None,
            "calibrated_probability_source": "TODO:model_or_validation_artifact",
            "calibration_status": "validated_calibrated_probability",
            "probability_uncertainty": None,
            "source_repo_id": row["source_repo_id"],
            "source_row_id": row["row_id"],
            "notes": "Fill only after a validated calibrated model produces a contract-level probability.",
        }
        for row in selected
    ]
    if direct_pass_ready:
        status = "calibration_work_order_ready"
    elif selected:
        status = "calibration_work_order_ready_source_gated"
    else:
        status = "calibration_work_order_blocked_no_candidate_rows"
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "summary": {
            "ledger_status": ledger.get("status"),
            "ledger_row_count": len(ledger.get("rows", [])),
            "candidate_row_count": len(candidates),
            "selected_row_count": len(selected),
            "direct_pass_ready_candidate_count": len(direct_pass_ready),
            "source_gated_candidate_count": len(candidates) - len(direct_pass_ready),
            "verified_terms_candidate_count": sum(
                1 for row in candidates if row.get("resolution_rule_status") == "verified_official_terms"
            ),
            "non_temporal_mismatch_candidate_count": sum(
                1 for row in candidates if not temporal_mismatch_status(row.get("timing_status"))
            ),
            "usable_ledger_row_count": ledger.get("summary", {}).get("usable_row_count", 0),
        },
        "selection_policy": {
            "purpose": (
                "Queue exact Kalshi contracts that already have terms and execution-cost evidence, "
                "but still need a validated calibrated contract probability."
            ),
            "excludes": [
                "rows with an existing calibrated probability",
                "rows with missing contract ticker or side",
                "rows with unverified official terms",
                "rows with missing all-in break-even probability",
                "rows downgraded for temporal mismatch",
            ],
            "sort": [
                "fewer non-probability blockers",
                "verified official terms",
                "fee-aware all-in cost present",
                "higher mapping confidence",
                "larger absolute gap between reference probability and all-in break-even, for review attention only",
            ],
        },
        "rows": selected,
        "probability_overlay_template": {
            "research_only": True,
            "execution_enabled": False,
            "safety": {
                "market_execution": False,
                "account_or_order_paths": False,
                "provider_api_calls": False,
                "database_writes": False,
            },
            "rows": template_rows,
        },
        "next_action": calibration_work_order_next_action(selected),
        "safety": {
            "research_only": True,
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "raw_payloads_copied_to_repo": False,
        },
    }


def calibration_work_order_candidate(row: dict[str, Any]) -> bool:
    if row.get("calibrated_probability") is not None:
        return False
    if not row.get("contract_ticker") or not row.get("side"):
        return False
    if row.get("resolution_rule_status") != "verified_official_terms":
        return False
    if row.get("all_in_break_even_probability") is None:
        return False
    if temporal_mismatch_status(row.get("timing_status")):
        return False
    return True


def calibration_work_order_row(row: dict[str, Any]) -> dict[str, Any]:
    non_probability_reasons = [
        reason
        for reason in row.get("gate_reasons") or []
        if reason
        not in {
            "probability source is sportsbook no-vig reference, not a calibrated platform model",
            "calibrated contract probability is missing",
        }
    ]
    reference_probability = optional_float(row.get("reference_probability"))
    break_even = optional_float(row.get("all_in_break_even_probability"))
    reference_gap = (
        reference_probability - break_even
        if reference_probability is not None and break_even is not None
        else None
    )
    return {
        "row_id": row.get("row_id"),
        "source_repo_id": row.get("source_repo_id"),
        "source_artifact": row.get("source_artifact"),
        "source_artifact_sha256": row.get("source_artifact_sha256"),
        "source_row_index": row.get("source_row_index"),
        "contract_ticker": row.get("contract_ticker"),
        "event_ticker": row.get("event_ticker"),
        "side": row.get("side"),
        "selection": row.get("selection"),
        "market_type": row.get("market_type"),
        "title": row.get("title"),
        "resolution_rule": row.get("resolution_rule"),
        "resolution_rule_source_artifact": row.get("resolution_rule_source_artifact"),
        "resolution_rule_source_sha256": row.get("resolution_rule_source_sha256"),
        "resolution_rule_status": row.get("resolution_rule_status"),
        "display_price": row.get("display_price"),
        "all_in_break_even_probability": row.get("all_in_break_even_probability"),
        "break_even_source": row.get("break_even_source"),
        "fee_estimate": row.get("fee_estimate"),
        "fee_source": row.get("fee_source"),
        "effective_hold_probability": row.get("effective_hold_probability"),
        "reference_probability": row.get("reference_probability"),
        "reference_probability_source": row.get("reference_probability_source"),
        "reference_minus_break_even_probability": json_float(reference_gap),
        "timing_status": row.get("timing_status"),
        "review_status": row.get("review_status"),
        "mapping_confidence": row.get("mapping_confidence"),
        "current_gate_status": row.get("gate_status"),
        "source_gate_status": row.get("source_gate_status"),
        "non_probability_gate_reasons": non_probability_reasons,
        "minimum_probability_to_clear": row.get("all_in_break_even_probability"),
        "required_overlay_key": {
            "contract_ticker": row.get("contract_ticker"),
            "side": row.get("side"),
        },
    }


def calibration_candidate_direct_pass_ready(row: dict[str, Any]) -> bool:
    return row.get("source_gate_status") == "pass" and not row.get("non_probability_gate_reasons")


def temporal_mismatch_status(value: Any) -> bool:
    return "temporal_mismatch" in str(value or "").lower()


def calibration_work_order_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    reasons = row.get("non_probability_gate_reasons") or []
    confidence_rank = {"high": 0, "operator_verified": 0, "medium": 1, "manual_overlay": 1}
    mapping_rank = confidence_rank.get(str(row.get("mapping_confidence") or "").lower(), 2)
    reference_gap = optional_float(row.get("reference_minus_break_even_probability"))
    attention_gap = abs(reference_gap) if reference_gap is not None else -1.0
    return (
        len(reasons),
        0 if row.get("resolution_rule_status") == "verified_official_terms" else 1,
        0 if row.get("all_in_break_even_probability") is not None else 1,
        mapping_rank,
        -attention_gap,
        str(row.get("source_repo_id") or ""),
        str(row.get("contract_ticker") or ""),
        str(row.get("side") or ""),
    )


def calibration_work_order_next_action(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return (
            "No calibration candidates are ready. Collect exact contracts with verified terms, "
            "clean timing, and all-in execution costs before requesting calibrated probabilities."
        )
    if not any(calibration_candidate_direct_pass_ready(row) for row in rows):
        return (
            "Current exact contract rows still have non-probability source gates, so probabilities alone "
            "will not create usable EV rows. Use the contract-mapping work order for a pass-ready repo lane "
            "or clear the source gates before filling calibrated probabilities."
        )
    return (
        "Send the probability_overlay_template rows to the appropriate model repo or worker. "
        "Write the filled safe overlay under /home/mrwatson/manual_drops/kalshi_ev_probabilities/, "
        "then run make kalshi-ev-overlay-preflight && make kalshi-ev-ledger."
    )


def build_contract_mapping_work_order(
    *,
    generated_utc: str | None = None,
    limit: int = 32,
    nfl_fair_line_path: Path = DEFAULT_NFL_FAIR_LINE_REVIEW_PATH,
    nfl_validation_paths: list[Path] | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    validation_paths = nfl_validation_paths or [
        DEFAULT_NFL_HISTORICAL_LINE_BACKTEST_PATH,
        DEFAULT_NFL_HISTORICAL_LINE_VALIDATION_PATH,
    ]
    fair_line = read_json_or_none(nfl_fair_line_path)
    validation_artifacts = [
        {
            "path": str(path),
            "sha256": sha256_file(path),
            "status": (read_json_or_none(path) or {}).get("status"),
        }
        for path in validation_paths
        if path.is_file()
    ]
    gates = contract_mapping_work_order_gates(
        fair_line=fair_line,
        fair_line_path=nfl_fair_line_path,
        validation_artifacts=validation_artifacts,
    )
    if not safe_research_artifact(fair_line):
        selected: list[dict[str, Any]] = []
    else:
        selected = nfl_contract_mapping_candidates(
            fair_line=fair_line or {},
            source_path=nfl_fair_line_path,
        )[: max(0, limit)]
    status = (
        "contract_mapping_work_order_ready"
        if selected and all(gate["status"] != "blocked" for gate in gates)
        else "contract_mapping_work_order_blocked_missing_model_source"
    )
    mapping_template_rows = [contract_mapping_template_row(row) for row in selected]
    probability_template_rows = [contract_mapping_probability_template_row(row) for row in selected]
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "summary": {
            "source_repo_id": "nfl_quant_glm51_greenfield",
            "source_artifact": str(nfl_fair_line_path),
            "source_sha256": sha256_file(nfl_fair_line_path),
            "model_row_count": len((fair_line or {}).get("rows") or []) if isinstance(fair_line, dict) else 0,
            "selected_contract_side_count": len(selected),
            "validation_artifact_count": len(validation_artifacts),
            "selected_home_side_count": sum(1 for row in selected if row.get("team_role") == "home"),
            "selected_away_side_count": sum(1 for row in selected if row.get("team_role") == "away"),
        },
        "selection_policy": {
            "purpose": (
                "Bridge a model repo that has calibrated probabilities but no exact Kalshi contract mapping. "
                "This is a mapping assignment, not an EV claim."
            ),
            "requires_before_evidence": [
                "exact Kalshi contract_ticker",
                "side",
                "official Kalshi resolution terms from a local snapshot",
                "executable price or all-in cost basis",
                "clean timing status",
                "matching calibrated-probability overlay keyed by the exact ticker and side",
            ],
            "sort": [
                "larger absolute model-vs-consensus probability delta first",
                "home and away moneyline sides emitted separately",
            ],
        },
        "validation_artifacts": validation_artifacts,
        "gates": gates,
        "rows": selected,
        "contract_mapping_overlay_template": {
            "template_only": True,
            "research_only": True,
            "execution_enabled": False,
            "safety": {
                "market_execution": False,
                "account_or_order_paths": False,
                "provider_api_calls": False,
                "database_writes": False,
            },
            "rows": mapping_template_rows,
        },
        "calibrated_probability_overlay_template": {
            "template_only": True,
            "research_only": True,
            "execution_enabled": False,
            "safety": {
                "market_execution": False,
                "account_or_order_paths": False,
                "provider_api_calls": False,
                "database_writes": False,
            },
            "rows": probability_template_rows,
        },
        "next_action": contract_mapping_work_order_next_action(selected),
        "safety": {
            "research_only": True,
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "raw_payloads_copied_to_repo": False,
        },
    }


def contract_mapping_work_order_gates(
    *,
    fair_line: dict[str, Any] | None,
    fair_line_path: Path,
    validation_artifacts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    safe = safe_research_artifact(fair_line)
    row_count = len(fair_line.get("rows") or []) if isinstance(fair_line, dict) else 0
    return [
        {
            "name": "nfl_fair_line_review_present",
            "status": "pass" if fair_line_path.is_file() else "blocked",
            "reasons": [f"Found {fair_line_path}."]
            if fair_line_path.is_file()
            else [f"Missing {fair_line_path}."],
        },
        {
            "name": "nfl_fair_line_review_safe",
            "status": "pass" if safe else "blocked",
            "reasons": ["NFL fair-line review is research-only and execution-disabled."]
            if safe
            else ["NFL fair-line review is missing safety flags or is unsafe."],
        },
        {
            "name": "nfl_calibrated_model_rows_present",
            "status": "pass" if row_count else "blocked",
            "reasons": [f"Found {row_count} NFL model row(s)."]
            if row_count
            else ["No NFL model rows found."],
        },
        {
            "name": "nfl_validation_artifacts_present",
            "status": "pass" if validation_artifacts else "warn",
            "reasons": [f"Found {len(validation_artifacts)} validation artifact(s)."]
            if validation_artifacts
            else ["No historical validation artifacts were found beside the fair-line review."],
        },
    ]


def nfl_contract_mapping_candidates(
    *,
    fair_line: dict[str, Any],
    source_path: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(fair_line.get("rows") or []):
        if not isinstance(row, dict) or row.get("model_calibration_active") is not True:
            continue
        home_prob = optional_float(row.get("model_prob_home"))
        away_prob = optional_float(row.get("model_prob_away"))
        market_home = optional_float(row.get("market_prob_home"))
        sides = [
            ("home", row.get("home_team"), row.get("away_team"), home_prob, market_home),
            (
                "away",
                row.get("away_team"),
                row.get("home_team"),
                away_prob,
                1.0 - market_home if market_home is not None else None,
            ),
        ]
        for role, team, opponent, probability, market_probability in sides:
            if probability is None or not team or not opponent:
                continue
            delta = (
                probability - market_probability
                if market_probability is not None
                else None
            )
            rows.append(
                {
                    "source_repo_id": "nfl_quant_glm51_greenfield",
                    "source_artifact": str(source_path),
                    "source_artifact_sha256": sha256_file(source_path),
                    "source_row_index": index,
                    "season": row.get("season"),
                    "week": row.get("week"),
                    "game": row.get("game"),
                    "home_team": row.get("home_team"),
                    "away_team": row.get("away_team"),
                    "team_role": role,
                    "selection": str(team),
                    "opponent": str(opponent),
                    "market_type": "nfl_game_moneyline",
                    "model_calibrated_probability": json_float(probability),
                    "market_reference_probability": json_float(market_probability),
                    "model_minus_market_probability": json_float(delta),
                    "model_probability_source": row.get("model_prob_source"),
                    "model_probability_detail": row.get("model_prob_detail"),
                    "model_calibration_source": row.get("model_calibration_source"),
                    "model_calibration_detail": row.get("model_calibration_detail"),
                    "model_calibration_active": row.get("model_calibration_active"),
                    "suggested_calibration_status": "validated_calibrated_probability",
                    "required_contract_mapping_fields": [
                        "contract_ticker",
                        "side",
                        "resolution_rule",
                        "resolution_rule_status=verified_official_terms",
                        "executable_price or all_in_cost or payout_multiple",
                        "timing_status=clean",
                    ],
                }
            )
    rows.sort(
        key=lambda item: (
            -abs(optional_float(item.get("model_minus_market_probability")) or 0.0),
            str(item.get("game") or ""),
            str(item.get("selection") or ""),
        )
    )
    return rows


def contract_mapping_template_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_repo_id": row.get("source_repo_id"),
        "contract_ticker": "TODO:exact_kalshi_contract_ticker",
        "event_ticker": "TODO:exact_kalshi_event_ticker",
        "side": "yes",
        "selection": row.get("selection"),
        "market_type": row.get("market_type"),
        "title": f"{row.get('selection')} to beat {row.get('opponent')}",
        "mapping_status": "TODO:verified_contract_mapping",
        "mapping_confidence": "TODO:operator_verified",
        "resolution_rule_status": "TODO:verified_official_terms",
        "resolution_rule": "TODO:paste official Kalshi rules for this exact contract",
        "resolution_rule_source": "TODO:local_kalshi_snapshot_path",
        "executable_price": None,
        "kalshi_payout_multiple": None,
        "all_in_cost": None,
        "timing_status": "TODO:clean",
        "source_model_artifact": row.get("source_artifact"),
        "source_model_row_index": row.get("source_row_index"),
        "notes": "Template row only. Replace TODO values before saving under manual_drops.",
    }


def contract_mapping_probability_template_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_ticker": "TODO:exact_kalshi_contract_ticker",
        "side": "yes",
        "calibrated_probability": row.get("model_calibrated_probability"),
        "calibrated_probability_source": (
            "nfl_quant_glm51_greenfield:"
            f"{row.get('model_probability_source')}:{row.get('model_calibration_source')}"
        ),
        "calibration_status": "TODO:validated_calibrated_probability",
        "probability_uncertainty": None,
        "source_repo_id": row.get("source_repo_id"),
        "source_model_artifact": row.get("source_artifact"),
        "source_model_row_index": row.get("source_row_index"),
        "model_calibration_detail": row.get("model_calibration_detail"),
        "notes": "Template row only. Replace contract_ticker and calibration_status after exact mapping verification.",
    }


def contract_mapping_work_order_next_action(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return (
            "No model rows are ready for contract mapping. Refresh the source model lane or provide "
            "a safe model probability artifact first."
        )
    return (
        "Fill exact Kalshi ticker, official terms, clean timing status, and executable cost for one "
        "selected NFL row; write matching contract-mapping and calibrated-probability overlays under "
        "/home/mrwatson/manual_drops/kalshi_ev_contract_mappings/ and "
        "/home/mrwatson/manual_drops/kalshi_ev_probabilities/, then rerun overlay preflight and the EV ledger."
    )


def overlay_preflight_gates(
    *,
    probability_files: list[Path],
    mapping_files: list[Path],
    probability_count: int,
    mapping_count: int,
    joined_count: int,
    usable_count: int,
) -> list[dict[str, Any]]:
    return [
        {
            "name": "contract_mapping_files_present",
            "status": "pass" if mapping_files else "blocked",
            "reasons": [f"Found {len(mapping_files)} contract-mapping overlay file(s)."]
            if mapping_files
            else ["No contract-mapping overlay files found."],
        },
        {
            "name": "calibrated_probability_files_present",
            "status": "pass" if probability_files else "blocked",
            "reasons": [f"Found {len(probability_files)} calibrated-probability overlay file(s)."]
            if probability_files
            else ["No calibrated-probability overlay files found."],
        },
        {
            "name": "valid_contract_mapping_rows_present",
            "status": "pass" if mapping_count else "blocked",
            "reasons": [f"Loaded {mapping_count} valid contract-mapping row(s)."]
            if mapping_count
            else ["No safe, verified contract-mapping rows loaded."],
        },
        {
            "name": "valid_calibrated_probability_rows_present",
            "status": "pass" if probability_count else "blocked",
            "reasons": [f"Loaded {probability_count} valid calibrated-probability row(s)."]
            if probability_count
            else ["No safe calibrated-probability rows loaded."],
        },
        {
            "name": "exact_ticker_side_join_present",
            "status": "pass" if joined_count else "blocked",
            "reasons": [f"Found {joined_count} exact contract_ticker/side join(s)."]
            if joined_count
            else ["No mapping/probability rows join on exact contract_ticker and side."],
        },
        {
            "name": "usable_overlay_ev_rows_present",
            "status": "pass" if usable_count else "warn",
            "reasons": [f"Found {usable_count} usable overlay EV row(s)."]
            if usable_count
            else ["No overlay EV rows are usable yet."],
        },
    ]


def overlay_preflight_next_action(
    *,
    mapping_count: int,
    probability_count: int,
    joined_count: int,
    usable_count: int,
) -> str:
    if usable_count:
        return "Review the usable overlay EV rows in the ledger; execution remains disabled."
    if not mapping_count:
        return (
            "Drop a safe contract-mapping overlay under "
            "/home/mrwatson/manual_drops/kalshi_ev_contract_mappings/."
        )
    if not probability_count:
        return (
            "Drop a safe calibrated-probability overlay under "
            "/home/mrwatson/manual_drops/kalshi_ev_probabilities/."
        )
    if not joined_count:
        return "Fix overlay contract_ticker/side keys so mapping and probability rows join exactly."
    return "Joined overlay rows exist but are not usable; inspect row gate reasons in the EV ledger."


def mapping_confidence(candidate: dict[str, Any]) -> str:
    mode = str(candidate.get("game_id_match_mode") or "")
    if "exact" in mode:
        return "high"
    if "tolerance" in mode:
        return "medium"
    return "unknown"


def predmarket_selection(candidate: dict[str, Any]) -> str:
    return str(
        candidate.get("team")
        or contract_selection(str(candidate.get("kalshi_ticker") or ""))
        or candidate.get("title")
        or ""
    )


def predmarket_resolution_rule(candidate: dict[str, Any]) -> str:
    ticker = str(candidate.get("kalshi_ticker") or "")
    event = str(candidate.get("event_ticker") or event_from_contract(ticker) or "")
    selection = predmarket_selection(candidate)
    title = str(candidate.get("title") or "")
    return (
        f"YES resolves according to official Kalshi contract terms for {ticker or 'unknown contract'}; "
        f"candidate selection={selection or 'unknown'}; event={event or 'unknown'}; title={title or 'unknown'}."
    )


def mlb_resolution_rule(candidate: dict[str, Any]) -> str:
    market = str(candidate.get("market") or "unknown")
    selection = str(candidate.get("selection") or "unknown")
    contract = str(candidate.get("exchange_market_id") or "unknown contract")
    game_id = str(candidate.get("game_id") or "unknown game")
    line = candidate.get("line")
    line_text = "none" if line is None else str(line)
    return (
        f"YES resolves according to official Kalshi contract terms for {contract}; "
        f"game_id={game_id}; market={market}; selection={selection}; line={line_text}."
    )


def next_action(feeds: list[dict[str, Any]], rows: list[dict[str, Any]]) -> str:
    usable = [row for row in rows if row.get("usable") is True]
    if usable:
        return "Review usable rows manually; execution remains disabled until a separate explicit decision gate exists."
    if rows:
        return (
            "Rows exist, but none are usable EV edges. Add calibrated contract probabilities, "
            "clear timing/mapping gates, and executable Kalshi contract cost bases before considering "
            "any row usable. Order-ticket payout multipliers supply the gross fill hurdle when present; "
            "the official fee model supplies the default fee estimate."
        )
    missing = ", ".join(feed["repo_id"] for feed in feeds if feed.get("row_count") == 0)
    return f"No repo emits usable Kalshi contract EV rows yet. Build contract mappings for: {missing}."


def write_ledger(ledger: dict[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-contract-ev-ledger.json"
    md_path = out_dir / "kalshi-contract-ev-ledger.md"
    csv_path = out_dir / "kalshi-contract-ev-ledger.csv"
    json_path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(ledger), encoding="utf-8")
    write_rows_csv(ledger.get("rows", []), csv_path)
    latest_json = MACRO_DIR / "latest-kalshi-contract-ev-ledger.json"
    latest_md = MACRO_DIR / "latest-kalshi-contract-ev-ledger.md"
    latest_json.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest_md.write_text(render_markdown(ledger), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
    }


def write_overlay_preflight(
    report: dict[str, Any],
    out_dir: Path = DEFAULT_OVERLAY_PREFLIGHT_OUT_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-ev-overlay-preflight.json"
    md_path = out_dir / "kalshi-ev-overlay-preflight.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_overlay_preflight_markdown(report), encoding="utf-8")
    latest_json = MACRO_DIR / "latest-kalshi-ev-overlay-preflight.json"
    latest_md = MACRO_DIR / "latest-kalshi-ev-overlay-preflight.md"
    latest_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest_md.write_text(render_overlay_preflight_markdown(report), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
    }


def write_calibration_work_order(
    report: dict[str, Any],
    out_dir: Path = DEFAULT_CALIBRATION_WORK_ORDER_OUT_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-ev-calibration-work-order.json"
    md_path = out_dir / "kalshi-ev-calibration-work-order.md"
    template_path = out_dir / "kalshi-ev-calibrated-probability-template.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_calibration_work_order_markdown(report), encoding="utf-8")
    template_path.write_text(
        json.dumps(report.get("probability_overlay_template") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-ev-calibration-work-order.json"
    latest_md = MACRO_DIR / "latest-kalshi-ev-calibration-work-order.md"
    latest_template = MACRO_DIR / "latest-kalshi-ev-calibrated-probability-template.json"
    latest_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest_md.write_text(render_calibration_work_order_markdown(report), encoding="utf-8")
    latest_template.write_text(
        json.dumps(report.get("probability_overlay_template") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "template_path": str(template_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
        "latest_template_path": str(latest_template),
    }


def write_contract_mapping_work_order(
    report: dict[str, Any],
    out_dir: Path = DEFAULT_CONTRACT_MAPPING_WORK_ORDER_OUT_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-ev-contract-mapping-work-order.json"
    md_path = out_dir / "kalshi-ev-contract-mapping-work-order.md"
    mapping_template_path = out_dir / "kalshi-ev-contract-mapping-template.json"
    probability_template_path = out_dir / "kalshi-ev-contract-mapped-probability-template.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_contract_mapping_work_order_markdown(report), encoding="utf-8")
    mapping_template_path.write_text(
        json.dumps(report.get("contract_mapping_overlay_template") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    probability_template_path.write_text(
        json.dumps(report.get("calibrated_probability_overlay_template") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-ev-contract-mapping-work-order.json"
    latest_md = MACRO_DIR / "latest-kalshi-ev-contract-mapping-work-order.md"
    latest_mapping_template = MACRO_DIR / "latest-kalshi-ev-contract-mapping-template.json"
    latest_probability_template = MACRO_DIR / "latest-kalshi-ev-contract-mapped-probability-template.json"
    latest_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest_md.write_text(render_contract_mapping_work_order_markdown(report), encoding="utf-8")
    latest_mapping_template.write_text(
        json.dumps(report.get("contract_mapping_overlay_template") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    latest_probability_template.write_text(
        json.dumps(report.get("calibrated_probability_overlay_template") or {}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "mapping_template_path": str(mapping_template_path),
        "probability_template_path": str(probability_template_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
        "latest_mapping_template_path": str(latest_mapping_template),
        "latest_probability_template_path": str(latest_probability_template),
    }


def render_markdown(ledger: dict[str, Any]) -> str:
    summary = ledger.get("summary", {})
    lines = [
        "# Kalshi Contract EV Ledger",
        "",
        f"- Status: `{ledger.get('status')}`",
        f"- Research only: `{str(ledger.get('research_only')).lower()}`",
        f"- Rows: `{summary.get('row_count')}`",
        f"- Usable rows: `{summary.get('usable_row_count')}`",
        f"- Positive-edge rows: `{summary.get('positive_edge_row_count')}`",
        f"- Verified official resolution-rule rows: `{summary.get('verified_resolution_rule_row_count')}`",
        f"- Inferred resolution-rule rows: `{summary.get('inferred_resolution_rule_row_count')}`",
        f"- Missing calibrated-probability rows: `{summary.get('missing_calibrated_probability_row_count')}`",
        f"- Local calibrated-probability overlay rows: `{summary.get('calibrated_probability_overlay_row_count')}`",
        f"- Local contract-mapping overlay rows: `{summary.get('contract_mapping_overlay_row_count')}`",
        "",
        "## Contract Math",
        "",
        "- `contract_price_break_even_probability = executable_price`",
        "- `displayed_price_break_even_probability = display_price`",
        "- `all_in_break_even_probability` uses explicit all-in cost first, then fee-inclusive payout multiple, then gross ticket payout plus explicit/official fee estimate, then executable price plus explicit/official fee estimate.",
        "- `break_even_probability` is an alias for `all_in_break_even_probability`",
        "- `payout_implied_break_even_probability = 1 / payout_multiple` when a ticket/order payout is present.",
        "- `all_in_cost` follows the same cost-basis hierarchy as `all_in_break_even_probability`.",
        "- `effective_hold_probability = break_even_probability - display_price`",
        "- `margin_probability = calibrated_probability - break_even_probability`",
        "- `expected_value_per_contract = calibrated_probability * payout_if_correct - all_in_cost`",
        "- `resolution_rule_status = verified_official_terms` is required before a row can be usable.",
        "- `resolution_rule_source_artifact` records the local Kalshi snapshot used to verify official terms when available.",
        "- The EV hurdle is the captured execution cost basis, not the prettiest screen number.",
        "",
        "## Repo Feeds",
        "",
        "| Repo | Status | Rows | Usable | EV Readiness | Next Input |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for feed in ledger.get("repo_feeds", []):
        readiness = feed.get("ev_readiness") or {}
        readiness_text = "; ".join(
            [
                f"contracts={readiness.get('contract_mapping_status')}",
                f"terms={readiness.get('official_terms_status')}",
                f"cost={readiness.get('execution_cost_status')}",
                f"prob={readiness.get('calibrated_probability_status')}",
                f"gates={readiness.get('row_gate_status')}",
            ]
        )
        next_input = str(readiness.get("exact_next_input") or "; ".join(feed.get("blockers") or ""))[:260]
        lines.append(
            f"| `{feed.get('repo_id')}` | `{feed.get('status')}` | "
            f"{feed.get('row_count')} | {feed.get('usable_row_count')} | {readiness_text} | {next_input} |"
        )
    top_reasons = summary.get("top_blocked_row_reasons") or []
    if top_reasons:
        lines.extend(["", "## Top Row Blockers", ""])
        for item in top_reasons[:8]:
            lines.append(f"- `{item.get('count')}`: {item.get('reason')}")
    lines.extend(["", "## Next Action", "", str(ledger.get("next_action", "")), ""])
    return "\n".join(lines)


def render_overlay_preflight_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Kalshi EV Overlay Preflight",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Research only: `{str(report.get('research_only')).lower()}`",
        f"- Contract-mapping files: `{summary.get('contract_mapping_file_count')}`",
        f"- Probability files: `{summary.get('calibrated_probability_file_count')}`",
        f"- Valid contract-mapping rows: `{summary.get('valid_contract_mapping_row_count')}`",
        f"- Valid calibrated-probability rows: `{summary.get('valid_calibrated_probability_row_count')}`",
        f"- Exact joins: `{summary.get('exact_join_row_count')}`",
        f"- Overlay EV rows: `{summary.get('overlay_ev_row_count')}`",
        f"- Usable overlay EV rows: `{summary.get('usable_overlay_ev_row_count')}`",
        "",
        "## Gates",
        "",
        "| Gate | Status | Reasons |",
        "| --- | --- | --- |",
    ]
    for gate in report.get("gates", []):
        reasons = "; ".join(gate.get("reasons") or [])
        lines.append(f"| `{gate.get('name')}` | `{gate.get('status')}` | {reasons} |")
    lines.extend(["", "## Next Action", "", str(report.get("next_action") or ""), ""])
    return "\n".join(lines)


def render_calibration_work_order_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Kalshi EV Calibration Work Order",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Research only: `{str(report.get('research_only')).lower()}`",
        f"- Ledger status: `{summary.get('ledger_status')}`",
        f"- Ledger rows: `{summary.get('ledger_row_count')}`",
        f"- Candidate rows: `{summary.get('candidate_row_count')}`",
        f"- Selected rows: `{summary.get('selected_row_count')}`",
        f"- Usable ledger rows today: `{summary.get('usable_ledger_row_count')}`",
        "",
        "## Selected Contracts",
        "",
        "| Repo | Contract | Side | Break-even | Reference | Timing | Remaining Non-Probability Reasons |",
        "| --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for row in report.get("rows", []):
        reasons = "; ".join(row.get("non_probability_gate_reasons") or [])
        lines.append(
            f"| `{row.get('source_repo_id')}` | `{row.get('contract_ticker')}` | `{row.get('side')}` | "
            f"{row.get('all_in_break_even_probability')} | {row.get('reference_probability')} | "
            f"`{row.get('timing_status')}` | {reasons or 'none'} |"
        )
    lines.extend(
        [
            "",
            "## Probability Overlay Template",
            "",
            "The JSON template is written beside this report and to "
            "`docs/codex/macro/latest-kalshi-ev-calibrated-probability-template.json`.",
            "",
            "A filled overlay belongs under `/home/mrwatson/manual_drops/kalshi_ev_probabilities/`, "
            "not in the repo, and must keep `research_only=true`, `execution_enabled=false`, "
            "and account/order/market execution flags false.",
            "",
            "## Next Action",
            "",
            str(report.get("next_action") or ""),
            "",
        ]
    )
    return "\n".join(lines)


def render_contract_mapping_work_order_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Kalshi EV Contract Mapping Work Order",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Research only: `{str(report.get('research_only')).lower()}`",
        f"- Source repo: `{summary.get('source_repo_id')}`",
        f"- Model rows: `{summary.get('model_row_count')}`",
        f"- Selected contract sides: `{summary.get('selected_contract_side_count')}`",
        f"- Validation artifacts: `{summary.get('validation_artifact_count')}`",
        "",
        "## Selected NFL Rows",
        "",
        "| Game | Selection | Probability | Market Reference | Delta | Calibration | Required Next Fact |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for row in report.get("rows", []):
        lines.append(
            f"| `{row.get('game')}` | `{row.get('selection')}` | "
            f"{row.get('model_calibrated_probability')} | {row.get('market_reference_probability')} | "
            f"{row.get('model_minus_market_probability')} | `{row.get('model_calibration_source')}` | "
            "exact Kalshi ticker + official terms + executable cost |"
        )
    lines.extend(
        [
            "",
            "## Templates",
            "",
            "- Contract mapping template: `docs/codex/macro/latest-kalshi-ev-contract-mapping-template.json`",
            "- Matching probability template: `docs/codex/macro/latest-kalshi-ev-contract-mapped-probability-template.json`",
            "",
            "Both templates are marked `template_only=true` and use TODO statuses so they are not evidence. "
            "Filled overlays belong under `/home/mrwatson/manual_drops/kalshi_ev_contract_mappings/` and "
            "`/home/mrwatson/manual_drops/kalshi_ev_probabilities/`.",
            "",
            "## Next Action",
            "",
            str(report.get("next_action") or ""),
            "",
        ]
    )
    return "\n".join(lines)


def write_rows_csv(rows: list[dict[str, Any]], path: Path) -> None:
    columns = [
        "row_id",
        "source_repo_id",
        "contract_ticker",
        "side",
        "resolution_rule",
        "resolution_rule_source",
        "resolution_rule_status",
        "resolution_rule_source_artifact",
        "resolution_rule_source_sha256",
        "display_price",
        "executable_price",
        "gross_execution_cost",
        "fee_estimate",
        "fee_source",
        "fee_rate",
        "fee_mode",
        "all_in_cost",
        "cost_basis_source",
        "cost_quality",
        "payout_if_correct",
        "payout_multiple",
        "all_in_payout_multiple",
        "payout_multiple_source",
        "contract_price_break_even_probability",
        "displayed_price_break_even_probability",
        "all_in_break_even_probability",
        "payout_implied_break_even_probability",
        "gross_payout_implied_break_even_probability",
        "fee_inclusive_payout_implied_break_even_probability",
        "payout_multiplier_discrepancy_probability",
        "break_even_probability",
        "break_even_source",
        "effective_hold_probability",
        "calibrated_probability",
        "calibration_status",
        "calibrated_probability_source_artifact",
        "calibrated_probability_source_sha256",
        "reference_probability",
        "estimated_probability",
        "edge_probability",
        "margin_probability",
        "expected_value_per_contract",
        "expected_roi",
        "source_gate_status",
        "gate_status",
        "usable",
        "review_status",
        "timing_status",
        "mapping_confidence",
        "source_artifact",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column) for column in columns})


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_or_none(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    raw = read_json(path)
    return raw if isinstance(raw, dict) else None


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    raw = digest.hexdigest()
    return "sha256:" + " ".join(raw[index : index + 8] for index in range(0, len(raw), 8))


def stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


def optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def extract_kalshi_payout_multiple(row: dict[str, Any]) -> float | None:
    for key in KALSHI_PAYOUT_MULTIPLE_KEYS:
        multiple = optional_numeric_token(row.get(key))
        if multiple is not None and multiple > MIN_VALID_PAYOUT_MULTIPLE:
            return multiple
    return None


def extract_all_in_payout_multiple(row: dict[str, Any]) -> float | None:
    for key in ALL_IN_PAYOUT_MULTIPLE_KEYS:
        multiple = optional_numeric_token(row.get(key))
        if multiple is not None and multiple > MIN_VALID_PAYOUT_MULTIPLE:
            return multiple
    return None


def extract_explicit_all_in_cost(row: dict[str, Any]) -> float | None:
    for key in EXPLICIT_ALL_IN_COST_KEYS:
        cost = optional_price_token(row.get(key))
        if cost is not None and 0.0 < cost <= DEFAULT_BINARY_PAYOUT:
            return cost
    return None


def contract_cost_basis_available(
    *,
    display_price: float | None,
    explicit_all_in_cost: float | None,
    all_in_payout_multiple: float | None,
    kalshi_payout_multiple: float | None,
) -> bool:
    return (
        display_price is not None
        or explicit_all_in_cost is not None
        or all_in_payout_multiple is not None
        or kalshi_payout_multiple is not None
    )


def payout_multiple_source(
    *,
    all_in_payout_multiple: float | None,
    kalshi_payout_multiple: float | None,
) -> str | None:
    if all_in_payout_multiple is not None:
        return "kalshi_fee_inclusive_payout"
    if kalshi_payout_multiple is not None:
        return "kalshi_ticket_payout_gross"
    return None


def optional_price_token(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        token = value.strip().lower().replace(",", "")
        if token.endswith("¢"):
            cents = optional_float(token[:-1].strip())
            return cents / 100.0 if cents is not None else None
        if token.endswith(" cents"):
            cents = optional_float(token[: -len(" cents")].strip())
            return cents / 100.0 if cents is not None else None
        if token.startswith("$"):
            return optional_float(token[1:].strip())
    return optional_numeric_token(value)


def optional_numeric_token(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        token = value.strip().lower().replace(",", "")
        if token.endswith("x"):
            token = token[:-1].strip()
        if token.endswith("%"):
            parsed = optional_float(token[:-1].strip())
            return parsed / 100.0 if parsed is not None else None
        return optional_float(token)
    return optional_float(value)


def json_float(value: float | None) -> float | None:
    if value is None:
        return None
    return float(value) if math.isfinite(float(value)) else None


def safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def event_from_contract(contract: str) -> str:
    if "-" not in contract:
        return contract
    return "-".join(contract.split("-")[:-1])


def contract_selection(contract: str) -> str:
    if "-" not in contract:
        return ""
    return contract.rsplit("-", 1)[-1]


def disposition_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("kalshi_ticker") or ""), str(row.get("reference_id") or ""))


def dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value)
        if text and text not in seen:
            out.append(text)
            seen.add(text)
    return out


def gate_reason_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for reason in row.get("gate_reasons") or []:
            text = str(reason)
            if text:
                counts[text] = counts.get(text, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def top_gate_reasons(rows: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    counts = gate_reason_counts(rows)
    return [
        {"reason": reason, "count": count}
        for reason, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active-universe", type=Path, default=ACTIVE_UNIVERSE_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-rows-per-repo", type=int, default=500)
    parser.add_argument("--overlay-preflight", action="store_true")
    parser.add_argument("--calibration-work-order", action="store_true")
    parser.add_argument("--contract-mapping-work-order", action="store_true")
    parser.add_argument("--work-order-limit", type=int, default=25)
    parser.add_argument("--nfl-fair-line-review-path", type=Path, default=DEFAULT_NFL_FAIR_LINE_REVIEW_PATH)
    parser.add_argument("--nfl-validation-path", type=Path, action="append")
    parser.add_argument("--contract-mapping-path", type=Path, action="append")
    parser.add_argument("--calibrated-probability-path", type=Path, action="append")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.overlay_preflight:
        report = build_overlay_preflight(
            active_universe_path=args.active_universe,
            calibrated_probability_paths=args.calibrated_probability_path,
            contract_mapping_paths=args.contract_mapping_path,
        )
        if args.write:
            paths = write_overlay_preflight(report, args.out_dir)
            print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.calibration_work_order:
        report = build_calibration_work_order(
            active_universe_path=args.active_universe,
            max_rows_per_repo=args.max_rows_per_repo,
            limit=args.work_order_limit,
            calibrated_probability_paths=args.calibrated_probability_path,
            contract_mapping_paths=args.contract_mapping_path,
        )
        if args.write:
            paths = write_calibration_work_order(report, args.out_dir)
            print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.contract_mapping_work_order:
        report = build_contract_mapping_work_order(
            limit=args.work_order_limit,
            nfl_fair_line_path=args.nfl_fair_line_review_path,
            nfl_validation_paths=args.nfl_validation_path,
        )
        if args.write:
            paths = write_contract_mapping_work_order(report, args.out_dir)
            print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    ledger = build_ledger(
        active_universe_path=args.active_universe,
        max_rows_per_repo=args.max_rows_per_repo,
        calibrated_probability_paths=args.calibrated_probability_path,
        contract_mapping_paths=args.contract_mapping_path,
    )
    if args.write:
        paths = write_ledger(ledger, args.out_dir)
        print(json.dumps({"status": ledger["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(ledger, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
