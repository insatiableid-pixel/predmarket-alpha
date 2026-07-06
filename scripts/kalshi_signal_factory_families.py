"""Family registry for the Kalshi signal factory status report.

Enumerates signal families (crypto_proxy, sports_baseball) so capability
iteration is data-driven, not a hardcoded crypto-only list.  Adding a family
is a data change (register it here), not a rewrite of the status script.

This module is a companion to ``scripts/kalshi_signal_factory_status.py`` and
is imported by it.  It deliberately does NOT import from ``predmarket/``
(respecting the binding import boundary).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Family IDs.
CRYPTO_PROXY_FAMILY_ID = "crypto_proxy"
SPORTS_BASEBALL_FAMILY_ID = "sports_baseball"
WEATHER_PROXY_FAMILY_ID = "weather_proxy"

# Capability names that belong to the crypto family (not shared infrastructure).
CRYPTO_FAMILY_CAPABILITY_NAMES = frozenset(
    {
        "crypto_proxy_feature_packet",
        "crypto_proxy_observation_loop",
        "crypto_proxy_feature_model_falsification",
        "crypto_proxy_research_candidate_replay",
        "crypto_proxy_capacity_correlation_decay",
        "crypto_proxy_correlation_cluster_control",
        "capacity_model",
        "correlation_model",
    }
)

# Capability names that belong to the weather proxy family.
WEATHER_PROXY_FAMILY_CAPABILITY_NAMES = frozenset(
    {
        "weather_proxy_feature_packet",
        "weather_proxy_observation_loop",
        "weather_proxy_feature_model_falsification",
        "weather_proxy_research_candidate_replay",
        "weather_proxy_capacity_correlation_decay",
        "weather_proxy_correlation_cluster_control",
    }
)

# Favorite-longshot bias family.
FAVORITE_LONGSHOT_FAMILY_ID = "favorite_longshot_bias"

FAVORITE_LONGSHOT_CAPABILITY_NAMES = frozenset(
    {
        "favorite_longshot_bias_feature_packet",
        "favorite_longshot_bias_observation_loop",
        "favorite_longshot_bias_feature_model_falsification",
        "favorite_longshot_bias_research_candidate_replay",
        "favorite_longshot_bias_capacity_correlation_decay",
        "favorite_longshot_bias_correlation_cluster_control",
    }
)

# Passive liquidity provision family.
PASSIVE_LIQUIDITY_FAMILY_ID = "passive_liquidity_provision"

PASSIVE_LIQUIDITY_CAPABILITY_NAMES = frozenset(
    {
        "passive_liquidity_provision_feature_packet",
        "passive_liquidity_provision_observation_loop",
        "passive_liquidity_provision_feature_model_falsification",
        "passive_liquidity_provision_research_candidate_replay",
        "passive_liquidity_provision_capacity_correlation_decay",
        "passive_liquidity_provision_correlation_cluster_control",
    }
)


def _capability(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def family_status_rank(status: str) -> int:  # noqa: C901
    """Advancement rank: higher = further along the pipeline.

    Blocked/missing = 0.  Used to select the leading family for the
    top-level status.  Ties resolve to crypto (the default lane).
    """
    if "blocked" in status or "missing" in status:
        return 0
    if "sports_stack_sequencing_ready" in status:
        return 18
    if "cluster_control_ready" in status:
        return 19
    if "cluster" in status:
        return 18
    if "ccd_ready" in status:
        return 17
    if "capacity_correlation_decay_ready" in status:
        return 17
    if "capacity" in status or "correlation_concentration" in status or "decay_survival" in status:
        return 16
    if "ccd_blocked" in status:
        return 16
    if "current_candidates" in status:
        return 16
    if "replay_ready_paper" in status:
        return 15
    if "replay" in status:
        return 14
    if "falsification_ready" in status:
        return 13
    if "feature_model_research" in status:
        return 13
    if "falsification" in status:
        return 12
    if "feature_model" in status:
        return 12
    if "labels_ready" in status:
        return 11
    if "observations_waiting" in status:
        return 10
    if "feature_packet_ready" in status:
        return 9
    if "breadth_scout_ready" in status:
        return 8
    if "oos_backtest_ready" in status:
        return 7
    if "oos_pending" in status:
        return 6
    if "label_packet" in status:
        return 5
    if "oos_backtest_harness" in status:
        return 4
    if "oos_samples" in status:
        return 4
    if "hypothesis_registry" in status:
        return 3
    if "falsification_missing" in status:
        return 2
    if "foundation_ready" in status:
        return 1
    return 0


# Sports family tranche map (additive; mirrors crypto tranche pattern).
SPORTS_BASEBALL_NEXT_TRANCHES: dict[str, dict[str, str]] = {
    "signal_factory_sports_stack_sequencing_ready_current_depth_passed": {
        "name": "kalshi_world_cup_mlb_atp_evidence_loop",
        "why": (
            "Current sports sequencing is live: World Cup/FIFA first, MLB second, ATP third, "
            "with cap_i current-depth preflight passing. Run family-specific observation, "
            "label, and falsification loops in that order."
        ),
        "stop_condition": (
            "Stop before merging sport feature layers, locking capacity from stale depth, "
            "sizing, execution, account/order paths, or treating unresolved labels as edge."
        ),
    },
    "signal_factory_sports_stack_sequencing_ready_cap_i_lock_blocked": {
        "name": "kalshi_ghost_listing_depth_diagnostic",
        "why": (
            "Sports rows are sequenced, but cap_i is blocked until current public orderbook "
            "depth proves the markets are not ghost listings."
        ),
        "stop_condition": (
            "Stop before locking cap_i, sizing, execution, account/order paths, or inferring "
            "capacity from inventory-only/top-of-book artifacts."
        ),
    },
    "signal_factory_sports_baseball_cluster_control_ready": {
        "name": "kalshi_sports_proxy_paper_probability_overlay",
        "why": "Sports cluster exposure limits are machine-readable and passing for the current research-only candidate set.",
        "stop_condition": "Stop before real positions, execution, account/order paths, staking, or live edge claims.",
    },
    "signal_factory_sports_baseball_ccd_ready": {
        "name": "kalshi_sports_proxy_correlation_cluster_control",
        "why": "Sports capacity, correlation, and decay gates passed; apply cluster exposure controls before overlay.",
        "stop_condition": "Stop before paper overlay until cluster exposure limits are machine-readable and passing.",
    },
    "signal_factory_sports_baseball_replay_blocked_predeployment_gates": {
        "name": "kalshi_sports_proxy_capacity_correlation_decay",
        "why": "A research candidate has conservative cost-adjusted replay rows, but capacity, correlation, and decay gates block any usable edge.",
        "stop_condition": "Stop before sizing, execution, account/order paths, or treating positive replay rows as deployable.",
    },
    "signal_factory_sports_baseball_falsification_ready": {
        "name": "kalshi_sports_proxy_probability_calibration",
        "why": "At least one sports feature family survived OOS/FDR as a research candidate; next work is calibrated probability modeling and cost replay.",
        "stop_condition": "Stop before sizing or execution until calibrated probabilities, all-in costs, capacity, correlation, and kill-switch gates exist.",
    },
    "signal_factory_sports_baseball_labels_ready": {
        "name": "kalshi_sports_proxy_feature_model_falsification",
        "why": (
            "Sports proxy observations now have true public Kalshi settlement labels; the next useful "
            "work is a cost-aware feature model plus out-of-sample/FDR falsification."
        ),
        "stop_condition": (
            "Stop before promotion, sizing, execution, or account/order paths without calibrated "
            "probabilities, all-in costs, and FDR-controlled OOS survival."
        ),
    },
    "signal_factory_sports_baseball_observations_waiting_settlement": {
        "name": "kalshi_sports_proxy_observation_accumulation",
        "why": (
            "Sports proxy feature observations are archived, but true Kalshi settlement labels are "
            "still missing or insufficient; keep collecting snapshots and public settled outcomes."
        ),
        "stop_condition": (
            "Stop before using proxy feeds as labels, calibrated probabilities, EV, sizing, execution, "
            "or account/order evidence."
        ),
    },
    "signal_factory_sports_baseball_feature_packet_ready": {
        "name": "kalshi_sports_proxy_observation_loop",
        "why": (
            "Contract-keyed sports proxy feature packets now exist; the next useful work is repeated "
            "snapshots plus settled Kalshi outcome matching for out-of-sample falsification."
        ),
        "stop_condition": (
            "Stop before treating proxy feeds as official settlement labels, computing usable EV, "
            "sizing, execution, or account/order paths."
        ),
    },
    "signal_factory_probability_breadth_scout_ready_sports_baseball_route": {
        "name": "kalshi_sports_proxy_feature_packet",
        "why": (
            "Fast-settling baseball game-winner contracts are available and keyless feature sources "
            "are reachable; build contract-keyed feature packets with official game results as "
            "the settlement source."
        ),
        "stop_condition": (
            "Stop before treating proxy feeds as official settlement labels, computing usable EV, "
            "sizing, execution, or account/order paths."
        ),
    },
    "signal_factory_sports_baseball_blocked_missing_feature_packet": {
        "name": "kalshi_sports_proxy_feature_packet",
        "why": "No sports proxy feature packet artifact exists yet; build the baseball lane's feature packet.",
        "stop_condition": "Stop before sizing, execution, or account/order paths; this is research-only.",
    },
}


def build_sports_baseball_capabilities(
    *,
    feature_present: bool,
    feature_status: str,
    feature_summary: Mapping[str, Any],
    observation_present: bool,
    observation_status: str,
    observation_summary: Mapping[str, Any],
    model_present: bool = False,
    model_status: str = "",
    model_summary: Mapping[str, Any] | None = None,
    replay_present: bool = False,
    replay_status: str = "",
    replay_summary: Mapping[str, Any] | None = None,
    ccd_present: bool = False,
    ccd_status: str = "",
    ccd_summary: Mapping[str, Any] | None = None,
    cluster_present: bool = False,
    cluster_status: str = "",
    cluster_summary: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Build sports-baseball family capability gates (additive; crypto untouched).

    Extended in M2 to include falsification, replay, CCD, and cluster-control stages.
    """
    feature_ready = feature_status == "sports_proxy_feature_packet_ready"
    obs_label_ready = observation_status == "sports_proxy_observation_loop_label_rows_ready"
    obs_waiting = observation_status in {
        "sports_proxy_observation_loop_ready_waiting_settlement",
        "sports_proxy_observation_loop_observations_recorded_waiting_settlement",
    }
    model_summary_data = model_summary or {}
    replay_summary_data = replay_summary or {}
    ccd_summary_data = ccd_summary or {}
    cluster_summary_data = cluster_summary or {}
    return [
        _capability(
            "sports_baseball_feature_packet",
            "pass" if feature_ready else ("warn" if feature_present else "blocked"),
            (
                f"Sports proxy feature packet status is `{feature_status}` with "
                f"{feature_summary.get('feature_row_count', 0)} feature row(s) and "
                f"{feature_summary.get('feature_ready_count', 0)} feature-ready row(s)."
                if feature_present
                else "No contract-keyed sports proxy feature packet exists yet."
            ),
        ),
        _capability(
            "sports_baseball_observation_loop",
            "pass"
            if obs_label_ready or obs_waiting
            else ("warn" if observation_present else "blocked"),
            (
                f"Sports proxy observation loop status is `{observation_status}` with "
                f"{observation_summary.get('total_observation_row_count', 0)} total observation row(s), "
                f"{observation_summary.get('new_observation_row_count', 0)} new row(s), and "
                f"{observation_summary.get('label_row_count', 0)} settled label row(s)."
                if observation_present
                else "No repeated sports proxy observation/label loop report exists yet."
            ),
        ),
        _capability(
            "sports_baseball_feature_model_falsification",
            "pass"
            if "research_candidate" in model_status
            else ("warn" if model_present else "blocked"),
            (
                f"Sports proxy model falsification status is `{model_status}` with "
                f"{model_summary_data.get('independent_contract_label_count', 0)} independent label(s) and "
                f"{model_summary_data.get('research_candidate_count', 0)} research candidate(s)."
                if model_present
                else "No sports proxy feature-model falsification report exists yet."
            ),
        ),
        _capability(
            "sports_baseball_research_candidate_replay",
            "pass"
            if replay_present and "blocked_predeployment" in replay_status
            else ("warn" if replay_present else "blocked"),
            (
                f"Sports proxy research-candidate replay status is `{replay_status}` with "
                f"{replay_summary_data.get('replay_row_count', 0)} replay row(s) and "
                f"{replay_summary_data.get('positive_expected_value_row_count', 0)} positive cost-adjusted row(s)."
                if replay_present
                else "No sports proxy cost/capacity/correlation/decay replay report exists yet."
            ),
        ),
        _capability(
            "sports_baseball_capacity_correlation_decay",
            "pass"
            if ccd_status == "sports_proxy_capacity_correlation_decay_ready_for_paper_overlay"
            else ("warn" if ccd_present else "blocked"),
            (
                f"Sports proxy CCD status is `{ccd_status}` with "
                f"{ccd_summary_data.get('candidate_row_count', 0)} current candidate(s), "
                f"{ccd_summary_data.get('orderbook_count', 0)} orderbook(s), and "
                f"decay status `{ccd_summary_data.get('decay_status')}`."
                if ccd_present
                else "No sports proxy capacity/correlation/decay gate report exists yet."
            ),
        ),
        _capability(
            "sports_baseball_correlation_cluster_control",
            "pass"
            if cluster_status == "sports_proxy_correlation_cluster_control_ready_for_paper_overlay"
            else ("warn" if cluster_present else "blocked"),
            (
                f"Sports proxy cluster-control status is `{cluster_status}`; "
                f"largest controlled cluster share is `{cluster_summary_data.get('largest_controlled_cluster_share')}`."
                if cluster_present
                else "No sports proxy correlation-cluster control report exists yet."
            ),
        ),
        _capability(
            "sports_baseball_capacity_model",
            "pass"
            if ccd_summary_data.get("capacity_status") == "capacity_depth_positive"
            else "blocked",
            (
                f"Sports proxy capacity depth status is `{ccd_summary_data.get('capacity_status')}` with "
                f"{ccd_summary_data.get('positive_depth_contracts', 0)} positive-depth contract(s)."
                if ccd_present
                else "No capacity model exists for sports proxy candidates."
            ),
        ),
    ]


