#!/usr/bin/env python3
"""Falsify simple crypto proxy feature families against settled Kalshi labels.

This is deliberately a research gate, not a picker. It consumes label packets
from the crypto proxy observation loop, collapses repeated observations to
independent contract labels, and tests only after minimum OOS sample rules are
met. It never emits usable EV, sizing, or execution instructions.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_LABEL_DIR = Path("/home/mrwatson/manual_drops/kalshi_crypto_proxy_labels")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-crypto-proxy-feature-model-falsification-latest"
DEFAULT_MIN_INDEPENDENT_LABELS = 30
DEFAULT_MIN_OOS_LABELS = 10
DEFAULT_TEST_FRACTION = 0.30
DEFAULT_FDR_ALPHA = 0.10
CSV_FIELDS = [
    "model_id",
    "status",
    "independent_label_count",
    "oos_count",
    "oos_accuracy",
    "p_value",
    "q_value",
    "mean_market_brier",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_crypto_proxy_feature_model_falsification(
    *,
    label_dir: Path = DEFAULT_LABEL_DIR,
    generated_utc: str | None = None,
    min_independent_labels: int = DEFAULT_MIN_INDEPENDENT_LABELS,
    min_oos_labels: int = DEFAULT_MIN_OOS_LABELS,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    fdr_alpha: float = DEFAULT_FDR_ALPHA,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    label_load = load_label_packets(label_dir)
    normalized_rows, invalid_rows = normalize_label_rows(label_load["rows"])
    independent_rows = independent_contract_rows(normalized_rows)
    evaluations = evaluate_models(
        independent_rows,
        min_independent_labels=min_independent_labels,
        min_oos_labels=min_oos_labels,
        test_fraction=test_fraction,
        fdr_alpha=fdr_alpha,
    )
    summary = build_summary(
        label_load=label_load,
        normalized_rows=normalized_rows,
        independent_rows=independent_rows,
        invalid_rows=invalid_rows,
        evaluations=evaluations,
        min_independent_labels=min_independent_labels,
        min_oos_labels=min_oos_labels,
    )
    gates = build_gates(summary=summary, evaluations=evaluations, label_dir=label_dir)
    status = report_status(summary, evaluations)
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
            "label_dir": str(label_dir),
            "label_packet_count": label_load["packet_count"],
            "label_packet_paths": label_load["packet_paths"],
            "unsafe_packet_count": len(label_load["unsafe_packets"]),
        },
        "method": {
            "independence_rule": "Collapse repeated observations by exact contract_ticker; keep earliest decision_time.",
            "candidate_feature_families": [
                "proxy_state_directional_accuracy",
                "market_yes_ask_probability_baseline",
            ],
            "split": "chronological holdout by decision_time",
            "test_fraction": test_fraction,
            "min_independent_labels": min_independent_labels,
            "min_oos_labels": min_oos_labels,
            "p_value": "one-sided binomial survival versus 50% directional accuracy on OOS rows",
            "fdr": "Benjamini-Hochberg q-values across testable directional feature families",
            "promotion_boundary": "Research candidate only; no calibrated probability, EV, sizing, or execution.",
        },
        "summary": summary,
        "gates": gates,
        "evaluations": evaluations,
        "independent_label_rows_sample": independent_rows[:25],
        "invalid_label_rows_sample": invalid_rows[:50],
        "next_action": next_action(status),
        "safety": safety_flags(),
    }


def load_label_packets(label_dir: Path) -> dict[str, Any]:
    rows: list[Mapping[str, Any]] = []
    packet_paths: list[str] = []
    unsafe_packets: list[dict[str, str]] = []
    if not label_dir.exists():
        return {"packet_count": 0, "packet_paths": [], "rows": [], "unsafe_packets": []}
    for path in sorted(label_dir.glob("*.json")):
        payload = read_json_or_empty(path)
        if not safe_research_artifact(payload):
            unsafe_packets.append({"path": str(path), "reason": "unsafe_or_missing_research_flags"})
            continue
        packet_rows = payload.get("rows", [])
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


def normalize_label_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for row in rows:
        errors: list[str] = []
        ticker = str(row.get("contract_ticker") or "").strip()
        outcome = outcome_value(row.get("yes_outcome", row.get("side_outcome")))
        decision_ts = timestamp(row.get("decision_time"))
        settled_ts = timestamp(row.get("settled_time"))
        close_ts = timestamp(row.get("close_time"))
        yes_ask = probability(row.get("yes_ask"))
        if not ticker:
            errors.append("missing_contract_ticker")
        if outcome is None:
            errors.append("missing_yes_outcome")
        if decision_ts is None:
            errors.append("missing_decision_time")
        if close_ts is None:
            errors.append("missing_close_time")
        if settled_ts is None:
            errors.append("missing_settled_time")
        if decision_ts is not None and close_ts is not None and decision_ts >= close_ts:
            errors.append("decision_not_before_close")
        if close_ts is not None and settled_ts is not None and close_ts > settled_ts:
            errors.append("close_after_settlement")
        if errors:
            invalid.append({"contract_ticker": ticker or None, "errors": errors})
            continue
        assert outcome is not None
        assert decision_ts is not None
        assert close_ts is not None
        assert settled_ts is not None
        normalized.append(
            {
                "contract_ticker": ticker,
                "event_ticker": row.get("event_ticker"),
                "series_ticker": row.get("series_ticker"),
                "asset_symbol": row.get("asset_symbol"),
                "contract_family": row.get("contract_family"),
                "proxy_state": row.get("proxy_state"),
                "proxy_price": optional_float(row.get("proxy_price")),
                "proxy_distance_to_floor": optional_float(row.get("proxy_distance_to_floor")),
                "proxy_distance_to_cap": optional_float(row.get("proxy_distance_to_cap")),
                "yes_ask": yes_ask,
                "yes_outcome": outcome,
                "decision_ts": decision_ts,
                "close_ts": close_ts,
                "settled_ts": settled_ts,
                "decision_time": iso_from_timestamp(decision_ts),
                "close_time": iso_from_timestamp(close_ts),
                "settled_time": iso_from_timestamp(settled_ts),
                "usable": False,
                "calibrated_probability": None,
                "expected_value_per_contract": None,
            }
        )
    normalized.sort(key=lambda item: (item["decision_ts"], item["contract_ticker"]))
    return normalized, invalid


def independent_contract_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_ticker: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("contract_ticker") or "")
        if not ticker:
            continue
        if ticker not in by_ticker or float(row.get("decision_ts") or 0) < float(by_ticker[ticker].get("decision_ts") or 0):
            by_ticker[ticker] = dict(row)
    return sorted(by_ticker.values(), key=lambda item: (item["decision_ts"], item["contract_ticker"]))


def evaluate_models(
    rows: Sequence[Mapping[str, Any]],
    *,
    min_independent_labels: int,
    min_oos_labels: int,
    test_fraction: float,
    fdr_alpha: float,
) -> list[dict[str, Any]]:
    sorted_rows = list(rows)
    split_index = chronological_split_index(len(sorted_rows), test_fraction)
    oos_rows = sorted_rows[split_index:]
    evaluations = [
        evaluate_proxy_state_directional(
            rows=sorted_rows,
            oos_rows=oos_rows,
            min_independent_labels=min_independent_labels,
            min_oos_labels=min_oos_labels,
        ),
        evaluate_market_yes_ask_baseline(rows=sorted_rows, oos_rows=oos_rows),
    ]
    p_values = [
        (index, row["p_value"])
        for index, row in enumerate(evaluations)
        if isinstance(row.get("p_value"), (int, float))
    ]
    q_by_index = benjamini_hochberg(p_values)
    for index, q_value in q_by_index.items():
        evaluations[index]["q_value"] = q_value
        if (
            evaluations[index]["status"] == "testable_research_candidate"
            and q_value <= fdr_alpha
            and float(evaluations[index].get("oos_accuracy") or 0.0) > 0.5
        ):
            evaluations[index]["status"] = "research_candidate_fdr_passed"
    return evaluations


def evaluate_proxy_state_directional(
    *,
    rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    min_independent_labels: int,
    min_oos_labels: int,
) -> dict[str, Any]:
    scored = [row for row in oos_rows if proxy_state_prediction(row.get("proxy_state")) is not None]
    wins = sum(1 for row in scored if proxy_state_prediction(row.get("proxy_state")) == row.get("yes_outcome"))
    p_value = binomial_survival(wins, len(scored), 0.5) if len(rows) >= min_independent_labels and len(scored) >= min_oos_labels else None
    if len(rows) < min_independent_labels:
        status = "blocked_insufficient_independent_labels"
    elif len(scored) < min_oos_labels:
        status = "blocked_insufficient_oos_labels"
    else:
        status = "testable_research_candidate"
    return {
        "model_id": "proxy_state_directional_accuracy",
        "status": status,
        "independent_label_count": len(rows),
        "oos_count": len(scored),
        "oos_correct_count": wins,
        "oos_accuracy": wins / len(scored) if scored else None,
        "p_value": p_value,
        "q_value": None,
        "feature_rule": "Predict YES when proxy_state contains above; predict NO when proxy_state contains below.",
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


def evaluate_market_yes_ask_baseline(
    *,
    rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    scored = [row for row in oos_rows if probability(row.get("yes_ask")) is not None]
    briers = [(float(row["yes_ask"]) - float(row["yes_outcome"])) ** 2 for row in scored]
    return {
        "model_id": "market_yes_ask_probability_baseline",
        "status": "diagnostic_baseline_only",
        "independent_label_count": len(rows),
        "oos_count": len(scored),
        "mean_market_brier": sum(briers) / len(briers) if briers else None,
        "p_value": None,
        "q_value": None,
        "feature_rule": "Market YES ask is recorded as a baseline probability diagnostic, not a model promotion.",
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


def build_summary(
    *,
    label_load: Mapping[str, Any],
    normalized_rows: Sequence[Mapping[str, Any]],
    independent_rows: Sequence[Mapping[str, Any]],
    invalid_rows: Sequence[Mapping[str, Any]],
    evaluations: Sequence[Mapping[str, Any]],
    min_independent_labels: int,
    min_oos_labels: int,
) -> dict[str, Any]:
    return {
        "label_packet_count": label_load.get("packet_count", 0),
        "unsafe_label_packet_count": len(label_load.get("unsafe_packets", [])),
        "raw_label_row_count": len(label_load.get("rows", [])),
        "valid_label_row_count": len(normalized_rows),
        "invalid_label_row_count": len(invalid_rows),
        "independent_contract_label_count": len(independent_rows),
        "duplicate_label_row_count": max(0, len(normalized_rows) - len(independent_rows)),
        "min_independent_labels": min_independent_labels,
        "min_oos_labels": min_oos_labels,
        "testable_model_count": sum(1 for item in evaluations if item.get("status") == "testable_research_candidate"),
        "research_candidate_count": sum(1 for item in evaluations if item.get("status") == "research_candidate_fdr_passed"),
        "label_outcome_counts": counts(row.get("yes_outcome") for row in independent_rows),
        "asset_counts": counts(row.get("asset_symbol") for row in independent_rows),
        "contract_family_counts": counts(row.get("contract_family") for row in independent_rows),
        "proxy_state_counts": counts(row.get("proxy_state") for row in independent_rows),
    }


def build_gates(
    *,
    summary: Mapping[str, Any],
    evaluations: Sequence[Mapping[str, Any]],
    label_dir: Path,
) -> list[dict[str, Any]]:
    return [
        gate(
            "label_packets_safe",
            "pass" if int(summary.get("unsafe_label_packet_count") or 0) == 0 else "blocked",
            f"{summary.get('label_packet_count')} safe packet(s), {summary.get('unsafe_label_packet_count')} unsafe packet(s).",
        ),
        gate(
            "label_dir_outside_repo",
            "pass" if outside_repo(label_dir) else "blocked",
            "Crypto proxy label packets must stay outside the repo.",
        ),
        gate(
            "independent_label_minimum",
            "pass"
            if int(summary.get("independent_contract_label_count") or 0) >= int(summary.get("min_independent_labels") or 0)
            else "blocked",
            f"{summary.get('independent_contract_label_count')} independent label(s); minimum is {summary.get('min_independent_labels')}.",
        ),
        gate(
            "oos_label_minimum",
            "pass"
            if any(str(item.get("status")) in {"testable_research_candidate", "research_candidate_fdr_passed"} for item in evaluations)
            else "blocked",
            f"{summary.get('testable_model_count')} testable model(s); minimum OOS labels is {summary.get('min_oos_labels')}.",
        ),
        gate(
            "no_probability_ev_or_execution_claims",
            "pass"
            if all(
                item.get("usable") is False
                and item.get("calibrated_probability") is None
                and item.get("expected_value_per_contract") is None
                for item in evaluations
            )
            else "fail",
            "Falsification output remains research-only and does not produce usable EV.",
        ),
    ]


def report_status(summary: Mapping[str, Any], evaluations: Sequence[Mapping[str, Any]]) -> str:
    if int(summary.get("valid_label_row_count") or 0) == 0:
        return "crypto_proxy_feature_model_falsification_blocked_missing_labels"
    if int(summary.get("independent_contract_label_count") or 0) < int(summary.get("min_independent_labels") or 0):
        return "crypto_proxy_feature_model_falsification_blocked_insufficient_independent_labels"
    if not any(str(item.get("status")) in {"testable_research_candidate", "research_candidate_fdr_passed"} for item in evaluations):
        return "crypto_proxy_feature_model_falsification_blocked_insufficient_oos_labels"
    if int(summary.get("research_candidate_count") or 0) > 0:
        return "crypto_proxy_feature_model_falsification_ready_with_research_candidates"
    return "crypto_proxy_feature_model_falsification_ready_no_research_candidates"


def next_action(status: str) -> dict[str, str]:
    if status == "crypto_proxy_feature_model_falsification_ready_with_research_candidates":
        return {
            "name": "kalshi_crypto_proxy_probability_calibration",
            "why": "At least one feature family survived OOS/FDR as a research candidate; next work is calibrated probability modeling and cost replay.",
            "stop_condition": "Stop before sizing or execution until calibrated probabilities, all-in costs, capacity, correlation, and kill-switch gates exist.",
        }
    if status in {
        "crypto_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
        "crypto_proxy_feature_model_falsification_blocked_insufficient_oos_labels",
        "crypto_proxy_feature_model_falsification_blocked_missing_labels",
    }:
        return {
            "name": "kalshi_crypto_proxy_observation_accumulation",
            "why": "True labels exist but are not enough for independent OOS/FDR falsification.",
            "stop_condition": "Stop before lowering sample thresholds, using duplicate contract labels as independent evidence, or creating EV/sizing/execution claims.",
        }
    return {
        "name": "kalshi_crypto_proxy_signal_family_rotation",
        "why": "No crypto proxy feature family survived the current falsification gate.",
        "stop_condition": "Stop before discretionary signal selection or reusing failed hypotheses without a new registered feature family.",
    }


def write_crypto_proxy_feature_model_falsification(
    report: Mapping[str, Any],
    out_dir: Path = DEFAULT_OUT_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-crypto-proxy-feature-model-falsification.json"
    markdown_path = out_dir / "kalshi-crypto-proxy-feature-model-falsification.md"
    csv_path = out_dir / "kalshi-crypto-proxy-feature-model-falsification.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, csv_path)
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-crypto-proxy-feature-model-falsification.json"
    latest_md = MACRO_DIR / "latest-kalshi-crypto-proxy-feature-model-falsification.md"
    latest_csv = MACRO_DIR / "latest-kalshi-crypto-proxy-feature-model-falsification.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, latest_csv)
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "csv_path": str(csv_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
        "latest_csv_path": str(latest_csv),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Crypto Proxy Feature Model Falsification",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Raw label rows: `{summary.get('raw_label_row_count')}`",
        f"- Independent contract labels: `{summary.get('independent_contract_label_count')}`",
        f"- Research candidates: `{summary.get('research_candidate_count')}`",
        "",
        "## Gates",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for item in report.get("gates", []):
        if isinstance(item, Mapping):
            lines.append(f"| `{item.get('name')}` | `{item.get('status')}` | {item.get('reason')} |")
    lines.extend(
        [
            "",
            "## Evaluations",
            "",
            "| Model | Status | OOS Count | Accuracy | p | q |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in report.get("evaluations", []):
        if isinstance(item, Mapping):
            lines.append(
                f"| `{item.get('model_id')}` | `{item.get('status')}` | "
                f"{item.get('oos_count')} | {item.get('oos_accuracy')} | {item.get('p_value')} | {item.get('q_value')} |"
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
            "This report is not a betting recommendation. It does not produce calibrated probabilities, EV, sizing, or orders.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(report: Mapping[str, Any], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in report.get("evaluations", []):
            if isinstance(row, Mapping):
                writer.writerow({field: row.get(field) for field in CSV_FIELDS})


def chronological_split_index(count: int, test_fraction: float) -> int:
    if count <= 0:
        return 0
    test_count = max(1, math.ceil(count * min(max(test_fraction, 0.0), 1.0)))
    return max(0, count - test_count)


def proxy_state_prediction(value: Any) -> int | None:
    text = str(value or "").lower()
    if "above" in text:
        return 1
    if "below" in text:
        return 0
    return None


def benjamini_hochberg(indexed_p_values: Sequence[tuple[int, float]]) -> dict[int, float]:
    ordered = sorted(indexed_p_values, key=lambda item: item[1])
    count = len(ordered)
    output: dict[int, float] = {}
    running = 1.0
    for rank_from_end, (index, p_value) in enumerate(reversed(ordered), start=1):
        rank = count - rank_from_end + 1
        running = min(running, p_value * count / rank)
        output[index] = running
    return output


def binomial_survival(successes: int, trials: int, probability_null: float) -> float:
    if trials <= 0 or successes < 0:
        return 1.0
    total = 0.0
    for k in range(successes, trials + 1):
        total += math.comb(trials, k) * (probability_null**k) * ((1.0 - probability_null) ** (trials - k))
    return min(max(total, 0.0), 1.0)


def outcome_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    number = probability(value)
    if number is not None:
        if number >= 0.999:
            return 1
        if number <= 0.001:
            return 0
    text = str(value or "").strip().lower()
    if text in {"yes", "true", "win", "1"}:
        return 1
    if text in {"no", "false", "loss", "0"}:
        return 0
    return None


def probability(value: Any) -> float | None:
    number = optional_float(value)
    return number if number is not None and 0.0 <= number <= 1.0 else None


def optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip().rstrip("%")
            if not value:
                return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


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
        number = float(text)
    except ValueError:
        number = None
    if number is not None:
        return number if math.isfinite(number) else None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def iso_from_timestamp(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def counts(values: Sequence[Any]) -> dict[str, int]:
    counter = Counter(str(value if value is not None else "unknown") for value in values)
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def safe_research_artifact(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
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


def outside_repo(path: Path) -> bool:
    try:
        path.expanduser().resolve().relative_to(CONTROL_REPO.resolve())
    except ValueError:
        return True
    return False


def read_json_or_empty(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--min-independent-labels", type=int, default=DEFAULT_MIN_INDEPENDENT_LABELS)
    parser.add_argument("--min-oos-labels", type=int, default=DEFAULT_MIN_OOS_LABELS)
    parser.add_argument("--test-fraction", type=float, default=DEFAULT_TEST_FRACTION)
    parser.add_argument("--fdr-alpha", type=float, default=DEFAULT_FDR_ALPHA)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_crypto_proxy_feature_model_falsification(
        label_dir=args.label_dir,
        min_independent_labels=args.min_independent_labels,
        min_oos_labels=args.min_oos_labels,
        test_fraction=args.test_fraction,
        fdr_alpha=args.fdr_alpha,
    )
    if args.write:
        paths = write_crypto_proxy_feature_model_falsification(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
