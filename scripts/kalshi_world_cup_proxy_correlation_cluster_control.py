#!/usr/bin/env python3
"""Apply deterministic cluster controls to World Cup/FIFA proxy candidates."""

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

from kalshi_sports_proxy_correlation_cluster_control import (  # noqa: E402
    DEFAULT_MAX_CLUSTER_SHARE,
    DEFAULT_MIN_POSITIVE_CLUSTERS,
    build_sports_proxy_correlation_cluster_control,
    write_csv,
)
from kalshi_sports_proxy_correlation_cluster_control import (  # noqa: E402
    render_markdown as render_sports_markdown,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_CCD_PATH = MACRO_DIR / "latest-kalshi-world-cup-proxy-capacity-correlation-decay.json"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-world-cup-proxy-correlation-cluster-control-latest"


def world_cup_status(status: str) -> str:
    return status.replace("sports_proxy_", "world_cup_proxy_", 1)


def build_world_cup_proxy_correlation_cluster_control(
    *,
    ccd_path: Path = DEFAULT_CCD_PATH,
    generated_utc: str | None = None,
    max_cluster_share: float = DEFAULT_MAX_CLUSTER_SHARE,
    min_positive_clusters: int = DEFAULT_MIN_POSITIVE_CLUSTERS,
) -> dict[str, Any]:
    report = build_sports_proxy_correlation_cluster_control(
        ccd_path=ccd_path,
        generated_utc=generated_utc,
        max_cluster_share=max_cluster_share,
        min_positive_clusters=min_positive_clusters,
    )
    report["status"] = world_cup_status(str(report.get("status") or ""))
    report["family_id"] = "world_cup_soccer"
    report["inputs"]["family_id"] = "world_cup_soccer"
    report["method"]["family_adapter"] = (
        "World Cup/FIFA wrapper over the shared sports cluster-control spine."
    )
    report["next_action"] = next_action(str(report["status"]))
    return report


def next_action(status: str) -> dict[str, str]:
    if status == "world_cup_proxy_correlation_cluster_control_ready_for_paper_overlay":
        return {
            "name": "kalshi_world_cup_proxy_ev_ledger_promotion",
            "why": "World Cup cluster exposure limits are passing for research-only current candidates.",
            "stop_condition": "Let EV ledger and paper gates decide; do not touch live/account/order paths.",
        }
    return {
        "name": "kalshi_world_cup_proxy_cluster_or_capacity_accumulation",
        "why": "World Cup cluster control is blocked by missing or upstream-invalid CCD evidence.",
        "stop_condition": "Stop before reducing cluster breadth requirements without explicit policy review.",
    }


def write_world_cup_proxy_correlation_cluster_control(
    report: Mapping[str, Any],
    out_dir: Path = DEFAULT_OUT_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-world-cup-proxy-correlation-cluster-control.json"
    markdown_path = out_dir / "kalshi-world-cup-proxy-correlation-cluster-control.md"
    csv_path = out_dir / "kalshi-world-cup-proxy-correlation-cluster-control.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, csv_path)

    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-world-cup-proxy-correlation-cluster-control.json"
    latest_md = MACRO_DIR / "latest-kalshi-world-cup-proxy-correlation-cluster-control.md"
    latest_csv = MACRO_DIR / "latest-kalshi-world-cup-proxy-correlation-cluster-control.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, latest_csv)
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
        "# Kalshi Sports Proxy Correlation Cluster Control",
        "# Kalshi World Cup Proxy Correlation Cluster Control",
        1,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ccd-path", type=Path, default=DEFAULT_CCD_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-cluster-share", type=float, default=DEFAULT_MAX_CLUSTER_SHARE)
    parser.add_argument("--min-positive-clusters", type=int, default=DEFAULT_MIN_POSITIVE_CLUSTERS)
    parser.add_argument("--write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_world_cup_proxy_correlation_cluster_control(
        ccd_path=args.ccd_path,
        max_cluster_share=args.max_cluster_share,
        min_positive_clusters=args.min_positive_clusters,
    )
    if args.write:
        paths = write_world_cup_proxy_correlation_cluster_control(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], "paths": paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
