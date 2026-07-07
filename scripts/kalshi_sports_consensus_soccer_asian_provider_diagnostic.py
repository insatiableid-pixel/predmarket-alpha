#!/usr/bin/env python3
"""Audit/probe soccer Asian sharp-provider availability."""

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

from predmarket.shared_helpers import manual_drop_path  # noqa: E402
from predmarket.sports_consensus_reference_builder import (  # noqa: E402
    DEFAULT_KEY_FILE,
    DEFAULT_RAW_DIR,
    _read_api_key,
    capture_the_odds_api_current,
)
from predmarket.sports_consensus_soccer_asian_provider import (  # noqa: E402
    DEFAULT_TARGET_PROVIDERS,
    build_soccer_asian_provider_diagnostic,
    render_soccer_asian_provider_diagnostic_markdown,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_REPORT_DIR = MACRO_DIR / "kalshi-sports-consensus-soccer-asian-provider-diagnostic-latest"
DEFAULT_ODDS_API_DIR = manual_drop_path("odds_api")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--run-id", default="kalshi-sports-consensus-soccer-asian-provider-latest")
    parser.add_argument("--raw-provider-json", type=Path, action="append", default=[])
    parser.add_argument("--raw-provider-meta-json", type=Path, action="append", default=[])
    parser.add_argument("--include-defaults", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-raw-files", type=int, default=12)
    parser.add_argument("--capture-current", action="store_true")
    parser.add_argument("--api-key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--sport-key", default="soccer_fifa_world_cup")
    parser.add_argument("--target-providers", default=",".join(DEFAULT_TARGET_PROVIDERS))
    parser.add_argument("--raw-output-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    sources = _load_sources(args)
    report = build_soccer_asian_provider_diagnostic(
        sources=sources,
        run_id=args.run_id,
        target_providers=_split_csv(args.target_providers),
    )
    paths = write_outputs(report, args.out_dir)
    print(
        json.dumps(
            {
                "status": report["status"],
                "summary": report["summary"],
                "json_path": str(paths["json"]),
                "markdown_path": str(paths["markdown"]),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def write_outputs(report: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-consensus-soccer-asian-provider-diagnostic.json"
    md_path = out_dir / "kalshi-sports-consensus-soccer-asian-provider-diagnostic.md"
    json_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_soccer_asian_provider_diagnostic_markdown(report)
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    if _path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-sports-consensus-soccer-asian-provider-diagnostic.json"
        latest_md = MACRO_DIR / "latest-kalshi-sports-consensus-soccer-asian-provider-diagnostic.md"
        latest_json.write_text(json_text, encoding="utf-8")
        latest_md.write_text(markdown, encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def _load_sources(args: argparse.Namespace) -> list[dict[str, Any]]:
    raw_paths = list(args.raw_provider_json)
    meta_paths = list(args.raw_provider_meta_json)
    if args.include_defaults:
        raw_paths.extend(_latest_soccer_raw_files(DEFAULT_ODDS_API_DIR, limit=args.max_raw_files))
    if args.capture_current:
        api_key = _read_api_key(args.api_key_file)
        payload, meta, raw_path = capture_the_odds_api_current(
            api_key=api_key,
            sport_key=args.sport_key,
            output_dir=args.raw_output_dir,
            bookmakers=_split_csv(args.target_providers),
            markets=("h2h",),
            timeout_seconds=float(args.timeout_seconds),
        )
        return [
            *_json_sources(raw_paths, meta_paths),
            {
                "source_id": raw_path.stem,
                "source_path": str(raw_path),
                "source_kind": "raw_provider_capture",
                "payload": payload,
                "meta": meta,
                "meta_path": str(raw_path.with_suffix(".meta.json")),
            },
        ]
    return _json_sources(raw_paths, meta_paths)


def _json_sources(raw_paths: Sequence[Path], meta_paths: Sequence[Path]) -> list[dict[str, Any]]:
    meta_by_raw = _meta_by_raw(raw_paths, meta_paths)
    sources: list[dict[str, Any]] = []
    for path in _unique_paths(raw_paths):
        payload = _read_json(path)
        if payload is None:
            continue
        meta_path = meta_by_raw.get(str(path))
        meta = _read_json(meta_path) if meta_path else None
        sources.append(
            {
                "source_id": path.stem,
                "source_path": str(path),
                "source_kind": "raw_provider_capture",
                "payload": payload,
                "meta": meta if isinstance(meta, dict) else {},
                "meta_path": str(meta_path) if meta_path else None,
            }
        )
    return sources


def _meta_by_raw(raw_paths: Sequence[Path], meta_paths: Sequence[Path]) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for raw_path in raw_paths:
        candidate = raw_path.with_name(f"{raw_path.stem}.meta.json")
        if candidate.is_file():
            out[str(raw_path)] = candidate
    for meta_path in meta_paths:
        raw_name = meta_path.name.replace(".meta.json", ".json")
        raw_path = meta_path.with_name(raw_name)
        if raw_path.is_file():
            out[str(raw_path)] = meta_path
    return out


def _latest_soccer_raw_files(directory: Path, *, limit: int) -> list[Path]:
    if not directory.is_dir() or limit <= 0:
        return []
    paths = [
        path
        for path in directory.glob("soccer_fifa_world_cup_current_*.json")
        if path.is_file() and not path.name.endswith(".meta.json")
    ]
    paths.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return paths[:limit]


def _read_json(path: Path | None) -> Any | None:
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _unique_paths(paths: Sequence[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            out.append(path)
            seen.add(key)
    return out


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in str(value).split(",") if part.strip())


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