def compute_sports_baseball_status(
    *,
    feature_present: bool,
    feature_status: str,
    observation_present: bool,
    observation_status: str,
    probability_breadth_status: str = "",
    probability_breadth_present: bool = False,
    model_present: bool = False,
    model_status: str = "",
    replay_present: bool = False,
    replay_status: str = "",
    ccd_present: bool = False,
    ccd_status: str = "",
    cluster_present: bool = False,
    cluster_status: str = "",
) -> str:
    """Compute the sports-baseball family's individual status string.

    Extended in M2 to include falsification, replay, CCD, and cluster-control
    stage detection.
    """
    # Most advanced first: cluster control ready
    if (
        cluster_present
        and cluster_status == "sports_proxy_correlation_cluster_control_ready_for_paper_overlay"
    ):
        return "signal_factory_sports_baseball_cluster_control_ready"
    # CCD present (any status)
    if ccd_present and ccd_status:
        if "ready_for_paper_overlay" in ccd_status:
            return "signal_factory_sports_baseball_ccd_ready"
        if "blocked_decay_survival" in ccd_status:
            return "signal_factory_sports_baseball_ccd_blocked_decay"
        if "blocked_correlation" in ccd_status:
            return "signal_factory_sports_baseball_ccd_blocked_correlation"
        if "blocked_capacity_depth" in ccd_status:
            return "signal_factory_sports_baseball_ccd_blocked_capacity_depth"
        if "blocked_no_current" in ccd_status:
            return "signal_factory_sports_baseball_ccd_blocked_no_current_candidates"
        return "signal_factory_sports_baseball_ccd_blocked"
    # Replay present
    if replay_present and replay_status:
        if "blocked_predeployment" in replay_status:
            return "signal_factory_sports_baseball_replay_blocked_predeployment_gates"
        if "ready_for_paper" in replay_status:
            return "signal_factory_sports_baseball_replay_ready_paper"
        return "signal_factory_sports_baseball_replay_blocked"
    # Falsification present
    if model_present and model_status:
        if "ready_with_research_candidates" in model_status:
            return "signal_factory_sports_baseball_falsification_ready"
        if "ready_no_research" in model_status:
            return "signal_factory_sports_baseball_falsification_no_candidates"
        return "signal_factory_sports_baseball_falsification_blocked"
    # Feature packet and observation
    obs_label_ready = observation_status == "sports_proxy_observation_loop_label_rows_ready"
    obs_waiting = observation_status in {
        "sports_proxy_observation_loop_ready_waiting_settlement",
        "sports_proxy_observation_loop_observations_recorded_waiting_settlement",
    }
    if feature_present and feature_status == "sports_proxy_feature_packet_ready":
        if observation_present and obs_label_ready:
            return "signal_factory_sports_baseball_labels_ready"
        if observation_present and obs_waiting:
            return "signal_factory_sports_baseball_observations_waiting_settlement"
        return "signal_factory_sports_baseball_feature_packet_ready"
    if (
        probability_breadth_present
        and probability_breadth_status == "probability_breadth_scout_ready_sports_baseball_route"
    ):
        return "signal_factory_probability_breadth_scout_ready_sports_baseball_route"
    return "signal_factory_sports_baseball_blocked_missing_feature_packet"


