#!/usr/bin/env python3
"""Run labeled OOS falsification for registered Kalshi hypotheses.

The harness consumes safe local label packets keyed by HypothesisCandidate IDs.
It does not fetch providers, write databases, size positions, or authorize
execution. If labels are missing, it writes a blocked report that names the
exact missing evidence contract.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_REGISTRY_PATH = MACRO_DIR / "latest-kalshi-hypothesis-registry.json"
DEFAULT_LABEL_DIR = Path("/home/mrwatson/manual_drops/kalshi_oos_labels")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-labeled-oos-backtest-latest"
DEFAULT_MIN_OBSERVATIONS = 30
DEFAULT_MIN_OOS_OBSERVATIONS = 10
DEFAULT_FDR_ALPHA = 0.10
DEFAULT_TEST_FRACTION = 0.30
CSV_FIELDS = [
    "hypothesis_id",
    "status",
    "observation_count",
    "time_safe_count",
    "positive_decision_count",
    "oos_count",
    "mean_expected_edge",
    "mean_realized_pnl_per_contract",
    "win_rate",
    "p_value",
    "q_value",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_labeled_oos_backtest(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    label_dir: Path = DEFAULT_LABEL_DIR,
    generated_utc: str | None = None,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
    min_oos_observations: int = DEFAULT_MIN_OOS_OBSERVATIONS,
    fdr_alpha: float = DEFAULT_FDR_ALPHA,
    test_fraction: float = DEFAULT_TEST_FRACTION,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    registry = read_json_or_empty(registry_path)
    hypotheses = [
        row for row in registry.get("hypotheses", []) if isinstance(row, Mapping)
    ]
    hypothesis_by_id = {str(row.get("hypothesis_id")): row for row in hypotheses}
    label_load = load_label_packets(label_dir)
    valid_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    unknown_hypothesis_rows = 0

    for raw in label_load["rows"]:
        normalized, errors = normalize_observation(raw)
        if normalized and normalized["hypothesis_id"] not in hypothesis_by_id:
            unknown_hypothesis_rows += 1
            errors.append("unknown_hypothesis_id")
        if errors or normalized is None:
            invalid_rows.append(
                {
                    "hypothesis_id": raw.get("hypothesis_id") if isinstance(raw, Mapping) else None,
                    "contract_ticker": raw.get("contract_ticker") if isinstance(raw, Mapping) else None,
                    "errors": errors or ["invalid_observation_shape"],
                }
            )
            continue
        valid_rows.append(normalized)

    evaluations = evaluate_hypotheses(
        hypotheses,
        valid_rows,
        min_observations=min_observations,
        min_oos_observations=min_oos_observations,
        fdr_alpha=fdr_alpha,
        test_fraction=test_fraction,
    )
    evaluations_by_id = {row["hypothesis_id"]: row for row in evaluations}
    gate = build_falsification_gate(
        hypotheses=hypotheses,
        evaluations=evaluations,
        valid_observation_count=len(valid_rows),
        invalid_observation_count=len(invalid_rows),
        label_load=label_load,
        generated_utc=generated,
    )
    summary = summary_from_evaluations(
        evaluations,
        label_load=label_load,
        valid_observation_count=len(valid_rows),
        invalid_observation_count=len(invalid_rows),
        unknown_hypothesis_rows=unknown_hypothesis_rows,
    )
    if not hypotheses:
        status = "labeled_oos_backtest_blocked_missing_hypothesis_registry"
    elif len(valid_rows) == 0:
        status = "labeled_oos_backtest_blocked_missing_labeled_observations"
    elif summary["testable_hypothesis_count"] == 0:
        status = "labeled_oos_backtest_blocked_insufficient_oos_samples"
    elif summary["promoted_research_hypothesis_count"] > 0:
        status = "labeled_oos_backtest_ready_with_research_promotions"
    else:
        status = "labeled_oos_backtest_ready_no_research_promotions"

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
        "inputs": {
            "hypothesis_registry_path": str(registry_path),
            "hypothesis_registry_sha256": sha256_or_none(registry_path),
            "label_dir": str(label_dir),
            "label_packet_count": label_load["packet_count"],
            "label_packet_paths": label_load["packet_paths"],
        },
        "method": {
            "split": "chronological holdout by decision_ts with time-safety checks",
            "test_fraction": test_fraction,
            "min_observations": min_observations,
            "min_oos_observations": min_oos_observations,
            "p_value": "one-sided binomial survival on positive OOS realized PnL rows",
            "fdr": "Benjamini-Hochberg q-values across testable hypotheses",
            "cost_basis": "all_in_break_even_probability or all_in_cost supplied in the label packet",
        },
        "summary": summary,
        "evaluations": evaluations,
        "evaluations_by_hypothesis_id": evaluations_by_id,
        "invalid_observation_samples": invalid_rows[:50],
        "falsification_gate": gate,
        "next_action": next_action(status),
        "safety": safety_flags(),
    }


def load_label_packets(label_dir: Path) -> dict[str, Any]:
    rows: list[Mapping[str, Any]] = []
    packet_paths: list[str] = []
    unsafe_packets: list[dict[str, str]] = []
    if not label_dir.exists():
        return {
            "packet_count": 0,
            "packet_paths": [],
            "rows": [],
            "unsafe_packets": [],
        }
    for path in sorted(label_dir.glob("*.json")):
        payload = read_json_or_empty(path)
        if not safe_research_artifact(payload):
            unsafe_packets.append({"path": str(path), "reason": "unsafe_or_missing_research_flags"})
            continue
        packet_rows = payload.get("rows", payload.get("observations", []))
        if not isinstance(packet_rows, list):
            unsafe_packets.append({"path": str(path), "reason": "missing_rows_list"})
            continue
        packet_paths.append(str(path))
        rows.extend(row for row in packet_rows if isinstance(row, Mapping))
    return {
        "packet_count": len(packet_paths),
        "packet_paths": packet_paths,
        "rows": rows,
        "unsafe_packets": unsafe_packets,
    }


def normalize_observation(row: Mapping[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    hypothesis_id = str(row.get("hypothesis_id") or "").strip()
    contract_ticker = str(row.get("contract_ticker") or "").strip()
    side = str(row.get("side") or "yes").lower()
    if side not in {"yes", "no"}:
        errors.append("side_must_be_yes_or_no")
    model_probability = probability(row.get("model_probability", row.get("calibrated_probability")))
    all_in_cost = probability(
        row.get("all_in_break_even_probability", row.get("all_in_cost", row.get("break_even_probability")))
    )
    side_outcome = outcome_value(row.get("side_outcome", row.get("outcome")))
    decision_ts = timestamp(row.get("decision_ts", row.get("decision_time")))
    quote_ts = timestamp(row.get("quote_ts", row.get("quote_time", row.get("as_of_ts"))))
    model_ts = timestamp(row.get("model_ts", row.get("model_time", decision_ts)))
    close_ts = timestamp(row.get("close_ts", row.get("close_time")))
    settled_ts = timestamp(row.get("settled_ts", row.get("settled_time", row.get("resolved_ts"))))
    fields = {
        "hypothesis_id": hypothesis_id,
        "contract_ticker": contract_ticker,
        "model_probability": model_probability,
        "all_in_break_even_probability": all_in_cost,
        "side_outcome": side_outcome,
        "decision_ts": decision_ts,
        "quote_ts": quote_ts,
        "model_ts": model_ts,
        "close_ts": close_ts,
        "settled_ts": settled_ts,
    }
    for key, value in fields.items():
        if value in {"", None}:
            errors.append(f"missing_{key}")
    if errors:
        return None, errors

    assert model_probability is not None
    assert all_in_cost is not None
    assert side_outcome is not None
    assert decision_ts is not None
    assert quote_ts is not None
    assert model_ts is not None
    assert close_ts is not None
    assert settled_ts is not None
    time_safe = quote_ts <= decision_ts and model_ts <= decision_ts and decision_ts < close_ts <= settled_ts
    if not time_safe:
        errors.append("not_time_safe")
    expected_edge = model_probability - all_in_cost
    realized_pnl = float(side_outcome) - all_in_cost
    return (
        {
            "hypothesis_id": hypothesis_id,
            "contract_ticker": contract_ticker,
            "event_ticker": row.get("event_ticker"),
            "side": side,
            "decision_ts": decision_ts,
            "quote_ts": quote_ts,
            "model_ts": model_ts,
            "close_ts": close_ts,
            "settled_ts": settled_ts,
            "model_probability": model_probability,
            "all_in_break_even_probability": all_in_cost,
            "side_outcome": side_outcome,
            "expected_edge": expected_edge,
            "realized_pnl_per_contract": realized_pnl,
            "positive_decision": expected_edge > 0.0,
            "time_safe": time_safe,
            "source_artifact": row.get("source_artifact"),
            "label_source": row.get("label_source"),
            "cost_source": row.get("cost_source"),
        },
        errors,
    )


def evaluate_hypotheses(
    hypotheses: Sequence[Mapping[str, Any]],
    observations: Sequence[Mapping[str, Any]],
    *,
    min_observations: int,
    min_oos_observations: int,
    fdr_alpha: float,
    test_fraction: float,
) -> list[dict[str, Any]]:
    rows_by_hypothesis: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in observations:
        rows_by_hypothesis[str(row.get("hypothesis_id"))].append(row)

    evaluations: list[dict[str, Any]] = []
    testable: list[dict[str, Any]] = []
    for hypothesis in hypotheses:
        hypothesis_id = str(hypothesis.get("hypothesis_id"))
        rows = sorted(rows_by_hypothesis.get(hypothesis_id, []), key=lambda item: float(item["decision_ts"]))
        positive_rows = [row for row in rows if row.get("positive_decision") is True]
        oos_rows = chronological_holdout(positive_rows, test_fraction=test_fraction)
        evaluation = base_evaluation(hypothesis, rows, positive_rows, oos_rows)
        if len(rows) < min_observations:
            evaluation["status"] = "hypothesis_backtest_blocked_insufficient_observations"
            evaluation["blocked_reasons"].append(f"observation_count<{min_observations}")
        elif len(oos_rows) < min_oos_observations:
            evaluation["status"] = "hypothesis_backtest_blocked_insufficient_oos"
            evaluation["blocked_reasons"].append(f"oos_count<{min_oos_observations}")
        else:
            evaluation.update(score_oos_rows(oos_rows))
            evaluation["status"] = "hypothesis_backtest_tested_pending_fdr"
            testable.append(evaluation)
        evaluations.append(evaluation)

    q_values = benjamini_hochberg(
        {
            row["hypothesis_id"]: row["p_value"]
            for row in testable
            if row.get("p_value") is not None
        }
    )
    for evaluation in evaluations:
        hypothesis_id = evaluation["hypothesis_id"]
        if hypothesis_id in q_values:
            evaluation["q_value"] = q_values[hypothesis_id]
            if (
                q_values[hypothesis_id] <= fdr_alpha
                and float(evaluation.get("mean_realized_pnl_per_contract") or 0.0) > 0.0
                and float(evaluation.get("mean_expected_edge") or 0.0) > 0.0
                and float(evaluation.get("brier_improvement") or 0.0) > 0.0
            ):
                evaluation["status"] = "hypothesis_promoted_research_fdr_passed"
            else:
                evaluation["status"] = "hypothesis_rejected_oos_cost_aware"
                evaluation["blocked_reasons"].append("failed_oos_cost_or_fdr_gate")
    return evaluations


def base_evaluation(
    hypothesis: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    positive_rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "hypothesis_id": hypothesis.get("hypothesis_id"),
        "status": "hypothesis_backtest_blocked_missing_observations" if not rows else "hypothesis_backtest_unscored",
        "classification": hypothesis.get("classification"),
        "model_route": hypothesis.get("model_route"),
        "feature_family": hypothesis.get("feature_family"),
        "multiple_testing_family": hypothesis.get("multiple_testing_family"),
        "observation_count": len(rows),
        "time_safe_count": sum(1 for row in rows if row.get("time_safe") is True),
        "positive_decision_count": len(positive_rows),
        "oos_count": len(oos_rows),
        "mean_expected_edge": mean(row.get("expected_edge") for row in oos_rows),
        "mean_realized_pnl_per_contract": mean(row.get("realized_pnl_per_contract") for row in oos_rows),
        "win_rate": None,
        "brier": None,
        "baseline_brier": None,
        "brier_improvement": None,
        "p_value": None,
        "q_value": None,
        "blocked_reasons": [] if rows else ["missing_labeled_observations_for_hypothesis"],
        "sample_contracts": [
            {
                "contract_ticker": row.get("contract_ticker"),
                "decision_ts": row.get("decision_ts"),
                "all_in_break_even_probability": row.get("all_in_break_even_probability"),
                "model_probability": row.get("model_probability"),
                "side_outcome": row.get("side_outcome"),
            }
            for row in list(rows)[:5]
        ],
        "safety": safety_flags(),
    }


def score_oos_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    wins = sum(1 for row in rows if float(row.get("realized_pnl_per_contract") or 0.0) > 0.0)
    n = len(rows)
    model_probs = [float(row["model_probability"]) for row in rows]
    costs = [float(row["all_in_break_even_probability"]) for row in rows]
    outcomes = [float(row["side_outcome"]) for row in rows]
    brier = sum((p - y) ** 2 for p, y in zip(model_probs, outcomes, strict=True)) / n
    baseline_brier = sum((p - y) ** 2 for p, y in zip(costs, outcomes, strict=True)) / n
    return {
        "win_rate": wins / n if n else None,
        "brier": brier,
        "baseline_brier": baseline_brier,
        "brier_improvement": baseline_brier - brier,
        "p_value": binomial_survival(wins, n, p=0.5),
        "mean_expected_edge": mean(row.get("expected_edge") for row in rows),
        "mean_realized_pnl_per_contract": mean(row.get("realized_pnl_per_contract") for row in rows),
    }


def chronological_holdout(rows: Sequence[Mapping[str, Any]], *, test_fraction: float) -> list[Mapping[str, Any]]:
    if not rows:
        return []
    count = max(1, math.ceil(len(rows) * test_fraction))
    return list(rows[-count:])


def build_falsification_gate(
    *,
    hypotheses: Sequence[Mapping[str, Any]],
    evaluations: Sequence[Mapping[str, Any]],
    valid_observation_count: int,
    invalid_observation_count: int,
    label_load: Mapping[str, Any],
    generated_utc: str,
) -> dict[str, Any]:
    promoted = [row for row in evaluations if row.get("status") == "hypothesis_promoted_research_fdr_passed"]
    tested = [row for row in evaluations if row.get("p_value") is not None]
    status = (
        "falsification_gate_research_promotions_present"
        if promoted
        else "falsification_gate_blocked_missing_labeled_oos_evidence"
        if valid_observation_count == 0
        else "falsification_gate_blocked_no_hypothesis_promotions"
    )
    gates = [
        gate(
            "label_packets_available",
            "pass" if label_load.get("packet_count") else "blocked",
            f"{label_load.get('packet_count', 0)} safe label packet(s) loaded.",
        ),
        gate(
            "valid_time_safe_observations",
            "pass" if valid_observation_count else "blocked",
            f"{valid_observation_count} valid observation row(s); {invalid_observation_count} invalid row(s).",
        ),
        gate(
            "oos_hypotheses_tested",
            "pass" if tested else "blocked",
            f"{len(tested)} hypothesis/hypotheses have OOS test statistics.",
        ),
        gate(
            "fdr_controlled_promotions",
            "pass" if promoted else "blocked",
            f"{len(promoted)} research promotion(s) after FDR control.",
        ),
        gate("no_execution_boundary", "pass", "Harness is research-only and emits no account/order fields."),
    ]
    counts = Counter(item["status"] for item in gates)
    return {
        "schema_version": 1,
        "generated_utc": generated_utc,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "registered_hypothesis_count": len(hypotheses),
        "tested_hypothesis_count": len(tested),
        "promoted_hypothesis_count": len(promoted),
        "rejected_hypothesis_count": sum(
            1 for row in evaluations if row.get("status") == "hypothesis_rejected_oos_cost_aware"
        ),
        "blocked_hypothesis_count": sum(
            1 for row in evaluations if str(row.get("status", "")).startswith("hypothesis_backtest_blocked")
        ),
        "gates": gates,
        "gate_counts": {
            "pass": counts["pass"],
            "warn": counts["warn"],
            "blocked": counts["blocked"],
            "fail": counts["fail"],
        },
        "safety": safety_flags(),
    }


def summary_from_evaluations(
    evaluations: Sequence[Mapping[str, Any]],
    *,
    label_load: Mapping[str, Any],
    valid_observation_count: int,
    invalid_observation_count: int,
    unknown_hypothesis_rows: int,
) -> dict[str, Any]:
    statuses = Counter(str(row.get("status")) for row in evaluations)
    return {
        "hypothesis_count": len(evaluations),
        "label_packet_count": label_load.get("packet_count", 0),
        "unsafe_label_packet_count": len(label_load.get("unsafe_packets", [])),
        "raw_observation_count": len(label_load.get("rows", [])),
        "valid_observation_count": valid_observation_count,
        "invalid_observation_count": invalid_observation_count,
        "unknown_hypothesis_observation_count": unknown_hypothesis_rows,
        "testable_hypothesis_count": sum(1 for row in evaluations if row.get("p_value") is not None),
        "promoted_research_hypothesis_count": statuses["hypothesis_promoted_research_fdr_passed"],
        "rejected_hypothesis_count": statuses["hypothesis_rejected_oos_cost_aware"],
        "blocked_hypothesis_count": sum(
            count for status, count in statuses.items() if status.startswith("hypothesis_backtest_blocked")
        ),
        "by_status": dict(sorted(statuses.items())),
    }


def next_action(status: str) -> dict[str, str]:
    if status == "labeled_oos_backtest_blocked_missing_labeled_observations":
        return {
            "name": "collect_hypothesis_labeled_observation_packets",
            "why": "The harness exists, but no settled OOS observations are keyed to HypothesisCandidate IDs yet.",
            "stop_condition": "Stop before testing or promoting hypotheses from unlabeled, time-unsafe, or non-cost-aware rows.",
        }
    if status == "labeled_oos_backtest_blocked_insufficient_oos_samples":
        return {
            "name": "accumulate_more_time_safe_labeled_observations",
            "why": "Some labels exist, but not enough OOS observations satisfy the minimum validation policy.",
            "stop_condition": "Stop before lowering sample-size/FDR thresholds without an explicit policy review.",
        }
    return {
        "name": "review_falsification_results_before_capacity_or_sizing",
        "why": "Backtest evidence exists; the next gate is capacity/correlation only after research promotions survive.",
        "stop_condition": "Stop before sizing, execution, or account/order paths.",
    }


def benjamini_hochberg(p_values: Mapping[str, float]) -> dict[str, float]:
    items = sorted((key, float(value)) for key, value in p_values.items())
    if not items:
        return {}
    ordered = sorted(items, key=lambda item: item[1])
    m = len(ordered)
    adjusted: dict[str, float] = {}
    running = 1.0
    for rank, (key, p_value) in reversed(list(enumerate(ordered, start=1))):
        running = min(running, p_value * m / rank)
        adjusted[key] = min(running, 1.0)
    return adjusted


def binomial_survival(k: int, n: int, *, p: float) -> float:
    if n <= 0:
        return 1.0
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    log_p = math.log(p)
    log_q = math.log(1.0 - p)
    total = 0.0
    for i in range(k, n + 1):
        log_term = (
            math.lgamma(n + 1)
            - math.lgamma(i + 1)
            - math.lgamma(n - i + 1)
            + i * log_p
            + (n - i) * log_q
        )
        total += math.exp(log_term)
    return min(max(total, 0.0), 1.0)


def probability(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0.0 or number > 1.0:
        return None
    return number


def outcome_value(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number in {0, 1} else None


def timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def mean(values: Sequence[Any]) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


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


def write_labeled_oos_backtest(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-labeled-oos-backtest.json"
    markdown_path = out_dir / "kalshi-labeled-oos-backtest.md"
    csv_path = out_dir / "kalshi-labeled-oos-backtest.csv"
    gate_json_path = out_dir / "kalshi-oos-falsification-gate.json"
    gate_markdown_path = out_dir / "kalshi-oos-falsification-gate.md"

    report_text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    gate_payload = report.get("falsification_gate") if isinstance(report.get("falsification_gate"), Mapping) else {}
    gate_text = json.dumps(gate_payload, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(report_text, encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("evaluations", []), csv_path)
    gate_json_path.write_text(gate_text, encoding="utf-8")
    gate_markdown_path.write_text(render_gate_markdown(gate_payload), encoding="utf-8")

    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-labeled-oos-backtest.json"
    latest_md = MACRO_DIR / "latest-kalshi-labeled-oos-backtest.md"
    latest_csv = MACRO_DIR / "latest-kalshi-labeled-oos-backtest.csv"
    latest_gate_json = MACRO_DIR / "latest-kalshi-oos-falsification-gate.json"
    latest_gate_md = MACRO_DIR / "latest-kalshi-oos-falsification-gate.md"
    latest_json.write_text(report_text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("evaluations", []), latest_csv)
    latest_gate_json.write_text(gate_text, encoding="utf-8")
    latest_gate_md.write_text(render_gate_markdown(gate_payload), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "csv_path": str(csv_path),
        "falsification_gate_json_path": str(gate_json_path),
        "falsification_gate_markdown_path": str(gate_markdown_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
        "latest_csv_path": str(latest_csv),
        "latest_falsification_gate_json_path": str(latest_gate_json),
        "latest_falsification_gate_markdown_path": str(latest_gate_md),
    }


def write_csv(evaluations: Any, path: Path) -> None:
    rows = [row for row in evaluations if isinstance(row, Mapping)]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in CSV_FIELDS})


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Labeled OOS Backtest",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Hypotheses: `{summary.get('hypothesis_count', 0)}`",
        f"- Label packets: `{summary.get('label_packet_count', 0)}`",
        f"- Valid observations: `{summary.get('valid_observation_count', 0)}`",
        f"- Testable hypotheses: `{summary.get('testable_hypothesis_count', 0)}`",
        f"- Research promotions: `{summary.get('promoted_research_hypothesis_count', 0)}`",
        "",
        "## Status Counts",
        "",
    ]
    by_status = summary.get("by_status") if isinstance(summary.get("by_status"), Mapping) else {}
    for status, count in by_status.items():
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(
        [
            "",
            "## Guardrail",
            "",
            "This is a falsification report. It does not size positions, submit orders, or authorize execution.",
            "",
        ]
    )
    return "\n".join(lines)


def render_gate_markdown(gate_payload: Mapping[str, Any]) -> str:
    lines = [
        "# Kalshi OOS Falsification Gate",
        "",
        f"- Status: `{gate_payload.get('status')}`",
        f"- Registered hypotheses: `{gate_payload.get('registered_hypothesis_count', 0)}`",
        f"- Tested hypotheses: `{gate_payload.get('tested_hypothesis_count', 0)}`",
        f"- Research promotions: `{gate_payload.get('promoted_hypothesis_count', 0)}`",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for item in gate_payload.get("gates", []):
        if isinstance(item, Mapping):
            lines.append(f"| `{item.get('name')}` | `{item.get('status')}` | {item.get('reason')} |")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--min-observations", type=int, default=DEFAULT_MIN_OBSERVATIONS)
    parser.add_argument("--min-oos-observations", type=int, default=DEFAULT_MIN_OOS_OBSERVATIONS)
    parser.add_argument("--fdr-alpha", type=float, default=DEFAULT_FDR_ALPHA)
    parser.add_argument("--test-fraction", type=float, default=DEFAULT_TEST_FRACTION)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_labeled_oos_backtest(
        registry_path=args.registry_path,
        label_dir=args.label_dir,
        min_observations=args.min_observations,
        min_oos_observations=args.min_oos_observations,
        fdr_alpha=args.fdr_alpha,
        test_fraction=args.test_fraction,
    )
    if args.write:
        paths = write_labeled_oos_backtest(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
