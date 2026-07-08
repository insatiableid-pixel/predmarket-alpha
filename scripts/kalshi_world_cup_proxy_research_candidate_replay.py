#!/usr/bin/env python3
"""Replay World Cup/FIFA research candidates through all-in Kalshi cost gates.

This is a family-specific wrapper over the generic sports replay machinery.
It exists so World Cup/FIFA OOS/FDR candidates can advance beyond the label
ledger without clobbering the MLB ``latest-kalshi-sports-proxy-*`` artifacts.
Rows remain research-only and never authorize sizing or execution.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = CONTROL_REPO / "scripts"
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kalshi_falsification_replay_shared import (  # noqa: E402
    DEFAULT_CONFIDENCE_Z,
    DEFAULT_MIN_DECAY_BUCKETS,
    DEFAULT_MIN_DECAY_LABELS,
    DEFAULT_MIN_SIDE_OOS_LABELS,
    REPLAY_CSV_FIELDS,
    write_csv_generic,
)
from kalshi_sports_proxy_research_candidate_replay import (  # noqa: E402
    build_sports_proxy_research_candidate_replay,
)
from kalshi_sports_proxy_research_candidate_replay import (  # noqa: E402
    render_markdown as render_sports_markdown,
)

from predmarket.shared_helpers import manual_drop_path  # noqa: E402

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_LABEL_DIR = manual_drop_path("kalshi_world_cup_proxy_labels")
DEFAULT_MODEL_FALSIFICATION_PATH = (
    MACRO_DIR / "latest-kalshi-world-cup-proxy-feature-model-falsification.json"
)
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-world-cup-proxy-research-candidate-replay-latest"


def world_cup_status(status: str) -> str:
    return status.replace("sports_proxy_", "world_cup_proxy_", 1)


def build_world_cup_proxy_research_candidate_replay(
    *,
    label_dir: Path = DEFAULT_LABEL_DIR,
    model_falsification_path: Path = DEFAULT_MODEL_FALSIFICATION_PATH,
    generated_utc: str | None = None,
    confidence_z: float = DEFAULT_CONFIDENCE_Z,
    min_side_oos_labels: int = DEFAULT_MIN_SIDE_OOS_LABELS,
    min_decay_buckets: int = DEFAULT_MIN_DECAY_BUCKETS,
    min_decay_labels: int = DEFAULT_MIN_DECAY_LABELS,
    preferred_model_id: str | None = None,
) -> dict[str, Any]:
    report = build_sports_proxy_research_candidate_replay(
        label_dir=label_dir,
        model_falsification_path=model_falsification_path,
        generated_utc=generated_utc,
        confidence_z=confidence_z,
        min_side_oos_labels=min_side_oos_labels,
        min_decay_buckets=min_decay_buckets,
        min_decay_labels=min_decay_labels,
        preferred_model_id=preferred_model_id,
    )
    report["status"] = world_cup_status(str(report.get("status") or ""))
    report["family_id"] = "world_cup_soccer"
    report["inputs"]["family_id"] = "world_cup_soccer"
    report["method"]["family_adapter"] = (
        "World Cup/FIFA wrapper over the shared sports replay spine; prediction rules come "
        "from OOS/FDR-passed market-structure labels, not soccer handicapping."
    )
    report["next_action"] = next_action(str(report["status"]))
    return report


def next_action(status: str) -> dict[str, str]:
    if status == "world_cup_proxy_research_candidate_replay_blocked_predeployment_gates":
        return {
            "name": "kalshi_world_cup_proxy_capacity_correlation_decay",
            "why": "A World Cup research candidate has conservative cost-adjusted replay rows, but capacity, correlation, and decay gates still decide promotion.",
            "stop_condition": "Stop before paper stake or live order until cost, depth, cluster, and decay gates pass.",
        }
    if status == "world_cup_proxy_research_candidate_replay_ready_for_paper_probability_overlay":
        return {
            "name": "kalshi_world_cup_proxy_paper_probability_overlay",
            "why": "Replay gates are research-ready; next work is capacity, cluster, and paper-only overlay handling.",
            "stop_condition": "Stop before real positions, execution, or account/order paths.",
        }
    return {
        "name": "kalshi_world_cup_proxy_observation_accumulation",
        "why": "World Cup replay is missing a passed candidate, usable replay rows, or positive cost-adjusted rows.",
        "stop_condition": "Stop before lowering thresholds or using unsettled contracts as labels.",
    }


def write_world_cup_proxy_research_candidate_replay(
    report: Mapping[str, Any],
    out_dir: Path = DEFAULT_OUT_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-world-cup-proxy-research-candidate-replay.json"
    markdown_path = out_dir / "kalshi-world-cup-proxy-research-candidate-replay.md"
    csv_path = out_dir / "kalshi-world-cup-proxy-research-candidate-replay.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv_generic(report, csv_path, REPLAY_CSV_FIELDS, rows_key="replay_rows")

    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-world-cup-proxy-research-candidate-replay.json"
    latest_md = MACRO_DIR / "latest-kalshi-world-cup-proxy-research-candidate-replay.md"
    latest_csv = MACRO_DIR / "latest-kalshi-world-cup-proxy-research-candidate-replay.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv_generic(report, latest_csv, REPLAY_CSV_FIELDS, rows_key="replay_rows")
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "csv_path": str(csv_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
        "latest_csv_path": str(latest_csv),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    return render_sports_markdown(report).replace(
        "# Kalshi Sports Proxy Research Candidate Replay",
        "# Kalshi World Cup Proxy Research Candidate Replay",
        1,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument(
        "--model-falsification-path", type=Path, default=DEFAULT_MODEL_FALSIFICATION_PATH
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--confidence-z", type=float, default=DEFAULT_CONFIDENCE_Z)
    parser.add_argument("--min-side-oos-labels", type=int, default=DEFAULT_MIN_SIDE_OOS_LABELS)
    parser.add_argument("--min-decay-buckets", type=int, default=DEFAULT_MIN_DECAY_BUCKETS)
    parser.add_argument("--min-decay-labels", type=int, default=DEFAULT_MIN_DECAY_LABELS)
    parser.add_argument("--preferred-model-id", default=None)
    parser.add_argument("--write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_world_cup_proxy_research_candidate_replay(
        label_dir=args.label_dir,
        model_falsification_path=args.model_falsification_path,
        confidence_z=args.confidence_z,
        min_side_oos_labels=args.min_side_oos_labels,
        min_decay_buckets=args.min_decay_buckets,
        min_decay_labels=args.min_decay_labels,
        preferred_model_id=args.preferred_model_id,
    )
    if args.write:
        paths = write_world_cup_proxy_research_candidate_replay(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], "paths": paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
