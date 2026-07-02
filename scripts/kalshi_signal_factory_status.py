#!/usr/bin/env python3
"""North-star Kalshi signal factory status.

This report keeps the operation honest: universe inventory is not an edge,
softness is not a signal, and positive EV rows are not deployable until the
falsification, capacity, correlation, sizing, execution-control, and decay
loops exist.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_UNIVERSE_SCAN_PATH = MACRO_DIR / "latest-kalshi-universe-scan.json"
DEFAULT_EV_LEDGER_PATH = MACRO_DIR / "latest-kalshi-contract-ev-ledger.json"
DEFAULT_REVIEW_QUEUE_PATH = MACRO_DIR / "latest-kalshi-ev-review-queue.json"
DEFAULT_ROBUSTNESS_PATH = MACRO_DIR / "latest-kalshi-ev-queue-robustness.json"
DEFAULT_HYPOTHESIS_REGISTRY_PATH = MACRO_DIR / "latest-kalshi-hypothesis-registry.json"
DEFAULT_FALSIFICATION_GATE_PATH = MACRO_DIR / "latest-kalshi-falsification-gate.json"
DEFAULT_LABELED_OBSERVATION_BUILDER_PATH = MACRO_DIR / "latest-kalshi-labeled-observation-builder.json"
DEFAULT_LABELED_OOS_BACKTEST_PATH = MACRO_DIR / "latest-kalshi-labeled-oos-backtest.json"
DEFAULT_PROBABILITY_BREADTH_SCOUT_PATH = MACRO_DIR / "latest-kalshi-probability-breadth-scout.json"
DEFAULT_CRYPTO_PROXY_FEATURE_PACKET_PATH = MACRO_DIR / "latest-kalshi-crypto-proxy-feature-packet.json"
DEFAULT_CRYPTO_PROXY_OBSERVATION_LOOP_PATH = MACRO_DIR / "latest-kalshi-crypto-proxy-observation-loop.json"
DEFAULT_CRYPTO_PROXY_MODEL_FALSIFICATION_PATH = (
    MACRO_DIR / "latest-kalshi-crypto-proxy-feature-model-falsification.json"
)
DEFAULT_CRYPTO_PROXY_RESEARCH_CANDIDATE_REPLAY_PATH = (
    MACRO_DIR / "latest-kalshi-crypto-proxy-research-candidate-replay.json"
)
DEFAULT_CRYPTO_PROXY_CAPACITY_CORRELATION_DECAY_PATH = (
    MACRO_DIR / "latest-kalshi-crypto-proxy-capacity-correlation-decay.json"
)
DEFAULT_CRYPTO_PROXY_CORRELATION_CLUSTER_CONTROL_PATH = (
    MACRO_DIR / "latest-kalshi-crypto-proxy-correlation-cluster-control.json"
)
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-signal-factory-status-latest"

CCD_SIGNAL_STATUSES = {
    "crypto_proxy_capacity_correlation_decay_ready_for_paper_overlay": (
        "signal_factory_crypto_proxy_capacity_correlation_decay_ready_paper_overlay"
    ),
    "crypto_proxy_capacity_correlation_decay_blocked_capacity_depth": (
        "signal_factory_crypto_proxy_capacity_depth_blocked"
    ),
    "crypto_proxy_capacity_correlation_decay_blocked_correlation_concentration": (
        "signal_factory_crypto_proxy_correlation_concentration_blocked"
    ),
    "crypto_proxy_capacity_correlation_decay_blocked_decay_survival": (
        "signal_factory_crypto_proxy_decay_survival_blocked"
    ),
    "crypto_proxy_capacity_correlation_decay_blocked_no_current_candidates": (
        "signal_factory_crypto_proxy_current_candidates_missing"
    ),
    "crypto_proxy_capacity_correlation_decay_failed_safety_gate": (
        "signal_factory_crypto_proxy_capacity_correlation_decay_failed_safety_gate"
    ),
}

CCD_NEXT_TRANCHES = {
    "crypto_proxy_capacity_correlation_decay_ready_for_paper_overlay": {
        "name": "kalshi_crypto_proxy_paper_probability_overlay",
        "why": "Capacity, correlation, and decay gates passed for the current research-only crypto proxy candidate set.",
        "stop_condition": "Stop before real positions, execution, account/order paths, staking, or live edge claims.",
    },
    "crypto_proxy_capacity_correlation_decay_blocked_capacity_depth": {
        "name": "kalshi_crypto_proxy_orderbook_depth_accumulation",
        "why": "The CCD gate exists but public orderbook depth is missing or not positive under the conservative probability hurdle.",
        "stop_condition": "Stop before inferring capacity from top-of-book prices without public depth.",
    },
    "crypto_proxy_capacity_correlation_decay_blocked_correlation_concentration": {
        "name": "kalshi_crypto_proxy_correlation_cluster_control",
        "why": "The CCD gate found positive depth, but current candidates are too concentrated in a venue/asset/contract-family bucket.",
        "stop_condition": "Stop before paper overlay until cluster exposure limits are machine-readable and passing.",
    },
    "crypto_proxy_capacity_correlation_decay_blocked_decay_survival": {
        "name": "kalshi_crypto_proxy_decay_and_sample_accumulation",
        "why": "Capacity/correlation gates are not enough; the signal still needs repeated settled-bucket decay survival.",
        "stop_condition": "Stop before lowering decay or sample thresholds without an explicit policy review.",
    },
    "crypto_proxy_capacity_correlation_decay_blocked_no_current_candidates": {
        "name": "kalshi_crypto_proxy_observation_accumulation",
        "why": "The CCD gate found no current close-window crypto proxy candidates; refresh observations before retrying depth.",
        "stop_condition": "Stop before treating stale expired replay rows as current capacity evidence.",
    },
    "crypto_proxy_capacity_correlation_decay_failed_safety_gate": {
        "name": "kalshi_crypto_proxy_capacity_correlation_decay_safety_audit",
        "why": "The CCD gate failed a research-only safety condition.",
        "stop_condition": (
            "Stop before any paper overlay, sizing, execution, or account/order path until the failed safety gate is fixed."
        ),
    },
}

CLUSTER_CONTROL_SIGNAL_STATUSES = {
    "crypto_proxy_correlation_cluster_control_ready_for_paper_overlay": (
        "signal_factory_crypto_proxy_cluster_control_ready_paper_overlay"
    ),
    "crypto_proxy_correlation_cluster_control_blocked_insufficient_clusters": (
        "signal_factory_crypto_proxy_cluster_breadth_blocked"
    ),
    "crypto_proxy_correlation_cluster_control_blocked_share_limit": (
        "signal_factory_crypto_proxy_cluster_share_blocked"
    ),
    "crypto_proxy_correlation_cluster_control_blocked_upstream_ccd": (
        "signal_factory_crypto_proxy_cluster_control_blocked_upstream_ccd"
    ),
    "crypto_proxy_correlation_cluster_control_blocked_missing_ccd": (
        "signal_factory_crypto_proxy_cluster_control_missing_ccd"
    ),
    "crypto_proxy_correlation_cluster_control_blocked_no_positive_depth": (
        "signal_factory_crypto_proxy_cluster_control_no_positive_depth"
    ),
    "crypto_proxy_correlation_cluster_control_failed_safety_gate": (
        "signal_factory_crypto_proxy_cluster_control_failed_safety_gate"
    ),
}

CLUSTER_CONTROL_NEXT_TRANCHES = {
    "crypto_proxy_correlation_cluster_control_ready_for_paper_overlay": {
        "name": "kalshi_crypto_proxy_paper_probability_overlay",
        "why": "Capacity, decay, and controlled cluster exposure pass for the current research-only crypto proxy candidate set.",
        "stop_condition": "Stop before real positions, execution, account/order paths, staking, or live edge claims.",
    },
    "crypto_proxy_correlation_cluster_control_blocked_insufficient_clusters": {
        "name": "kalshi_crypto_proxy_cluster_breadth_accumulation",
        "why": (
            "Positive depth exists, but it is not spread across enough independent correlation clusters "
            "to satisfy the configured exposure cap."
        ),
        "stop_condition": "Stop before reducing cluster breadth requirements without an explicit policy review.",
    },
    "crypto_proxy_correlation_cluster_control_blocked_share_limit": {
        "name": "kalshi_crypto_proxy_cluster_cap_refinement",
        "why": "Cluster breadth exists, but the deterministic cap cannot produce a share-limited candidate set.",
        "stop_condition": "Stop before paper overlay until the controlled share limit is passing.",
    },
    "crypto_proxy_correlation_cluster_control_blocked_upstream_ccd": {
        "name": "kalshi_crypto_proxy_capacity_correlation_decay",
        "why": "Cluster control is blocked because the upstream capacity/depth/decay report is not passing its prerequisites.",
        "stop_condition": "Stop before paper overlay until upstream CCD evidence is current and passing.",
    },
    "crypto_proxy_correlation_cluster_control_blocked_missing_ccd": {
        "name": "kalshi_crypto_proxy_capacity_correlation_decay",
        "why": "Cluster control is blocked because the upstream capacity/depth/decay report is missing.",
        "stop_condition": "Stop before paper overlay until upstream CCD evidence exists.",
    },
    "crypto_proxy_correlation_cluster_control_blocked_no_positive_depth": {
        "name": "kalshi_crypto_proxy_orderbook_depth_accumulation",
        "why": "Cluster control found no positive-depth capacity to allocate after upstream CCD.",
        "stop_condition": "Stop before inferring capacity from top-of-book prices without public depth.",
    },
    "crypto_proxy_correlation_cluster_control_failed_safety_gate": {
        "name": "kalshi_crypto_proxy_cluster_control_safety_audit",
        "why": "The cluster-control report failed a research-only safety condition.",
        "stop_condition": (
            "Stop before any paper overlay, sizing, execution, or account/order path until the failed safety gate is fixed."
        ),
    },
}


@dataclass(frozen=True)
class Artifacts:
    """Bundle of all upstream artifact paths consumed by the status report.

    This eliminates the footgun of forgetting a path parameter: every path
    is covered by the bundle, so callers cannot accidentally leak real on-disk
    state through a forgotten default.
    """

    universe_scan_path: Path
    ev_ledger_path: Path
    review_queue_path: Path
    robustness_path: Path
    hypothesis_registry_path: Path
    falsification_gate_path: Path
    labeled_observation_builder_path: Path
    labeled_oos_backtest_path: Path
    probability_breadth_scout_path: Path
    crypto_proxy_feature_packet_path: Path
    crypto_proxy_observation_loop_path: Path
    crypto_proxy_model_falsification_path: Path
    crypto_proxy_research_candidate_replay_path: Path
    crypto_proxy_capacity_correlation_decay_path: Path
    crypto_proxy_correlation_cluster_control_path: Path

    @classmethod
    def isolated(cls, base: Path) -> Artifacts:
        """Return a bundle where every path points to a missing file under *base*.

        Use ``dataclasses.replace`` to override individual fields with real
        artifact paths.  This is the hermetic default for tests.
        """
        return cls(
            universe_scan_path=base / "missing-universe.json",
            ev_ledger_path=base / "missing-ledger.json",
            review_queue_path=base / "missing-queue.json",
            robustness_path=base / "missing-robustness.json",
            hypothesis_registry_path=base / "missing-registry.json",
            falsification_gate_path=base / "missing-falsification.json",
            labeled_observation_builder_path=base / "missing-builder.json",
            labeled_oos_backtest_path=base / "missing-oos.json",
            probability_breadth_scout_path=base / "missing-breadth.json",
            crypto_proxy_feature_packet_path=base / "missing-crypto-feature.json",
            crypto_proxy_observation_loop_path=base / "missing-crypto-observation.json",
            crypto_proxy_model_falsification_path=base / "missing-crypto-model.json",
            crypto_proxy_research_candidate_replay_path=base / "missing-crypto-replay.json",
            crypto_proxy_capacity_correlation_decay_path=base / "missing-crypto-ccd.json",
            crypto_proxy_correlation_cluster_control_path=base / "missing-crypto-cluster-control.json",
        )

    @classmethod
    def from_macro_dir(cls, macro_dir: Path = MACRO_DIR) -> Artifacts:
        """Production default bundle resolving all paths under the macro dir."""
        return cls(
            universe_scan_path=macro_dir / "latest-kalshi-universe-scan.json",
            ev_ledger_path=macro_dir / "latest-kalshi-contract-ev-ledger.json",
            review_queue_path=macro_dir / "latest-kalshi-ev-review-queue.json",
            robustness_path=macro_dir / "latest-kalshi-ev-queue-robustness.json",
            hypothesis_registry_path=macro_dir / "latest-kalshi-hypothesis-registry.json",
            falsification_gate_path=macro_dir / "latest-kalshi-falsification-gate.json",
            labeled_observation_builder_path=macro_dir / "latest-kalshi-labeled-observation-builder.json",
            labeled_oos_backtest_path=macro_dir / "latest-kalshi-labeled-oos-backtest.json",
            probability_breadth_scout_path=macro_dir / "latest-kalshi-probability-breadth-scout.json",
            crypto_proxy_feature_packet_path=macro_dir / "latest-kalshi-crypto-proxy-feature-packet.json",
            crypto_proxy_observation_loop_path=macro_dir / "latest-kalshi-crypto-proxy-observation-loop.json",
            crypto_proxy_model_falsification_path=macro_dir
            / "latest-kalshi-crypto-proxy-feature-model-falsification.json",
            crypto_proxy_research_candidate_replay_path=macro_dir
            / "latest-kalshi-crypto-proxy-research-candidate-replay.json",
            crypto_proxy_capacity_correlation_decay_path=macro_dir
            / "latest-kalshi-crypto-proxy-capacity-correlation-decay.json",
            crypto_proxy_correlation_cluster_control_path=(
                macro_dir / "latest-kalshi-crypto-proxy-correlation-cluster-control.json"
            ),
        )


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_signal_factory_status(
    *,
    artifacts: Artifacts,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    universe = read_json_or_empty(artifacts.universe_scan_path)
    ledger = read_json_or_empty(artifacts.ev_ledger_path)
    queue = read_json_or_empty(artifacts.review_queue_path)
    robustness = read_json_or_empty(artifacts.robustness_path)
    registry = read_json_or_empty(artifacts.hypothesis_registry_path)
    falsification_gate = read_json_or_empty(artifacts.falsification_gate_path)
    observation_builder = read_json_or_empty(artifacts.labeled_observation_builder_path)
    labeled_oos = read_json_or_empty(artifacts.labeled_oos_backtest_path)
    probability_breadth_scout = read_json_or_empty(artifacts.probability_breadth_scout_path)
    crypto_proxy_feature_packet = read_json_or_empty(artifacts.crypto_proxy_feature_packet_path)
    crypto_proxy_observation_loop = read_json_or_empty(artifacts.crypto_proxy_observation_loop_path)
    crypto_proxy_model_falsification = read_json_or_empty(artifacts.crypto_proxy_model_falsification_path)
    crypto_proxy_research_candidate_replay = read_json_or_empty(artifacts.crypto_proxy_research_candidate_replay_path)
    crypto_proxy_capacity_correlation_decay = read_json_or_empty(artifacts.crypto_proxy_capacity_correlation_decay_path)
    crypto_proxy_correlation_cluster_control = read_json_or_empty(
        artifacts.crypto_proxy_correlation_cluster_control_path
    )

    universe_summary = summary(universe)
    ledger_summary = summary(ledger)
    queue_summary = summary(queue)
    robustness_summary = summary(robustness)
    registry_summary = summary(registry)
    observation_builder_summary = summary(observation_builder)
    labeled_oos_summary = summary(labeled_oos)
    probability_breadth_summary = summary(probability_breadth_scout)
    crypto_proxy_feature_summary = summary(crypto_proxy_feature_packet)
    crypto_proxy_observation_summary = summary(crypto_proxy_observation_loop)
    crypto_proxy_model_summary = summary(crypto_proxy_model_falsification)
    crypto_proxy_replay_summary = summary(crypto_proxy_research_candidate_replay)
    crypto_proxy_ccd_summary = summary(crypto_proxy_capacity_correlation_decay)
    crypto_proxy_cluster_summary = summary(crypto_proxy_correlation_cluster_control)
    falsification_summary = gate_summary(falsification_gate)
    registry_ready = safe_research_artifact(registry) and int(registry_summary.get("hypothesis_count") or 0) > 0
    falsification_status = str(falsification_gate.get("status") or "")
    falsification_present = safe_research_artifact(falsification_gate) and bool(falsification_status)
    falsification_blocked = not falsification_present or falsification_status.startswith("falsification_gate_blocked")
    labeled_oos_present = safe_research_artifact(labeled_oos) and bool(labeled_oos.get("status"))
    labeled_oos_status = str(labeled_oos.get("status") or "")
    observation_builder_present = safe_research_artifact(observation_builder) and bool(
        observation_builder.get("status")
    )
    observation_builder_status = str(observation_builder.get("status") or "")
    probability_breadth_present = safe_research_artifact(probability_breadth_scout) and bool(
        probability_breadth_scout.get("status")
    )
    probability_breadth_status = str(probability_breadth_scout.get("status") or "")
    probability_breadth_ready = probability_breadth_status in {
        "probability_breadth_scout_ready_crypto_proxy_feature_route",
        "probability_breadth_scout_ready_crypto_route_needs_proxy_probe",
        "probability_breadth_scout_ready_weather_reference_route",
    }
    crypto_proxy_feature_present = safe_research_artifact(crypto_proxy_feature_packet) and bool(
        crypto_proxy_feature_packet.get("status")
    )
    crypto_proxy_feature_status = str(crypto_proxy_feature_packet.get("status") or "")
    crypto_proxy_feature_ready = crypto_proxy_feature_status == "crypto_proxy_feature_packet_ready"
    crypto_proxy_observation_present = safe_research_artifact(crypto_proxy_observation_loop) and bool(
        crypto_proxy_observation_loop.get("status")
    )
    crypto_proxy_observation_status = str(crypto_proxy_observation_loop.get("status") or "")
    crypto_proxy_observation_label_ready = (
        crypto_proxy_observation_status == "crypto_proxy_observation_loop_label_rows_ready"
    )
    crypto_proxy_observation_waiting = crypto_proxy_observation_status in {
        "crypto_proxy_observation_loop_ready_waiting_settlement",
        "crypto_proxy_observation_loop_observations_recorded_waiting_settlement",
    }
    crypto_proxy_model_present = safe_research_artifact(crypto_proxy_model_falsification) and bool(
        crypto_proxy_model_falsification.get("status")
    )
    crypto_proxy_model_status = str(crypto_proxy_model_falsification.get("status") or "")
    crypto_proxy_model_insufficient = crypto_proxy_model_status in {
        "crypto_proxy_feature_model_falsification_blocked_missing_labels",
        "crypto_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
        "crypto_proxy_feature_model_falsification_blocked_insufficient_oos_labels",
    }
    crypto_proxy_model_ready = crypto_proxy_model_status in {
        "crypto_proxy_feature_model_falsification_ready_no_research_candidates",
        "crypto_proxy_feature_model_falsification_ready_with_research_candidates",
    }
    crypto_proxy_replay_present = safe_research_artifact(crypto_proxy_research_candidate_replay) and bool(
        crypto_proxy_research_candidate_replay.get("status")
    )
    crypto_proxy_replay_status = str(crypto_proxy_research_candidate_replay.get("status") or "")
    crypto_proxy_replay_ready = crypto_proxy_replay_status in {
        "crypto_proxy_research_candidate_replay_blocked_predeployment_gates",
        "crypto_proxy_research_candidate_replay_ready_for_paper_probability_overlay",
        "crypto_proxy_research_candidate_replay_ready_no_positive_cost_adjusted_rows",
    }
    crypto_proxy_ccd_present = safe_research_artifact(crypto_proxy_capacity_correlation_decay) and bool(
        crypto_proxy_capacity_correlation_decay.get("status")
    )
    crypto_proxy_ccd_status = str(crypto_proxy_capacity_correlation_decay.get("status") or "")
    crypto_proxy_cluster_present = safe_research_artifact_present(crypto_proxy_correlation_cluster_control)
    crypto_proxy_cluster_status = str(crypto_proxy_correlation_cluster_control.get("status") or "")

    capabilities = [
        capability(
            "kalshi_universe_inventory",
            "pass"
            if safe_research_artifact(universe) and int(universe_summary.get("candidate_count") or 0) > 0
            else "blocked",
            (
                f"{universe_summary.get('candidate_count')} public-market candidates in the configured window."
                if safe_research_artifact(universe)
                else "Universe scanner artifact is missing or unsafe."
            ),
        ),
        capability(
            "deterministic_route_inventory",
            "pass" if int(universe_summary.get("model_route_candidate_count") or 0) > 0 else "warn",
            (
                f"{universe_summary.get('model_route_candidate_count')} model-route candidate(s), "
                f"{universe_summary.get('soft_watch_candidate_count')} soft-watch candidate(s)."
            ),
        ),
        capability(
            "contract_ev_ledger",
            "pass" if safe_research_artifact(ledger) and int(ledger_summary.get("row_count") or 0) > 0 else "blocked",
            (
                f"{ledger_summary.get('row_count')} contract EV row(s); "
                f"{ledger_summary.get('usable_row_count')} currently pass legacy research gates."
                if safe_research_artifact(ledger)
                else "Contract EV ledger is missing or unsafe."
            ),
        ),
        capability(
            "agentic_hypothesis_registry",
            "pass" if registry_ready else "blocked",
            (
                f"{registry_summary.get('hypothesis_count')} HypothesisCandidate row(s) across "
                f"{registry_summary.get('multiple_testing_family_count')} multiple-testing family/families."
                if registry_ready
                else "No HypothesisCandidate registry exists yet; signals are not generated or versioned systematically."
            ),
        ),
        capability(
            "fdr_controlled_falsification_gate",
            "blocked" if falsification_blocked else "pass",
            (
                f"Falsification gate is `{falsification_status}` with "
                f"{falsification_summary.get('registered_hypothesis_count', 0)} registered and "
                f"{falsification_summary.get('tested_hypothesis_count', 0)} tested hypothesis/hypotheses."
                if falsification_present
                else "No first-class FDR-controlled out-of-sample, cost-aware falsification gate exists yet."
            ),
        ),
        capability(
            "labeled_oos_backtest_harness",
            "pass" if labeled_oos_present else "blocked",
            (
                f"Labeled OOS harness status is `{labeled_oos_status}` with "
                f"{labeled_oos_summary.get('valid_observation_count', 0)} valid observation(s), "
                f"{labeled_oos_summary.get('testable_hypothesis_count', 0)} testable hypothesis/hypotheses, and "
                f"{labeled_oos_summary.get('promoted_research_hypothesis_count', 0)} research promotion(s)."
                if labeled_oos_present
                else "No labeled OOS replay/backtest harness report exists yet."
            ),
        ),
        capability(
            "labeled_observation_packet_builder",
            "pass" if observation_builder_present else "blocked",
            (
                f"Observation builder status is `{observation_builder_status}` with "
                f"{observation_builder_summary.get('total_pending_row_count', 0)} pending observation(s) and "
                f"{observation_builder_summary.get('label_row_count', 0)} label row(s)."
                if observation_builder_present
                else "No pending/settled observation packet builder report exists yet."
            ),
        ),
        capability(
            "calibrated_probability_feeds",
            "warn" if int(ledger_summary.get("calibrated_probability_overlay_row_count") or 0) > 0 else "blocked",
            (
                f"{ledger_summary.get('calibrated_probability_overlay_row_count')} calibrated probability overlay row(s), "
                "but no central probability decay/falsification registry."
            ),
        ),
        capability(
            "probability_breadth_scout",
            "pass" if probability_breadth_ready else ("warn" if probability_breadth_present else "blocked"),
            (
                f"Probability breadth scout status is `{probability_breadth_status}` with "
                f"{probability_breadth_summary.get('crypto_fast_candidate_count', 0)} fast crypto candidate(s), "
                f"{probability_breadth_summary.get('weather_fast_candidate_count', 0)} fast weather candidate(s), and "
                f"{probability_breadth_summary.get('available_proxy_source_count', 0)} available proxy source(s)."
                if probability_breadth_present
                else "No probability breadth scout exists yet for fast-settling routes."
            ),
        ),
        capability(
            "crypto_proxy_feature_packet",
            "pass" if crypto_proxy_feature_ready else ("warn" if crypto_proxy_feature_present else "blocked"),
            (
                f"Crypto proxy feature packet status is `{crypto_proxy_feature_status}` with "
                f"{crypto_proxy_feature_summary.get('feature_row_count', 0)} feature row(s), "
                f"{crypto_proxy_feature_summary.get('feature_ready_count', 0)} feature-ready row(s), and "
                f"{crypto_proxy_feature_summary.get('proxy_available_asset_count', 0)} proxy-covered asset(s)."
                if crypto_proxy_feature_present
                else "No contract-keyed crypto proxy feature packet exists yet."
            ),
        ),
        capability(
            "crypto_proxy_observation_loop",
            "pass"
            if crypto_proxy_observation_label_ready or crypto_proxy_observation_waiting
            else ("warn" if crypto_proxy_observation_present else "blocked"),
            (
                f"Crypto proxy observation loop status is `{crypto_proxy_observation_status}` with "
                f"{crypto_proxy_observation_summary.get('total_observation_row_count', 0)} total observation row(s), "
                f"{crypto_proxy_observation_summary.get('new_observation_row_count', 0)} new row(s), and "
                f"{crypto_proxy_observation_summary.get('label_row_count', 0)} settled label row(s)."
                if crypto_proxy_observation_present
                else "No repeated crypto proxy observation/label loop report exists yet."
            ),
        ),
        capability(
            "crypto_proxy_feature_model_falsification",
            "pass"
            if crypto_proxy_model_ready
            else ("warn" if crypto_proxy_model_insufficient else ("warn" if crypto_proxy_model_present else "blocked")),
            (
                f"Crypto proxy model falsification status is `{crypto_proxy_model_status}` with "
                f"{crypto_proxy_model_summary.get('independent_contract_label_count', 0)} independent label(s), "
                f"{crypto_proxy_model_summary.get('duplicate_label_row_count', 0)} duplicate label row(s), and "
                f"{crypto_proxy_model_summary.get('research_candidate_count', 0)} research candidate(s)."
                if crypto_proxy_model_present
                else "No crypto proxy feature-model falsification report exists yet."
            ),
        ),
        capability(
            "crypto_proxy_research_candidate_replay",
            "pass" if crypto_proxy_replay_ready else ("warn" if crypto_proxy_replay_present else "blocked"),
            (
                f"Crypto proxy research-candidate replay status is `{crypto_proxy_replay_status}` with "
                f"{crypto_proxy_replay_summary.get('replay_row_count', 0)} replay row(s), "
                f"{crypto_proxy_replay_summary.get('positive_expected_value_row_count', 0)} positive cost-adjusted row(s), "
                f"{crypto_proxy_replay_summary.get('conservative_calibrated_side_probability')} conservative selected-side probability, and "
                f"{crypto_proxy_replay_summary.get('usable_row_count', 0)} usable row(s)."
                if crypto_proxy_replay_present
                else "No crypto proxy cost/capacity/correlation/decay replay report exists yet."
            ),
        ),
        capability(
            "crypto_proxy_capacity_correlation_decay",
            "pass"
            if crypto_proxy_ccd_status == "crypto_proxy_capacity_correlation_decay_ready_for_paper_overlay"
            else ("warn" if crypto_proxy_ccd_present else "blocked"),
            (
                f"Crypto proxy capacity/correlation/decay status is `{crypto_proxy_ccd_status}` with "
                f"{crypto_proxy_ccd_summary.get('candidate_row_count', 0)} current candidate(s), "
                f"{crypto_proxy_ccd_summary.get('orderbook_count', 0)} orderbook(s), "
                f"{crypto_proxy_ccd_summary.get('positive_depth_contracts', 0)} positive-depth contract(s), "
                f"largest cluster share `{crypto_proxy_ccd_summary.get('largest_correlation_cluster_share')}`, and "
                f"decay status `{crypto_proxy_ccd_summary.get('decay_status')}`."
                if crypto_proxy_ccd_present
                else "No crypto proxy capacity/correlation/decay gate report exists yet."
            ),
        ),
        crypto_proxy_cluster_control_capability(
            status=crypto_proxy_cluster_status,
            summary_data=crypto_proxy_cluster_summary,
            present=crypto_proxy_cluster_present,
        ),
        capability(
            "capacity_model",
            "pass" if crypto_proxy_ccd_summary.get("capacity_status") == "capacity_depth_positive" else "blocked",
            (
                f"Crypto proxy capacity depth status is `{crypto_proxy_ccd_summary.get('capacity_status')}` with "
                f"{crypto_proxy_ccd_summary.get('positive_depth_contracts', 0)} positive-depth contract(s)."
                if crypto_proxy_ccd_present
                else "No ghost-listing-adjusted capacity model exists; liquidity/price-impact constraints are not quantified."
            ),
        ),
        capability(
            "correlation_model",
            "pass"
            if crypto_proxy_cluster_status == "crypto_proxy_correlation_cluster_control_ready_for_paper_overlay"
            else "blocked",
            (
                f"Crypto proxy cluster-control status is `{crypto_proxy_cluster_status}`; "
                f"largest controlled cluster share is `{crypto_proxy_cluster_summary.get('largest_controlled_cluster_share')}`."
                if crypto_proxy_cluster_present
                else "No within-venue correlation-cluster exposure control exists for the current candidate set."
            ),
        ),
        capability(
            "fractional_kelly_sizing_policy",
            "blocked",
            "Sizing is intentionally disabled until falsification, capacity, and correlation gates exist.",
        ),
        capability(
            "execution_control_plane",
            "blocked",
            "Execution remains disabled; no account/order path should be wired before the audited sizing and kill-switch gates.",
        ),
        capability(
            "realized_pnl_decay_loop",
            "blocked",
            "No realized P&L and signal-decay retirement loop exists yet.",
        ),
    ]
    gate_counts = count_statuses(capabilities)
    universe_ready = gate_by_name(capabilities, "kalshi_universe_inventory")["status"] == "pass"
    crypto_proxy_gate_signal_status = crypto_proxy_gate_status(
        cluster_status=crypto_proxy_cluster_status,
        ccd_status=crypto_proxy_ccd_status,
        ccd_summary=crypto_proxy_ccd_summary,
    )
    crypto_proxy_chain_context_ready = (
        universe_ready
        and registry_ready
        and labeled_oos_status == "labeled_oos_backtest_blocked_missing_labeled_observations"
        and observation_builder_status == "labeled_observation_builder_pending_observations_waiting_settlement"
    )
    if crypto_proxy_chain_context_ready and crypto_proxy_gate_signal_status:
        status = crypto_proxy_gate_signal_status
    elif (
        universe_ready
        and registry_ready
        and labeled_oos_status == "labeled_oos_backtest_blocked_missing_labeled_observations"
        and observation_builder_status == "labeled_observation_builder_pending_observations_waiting_settlement"
        and crypto_proxy_replay_status == "crypto_proxy_research_candidate_replay_blocked_predeployment_gates"
    ):
        status = "signal_factory_crypto_proxy_replay_blocked_predeployment_gates"
    elif (
        universe_ready
        and registry_ready
        and labeled_oos_status == "labeled_oos_backtest_blocked_missing_labeled_observations"
        and observation_builder_status == "labeled_observation_builder_pending_observations_waiting_settlement"
        and crypto_proxy_replay_status == "crypto_proxy_research_candidate_replay_ready_for_paper_probability_overlay"
    ):
        status = "signal_factory_crypto_proxy_replay_ready_paper_overlay"
    elif (
        universe_ready
        and registry_ready
        and labeled_oos_status == "labeled_oos_backtest_blocked_missing_labeled_observations"
        and observation_builder_status == "labeled_observation_builder_pending_observations_waiting_settlement"
        and crypto_proxy_replay_status == "crypto_proxy_research_candidate_replay_ready_no_positive_cost_adjusted_rows"
    ):
        status = "signal_factory_crypto_proxy_replay_no_positive_cost_adjusted_rows"
    elif (
        universe_ready
        and registry_ready
        and labeled_oos_status == "labeled_oos_backtest_blocked_missing_labeled_observations"
        and observation_builder_status == "labeled_observation_builder_pending_observations_waiting_settlement"
        and crypto_proxy_model_status == "crypto_proxy_feature_model_falsification_ready_with_research_candidates"
    ):
        status = "signal_factory_crypto_proxy_feature_model_research_candidates"
    elif (
        universe_ready
        and registry_ready
        and labeled_oos_status == "labeled_oos_backtest_blocked_missing_labeled_observations"
        and observation_builder_status == "labeled_observation_builder_pending_observations_waiting_settlement"
        and crypto_proxy_model_status == "crypto_proxy_feature_model_falsification_ready_no_research_candidates"
    ):
        status = "signal_factory_crypto_proxy_feature_model_no_research_candidates"
    elif (
        universe_ready
        and registry_ready
        and labeled_oos_status == "labeled_oos_backtest_blocked_missing_labeled_observations"
        and observation_builder_status == "labeled_observation_builder_pending_observations_waiting_settlement"
        and crypto_proxy_model_insufficient
    ):
        status = "signal_factory_crypto_proxy_feature_model_insufficient_labels"
    elif (
        universe_ready
        and registry_ready
        and labeled_oos_status == "labeled_oos_backtest_blocked_missing_labeled_observations"
        and observation_builder_status == "labeled_observation_builder_pending_observations_waiting_settlement"
        and crypto_proxy_observation_label_ready
    ):
        status = "signal_factory_crypto_proxy_labels_ready"
    elif (
        universe_ready
        and registry_ready
        and labeled_oos_status == "labeled_oos_backtest_blocked_missing_labeled_observations"
        and observation_builder_status == "labeled_observation_builder_pending_observations_waiting_settlement"
        and crypto_proxy_observation_waiting
    ):
        status = "signal_factory_crypto_proxy_observations_waiting_settlement"
    elif (
        universe_ready
        and registry_ready
        and labeled_oos_status == "labeled_oos_backtest_blocked_missing_labeled_observations"
        and observation_builder_status == "labeled_observation_builder_pending_observations_waiting_settlement"
        and crypto_proxy_feature_status == "crypto_proxy_feature_packet_ready"
    ):
        status = "signal_factory_crypto_proxy_feature_packet_ready"
    elif (
        universe_ready
        and registry_ready
        and labeled_oos_status == "labeled_oos_backtest_blocked_missing_labeled_observations"
        and observation_builder_status == "labeled_observation_builder_pending_observations_waiting_settlement"
        and probability_breadth_status == "probability_breadth_scout_ready_crypto_proxy_feature_route"
    ):
        status = "signal_factory_probability_breadth_scout_ready_crypto_proxy_route"
    elif (
        universe_ready
        and registry_ready
        and labeled_oos_status == "labeled_oos_backtest_blocked_missing_labeled_observations"
        and observation_builder_status == "labeled_observation_builder_pending_observations_waiting_settlement"
    ):
        status = "signal_factory_oos_pending_observations_waiting_settlement"
    elif (
        universe_ready
        and registry_ready
        and labeled_oos_status == "labeled_oos_backtest_blocked_missing_labeled_observations"
        and observation_builder_status == "labeled_observation_builder_label_packet_ready"
    ):
        status = "signal_factory_oos_label_packet_ready_backtest_pending"
    elif (
        universe_ready
        and registry_ready
        and labeled_oos_status == "labeled_oos_backtest_blocked_missing_labeled_observations"
    ):
        status = "signal_factory_oos_backtest_harness_ready_labeled_observations_missing"
    elif (
        universe_ready
        and registry_ready
        and labeled_oos_status == "labeled_oos_backtest_blocked_insufficient_oos_samples"
    ):
        status = "signal_factory_oos_backtest_harness_ready_oos_samples_insufficient"
    elif (
        universe_ready
        and registry_ready
        and labeled_oos_status == "labeled_oos_backtest_ready_with_research_promotions"
    ):
        status = "signal_factory_oos_backtest_ready_research_promotions_present"
    elif universe_ready and registry_ready and falsification_blocked:
        status = "signal_factory_hypothesis_registry_ready_falsification_blocked_missing_labeled_oos_evidence"
    elif universe_ready and gate_by_name(capabilities, "fdr_controlled_falsification_gate")["status"] == "blocked":
        status = "signal_factory_foundation_ready_falsification_missing"
    elif universe_ready:
        status = "signal_factory_foundation_ready"
    else:
        status = "signal_factory_blocked_missing_universe_inventory"

    return {
        "schema_version": 1,
        "generated_utc": generated_utc or utc_now(),
        "status": status,
        "north_star": "Extract and exploit mispricings in Kalshi event contracts before the crowd corrects them.",
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": False,
        "authenticated_api_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "axioms": {
            "no_discretion": "Human judgment may configure systems but must not select trades, entries, exits, or sizing.",
            "signal_breadth_over_depth": "The operation scales through many weak, uncorrelated signals, not concentrated conviction.",
            "capacity_discipline": "Position sizing must be capped by ghost-listing-adjusted liquidity and price-impact estimates.",
        },
        "summary": {
            "universe_candidate_count": universe_summary.get("candidate_count", 0),
            "model_route_candidate_count": universe_summary.get("model_route_candidate_count", 0),
            "soft_watch_candidate_count": universe_summary.get("soft_watch_candidate_count", 0),
            "classification_counts": universe_summary.get("classification_counts", {}),
            "ev_ledger_row_count": ledger_summary.get("row_count", 0),
            "legacy_usable_ev_row_count": ledger_summary.get("usable_row_count", 0),
            "review_queue_row_count": queue_summary.get("queued_row_count", 0),
            "repeat_positive_row_count": robustness_summary.get("repeat_positive_row_count", 0),
            "hypothesis_count": registry_summary.get("hypothesis_count", 0),
            "candidate_unvalidated_hypothesis_count": registry_summary.get("candidate_unvalidated_count", 0),
            "multiple_testing_family_count": registry_summary.get("multiple_testing_family_count", 0),
            "falsification_status": falsification_status or None,
            "blocked_by_falsification_count": registry_summary.get("blocked_by_falsification_count", 0),
            "labeled_observation_builder_status": observation_builder_status or None,
            "labeled_observation_pending_count": observation_builder_summary.get("total_pending_row_count", 0),
            "labeled_observation_label_row_count": observation_builder_summary.get("label_row_count", 0),
            "labeled_oos_backtest_status": labeled_oos_status or None,
            "labeled_oos_valid_observation_count": labeled_oos_summary.get("valid_observation_count", 0),
            "labeled_oos_testable_hypothesis_count": labeled_oos_summary.get("testable_hypothesis_count", 0),
            "labeled_oos_promoted_research_hypothesis_count": labeled_oos_summary.get(
                "promoted_research_hypothesis_count", 0
            ),
            "probability_breadth_scout_status": probability_breadth_status or None,
            "probability_breadth_fast_candidate_count": probability_breadth_summary.get("fast_candidate_count", 0),
            "probability_breadth_crypto_fast_candidate_count": probability_breadth_summary.get(
                "crypto_fast_candidate_count", 0
            ),
            "probability_breadth_weather_fast_candidate_count": probability_breadth_summary.get(
                "weather_fast_candidate_count", 0
            ),
            "probability_breadth_available_proxy_source_count": probability_breadth_summary.get(
                "available_proxy_source_count", 0
            ),
            "probability_breadth_selected_route": probability_breadth_summary.get("selected_route"),
            "crypto_proxy_feature_packet_status": crypto_proxy_feature_status or None,
            "crypto_proxy_feature_row_count": crypto_proxy_feature_summary.get("feature_row_count", 0),
            "crypto_proxy_feature_ready_count": crypto_proxy_feature_summary.get("feature_ready_count", 0),
            "crypto_proxy_feature_asset_counts": crypto_proxy_feature_summary.get("asset_counts", {}),
            "crypto_proxy_observation_loop_status": crypto_proxy_observation_status or None,
            "crypto_proxy_observation_total_count": crypto_proxy_observation_summary.get(
                "total_observation_row_count", 0
            ),
            "crypto_proxy_observation_new_count": crypto_proxy_observation_summary.get("new_observation_row_count", 0),
            "crypto_proxy_observation_label_count": crypto_proxy_observation_summary.get("label_row_count", 0),
            "crypto_proxy_model_falsification_status": crypto_proxy_model_status or None,
            "crypto_proxy_model_independent_label_count": crypto_proxy_model_summary.get(
                "independent_contract_label_count", 0
            ),
            "crypto_proxy_model_duplicate_label_row_count": crypto_proxy_model_summary.get(
                "duplicate_label_row_count", 0
            ),
            "crypto_proxy_model_research_candidate_count": crypto_proxy_model_summary.get(
                "research_candidate_count", 0
            ),
            "crypto_proxy_replay_status": crypto_proxy_replay_status or None,
            "crypto_proxy_replay_row_count": crypto_proxy_replay_summary.get("replay_row_count", 0),
            "crypto_proxy_replay_positive_expected_value_row_count": crypto_proxy_replay_summary.get(
                "positive_expected_value_row_count", 0
            ),
            "crypto_proxy_replay_conservative_calibrated_side_probability": crypto_proxy_replay_summary.get(
                "conservative_calibrated_side_probability"
            ),
            "crypto_proxy_replay_usable_row_count": crypto_proxy_replay_summary.get("usable_row_count", 0),
            "crypto_proxy_capacity_correlation_decay_status": crypto_proxy_ccd_status or None,
            "crypto_proxy_ccd_candidate_row_count": crypto_proxy_ccd_summary.get("candidate_row_count", 0),
            "crypto_proxy_ccd_orderbook_count": crypto_proxy_ccd_summary.get("orderbook_count", 0),
            "crypto_proxy_ccd_positive_depth_contracts": crypto_proxy_ccd_summary.get("positive_depth_contracts", 0),
            "crypto_proxy_ccd_largest_cluster_share": crypto_proxy_ccd_summary.get("largest_correlation_cluster_share"),
            "crypto_proxy_ccd_decay_status": crypto_proxy_ccd_summary.get("decay_status"),
            "crypto_proxy_correlation_cluster_control_status": crypto_proxy_cluster_status or None,
            "crypto_proxy_cluster_positive_count": crypto_proxy_cluster_summary.get("positive_cluster_count", 0),
            "crypto_proxy_cluster_required_positive_count": crypto_proxy_cluster_summary.get(
                "required_positive_cluster_count", 0
            ),
            "crypto_proxy_cluster_total_controlled_depth_cost": crypto_proxy_cluster_summary.get(
                "total_controlled_depth_cost", 0
            ),
            "crypto_proxy_cluster_largest_controlled_share": crypto_proxy_cluster_summary.get(
                "largest_controlled_cluster_share"
            ),
            "capability_gate_counts": gate_counts,
        },
        "capabilities": capabilities,
        "inputs": {
            "universe_scan_path": str(artifacts.universe_scan_path),
            "ev_ledger_path": str(artifacts.ev_ledger_path),
            "review_queue_path": str(artifacts.review_queue_path),
            "robustness_path": str(artifacts.robustness_path),
            "hypothesis_registry_path": str(artifacts.hypothesis_registry_path),
            "falsification_gate_path": str(artifacts.falsification_gate_path),
            "labeled_observation_builder_path": str(artifacts.labeled_observation_builder_path),
            "labeled_oos_backtest_path": str(artifacts.labeled_oos_backtest_path),
            "probability_breadth_scout_path": str(artifacts.probability_breadth_scout_path),
            "crypto_proxy_feature_packet_path": str(artifacts.crypto_proxy_feature_packet_path),
            "crypto_proxy_observation_loop_path": str(artifacts.crypto_proxy_observation_loop_path),
            "crypto_proxy_model_falsification_path": str(artifacts.crypto_proxy_model_falsification_path),
            "crypto_proxy_research_candidate_replay_path": str(artifacts.crypto_proxy_research_candidate_replay_path),
            "crypto_proxy_capacity_correlation_decay_path": str(artifacts.crypto_proxy_capacity_correlation_decay_path),
            "crypto_proxy_correlation_cluster_control_path": str(
                artifacts.crypto_proxy_correlation_cluster_control_path
            ),
        },
        "next_tranche": next_tranche(
            registry_ready=registry_ready,
            falsification_blocked=falsification_blocked,
            observation_builder_status=observation_builder_status,
            labeled_oos_status=labeled_oos_status,
            probability_breadth_status=probability_breadth_status,
            crypto_proxy_feature_status=crypto_proxy_feature_status,
            crypto_proxy_observation_status=crypto_proxy_observation_status,
            crypto_proxy_model_status=crypto_proxy_model_status,
            crypto_proxy_replay_status=crypto_proxy_replay_status,
            crypto_proxy_ccd_status=crypto_proxy_ccd_status,
            crypto_proxy_cluster_status=crypto_proxy_cluster_status,
            crypto_proxy_ccd_capacity_status=str(crypto_proxy_ccd_summary.get("capacity_status") or ""),
            crypto_proxy_ccd_decay_status=str(crypto_proxy_ccd_summary.get("decay_status") or ""),
        ),
        "safety": {
            "research_only": True,
            "public_market_data_calls": False,
            "authenticated_api_calls": False,
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "raw_payloads_copied_to_repo": False,
            "staking_or_sizing_guidance": False,
        },
    }


def capability(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def crypto_proxy_cluster_control_capability(
    *,
    status: str,
    summary_data: Mapping[str, Any],
    present: bool,
) -> dict[str, str]:
    gate_status = (
        "pass"
        if status == "crypto_proxy_correlation_cluster_control_ready_for_paper_overlay"
        else ("warn" if present else "blocked")
    )
    reason = (
        f"Crypto proxy cluster-control status is `{status}` with "
        f"{summary_data.get('positive_cluster_count', 0)} positive cluster(s), "
        f"{summary_data.get('required_positive_cluster_count', 0)} required cluster(s), "
        f"{summary_data.get('total_controlled_depth_cost', 0)} controlled-depth cost, "
        f"largest controlled share `{summary_data.get('largest_controlled_cluster_share')}`, "
        f"and {summary_data.get('usable_row_count', 0)} usable row(s)."
        if present
        else "No crypto proxy correlation-cluster exposure control report exists yet."
    )
    return capability("crypto_proxy_correlation_cluster_control", gate_status, reason)


def crypto_proxy_gate_status(
    *,
    cluster_status: str,
    ccd_status: str,
    ccd_summary: Mapping[str, Any],
) -> str | None:
    if cluster_status == "crypto_proxy_correlation_cluster_control_blocked_upstream_ccd":
        if ccd_summary.get("capacity_status") != "capacity_depth_positive":
            return "signal_factory_crypto_proxy_capacity_depth_blocked"
        if ccd_summary.get("decay_status") != "decay_survival_pass":
            return "signal_factory_crypto_proxy_decay_survival_blocked"
    return CLUSTER_CONTROL_SIGNAL_STATUSES.get(cluster_status) or CCD_SIGNAL_STATUSES.get(ccd_status)


def gate_by_name(capabilities: Sequence[Mapping[str, Any]], name: str) -> Mapping[str, Any]:
    for item in capabilities:
        if item.get("name") == name:
            return item
    return {"status": "blocked"}


def count_statuses(capabilities: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"pass": 0, "warn": 0, "blocked": 0, "fail": 0}
    for item in capabilities:
        status = str(item.get("status") or "blocked")
        counts[status] = counts.get(status, 0) + 1
    return counts


def gate_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "registered_hypothesis_count": value.get("registered_hypothesis_count", 0),
        "tested_hypothesis_count": value.get("tested_hypothesis_count", 0),
        "promoted_hypothesis_count": value.get("promoted_hypothesis_count", 0),
        "blocked_hypothesis_count": value.get("blocked_hypothesis_count", 0),
    }


def next_tranche(
    *,
    registry_ready: bool,
    falsification_blocked: bool,
    observation_builder_status: str = "",
    labeled_oos_status: str = "",
    probability_breadth_status: str = "",
    crypto_proxy_feature_status: str = "",
    crypto_proxy_observation_status: str = "",
    crypto_proxy_model_status: str = "",
    crypto_proxy_replay_status: str = "",
    crypto_proxy_ccd_status: str = "",
    crypto_proxy_cluster_status: str = "",
    crypto_proxy_ccd_capacity_status: str = "",
    crypto_proxy_ccd_decay_status: str = "",
) -> dict[str, str]:
    cluster_tranche = cluster_control_next_tranche(
        cluster_status=crypto_proxy_cluster_status,
        ccd_capacity_status=crypto_proxy_ccd_capacity_status,
        ccd_decay_status=crypto_proxy_ccd_decay_status,
    )
    if cluster_tranche:
        return cluster_tranche
    if crypto_proxy_ccd_status in CCD_NEXT_TRANCHES:
        return CCD_NEXT_TRANCHES[crypto_proxy_ccd_status]
    if crypto_proxy_replay_status == "crypto_proxy_research_candidate_replay_blocked_predeployment_gates":
        return {
            "name": "kalshi_crypto_proxy_capacity_correlation_decay",
            "why": (
                "The crypto proxy research candidate has been replayed against all-in execution costs, but "
                "capacity depth, within-venue correlation controls, and decay survival still block usable edge."
            ),
            "stop_condition": (
                "Stop before sizing, execution, account/order paths, or treating positive replay rows as deployable."
            ),
        }
    if crypto_proxy_replay_status == "crypto_proxy_research_candidate_replay_ready_for_paper_probability_overlay":
        return {
            "name": "kalshi_crypto_proxy_paper_probability_overlay",
            "why": "Replay gates are research-ready; the next step is a paper-only probability overlay and decay monitor.",
            "stop_condition": "Stop before real positions, execution, account/order paths, or staking guidance.",
        }
    if crypto_proxy_replay_status == "crypto_proxy_research_candidate_replay_ready_no_positive_cost_adjusted_rows":
        return {
            "name": "kalshi_crypto_proxy_signal_family_rotation",
            "why": "The current research candidate did not survive conservative all-in cost replay.",
            "stop_condition": "Stop before discretionary feature selection; register and falsify new feature families.",
        }
    if crypto_proxy_model_status in {
        "crypto_proxy_feature_model_falsification_blocked_missing_labels",
        "crypto_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
        "crypto_proxy_feature_model_falsification_blocked_insufficient_oos_labels",
    }:
        return {
            "name": "kalshi_crypto_proxy_observation_accumulation",
            "why": (
                "The first crypto proxy model falsification gate exists, but there are not enough independent "
                "settled labels for OOS/FDR testing."
            ),
            "stop_condition": (
                "Stop before lowering sample thresholds, counting duplicate contract labels as independent, "
                "or creating EV/sizing/execution claims."
            ),
        }
    if crypto_proxy_model_status == "crypto_proxy_feature_model_falsification_ready_with_research_candidates":
        return {
            "name": "kalshi_crypto_proxy_research_candidate_replay",
            "why": "A crypto proxy feature family survived OOS/FDR as a research candidate; the next gate is conservative probability preflight plus all-in cost replay.",
            "stop_condition": "Stop before sizing or execution until all-in costs, capacity, correlation, and kill-switch gates exist.",
        }
    if crypto_proxy_model_status == "crypto_proxy_feature_model_falsification_ready_no_research_candidates":
        return {
            "name": "kalshi_crypto_proxy_signal_family_rotation",
            "why": "No crypto proxy feature family survived the falsification gate; rotate to new registered feature families.",
            "stop_condition": "Stop before discretionary signal selection or reusing failed hypotheses without new registered feature definitions.",
        }
    if crypto_proxy_observation_status == "crypto_proxy_observation_loop_label_rows_ready":
        return {
            "name": "kalshi_crypto_proxy_feature_model_falsification",
            "why": (
                "Crypto proxy observations now have true public Kalshi settlement labels; the next useful work "
                "is a cost-aware feature model plus out-of-sample/FDR falsification."
            ),
            "stop_condition": (
                "Stop before promotion, sizing, execution, or account/order paths without calibrated probabilities, "
                "all-in costs, and FDR-controlled OOS survival."
            ),
        }
    if crypto_proxy_observation_status in {
        "crypto_proxy_observation_loop_ready_waiting_settlement",
        "crypto_proxy_observation_loop_observations_recorded_waiting_settlement",
    }:
        return {
            "name": "kalshi_crypto_proxy_observation_accumulation",
            "why": (
                "Crypto proxy feature observations are archived, but true Kalshi settlement labels are still "
                "missing or insufficient; keep collecting snapshots and public settled outcomes."
            ),
            "stop_condition": (
                "Stop before using proxy states as labels, calibrated probabilities, EV, sizing, execution, or "
                "account/order evidence."
            ),
        }
    if crypto_proxy_feature_status == "crypto_proxy_feature_packet_ready":
        return {
            "name": "kalshi_crypto_proxy_observation_loop",
            "why": (
                "Contract-keyed crypto proxy feature packets now exist for fast-settling Kalshi contracts; "
                "the next useful work is repeated snapshots plus settled Kalshi outcome matching for "
                "out-of-sample falsification."
            ),
            "stop_condition": (
                "Stop before treating proxy states as official settlement labels, computing usable EV, "
                "sizing, execution, or account/order paths."
            ),
        }
    if probability_breadth_status == "probability_breadth_scout_ready_crypto_proxy_feature_route":
        return {
            "name": "kalshi_crypto_proxy_feature_packet",
            "why": (
                "Fast-settling crypto contracts dominate the current Kalshi universe and public proxy feeds "
                "are reachable; the next useful work is contract-keyed feature packets, with CF Benchmarks "
                "kept as the official settlement source."
            ),
            "stop_condition": (
                "Stop before treating proxy prices as official settlement labels, computing usable EV, sizing, "
                "execution, or account/order paths."
            ),
        }
    if probability_breadth_status == "probability_breadth_scout_ready_crypto_route_needs_proxy_probe":
        return {
            "name": "kalshi_crypto_proxy_source_probe",
            "why": "Fast-settling crypto dominates the universe, but public proxy-source availability is not recorded yet.",
            "stop_condition": "Stop before using proxy prices as labels, calibrated probabilities, EV, sizing, or execution evidence.",
        }
    if observation_builder_status == "labeled_observation_builder_label_packet_ready":
        return {
            "name": "kalshi_labeled_oos_backtest",
            "why": "A settled, time-safe label packet exists; the falsification harness should score it before any capacity or sizing work.",
            "stop_condition": "Stop before sizing, execution, or account/order paths; research promotion still requires FDR-controlled OOS survival.",
        }
    if observation_builder_status == "labeled_observation_builder_pending_observations_waiting_settlement":
        return {
            "name": "kalshi_probability_breadth_while_oos_observations_settle",
            "why": "Model-backed pending observations exist, but none have settled labels yet; the useful work is expanding calibrated probability coverage and keeping settlement capture ready.",
            "stop_condition": "Stop before treating unresolved pending observations as OOS proof.",
        }
    if labeled_oos_status == "labeled_oos_backtest_blocked_missing_labeled_observations":
        return {
            "name": "kalshi_labeled_observation_packet_builder",
            "why": (
                "The labeled OOS harness exists, but no settled, time-safe, cost-aware observations are keyed "
                "to registered HypothesisCandidate IDs yet."
            ),
            "stop_condition": (
                "Stop before testing, promoting, sizing, or executing hypotheses from unlabeled, time-unsafe, "
                "or non-cost-aware rows."
            ),
        }
    if labeled_oos_status == "labeled_oos_backtest_blocked_insufficient_oos_samples":
        return {
            "name": "kalshi_labeled_oos_sample_accumulation",
            "why": "Some label rows exist, but not enough OOS rows satisfy the minimum falsification policy.",
            "stop_condition": "Stop before lowering OOS/FDR thresholds without an explicit policy review.",
        }
    if labeled_oos_status == "labeled_oos_backtest_ready_with_research_promotions":
        return {
            "name": "kalshi_capacity_and_correlation_gates",
            "why": "Research promotions exist; the next gates are capacity, correlation, decay, and execution controls.",
            "stop_condition": "Stop before execution/account/order paths until capacity, correlation, sizing, and kill-switch gates exist.",
        }
    if registry_ready and falsification_blocked:
        return {
            "name": "kalshi_labeled_oos_backtest_harness",
            "why": (
                "Hypotheses are now registered, so the next structural bottleneck is labeled historical outcomes, "
                "time-safe walk-forward splits, all-in cost replay, and FDR-adjusted promotion/rejection."
            ),
            "stop_condition": (
                "Stop before sizing, execution, account/order paths, discretionary candidate selection, or promoting "
                "any hypothesis without machine-readable OOS cost-aware FDR evidence."
            ),
        }
    return {
        "name": "kalshi_hypothesis_registry_and_falsification_gate",
        "why": (
            "Hypothesis generation is now cheap, so the next structural bottleneck is false discovery control, "
            "out-of-sample survival, cost-aware backtesting, and signal retirement."
        ),
        "stop_condition": (
            "Stop before adding sizing or execution; a signal must survive FDR-controlled falsification, "
            "capacity, and correlation gates first."
        ),
    }


def cluster_control_next_tranche(
    *,
    cluster_status: str,
    ccd_capacity_status: str,
    ccd_decay_status: str,
) -> dict[str, str] | None:
    if cluster_status == "crypto_proxy_correlation_cluster_control_blocked_upstream_ccd":
        if ccd_capacity_status != "capacity_depth_positive":
            return CCD_NEXT_TRANCHES["crypto_proxy_capacity_correlation_decay_blocked_capacity_depth"]
        if ccd_decay_status != "decay_survival_pass":
            return CCD_NEXT_TRANCHES["crypto_proxy_capacity_correlation_decay_blocked_decay_survival"]
    return CLUSTER_CONTROL_NEXT_TRANCHES.get(cluster_status)


def write_signal_factory_status(
    report: Mapping[str, Any],
    out_dir: Path = DEFAULT_OUT_DIR,
    *,
    latest_dir: Path | None = None,
    write_latest: bool | None = None,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-signal-factory-status.json"
    markdown_path = out_dir / "kalshi-signal-factory-status.md"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    paths = {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }
    target_latest_dir = latest_dir or MACRO_DIR
    should_write_latest = path_is_within(out_dir, MACRO_DIR) if write_latest is None else write_latest
    if should_write_latest:
        target_latest_dir.mkdir(parents=True, exist_ok=True)
        latest_json = target_latest_dir / "latest-kalshi-signal-factory-status.json"
        latest_md = target_latest_dir / "latest-kalshi-signal-factory-status.md"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        paths["latest_json_path"] = str(latest_json)
        paths["latest_markdown_path"] = str(latest_md)
    return paths


def render_markdown(report: Mapping[str, Any]) -> str:
    summary_data = summary(report)
    lines = [
        "# Kalshi Signal Factory Status",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Research only: `{str(report.get('research_only')).lower()}`",
        f"- Execution enabled: `{str(report.get('execution_enabled')).lower()}`",
        f"- Universe candidates: `{summary_data.get('universe_candidate_count')}`",
        f"- Model-route candidates: `{summary_data.get('model_route_candidate_count')}`",
        f"- Soft-watch candidates: `{summary_data.get('soft_watch_candidate_count')}`",
        "",
        "## Capability Gates",
        "",
        "| Capability | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for item in report.get("capabilities", []):
        if isinstance(item, Mapping):
            lines.append(f"| `{item.get('name')}` | `{item.get('status')}` | {item.get('reason')} |")
    next_tranche = report.get("next_tranche") if isinstance(report.get("next_tranche"), Mapping) else {}
    lines.extend(
        [
            "",
            "## Next Tranche",
            "",
            f"- Name: `{next_tranche.get('name')}`",
            f"- Why: {next_tranche.get('why')}",
            f"- Stop condition: {next_tranche.get('stop_condition')}",
            "",
            "## Guardrail",
            "",
            "This is a system status artifact. It does not authorize sizing, orders, or execution.",
            "",
        ]
    )
    return "\n".join(lines)


def safe_research_artifact(value: Mapping[str, Any]) -> bool:
    safety = value.get("safety") if isinstance(value.get("safety"), Mapping) else {}
    return (
        value.get("research_only") is True
        and value.get("execution_enabled") is False
        and safety.get("market_execution") is False
        and safety.get("account_or_order_paths") is False
        and safety.get("database_writes") is False
    )


def safe_research_artifact_present(value: Mapping[str, Any]) -> bool:
    return safe_research_artifact(value) and bool(value.get("status"))


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def summary(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping) and isinstance(value.get("summary"), Mapping):
        return dict(value["summary"])
    return {}


def read_json_or_empty(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-scan-path", type=Path, default=DEFAULT_UNIVERSE_SCAN_PATH)
    parser.add_argument("--ev-ledger-path", type=Path, default=DEFAULT_EV_LEDGER_PATH)
    parser.add_argument("--review-queue-path", type=Path, default=DEFAULT_REVIEW_QUEUE_PATH)
    parser.add_argument("--robustness-path", type=Path, default=DEFAULT_ROBUSTNESS_PATH)
    parser.add_argument("--hypothesis-registry-path", type=Path, default=DEFAULT_HYPOTHESIS_REGISTRY_PATH)
    parser.add_argument("--falsification-gate-path", type=Path, default=DEFAULT_FALSIFICATION_GATE_PATH)
    parser.add_argument(
        "--labeled-observation-builder-path", type=Path, default=DEFAULT_LABELED_OBSERVATION_BUILDER_PATH
    )
    parser.add_argument("--labeled-oos-backtest-path", type=Path, default=DEFAULT_LABELED_OOS_BACKTEST_PATH)
    parser.add_argument("--probability-breadth-scout-path", type=Path, default=DEFAULT_PROBABILITY_BREADTH_SCOUT_PATH)
    parser.add_argument(
        "--crypto-proxy-feature-packet-path", type=Path, default=DEFAULT_CRYPTO_PROXY_FEATURE_PACKET_PATH
    )
    parser.add_argument(
        "--crypto-proxy-observation-loop-path",
        type=Path,
        default=DEFAULT_CRYPTO_PROXY_OBSERVATION_LOOP_PATH,
    )
    parser.add_argument(
        "--crypto-proxy-model-falsification-path",
        type=Path,
        default=DEFAULT_CRYPTO_PROXY_MODEL_FALSIFICATION_PATH,
    )
    parser.add_argument(
        "--crypto-proxy-research-candidate-replay-path",
        type=Path,
        default=DEFAULT_CRYPTO_PROXY_RESEARCH_CANDIDATE_REPLAY_PATH,
    )
    parser.add_argument(
        "--crypto-proxy-capacity-correlation-decay-path",
        type=Path,
        default=DEFAULT_CRYPTO_PROXY_CAPACITY_CORRELATION_DECAY_PATH,
    )
    parser.add_argument(
        "--crypto-proxy-correlation-cluster-control-path",
        type=Path,
        default=DEFAULT_CRYPTO_PROXY_CORRELATION_CLUSTER_CONTROL_PATH,
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    artifacts = Artifacts(
        universe_scan_path=args.universe_scan_path,
        ev_ledger_path=args.ev_ledger_path,
        review_queue_path=args.review_queue_path,
        robustness_path=args.robustness_path,
        hypothesis_registry_path=args.hypothesis_registry_path,
        falsification_gate_path=args.falsification_gate_path,
        labeled_observation_builder_path=args.labeled_observation_builder_path,
        labeled_oos_backtest_path=args.labeled_oos_backtest_path,
        probability_breadth_scout_path=args.probability_breadth_scout_path,
        crypto_proxy_feature_packet_path=args.crypto_proxy_feature_packet_path,
        crypto_proxy_observation_loop_path=args.crypto_proxy_observation_loop_path,
        crypto_proxy_model_falsification_path=args.crypto_proxy_model_falsification_path,
        crypto_proxy_research_candidate_replay_path=args.crypto_proxy_research_candidate_replay_path,
        crypto_proxy_capacity_correlation_decay_path=args.crypto_proxy_capacity_correlation_decay_path,
        crypto_proxy_correlation_cluster_control_path=args.crypto_proxy_correlation_cluster_control_path,
    )
    report = build_signal_factory_status(artifacts=artifacts)
    if args.write:
        paths = write_signal_factory_status(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
