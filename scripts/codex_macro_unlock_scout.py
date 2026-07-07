#!/usr/bin/env python3
"""Summarize parked macro unlock inputs from local files only."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from predmarket.shared_helpers import manual_drop_path, project_path

CONTROL_REPO = Path(__file__).resolve().parents[1]
DEFAULT_MANUAL_DROPS = manual_drop_path()
DEFAULT_MLB_REPO = project_path("mlb-platform")


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def local_make_command(repo_name: str, target: str) -> str:
    return f"cd {project_path(repo_name)} && make {target}"


def build_unlock_scout(
    *,
    control_repo: Path = CONTROL_REPO,
    manual_drops: Path = DEFAULT_MANUAL_DROPS,
    mlb_repo: Path = DEFAULT_MLB_REPO,
    as_of_utc: str | None = None,
) -> dict[str, Any]:
    latest_decision = _read_json(control_repo / "docs/codex/macro/latest-decision.json")
    predmarket_builder = _read_json(control_repo / "docs/codex/artifacts/type2-reference-builder-latest/type2-reference-builder-latest.json")
    predmarket_disposition = _read_json(
        control_repo / "docs/codex/artifacts/type2-candidate-disposition-latest/type2-candidate-disposition-latest.json"
    )
    kalshi_ev_ledger = _read_json(control_repo / "docs/codex/macro/latest-kalshi-contract-ev-ledger.json")
    kalshi_ev_overlay_preflight = _read_json(control_repo / "docs/codex/macro/latest-kalshi-ev-overlay-preflight.json")
    kalshi_ev_calibration_work_order = _read_json(
        control_repo / "docs/codex/macro/latest-kalshi-ev-calibration-work-order.json"
    )
    kalshi_ev_contract_mapping_work_order = _read_json(
        control_repo / "docs/codex/macro/latest-kalshi-ev-contract-mapping-work-order.json"
    )
    kalshi_ev_local_contract_evidence_scout = _read_json(
        control_repo / "docs/codex/macro/latest-kalshi-ev-local-contract-evidence-scout.json"
    )
    kalshi_ev_nfl_overlay_assembler = _read_json(
        control_repo / "docs/codex/macro/latest-kalshi-ev-nfl-overlay-assembler.json"
    )
    atp_diagnostic = _read_json(
        project_path(
            "atp-oracle",
            "docs/codex/artifacts/type2-g1g2-diagnostic-latest/type2-g1g2-diagnostic.json",
        )
    )

    odds_files = _files(manual_drops / "odds_api", patterns=("*.json",))
    kalshi_files = _files(manual_drops / "kalshi", patterns=("*.json",))
    predmarket_reference = manual_drops / "predmarket/type2-sportsbook-reference.json"
    mlb_intake_status = _read_latest_pregame_intake_status(mlb_repo)
    mlb_review_adjudication = _read_latest_review_adjudication(mlb_repo)
    mlb_repeatability_ledger = _read_latest_repeatability_ledger(mlb_repo)
    mlb_repeatability_research_review = _read_latest_repeatability_research_review(mlb_repo)
    mlb_threshold_policy_review = _read_latest_threshold_policy_review(mlb_repo)
    mlb_settled_validation = _read_latest_settled_validation(mlb_repo)
    mlb_closing_proxy_validation = _read_latest_closing_proxy_validation(mlb_repo)
    mlb_betexplorer_moneyline_comparison = _read_latest_betexplorer_moneyline_comparison(mlb_repo)
    mlb_betexplorer_market_comparison = _read_latest_betexplorer_market_comparison(mlb_repo)

    lanes = [
        _predmarket_lane(
            manual_drops,
            predmarket_reference,
            predmarket_builder,
            predmarket_disposition,
            kalshi_ev_ledger,
            kalshi_ev_overlay_preflight,
            kalshi_ev_calibration_work_order,
            kalshi_ev_contract_mapping_work_order,
            kalshi_ev_local_contract_evidence_scout,
            kalshi_ev_nfl_overlay_assembler,
        ),
        _mlb_lane(
            odds_files,
            kalshi_files,
            mlb_intake_status,
            mlb_review_adjudication,
            mlb_repeatability_ledger,
            mlb_repeatability_research_review,
            mlb_threshold_policy_review,
            mlb_settled_validation,
            mlb_closing_proxy_validation,
            mlb_betexplorer_moneyline_comparison,
            mlb_betexplorer_market_comparison,
        ),
        _atp_lane(atp_diagnostic),
        _route_lane(latest_decision, "nba-analytics-platform"),
        _route_lane(latest_decision, "nfl_quant_glm51_greenfield"),
    ]
    return {
        "schema_version": 1,
        "as_of_utc": as_of_utc or utc_now(),
        "research_only": True,
        "execution_enabled": False,
        "safety": {
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "account_or_order_paths": False,
            "market_execution": False,
        },
        "router": {
            "all_lanes_parked": latest_decision.get("all_lanes_parked"),
            "recommended_repo_id": latest_decision.get("recommended_repo_id"),
        },
        "local_inputs": {
            "manual_drops": str(manual_drops),
            "odds_api_json_count": len(odds_files),
            "kalshi_json_count": len(kalshi_files),
            "predmarket_reference_exists": predmarket_reference.is_file(),
            "kalshi_ev_probability_overlay_count": len(
                _files(manual_drops / "kalshi_ev_probabilities", patterns=("*.json",))
            ),
            "kalshi_ev_contract_mapping_overlay_count": len(
                _files(manual_drops / "kalshi_ev_contract_mappings", patterns=("*.json",))
            ),
        },
        "kalshi_ev": {
            "ledger_status": kalshi_ev_ledger.get("status") if isinstance(kalshi_ev_ledger, Mapping) else None,
            "ledger_summary": kalshi_ev_ledger.get("summary") if isinstance(kalshi_ev_ledger, Mapping) else {},
            "overlay_preflight_status": (
                kalshi_ev_overlay_preflight.get("status")
                if isinstance(kalshi_ev_overlay_preflight, Mapping)
                else None
            ),
            "overlay_preflight_summary": (
                kalshi_ev_overlay_preflight.get("summary")
                if isinstance(kalshi_ev_overlay_preflight, Mapping)
                else {}
            ),
            "calibration_work_order_status": (
                kalshi_ev_calibration_work_order.get("status")
                if isinstance(kalshi_ev_calibration_work_order, Mapping)
                else None
            ),
            "calibration_work_order_summary": (
                kalshi_ev_calibration_work_order.get("summary")
                if isinstance(kalshi_ev_calibration_work_order, Mapping)
                else {}
            ),
            "contract_mapping_work_order_status": (
                kalshi_ev_contract_mapping_work_order.get("status")
                if isinstance(kalshi_ev_contract_mapping_work_order, Mapping)
                else None
            ),
            "contract_mapping_work_order_summary": (
                kalshi_ev_contract_mapping_work_order.get("summary")
                if isinstance(kalshi_ev_contract_mapping_work_order, Mapping)
                else {}
            ),
            "local_contract_evidence_scout_status": (
                kalshi_ev_local_contract_evidence_scout.get("status")
                if isinstance(kalshi_ev_local_contract_evidence_scout, Mapping)
                else None
            ),
            "local_contract_evidence_scout_summary": (
                kalshi_ev_local_contract_evidence_scout.get("summary")
                if isinstance(kalshi_ev_local_contract_evidence_scout, Mapping)
                else {}
            ),
            "nfl_overlay_assembler_status": (
                kalshi_ev_nfl_overlay_assembler.get("status")
                if isinstance(kalshi_ev_nfl_overlay_assembler, Mapping)
                else None
            ),
            "nfl_overlay_assembler_summary": (
                kalshi_ev_nfl_overlay_assembler.get("summary")
                if isinstance(kalshi_ev_nfl_overlay_assembler, Mapping)
                else {}
            ),
        },
        "lanes": lanes,
    }


def write_unlock_scout(report: Mapping[str, Any], *, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "latest-unlock-scout.json"
    md_path = output_dir / "latest-unlock-scout.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_unlock_scout_markdown(report), encoding="utf-8")
    return json_path, md_path


def render_unlock_scout_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Macro Unlock Scout",
        "",
        f"- As of UTC: `{report.get('as_of_utc', '')}`",
        "- Mode: review-only",
        "- Provider/API calls: false",
        "- Market execution: false",
        f"- All lanes parked: `{str(report.get('router', {}).get('all_lanes_parked')).lower()}`",
        "",
        "## Local Inputs",
        "",
    ]
    local_inputs = report.get("local_inputs", {})
    for key in (
        "manual_drops",
        "odds_api_json_count",
        "kalshi_json_count",
        "predmarket_reference_exists",
        "kalshi_ev_probability_overlay_count",
        "kalshi_ev_contract_mapping_overlay_count",
    ):
        lines.append(f"- `{key}`: `{local_inputs.get(key)}`")
    kalshi_ev = report.get("kalshi_ev", {})
    lines.extend(
        [
            "",
            "## Kalshi EV",
            "",
            f"- Ledger status: `{kalshi_ev.get('ledger_status')}`",
            f"- Overlay preflight status: `{kalshi_ev.get('overlay_preflight_status')}`",
            f"- Calibration work order status: `{kalshi_ev.get('calibration_work_order_status')}`",
            f"- Contract mapping work order status: `{kalshi_ev.get('contract_mapping_work_order_status')}`",
            f"- Local contract evidence scout status: `{kalshi_ev.get('local_contract_evidence_scout_status')}`",
            f"- NFL overlay assembler status: `{kalshi_ev.get('nfl_overlay_assembler_status')}`",
        ]
    )
    lines.extend(["", "## Lanes", ""])
    for lane in report.get("lanes", []):
        lines.extend(
            [
                f"### {lane.get('repo_id', '')}",
                "",
                f"- Status: `{lane.get('status', '')}`",
                f"- Blocked: `{str(lane.get('blocked', False)).lower()}`",
                f"- What exists: {lane.get('what_exists', '')}",
                f"- Missing input: {lane.get('missing_input', '')}",
                f"- Next local command: `{lane.get('next_local_command', '')}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Guardrail",
            "",
            "This scout only summarizes local evidence and next local commands. It does not authorize execution or account activity.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _predmarket_lane(
    manual_drops: Path,
    predmarket_reference: Path,
    builder: Mapping[str, Any],
    disposition: Mapping[str, Any],
    kalshi_ev_ledger: Mapping[str, Any],
    kalshi_ev_overlay_preflight: Mapping[str, Any],
    kalshi_ev_calibration_work_order: Mapping[str, Any],
    kalshi_ev_contract_mapping_work_order: Mapping[str, Any],
    kalshi_ev_local_contract_evidence_scout: Mapping[str, Any],
    kalshi_ev_nfl_overlay_assembler: Mapping[str, Any],
) -> dict[str, Any]:
    if _safe_research_json(kalshi_ev_ledger) and _safe_research_json(kalshi_ev_contract_mapping_work_order):
        ledger_summary = kalshi_ev_ledger.get("summary") if isinstance(kalshi_ev_ledger.get("summary"), Mapping) else {}
        mapping_summary = (
            kalshi_ev_contract_mapping_work_order.get("summary")
            if isinstance(kalshi_ev_contract_mapping_work_order.get("summary"), Mapping)
            else {}
        )
        local_evidence_summary = (
            kalshi_ev_local_contract_evidence_scout.get("summary")
            if isinstance(kalshi_ev_local_contract_evidence_scout.get("summary"), Mapping)
            else {}
        )
        local_evidence_status = kalshi_ev_local_contract_evidence_scout.get("status")
        ready_target_matches = int(local_evidence_summary.get("ready_target_match_count") or 0)
        nfl_contract_rows = int(local_evidence_summary.get("nfl_contract_evidence_row_count") or 0)
        assembler_summary = (
            kalshi_ev_nfl_overlay_assembler.get("summary")
            if isinstance(kalshi_ev_nfl_overlay_assembler.get("summary"), Mapping)
            else {}
        )
        assembler_status = kalshi_ev_nfl_overlay_assembler.get("status")
        if kalshi_ev_contract_mapping_work_order.get("status") == "contract_mapping_work_order_ready":
            if ready_target_matches:
                missing_input = (
                    "No new external input is needed for the ready target match; fill matching safe overlays outside "
                    "the repo, then rerun preflight and ledger."
                )
            elif local_evidence_status == "local_contract_evidence_blocked_no_nfl_target_snapshot":
                missing_input = (
                    "Local Kalshi NFL contract snapshot for one selected work-order game, including exact ticker, "
                    "official terms, clean timing, and executable cost."
                )
            elif nfl_contract_rows:
                missing_input = (
                    "A selected NFL target match with official terms and executable cost; current local NFL snapshots "
                    "do not yet clear the ready-evidence gate."
                )
            else:
                missing_input = (
                    "Exact Kalshi ticker, official terms, clean timing status, and executable cost for one selected "
                    "NFL mapping row, plus matching safe overlays under manual_drops."
                )
            return {
                "repo_id": "predmarket-alpha",
                "status": str(local_evidence_status or "contract_mapping_work_order_ready"),
                "blocked": ready_target_matches == 0,
                "what_exists": (
                    f"ev_ledger_status={kalshi_ev_ledger.get('status')}, "
                    f"ledger_rows={ledger_summary.get('row_count')}, usable_rows={ledger_summary.get('usable_row_count')}, "
                    f"nfl_mapping_sides={mapping_summary.get('selected_contract_side_count')}, "
                    f"source_model_rows={mapping_summary.get('model_row_count')}, "
                    f"local_contract_evidence_status={local_evidence_status}, "
                    f"nfl_contract_evidence_rows={nfl_contract_rows}, "
                    f"ready_target_matches={ready_target_matches}, "
                    f"overlay_assembler_status={assembler_status}, "
                    f"assembled_overlay_pairs={assembler_summary.get('assembled_overlay_pair_count')}"
                ),
                "missing_input": missing_input,
                "next_local_command": (
                    "make kalshi-ev-contract-mapping-work-order && make kalshi-ev-local-contract-evidence-scout "
                    "&& make kalshi-ev-nfl-overlay-assembler && make kalshi-ev-overlay-preflight && make kalshi-ev-ledger"
                ),
            }
    if _safe_research_json(kalshi_ev_ledger) and _safe_research_json(kalshi_ev_calibration_work_order):
        ledger_summary = kalshi_ev_ledger.get("summary") if isinstance(kalshi_ev_ledger.get("summary"), Mapping) else {}
        work_summary = (
            kalshi_ev_calibration_work_order.get("summary")
            if isinstance(kalshi_ev_calibration_work_order.get("summary"), Mapping)
            else {}
        )
        preflight_summary = (
            kalshi_ev_overlay_preflight.get("summary")
            if isinstance(kalshi_ev_overlay_preflight.get("summary"), Mapping)
            else {}
        )
        usable = int(ledger_summary.get("usable_row_count") or 0)
        selected = int(work_summary.get("selected_row_count") or 0)
        status = str(kalshi_ev_calibration_work_order.get("status") or kalshi_ev_ledger.get("status") or "unknown")
        return {
            "repo_id": "predmarket-alpha",
            "status": status,
            "blocked": usable == 0,
            "what_exists": (
                f"ev_ledger_status={kalshi_ev_ledger.get('status')}, "
                f"ledger_rows={ledger_summary.get('row_count')}, usable_rows={usable}, "
                f"missing_calibrated_rows={ledger_summary.get('missing_calibrated_probability_row_count')}, "
                f"work_order_selected_rows={selected}, "
                f"overlay_exact_joins={preflight_summary.get('exact_join_row_count')}"
            ),
            "missing_input": (
                "Safe validated calibrated-probability overlay under "
                f"{manual_drops / 'kalshi_ev_probabilities'} keyed by exact contract_ticker and side."
                if usable == 0
                else "No missing EV overlay input; usable research-only rows are present for review."
            ),
            "next_local_command": (
                "make kalshi-ev-calibration-work-order && make kalshi-ev-overlay-preflight && make kalshi-ev-ledger"
            ),
        }
    builder_summary = builder.get("summary") if isinstance(builder, Mapping) else {}
    if not isinstance(builder_summary, Mapping):
        builder_summary = {}
    disposition_summary = disposition.get("summary") if isinstance(disposition, Mapping) else {}
    if not isinstance(disposition_summary, Mapping):
        disposition_summary = {}
    kept = int(disposition_summary.get("kept_review_candidate", 0) or 0)
    watch_only = int(disposition_summary.get("watch_only", 0) or 0)
    downgraded = int(disposition_summary.get("downgraded_temporal_mismatch", 0) or 0)
    disposition_status = str(disposition.get("status") or "")
    if kept > 0:
        missing_input = "No missing predmarket reference input; review candidates are present."
    elif disposition_status == "candidate_disposition_watch_only":
        missing_input = (
            "Timing-safe mapped reference exists, but no candidate cleared the review threshold; "
            "wait for a new slate/reference or an explicit threshold-policy change."
        )
    elif disposition_status == "candidate_disposition_all_passes_downgraded":
        missing_input = "Timing-safe mapped sportsbook reference captured before event start."
    else:
        missing_input = "Mapped sportsbook reference and candidate disposition need refresh."
    return {
        "repo_id": "predmarket-alpha",
        "status": disposition_status or builder.get("status") or "unknown",
        "blocked": kept == 0,
        "what_exists": (
            f"reference_exists={predmarket_reference.is_file()}, "
            f"builder_status={builder.get('status')}, rows={builder_summary.get('market_count')}, "
            f"kept_review_candidates={kept}, watch_only_candidates={watch_only}, "
            f"downgraded_temporal_mismatches={downgraded}"
        ),
        "missing_input": missing_input,
        "next_local_command": "make type2-reference-build && make type2-reference-preflight && make type2-paper-matcher && make type2-candidate-disposition",
    }


def _safe_research_json(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    safety = value.get("safety") if isinstance(value.get("safety"), Mapping) else {}
    return (
        value.get("research_only") is True
        and value.get("execution_enabled") is False
        and safety.get("market_execution") is False
        and safety.get("account_or_order_paths") is False
        and safety.get("database_writes") is False
    )


def _mlb_lane(
    odds_files: Sequence[Path],
    kalshi_files: Sequence[Path],
    intake_status: Mapping[str, Any],
    review_adjudication: Mapping[str, Any],
    repeatability_ledger: Mapping[str, Any],
    repeatability_research_review: Mapping[str, Any],
    threshold_policy_review: Mapping[str, Any],
    settled_validation: Mapping[str, Any],
    closing_proxy_validation: Mapping[str, Any],
    betexplorer_moneyline_comparison: Mapping[str, Any],
    betexplorer_market_comparison: Mapping[str, Any],
) -> dict[str, Any]:
    has_local_inputs = bool(odds_files and kalshi_files)
    status = "manual_drop_presence_checked"
    ledger_status: str | None = None
    blocked = not has_local_inputs
    what_exists = f"odds_api_json_files={len(odds_files)}, kalshi_json_files={len(kalshi_files)}"
    missing_input = (
        "Same-slate sportsbook and Kalshi pregame drops captured strictly before first pitch."
        if blocked
        else "Run intake to verify whether the local pair is timing-clean."
    )

    if has_local_inputs and intake_status:
        status = str(intake_status.get("status") or status)
        ready = bool(intake_status.get("ready"))
        blockers = intake_status.get("blockers") if isinstance(intake_status.get("blockers"), list) else []
        blocked = not ready
        what_exists = (
            f"{what_exists}, latest_intake_status={status}, latest_intake_ready={ready}, "
            f"latest_intake_blockers={len(blockers)}, latest_intake_report={intake_status.get('_source_path')}"
        )
        if ready:
            missing_input = "No missing local paired-input blocker; continue with the next review-only Type 2 audit surface."
        else:
            missing_input = (
                "Same-slate sportsbook and Kalshi pregame drops captured strictly before first pitch; "
                "the current local pair failed intake."
            )
    if review_adjudication and review_adjudication.get("ready_for_human_review") is True:
        summary = review_adjudication.get("summary") if isinstance(review_adjudication.get("summary"), Mapping) else {}
        status = str(review_adjudication.get("status") or status)
        blocked = False
        what_exists = (
            f"{what_exists}, latest_review_adjudication_status={status}, "
            f"review_ready_clusters={summary.get('review_ready_cluster_count')}, "
            f"review_ready_rows={summary.get('review_ready_row_count')}, "
            f"latest_review_adjudication_report={review_adjudication.get('_source_path')}"
        )
        missing_input = (
            "A second clean same-slate pregame pair is needed to compare whether the reviewed "
            "cluster pattern repeats."
        )
    if repeatability_ledger and repeatability_ledger.get("review_only") is True:
        summary = repeatability_ledger.get("summary") if isinstance(repeatability_ledger.get("summary"), Mapping) else {}
        status = str(repeatability_ledger.get("status") or status)
        ledger_status = status
        blocked = status != "repeatability_ready_for_research_review"
        what_exists = (
            f"{what_exists}, latest_repeatability_status={status}, "
            f"clean_packets={summary.get('clean_packet_count')}, "
            f"clean_no_signal_packets={summary.get('clean_no_signal_packet_count')}, "
            f"repeated_descriptors={summary.get('repeated_descriptor_count')}, "
            f"latest_repeatability_report={repeatability_ledger.get('_source_path')}"
        )
        if status == "repeatability_ready_for_research_review":
            missing_input = (
                "No missing local input: repeatability reached the three-clean-packet "
                "research-review threshold; next work is local synthesis."
            )
        elif status == "repeatability_observed_two_clean_packets":
            missing_input = (
                "Explicitly authorize another bounded clean current capture before trying to reach "
                "the three-packet research-review threshold."
            )
        elif status == "repeatability_blocked_no_clean_packets":
            missing_input = (
                "Corrected contract mapping leaves zero clean adjudicated packets; "
                "the prior run-line repeatability result is superseded."
            )
        elif status == "repeatability_no_signal_clean_packets":
            missing_input = (
                "Corrected, timing-clean packets exist, but zero rows cleared the current "
                "review threshold; next unlock is threshold policy, a new slate, or settled validation."
            )
        else:
            missing_input = (
                "A second clean same-slate pregame pair is needed to compare whether the reviewed "
                "cluster pattern repeats."
            )
    if repeatability_ledger and repeatability_ledger.get("review_only") is True:
        terminal_repeatability_status = status in {
            "repeatability_ready_for_research_review",
            "repeatability_blocked_no_clean_packets",
            "repeatability_no_signal_clean_packets",
        }
        next_local_command = (
            local_make_command("mlb-platform", "macro-status")
            if terminal_repeatability_status
            else local_make_command("mlb-platform", "type2-repeatability-ledger")
        )
    elif review_adjudication and review_adjudication.get("ready_for_human_review") is True:
        next_local_command = (
            f"{local_make_command('mlb-platform', 'type2-review-adjudication')} "
            "TYPE2_BUNDLE_DIR=<clean_bundle>"
        )
    else:
        next_local_command = (
            f"{local_make_command('mlb-platform', 'type2-pregame-drop-intake')} "
            "TYPE2_PREGAME_ODDS_RAW=<odds_json> TYPE2_PREGAME_ODDS_META=<odds_meta> "
            "TYPE2_PREGAME_KALSHI_JSON=<kalshi_json>"
        )
    if repeatability_research_review and repeatability_research_review.get("review_only") is True:
        summary = (
            repeatability_research_review.get("summary")
            if isinstance(repeatability_research_review.get("summary"), Mapping)
            else {}
        )
        status = str(repeatability_research_review.get("status") or status)
        blocked = True
        what_exists = (
            f"{what_exists}, latest_repeatability_research_review_status={status}, "
            f"stable_recurring_descriptors={summary.get('stable_recurring_descriptor_count')}, "
            f"same_slate_dates={summary.get('same_slate_dates')}, "
            f"latest_repeatability_research_review_report="
            f"{repeatability_research_review.get('_source_path')}"
        )
        if status == "repeatability_research_review_ready":
            missing_input = (
                "Cross-slate clean packet or settled/closing-line validation evidence; "
                "the current research review is ready but same-slate caveated."
            )
        elif ledger_status == "repeatability_no_signal_clean_packets":
            missing_input = (
                "Corrected, timing-clean packets exist, but zero rows cleared the current "
                "review threshold; next unlock is threshold policy, a new slate, or settled validation."
            )
        else:
            missing_input = (
                "Corrected contract mapping invalidated the previous run-line repeatability result; "
                "zero clean packets remain for research review."
            )
        next_local_command = local_make_command("mlb-platform", "macro-status")
    if threshold_policy_review and threshold_policy_review.get("review_only") is True:
        summary = (
            threshold_policy_review.get("summary")
            if isinstance(threshold_policy_review.get("summary"), Mapping)
            else {}
        )
        status = str(threshold_policy_review.get("status") or status)
        blocked = status != "threshold_policy_review_candidate"
        best = summary.get("best_lower_threshold_candidate") if isinstance(summary, Mapping) else {}
        if not isinstance(best, Mapping):
            best = {}
        what_exists = (
            f"{what_exists}, latest_threshold_policy_status={status}, "
            f"current_threshold_count={summary.get('current_threshold_count')}, "
            f"max_abs_net_edge={summary.get('max_abs_net_edge')}, "
            f"same_slate_date_count={summary.get('same_slate_date_count')}, "
            f"best_lower_threshold={best.get('threshold')}, "
            f"latest_threshold_policy_report={threshold_policy_review.get('_source_path')}"
        )
        if status == "threshold_policy_review_candidate":
            missing_input = (
                "No missing local input for threshold-policy review; manually inspect the candidate "
                "without changing thresholds or execution behavior."
            )
        elif status == "threshold_policy_hold_current":
            missing_input = (
                "Threshold-policy review says hold the current threshold: lower-threshold recurrence "
                "exists only on one slate. Next evidence is a new clean slate or settled/closing-line validation."
            )
        else:
            missing_input = (
                "Clean threshold-policy evidence is incomplete; produce a safe local threshold-policy report."
            )
        next_local_command = local_make_command("mlb-platform", "macro-status")
    if settled_validation and settled_validation.get("review_only") is True:
        summary = (
            settled_validation.get("summary")
            if isinstance(settled_validation.get("summary"), Mapping)
            else {}
        )
        status = str(settled_validation.get("status") or status)
        blocked = status != "settled_validation_review_candidate"
        correct_rate = summary.get("directional_correct_rate")
        correct_rate_text = f"{float(correct_rate):.1%}" if isinstance(correct_rate, (float, int)) else "n/a"
        what_exists = (
            f"{what_exists}, latest_settled_validation_status={status}, "
            f"valid_directional_rows={summary.get('valid_directional_row_count')}, "
            f"directional_correct_rate={correct_rate_text}, "
            f"current_threshold_count={summary.get('current_threshold_count')}, "
            f"same_slate_date_count={summary.get('same_slate_date_count')}, "
            f"latest_settled_validation_report={settled_validation.get('_source_path')}"
        )
        if status == "settled_validation_review_candidate":
            missing_input = (
                "No missing local input for settled-validation review; manually inspect it "
                "without changing thresholds or execution behavior."
            )
        elif status in {"settled_validation_no_policy_change_same_slate", "settled_validation_no_policy_change"}:
            missing_input = (
                "Settled validation does not support a threshold change: lower-threshold "
                f"directions settled at {correct_rate_text}, with zero current-threshold rows. "
                "Next evidence is an independent clean slate or closing-line validation."
            )
        else:
            missing_input = (
                "Settled validation is incomplete; produce a safe local settled-outcome report."
            )
        next_local_command = local_make_command("mlb-platform", "macro-status")
    if closing_proxy_validation and closing_proxy_validation.get("review_only") is True:
        summary = (
            closing_proxy_validation.get("summary")
            if isinstance(closing_proxy_validation.get("summary"), Mapping)
            else {}
        )
        best = summary.get("best_lower_threshold_candidate") if isinstance(summary, Mapping) else {}
        if not isinstance(best, Mapping):
            best = {}
        status = str(closing_proxy_validation.get("status") or status)
        blocked = status != "closing_proxy_review_candidate"
        what_exists = (
            f"{what_exists}, latest_closing_proxy_status={status}, "
            f"paired_rows={summary.get('paired_row_count')}, "
            f"current_threshold_count={summary.get('current_threshold_count')}, "
            f"same_slate_date_count={summary.get('same_slate_date_count')}, "
            f"best_lower_threshold={best.get('threshold')}, "
            f"best_lower_support={best.get('exchange_support_count')}, "
            f"best_lower_against={best.get('exchange_against_count')}, "
            f"latest_closing_proxy_report={closing_proxy_validation.get('_source_path')}"
        )
        if status == "closing_proxy_review_candidate":
            missing_input = (
                "No missing local input for closing-proxy review; manually inspect it "
                "without treating it as true close or changing thresholds."
            )
        elif status == "closing_proxy_same_slate_support_insufficient":
            missing_input = (
                "Closing-proxy support exists, but it is only same-slate later-snapshot evidence "
                "and settled validation did not support the lower-threshold directions. Next evidence "
                "is an independent clean slate or true closing-line validation."
            )
        else:
            missing_input = (
                "Closing-proxy validation is incomplete; produce a safe local proxy report from "
                "existing clean packets only."
            )
        next_local_command = local_make_command("mlb-platform", "macro-status")
    if betexplorer_moneyline_comparison and betexplorer_moneyline_comparison.get("review_only") is True:
        summary = (
            betexplorer_moneyline_comparison.get("summary")
            if isinstance(betexplorer_moneyline_comparison.get("summary"), Mapping)
            else {}
        )
        status = str(betexplorer_moneyline_comparison.get("status") or status)
        blocked = status != "betexplorer_moneyline_closing_comparison_review_candidate"
        what_exists = (
            f"{what_exists}, latest_betexplorer_moneyline_status={status}, "
            f"matched_rows={summary.get('matched_row_count')}, "
            f"current_threshold_count={summary.get('current_threshold_count')}, "
            f"converged={summary.get('converged_count')}, "
            f"diverged={summary.get('diverged_count')}, "
            f"direction_support={summary.get('direction_support_count')}, "
            f"direction_against={summary.get('direction_against_count')}, "
            f"latest_betexplorer_moneyline_report={betexplorer_moneyline_comparison.get('_source_path')}"
        )
        if status == "betexplorer_moneyline_closing_comparison_ready_no_policy_change":
            missing_input = (
                "Public BetExplorer moneyline comparison is present and date-matched, but it covers "
                "direct book moneyline rows only and has zero current-threshold rows. Next evidence is "
                "broader book/market mapping, an independent clean slate, or true full closing-line validation."
            )
        else:
            missing_input = (
                "BetExplorer moneyline comparison is incomplete; fix mapping before using it as a "
                "closing-line evidence surface."
            )
        next_local_command = local_make_command("mlb-platform", "macro-status")
    if betexplorer_market_comparison and betexplorer_market_comparison.get("review_only") is True:
        summary = (
            betexplorer_market_comparison.get("summary")
            if isinstance(betexplorer_market_comparison.get("summary"), Mapping)
            else {}
        )
        status = str(betexplorer_market_comparison.get("status") or status)
        blocked = status != "betexplorer_market_closing_comparison_review_candidate"
        what_exists = (
            f"{what_exists}, latest_betexplorer_market_status={status}, "
            f"matched_rows={summary.get('matched_row_count')}, "
            f"matched_by_market={summary.get('matched_by_market')}, "
            f"current_threshold_count={summary.get('current_threshold_count')}, "
            f"converged={summary.get('converged_count')}, "
            f"diverged={summary.get('diverged_count')}, "
            f"direction_support={summary.get('direction_support_count')}, "
            f"direction_against={summary.get('direction_against_count')}, "
            f"latest_betexplorer_market_report={betexplorer_market_comparison.get('_source_path')}"
        )
        if status == "betexplorer_market_closing_comparison_ready_no_policy_change":
            missing_input = (
                "Public BetExplorer multi-market comparison is present and date-matched, but it is "
                "still narrow, has zero current-threshold rows, and does not justify a policy change. "
                "Next evidence is broader book/line/source coverage, an independent clean slate, or "
                "stronger true closing-line validation."
            )
        else:
            missing_input = (
                "BetExplorer market comparison is incomplete; fix book/market/selection/line mapping "
                "before using it as a closing-line evidence surface."
            )
        next_local_command = local_make_command("mlb-platform", "macro-status")
    return {
        "repo_id": "mlb-platform",
        "status": status,
        "blocked": blocked,
        "what_exists": what_exists,
        "missing_input": missing_input,
        "next_local_command": next_local_command,
    }


def _atp_lane(diagnostic: Mapping[str, Any]) -> dict[str, Any]:
    summary = diagnostic.get("summary") if isinstance(diagnostic, Mapping) else {}
    external_blockers = "D3/G5/P5 external proof"
    if isinstance(summary, Mapping) and summary.get("external_evidence_blocker_count") is not None:
        external_blockers = f"D3/G5/P5 external proof ({summary.get('external_evidence_blocker_count')} blockers)"
    return {
        "repo_id": "atp-oracle",
        "status": diagnostic.get("status") or "unknown",
        "blocked": True,
        "what_exists": (
            f"diagnostic_status={diagnostic.get('status')}, "
            f"vision_score={summary.get('vision_score') if isinstance(summary, Mapping) else None}"
        ),
        "missing_input": f"Fresh validation/promotion evidence plus {external_blockers}.",
        "next_local_command": local_make_command("atp-oracle", "type2-g1g2-diagnostic"),
    }


def _route_lane(decision: Mapping[str, Any], repo_id: str) -> dict[str, Any]:
    row = {}
    for candidate in decision.get("blocker_summary", []) if isinstance(decision, Mapping) else []:
        if isinstance(candidate, Mapping) and candidate.get("repo_id") == repo_id:
            row = dict(candidate)
            break
    if not row:
        for candidate in decision.get("ranked_repos", []) if isinstance(decision, Mapping) else []:
            if isinstance(candidate, Mapping) and candidate.get("repo_id") == repo_id:
                row = dict(candidate)
                break
    priority = row.get("priority")
    gate_counts = row.get("gate_counts") if isinstance(row.get("gate_counts"), Mapping) else {}
    status = str(row.get("status") or "unknown")
    missing_input, next_command = _route_lane_unlock(repo_id=repo_id, status=status, fallback=row.get("unlock"))
    return {
        "repo_id": repo_id,
        "status": status,
        "blocked": bool(gate_counts.get("blocked")) or (isinstance(priority, int) and priority <= 0),
        "what_exists": f"router_priority={row.get('priority')}, gate_counts={row.get('gate_counts')}",
        "missing_input": missing_input,
        "next_local_command": next_command,
    }


def _route_lane_unlock(*, repo_id: str, status: str, fallback: Any) -> tuple[str, str]:
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip(), "make macro-status"
    if repo_id == "nba-analytics-platform":
        if status == "macro_partial_truth_shrinkage_clipped_residual_market_parity":
            return (
                "New source-backed NBA signal or market dataset that can beat the current market-parity baseline; "
                "do not run new residual variants without that input.",
                local_make_command("nba-analytics-platform", "macro-status"),
            )
        return (
            "A source-backed NBA signal/data update plus current macro-status evidence for promotability gates.",
            local_make_command("nba-analytics-platform", "macro-status"),
        )
    if repo_id == "nfl_quant_glm51_greenfield":
        if status == "line_readiness_profiled_slate_forward_context_not_yet_due_research_only":
            return (
                "Forward-context evidence when due or manually dropped outside the repo: injuries, weather, official "
                "starting QBs/depth chart changes, and closing/reference line evidence. Current availability says these "
                "inputs are not yet due.",
                local_make_command(
                    "nfl_quant_glm51_greenfield",
                    "forward-context-availability && make macro-status",
                ),
            )
        return (
            "Fresh NFL governance/line-readiness evidence from local artifacts only; no new betting features.",
            local_make_command("nfl_quant_glm51_greenfield", "macro-status"),
        )
    return (
        "A named external evidence input for this lane plus refreshed macro-status evidence.",
        "make macro-status",
    )


def _files(root: Path, *, patterns: Sequence[str]) -> list[Path]:
    if not root.is_dir():
        return []
    out: list[Path] = []
    for pattern in patterns:
        out.extend(path for path in root.glob(pattern) if path.is_file())
    return sorted(set(out))


def _read_latest_pregame_intake_status(mlb_repo: Path) -> dict[str, Any]:
    root = mlb_repo / "docs/codex/artifacts"
    if not root.is_dir():
        return {}
    candidates = sorted(
        root.glob("*/pregame-drop-intake-status.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        payload = _read_json(path)
        if payload:
            return {**payload, "_source_path": str(path)}
    return {}


def _read_latest_review_adjudication(mlb_repo: Path) -> dict[str, Any]:
    root = mlb_repo / "docs/codex/artifacts"
    if not root.is_dir():
        return {}
    candidates = sorted(
        root.glob("*/review-adjudication.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        payload = _read_json(path)
        if payload:
            return {**payload, "_source_path": str(path)}
    return {}


def _read_latest_repeatability_ledger(mlb_repo: Path) -> dict[str, Any]:
    root = mlb_repo / "docs/codex/artifacts"
    if not root.is_dir():
        return {}
    candidates = sorted(
        root.glob("*/type2-repeatability-ledger.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        payload = _read_json(path)
        if payload:
            return {**payload, "_source_path": str(path)}
    return {}


def _read_latest_repeatability_research_review(mlb_repo: Path) -> dict[str, Any]:
    root = mlb_repo / "docs/codex/artifacts"
    if not root.is_dir():
        return {}
    candidates = sorted(
        root.glob("*/type2-repeatability-research-review.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        payload = _read_json(path)
        if payload:
            return {**payload, "_source_path": str(path)}
    return {}


def _read_latest_threshold_policy_review(mlb_repo: Path) -> dict[str, Any]:
    root = mlb_repo / "docs/codex/artifacts"
    if not root.is_dir():
        return {}
    candidates = sorted(
        root.glob("*/type2-threshold-policy-review.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        payload = _read_json(path)
        if payload:
            return {**payload, "_source_path": str(path)}
    return {}


def _read_latest_settled_validation(mlb_repo: Path) -> dict[str, Any]:
    root = mlb_repo / "docs/codex/artifacts"
    if not root.is_dir():
        return {}
    candidates = sorted(
        root.glob("*/type2-settled-outcome-validation.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        payload = _read_json(path)
        if payload:
            return {**payload, "_source_path": str(path)}
    return {}


def _read_latest_closing_proxy_validation(mlb_repo: Path) -> dict[str, Any]:
    root = mlb_repo / "docs/codex/artifacts"
    if not root.is_dir():
        return {}
    candidates = sorted(
        root.glob("*/type2-closing-proxy-validation.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        payload = _read_json(path)
        if payload:
            return {**payload, "_source_path": str(path)}
    return {}


def _read_latest_betexplorer_moneyline_comparison(mlb_repo: Path) -> dict[str, Any]:
    root = mlb_repo / "docs/codex/artifacts"
    if not root.is_dir():
        return {}
    candidates = sorted(
        root.glob("*/type2-betexplorer-moneyline-closing-comparison.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        payload = _read_json(path)
        if payload:
            return {**payload, "_source_path": str(path)}
    return {}


def _read_latest_betexplorer_market_comparison(mlb_repo: Path) -> dict[str, Any]:
    root = mlb_repo / "docs/codex/artifacts"
    if not root.is_dir():
        return {}
    candidates = sorted(
        root.glob("*/type2-betexplorer-market-closing-comparison.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        payload = _read_json(path)
        if payload:
            return {**payload, "_source_path": str(path)}
    return {}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a local-only macro unlock scout report.")
    parser.add_argument("--control-repo", default=str(CONTROL_REPO))
    parser.add_argument("--manual-drops", default=str(DEFAULT_MANUAL_DROPS))
    parser.add_argument("--mlb-repo", default=str(DEFAULT_MLB_REPO))
    parser.add_argument("--output-dir", default="docs/codex/macro")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    report = build_unlock_scout(
        control_repo=Path(args.control_repo),
        manual_drops=Path(args.manual_drops),
        mlb_repo=Path(args.mlb_repo),
    )
    if args.write:
        json_path, md_path = write_unlock_scout(report, output_dir=Path(args.output_dir))
        report = {**report, "outputs": {"json_path": str(json_path), "markdown_path": str(md_path)}}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
