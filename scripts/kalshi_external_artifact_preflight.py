#!/usr/bin/env python3
"""Validate configured external donor artifacts before they enter the EV engine."""

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

from predmarket.external_artifact_bridge import load_external_artifact  # noqa: E402
from predmarket.external_artifact_wrappers import (  # noqa: E402
    DEFAULT_WRAP_ROOT,
    wrap_external_artifact,
)
from predmarket.shared_helpers import utc_now  # noqa: E402
from predmarket.source_inventory import DEFAULT_SOURCE_REPOS, SourceRepoDescriptor  # noqa: E402

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "external-artifact-preflight-latest"
CSV_FIELDS = [
    "source_repo_id",
    "family_id",
    "artifact_kind",
    "source_path",
    "path",
    "status",
    "safe",
    "row_count",
    "errors",
]


def build_external_artifact_preflight(
    generated_utc: str | None = None,
    *,
    wrap_root: Path = DEFAULT_WRAP_ROOT,
    auto_wrap: bool = True,
    descriptors: Sequence[SourceRepoDescriptor] = DEFAULT_SOURCE_REPOS,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for descriptor in descriptors:
        for artifact in descriptor.admissible_artifacts:
            source_path = Path(artifact)
            wrapped = (
                wrap_external_artifact(
                    source_repo_id=descriptor.repo_id,
                    family_id=descriptor.family_ids[0] if descriptor.family_ids else "unknown",
                    source_path=source_path,
                    wrap_root=wrap_root,
                    generated_utc=generated_utc,
                )
                if auto_wrap
                else {}
            )
            preflight_path = Path(str(wrapped.get("wrapped_path") or artifact))
            loaded = load_external_artifact(
                path=preflight_path,
                source_repo_id=descriptor.repo_id,
                family_id=(descriptor.family_ids[0] if descriptor.family_ids else "unknown"),
                control_repo=CONTROL_REPO,
                model_id=None,
                requires_exact_contract_mapping=False,
            )
            preflight = (
                loaded.get("preflight") if isinstance(loaded.get("preflight"), Mapping) else {}
            )
            rows.append(
                {
                    "source_repo_id": descriptor.repo_id,
                    "family_id": descriptor.family_ids[0] if descriptor.family_ids else "unknown",
                    "artifact_kind": wrapped.get("artifact_kind"),
                    "source_path": artifact,
                    "path": str(preflight_path),
                    "wrapped": wrapped.get("wrapped", False),
                    "wrapped_path": wrapped.get("wrapped_path"),
                    "wrap_status": wrapped.get("status"),
                    "status": loaded.get("status"),
                    "safe": loaded.get("safe"),
                    "row_count": loaded.get("row_count"),
                    "errors": preflight.get("errors") or [],
                    "sha256": loaded.get("sha256"),
                    "outside_repo": loaded.get("outside_repo"),
                }
            )
    blocked = sum(1 for row in rows if not row.get("safe"))
    return {
        "schema_version": 1,
        "generated_utc": generated_utc or utc_now(),
        "status": "external_artifact_preflight_ready",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "wrap_root": str(wrap_root),
        "auto_wrap": auto_wrap,
        "summary": {
            "artifact_count": len(rows),
            "safe_artifact_count": len(rows) - blocked,
            "blocked_artifact_count": blocked,
            "wrapped_artifact_count": sum(1 for row in rows if row.get("wrapped")),
            "safe_wrapped_artifact_count": sum(
                1 for row in rows if row.get("wrapped") and row.get("safe")
            ),
            "safe_row_count": sum(
                int(row.get("row_count") or 0) for row in rows if row.get("safe")
            ),
        },
        "artifacts": rows,
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
        },
    }


def write_preflight(report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "external-artifact-preflight.json"
    md_path = out_dir / "external-artifact-preflight.md"
    csv_path = out_dir / "external-artifact-preflight.csv"
    json_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(
        report.get("artifacts") if isinstance(report.get("artifacts"), list) else [], csv_path
    )
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-external-artifact-preflight.json"
    latest_md = MACRO_DIR / "latest-external-artifact-preflight.md"
    latest_csv = MACRO_DIR / "latest-external-artifact-preflight.csv"
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
        "# External Artifact Preflight",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Safe artifacts: `{summary.get('safe_artifact_count')}`",
        f"- Blocked artifacts: `{summary.get('blocked_artifact_count')}`",
        "",
        "| Source | Family | Status | Rows | Errors |",
        "| --- | --- | --- | ---: | --- |",
    ]
    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), list) else []
    for row in artifacts:
        errors = "; ".join(str(error) for error in row.get("errors") or [])
        lines.append(
            f"| `{row.get('source_repo_id')}` | `{row.get('family_id')}` | `{row.get('status')}` | "
            f"{row.get('row_count')} | {errors or 'none'} |"
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
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--wrap-root", type=Path, default=DEFAULT_WRAP_ROOT)
    parser.add_argument("--no-wrap", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_external_artifact_preflight(wrap_root=args.wrap_root, auto_wrap=not args.no_wrap)
    if args.write:
        paths = write_preflight(report, args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
