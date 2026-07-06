#!/usr/bin/env python3
"""Build the derived sports no-vig consensus reference used by preflight."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.sports_consensus_reference_builder import (  # noqa: E402
    DEFAULT_KEY_FILE,
    DEFAULT_RAW_DIR,
    DEFAULT_REFERENCE_JSON,
    DEFAULT_REQUIRED_BOOKS,
    run_sports_consensus_reference_build,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_KALSHI_PATH = MACRO_DIR / "latest-kalshi-universe-scan.json"
DEFAULT_REPORT_DIR = MACRO_DIR / "kalshi-sports-consensus-reference-build-latest"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kalshi-json", type=Path, default=DEFAULT_KALSHI_PATH)
    parser.add_argument("--reference-json", type=Path, default=DEFAULT_REFERENCE_JSON)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--run-id", default="kalshi-sports-consensus-reference-build-latest")
    parser.add_argument("--odds-raw-json", type=Path, action="append", default=[])
    parser.add_argument("--odds-meta-json", type=Path, action="append", default=[])
    parser.add_argument("--capture-current", action="store_true")
    parser.add_argument("--api-key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--sport-keys", default="baseball_mlb")
    parser.add_argument("--regions", default="us")
    parser.add_argument("--bookmakers", default="")
    parser.add_argument("--markets", default="h2h")
    parser.add_argument("--odds-format", default="american")
    parser.add_argument("--raw-output-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--required-books", default=",".join(DEFAULT_REQUIRED_BOOKS))
    parser.add_argument("--max-event-delta-seconds", type=float, default=900.0)
    parser.add_argument("--max-source-age-seconds", type=float, default=900.0)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        artifacts = run_sports_consensus_reference_build(
            kalshi_json=args.kalshi_json,
            reference_json=args.reference_json,
            report_dir=args.report_dir,
            run_id=args.run_id,
            odds_raw_json=args.odds_raw_json,
            odds_meta_json=args.odds_meta_json,
            capture_current=bool(args.capture_current),
            api_key_file=args.api_key_file,
            sport_keys=_split_csv(args.sport_keys),
            regions=_split_csv(args.regions),
            bookmakers=_split_csv(args.bookmakers),
            markets=_split_csv(args.markets),
            odds_format=str(args.odds_format),
            raw_output_dir=args.raw_output_dir,
            required_books=_split_csv(args.required_books),
            max_event_delta_seconds=float(args.max_event_delta_seconds),
            max_source_age_seconds=float(args.max_source_age_seconds),
            timeout_seconds=float(args.timeout_seconds),
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "sports_consensus_reference_build_blocked_runtime_error",
                    "research_only": True,
                    "execution_enabled": False,
                    "market_execution": False,
                    "account_or_order_paths": False,
                    "raw_provider_payload_copied": False,
                    "api_key_printed": False,
                    "error": str(exc),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 70

    print(
        json.dumps(
            {
                "status": artifacts.report.get("status"),
                "reference_json_path": str(artifacts.reference_json_path),
                "json_path": str(artifacts.report_json_path),
                "markdown_path": str(artifacts.report_markdown_path),
                "summary": artifacts.report.get("summary"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in str(value).split(",") if part.strip())


if __name__ == "__main__":
    raise SystemExit(main())
