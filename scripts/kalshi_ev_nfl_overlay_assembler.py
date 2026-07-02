#!/usr/bin/env python3
"""Assemble NFL Kalshi EV overlays from ready local contract evidence.

This command is intentionally local-only. It never calls Kalshi/providers,
never writes databases, never touches account/order paths, and never creates a
betting instruction. It converts already-verified local evidence into the two
manual-drop overlays consumed by the EV ledger.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-ev-nfl-overlay-assembler-latest"
DEFAULT_SCOUT_PATH = MACRO_DIR / "latest-kalshi-ev-local-contract-evidence-scout.json"
DEFAULT_WORK_ORDER_PATH = MACRO_DIR / "latest-kalshi-ev-contract-mapping-work-order.json"
DEFAULT_MAPPING_OUTPUT_DIR = Path("/home/mrwatson/manual_drops/kalshi_ev_contract_mappings")
DEFAULT_PROBABILITY_OUTPUT_DIR = Path("/home/mrwatson/manual_drops/kalshi_ev_probabilities")
CLEAN_TIMING_STATUSES = {"clean", "pregame_clean", "not_applicable"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_nfl_overlay_assembler(
    *,
    scout_path: Path = DEFAULT_SCOUT_PATH,
    work_order_path: Path = DEFAULT_WORK_ORDER_PATH,
    mapping_output_dir: Path = DEFAULT_MAPPING_OUTPUT_DIR,
    probability_output_dir: Path = DEFAULT_PROBABILITY_OUTPUT_DIR,
    generated_utc: str | None = None,
    limit: int = 1,
    emit_overlays: bool = False,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    scout = read_json_or_empty(scout_path)
    work_order = read_json_or_empty(work_order_path)
    target_rows = work_order.get("rows") if isinstance(work_order.get("rows"), list) else []
    target_rows = [row for row in target_rows if isinstance(row, Mapping)]
    matches = scout.get("target_matches") if isinstance(scout.get("target_matches"), list) else []
    all_ready_matches = unique_ready_matches(
        match
        for match in matches
        if isinstance(match, Mapping) and ready_match(match)
    )
    ready_matches = all_ready_matches[: max(0, limit)]
    assembled = [
        assemble_overlay_pair(match=match, target_rows=target_rows)
        for match in ready_matches
    ]
    assembled = [item for item in assembled if item is not None]
    gates = assembler_gates(
        scout=scout,
        work_order=work_order,
        target_row_count=len(target_rows),
        ready_match_count=len(ready_matches),
        assembled_count=len(assembled),
        mapping_output_dir=mapping_output_dir,
        probability_output_dir=probability_output_dir,
    )
    blocked_gates = [gate for gate in gates if gate["status"] == "blocked"]
    overlay_paths: dict[str, str] = {}
    if assembled and emit_overlays and not blocked_gates:
        overlay_paths = write_overlay_files(
            assembled=assembled,
            generated_utc=generated,
            mapping_output_dir=mapping_output_dir,
            probability_output_dir=probability_output_dir,
        )

    if overlay_paths:
        status = "nfl_overlay_assembler_overlays_written"
    elif assembled and not blocked_gates:
        status = "nfl_overlay_assembler_ready_dry_run"
    elif ready_matches:
        status = "nfl_overlay_assembler_blocked_invalid_ready_match"
    else:
        status = "nfl_overlay_assembler_blocked_no_ready_local_contract_evidence"

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
            "scout_path": str(scout_path),
            "scout_sha256": sha256_file(scout_path),
            "scout_status": scout.get("status"),
            "work_order_path": str(work_order_path),
            "work_order_sha256": sha256_file(work_order_path),
            "work_order_status": work_order.get("status"),
        },
        "outputs": {
            "mapping_output_dir": str(mapping_output_dir),
            "probability_output_dir": str(probability_output_dir),
            **overlay_paths,
        },
        "summary": {
            "target_contract_side_count": len(target_rows),
            "scout_target_match_count": len(matches),
            "total_unique_ready_target_match_count": len(all_ready_matches),
            "selected_ready_target_match_count": len(ready_matches),
            "ready_target_match_count": len(ready_matches),
            "assembled_overlay_pair_count": len(assembled),
            "mapping_overlay_row_count": len(assembled),
            "probability_overlay_row_count": len(assembled),
            "overlays_written": bool(overlay_paths),
        },
        "gates": gates,
        "assembled_rows": [
            {
                "contract_ticker": item["mapping"]["contract_ticker"],
                "side": item["mapping"]["side"],
                "selection": item["mapping"].get("selection"),
                "calibrated_probability": item["probability"].get("calibrated_probability"),
                "executable_price": item["mapping"].get("executable_price"),
                "timing_status": item["mapping"].get("timing_status"),
                "source_model_artifact": item["mapping"].get("source_model_artifact"),
                "contract_evidence_source": item["mapping"].get("resolution_rule_source_artifact"),
            }
            for item in assembled
        ],
        "next_action": assembler_next_action(status=status, overlay_paths=overlay_paths),
    }


def ready_match(match: Mapping[str, Any]) -> bool:
    return (
        match.get("match_quality") == "ready_exact_local_evidence"
        and bool(match.get("contract_ticker"))
        and bool(match.get("event_ticker"))
        and bool(match.get("resolution_rule"))
        and match.get("official_terms_present") is True
        and match.get("executable_cost_present") is True
        and match.get("clean_timing_present") is True
        and str(match.get("timing_status") or "") in CLEAN_TIMING_STATUSES
        and optional_float(match.get("yes_ask")) is not None
    )


def unique_ready_matches(matches: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    seen: set[tuple[int, str]] = set()
    unique: list[Mapping[str, Any]] = []
    for match in matches:
        target_index = optional_int(match.get("target_index"))
        contract_ticker = str(match.get("contract_ticker") or "").strip()
        if target_index is None or not contract_ticker:
            continue
        key = (target_index, contract_ticker)
        if key in seen:
            continue
        seen.add(key)
        unique.append(match)
    return unique


def assemble_overlay_pair(
    *,
    match: Mapping[str, Any],
    target_rows: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]] | None:
    target_index = optional_int(match.get("target_index"))
    if target_index is None or target_index < 0 or target_index >= len(target_rows):
        return None
    target = target_rows[target_index]
    contract_ticker = str(match.get("contract_ticker") or "").strip()
    event_ticker = str(match.get("event_ticker") or "").strip()
    side = "yes"
    executable_price = optional_float(match.get("yes_ask"))
    calibrated_probability = optional_float(target.get("model_calibrated_probability"))
    if not contract_ticker or not event_ticker or executable_price is None or calibrated_probability is None:
        return None
    mapping = {
        "source_repo_id": "nfl_quant_glm51_greenfield",
        "contract_ticker": contract_ticker,
        "event_ticker": event_ticker,
        "side": side,
        "selection": target.get("selection"),
        "market_type": target.get("market_type") or "nfl_game_moneyline",
        "title": match.get("title") or f"{target.get('selection')} to beat {target.get('opponent')}",
        "mapping_status": "verified_contract_mapping",
        "mapping_confidence": "local_contract_evidence_scout_ready",
        "resolution_rule": match.get("resolution_rule"),
        "resolution_rule_source": "local_kalshi_contract_evidence_scout",
        "resolution_rule_status": "verified_official_terms",
        "resolution_rule_source_artifact": match.get("source_path"),
        "resolution_rule_source_sha256": match.get("source_sha256"),
        "executable_price": executable_price,
        "timing_status": match.get("timing_status"),
        "source_model_artifact": target.get("source_artifact"),
        "source_model_artifact_sha256": target.get("source_artifact_sha256"),
        "source_model_row_index": target.get("source_row_index"),
        "source_work_order_target_index": target_index,
        "game": target.get("game"),
        "selection_probability_source": target.get("model_probability_source"),
        "notes": "Assembled from local ready contract evidence and NFL fair-line work-order row; research-only.",
    }
    probability = {
        "contract_ticker": contract_ticker,
        "side": side,
        "calibrated_probability": calibrated_probability,
        "calibrated_probability_source": (
            "nfl_quant_glm51_greenfield:"
            f"{target.get('model_probability_source')}:{target.get('model_calibration_source')}"
        ),
        "calibration_status": "validated_calibrated_probability",
        "probability_uncertainty": target.get("probability_uncertainty"),
        "source_repo_id": "nfl_quant_glm51_greenfield",
        "source_model_artifact": target.get("source_artifact"),
        "source_model_artifact_sha256": target.get("source_artifact_sha256"),
        "source_model_row_index": target.get("source_row_index"),
        "model_calibration_detail": target.get("model_calibration_detail"),
        "notes": "Assembled from validated NFL fair-line model probability after exact Kalshi mapping evidence passed.",
    }
    return {"mapping": mapping, "probability": probability}


def assembler_gates(
    *,
    scout: Mapping[str, Any],
    work_order: Mapping[str, Any],
    target_row_count: int,
    ready_match_count: int,
    assembled_count: int,
    mapping_output_dir: Path,
    probability_output_dir: Path,
) -> list[dict[str, Any]]:
    return [
        {
            "name": "research_only_no_live_calls",
            "status": "pass",
            "reasons": ["Assembler consumes local scout/work-order JSON only; live/provider calls are not implemented."],
        },
        {
            "name": "scout_present_safe",
            "status": "pass" if safe_research_json(scout) else "blocked",
            "reasons": ["Scout artifact is present and research-only."]
            if safe_research_json(scout)
            else ["Scout artifact is missing or unsafe."],
        },
        {
            "name": "contract_mapping_work_order_present",
            "status": "pass" if target_row_count else "blocked",
            "reasons": [f"Loaded {target_row_count} work-order target side(s)."],
        },
        {
            "name": "ready_local_target_evidence_present",
            "status": "pass" if ready_match_count else "blocked",
            "reasons": [f"Found {ready_match_count} ready local target match(es)."]
            if ready_match_count
            else ["No ready local target match has ticker, terms, executable cost, and clean timing."],
        },
        {
            "name": "overlay_rows_assembled",
            "status": "pass" if assembled_count else "blocked",
            "reasons": [f"Assembled {assembled_count} overlay pair(s)."]
            if assembled_count
            else ["No overlay rows were assembled."],
        },
        {
            "name": "overlay_output_dirs_outside_repo",
            "status": "pass"
            if outside_repo(mapping_output_dir) and outside_repo(probability_output_dir)
            else "blocked",
            "reasons": [
                "Overlay output directories are outside the repo."
                if outside_repo(mapping_output_dir) and outside_repo(probability_output_dir)
                else "Overlay output directories must be outside the repo."
            ],
        },
        {
            "name": "work_order_status_ready",
            "status": "pass" if work_order.get("status") == "contract_mapping_work_order_ready" else "blocked",
            "reasons": [f"Work-order status is {work_order.get('status')}."],
        },
    ]


def write_overlay_files(
    *,
    assembled: Sequence[Mapping[str, Mapping[str, Any]]],
    generated_utc: str,
    mapping_output_dir: Path,
    probability_output_dir: Path,
) -> dict[str, str]:
    mapping_output_dir.mkdir(parents=True, exist_ok=True)
    probability_output_dir.mkdir(parents=True, exist_ok=True)
    stamp = overlay_key_stamp(assembled) or safe_stamp(generated_utc)
    mapping_path = mapping_output_dir / f"kalshi_ev_nfl_contract_mapping_overlay_{stamp}.json"
    probability_path = probability_output_dir / f"kalshi_ev_nfl_calibrated_probability_overlay_{stamp}.json"
    mapping_rows = [timestamped_overlay_row(item["mapping"], generated_utc=generated_utc) for item in assembled]
    probability_rows = [
        timestamped_overlay_row(item["probability"], generated_utc=generated_utc) for item in assembled
    ]
    mapping_payload = overlay_payload(mapping_rows, generated_utc=generated_utc)
    probability_payload = overlay_payload(probability_rows, generated_utc=generated_utc)
    mapping_path.write_text(json.dumps(mapping_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    probability_path.write_text(json.dumps(probability_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "mapping_overlay_path": str(mapping_path),
        "probability_overlay_path": str(probability_path),
        "mapping_overlay_sha256": sha256_file(mapping_path),
        "probability_overlay_sha256": sha256_file(probability_path),
    }


def overlay_key_stamp(assembled: Sequence[Mapping[str, Mapping[str, Any]]]) -> str | None:
    keys: list[str] = []
    for item in assembled:
        mapping = item.get("mapping") if isinstance(item.get("mapping"), Mapping) else {}
        contract_ticker = str(mapping.get("contract_ticker") or "").strip()
        side = str(mapping.get("side") or "").strip()
        if not contract_ticker or not side:
            return None
        keys.append(f"{contract_ticker}:{side}")
    if not keys:
        return None
    digest = hashlib.sha256("|".join(sorted(keys)).encode("utf-8")).hexdigest()[:12]
    return f"keys_{digest}"


def timestamped_overlay_row(row: Mapping[str, Any], *, generated_utc: str) -> dict[str, Any]:
    output = dict(row)
    output.setdefault("as_of_utc", generated_utc)
    output.setdefault("decision_time", generated_utc)
    output.setdefault("quote_time", generated_utc)
    output.setdefault("model_time", generated_utc)
    return output


def overlay_payload(rows: Sequence[Mapping[str, Any]], *, generated_utc: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_utc": generated_utc,
        "as_of_utc": generated_utc,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "staking_or_sizing_guidance": False,
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "raw_payloads_copied_to_repo": False,
        },
        "rows": list(rows),
    }


def write_assembler_report(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-ev-nfl-overlay-assembler.json"
    md_path = out_dir / "kalshi-ev-nfl-overlay-assembler.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-ev-nfl-overlay-assembler.json"
    latest_md = MACRO_DIR / "latest-kalshi-ev-nfl-overlay-assembler.md"
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
        "# Kalshi EV NFL Overlay Assembler",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Research only: `{str(report.get('research_only')).lower()}`",
        f"- Ready target matches: `{summary.get('ready_target_match_count')}`",
        f"- Assembled overlay pairs: `{summary.get('assembled_overlay_pair_count')}`",
        f"- Overlays written: `{str(summary.get('overlays_written')).lower()}`",
        "",
        "## Gates",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for gate in report.get("gates", []):
        reasons = "; ".join(gate.get("reasons") or [])
        lines.append(f"| `{gate.get('name')}` | `{gate.get('status')}` | {reasons} |")
    assembled = report.get("assembled_rows") if isinstance(report.get("assembled_rows"), list) else []
    if assembled:
        lines.extend(
            [
                "",
                "## Assembled Rows",
                "",
                "| Contract | Side | Selection | Probability | Executable Price | Timing |",
                "| --- | --- | --- | ---: | ---: | --- |",
            ]
        )
        for row in assembled:
            lines.append(
                f"| `{row.get('contract_ticker')}` | `{row.get('side')}` | `{row.get('selection')}` | "
                f"{row.get('calibrated_probability')} | {row.get('executable_price')} | "
                f"`{row.get('timing_status')}` |"
            )
    lines.extend(["", "## Next Action", "", str(report.get("next_action") or ""), ""])
    return "\n".join(lines)


def assembler_next_action(*, status: str, overlay_paths: Mapping[str, str]) -> str:
    if status == "nfl_overlay_assembler_overlays_written":
        return (
            "Run make kalshi-ev-overlay-preflight && make kalshi-ev-ledger to evaluate the assembled overlay rows; "
            "execution remains disabled."
        )
    if status == "nfl_overlay_assembler_ready_dry_run":
        return "Re-run with --write to emit overlays outside the repo, then run overlay preflight and the EV ledger."
    if status == "nfl_overlay_assembler_blocked_invalid_ready_match":
        return "Inspect the scout target match; it looked ready but failed overlay assembly validation."
    return (
        "Drop a local Kalshi NFL contract snapshot that passes the scout ready gate, then rerun "
        "make kalshi-ev-local-contract-evidence-scout && make kalshi-ev-nfl-overlay-assembler."
    )


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


def outside_repo(path: Path) -> bool:
    try:
        path.expanduser().resolve().relative_to(CONTROL_REPO.resolve())
    except ValueError:
        return True
    return False


def optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip().rstrip("x%")
            if not value:
                return None
        output = float(value)
    except (TypeError, ValueError):
        return None
    return output if 0.0 <= output <= 1.0 else None


def optional_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_stamp(value: str) -> str:
    stamp = re.sub(r"[^0-9A-Za-z]+", "", value)
    return stamp or "latest"


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
    parser.add_argument("--scout-path", type=Path, default=DEFAULT_SCOUT_PATH)
    parser.add_argument("--work-order-path", type=Path, default=DEFAULT_WORK_ORDER_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--mapping-output-dir", type=Path, default=DEFAULT_MAPPING_OUTPUT_DIR)
    parser.add_argument("--probability-output-dir", type=Path, default=DEFAULT_PROBABILITY_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--no-overlay-write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_nfl_overlay_assembler(
        scout_path=args.scout_path,
        work_order_path=args.work_order_path,
        mapping_output_dir=args.mapping_output_dir,
        probability_output_dir=args.probability_output_dir,
        limit=args.limit,
        emit_overlays=args.write and not args.no_overlay_write,
    )
    if args.write:
        paths = write_assembler_report(report, args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