# Weather proxy family tranche map (additive; mirrors crypto/sports pattern).
WEATHER_PROXY_NEXT_TRANCHES: dict[str, dict[str, str]] = {
    "signal_factory_weather_proxy_feature_packet_ready": {
        "name": "kalshi_weather_proxy_observation_loop",
        "why": (
            "Contract-keyed weather proxy feature packets now exist; the next useful work is repeated "
            "snapshots plus settled Kalshi outcome matching for out-of-sample falsification."
        ),
        "stop_condition": (
            "Stop before treating proxy feeds as official settlement labels, computing usable EV, "
            "sizing, execution, or account/order paths."
        ),
    },
    "signal_factory_weather_proxy_blocked_missing_feature_packet": {
        "name": "kalshi_weather_proxy_feature_packet",
        "why": "No weather proxy feature packet artifact exists yet; build the weather lane's feature packet.",
        "stop_condition": "Stop before sizing, execution, or account/order paths; this is research-only.",
    },
    "signal_factory_probability_breadth_scout_ready_weather_proxy_route": {
        "name": "kalshi_weather_proxy_feature_packet",
        "why": (
            "Fast-settling weather contracts are available and keyless NWS feature sources "
            "are reachable (api.weather.gov); build contract-keyed feature packets with the "
            "NWS Daily Climate Report as the settlement source."
        ),
        "stop_condition": (
            "Stop before treating proxy feeds as official settlement labels, computing usable EV, "
            "sizing, execution, or account/order paths."
        ),
    },
    "signal_factory_weather_proxy_observations_waiting_settlement": {
        "name": "kalshi_weather_proxy_observation_accumulation",
        "why": (
            "Weather proxy feature observations are archived, but Kalshi settlement labels are "
            "still missing or insufficient; keep collecting snapshots and public settled outcomes."
        ),
        "stop_condition": (
            "Stop before using proxy feeds as labels, calibrated probabilities, EV, sizing, execution, "
            "or account/order evidence."
        ),
    },
    "signal_factory_weather_proxy_labels_ready": {
        "name": "kalshi_weather_proxy_feature_model_falsification",
        "why": (
            "Weather proxy observations now have true public Kalshi settlement labels; the next useful "
            "work is a cost-aware feature model plus out-of-sample/FDR falsification."
        ),
        "stop_condition": (
            "Stop before promotion, sizing, execution, or account/order paths without calibrated "
            "probabilities, all-in costs, and FDR-controlled OOS survival."
        ),
    },
    "signal_factory_weather_proxy_falsification_no_candidates": {
        "name": "kalshi_weather_proxy_signal_replacement",
        "why": (
            "Weather labels are sufficient for falsification, but the current bracket-probability "
            "rule produced no FDR-surviving research candidate. Retire/deprioritize this rule and "
            "generate replacement weak signals without lowering thresholds."
        ),
        "stop_condition": (
            "Stop before changing thresholds, promoting failed weather rules, sizing, execution, "
            "or account/order paths."
        ),
    },
    "signal_factory_weather_proxy_falsification_ready": {
        "name": "kalshi_weather_proxy_research_candidate_replay",
        "why": "A weather feature family survived OOS/FDR; replay it against all-in Kalshi costs before any overlay.",
        "stop_condition": "Stop before sizing or execution until cost, capacity, correlation, and decay gates pass.",
    },
    "signal_factory_weather_proxy_replay_blocked": {
        "name": "kalshi_weather_proxy_signal_replacement_or_evidence_accumulation",
        "why": "Weather replay has no deployable research candidate or positive cost-adjusted rows.",
        "stop_condition": "Stop before paper/live promotion without a replay-passing research candidate.",
    },
}


