#!/usr/bin/env python3
"""Write a Kalshi live risk snapshot from durable live state."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from kalshi_live_common import DEFAULT_STATE_DIR, MACRO_DIR, write_and_print

from predmarket.config import load_config
from predmarket.kalshi_live_engine import (
    LiveRiskLimits,
    LiveStateStore,
    build_live_risk_snapshot,
)

DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-live-risk-snapshot-latest"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--account-balance-usd", type=float, default=None)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config()
    state = LiveStateStore(args.state_dir).load()
    risk = build_live_risk_snapshot(
        state=state,
        account_balance_usd=args.account_balance_usd,
        limits=LiveRiskLimits.from_config(config),
    )
    report = {
        "schema_version": 1,
        "generated_utc": risk["generated_utc"],
        "status": "kalshi_live_risk_snapshot_ready",
        "execution_mode": config.kalshi_live.execution_mode,
        "armed": False,
        "summary": {
            "live_decision_count": 0,
            "live_eligible_count": 0,
            "blocked_decision_count": 0,
            "total_live_stake": 0.0,
        },
        "risk_snapshot": risk,
        "decisions": [],
    }
    if args.write:
        write_and_print(
            report,
            out_dir=args.out_dir,
            stem="kalshi-live-risk-snapshot",
            title="Kalshi Live Risk Snapshot",
        )
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
