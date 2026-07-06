#!/usr/bin/env python3
"""Build the signal decay and retirement ledger."""

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

from predmarket.signal_decay_retirement import build_signal_decay_retirement_ledger  # noqa: E402

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_PAPER_DECISIONS_PATH = MACRO_DIR / "latest-paper-decision-candidates.json"
DEFAULT_OUT_DIR = MACRO_DIR / "signal-decay-retirement-ledger-latest"
CSV_FIELDS = [
    "signal_key",
    "retirement_status",
    "label_count",
    "accuracy",
    "recent_bucket",
    "recent_label_count",
    "recent_accuracy",
    "mean_calibration_error",
    "capacity_disappeared",
    "retirement_reasons",
]


def write_ledger(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "signal-decay-retirement-ledger.json"
    md_path = out_dir / "signal-decay-retirement-ledger.md"
    csv_path = out_dir / "signal-decay-retirement-ledger.csv"
    json_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("signals") if isinstance(report.get("signals"), list) else [], csv_path)
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-signal-decay-retirement-ledger.json"
    latest_md = MACRO_DIR / "latest-signal-decay-retirement-ledger.md"
    latest_csv = MACRO_DIR / "latest-signal-decay-retirement-ledger.csv"
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("signals") if isinstance(report.get("signals"), list) else [], latest_csv)
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
        "# Signal Decay Retirement Ledger",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Signals: `{summary.get('signal_count')}`",
        f"- Retired: `{summary.get('retired_signal_count')}`",
        f"- Active: `{summary.get('active_signal_count')}`",
        "",
        "| Signal | Status | Recent Accuracy | Reasons |",
        "| --- | --- | ---: | --- |",
    ]
    signals = report.get("signals") if isinstance(report.get("signals"), list) else []
    for row in signals:
        reasons = "; ".join(str(item) for item in row.get("retirement_reasons") or [])
        lines.append(
            f"| `{row.get('signal_key')}` | `{row.get('retirement_status')}` | "
            f"{row.get('recent_accuracy')} | {reasons or 'none'} |"
        )
    if not signals:
        lines.append("|  |  |  | No signals |")
    lines.append("")
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            output = dict(row)
            output["retirement_reasons"] = "; ".join(
                str(item) for item in row.get("retirement_reasons") or []
            )
            writer.writerow(output)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-decisions-path", type=Path, default=DEFAULT_PAPER_DECISIONS_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--min-recent-decisions", type=int, default=3)
    parser.add_argument("--min-recent-accuracy", type=float, default=0.5)
    parser.add_argument("--max-calibration-error", type=float, default=0.2)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_signal_decay_retirement_ledger(
        paper_decisions_path=args.paper_decisions_path,
        min_recent_decisions=args.min_recent_decisions,
        min_recent_accuracy=args.min_recent_accuracy,
        max_calibration_error=args.max_calibration_error,
    )
    if args.write:
        paths = write_ledger(report, args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