def build_weather_proxy_capabilities(
    *,
    feature_present: bool,
    feature_status: str,
    feature_summary: Mapping[str, Any],
    observation_present: bool,
    observation_status: str,
    observation_summary: Mapping[str, Any],
    probability_breadth_present: bool = False,
    probability_breadth_status: str = "",
    model_present: bool = False,
    model_status: str = "",
    model_summary: Mapping[str, Any] | None = None,
    replay_present: bool = False,
    replay_status: str = "",
    replay_summary: Mapping[str, Any] | None = None,
    ccd_present: bool = False,
    ccd_status: str = "",
    ccd_summary: Mapping[str, Any] | None = None,
    cluster_present: bool = False,
    cluster_status: str = "",
    cluster_summary: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Build weather-proxy family capability gates (additive; crypto/sports untouched)."""
    feature_ready = feature_status == "weather_proxy_feature_packet_ready"
    obs_ready = "ready" in observation_status and "label" in observation_status.lower()
    obs_waiting = observation_status in {
        "weather_proxy_observation_loop_partial_observations_no_labels",
        "weather_proxy_observation_loop_blocked_no_new_observations_or_labels",
    }
    model_summary_data = model_summary or {}
    replay_summary_data = replay_summary or {}
    ccd_summary_data = ccd_summary or {}
    cluster_summary_data = cluster_summary or {}
    return [
        _capability(
            "weather_proxy_feature_packet",
            "pass" if feature_ready else ("warn" if feature_present else "blocked"),
            (
                f"Weather proxy feature packet status is `{feature_status}` with "
                f"{feature_summary.get('feature_row_count', 0)} feature row(s) and "
                f"{feature_summary.get('feature_ready_count', 0)} feature-ready row(s)."
                if feature_present
                else "No contract-keyed weather proxy feature packet exists yet."
            ),
        ),
        _capability(
            "weather_proxy_observation_loop",
            "pass" if obs_ready or obs_waiting else ("warn" if observation_present else "blocked"),
            (
                f"Weather proxy observation loop status is `{observation_status}` with "
                f"{observation_summary.get('new_observation_row_count', 0)} new observation row(s) and "
                f"{observation_summary.get('new_label_row_count', 0)} settled label row(s)."
                if observation_present
                else "No repeated weather proxy observation/label loop report exists yet."
            ),
        ),
        _capability(
            "weather_proxy_feature_model_falsification",
            "pass"
            if "ready_with_research_candidates" in model_status
            else ("warn" if model_present else "blocked"),
            (
                f"Weather proxy model falsification status is `{model_status}` with "
                f"{model_summary_data.get('independent_contract_label_count', 0)} independent label(s), "
                f"{model_summary_data.get('testable_model_count', 0)} testable model(s), and "
                f"{model_summary_data.get('research_candidate_count', 0)} research candidate(s)."
                if model_present
                else "No weather proxy feature-model falsification report exists yet."
            ),
        ),
        _capability(
            "weather_proxy_research_candidate_replay",
            "pass"
            if replay_present and "blocked_predeployment" in replay_status
            else ("warn" if replay_present else "blocked"),
            (
                f"Weather proxy replay status is `{replay_status}` with "
                f"{replay_summary_data.get('replay_row_count', 0)} replay row(s), "
                f"{replay_summary_data.get('positive_expected_value_row_count', 0)} positive cost-adjusted row(s), "
                f"and decay status `{replay_summary_data.get('decay_status')}`."
                if replay_present
                else "No weather proxy research-candidate replay report exists yet."
            ),
        ),
        _capability(
            "weather_proxy_capacity_correlation_decay",
            "pass"
            if ccd_status == "weather_proxy_capacity_correlation_decay_ready_for_paper_overlay"
            else ("warn" if ccd_present else "blocked"),
            (
                f"Weather proxy CCD status is `{ccd_status}` with "
                f"{ccd_summary_data.get('candidate_row_count', 0)} current candidate(s), "
                f"{ccd_summary_data.get('orderbook_count', 0)} orderbook(s), and "
                f"decay status `{ccd_summary_data.get('decay_status')}`."
                if ccd_present
                else "No weather proxy capacity/correlation/decay gate report exists yet."
            ),
        ),
        _capability(
            "weather_proxy_correlation_cluster_control",
            "pass"
            if cluster_status == "weather_proxy_correlation_cluster_control_ready_for_paper_overlay"
            else ("warn" if cluster_present else "blocked"),
            (
                f"Weather proxy cluster-control status is `{cluster_status}`; "
                f"largest controlled cluster share is `{cluster_summary_data.get('largest_controlled_cluster_share')}`."
                if cluster_present
                else "No weather proxy correlation-cluster control report exists yet."
            ),
        ),
    ]


def compute_weather_proxy_status(
    *,
    feature_present: bool,
    feature_status: str,
    observation_present: bool,
    observation_status: str,
    probability_breadth_status: str = "",
    probability_breadth_present: bool = False,
    model_present: bool = False,
    model_status: str = "",
    replay_present: bool = False,
    replay_status: str = "",
    ccd_present: bool = False,
    ccd_status: str = "",
    cluster_present: bool = False,
    cluster_status: str = "",
) -> str:
    """Compute the weather-proxy family's individual status string."""
    if (
        cluster_present
        and cluster_status == "weather_proxy_correlation_cluster_control_ready_for_paper_overlay"
    ):
        return "signal_factory_weather_proxy_cluster_control_ready"
    if ccd_present and ccd_status:
        if "ready_for_paper_overlay" in ccd_status:
            return "signal_factory_weather_proxy_ccd_ready"
        return "signal_factory_weather_proxy_ccd_blocked"
    if replay_present and replay_status:
        if "blocked_missing_research_candidate" in replay_status:
            return "signal_factory_weather_proxy_replay_blocked"
        if "blocked_predeployment" in replay_status:
            return "signal_factory_weather_proxy_replay_blocked"
        if "ready_for_paper" in replay_status:
            return "signal_factory_weather_proxy_replay_ready_paper"
        return "signal_factory_weather_proxy_replay_blocked"
    if model_present and model_status:
        if "ready_with_research_candidates" in model_status:
            return "signal_factory_weather_proxy_falsification_ready"
        if "ready_no_research_candidates" in model_status:
            return "signal_factory_weather_proxy_falsification_no_candidates"
        return "signal_factory_weather_proxy_falsification_blocked"
    obs_ready = "ready_with_labels" in observation_status
    obs_waiting = observation_status in {
        "weather_proxy_observation_loop_partial_observations_no_labels",
        "weather_proxy_observation_loop_blocked_no_new_observations_or_labels",
    }
    if feature_present and feature_status == "weather_proxy_feature_packet_ready":
        if observation_present and obs_ready:
            return "signal_factory_weather_proxy_labels_ready"
        if observation_present and obs_waiting:
            return "signal_factory_weather_proxy_observations_waiting_settlement"
        return "signal_factory_weather_proxy_feature_packet_ready"
    if probability_breadth_present and "weather" in probability_breadth_status:
        return "signal_factory_probability_breadth_scout_ready_weather_proxy_route"
    return "signal_factory_weather_proxy_blocked_missing_feature_packet"


# Favorite-longshot bias family tranche map.
FAVORITE_LONGSHOT_NEXT_TRANCHES: dict[str, dict[str, str]] = {
    "signal_factory_favorite_longshot_bias_falsification_no_candidates": {
        "name": "kalshi_favorite_longshot_bias_signal_replacement",
        "why": (
            "Favorite-longshot bias labels are sufficient for falsification, but the price-bucket "
            "rule produced no FDR-surviving research candidate. Retire/deprioritize this rule and "
            "generate replacement weak signals without lowering thresholds."
        ),
        "stop_condition": (
            "Stop before changing thresholds, promoting failed rules, sizing, execution, "
            "or account/order paths."
        ),
    },
    "signal_factory_favorite_longshot_bias_falsification_ready": {
        "name": "kalshi_favorite_longshot_bias_research_candidate_replay",
        "why": (
            "The favorite-longshot bias family survived OOS/FDR falsification; replay research "
            "candidates against all-in Kalshi costs before any overlay."
        ),
        "stop_condition": (
            "Stop before sizing or execution until cost, capacity, correlation, and decay gates pass."
        ),
    },
    "signal_factory_favorite_longshot_bias_labels_ready": {
        "name": "kalshi_favorite_longshot_bias_feature_model_falsification",
        "why": (
            "Favorite-longshot bias observations have Kalshi settlement labels; the next useful "
            "work is cost-aware feature model plus OOS/FDR falsification."
        ),
        "stop_condition": (
            "Stop before promotion, sizing, execution, or account/order paths without calibrated "
            "probabilities, all-in costs, and FDR-controlled OOS survival."
        ),
    },
    "signal_factory_favorite_longshot_bias_observations_waiting_settlement": {
        "name": "kalshi_favorite_longshot_bias_observation_accumulation",
        "why": (
            "Favorite-longshot bias observations are archived, but Kalshi settlement labels are "
            "still missing or insufficient; keep collecting snapshots and public settled outcomes."
        ),
        "stop_condition": (
            "Stop before using proxy feeds as labels, calibrated probabilities, EV, sizing, execution, "
            "or account/order evidence."
        ),
    },
    "signal_factory_favorite_longshot_bias_feature_packet_ready": {
        "name": "kalshi_favorite_longshot_bias_observation_loop",
        "why": (
            "Favorite-longshot bias feature packets now exist; the next useful work is repeated "
            "snapshots plus settled Kalshi outcome matching for out-of-sample falsification."
        ),
        "stop_condition": (
            "Stop before treating raw price observations as falsified signals, computing usable EV, "
            "sizing, execution, or account/order paths."
        ),
    },
    "signal_factory_favorite_longshot_bias_blocked_missing_feature_packet": {
        "name": "kalshi_favorite_longshot_bias_feature_packet",
        "why": (
            "No favorite-longshot bias feature packet artifact exists yet; build the price-bucket "
            "feature packet from contract observations."
        ),
        "stop_condition": (
            "Stop before sizing, execution, or account/order paths; this is research-only."
        ),
    },
}


# Passive liquidity provision family tranche map.
PASSIVE_LIQUIDITY_NEXT_TRANCHES: dict[str, dict[str, str]] = {
    "signal_factory_passive_liquidity_provision_falsification_no_candidates": {
        "name": "kalshi_passive_liquidity_signal_replacement_or_evidence_accumulation",
        "why": (
            "Passive liquidity provision labels are sufficient for falsification, but the "
            "counterfactual net-EV analysis produced no positive-EV maker side. Accumulate "
            "more microstructure evidence or generate replacement weak signals."
        ),
        "stop_condition": (
            "Stop before changing thresholds, promoting failed signals, sizing, execution, "
            "or account/order paths."
        ),
    },
    "signal_factory_passive_liquidity_provision_falsification_ready": {
        "name": "kalshi_passive_liquidity_research_candidate_replay",
        "why": (
            "The passive liquidity provision family shows positive maker-fill net EV after "
            "adverse selection; replay research candidates against all-in Kalshi costs "
            "before any overlay."
        ),
        "stop_condition": (
            "Stop before sizing or execution until cost, capacity, correlation, and decay gates pass."
        ),
    },
    "signal_factory_passive_liquidity_provision_labels_ready": {
        "name": "kalshi_passive_liquidity_provision_feature_model_falsification",
        "why": (
            "Passive liquidity provision observations have Kalshi settlement labels; the next "
            "useful work is counterfactual net-EV analysis plus OOS/FDR falsification."
        ),
        "stop_condition": (
            "Stop before promotion, sizing, execution, or account/order paths without "
            "validated net-EV after adverse selection."
        ),
    },
    "signal_factory_passive_liquidity_provision_observations_waiting_settlement": {
        "name": "kalshi_passive_liquidity_microstructure_accumulation",
        "why": (
            "Passive liquidity provision observations are archived, but Kalshi settlement labels "
            "are still missing or insufficient; keep collecting microstructure snapshots and "
            "public settled outcomes."
        ),
        "stop_condition": (
            "Stop before using proxy feeds as labels, calibrated probabilities, EV, sizing, "
            "execution, or account/order evidence."
        ),
    },
    "signal_factory_passive_liquidity_provision_feature_packet_ready": {
        "name": "kalshi_passive_liquidity_provision_microstructure_loop",
        "why": (
            "Passive liquidity provision feature packets now exist; the next useful work is "
            "repeated microstructure snapshots plus virtual order replay against settled outcomes."
        ),
        "stop_condition": (
            "Stop before treating raw microstructure observations as falsified signals, "
            "computing usable EV, sizing, execution, or account/order paths."
        ),
    },
    "signal_factory_passive_liquidity_provision_blocked_missing_feature_packet": {
        "name": "kalshi_passive_liquidity_provision_feature_packet",
        "why": (
            "No passive liquidity provision feature packet artifact exists yet; build the "
            "maker-side quote feature packet from microstructure observations."
        ),
        "stop_condition": (
            "Stop before sizing, execution, or account/order paths; this is research-only."
        ),
    },
}


def build_passive_liquidity_capabilities(
    *,
    feature_present: bool = False,
    feature_status: str = "",
    feature_summary: Mapping[str, Any] | None = None,
    observation_present: bool = False,
    observation_status: str = "",
    observation_summary: Mapping[str, Any] | None = None,
    model_present: bool = False,
    model_status: str = "",
    model_summary: Mapping[str, Any] | None = None,
    replay_present: bool = False,
    replay_status: str = "",
    replay_summary: Mapping[str, Any] | None = None,
    ccd_present: bool = False,
    ccd_status: str = "",
    ccd_summary: Mapping[str, Any] | None = None,
    cluster_present: bool = False,
    cluster_status: str = "",
    cluster_summary: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Build passive liquidity provision family capability gates (additive; other families untouched)."""
    model_summary_data = model_summary or {}
    replay_summary_data = replay_summary or {}
    ccd_summary_data = ccd_summary or {}
    cluster_summary_data = cluster_summary or {}
    feature_ready = feature_status == "passive_liquidity_provision_feature_packet_ready"
    return [
        _capability(
            "passive_liquidity_provision_feature_packet",
            "pass" if feature_ready else ("warn" if feature_present else "blocked"),
            (
                f"Passive liquidity provision feature packet status is `{feature_status}` with "
                f"{feature_summary.get('feature_row_count', 0)} feature row(s) and "
                f"{feature_summary.get('feature_ready_count', 0)} feature-ready row(s)."
                if feature_present
                else "No passive liquidity provision feature packet exists yet."
            ),
        ),
        _capability(
            "passive_liquidity_provision_observation_loop",
            "pass"
            if observation_present and "label" in observation_status.lower()
            else ("warn" if observation_present else "blocked"),
            (
                f"Passive liquidity provision observation loop status is `{observation_status}` with "
                f"{observation_summary.get('total_observation_row_count', 0)} total row(s)."
                if observation_present
                else "No passive liquidity provision microstructure observation loop report exists yet."
            ),
        ),
        _capability(
            "passive_liquidity_provision_feature_model_falsification",
            "pass"
            if "ready_with_research_candidates" in model_status
            else ("warn" if model_present else "blocked"),
            (
                f"Passive liquidity provision model falsification status is `{model_status}` with "
                f"{model_summary_data.get('independent_label_count', 0)} independent label(s), "
                f"{model_summary_data.get('oos_virtual_order_count', 0)} virtual order(s), and "
                f"{model_summary_data.get('maker_fill_net_ev_after_adverse_selection')} net EV after adverse selection."
                if model_present
                else "No passive liquidity provision feature-model falsification report exists yet."
            ),
        ),
        _capability(
            "passive_liquidity_provision_research_candidate_replay",
            "pass"
            if replay_present and "blocked_predeployment" in replay_status
            else ("warn" if replay_present else "blocked"),
            (
                f"Passive liquidity provision replay status is `{replay_status}` with "
                f"{replay_summary_data.get('replay_row_count', 0)} replay row(s) and "
                f"{replay_summary_data.get('positive_expected_value_row_count', 0)} positive cost-adjusted row(s)."
                if replay_present
                else "No passive liquidity provision research-candidate replay report exists yet."
            ),
        ),
        _capability(
            "passive_liquidity_provision_capacity_correlation_decay",
            "pass"
            if ccd_status == "passive_liquidity_provision_capacity_correlation_decay_ready_for_paper_overlay"
            else ("warn" if ccd_present else "blocked"),
            (
                f"Passive liquidity provision CCD status is `{ccd_status}` with "
                f"{ccd_summary_data.get('candidate_row_count', 0)} candidate(s)."
                if ccd_present
                else "No passive liquidity provision CCD gate report exists yet."
            ),
        ),
        _capability(
            "passive_liquidity_provision_correlation_cluster_control",
            "pass"
            if cluster_status == "passive_liquidity_provision_correlation_cluster_control_ready_for_paper_overlay"
            else ("warn" if cluster_present else "blocked"),
            (
                f"Passive liquidity provision cluster-control status is `{cluster_status}`."
                if cluster_present
                else "No passive liquidity provision correlation-cluster control report exists yet."
            ),
        ),
    ]


def compute_passive_liquidity_status(
    *,
    feature_present: bool = False,
    feature_status: str = "",
    observation_present: bool = False,
    observation_status: str = "",
    model_present: bool = False,
    model_status: str = "",
    replay_present: bool = False,
    replay_status: str = "",
    ccd_present: bool = False,
    ccd_status: str = "",
    cluster_present: bool = False,
    cluster_status: str = "",
) -> str:
    """Compute the passive liquidity provision family's individual status string."""
    if cluster_present and cluster_status:
        return "signal_factory_passive_liquidity_provision_cluster_control_ready"
    if ccd_present and ccd_status:
        if "ready_for_paper_overlay" in ccd_status:
            return "signal_factory_passive_liquidity_provision_ccd_ready"
        return "signal_factory_passive_liquidity_provision_ccd_blocked"
    if replay_present and replay_status:
        if "blocked_predeployment" in replay_status:
            return "signal_factory_passive_liquidity_provision_replay_blocked_predeployment_gates"
        if "ready_for_paper" in replay_status:
            return "signal_factory_passive_liquidity_provision_replay_ready_paper"
        return "signal_factory_passive_liquidity_provision_replay_blocked"
    if model_present and model_status:
        if "ready_with_research_candidates" in model_status:
            return "signal_factory_passive_liquidity_provision_falsification_ready"
        if "ready_no_research" in model_status:
            return "signal_factory_passive_liquidity_provision_falsification_no_candidates"
        return "signal_factory_passive_liquidity_provision_falsification_blocked"
    if feature_present and feature_status:
        obs_labels_ready = observation_present and "label" in observation_status.lower()
        obs_waiting = observation_present and "waiting" in observation_status.lower()
        if obs_labels_ready:
            return "signal_factory_passive_liquidity_provision_labels_ready"
        if obs_waiting:
            return "signal_factory_passive_liquidity_provision_observations_waiting_settlement"
        return "signal_factory_passive_liquidity_provision_feature_packet_ready"
    return "signal_factory_passive_liquidity_provision_blocked_missing_feature_packet"


def build_favorite_longshot_capabilities(
    *,
    feature_present: bool = False,
    feature_status: str = "",
    feature_summary: Mapping[str, Any] | None = None,
    observation_present: bool = False,
    observation_status: str = "",
    observation_summary: Mapping[str, Any] | None = None,
    model_present: bool = False,
    model_status: str = "",
    model_summary: Mapping[str, Any] | None = None,
    replay_present: bool = False,
    replay_status: str = "",
    replay_summary: Mapping[str, Any] | None = None,
    ccd_present: bool = False,
    ccd_status: str = "",
    ccd_summary: Mapping[str, Any] | None = None,
    cluster_present: bool = False,
    cluster_status: str = "",
    cluster_summary: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Build favorite-longshot bias family capability gates (additive; other families untouched)."""
    model_summary_data = model_summary or {}
    replay_summary_data = replay_summary or {}
    ccd_summary_data = ccd_summary or {}
    cluster_summary_data = cluster_summary or {}
    feature_ready = feature_status == "favorite_longshot_bias_feature_packet_ready"
    return [
        _capability(
            "favorite_longshot_bias_feature_packet",
            "pass" if feature_ready else ("warn" if feature_present else "blocked"),
            (
                f"Favorite-longshot bias feature packet status is `{feature_status}` with "
                f"{feature_summary.get('feature_row_count', 0)} feature row(s) and "
                f"{feature_summary.get('feature_ready_count', 0)} feature-ready row(s)."
                if feature_present
                else "No favorite-longshot bias feature packet exists yet."
            ),
        ),
        _capability(
            "favorite_longshot_bias_observation_loop",
            "pass"
            if observation_present and "label" in observation_status.lower()
            else ("warn" if observation_present else "blocked"),
            (
                f"Favorite-longshot bias observation loop status is `{observation_status}` with "
                f"{observation_summary.get('total_observation_row_count', 0)} total row(s)."
                if observation_present
                else "No favorite-longshot bias observation loop report exists yet."
            ),
        ),
        _capability(
            "favorite_longshot_bias_feature_model_falsification",
            "pass"
            if "ready_with_research_candidates" in model_status
            else ("warn" if model_present else "blocked"),
            (
                f"Favorite-longshot bias model falsification status is `{model_status}` with "
                f"{model_summary_data.get('independent_contract_label_count', 0)} independent label(s), "
                f"{model_summary_data.get('testable_model_count', 0)} testable model(s), and "
                f"{model_summary_data.get('research_candidate_count', 0)} research candidate(s)."
                if model_present
                else "No favorite-longshot bias feature-model falsification report exists yet."
            ),
        ),
        _capability(
            "favorite_longshot_bias_research_candidate_replay",
            "pass"
            if replay_present and "blocked_predeployment" in replay_status
            else ("warn" if replay_present else "blocked"),
            (
                f"Favorite-longshot bias replay status is `{replay_status}` with "
                f"{replay_summary_data.get('replay_row_count', 0)} replay row(s) and "
                f"{replay_summary_data.get('positive_expected_value_row_count', 0)} positive cost-adjusted row(s)."
                if replay_present
                else "No favorite-longshot bias research-candidate replay report exists yet."
            ),
        ),
        _capability(
            "favorite_longshot_bias_capacity_correlation_decay",
            "pass"
            if ccd_status == "favorite_longshot_bias_capacity_correlation_decay_ready_for_paper_overlay"
            else ("warn" if ccd_present else "blocked"),
            (
                f"Favorite-longshot bias CCD status is `{ccd_status}` with "
                f"{ccd_summary_data.get('candidate_row_count', 0)} candidate(s)."
                if ccd_present
                else "No favorite-longshot bias CCD gate report exists yet."
            ),
        ),
        _capability(
            "favorite_longshot_bias_correlation_cluster_control",
            "pass"
            if cluster_status == "favorite_longshot_bias_correlation_cluster_control_ready_for_paper_overlay"
            else ("warn" if cluster_present else "blocked"),
            (
                f"Favorite-longshot bias cluster-control status is `{cluster_status}`."
                if cluster_present
                else "No favorite-longshot bias correlation-cluster control report exists yet."
            ),
        ),
    ]


def compute_favorite_longshot_status(
    *,
    feature_present: bool = False,
    feature_status: str = "",
    observation_present: bool = False,
    observation_status: str = "",
    model_present: bool = False,
    model_status: str = "",
    replay_present: bool = False,
    replay_status: str = "",
    ccd_present: bool = False,
    ccd_status: str = "",
    cluster_present: bool = False,
    cluster_status: str = "",
) -> str:
    """Compute the favorite-longshot bias family's individual status string."""
    if cluster_present and cluster_status:
        return "signal_factory_favorite_longshot_bias_cluster_control_ready"
    if ccd_present and ccd_status:
        if "ready_for_paper_overlay" in ccd_status:
            return "signal_factory_favorite_longshot_bias_ccd_ready"
        return "signal_factory_favorite_longshot_bias_ccd_blocked"
    if replay_present and replay_status:
        if "blocked_predeployment" in replay_status:
            return "signal_factory_favorite_longshot_bias_replay_blocked_predeployment_gates"
        if "ready_for_paper" in replay_status:
            return "signal_factory_favorite_longshot_bias_replay_ready_paper"
        return "signal_factory_favorite_longshot_bias_replay_blocked"
    if model_present and model_status:
        if "ready_with_research_candidates" in model_status:
            return "signal_factory_favorite_longshot_bias_falsification_ready"
        if "ready_no_research" in model_status:
            return "signal_factory_favorite_longshot_bias_falsification_no_candidates"
        return "signal_factory_favorite_longshot_bias_falsification_blocked"
    if feature_present and feature_status:
        obs_labels_ready = observation_present and "label" in observation_status.lower()
        obs_waiting = observation_present and "waiting" in observation_status.lower()
        if obs_labels_ready:
            return "signal_factory_favorite_longshot_bias_labels_ready"
        if obs_waiting:
            return "signal_factory_favorite_longshot_bias_observations_waiting_settlement"
        return "signal_factory_favorite_longshot_bias_feature_packet_ready"
    return "signal_factory_favorite_longshot_bias_blocked_missing_feature_packet"


def select_leading_family(
    *,
    crypto_status: str,
    sports_status: str,
    weather_status: str = "",
    favorite_longshot_status: str = "",
    passive_liquidity_status: str = "",
) -> tuple[str, str, str]:
    """Select the leading family for the top-level status.

    Returns ``(top_level_status, selected_family_id, reason)``.  The leading
    family is the one with the highest advancement rank; ties resolve to
    crypto_proxy (the default lane) to preserve backward compatibility.
    """
    crypto_rank = family_status_rank(crypto_status)
    sports_rank = family_status_rank(sports_status)
    weather_rank = family_status_rank(weather_status)
    fav_rank = family_status_rank(favorite_longshot_status)
    pl_rank = family_status_rank(passive_liquidity_status)
    # Order matters for ties: crypto first (default lane), then sports, then weather
    ranked = [
        (crypto_rank, crypto_status, CRYPTO_PROXY_FAMILY_ID),
        (sports_rank, sports_status, SPORTS_BASEBALL_FAMILY_ID),
        (weather_rank, weather_status, WEATHER_PROXY_FAMILY_ID),
        (fav_rank, favorite_longshot_status, FAVORITE_LONGSHOT_FAMILY_ID),
        (pl_rank, passive_liquidity_status, PASSIVE_LIQUIDITY_FAMILY_ID),
    ]
    # When all ranks are 0 (blocked), use the legacy top-level status (crypto)
    if all(r == 0 for r, _, _ in ranked):
        return (
            crypto_status,
            CRYPTO_PROXY_FAMILY_ID,
            "All families are blocked; crypto_proxy is the default lane.",
        )
    best = max(ranked, key=lambda item: (item[0], 0 if item[2] == CRYPTO_PROXY_FAMILY_ID else 1))
    return (
        best[1],
        best[2],
        f"{best[2]} rank {best[0]} is the leading family.",
    )
