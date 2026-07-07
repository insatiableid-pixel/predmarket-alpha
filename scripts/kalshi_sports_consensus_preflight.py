#!/usr/bin/env python3
"""Validate sports no-vig consensus rows before they can feed Kalshi gates."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import manual_drop_path  # noqa: E402
from predmarket.sports_consensus import (  # noqa: E402
    build_sports_consensus_preflight,
    render_sports_consensus_markdown,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_KALSHI_PATH = MACRO_DIR / "latest-kalshi-universe-scan.json"
DEFAULT_CONSENSUS_PATH = manual_drop_path("predmarket", "sports-no-vig-consensus.json")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-consensus-preflight-latest"


def run_sports_consensus_preflight(
    *,
    kalshi_json: Path = DEFAULT_KALSHI_PATH,
    consensus_json: Path = DEFAULT_CONSENSUS_PATH,
    output_dir: Path = DEFAULT_OUT_DIR,
    run_id: str | None = None,
    min_distinct_books: int = 2,
    max_timestamp_skew_seconds: float = 180.0,
    write: bool = False,
) -> dict[str, Any]:
    kalshi_payload = _read_json_object(kalshi_json) if kalshi_json.is_file() else {}
    consensus_payload = _read_json_object(consensus_json) if consensus_json.is_file() else None
    report = build_sports_consensus_preflight(
        kalshi_payload,
        consensus_payload,
        kalshi_path=kalshi_json,
        consensus_path=consensus_json,
        run_id=run_id,
        min_distinct_books=min_distinct_books,
        max_timestamp_skew_seconds=max_timestamp_skew_seconds,
    )
    if write:
        paths = write_outputs(report, out_dir=output_dir)
        report = {**report, "output_paths": paths}
    return report


def write_outputs(report: Mapping[str, Any], *, out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-consensus-preflight.json"
    md_path = out_dir / "kalshi-sports-consensus-preflight.md"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    markdown = render_sports_consensus_markdown(report)
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")

    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
    }
    if _path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-sports-consensus-preflight.json"
        latest_md = MACRO_DIR / "latest-kalshi-sports-consensus-preflight.md"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(markdown, encoding="utf-8")
        paths.update(
            {
                "latest_json_path": str(latest_json),
                "latest_markdown_path": str(latest_md),
            }
        )
    return paths


def _path_is_within(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
    except ValueError:
        return False
    return True


def _read_json_object(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, Mapping):
        return payload
    if isinstance(payload, list):
        return {"rows": payload}
    raise ValueError(f"Expected JSON object or list in {path}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kalshi-json", type=Path, default=DEFAULT_KALSHI_PATH)
    parser.add_argument("--consensus-json", type=Path, default=DEFAULT_CONSENSUS_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--run-id", default="kalshi-sports-consensus-preflight-latest")
    parser.add_argument("--min-distinct-books", type=int, default=2)
    parser.add_argument("--max-timestamp-skew-seconds", type=float, default=180.0)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_sports_consensus_preflight(
        kalshi_json=args.kalshi_json,
        consensus_json=args.consensus_json,
        output_dir=args.out_dir,
        run_id=args.run_id,
        min_distinct_books=args.min_distinct_books,
        max_timestamp_skew_seconds=args.max_timestamp_skew_seconds,
        write=args.write,
    )
    if args.write:
        output = {
            "status": report.get("status"),
            "ready": report.get("ready"),
            **dict(report.get("output_paths", {})),
        }
    else:
        output = report
    print(json.dumps(output, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
