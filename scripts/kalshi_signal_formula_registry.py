#!/usr/bin/env python3
"""Build the safe signal-formula registry for agentic weak signals."""

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

from predmarket.shared_helpers import read_json_or_empty, utc_now  # noqa: E402
from predmarket.signal_formula import (  # noqa: E402
    SignalFormulaSpec,
    build_signal_formula_registry,
    default_signal_formula_specs,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "signal-formula-registry-latest"
CSV_FIELDS = [
    "signal_formula_key",
    "name",
    "family_id",
    "model_id",
    "output",
    "status",
    "counts_toward_multiple_testing",
    "errors",
]


def load_specs(path: Path | None) -> tuple[SignalFormulaSpec, ...]:
    if path is None or not path.exists():
        return default_signal_formula_specs()
    payload = read_json_or_empty(path)
    rows = payload.get("formulas") if isinstance(payload.get("formulas"), list) else []
    specs: list[SignalFormulaSpec] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        specs.append(
            SignalFormulaSpec(
                name=str(row.get("name") or ""),
                formula=str(row.get("formula") or ""),
                family_id=str(row.get("family_id") or "generic"),
                output=str(row.get("output") or "feature"),
                input_fields=tuple(str(value) for value in row.get("input_fields") or ()),
                multiple_testing_family_id=row.get("multiple_testing_family_id"),
                model_id=row.get("model_id"),
                version=str(row.get("version") or "1.0"),
                description=str(row.get("description") or ""),
            )
        )
    return tuple(specs)


def build_registry_report(
    spec_path: Path | None = None, generated_utc: str | None = None
) -> dict[str, Any]:
    report = build_signal_formula_registry(load_specs(spec_path))
    report["generated_utc"] = generated_utc or utc_now()
    report["inputs"] = {"spec_path": str(spec_path) if spec_path else None}
    return report


def write_registry(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "signal-formula-registry.json"
    md_path = out_dir / "signal-formula-registry.md"
    csv_path = out_dir / "signal-formula-registry.csv"
    json_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("formulas") if isinstance(report.get("formulas"), list) else [], csv_path)
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-signal-formula-registry.json"
    latest_md = MACRO_DIR / "latest-signal-formula-registry.md"
    latest_csv = MACRO_DIR / "latest-signal-formula-registry.csv"
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(
        report.get("formulas") if isinstance(report.get("formulas"), list) else [], latest_csv
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
        "# Signal Formula Registry",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Formula count: `{summary.get('formula_count')}`",
        f"- Ready formulas: `{summary.get('ready_formula_count')}`",
        f"- Multiple-testing count: `{summary.get('multiple_testing_hypothesis_count')}`",
        "",
        "| Formula | Family | Output | Status |",
        "| --- | --- | --- | --- |",
    ]
    formulas = report.get("formulas") if isinstance(report.get("formulas"), list) else []
    for row in formulas:
        lines.append(
            f"| `{row.get('name')}` | `{row.get('family_id')}` | `{row.get('output')}` | `{row.get('status')}` |"
        )
    lines.append("")
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            output = dict(row)
            output["errors"] = "; ".join(str(error) for error in row.get("errors") or [])
            writer.writerow(output)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec-path", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_registry_report(args.spec_path)
    if args.write:
        paths = write_registry(report, args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
