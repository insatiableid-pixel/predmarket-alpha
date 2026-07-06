#!/usr/bin/env python3
"""Wrap external donor artifacts in the strict Kalshi EV intake manifest."""

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

from predmarket.external_artifact_wrappers import (  # noqa: E402
    DEFAULT_WRAP_ROOT,
    wrap_descriptor_artifacts,
    wrap_summary,
)
from predmarket.shared_helpers import utc_now  # noqa: E402
from predmarket.source_inventory import DEFAULT_SOURCE_REPOS  # noqa: E402

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "external-artifact-wrap-latest"
CSV_FIELDS = [
    "source_repo_id",
    "family_id",
    "artifact_kind",
    "source_path",
    "wrapped",
    "wrapped_path",
    "row_count",
    "status",
    "errors",
]


def build_external_artifact_wrap_report(
    *,
    wrap_root: Path = DEFAULT_WRAP_ROOT,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for descriptor in DEFAULT_SOURCE_REPOS:
        rows.extend(
            wrap_descriptor_artifacts(
                descriptor,
                wrap_root=wrap_root,
                generated_utc=generated_utc,
            )
        )
    return {
        "schema_version": 1,
        "generated_utc": generated_utc or utc_now(),
        "status": "external_artifact_wrap_ready",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "wrap_root": str(wrap_root),
        "summary": wrap_summary(rows),
        "artifacts": rows,
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
        },
    }


def write_wrap_report(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "external-artifact-wrap.json"
    md_path = out_dir / "external-artifact-wrap.md"
    csv_path = out_dir / "external-artifact-wrap.csv"
    json_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(
        report.get("artifacts") if isinstance(report.get("artifacts"), list) else [], csv_path
    )
    latest_json = MACRO_DIR / "latest-external-artifact-wrap.json"
    latest_md = MACRO_DIR / "latest-external-artifact-wrap.md"
    latest_csv = MACRO_DIR / "latest-external-artifact-wrap.csv"
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(
        report.get("artifacts") if isinstance(report.get("artifacts"), list) else [], latest_csv
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
        "# External Artifact Wrap",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Wrapped artifacts: `{summary.get('wrapped_artifact_count')}`",
        f"- Blocked artifacts: `{summary.get('blocked_artifact_count')}`",
        f"- Wrapped rows: `{summary.get('wrapped_row_count')}`",
        "",
        "| Source | Kind | Rows | Status | Wrapped Path | Errors |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), list) else []
    for row in artifacts:
        errors = "; ".join(str(error) for error in row.get("errors") or [])
        lines.append(
            f"| `{row.get('source_repo_id')}` | `{row.get('artifact_kind')}` | "
            f"{row.get('row_count')} | `{row.get('status')}` | `{row.get('wrapped_path')}` | "
            f"{errors or 'none'} |"
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
    parser.add_argument("--wrap-root", type=Path, default=DEFAULT_WRAP_ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_external_artifact_wrap_report(wrap_root=args.wrap_root)
    if args.write:
        paths = write_wrap_report(report, args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
