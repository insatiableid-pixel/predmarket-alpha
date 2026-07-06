#!/usr/bin/env python3
"""Wrap World Cup soccer sharp rows into the strict sports consensus manifest."""

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

from predmarket.sports_consensus_reference_builder import (  # noqa: E402
    DEFAULT_KEY_FILE,
    DEFAULT_RAW_DIR,
    capture_the_odds_api_current,
)
from predmarket.sports_consensus_soccer_adapter import (  # noqa: E402
    DEFAULT_ALLOWED_BOOKS,
    build_soccer_consensus_adapter,
    render_soccer_consensus_adapter_markdown,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-consensus-soccer-adapter-latest"
DEFAULT_REFERENCE_JSON = Path("/home/mrwatson/manual_drops/predmarket/sports-no-vig-consensus.json")
DEFAULT_COMBINED_KALSHI_JSON = Path(
    "/home/mrwatson/manual_drops/predmarket/sports-consensus-kalshi-snapshot.json"
)
DEFAULT_BASE_KALSHI_JSON = MACRO_DIR / "latest-kalshi-universe-scan.json"
DEFAULT_SOCCER_KALSHI_JSON = Path(
    "/home/mrwatson/manual_drops/kalshi/kalshi_world_cup_game_series_latest.json"
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-json", type=Path, default=DEFAULT_REFERENCE_JSON)
    parser.add_argument("--combined-kalshi-json", type=Path, default=DEFAULT_COMBINED_KALSHI_JSON)
    parser.add_argument("--base-kalshi-json", type=Path, default=DEFAULT_BASE_KALSHI_JSON)
    parser.add_argument("--soccer-kalshi-json", type=Path, default=DEFAULT_SOCCER_KALSHI_JSON)
    parser.add_argument("--soccer-odds-json", type=Path, default=None)
    parser.add_argument("--soccer-odds-meta-json", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--run-id", default="kalshi-sports-consensus-soccer-adapter-latest")
    parser.add_argument("--allowed-books", default=",".join(DEFAULT_ALLOWED_BOOKS))
    parser.add_argument("--max-source-age-seconds", type=float, default=900.0)
    parser.add_argument("--max-game-duration-seconds", type=float, default=21_600.0)
    parser.add_argument("--capture-current", action="store_true")
    parser.add_argument("--api-key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--raw-output-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def run_soccer_consensus_adapter(
    *,
    reference_json: Path = DEFAULT_REFERENCE_JSON,
    combined_kalshi_json: Path = DEFAULT_COMBINED_KALSHI_JSON,
    base_kalshi_json: Path = DEFAULT_BASE_KALSHI_JSON,
    soccer_kalshi_json: Path = DEFAULT_SOCCER_KALSHI_JSON,
    soccer_odds_json: Path | None = None,
    soccer_odds_meta_json: Path | None = None,
    out_dir: Path = DEFAULT_OUT_DIR,
    run_id: str | None = None,
    allowed_books: Sequence[str] = DEFAULT_ALLOWED_BOOKS,
    max_source_age_seconds: float = 900.0,
    max_game_duration_seconds: float = 21_600.0,
    capture_current: bool = False,
    api_key_file: Path = DEFAULT_KEY_FILE,
    raw_output_dir: Path = DEFAULT_RAW_DIR,
    timeout_seconds: float = 20.0,
    write: bool = False,
) -> dict[str, Any]:
    existing_reference = _read_json_object(reference_json) if reference_json.is_file() else {}
    base_kalshi = _read_json_object(base_kalshi_json) if base_kalshi_json.is_file() else {}
    soccer_kalshi = _read_json_object(soccer_kalshi_json) if soccer_kalshi_json.is_file() else {}
    odds_path = soccer_odds_json or _latest_soccer_odds_json(raw_output_dir)
    meta_path = soccer_odds_meta_json or _meta_path_for(odds_path)
    if capture_current:
        payload, meta, raw_path = capture_the_odds_api_current(
            api_key=_read_api_key(api_key_file),
            sport_key="soccer_fifa_world_cup",
            output_dir=raw_output_dir,
            bookmakers=tuple(allowed_books),
            markets=("h2h",),
            timeout_seconds=timeout_seconds,
        )
        odds_rows = [dict(row) for row in payload if isinstance(row, Mapping)]
        odds_meta = meta
        odds_path = raw_path
        meta_path = _meta_path_for(raw_path)
    else:
        odds_rows = _read_json_list(odds_path) if odds_path and odds_path.is_file() else []
        odds_meta = _read_json_object(meta_path) if meta_path and meta_path.is_file() else {}
    reference, combined_kalshi, report = build_soccer_consensus_adapter(
        existing_reference=existing_reference,
        base_kalshi_payload=base_kalshi,
        soccer_kalshi_payload=soccer_kalshi,
        soccer_odds_payload=odds_rows,
        soccer_odds_meta=odds_meta,
        existing_reference_path=reference_json,
        base_kalshi_path=base_kalshi_json,
        soccer_kalshi_path=soccer_kalshi_json,
        soccer_odds_path=odds_path,
        soccer_odds_meta_path=meta_path,
        combined_kalshi_path=combined_kalshi_json,
        run_id=run_id,
        allowed_books=allowed_books,
        max_source_age_seconds=max_source_age_seconds,
        max_game_duration_seconds=max_game_duration_seconds,
    )
    if write:
        paths = write_outputs(
            reference,
            combined_kalshi,
            report,
            reference_json=reference_json,
            combined_kalshi_json=combined_kalshi_json,
            out_dir=out_dir,
        )
        report = {**report, "output_paths": paths}
    return report


def write_outputs(
    reference: Mapping[str, Any],
    combined_kalshi: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    reference_json: Path,
    combined_kalshi_json: Path,
    out_dir: Path,
) -> dict[str, str]:
    reference_json.parent.mkdir(parents=True, exist_ok=True)
    combined_kalshi_json.parent.mkdir(parents=True, exist_ok=True)
    reference_text = json.dumps(reference, indent=2, sort_keys=True, default=str) + "\n"
    kalshi_text = json.dumps(combined_kalshi, indent=2, sort_keys=True, default=str) + "\n"
    reference_json.write_text(reference_text, encoding="utf-8")
    combined_kalshi_json.write_text(kalshi_text, encoding="utf-8")

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-consensus-soccer-adapter.json"
    md_path = out_dir / "kalshi-sports-consensus-soccer-adapter.md"
    report_text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    markdown = render_soccer_consensus_adapter_markdown(report)
    json_path.write_text(report_text, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "reference_json_path": str(reference_json),
        "combined_kalshi_json_path": str(combined_kalshi_json),
    }
    if _path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-sports-consensus-soccer-adapter.json"
        latest_md = MACRO_DIR / "latest-kalshi-sports-consensus-soccer-adapter.md"
        latest_json.write_text(report_text, encoding="utf-8")
        latest_md.write_text(markdown, encoding="utf-8")
        paths.update({"latest_json_path": str(latest_json), "latest_markdown_path": str(latest_md)})
    return paths


def _latest_soccer_odds_json(raw_output_dir: Path) -> Path | None:
    matches = sorted(raw_output_dir.glob("soccer_fifa_world_cup_current_*.json"))
    matches = [path for path in matches if not path.name.endswith(".meta.json")]
    return matches[-1] if matches else None


def _meta_path_for(path: Path | None) -> Path | None:
    if path is None:
        return None
    return path.with_name(path.name.removesuffix(".json") + ".meta.json")


def _read_json_object(path: Path | None) -> Mapping[str, Any]:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, Mapping) else {}


def _read_json_list(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        return []
    return [dict(row) for row in payload if isinstance(row, Mapping)]


def _read_api_key(path: Path) -> str:
    key = path.expanduser().read_text(encoding="utf-8").strip()
    if not key:
        raise ValueError(f"API key file is empty: {path}")
    return key


def _path_is_within(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
    except ValueError:
        return False
    return True


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_soccer_consensus_adapter(
        reference_json=args.reference_json,
        combined_kalshi_json=args.combined_kalshi_json,
        base_kalshi_json=args.base_kalshi_json,
        soccer_kalshi_json=args.soccer_kalshi_json,
        soccer_odds_json=args.soccer_odds_json,
        soccer_odds_meta_json=args.soccer_odds_meta_json,
        out_dir=args.out_dir,
        run_id=args.run_id,
        allowed_books=tuple(part.strip() for part in args.allowed_books.split(",") if part.strip()),
        max_source_age_seconds=args.max_source_age_seconds,
        max_game_duration_seconds=args.max_game_duration_seconds,
        capture_current=args.capture_current,
        api_key_file=args.api_key_file,
        raw_output_dir=args.raw_output_dir,
        timeout_seconds=args.timeout_seconds,
        write=args.write,
    )
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "summary": report.get("summary"),
                **dict(report.get("output_paths", {})),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
