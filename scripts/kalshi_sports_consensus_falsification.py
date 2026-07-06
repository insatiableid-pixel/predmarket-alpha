#!/usr/bin/env python3
"""Falsification ledger CLI for the Kalshi sports no-vig consensus surface.

Reads:
- the latest sports consensus preflight artifact (current candidates),
- a directory of archived consensus observation packets (joined at archive
  time to the timestamp-matched Kalshi mid),
- a directory of exact Kalshi settlement label packets.

Joins observations to settlement labels by exact contract_ticker+side and
runs ``predmarket.sports_consensus_falsification`` to produce a
multiple-testing-controlled research artifact.

The artifact is research-only. No EV, sizing, or execution.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import (  # noqa: E402
    path_is_within,
    read_json_or_empty,
    safe_research_artifact,
)
from predmarket.sports_consensus_falsification import (  # noqa: E402
    DEFAULT_FDR_ALPHA,
    DEFAULT_MIN_INDEPENDENT_LABELS,
    DEFAULT_MIN_OOS_LABELS,
    DEFAULT_TEST_FRACTION,
    FAMILY_ID,
    build_sports_consensus_falsification,
    render_sports_consensus_falsification_markdown,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_PREFLIGHT_PATH = MACRO_DIR / "latest-kalshi-sports-consensus-preflight.json"
DEFAULT_OBSERVATION_DIR = Path("/home/mrwatson/manual_drops/kalshi_sports_consensus_observations")
DEFAULT_LABEL_DIR = Path("/home/mrwatson/manual_drops/kalshi_sports_consensus_labels")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-consensus-falsification-latest"

CSV_FIELDS = [
    "contract_ticker",
    "event_ticker",
    "family_id",
    "model_id",
    "signal_key",
    "candidate_rule",
    "threshold",
    "price_bucket",
    "side",
    "kalshi_mid_for_side",
    "consensus_probability_for_side",
    "divergence",
    "selected_side_prediction",
    "settlement_outcome",
    "correct",
    "observed_utc",
    "settlement_time_utc",
    "sport_key",
    "market_key",
    "cluster_key",
    "book_count",
    "distinct_books",
    "source_reference_sha256",
    "research_only",
    "usable",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_sports_consensus_falsification(
    *,
    preflight_path: Path = DEFAULT_PREFLIGHT_PATH,
    observation_dir: Path = DEFAULT_OBSERVATION_DIR,
    label_dir: Path = DEFAULT_LABEL_DIR,
    output_dir: Path = DEFAULT_OUT_DIR,
    min_independent_labels: int = DEFAULT_MIN_INDEPENDENT_LABELS,
    min_oos_labels: int = DEFAULT_MIN_OOS_LABELS,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    fdr_alpha: float = DEFAULT_FDR_ALPHA,
    write: bool = False,
) -> dict[str, Any]:
    preflight_payload = read_json_or_empty(preflight_path) if preflight_path.is_file() else {}
    preflight_report = preflight_payload or None
    observations = load_packet_rows(observation_dir)
    labels = load_packet_rows(label_dir)
    report = build_sports_consensus_falsification(
        preflight_report=preflight_report,
        consensus_observations=observations,
        settlement_labels=labels,
        min_independent_labels=min_independent_labels,
        min_oos_labels=min_oos_labels,
        test_fraction=test_fraction,
        fdr_alpha=fdr_alpha,
        preflight_path=preflight_path if preflight_path.is_file() else None,
        observation_dir=observation_dir,
        label_dir=label_dir,
    )
    if write:
        paths = write_outputs(report, out_dir=output_dir)
        report = {**report, "output_paths": paths}
    return report


def load_packet_rows(packet_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    if not packet_dir.exists():
        return rows
    for path in sorted(packet_dir.glob("*.json")):
        payload = read_json_or_empty(path)
        if not safe_research_artifact(payload):
            continue
        packet_rows = payload.get("rows")
        if not isinstance(packet_rows, list):
            continue
        for row in packet_rows:
            if isinstance(row, Mapping):
                key = str(row.get("observation_id") or "")
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                rows.append(dict(row))
    return rows


def write_outputs(report: Mapping[str, Any], *, out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-consensus-falsification.json"
    md_path = out_dir / "kalshi-sports-consensus-falsification.md"
    csv_path = out_dir / "kalshi-sports-consensus-falsification.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    markdown = render_sports_consensus_falsification_markdown(report)
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    write_csv(report.get("rows", []), csv_path)

    paths = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
    }
    if path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-sports-consensus-falsification.json"
        latest_md = MACRO_DIR / "latest-kalshi-sports-consensus-falsification.md"
        latest_csv = MACRO_DIR / "latest-kalshi-sports-consensus-falsification.csv"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(markdown, encoding="utf-8")
        write_csv(report.get("rows", []), latest_csv)
        paths.update(
            {
                "latest_json_path": str(latest_json),
                "latest_markdown_path": str(latest_md),
                "latest_csv_path": str(latest_csv),
            }
        )
    return paths


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            if isinstance(row, Mapping):
                writer.writerow({field: row.get(field) for field in CSV_FIELDS})


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-path", type=Path, default=DEFAULT_PREFLIGHT_PATH)
    parser.add_argument("--observation-dir", type=Path, default=DEFAULT_OBSERVATION_DIR)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--min-independent-labels", type=int, default=DEFAULT_MIN_INDEPENDENT_LABELS
    )
    parser.add_argument("--min-oos-labels", type=int, default=DEFAULT_MIN_OOS_LABELS)
    parser.add_argument("--test-fraction", type=float, default=DEFAULT_TEST_FRACTION)
    parser.add_argument("--fdr-alpha", type=float, default=DEFAULT_FDR_ALPHA)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_sports_consensus_falsification(
        preflight_path=args.preflight_path,
        observation_dir=args.observation_dir,
        label_dir=args.label_dir,
        output_dir=args.out_dir,
        min_independent_labels=args.min_independent_labels,
        min_oos_labels=args.min_oos_labels,
        test_fraction=args.test_fraction,
        fdr_alpha=args.fdr_alpha,
        write=args.write,
    )
    if args.write:
        paths = report.get("output_paths", {})
        output = {"status": report.get("status"), "family_id": FAMILY_ID, **paths}
    else:
        output = report
    print(json.dumps(output, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
