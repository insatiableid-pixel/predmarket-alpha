#!/usr/bin/env python3
"""Build paper-autonomous Kalshi decision candidates from the EV ledger."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.paper_decision_engine import build_paper_decision_candidates  # noqa: E402
from predmarket.shared_helpers import read_json_or_empty  # noqa: E402

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_LEDGER_PATH = MACRO_DIR / "latest-kalshi-contract-ev-ledger.json"
DEFAULT_RETIREMENT_PATH = MACRO_DIR / "latest-signal-decay-retirement-ledger.json"
DEFAULT_GATE_EVIDENCE_PATHS = (
    MACRO_DIR / "latest-kalshi-sports-stack-sequencing.json",
    MACRO_DIR / "latest-kalshi-near-resolution-flow-replay-gates.json",
)
DEFAULT_OUT_DIR = MACRO_DIR / "paper-decision-candidates-latest"
CSV_FIELDS = [
    "contract_ticker",
    "side",
    "family_id",
    "model_id",
    "signal_key",
    "signal_formula_key",
    "calibrated_probability",
    "market_probability",
    "all_in_cost",
    "expected_value_per_contract",
    "capacity_estimate",
    "cluster_key",
    "decay_status",
    "kelly_fraction",
    "paper_stake",
    "paper_usable",
    "decision_time",
    "close_time",
    "close_bucket",
    "predicted_outcome",
    "settled_outcome",
    "blocker_list",
]


def build_report(
    *,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    retirement_path: Path = DEFAULT_RETIREMENT_PATH,
    gate_evidence_paths: Sequence[Path] = DEFAULT_GATE_EVIDENCE_PATHS,
    ghost_depth_path: Path | None = None,
    paper_bankroll: float = 10_000.0,
    kelly_fraction: float = 0.25,
    max_fraction_per_contract: float = 0.02,
    max_cluster_share: float = 0.35,
    enforce_portfolio_caps: bool = True,
) -> dict[str, Any]:
    retirement = read_json_or_empty(retirement_path)
    return build_paper_decision_candidates(
        ledger_path=ledger_path,
        retirement_ledger=retirement,
        gate_evidence_paths=gate_evidence_paths,
        ghost_depth_path=ghost_depth_path,
        paper_bankroll=paper_bankroll,
        kelly_fraction=kelly_fraction,
        max_fraction_per_contract=max_fraction_per_contract,
        max_cluster_share=max_cluster_share,
        enforce_portfolio_caps=enforce_portfolio_caps,
    )


def write_candidates(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "paper-decision-candidates.json"
    md_path = out_dir / "paper-decision-candidates.md"
    csv_path = out_dir / "paper-decision-candidates.csv"
    json_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(
        report.get("candidates") if isinstance(report.get("candidates"), list) else [], csv_path
    )
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-paper-decision-candidates.json"
    latest_md = MACRO_DIR / "latest-paper-decision-candidates.md"
    latest_csv = MACRO_DIR / "latest-paper-decision-candidates.csv"
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(
        report.get("candidates") if isinstance(report.get("candidates"), list) else [], latest_csv
    )
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
        "# Paper Decision Candidates",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Candidate count: `{summary.get('candidate_count')}`",
        f"- Paper-usable count: `{summary.get('paper_usable_count')}`",
        f"- Total paper stake: `{summary.get('total_paper_stake')}`",
        f"- Portfolio cap status: `{summary.get('paper_portfolio_cap_status')}`",
        f"- Portfolio cap enforcement: `{summary.get('paper_portfolio_cap_enforcement_enabled')}`",
        f"- Portfolio cap-blocked candidates: `{summary.get('paper_portfolio_cap_blocked_candidate_count')}`",
        f"- Largest cluster: `{summary.get('paper_portfolio_largest_cluster')}`",
        f"- Largest contract: `{summary.get('paper_portfolio_largest_contract')}`",
        "",
        "| Contract | Side | Model | Paper Stake | Blockers |",
        "| --- | --- | --- | ---: | --- |",
    ]
    candidates = report.get("candidates") if isinstance(report.get("candidates"), list) else []
    for row in candidates[:50]:
        blockers = "; ".join(str(item) for item in row.get("blocker_list") or [])
        lines.append(
            f"| `{row.get('contract_ticker')}` | `{row.get('side')}` | `{row.get('model_id')}` | "
            f"{row.get('paper_stake')} | {blockers or 'none'} |"
        )
    if not candidates:
        lines.append("|  |  |  |  | No candidates |")
    lines.append("")
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            output = dict(row)
            output["blocker_list"] = "; ".join(str(item) for item in row.get("blocker_list") or [])
            writer.writerow(output)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-path", type=Path, default=DEFAULT_LEDGER_PATH)
    parser.add_argument("--retirement-path", type=Path, default=DEFAULT_RETIREMENT_PATH)
    parser.add_argument(
        "--gate-evidence-path",
        type=Path,
        action="append",
        default=[],
        help="Research-only gate artifact carrying paper_decision_blocker_rows.",
    )
    parser.add_argument(
        "--no-default-gate-evidence",
        action="store_true",
        help="Do not include default sports gate evidence blocker rows.",
    )
    parser.add_argument(
        "--ghost-depth-path",
        type=Path,
        default=None,
        help="Path to Kalshi ghost-listing depth diagnostic JSON used for capacity override.",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--paper-bankroll", type=float, default=10_000.0)
    parser.add_argument("--kelly-fraction", type=float, default=0.25)
    parser.add_argument("--max-fraction-per-contract", type=float, default=0.02)
    parser.add_argument("--max-cluster-share", type=float, default=0.35)
    parser.add_argument(
        "--no-enforce-portfolio-caps",
        action="store_true",
        help="Leave portfolio caps as diagnostics only. Operational Make targets should not use this.",
    )
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    gate_evidence_paths = tuple(args.gate_evidence_path or ())
    if not args.no_default_gate_evidence:
        gate_evidence_paths = (*DEFAULT_GATE_EVIDENCE_PATHS, *gate_evidence_paths)
    report = build_report(
        ledger_path=args.ledger_path,
        retirement_path=args.retirement_path,
        gate_evidence_paths=gate_evidence_paths,
        ghost_depth_path=args.ghost_depth_path,
        paper_bankroll=args.paper_bankroll,
        kelly_fraction=args.kelly_fraction,
        max_fraction_per_contract=args.max_fraction_per_contract,
        max_cluster_share=args.max_cluster_share,
        enforce_portfolio_caps=not args.no_enforce_portfolio_caps,
    )
    if args.write:
        paths = write_candidates(report, args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
