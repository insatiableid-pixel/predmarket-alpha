#!/usr/bin/env python3
"""Capture current sports sharp-provider availability without exact mapping."""

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
from predmarket.sports_consensus_reference_builder import DEFAULT_KEY_FILE  # noqa: E402
from predmarket.sports_consensus_sharp_provider_capture import (  # noqa: E402
    build_sharp_provider_capture_report,
    capture_sharp_provider_sources,
    write_sharp_provider_capture_outputs,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-consensus-sharp-provider-capture-latest"
DEFAULT_RAW_DIR = manual_drop_path("odds_api")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--run-id", default="kalshi-sports-consensus-sharp-provider-capture-latest")
    parser.add_argument("--capture-current", action="store_true")
    parser.add_argument("--raw-provider-json", type=Path, action="append", default=[])
    parser.add_argument("--api-key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument(
        "--sport-keys",
        default="baseball_mlb,tennis_atp_wimbledon,soccer_fifa_world_cup,americanfootball_nfl,basketball_nba",
    )
    parser.add_argument("--regions", default="us")
    parser.add_argument("--bookmakers", default="pinnacle,circa,bookmaker,betcris,betfair_ex_uk,matchbook,smarkets")
    parser.add_argument("--markets", default="h2h")
    parser.add_argument("--odds-format", default="american")
    parser.add_argument("--raw-output-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    sport_keys = _split_csv(args.sport_keys)
    bookmakers = _split_csv(args.bookmakers)
    markets = _split_csv(args.markets)
    regions = _split_csv(args.regions)
    try:
        report = run_sharp_provider_capture(
            out_dir=args.out_dir,
            run_id=args.run_id,
            capture_current=bool(args.capture_current),
            raw_provider_json=args.raw_provider_json,
            api_key_file=args.api_key_file,
            sport_keys=sport_keys,
            regions=regions,
            bookmakers=bookmakers,
            markets=markets,
            odds_format=args.odds_format,
            raw_output_dir=args.raw_output_dir,
            timeout_seconds=args.timeout_seconds,
            write=True,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "sports_consensus_sharp_provider_capture_blocked_runtime_error",
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
                "status": report["status"],
                "summary": report["summary"],
                "json_path": str(args.out_dir / "kalshi-sports-consensus-sharp-provider-capture.json"),
                "markdown_path": str(
                    args.out_dir / "kalshi-sports-consensus-sharp-provider-capture.md"
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def run_sharp_provider_capture(
    *,
    out_dir: Path = DEFAULT_OUT_DIR,
    run_id: str = "kalshi-sports-consensus-sharp-provider-capture-latest",
    capture_current: bool = False,
    raw_provider_json: Sequence[Path] = (),
    api_key_file: Path = DEFAULT_KEY_FILE,
    sport_keys: Sequence[str] = (),
    regions: Sequence[str] = ("us",),
    bookmakers: Sequence[str] = (),
    markets: Sequence[str] = ("h2h",),
    odds_format: str = "american",
    raw_output_dir: Path = DEFAULT_RAW_DIR,
    timeout_seconds: float = 20.0,
    write: bool = False,
) -> dict[str, Any]:
    captures = [_capture_from_raw(path) for path in raw_provider_json]
    if capture_current:
        captures.extend(
            capture_sharp_provider_sources(
                api_key=_read_api_key(api_key_file),
                sport_keys=sport_keys,
                raw_output_dir=raw_output_dir,
                regions=regions,
                bookmakers=bookmakers,
                markets=markets,
                odds_format=odds_format,
                timeout_seconds=timeout_seconds,
            )
        )
    report = build_sharp_provider_capture_report(
        captures=captures,
        requested_sport_keys=sport_keys,
        requested_bookmakers=bookmakers,
        requested_markets=markets,
        requested_regions=regions,
        run_id=run_id,
    )
    if write:
        write_sharp_provider_capture_outputs(report, out_dir)
    return report


def _capture_from_raw(path: Path) -> dict[str, Any]:
    payload = _read_json_list(path)
    meta_path = _meta_path_for(path)
    meta = _read_json_object(meta_path) if meta_path.is_file() else {}
    sport_key = str(meta.get("sport_key") or _infer_sport_key(payload) or path.stem)
    return {
        "sport_key": sport_key,
        "payload": payload,
        "meta": meta,
        "raw_path": path,
        "error": None,
    }


def _read_api_key(path: Path) -> str:
    key = path.expanduser().read_text(encoding="utf-8").strip()
    if not key:
        raise ValueError(f"API key file is empty: {path}")
    return key


def _read_json_list(path: Path) -> list[Mapping[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected JSON list in {path}")
    return [row for row in payload if isinstance(row, Mapping)]


def _read_json_object(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _meta_path_for(path: Path) -> Path:
    if path.name.endswith(".json"):
        return path.with_name(f"{path.stem}.meta.json")
    return path.with_suffix(f"{path.suffix}.meta.json")


def _infer_sport_key(payload: Sequence[Mapping[str, Any]]) -> str | None:
    for row in payload:
        sport_key = row.get("sport_key")
        if sport_key:
            return str(sport_key)
    return None


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in str(value).split(",") if part.strip())


if __name__ == "__main__":
    raise SystemExit(main())
