#!/usr/bin/env python3
"""Gate World Cup/FIFA replay candidates on depth, clusters, and decay.

This wrapper reuses the sports CCD implementation but points it at the World
Cup observation/replay artifacts and writes World Cup-named outputs. It remains
research-only and never emits usable rows, stake, account, or order actions.
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

from kalshi_sports_proxy_capacity_correlation_decay import (  # noqa: E402
    DEFAULT_DELAY_SECONDS,
    DEFAULT_DEPTH,
    DEFAULT_MAX_CLUSTER_SHARE,
    DEFAULT_MIN_DECAY_BUCKETS,
    DEFAULT_MIN_DECAY_LABELS,
    DEFAULT_MIN_POSITIVE_CAPACITY_CONTRACTS,
    build_sports_proxy_capacity_correlation_decay,
    write_csv,
)
from kalshi_sports_proxy_capacity_correlation_decay import (  # noqa: E402
    render_markdown as render_sports_markdown,
)

from predmarket.shared_helpers import manual_drop_path  # noqa: E402

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_FEATURE_PACKET_PATH = MACRO_DIR / "latest-kalshi-world-cup-proxy-observation-loop.json"
DEFAULT_REPLAY_PATH = MACRO_DIR / "latest-kalshi-world-cup-proxy-research-candidate-replay.json"
DEFAULT_RAW_ORDERBOOK_DIR = manual_drop_path("kalshi_world_cup_proxy_orderbooks")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-world-cup-proxy-capacity-correlation-decay-latest"
DEFAULT_MAX_CLOSE_HOURS = 72.0
DEFAULT_MAX_TICKERS = 80


def world_cup_status(status: str) -> str:
    return status.replace("sports_proxy_", "world_cup_proxy_", 1)


def build_world_cup_proxy_capacity_correlation_decay(
    *,
    feature_packet_path: Path = DEFAULT_FEATURE_PACKET_PATH,
    replay_path: Path = DEFAULT_REPLAY_PATH,
    raw_orderbook_dir: Path = DEFAULT_RAW_ORDERBOOK_DIR,
    generated_utc: str | None = None,
    max_close_hours: float = DEFAULT_MAX_CLOSE_HOURS,
    max_tickers: int = DEFAULT_MAX_TICKERS,
    depth: int = DEFAULT_DEPTH,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    capture_orderbooks: bool = False,
    max_cluster_share: float = DEFAULT_MAX_CLUSTER_SHARE,
    min_positive_capacity_contracts: float = DEFAULT_MIN_POSITIVE_CAPACITY_CONTRACTS,
    min_decay_buckets: int = DEFAULT_MIN_DECAY_BUCKETS,
    min_decay_labels: int = DEFAULT_MIN_DECAY_LABELS,
) -> dict[str, Any]:
    report = build_sports_proxy_capacity_correlation_decay(
        feature_packet_path=feature_packet_path,
        replay_path=replay_path,
        raw_orderbook_dir=raw_orderbook_dir,
        generated_utc=generated_utc,
        max_close_hours=max_close_hours,
        max_tickers=max_tickers,
        depth=depth,
        delay_seconds=delay_seconds,
        capture_orderbooks=capture_orderbooks,
        max_cluster_share=max_cluster_share,
        min_positive_capacity_contracts=min_positive_capacity_contracts,
        min_decay_buckets=min_decay_buckets,
        min_decay_labels=min_decay_labels,
    )
    report["status"] = world_cup_status(str(report.get("status") or ""))
    report["family_id"] = "world_cup_soccer"
    report["inputs"]["family_id"] = "world_cup_soccer"
    report["method"]["family_adapter"] = (
        "World Cup/FIFA wrapper over the shared sports CCD spine; current rows come from "
        "the World Cup observation packet and side selection comes from the replay model."
    )
    report["next_action"] = next_action(str(report["status"]))
    return report


def next_action(status: str) -> dict[str, str]:
    if status == "world_cup_proxy_capacity_correlation_decay_ready_for_paper_overlay":
        return {
            "name": "kalshi_world_cup_proxy_correlation_cluster_control",
            "why": "World Cup capacity, depth, and decay gates passed; cluster control decides any paper overlay.",
            "stop_condition": "Stop before real positions, execution, account/order paths, staking, or live edge claims.",
        }
    return {
        "name": "kalshi_world_cup_proxy_gate_accumulation",
        "why": "World Cup capacity/depth/correlation/decay gates are not all passing yet.",
        "stop_condition": "Stop before lowering thresholds or inferring capacity from quotes without depth.",
    }


def write_world_cup_proxy_capacity_correlation_decay(
    report: Mapping[str, Any],
    out_dir: Path = DEFAULT_OUT_DIR,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-world-cup-proxy-capacity-correlation-decay.json"
    markdown_path = out_dir / "kalshi-world-cup-proxy-capacity-correlation-decay.md"
    csv_path = out_dir / "kalshi-world-cup-proxy-capacity-correlation-decay.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, csv_path)

    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-world-cup-proxy-capacity-correlation-decay.json"
    latest_md = MACRO_DIR / "latest-kalshi-world-cup-proxy-capacity-correlation-decay.md"
    latest_csv = MACRO_DIR / "latest-kalshi-world-cup-proxy-capacity-correlation-decay.csv"
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
        "# Kalshi Sports Proxy Capacity Correlation Decay",
        "# Kalshi World Cup Proxy Capacity Correlation Decay",
        1,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-packet-path", type=Path, default=DEFAULT_FEATURE_PACKET_PATH)
    parser.add_argument("--replay-path", type=Path, default=DEFAULT_REPLAY_PATH)
    parser.add_argument("--raw-orderbook-dir", type=Path, default=DEFAULT_RAW_ORDERBOOK_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-close-hours", type=float, default=DEFAULT_MAX_CLOSE_HOURS)
    parser.add_argument("--max-tickers", type=int, default=DEFAULT_MAX_TICKERS)
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    parser.add_argument("--delay-seconds", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--max-cluster-share", type=float, default=DEFAULT_MAX_CLUSTER_SHARE)
    parser.add_argument(
        "--min-positive-capacity-contracts",
        type=float,
        default=DEFAULT_MIN_POSITIVE_CAPACITY_CONTRACTS,
    )
    parser.add_argument("--min-decay-buckets", type=int, default=DEFAULT_MIN_DECAY_BUCKETS)
    parser.add_argument("--min-decay-labels", type=int, default=DEFAULT_MIN_DECAY_LABELS)
    parser.add_argument("--capture-orderbooks", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_world_cup_proxy_capacity_correlation_decay(
        feature_packet_path=args.feature_packet_path,
        replay_path=args.replay_path,
        raw_orderbook_dir=args.raw_orderbook_dir,
        max_close_hours=args.max_close_hours,
        max_tickers=args.max_tickers,
        depth=args.depth,
        delay_seconds=args.delay_seconds,
        capture_orderbooks=args.capture_orderbooks,
        max_cluster_share=args.max_cluster_share,
        min_positive_capacity_contracts=args.min_positive_capacity_contracts,
        min_decay_buckets=args.min_decay_buckets,
        min_decay_labels=args.min_decay_labels,
    )
    if args.write:
        paths = write_world_cup_proxy_capacity_correlation_decay(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], "paths": paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
