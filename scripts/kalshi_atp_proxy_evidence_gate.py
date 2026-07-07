#!/usr/bin/env python3
"""Summarize ATP/Wimbledon evidence gates before any EV or sizing promotion.

This script is intentionally conservative. It does not create probabilities,
EV rows, paper stakes, or orders. It only answers whether ATP/Wimbledon evidence
is mature enough to enter the stricter falsification/replay chain.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import (  # noqa: E402
    project_path,
    safe_research_artifact,
    sha256_or_none,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OBSERVATION_LOOP_PATH = MACRO_DIR / "latest-kalshi-atp-proxy-observation-loop.json"
DEFAULT_FORWARD_OOS_PATH = project_path(
    "atp-oracle", "docs/codex/artifacts/kalshi-forward-oos-latest/report.json"
)
DEFAULT_LIQUIDITY_PATH = project_path(
    "atp-oracle",
    "docs/codex/artifacts/kalshi-forward-oos-liquidity-latest/liquidity.json",
)
DEFAULT_BETTABLE_GATE_PATH = project_path(
    "atp-oracle",
    "docs/codex/artifacts/kalshi-bettable-line-gate-latest/bettable-line-gate.json",
)
DEFAULT_PRICE_OBSERVATIONS_PATH = project_path(
    "atp-oracle",
    "docs/codex/artifacts/kalshi-forward-oos-price-observations-latest/prices.json",
)
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-atp-proxy-evidence-gate-latest"
DEFAULT_MIN_SETTLED_LABELS = 10

CSV_FIELDS = ["gate", "status", "reason"]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_atp_proxy_evidence_gate(
    *,
    observation_loop_path: Path = DEFAULT_OBSERVATION_LOOP_PATH,
    forward_oos_path: Path = DEFAULT_FORWARD_OOS_PATH,
    liquidity_path: Path = DEFAULT_LIQUIDITY_PATH,
    bettable_gate_path: Path = DEFAULT_BETTABLE_GATE_PATH,
    price_observations_path: Path = DEFAULT_PRICE_OBSERVATIONS_PATH,
    min_settled_labels: int = DEFAULT_MIN_SETTLED_LABELS,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    observation = read_json_or_empty(observation_loop_path)
    forward = read_json_or_empty(forward_oos_path)
    liquidity = read_json_or_empty(liquidity_path)
    bettable = read_json_or_empty(bettable_gate_path)
    prices = read_json_or_empty(price_observations_path)
    summary = build_summary(
        observation=observation,
        forward=forward,
        liquidity=liquidity,
        bettable=bettable,
        prices=prices,
        min_settled_labels=min_settled_labels,
    )
    gates = build_gates(summary=summary)
    status = report_status(gates)
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "family_id": "atp",
        "public_market_data_calls": False,
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "inputs": {
            "observation_loop_path": str(observation_loop_path),
            "observation_loop_sha256": sha256_or_none(observation_loop_path),
            "forward_oos_path": str(forward_oos_path),
            "forward_oos_sha256": sha256_or_none(forward_oos_path),
            "liquidity_path": str(liquidity_path),
            "liquidity_sha256": sha256_or_none(liquidity_path),
            "bettable_gate_path": str(bettable_gate_path),
            "bettable_gate_sha256": sha256_or_none(bettable_gate_path),
            "price_observations_path": str(price_observations_path),
            "price_observations_sha256": sha256_or_none(price_observations_path),
        },
        "summary": summary,
        "gates": gates,
        "next_action": next_action(status),
        "safety": safety_flags(),
    }


def build_summary(
    *,
    observation: Mapping[str, Any],
    forward: Mapping[str, Any],
    liquidity: Mapping[str, Any],
    bettable: Mapping[str, Any],
    prices: Mapping[str, Any],
    min_settled_labels: int,
) -> dict[str, Any]:
    obs_summary = (
        observation.get("summary") if isinstance(observation.get("summary"), Mapping) else {}
    )
    liquidity_summary = (
        liquidity.get("summary") if isinstance(liquidity.get("summary"), Mapping) else {}
    )
    price_summary = prices.get("summary") if isinstance(prices.get("summary"), Mapping) else {}
    return {
        "min_settled_labels": min_settled_labels,
        "observation_safe": safe_research_artifact(observation),
        "observation_status": observation.get("status"),
        "observation_count": int_value(obs_summary.get("total_observation_row_count")),
        "settled_label_count": int_value(obs_summary.get("label_row_count")),
        "next_public_label_probe_utc": obs_summary.get("next_public_label_probe_utc"),
        "next_expected_expiration_utc": obs_summary.get("next_expected_expiration_utc"),
        "forward_oos_verdict": forward.get("verdict"),
        "forward_oos_summary": forward.get("summary"),
        "forward_oos_resolved": int_value(forward.get("n_resolved")),
        "forward_oos_min_probe": int_value(forward.get("min_resolved_for_probe")),
        "forward_oos_min_stake": int_value(forward.get("min_resolved_for_stake")),
        "probe_bankroll_eligible": bool(forward.get("probe_bankroll_eligible")),
        "first_real_stake_eligible": bool(forward.get("first_real_stake_eligible")),
        "true_clv_mean_pp": float_value(forward.get("true_clv_mean_pp")),
        "true_clv_ci95_lower_pp": float_value(forward.get("true_clv_ci95_lower_pp")),
        "true_clv_threshold_pp": float_value(forward.get("true_clv_threshold_pp")),
        "liquidity_gate_passes_for_first_stake": bool(
            liquidity_summary.get("gate_passes_for_first_stake")
        ),
        "liquidity_passing_candidates": int_value(liquidity_summary.get("passing_candidates")),
        "liquidity_required_passing_candidates": int_value(
            liquidity_summary.get("required_passing_candidates")
        ),
        "liquidity_reason": liquidity_summary.get("reason"),
        "bettable_gate_status": bettable.get("status"),
        "bettable_count": int_value(bettable.get("bettable_count")),
        "bettable_candidate_count": int_value(bettable.get("candidate_count")),
        "price_observations_usable_for_true_clv_total": int_value(
            price_summary.get("usable_for_true_clv_total")
            or prices.get("usable_for_true_clv_total")
        ),
        "price_observation_errors_count": int_value(
            price_summary.get("errors_count") or prices.get("errors_count")
        ),
    }


def build_gates(*, summary: Mapping[str, Any]) -> list[dict[str, str]]:
    label_count = int(summary.get("settled_label_count") or 0)
    min_labels = int(summary.get("min_settled_labels") or DEFAULT_MIN_SETTLED_LABELS)
    resolved = int(summary.get("forward_oos_resolved") or 0)
    min_probe = int(summary.get("forward_oos_min_probe") or 10)
    min_stake = int(summary.get("forward_oos_min_stake") or 25)
    clv_lower = float_value(summary.get("true_clv_ci95_lower_pp"))
    clv_threshold = float_value(summary.get("true_clv_threshold_pp")) or 0.0
    liquidity_passing = int(summary.get("liquidity_passing_candidates") or 0)
    liquidity_required = int(summary.get("liquidity_required_passing_candidates") or 25)
    bettable_status = str(summary.get("bettable_gate_status") or "").lower()
    return [
        gate(
            "atp_observations_available",
            "pass"
            if summary.get("observation_safe") and summary.get("observation_count")
            else "blocked",
            f"{summary.get('observation_count')} ATP observation row(s) loaded.",
        ),
        gate(
            "settled_labels_available",
            "pass" if label_count >= min_labels else "blocked",
            f"{label_count}/{min_labels} settled predmarket ATP label(s).",
        ),
        gate(
            "forward_oos_probe_sample",
            "pass" if resolved >= min_probe else "blocked",
            f"{resolved}/{min_probe} resolved forward-OOS candidate(s) for probe review.",
        ),
        gate(
            "forward_oos_first_stake_sample",
            "pass" if resolved >= min_stake else "blocked",
            f"{resolved}/{min_stake} resolved forward-OOS candidate(s) for first stake.",
        ),
        gate(
            "forward_oos_clv_survival",
            "pass" if clv_lower is not None and clv_lower > clv_threshold else "blocked",
            f"true_clv_ci95_lower_pp={clv_lower}, threshold={clv_threshold}.",
        ),
        gate(
            "executable_liquidity_depth",
            "pass" if summary.get("liquidity_gate_passes_for_first_stake") else "blocked",
            f"{liquidity_passing}/{liquidity_required} candidates pass executable liquidity; reason={summary.get('liquidity_reason')}.",
        ),
        gate(
            "bettable_line_gate",
            "pass" if bettable_status in {"pass", "passed", "ready", "open"} else "blocked",
            f"ATP bettable-line gate status={summary.get('bettable_gate_status')}; bettable_count={summary.get('bettable_count')}.",
        ),
        gate(
            "no_ev_sizing_or_execution",
            "pass",
            "This report is a research evidence gate only; no probabilities, EV, sizing, or orders are emitted.",
        ),
    ]


def report_status(gates: Sequence[Mapping[str, Any]]) -> str:
    blocked = {str(gate["gate"]) for gate in gates if gate.get("status") != "pass"}
    if not blocked:
        return "atp_proxy_evidence_gate_ready_for_falsification"
    if "settled_labels_available" in blocked:
        return "atp_proxy_evidence_gate_blocked_waiting_settlement_labels"
    if any(name.startswith("forward_oos") for name in blocked):
        return "atp_proxy_evidence_gate_blocked_forward_oos"
    if "executable_liquidity_depth" in blocked:
        return "atp_proxy_evidence_gate_blocked_liquidity"
    if "bettable_line_gate" in blocked:
        return "atp_proxy_evidence_gate_blocked_bettable_line"
    return "atp_proxy_evidence_gate_blocked"


def next_action(status: str) -> dict[str, str]:
    if status == "atp_proxy_evidence_gate_ready_for_falsification":
        return {
            "name": "kalshi_atp_proxy_falsification_replay",
            "why": "Settlement labels and upstream ATP evidence gates are sufficient for statistical falsification.",
            "stop_condition": "Stop before paper/live sizing until FDR, replay, capacity, correlation, and decay gates pass.",
        }
    return {
        "name": "kalshi_atp_proxy_evidence_accumulation",
        "why": "ATP/Wimbledon evidence is not mature enough for promotion.",
        "stop_condition": "Do not use ATP donor prices or unresolved forward-OOS candidates as tradable probabilities.",
    }


def write_atp_proxy_evidence_gate(
    report: Mapping[str, Any], *, out_dir: Path = DEFAULT_OUT_DIR
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-atp-proxy-evidence-gate.json"
    md_path = out_dir / "kalshi-atp-proxy-evidence-gate.md"
    csv_path = out_dir / "kalshi-atp-proxy-evidence-gate.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_gate_csv(report.get("gates", []), csv_path)
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-atp-proxy-evidence-gate.json"
    latest_md = MACRO_DIR / "latest-kalshi-atp-proxy-evidence-gate.md"
    latest_csv = MACRO_DIR / "latest-kalshi-atp-proxy-evidence-gate.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_gate_csv(report.get("gates", []), latest_csv)
    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
        "latest_csv_path": str(latest_csv),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi ATP Proxy Evidence Gate",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Settled labels: `{summary.get('settled_label_count')}/{summary.get('min_settled_labels')}`",
        f"- Forward-OOS resolved: `{summary.get('forward_oos_resolved')}/{summary.get('forward_oos_min_stake')}`",
        f"- Next expected expiration: `{summary.get('next_expected_expiration_utc')}`",
        f"- True CLV lower: `{summary.get('true_clv_ci95_lower_pp')}`",
        f"- Liquidity: `{summary.get('liquidity_passing_candidates')}/{summary.get('liquidity_required_passing_candidates')}`",
        f"- Bettable gate: `{summary.get('bettable_gate_status')}`",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for item in report.get("gates", []):
        if isinstance(item, Mapping):
            lines.append(
                f"| `{item.get('gate')}` | `{item.get('status')}` | {item.get('reason')} |"
            )
    lines.extend(
        [
            "",
            "This is not a betting report. It emits no probabilities, EV, sizing, or orders.",
            "",
        ]
    )
    return "\n".join(lines)


def write_gate_csv(gates: Any, path: Path) -> None:
    rows = [row for row in gates if isinstance(row, Mapping)]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def int_value(value: Any) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def float_value(value: Any) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"gate": name, "status": status, "reason": reason}


def safety_flags() -> dict[str, Any]:
    return {
        "research_only": True,
        "public_market_data_calls": False,
        "authenticated_api_calls": False,
        "account_or_order_paths": False,
        "market_execution": False,
        "database_writes": False,
        "paid_calls": False,
        "staking_or_sizing_guidance": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation-loop-path", type=Path, default=DEFAULT_OBSERVATION_LOOP_PATH)
    parser.add_argument("--forward-oos-path", type=Path, default=DEFAULT_FORWARD_OOS_PATH)
    parser.add_argument("--liquidity-path", type=Path, default=DEFAULT_LIQUIDITY_PATH)
    parser.add_argument("--bettable-gate-path", type=Path, default=DEFAULT_BETTABLE_GATE_PATH)
    parser.add_argument(
        "--price-observations-path", type=Path, default=DEFAULT_PRICE_OBSERVATIONS_PATH
    )
    parser.add_argument("--min-settled-labels", type=int, default=DEFAULT_MIN_SETTLED_LABELS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_atp_proxy_evidence_gate(
        observation_loop_path=args.observation_loop_path,
        forward_oos_path=args.forward_oos_path,
        liquidity_path=args.liquidity_path,
        bettable_gate_path=args.bettable_gate_path,
        price_observations_path=args.price_observations_path,
        min_settled_labels=args.min_settled_labels,
    )
    if args.write:
        paths = write_atp_proxy_evidence_gate(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
