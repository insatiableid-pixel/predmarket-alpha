#!/usr/bin/env python3
"""Audit whether all macro Kalshi EV lanes are blocked by named inputs.

This is a command-center proof artifact, not a scheduler. It reads local macro
artifacts only and answers: can we honestly stop because every active lane is
blocked by a specific missing input with a concrete next command?
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "macro-blocker-audit-latest"
GENERIC_MISSING_INPUT_MARKERS = (
    "no immediate local unlock",
    "see latest macro decision",
    "unknown",
    "tbd",
    "todo",
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_blocker_audit(
    *,
    macro_dir: Path = MACRO_DIR,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    latest_status_path = macro_dir / "latest-status.json"
    latest_decision_path = macro_dir / "latest-decision.json"
    unlock_scout_path = macro_dir / "latest-unlock-scout.json"
    ev_ledger_path = macro_dir / "latest-kalshi-contract-ev-ledger.json"
    local_contract_scout_path = macro_dir / "latest-kalshi-ev-local-contract-evidence-scout.json"
    nfl_overlay_assembler_path = macro_dir / "latest-kalshi-ev-nfl-overlay-assembler.json"

    latest_status = read_json_or_empty(latest_status_path)
    latest_decision = read_json_or_empty(latest_decision_path)
    unlock_scout = read_json_or_empty(unlock_scout_path)
    ev_ledger = read_json_or_empty(ev_ledger_path)
    local_contract_scout = read_json_or_empty(local_contract_scout_path)
    nfl_overlay_assembler = read_json_or_empty(nfl_overlay_assembler_path)

    lanes = unlock_scout.get("lanes") if isinstance(unlock_scout.get("lanes"), list) else []
    lane_audits = [audit_lane(lane) for lane in lanes if isinstance(lane, Mapping)]
    all_lanes_blocked = bool(lane_audits) and all(lane["blocked"] for lane in lane_audits)
    all_lanes_exact = bool(lane_audits) and all(lane["missing_input_specific"] for lane in lane_audits)
    all_commands_present = bool(lane_audits) and all(lane["next_command_present"] for lane in lane_audits)
    usable_ev_rows = int_value(nested(ev_ledger, "summary", "usable_row_count"))
    overlays_written = bool(nested(nfl_overlay_assembler, "summary", "overlays_written"))
    ready_target_matches = int_value(nested(local_contract_scout, "summary", "ready_target_match_count"))

    gates = [
        gate(
            "unlock_scout_present",
            bool(lanes),
            f"Loaded {len(lane_audits)} lane(s) from {unlock_scout_path}.",
        ),
        gate(
            "all_lanes_marked_blocked",
            all_lanes_blocked,
            "Every unlock-scout lane is currently blocked."
            if all_lanes_blocked
            else "At least one unlock-scout lane is not marked blocked.",
        ),
        gate(
            "all_missing_inputs_specific",
            all_lanes_exact,
            "Every lane has a named missing input."
            if all_lanes_exact
            else "At least one lane still has a generic or empty missing input.",
        ),
        gate(
            "all_next_commands_present",
            all_commands_present,
            "Every lane has a next local command."
            if all_commands_present
            else "At least one lane lacks a next local command.",
        ),
        gate(
            "no_usable_ev_rows",
            usable_ev_rows == 0,
            f"Usable EV ledger rows: {usable_ev_rows}.",
        ),
        gate(
            "no_overlay_rows_written_without_evidence",
            not overlays_written,
            "NFL overlay assembler has not written overlays without ready evidence."
            if not overlays_written
            else "NFL overlay assembler wrote overlays; ledger/preflight must be reviewed instead of declaring blocked.",
        ),
        gate(
            "no_ready_nfl_target_contract_evidence",
            ready_target_matches == 0,
            f"Ready NFL target contract matches: {ready_target_matches}.",
        ),
        gate(
            "research_only_safety",
            safe_research_json(unlock_scout) and safe_research_json(ev_ledger),
            "Unlock scout and EV ledger are research-only and execution-disabled.",
        ),
    ]
    blocked_gates = [item for item in gates if item["status"] == "blocked"]
    if not blocked_gates and all_lanes_blocked:
        status = "macro_blocker_audit_all_lanes_blocked_with_exact_inputs"
    else:
        status = "macro_blocker_audit_incomplete"

    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "live_calls_made": False,
        "provider_api_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "raw_payloads_copied_to_repo": False,
        "safety": {
            "research_only": True,
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "raw_payloads_copied_to_repo": False,
        },
        "inputs": {
            "latest_status_path": str(latest_status_path),
            "latest_status_sha256": sha256_file(latest_status_path),
            "latest_decision_path": str(latest_decision_path),
            "latest_decision_sha256": sha256_file(latest_decision_path),
            "unlock_scout_path": str(unlock_scout_path),
            "unlock_scout_sha256": sha256_file(unlock_scout_path),
            "ev_ledger_path": str(ev_ledger_path),
            "ev_ledger_sha256": sha256_file(ev_ledger_path),
            "local_contract_scout_path": str(local_contract_scout_path),
            "local_contract_scout_sha256": sha256_file(local_contract_scout_path),
            "nfl_overlay_assembler_path": str(nfl_overlay_assembler_path),
            "nfl_overlay_assembler_sha256": sha256_file(nfl_overlay_assembler_path),
        },
        "summary": {
            "lane_count": len(lane_audits),
            "blocked_lane_count": sum(1 for lane in lane_audits if lane["blocked"]),
            "specific_missing_input_lane_count": sum(1 for lane in lane_audits if lane["missing_input_specific"]),
            "next_command_lane_count": sum(1 for lane in lane_audits if lane["next_command_present"]),
            "usable_ev_row_count": usable_ev_rows,
            "ready_nfl_target_match_count": ready_target_matches,
            "nfl_overlays_written": overlays_written,
            "router_recommended_repo_id": latest_decision.get("recommended_repo_id"),
            "router_all_lanes_parked": latest_decision.get("all_lanes_parked"),
        },
        "gates": gates,
        "lane_audits": lane_audits,
        "next_action": next_action(status, lane_audits),
        "source_status_brief": {
            "latest_status_repo_count": len(latest_status.get("repos") or []),
            "latest_decision_statuses": [
                {
                    "repo_id": row.get("repo_id"),
                    "status": row.get("status"),
                    "priority": row.get("priority"),
                }
                for row in latest_decision.get("ranked_repos", [])
                if isinstance(row, Mapping)
            ],
        },
    }


def audit_lane(lane: Mapping[str, Any]) -> dict[str, Any]:
    missing_input = str(lane.get("missing_input") or "").strip()
    next_command = str(lane.get("next_local_command") or "").strip()
    generic = any(marker in missing_input.lower() for marker in GENERIC_MISSING_INPUT_MARKERS)
    specific = bool(missing_input) and not generic and len(missing_input) >= 30
    return {
        "repo_id": lane.get("repo_id"),
        "status": lane.get("status"),
        "blocked": lane.get("blocked") is True,
        "missing_input": missing_input,
        "missing_input_specific": specific,
        "next_local_command": next_command,
        "next_command_present": bool(next_command),
        "what_exists": lane.get("what_exists"),
        "proof_status": "pass"
        if lane.get("blocked") is True and specific and next_command
        else "blocked",
    }


def gate(name: str, passed: bool, reason: str) -> dict[str, Any]:
    return {"name": name, "status": "pass" if passed else "blocked", "reasons": [reason]}


def next_action(status: str, lane_audits: Sequence[Mapping[str, Any]]) -> str:
    if status == "macro_blocker_audit_all_lanes_blocked_with_exact_inputs":
        primary = next((lane for lane in lane_audits if lane.get("repo_id") == "predmarket-alpha"), None)
        if primary:
            return (
                "All lanes are currently blocked by named inputs. Primary missing input: "
                f"{primary.get('missing_input')} Next command after input: {primary.get('next_local_command')}"
            )
        return "All lanes are currently blocked by named inputs; follow each lane's next command after supplying evidence."
    incomplete = [lane.get("repo_id") for lane in lane_audits if lane.get("proof_status") != "pass"]
    return f"Blocker proof is incomplete for: {', '.join(str(item) for item in incomplete)}."


def safe_research_json(value: Any) -> bool:
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


def nested(value: Mapping[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def write_blocker_audit(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "macro-blocker-audit.json"
    md_path = out_dir / "macro-blocker-audit.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-macro-blocker-audit.json"
    latest_md = MACRO_DIR / "latest-macro-blocker-audit.md"
    latest_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Macro Blocker Audit",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Research only: `{str(report.get('research_only')).lower()}`",
        f"- Lanes: `{summary.get('lane_count')}`",
        f"- Blocked lanes: `{summary.get('blocked_lane_count')}`",
        f"- Specific missing-input lanes: `{summary.get('specific_missing_input_lane_count')}`",
        f"- Usable EV rows: `{summary.get('usable_ev_row_count')}`",
        "",
        "## Gates",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for item in report.get("gates", []):
        lines.append(
            f"| `{item.get('name')}` | `{item.get('status')}` | "
            f"{'; '.join(item.get('reasons') or [])} |"
        )
    lines.extend(
        [
            "",
            "## Lane Proof",
            "",
            "| Repo | Status | Proof | Missing Input | Next Command |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for lane in report.get("lane_audits", []):
        lines.append(
            f"| `{lane.get('repo_id')}` | `{lane.get('status')}` | `{lane.get('proof_status')}` | "
            f"{lane.get('missing_input')} | `{lane.get('next_local_command')}` |"
        )
    lines.extend(["", "## Next Action", "", str(report.get("next_action") or ""), ""])
    return "\n".join(lines)


def read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--macro-dir", type=Path, default=MACRO_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_blocker_audit(macro_dir=args.macro_dir)
    if args.write:
        paths = write_blocker_audit(report, args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
