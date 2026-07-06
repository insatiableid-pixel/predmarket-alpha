#!/usr/bin/env python3
"""Audit local sports consensus provider coverage without provider calls."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.sports_consensus_provider_policy import (  # noqa: E402
    DEFAULT_PROVIDER_AUDIT_TARGET_SPORTS,
    build_provider_audit,
    provider_rows_to_csv,
    render_provider_audit_markdown,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_REPORT_DIR = MACRO_DIR / "kalshi-sports-consensus-provider-audit-latest"
DEFAULT_STRICT_CONSENSUS = Path(
    "/home/mrwatson/manual_drops/predmarket/sports-no-vig-consensus.json"
)
DEFAULT_ATP_CONSENSUS = Path(
    "/home/mrwatson/projects/atp-oracle/docs/codex/artifacts/"
    "sports-market-consensus-latest/sports-market-consensus.json"
)
DEFAULT_ATP_BOOK_GLOB = Path("/home/mrwatson/projects/atp-oracle/data/sports/books")
DEFAULT_ODDS_API_GLOB = Path("/home/mrwatson/manual_drops/odds_api")
DEFAULT_SOCCER_ASIAN_DIAGNOSTIC = (
    MACRO_DIR / "latest-kalshi-sports-consensus-soccer-asian-provider-diagnostic.json"
)
DEFAULT_ATP_ADAPTER_REPORT = MACRO_DIR / "latest-kalshi-sports-consensus-atp-donor-adapter.json"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--run-id", default="kalshi-sports-consensus-provider-audit-latest")
    parser.add_argument("--strict-consensus-json", type=Path, action="append", default=[])
    parser.add_argument("--donor-json", type=Path, action="append", default=[])
    parser.add_argument("--donor-jsonl", type=Path, action="append", default=[])
    parser.add_argument("--raw-provider-json", type=Path, action="append", default=[])
    parser.add_argument("--include-defaults", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-raw-files", type=int, default=20)
    parser.add_argument(
        "--target-sports",
        default=",".join(DEFAULT_PROVIDER_AUDIT_TARGET_SPORTS),
        help="Comma-separated canonical sports to audit for strict sharp-consensus maturity.",
    )
    parser.add_argument(
        "--deferred-target-sports",
        default="",
        help=(
            "Comma-separated target sports to keep visible but exclude from actionable "
            "provider-gap counts when no current provider observations exist."
        ),
    )
    parser.add_argument(
        "--incompatible-market-sports",
        default="",
        help=(
            "Comma-separated target sports to keep visible but exclude from actionable "
            "provider-gap counts because current Kalshi contract types are not compatible "
            "with the available sharp consensus market."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    sources = _load_sources(args)
    incompatible_market_sports = [
        sport.strip() for sport in args.incompatible_market_sports.split(",") if sport.strip()
    ]
    if args.include_defaults:
        incompatible_market_sports.extend(_default_incompatible_market_sports())
    report = build_provider_audit(
        sources,
        run_id=args.run_id,
        target_sports=[sport.strip() for sport in args.target_sports.split(",") if sport.strip()],
        deferred_sports=[
            sport.strip() for sport in args.deferred_target_sports.split(",") if sport.strip()
        ],
        incompatible_market_sports=incompatible_market_sports,
    )
    paths = write_outputs(report, args.out_dir)
    print(
        json.dumps(
            {
                "status": report["status"],
                "summary": report["summary"],
                "json_path": str(paths["json"]),
                "markdown_path": str(paths["markdown"]),
                "csv_path": str(paths["csv"]),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def write_outputs(report: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-consensus-provider-audit.json"
    md_path = out_dir / "kalshi-sports-consensus-provider-audit.md"
    csv_path = out_dir / "kalshi-sports-consensus-provider-audit.csv"
    json_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_provider_audit_markdown(report)
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    provider_rows_to_csv(report.get("providers", []), csv_path)
    if _path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-sports-consensus-provider-audit.json"
        latest_md = MACRO_DIR / "latest-kalshi-sports-consensus-provider-audit.md"
        latest_csv = MACRO_DIR / "latest-kalshi-sports-consensus-provider-audit.csv"
        latest_json.write_text(json_text, encoding="utf-8")
        latest_md.write_text(markdown, encoding="utf-8")
        latest_csv.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
    return {"json": json_path, "markdown": md_path, "csv": csv_path}


def _load_sources(args: argparse.Namespace) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    strict_paths = list(args.strict_consensus_json)
    donor_json_paths = list(args.donor_json)
    donor_jsonl_paths = list(args.donor_jsonl)
    raw_paths = list(args.raw_provider_json)
    if args.include_defaults:
        strict_paths.extend(_existing([DEFAULT_STRICT_CONSENSUS]))
        donor_json_paths.extend(_existing([DEFAULT_ATP_CONSENSUS]))
        raw_paths.extend(_existing([DEFAULT_SOCCER_ASIAN_DIAGNOSTIC]))
        donor_jsonl_paths.extend(sorted(DEFAULT_ATP_BOOK_GLOB.glob("*.jsonl")))
        raw_paths.extend(_latest_json_files(DEFAULT_ODDS_API_GLOB, limit=args.max_raw_files))
    sources.extend(_json_sources(strict_paths, source_kind="strict_consensus"))
    sources.extend(_json_sources(donor_json_paths, source_kind="donor_consensus"))
    sources.extend(_jsonl_sources(donor_jsonl_paths, source_kind="donor_consensus"))
    sources.extend(_json_sources(raw_paths, source_kind="raw_provider_capture"))
    return sources


def _default_incompatible_market_sports() -> list[str]:
    payload = _read_json(DEFAULT_ATP_ADAPTER_REPORT)
    if not isinstance(payload, dict):
        return []
    if (
        payload.get("status")
        == "sports_consensus_atp_donor_adapter_blocked_no_compatible_atp_match_markets"
    ):
        return ["tennis"]
    return []


def _json_sources(paths: Sequence[Path], *, source_kind: str) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for path in _unique_paths(paths):
        payload = _read_json(path)
        if payload is None:
            continue
        sources.append(
            {
                "source_id": path.stem,
                "source_path": str(path),
                "source_kind": source_kind,
                "payload": payload,
            }
        )
    return sources


def _jsonl_sources(paths: Sequence[Path], *, source_kind: str) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for path in _unique_paths(paths):
        rows = _read_jsonl(path)
        if not rows:
            continue
        sources.append(
            {
                "source_id": path.stem,
                "source_path": str(path),
                "source_kind": source_kind,
                "payload": {"rows": rows},
            }
        )
    return sources


def _read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                row = json.loads(text)
                if isinstance(row, dict):
                    rows.append(row)
    except (OSError, json.JSONDecodeError):
        return []
    return rows


def _latest_json_files(directory: Path, *, limit: int) -> list[Path]:
    if not directory.is_dir() or limit <= 0:
        return []
    paths = [
        path
        for path in directory.glob("*.json")
        if path.is_file() and not path.name.endswith(".meta.json")
    ]
    paths.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return paths[:limit]


def _existing(paths: Sequence[Path]) -> list[Path]:
    return [path for path in paths if path.is_file()]


def _unique_paths(paths: Sequence[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            out.append(path)
            seen.add(key)
    return out


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
