#!/usr/bin/env python3
"""Reconcile unresolved live Kalshi orders against the exchange."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from kalshi_live_common import (
    DEFAULT_STATE_DIR,
    MACRO_DIR,
    client_or_none,
    write_and_print,
)

from predmarket.config import load_config
from predmarket.kalshi_live_engine import LiveStateStore, reconcile_live_orders

DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-live-reconcile-latest"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--execution-mode", default=None)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def blocked_report(reason: str, execution_mode: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "kalshi_live_reconcile_blocked",
        "execution_mode": execution_mode,
        "armed": False,
        "summary": {"live_decision_count": 0, "live_eligible_count": 0},
        "risk_snapshot": {"kill_switch_reasons": [reason]},
        "decisions": [],
        "reconciliation": {"status": "blocked", "reason": reason},
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config()
    mode = str(args.execution_mode or config.kalshi_live.execution_mode)
    client = client_or_none(config, execution_mode=mode)
    report: dict[str, object]
    if client is None:
        report = blocked_report("Kalshi credentials missing", mode)
    else:
        state_store = LiveStateStore(args.state_dir)
        report = {
            "schema_version": 1,
            "status": "kalshi_live_reconcile_ready",
            "execution_mode": mode,
            "armed": False,
            "summary": {"live_decision_count": 0, "live_eligible_count": 0},
            "risk_snapshot": {"kill_switch_reasons": []},
            "decisions": [],
            "reconciliation": reconcile_live_orders(client=client, state_store=state_store),
        }
    if args.write:
        write_and_print(
            report,
            out_dir=args.out_dir,
            stem="kalshi-live-reconcile",
            title="Kalshi Live Reconcile",
        )
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
