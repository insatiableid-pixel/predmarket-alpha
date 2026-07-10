"""Lifecycle, phase-0 audit, and synthetic suite for MLB settlement miscalibration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from predmarket.shared_helpers import (
    optional_float,
    timestamp,
)
from predmarket.sports_mlb_settlement_miscalibration import (
    DEFAULT_CLOCKS_SECONDS,
    DEFAULT_STALENESS_SECONDS,
    FAMILY_ID,
    FDR_ALPHA,
    PRIOR_NEGATIVE_SPECS,
    build_fixed_clock_labels,
    normalize_observation_row,
    sha256_file,
    validate_book,
)
from predmarket.sports_mlb_settlement_miscalibration_eval import (
    collapse_event_independence,
    eligible_signal_rows,
    slate_cluster_sign_flip_test,
)


def phase0_audit(
    *,
    observations: Sequence[Mapping[str, Any]],
    settlements: Mapping[str, Mapping[str, Any]],
    observation_dirs: Sequence[Path],
    settlement_paths: Sequence[Path],
) -> dict[str, Any]:
    missing_book = 0
    crossed = 0
    future_settle = 0
    for row in observations:
        ok, reason = validate_book(
            optional_float(row.get("best_yes_bid")),
            optional_float(row.get("best_yes_ask")),
        )
        if not ok and reason == "missing_bid_or_ask":
            missing_book += 1
        if not ok and reason == "crossed_book":
            crossed += 1
        obs_ts = optional_float(row.get("observed_ts"))
        settle_ts = timestamp(row.get("settlement_time"))
        if obs_ts is not None and settle_ts is not None and settle_ts < obs_ts:
            future_settle += 1

    obs_hashes = {}
    for directory in observation_dirs:
        if directory.is_dir():
            for path in sorted(directory.glob("*.json"))[:30]:
                obs_hashes[str(path)] = sha256_file(path)
    sett_hashes = {str(path): sha256_file(path) for path in settlement_paths if path.is_file()}

    return {
        "family_id": FAMILY_ID,
        "prior_negative_specs": list(PRIOR_NEGATIVE_SPECS),
        "novelty_map": {
            "closed_families": [row["spec_id"] for row in PRIOR_NEGATIVE_SPECS],
            "this_family": FAMILY_ID,
            "distinct_mechanisms": [
                "fixed pregame clocks vs short-horizon microstructure",
                "hold-to-settlement economics vs next-mid / round-trip",
                "calibration residual surface separate from executable EV",
                "listing-age cold-start and clock-geometry path features",
            ],
            "baseline_only": ["static price buckets"],
        },
        "timestamp_semantics": {
            "market_observation_time": "observed_at_utc / quote_time of book snapshot",
            "orderbook_receipt_time": "same as observation time for stored packets",
            "scheduled_game_start": "occurrence_datetime preferred; ticker parse fallback",
            "market_close": "close_time from public market payload",
            "settlement_time": "public Kalshi settlement/result on contract ticker",
            "join_rule": "strict as-of: latest book with observed_ts <= clock_ts",
            "staleness": DEFAULT_STALENESS_SECONDS,
            "no_nearest_absolute_future_match": True,
        },
        "book_orientation": {
            "yes_ask": "executable entry for YES",
            "no_ask": "executable entry for NO; never inferred from invalid complement for economics",
            "complementary_contracts": "same event_ticker collapsed for independence",
        },
        "observation_row_count": len(observations),
        "settlement_ticker_count": len(settlements),
        "missing_yes_book_count": missing_book,
        "crossed_yes_book_count": crossed,
        "settlement_before_observation_count": future_settle,
        "observation_source_hashes_sample": obs_hashes,
        "settlement_source_hashes": sett_hashes,
        "synthetic_tests": synthetic_tests(),
        "clocks_frozen_before_outcomes": list(DEFAULT_CLOCKS_SECONDS.keys()),
        "staleness_frozen_before_outcomes": DEFAULT_STALENESS_SECONDS,
    }


def synthetic_tests() -> list[dict[str, Any]]:
    """Positive/negative/leakage/fee/staleness synthetic suite."""

    def iso(ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=UTC).isoformat().replace("+00:00", "Z")

    game_start = datetime(2026, 7, 8, 23, 5, tzinfo=UTC).timestamp()
    ticker = "KXMLBGAME-26JUL081805BOSNYY-BOS"
    event = "KXMLBGAME-26JUL081805BOSNYY"
    # Books: T-60m exact, future book after clock, stale book.
    t_60 = game_start - 3600
    observations = [
        {
            "snapshot_id": "past",
            "contract_ticker": ticker,
            "event_ticker": event,
            "series_ticker": "KXMLBGAME",
            "observed_at_utc": iso(t_60 - 120),
            "best_yes_bid": 0.54,
            "best_yes_ask": 0.56,
            "best_no_bid": 0.44,
            "best_no_ask": 0.46,
            "yes_bid_depth_top1": 10,
            "yes_ask_depth_top1": 12,
            "no_bid_depth_top1": 8,
            "no_ask_depth_top1": 9,
            "yes_mid": 0.55,
            "yes_spread": 0.02,
            "entry_source": "synthetic",
        },
        {
            "snapshot_id": "future_leak",
            "contract_ticker": ticker,
            "event_ticker": event,
            "series_ticker": "KXMLBGAME",
            "observed_at_utc": iso(t_60 + 30),
            "best_yes_bid": 0.80,
            "best_yes_ask": 0.82,
            "best_no_bid": 0.18,
            "best_no_ask": 0.20,
            "yes_bid_depth_top1": 10,
            "yes_ask_depth_top1": 12,
            "no_bid_depth_top1": 8,
            "no_ask_depth_top1": 9,
            "yes_mid": 0.81,
            "yes_spread": 0.02,
            "entry_source": "synthetic",
        },
    ]
    # Normalize.
    norm = []
    for index, row in enumerate(observations):
        item = normalize_observation_row(
            row, source_path="synthetic", source_sha256="synthetic", index=index
        )
        assert item is not None
        norm.append(item)
    settlements = {
        ticker: {
            "ticker": ticker,
            "event_ticker": event,
            "result": "yes",
            "occurrence_datetime": iso(game_start),
            "open_time": iso(game_start - 3 * 86400),
            "yes_outcome": 1,
        }
    }
    labels, _summary = build_fixed_clock_labels(
        norm,
        settlements,
        clocks={"T-60m": 3600},
        staleness={"T-60m": 15 * 60},
    )
    labeled = [row for row in labels if row.get("label_status") == "labeled"]
    tests: list[dict[str, Any]] = []
    tests.append(
        {
            "name": "asof_never_selects_future_book",
            "passed": bool(labeled)
            and labeled[0].get("snapshot_id") == "past"
            and float(labeled[0]["p_hat"]) < 0.7,
            "detail": labeled[0] if labeled else None,
        }
    )
    if labeled:
        fee = float(labeled[0]["yes_entry_fee"] or 0)
        gross = float(labeled[0]["yes_gross_payoff"] or 0)
        net = float(labeled[0]["yes_net_payoff"] or 0)
        tests.append(
            {
                "name": "hold_to_settlement_fee_is_entry_only",
                "passed": abs((gross - fee) - net) < 1e-9 and fee > 0,
                "detail": {"gross": gross, "fee": fee, "net": net},
            }
        )
        tests.append(
            {
                "name": "positive_path_yes_settlement_payoff",
                "passed": labeled[0]["yes_settlement_payoff"] == 1.0,
                "detail": labeled[0]["yes_settlement_payoff"],
            }
        )
    else:
        tests.append({"name": "hold_to_settlement_fee_is_entry_only", "passed": False})
        tests.append({"name": "positive_path_yes_settlement_payoff", "passed": False})

    # Stale book censoring.
    stale_only = [
        normalize_observation_row(
            {
                "snapshot_id": "stale",
                "contract_ticker": ticker,
                "event_ticker": event,
                "series_ticker": "KXMLBGAME",
                "observed_at_utc": iso(t_60 - 3600),
                "best_yes_bid": 0.5,
                "best_yes_ask": 0.52,
                "best_no_bid": 0.48,
                "best_no_ask": 0.5,
                "yes_mid": 0.51,
                "yes_spread": 0.02,
            },
            source_path="synthetic",
            source_sha256="synthetic",
            index=0,
        )
    ]
    assert stale_only[0] is not None
    stale_labels, _ = build_fixed_clock_labels(
        stale_only,
        settlements,
        clocks={"T-60m": 3600},
        staleness={"T-60m": 15 * 60},
    )
    tests.append(
        {
            "name": "stale_book_censored",
            "passed": all(row.get("label_status") == "censored_stale_book" for row in stale_labels),
            "detail": [row.get("label_status") for row in stale_labels],
        }
    )

    # Missing book.
    empty_labels, _ = build_fixed_clock_labels(
        [],
        settlements,
        clocks={"T-60m": 3600},
        staleness={"T-60m": 15 * 60},
    )
    tests.append(
        {
            "name": "missing_book_no_phantom_labels",
            "passed": empty_labels == [],
            "detail": len(empty_labels),
        }
    )

    # Complementary independence collapse.
    complementary = []
    for team, _outcome in (("BOS", 1), ("NYY", 0)):
        t = f"KXMLBGAME-26JUL081805BOSNYY-{team}"
        complementary.append(
            normalize_observation_row(
                {
                    "snapshot_id": f"c-{team}",
                    "contract_ticker": t,
                    "event_ticker": event,
                    "series_ticker": "KXMLBGAME",
                    "observed_at_utc": iso(t_60 - 60),
                    "best_yes_bid": 0.54,
                    "best_yes_ask": 0.56,
                    "best_no_bid": 0.44,
                    "best_no_ask": 0.46,
                    "yes_mid": 0.55,
                    "yes_spread": 0.02,
                },
                source_path="synthetic",
                source_sha256="synthetic",
                index=0,
            )
        )
    sett2 = {
        "KXMLBGAME-26JUL081805BOSNYY-BOS": {
            "ticker": "KXMLBGAME-26JUL081805BOSNYY-BOS",
            "event_ticker": event,
            "result": "yes",
            "occurrence_datetime": iso(game_start),
            "open_time": iso(game_start - 86400),
        },
        "KXMLBGAME-26JUL081805BOSNYY-NYY": {
            "ticker": "KXMLBGAME-26JUL081805BOSNYY-NYY",
            "event_ticker": event,
            "result": "no",
            "occurrence_datetime": iso(game_start),
            "open_time": iso(game_start - 86400),
        },
    }
    comp_labels, _ = build_fixed_clock_labels(
        [row for row in complementary if row is not None],
        sett2,
        clocks={"T-60m": 3600},
        staleness={"T-60m": 15 * 60},
    )
    fired = eligible_signal_rows(
        comp_labels,
        {
            "clock_name": "T-60m",
            "side": "yes",
            "feature": "p_hat",
            "direction": "gt",
            "threshold": 0.01,
        },
    )
    collapsed = collapse_event_independence(fired)
    tests.append(
        {
            "name": "event_independence_collapses_complementary_contracts",
            "passed": len(fired) == 2 and len(collapsed) == 1,
            "detail": {"fired": len(fired), "collapsed": len(collapsed)},
        }
    )

    # Duplicate snapshot stability.
    dup = norm + norm
    labels_dup, _ = build_fixed_clock_labels(
        dup,
        settlements,
        clocks={"T-60m": 3600},
        staleness={"T-60m": 15 * 60},
    )
    tests.append(
        {
            "name": "duplicate_books_do_not_double_count_clock_rows",
            "passed": sum(1 for row in labels_dup if row.get("label_status") == "labeled") == 1,
            "detail": len(labels_dup),
        }
    )

    # Duplicated snapshots / complements must not increase effective settlement power.
    base_events = [
        {
            "event_ticker": f"EVT{i}",
            "game_start_ts": 1_720_000_000 + (i // 3) * 86400,
            "selected_net_return": 0.05 if i % 2 == 0 else -0.02,
            "selected_calibration_residual": 0.04 if i % 2 == 0 else -0.01,
        }
        for i in range(12)
    ]
    # Collapse to events first (as evaluate_hypothesis does).
    collapsed_base = collapse_event_independence(
        [
            {
                **row,
                "decision_ts": row["game_start_ts"],
                "contract_ticker": row["event_ticker"],
            }
            for row in base_events
        ]
    )
    # Complements sharing event_ticker collapse.
    complements = [
        {
            "event_ticker": "EVT0",
            "contract_ticker": "EVT0-A",
            "decision_ts": 1.0,
            "selected_net_return": 0.9,
            "selected_calibration_residual": 0.5,
            "game_start_ts": 1_720_000_000,
        },
        {
            "event_ticker": "EVT0",
            "contract_ticker": "EVT0-B",
            "decision_ts": 2.0,
            "selected_net_return": -0.9,
            "selected_calibration_residual": -0.5,
            "game_start_ts": 1_720_000_000,
        },
    ]
    collapsed_comp = collapse_event_independence(complements)
    inf_base = slate_cluster_sign_flip_test(
        collapsed_base, "selected_net_return", n_resamples=200, seed=3, min_clusters=2
    )
    # Flat list with duplicate events without collapse would inflate n; with collapse n matches.
    tests.append(
        {
            "name": "complements_do_not_inflate_effective_n",
            "passed": len(collapsed_comp) == 1 and collapsed_comp[0]["contract_ticker"] == "EVT0-A",
            "detail": {"collapsed": len(collapsed_comp)},
        }
    )
    tests.append(
        {
            "name": "economic_p_value_is_mean_net_not_win_rate",
            "passed": (
                inf_base.get("method") == "slate_cluster_sign_flip"
                and inf_base.get("null") == "E[value] <= 0"
                and inf_base.get("observed_mean") is not None
            ),
            "detail": inf_base,
        }
    )
    return tests


def resolve_spec_status(
    evaluation: Mapping[str, Any],
    assessment: Mapping[str, Any],
    *,
    confirmation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Map corrected inference + hard gates onto per-spec lifecycle statuses."""
    item = dict(evaluation)
    if item.get("negative_control") or item.get("baseline_only"):
        item["resolution"] = "descriptive_control"
        return item

    status = str(item.get("status") or "underpowered")
    if status == "underpowered" or not item.get("power_met"):
        item["status"] = "underpowered"
        item["resolution"] = "underpowered"
        item["resolution_reason"] = item.get("power_reason") or "per_spec_power_not_met"
        return item

    failed = list(assessment.get("failed_non_confirmation_gates") or [])
    breadth_only = bool(assessment.get("breadth_only_failure"))

    if status == "research_candidate_fdr_passed":
        if assessment.get("research_ready"):
            item["status"] = "research_ready_survivor"
            item["resolution"] = "research_ready_survivor"
            return item
        if assessment.get("discovery_gates_pass"):
            item["status"] = "confirmation_pending"
            item["resolution"] = "confirmation_pending"
            return item
        if breadth_only:
            item["status"] = "frozen_candidate_waiting_multi_slate_confirmation"
            item["resolution"] = "frozen_candidate_waiting_multi_slate_confirmation"
            item["resolution_reason"] = "passes_corrected_joint_inference_fails_slate_breadth"
            return item
        # Genuine non-confirmation validity/implementability failure.
        item["status"] = "powered_falsified"
        item["resolution"] = "powered_falsified"
        item["resolution_reason"] = "hard_gates_failed:" + ",".join(failed)
        return item

    # Powered but did not pass joint FDR / positive means.
    mean_net = optional_float(item.get("oos_mean_net_return"))
    mean_resid = optional_float(item.get("oos_mean_calibration_residual"))
    q_value = optional_float(item.get("q_value"))
    if (
        mean_net is not None
        and mean_net > 0
        and mean_resid is not None
        and mean_resid > 0
        and q_value is not None
        and q_value <= FDR_ALPHA
    ):
        # Should have been marked research_candidate; treat as FDR pass path.
        item["status"] = "research_candidate_fdr_passed"
        return resolve_spec_status(item, assessment, confirmation=confirmation)

    item["status"] = "powered_falsified"
    item["resolution"] = "powered_falsified"
    item["resolution_reason"] = (
        f"powered_but_failed_joint_inference_or_sign mean_net={mean_net} "
        f"mean_resid={mean_resid} p_joint={item.get('p_joint')} q={q_value}"
    )
    return item


