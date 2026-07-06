#!/usr/bin/env python3
"""Build the prior-only donor gate for cold-start Kalshi signal families."""

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

from predmarket.prior_only_donor import build_prior_only_donor_gate  # noqa: E402
from predmarket.shared_helpers import path_is_within  # noqa: E402

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_EXTERNAL_PREFLIGHT_PATH = MACRO_DIR / "latest-external-artifact-preflight.json"
DEFAULT_FORMULA_REGISTRY_PATH = MACRO_DIR / "latest-signal-formula-registry.json"
DEFAULT_OUT_DIR = MACRO_DIR / "prior-only-donor-gate-latest"
CSV_FIELDS = [
    "prior_context_key",
    "source_repo_id",
    "family_id",
    "model_id",
    "artifact_kind",
    "contract_ticker",
    "side",
    "status",
    "prior_probability",
    "can_seed_signal_formula_generation",
    "counts_toward_independent_labels",
    "paper_usable",
    "live_eligible",
    "blocker_list",
]


def write_report(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "prior-only-donor-gate.json"
    md_path = out_dir / "prior-only-donor-gate.md"
    csv_path = out_dir / "prior-only-donor-gate.csv"
    json_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("prior_context_rows") or [], csv_path)
    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
    }
    if path_is_within(out_dir, MACRO_DIR):
        MACRO_DIR.mkdir(parents=True, exist_ok=True)
        latest_json = MACRO_DIR / "latest-prior-only-donor-gate.json"
        latest_md = MACRO_DIR / "latest-prior-only-donor-gate.md"
        latest_csv = MACRO_DIR / "latest-prior-only-donor-gate.csv"
        latest_json.write_text(json_text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        write_csv(report.get("prior_context_rows") or [], latest_csv)
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
        "# Prior-Only Donor Gate",
        "",
        f"- Status: `{report.get('status')}`",
        "- Mode: `research-only`",
        f"- Eligible prior context rows: `{summary.get('eligible_prior_context_count')}`",
        f"- Blocked prior context rows: `{summary.get('blocked_prior_context_count')}`",
        f"- Label credit: settlement `{summary.get('settlement_label_credit_count')}`, "
        f"independent `{summary.get('independent_label_credit_count')}`, "
        f"OOS `{summary.get('oos_label_credit_count')}`",
        f"- Paper/live promotion: paper `{summary.get('paper_usable_count')}`, "
        f"live `{summary.get('live_eligible_count')}`",
        "",
        "## Boundary",
        "",
        "- Donor priors can seed hypothesis generation only.",
        "- Donor priors do not satisfy settlement labels, OOS labels, FDR, EV, paper sizing, or live eligibility.",
        "- Generated formulas still enter the multiple-testing ledger before falsification.",
        "",
        "## Gates",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for gate in report.get("gates") if isinstance(report.get("gates"), list) else []:
        lines.append(f"| `{gate.get('name')}` | `{gate.get('status')}` | {gate.get('reason')} |")
    lines.extend(
        [
            "",
            "## Source Counts",
            "",
        ]
    )
    for source, count in sorted((summary.get("source_repo_counts") or {}).items()):
        lines.append(f"- `{source}`: `{count}` prior context row(s)")
    lines.append("")
    lines.append(
        "> Control-plane artifact only. No probability, EV, stake, order, account, or execution path is authorized by this report."
    )
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
    parser.add_argument(
        "--external-preflight-path", type=Path, default=DEFAULT_EXTERNAL_PREFLIGHT_PATH
    )
    parser.add_argument("--formula-registry-path", type=Path, default=DEFAULT_FORMULA_REGISTRY_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    formula_registry_path = args.formula_registry_path if args.formula_registry_path else None
    report = build_prior_only_donor_gate(
        external_preflight_path=args.external_preflight_path,
        formula_registry_path=formula_registry_path,
    )
    if args.write:
        paths = write_report(report, args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
