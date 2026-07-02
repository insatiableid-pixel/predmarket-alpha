#!/usr/bin/env python3
"""Federated Codex macro status router.

This script is intentionally stdlib-only and read-only unless `route --write`
is passed. It must be safe to call from any active repo's `make macro-status`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
ACTIVE_UNIVERSE_PATH = MACRO_DIR / "active-universe.json"

STATUS_VERSION = 1

BASE_COMPONENTS: dict[str, dict[str, int]] = {
    "predmarket-alpha": {
        "architecture_leverage": 5,
        "evidence_delta": 4,
        "edge_feedback_speed": 4,
        "blocker_criticality": 1,
        "live_data_risk": 1,
        "verification_cost": 1,
    },
    "mlb-platform": {
        "architecture_leverage": 5,
        "evidence_delta": 5,
        "edge_feedback_speed": 5,
        "blocker_criticality": 3,
        "live_data_risk": 2,
        "verification_cost": 3,
    },
    "atp-oracle": {
        "architecture_leverage": 3,
        "evidence_delta": 3,
        "edge_feedback_speed": 4,
        "blocker_criticality": 4,
        "live_data_risk": 1,
        "verification_cost": 4,
    },
    "nba-analytics-platform": {
        "architecture_leverage": 4,
        "evidence_delta": 3,
        "edge_feedback_speed": 3,
        "blocker_criticality": 5,
        "live_data_risk": 1,
        "verification_cost": 4,
    },
    "nfl_quant_glm51_greenfield": {
        "architecture_leverage": 5,
        "evidence_delta": 2,
        "edge_feedback_speed": 1,
        "blocker_criticality": 2,
        "live_data_risk": 0,
        "verification_cost": 3,
    },
}

TRANCHES: dict[str, str] = {
    "predmarket-alpha": (
        "Maintain the macro router and Kalshi paper ledger; run the Type 2 "
        "reference preflight first, then run the paper matcher only when a "
        "mapped local sportsbook reference exists."
    ),
    "mlb-platform": (
        "Build the MLB Type 2 repeatability ledger: append clean review-adjudication "
        "cluster summaries, define the minimum repeated clean-snapshot evidence, "
        "and keep every output review-only."
    ),
    "atp-oracle": (
        "Run tennis Type 2 diagnostics only; readiness surface is blocked until "
        "G1/G2 model-quality gates and D3/G5/P5 external proof gaps clear."
    ),
    "nba-analytics-platform": (
        "Park NBA residual-model variants unless new source-backed signal is available. "
        "Route future NBA work to a data/source unlock or a non-model blocker; do not "
        "promote, settle, initialize risk, or execute."
    ),
    "nfl_quant_glm51_greenfield": (
        "Export governance patterns: offline status, artifact audit, validation "
        "ledger, and profile-validation gate evidence."
    ),
}

MLB_REPEATABILITY_RESEARCH_REVIEW_TRANCHE = (
    "Run an MLB Type 2 repeatability research review: synthesize the three clean "
    "packets, compare stable descriptor shapes, state what is recurring versus "
    "still unproven, and keep the output review-only."
)

MLB_REPEATABILITY_RESEARCH_REVIEW_STOP_CONDITION = (
    "Stop before another provider/API capture, paid historical request, database "
    "write, market execution, account/order path, staking/sizing language, or any "
    "tradable/profitability claim."
)

MLB_REPEATABILITY_CROSS_SLATE_TRANCHE = (
    "Park MLB Type 2 coding until cross-slate or settled-validation evidence exists; "
    "use the completed research review as the current truth surface."
)

MLB_REPEATABILITY_CROSS_SLATE_STOP_CONDITION = (
    "Stop until a new calendar-slate clean pregame packet, settled-outcome evidence, "
    "or closing-line validation evidence is available without inventing data or making "
    "unapproved provider/API calls."
)

MLB_REPEATABILITY_NO_CLEAN_PACKETS_TRANCHE = (
    "Park MLB repeatability promotion: the corrected contract mapping leaves zero "
    "clean adjudicated packets. Treat the prior run-line repeatability result as "
    "superseded and require a new contract-safe clean packet or settled/closing-line "
    "validation before more MLB promotion work."
)

MLB_REPEATABILITY_NO_CLEAN_PACKETS_STOP_CONDITION = (
    "Stop until a new contract-safe clean pregame packet, settled-outcome evidence, "
    "closing-line validation evidence, or explicit future capture authorization exists; "
    "do not rely on the superseded run-line pattern."
)

MLB_REPEATABILITY_NO_SIGNAL_TRANCHE = (
    "Park MLB Type 2 promotion at the current threshold: corrected, timing-clean "
    "packets exist, but they produced zero review-ready rows. Next useful work is an "
    "explicit threshold-policy review, a new slate, or settled/closing-line validation."
)

MLB_REPEATABILITY_NO_SIGNAL_STOP_CONDITION = (
    "Stop before lowering thresholds, making another provider/API capture, or claiming "
    "edge unless there is an explicit threshold-policy directive, a new clean slate, "
    "or settled/closing-line validation evidence."
)

MLB_THRESHOLD_POLICY_HOLD_TRANCHE = (
    "Park MLB Type 2 threshold promotion: the explicit threshold-policy review says "
    "to hold the current threshold because lower-threshold recurrence is same-slate-only. "
    "Next useful evidence is a new independent clean slate or settled/closing-line validation."
)

MLB_THRESHOLD_POLICY_HOLD_STOP_CONDITION = (
    "Stop before lowering the threshold, making another provider/API capture, or claiming "
    "edge until a new clean slate, settled-outcome evidence, or closing-line validation "
    "independently supports a policy change."
)

MLB_THRESHOLD_POLICY_REVIEW_TRANCHE = (
    "Run human research review on the MLB threshold-policy candidate; inspect recurring "
    "lower-threshold descriptors without lowering the production review threshold."
)

MLB_THRESHOLD_POLICY_REVIEW_STOP_CONDITION = (
    "Stop before changing thresholds, making provider/API calls, writing databases, touching "
    "execution/account/order paths, or making tradable/profitability claims."
)

MLB_SETTLED_VALIDATION_NO_POLICY_TRANCHE = (
    "Park MLB Type 2 policy promotion: settled-outcome validation of the same-slate "
    "lower-threshold rows does not support a threshold change. Next useful evidence is "
    "a new independent clean slate or closing-line validation."
)

MLB_SETTLED_VALIDATION_NO_POLICY_STOP_CONDITION = (
    "Stop before lowering thresholds, making another provider/API capture, or claiming "
    "edge until independent cross-slate settled validation or closing-line validation "
    "supports a policy change."
)

MLB_SETTLED_VALIDATION_REVIEW_TRANCHE = (
    "Run human research review on the MLB settled-outcome validation candidate; inspect "
    "settled directional evidence without lowering thresholds or changing execution behavior."
)

MLB_SETTLED_VALIDATION_REVIEW_STOP_CONDITION = (
    "Stop before changing thresholds, making provider/API calls, writing databases, touching "
    "execution/account/order paths, or making tradable/profitability claims."
)

MLB_CLOSING_PROXY_INSUFFICIENT_TRANCHE = (
    "Park MLB Type 2 promotion: same-slate later snapshots moved favorably for lower-threshold "
    "rows, but this is only a closing-line-style proxy and it conflicts with poor settled-outcome "
    "validation. Next useful evidence is an independent clean slate or true closing-line validation."
)

MLB_CLOSING_PROXY_INSUFFICIENT_STOP_CONDITION = (
    "Stop before treating same-slate proxy movement as true closing-line validation, lowering "
    "thresholds, making another provider/API capture, or claiming edge until independent clean-slate "
    "settled results or true closing-line evidence supports a policy change."
)

MLB_CLOSING_PROXY_REVIEW_TRANCHE = (
    "Run human research review on the MLB closing-proxy candidate; inspect later-snapshot support "
    "without treating it as true closing-line validation or changing threshold policy."
)

MLB_CLOSING_PROXY_REVIEW_STOP_CONDITION = (
    "Stop before changing thresholds, making provider/API calls, writing databases, touching "
    "execution/account/order paths, or making tradable/profitability claims."
)

MLB_BETEXPLORER_MONEYLINE_NO_POLICY_TRANCHE = (
    "Park MLB Type 2 policy promotion: public BetExplorer moneyline comparison exists "
    "and is date-matched, but it covers direct book moneyline rows only and has zero "
    "current-threshold rows. Next useful work is broader book/market mapping or an "
    "independent clean slate, not a threshold or execution change."
)

MLB_BETEXPLORER_MONEYLINE_NO_POLICY_STOP_CONDITION = (
    "Stop before treating the BetExplorer moneyline comparison as full closing-line "
    "validation, lowering thresholds, making provider/API calls, writing databases, "
    "touching execution/account/order paths, or making tradable/profitability claims."
)

MLB_BETEXPLORER_MARKET_NO_POLICY_TRANCHE = (
    "Park MLB Type 2 policy promotion: public BetExplorer multi-market comparison "
    "exists and is date-matched, but it adds only narrow run-line coverage, has zero "
    "current-threshold rows, and does not support a threshold or execution change. "
    "Next useful evidence is broader book/line/source coverage, an independent clean "
    "slate, or stronger true closing-line validation."
)

MLB_BETEXPLORER_MARKET_NO_POLICY_STOP_CONDITION = (
    "Stop before treating the BetExplorer market comparison as full closing-line "
    "validation, lowering thresholds, making provider/API calls, writing databases, "
    "touching execution/account/order paths, or making tradable/profitability claims."
)

NFL_LINE_READINESS_CONTEXT_TRANCHE = (
    "Advance NFL line-readiness: use the profiled fair-line packet, consensus current-market "
    "reference, and forward-context readiness report as the current truth surface, then fill "
    "missing injury, depth-chart, weather, and official starting-QB context only through safe "
    "public/cache/manual-drop inputs before integrating those features into model probabilities."
)

NFL_LINE_READINESS_CONTEXT_STOP_CONDITION = (
    "Stop before account/order/execution paths, staking/sizing language, database writes, "
    "unapproved provider calls, or changing model probabilities with injury/depth/weather/QB "
    "inputs whose readiness gates are not present and passing."
)

STOP_CONDITIONS: dict[str, str] = {
    "predmarket-alpha": (
        "Stop before any tradable claim, execution path, or live Kalshi action; "
        "REVIEW_READY remains review-only."
    ),
    "mlb-platform": (
        "Stop before paid historical requests, database writes, market execution, "
        "account/order paths, staking/sizing language, or any tradable claim; "
        "do not make another provider call unless a future directive explicitly authorizes it."
    ),
    "atp-oracle": (
        "Stop on any model-quality gate failure, commercial data-source gap, or "
        "premium/user-proof external dependency."
    ),
    "nba-analytics-platform": (
        "Stop if dirty-state classification changes, T21 completion evidence is "
        "missing, the shrinkage/clipped residual parity result is missing, or any "
        "platform consistency artifact regresses."
    ),
    "nfl_quant_glm51_greenfield": (
        "Stop if offline status, artifact audit, validation ledger, or profile "
        "validation evidence is missing or stale."
    ),
}

PARKED_COMMAND_CENTER_TRANCHE = (
    "All active macro lanes are parked or waiting on external evidence. "
    "Use predmarket as the command center to review the blocker summary, collect the missing inputs, "
    "and stop before coding against invented evidence."
)

PARKED_COMMAND_CENTER_STOP_CONDITION = (
    "Stop until a predmarket timing-safe reference has a review-threshold candidate, a contract-safe MLB pregame packet, "
    "fresh ATP validation/promotion evidence, new NBA source-backed signal, or stale/missing NFL governance evidence appears."
)

KALSHI_EV_CALIBRATION_WORK_ORDER_TRANCHE = (
    "Use predmarket as the Kalshi EV command center: dispatch the calibration work-order template "
    "to the appropriate model repo or worker, require validated calibrated probabilities keyed by exact "
    "contract_ticker and side, then rerun overlay preflight and the EV ledger."
)

KALSHI_EV_CALIBRATION_WORK_ORDER_STOP_CONDITION = (
    "Stop before inventing model probabilities, treating sportsbook/reference probabilities as calibrated, "
    "copying raw provider payloads into a repo, touching execution/account/order paths, or making tradable claims."
)

KALSHI_EV_CONTRACT_MAPPING_WORK_ORDER_TRANCHE = (
    "Use predmarket as the Kalshi EV command center: take one selected NFL contract-mapping work-order row, "
    "supply exact Kalshi ticker, official terms, clean timing status, and executable cost from local evidence, "
    "write matching safe mapping/probability overlays outside the repo, then rerun overlay preflight and the EV ledger."
)

KALSHI_EV_CONTRACT_MAPPING_WORK_ORDER_STOP_CONDITION = (
    "Stop before guessing a ticker, using unverified resolution rules, inventing executable costs, making live/provider "
    "calls without explicit authorization, copying raw payloads into a repo, touching execution/account/order paths, "
    "or making tradable claims."
)

KALSHI_EV_LOCAL_CONTRACT_EVIDENCE_SCOUT_TRANCHE = (
    "Use predmarket as the Kalshi EV command center: inspect the local contract-evidence scout. If it reports a ready "
    "target match, fill matching safe overlays outside the repo and rerun overlay preflight plus the EV ledger. If it "
    "reports no NFL target snapshot, obtain a local Kalshi NFL contract snapshot for one selected work-order game before "
    "any overlay fill."
)

KALSHI_EV_LOCAL_CONTRACT_EVIDENCE_SCOUT_STOP_CONDITION = (
    "Stop before guessing a ticker, using unverified resolution rules, inventing executable costs, making live/provider "
    "calls without explicit authorization, copying raw payloads into a repo, touching execution/account/order paths, "
    "or making tradable claims."
)

KALSHI_EV_REVIEW_QUEUE_TRANCHE = (
    "Use predmarket as the Kalshi EV command center: inspect the ranked review queue, separate robust candidates "
    "from positive watch rows, and advance only robustness evidence such as repeat snapshots, actual ticket all-in "
    "cost confirmation, forward context, or independent validation. Keep every row research-only."
)

KALSHI_EV_REVIEW_QUEUE_STOP_CONDITION = (
    "Stop before treating queue rows as picks, making execution/account/order calls, giving staking/sizing guidance, "
    "copying raw payloads into a repo, or promoting candidates whose robustness disposition still has unresolved caveats."
)

KALSHI_EV_QUEUE_ROBUSTNESS_TRANCHE = (
    "Use predmarket as the Kalshi EV command center: inspect the queue robustness artifact, verify whether "
    "repeat-positive rows survived multiple public snapshots, and advance only the remaining blocker: actual all-in "
    "ticket-cost confirmation without submitting an order, plus forward context and independent validation."
)

KALSHI_EV_QUEUE_ROBUSTNESS_STOP_CONDITION = (
    "Stop before submitting or previewing an order beyond a read-only cost check, touching account/order paths, "
    "giving staking/sizing guidance, copying raw payloads into a repo, or calling cost-caveated repeat-positive rows usable."
)

KALSHI_UNIVERSE_SCAN_TRANCHE = (
    "Use predmarket as the Kalshi universe command center: inspect the latest public market inventory, route core "
    "NFL/MLB/NBA/ATP candidates to model-specific work orders, and route non-core soft-watch candidates only after "
    "naming an external evidence source and probability method."
)

KALSHI_UNIVERSE_SCAN_STOP_CONDITION = (
    "Stop before computing EV inside the scanner, using authenticated/account/order endpoints, copying raw public "
    "payloads into a repo, making staking/sizing claims, or treating softness as edge."
)

KALSHI_SIGNAL_FACTORY_TRANCHE = (
    "Use predmarket as the Kalshi signal-factory command center: build the HypothesisCandidate registry and "
    "FDR-controlled, out-of-sample, cost-aware falsification gate before adding sizing, execution, or more "
    "signal-generation breadth."
)

KALSHI_SIGNAL_FACTORY_STOP_CONDITION = (
    "Stop before adding or enabling sizing, execution, account/order paths, or discretionary candidate selection; "
    "the tranche is complete only when hypotheses are versioned and rejected/promoted by machine-readable "
    "falsification gates."
)

KALSHI_LABELED_OOS_BACKTEST_TRANCHE = (
    "Use predmarket as the Kalshi signal-factory command center: build the labeled out-of-sample replay/backtest "
    "harness that attaches settled outcomes, time-safe quote snapshots, all-in costs, and FDR-adjusted "
    "promotion/rejection evidence to registered HypothesisCandidate IDs."
)

KALSHI_LABELED_OOS_BACKTEST_STOP_CONDITION = (
    "Stop before sizing, execution, account/order paths, discretionary candidate selection, or promoting any "
    "hypothesis without machine-readable OOS cost-aware FDR evidence."
)

KALSHI_LABELED_OBSERVATION_PACKET_TRANCHE = (
    "Use predmarket as the Kalshi signal-factory command center: build safe labeled-observation packets keyed "
    "to registered HypothesisCandidate IDs by attaching settled outcomes, point-in-time quote/model timestamps, "
    "and all-in costs without relabeling proxy evidence as OOS proof."
)

KALSHI_LABELED_OBSERVATION_PACKET_STOP_CONDITION = (
    "Stop before testing, promoting, sizing, execution, or account/order paths from unlabeled, time-unsafe, "
    "or non-cost-aware rows."
)

KALSHI_PROBABILITY_BREADTH_TRANCHE = (
    "Use predmarket as the Kalshi signal-factory command center: while pending OOS observations wait for "
    "settlement, expand calibrated-probability coverage across exact Kalshi contracts and fast-settling routes "
    "without treating unresolved rows as proof."
)

KALSHI_PROBABILITY_BREADTH_STOP_CONDITION = (
    "Stop before treating pending unresolved observations as OOS evidence, inventing calibrated probabilities, "
    "lowering falsification thresholds, sizing positions, execution, or account/order paths."
)

KALSHI_CRYPTO_PROXY_FEATURE_TRANCHE = (
    "Use predmarket as the Kalshi signal-factory command center: build contract-keyed crypto proxy feature "
    "packets for fast-settling Kalshi crypto contracts, while preserving CF Benchmarks RTI as the official "
    "settlement source and treating Coinbase/Kraken data as model features only."
)

KALSHI_CRYPTO_PROXY_FEATURE_STOP_CONDITION = (
    "Stop before treating proxy prices as official settlement labels, computing usable EV, sizing positions, "
    "execution, account/order paths, or promoting any crypto hypothesis without settled Kalshi outcomes and "
    "OOS cost-aware FDR evidence."
)

KALSHI_CRYPTO_PROXY_OBSERVATION_TRANCHE = (
    "Use predmarket as the Kalshi signal-factory command center: run a repeated crypto proxy observation loop "
    "that saves contract-keyed feature snapshots, waits for settled Kalshi outcomes, and builds label-ready "
    "packets for OOS falsification without using proxy prices as settlement truth."
)

KALSHI_CRYPTO_PROXY_OBSERVATION_STOP_CONDITION = (
    "Stop before treating proxy states as official settlement labels, computing usable EV, sizing positions, "
    "execution, account/order paths, or promoting any crypto hypothesis without settled Kalshi outcomes and "
    "OOS cost-aware FDR evidence."
)

KALSHI_CRYPTO_PROXY_OBSERVATION_ACCUMULATION_TRANCHE = (
    "Use predmarket as the Kalshi signal-factory command center: continue the crypto proxy observation loop "
    "until public Kalshi settlements attach true outcomes to archived contract-keyed feature snapshots."
)

KALSHI_CRYPTO_PROXY_OBSERVATION_ACCUMULATION_STOP_CONDITION = (
    "Stop before using proxy states as labels, calibrated probabilities, EV, sizing positions, execution, "
    "or account/order paths."
)

KALSHI_CRYPTO_PROXY_FEATURE_MODEL_TRANCHE = (
    "Use predmarket as the Kalshi signal-factory command center: train and falsify the first crypto proxy "
    "feature model against true settled Kalshi labels with all-in execution cost and FDR-controlled OOS gates."
)

KALSHI_CRYPTO_PROXY_FEATURE_MODEL_STOP_CONDITION = (
    "Stop before promotion, sizing positions, execution, or account/order paths without calibrated probabilities, "
    "all-in costs, capacity/correlation constraints, and FDR-controlled OOS survival."
)

KALSHI_CRYPTO_PROXY_RESEARCH_REPLAY_TRANCHE = (
    "Use predmarket as the Kalshi signal-factory command center: replay crypto proxy research candidates "
    "against conservative calibrated probability, all-in execution cost, capacity, correlation, and decay gates."
)

KALSHI_CRYPTO_PROXY_RESEARCH_REPLAY_STOP_CONDITION = (
    "Stop before sizing positions, execution, account/order paths, or treating positive replay rows as deployable."
)

KALSHI_CRYPTO_PROXY_CAPACITY_CORRELATION_DECAY_TRANCHE = (
    "Use predmarket as the Kalshi signal-factory command center: add safe capacity-depth, correlation-cluster, "
    "and decay-survival gates for crypto proxy replay candidates before any paper probability overlay."
)

KALSHI_CRYPTO_PROXY_CAPACITY_CORRELATION_DECAY_STOP_CONDITION = (
    "Stop before sizing positions, execution, account/order paths, staking guidance, or using replay rows as live edges."
)

KALSHI_CRYPTO_PROXY_CLUSTER_BREADTH_TRANCHE = (
    "Use predmarket as the Kalshi signal-factory command center: accumulate diversified current crypto proxy "
    "candidates across independent asset/family/close-time clusters before any paper probability overlay."
)

KALSHI_CRYPTO_PROXY_CLUSTER_BREADTH_STOP_CONDITION = (
    "Stop before reducing cluster breadth requirements, paper overlay, sizing positions, execution, "
    "or account/order paths without an explicit policy review."
)

PARKED_UNLOCKS: dict[str, str] = {
    "signal_factory_crypto_proxy_cluster_control_ready_paper_overlay": (
        "Crypto proxy controlled cluster exposure passed; build a paper-only overlay while execution stays disabled."
    ),
    "signal_factory_crypto_proxy_cluster_breadth_blocked": (
        "Crypto proxy cluster control exists, but positive depth is not spread across enough independent clusters."
    ),
    "signal_factory_crypto_proxy_cluster_share_blocked": (
        "Crypto proxy cluster breadth exists, but deterministic cluster caps still cannot satisfy the share limit."
    ),
    "signal_factory_crypto_proxy_cluster_control_blocked_upstream_ccd": (
        "Crypto proxy cluster control is blocked by upstream capacity/depth/decay evidence."
    ),
    "signal_factory_crypto_proxy_cluster_control_missing_ccd": (
        "Crypto proxy cluster control is blocked because upstream CCD evidence is missing."
    ),
    "signal_factory_crypto_proxy_cluster_control_no_positive_depth": (
        "Crypto proxy cluster control found no positive-depth capacity to allocate."
    ),
    "signal_factory_crypto_proxy_cluster_control_failed_safety_gate": (
        "Crypto proxy cluster control failed a research-only safety condition."
    ),
    "signal_factory_crypto_proxy_capacity_correlation_decay_ready_paper_overlay": (
        "Crypto proxy capacity, correlation, and decay gates passed; build a paper-only overlay while execution stays disabled."
    ),
    "signal_factory_crypto_proxy_capacity_depth_blocked": (
        "Crypto proxy CCD gate exists, but public orderbook depth is missing or not positive under the conservative hurdle."
    ),
    "signal_factory_crypto_proxy_correlation_concentration_blocked": (
        "Crypto proxy CCD gate found depth, but candidate capacity is too concentrated in one cluster."
    ),
    "signal_factory_crypto_proxy_decay_survival_blocked": (
        "Crypto proxy CCD gate found depth/correlation evidence but needs more settled-bucket decay survival."
    ),
    "signal_factory_crypto_proxy_current_candidates_missing": (
        "Crypto proxy CCD gate has no current close-window candidates; refresh observations before retrying depth."
    ),
    "signal_factory_crypto_proxy_capacity_correlation_decay_failed_safety_gate": (
        "Crypto proxy CCD gate failed a research-only safety condition."
    ),
    "signal_factory_crypto_proxy_replay_blocked_predeployment_gates": (
        "Crypto proxy replay exists, but capacity, correlation, and decay gates still block usable edge."
    ),
    "signal_factory_crypto_proxy_replay_ready_paper_overlay": (
        "Crypto proxy replay is research-ready for paper-only probability overlay; execution remains disabled."
    ),
    "signal_factory_crypto_proxy_replay_no_positive_cost_adjusted_rows": (
        "Crypto proxy replay found no positive cost-adjusted rows; rotate feature families."
    ),
    "signal_factory_crypto_proxy_feature_model_research_candidates": (
        "Crypto proxy feature model has research candidates; add calibration/cost/capacity gates before sizing."
    ),
    "signal_factory_crypto_proxy_feature_model_no_research_candidates": (
        "Crypto proxy feature model found no research candidates; rotate to new registered feature families."
    ),
    "signal_factory_crypto_proxy_feature_model_insufficient_labels": (
        "Crypto proxy model falsification exists but lacks enough independent labels; keep collecting labels."
    ),
    "signal_factory_crypto_proxy_labels_ready": (
        "Crypto proxy observations have true settled Kalshi labels; run model falsification before any sizing work."
    ),
    "signal_factory_crypto_proxy_observations_waiting_settlement": (
        "Crypto proxy feature observations are archived; keep accumulating snapshots and public settled outcomes."
    ),
    "signal_factory_crypto_proxy_feature_packet_ready": (
        "Contract-keyed crypto proxy feature packets exist; run repeated observations and settled outcome matching next."
    ),
    "signal_factory_probability_breadth_scout_ready_crypto_proxy_route": (
        "Fast-settling crypto dominates the current universe and public proxy feeds are reachable; build "
        "contract-keyed feature packets without treating proxies as official labels."
    ),
    "signal_factory_oos_pending_observations_waiting_settlement": (
        "Pending model-backed OOS observations exist; expand calibrated probability breadth while waiting for settlement."
    ),
    "signal_factory_oos_label_packet_ready_backtest_pending": (
        "A settled label packet is ready; run the labeled OOS backtest before any capacity/sizing work."
    ),
    "signal_factory_oos_backtest_harness_ready_labeled_observations_missing": (
        "OOS harness exists; build safe labeled observation packets keyed to HypothesisCandidate IDs."
    ),
    "signal_factory_oos_backtest_harness_ready_oos_samples_insufficient": (
        "OOS harness has some labels but not enough time-safe samples; accumulate more labeled observations."
    ),
    "signal_factory_oos_backtest_ready_research_promotions_present": (
        "Research promotions exist; add capacity/correlation/decay gates before any sizing or execution."
    ),
    "signal_factory_hypothesis_registry_ready_falsification_blocked_missing_labeled_oos_evidence": (
        "Hypotheses are registered; build labeled OOS cost-aware falsification evidence before capacity, sizing, or execution."
    ),
    "signal_factory_foundation_ready_falsification_missing": (
        "Universe inventory exists; build hypothesis registry and falsification gates before sizing or execution."
    ),
    "signal_factory_foundation_ready": (
        "Signal-factory foundation exists; inspect remaining blocked capability gates."
    ),
    "signal_factory_blocked_missing_universe_inventory": (
        "Run the public Kalshi universe scan before signal-factory work."
    ),
    "universe_scan_ready_with_model_routes": (
        "Public Kalshi universe scan found candidates for existing model routes; dispatch work orders before EV."
    ),
    "universe_scan_ready_soft_watch_only": (
        "Public Kalshi universe scan found only non-core soft-watch candidates; choose evidence sources before modeling."
    ),
    "universe_scan_ready": (
        "Public Kalshi universe scan is ready, but no immediate model-route unlock is present."
    ),
    "universe_scan_blocked_public_fetch_failed": (
        "Public Kalshi universe scan did not fetch usable markets; retry with smaller page/window settings."
    ),
    "kalshi_ev_queue_robustness_ready": (
        "Repeat-positive rows cleared robustness gates; review manually, with execution still disabled."
    ),
    "kalshi_ev_queue_robustness_repeat_positive_cost_caveated": (
        "Repeat-positive rows exist across snapshots, but all-in ticket cost still needs verification."
    ),
    "kalshi_ev_queue_robustness_observed_not_repeat_positive": (
        "Queue rows were observed, but positive margins did not repeat across snapshots."
    ),
    "kalshi_ev_queue_robustness_blocked_no_snapshots": (
        "Add at least two local KXNFLGAME public snapshots before assessing queue robustness."
    ),
    "kalshi_ev_review_queue_ready_with_robust_candidates": (
        "Review robust research candidates manually; execution remains disabled."
    ),
    "kalshi_ev_review_queue_positive_candidates_need_robustness": (
        "Positive fee-aware rows exist, but robustness evidence is still needed before any stronger claim."
    ),
    "kalshi_ev_review_queue_blocked_no_positive_usable_rows": (
        "No positive usable rows are queued; refresh exact mappings and calibrated probabilities."
    ),
    "kalshi_ev_ledger_ready_with_usable_contract_edges": (
        "Review the usable research-only EV rows; execution remains disabled."
    ),
    "kalshi_ev_calibration_work_order_ready": (
        "Fill a safe calibrated-probability overlay from the generated work-order template."
    ),
    "kalshi_ev_calibration_work_order_ready_source_gated": (
        "Current exact contract rows still have non-probability source gates; do not spend a worker on probabilities alone."
    ),
    "kalshi_ev_contract_mapping_work_order_ready": (
        "Fill exact Kalshi ticker, official terms, clean timing status, and executable cost for a mapped model row."
    ),
    "kalshi_ev_local_contract_evidence_blocked_no_nfl_target_snapshot": (
        "Drop a local Kalshi NFL contract snapshot with exact ticker, official terms, and executable cost for one selected mapped model row."
    ),
    "kalshi_ev_local_contract_evidence_blocked_no_ready_target_match": (
        "Inspect local NFL snapshots and add the missing exact terms/cost or matching target game evidence before filling overlays."
    ),
    "kalshi_ev_local_contract_evidence_ready_for_overlay_fill": (
        "Fill safe contract-mapping and calibrated-probability overlays from the ready local contract evidence."
    ),
    "kalshi_ev_overlay_preflight_blocked_missing_or_unjoined_inputs": (
        "Drop safe contract-mapping and calibrated-probability overlays that join on exact ticker and side."
    ),
    "kalshi_ev_ledger_candidates_present_but_not_usable": (
        "Use the calibration work order to produce validated calibrated probabilities for exact contract rows."
    ),
    "kalshi_type2_reference_preflight_blocked_missing_sportsbook_reference": (
        "Provide a small local sportsbook reference JSON with exact kalshi_ticker mappings."
    ),
    "kalshi_type2_candidate_disposition_all_passes_downgraded": (
        "Provide a timing-safe mapped sportsbook reference whose candidate captures are strictly before event start."
    ),
    "kalshi_type2_candidate_disposition_watch_only": (
        "Timing-safe mapped reference exists, but no candidate cleared the review threshold; wait for a new slate/reference or an explicit threshold-policy change."
    ),
    "primary_type2_pregame_intake_blocked_missing_operator_drop": (
        "Provide same-slate sportsbook and Kalshi pregame drops captured strictly before first pitch."
    ),
    "primary_type2_repeatability_insufficient": (
        "Provide another clean same-slate pregame pair before claiming repeatability."
    ),
    "primary_type2_repeatability_observed": (
        "Repeatability is observed across two clean packets; explicitly authorize a third clean capture before further MLB capture work."
    ),
    "primary_type2_repeatability_blocked_no_clean_packets": (
        "Corrected contract mapping leaves zero clean adjudicated packets; collect a new contract-safe clean packet or settled validation."
    ),
    "primary_type2_repeatability_no_signal_clean_packets": (
        "Corrected, timing-clean packets exist but produced zero review-ready rows at the current threshold; next unlock is threshold policy, a new slate, or settled validation."
    ),
    "primary_type2_threshold_policy_hold_current": (
        "Threshold-policy review says to hold the current threshold; collect a new clean slate or settled/closing-line validation before changing policy."
    ),
    "primary_type2_threshold_policy_review_candidate": (
        "Threshold-policy review has a candidate; inspect it manually without changing thresholds or execution behavior."
    ),
    "primary_type2_settled_validation_no_policy_change_same_slate": (
        "Settled-outcome validation does not support a policy change; collect an independent clean slate or closing-line validation."
    ),
    "primary_type2_settled_validation_review_candidate": (
        "Settled-outcome validation has a research-review candidate; inspect manually without changing thresholds or execution behavior."
    ),
    "primary_type2_closing_proxy_same_slate_support_insufficient": (
        "Closing-proxy support exists, but it is same-slate proxy evidence and conflicts with settled results; collect an independent clean slate or true closing-line validation."
    ),
    "primary_type2_closing_proxy_review_candidate": (
        "Closing-proxy validation has a research-review candidate; inspect manually without changing thresholds or execution behavior."
    ),
    "primary_type2_betexplorer_moneyline_closing_comparison_no_policy_change": (
        "Public BetExplorer moneyline comparison is present but narrow; expand book/market mapping or collect an independent clean slate before any policy change."
    ),
    "primary_type2_betexplorer_market_closing_comparison_no_policy_change": (
        "Public BetExplorer multi-market comparison is present but still narrow; expand book/line/source coverage or collect an independent clean slate before any policy change."
    ),
    "primary_type2_repeatability_research_review_ready_same_slate_caveat": (
        "Research review is complete for the three same-slate packets; next evidence requires another slate or settled validation."
    ),
    "primary_type2_repeatability_ready_for_research_review": (
        "Repeatability has reached the three-clean-packet research-review threshold; next work is local synthesis, not another capture."
    ),
    "tennis_type2_g1g2_diagnostic_ready_blocked_fresh_validation_external_evidence": (
        "Refresh local validation/promotion evidence and supply D3/G5/P5 external proof before readiness changes."
    ),
    "macro_partial_truth_shrinkage_clipped_residual_market_parity": (
        "Supply a new source-backed NBA signal or market dataset; residual variants are parked at market parity."
    ),
    "governance_macro_export_ready_fresh_snapshots_research_only": (
        "No immediate NFL work: governance snapshots are fresh; reroute only if evidence becomes stale or missing."
    ),
    "line_readiness_profiled_slate_context_missing_research_only": (
        "Profiled NFL fair-line packet exists, but forward-context readiness has not been generated."
    ),
    "line_readiness_profiled_slate_forward_context_partial_research_only": (
        "Profiled NFL fair-line packet and safe context report exist; missing injury, depth-chart, weather, and starting-QB inputs block feature integration."
    ),
    "line_readiness_profiled_slate_forward_context_ready_research_only": (
        "Profiled NFL fair-line packet and forward-context gates are ready; next work is feature integration review, not execution."
    ),
    "line_readiness_profiled_slate_forward_context_blocked_research_only": (
        "Profiled NFL fair-line packet exists, but core schedule/roster context is blocked."
    ),
    "line_readiness_profiled_slate_forward_context_manual_drop_blocked_research_only": (
        "Profiled NFL fair-line and forward-context packets exist, but the safe manual-drop input gate is blocked."
    ),
    "line_readiness_profiled_slate_forward_context_manual_drop_partial_research_only": (
        "Profiled NFL fair-line and forward-context packets exist, and manual-drop inputs are safe but incomplete."
    ),
    "line_readiness_profiled_slate_forward_context_not_yet_due_research_only": (
        "Profiled NFL fair-line and forward-context packets exist, but missing injury/weather/official-QB/closing inputs are not due yet."
    ),
    "line_readiness_profiled_slate_forward_context_manual_drop_ready_research_only": (
        "Profiled NFL fair-line, forward-context, and manual-drop input gates are ready for feature-integration review."
    ),
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_universe() -> dict[str, Any]:
    return json.loads(ACTIVE_UNIVERSE_PATH.read_text(encoding="utf-8"))


def repo_configs() -> dict[str, dict[str, Any]]:
    universe = load_universe()
    return {repo["repo_id"]: repo for repo in universe["repos"]}


def repo_path(repo_id: str) -> Path:
    configs = repo_configs()
    if repo_id not in configs:
        raise SystemExit(f"Unknown repo_id {repo_id!r}. Known: {', '.join(sorted(configs))}")
    return Path(configs[repo_id]["path"])


def run_git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.rstrip("\n")


def git_snapshot(root: Path) -> dict[str, Any]:
    branch = run_git(root, "rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    head = run_git(root, "rev-parse", "--short", "HEAD") or "unknown"
    porcelain = run_git(root, "status", "--porcelain=v1")
    lines = [line for line in porcelain.splitlines() if line.strip()]

    counts: Counter[str] = Counter()
    sample_paths: list[str] = []
    for line in lines:
        code = line[:2]
        path = line[3:].strip() if len(line) > 3 else ""
        if len(sample_paths) < 20 and path:
            sample_paths.append(path)
        x = code[0] if len(code) > 0 else " "
        y = code[1] if len(code) > 1 else " "

        if code == "??":
            counts["untracked"] += 1
            counts["unstaged"] += 1
        else:
            if x != " ":
                counts["staged"] += 1
            if y != " ":
                counts["unstaged"] += 1
            if "M" in code:
                counts["modified"] += 1
            if "A" in code:
                counts["added"] += 1
            if "D" in code:
                counts["deleted"] += 1
            if "R" in code:
                counts["renamed"] += 1

    dirty_counts = {
        "total": len(lines),
        "modified": counts["modified"],
        "added": counts["added"],
        "deleted": counts["deleted"],
        "renamed": counts["renamed"],
        "untracked": counts["untracked"],
        "staged": counts["staged"],
        "unstaged": counts["unstaged"],
    }
    risk_flags = {
        "dirty_tree": dirty_counts["total"] > 0,
        "staged_changes": dirty_counts["staged"] > 0,
        "generated_or_data_paths": any(
            p.startswith(("data/", "reports/", ".tmp/", "dist/", "build/")) for p in sample_paths
        ),
        "ide_or_temp_paths": any(
            p.startswith((".idea/", ".vscode/", ".hermes/")) or ".hermes-tmp" in p for p in sample_paths
        ),
        "large_dirty_tree": dirty_counts["total"] >= 100,
        "massive_dirty_tree": dirty_counts["total"] >= 500,
        "deleted_paths": dirty_counts["deleted"] > 0,
    }
    return {
        "branch": branch,
        "head": head,
        "dirty_counts": dirty_counts,
        "risk_flags": risk_flags,
        "sample_paths": sample_paths,
    }


def dirty_risk(git: dict[str, Any]) -> int:
    total = int(git["dirty_counts"]["total"])
    if total == 0:
        risk = 0
    elif total <= 10:
        risk = 1
    elif total <= 100:
        risk = 2
    elif total <= 250:
        risk = 3
    else:
        risk = 5
    flags = git["risk_flags"]
    if flags.get("staged_changes"):
        risk += 1
    if flags.get("deleted_paths"):
        risk += 1
    if flags.get("ide_or_temp_paths"):
        risk += 1
    return risk


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    raw = digest.hexdigest()
    return "sha256:" + " ".join(raw[index : index + 8] for index in range(0, len(raw), 8))


def artifact_pack(root: Path, rel_paths: list[str]) -> tuple[list[str], dict[str, str]]:
    artifacts: list[str] = []
    hashes: dict[str, str] = {}
    seen: set[str] = set()
    for rel_path in rel_paths:
        path = root / rel_path
        if not path.is_file():
            continue
        key = rel(root, path)
        if key in seen:
            continue
        seen.add(key)
        artifacts.append(key)
        hashes[key] = sha256(path)
    return artifacts, hashes


def latest_matching(root: Path, patterns: list[str], limit: int = 5) -> list[str]:
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(path for path in root.glob(pattern) if path.is_file())
    matches = sorted(set(matches), key=lambda path: path.stat().st_mtime, reverse=True)
    return [rel(root, path) for path in matches[:limit]]


def _latest_artifact_rel(root: Path, pattern: str) -> str | None:
    matches = latest_matching(root, [pattern], limit=1)
    return matches[0] if matches else None


def read_text(root: Path, rel_path: str, max_chars: int = 200_000) -> str:
    path = root / rel_path
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]


def read_json(root: Path, rel_path: str) -> Any | None:
    path = root / rel_path
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def safe_research_json(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    safety = value.get("safety") if isinstance(value.get("safety"), dict) else {}
    return (
        value.get("research_only") is True
        and value.get("execution_enabled") is False
        and safety.get("market_execution") is False
        and safety.get("account_or_order_paths") is False
        and safety.get("database_writes") is False
    )


def _path_value_exists(root: Path, value: Any) -> bool:
    if not value:
        return False
    path = Path(str(value))
    if path.is_absolute():
        return path.is_file()
    return (root / path).is_file()


def json_brief(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        first = value[0] if value else {}
        return {
            "json_type": "list",
            "row_count": len(value),
            "first_keys": sorted(first)[:20] if isinstance(first, dict) else [],
        }
    if isinstance(value, dict):
        brief: dict[str, Any] = {"json_type": "object", "top_level_keys": sorted(value)[:30]}
        for key in ("status", "generated_at", "blocker_count", "claim_count", "ready_claim_count", "blocked_claim_count"):
            if key in value:
                brief[key] = value[key]
        return brief
    return {"json_type": type(value).__name__}


def exists_map(root: Path, paths: list[str]) -> dict[str, bool]:
    return {path: (root / path).exists() for path in paths}


def extract_score(text: str, label_patterns: list[str]) -> int | None:
    for pattern in label_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return int(match.group(1))
    return None


def make_gate(name: str, status: str, reasons: list[str], artifacts: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "reasons": reasons,
        "source_artifacts": artifacts,
    }


def gate_counts(gates: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(gate["status"] for gate in gates)
    return {
        "pass": counts["pass"],
        "warn": counts["warn"],
        "blocked": counts["blocked"],
        "fail": counts["fail"],
    }


def base_status(repo_id: str, root: Path) -> dict[str, Any]:
    return {
        "schema_version": STATUS_VERSION,
        "repo_id": repo_id,
        "repo_path": str(root),
        "as_of_utc": utc_now(),
        "git": git_snapshot(root),
        "mode": {
            "research_only": True,
            "execution_enabled": False,
            "live_calls_allowed": False,
            "notes": [
                "Phase 1 macro status is offline/read-only by default.",
                "Provider, API, database write, and execution paths require an explicit non-default command.",
            ],
        },
        "evidence": {},
        "gates": [],
        "scheduling": {},
    }


def apply_scheduling(status: dict[str, Any]) -> dict[str, Any]:
    repo_id = status["repo_id"]
    components = dict(BASE_COMPONENTS[repo_id])
    evidence_status = status.get("evidence", {}).get("status")
    if repo_id == "mlb-platform" and evidence_status == "primary_type2_pregame_intake_blocked_missing_operator_drop":
        components.update(
            {
                "architecture_leverage": 3,
                "evidence_delta": 0,
                "edge_feedback_speed": 0,
                "blocker_criticality": 0,
                "verification_cost": 8,
            }
        )
    if repo_id == "mlb-platform" and evidence_status == "primary_type2_review_adjudication_ready":
        components.update(
            {
                "architecture_leverage": 5,
                "evidence_delta": 4,
                "edge_feedback_speed": 4,
                "blocker_criticality": 2,
                "verification_cost": 4,
            }
        )
    if repo_id == "mlb-platform" and evidence_status in {
        "primary_type2_repeatability_insufficient",
        "primary_type2_repeatability_observed",
    }:
        components.update(
            {
                "architecture_leverage": 3,
                "evidence_delta": 0,
                "edge_feedback_speed": 0,
                "blocker_criticality": 0,
                "verification_cost": 8,
            }
        )
    if repo_id == "mlb-platform" and evidence_status == "primary_type2_repeatability_ready_for_research_review":
        components.update(
            {
                "architecture_leverage": 5,
                "evidence_delta": 5,
                "edge_feedback_speed": 4,
                "blocker_criticality": 1,
                "verification_cost": 3,
            }
        )
    if (
        repo_id == "mlb-platform"
        and evidence_status == "primary_type2_repeatability_research_review_ready_same_slate_caveat"
    ):
        components.update(
            {
                "architecture_leverage": 3,
                "evidence_delta": 0,
                "edge_feedback_speed": 0,
                "blocker_criticality": 0,
                "verification_cost": 8,
            }
        )
    if repo_id == "mlb-platform" and evidence_status in {
        "primary_type2_repeatability_blocked_no_clean_packets",
        "primary_type2_repeatability_no_signal_clean_packets",
        "primary_type2_threshold_policy_hold_current",
        "primary_type2_settled_validation_no_policy_change_same_slate",
        "primary_type2_closing_proxy_same_slate_support_insufficient",
        "primary_type2_betexplorer_moneyline_closing_comparison_no_policy_change",
        "primary_type2_betexplorer_market_closing_comparison_no_policy_change",
    }:
        components.update(
            {
                "architecture_leverage": 3,
                "evidence_delta": 0,
                "edge_feedback_speed": 0,
                "blocker_criticality": 0,
                "verification_cost": 8,
            }
        )
    if repo_id == "mlb-platform" and evidence_status in {
        "primary_type2_threshold_policy_review_candidate",
        "primary_type2_settled_validation_review_candidate",
        "primary_type2_closing_proxy_review_candidate",
    }:
        components.update(
            {
                "architecture_leverage": 4,
                "evidence_delta": 3,
                "edge_feedback_speed": 2,
                "blocker_criticality": 1,
                "verification_cost": 3,
            }
        )
    if (
        repo_id == "predmarket-alpha"
        and evidence_status == "kalshi_type2_reference_preflight_blocked_missing_sportsbook_reference"
    ):
        components.update(
            {
                "architecture_leverage": 3,
                "evidence_delta": 0,
                "edge_feedback_speed": 0,
                "blocker_criticality": 0,
                "verification_cost": 8,
            }
        )
    if repo_id == "predmarket-alpha" and evidence_status == "kalshi_type2_candidate_disposition_all_passes_downgraded":
        components.update(
            {
                "architecture_leverage": 3,
                "evidence_delta": 0,
                "edge_feedback_speed": 0,
                "blocker_criticality": 0,
                "verification_cost": 8,
            }
        )
    if repo_id == "predmarket-alpha" and evidence_status == "kalshi_type2_candidate_disposition_watch_only":
        components.update(
            {
                "architecture_leverage": 3,
                "evidence_delta": 0,
                "edge_feedback_speed": 0,
                "blocker_criticality": 0,
                "verification_cost": 8,
            }
        )
    if repo_id == "predmarket-alpha" and evidence_status == "kalshi_type2_matcher_blocked_missing_sportsbook_reference":
        components.update(
            {
                "evidence_delta": 1,
                "edge_feedback_speed": 1,
                "blocker_criticality": 1,
                "verification_cost": 3,
            }
        )
    if repo_id == "predmarket-alpha" and evidence_status in {
        "kalshi_ev_calibration_work_order_ready",
        "kalshi_ev_calibration_work_order_ready_source_gated",
        "kalshi_ev_contract_mapping_work_order_ready",
        "kalshi_ev_local_contract_evidence_blocked_no_nfl_target_snapshot",
        "kalshi_ev_local_contract_evidence_blocked_no_ready_target_match",
        "kalshi_ev_local_contract_evidence_ready_for_overlay_fill",
        "kalshi_ev_overlay_preflight_blocked_missing_or_unjoined_inputs",
        "kalshi_ev_ledger_candidates_present_but_not_usable",
    }:
        components.update(
            {
                "architecture_leverage": 5,
                "evidence_delta": 3,
                "edge_feedback_speed": 2,
                "blocker_criticality": 3,
                "verification_cost": 3,
            }
        )
    if repo_id == "predmarket-alpha" and evidence_status == "kalshi_ev_ledger_ready_with_usable_contract_edges":
        components.update(
            {
                "architecture_leverage": 5,
                "evidence_delta": 5,
                "edge_feedback_speed": 4,
                "blocker_criticality": 4,
                "verification_cost": 3,
            }
        )
    if repo_id == "predmarket-alpha" and evidence_status in {
        "kalshi_ev_review_queue_ready_with_robust_candidates",
        "kalshi_ev_review_queue_positive_candidates_need_robustness",
    }:
        components.update(
            {
                "architecture_leverage": 5,
                "evidence_delta": 5,
                "edge_feedback_speed": 5,
                "blocker_criticality": 3,
                "verification_cost": 3,
            }
        )
    if repo_id == "predmarket-alpha" and evidence_status in {
        "kalshi_ev_queue_robustness_ready",
        "kalshi_ev_queue_robustness_repeat_positive_cost_caveated",
    }:
        components.update(
            {
                "architecture_leverage": 5,
                "evidence_delta": 5,
                "edge_feedback_speed": 5,
                "blocker_criticality": 4,
                "verification_cost": 3,
            }
        )
    if repo_id == "predmarket-alpha" and evidence_status in {
        "kalshi_ev_queue_robustness_observed_not_repeat_positive",
        "kalshi_ev_queue_robustness_blocked_no_snapshots",
    }:
        components.update(
            {
                "architecture_leverage": 5,
                "evidence_delta": 1,
                "edge_feedback_speed": 1,
                "blocker_criticality": 1,
                "verification_cost": 4,
            }
        )
    if repo_id == "predmarket-alpha" and evidence_status == "universe_scan_ready_with_model_routes":
        components.update(
            {
                "architecture_leverage": 5,
                "evidence_delta": 5,
                "edge_feedback_speed": 5,
                "blocker_criticality": 5,
                "verification_cost": 2,
            }
        )
    if repo_id == "predmarket-alpha" and evidence_status == "universe_scan_ready_soft_watch_only":
        components.update(
            {
                "architecture_leverage": 5,
                "evidence_delta": 4,
                "edge_feedback_speed": 4,
                "blocker_criticality": 3,
                "verification_cost": 3,
            }
        )
    if repo_id == "predmarket-alpha" and evidence_status in {
        "universe_scan_ready",
        "universe_scan_blocked_public_fetch_failed",
    }:
        components.update(
            {
                "architecture_leverage": 5,
                "evidence_delta": 2,
                "edge_feedback_speed": 2,
                "blocker_criticality": 1,
                "verification_cost": 3,
            }
        )
    if repo_id == "predmarket-alpha" and evidence_status in {
        "signal_factory_crypto_proxy_cluster_control_ready_paper_overlay",
        "signal_factory_crypto_proxy_cluster_breadth_blocked",
        "signal_factory_crypto_proxy_cluster_share_blocked",
        "signal_factory_crypto_proxy_cluster_control_blocked_upstream_ccd",
        "signal_factory_crypto_proxy_cluster_control_missing_ccd",
        "signal_factory_crypto_proxy_cluster_control_no_positive_depth",
        "signal_factory_crypto_proxy_cluster_control_failed_safety_gate",
        "signal_factory_crypto_proxy_capacity_correlation_decay_ready_paper_overlay",
        "signal_factory_crypto_proxy_capacity_depth_blocked",
        "signal_factory_crypto_proxy_correlation_concentration_blocked",
        "signal_factory_crypto_proxy_decay_survival_blocked",
        "signal_factory_crypto_proxy_current_candidates_missing",
        "signal_factory_crypto_proxy_capacity_correlation_decay_failed_safety_gate",
        "signal_factory_crypto_proxy_replay_blocked_predeployment_gates",
        "signal_factory_crypto_proxy_replay_ready_paper_overlay",
        "signal_factory_crypto_proxy_replay_no_positive_cost_adjusted_rows",
        "signal_factory_crypto_proxy_feature_model_research_candidates",
        "signal_factory_crypto_proxy_feature_model_no_research_candidates",
        "signal_factory_crypto_proxy_feature_model_insufficient_labels",
        "signal_factory_crypto_proxy_labels_ready",
        "signal_factory_crypto_proxy_observations_waiting_settlement",
        "signal_factory_crypto_proxy_feature_packet_ready",
        "signal_factory_probability_breadth_scout_ready_crypto_proxy_route",
        "signal_factory_oos_pending_observations_waiting_settlement",
        "signal_factory_oos_label_packet_ready_backtest_pending",
        "signal_factory_oos_backtest_harness_ready_labeled_observations_missing",
        "signal_factory_oos_backtest_harness_ready_oos_samples_insufficient",
        "signal_factory_oos_backtest_ready_research_promotions_present",
        "signal_factory_hypothesis_registry_ready_falsification_blocked_missing_labeled_oos_evidence",
        "signal_factory_foundation_ready_falsification_missing",
        "signal_factory_foundation_ready",
    }:
        components.update(
            {
                "architecture_leverage": 5,
                "evidence_delta": 5,
                "edge_feedback_speed": 5,
                "blocker_criticality": 5,
                "verification_cost": 2,
            }
        )
    if repo_id == "predmarket-alpha" and evidence_status == "signal_factory_blocked_missing_universe_inventory":
        components.update(
            {
                "architecture_leverage": 5,
                "evidence_delta": 2,
                "edge_feedback_speed": 2,
                "blocker_criticality": 3,
                "verification_cost": 2,
            }
        )
    if repo_id == "atp-oracle" and evidence_status == "tennis_type2_readiness_blocked_model_quality_external_evidence":
        components.update(
            {
                "evidence_delta": 1,
                "edge_feedback_speed": 1,
                "blocker_criticality": 2,
                "verification_cost": 5,
            }
        )
    if (
        repo_id == "atp-oracle"
        and evidence_status == "tennis_type2_g1g2_diagnostic_ready_blocked_fresh_validation_external_evidence"
    ):
        components.update(
            {
                "evidence_delta": 0,
                "edge_feedback_speed": 0,
                "blocker_criticality": 0,
                "verification_cost": 8,
            }
        )
    if repo_id == "nba-analytics-platform" and evidence_status in {
        "macro_partial_truth_stabilized_dirty_classified",
        "macro_partial_truth_market_gate_blocked_model_promotability",
        "macro_partial_truth_model_promotability_design_ready",
        "macro_partial_truth_residual_evaluator_collapsed_to_market",
        "macro_partial_truth_residual_signal_cancellation_explained",
        "macro_partial_truth_canonical_residual_not_promotable",
        "macro_partial_truth_residual_overcorrection_large_correction_overfit",
        "macro_partial_truth_shrinkage_clipped_residual_market_parity",
    }:
        components.update(
            {
                "architecture_leverage": (
                    2
                    if evidence_status == "macro_partial_truth_shrinkage_clipped_residual_market_parity"
                    else components["architecture_leverage"]
                ),
                "evidence_delta": (
                    0
                    if evidence_status == "macro_partial_truth_shrinkage_clipped_residual_market_parity"
                    else (
                        4
                        if evidence_status
                        in {
                            "macro_partial_truth_model_promotability_design_ready",
                            "macro_partial_truth_residual_evaluator_collapsed_to_market",
                            "macro_partial_truth_residual_signal_cancellation_explained",
                            "macro_partial_truth_canonical_residual_not_promotable",
                            "macro_partial_truth_residual_overcorrection_large_correction_overfit",
                        }
                        else 3
                    )
                ),
                "edge_feedback_speed": (
                    0
                    if evidence_status == "macro_partial_truth_shrinkage_clipped_residual_market_parity"
                    else 2
                ),
                "blocker_criticality": (
                    0
                    if evidence_status == "macro_partial_truth_shrinkage_clipped_residual_market_parity"
                    else 4
                ),
                "verification_cost": (
                    8
                    if evidence_status == "macro_partial_truth_shrinkage_clipped_residual_market_parity"
                    else 4
                ),
            }
        )
    if repo_id == "nfl_quant_glm51_greenfield" and evidence_status in {
        "governance_macro_export_ready_dirty_research_only",
        "governance_macro_export_ready_fresh_snapshots_research_only",
    }:
        components.update(
            {
                "architecture_leverage": (
                    3
                    if evidence_status == "governance_macro_export_ready_fresh_snapshots_research_only"
                    else components["architecture_leverage"]
                ),
                "evidence_delta": 0,
                "edge_feedback_speed": 0,
                "blocker_criticality": 0,
                "verification_cost": (
                    10
                    if evidence_status == "governance_macro_export_ready_fresh_snapshots_research_only"
                    else 4
                ),
            }
        )
    if repo_id == "nfl_quant_glm51_greenfield" and evidence_status in {
        "line_readiness_profiled_slate_context_missing_research_only",
        "line_readiness_profiled_slate_forward_context_partial_research_only",
        "line_readiness_profiled_slate_forward_context_ready_research_only",
        "line_readiness_profiled_slate_forward_context_blocked_research_only",
        "line_readiness_profiled_slate_forward_context_manual_drop_blocked_research_only",
        "line_readiness_profiled_slate_forward_context_manual_drop_partial_research_only",
        "line_readiness_profiled_slate_forward_context_manual_drop_ready_research_only",
        "line_readiness_profiled_slate_forward_context_not_yet_due_research_only",
    }:
        components.update(
            {
                "architecture_leverage": (
                    2
                    if evidence_status == "line_readiness_profiled_slate_forward_context_not_yet_due_research_only"
                    else 5
                ),
                "evidence_delta": (
                    0
                    if evidence_status == "line_readiness_profiled_slate_forward_context_not_yet_due_research_only"
                    else 4
                    if evidence_status
                    in {
                        "line_readiness_profiled_slate_forward_context_partial_research_only",
                        "line_readiness_profiled_slate_forward_context_ready_research_only",
                        "line_readiness_profiled_slate_forward_context_manual_drop_partial_research_only",
                        "line_readiness_profiled_slate_forward_context_manual_drop_ready_research_only",
                    }
                    else 3
                ),
                "edge_feedback_speed": (
                    0
                    if evidence_status == "line_readiness_profiled_slate_forward_context_not_yet_due_research_only"
                    else 2
                ),
                "blocker_criticality": (
                    0
                    if evidence_status == "line_readiness_profiled_slate_forward_context_not_yet_due_research_only"
                    else 4
                    if evidence_status
                    in {
                        "line_readiness_profiled_slate_context_missing_research_only",
                        "line_readiness_profiled_slate_forward_context_blocked_research_only",
                        "line_readiness_profiled_slate_forward_context_manual_drop_blocked_research_only",
                    }
                    else 2
                ),
                "verification_cost": (
                    8
                    if evidence_status == "line_readiness_profiled_slate_forward_context_not_yet_due_research_only"
                    else 4
                ),
            }
        )
    components["dirty_risk"] = dirty_risk(status["git"])
    priority = (
        3 * components["architecture_leverage"]
        + 2 * components["evidence_delta"]
        + 2 * components["edge_feedback_speed"]
        + components["blocker_criticality"]
        - components["dirty_risk"]
        - components["live_data_risk"]
        - components["verification_cost"]
    )
    recommended_next_tranche = TRANCHES[repo_id]
    stop_condition = STOP_CONDITIONS[repo_id]
    if repo_id == "mlb-platform" and evidence_status == "primary_type2_repeatability_ready_for_research_review":
        recommended_next_tranche = MLB_REPEATABILITY_RESEARCH_REVIEW_TRANCHE
        stop_condition = MLB_REPEATABILITY_RESEARCH_REVIEW_STOP_CONDITION
    if repo_id == "nfl_quant_glm51_greenfield" and evidence_status in {
        "line_readiness_profiled_slate_context_missing_research_only",
        "line_readiness_profiled_slate_forward_context_partial_research_only",
        "line_readiness_profiled_slate_forward_context_ready_research_only",
        "line_readiness_profiled_slate_forward_context_blocked_research_only",
        "line_readiness_profiled_slate_forward_context_manual_drop_blocked_research_only",
        "line_readiness_profiled_slate_forward_context_manual_drop_partial_research_only",
        "line_readiness_profiled_slate_forward_context_manual_drop_ready_research_only",
    }:
        recommended_next_tranche = NFL_LINE_READINESS_CONTEXT_TRANCHE
        stop_condition = NFL_LINE_READINESS_CONTEXT_STOP_CONDITION
    if (
        repo_id == "nfl_quant_glm51_greenfield"
        and evidence_status == "line_readiness_profiled_slate_forward_context_not_yet_due_research_only"
    ):
        recommended_next_tranche = (
            "Park NFL forward-context collection: the fair-line/current-market machinery is ready, "
            "but missing injury, weather, official starting-QB, and closing inputs are not due yet. "
            "Do not spend Codex cycles here until the next due date or a verified outside-repo manual drop appears."
        )
        stop_condition = (
            "Stop until the forward-context availability artifact reports due_now inputs, a verified manual drop appears, "
            "or the user explicitly overrides the calendar; do not make provider calls or alter model probabilities."
        )
    if (
        repo_id == "mlb-platform"
        and evidence_status == "primary_type2_repeatability_research_review_ready_same_slate_caveat"
    ):
        recommended_next_tranche = MLB_REPEATABILITY_CROSS_SLATE_TRANCHE
        stop_condition = MLB_REPEATABILITY_CROSS_SLATE_STOP_CONDITION
    if repo_id == "mlb-platform" and evidence_status == "primary_type2_repeatability_blocked_no_clean_packets":
        recommended_next_tranche = MLB_REPEATABILITY_NO_CLEAN_PACKETS_TRANCHE
        stop_condition = MLB_REPEATABILITY_NO_CLEAN_PACKETS_STOP_CONDITION
    if repo_id == "mlb-platform" and evidence_status == "primary_type2_repeatability_no_signal_clean_packets":
        recommended_next_tranche = MLB_REPEATABILITY_NO_SIGNAL_TRANCHE
        stop_condition = MLB_REPEATABILITY_NO_SIGNAL_STOP_CONDITION
    if repo_id == "mlb-platform" and evidence_status == "primary_type2_threshold_policy_hold_current":
        recommended_next_tranche = MLB_THRESHOLD_POLICY_HOLD_TRANCHE
        stop_condition = MLB_THRESHOLD_POLICY_HOLD_STOP_CONDITION
    if repo_id == "mlb-platform" and evidence_status == "primary_type2_threshold_policy_review_candidate":
        recommended_next_tranche = MLB_THRESHOLD_POLICY_REVIEW_TRANCHE
        stop_condition = MLB_THRESHOLD_POLICY_REVIEW_STOP_CONDITION
    if repo_id == "mlb-platform" and evidence_status == "primary_type2_settled_validation_no_policy_change_same_slate":
        recommended_next_tranche = MLB_SETTLED_VALIDATION_NO_POLICY_TRANCHE
        stop_condition = MLB_SETTLED_VALIDATION_NO_POLICY_STOP_CONDITION
    if repo_id == "mlb-platform" and evidence_status == "primary_type2_settled_validation_review_candidate":
        recommended_next_tranche = MLB_SETTLED_VALIDATION_REVIEW_TRANCHE
        stop_condition = MLB_SETTLED_VALIDATION_REVIEW_STOP_CONDITION
    if repo_id == "mlb-platform" and evidence_status == "primary_type2_closing_proxy_same_slate_support_insufficient":
        recommended_next_tranche = MLB_CLOSING_PROXY_INSUFFICIENT_TRANCHE
        stop_condition = MLB_CLOSING_PROXY_INSUFFICIENT_STOP_CONDITION
    if repo_id == "mlb-platform" and evidence_status == "primary_type2_closing_proxy_review_candidate":
        recommended_next_tranche = MLB_CLOSING_PROXY_REVIEW_TRANCHE
        stop_condition = MLB_CLOSING_PROXY_REVIEW_STOP_CONDITION
    if (
        repo_id == "mlb-platform"
        and evidence_status == "primary_type2_betexplorer_moneyline_closing_comparison_no_policy_change"
    ):
        recommended_next_tranche = MLB_BETEXPLORER_MONEYLINE_NO_POLICY_TRANCHE
        stop_condition = MLB_BETEXPLORER_MONEYLINE_NO_POLICY_STOP_CONDITION
    if (
        repo_id == "mlb-platform"
        and evidence_status == "primary_type2_betexplorer_market_closing_comparison_no_policy_change"
    ):
        recommended_next_tranche = MLB_BETEXPLORER_MARKET_NO_POLICY_TRANCHE
        stop_condition = MLB_BETEXPLORER_MARKET_NO_POLICY_STOP_CONDITION
    if repo_id == "predmarket-alpha" and evidence_status in {
        "signal_factory_crypto_proxy_cluster_control_ready_paper_overlay",
        "signal_factory_crypto_proxy_cluster_breadth_blocked",
        "signal_factory_crypto_proxy_cluster_share_blocked",
        "signal_factory_crypto_proxy_cluster_control_blocked_upstream_ccd",
        "signal_factory_crypto_proxy_cluster_control_missing_ccd",
        "signal_factory_crypto_proxy_cluster_control_no_positive_depth",
        "signal_factory_crypto_proxy_cluster_control_failed_safety_gate",
        "signal_factory_crypto_proxy_capacity_correlation_decay_ready_paper_overlay",
        "signal_factory_crypto_proxy_capacity_depth_blocked",
        "signal_factory_crypto_proxy_correlation_concentration_blocked",
        "signal_factory_crypto_proxy_decay_survival_blocked",
        "signal_factory_crypto_proxy_current_candidates_missing",
        "signal_factory_crypto_proxy_capacity_correlation_decay_failed_safety_gate",
        "signal_factory_crypto_proxy_replay_blocked_predeployment_gates",
        "signal_factory_crypto_proxy_replay_ready_paper_overlay",
        "signal_factory_crypto_proxy_replay_no_positive_cost_adjusted_rows",
        "signal_factory_crypto_proxy_feature_model_research_candidates",
        "signal_factory_crypto_proxy_feature_model_no_research_candidates",
        "signal_factory_crypto_proxy_feature_model_insufficient_labels",
        "signal_factory_crypto_proxy_labels_ready",
        "signal_factory_crypto_proxy_observations_waiting_settlement",
        "signal_factory_crypto_proxy_feature_packet_ready",
        "signal_factory_probability_breadth_scout_ready_crypto_proxy_route",
        "signal_factory_oos_pending_observations_waiting_settlement",
        "signal_factory_oos_label_packet_ready_backtest_pending",
        "signal_factory_oos_backtest_harness_ready_labeled_observations_missing",
        "signal_factory_oos_backtest_harness_ready_oos_samples_insufficient",
        "signal_factory_oos_backtest_ready_research_promotions_present",
        "signal_factory_hypothesis_registry_ready_falsification_blocked_missing_labeled_oos_evidence",
        "signal_factory_foundation_ready_falsification_missing",
        "signal_factory_foundation_ready",
        "signal_factory_blocked_missing_universe_inventory",
    }:
        if evidence_status == "signal_factory_crypto_proxy_cluster_control_ready_paper_overlay":
            recommended_next_tranche = (
                "Use predmarket as the Kalshi signal-factory command center: build a paper-only crypto proxy "
                "probability overlay and decay monitor from cluster-control-passing research candidates."
            )
            stop_condition = (
                "Stop before real positions, execution, account/order paths, staking guidance, or live edge claims."
            )
        elif evidence_status == "signal_factory_crypto_proxy_cluster_breadth_blocked":
            recommended_next_tranche = KALSHI_CRYPTO_PROXY_CLUSTER_BREADTH_TRANCHE
            stop_condition = KALSHI_CRYPTO_PROXY_CLUSTER_BREADTH_STOP_CONDITION
        elif evidence_status == "signal_factory_crypto_proxy_cluster_share_blocked":
            recommended_next_tranche = (
                "Use predmarket as the Kalshi signal-factory command center: refine deterministic crypto proxy "
                "cluster caps until positive-depth candidates satisfy the configured share limit."
            )
            stop_condition = "Stop before paper overlay until the controlled cluster share limit is passing."
        elif evidence_status in {
            "signal_factory_crypto_proxy_cluster_control_blocked_upstream_ccd",
            "signal_factory_crypto_proxy_cluster_control_missing_ccd",
        }:
            recommended_next_tranche = KALSHI_CRYPTO_PROXY_CAPACITY_CORRELATION_DECAY_TRANCHE
            stop_condition = "Stop before paper overlay until upstream CCD evidence exists and passes prerequisites."
        elif evidence_status == "signal_factory_crypto_proxy_cluster_control_no_positive_depth":
            recommended_next_tranche = (
                "Use predmarket as the Kalshi signal-factory command center: accumulate public orderbook depth "
                "for current crypto proxy candidates before retrying cluster exposure controls."
            )
            stop_condition = "Stop before inferring capacity from top-of-book prices without public depth."
        elif evidence_status == "signal_factory_crypto_proxy_cluster_control_failed_safety_gate":
            recommended_next_tranche = (
                "Use predmarket as the Kalshi signal-factory command center: audit and repair the failed crypto "
                "proxy cluster-control research-only safety gate."
            )
            stop_condition = (
                "Stop before any paper overlay, sizing, execution, or account/order path until the failed safety gate is fixed."
            )
        elif evidence_status == "signal_factory_crypto_proxy_capacity_correlation_decay_ready_paper_overlay":
            recommended_next_tranche = (
                "Use predmarket as the Kalshi signal-factory command center: build a paper-only crypto proxy "
                "probability overlay and decay monitor from CCD-passing research candidates."
            )
            stop_condition = (
                "Stop before real positions, execution, account/order paths, staking guidance, or live edge claims."
            )
        elif evidence_status == "signal_factory_crypto_proxy_capacity_depth_blocked":
            recommended_next_tranche = (
                "Use predmarket as the Kalshi signal-factory command center: accumulate public orderbook depth "
                "for current crypto proxy candidates and keep capacity blocked until positive depth clears the "
                "conservative probability hurdle."
            )
            stop_condition = "Stop before inferring capacity from top-of-book prices without depth."
        elif evidence_status == "signal_factory_crypto_proxy_correlation_concentration_blocked":
            recommended_next_tranche = (
                "Use predmarket as the Kalshi signal-factory command center: add correlation-cluster exposure "
                "controls for crypto proxy candidates before any paper overlay."
            )
            stop_condition = (
                "Stop before paper overlay until cluster exposure limits are machine-readable and passing."
            )
        elif evidence_status == "signal_factory_crypto_proxy_decay_survival_blocked":
            recommended_next_tranche = (
                "Use predmarket as the Kalshi signal-factory command center: accumulate repeated settled buckets "
                "and keep the crypto proxy signal blocked until decay survival is passing."
            )
            stop_condition = "Stop before lowering decay or sample thresholds without an explicit policy review."
        elif evidence_status == "signal_factory_crypto_proxy_current_candidates_missing":
            recommended_next_tranche = KALSHI_CRYPTO_PROXY_OBSERVATION_ACCUMULATION_TRANCHE
            stop_condition = "Stop before treating stale expired replay rows as current capacity evidence."
        elif evidence_status == "signal_factory_crypto_proxy_capacity_correlation_decay_failed_safety_gate":
            recommended_next_tranche = (
                "Use predmarket as the Kalshi signal-factory command center: audit and repair the failed "
                "capacity/correlation/decay research-only safety gate."
            )
            stop_condition = (
                "Stop before any paper overlay, sizing, execution, or account/order path until the failed safety gate is fixed."
            )
        elif evidence_status == "signal_factory_crypto_proxy_replay_blocked_predeployment_gates":
            recommended_next_tranche = KALSHI_CRYPTO_PROXY_CAPACITY_CORRELATION_DECAY_TRANCHE
            stop_condition = KALSHI_CRYPTO_PROXY_CAPACITY_CORRELATION_DECAY_STOP_CONDITION
        elif evidence_status == "signal_factory_crypto_proxy_replay_ready_paper_overlay":
            recommended_next_tranche = (
                "Use predmarket as the Kalshi signal-factory command center: build a paper-only crypto proxy "
                "probability overlay and decay monitor from replay-ready research candidates."
            )
            stop_condition = (
                "Stop before real positions, execution, account/order paths, staking guidance, or live edge claims."
            )
        elif evidence_status == "signal_factory_crypto_proxy_replay_no_positive_cost_adjusted_rows":
            recommended_next_tranche = (
                "Use predmarket as the Kalshi signal-factory command center: rotate to new registered crypto "
                "feature families after conservative all-in cost replay found no positive rows."
            )
            stop_condition = (
                "Stop before discretionary signal selection or reusing failed hypotheses without new registered features."
            )
        elif evidence_status == "signal_factory_crypto_proxy_feature_model_research_candidates":
            recommended_next_tranche = KALSHI_CRYPTO_PROXY_RESEARCH_REPLAY_TRANCHE
            stop_condition = KALSHI_CRYPTO_PROXY_RESEARCH_REPLAY_STOP_CONDITION
        elif evidence_status == "signal_factory_crypto_proxy_feature_model_no_research_candidates":
            recommended_next_tranche = (
                "Use predmarket as the Kalshi signal-factory command center: rotate to new registered crypto "
                "feature families after the current proxy model failed falsification."
            )
            stop_condition = (
                "Stop before discretionary signal selection or reusing failed hypotheses without new registered features."
            )
        elif evidence_status == "signal_factory_crypto_proxy_feature_model_insufficient_labels":
            recommended_next_tranche = KALSHI_CRYPTO_PROXY_OBSERVATION_ACCUMULATION_TRANCHE
            stop_condition = (
                "Stop before lowering sample thresholds, counting duplicate contract labels as independent evidence, "
                "or creating EV/sizing/execution claims."
            )
        elif evidence_status == "signal_factory_crypto_proxy_labels_ready":
            recommended_next_tranche = KALSHI_CRYPTO_PROXY_FEATURE_MODEL_TRANCHE
            stop_condition = KALSHI_CRYPTO_PROXY_FEATURE_MODEL_STOP_CONDITION
        elif evidence_status == "signal_factory_crypto_proxy_observations_waiting_settlement":
            recommended_next_tranche = KALSHI_CRYPTO_PROXY_OBSERVATION_ACCUMULATION_TRANCHE
            stop_condition = KALSHI_CRYPTO_PROXY_OBSERVATION_ACCUMULATION_STOP_CONDITION
        elif evidence_status == "signal_factory_crypto_proxy_feature_packet_ready":
            recommended_next_tranche = KALSHI_CRYPTO_PROXY_OBSERVATION_TRANCHE
            stop_condition = KALSHI_CRYPTO_PROXY_OBSERVATION_STOP_CONDITION
        elif evidence_status == "signal_factory_probability_breadth_scout_ready_crypto_proxy_route":
            recommended_next_tranche = KALSHI_CRYPTO_PROXY_FEATURE_TRANCHE
            stop_condition = KALSHI_CRYPTO_PROXY_FEATURE_STOP_CONDITION
        elif evidence_status == "signal_factory_oos_pending_observations_waiting_settlement":
            recommended_next_tranche = KALSHI_PROBABILITY_BREADTH_TRANCHE
            stop_condition = KALSHI_PROBABILITY_BREADTH_STOP_CONDITION
        elif evidence_status == "signal_factory_oos_label_packet_ready_backtest_pending":
            recommended_next_tranche = KALSHI_LABELED_OOS_BACKTEST_TRANCHE
            stop_condition = KALSHI_LABELED_OOS_BACKTEST_STOP_CONDITION
        elif evidence_status == "signal_factory_oos_backtest_harness_ready_labeled_observations_missing":
            recommended_next_tranche = KALSHI_LABELED_OBSERVATION_PACKET_TRANCHE
            stop_condition = KALSHI_LABELED_OBSERVATION_PACKET_STOP_CONDITION
        elif evidence_status == "signal_factory_oos_backtest_harness_ready_oos_samples_insufficient":
            recommended_next_tranche = (
                "Use predmarket as the Kalshi signal-factory command center: accumulate more time-safe labeled "
                "OOS observations for the registered hypotheses without lowering validation thresholds."
            )
            stop_condition = "Stop before lowering OOS/FDR thresholds without an explicit policy review."
        elif evidence_status == "signal_factory_oos_backtest_ready_research_promotions_present":
            recommended_next_tranche = (
                "Use predmarket as the Kalshi signal-factory command center: build capacity, correlation, decay, "
                "and execution-control gates for research-promoted hypotheses before any sizing work."
            )
            stop_condition = (
                "Stop before execution/account/order paths until capacity, correlation, sizing, and kill-switch gates exist."
            )
        elif evidence_status == "signal_factory_hypothesis_registry_ready_falsification_blocked_missing_labeled_oos_evidence":
            recommended_next_tranche = KALSHI_LABELED_OOS_BACKTEST_TRANCHE
            stop_condition = KALSHI_LABELED_OOS_BACKTEST_STOP_CONDITION
        else:
            recommended_next_tranche = KALSHI_SIGNAL_FACTORY_TRANCHE
            stop_condition = KALSHI_SIGNAL_FACTORY_STOP_CONDITION
    if repo_id == "predmarket-alpha" and evidence_status in {
        "universe_scan_ready_with_model_routes",
        "universe_scan_ready_soft_watch_only",
        "universe_scan_ready",
        "universe_scan_blocked_public_fetch_failed",
    }:
        recommended_next_tranche = KALSHI_UNIVERSE_SCAN_TRANCHE
        stop_condition = KALSHI_UNIVERSE_SCAN_STOP_CONDITION
    if repo_id == "predmarket-alpha" and evidence_status in {
        "kalshi_ev_queue_robustness_ready",
        "kalshi_ev_queue_robustness_repeat_positive_cost_caveated",
        "kalshi_ev_queue_robustness_observed_not_repeat_positive",
        "kalshi_ev_queue_robustness_blocked_no_snapshots",
    }:
        recommended_next_tranche = KALSHI_EV_QUEUE_ROBUSTNESS_TRANCHE
        stop_condition = KALSHI_EV_QUEUE_ROBUSTNESS_STOP_CONDITION
    if repo_id == "predmarket-alpha" and evidence_status in {
        "kalshi_ev_review_queue_ready_with_robust_candidates",
        "kalshi_ev_review_queue_positive_candidates_need_robustness",
        "kalshi_ev_review_queue_blocked_no_positive_usable_rows",
    }:
        recommended_next_tranche = KALSHI_EV_REVIEW_QUEUE_TRANCHE
        stop_condition = KALSHI_EV_REVIEW_QUEUE_STOP_CONDITION
    if repo_id == "predmarket-alpha" and evidence_status in {
        "kalshi_ev_calibration_work_order_ready",
        "kalshi_ev_calibration_work_order_ready_source_gated",
        "kalshi_ev_overlay_preflight_blocked_missing_or_unjoined_inputs",
        "kalshi_ev_ledger_candidates_present_but_not_usable",
        "kalshi_ev_ledger_ready_with_usable_contract_edges",
    }:
        recommended_next_tranche = KALSHI_EV_CALIBRATION_WORK_ORDER_TRANCHE
        stop_condition = KALSHI_EV_CALIBRATION_WORK_ORDER_STOP_CONDITION
    if repo_id == "predmarket-alpha" and evidence_status == "kalshi_ev_contract_mapping_work_order_ready":
        recommended_next_tranche = KALSHI_EV_CONTRACT_MAPPING_WORK_ORDER_TRANCHE
        stop_condition = KALSHI_EV_CONTRACT_MAPPING_WORK_ORDER_STOP_CONDITION
    if repo_id == "predmarket-alpha" and evidence_status in {
        "kalshi_ev_local_contract_evidence_blocked_no_nfl_target_snapshot",
        "kalshi_ev_local_contract_evidence_blocked_no_ready_target_match",
        "kalshi_ev_local_contract_evidence_ready_for_overlay_fill",
    }:
        recommended_next_tranche = KALSHI_EV_LOCAL_CONTRACT_EVIDENCE_SCOUT_TRANCHE
        stop_condition = KALSHI_EV_LOCAL_CONTRACT_EVIDENCE_SCOUT_STOP_CONDITION

    status["scheduling"] = {
        "score_components": components,
        "priority": priority,
        "recommended_next_tranche": recommended_next_tranche,
        "stop_condition": stop_condition,
    }
    return status


def finish_status(status: dict[str, Any], evidence: dict[str, Any], gates: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = dict(evidence)
    evidence["gate_counts"] = gate_counts(gates)
    status["evidence"] = evidence
    status["gates"] = gates
    return apply_scheduling(status)


def predmarket_status(root: Path) -> dict[str, Any]:
    status = base_status("predmarket-alpha", root)
    artifact_paths = [
        "docs/codex/macro/federated-market-edge-os-plan.md",
        "docs/codex/macro/kalshi-signal-factory-north-star.md",
        "docs/codex/macro/active-universe.json",
        "docs/codex/macro/status.schema.json",
        "docs/codex/macro/kalshi-contract-ev-ledger.schema.json",
        "docs/codex/macro/kalshi-universe-candidate.schema.json",
        "docs/codex/macro/kalshi-hypothesis-candidate.schema.json",
        "docs/codex/macro/kalshi-labeled-oos-observation.schema.json",
        "docs/codex/macro/latest-kalshi-contract-ev-ledger.json",
        "docs/codex/macro/latest-kalshi-contract-ev-ledger.md",
        "docs/codex/macro/latest-kalshi-ev-overlay-preflight.json",
        "docs/codex/macro/latest-kalshi-ev-overlay-preflight.md",
        "docs/codex/macro/latest-kalshi-ev-calibration-work-order.json",
        "docs/codex/macro/latest-kalshi-ev-calibration-work-order.md",
        "docs/codex/macro/latest-kalshi-ev-calibrated-probability-template.json",
        "docs/codex/macro/latest-kalshi-ev-contract-mapping-work-order.json",
        "docs/codex/macro/latest-kalshi-ev-contract-mapping-work-order.md",
        "docs/codex/macro/latest-kalshi-ev-contract-mapping-template.json",
        "docs/codex/macro/latest-kalshi-ev-contract-mapped-probability-template.json",
        "docs/codex/macro/latest-kalshi-ev-local-contract-evidence-scout.json",
        "docs/codex/macro/latest-kalshi-ev-local-contract-evidence-scout.md",
        "docs/codex/macro/latest-kalshi-ev-nfl-overlay-assembler.json",
        "docs/codex/macro/latest-kalshi-ev-nfl-overlay-assembler.md",
        "docs/codex/macro/latest-kalshi-ev-review-queue.json",
        "docs/codex/macro/latest-kalshi-ev-review-queue.md",
        "docs/codex/macro/latest-kalshi-ev-review-queue.csv",
        "docs/codex/macro/latest-kalshi-ev-queue-robustness.json",
        "docs/codex/macro/latest-kalshi-ev-queue-robustness.md",
        "docs/codex/macro/latest-kalshi-ev-queue-robustness.csv",
        "docs/codex/macro/latest-kalshi-universe-scan.json",
        "docs/codex/macro/latest-kalshi-universe-candidates.csv",
        "docs/codex/macro/latest-kalshi-universe-routes.json",
        "docs/codex/macro/latest-kalshi-soft-market-watch.md",
        "docs/codex/macro/latest-kalshi-signal-factory-status.json",
        "docs/codex/macro/latest-kalshi-signal-factory-status.md",
        "docs/codex/macro/latest-kalshi-hypothesis-registry.json",
        "docs/codex/macro/latest-kalshi-hypothesis-registry.md",
        "docs/codex/macro/latest-kalshi-hypothesis-registry.csv",
        "docs/codex/macro/latest-kalshi-falsification-gate.json",
        "docs/codex/macro/latest-kalshi-falsification-gate.md",
        "docs/codex/macro/latest-kalshi-labeled-observation-builder.json",
        "docs/codex/macro/latest-kalshi-labeled-observation-builder.md",
        "docs/codex/macro/latest-kalshi-labeled-observation-builder.csv",
        "docs/codex/macro/latest-kalshi-labeled-oos-backtest.json",
        "docs/codex/macro/latest-kalshi-labeled-oos-backtest.md",
        "docs/codex/macro/latest-kalshi-labeled-oos-backtest.csv",
        "docs/codex/macro/latest-kalshi-oos-falsification-gate.json",
        "docs/codex/macro/latest-kalshi-oos-falsification-gate.md",
        "docs/codex/macro/latest-kalshi-probability-breadth-scout.json",
        "docs/codex/macro/latest-kalshi-probability-breadth-scout.md",
        "docs/codex/macro/latest-kalshi-probability-breadth-scout-candidates.csv",
        "docs/codex/macro/latest-kalshi-crypto-proxy-feature-packet.json",
        "docs/codex/macro/latest-kalshi-crypto-proxy-feature-packet.md",
        "docs/codex/macro/latest-kalshi-crypto-proxy-feature-packet.csv",
        "docs/codex/macro/latest-kalshi-crypto-proxy-observation-loop.json",
        "docs/codex/macro/latest-kalshi-crypto-proxy-observation-loop.md",
        "docs/codex/macro/latest-kalshi-crypto-proxy-observation-loop.csv",
        "docs/codex/macro/latest-kalshi-crypto-proxy-feature-model-falsification.json",
        "docs/codex/macro/latest-kalshi-crypto-proxy-feature-model-falsification.md",
        "docs/codex/macro/latest-kalshi-crypto-proxy-feature-model-falsification.csv",
        "docs/codex/macro/latest-macro-blocker-audit.json",
        "docs/codex/macro/latest-macro-blocker-audit.md",
        "docs/codex/current-state.md",
        "docs/codex/manual-drops/kalshi-ev-calibrated-probability-contract.md",
        "docs/codex/manual-drops/kalshi-ev-contract-mapping-contract.md",
        "docs/codex/manual-drops/kalshi-ev-nfl-contract-snapshot-contract.md",
        "docs/codex/manual-drops/predmarket-type2-sportsbook-reference-contract.md",
        "docs/codex/tranches/2026-07-01-kalshi-contract-ev-ledger.md",
        "docs/codex/tranches/2026-07-01-kalshi-ev-local-contract-evidence-scout.md",
        "docs/codex/tranches/2026-07-01-kalshi-ev-nfl-overlay-assembler.md",
        "docs/codex/tranches/2026-07-01-kalshi-universe-scanner.md",
        "docs/codex/tranches/2026-07-01-kalshi-signal-factory-status.md",
        "docs/codex/tranches/2026-07-01-kalshi-hypothesis-registry.md",
        "docs/codex/tranches/2026-07-01-kalshi-labeled-oos-backtest.md",
        "docs/codex/tranches/2026-07-01-kalshi-labeled-observation-builder.md",
        "docs/codex/tranches/2026-07-01-kalshi-probability-breadth-scout.md",
        "docs/codex/tranches/2026-07-01-kalshi-crypto-proxy-feature-packet.md",
        "docs/codex/tranches/2026-07-02-kalshi-crypto-proxy-observation-loop.md",
        "docs/codex/tranches/2026-07-02-kalshi-crypto-proxy-feature-model-falsification.md",
        "docs/codex/tranches/2026-07-01-macro-blocker-audit.md",
        "docs/kalshi_edge_strategy.md",
        "docs/kalshi_research_desk.md",
        "predmarket/kalshi_execution_cost.py",
        "predmarket/kalshi_manual_drop_capture.py",
        "predmarket/kalshi_universe_scan.py",
        "predmarket/type2_reference_builder.py",
        "predmarket/type2_reference_intake.py",
        "predmarket/type2_paper_matcher.py",
        "predmarket/type2_candidate_disposition.py",
        "predmarket/type2_threshold_sensitivity.py",
        "scripts/kalshi_contract_ev_ledger.py",
        "scripts/kalshi_ev_local_contract_evidence_scout.py",
        "scripts/kalshi_ev_nfl_overlay_assembler.py",
        "scripts/kalshi_ev_review_queue.py",
        "scripts/kalshi_ev_queue_robustness.py",
        "scripts/kalshi_signal_factory_status.py",
        "scripts/kalshi_hypothesis_registry.py",
        "scripts/kalshi_labeled_observation_builder.py",
        "scripts/kalshi_labeled_oos_backtest.py",
        "scripts/kalshi_probability_breadth_scout.py",
        "scripts/kalshi_crypto_proxy_feature_packet.py",
        "scripts/kalshi_crypto_proxy_observation_loop.py",
        "scripts/kalshi_crypto_proxy_feature_model_falsification.py",
        "scripts/kalshi_crypto_proxy_research_candidate_replay.py",
        "scripts/codex_macro_blocker_audit.py",
        "scripts/codex_macro_router.py",
        "scripts/codex_macro_unlock_scout.py",
        "tests/test_kalshi_execution_cost.py",
        "tests/test_kalshi_contract_ev_ledger.py",
        "tests/test_kalshi_ev_local_contract_evidence_scout.py",
        "tests/test_kalshi_ev_nfl_overlay_assembler.py",
        "tests/test_kalshi_ev_review_queue.py",
        "tests/test_kalshi_ev_queue_robustness.py",
        "tests/test_kalshi_universe_scan.py",
        "tests/test_kalshi_signal_factory_status.py",
        "tests/test_kalshi_hypothesis_registry.py",
        "tests/test_kalshi_labeled_observation_builder.py",
        "tests/test_kalshi_labeled_oos_backtest.py",
        "tests/test_kalshi_probability_breadth_scout.py",
        "tests/test_kalshi_crypto_proxy_feature_packet.py",
        "tests/test_kalshi_crypto_proxy_observation_loop.py",
        "tests/test_kalshi_crypto_proxy_feature_model_falsification.py",
        "tests/test_kalshi_crypto_proxy_research_candidate_replay.py",
        "tests/test_codex_macro_blocker_audit.py",
        "tests/test_kalshi_manual_drop_capture.py",
        "tests/test_type2_reference_builder.py",
        "tests/test_type2_reference_intake.py",
        "tests/test_type2_paper_matcher.py",
        "tests/test_type2_candidate_disposition.py",
        "tests/test_type2_threshold_sensitivity.py",
        "tests/test_codex_macro_router.py",
        "tests/test_codex_macro_unlock_scout.py",
        "docs/codex/macro/latest-unlock-scout.json",
        "docs/codex/macro/latest-unlock-scout.md",
        "docs/codex/artifacts/kalshi-manual-drop-capture-latest/kalshi-manual-drop-capture-latest.json",
        "docs/codex/artifacts/kalshi-manual-drop-capture-latest/kalshi-manual-drop-capture-latest.md",
        "docs/codex/artifacts/type2-reference-builder-latest/type2-reference-builder-latest.json",
        "docs/codex/artifacts/type2-reference-builder-latest/type2-reference-builder-latest.md",
        "docs/codex/artifacts/type2-reference-preflight-latest/type2-reference-preflight-latest.json",
        "docs/codex/artifacts/type2-reference-preflight-latest/type2-reference-preflight-latest.md",
        "docs/codex/artifacts/type2-paper-matcher-latest/type2-paper-matcher-latest.json",
        "docs/codex/artifacts/type2-paper-matcher-latest/type2-paper-matcher-latest.md",
        "docs/codex/artifacts/type2-candidate-disposition-latest/type2-candidate-disposition-latest.json",
        "docs/codex/artifacts/type2-candidate-disposition-latest/type2-candidate-disposition-latest.md",
        "docs/codex/artifacts/type2-threshold-sensitivity-latest/type2-threshold-sensitivity-latest.json",
        "docs/codex/artifacts/type2-threshold-sensitivity-latest/type2-threshold-sensitivity-latest.md",
        "docs/codex/tranches/2026-06-28-predmarket-reference-input-acquired.md",
        "docs/codex/tranches/2026-06-28-macro-parked-state-router-summary.md",
        "docs/codex/tranches/2026-06-28-predmarket-blocked-input-router-hardening.md",
        "docs/codex/tranches/2026-06-28-predmarket-type2-reference-intake-preflight.md",
        "docs/codex/tranches/2026-06-27-predmarket-type2-paper-matcher-readiness.md",
        "docs/codex/tranches/2026-06-28-kalshi-manual-drop-capture.md",
        "docs/codex/tranches/2026-06-29-repeatability-os-command-center-refresh.md",
        "NEXT_DIRECTIVE_2026-06-29_MACRO_PARKED_INPUT_COLLECTION.md",
        "NEXT_DIRECTIVE_2026-06-28_KALSHI_MANUAL_DROP_CAPTURE.md",
        "NEXT_DIRECTIVE_2026-06-28_MACRO_PARKED_STATE_ROUTER_SUMMARY.md",
        "NEXT_DIRECTIVE_2026-06-28_PREDMARKET_TYPE2_REFERENCE_BUILDER_HARDENING.md",
        "NEXT_DIRECTIVE_2026-06-28_PREDMARKET_TYPE2_CANDIDATE_DISPOSITION.md",
        "NEXT_DIRECTIVE_2026-06-28_PREDMARKET_BLOCKED_INPUT_ROUTER_HARDENING.md",
        "NEXT_DIRECTIVE_2026-06-28_PREDMARKET_TYPE2_REFERENCE_INTAKE_PREFLIGHT.md",
        "NEXT_DIRECTIVE_2026-06-27_PREDMARKET_TYPE2_PAPER_MATCHER_READINESS.md",
        "NEXT_DIRECTIVE_2026-07-01_KALSHI_PROBABILITY_BREADTH_SCOUT.md",
        "NEXT_DIRECTIVE_2026-07-01_KALSHI_CRYPTO_PROXY_FEATURE_PACKET.md",
        "COMPLETION_REPORT_2026-06-28_MACRO_PARKED_STATE_ROUTER_SUMMARY_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-28_PREDMARKET_BLOCKED_INPUT_ROUTER_HARDENING_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-28_PREDMARKET_TYPE2_REFERENCE_INTAKE_PREFLIGHT_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-27_PREDMARKET_TYPE2_PAPER_MATCHER_READINESS_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-28_KALSHI_MANUAL_DROP_CAPTURE_FULFILLED.md",
        "COMPLETION_REPORT_2026-07-01_KALSHI_EV_OVERLAY_PREFLIGHT_FULFILLED.md",
        "COMPLETION_REPORT_2026-07-01_KALSHI_EV_CALIBRATION_WORK_ORDER_AND_ROUTER_INTEGRATION_FULFILLED.md",
        "COMPLETION_REPORT_2026-07-01_KALSHI_EV_NFL_CONTRACT_MAPPING_WORK_ORDER_FULFILLED.md",
        "COMPLETION_REPORT_2026-07-01_KALSHI_EV_LOCAL_CONTRACT_EVIDENCE_SCOUT_FULFILLED.md",
        "COMPLETION_REPORT_2026-07-01_KALSHI_EV_NFL_OVERLAY_ASSEMBLER_FULFILLED.md",
        "COMPLETION_REPORT_2026-07-01_KALSHI_EV_QUEUE_ROBUSTNESS_FULFILLED.md",
        "COMPLETION_REPORT_2026-07-01_KALSHI_UNIVERSE_SCANNER_FULFILLED.md",
        "COMPLETION_REPORT_2026-07-01_KALSHI_SIGNAL_FACTORY_STATUS_FULFILLED.md",
        "COMPLETION_REPORT_2026-07-01_KALSHI_HYPOTHESIS_REGISTRY_AND_FALSIFICATION_GATE_FULFILLED.md",
        "COMPLETION_REPORT_2026-07-01_KALSHI_LABELED_OOS_BACKTEST_HARNESS_FULFILLED.md",
        "COMPLETION_REPORT_2026-07-01_KALSHI_LABELED_OBSERVATION_BUILDER_FULFILLED.md",
        "COMPLETION_REPORT_2026-07-01_KALSHI_PROBABILITY_BREADTH_SCOUT_FULFILLED.md",
        "COMPLETION_REPORT_2026-07-01_KALSHI_CRYPTO_PROXY_FEATURE_PACKET_FULFILLED.md",
        "COMPLETION_REPORT_2026-07-01_MACRO_BLOCKER_AUDIT_FULFILLED.md",
        "data/kalshi_edge_report_2026-06-16.md",
        "data/kalshi_scored_refined_2026-06-16.json",
        "data/kalshi_scored_2026-06-16.json",
        "data/kalshi_run_log_2026-06-16.txt",
        ".tmp/kalshi-smoke.json",
    ]
    artifacts, hashes = artifact_pack(root, artifact_paths)
    config_text = read_text(root, "config/config.yaml")
    strategy_text = read_text(root, "docs/kalshi_edge_strategy.md")
    refined = read_json(root, "data/kalshi_scored_refined_2026-06-16.json")
    scored = read_json(root, "data/kalshi_scored_2026-06-16.json")
    smoke = read_json(root, ".tmp/kalshi-smoke.json")
    type2_matcher = read_json(
        root,
        "docs/codex/artifacts/type2-paper-matcher-latest/type2-paper-matcher-latest.json",
    )
    type2_builder = read_json(
        root,
        "docs/codex/artifacts/type2-reference-builder-latest/type2-reference-builder-latest.json",
    )
    type2_preflight = read_json(
        root,
        "docs/codex/artifacts/type2-reference-preflight-latest/type2-reference-preflight-latest.json",
    )
    type2_disposition = read_json(
        root,
        "docs/codex/artifacts/type2-candidate-disposition-latest/type2-candidate-disposition-latest.json",
    )
    type2_threshold_sensitivity = read_json(
        root,
        "docs/codex/artifacts/type2-threshold-sensitivity-latest/type2-threshold-sensitivity-latest.json",
    )
    kalshi_ev_ledger = read_json(root, "docs/codex/macro/latest-kalshi-contract-ev-ledger.json")
    kalshi_ev_overlay_preflight = read_json(root, "docs/codex/macro/latest-kalshi-ev-overlay-preflight.json")
    kalshi_ev_calibration_work_order = read_json(
        root,
        "docs/codex/macro/latest-kalshi-ev-calibration-work-order.json",
    )
    kalshi_ev_contract_mapping_work_order = read_json(
        root,
        "docs/codex/macro/latest-kalshi-ev-contract-mapping-work-order.json",
    )
    kalshi_ev_local_contract_evidence_scout = read_json(
        root,
        "docs/codex/macro/latest-kalshi-ev-local-contract-evidence-scout.json",
    )
    kalshi_ev_nfl_overlay_assembler = read_json(
        root,
        "docs/codex/macro/latest-kalshi-ev-nfl-overlay-assembler.json",
    )
    kalshi_ev_review_queue = read_json(
        root,
        "docs/codex/macro/latest-kalshi-ev-review-queue.json",
    )
    kalshi_ev_queue_robustness = read_json(
        root,
        "docs/codex/macro/latest-kalshi-ev-queue-robustness.json",
    )
    kalshi_universe_scan = read_json(
        root,
        "docs/codex/macro/latest-kalshi-universe-scan.json",
    )
    kalshi_signal_factory_status = read_json(
        root,
        "docs/codex/macro/latest-kalshi-signal-factory-status.json",
    )
    kalshi_hypothesis_registry = read_json(
        root,
        "docs/codex/macro/latest-kalshi-hypothesis-registry.json",
    )
    kalshi_falsification_gate = read_json(
        root,
        "docs/codex/macro/latest-kalshi-falsification-gate.json",
    )
    kalshi_labeled_observation_builder = read_json(
        root,
        "docs/codex/macro/latest-kalshi-labeled-observation-builder.json",
    )
    kalshi_labeled_oos_backtest = read_json(
        root,
        "docs/codex/macro/latest-kalshi-labeled-oos-backtest.json",
    )
    kalshi_probability_breadth_scout = read_json(
        root,
        "docs/codex/macro/latest-kalshi-probability-breadth-scout.json",
    )
    kalshi_crypto_proxy_feature_packet = read_json(
        root,
        "docs/codex/macro/latest-kalshi-crypto-proxy-feature-packet.json",
    )
    kalshi_crypto_proxy_observation_loop = read_json(
        root,
        "docs/codex/macro/latest-kalshi-crypto-proxy-observation-loop.json",
    )
    kalshi_crypto_proxy_feature_model_falsification = read_json(
        root,
        "docs/codex/macro/latest-kalshi-crypto-proxy-feature-model-falsification.json",
    )
    kalshi_crypto_proxy_research_candidate_replay = read_json(
        root,
        "docs/codex/macro/latest-kalshi-crypto-proxy-research-candidate-replay.json",
    )
    kalshi_capture = read_json(
        root,
        "docs/codex/artifacts/kalshi-manual-drop-capture-latest/kalshi-manual-drop-capture-latest.json",
    )
    execution_disabled = bool(re.search(r"execution_enabled:\s*false", config_text, re.IGNORECASE))
    type2_loaded = "Type 2" in strategy_text and "sports" in strategy_text.lower()
    type2_matcher_present = (
        isinstance(type2_matcher, dict)
        and type2_matcher.get("research_only") is True
        and type2_matcher.get("execution_enabled") is False
        and isinstance(type2_matcher.get("safety"), dict)
        and type2_matcher["safety"].get("provider_api_calls") is False
        and type2_matcher["safety"].get("account_or_order_paths") is False
    )
    type2_matcher_status = type2_matcher.get("status") if isinstance(type2_matcher, dict) else None
    type2_builder_present = (
        isinstance(type2_builder, dict)
        and type2_builder.get("research_only") is True
        and type2_builder.get("execution_enabled") is False
        and isinstance(type2_builder.get("safety"), dict)
        and type2_builder["safety"].get("provider_api_calls") is False
        and type2_builder["safety"].get("account_or_order_paths") is False
    )
    type2_builder_status = type2_builder.get("status") if isinstance(type2_builder, dict) else None
    type2_preflight_present = (
        isinstance(type2_preflight, dict)
        and type2_preflight.get("research_only") is True
        and type2_preflight.get("execution_enabled") is False
        and isinstance(type2_preflight.get("safety"), dict)
        and type2_preflight["safety"].get("provider_api_calls") is False
        and type2_preflight["safety"].get("account_or_order_paths") is False
    )
    type2_preflight_status = type2_preflight.get("status") if isinstance(type2_preflight, dict) else None
    type2_disposition_present = (
        isinstance(type2_disposition, dict)
        and type2_disposition.get("research_only") is True
        and type2_disposition.get("execution_enabled") is False
        and isinstance(type2_disposition.get("safety"), dict)
        and type2_disposition["safety"].get("provider_api_calls") is False
        and type2_disposition["safety"].get("account_or_order_paths") is False
    )
    type2_disposition_status = type2_disposition.get("status") if isinstance(type2_disposition, dict) else None
    type2_disposition_summary = type2_disposition.get("summary") if isinstance(type2_disposition, dict) else {}
    type2_threshold_sensitivity_present = (
        isinstance(type2_threshold_sensitivity, dict)
        and type2_threshold_sensitivity.get("research_only") is True
        and type2_threshold_sensitivity.get("execution_enabled") is False
        and isinstance(type2_threshold_sensitivity.get("safety"), dict)
        and type2_threshold_sensitivity["safety"].get("provider_api_calls") is False
        and type2_threshold_sensitivity["safety"].get("account_or_order_paths") is False
    )
    type2_threshold_sensitivity_status = (
        type2_threshold_sensitivity.get("status")
        if isinstance(type2_threshold_sensitivity, dict)
        else None
    )
    type2_threshold_sensitivity_summary = (
        type2_threshold_sensitivity.get("summary")
        if isinstance(type2_threshold_sensitivity, dict)
        else {}
    )
    kalshi_capture_summary = kalshi_capture.get("summary") if isinstance(kalshi_capture, dict) else {}
    kalshi_capture_present = (
        isinstance(kalshi_capture, dict)
        and kalshi_capture.get("research_only") is True
        and kalshi_capture.get("execution_enabled") is False
        and isinstance(kalshi_capture.get("safety"), dict)
        and kalshi_capture["safety"].get("account_or_order_paths") is False
        and kalshi_capture["safety"].get("market_execution") is False
        and kalshi_capture["safety"].get("database_writes") is False
        and int(kalshi_capture_summary.get("market_count") or 0) > 0
    )
    kalshi_capture_status = kalshi_capture.get("status") if isinstance(kalshi_capture, dict) else None
    kalshi_ev_ledger_present = safe_research_json(kalshi_ev_ledger)
    kalshi_ev_ledger_status = kalshi_ev_ledger.get("status") if isinstance(kalshi_ev_ledger, dict) else None
    kalshi_ev_ledger_summary = (
        kalshi_ev_ledger.get("summary")
        if isinstance(kalshi_ev_ledger, dict) and isinstance(kalshi_ev_ledger.get("summary"), dict)
        else {}
    )
    kalshi_ev_overlay_preflight_present = safe_research_json(kalshi_ev_overlay_preflight)
    kalshi_ev_overlay_preflight_status = (
        kalshi_ev_overlay_preflight.get("status")
        if isinstance(kalshi_ev_overlay_preflight, dict)
        else None
    )
    kalshi_ev_overlay_preflight_summary = (
        kalshi_ev_overlay_preflight.get("summary")
        if (
            isinstance(kalshi_ev_overlay_preflight, dict)
            and isinstance(kalshi_ev_overlay_preflight.get("summary"), dict)
        )
        else {}
    )
    kalshi_ev_calibration_work_order_present = safe_research_json(kalshi_ev_calibration_work_order)
    kalshi_ev_calibration_work_order_status = (
        kalshi_ev_calibration_work_order.get("status")
        if isinstance(kalshi_ev_calibration_work_order, dict)
        else None
    )
    kalshi_ev_calibration_work_order_summary = (
        kalshi_ev_calibration_work_order.get("summary")
        if (
            isinstance(kalshi_ev_calibration_work_order, dict)
            and isinstance(kalshi_ev_calibration_work_order.get("summary"), dict)
        )
        else {}
    )
    kalshi_ev_contract_mapping_work_order_present = safe_research_json(kalshi_ev_contract_mapping_work_order)
    kalshi_ev_contract_mapping_work_order_status = (
        kalshi_ev_contract_mapping_work_order.get("status")
        if isinstance(kalshi_ev_contract_mapping_work_order, dict)
        else None
    )
    kalshi_ev_contract_mapping_work_order_summary = (
        kalshi_ev_contract_mapping_work_order.get("summary")
        if (
            isinstance(kalshi_ev_contract_mapping_work_order, dict)
            and isinstance(kalshi_ev_contract_mapping_work_order.get("summary"), dict)
        )
        else {}
    )
    kalshi_ev_local_contract_evidence_scout_present = safe_research_json(
        kalshi_ev_local_contract_evidence_scout
    )
    kalshi_ev_local_contract_evidence_scout_status = (
        kalshi_ev_local_contract_evidence_scout.get("status")
        if isinstance(kalshi_ev_local_contract_evidence_scout, dict)
        else None
    )
    kalshi_ev_local_contract_evidence_scout_summary = (
        kalshi_ev_local_contract_evidence_scout.get("summary")
        if (
            isinstance(kalshi_ev_local_contract_evidence_scout, dict)
            and isinstance(kalshi_ev_local_contract_evidence_scout.get("summary"), dict)
        )
        else {}
    )
    kalshi_ev_nfl_overlay_assembler_present = safe_research_json(kalshi_ev_nfl_overlay_assembler)
    kalshi_ev_nfl_overlay_assembler_status = (
        kalshi_ev_nfl_overlay_assembler.get("status")
        if isinstance(kalshi_ev_nfl_overlay_assembler, dict)
        else None
    )
    kalshi_ev_nfl_overlay_assembler_summary = (
        kalshi_ev_nfl_overlay_assembler.get("summary")
        if (
            isinstance(kalshi_ev_nfl_overlay_assembler, dict)
            and isinstance(kalshi_ev_nfl_overlay_assembler.get("summary"), dict)
        )
        else {}
    )
    kalshi_ev_review_queue_present = safe_research_json(kalshi_ev_review_queue)
    kalshi_ev_review_queue_status = (
        kalshi_ev_review_queue.get("status")
        if isinstance(kalshi_ev_review_queue, dict)
        else None
    )
    kalshi_ev_review_queue_summary = (
        kalshi_ev_review_queue.get("summary")
        if (
            isinstance(kalshi_ev_review_queue, dict)
            and isinstance(kalshi_ev_review_queue.get("summary"), dict)
        )
        else {}
    )
    kalshi_ev_queue_robustness_present = safe_research_json(kalshi_ev_queue_robustness)
    kalshi_ev_queue_robustness_status = (
        kalshi_ev_queue_robustness.get("status")
        if isinstance(kalshi_ev_queue_robustness, dict)
        else None
    )
    kalshi_ev_queue_robustness_summary = (
        kalshi_ev_queue_robustness.get("summary")
        if (
            isinstance(kalshi_ev_queue_robustness, dict)
            and isinstance(kalshi_ev_queue_robustness.get("summary"), dict)
        )
        else {}
    )
    kalshi_universe_scan_present = safe_research_json(kalshi_universe_scan)
    kalshi_universe_scan_status = (
        kalshi_universe_scan.get("status")
        if isinstance(kalshi_universe_scan, dict)
        else None
    )
    kalshi_universe_scan_summary = (
        kalshi_universe_scan.get("summary")
        if (
            isinstance(kalshi_universe_scan, dict)
            and isinstance(kalshi_universe_scan.get("summary"), dict)
        )
        else {}
    )
    kalshi_signal_factory_status_present = safe_research_json(kalshi_signal_factory_status)
    kalshi_signal_factory_evidence_status = (
        kalshi_signal_factory_status.get("status")
        if isinstance(kalshi_signal_factory_status, dict)
        else None
    )
    kalshi_signal_factory_summary = (
        kalshi_signal_factory_status.get("summary")
        if (
            isinstance(kalshi_signal_factory_status, dict)
            and isinstance(kalshi_signal_factory_status.get("summary"), dict)
        )
        else {}
    )
    kalshi_hypothesis_registry_present = safe_research_json(kalshi_hypothesis_registry)
    kalshi_hypothesis_registry_status = (
        kalshi_hypothesis_registry.get("status")
        if isinstance(kalshi_hypothesis_registry, dict)
        else None
    )
    kalshi_hypothesis_registry_summary = (
        kalshi_hypothesis_registry.get("summary")
        if (
            isinstance(kalshi_hypothesis_registry, dict)
            and isinstance(kalshi_hypothesis_registry.get("summary"), dict)
        )
        else {}
    )
    kalshi_falsification_gate_present = safe_research_json(kalshi_falsification_gate)
    kalshi_falsification_gate_status = (
        kalshi_falsification_gate.get("status")
        if isinstance(kalshi_falsification_gate, dict)
        else None
    )
    kalshi_labeled_observation_builder_present = safe_research_json(kalshi_labeled_observation_builder)
    kalshi_labeled_observation_builder_status = (
        kalshi_labeled_observation_builder.get("status")
        if isinstance(kalshi_labeled_observation_builder, dict)
        else None
    )
    kalshi_labeled_observation_builder_summary = (
        kalshi_labeled_observation_builder.get("summary")
        if (
            isinstance(kalshi_labeled_observation_builder, dict)
            and isinstance(kalshi_labeled_observation_builder.get("summary"), dict)
        )
        else {}
    )
    kalshi_labeled_oos_backtest_present = safe_research_json(kalshi_labeled_oos_backtest)
    kalshi_labeled_oos_backtest_status = (
        kalshi_labeled_oos_backtest.get("status")
        if isinstance(kalshi_labeled_oos_backtest, dict)
        else None
    )
    kalshi_labeled_oos_backtest_summary = (
        kalshi_labeled_oos_backtest.get("summary")
        if (
            isinstance(kalshi_labeled_oos_backtest, dict)
            and isinstance(kalshi_labeled_oos_backtest.get("summary"), dict)
        )
        else {}
    )
    kalshi_probability_breadth_scout_present = safe_research_json(kalshi_probability_breadth_scout)
    kalshi_probability_breadth_scout_status = (
        kalshi_probability_breadth_scout.get("status")
        if isinstance(kalshi_probability_breadth_scout, dict)
        else None
    )
    kalshi_probability_breadth_scout_summary = (
        kalshi_probability_breadth_scout.get("summary")
        if (
            isinstance(kalshi_probability_breadth_scout, dict)
            and isinstance(kalshi_probability_breadth_scout.get("summary"), dict)
        )
        else {}
    )
    kalshi_crypto_proxy_feature_packet_present = safe_research_json(kalshi_crypto_proxy_feature_packet)
    kalshi_crypto_proxy_feature_packet_status = (
        kalshi_crypto_proxy_feature_packet.get("status")
        if isinstance(kalshi_crypto_proxy_feature_packet, dict)
        else None
    )
    kalshi_crypto_proxy_feature_packet_summary = (
        kalshi_crypto_proxy_feature_packet.get("summary")
        if (
            isinstance(kalshi_crypto_proxy_feature_packet, dict)
            and isinstance(kalshi_crypto_proxy_feature_packet.get("summary"), dict)
        )
        else {}
    )
    kalshi_crypto_proxy_observation_loop_present = safe_research_json(kalshi_crypto_proxy_observation_loop)
    kalshi_crypto_proxy_observation_loop_status = (
        kalshi_crypto_proxy_observation_loop.get("status")
        if isinstance(kalshi_crypto_proxy_observation_loop, dict)
        else None
    )
    kalshi_crypto_proxy_observation_loop_summary = (
        kalshi_crypto_proxy_observation_loop.get("summary")
        if (
            isinstance(kalshi_crypto_proxy_observation_loop, dict)
            and isinstance(kalshi_crypto_proxy_observation_loop.get("summary"), dict)
        )
        else {}
    )
    kalshi_crypto_proxy_feature_model_falsification_present = safe_research_json(
        kalshi_crypto_proxy_feature_model_falsification
    )
    kalshi_crypto_proxy_feature_model_falsification_status = (
        kalshi_crypto_proxy_feature_model_falsification.get("status")
        if isinstance(kalshi_crypto_proxy_feature_model_falsification, dict)
        else None
    )
    kalshi_crypto_proxy_feature_model_falsification_summary = (
        kalshi_crypto_proxy_feature_model_falsification.get("summary")
        if (
            isinstance(kalshi_crypto_proxy_feature_model_falsification, dict)
            and isinstance(kalshi_crypto_proxy_feature_model_falsification.get("summary"), dict)
        )
        else {}
    )
    kalshi_crypto_proxy_research_candidate_replay_present = safe_research_json(
        kalshi_crypto_proxy_research_candidate_replay
    )
    kalshi_crypto_proxy_research_candidate_replay_status = (
        kalshi_crypto_proxy_research_candidate_replay.get("status")
        if isinstance(kalshi_crypto_proxy_research_candidate_replay, dict)
        else None
    )
    kalshi_crypto_proxy_research_candidate_replay_summary = (
        kalshi_crypto_proxy_research_candidate_replay.get("summary")
        if (
            isinstance(kalshi_crypto_proxy_research_candidate_replay, dict)
            and isinstance(kalshi_crypto_proxy_research_candidate_replay.get("summary"), dict)
        )
        else {}
    )
    kept_disposition_candidates = (
        int(type2_disposition_summary.get("kept_review_candidate") or 0)
        if isinstance(type2_disposition_summary, dict)
        else 0
    )
    watch_only_disposition_candidates = (
        int(type2_disposition_summary.get("watch_only") or 0)
        if isinstance(type2_disposition_summary, dict)
        else 0
    )
    missing_mapped_sportsbook_reference = (
        type2_preflight_status == "blocked_missing_sportsbook_reference"
        or type2_matcher_status == "blocked_missing_sportsbook_reference"
    )

    gates = [
        make_gate(
            "research_only_execution_disabled",
            "pass" if execution_disabled else "fail",
            ["config/config.yaml keeps Kalshi execution disabled." if execution_disabled else "Kalshi execution flag is not explicitly false."],
            ["config/config.yaml"],
        ),
        make_gate(
            "kalshi_type2_strategy_loaded",
            "pass" if type2_loaded else "blocked",
            ["Kalshi strategy memo prioritizes Type 2 sports props." if type2_loaded else "Type 2 strategy memo was not found."],
            ["docs/kalshi_edge_strategy.md"],
        ),
        make_gate(
            "june_16_kalshi_paper_artifacts",
            "pass" if refined or scored else "warn",
            ["June 16 Kalshi scored artifacts are present." if refined or scored else "No June 16 scored artifact found."],
            ["data/kalshi_scored_refined_2026-06-16.json", "data/kalshi_scored_2026-06-16.json"],
        ),
        make_gate(
            "kalshi_manual_drop_capture_ready",
            "pass" if kalshi_capture_present else "warn",
            [
                (
                    "Kalshi manual-drop capture report is present, safe, and non-empty."
                    if kalshi_capture_present
                    else "Kalshi manual-drop capture report is missing or empty."
                )
            ],
            [
                path
                for path in [
                    "predmarket/kalshi_manual_drop_capture.py",
                    "tests/test_kalshi_manual_drop_capture.py",
                    "docs/codex/artifacts/kalshi-manual-drop-capture-latest/kalshi-manual-drop-capture-latest.json",
                    "docs/codex/artifacts/kalshi-manual-drop-capture-latest/kalshi-manual-drop-capture-latest.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "type2_reference_builder_ready",
            "pass" if type2_builder_present else "warn",
            [
                (
                    f"Type 2 reference builder report is present and safe; current run status is {type2_builder_status}."
                    if type2_builder_present
                    else "Type 2 reference builder report is missing."
                )
            ],
            [
                path
                for path in [
                    "predmarket/type2_reference_builder.py",
                    "tests/test_type2_reference_builder.py",
                    "docs/codex/artifacts/type2-reference-builder-latest/type2-reference-builder-latest.json",
                    "docs/codex/artifacts/type2-reference-builder-latest/type2-reference-builder-latest.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "type2_paper_matcher_ready",
            "pass" if type2_matcher_present else "blocked",
            [
                (
                    f"Type 2 paper matcher tool/report is present and safe; current run status is {type2_matcher_status}."
                    if type2_matcher_present
                    else "Type 2 paper matcher report is missing or unsafe."
                )
            ],
            [
                path
                for path in [
                    "predmarket/type2_paper_matcher.py",
                    "tests/test_type2_paper_matcher.py",
                    "docs/codex/artifacts/type2-paper-matcher-latest/type2-paper-matcher-latest.json",
                    "docs/codex/artifacts/type2-paper-matcher-latest/type2-paper-matcher-latest.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "type2_reference_preflight_ready",
            "pass" if type2_preflight_present else "blocked",
            [
                (
                    f"Type 2 reference preflight tool/report is present and safe; current run status is {type2_preflight_status}."
                    if type2_preflight_present
                    else "Type 2 reference preflight report is missing or unsafe."
                )
            ],
            [
                path
                for path in [
                    "predmarket/type2_reference_intake.py",
                    "tests/test_type2_reference_intake.py",
                    "docs/codex/manual-drops/predmarket-type2-sportsbook-reference-contract.md",
                    "docs/codex/artifacts/type2-reference-preflight-latest/type2-reference-preflight-latest.json",
                    "docs/codex/artifacts/type2-reference-preflight-latest/type2-reference-preflight-latest.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "mapped_sportsbook_reference_available",
            (
                "blocked"
                if missing_mapped_sportsbook_reference
                else ("pass" if type2_preflight_status == "reference_ready" else ("pass" if type2_matcher_present else "blocked"))
            ),
            [
                (
                    "No mapped local sportsbook reference was supplied; preflight and matcher are intentionally blocked."
                    if missing_mapped_sportsbook_reference
                    else (
                        "Mapped sportsbook reference passed the preflight."
                        if type2_preflight_status == "reference_ready"
                        else "Matcher status is unavailable."
                    )
                )
            ],
            [
                path
                for path in [
                    "docs/codex/artifacts/type2-reference-preflight-latest/type2-reference-preflight-latest.json",
                    "docs/codex/artifacts/type2-paper-matcher-latest/type2-paper-matcher-latest.json",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "type2_candidate_disposition_ready",
            "pass" if type2_disposition_present else "warn",
            [
                (
                    f"Type 2 candidate disposition report is present and safe; current run status is {type2_disposition_status}."
                    if type2_disposition_present
                    else "Type 2 candidate disposition report is missing."
                )
            ],
            [
                path
                for path in [
                    "predmarket/type2_candidate_disposition.py",
                    "tests/test_type2_candidate_disposition.py",
                    "docs/codex/artifacts/type2-candidate-disposition-latest/type2-candidate-disposition-latest.json",
                    "docs/codex/artifacts/type2-candidate-disposition-latest/type2-candidate-disposition-latest.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "timing_safe_review_candidates",
            (
                "pass"
                if kept_disposition_candidates > 0
                else ("blocked" if type2_disposition_status == "candidate_disposition_all_passes_downgraded" else "warn")
            ),
            [
                (
                    f"Timing-safe review candidates kept: {kept_disposition_candidates}."
                    if kept_disposition_candidates > 0
                    else (
                        "All paper-matcher pass rows were downgraded by timing checks."
                        if type2_disposition_status == "candidate_disposition_all_passes_downgraded"
                        else (
                            f"Timing-safe reference exists, but all {watch_only_disposition_candidates} "
                            "candidates are watch-only below the review threshold."
                            if type2_disposition_status == "candidate_disposition_watch_only"
                            else "Timing-safe candidate count is unknown."
                        )
                    )
                )
            ],
            [
                path
                for path in [
                    "docs/codex/artifacts/type2-candidate-disposition-latest/type2-candidate-disposition-latest.json",
                    "docs/codex/artifacts/type2-paper-matcher-latest/type2-paper-matcher-latest.json",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "type2_threshold_sensitivity_ready",
            "pass" if type2_threshold_sensitivity_present else "warn",
            [
                (
                    "Threshold sensitivity report is present and safe; "
                    f"max net divergence is {type2_threshold_sensitivity_summary.get('max_positive_review_only_net_divergence')}."
                    if type2_threshold_sensitivity_present
                    else "Threshold sensitivity report is missing."
                )
            ],
            [
                path
                for path in [
                    "predmarket/type2_threshold_sensitivity.py",
                    "tests/test_type2_threshold_sensitivity.py",
                    "docs/codex/artifacts/type2-threshold-sensitivity-latest/type2-threshold-sensitivity-latest.json",
                    "docs/codex/artifacts/type2-threshold-sensitivity-latest/type2-threshold-sensitivity-latest.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_ev_ledger_ready",
            (
                "pass"
                if kalshi_ev_ledger_present and int(kalshi_ev_ledger_summary.get("row_count") or 0) > 0
                else "blocked"
            ),
            [
                (
                    "Kalshi EV ledger is present, safe, and has "
                    f"{kalshi_ev_ledger_summary.get('row_count')} contract row(s)."
                    if kalshi_ev_ledger_present
                    else "Kalshi EV ledger is missing or unsafe."
                )
            ],
            [
                path
                for path in [
                    "scripts/kalshi_contract_ev_ledger.py",
                    "tests/test_kalshi_contract_ev_ledger.py",
                    "docs/codex/macro/latest-kalshi-contract-ev-ledger.json",
                    "docs/codex/macro/latest-kalshi-contract-ev-ledger.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_ev_overlay_preflight_ready",
            "pass" if kalshi_ev_overlay_preflight_present else "blocked",
            [
                (
                    f"Overlay preflight is present and safe; current status is {kalshi_ev_overlay_preflight_status}."
                    if kalshi_ev_overlay_preflight_present
                    else "Overlay preflight report is missing or unsafe."
                )
            ],
            [
                path
                for path in [
                    "docs/codex/macro/latest-kalshi-ev-overlay-preflight.json",
                    "docs/codex/macro/latest-kalshi-ev-overlay-preflight.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_ev_calibration_work_order_ready",
            (
                "pass"
                if (
                    kalshi_ev_calibration_work_order_present
                    and kalshi_ev_calibration_work_order_status
                    in {"calibration_work_order_ready", "calibration_work_order_ready_source_gated"}
                    and int(kalshi_ev_calibration_work_order_summary.get("selected_row_count") or 0) > 0
                )
                else "blocked"
            ),
            [
                (
                    "Calibration work order is ready with "
                    f"{kalshi_ev_calibration_work_order_summary.get('selected_row_count')} selected row(s)."
                    if kalshi_ev_calibration_work_order_present
                    else "Calibration work order report is missing or unsafe."
                )
            ],
            [
                path
                for path in [
                    "docs/codex/macro/latest-kalshi-ev-calibration-work-order.json",
                    "docs/codex/macro/latest-kalshi-ev-calibration-work-order.md",
                    "docs/codex/macro/latest-kalshi-ev-calibrated-probability-template.json",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_ev_contract_mapping_work_order_ready",
            (
                "pass"
                if (
                    kalshi_ev_contract_mapping_work_order_present
                    and kalshi_ev_contract_mapping_work_order_status == "contract_mapping_work_order_ready"
                    and int(kalshi_ev_contract_mapping_work_order_summary.get("selected_contract_side_count") or 0) > 0
                )
                else "blocked"
            ),
            [
                (
                    "Contract-mapping work order is ready with "
                    f"{kalshi_ev_contract_mapping_work_order_summary.get('selected_contract_side_count')} selected side(s)."
                    if kalshi_ev_contract_mapping_work_order_present
                    else "Contract-mapping work order report is missing or unsafe."
                )
            ],
            [
                path
                for path in [
                    "docs/codex/macro/latest-kalshi-ev-contract-mapping-work-order.json",
                    "docs/codex/macro/latest-kalshi-ev-contract-mapping-work-order.md",
                    "docs/codex/macro/latest-kalshi-ev-contract-mapping-template.json",
                    "docs/codex/macro/latest-kalshi-ev-contract-mapped-probability-template.json",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_ev_local_contract_evidence_scout_ready",
            "pass" if kalshi_ev_local_contract_evidence_scout_present else "warn",
            [
                (
                    "Local contract-evidence scout is present and safe; current status is "
                    f"{kalshi_ev_local_contract_evidence_scout_status}."
                    if kalshi_ev_local_contract_evidence_scout_present
                    else "Local contract-evidence scout has not been generated yet."
                )
            ],
            [
                path
                for path in [
                    "scripts/kalshi_ev_local_contract_evidence_scout.py",
                    "tests/test_kalshi_ev_local_contract_evidence_scout.py",
                    "docs/codex/macro/latest-kalshi-ev-local-contract-evidence-scout.json",
                    "docs/codex/macro/latest-kalshi-ev-local-contract-evidence-scout.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_ev_ready_local_target_contract_evidence_present",
            (
                "pass"
                if int(kalshi_ev_local_contract_evidence_scout_summary.get("ready_target_match_count") or 0) > 0
                else "blocked"
            ),
            [
                (
                    "Ready local target contract evidence rows present: "
                    f"{kalshi_ev_local_contract_evidence_scout_summary.get('ready_target_match_count')}."
                    if int(kalshi_ev_local_contract_evidence_scout_summary.get("ready_target_match_count") or 0) > 0
                    else (
                        "No selected NFL target has local exact ticker, official terms, and executable cost evidence."
                    )
                )
            ],
            [
                path
                for path in [
                    "docs/codex/macro/latest-kalshi-ev-local-contract-evidence-scout.json",
                    "docs/codex/macro/latest-kalshi-ev-local-contract-evidence-scout.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_ev_nfl_overlay_assembler_ready",
            "pass" if kalshi_ev_nfl_overlay_assembler_present else "warn",
            [
                (
                    "NFL overlay assembler report is present and safe; current status is "
                    f"{kalshi_ev_nfl_overlay_assembler_status}."
                    if kalshi_ev_nfl_overlay_assembler_present
                    else "NFL overlay assembler report has not been generated yet."
                )
            ],
            [
                path
                for path in [
                    "scripts/kalshi_ev_nfl_overlay_assembler.py",
                    "tests/test_kalshi_ev_nfl_overlay_assembler.py",
                    "docs/codex/macro/latest-kalshi-ev-nfl-overlay-assembler.json",
                    "docs/codex/macro/latest-kalshi-ev-nfl-overlay-assembler.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_ev_usable_rows_present",
            "pass" if int(kalshi_ev_ledger_summary.get("usable_row_count") or 0) > 0 else "blocked",
            [
                (
                    f"Usable EV rows present: {kalshi_ev_ledger_summary.get('usable_row_count')}."
                    if int(kalshi_ev_ledger_summary.get("usable_row_count") or 0) > 0
                    else (
                        "No usable EV rows yet; calibrated-probability and overlay gates still block usage."
                    )
                )
            ],
            [
                path
                for path in [
                    "docs/codex/macro/latest-kalshi-contract-ev-ledger.json",
                    "docs/codex/macro/latest-kalshi-ev-calibration-work-order.json",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_ev_review_queue_positive_rows_present",
            (
                "pass"
                if (
                    kalshi_ev_review_queue_present
                    and int(kalshi_ev_review_queue_summary.get("queued_row_count") or 0) > 0
                )
                else "blocked"
            ),
            [
                (
                    "EV review queue is present with "
                    f"{kalshi_ev_review_queue_summary.get('queued_row_count')} queued row(s), "
                    f"{kalshi_ev_review_queue_summary.get('positive_watch_count')} positive watch row(s), "
                    f"and {kalshi_ev_review_queue_summary.get('thin_positive_watch_count')} thin watch row(s)."
                    if kalshi_ev_review_queue_present
                    else "EV review queue report is missing or unsafe."
                )
            ],
            [
                path
                for path in [
                    "scripts/kalshi_ev_review_queue.py",
                    "tests/test_kalshi_ev_review_queue.py",
                    "docs/codex/macro/latest-kalshi-ev-review-queue.json",
                    "docs/codex/macro/latest-kalshi-ev-review-queue.md",
                    "docs/codex/macro/latest-kalshi-ev-review-queue.csv",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_ev_queue_robustness_present",
            (
                "pass"
                if (
                    kalshi_ev_queue_robustness_present
                    and int(kalshi_ev_queue_robustness_summary.get("repeat_positive_row_count") or 0) > 0
                )
                else ("warn" if kalshi_ev_queue_robustness_present else "blocked")
            ),
            [
                (
                    "EV queue robustness is present with "
                    f"{kalshi_ev_queue_robustness_summary.get('distinct_snapshot_count')} distinct snapshot(s), "
                    f"{kalshi_ev_queue_robustness_summary.get('repeat_positive_row_count')} repeat-positive row(s), "
                    f"and {kalshi_ev_queue_robustness_summary.get('robust_candidate_count')} robust candidate(s)."
                    if kalshi_ev_queue_robustness_present
                    else "EV queue robustness report is missing or unsafe."
                )
            ],
            [
                path
                for path in [
                    "scripts/kalshi_ev_queue_robustness.py",
                    "tests/test_kalshi_ev_queue_robustness.py",
                    "docs/codex/macro/latest-kalshi-ev-queue-robustness.json",
                    "docs/codex/macro/latest-kalshi-ev-queue-robustness.md",
                    "docs/codex/macro/latest-kalshi-ev-queue-robustness.csv",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_universe_scan_ready",
            (
                "pass"
                if (
                    kalshi_universe_scan_present
                    and int(kalshi_universe_scan_summary.get("candidate_count") or 0) > 0
                )
                else ("warn" if kalshi_universe_scan_present else "blocked")
            ),
            [
                (
                    "Kalshi universe scan is present with "
                    f"{kalshi_universe_scan_summary.get('candidate_count')} candidate(s), "
                    f"{kalshi_universe_scan_summary.get('model_route_candidate_count')} model-route candidate(s), "
                    f"and {kalshi_universe_scan_summary.get('soft_watch_candidate_count')} soft-watch candidate(s)."
                    if kalshi_universe_scan_present
                    else "Kalshi universe scan has not been generated yet."
                )
            ],
            [
                path
                for path in [
                    "predmarket/kalshi_universe_scan.py",
                    "tests/test_kalshi_universe_scan.py",
                    "docs/codex/macro/latest-kalshi-universe-scan.json",
                    "docs/codex/macro/latest-kalshi-universe-candidates.csv",
                    "docs/codex/macro/latest-kalshi-universe-routes.json",
                    "docs/codex/macro/latest-kalshi-soft-market-watch.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_signal_factory_status_ready",
            (
                "pass"
                if kalshi_signal_factory_status_present
                and kalshi_signal_factory_evidence_status
                and not str(kalshi_signal_factory_evidence_status).startswith("signal_factory_blocked")
                else ("blocked" if not kalshi_signal_factory_status_present else "warn")
            ),
            [
                (
                    "Signal factory status is present with "
                    f"{kalshi_signal_factory_summary.get('universe_candidate_count')} universe candidate(s), "
                    f"{kalshi_signal_factory_summary.get('legacy_usable_ev_row_count')} legacy usable row(s), "
                    f"and capability gates {kalshi_signal_factory_summary.get('capability_gate_counts')}."
                    if kalshi_signal_factory_status_present
                    else "Signal factory status has not been generated yet."
                )
            ],
            [
                path
                for path in [
                    "scripts/kalshi_signal_factory_status.py",
                    "tests/test_kalshi_signal_factory_status.py",
                    "docs/codex/macro/latest-kalshi-signal-factory-status.json",
                    "docs/codex/macro/latest-kalshi-signal-factory-status.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_hypothesis_registry_ready",
            (
                "pass"
                if (
                    kalshi_hypothesis_registry_present
                    and int(kalshi_hypothesis_registry_summary.get("hypothesis_count") or 0) > 0
                )
                else ("blocked" if not kalshi_hypothesis_registry_present else "warn")
            ),
            [
                (
                    "Hypothesis registry is present with "
                    f"{kalshi_hypothesis_registry_summary.get('hypothesis_count')} hypothesis candidate(s), "
                    f"{kalshi_hypothesis_registry_summary.get('multiple_testing_family_count')} multiple-testing family/families, "
                    f"and falsification status `{kalshi_hypothesis_registry_summary.get('falsification_status')}`."
                    if kalshi_hypothesis_registry_present
                    else "Hypothesis registry has not been generated yet."
                )
            ],
            [
                path
                for path in [
                    "scripts/kalshi_hypothesis_registry.py",
                    "tests/test_kalshi_hypothesis_registry.py",
                    "docs/codex/macro/kalshi-hypothesis-candidate.schema.json",
                    "docs/codex/macro/latest-kalshi-hypothesis-registry.json",
                    "docs/codex/macro/latest-kalshi-hypothesis-registry.md",
                    "docs/codex/macro/latest-kalshi-hypothesis-registry.csv",
                    "docs/codex/macro/latest-kalshi-falsification-gate.json",
                    "docs/codex/macro/latest-kalshi-falsification-gate.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_falsification_gate_ready",
            (
                "blocked"
                if kalshi_falsification_gate_present
                and str(kalshi_falsification_gate_status or "").startswith("falsification_gate_blocked")
                else ("pass" if kalshi_falsification_gate_present else "blocked")
            ),
            [
                (
                    f"Falsification gate status is `{kalshi_falsification_gate_status}`; "
                    "promotion remains blocked until labeled OOS cost-aware FDR evidence exists."
                    if kalshi_falsification_gate_present
                    else "Falsification gate has not been generated yet."
                )
            ],
            [
                path
                for path in [
                    "scripts/kalshi_hypothesis_registry.py",
                    "docs/codex/macro/latest-kalshi-falsification-gate.json",
                    "docs/codex/macro/latest-kalshi-falsification-gate.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_labeled_observation_builder_ready",
            (
                "pass"
                if kalshi_labeled_observation_builder_present
                else "blocked"
            ),
            [
                (
                    "Labeled observation builder is present with status "
                    f"`{kalshi_labeled_observation_builder_status}`, "
                    f"{kalshi_labeled_observation_builder_summary.get('total_pending_row_count')} pending observation(s), "
                    f"and {kalshi_labeled_observation_builder_summary.get('label_row_count')} label row(s)."
                    if kalshi_labeled_observation_builder_present
                    else "Labeled observation builder report has not been generated yet."
                )
            ],
            [
                path
                for path in [
                    "scripts/kalshi_labeled_observation_builder.py",
                    "tests/test_kalshi_labeled_observation_builder.py",
                    "docs/codex/macro/latest-kalshi-labeled-observation-builder.json",
                    "docs/codex/macro/latest-kalshi-labeled-observation-builder.md",
                    "docs/codex/macro/latest-kalshi-labeled-observation-builder.csv",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_labeled_oos_backtest_ready",
            (
                "pass"
                if kalshi_labeled_oos_backtest_present
                else "blocked"
            ),
            [
                (
                    "Labeled OOS backtest is present with status "
                    f"`{kalshi_labeled_oos_backtest_status}`, "
                    f"{kalshi_labeled_oos_backtest_summary.get('valid_observation_count')} valid observation(s), "
                    f"{kalshi_labeled_oos_backtest_summary.get('testable_hypothesis_count')} testable hypothesis/hypotheses, and "
                    f"{kalshi_labeled_oos_backtest_summary.get('promoted_research_hypothesis_count')} research promotion(s)."
                    if kalshi_labeled_oos_backtest_present
                    else "Labeled OOS backtest harness report has not been generated yet."
                )
            ],
            [
                path
                for path in [
                    "scripts/kalshi_labeled_oos_backtest.py",
                    "tests/test_kalshi_labeled_oos_backtest.py",
                    "docs/codex/macro/kalshi-labeled-oos-observation.schema.json",
                    "docs/codex/macro/latest-kalshi-labeled-oos-backtest.json",
                    "docs/codex/macro/latest-kalshi-labeled-oos-backtest.md",
                    "docs/codex/macro/latest-kalshi-labeled-oos-backtest.csv",
                    "docs/codex/macro/latest-kalshi-oos-falsification-gate.json",
                    "docs/codex/macro/latest-kalshi-oos-falsification-gate.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_probability_breadth_scout_ready",
            (
                "pass"
                if kalshi_probability_breadth_scout_present
                and str(kalshi_probability_breadth_scout_status or "").startswith("probability_breadth_scout_ready")
                else ("warn" if kalshi_probability_breadth_scout_present else "blocked")
            ),
            [
                (
                    "Probability breadth scout is present with status "
                    f"`{kalshi_probability_breadth_scout_status}`, "
                    f"{kalshi_probability_breadth_scout_summary.get('crypto_fast_candidate_count')} fast crypto candidate(s), "
                    f"{kalshi_probability_breadth_scout_summary.get('weather_fast_candidate_count')} fast weather candidate(s), and "
                    f"{kalshi_probability_breadth_scout_summary.get('available_proxy_source_count')} available proxy source(s)."
                    if kalshi_probability_breadth_scout_present
                    else "Probability breadth scout has not been generated yet."
                )
            ],
            [
                path
                for path in [
                    "scripts/kalshi_probability_breadth_scout.py",
                    "tests/test_kalshi_probability_breadth_scout.py",
                    "docs/codex/macro/latest-kalshi-probability-breadth-scout.json",
                    "docs/codex/macro/latest-kalshi-probability-breadth-scout.md",
                    "docs/codex/macro/latest-kalshi-probability-breadth-scout-candidates.csv",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_crypto_proxy_feature_packet_ready",
            (
                "pass"
                if kalshi_crypto_proxy_feature_packet_present
                and kalshi_crypto_proxy_feature_packet_status == "crypto_proxy_feature_packet_ready"
                else ("warn" if kalshi_crypto_proxy_feature_packet_present else "blocked")
            ),
            [
                (
                    "Crypto proxy feature packet is present with status "
                    f"`{kalshi_crypto_proxy_feature_packet_status}`, "
                    f"{kalshi_crypto_proxy_feature_packet_summary.get('feature_row_count')} feature row(s), "
                    f"{kalshi_crypto_proxy_feature_packet_summary.get('feature_ready_count')} feature-ready row(s), and "
                    f"{kalshi_crypto_proxy_feature_packet_summary.get('proxy_available_asset_count')} proxy-covered asset(s)."
                    if kalshi_crypto_proxy_feature_packet_present
                    else "Crypto proxy feature packet has not been generated yet."
                )
            ],
            [
                path
                for path in [
                    "scripts/kalshi_crypto_proxy_feature_packet.py",
                    "tests/test_kalshi_crypto_proxy_feature_packet.py",
                    "docs/codex/macro/latest-kalshi-crypto-proxy-feature-packet.json",
                    "docs/codex/macro/latest-kalshi-crypto-proxy-feature-packet.md",
                    "docs/codex/macro/latest-kalshi-crypto-proxy-feature-packet.csv",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_crypto_proxy_observation_loop_ready",
            (
                "pass"
                if kalshi_crypto_proxy_observation_loop_present
                and kalshi_crypto_proxy_observation_loop_status
                in {
                    "crypto_proxy_observation_loop_label_rows_ready",
                    "crypto_proxy_observation_loop_ready_waiting_settlement",
                    "crypto_proxy_observation_loop_observations_recorded_waiting_settlement",
                }
                else ("warn" if kalshi_crypto_proxy_observation_loop_present else "blocked")
            ),
            [
                (
                    "Crypto proxy observation loop is present with status "
                    f"`{kalshi_crypto_proxy_observation_loop_status}`, "
                    f"{kalshi_crypto_proxy_observation_loop_summary.get('total_observation_row_count')} total observation row(s), "
                    f"{kalshi_crypto_proxy_observation_loop_summary.get('new_observation_row_count')} new row(s), and "
                    f"{kalshi_crypto_proxy_observation_loop_summary.get('label_row_count')} settled label row(s)."
                    if kalshi_crypto_proxy_observation_loop_present
                    else "Crypto proxy observation loop has not been generated yet."
                )
            ],
            [
                path
                for path in [
                    "scripts/kalshi_crypto_proxy_observation_loop.py",
                    "tests/test_kalshi_crypto_proxy_observation_loop.py",
                    "docs/codex/macro/latest-kalshi-crypto-proxy-observation-loop.json",
                    "docs/codex/macro/latest-kalshi-crypto-proxy-observation-loop.md",
                    "docs/codex/macro/latest-kalshi-crypto-proxy-observation-loop.csv",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_crypto_proxy_feature_model_falsification_ready",
            (
                "pass"
                if kalshi_crypto_proxy_feature_model_falsification_present
                and kalshi_crypto_proxy_feature_model_falsification_status
                in {
                    "crypto_proxy_feature_model_falsification_ready_no_research_candidates",
                    "crypto_proxy_feature_model_falsification_ready_with_research_candidates",
                }
                else ("warn" if kalshi_crypto_proxy_feature_model_falsification_present else "blocked")
            ),
            [
                (
                    "Crypto proxy feature-model falsification is present with status "
                    f"`{kalshi_crypto_proxy_feature_model_falsification_status}`, "
                    f"{kalshi_crypto_proxy_feature_model_falsification_summary.get('independent_contract_label_count')} independent labels, "
                    f"{kalshi_crypto_proxy_feature_model_falsification_summary.get('duplicate_label_row_count')} duplicate label rows, and "
                    f"{kalshi_crypto_proxy_feature_model_falsification_summary.get('research_candidate_count')} research candidates."
                    if kalshi_crypto_proxy_feature_model_falsification_present
                    else "Crypto proxy feature-model falsification has not been generated yet."
                )
            ],
            [
                path
                for path in [
                    "scripts/kalshi_crypto_proxy_feature_model_falsification.py",
                    "tests/test_kalshi_crypto_proxy_feature_model_falsification.py",
                    "docs/codex/macro/latest-kalshi-crypto-proxy-feature-model-falsification.json",
                    "docs/codex/macro/latest-kalshi-crypto-proxy-feature-model-falsification.md",
                    "docs/codex/macro/latest-kalshi-crypto-proxy-feature-model-falsification.csv",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "kalshi_crypto_proxy_research_candidate_replay_ready",
            (
                "pass"
                if kalshi_crypto_proxy_research_candidate_replay_present
                and kalshi_crypto_proxy_research_candidate_replay_status
                in {
                    "crypto_proxy_research_candidate_replay_blocked_predeployment_gates",
                    "crypto_proxy_research_candidate_replay_ready_for_paper_probability_overlay",
                    "crypto_proxy_research_candidate_replay_ready_no_positive_cost_adjusted_rows",
                }
                else ("warn" if kalshi_crypto_proxy_research_candidate_replay_present else "blocked")
            ),
            [
                (
                    "Crypto proxy research-candidate replay is present with status "
                    f"`{kalshi_crypto_proxy_research_candidate_replay_status}`, "
                    f"{kalshi_crypto_proxy_research_candidate_replay_summary.get('replay_row_count')} replay rows, "
                    f"{kalshi_crypto_proxy_research_candidate_replay_summary.get('positive_expected_value_row_count')} positive cost-adjusted rows, and "
                    f"{kalshi_crypto_proxy_research_candidate_replay_summary.get('usable_row_count')} usable rows."
                    if kalshi_crypto_proxy_research_candidate_replay_present
                    else "Crypto proxy research-candidate replay has not been generated yet."
                )
            ],
            [
                path
                for path in [
                    "scripts/kalshi_crypto_proxy_research_candidate_replay.py",
                    "tests/test_kalshi_crypto_proxy_research_candidate_replay.py",
                    "docs/codex/macro/latest-kalshi-crypto-proxy-research-candidate-replay.json",
                    "docs/codex/macro/latest-kalshi-crypto-proxy-research-candidate-replay.md",
                    "docs/codex/macro/latest-kalshi-crypto-proxy-research-candidate-replay.csv",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "dirty_tree_risk",
            "warn" if status["git"]["dirty_counts"]["total"] else "pass",
            [f"Dirty paths: {status['git']['dirty_counts']['total']}."],
            [],
        ),
    ]
    metrics = {
        "kalshi_scored_refined": json_brief(refined) if refined is not None else {"missing": True},
        "kalshi_scored": json_brief(scored) if scored is not None else {"missing": True},
        "kalshi_smoke": json_brief(smoke) if smoke is not None else {"missing": True},
        "kalshi_manual_drop_capture": json_brief(kalshi_capture)
        if kalshi_capture is not None
        else {"missing": True},
        "kalshi_manual_drop_capture_present": kalshi_capture_present,
        "kalshi_manual_drop_capture_status": kalshi_capture_status,
        "type2_reference_builder": json_brief(type2_builder)
        if type2_builder is not None
        else {"missing": True},
        "type2_paper_matcher": json_brief(type2_matcher)
        if type2_matcher is not None
        else {"missing": True},
        "type2_reference_preflight": json_brief(type2_preflight)
        if type2_preflight is not None
        else {"missing": True},
        "type2_candidate_disposition": json_brief(type2_disposition)
        if type2_disposition is not None
        else {"missing": True},
        "type2_threshold_sensitivity": json_brief(type2_threshold_sensitivity)
        if type2_threshold_sensitivity is not None
        else {"missing": True},
        "kalshi_ev_ledger": json_brief(kalshi_ev_ledger)
        if kalshi_ev_ledger is not None
        else {"missing": True},
        "kalshi_ev_overlay_preflight": json_brief(kalshi_ev_overlay_preflight)
        if kalshi_ev_overlay_preflight is not None
        else {"missing": True},
        "kalshi_ev_calibration_work_order": json_brief(kalshi_ev_calibration_work_order)
        if kalshi_ev_calibration_work_order is not None
        else {"missing": True},
        "kalshi_ev_contract_mapping_work_order": json_brief(kalshi_ev_contract_mapping_work_order)
        if kalshi_ev_contract_mapping_work_order is not None
        else {"missing": True},
        "kalshi_ev_review_queue": json_brief(kalshi_ev_review_queue)
        if kalshi_ev_review_queue is not None
        else {"missing": True},
        "kalshi_ev_queue_robustness": json_brief(kalshi_ev_queue_robustness)
        if kalshi_ev_queue_robustness is not None
        else {"missing": True},
        "kalshi_universe_scan": json_brief(kalshi_universe_scan)
        if kalshi_universe_scan is not None
        else {"missing": True},
        "kalshi_signal_factory_status": json_brief(kalshi_signal_factory_status)
        if kalshi_signal_factory_status is not None
        else {"missing": True},
        "kalshi_hypothesis_registry": json_brief(kalshi_hypothesis_registry)
        if kalshi_hypothesis_registry is not None
        else {"missing": True},
        "kalshi_falsification_gate": json_brief(kalshi_falsification_gate)
        if kalshi_falsification_gate is not None
        else {"missing": True},
        "kalshi_labeled_observation_builder": json_brief(kalshi_labeled_observation_builder)
        if kalshi_labeled_observation_builder is not None
        else {"missing": True},
        "kalshi_labeled_oos_backtest": json_brief(kalshi_labeled_oos_backtest)
        if kalshi_labeled_oos_backtest is not None
        else {"missing": True},
        "kalshi_probability_breadth_scout": json_brief(kalshi_probability_breadth_scout)
        if kalshi_probability_breadth_scout is not None
        else {"missing": True},
        "kalshi_crypto_proxy_feature_packet": json_brief(kalshi_crypto_proxy_feature_packet)
        if kalshi_crypto_proxy_feature_packet is not None
        else {"missing": True},
        "kalshi_crypto_proxy_observation_loop": json_brief(kalshi_crypto_proxy_observation_loop)
        if kalshi_crypto_proxy_observation_loop is not None
        else {"missing": True},
        "kalshi_crypto_proxy_feature_model_falsification": json_brief(
            kalshi_crypto_proxy_feature_model_falsification
        )
        if kalshi_crypto_proxy_feature_model_falsification is not None
        else {"missing": True},
        "kalshi_crypto_proxy_research_candidate_replay": json_brief(
            kalshi_crypto_proxy_research_candidate_replay
        )
        if kalshi_crypto_proxy_research_candidate_replay is not None
        else {"missing": True},
        "type2_reference_builder_present": type2_builder_present,
        "type2_reference_builder_status": type2_builder_status,
        "type2_paper_matcher_present": type2_matcher_present,
        "type2_paper_matcher_status": type2_matcher_status,
        "type2_reference_preflight_present": type2_preflight_present,
        "type2_reference_preflight_status": type2_preflight_status,
        "type2_candidate_disposition_present": type2_disposition_present,
        "type2_candidate_disposition_status": type2_disposition_status,
        "type2_threshold_sensitivity_present": type2_threshold_sensitivity_present,
        "type2_threshold_sensitivity_status": type2_threshold_sensitivity_status,
        "type2_threshold_sensitivity_summary": type2_threshold_sensitivity_summary
        if isinstance(type2_threshold_sensitivity_summary, dict)
        else {},
        "kalshi_ev_ledger_present": kalshi_ev_ledger_present,
        "kalshi_ev_ledger_status": kalshi_ev_ledger_status,
        "kalshi_ev_ledger_summary": kalshi_ev_ledger_summary,
        "kalshi_ev_overlay_preflight_present": kalshi_ev_overlay_preflight_present,
        "kalshi_ev_overlay_preflight_status": kalshi_ev_overlay_preflight_status,
        "kalshi_ev_overlay_preflight_summary": kalshi_ev_overlay_preflight_summary,
        "kalshi_ev_calibration_work_order_present": kalshi_ev_calibration_work_order_present,
        "kalshi_ev_calibration_work_order_status": kalshi_ev_calibration_work_order_status,
        "kalshi_ev_calibration_work_order_summary": kalshi_ev_calibration_work_order_summary,
        "kalshi_ev_contract_mapping_work_order_present": kalshi_ev_contract_mapping_work_order_present,
        "kalshi_ev_contract_mapping_work_order_status": kalshi_ev_contract_mapping_work_order_status,
        "kalshi_ev_contract_mapping_work_order_summary": kalshi_ev_contract_mapping_work_order_summary,
        "kalshi_ev_local_contract_evidence_scout_present": kalshi_ev_local_contract_evidence_scout_present,
        "kalshi_ev_local_contract_evidence_scout_status": kalshi_ev_local_contract_evidence_scout_status,
        "kalshi_ev_local_contract_evidence_scout_summary": kalshi_ev_local_contract_evidence_scout_summary,
        "kalshi_ev_nfl_overlay_assembler_present": kalshi_ev_nfl_overlay_assembler_present,
        "kalshi_ev_nfl_overlay_assembler_status": kalshi_ev_nfl_overlay_assembler_status,
        "kalshi_ev_nfl_overlay_assembler_summary": kalshi_ev_nfl_overlay_assembler_summary,
        "kalshi_ev_review_queue_present": kalshi_ev_review_queue_present,
        "kalshi_ev_review_queue_status": kalshi_ev_review_queue_status,
        "kalshi_ev_review_queue_summary": kalshi_ev_review_queue_summary,
        "kalshi_ev_queue_robustness_present": kalshi_ev_queue_robustness_present,
        "kalshi_ev_queue_robustness_status": kalshi_ev_queue_robustness_status,
        "kalshi_ev_queue_robustness_summary": kalshi_ev_queue_robustness_summary,
        "kalshi_universe_scan_present": kalshi_universe_scan_present,
        "kalshi_universe_scan_status": kalshi_universe_scan_status,
        "kalshi_universe_scan_summary": kalshi_universe_scan_summary,
        "kalshi_signal_factory_status_present": kalshi_signal_factory_status_present,
        "kalshi_signal_factory_evidence_status": kalshi_signal_factory_evidence_status,
        "kalshi_signal_factory_summary": kalshi_signal_factory_summary,
        "kalshi_hypothesis_registry_present": kalshi_hypothesis_registry_present,
        "kalshi_hypothesis_registry_status": kalshi_hypothesis_registry_status,
        "kalshi_hypothesis_registry_summary": kalshi_hypothesis_registry_summary,
        "kalshi_falsification_gate_present": kalshi_falsification_gate_present,
        "kalshi_falsification_gate_status": kalshi_falsification_gate_status,
        "kalshi_labeled_observation_builder_present": kalshi_labeled_observation_builder_present,
        "kalshi_labeled_observation_builder_status": kalshi_labeled_observation_builder_status,
        "kalshi_labeled_observation_builder_summary": kalshi_labeled_observation_builder_summary,
        "kalshi_labeled_oos_backtest_present": kalshi_labeled_oos_backtest_present,
        "kalshi_labeled_oos_backtest_status": kalshi_labeled_oos_backtest_status,
        "kalshi_labeled_oos_backtest_summary": kalshi_labeled_oos_backtest_summary,
        "kalshi_probability_breadth_scout_present": kalshi_probability_breadth_scout_present,
        "kalshi_probability_breadth_scout_status": kalshi_probability_breadth_scout_status,
        "kalshi_probability_breadth_scout_summary": kalshi_probability_breadth_scout_summary,
        "kalshi_crypto_proxy_feature_packet_present": kalshi_crypto_proxy_feature_packet_present,
        "kalshi_crypto_proxy_feature_packet_status": kalshi_crypto_proxy_feature_packet_status,
        "kalshi_crypto_proxy_feature_packet_summary": kalshi_crypto_proxy_feature_packet_summary,
        "kalshi_crypto_proxy_observation_loop_present": kalshi_crypto_proxy_observation_loop_present,
        "kalshi_crypto_proxy_observation_loop_status": kalshi_crypto_proxy_observation_loop_status,
        "kalshi_crypto_proxy_observation_loop_summary": kalshi_crypto_proxy_observation_loop_summary,
        "kalshi_crypto_proxy_feature_model_falsification_present": (
            kalshi_crypto_proxy_feature_model_falsification_present
        ),
        "kalshi_crypto_proxy_feature_model_falsification_status": (
            kalshi_crypto_proxy_feature_model_falsification_status
        ),
        "kalshi_crypto_proxy_feature_model_falsification_summary": (
            kalshi_crypto_proxy_feature_model_falsification_summary
        ),
        "kalshi_crypto_proxy_research_candidate_replay_present": (
            kalshi_crypto_proxy_research_candidate_replay_present
        ),
        "kalshi_crypto_proxy_research_candidate_replay_status": (
            kalshi_crypto_proxy_research_candidate_replay_status
        ),
        "kalshi_crypto_proxy_research_candidate_replay_summary": (
            kalshi_crypto_proxy_research_candidate_replay_summary
        ),
        "timing_safe_review_candidates": kept_disposition_candidates,
        "watch_only_candidates": watch_only_disposition_candidates,
        "strategy_type2_loaded": type2_loaded,
        "review_ready_mentions": strategy_text.count("REVIEW_READY")
        + read_text(root, "data/kalshi_run_log_2026-06-16.txt").count("REVIEW_READY"),
    }
    if (
        kalshi_signal_factory_status_present
        and kalshi_signal_factory_evidence_status
        and int(kalshi_signal_factory_summary.get("universe_candidate_count") or 0) > 0
    ):
        predmarket_evidence_status = str(kalshi_signal_factory_evidence_status)
    elif (
        kalshi_universe_scan_present
        and kalshi_universe_scan_status
        and int(kalshi_universe_scan_summary.get("candidate_count") or 0) > 0
    ):
        predmarket_evidence_status = str(kalshi_universe_scan_status)
    elif (
        kalshi_ev_queue_robustness_present
        and kalshi_ev_queue_robustness_status
        and int(kalshi_ev_queue_robustness_summary.get("queue_row_count") or 0) > 0
    ):
        predmarket_evidence_status = str(kalshi_ev_queue_robustness_status)
    elif (
        kalshi_ev_review_queue_present
        and kalshi_ev_review_queue_status
        and int(kalshi_ev_review_queue_summary.get("queued_row_count") or 0) > 0
    ):
        predmarket_evidence_status = str(kalshi_ev_review_queue_status)
    elif (
        kalshi_ev_ledger_present
        and int(kalshi_ev_ledger_summary.get("usable_row_count") or 0) > 0
    ):
        predmarket_evidence_status = "kalshi_ev_ledger_ready_with_usable_contract_edges"
    elif (
        kalshi_ev_local_contract_evidence_scout_present
        and kalshi_ev_local_contract_evidence_scout_status
    ):
        predmarket_evidence_status = f"kalshi_ev_{kalshi_ev_local_contract_evidence_scout_status}"
    elif (
        kalshi_ev_contract_mapping_work_order_present
        and kalshi_ev_contract_mapping_work_order_status == "contract_mapping_work_order_ready"
    ):
        predmarket_evidence_status = "kalshi_ev_contract_mapping_work_order_ready"
    elif (
        kalshi_ev_calibration_work_order_present
        and kalshi_ev_calibration_work_order_status in {
            "calibration_work_order_ready",
            "calibration_work_order_ready_source_gated",
        }
    ):
        predmarket_evidence_status = f"kalshi_ev_{kalshi_ev_calibration_work_order_status}"
    elif kalshi_ev_overlay_preflight_present and kalshi_ev_overlay_preflight_status:
        predmarket_evidence_status = f"kalshi_ev_{kalshi_ev_overlay_preflight_status}"
    elif kalshi_ev_ledger_present and kalshi_ev_ledger_status:
        predmarket_evidence_status = f"kalshi_ev_{kalshi_ev_ledger_status}"
    elif type2_disposition_status == "candidate_disposition_all_passes_downgraded":
        predmarket_evidence_status = "kalshi_type2_candidate_disposition_all_passes_downgraded"
    elif type2_disposition_status == "candidate_disposition_watch_only":
        predmarket_evidence_status = "kalshi_type2_candidate_disposition_watch_only"
    elif type2_preflight_present and type2_preflight_status == "blocked_missing_sportsbook_reference":
        predmarket_evidence_status = "kalshi_type2_reference_preflight_blocked_missing_sportsbook_reference"
    elif type2_preflight_present and type2_preflight_status == "reference_ready":
        predmarket_evidence_status = "kalshi_type2_reference_preflight_ready"
    elif type2_matcher_present and type2_matcher_status == "blocked_missing_sportsbook_reference":
        predmarket_evidence_status = "kalshi_type2_matcher_blocked_missing_sportsbook_reference"
    elif type2_matcher_present and type2_matcher_status == "review_candidates_present":
        predmarket_evidence_status = "kalshi_type2_matcher_review_candidates_present"
    elif type2_matcher_present:
        predmarket_evidence_status = "kalshi_type2_matcher_watch_only"
    else:
        predmarket_evidence_status = "kalshi_command_center_research_only"
    evidence = {
        "status": predmarket_evidence_status,
        "latest_artifacts": artifacts,
        "hashes": hashes,
        "blocker_count": sum(1 for gate in gates if gate["status"] in {"blocked", "fail"}),
        "metrics": metrics,
    }
    return finish_status(status, evidence, gates)


def mlb_status(root: Path) -> dict[str, Any]:
    status = base_status("mlb-platform", root)
    artifact_paths = [
        "README.md",
        "AGENTS.md",
        "docs/codex/current-state.md",
        "docs/codex/tranches/2026-06-16-type2-edge-contract.md",
        "docs/codex/tranches/2026-06-16-kalshi-exchange-adapter.md",
        "docs/codex/artifacts/2026-06-16-kalshi-exchange-probabilities.json",
        "docs/codex/artifacts/2026-06-20-type2-sportsbook-bridge-preflight.json",
        "docs/codex/artifacts/2026-06-20-mlb-sportsbook-local-inventory.json",
        "docs/codex/artifacts/2026-06-20-type2-sportsbook-odds.jsonl",
        "docs/codex/artifacts/2026-06-20-kalshi-exchange-probabilities.json",
        "docs/codex/artifacts/2026-06-20-type2-audit-bundle-current/summary.json",
        "docs/codex/artifacts/2026-06-20-type2-audit-bundle-current/type2-audit.json",
        "docs/codex/artifacts/2026-06-20-type2-audit-bundle-current/type2-candidates.json",
        "docs/codex/artifacts/2026-06-20-type2-audit-bundle-current/type2-evidence.json",
        "docs/codex/artifacts/2026-06-20-type2-audit-bundle-current/review-packet.json",
        "docs/codex/artifacts/2026-06-20-type2-audit-bundle-current/review-packet.md",
        "docs/codex/artifacts/2026-06-20-type2-audit-bundle-current/temporal-mismatch-disposition.json",
        "docs/codex/artifacts/2026-06-20-type2-audit-bundle-current/temporal-mismatch-disposition.md",
        "docs/codex/artifacts/2026-06-20-type2-audit-bundle-current/pregame-pairing-readiness.json",
        "docs/codex/artifacts/2026-06-20-type2-audit-bundle-current/pregame-pairing-readiness.md",
        "docs/codex/artifacts/type2-pregame-drop-intake-latest/pregame-drop-intake-status.json",
        "docs/codex/artifacts/type2-pregame-drop-intake-latest/pregame-drop-intake-status.md",
        *latest_matching(
            root,
            [
                "docs/codex/artifacts/*/pregame-drop-intake-status.json",
                "docs/codex/artifacts/*/pregame-drop-intake-status.md",
                "docs/codex/artifacts/*/pregame-pairing-readiness.json",
                "docs/codex/artifacts/*/pregame-pairing-readiness.md",
                "docs/codex/artifacts/*/summary.json",
                "docs/codex/artifacts/*/review-packet.json",
                "docs/codex/artifacts/*/review-packet.md",
                "docs/codex/artifacts/*/review-adjudication.json",
                "docs/codex/artifacts/*/review-adjudication.md",
                "docs/codex/artifacts/*/type2-repeatability-ledger.json",
                "docs/codex/artifacts/*/type2-repeatability-ledger.md",
                "docs/codex/artifacts/*/type2-repeatability-research-review.json",
                "docs/codex/artifacts/*/type2-repeatability-research-review.md",
                "docs/codex/artifacts/*/type2-threshold-policy-review.json",
                "docs/codex/artifacts/*/type2-threshold-policy-review.md",
                "docs/codex/artifacts/*/type2-settled-outcome-validation.json",
                "docs/codex/artifacts/*/type2-settled-outcome-validation.md",
                "docs/codex/artifacts/*/type2-closing-proxy-validation.json",
                "docs/codex/artifacts/*/type2-closing-proxy-validation.md",
                "docs/codex/artifacts/*/type2-public-closing-evidence-scout.json",
                "docs/codex/artifacts/*/type2-public-closing-evidence-scout.md",
                "docs/codex/artifacts/*/type2-betexplorer-public-closing-import.json",
                "docs/codex/artifacts/*/type2-betexplorer-public-closing-import.md",
                "docs/codex/artifacts/*/type2-betexplorer-full-slate-public-import.json",
                "docs/codex/artifacts/*/type2-betexplorer-full-slate-public-import.md",
                "docs/codex/artifacts/*/type2-betexplorer-moneyline-closing-comparison.json",
                "docs/codex/artifacts/*/type2-betexplorer-moneyline-closing-comparison.md",
                "docs/codex/artifacts/*/type2-betexplorer-market-closing-comparison.json",
                "docs/codex/artifacts/*/type2-betexplorer-market-closing-comparison.md",
                "docs/codex/artifacts/*/temporal-mismatch-disposition.json",
                "docs/codex/artifacts/*/temporal-mismatch-disposition.md",
            ],
            limit=20,
        ),
        "docs/codex/manual-drops/mlb-type2-pregame-pair-contract.md",
        "COMPLETION_REPORT_2026-06-20_MLB_TYPE2_SPORTSBOOK_BRIDGE_PREFLIGHT_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-20_MLB_TYPE2_ZERO_SPEND_SPORTSBOOK_UNLOCK_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-20_MLB_TYPE2_CURRENT_AUDIT_REVIEW_HARDENING_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-20_MLB_TYPE2_TEMPORAL_MISMATCH_DISPOSITION_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-20_MLB_TYPE2_PREGAME_PAIRING_READINESS_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-21_MLB_TYPE2_PREGAME_DROP_INTAKE_RUNNER_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-28_MLB_PREGAME_DROP_BLOCKED_INPUT_ROUTER_HARDENING_FULFILLED.md",
        "NEXT_DIRECTIVE_2026-06-29_MLB_TYPE2_CURRENT_SAME_SLATE_CAPTURE_AND_INTAKE.md",
        "COMPLETION_REPORT_2026-06-29_MLB_TYPE2_CURRENT_SAME_SLATE_CAPTURE_AND_INTAKE_FULFILLED.md",
        "NEXT_DIRECTIVE_2026-06-29_MLB_TYPE2_REVIEW_PACKET_ADJUDICATION.md",
        "COMPLETION_REPORT_2026-06-29_MLB_TYPE2_REVIEW_PACKET_ADJUDICATION_FULFILLED.md",
        "NEXT_DIRECTIVE_2026-06-29_MLB_TYPE2_REPEATABILITY_OS_AND_SECOND_CAPTURE.md",
        "COMPLETION_REPORT_2026-06-29_MLB_TYPE2_REPEATABILITY_OS_AND_SECOND_CAPTURE_FULFILLED.md",
        "NEXT_DIRECTIVE_2026-06-30_MLB_TYPE2_THRESHOLD_POLICY_REVIEW.md",
        "COMPLETION_REPORT_2026-06-30_MLB_TYPE2_THRESHOLD_POLICY_REVIEW_FULFILLED.md",
        "NEXT_DIRECTIVE_2026-06-30_MLB_TYPE2_SETTLED_OUTCOME_VALIDATION.md",
        "COMPLETION_REPORT_2026-06-30_MLB_TYPE2_SETTLED_OUTCOME_VALIDATION_FULFILLED.md",
        *latest_matching(root, ["COMPLETION_REPORT_2026-06-30*.md"], limit=5),
        "WORKER_DIRECTIVE_2026-06-20_MLB_TYPE2_ZERO_SPEND_SPORTSBOOK_UNLOCK.md",
        "docs/backtest-data-contract.md",
        "docs/historical-data.md",
        "docs/codex/tranches/2026-06-28-mlb-pregame-drop-blocked-input-router-hardening.md",
        "NEXT_DIRECTIVE_2026-06-28_MLB_PREGAME_DROP_BLOCKED_INPUT_ROUTER_HARDENING.md",
        *latest_matching(root, ["NEXT_DIRECTIVE_2026-06-15*.md"], limit=5),
        *latest_matching(root, ["NEXT_DIRECTIVE_2026-06-20*.md"], limit=5),
        *latest_matching(root, ["NEXT_DIRECTIVE_2026-06-21*.md"], limit=5),
        *latest_matching(root, ["NEXT_DIRECTIVE_2026-06-29*.md"], limit=5),
        *latest_matching(root, ["NEXT_DIRECTIVE_2026-06-30*.md"], limit=5),
    ]
    artifacts, hashes = artifact_pack(root, artifact_paths)
    capability_paths = [
        "src/mlb_platform/market/implied_prob.py",
        "src/mlb_platform/market/edge.py",
        "src/mlb_platform/market/type2_edge.py",
        "src/mlb_platform/market/kelly.py",
        "src/mlb_platform/market/clv.py",
        "src/mlb_platform/market/odds_api.py",
        "src/mlb_platform/backtest/type2_candidates.py",
        "src/mlb_platform/backtest/kalshi_exchange.py",
        "src/mlb_platform/backtest/sportsbook_bridge.py",
        "src/mlb_platform/backtest/odds_api_raw_bridge.py",
        "src/mlb_platform/ingestion/odds_api_current_capture.py",
        "src/mlb_platform/reports/type2_audit.py",
        "src/mlb_platform/reports/type2_temporal_disposition.py",
        "src/mlb_platform/reports/type2_pregame_pairing.py",
        "src/mlb_platform/reports/type2_pregame_intake.py",
        "src/mlb_platform/reports/type2_review_adjudication.py",
        "src/mlb_platform/reports/type2_repeatability_ledger.py",
        "src/mlb_platform/reports/type2_repeatability_research_review.py",
        "src/mlb_platform/reports/type2_threshold_policy_review.py",
        "src/mlb_platform/reports/type2_settled_outcome_validation.py",
        "src/mlb_platform/reports/type2_closing_proxy_validation.py",
        "src/mlb_platform/cli/type2_audit.py",
        "src/mlb_platform/cli/type2_candidates.py",
        "src/mlb_platform/cli/type2_evidence.py",
        "src/mlb_platform/cli/type2_kalshi_exchange.py",
        "src/mlb_platform/cli/type2_sportsbook_bridge.py",
        "src/mlb_platform/cli/type2_odds_api_raw_bridge.py",
        "src/mlb_platform/cli/type2_odds_api_current_capture.py",
        "scripts/generate_type2_review_packet.py",
        "scripts/generate_type2_temporal_disposition.py",
        "scripts/generate_type2_pregame_pairing_readiness.py",
        "scripts/generate_type2_review_adjudication.py",
        "scripts/generate_type2_repeatability_ledger.py",
        "scripts/generate_type2_repeatability_research_review.py",
        "scripts/generate_type2_threshold_policy_review.py",
        "scripts/generate_type2_settled_outcome_validation.py",
        "scripts/generate_type2_closing_proxy_validation.py",
        "scripts/run_type2_pregame_drop_intake.py",
        "src/mlb_platform/backtest/historical_loader.py",
        "src/mlb_platform/backtest/market_model.py",
        "src/mlb_platform/backtest/settlement.py",
        "src/mlb_platform/backtest/pipeline.py",
        "src/mlb_platform/cli/source_preflight.py",
        "src/mlb_platform/cli/ops_check.py",
        "tests/test_trap_stats.py",
        "tests/test_backtest/test_kalshi_exchange.py",
        "tests/test_cli/test_type2_kalshi_exchange.py",
        "tests/test_backtest/test_sportsbook_bridge.py",
        "tests/test_cli/test_type2_sportsbook_bridge.py",
        "tests/test_backtest/test_odds_api_raw_bridge.py",
        "tests/test_cli/test_type2_odds_api_raw_bridge.py",
        "tests/test_ingestion/test_odds_api_current_capture.py",
        "tests/test_cli/test_type2_odds_api_current_capture.py",
        "tests/test_backtest/test_type2_candidates.py",
        "tests/test_market/test_type2_edge.py",
        "tests/test_cli/test_type2_evidence.py",
        "tests/test_reports/test_type2_audit.py",
        "tests/test_reports/test_type2_temporal_disposition.py",
        "tests/test_reports/test_type2_pregame_pairing.py",
        "tests/test_reports/test_type2_pregame_intake.py",
        "tests/test_reports/test_type2_review_adjudication.py",
        "tests/test_reports/test_type2_repeatability_ledger.py",
        "tests/test_reports/test_type2_repeatability_research_review.py",
        "tests/test_reports/test_type2_threshold_policy_review.py",
        "tests/test_reports/test_type2_settled_outcome_validation.py",
        "tests/test_reports/test_type2_closing_proxy_validation.py",
        "src/mlb_platform/reports/type2_public_closing_evidence_scout.py",
        "src/mlb_platform/reports/type2_betexplorer_public_closing_import.py",
        "src/mlb_platform/reports/type2_betexplorer_moneyline_closing_comparison.py",
        "src/mlb_platform/reports/type2_betexplorer_market_closing_comparison.py",
        "scripts/generate_type2_public_closing_evidence_scout.py",
        "scripts/generate_type2_betexplorer_public_closing_import.py",
        "scripts/generate_type2_betexplorer_full_slate_public_import.py",
        "scripts/generate_type2_betexplorer_moneyline_closing_comparison.py",
        "scripts/generate_type2_betexplorer_market_closing_comparison.py",
        "tests/test_reports/test_type2_public_closing_evidence_scout.py",
        "tests/test_reports/test_type2_betexplorer_public_closing_import.py",
        "tests/test_reports/test_type2_betexplorer_moneyline_closing_comparison.py",
        "tests/test_reports/test_type2_betexplorer_market_closing_comparison.py",
    ]
    capabilities = exists_map(root, capability_paths)
    current_kalshi_exchange_artifact = read_json(root, "docs/codex/artifacts/2026-06-20-kalshi-exchange-probabilities.json")
    legacy_kalshi_exchange_artifact = read_json(root, "docs/codex/artifacts/2026-06-16-kalshi-exchange-probabilities.json")
    kalshi_exchange_artifact = current_kalshi_exchange_artifact or legacy_kalshi_exchange_artifact
    sportsbook_preflight = read_json(root, "docs/codex/artifacts/2026-06-20-type2-sportsbook-bridge-preflight.json")
    sportsbook_inventory = read_json(root, "docs/codex/artifacts/2026-06-20-mlb-sportsbook-local-inventory.json")
    latest_summary_rel = _latest_artifact_rel(root, "docs/codex/artifacts/*/summary.json")
    latest_review_packet_rel = _latest_artifact_rel(root, "docs/codex/artifacts/*/review-packet.json")
    latest_review_adjudication_rel = _latest_artifact_rel(root, "docs/codex/artifacts/*/review-adjudication.json")
    latest_repeatability_ledger_rel = _latest_artifact_rel(root, "docs/codex/artifacts/*/type2-repeatability-ledger.json")
    latest_repeatability_research_review_rel = _latest_artifact_rel(
        root,
        "docs/codex/artifacts/*/type2-repeatability-research-review.json",
    )
    latest_threshold_policy_review_rel = _latest_artifact_rel(
        root,
        "docs/codex/artifacts/*/type2-threshold-policy-review.json",
    )
    latest_settled_validation_rel = _latest_artifact_rel(
        root,
        "docs/codex/artifacts/*/type2-settled-outcome-validation.json",
    )
    latest_closing_proxy_validation_rel = _latest_artifact_rel(
        root,
        "docs/codex/artifacts/*/type2-closing-proxy-validation.json",
    )
    latest_public_closing_scout_rel = _latest_artifact_rel(
        root,
        "docs/codex/artifacts/*/type2-public-closing-evidence-scout.json",
    )
    latest_betexplorer_public_import_rel = _latest_artifact_rel(
        root,
        "docs/codex/artifacts/*/type2-betexplorer-public-closing-import.json",
    )
    latest_betexplorer_full_slate_import_rel = _latest_artifact_rel(
        root,
        "docs/codex/artifacts/*/type2-betexplorer-full-slate-public-import.json",
    )
    latest_betexplorer_moneyline_comparison_rel = _latest_artifact_rel(
        root,
        "docs/codex/artifacts/*/type2-betexplorer-moneyline-closing-comparison.json",
    )
    latest_betexplorer_market_comparison_rel = _latest_artifact_rel(
        root,
        "docs/codex/artifacts/*/type2-betexplorer-market-closing-comparison.json",
    )
    latest_temporal_rel = _latest_artifact_rel(root, "docs/codex/artifacts/*/temporal-mismatch-disposition.json")
    latest_pregame_readiness_rel = _latest_artifact_rel(root, "docs/codex/artifacts/*/pregame-pairing-readiness.json")
    latest_pregame_intake_rel = _latest_artifact_rel(root, "docs/codex/artifacts/*/pregame-drop-intake-status.json")
    current_audit_summary = read_json(
        root,
        latest_summary_rel or "docs/codex/artifacts/2026-06-20-type2-audit-bundle-current/summary.json",
    )
    review_packet = read_json(
        root,
        latest_review_packet_rel or "docs/codex/artifacts/2026-06-20-type2-audit-bundle-current/review-packet.json",
    )
    review_adjudication = read_json(root, latest_review_adjudication_rel) if latest_review_adjudication_rel else None
    repeatability_ledger = read_json(root, latest_repeatability_ledger_rel) if latest_repeatability_ledger_rel else None
    repeatability_research_review = (
        read_json(root, latest_repeatability_research_review_rel)
        if latest_repeatability_research_review_rel
        else None
    )
    threshold_policy_review = (
        read_json(root, latest_threshold_policy_review_rel)
        if latest_threshold_policy_review_rel
        else None
    )
    settled_validation = (
        read_json(root, latest_settled_validation_rel)
        if latest_settled_validation_rel
        else None
    )
    closing_proxy_validation = (
        read_json(root, latest_closing_proxy_validation_rel)
        if latest_closing_proxy_validation_rel
        else None
    )
    public_closing_scout = (
        read_json(root, latest_public_closing_scout_rel)
        if latest_public_closing_scout_rel
        else None
    )
    betexplorer_public_import = (
        read_json(root, latest_betexplorer_public_import_rel)
        if latest_betexplorer_public_import_rel
        else None
    )
    betexplorer_full_slate_import = (
        read_json(root, latest_betexplorer_full_slate_import_rel)
        if latest_betexplorer_full_slate_import_rel
        else None
    )
    betexplorer_moneyline_comparison = (
        read_json(root, latest_betexplorer_moneyline_comparison_rel)
        if latest_betexplorer_moneyline_comparison_rel
        else None
    )
    betexplorer_market_comparison = (
        read_json(root, latest_betexplorer_market_comparison_rel)
        if latest_betexplorer_market_comparison_rel
        else None
    )
    temporal_disposition = read_json(
        root,
        latest_temporal_rel or "docs/codex/artifacts/2026-06-20-type2-audit-bundle-current/temporal-mismatch-disposition.json",
    )
    pregame_readiness = read_json(
        root,
        latest_pregame_readiness_rel or "docs/codex/artifacts/2026-06-20-type2-audit-bundle-current/pregame-pairing-readiness.json",
    )
    pregame_intake = read_json(
        root,
        latest_pregame_intake_rel or "docs/codex/artifacts/type2-pregame-drop-intake-latest/pregame-drop-intake-status.json",
    )
    offline_bridge_report = read_text(
        root,
        "COMPLETION_REPORT_2026-06-20_MLB_TYPE2_ZERO_SPEND_SPORTSBOOK_UNLOCK_FULFILLED.md",
    )
    kalshi_exchange_count = (
        int(kalshi_exchange_artifact.get("exchange_quote_count", 0))
        if isinstance(kalshi_exchange_artifact, dict)
        else 0
    )
    inventory_conclusion = (
        sportsbook_inventory.get("conclusion", {})
        if isinstance(sportsbook_inventory, dict)
        else {}
    )
    local_mlb_sportsbook_rows = (
        int(inventory_conclusion.get("local_baseball_mlb_sportsbook_odds_rows_found", -1))
        if isinstance(inventory_conclusion, dict)
        else -1
    )
    core_ready = all(
        capabilities[path]
        for path in [
            "src/mlb_platform/market/implied_prob.py",
            "src/mlb_platform/market/edge.py",
            "src/mlb_platform/market/type2_edge.py",
            "src/mlb_platform/backtest/type2_candidates.py",
            "src/mlb_platform/reports/type2_audit.py",
            "src/mlb_platform/cli/type2_audit.py",
            "src/mlb_platform/cli/type2_candidates.py",
            "src/mlb_platform/cli/type2_evidence.py",
            "src/mlb_platform/market/clv.py",
            "src/mlb_platform/backtest/market_model.py",
            "src/mlb_platform/cli/source_preflight.py",
        ]
    )
    kalshi_exchange_ready = (
        capabilities.get("src/mlb_platform/backtest/kalshi_exchange.py", False)
        and capabilities.get("src/mlb_platform/cli/type2_kalshi_exchange.py", False)
        and kalshi_exchange_count > 0
    )
    offline_raw_bridge_ready = (
        capabilities.get("src/mlb_platform/backtest/odds_api_raw_bridge.py", False)
        and capabilities.get("src/mlb_platform/cli/type2_odds_api_raw_bridge.py", False)
        and capabilities.get("tests/test_backtest/test_odds_api_raw_bridge.py", False)
        and capabilities.get("tests/test_cli/test_type2_odds_api_raw_bridge.py", False)
        and isinstance(sportsbook_inventory, dict)
        and "offline/manual-drop importer" in offline_bridge_report
    )
    real_sportsbook_jsonl = "docs/codex/artifacts/2026-06-20-type2-sportsbook-odds.jsonl"
    real_sportsbook_jsonl_present = (root / real_sportsbook_jsonl).is_file()
    current_audit_ready = (
        isinstance(current_audit_summary, dict)
        and current_audit_summary.get("ready") is True
        and isinstance(current_audit_summary.get("counts"), dict)
        and int(current_audit_summary["counts"].get("review_ready_count", 0)) > 0
    )
    review_packet_summary = review_packet.get("summary_counts", {}) if isinstance(review_packet, dict) else {}
    review_packet_suspects = (
        review_packet.get("suspicious_rows_to_downgrade_or_manually_check", {})
        if isinstance(review_packet, dict)
        else {}
    )
    temporal_mismatch_totals = (
        len(review_packet_suspects.get("likely_live_game_temporal_mismatch_totals", []))
        if isinstance(review_packet_suspects, dict)
        else 0
    )
    temporal_mismatch_run_lines = (
        len(review_packet_suspects.get("likely_live_game_temporal_mismatch_run_lines", []))
        if isinstance(review_packet_suspects, dict)
        else 0
    )
    temporal_mismatch_count = temporal_mismatch_totals + temporal_mismatch_run_lines
    review_packet_missing_spread = (
        len(review_packet.get("review_ready_rows_with_missing_spread", []))
        if isinstance(review_packet, dict)
        else 0
    )
    review_packet_wide_spread = (
        len(review_packet.get("review_ready_rows_with_wide_spread", []))
        if isinstance(review_packet, dict)
        else 0
    )
    review_packet_ready = (
        isinstance(review_packet, dict)
        and review_packet.get("ready") is True
        and review_packet.get("review_only") is True
        and review_packet.get("execution_enabled") is False
        and int(review_packet_summary.get("review_ready_count", 0)) > 0
        and review_packet_missing_spread == 0
        and review_packet_wide_spread == 0
    )
    temporal_summary = temporal_disposition.get("summary", {}) if isinstance(temporal_disposition, dict) else {}
    temporal_downgraded_count = int(temporal_summary.get("downgraded_temporal_mismatch_count", 0) or 0)
    temporal_manual_count = int(temporal_summary.get("needs_manual_verification_count", 0) or 0)
    temporal_unclassified_count = int(temporal_summary.get("unclassified_count", 0) or 0)
    temporal_disposition_ready = (
        isinstance(temporal_disposition, dict)
        and temporal_disposition.get("review_only") is True
        and temporal_disposition.get("execution_enabled") is False
        and temporal_disposition.get("provider_api_calls") is False
        and temporal_disposition.get("database_writes") is False
        and int(temporal_summary.get("suspicious_row_count", 0) or 0) == temporal_mismatch_count
        and temporal_unclassified_count == 0
    )
    pregame_summary = pregame_readiness.get("summary", {}) if isinstance(pregame_readiness, dict) else {}
    pregame_failing_gates = (
        list(pregame_summary.get("failing_gates", []))
        if isinstance(pregame_summary.get("failing_gates", []), list)
        else []
    )
    pregame_readiness_present = (
        isinstance(pregame_readiness, dict)
        and pregame_readiness.get("review_only") is True
        and pregame_readiness.get("execution_enabled") is False
        and pregame_readiness.get("provider_api_calls") is False
        and pregame_readiness.get("database_writes") is False
        and "ready" in pregame_readiness
        and isinstance(pregame_readiness.get("gates"), list)
    )
    pregame_ready = bool(pregame_readiness.get("ready")) if isinstance(pregame_readiness, dict) else False
    pregame_intake_present = (
        isinstance(pregame_intake, dict)
        and pregame_intake.get("review_only") is True
        and pregame_intake.get("execution_enabled") is False
        and pregame_intake.get("provider_api_calls") is False
        and pregame_intake.get("database_writes") is False
        and pregame_intake.get("raw_payload_copied_into_repo") is False
        and "status" in pregame_intake
    )
    pregame_intake_status = pregame_intake.get("status") if isinstance(pregame_intake, dict) else None
    pregame_intake_ready = bool(pregame_intake.get("ready")) if isinstance(pregame_intake, dict) else False
    review_adjudication_summary = (
        review_adjudication.get("summary", {}) if isinstance(review_adjudication, dict) else {}
    )
    review_adjudication_gate_counts = (
        review_adjudication_summary.get("gate_status_counts", {})
        if isinstance(review_adjudication_summary, dict)
        else {}
    )
    review_adjudication_ready = (
        isinstance(review_adjudication, dict)
        and review_adjudication.get("status") == "review_adjudication_ready"
        and review_adjudication.get("ready_for_human_review") is True
        and review_adjudication.get("review_only") is True
        and review_adjudication.get("execution_enabled") is False
        and review_adjudication.get("provider_api_calls") is False
        and review_adjudication.get("database_writes") is False
        and int(review_adjudication_gate_counts.get("fail", 0) or 0) == 0
    )
    repeatability_summary = (
        repeatability_ledger.get("summary", {}) if isinstance(repeatability_ledger, dict) else {}
    )
    repeatability_status = repeatability_ledger.get("status") if isinstance(repeatability_ledger, dict) else None
    repeatability_safe = (
        isinstance(repeatability_ledger, dict)
        and repeatability_ledger.get("review_only") is True
        and repeatability_ledger.get("execution_enabled") is False
        and repeatability_ledger.get("provider_api_calls") is False
        and repeatability_ledger.get("database_writes") is False
    )
    repeatability_observed = repeatability_safe and repeatability_status == "repeatability_observed_two_clean_packets"
    repeatability_insufficient = repeatability_safe and repeatability_status == "repeatability_insufficient_one_clean_packet"
    repeatability_ready_for_review = repeatability_safe and repeatability_status == "repeatability_ready_for_research_review"
    repeatability_blocked_no_clean_packets = (
        repeatability_safe and repeatability_status == "repeatability_blocked_no_clean_packets"
    )
    repeatability_no_signal_clean_packets = (
        repeatability_safe and repeatability_status == "repeatability_no_signal_clean_packets"
    )
    repeatability_research_review_summary = (
        repeatability_research_review.get("summary", {})
        if isinstance(repeatability_research_review, dict)
        else {}
    )
    repeatability_research_review_status = (
        repeatability_research_review.get("status")
        if isinstance(repeatability_research_review, dict)
        else None
    )
    repeatability_research_review_ready = (
        isinstance(repeatability_research_review, dict)
        and repeatability_research_review_status == "repeatability_research_review_ready"
        and repeatability_research_review.get("review_only") is True
        and repeatability_research_review.get("execution_enabled") is False
        and repeatability_research_review.get("provider_api_calls") is False
        and repeatability_research_review.get("database_writes") is False
    )
    threshold_policy_summary = (
        threshold_policy_review.get("summary", {})
        if isinstance(threshold_policy_review, dict)
        else {}
    )
    threshold_policy_status = (
        threshold_policy_review.get("status")
        if isinstance(threshold_policy_review, dict)
        else None
    )
    threshold_policy_safe = (
        isinstance(threshold_policy_review, dict)
        and threshold_policy_review.get("review_only") is True
        and threshold_policy_review.get("execution_enabled") is False
        and threshold_policy_review.get("provider_api_calls") is False
        and threshold_policy_review.get("database_writes") is False
        and threshold_policy_review.get("market_execution") is False
        and threshold_policy_review.get("account_or_order_paths") is False
    )
    threshold_policy_hold_current = threshold_policy_safe and threshold_policy_status == "threshold_policy_hold_current"
    threshold_policy_review_candidate = (
        threshold_policy_safe and threshold_policy_status == "threshold_policy_review_candidate"
    )
    settled_validation_summary = (
        settled_validation.get("summary", {})
        if isinstance(settled_validation, dict)
        else {}
    )
    settled_validation_status = (
        settled_validation.get("status")
        if isinstance(settled_validation, dict)
        else None
    )
    settled_validation_safe = (
        isinstance(settled_validation, dict)
        and settled_validation.get("review_only") is True
        and settled_validation.get("execution_enabled") is False
        and settled_validation.get("provider_api_calls") is False
        and settled_validation.get("database_writes") is False
        and settled_validation.get("market_execution") is False
        and settled_validation.get("account_or_order_paths") is False
    )
    settled_validation_no_policy = settled_validation_safe and settled_validation_status in {
        "settled_validation_no_policy_change_same_slate",
        "settled_validation_no_policy_change",
    }
    settled_validation_review_candidate = (
        settled_validation_safe and settled_validation_status == "settled_validation_review_candidate"
    )
    closing_proxy_summary = (
        closing_proxy_validation.get("summary", {})
        if isinstance(closing_proxy_validation, dict)
        else {}
    )
    closing_proxy_status = (
        closing_proxy_validation.get("status")
        if isinstance(closing_proxy_validation, dict)
        else None
    )
    closing_proxy_safe = (
        isinstance(closing_proxy_validation, dict)
        and closing_proxy_validation.get("review_only") is True
        and closing_proxy_validation.get("execution_enabled") is False
        and closing_proxy_validation.get("provider_api_calls") is False
        and closing_proxy_validation.get("database_writes") is False
        and closing_proxy_validation.get("market_execution") is False
        and closing_proxy_validation.get("account_or_order_paths") is False
        and closing_proxy_validation.get("true_closing_line_available") is False
    )
    closing_proxy_insufficient = (
        closing_proxy_safe
        and closing_proxy_status == "closing_proxy_same_slate_support_insufficient"
    )
    closing_proxy_review_candidate = (
        closing_proxy_safe and closing_proxy_status == "closing_proxy_review_candidate"
    )
    public_closing_scout_summary = (
        public_closing_scout.get("summary", {})
        if isinstance(public_closing_scout, dict)
        else {}
    )
    public_closing_scout_safe = (
        isinstance(public_closing_scout, dict)
        and public_closing_scout.get("review_only") is True
        and public_closing_scout.get("execution_enabled") is False
        and public_closing_scout.get("provider_api_calls") is False
        and public_closing_scout.get("paid_calls") is False
        and public_closing_scout.get("database_writes") is False
        and public_closing_scout.get("market_execution") is False
        and public_closing_scout.get("account_or_order_paths") is False
    )
    betexplorer_full_slate_summary = (
        betexplorer_full_slate_import.get("summary", {})
        if isinstance(betexplorer_full_slate_import, dict)
        else {}
    )
    betexplorer_full_slate_safe = (
        isinstance(betexplorer_full_slate_import, dict)
        and betexplorer_full_slate_import.get("review_only") is True
        and betexplorer_full_slate_import.get("execution_enabled") is False
        and betexplorer_full_slate_import.get("provider_api_calls") is False
        and betexplorer_full_slate_import.get("paid_calls") is False
        and betexplorer_full_slate_import.get("database_writes") is False
        and betexplorer_full_slate_import.get("market_execution") is False
        and betexplorer_full_slate_import.get("account_or_order_paths") is False
        and betexplorer_full_slate_import.get("raw_payload_copied_into_repo") is False
        and betexplorer_full_slate_import.get("status") == "betexplorer_public_closing_full_slate_import_ready"
    )
    betexplorer_moneyline_summary = (
        betexplorer_moneyline_comparison.get("summary", {})
        if isinstance(betexplorer_moneyline_comparison, dict)
        else {}
    )
    betexplorer_moneyline_status = (
        betexplorer_moneyline_comparison.get("status")
        if isinstance(betexplorer_moneyline_comparison, dict)
        else None
    )
    betexplorer_moneyline_safe = (
        isinstance(betexplorer_moneyline_comparison, dict)
        and betexplorer_moneyline_comparison.get("review_only") is True
        and betexplorer_moneyline_comparison.get("execution_enabled") is False
        and betexplorer_moneyline_comparison.get("provider_api_calls") is False
        and betexplorer_moneyline_comparison.get("paid_calls") is False
        and betexplorer_moneyline_comparison.get("database_writes") is False
        and betexplorer_moneyline_comparison.get("market_execution") is False
        and betexplorer_moneyline_comparison.get("account_or_order_paths") is False
        and betexplorer_moneyline_comparison.get("full_closing_validation") is False
    )
    betexplorer_moneyline_no_policy = (
        betexplorer_moneyline_safe
        and betexplorer_moneyline_status == "betexplorer_moneyline_closing_comparison_ready_no_policy_change"
    )
    betexplorer_market_summary = (
        betexplorer_market_comparison.get("summary", {})
        if isinstance(betexplorer_market_comparison, dict)
        else {}
    )
    betexplorer_market_status = (
        betexplorer_market_comparison.get("status")
        if isinstance(betexplorer_market_comparison, dict)
        else None
    )
    betexplorer_market_safe = (
        isinstance(betexplorer_market_comparison, dict)
        and betexplorer_market_comparison.get("review_only") is True
        and betexplorer_market_comparison.get("execution_enabled") is False
        and betexplorer_market_comparison.get("provider_api_calls") is False
        and betexplorer_market_comparison.get("paid_calls") is False
        and betexplorer_market_comparison.get("database_writes") is False
        and betexplorer_market_comparison.get("market_execution") is False
        and betexplorer_market_comparison.get("account_or_order_paths") is False
        and betexplorer_market_comparison.get("full_closing_validation") is False
    )
    betexplorer_market_no_policy = (
        betexplorer_market_safe
        and betexplorer_market_status == "betexplorer_market_closing_comparison_ready_no_policy_change"
    )
    has_makefile = (root / "Makefile").is_file()
    readme = read_text(root, "README.md")
    live_review_required = "live data quality" in readme.lower() or "operator review" in readme.lower()
    gates = [
        make_gate(
            "type2_market_capabilities_present",
            "pass" if core_ready else "blocked",
            ["MLB has no-vig/implied probability, edge, CLV, backtest, and source-preflight modules." if core_ready else "One or more core Type 2 capability files is missing."],
            [path for path, exists in capabilities.items() if exists],
        ),
        make_gate(
            "macro_makefile_target_available",
            "pass" if has_makefile else "blocked",
            ["Makefile exists for macro-status wiring." if has_makefile else "No Makefile exists yet."],
            ["Makefile"] if has_makefile else [],
        ),
        make_gate(
            "kalshi_exchange_adapter_ready",
            "pass" if kalshi_exchange_ready else "blocked",
            [f"Local Kalshi exchange artifact contains {kalshi_exchange_count} Type 2 quotes." if kalshi_exchange_ready else "Kalshi exchange adapter or generated artifact is missing."],
            [
                path
                for path in [
                    "src/mlb_platform/backtest/kalshi_exchange.py",
                    "src/mlb_platform/cli/type2_kalshi_exchange.py",
                    "docs/codex/artifacts/2026-06-20-kalshi-exchange-probabilities.json",
                    "docs/codex/artifacts/2026-06-16-kalshi-exchange-probabilities.json",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "local_sportsbook_odds_pairing_present",
            "pass" if real_sportsbook_jsonl_present else "blocked",
            [
                f"Real Type 2 sportsbook JSONL exists at {real_sportsbook_jsonl}."
                if real_sportsbook_jsonl_present
                else "No real operator-dropped baseball_mlb sportsbook odds JSONL with matching Kalshi-derived game IDs has been verified. The engineering bridge is ready; the blocker is now the data drop."
            ],
            [real_sportsbook_jsonl] if real_sportsbook_jsonl_present else [
                "docs/codex/artifacts/2026-06-20-mlb-sportsbook-local-inventory.json",
                "COMPLETION_REPORT_2026-06-20_MLB_TYPE2_ZERO_SPEND_SPORTSBOOK_UNLOCK_FULFILLED.md",
            ],
        ),
        make_gate(
            "offline_raw_odds_bridge_ready",
            "pass" if offline_raw_bridge_ready else "blocked",
            [
                "Offline/manual-drop raw The Odds API MLB bridge is implemented, tested, and documented."
                if offline_raw_bridge_ready
                else "Offline raw odds bridge evidence is missing or incomplete."
            ],
            [
                path
                for path in [
                    "src/mlb_platform/backtest/odds_api_raw_bridge.py",
                    "src/mlb_platform/cli/type2_odds_api_raw_bridge.py",
                    "tests/test_backtest/test_odds_api_raw_bridge.py",
                    "tests/test_cli/test_type2_odds_api_raw_bridge.py",
                    "docs/codex/artifacts/2026-06-20-mlb-sportsbook-local-inventory.json",
                    "COMPLETION_REPORT_2026-06-20_MLB_TYPE2_ZERO_SPEND_SPORTSBOOK_UNLOCK_FULFILLED.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "current_type2_audit_review_ready",
            "pass" if current_audit_ready else "blocked",
            [
                "Current Type 2 audit bundle is ready for review and contains review-ready candidates."
                if current_audit_ready
                else "Current Type 2 audit bundle is missing or has no review-ready candidates."
            ],
            [
                path
                for path in [
                    latest_summary_rel or "",
                    "docs/codex/artifacts/2026-06-20-type2-audit-bundle-current/type2-audit.json",
                ]
                if path and (root / path).exists()
            ],
        ),
        make_gate(
            "current_type2_review_packet_ready",
            "pass" if review_packet_ready else "blocked",
            [
                (
                    f"Review packet exists with {int(review_packet_summary.get('review_ready_count', 0))} "
                    "review-ready rows and no wide/missing-spread review-ready rows."
                )
                if review_packet_ready
                else "Current Type 2 review packet is missing or lacks required review-only quote-quality checks."
            ],
            [
                path
                for path in [
                    latest_review_packet_rel or "",
                    "scripts/generate_type2_review_packet.py",
                    "COMPLETION_REPORT_2026-06-20_MLB_TYPE2_CURRENT_AUDIT_REVIEW_HARDENING_FULFILLED.md",
                ]
                if path and (root / path).exists()
            ],
        ),
        make_gate(
            "temporal_mismatch_manual_review",
            "pass" if (not temporal_mismatch_count or (temporal_disposition_ready and temporal_manual_count == 0)) else "warn",
            [
                (
                    f"Review packet flagged {temporal_mismatch_count} likely live-game temporal mismatch rows; "
                    f"{temporal_downgraded_count} were downgraded and {temporal_manual_count} need manual verification."
                    if temporal_disposition_ready
                    else f"Review packet flags {temporal_mismatch_count} likely live-game temporal mismatch rows "
                    f"({temporal_mismatch_totals} totals, {temporal_mismatch_run_lines} run lines); "
                    "downgrade or manually verify them before any edge claim."
                )
                if temporal_mismatch_count
                else "Review packet flags no likely live-game temporal mismatch rows."
            ],
            [
                path
                for path in [
                    latest_review_packet_rel or "",
                    latest_temporal_rel or "",
                ]
                if path and (root / path).exists()
            ],
        ),
        make_gate(
            "pregame_pair_required",
            "warn" if pregame_readiness_present and not pregame_ready else ("pass" if pregame_ready else "blocked"),
            [
                (
                    "Current pre-game pairing readiness report is blocked on: "
                    + ", ".join(pregame_failing_gates)
                )
                if pregame_readiness_present and not pregame_ready
                else (
                    "Pre-game pairing readiness gate is clean."
                    if pregame_ready
                    else "Pre-game pairing readiness report is missing."
                )
            ],
            [
                path
                for path in [
                    "docs/codex/current-state.md",
                    latest_pregame_readiness_rel or "",
                    "docs/codex/manual-drops/mlb-type2-pregame-pair-contract.md",
                    "COMPLETION_REPORT_2026-06-20_MLB_TYPE2_PREGAME_PAIRING_READINESS_FULFILLED.md",
                ]
                if path and (root / path).exists()
            ],
        ),
        make_gate(
            "pregame_drop_intake_runner_ready",
            "pass" if pregame_intake_present else "blocked",
            [
                (
                    f"Pregame drop intake runner wrote status {pregame_intake_status}; "
                    "missing operator drop is represented as a blocked report without provider calls."
                )
                if pregame_intake_present
                else "Pregame drop intake status report is missing or unsafe."
            ],
            [
                path
                for path in [
                    "src/mlb_platform/reports/type2_pregame_intake.py",
                    "scripts/run_type2_pregame_drop_intake.py",
                    "tests/test_reports/test_type2_pregame_intake.py",
                    "docs/codex/artifacts/type2-pregame-drop-intake-latest/pregame-drop-intake-status.json",
                    "docs/codex/artifacts/type2-pregame-drop-intake-latest/pregame-drop-intake-status.md",
                    "COMPLETION_REPORT_2026-06-21_MLB_TYPE2_PREGAME_DROP_INTAKE_RUNNER_FULFILLED.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "pregame_operator_drop_available",
            "blocked"
            if pregame_intake_present and pregame_intake_status == "blocked_missing_operator_drop"
            else ("pass" if pregame_intake_ready else "blocked"),
            [
                (
                    "No same-slate pregame sportsbook/Kalshi operator drop was supplied; intake is intentionally blocked."
                    if pregame_intake_present and pregame_intake_status == "blocked_missing_operator_drop"
                    else (
                        "Pregame operator drop intake reports ready."
                        if pregame_intake_ready
                        else "Pregame operator drop status is missing or not ready."
                    )
                )
            ],
            [
                path
                for path in [
                    latest_pregame_intake_rel or "",
                    "docs/codex/manual-drops/mlb-type2-pregame-pair-contract.md",
                ]
                if path and (root / path).exists()
            ],
        ),
        make_gate(
            "review_adjudication_ready",
            "pass" if review_adjudication_ready else "blocked",
            [
                (
                    f"Review adjudication reports {review_adjudication_summary.get('review_ready_cluster_count')} "
                    "passing cluster(s) with no failed gates."
                    if review_adjudication_ready
                    else "Review adjudication artifact is missing, unsafe, or has failed gates."
                )
            ],
            [
                path
                for path in [
                    latest_review_adjudication_rel or "",
                    "src/mlb_platform/reports/type2_review_adjudication.py",
                    "scripts/generate_type2_review_adjudication.py",
                    "tests/test_reports/test_type2_review_adjudication.py",
                ]
                if path and (root / path).exists()
            ],
        ),
        make_gate(
            "repeatability_ledger_present",
            (
                "pass"
                if repeatability_observed or repeatability_ready_for_review
                else ("warn" if repeatability_insufficient or repeatability_no_signal_clean_packets else "blocked")
            ),
            [
                (
                    f"Repeatability ledger status {repeatability_status}; "
                    f"clean_packet_count={repeatability_summary.get('clean_packet_count')}, "
                    f"clean_no_signal_packet_count={repeatability_summary.get('clean_no_signal_packet_count')}, "
                    f"repeated_descriptor_count={repeatability_summary.get('repeated_descriptor_count')}."
                )
                if repeatability_safe
                else "Repeatability ledger is missing or unsafe."
            ],
            [
                path
                for path in [
                    latest_repeatability_ledger_rel or "",
                    "src/mlb_platform/reports/type2_repeatability_ledger.py",
                    "scripts/generate_type2_repeatability_ledger.py",
                    "tests/test_reports/test_type2_repeatability_ledger.py",
                ]
                if path and (root / path).exists()
            ],
        ),
        make_gate(
            "repeatability_research_review_ready",
            "pass" if repeatability_research_review_ready else ("warn" if repeatability_ready_for_review else "blocked"),
            [
                (
                    f"Repeatability research review status {repeatability_research_review_status}; "
                    f"stable_recurring_descriptor_count="
                    f"{repeatability_research_review_summary.get('stable_recurring_descriptor_count')}, "
                    f"same_slate_date_count={repeatability_research_review_summary.get('same_slate_date_count')}."
                )
                if repeatability_research_review_ready
                else (
                    "Repeatability ledger is ready, but the research-review synthesis has not been generated."
                    if repeatability_ready_for_review
                    else "Repeatability research review is missing until the ledger reaches the review threshold."
                )
            ],
            [
                path
                for path in [
                    latest_repeatability_research_review_rel or "",
                    "src/mlb_platform/reports/type2_repeatability_research_review.py",
                    "scripts/generate_type2_repeatability_research_review.py",
                    "tests/test_reports/test_type2_repeatability_research_review.py",
                ]
                if path and (root / path).exists()
            ],
        ),
        make_gate(
            "threshold_policy_review_present",
            (
                "pass"
                if threshold_policy_review_candidate
                else ("warn" if threshold_policy_hold_current else "blocked")
            ),
            [
                (
                    f"Threshold-policy review status {threshold_policy_status}; "
                    f"current_threshold_count={threshold_policy_summary.get('current_threshold_count')}, "
                    f"max_abs_net_edge={threshold_policy_summary.get('max_abs_net_edge')}, "
                    f"same_slate_date_count={threshold_policy_summary.get('same_slate_date_count')}."
                )
                if threshold_policy_safe
                else "Threshold-policy review is missing or unsafe."
            ],
            [
                path
                for path in [
                    latest_threshold_policy_review_rel or "",
                    "src/mlb_platform/reports/type2_threshold_policy_review.py",
                    "scripts/generate_type2_threshold_policy_review.py",
                    "tests/test_reports/test_type2_threshold_policy_review.py",
                ]
                if path and (root / path).exists()
            ],
        ),
        make_gate(
            "settled_outcome_validation_present",
            (
                "pass"
                if settled_validation_review_candidate
                else ("warn" if settled_validation_no_policy else "blocked")
            ),
            [
                (
                    f"Settled validation status {settled_validation_status}; "
                    f"valid_directional_row_count={settled_validation_summary.get('valid_directional_row_count')}, "
                    f"directional_correct_rate={settled_validation_summary.get('directional_correct_rate')}, "
                    f"current_threshold_count={settled_validation_summary.get('current_threshold_count')}, "
                    f"same_slate_date_count={settled_validation_summary.get('same_slate_date_count')}."
                )
                if settled_validation_safe
                else "Settled-outcome validation is missing or unsafe."
            ],
            [
                path
                for path in [
                    latest_settled_validation_rel or "",
                    "src/mlb_platform/reports/type2_settled_outcome_validation.py",
                    "scripts/generate_type2_settled_outcome_validation.py",
                    "tests/test_reports/test_type2_settled_outcome_validation.py",
                ]
                if path and (root / path).exists()
            ],
        ),
        make_gate(
            "closing_proxy_validation_present",
            (
                "pass"
                if closing_proxy_review_candidate
                else ("warn" if closing_proxy_insufficient else "blocked")
            ),
            [
                (
                    f"Closing-proxy validation status {closing_proxy_status}; "
                    f"paired_row_count={closing_proxy_summary.get('paired_row_count')}, "
                    f"current_threshold_count={closing_proxy_summary.get('current_threshold_count')}, "
                    f"same_slate_date_count={closing_proxy_summary.get('same_slate_date_count')}, "
                    f"best_lower_threshold="
                    f"{(closing_proxy_summary.get('best_lower_threshold_candidate') or {}).get('threshold') if isinstance(closing_proxy_summary.get('best_lower_threshold_candidate'), dict) else None}."
                )
                if closing_proxy_safe
                else "Closing-proxy validation is missing or unsafe."
            ],
            [
                path
                for path in [
                    latest_closing_proxy_validation_rel or "",
                    "src/mlb_platform/reports/type2_closing_proxy_validation.py",
                    "scripts/generate_type2_closing_proxy_validation.py",
                    "tests/test_reports/test_type2_closing_proxy_validation.py",
                ]
                if path and (root / path).exists()
            ],
        ),
        make_gate(
            "betexplorer_moneyline_closing_comparison_present",
            (
                "pass"
                if betexplorer_moneyline_no_policy
                else ("warn" if betexplorer_full_slate_safe or public_closing_scout_safe else "blocked")
            ),
            [
                (
                    f"BetExplorer comparison status {betexplorer_moneyline_status}; "
                    f"matched_rows={betexplorer_moneyline_summary.get('matched_row_count')}, "
                    f"current_threshold_count={betexplorer_moneyline_summary.get('current_threshold_count')}, "
                    f"converged={betexplorer_moneyline_summary.get('converged_count')}, "
                    f"diverged={betexplorer_moneyline_summary.get('diverged_count')}, "
                    f"direction_support={betexplorer_moneyline_summary.get('direction_support_count')}, "
                    f"direction_against={betexplorer_moneyline_summary.get('direction_against_count')}."
                )
                if betexplorer_moneyline_safe
                else (
                    f"BetExplorer full-slate public import is present with "
                    f"{betexplorer_full_slate_summary.get('target_event_count')} events and "
                    f"{betexplorer_full_slate_summary.get('row_count')} rows, but comparison is missing."
                    if betexplorer_full_slate_safe
                    else (
                        f"Public closing scout found "
                        f"{public_closing_scout_summary.get('usable_true_closing_source_count')} usable source(s), "
                        "but BetExplorer import/comparison is missing."
                        if public_closing_scout_safe
                        else "Public closing comparison is missing or unsafe."
                    )
                )
            ],
            [
                path
                for path in [
                    latest_public_closing_scout_rel or "",
                    latest_betexplorer_public_import_rel or "",
                    latest_betexplorer_full_slate_import_rel or "",
                    latest_betexplorer_moneyline_comparison_rel or "",
                    "src/mlb_platform/reports/type2_betexplorer_moneyline_closing_comparison.py",
                    "scripts/generate_type2_betexplorer_moneyline_closing_comparison.py",
                    "tests/test_reports/test_type2_betexplorer_moneyline_closing_comparison.py",
                ]
                if path and (root / path).exists()
            ],
        ),
        make_gate(
            "betexplorer_market_closing_comparison_present",
            "pass" if betexplorer_market_no_policy else ("warn" if betexplorer_full_slate_safe else "blocked"),
            [
                (
                    f"BetExplorer market comparison status {betexplorer_market_status}; "
                    f"matched_rows={betexplorer_market_summary.get('matched_row_count')}, "
                    f"matched_by_market={betexplorer_market_summary.get('matched_by_market')}, "
                    f"current_threshold_count={betexplorer_market_summary.get('current_threshold_count')}, "
                    f"converged={betexplorer_market_summary.get('converged_count')}, "
                    f"diverged={betexplorer_market_summary.get('diverged_count')}, "
                    f"direction_support={betexplorer_market_summary.get('direction_support_count')}, "
                    f"direction_against={betexplorer_market_summary.get('direction_against_count')}."
                )
                if betexplorer_market_safe
                else (
                    "BetExplorer full-slate public import is present, but the multi-market comparison is missing."
                    if betexplorer_full_slate_safe
                    else "BetExplorer market comparison is missing or unsafe."
                )
            ],
            [
                path
                for path in [
                    latest_betexplorer_full_slate_import_rel or "",
                    latest_betexplorer_market_comparison_rel or "",
                    "src/mlb_platform/reports/type2_betexplorer_market_closing_comparison.py",
                    "scripts/generate_type2_betexplorer_market_closing_comparison.py",
                    "tests/test_reports/test_type2_betexplorer_market_closing_comparison.py",
                ]
                if path and (root / path).exists()
            ],
        ),
        make_gate(
            "trap_stats_guard_present",
            "pass" if capabilities.get("tests/test_trap_stats.py") else "warn",
            ["Trap stats guard test exists." if capabilities.get("tests/test_trap_stats.py") else "Trap stats guard test was not found."],
            ["tests/test_trap_stats.py"] if capabilities.get("tests/test_trap_stats.py") else [],
        ),
        make_gate(
            "live_data_operator_review",
            "warn",
            ["README requires live data quality/source freshness operator review before production; current audit remains review-only." if live_review_required else "Production live-data review language was not found in README."],
            ["README.md"],
        ),
        make_gate(
            "dirty_tree_risk",
            "warn" if status["git"]["dirty_counts"]["total"] else "pass",
            [f"Dirty paths: {status['git']['dirty_counts']['total']}."],
            [],
        ),
    ]
    evidence = {
        "status": (
            "primary_type2_pregame_intake_blocked_missing_operator_drop"
            if pregame_intake_present and pregame_intake_status == "blocked_missing_operator_drop"
            else (
                "primary_type2_repeatability_research_review_ready_same_slate_caveat"
                if repeatability_research_review_ready
                else (
                    "primary_type2_repeatability_ready_for_research_review"
                    if repeatability_ready_for_review
                    else (
                        "primary_type2_repeatability_observed"
                        if repeatability_observed
                        else (
                            "primary_type2_repeatability_insufficient"
                            if repeatability_insufficient
                            else (
                                "primary_type2_betexplorer_market_closing_comparison_no_policy_change"
                                if betexplorer_market_no_policy
                                else (
                                    "primary_type2_betexplorer_moneyline_closing_comparison_no_policy_change"
                                    if betexplorer_moneyline_no_policy
                                    else (
                                        "primary_type2_closing_proxy_review_candidate"
                                        if closing_proxy_review_candidate
                                        else (
                                            "primary_type2_closing_proxy_same_slate_support_insufficient"
                                            if closing_proxy_insufficient
                                            else (
                                                "primary_type2_settled_validation_review_candidate"
                                                if settled_validation_review_candidate
                                                else (
                                                    "primary_type2_settled_validation_no_policy_change_same_slate"
                                                    if settled_validation_no_policy
                                                    else (
                                                        "primary_type2_threshold_policy_review_candidate"
                                                        if threshold_policy_review_candidate
                                                        else (
                                                            "primary_type2_threshold_policy_hold_current"
                                                            if threshold_policy_hold_current
                                                            else (
                                                                "primary_type2_repeatability_no_signal_clean_packets"
                                                                if repeatability_no_signal_clean_packets
                                                                else (
                                                                    "primary_type2_repeatability_blocked_no_clean_packets"
                                                                    if repeatability_blocked_no_clean_packets
                                                                    else (
                                                                        "primary_type2_review_adjudication_ready"
                                                                        if review_adjudication_ready
                                                                        else (
                                                                            "primary_type2_pregame_intake_ready_pair"
                                                                            if pregame_intake_ready
                                                                            else (
                                                                                "primary_type2_pregame_gate_ready_operator_drop_required"
                                                                                if pregame_readiness_present and not pregame_ready
                                                                                else (
                                                                                    "primary_type2_pregame_pair_clean_ready"
                                                                                    if pregame_ready
                                                                                    else (
                                                                                        "primary_type2_temporal_downgraded_pregame_pair_required"
                                                                                        if review_packet_ready
                                                                                        and temporal_disposition_ready
                                                                                        and temporal_manual_count == 0
                                                                                        else (
                                                                                            "primary_type2_review_packet_ready_temporal_mismatch_verification_needed"
                                                                                            if review_packet_ready
                                                                                            and temporal_mismatch_count
                                                                                            else (
                                                                                                "primary_type2_current_audit_review_ready"
                                                                                                if current_audit_ready
                                                                                                else "primary_type2_pairing_ready_audit_blocked"
                                                                                            )
                                                                                        )
                                                                                    )
                                                                                )
                                                                            )
                                                                        )
                                                                    )
                                                                )
                                                            )
                                                        )
                                                    )
                                                )
                                            )
                                        )
                                    )
                                )
                            )
                        )
                    )
                )
            )
        ),
        "latest_artifacts": artifacts,
        "hashes": hashes,
        "blocker_count": sum(1 for gate in gates if gate["status"] in {"blocked", "fail"}),
        "metrics": {
            "capabilities": capabilities,
            "kalshi_exchange_artifact": json_brief(kalshi_exchange_artifact)
            if kalshi_exchange_artifact is not None
            else {"missing": True},
            "sportsbook_preflight": json_brief(sportsbook_preflight)
            if sportsbook_preflight is not None
            else {"missing": True},
            "sportsbook_inventory": json_brief(sportsbook_inventory)
            if sportsbook_inventory is not None
            else {"missing": True},
            "current_type2_audit_summary": json_brief(current_audit_summary)
            if current_audit_summary is not None
            else {"missing": True},
            "current_type2_review_packet": {
                "missing": review_packet is None,
                "ready": review_packet_ready,
                "summary_counts": review_packet_summary,
                "review_ready_by_market": review_packet.get("review_ready_by_market", {})
                if isinstance(review_packet, dict)
                else {},
                "game_id_match_modes": review_packet.get("game_id_match_modes", {})
                if isinstance(review_packet, dict)
                else {},
                "exchange_spread_distribution": review_packet.get("exchange_spread_distribution", {})
                if isinstance(review_packet, dict)
                else {},
                "review_ready_rows_with_missing_spread": review_packet_missing_spread,
                "review_ready_rows_with_wide_spread": review_packet_wide_spread,
                "likely_live_game_temporal_mismatch_totals": temporal_mismatch_totals,
                "likely_live_game_temporal_mismatch_run_lines": temporal_mismatch_run_lines,
                "likely_live_game_temporal_mismatch_total": temporal_mismatch_count,
            },
            "temporal_mismatch_disposition": {
                "missing": temporal_disposition is None,
                "ready": temporal_disposition_ready,
                "summary": temporal_summary,
                "downgraded_temporal_mismatch_count": temporal_downgraded_count,
                "needs_manual_verification_count": temporal_manual_count,
                "unclassified_count": temporal_unclassified_count,
            },
            "pregame_pairing_readiness": {
                "missing": pregame_readiness is None,
                "present": pregame_readiness_present,
                "ready": pregame_ready,
                "status": pregame_readiness.get("status") if isinstance(pregame_readiness, dict) else None,
                "source_artifact": latest_pregame_readiness_rel,
                "summary": pregame_summary,
                "failing_gates": pregame_failing_gates,
            },
            "pregame_drop_intake": {
                "missing": pregame_intake is None,
                "present": pregame_intake_present,
                "ready": pregame_intake_ready,
                "status": pregame_intake_status,
                "source_artifact": latest_pregame_intake_rel,
                "blockers": pregame_intake.get("blockers", [])
                if isinstance(pregame_intake, dict)
                else [],
            },
            "review_adjudication": {
                "missing": review_adjudication is None,
                "ready": review_adjudication_ready,
                "status": review_adjudication.get("status")
                if isinstance(review_adjudication, dict)
                else None,
                "source_artifact": latest_review_adjudication_rel,
                "summary": review_adjudication_summary,
            },
            "repeatability_ledger": {
                "missing": repeatability_ledger is None,
                "safe": repeatability_safe,
                "status": repeatability_status,
                "source_artifact": latest_repeatability_ledger_rel,
                "summary": repeatability_summary,
            },
            "repeatability_research_review": {
                "missing": repeatability_research_review is None,
                "ready": repeatability_research_review_ready,
                "status": repeatability_research_review_status,
                "source_artifact": latest_repeatability_research_review_rel,
                "summary": repeatability_research_review_summary,
            },
            "threshold_policy_review": {
                "missing": threshold_policy_review is None,
                "safe": threshold_policy_safe,
                "status": threshold_policy_status,
                "source_artifact": latest_threshold_policy_review_rel,
                "summary": threshold_policy_summary,
            },
            "settled_outcome_validation": {
                "missing": settled_validation is None,
                "safe": settled_validation_safe,
                "status": settled_validation_status,
                "source_artifact": latest_settled_validation_rel,
                "summary": settled_validation_summary,
            },
            "closing_proxy_validation": {
                "missing": closing_proxy_validation is None,
                "safe": closing_proxy_safe,
                "status": closing_proxy_status,
                "source_artifact": latest_closing_proxy_validation_rel,
                "summary": closing_proxy_summary,
            },
            "public_closing_scout": {
                "missing": public_closing_scout is None,
                "safe": public_closing_scout_safe,
                "status": public_closing_scout.get("status")
                if isinstance(public_closing_scout, dict)
                else None,
                "source_artifact": latest_public_closing_scout_rel,
                "summary": public_closing_scout_summary,
            },
            "betexplorer_public_import": json_brief(betexplorer_public_import)
            if betexplorer_public_import is not None
            else {"missing": True},
            "betexplorer_full_slate_import": {
                "missing": betexplorer_full_slate_import is None,
                "safe": betexplorer_full_slate_safe,
                "status": betexplorer_full_slate_import.get("status")
                if isinstance(betexplorer_full_slate_import, dict)
                else None,
                "source_artifact": latest_betexplorer_full_slate_import_rel,
                "summary": betexplorer_full_slate_summary,
            },
            "betexplorer_moneyline_closing_comparison": {
                "missing": betexplorer_moneyline_comparison is None,
                "safe": betexplorer_moneyline_safe,
                "status": betexplorer_moneyline_status,
                "source_artifact": latest_betexplorer_moneyline_comparison_rel,
                "summary": betexplorer_moneyline_summary,
            },
            "betexplorer_market_closing_comparison": {
                "missing": betexplorer_market_comparison is None,
                "safe": betexplorer_market_safe,
                "status": betexplorer_market_status,
                "source_artifact": latest_betexplorer_market_comparison_rel,
                "summary": betexplorer_market_summary,
            },
            "kalshi_exchange_quote_count": kalshi_exchange_count,
            "local_baseball_mlb_sportsbook_rows_found": local_mlb_sportsbook_rows,
            "offline_raw_bridge_ready": offline_raw_bridge_ready,
            "real_sportsbook_jsonl_present": real_sportsbook_jsonl_present,
            "current_audit_ready": current_audit_ready,
            "latest_directives": latest_matching(
                root,
                [
                    "NEXT_DIRECTIVE_2026-06-15*.md",
                    "NEXT_DIRECTIVE_2026-06-20*.md",
                    "NEXT_DIRECTIVE_2026-06-21*.md",
                    "NEXT_DIRECTIVE_2026-06-29*.md",
                    "NEXT_DIRECTIVE_2026-06-30*.md",
                    "WORKER_DIRECTIVE_2026-06-20*.md",
                ],
                limit=10,
            ),
            "dirty_total": status["git"]["dirty_counts"]["total"],
        },
    }
    return finish_status(status, evidence, gates)


def atp_status(root: Path) -> dict[str, Any]:
    status = base_status("atp-oracle", root)
    artifact_paths = [
        ".codex/ACTIVE_GOAL.md",
        "VISION_GOAL_STATUS_2026-06-10.md",
        "docs/vision-implementation-matrix.json",
        "docs/vision-implementation-matrix.md",
        "docs/codex/current-state.md",
        "backend/app/services/type2_readiness.py",
        "backend/app/services/type2_readiness_cli.py",
        "backend/app/services/type2_g1g2_diagnostic.py",
        "backend/tests/test_type2_readiness.py",
        "backend/tests/test_type2_g1g2_diagnostic.py",
        "docs/codex/artifacts/type2-readiness-latest/type2-readiness.json",
        "docs/codex/artifacts/type2-readiness-latest/type2-readiness.md",
        "docs/codex/artifacts/type2-g1g2-diagnostic-latest/type2-g1g2-diagnostic.json",
        "docs/codex/artifacts/type2-g1g2-diagnostic-latest/type2-g1g2-diagnostic.md",
        *latest_matching(
            root,
            [
                "docs/codex/artifacts/type2-g1g2-diagnostic-latest/vision_model_quality_gates_*.json",
                "docs/codex/artifacts/type2-g1g2-diagnostic-latest/model_promotion_gate_*.json",
            ],
            limit=5,
        ),
        "docs/codex/tranches/2026-06-28-atp-type2-g1g2-diagnostic-bundle.md",
        "docs/codex/tranches/2026-06-27-atp-type2-readiness-status-surface.md",
        "NEXT_DIRECTIVE_2026-06-28_ATP_TYPE2_G1G2_DIAGNOSTIC_BUNDLE.md",
        "NEXT_DIRECTIVE_2026-06-27_ATP_TYPE2_READINESS_STATUS_SURFACE.md",
        "COMPLETION_REPORT_2026-06-28_ATP_TYPE2_G1G2_DIAGNOSTIC_BUNDLE_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-27_ATP_TYPE2_READINESS_STATUS_SURFACE_FULFILLED.md",
    ]
    artifacts, hashes = artifact_pack(root, artifact_paths)
    active_goal = read_text(root, ".codex/ACTIVE_GOAL.md")
    goal_status = read_text(root, "VISION_GOAL_STATUS_2026-06-10.md")
    vision_md = read_text(root, "docs/vision-implementation-matrix.md")
    type2_readiness = read_json(root, "docs/codex/artifacts/type2-readiness-latest/type2-readiness.json")
    type2_g1g2_diagnostic = read_json(
        root,
        "docs/codex/artifacts/type2-g1g2-diagnostic-latest/type2-g1g2-diagnostic.json",
    )
    text = f"{active_goal}\n{goal_status}\n{vision_md}"
    score = (
        extract_score(goal_status, [r"Matrix score:\*\*\s*\*\*(\d+)\s*/\s*100"])
        or extract_score(vision_md, [r"Current evidence-backed implementation score:\s*\*\*(\d+)\s*/\s*100"])
        or extract_score(active_goal, [r"\|\s*2026-06-\d+\s*\|\s*(\d+)\s*/\s*100\s*\|[^\n]*remains"])
    )
    mentions_g1 = "G1" in text and ("failing" in text.lower() or "not promoted" in text.lower())
    mentions_g2 = "G2" in text and "failing" in text.lower()
    external_gap = any(token in text for token in ("D3", "P5", "G5"))
    type2_readiness_present = (
        isinstance(type2_readiness, dict)
        and type2_readiness.get("research_only") is True
        and type2_readiness.get("execution_enabled") is False
        and isinstance(type2_readiness.get("safety"), dict)
        and type2_readiness["safety"].get("provider_api_calls") is False
        and type2_readiness["safety"].get("score_or_promotion_changed") is False
    )
    type2_readiness_status = type2_readiness.get("status") if isinstance(type2_readiness, dict) else None
    type2_readiness_ready = bool(type2_readiness.get("ready")) if isinstance(type2_readiness, dict) else False
    type2_g1g2_present = (
        isinstance(type2_g1g2_diagnostic, dict)
        and type2_g1g2_diagnostic.get("research_only") is True
        and type2_g1g2_diagnostic.get("execution_enabled") is False
        and type2_g1g2_diagnostic.get("ready") is False
        and isinstance(type2_g1g2_diagnostic.get("safety"), dict)
        and type2_g1g2_diagnostic["safety"].get("provider_api_calls") is False
        and type2_g1g2_diagnostic["safety"].get("score_or_promotion_changed") is False
        and type2_g1g2_diagnostic["safety"].get("model_promotion") is False
        and type2_g1g2_diagnostic["safety"].get("threshold_changed") is False
    )
    type2_g1g2_status = type2_g1g2_diagnostic.get("status") if isinstance(type2_g1g2_diagnostic, dict) else None
    gates = [
        make_gate(
            "vision_score_not_complete",
            "blocked" if score is not None and score < 100 else "warn",
            [f"Vision score is {score}/100." if score is not None else "Vision score was not found."],
            [".codex/ACTIVE_GOAL.md", "VISION_GOAL_STATUS_2026-06-10.md"],
        ),
        make_gate(
            "g1_model_quality_gate",
            "blocked" if mentions_g1 else "warn",
            ["G1 Brier/Elo promotion remains blocked." if mentions_g1 else "G1 blocker text was not found."],
            [".codex/ACTIVE_GOAL.md"],
        ),
        make_gate(
            "g2_calibration_gate",
            "blocked" if mentions_g2 else "warn",
            ["G2 calibration gate remains blocked." if mentions_g2 else "G2 blocker text was not found."],
            [".codex/ACTIVE_GOAL.md"],
        ),
        make_gate(
            "external_proof_gaps",
            "blocked" if external_gap else "warn",
            ["D3/G5/P5 external evidence gaps remain." if external_gap else "External gap text was not found."],
            [".codex/ACTIVE_GOAL.md", "VISION_GOAL_STATUS_2026-06-10.md"],
        ),
        make_gate(
            "type2_readiness_surface_ready",
            "pass" if type2_readiness_present else "blocked",
            [
                (
                    f"Type 2 readiness surface reports {type2_readiness_status}."
                    if type2_readiness_present
                    else "Type 2 readiness surface is missing or unsafe."
                )
            ],
            [
                path
                for path in [
                    "backend/app/services/type2_readiness.py",
                    "backend/app/services/type2_readiness_cli.py",
                    "backend/tests/test_type2_readiness.py",
                    "docs/codex/artifacts/type2-readiness-latest/type2-readiness.json",
                    "docs/codex/artifacts/type2-readiness-latest/type2-readiness.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "type2_g1g2_diagnostic_ready",
            "pass" if type2_g1g2_present else "blocked",
            [
                (
                    f"Type 2 G1/G2 diagnostic bundle reports {type2_g1g2_status}."
                    if type2_g1g2_present
                    else "Type 2 G1/G2 diagnostic bundle is missing or unsafe."
                )
            ],
            [
                path
                for path in [
                    "backend/app/services/type2_g1g2_diagnostic.py",
                    "backend/tests/test_type2_g1g2_diagnostic.py",
                    "docs/codex/artifacts/type2-g1g2-diagnostic-latest/type2-g1g2-diagnostic.json",
                    "docs/codex/artifacts/type2-g1g2-diagnostic-latest/type2-g1g2-diagnostic.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "dirty_tree_risk",
            "warn" if status["git"]["dirty_counts"]["total"] else "pass",
            [f"Dirty paths: {status['git']['dirty_counts']['total']}."],
            [],
        ),
    ]
    evidence = {
        "status": (
            "tennis_type2_ready_for_manual_review"
            if type2_readiness_present and type2_readiness_ready
            else (
                "tennis_type2_g1g2_diagnostic_ready_blocked_fresh_validation_external_evidence"
                if type2_g1g2_present
                else "tennis_type2_candidate_model_quality_blocked"
                if not type2_readiness_present
                else "tennis_type2_readiness_blocked_model_quality_external_evidence"
            )
        ),
        "latest_artifacts": artifacts,
        "hashes": hashes,
        "blocker_count": sum(1 for gate in gates if gate["status"] in {"blocked", "fail"}),
        "metrics": {
            "vision_score": score,
            "remaining_gap_points_estimate": None if score is None else max(0, 100 - score),
            "g1_blocked": mentions_g1,
            "g2_blocked": mentions_g2,
            "external_gap_present": external_gap,
            "type2_readiness": json_brief(type2_readiness)
            if type2_readiness is not None
            else {"missing": True},
            "type2_readiness_present": type2_readiness_present,
            "type2_readiness_ready": type2_readiness_ready,
            "type2_readiness_status": type2_readiness_status,
            "type2_g1g2_diagnostic": json_brief(type2_g1g2_diagnostic)
            if type2_g1g2_diagnostic is not None
            else {"missing": True},
            "type2_g1g2_diagnostic_present": type2_g1g2_present,
            "type2_g1g2_diagnostic_status": type2_g1g2_status,
            "dirty_total": status["git"]["dirty_counts"]["total"],
        },
    }
    return finish_status(status, evidence, gates)


def nba_status(root: Path) -> dict[str, Any]:
    status = base_status("nba-analytics-platform", root)
    platform_rel = "docs/annex/NBA_PLATFORM_MACRO_READINESS_2026-06-11.json"
    claim_rel = "docs/annex/NBA_PLATFORM_CLAIM_REGISTRY_2026-06-11.json"
    consistency_rel = "docs/annex/NBA_PLATFORM_READINESS_CONSISTENCY_2026-06-11.json"
    t21_rel = "docs/annex/NBA_SUBSTITUTION_IDENTITY_DIAGNOSTIC_T21_2026-06-15.json"
    t21_completion_rel = "completion_report_t21_ambiguous_substitution_identity_diagnostic.md"
    market_gate_rel = "docs/codex/artifacts/nba-market-claim-gate-latest/nba-market-claim-gate.json"
    market_bakeoff_rel = "docs/codex/artifacts/nba-market-claim-gate-latest/market-challenger-bakeoff.json"
    model_design_rel = "docs/codex/artifacts/nba-model-promotability-latest/nba-model-promotability-design.json"
    residual_signal_rel = "docs/codex/artifacts/nba-residual-signal-latest/nba-residual-signal-diagnostic.json"
    residual_overcorrection_rel = (
        "docs/codex/artifacts/nba-residual-overcorrection-latest/nba-residual-overcorrection-diagnostic.json"
    )
    artifact_paths = [
        platform_rel,
        claim_rel,
        consistency_rel,
        t21_rel,
        t21_completion_rel,
        "NBA_SUBSTITUTION_IDENTITY_DIAGNOSTIC_T21_2026-06-15.md",
        "docs/codex/current-state.md",
        "handicapper/market_challenger_bakeoff.py",
        "scripts/codex_nba_stabilization_status.py",
        "scripts/codex_nba_market_claim_gate.py",
        "scripts/codex_nba_model_promotability_design.py",
        "scripts/codex_nba_residual_signal_diagnostic.py",
        "scripts/codex_nba_residual_overcorrection_diagnostic.py",
        "tests/test_handicapper/test_market_model_diagnostics_t10.py",
        "tests/test_codex_nba_stabilization_status.py",
        "tests/test_codex_nba_market_claim_gate.py",
        "tests/test_codex_nba_model_promotability_design.py",
        "tests/test_codex_nba_residual_signal_diagnostic.py",
        "tests/test_codex_nba_residual_overcorrection_diagnostic.py",
        "docs/codex/artifacts/nba-stabilization-latest/nba-stabilization.json",
        "docs/codex/artifacts/nba-stabilization-latest/nba-stabilization.md",
        market_gate_rel,
        "docs/codex/artifacts/nba-market-claim-gate-latest/nba-market-claim-gate.md",
        market_bakeoff_rel,
        "docs/codex/artifacts/nba-market-claim-gate-latest/market-challenger-bakeoff.md",
        "docs/codex/artifacts/nba-market-claim-gate-latest/no-promotable-model-gate.json",
        "docs/codex/artifacts/nba-market-claim-gate-latest/no-promotable-model-gate.md",
        model_design_rel,
        "docs/codex/artifacts/nba-model-promotability-latest/nba-model-promotability-design.md",
        residual_signal_rel,
        "docs/codex/artifacts/nba-residual-signal-latest/nba-residual-signal-diagnostic.md",
        residual_overcorrection_rel,
        "docs/codex/artifacts/nba-residual-overcorrection-latest/nba-residual-overcorrection-diagnostic.md",
        "docs/codex/tranches/2026-06-28-nba-prior-season-shrinkage-clipping-evaluator.md",
        "docs/codex/tranches/2026-06-28-nba-residual-signal-diagnostic.md",
        "docs/codex/tranches/2026-06-28-nba-canonical-side-residual-evaluator.md",
        "docs/codex/tranches/2026-06-28-nba-residual-overcorrection-diagnostic.md",
        "docs/codex/tranches/2026-06-28-nba-market-residual-calibration-evaluator.md",
        "docs/codex/tranches/2026-06-28-nba-full-suite-residual-cleanup-before-evaluator.md",
        "docs/codex/tranches/2026-06-28-nba-model-promotability-diagnostic-design.md",
        "docs/codex/tranches/2026-06-28-nba-market-claim-gate-refresh.md",
        "docs/codex/tranches/2026-06-27-nba-stabilization-dirty-t21-completion.md",
        "NEXT_DIRECTIVE_2026-06-28_NBA_MARKET_RESIDUAL_CALIBRATION_EVALUATOR.md",
        "NEXT_DIRECTIVE_2026-06-28_NBA_RESIDUAL_SIGNAL_DIAGNOSTIC.md",
        "NEXT_DIRECTIVE_2026-06-28_NBA_CANONICAL_SIDE_RESIDUAL_EVALUATOR.md",
        "NEXT_DIRECTIVE_2026-06-28_NBA_RESIDUAL_OVERCORRECTION_DIAGNOSTIC.md",
        "NEXT_DIRECTIVE_2026-06-28_NBA_PRIOR_SEASON_SHRINKAGE_CLIPPING_EVALUATOR.md",
        "NEXT_DIRECTIVE_2026-06-28_NBA_FULL_SUITE_RESIDUAL_CLEANUP_BEFORE_EVALUATOR.md",
        "NEXT_DIRECTIVE_2026-06-28_NBA_MODEL_PROMOTABILITY_DIAGNOSTIC_DESIGN.md",
        "NEXT_DIRECTIVE_2026-06-28_NBA_MARKET_CLAIM_GATE_REFRESH.md",
        "NEXT_DIRECTIVE_2026-06-27_NBA_STABILIZATION_DIRTY_T21_COMPLETION.md",
        "COMPLETION_REPORT_2026-06-28_NBA_MARKET_RESIDUAL_CALIBRATION_EVALUATOR_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-28_NBA_RESIDUAL_SIGNAL_DIAGNOSTIC_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-28_NBA_CANONICAL_SIDE_RESIDUAL_EVALUATOR_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-28_NBA_RESIDUAL_OVERCORRECTION_DIAGNOSTIC_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-28_NBA_PRIOR_SEASON_SHRINKAGE_CLIPPING_EVALUATOR_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-28_NBA_FULL_SUITE_RESIDUAL_CLEANUP_BEFORE_EVALUATOR_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-28_NBA_MODEL_PROMOTABILITY_DIAGNOSTIC_DESIGN_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-28_NBA_MARKET_CLAIM_GATE_REFRESH_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-27_NBA_STABILIZATION_DIRTY_T21_COMPLETION_FULFILLED.md",
    ]
    artifacts, hashes = artifact_pack(root, artifact_paths)
    platform = read_json(root, platform_rel) or {}
    claims = read_json(root, claim_rel) or {}
    consistency = read_json(root, consistency_rel) or {}
    t21 = read_json(root, t21_rel) or {}
    stabilization = read_json(root, "docs/codex/artifacts/nba-stabilization-latest/nba-stabilization.json")
    market_gate = read_json(root, market_gate_rel)
    market_bakeoff = read_json(root, market_bakeoff_rel)
    model_design = read_json(root, model_design_rel)
    residual_signal = read_json(root, residual_signal_rel)
    residual_overcorrection = read_json(root, residual_overcorrection_rel)
    completion_exists = (root / t21_completion_rel).is_file()
    platform_blockers = int(platform.get("blocker_count", 13))
    claim_count = int(claims.get("claim_count", 14))
    ready_claim_count = int(claims.get("ready_claim_count", claim_count - int(claims.get("blocked_claim_count", 8))))
    blocked_claim_count = int(claims.get("blocked_claim_count", 8))
    consistency_passed = all(
        check.get("status") == "passed" for check in consistency.get("checks", [])
    ) if isinstance(consistency.get("checks"), list) else False
    t21_status = t21.get("status")
    t21_counts = t21.get("counts", {}) if isinstance(t21.get("counts"), dict) else {}
    stabilization_present = (
        isinstance(stabilization, dict)
        and stabilization.get("status") == "stabilization_snapshot_ready"
        and stabilization.get("research_only") is True
        and stabilization.get("execution_enabled") is False
        and isinstance(stabilization.get("safety"), dict)
        and stabilization["safety"].get("database_writes") is False
        and stabilization["safety"].get("resolver_or_model_changes") is False
    )
    market_gate_present = (
        isinstance(market_gate, dict)
        and market_gate.get("status") == "blocked_market_claim_gate"
        and market_gate.get("research_only") is True
        and market_gate.get("execution_enabled") is False
        and isinstance(market_gate.get("safety"), dict)
        and market_gate["safety"].get("database_writes") is False
        and market_gate["safety"].get("model_training") is False
        and market_gate["safety"].get("ledger_settlement") is False
        and market_gate["safety"].get("market_execution") is False
    )
    market_gate_summary = market_gate.get("summary", {}) if isinstance(market_gate, dict) else {}
    next_market_blocker = market_gate_summary.get("next_single_blocker") if isinstance(market_gate_summary, dict) else None
    model_design_candidate = (
        model_design.get("recommended_candidate", {}) if isinstance(model_design, dict) else {}
    )
    if not isinstance(model_design_candidate, dict):
        model_design_candidate = {}
    model_design_candidate_id = model_design_candidate.get("candidate_id")
    model_design_present = (
        isinstance(model_design, dict)
        and model_design.get("status") == "model_promotability_design_ready"
        and model_design.get("research_only") is True
        and model_design.get("execution_enabled") is False
        and model_design.get("training_allowed") is False
        and model_design.get("promotion_allowed") is False
        and model_design_candidate_id
        in {
            "market_residual_calibration_challenger_v1",
            "side_line_residual_stability_diagnostic_v1",
            "park_nba_residual_modeling_until_new_signal_v1",
        }
        and isinstance(model_design.get("safety"), dict)
        and all(value is False for value in model_design["safety"].values())
    )
    residual_challenger = {}
    if isinstance(market_bakeoff, dict) and isinstance(market_bakeoff.get("challengers"), list):
        for challenger in market_bakeoff["challengers"]:
            if isinstance(challenger, dict) and challenger.get("challenger") == "market_residual_calibration_challenger_v1":
                residual_challenger = challenger
                break
    residual_summary = residual_challenger.get("residual_contribution_summary", {}) if isinstance(residual_challenger, dict) else {}
    if not isinstance(residual_summary, dict):
        residual_summary = {}
    residual_evaluator_present = (
        bool(residual_challenger)
        and residual_challenger.get("status") == "ok"
        and int(residual_challenger.get("tested_rows") or 0) > 0
        and residual_summary.get("base_probability") == "same_timestamp_no_vig_market_probability"
    )
    residual_collapsed_to_market = (
        residual_evaluator_present
        and residual_challenger.get("effective_market_only") is True
        and residual_challenger.get("ties_market_overall") is True
        and residual_summary.get("collapsed_to_market") is True
    )

    canonical_challenger = {}
    if isinstance(market_bakeoff, dict) and isinstance(market_bakeoff.get("challengers"), list):
        for challenger in market_bakeoff["challengers"]:
            if isinstance(challenger, dict) and challenger.get("challenger") == "canonical_side_market_residual_challenger_v1":
                canonical_challenger = challenger
                break
    canonical_summary = (
        canonical_challenger.get("canonical_residual_summary", {})
        if isinstance(canonical_challenger, dict)
        else {}
    )
    if not isinstance(canonical_summary, dict):
        canonical_summary = {}
    canonical_evaluator_present = (
        bool(canonical_challenger)
        and canonical_challenger.get("status") == "ok"
        and int(canonical_challenger.get("tested_rows") or 0) > 0
        and canonical_summary.get("target_shape") == "single_canonical_side_per_market_pair"
    )
    canonical_not_promotable = (
        canonical_evaluator_present
        and canonical_challenger.get("strictly_beats_market_overall") is False
        and (
            float(canonical_challenger.get("brier_delta_model_minus_market") or 0.0) > 0.0
            or float(canonical_challenger.get("log_loss_delta_model_minus_market") or 0.0) > 0.0
            or bool(canonical_challenger.get("blockers"))
        )
    )
    shrinkage_clipped_challenger = {}
    if isinstance(market_bakeoff, dict) and isinstance(market_bakeoff.get("challengers"), list):
        for challenger in market_bakeoff["challengers"]:
            if (
                isinstance(challenger, dict)
                and challenger.get("challenger") == "canonical_side_shrinkage_clipped_residual_challenger_v1"
            ):
                shrinkage_clipped_challenger = challenger
                break
    shrinkage_clipped_summary = (
        shrinkage_clipped_challenger.get("shrinkage_clipping_summary", {})
        if isinstance(shrinkage_clipped_challenger, dict)
        else {}
    )
    if not isinstance(shrinkage_clipped_summary, dict):
        shrinkage_clipped_summary = {}
    shrinkage_clipped_selected = shrinkage_clipped_summary.get("selected_parameter_summary", {})
    if not isinstance(shrinkage_clipped_selected, dict):
        shrinkage_clipped_selected = {}
    shrinkage_clipped_evaluator_present = (
        bool(shrinkage_clipped_challenger)
        and shrinkage_clipped_challenger.get("status") == "ok"
        and int(shrinkage_clipped_challenger.get("tested_rows") or 0) > 0
        and shrinkage_clipped_summary.get("strategy") == "prior_oos_one_se_shrinkage_and_clip_selection"
    )
    shrinkage_clipped_market_parity = (
        shrinkage_clipped_evaluator_present
        and shrinkage_clipped_challenger.get("effective_market_only") is True
        and shrinkage_clipped_challenger.get("ties_market_overall") is True
        and shrinkage_clipped_summary.get("collapsed_to_market") is True
    )
    residual_signal_conclusion = (
        residual_signal.get("conclusion", {}) if isinstance(residual_signal, dict) else {}
    )
    if not isinstance(residual_signal_conclusion, dict):
        residual_signal_conclusion = {}
    residual_signal_mirrored = (
        residual_signal.get("mirrored_pair_diagnostic", {}) if isinstance(residual_signal, dict) else {}
    )
    if not isinstance(residual_signal_mirrored, dict):
        residual_signal_mirrored = {}
    residual_signal_canonical = (
        residual_signal.get("canonical_side_diagnostic", {}) if isinstance(residual_signal, dict) else {}
    )
    if not isinstance(residual_signal_canonical, dict):
        residual_signal_canonical = {}
    residual_signal_present = (
        isinstance(residual_signal, dict)
        and residual_signal.get("status") == "residual_signal_diagnostic_ready"
        and residual_signal.get("research_only") is True
        and residual_signal.get("execution_enabled") is False
        and residual_signal.get("training_allowed") is False
        and residual_signal.get("promotion_allowed") is False
        and isinstance(residual_signal.get("safety"), dict)
        and all(value is False for value in residual_signal["safety"].values())
        and residual_signal_conclusion.get("cause_id") == "two_sided_feature_label_cancellation"
        and int(residual_signal_mirrored.get("pair_rows") or 0) > 0
        and residual_signal_mirrored.get("pair_rows") == residual_signal_mirrored.get("cancelled_pair_rows")
        and residual_signal_mirrored.get("pair_rows") == residual_signal_mirrored.get("same_feature_pair_rows")
    )
    overcorrection_conclusion = (
        residual_overcorrection.get("conclusion", {}) if isinstance(residual_overcorrection, dict) else {}
    )
    if not isinstance(overcorrection_conclusion, dict):
        overcorrection_conclusion = {}
    overcorrection_diagnostics = (
        residual_overcorrection.get("diagnostics", {}) if isinstance(residual_overcorrection, dict) else {}
    )
    if not isinstance(overcorrection_diagnostics, dict):
        overcorrection_diagnostics = {}
    overcorrection_large = overcorrection_diagnostics.get("large_correction", {})
    if not isinstance(overcorrection_large, dict):
        overcorrection_large = {}
    residual_overcorrection_present = (
        isinstance(residual_overcorrection, dict)
        and residual_overcorrection.get("status") == "residual_overcorrection_diagnostic_ready"
        and residual_overcorrection.get("research_only") is True
        and residual_overcorrection.get("execution_enabled") is False
        and residual_overcorrection.get("training_allowed") is False
        and residual_overcorrection.get("promotion_allowed") is False
        and isinstance(residual_overcorrection.get("safety"), dict)
        and all(value is False for value in residual_overcorrection["safety"].values())
        and overcorrection_conclusion.get("cause_id") == "large_correction_overfit"
        and overcorrection_large.get("large_corrections_harmful") is True
    )
    gates = [
        make_gate(
            "platform_macro_truth_gated",
            "blocked",
            [f"Platform readiness still reports {platform_blockers} blockers."],
            [platform_rel],
        ),
        make_gate(
            "claim_registry_consistent",
            "pass" if claim_count == ready_claim_count + blocked_claim_count else "fail",
            [f"Claims: {claim_count}; ready: {ready_claim_count}; blocked: {blocked_claim_count}."],
            [claim_rel],
        ),
        make_gate(
            "platform_readiness_consistency",
            "pass" if consistency_passed else "blocked",
            ["All platform consistency checks passed." if consistency_passed else "Platform consistency checks are missing or not all passed."],
            [consistency_rel],
        ),
        make_gate(
            "t21_completion_note",
            "pass" if completion_exists else "blocked",
            ["T21 completion note exists." if completion_exists else "T21 completion note is missing."],
            [t21_completion_rel] if completion_exists else [t21_rel],
        ),
        make_gate(
            "t21_read_only_diagnostic",
            "pass" if t21_status == "diagnostic_ready_read_only" else "blocked",
            [f"T21 status: {t21_status or 'missing'}."],
            [t21_rel],
        ),
        make_gate(
            "dirty_tree_classified",
            "pass" if stabilization_present else "blocked",
            [
                (
                    "NBA stabilization artifact classifies dirty tree and preserves annex truth."
                    if stabilization_present
                    else "NBA dirty-tree stabilization artifact is missing or unsafe."
                )
            ],
            [
                path
                for path in [
                    "scripts/codex_nba_stabilization_status.py",
                    "tests/test_codex_nba_stabilization_status.py",
                    "docs/codex/artifacts/nba-stabilization-latest/nba-stabilization.json",
                    "docs/codex/artifacts/nba-stabilization-latest/nba-stabilization.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "market_claim_gate_refreshed",
            "blocked"
            if market_gate_present and next_market_blocker == "model_promotability"
            else ("pass" if market_gate_present else "blocked"),
            [
                (
                    "Market claim gate refreshed; next blocker is model_promotability."
                    if market_gate_present and next_market_blocker == "model_promotability"
                    else (
                        f"Market claim gate refreshed; next blocker is {next_market_blocker}."
                        if market_gate_present
                        else "Market claim gate summary is missing or unsafe."
                    )
                )
            ],
            [
                path
                for path in [
                    "scripts/codex_nba_market_claim_gate.py",
                    "tests/test_codex_nba_market_claim_gate.py",
                    market_gate_rel,
                    "docs/codex/artifacts/nba-market-claim-gate-latest/nba-market-claim-gate.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "model_promotability_design_ready",
            "pass" if model_design_present else "blocked",
            [
                (
                    f"Model-promotability design is ready for {model_design_candidate_id}."
                    if model_design_present
                    else "Model-promotability design artifact is missing or unsafe."
                )
            ],
            [
                path
                for path in [
                    "scripts/codex_nba_model_promotability_design.py",
                    "tests/test_codex_nba_model_promotability_design.py",
                    model_design_rel,
                    "docs/codex/artifacts/nba-model-promotability-latest/nba-model-promotability-design.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "market_residual_evaluator_ran",
            "pass" if residual_evaluator_present else "blocked",
            [
                (
                    "Residual evaluator ran; current disposition is market parity collapse."
                    if residual_collapsed_to_market
                    else (
                        "Residual evaluator ran."
                        if residual_evaluator_present
                        else "Residual evaluator evidence is missing from challenger bakeoff."
                    )
                )
            ],
            [
                path
                for path in [
                    "handicapper/market_challenger_bakeoff.py",
                    "tests/test_handicapper/test_market_model_diagnostics_t10.py",
                    market_bakeoff_rel,
                    "docs/codex/artifacts/nba-market-claim-gate-latest/market-challenger-bakeoff.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "residual_signal_diagnostic_ready",
            "pass" if residual_signal_present else "blocked",
            [
                (
                    "Residual-signal diagnostic explains collapse as two-sided feature/label cancellation."
                    if residual_signal_present
                    else "Residual-signal diagnostic artifact is missing or unsafe."
                )
            ],
            [
                path
                for path in [
                    "scripts/codex_nba_residual_signal_diagnostic.py",
                    "tests/test_codex_nba_residual_signal_diagnostic.py",
                    residual_signal_rel,
                    "docs/codex/artifacts/nba-residual-signal-latest/nba-residual-signal-diagnostic.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "canonical_residual_evaluator_ran",
            "pass" if canonical_evaluator_present else "blocked",
            [
                (
                    "Canonical-side residual evaluator ran and remains not promotable."
                    if canonical_not_promotable
                    else (
                        "Canonical-side residual evaluator ran."
                        if canonical_evaluator_present
                        else "Canonical-side residual evaluator evidence is missing from challenger bakeoff."
                    )
                )
            ],
            [
                path
                for path in [
                    "handicapper/market_challenger_bakeoff.py",
                    "tests/test_handicapper/test_market_model_diagnostics_t10.py",
                    market_bakeoff_rel,
                    "docs/codex/artifacts/nba-market-claim-gate-latest/market-challenger-bakeoff.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "residual_overcorrection_diagnostic_ready",
            "pass" if residual_overcorrection_present else "blocked",
            [
                (
                    "Residual-overcorrection diagnostic shows large canonical residual corrections are harmful."
                    if residual_overcorrection_present
                    else "Residual-overcorrection diagnostic artifact is missing or unsafe."
                )
            ],
            [
                path
                for path in [
                    "scripts/codex_nba_residual_overcorrection_diagnostic.py",
                    "tests/test_codex_nba_residual_overcorrection_diagnostic.py",
                    residual_overcorrection_rel,
                    "docs/codex/artifacts/nba-residual-overcorrection-latest/nba-residual-overcorrection-diagnostic.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "shrinkage_clipped_residual_evaluator_ran",
            "pass" if shrinkage_clipped_evaluator_present else "blocked",
            [
                (
                    "Prior-season shrinkage/clipping evaluator ran and collapsed to market parity."
                    if shrinkage_clipped_market_parity
                    else (
                        "Prior-season shrinkage/clipping evaluator ran."
                        if shrinkage_clipped_evaluator_present
                        else "Prior-season shrinkage/clipping evaluator evidence is missing from challenger bakeoff."
                    )
                )
            ],
            [
                path
                for path in [
                    "handicapper/market_challenger_bakeoff.py",
                    "tests/test_handicapper/test_market_model_diagnostics_t10.py",
                    market_bakeoff_rel,
                    "docs/codex/artifacts/nba-market-claim-gate-latest/market-challenger-bakeoff.md",
                    "NEXT_DIRECTIVE_2026-06-28_NBA_PRIOR_SEASON_SHRINKAGE_CLIPPING_EVALUATOR.md",
                    "COMPLETION_REPORT_2026-06-28_NBA_PRIOR_SEASON_SHRINKAGE_CLIPPING_EVALUATOR_FULFILLED.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "dirty_tree_risk",
            "blocked" if status["git"]["dirty_counts"]["total"] >= 500 else ("warn" if status["git"]["dirty_counts"]["total"] else "pass"),
            [f"Dirty paths: {status['git']['dirty_counts']['total']}."],
            [],
        ),
    ]
    evidence = {
        "status": (
            "macro_partial_truth_shrinkage_clipped_residual_market_parity"
            if completion_exists
            and stabilization_present
            and market_gate_present
            and next_market_blocker == "model_promotability"
            and model_design_present
            and model_design_candidate_id == "park_nba_residual_modeling_until_new_signal_v1"
            and residual_collapsed_to_market
            and residual_signal_present
            and canonical_not_promotable
            and residual_overcorrection_present
            and shrinkage_clipped_market_parity
            else (
            "macro_partial_truth_residual_overcorrection_large_correction_overfit"
            if completion_exists
            and stabilization_present
            and market_gate_present
            and next_market_blocker == "model_promotability"
            and model_design_present
            and residual_collapsed_to_market
            and residual_signal_present
            and canonical_not_promotable
            and residual_overcorrection_present
            else (
            "macro_partial_truth_canonical_residual_not_promotable"
            if completion_exists
            and stabilization_present
            and market_gate_present
            and next_market_blocker == "model_promotability"
            and model_design_present
            and residual_collapsed_to_market
            and residual_signal_present
            and canonical_not_promotable
            else (
            "macro_partial_truth_residual_signal_cancellation_explained"
            if completion_exists
            and stabilization_present
            and market_gate_present
            and next_market_blocker == "model_promotability"
            and model_design_present
            and residual_collapsed_to_market
            and residual_signal_present
            else (
            "macro_partial_truth_residual_evaluator_collapsed_to_market"
            if completion_exists
            and stabilization_present
            and market_gate_present
            and next_market_blocker == "model_promotability"
            and model_design_present
            and residual_collapsed_to_market
            else (
            "macro_partial_truth_model_promotability_design_ready"
            if completion_exists
            and stabilization_present
            and market_gate_present
            and next_market_blocker == "model_promotability"
            and model_design_present
            else (
            "macro_partial_truth_market_gate_blocked_model_promotability"
            if completion_exists
            and stabilization_present
            and market_gate_present
            and next_market_blocker == "model_promotability"
            else (
            "macro_partial_truth_stabilized_dirty_classified"
            if completion_exists and stabilization_present
            else "macro_partial_truth_gated"
            )
            )
            )
            )
            )
            )
            )
        ),
        "latest_artifacts": artifacts,
        "hashes": hashes,
        "blocker_count": platform_blockers,
        "metrics": {
            "claim_count": claim_count,
            "ready_claim_count": ready_claim_count,
            "blocked_claim_count": blocked_claim_count,
            "consistency_check_count": consistency.get("check_count"),
            "consistency_passed": consistency_passed,
            "t21_status": t21_status,
            "t21_counts": t21_counts,
            "stabilization": json_brief(stabilization)
            if stabilization is not None
            else {"missing": True},
            "stabilization_present": stabilization_present,
            "market_claim_gate": json_brief(market_gate)
            if market_gate is not None
            else {"missing": True},
            "market_claim_gate_present": market_gate_present,
            "market_claim_next_blocker": next_market_blocker,
            "market_claim_model_gate_ready": market_gate_summary.get("model_gate_ready")
            if isinstance(market_gate_summary, dict)
            else None,
            "market_claim_injury_gate_ready": market_gate_summary.get("injury_gate_ready")
            if isinstance(market_gate_summary, dict)
            else None,
            "market_claim_ledger_gate_ready": market_gate_summary.get("ledger_gate_ready")
            if isinstance(market_gate_summary, dict)
            else None,
            "model_promotability_design": json_brief(model_design)
            if model_design is not None
            else {"missing": True},
            "model_promotability_design_present": model_design_present,
            "model_promotability_candidate": model_design_candidate_id,
            "model_promotability_first_market_focus": model_design_candidate.get("first_market_focus"),
            "market_residual_evaluator_present": residual_evaluator_present,
            "market_residual_collapsed_to_market": residual_collapsed_to_market,
            "market_residual_tested_rows": residual_challenger.get("tested_rows")
            if isinstance(residual_challenger, dict)
            else None,
            "market_residual_max_abs_correction": residual_summary.get("max_abs_correction"),
            "market_residual_variable_feature_count": (
                residual_summary.get("feature_signal", {}).get("variable_feature_count")
                if isinstance(residual_summary.get("feature_signal"), dict)
                else None
            ),
            "residual_signal_diagnostic": json_brief(residual_signal)
            if residual_signal is not None
            else {"missing": True},
            "residual_signal_diagnostic_present": residual_signal_present,
            "residual_signal_cause_id": residual_signal_conclusion.get("cause_id"),
            "residual_signal_pair_rows": residual_signal_mirrored.get("pair_rows"),
            "residual_signal_cancelled_pair_rows": residual_signal_mirrored.get("cancelled_pair_rows"),
            "residual_signal_same_feature_pair_rows": residual_signal_mirrored.get("same_feature_pair_rows"),
            "residual_signal_canonical_max_abs_feature_correlation": residual_signal_canonical.get(
                "max_abs_feature_correlation"
            ),
            "canonical_residual_evaluator_present": canonical_evaluator_present,
            "canonical_residual_not_promotable": canonical_not_promotable,
            "canonical_residual_tested_rows": canonical_challenger.get("tested_rows")
            if isinstance(canonical_challenger, dict)
            else None,
            "canonical_residual_brier_delta_model_minus_market": canonical_challenger.get(
                "brier_delta_model_minus_market"
            )
            if isinstance(canonical_challenger, dict)
            else None,
            "canonical_residual_log_loss_delta_model_minus_market": canonical_challenger.get(
                "log_loss_delta_model_minus_market"
            )
            if isinstance(canonical_challenger, dict)
            else None,
            "canonical_residual_max_abs_correction": canonical_summary.get("max_abs_correction"),
            "canonical_residual_canonical_rows": canonical_summary.get("canonical_rows"),
            "canonical_residual_dropped_mirrored_rows": canonical_summary.get("dropped_mirrored_rows"),
            "residual_overcorrection_diagnostic": json_brief(residual_overcorrection)
            if residual_overcorrection is not None
            else {"missing": True},
            "residual_overcorrection_diagnostic_present": residual_overcorrection_present,
            "residual_overcorrection_cause_id": overcorrection_conclusion.get("cause_id"),
            "residual_overcorrection_large_rows": overcorrection_large.get("large_rows"),
            "residual_overcorrection_large_corrections_harmful": overcorrection_large.get(
                "large_corrections_harmful"
            ),
            "residual_overcorrection_large_brier_delta_model_minus_market": overcorrection_large.get(
                "large_brier_delta_model_minus_market"
            ),
            "residual_overcorrection_large_log_loss_delta_model_minus_market": overcorrection_large.get(
                "large_log_loss_delta_model_minus_market"
            ),
            "shrinkage_clipped_residual_evaluator_present": shrinkage_clipped_evaluator_present,
            "shrinkage_clipped_residual_market_parity": shrinkage_clipped_market_parity,
            "shrinkage_clipped_residual_tested_rows": shrinkage_clipped_challenger.get("tested_rows")
            if isinstance(shrinkage_clipped_challenger, dict)
            else None,
            "shrinkage_clipped_zero_shrinkage_season_count": shrinkage_clipped_selected.get(
                "zero_shrinkage_season_count"
            ),
            "shrinkage_clipped_nonzero_shrinkage_season_count": shrinkage_clipped_selected.get(
                "nonzero_shrinkage_season_count"
            ),
            "shrinkage_clipped_mean_abs_correction": shrinkage_clipped_summary.get("mean_abs_correction"),
            "shrinkage_clipped_max_abs_correction": shrinkage_clipped_summary.get("max_abs_correction"),
            "dirty_total": status["git"]["dirty_counts"]["total"],
        },
    }
    return finish_status(status, evidence, gates)


def nfl_status(root: Path) -> dict[str, Any]:
    status = base_status("nfl_quant_glm51_greenfield", root)
    completion_reports = latest_matching(root, ["COMPLETION_REPORT_*.md", "docs/**/COMPLETION_REPORT_*.md"], limit=5)
    validation_artifacts = latest_matching(
        root,
        ["**/*validation*ledger*.json", "**/*validation*ledger*.md", "**/*profile*validation*.json", "**/*artifact*audit*.json"],
        limit=8,
    )
    artifact_paths = [
        "Makefile",
        "docs/codex/current-state.md",
        "scripts/codex_nfl_governance_export.py",
        "tests/test_codex_nfl_governance_export.py",
        "src/nfl_quant/data/forward_context.py",
        "src/nfl_quant/data/forward_context_seed.py",
        "src/nfl_quant/data/forward_context_manual_drop.py",
        "src/nfl_quant/data/forward_context_availability.py",
        "src/nfl_quant/data/forward_context_adjustments.py",
        "src/nfl_quant/data/odds_api_market_reference.py",
        "src/nfl_quant/data/consensus_market.py",
        "src/nfl_quant/data/market_snapshot_ledger.py",
        "src/nfl_quant/validation/line_backtest.py",
        "tests/test_forward_context.py",
        "tests/test_consensus_market.py",
        "tests/test_market_snapshot_ledger.py",
        "tests/test_historical_line_backtest.py",
        "src/nfl_quant/pricing/fair_lines.py",
        "tests/test_fair_lines.py",
        "docs/codex/artifacts/nfl-governance-latest/nfl-governance.json",
        "docs/codex/artifacts/nfl-governance-latest/nfl-governance.md",
        "docs/codex/artifacts/nfl-line-readiness-latest/line-readiness-summary.json",
        "docs/codex/artifacts/nfl-line-readiness-latest/line-readiness-summary.md",
        "docs/codex/artifacts/nfl-line-readiness-latest/fair-line-review.json",
        "docs/codex/artifacts/nfl-line-readiness-latest/fair-line-review.md",
        "docs/codex/artifacts/nfl-line-readiness-latest/fair-lines-S2026-W01.csv",
        "docs/codex/artifacts/nfl-forward-context-latest/forward-context-readiness.json",
        "docs/codex/artifacts/nfl-forward-context-latest/forward-context-readiness.md",
        "docs/codex/artifacts/nfl-forward-context-seed-latest/forward-context-seed.json",
        "docs/codex/artifacts/nfl-forward-context-seed-latest/forward-context-seed.md",
        "docs/codex/artifacts/nfl-forward-context-manual-drop-latest/forward-context-manual-drop-readiness.json",
        "docs/codex/artifacts/nfl-forward-context-manual-drop-latest/forward-context-manual-drop-readiness.md",
        "docs/codex/artifacts/nfl-forward-context-availability-latest/forward-context-availability.json",
        "docs/codex/artifacts/nfl-forward-context-availability-latest/forward-context-availability.md",
        "docs/codex/artifacts/nfl-forward-context-adjustments-latest/forward-context-adjustments.json",
        "docs/codex/artifacts/nfl-forward-context-adjustments-latest/forward-context-adjustments.md",
        "docs/codex/artifacts/nfl-forward-context-adjustments-latest/forward-context-adjustments.csv",
        "docs/codex/artifacts/nfl-odds-api-market-reference-latest/odds-api-market-reference.json",
        "docs/codex/artifacts/nfl-odds-api-market-reference-latest/odds-api-market-reference.md",
        "docs/codex/artifacts/nfl-consensus-market-latest/consensus-market-reference.json",
        "docs/codex/artifacts/nfl-consensus-market-latest/consensus-market-reference.md",
        "docs/codex/artifacts/nfl-consensus-market-latest/consensus-market-reference.csv",
        "docs/codex/artifacts/nfl-market-snapshot-ledger-latest/market-snapshot-ledger.json",
        "docs/codex/artifacts/nfl-market-snapshot-ledger-latest/market-snapshot-ledger.md",
        "docs/codex/artifacts/nfl-market-snapshot-ledger-latest/market-snapshot-ledger.csv",
        "docs/codex/artifacts/nfl-market-snapshot-ledger-latest/closing-reference-candidates.csv",
        "docs/codex/artifacts/nfl-closing-line-validation-latest/closing-line-validation.json",
        "docs/codex/artifacts/nfl-closing-line-validation-latest/closing-line-validation.md",
        "docs/codex/artifacts/nfl-historical-line-backtest-latest/historical-line-backtest.json",
        "docs/codex/artifacts/nfl-historical-line-backtest-latest/historical-line-backtest.md",
        "docs/codex/artifacts/nfl-historical-line-backtest-latest/historical-line-backtest.csv",
        "docs/codex/manual-drops/nfl-forward-context-manual-drop-contract.md",
        "docs/codex/tranches/2026-07-01-nfl-first-class-historical-line-backtest.md",
        "docs/codex/tranches/2026-07-01-nfl-consensus-market-and-projected-qb-context.md",
        "docs/codex/tranches/2026-06-30-nfl-line-data-readiness-and-profiled-slate.md",
        "docs/codex/tranches/2026-06-28-nfl-governance-evidence-freshness-hardening.md",
        "docs/codex/tranches/2026-06-27-nfl-governance-macro-export.md",
        "NEXT_DIRECTIVE_2026-06-30_NFL_LINE_DATA_READINESS_AND_PROFILED_SLATE.md",
        "NEXT_DIRECTIVE_2026-06-28_NFL_GOVERNANCE_EVIDENCE_FRESHNESS_HARDENING.md",
        "NEXT_DIRECTIVE_2026-06-27_NFL_GOVERNANCE_MACRO_EXPORT.md",
        "COMPLETION_REPORT_2026-06-30_NFL_LINE_DATA_READINESS_AND_PROFILED_SLATE_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-28_NFL_GOVERNANCE_EVIDENCE_FRESHNESS_HARDENING_FULFILLED.md",
        "COMPLETION_REPORT_2026-06-27_NFL_GOVERNANCE_MACRO_EXPORT_FULFILLED.md",
        *completion_reports,
        *validation_artifacts,
    ]
    artifacts, hashes = artifact_pack(root, artifact_paths)
    makefile = read_text(root, "Makefile")
    completion_text = "\n".join(read_text(root, path, max_chars=80_000) for path in completion_reports)
    governance_export = read_json(root, "docs/codex/artifacts/nfl-governance-latest/nfl-governance.json")
    line_readiness = read_json(root, "docs/codex/artifacts/nfl-line-readiness-latest/line-readiness-summary.json")
    fair_line_review = read_json(root, "docs/codex/artifacts/nfl-line-readiness-latest/fair-line-review.json")
    forward_context = read_json(root, "docs/codex/artifacts/nfl-forward-context-latest/forward-context-readiness.json")
    forward_context_seed = read_json(root, "docs/codex/artifacts/nfl-forward-context-seed-latest/forward-context-seed.json")
    manual_drop = read_json(
        root,
        "docs/codex/artifacts/nfl-forward-context-manual-drop-latest/forward-context-manual-drop-readiness.json",
    )
    forward_context_availability = read_json(
        root,
        "docs/codex/artifacts/nfl-forward-context-availability-latest/forward-context-availability.json",
    )
    forward_context_adjustments = read_json(
        root,
        "docs/codex/artifacts/nfl-forward-context-adjustments-latest/forward-context-adjustments.json",
    )
    odds_api_market_reference = read_json(
        root,
        "docs/codex/artifacts/nfl-odds-api-market-reference-latest/odds-api-market-reference.json",
    )
    consensus_market = read_json(
        root,
        "docs/codex/artifacts/nfl-consensus-market-latest/consensus-market-reference.json",
    )
    market_snapshot_ledger = read_json(
        root,
        "docs/codex/artifacts/nfl-market-snapshot-ledger-latest/market-snapshot-ledger.json",
    )
    closing_line_validation = read_json(
        root,
        "docs/codex/artifacts/nfl-closing-line-validation-latest/closing-line-validation.json",
    )
    historical_line_backtest = read_json(
        root,
        "docs/codex/artifacts/nfl-historical-line-backtest-latest/historical-line-backtest.json",
    )
    governance_snapshots = (
        governance_export.get("evidence_snapshots", {}) if isinstance(governance_export, dict) else {}
    )
    if not isinstance(governance_snapshots, dict):
        governance_snapshots = {}
    profile_validation_snapshot = governance_snapshots.get("profile_validation_ci", {})
    if not isinstance(profile_validation_snapshot, dict):
        profile_validation_snapshot = {}
    artifact_audit_snapshot = governance_snapshots.get("artifact_audit_ci", {})
    if not isinstance(artifact_audit_snapshot, dict):
        artifact_audit_snapshot = {}
    has_status_json = "status" in makefile and "--json" in read_text(root, "src/nfl_quant/cli.py")
    has_artifact_audit = "artifact-audit-ci" in makefile or "ci-artifact-audit-smoke" in makefile
    has_profile_validation = "profile-validation-ci" in makefile
    governance_snapshots_ready = (
        profile_validation_snapshot.get("gate_status") == "pass"
        and artifact_audit_snapshot.get("gate_status") == "pass"
        and profile_validation_snapshot.get("fresh") is True
        and artifact_audit_snapshot.get("fresh") is True
    )
    governance_export_present = (
        isinstance(governance_export, dict)
        and governance_export.get("status") == "governance_macro_export_ready"
        and governance_export.get("research_only") is True
        and governance_export.get("execution_enabled") is False
        and isinstance(governance_export.get("safety"), dict)
        and governance_export["safety"].get("data_fetches") is False
        and governance_export["safety"].get("pricing_model_simulation_changes") is False
        and governance_snapshots_ready
    )
    line_profiled_slate = line_readiness.get("profiled_slate", {}) if isinstance(line_readiness, dict) else {}
    if not isinstance(line_profiled_slate, dict):
        line_profiled_slate = {}
    line_model_evidence = line_readiness.get("model_evidence", {}) if isinstance(line_readiness, dict) else {}
    if not isinstance(line_model_evidence, dict):
        line_model_evidence = {}
    line_safety = line_readiness.get("safety", {}) if isinstance(line_readiness, dict) else {}
    if not isinstance(line_safety, dict):
        line_safety = {}
    fair_lines_path_value = line_profiled_slate.get("fair_lines_csv")
    fair_lines_present = _path_value_exists(root, fair_lines_path_value)
    fair_line_review_safety = fair_line_review.get("safety", {}) if isinstance(fair_line_review, dict) else {}
    if not isinstance(fair_line_review_safety, dict):
        fair_line_review_safety = {}
    fair_line_review_ready = (
        isinstance(fair_line_review, dict)
        and fair_line_review.get("status") == "fair_line_review_ready_research_only"
        and fair_line_review.get("research_only") is True
        and int(fair_line_review.get("row_count") or 0) > 0
        and fair_line_review.get("model_line_columns_present") is True
        and fair_line_review_safety.get("market_execution") is False
        and fair_line_review_safety.get("account_or_order_paths") is False
        and fair_line_review_safety.get("database_writes") is False
        and fair_line_review_safety.get("staking_or_sizing_guidance") is False
        and fair_line_review_safety.get("model_probability_changes") is False
    )
    line_readiness_ready = (
        isinstance(line_readiness, dict)
        and line_readiness.get("status") == "line_readiness_profiled_slate_available_research_only"
        and line_safety.get("execution_enabled") is False
        and line_safety.get("account_or_order_paths_used") is False
        and line_safety.get("database_writes") is False
        and fair_lines_present
        and fair_line_review_ready
        and int(line_profiled_slate.get("slate_rows") or 0) > 0
        and line_model_evidence.get("validation_status") == "pass"
        and line_model_evidence.get("validation_decision") == "promotable"
    )
    forward_context_status = forward_context.get("status") if isinstance(forward_context, dict) else None
    forward_context_safety = forward_context.get("safety", {}) if isinstance(forward_context, dict) else {}
    if not isinstance(forward_context_safety, dict):
        forward_context_safety = {}
    forward_context_safe = (
        isinstance(forward_context, dict)
        and forward_context.get("research_only") is True
        and forward_context_safety.get("database_writes") is False
        and forward_context_safety.get("market_execution") is False
        and forward_context_safety.get("account_or_order_paths") is False
        and forward_context_safety.get("model_probability_changes") is False
    )
    forward_context_gate_status = (
        "pass"
        if forward_context_status == "forward_context_ready_safe_inputs" and forward_context_safe
        else "warn"
        if forward_context_status == "forward_context_partial_safe_inputs" and forward_context_safe
        else "blocked"
    )
    manual_drop_status = manual_drop.get("status") if isinstance(manual_drop, dict) else None
    manual_drop_safety = manual_drop.get("safety", {}) if isinstance(manual_drop, dict) else {}
    manual_drop_sidecar = manual_drop.get("sidecar", {}) if isinstance(manual_drop, dict) else {}
    if not isinstance(manual_drop_safety, dict):
        manual_drop_safety = {}
    if not isinstance(manual_drop_sidecar, dict):
        manual_drop_sidecar = {}
    manual_drop_safe = (
        isinstance(manual_drop, dict)
        and manual_drop.get("research_only") is True
        and manual_drop.get("drop_dir_inside_repo") is False
        and manual_drop_sidecar.get("status") == "safe"
        and manual_drop_safety.get("database_writes") is False
        and manual_drop_safety.get("market_execution") is False
        and manual_drop_safety.get("account_or_order_paths") is False
        and manual_drop_safety.get("model_probability_changes") is False
        and manual_drop_safety.get("raw_payloads_copied_to_repo") is False
    )
    manual_drop_gate_status = (
        "pass"
        if manual_drop_status == "manual_drop_ready_safe_inputs" and manual_drop_safe
        else "warn"
        if manual_drop_status == "manual_drop_partial_safe_inputs" and manual_drop_safe
        else "blocked"
        if isinstance(manual_drop, dict)
        else "warn"
    )
    availability_status = (
        forward_context_availability.get("status")
        if isinstance(forward_context_availability, dict)
        else None
    )
    availability_safety = (
        forward_context_availability.get("safety")
        if isinstance(forward_context_availability, dict)
        else {}
    )
    if not isinstance(availability_safety, dict):
        availability_safety = {}
    availability_safe = (
        isinstance(forward_context_availability, dict)
        and forward_context_availability.get("research_only") is True
        and availability_safety.get("provider_api_calls") is False
        and availability_safety.get("database_writes") is False
        and availability_safety.get("market_execution") is False
        and availability_safety.get("account_or_order_paths") is False
        and availability_safety.get("model_probability_changes") is False
        and availability_safety.get("raw_payloads_copied_to_repo") is False
    )
    availability_gate_status = (
        "pass"
        if availability_status
        in {
            "forward_context_availability_not_yet_due",
            "forward_context_availability_ready",
        }
        and availability_safe
        else "warn"
        if availability_status == "forward_context_availability_due_now" and availability_safe
        else "blocked"
        if isinstance(forward_context_availability, dict)
        else "warn"
    )
    odds_api_market_ready = (
        isinstance(odds_api_market_reference, dict)
        and odds_api_market_reference.get("status") == "odds_api_market_reference_ready"
        and odds_api_market_reference.get("research_only") is True
        and int(odds_api_market_reference.get("blocker_count") or 0) == 0
        and int(odds_api_market_reference.get("derived_market_reference_row_count") or 0) > 0
    )
    consensus_market_ready = (
        isinstance(consensus_market, dict)
        and consensus_market.get("status") == "consensus_market_ready"
        and consensus_market.get("research_only") is True
        and int(consensus_market.get("blocker_count") or 0) == 0
        and int(consensus_market.get("consensus_row_count") or 0) > 0
    )
    current_market_gate_status = "pass" if consensus_market_ready else "warn"
    market_snapshot_ledger_ready = (
        isinstance(market_snapshot_ledger, dict)
        and market_snapshot_ledger.get("status")
        in {
            "market_snapshot_ledger_ready_current_only",
            "market_snapshot_ledger_ready_with_closing_candidates",
        }
        and market_snapshot_ledger.get("research_only") is True
        and int(market_snapshot_ledger.get("blocker_count") or 0) == 0
        and int(market_snapshot_ledger.get("ledger_row_count") or 0) > 0
    )
    market_snapshot_ledger_gate_status = "pass" if market_snapshot_ledger_ready else "warn"
    closing_line_status = (
        closing_line_validation.get("status") if isinstance(closing_line_validation, dict) else None
    )
    closing_line_gate_status = (
        "pass"
        if closing_line_status == "closing_line_validation_ready_research_only"
        else "warn"
        if closing_line_status == "closing_line_validation_blocked_no_closing_reference"
        else "warn"
    )
    historical_line_backtest_safety = (
        historical_line_backtest.get("safety", {}) if isinstance(historical_line_backtest, dict) else {}
    )
    if not isinstance(historical_line_backtest_safety, dict):
        historical_line_backtest_safety = {}
    historical_line_backtest_ready = (
        isinstance(historical_line_backtest, dict)
        and historical_line_backtest.get("status") == "historical_line_backtest_ready_research_only"
        and historical_line_backtest.get("research_only") is True
        and int(historical_line_backtest.get("blocker_count") or 0) == 0
        and int(historical_line_backtest.get("row_count") or 0) > 0
        and historical_line_backtest_safety.get("provider_api_calls") is False
        and historical_line_backtest_safety.get("paid_calls") is False
        and historical_line_backtest_safety.get("database_writes") is False
        and historical_line_backtest_safety.get("market_execution") is False
        and historical_line_backtest_safety.get("account_or_order_paths") is False
        and historical_line_backtest_safety.get("staking_or_sizing_guidance") is False
        and historical_line_backtest_safety.get("model_probability_changes") is False
    )
    historical_line_backtest_gate_status = "pass" if historical_line_backtest_ready else "warn"
    passed_match = re.search(r"(\d+)\s+passed", completion_text)
    tests_passed = int(passed_match.group(1)) if passed_match else None
    gates = [
        make_gate(
            "offline_status_json_available",
            "pass" if has_status_json else "blocked",
            ["Existing CLI exposes offline status JSON." if has_status_json else "Could not confirm offline status JSON support."],
            ["Makefile", "src/nfl_quant/cli.py"],
        ),
        make_gate(
            "artifact_audit_gate_available",
            "pass" if has_artifact_audit else "blocked",
            ["Artifact audit CI targets are present." if has_artifact_audit else "Artifact audit CI targets were not found."],
            ["Makefile"],
        ),
        make_gate(
            "profile_validation_gate_available",
            "pass" if has_profile_validation else "blocked",
            ["Profile validation CI target is present." if has_profile_validation else "Profile validation CI target was not found."],
            ["Makefile"],
        ),
        make_gate(
            "completion_report_evidence",
            "pass" if completion_reports else "warn",
            [f"Latest completion reports found: {len(completion_reports)}." if completion_reports else "No completion report found."],
            completion_reports,
        ),
        make_gate(
            "governance_macro_export_ready",
            "pass" if governance_export_present else "blocked",
            [
                (
                    "NFL governance macro export is present, safe, and backed by fresh governance evidence snapshots."
                    if governance_export_present
                    else "NFL governance macro export is missing, unsafe, or stale."
                )
            ],
            [
                path
                for path in [
                    "scripts/codex_nfl_governance_export.py",
                    "tests/test_codex_nfl_governance_export.py",
                    "docs/codex/artifacts/nfl-governance-latest/nfl-governance.json",
                    "docs/codex/artifacts/nfl-governance-latest/nfl-governance.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "governance_evidence_snapshots_fresh",
            "pass" if governance_snapshots_ready else "blocked",
            [
                (
                    "Profile-validation and artifact-audit evidence snapshots are fresh and pass."
                    if governance_snapshots_ready
                    else "Profile-validation or artifact-audit evidence snapshots are missing, stale, or not passing."
                )
            ],
            [
                path
                for path in [
                    "docs/codex/artifacts/nfl-governance-latest/nfl-governance.json",
                    "docs/codex/artifacts/nfl-governance-latest/nfl-governance.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "line_readiness_packet_available",
            "pass" if line_readiness_ready else "warn",
            [
                (
                    "Profiled fair-line packet is present, safe, promotable-profile backed, and has model spread/total fair-line review evidence."
                    if line_readiness_ready
                    else "Profiled fair-line packet is missing, unsafe, not promotable-profile backed, or lacks model spread/total fair-line review evidence."
                )
            ],
            [
                path
                for path in [
                    "docs/codex/artifacts/nfl-line-readiness-latest/line-readiness-summary.json",
                    "docs/codex/artifacts/nfl-line-readiness-latest/line-readiness-summary.md",
                    "docs/codex/artifacts/nfl-line-readiness-latest/fair-line-review.json",
                    "docs/codex/artifacts/nfl-line-readiness-latest/fair-line-review.md",
                    "docs/codex/artifacts/nfl-line-readiness-latest/fair-lines-S2026-W01.csv",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "forward_context_readiness",
            forward_context_gate_status,
            [
                (
                    "Forward-context gates are ready."
                    if forward_context_gate_status == "pass"
                    else "Forward-context report is partial: rosters/schedules exist, but injury/depth/weather/QB context is incomplete."
                    if forward_context_gate_status == "warn"
                    else "Forward-context report is missing, unsafe, or blocked on core schedule/roster context."
                )
            ],
            [
                path
                for path in [
                    "docs/codex/artifacts/nfl-forward-context-latest/forward-context-readiness.json",
                    "docs/codex/artifacts/nfl-forward-context-latest/forward-context-readiness.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "forward_context_manual_drop_readiness",
            manual_drop_gate_status,
            [
                (
                    "Forward-context manual-drop inputs are safe and complete."
                    if manual_drop_gate_status == "pass"
                    else "Forward-context manual-drop inputs are safe but incomplete."
                    if manual_drop_gate_status == "warn" and manual_drop_safe
                    else "Forward-context manual-drop report is missing or blocked by safety/sidecar gates."
                )
            ],
            [
                path
                for path in [
                    "docs/codex/artifacts/nfl-forward-context-manual-drop-latest/forward-context-manual-drop-readiness.json",
                    "docs/codex/artifacts/nfl-forward-context-manual-drop-latest/forward-context-manual-drop-readiness.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "forward_context_availability_window",
            availability_gate_status,
            [
                (
                    "Forward-context availability calendar says missing inputs are not due yet."
                    if availability_status == "forward_context_availability_not_yet_due"
                    else "Forward-context availability calendar says missing inputs are due now."
                    if availability_status == "forward_context_availability_due_now"
                    else "Forward-context availability calendar is ready."
                    if availability_status == "forward_context_availability_ready"
                    else "Forward-context availability calendar is missing or blocked."
                )
            ],
            [
                path
                for path in [
                    "docs/codex/artifacts/nfl-forward-context-availability-latest/forward-context-availability.json",
                    "docs/codex/artifacts/nfl-forward-context-availability-latest/forward-context-availability.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "current_market_reference_ready",
            current_market_gate_status,
            [
                (
                    "Consensus current-market reference is ready and backed by a bounded Odds API capture."
                    if consensus_market_ready
                    else "Consensus current-market reference is missing or partial."
                )
            ],
            [
                path
                for path in [
                    "docs/codex/artifacts/nfl-odds-api-market-reference-latest/odds-api-market-reference.json",
                    "docs/codex/artifacts/nfl-consensus-market-latest/consensus-market-reference.json",
                    "docs/codex/artifacts/nfl-consensus-market-latest/consensus-market-reference.csv",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "market_snapshot_ledger_ready",
            market_snapshot_ledger_gate_status,
            [
                (
                    "Market snapshot ledger is present and classifies market rows by phase."
                    if market_snapshot_ledger_ready
                    else "Market snapshot ledger is missing or blocked, so current/open/closing market phases are not auditable."
                )
            ],
            [
                path
                for path in [
                    "docs/codex/artifacts/nfl-market-snapshot-ledger-latest/market-snapshot-ledger.json",
                    "docs/codex/artifacts/nfl-market-snapshot-ledger-latest/market-snapshot-ledger.md",
                    "docs/codex/artifacts/nfl-market-snapshot-ledger-latest/market-snapshot-ledger.csv",
                    "docs/codex/artifacts/nfl-market-snapshot-ledger-latest/closing-reference-candidates.csv",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "closing_line_validation_evidence",
            closing_line_gate_status,
            [
                (
                    "Closing-line validation evidence is ready."
                    if closing_line_gate_status == "pass"
                    else "Closing-line validation is not yet interpretable because true closing references/results are missing."
                )
            ],
            [
                path
                for path in [
                    "docs/codex/artifacts/nfl-closing-line-validation-latest/closing-line-validation.json",
                    "docs/codex/artifacts/nfl-closing-line-validation-latest/closing-line-validation.md",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "historical_line_backtest_ready",
            historical_line_backtest_gate_status,
            [
                (
                    "Historical line backtest is present, review-only, and has model-vs-market line rows."
                    if historical_line_backtest_ready
                    else "Historical line backtest is missing, blocked, unsafe, or has no model-vs-market rows."
                )
            ],
            [
                path
                for path in [
                    "docs/codex/artifacts/nfl-historical-line-backtest-latest/historical-line-backtest.json",
                    "docs/codex/artifacts/nfl-historical-line-backtest-latest/historical-line-backtest.md",
                    "docs/codex/artifacts/nfl-historical-line-backtest-latest/historical-line-backtest.csv",
                    "src/nfl_quant/validation/line_backtest.py",
                    "tests/test_historical_line_backtest.py",
                ]
                if (root / path).exists()
            ],
        ),
        make_gate(
            "dirty_tree_risk",
            "warn" if status["git"]["dirty_counts"]["total"] else "pass",
            [f"Dirty paths: {status['git']['dirty_counts']['total']}."],
            [],
        ),
    ]
    if line_readiness_ready:
        if (
            availability_status == "forward_context_availability_not_yet_due"
            and availability_safe
        ):
            evidence_status = "line_readiness_profiled_slate_forward_context_not_yet_due_research_only"
        elif forward_context_safe:
            if isinstance(manual_drop, dict):
                if manual_drop_status == "manual_drop_ready_safe_inputs" and manual_drop_safe:
                    evidence_status = "line_readiness_profiled_slate_forward_context_manual_drop_ready_research_only"
                elif manual_drop_status == "manual_drop_partial_safe_inputs" and manual_drop_safe:
                    evidence_status = "line_readiness_profiled_slate_forward_context_manual_drop_partial_research_only"
                else:
                    evidence_status = "line_readiness_profiled_slate_forward_context_manual_drop_blocked_research_only"
            elif forward_context_status == "forward_context_ready_safe_inputs":
                evidence_status = "line_readiness_profiled_slate_forward_context_ready_research_only"
            elif forward_context_status == "forward_context_partial_safe_inputs":
                evidence_status = "line_readiness_profiled_slate_forward_context_partial_research_only"
            else:
                evidence_status = "line_readiness_profiled_slate_forward_context_blocked_research_only"
        else:
            evidence_status = "line_readiness_profiled_slate_context_missing_research_only"
    else:
        evidence_status = (
            "governance_macro_export_ready_fresh_snapshots_research_only"
            if governance_export_present and governance_snapshots_ready
            else "governance_macro_export_ready_dirty_research_only"
            if governance_export_present
            else "governance_validation_source_dirty_research_only"
        )
    evidence = {
        "status": evidence_status,
        "latest_artifacts": artifacts,
        "hashes": hashes,
        "blocker_count": sum(1 for gate in gates if gate["status"] in {"blocked", "fail"}),
        "metrics": {
            "status_json_available": has_status_json,
            "artifact_audit_available": has_artifact_audit,
            "profile_validation_available": has_profile_validation,
            "latest_completion_reports": completion_reports,
            "validation_artifacts": validation_artifacts,
            "governance_export": json_brief(governance_export)
            if governance_export is not None
            else {"missing": True},
            "governance_export_present": governance_export_present,
            "governance_snapshots_ready": governance_snapshots_ready,
            "profile_validation_snapshot_status": profile_validation_snapshot.get("gate_status"),
            "profile_validation_snapshot_decision": profile_validation_snapshot.get("aggregate_decision"),
            "profile_validation_snapshot_fresh": profile_validation_snapshot.get("fresh"),
            "artifact_audit_snapshot_status": artifact_audit_snapshot.get("gate_status"),
            "artifact_audit_snapshot_audit_status": artifact_audit_snapshot.get("status"),
            "artifact_audit_snapshot_fresh": artifact_audit_snapshot.get("fresh"),
            "line_readiness": json_brief(line_readiness)
            if line_readiness is not None
            else {"missing": True},
            "line_readiness_ready": line_readiness_ready,
            "line_readiness_fair_lines_present": fair_lines_present,
            "fair_line_review": json_brief(fair_line_review)
            if fair_line_review is not None
            else {"missing": True},
            "fair_line_review_ready": fair_line_review_ready,
            "fair_line_review_status": fair_line_review.get("status")
            if isinstance(fair_line_review, dict)
            else None,
            "fair_line_review_row_count": fair_line_review.get("row_count")
            if isinstance(fair_line_review, dict)
            else None,
            "line_readiness_slate_rows": line_profiled_slate.get("slate_rows"),
            "line_readiness_profile_name": line_model_evidence.get("profile_name"),
            "line_readiness_validation_decision": line_model_evidence.get("validation_decision"),
            "forward_context": json_brief(forward_context)
            if forward_context is not None
            else {"missing": True},
            "forward_context_seed": json_brief(forward_context_seed)
            if forward_context_seed is not None
            else {"missing": True},
            "forward_context_seed_projected_qb_team_count": (
                forward_context_seed.get("projected_starting_qb_team_count")
                if isinstance(forward_context_seed, dict)
                else None
            ),
            "forward_context_safe": forward_context_safe,
            "forward_context_status": forward_context_status,
            "forward_context_warning_count": forward_context.get("warning_count")
            if isinstance(forward_context, dict)
            else None,
            "forward_context_blocker_count": forward_context.get("blocker_count")
            if isinstance(forward_context, dict)
            else None,
            "forward_context_next_action": forward_context.get("next_action")
            if isinstance(forward_context, dict)
            else None,
            "forward_context_manual_drop": json_brief(manual_drop)
            if manual_drop is not None
            else {"missing": True},
            "forward_context_manual_drop_safe": manual_drop_safe,
            "forward_context_manual_drop_status": manual_drop_status,
            "forward_context_manual_drop_warning_count": manual_drop.get("warning_count")
            if isinstance(manual_drop, dict)
            else None,
            "forward_context_manual_drop_blocker_count": manual_drop.get("blocker_count")
            if isinstance(manual_drop, dict)
            else None,
            "forward_context_manual_drop_next_action": manual_drop.get("next_action")
            if isinstance(manual_drop, dict)
            else None,
            "forward_context_availability": json_brief(forward_context_availability)
            if forward_context_availability is not None
            else {"missing": True},
            "forward_context_availability_safe": availability_safe,
            "forward_context_availability_status": availability_status,
            "forward_context_availability_next_action": (
                forward_context_availability.get("next_action")
                if isinstance(forward_context_availability, dict)
                else None
            ),
            "forward_context_availability_summary": (
                forward_context_availability.get("summary")
                if isinstance(forward_context_availability, dict)
                else None
            ),
            "forward_context_adjustments": json_brief(forward_context_adjustments)
            if forward_context_adjustments is not None
            else {"missing": True},
            "forward_context_adjustments_status": (
                forward_context_adjustments.get("status")
                if isinstance(forward_context_adjustments, dict)
                else None
            ),
            "forward_context_adjustments_row_count": (
                forward_context_adjustments.get("row_count")
                if isinstance(forward_context_adjustments, dict)
                else None
            ),
            "odds_api_market_reference": json_brief(odds_api_market_reference)
            if odds_api_market_reference is not None
            else {"missing": True},
            "odds_api_market_reference_ready": odds_api_market_ready,
            "odds_api_market_reference_derived_rows": (
                odds_api_market_reference.get("derived_market_reference_row_count")
                if isinstance(odds_api_market_reference, dict)
                else None
            ),
            "odds_api_market_reference_book_count": (
                odds_api_market_reference.get("derived_book_count")
                if isinstance(odds_api_market_reference, dict)
                else None
            ),
            "consensus_market": json_brief(consensus_market)
            if consensus_market is not None
            else {"missing": True},
            "consensus_market_ready": consensus_market_ready,
            "consensus_market_row_count": (
                consensus_market.get("consensus_row_count")
                if isinstance(consensus_market, dict)
                else None
            ),
            "consensus_market_raw_row_count": (
                consensus_market.get("raw_row_count") if isinstance(consensus_market, dict) else None
            ),
            "market_snapshot_ledger": json_brief(market_snapshot_ledger)
            if market_snapshot_ledger is not None
            else {"missing": True},
            "market_snapshot_ledger_ready": market_snapshot_ledger_ready,
            "market_snapshot_ledger_status": (
                market_snapshot_ledger.get("status")
                if isinstance(market_snapshot_ledger, dict)
                else None
            ),
            "market_snapshot_ledger_row_count": (
                market_snapshot_ledger.get("ledger_row_count")
                if isinstance(market_snapshot_ledger, dict)
                else None
            ),
            "market_snapshot_ledger_closing_candidate_count": (
                market_snapshot_ledger.get("closing_reference_row_count")
                if isinstance(market_snapshot_ledger, dict)
                else None
            ),
            "closing_line_validation": json_brief(closing_line_validation)
            if closing_line_validation is not None
            else {"missing": True},
            "closing_line_validation_status": closing_line_status,
            "historical_line_backtest": json_brief(historical_line_backtest)
            if historical_line_backtest is not None
            else {"missing": True},
            "historical_line_backtest_ready": historical_line_backtest_ready,
            "historical_line_backtest_status": (
                historical_line_backtest.get("status")
                if isinstance(historical_line_backtest, dict)
                else None
            ),
            "historical_line_backtest_row_count": (
                historical_line_backtest.get("row_count")
                if isinstance(historical_line_backtest, dict)
                else None
            ),
            "historical_line_backtest_fold_count": (
                historical_line_backtest.get("fold_count")
                if isinstance(historical_line_backtest, dict)
                else None
            ),
            "historical_line_backtest_skipped_fold_count": (
                historical_line_backtest.get("skipped_fold_count")
                if isinstance(historical_line_backtest, dict)
                else None
            ),
            "historical_line_backtest_summary": (
                historical_line_backtest.get("summary")
                if isinstance(historical_line_backtest, dict)
                else None
            ),
            "tests_passed_from_completion_report": tests_passed,
            "dirty_total": status["git"]["dirty_counts"]["total"],
        },
    }
    return finish_status(status, evidence, gates)


def collect_status(repo_id: str) -> dict[str, Any]:
    root = repo_path(repo_id)
    if repo_id == "predmarket-alpha":
        return predmarket_status(root)
    if repo_id == "mlb-platform":
        return mlb_status(root)
    if repo_id == "atp-oracle":
        return atp_status(root)
    if repo_id == "nba-analytics-platform":
        return nba_status(root)
    if repo_id == "nfl_quant_glm51_greenfield":
        return nfl_status(root)
    raise SystemExit(f"No adapter for {repo_id}")


def collect_all_statuses() -> list[dict[str, Any]]:
    return [collect_status(repo_id) for repo_id in repo_configs()]


def decide(statuses: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted(statuses, key=lambda item: item["scheduling"]["priority"], reverse=True)
    all_lanes_parked = all(int(status["scheduling"]["priority"]) <= 0 for status in ranked)
    if all_lanes_parked:
        top = next((status for status in statuses if status["repo_id"] == "predmarket-alpha"), ranked[0])
        recommended_next_tranche = PARKED_COMMAND_CENTER_TRANCHE
        stop_condition = PARKED_COMMAND_CENTER_STOP_CONDITION
    else:
        top = ranked[0]
        recommended_next_tranche = top["scheduling"]["recommended_next_tranche"]
        stop_condition = top["scheduling"]["stop_condition"]
    return {
        "schema_version": STATUS_VERSION,
        "as_of_utc": utc_now(),
        "priority_formula": (
            "3*architecture_leverage + 2*evidence_delta + 2*edge_feedback_speed "
            "+ blocker_criticality - dirty_risk - live_data_risk - verification_cost"
        ),
        "all_lanes_parked": all_lanes_parked,
        "blocker_summary": parked_blocker_summary(ranked) if all_lanes_parked else [],
        "recommended_repo_id": top["repo_id"],
        "recommended_repo_path": top["repo_path"],
        "recommended_next_tranche": recommended_next_tranche,
        "stop_condition": stop_condition,
        "ranked_repos": [
            {
                "repo_id": status["repo_id"],
                "priority": status["scheduling"]["priority"],
                "status": status["evidence"]["status"],
                "dirty_total": status["git"]["dirty_counts"]["total"],
                "gate_counts": status["evidence"]["gate_counts"],
            }
            for status in ranked
        ],
    }


def parked_blocker_summary(statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for status in statuses:
        evidence_status = str(status.get("evidence", {}).get("status", ""))
        summary.append(
            {
                "repo_id": status["repo_id"],
                "status": evidence_status,
                "priority": status["scheduling"]["priority"],
                "gate_counts": status["evidence"]["gate_counts"],
                "unlock": PARKED_UNLOCKS.get(evidence_status, status["scheduling"]["stop_condition"]),
            }
        )
    return summary


def write_route_outputs(statuses: list[dict[str, Any]], decision: dict[str, Any]) -> None:
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    (MACRO_DIR / "latest-status.json").write_text(
        json.dumps({"schema_version": STATUS_VERSION, "as_of_utc": utc_now(), "repos": statuses}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    (MACRO_DIR / "latest-decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (MACRO_DIR / "latest-decision.md").write_text(decision_markdown(decision), encoding="utf-8")


def decision_markdown(decision: dict[str, Any]) -> str:
    lines = [
        "# Latest Macro Routing Decision",
        "",
        f"- As of UTC: `{decision['as_of_utc']}`",
        f"- All lanes parked: `{str(decision.get('all_lanes_parked', False)).lower()}`",
        f"- Recommended repo: `{decision['recommended_repo_id']}`",
        f"- Repo path: `{decision['recommended_repo_path']}`",
        f"- Next tranche: {decision['recommended_next_tranche']}",
        f"- Stop condition: {decision['stop_condition']}",
        "",
        "## Ranking",
        "",
    ]
    for index, repo in enumerate(decision["ranked_repos"], start=1):
        counts = repo["gate_counts"]
        lines.append(
            f"{index}. `{repo['repo_id']}` priority `{repo['priority']}`; "
            f"status `{repo['status']}`; dirty `{repo['dirty_total']}`; "
            f"gates pass/warn/blocked/fail `{counts['pass']}/{counts['warn']}/{counts['blocked']}/{counts['fail']}`"
        )
    lines.append("")
    blocker_summary = list(decision.get("blocker_summary") or [])
    if blocker_summary:
        lines.extend(["## Parked Blockers", ""])
        for item in blocker_summary:
            lines.append(
                f"- `{item['repo_id']}` status `{item['status']}`; priority `{item['priority']}`; "
                f"unlock: {item['unlock']}"
            )
        lines.append("")
    return "\n".join(lines)


def print_json(value: Any) -> None:
    sys.stdout.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex federated macro router")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Print MacroRepoStatusV1 for one repo")
    status_parser.add_argument("--repo-id", required=True, choices=sorted(repo_configs()))

    route_parser = subparsers.add_parser("route", help="Collect all statuses and choose one next tranche")
    route_parser.add_argument("--write", action="store_true", help="Write latest-status and latest-decision artifacts")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "status":
        print_json(collect_status(args.repo_id))
        return 0
    if args.command == "route":
        statuses = collect_all_statuses()
        decision = decide(statuses)
        if args.write:
            write_route_outputs(statuses, decision)
        print_json(decision)
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