def lifecycle_status(evaluations: Sequence[Mapping[str, Any]]) -> str:
    novel = [
        row
        for row in evaluations
        if not row.get("negative_control") and not row.get("baseline_only")
    ]
    if any(row.get("status") == "research_ready_survivor" for row in novel):
        return "research_ready"
    if any(
        row.get("status")
        in {
            "confirmation_pending",
            "frozen_candidate_waiting_multi_slate_confirmation",
        }
        for row in novel
    ):
        return "confirmation_pending"
    if any(row.get("status") == "confirmation_failed" for row in novel) and all(
        row.get("status")
        in {
            "powered_falsified",
            "confirmation_failed",
            "structurally_untestable",
        }
        for row in novel
    ):
        return "falsified"

    unresolved = [
        row
        for row in novel
        if row.get("status")
        in {
            "underpowered",
            "evidence_pending",
            "testable",
            "research_candidate_fdr_passed",
            "insufficient_sample",
        }
    ]
    if unresolved:
        return "evidence_incomplete"

    if novel and all(
        row.get("status") in {"powered_falsified", "confirmation_failed", "structurally_untestable"}
        for row in novel
    ):
        return "falsified"
    return "evidence_incomplete"


def family_resolution_counts(evaluations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    novel = [
        row
        for row in evaluations
        if not row.get("negative_control") and not row.get("baseline_only")
    ]

    def count(status: str) -> int:
        return sum(1 for row in novel if row.get("status") == status)

    return {
        "novel_count": len(novel),
        "powered_count": sum(1 for row in novel if row.get("power_met")),
        "underpowered_count": count("underpowered"),
        "powered_falsified_count": count("powered_falsified"),
        "frozen_waiting_multi_slate_count": count(
            "frozen_candidate_waiting_multi_slate_confirmation"
        ),
        "confirmation_pending_count": count("confirmation_pending"),
        "confirmation_failed_count": count("confirmation_failed"),
        "research_ready_survivor_count": count("research_ready_survivor"),
        "structurally_untestable_count": count("structurally_untestable"),
        "novel_spec_ids": [row.get("model_id") for row in novel],
        "formula_hashes": {str(row.get("model_id")): row.get("formula_hash") for row in novel},
    }


def research_frontier(family_status: str, label_summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    if family_status == "research_ready":
        next_action = "Produce readiness packet; no sizing/execution"
    elif family_status == "falsified":
        next_action = (
            "Outcome B complete: do not retune thresholds/buckets; only a structurally "
            "distinct dense-panel family may reopen MLB modeling"
        )
    elif family_status == "confirmation_pending":
        next_action = (
            "Hold frozen candidates fixed; accumulate multi-slate dense fixed-clock panel "
            "for independent confirmation; do not retune"
        )
    else:
        next_action = (
            "Evidence incomplete: resolve underpowered novel members with denser multi-slate "
            "books; do not declare Outcome B and do not retune"
        )
    return [
        {
            "rank": 1,
            "lane": FAMILY_ID,
            "status": family_status,
            "decision_value": "Fixed-clock MLB moneyline settlement miscalibration",
            "independent_labels_now": label_summary.get("distinct_event_count"),
            "events_by_clock": label_summary.get("events_by_clock"),
            "slates_by_clock": label_summary.get("slates_by_clock"),
            "next_action": next_action,
        },
        {
            "rank": 2,
            "lane": "mlb_multiweek_dense_fixed_clock_panel_v2",
            "status": "discovery_pending",
            "decision_value": (
                "Next distinct surface: multi-week dense orderbook fixed-clock panel with "
                "pre-registered slate-breadth power (not cosmetic retune of v1 thresholds)"
            ),
            "next_action": (
                "Run scripts/kalshi_sports_mlb_dense_book_capture.py on a cadence covering "
                "primary T-60m/T-15m clocks across >=10 chronological slates before confirmation"
            ),
        },
        {
            "rank": 3,
            "lane": "sports_exact_cross_contract_moneyline_coherence",
            "status": "parked",
            "decision_value": (
                "Distinct settlement-miscalibration mechanism only where market terms prove "
                "complementary moneyline identity within event"
            ),
            "next_action": "Park until multi-week dense panel exists; do not mix with v1 retunes",
        },
        {
            "rank": 4,
            "lane": "retired_short_horizon_microstructure",
            "status": "falsified",
            "decision_value": "Do not resurrect short-horizon next-mid families",
            "next_action": "Parked permanently under negative registry",
        },
    ]


def negative_registry_update(
    evaluations: Sequence[Mapping[str, Any]], *, family_status: str
) -> list[dict[str, Any]]:
    rows = [dict(item) for item in PRIOR_NEGATIVE_SPECS]
    if family_status == "falsified":
        rows.append(
            {
                "family": FAMILY_ID,
                "spec_id": FAMILY_ID,
                "status": "falsified",
                "do_not_repeat": (
                    "Do not retune fixed-clock thresholds/buckets cosmetically; require a "
                    "genuinely new settlement-miscalibration mechanism or mapped sports surface"
                ),
                "evidence": {
                    "evaluations": [
                        {
                            "model_id": row.get("model_id"),
                            "status": row.get("status"),
                            "oos_event_count": row.get("oos_event_count"),
                            "oos_slate_count": row.get("oos_slate_count"),
                            "oos_mean_net_return": row.get("oos_mean_net_return"),
                            "p_economic": row.get("p_economic"),
                            "p_calibration": row.get("p_calibration"),
                            "p_joint": row.get("p_joint"),
                            "q_value": row.get("q_value"),
                        }
                        for row in evaluations
                    ]
                },
            }
        )
    for row in evaluations:
        if row.get("status") in {"powered_falsified", "confirmation_failed"}:
            rows.append(
                {
                    "family": FAMILY_ID,
                    "spec_id": row.get("model_id"),
                    "status": row.get("status"),
                    "do_not_repeat": (
                        f"Powered failure for {row.get('model_id')}: "
                        f"{row.get('resolution_reason') or row.get('status')}"
                    ),
                    "evidence": {
                        "oos_event_count": row.get("oos_event_count"),
                        "oos_slate_count": row.get("oos_slate_count"),
                        "oos_mean_net_return": row.get("oos_mean_net_return"),
                        "p_economic": row.get("p_economic"),
                        "p_calibration": row.get("p_calibration"),
                        "p_joint": row.get("p_joint"),
                        "q_value": row.get("q_value"),
                        "oos_mean_calibration_residual": row.get("oos_mean_calibration_residual"),
                        "formula_hash": row.get("formula_hash"),
                    },
                }
            )
    return rows
