#!/usr/bin/env python3
"""Diagnose World Cup outcome independence versus shared match correlation.

This report answers the Claude-advice question: whether World Cup totals,
BTTS, spreads, halves, and match-winner contracts can run as parallel label
clocks without pretending they are independent portfolio risk.

It is deliberately diagnostic only. It does not change the World Cup
falsification rule, compute EV, size paper stake, or create orders.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = CONTROL_REPO / "scripts"
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kalshi_falsification_replay_shared import (  # noqa: E402
    DEFAULT_MIN_INDEPENDENT_LABELS,
    DEFAULT_MIN_OOS_LABELS,
    independent_contract_rows,
    load_label_packets,
)
from kalshi_world_cup_proxy_feature_model_falsification import (  # noqa: E402
    normalize_world_cup_label_rows,
)

from predmarket.shared_helpers import (  # noqa: E402
    counts,
    gate_counts,
    path_is_within,
    read_json_or_empty,
    safe_research_artifact,
    safety_flags,
    sha256_or_none,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_LABEL_DIR = Path("/home/mrwatson/manual_drops/kalshi_world_cup_proxy_labels")
DEFAULT_WORLD_CUP_MODEL_PATH = (
    MACRO_DIR / "latest-kalshi-world-cup-proxy-feature-model-falsification.json"
)
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-world-cup-outcome-independence-diagnostic-latest"

CSV_FIELDS = [
    "outcome_family",
    "contract_label_count",
    "event_market_label_count",
    "outcome_family_label_count",
    "match_cluster_count",
    "series_tickers",
    "market_types",
    "sample_match_clusters",
    "hypothesis_counting_unit",
    "portfolio_cluster_unit",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_world_cup_outcome_independence_diagnostic(
    *,
    label_dir: Path = DEFAULT_LABEL_DIR,
    world_cup_model_path: Path = DEFAULT_WORLD_CUP_MODEL_PATH,
    generated_utc: str | None = None,
    min_independent_labels: int = DEFAULT_MIN_INDEPENDENT_LABELS,
    min_oos_labels: int = DEFAULT_MIN_OOS_LABELS,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    model = read_json_or_empty(world_cup_model_path)
    label_load = load_label_packets(label_dir)
    normalized_rows, invalid_rows = normalize_world_cup_label_rows(label_load["rows"])
    contract_rows = independent_contract_rows(normalized_rows)
    enriched_rows = [enriched_label_row(row) for row in contract_rows]
    outcome_rows = outcome_family_rows(enriched_rows)
    match_rows = match_cluster_rows(enriched_rows)
    summary = build_summary(
        label_load=label_load,
        model=model,
        normalized_rows=normalized_rows,
        contract_rows=enriched_rows,
        invalid_rows=invalid_rows,
        outcome_rows=outcome_rows,
        match_rows=match_rows,
        min_independent_labels=min_independent_labels,
        min_oos_labels=min_oos_labels,
    )
    gates = build_gates(
        label_load=label_load,
        model=model,
        summary=summary,
        outcome_rows=outcome_rows,
        match_rows=match_rows,
    )
    status = report_status(gates, summary)
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": False,
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "family_id": "world_cup_soccer",
        "method": {
            "purpose": "Separate duplicate contract labels, genuinely distinct outcome-family clocks, and shared match-level portfolio correlation.",
            "current_falsification_counting_unit": "exact_contract_ticker",
            "diagnostic_counting_units": [
                "exact_contract_ticker",
                "event_ticker",
                "match_key|outcome_family",
                "match_key",
            ],
            "portfolio_correlation_rule": "All World Cup outcome families from the same match must share a match-level correlation cluster for paper/live portfolio controls.",
            "boundary": "Diagnostic only; does not lower thresholds, rewrite label ledgers, promote candidates, or emit EV/stake/order fields.",
        },
        "inputs": {
            "label_dir": str(label_dir),
            "label_packet_count": label_load["packet_count"],
            "label_packet_paths": label_load["packet_paths"],
            "unsafe_packet_count": len(label_load["unsafe_packets"]),
            "world_cup_model_path": str(world_cup_model_path),
            "world_cup_model_sha256": sha256_or_none(world_cup_model_path),
            "world_cup_model_status": model.get("status"),
            "min_independent_labels": min_independent_labels,
            "min_oos_labels": min_oos_labels,
        },
        "summary": summary,
        "outcome_family_rows": outcome_rows,
        "match_cluster_rows": match_rows,
        "label_rows_sample": enriched_rows[:25],
        "invalid_label_rows_sample": invalid_rows[:50],
        "gates": gates,
        "next_action": next_action(status, summary),
        "safety": safety_flags(),
    }


def enriched_label_row(row: Mapping[str, Any]) -> dict[str, Any]:
    match_key = world_cup_match_key(row)
    family = outcome_family(row)
    event_ticker = str(row.get("event_ticker") or "").strip().upper()
    return {
        **dict(row),
        "world_cup_match_key": match_key,
        "outcome_family": family,
        "event_market_key": f"world_cup_event|{event_ticker or 'unknown'}",
        "outcome_clock_key": f"world_cup_outcome|{match_key}|{family}",
        "correlation_cluster_key": f"world_cup_match|{match_key}",
        "hypothesis_counting_unit": "match_outcome_family",
        "portfolio_cluster_unit": "match",
    }


def world_cup_match_key(row: Mapping[str, Any]) -> str:
    event = str(row.get("event_ticker") or "").strip().upper()
    series = str(row.get("series_ticker") or "").strip().upper()
    if event and series and event.startswith(series):
        slug = event[len(series) :].lstrip("-")
    elif event and "-" in event:
        slug = event.split("-", maxsplit=1)[1]
    else:
        ticker = str(row.get("contract_ticker") or "").strip().upper()
        parts = ticker.split("-")
        slug = parts[1] if len(parts) >= 3 else ticker
    return slug or "unknown"


def outcome_family(row: Mapping[str, Any]) -> str:
    series = str(row.get("series_ticker") or "").upper()
    market_type = str(row.get("market_type") or "").lower()
    period = "full_time"
    if "1H" in series or market_type == "first_half":
        period = "first_half"
    elif "2H" in series or market_type == "second_half":
        period = "second_half"

    if "BTTS" in series or market_type == "both_teams_to_score":
        return "both_teams_to_score"
    if "TOTAL" in series or market_type == "total":
        return f"{period}_total_goals"
    if "SPREAD" in series or market_type == "spread":
        return f"{period}_goal_spread"
    if "CORNERS" in series:
        return f"{period}_corners"
    if market_type in {"game", "first_half", "second_half"} or series in {
        "KXWCGAME",
        "KXWC1H",
        "KXWC2H",
    }:
        return f"{period}_match_result"
    return market_type or series.lower() or "unknown"


def outcome_family_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("outcome_family") or "unknown")].append(row)

    output: list[dict[str, Any]] = []
    for family, items in sorted(grouped.items()):
        event_markets = {str(row.get("event_market_key") or "") for row in items}
        outcome_clocks = {str(row.get("outcome_clock_key") or "") for row in items}
        match_clusters = {str(row.get("correlation_cluster_key") or "") for row in items}
        output.append(
            {
                "outcome_family": family,
                "contract_label_count": len(items),
                "event_market_label_count": len(event_markets),
                "outcome_family_label_count": len(outcome_clocks),
                "match_cluster_count": len(match_clusters),
                "series_tickers": sorted({str(row.get("series_ticker") or "") for row in items}),
                "market_types": sorted({str(row.get("market_type") or "") for row in items}),
                "sample_match_clusters": sorted(match_clusters)[:6],
                "hypothesis_counting_unit": "one label per match/outcome_family clock",
                "portfolio_cluster_unit": "world_cup_match",
            }
        )
    return output


def match_cluster_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("correlation_cluster_key") or "world_cup_match|unknown")].append(row)

    output: list[dict[str, Any]] = []
    for cluster, items in sorted(grouped.items()):
        output.append(
            {
                "correlation_cluster_key": cluster,
                "match_key": str(items[0].get("world_cup_match_key") or "unknown"),
                "contract_label_count": len(items),
                "event_market_label_count": len(
                    {str(row.get("event_market_key") or "") for row in items}
                ),
                "outcome_family_label_count": len(
                    {str(row.get("outcome_clock_key") or "") for row in items}
                ),
                "outcome_families": sorted(
                    {str(row.get("outcome_family") or "unknown") for row in items}
                ),
                "portfolio_cluster_unit": "world_cup_match",
            }
        )
    return output


def build_summary(
    *,
    label_load: Mapping[str, Any],
    model: Mapping[str, Any],
    normalized_rows: Sequence[Mapping[str, Any]],
    contract_rows: Sequence[Mapping[str, Any]],
    invalid_rows: Sequence[Mapping[str, Any]],
    outcome_rows: Sequence[Mapping[str, Any]],
    match_rows: Sequence[Mapping[str, Any]],
    min_independent_labels: int,
    min_oos_labels: int,
) -> dict[str, Any]:
    model_summary = model.get("summary") if isinstance(model.get("summary"), Mapping) else {}
    outcome_clock_count = len({str(row.get("outcome_clock_key") or "") for row in contract_rows})
    event_market_count = len({str(row.get("event_market_key") or "") for row in contract_rows})
    match_cluster_count = len(
        {str(row.get("correlation_cluster_key") or "") for row in contract_rows}
    )
    exact_count = len(contract_rows)
    non_match_result_families = [
        str(row.get("outcome_family") or "")
        for row in outcome_rows
        if "match_result" not in str(row.get("outcome_family") or "")
        and int_value(row.get("outcome_family_label_count")) > 0
    ]
    current_candidate_count = int_value(model_summary.get("research_candidate_count"))
    outcome_family_deficit = max(min_independent_labels - outcome_clock_count, 0)
    return {
        "raw_label_row_count": len(label_load.get("rows", [])),
        "valid_label_row_count": len(normalized_rows),
        "invalid_label_row_count": len(invalid_rows),
        "unsafe_label_packet_count": len(label_load.get("unsafe_packets", [])),
        "exact_contract_label_count": exact_count,
        "event_market_label_count": event_market_count,
        "outcome_family_label_count": outcome_clock_count,
        "match_cluster_count": match_cluster_count,
        "outcome_family_count": len(outcome_rows),
        "non_match_result_outcome_family_count": len(non_match_result_families),
        "non_match_result_outcome_families": sorted(non_match_result_families),
        "series_counts": counts(row.get("series_ticker") for row in contract_rows),
        "market_type_counts": counts(row.get("market_type") for row in contract_rows),
        "outcome_family_contract_counts": {
            row["outcome_family"]: row["contract_label_count"] for row in outcome_rows
        },
        "outcome_family_clock_counts": {
            row["outcome_family"]: row["outcome_family_label_count"] for row in outcome_rows
        },
        "min_independent_labels": min_independent_labels,
        "min_oos_labels": min_oos_labels,
        "outcome_family_label_deficit": outcome_family_deficit,
        "match_cluster_label_deficit": max(min_independent_labels - match_cluster_count, 0),
        "exact_contract_over_outcome_family_inflation": ratio(exact_count, outcome_clock_count),
        "exact_contract_over_match_cluster_inflation": ratio(exact_count, match_cluster_count),
        "current_world_cup_falsification_status": model.get("status"),
        "current_world_cup_research_candidate_count": current_candidate_count,
        "current_world_cup_independent_contract_label_count": int_value(
            model_summary.get("independent_contract_label_count")
        ),
        "current_world_cup_oos_inferred_or_reported_count": int_value(
            model_summary.get("oos_label_count")
        ),
        "outcome_level_parallel_clock_supported": outcome_clock_count > match_cluster_count
        and bool(non_match_result_families),
        "current_candidate_independence_requires_review": current_candidate_count > 0
        and outcome_family_deficit > 0,
        "recommended_hypothesis_counting_unit": "match_outcome_family",
        "recommended_portfolio_cluster_unit": "world_cup_match",
        "recommended_correlation_policy": (
            "Count at most one effective hypothesis label per match/outcome_family clock; "
            "keep all outcome families from the same match in one portfolio correlation cluster."
        ),
    }


def build_gates(
    *,
    label_load: Mapping[str, Any],
    model: Mapping[str, Any],
    summary: Mapping[str, Any],
    outcome_rows: Sequence[Mapping[str, Any]],
    match_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    unsafe_packets = int_value(summary.get("unsafe_label_packet_count"))
    exact_count = int_value(summary.get("exact_contract_label_count"))
    outcome_count = int_value(summary.get("outcome_family_label_count"))
    match_count = int_value(summary.get("match_cluster_count"))
    model_safe = safe_research_artifact(model)
    return [
        gate(
            "label_packets_safe",
            "pass" if unsafe_packets == 0 else "fail",
            f"{unsafe_packets} unsafe label packet(s).",
        ),
        gate(
            "label_packets_loaded",
            "pass" if int_value(label_load.get("packet_count")) > 0 else "blocked",
            f"{label_load.get('packet_count')} safe label packet(s) loaded.",
        ),
        gate(
            "world_cup_model_artifact_safe",
            "pass" if model_safe else "warn",
            f"World Cup model artifact status: {model.get('status')}.",
        ),
        gate(
            "exact_contract_labels_available",
            "pass" if exact_count > 0 else "blocked",
            f"{exact_count} exact-contract label(s) after duplicate-contract collapse.",
        ),
        gate(
            "outcome_family_keys_derived",
            "pass" if outcome_rows and outcome_count > 0 else "blocked",
            f"{outcome_count} match/outcome-family clock(s) across {len(outcome_rows)} outcome family row(s).",
        ),
        gate(
            "match_correlation_clusters_derived",
            "pass" if match_rows and match_count > 0 else "blocked",
            f"{match_count} match-level correlation cluster(s).",
        ),
        gate(
            "parallel_outcome_clock_supported",
            "pass" if summary.get("outcome_level_parallel_clock_supported") is True else "warn",
            (f"{outcome_count} outcome-family clock(s) versus {match_count} match cluster(s)."),
        ),
        gate(
            "current_candidate_independence_review",
            "warn"
            if summary.get("current_candidate_independence_requires_review") is True
            else "pass",
            (
                "Current World Cup research candidate count is "
                f"{summary.get('current_world_cup_research_candidate_count')}; "
                f"outcome-family label deficit is {summary.get('outcome_family_label_deficit')}."
            ),
        ),
        gate(
            "portfolio_match_cluster_required",
            "pass",
            "Portfolio controls must cluster all World Cup outcomes by match even when hypothesis labels are counted by outcome family.",
        ),
        gate(
            "no_probability_ev_or_execution_claims",
            "pass",
            "Diagnostic emits no calibrated probability, EV, sizing, or order fields.",
        ),
    ]


def report_status(gates: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> str:
    if any(item.get("status") == "fail" for item in gates):
        return "world_cup_outcome_independence_diagnostic_failed_safety_gate"
    if any(item.get("status") == "blocked" for item in gates):
        return "world_cup_outcome_independence_diagnostic_blocked_missing_labels"
    if summary.get("current_candidate_independence_requires_review") is True:
        return "world_cup_outcome_independence_diagnostic_ready_candidate_independence_review"
    if summary.get("outcome_level_parallel_clock_supported") is True:
        return "world_cup_outcome_independence_diagnostic_ready_parallel_outcome_clocks"
    return "world_cup_outcome_independence_diagnostic_ready_match_level_capped"


def next_action(status: str, summary: Mapping[str, Any]) -> dict[str, str]:
    if status.endswith("failed_safety_gate"):
        return {
            "name": "kalshi_world_cup_label_packet_safety_audit",
            "why": "At least one World Cup label packet is unsafe.",
            "stop_condition": "Stop before using unsafe labels or overriding research-only flags.",
        }
    if status.endswith("blocked_missing_labels"):
        return {
            "name": "kalshi_world_cup_exact_settlement_accumulation",
            "why": "No safe exact World Cup labels are available for independence diagnostics.",
            "stop_condition": "Stop before using non-Kalshi outcomes as settlement labels.",
        }
    if status.endswith("candidate_independence_review"):
        return {
            "name": "kalshi_world_cup_falsification_independence_review",
            "why": (
                "A current World Cup research candidate exists under exact-contract counting, "
                "but match/outcome-family clocks are still below the independent-label threshold."
            ),
            "stop_condition": "Stop before downstream EV/paper promotion unless correlation clustering and independence counting are explicitly reconciled.",
        }
    if summary.get("outcome_level_parallel_clock_supported") is True:
        return {
            "name": "kalshi_world_cup_parallel_outcome_label_clocks",
            "why": "World Cup has distinct outcome-family clocks beyond match-winner labels.",
            "stop_condition": "Stop before counting same-match outcome families as separate portfolio clusters.",
        }
    return {
        "name": "kalshi_world_cup_match_level_label_accumulation",
        "why": "World Cup evidence is still effectively capped at the match level.",
        "stop_condition": "Stop before padding label counts with duplicate same-match contracts.",
    }


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def gate_counts_for(gates: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return gate_counts(gates)


def ratio(left: int, right: int) -> float | None:
    if right <= 0:
        return None
    return round(left / right, 4)


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def write_outputs(report: Mapping[str, Any], *, out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-world-cup-outcome-independence-diagnostic.json"
    md_path = out_dir / "kalshi-world-cup-outcome-independence-diagnostic.md"
    csv_path = out_dir / "kalshi-world-cup-outcome-independence-diagnostic.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("outcome_family_rows", []), csv_path)

    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
    }
    if path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-world-cup-outcome-independence-diagnostic.json"
        latest_md = MACRO_DIR / "latest-kalshi-world-cup-outcome-independence-diagnostic.md"
        latest_csv = MACRO_DIR / "latest-kalshi-world-cup-outcome-independence-diagnostic.csv"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        write_csv(report.get("outcome_family_rows", []), latest_csv)
        paths.update(
            {
                "latest_json_path": str(latest_json),
                "latest_markdown_path": str(latest_md),
                "latest_csv_path": str(latest_csv),
            }
        )
    return paths


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi World Cup Outcome Independence Diagnostic",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Exact-contract labels: `{summary.get('exact_contract_label_count')}`",
        f"- Event-market labels: `{summary.get('event_market_label_count')}`",
        f"- Match/outcome-family clocks: `{summary.get('outcome_family_label_count')}`",
        f"- Match correlation clusters: `{summary.get('match_cluster_count')}`",
        f"- Current World Cup research candidates: `{summary.get('current_world_cup_research_candidate_count')}`",
        f"- Outcome-family label deficit: `{summary.get('outcome_family_label_deficit')}`",
        f"- Contract/outcome inflation: `{summary.get('exact_contract_over_outcome_family_inflation')}`",
        f"- Contract/match inflation: `{summary.get('exact_contract_over_match_cluster_inflation')}`",
        f"- Recommended hypothesis unit: `{summary.get('recommended_hypothesis_counting_unit')}`",
        f"- Recommended portfolio cluster: `{summary.get('recommended_portfolio_cluster_unit')}`",
        "",
        "## Gates",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for item in report.get("gates", []):
        if isinstance(item, Mapping):
            lines.append(
                f"| `{item.get('name')}` | `{item.get('status')}` | {item.get('reason')} |"
            )
    lines.extend(
        [
            "",
            "## Outcome Families",
            "",
            "| Outcome family | Contracts | Event markets | Outcome clocks | Match clusters |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report.get("outcome_family_rows", []):
        if isinstance(row, Mapping):
            lines.append(
                f"| `{row.get('outcome_family')}` | "
                f"{row.get('contract_label_count')} | "
                f"{row.get('event_market_label_count')} | "
                f"{row.get('outcome_family_label_count')} | "
                f"{row.get('match_cluster_count')} |"
            )
    next_step = report.get("next_action") if isinstance(report.get("next_action"), Mapping) else {}
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            f"- Name: `{next_step.get('name')}`",
            f"- Why: {next_step.get('why')}",
            f"- Stop condition: {next_step.get('stop_condition')}",
            "",
            "## Guardrail",
            "",
            "This diagnostic is research-only. It does not compute probability, EV, paper stake, live eligibility, or orders.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            output = dict(row)
            for key in ("series_tickers", "market_types", "sample_match_clusters"):
                if isinstance(output.get(key), list):
                    output[key] = ",".join(str(item) for item in output[key])
            writer.writerow(output)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument("--world-cup-model-path", type=Path, default=DEFAULT_WORLD_CUP_MODEL_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--min-independent-labels", type=int, default=DEFAULT_MIN_INDEPENDENT_LABELS
    )
    parser.add_argument("--min-oos-labels", type=int, default=DEFAULT_MIN_OOS_LABELS)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_world_cup_outcome_independence_diagnostic(
        label_dir=args.label_dir,
        world_cup_model_path=args.world_cup_model_path,
        min_independent_labels=args.min_independent_labels,
        min_oos_labels=args.min_oos_labels,
    )
    if args.write:
        paths = write_outputs(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
