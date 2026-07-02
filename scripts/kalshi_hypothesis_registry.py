#!/usr/bin/env python3
"""Build the Kalshi HypothesisCandidate registry and falsification gate.

This is the first signal-factory layer after universe inventory. It turns
market inventory and ledger rows into versioned, non-discretionary research
hypotheses, then blocks promotion until labeled out-of-sample evidence exists.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_UNIVERSE_SCAN_PATH = MACRO_DIR / "latest-kalshi-universe-scan.json"
DEFAULT_EV_LEDGER_PATH = MACRO_DIR / "latest-kalshi-contract-ev-ledger.json"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-hypothesis-registry-latest"
CSV_FIELDS = [
    "hypothesis_id",
    "status",
    "classification",
    "model_route",
    "feature_family",
    "candidate_count",
    "multiple_testing_family",
    "target_contract_class",
    "blocked_reason",
]

FEATURE_FAMILIES: tuple[tuple[str, str, str], ...] = (
    (
        "wide_spread_decay",
        "wide spread",
        "Crowd-implied probabilities in wide-spread markets are miscalibrated relative to an external probability reference after fees.",
    ),
    (
        "low_liquidity_ghost_listing",
        "liquidity",
        "Thin-liquidity markets contain stale or ghost-listing prices that decay after external reference updates.",
    ),
    (
        "near_settlement_probability_decay",
        "settles within",
        "Near-settlement markets underreact to fresh external data before close.",
    ),
    (
        "stale_metadata_update_lag",
        "metadata stale",
        "Markets with stale public metadata exhibit non-random crowd probability lag.",
    ),
    (
        "simple_rule_external_reference",
        "external reference data exists",
        "Simple-rule markets with public external references have measurable crowd miscalibration.",
    ),
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_hypothesis_registry(
    *,
    universe_scan_path: Path = DEFAULT_UNIVERSE_SCAN_PATH,
    ev_ledger_path: Path = DEFAULT_EV_LEDGER_PATH,
    generated_utc: str | None = None,
    max_examples_per_hypothesis: int = 5,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    universe = read_json_or_empty(universe_scan_path)
    ledger = read_json_or_empty(ev_ledger_path)
    universe_safe = safe_research_artifact(universe)
    ledger_safe = safe_research_artifact(ledger)

    universe_candidates = [
        row for row in universe.get("candidates", []) if isinstance(row, Mapping)
    ]
    hypotheses: list[dict[str, Any]] = []
    if universe_safe and universe_candidates:
        hypotheses.extend(
            hypotheses_from_universe(
                universe_candidates,
                source_path=universe_scan_path,
                max_examples=max_examples_per_hypothesis,
            )
        )
    if ledger_safe:
        hypotheses.extend(
            hypotheses_from_ledger(
                [row for row in ledger.get("rows", []) if isinstance(row, Mapping)],
                source_path=ev_ledger_path,
                max_examples=max_examples_per_hypothesis,
            )
        )

    hypotheses = sorted(hypotheses, key=lambda row: row["hypothesis_id"])
    falsification_gate = build_falsification_gate(
        hypotheses,
        universe_safe=universe_safe,
        ledger_safe=ledger_safe,
        generated_utc=generated,
        source_paths=[universe_scan_path, ev_ledger_path],
    )
    summary = registry_summary(hypotheses, falsification_gate=falsification_gate)
    if not universe_safe:
        status = "hypothesis_registry_blocked_missing_universe_inventory"
    elif not hypotheses:
        status = "hypothesis_registry_blocked_no_hypotheses_generated"
    else:
        status = "hypothesis_registry_ready_falsification_blocked_missing_labeled_oos_evidence"

    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": False,
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "north_star": "Extract and exploit mispricings in Kalshi event contracts before the crowd corrects them.",
        "policy": {
            "no_discretion": "Hypotheses are generated from deterministic artifact rules; human selection cannot promote a hypothesis.",
            "signal_breadth": "The registry tracks feature families across routes/classes so many weak hypotheses can be tested without hand-picking.",
            "false_discovery_control": "No hypothesis can be promoted without OOS, cost-aware, FDR-controlled evidence.",
            "ev_boundary": "This registry does not compute usable EV; the contract EV ledger remains the only margin surface.",
        },
        "inputs": {
            "universe_scan_path": str(universe_scan_path),
            "universe_scan_sha256": sha256_or_none(universe_scan_path),
            "ev_ledger_path": str(ev_ledger_path),
            "ev_ledger_sha256": sha256_or_none(ev_ledger_path),
        },
        "summary": summary,
        "hypotheses": hypotheses,
        "falsification_gate": falsification_gate,
        "next_action": {
            "name": "kalshi_labeled_oos_backtest_harness",
            "why": "The registry can now generate hypotheses, but none can promote without labeled outcomes, time-safe splits, costs, and FDR correction.",
            "stop_condition": "Stop before sizing, execution, account/order paths, discretionary selection, or promoting a hypothesis without machine-readable falsification evidence.",
        },
        "safety": safety_flags(),
    }


def hypotheses_from_universe(
    candidates: Sequence[Mapping[str, Any]],
    *,
    source_path: Path,
    max_examples: int,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in candidates:
        classification = str(row.get("classification") or "unknown")
        model_route = str(row.get("model_route") or "unrouted")
        reasons = " | ".join(str(reason).lower() for reason in row.get("softness_reasons", []))
        for family, reason_needle, _claim in FEATURE_FAMILIES:
            if reason_needle in reasons:
                grouped[(classification, model_route, family)].append(row)

    hypotheses: list[dict[str, Any]] = []
    for (classification, model_route, family), rows in grouped.items():
        _, _, claim = next(item for item in FEATURE_FAMILIES if item[0] == family)
        examples = compact_examples(rows[:max_examples])
        filter_text = {
            "classification": classification,
            "model_route": model_route,
            "feature_family": family,
            "artifact_filter": f"softness_reasons contains {family}",
        }
        hypotheses.append(
            hypothesis(
                source="universe_scan",
                source_path=source_path,
                classification=classification,
                model_route=model_route,
                feature_family=family,
                candidate_count=len(rows),
                target_contract_class=f"{classification}_kalshi_public_market",
                signal_definition=claim,
                market_universe_filter=filter_text,
                examples=examples,
                multiple_testing_family=f"universe::{classification}::{family}",
                external_data_requirements=external_requirements(classification),
            )
        )
    return hypotheses


def hypotheses_from_ledger(
    rows: Sequence[Mapping[str, Any]],
    *,
    source_path: Path,
    max_examples: int,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        source_repo = str(row.get("source_repo_id") or "unknown_repo")
        market_type = str(row.get("market_type") or "unknown_market")
        if row.get("calibrated_probability") is not None:
            grouped[(source_repo, market_type, "calibrated_probability_decay")].append(row)
        if row.get("gate_status") == "pass" or row.get("usable") is True:
            grouped[(source_repo, market_type, "legacy_positive_margin_survival")].append(row)

    hypotheses: list[dict[str, Any]] = []
    for (source_repo, market_type, family), ledger_rows in grouped.items():
        classification = infer_classification_from_market_type(market_type, source_repo)
        examples = compact_ledger_examples(ledger_rows[:max_examples])
        hypotheses.append(
            hypothesis(
                source="contract_ev_ledger",
                source_path=source_path,
                classification=classification,
                model_route=source_repo,
                feature_family=family,
                candidate_count=len(ledger_rows),
                target_contract_class=market_type,
                signal_definition=(
                    "Calibrated model probability minus all-in Kalshi break-even remains positive "
                    "after repeat snapshots, settlement, and cost-aware out-of-sample validation."
                ),
                market_universe_filter={
                    "source_repo_id": source_repo,
                    "market_type": market_type,
                    "feature_family": family,
                },
                examples=examples,
                multiple_testing_family=f"ev_ledger::{source_repo}::{market_type}::{family}",
                external_data_requirements=[
                    "settled contract outcomes",
                    "historical Kalshi quotes captured before decision time",
                    "model probabilities generated before market close",
                    "all-in execution cost estimates or verified ticket costs",
                ],
            )
        )
    return hypotheses


def hypothesis(
    *,
    source: str,
    source_path: Path,
    classification: str,
    model_route: str,
    feature_family: str,
    candidate_count: int,
    target_contract_class: str,
    signal_definition: str,
    market_universe_filter: Mapping[str, Any],
    examples: Sequence[Mapping[str, Any]],
    multiple_testing_family: str,
    external_data_requirements: Sequence[str],
) -> dict[str, Any]:
    material = json.dumps(
        {
            "source": source,
            "classification": classification,
            "model_route": model_route,
            "feature_family": feature_family,
            "target_contract_class": target_contract_class,
            "market_universe_filter": market_universe_filter,
        },
        sort_keys=True,
    )
    hypothesis_id = "hyp_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return {
        "schema_version": "HypothesisCandidateV1",
        "hypothesis_id": hypothesis_id,
        "status": "candidate_unvalidated",
        "source": source,
        "source_artifact": str(source_path),
        "source_artifact_sha256": sha256_or_none(source_path),
        "classification": classification,
        "model_route": model_route,
        "feature_family": feature_family,
        "candidate_count": candidate_count,
        "target_contract_class": target_contract_class,
        "market_universe_filter": dict(market_universe_filter),
        "signal_definition": signal_definition,
        "null_hypothesis": "After costs and time-safe validation, the signal has zero or negative expected value versus the Kalshi executable break-even.",
        "training_window_policy": "Use only observations timestamped before the validation decision point.",
        "validation_window_policy": "Use walk-forward or purged out-of-sample windows with no label overlap.",
        "cost_model": "All-in executable Kalshi break-even from the contract EV ledger, including known fees/slippage where available.",
        "multiple_testing_family": multiple_testing_family,
        "promotion_rule": "Requires positive OOS edge after all-in costs, FDR-adjusted q-value below threshold, adequate sample size, and no failed safety gates.",
        "retirement_rule": "Retire after repeated OOS failure, vanished capacity, or decay below cost-aware threshold.",
        "external_data_requirements": list(external_data_requirements),
        "example_contracts": list(examples),
        "gates": [
            {
                "name": "labeled_oos_evidence",
                "status": "blocked",
                "reason": "No labeled out-of-sample evidence packet is attached to this hypothesis.",
            },
            {
                "name": "fdr_controlled_significance",
                "status": "blocked",
                "reason": "No multiple-testing-corrected falsification result exists yet.",
            },
            {
                "name": "cost_aware_validation",
                "status": "blocked",
                "reason": "No backtest packet proves the signal survives all-in execution costs.",
            },
            {
                "name": "no_execution_boundary",
                "status": "pass",
                "reason": "Hypothesis registry is research-only and contains no account/order fields.",
            },
        ],
        "blocked_reason": "missing_labeled_oos_fdr_cost_aware_evidence",
        "calibrated_probability": None,
        "edge_probability": None,
        "usable": False,
        "safety": safety_flags(),
    }


def build_falsification_gate(
    hypotheses: Sequence[Mapping[str, Any]],
    *,
    universe_safe: bool,
    ledger_safe: bool,
    generated_utc: str,
    source_paths: Sequence[Path],
) -> dict[str, Any]:
    gates = [
        {
            "name": "universe_inventory_safe",
            "status": "pass" if universe_safe else "blocked",
            "reason": "Universe inventory is research-only and available." if universe_safe else "Universe inventory is missing or unsafe.",
        },
        {
            "name": "hypothesis_registry_nonempty",
            "status": "pass" if hypotheses else "blocked",
            "reason": f"{len(hypotheses)} hypothesis candidate(s) generated." if hypotheses else "No hypotheses generated.",
        },
        {
            "name": "contract_ev_cost_surface_available",
            "status": "pass" if ledger_safe else "warn",
            "reason": "EV ledger is available for all-in break-even costs." if ledger_safe else "EV ledger is missing; costs must be supplied before testing.",
        },
        {
            "name": "labeled_oos_evidence_available",
            "status": "blocked",
            "reason": "No labeled outcomes/backtest packet exists for these hypothesis IDs.",
        },
        {
            "name": "walk_forward_or_purged_split",
            "status": "blocked",
            "reason": "No time-safe split packet exists; random/k-fold validation is not acceptable.",
        },
        {
            "name": "fdr_multiple_testing_control",
            "status": "blocked",
            "reason": "No Benjamini-Hochberg/BY or equivalent q-value packet exists for the tested family.",
        },
        {
            "name": "promotion_disabled_until_falsified",
            "status": "pass",
            "reason": "All generated hypotheses remain candidate_unvalidated.",
        },
    ]
    counts = Counter(gate["status"] for gate in gates)
    status = (
        "falsification_gate_blocked_missing_labeled_oos_evidence"
        if hypotheses
        else "falsification_gate_blocked_missing_hypotheses"
    )
    return {
        "schema_version": 1,
        "generated_utc": generated_utc,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "source_artifacts": [str(path) for path in source_paths],
        "tested_hypothesis_count": 0,
        "registered_hypothesis_count": len(hypotheses),
        "promoted_hypothesis_count": 0,
        "rejected_hypothesis_count": 0,
        "blocked_hypothesis_count": len(hypotheses),
        "required_method": {
            "split": "walk_forward_or_purged_oos",
            "multiple_testing": "fdr_controlled_q_values",
            "costs": "all_in_kalshi_break_even_from_ev_ledger",
            "minimum_policy": "promotion requires OOS survival after costs and FDR correction",
        },
        "gates": gates,
        "gate_counts": {
            "pass": counts["pass"],
            "warn": counts["warn"],
            "blocked": counts["blocked"],
            "fail": counts["fail"],
        },
        "safety": safety_flags(),
    }


def registry_summary(
    hypotheses: Sequence[Mapping[str, Any]],
    *,
    falsification_gate: Mapping[str, Any],
) -> dict[str, Any]:
    by_status = Counter(str(row.get("status") or "unknown") for row in hypotheses)
    by_route = Counter(str(row.get("model_route") or "unknown") for row in hypotheses)
    by_classification = Counter(str(row.get("classification") or "unknown") for row in hypotheses)
    by_feature = Counter(str(row.get("feature_family") or "unknown") for row in hypotheses)
    families = {str(row.get("multiple_testing_family") or "") for row in hypotheses}
    return {
        "hypothesis_count": len(hypotheses),
        "candidate_unvalidated_count": by_status["candidate_unvalidated"],
        "promoted_hypothesis_count": 0,
        "rejected_hypothesis_count": 0,
        "blocked_by_falsification_count": int(falsification_gate.get("blocked_hypothesis_count") or 0),
        "multiple_testing_family_count": len([family for family in families if family]),
        "by_status": dict(sorted(by_status.items())),
        "by_route": dict(sorted(by_route.items())),
        "by_classification": dict(sorted(by_classification.items())),
        "by_feature_family": dict(sorted(by_feature.items())),
        "falsification_status": falsification_gate.get("status"),
        "gate_counts": falsification_gate.get("gate_counts", {}),
    }


def compact_examples(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for row in rows:
        examples.append(
            {
                "ticker": row.get("ticker"),
                "event_ticker": row.get("event_ticker"),
                "title": row.get("title"),
                "yes_ask": row.get("yes_ask"),
                "no_ask": row.get("no_ask"),
                "time_to_close_hours": row.get("time_to_close_hours"),
                "softness_score": row.get("softness_score"),
            }
        )
    return examples


def compact_ledger_examples(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for row in rows:
        examples.append(
            {
                "contract_ticker": row.get("contract_ticker"),
                "side": row.get("side"),
                "title": row.get("title"),
                "all_in_break_even_probability": row.get("all_in_break_even_probability"),
                "calibrated_probability": row.get("calibrated_probability"),
                "margin_probability": row.get("margin_probability"),
                "gate_status": row.get("gate_status"),
            }
        )
    return examples


def external_requirements(classification: str) -> list[str]:
    base = [
        "historical Kalshi quote snapshots before decision time",
        "settled contract outcomes",
        "all-in execution cost estimates or verified ticket costs",
    ]
    extra = {
        "mlb": ["game/prop model probabilities generated before close", "official settled game results"],
        "nfl": ["game/prop model probabilities generated before close", "official settled game results"],
        "nba": ["game/prop model probabilities generated before close", "official settled game results"],
        "atp": ["match model probabilities generated before close", "official settled match results"],
        "weather": ["station/location official weather observations", "forecast snapshots available before close"],
        "macro_econ": ["release calendar timestamps", "official economic release values"],
        "finance_crypto": ["reference asset price snapshots", "official settlement source values"],
        "politics_policy": ["official resolution source timeline", "timestamped public polling/news features"],
    }
    return base + extra.get(classification, ["explicit external reference source selected before testing"])


def infer_classification_from_market_type(market_type: str, source_repo: str) -> str:
    text = f"{market_type} {source_repo}".lower()
    if "mlb" in text or "baseball" in text:
        return "mlb"
    if "nfl" in text or "football" in text:
        return "nfl"
    if "nba" in text or "basketball" in text:
        return "nba"
    if "atp" in text or "tennis" in text:
        return "atp"
    return "unknown"


def safe_research_artifact(value: Mapping[str, Any]) -> bool:
    safety = value.get("safety") if isinstance(value.get("safety"), Mapping) else {}
    return (
        value.get("research_only") is True
        and value.get("execution_enabled") is False
        and value.get("market_execution") is not True
        and value.get("account_or_order_paths") is not True
        and safety.get("market_execution") is False
        and safety.get("account_or_order_paths") is False
        and safety.get("database_writes") is False
    )


def safety_flags() -> dict[str, bool]:
    return {
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
    }


def read_json_or_empty(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def sha256_or_none(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_hypothesis_registry(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-hypothesis-registry.json"
    markdown_path = out_dir / "kalshi-hypothesis-registry.md"
    csv_path = out_dir / "kalshi-hypothesis-registry.csv"
    gate_json_path = out_dir / "kalshi-falsification-gate.json"
    gate_markdown_path = out_dir / "kalshi-falsification-gate.md"

    registry_text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    gate = report.get("falsification_gate") if isinstance(report.get("falsification_gate"), Mapping) else {}
    gate_text = json.dumps(gate, indent=2, sort_keys=True, default=str) + "\n"

    json_path.write_text(registry_text, encoding="utf-8")
    markdown_path.write_text(render_registry_markdown(report), encoding="utf-8")
    write_registry_csv(report.get("hypotheses", []), csv_path)
    gate_json_path.write_text(gate_text, encoding="utf-8")
    gate_markdown_path.write_text(render_gate_markdown(gate), encoding="utf-8")

    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_registry_json = MACRO_DIR / "latest-kalshi-hypothesis-registry.json"
    latest_registry_md = MACRO_DIR / "latest-kalshi-hypothesis-registry.md"
    latest_registry_csv = MACRO_DIR / "latest-kalshi-hypothesis-registry.csv"
    latest_gate_json = MACRO_DIR / "latest-kalshi-falsification-gate.json"
    latest_gate_md = MACRO_DIR / "latest-kalshi-falsification-gate.md"
    latest_registry_json.write_text(registry_text, encoding="utf-8")
    latest_registry_md.write_text(render_registry_markdown(report), encoding="utf-8")
    write_registry_csv(report.get("hypotheses", []), latest_registry_csv)
    latest_gate_json.write_text(gate_text, encoding="utf-8")
    latest_gate_md.write_text(render_gate_markdown(gate), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "csv_path": str(csv_path),
        "falsification_gate_json_path": str(gate_json_path),
        "falsification_gate_markdown_path": str(gate_markdown_path),
        "latest_json_path": str(latest_registry_json),
        "latest_markdown_path": str(latest_registry_md),
        "latest_csv_path": str(latest_registry_csv),
        "latest_falsification_gate_json_path": str(latest_gate_json),
        "latest_falsification_gate_markdown_path": str(latest_gate_md),
    }


def write_registry_csv(hypotheses: Any, path: Path) -> None:
    rows = [row for row in hypotheses if isinstance(row, Mapping)]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in CSV_FIELDS})


def render_registry_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Hypothesis Registry",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Hypotheses: `{summary.get('hypothesis_count', 0)}`",
        f"- Multiple-testing families: `{summary.get('multiple_testing_family_count', 0)}`",
        f"- Falsification status: `{summary.get('falsification_status')}`",
        f"- Execution enabled: `{str(report.get('execution_enabled')).lower()}`",
        "",
        "## Route Counts",
        "",
    ]
    by_route = summary.get("by_route") if isinstance(summary.get("by_route"), Mapping) else {}
    for route, count in by_route.items():
        lines.append(f"- `{route}`: `{count}`")
    lines.extend(
        [
            "",
            "## Guardrail",
            "",
            "Every hypothesis is unvalidated. This artifact does not compute usable EV, pick trades, size positions, or authorize execution.",
            "",
        ]
    )
    return "\n".join(lines)


def render_gate_markdown(gate: Mapping[str, Any]) -> str:
    lines = [
        "# Kalshi Falsification Gate",
        "",
        f"- Status: `{gate.get('status')}`",
        f"- Registered hypotheses: `{gate.get('registered_hypothesis_count', 0)}`",
        f"- Tested hypotheses: `{gate.get('tested_hypothesis_count', 0)}`",
        f"- Promoted hypotheses: `{gate.get('promoted_hypothesis_count', 0)}`",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for item in gate.get("gates", []):
        if isinstance(item, Mapping):
            lines.append(f"| `{item.get('name')}` | `{item.get('status')}` | {item.get('reason')} |")
    lines.extend(
        [
            "",
            "No hypothesis may promote without labeled OOS evidence, time-safe validation, FDR correction, and cost-aware survival.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-scan-path", type=Path, default=DEFAULT_UNIVERSE_SCAN_PATH)
    parser.add_argument("--ev-ledger-path", type=Path, default=DEFAULT_EV_LEDGER_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-examples-per-hypothesis", type=int, default=5)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_hypothesis_registry(
        universe_scan_path=args.universe_scan_path,
        ev_ledger_path=args.ev_ledger_path,
        max_examples_per_hypothesis=args.max_examples_per_hypothesis,
    )
    if args.write:
        paths = write_hypothesis_registry(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
