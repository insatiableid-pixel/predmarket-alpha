#!/usr/bin/env python3
"""Write the donor source-repo inventory for the Kalshi EV engine."""

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

from predmarket.source_inventory import build_source_repo_inventory  # noqa: E402

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "source-repo-inventory-latest"
CSV_FIELDS = [
    "repo_id",
    "path",
    "donor_type",
    "admission_status",
    "exists",
    "git_branch",
    "git_dirty_count",
    "git_untracked_count",
    "artifact_count",
    "existing_artifact_count",
    "family_ids",
    "blockers",
]


def write_inventory(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "source-repo-inventory.json"
    md_path = out_dir / "source-repo-inventory.md"
    csv_path = out_dir / "source-repo-inventory.csv"
    json_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("repos") if isinstance(report.get("repos"), list) else [], csv_path)
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-source-repo-inventory.json"
    latest_md = MACRO_DIR / "latest-source-repo-inventory.md"
    latest_csv = MACRO_DIR / "latest-source-repo-inventory.csv"
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("repos") if isinstance(report.get("repos"), list) else [], latest_csv)
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
        "# Source Repo Inventory",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Repos: `{summary.get('repo_count')}`",
        f"- Existing repos: `{summary.get('existing_repo_count')}`",
        f"- Dirty repos: `{summary.get('dirty_repo_count')}`",
        f"- Existing artifacts: `{summary.get('existing_artifact_count')}` / `{summary.get('artifact_count')}`",
        "",
        "| Repo | Type | Admission | Dirty | Existing Artifacts | Families |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    repos = report.get("repos") if isinstance(report.get("repos"), list) else []
    for row in repos:
        lines.append(
            f"| `{row.get('repo_id')}` | `{row.get('donor_type')}` | `{row.get('admission_status')}` | "
            f"{row.get('git_dirty_count')} | {row.get('existing_artifact_count')}/{row.get('artifact_count')} | "
            f"{', '.join(row.get('family_ids') or [])} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            output = dict(row)
            output["family_ids"] = "; ".join(row.get("family_ids") or [])
            output["blockers"] = "; ".join(row.get("blockers") or [])
            writer.writerow(output)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_source_repo_inventory()
    if args.write:
        paths = write_inventory(report, args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
