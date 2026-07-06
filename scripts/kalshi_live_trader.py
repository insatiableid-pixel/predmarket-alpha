#!/usr/bin/env python3
"""Run one unattended Kalshi live-autonomous trading pass."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from kalshi_live_common import (
    DEFAULT_EXTERNAL_PREFLIGHT,
    DEFAULT_PAPER_DECISIONS,
    DEFAULT_RETIREMENT,
    DEFAULT_STATE_DIR,
    MACRO_DIR,
    client_or_none,
    write_and_print,
)
from kalshi_live_preflight import public_market_snapshots

from predmarket.config import load_config
from predmarket.kalshi_live_engine import (
    LiveStateStore,
    build_live_preflight_report,
    live_arming_state,
    normalize_market_snapshot_index,
    run_live_trader_once,
)
from predmarket.shared_helpers import read_json_or_empty

DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-live-trader-latest"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-decisions-path", type=Path, default=DEFAULT_PAPER_DECISIONS)
    parser.add_argument("--external-preflight-path", type=Path, default=DEFAULT_EXTERNAL_PREFLIGHT)
    parser.add_argument("--retirement-path", type=Path, default=DEFAULT_RETIREMENT)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--execution-mode", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def add_credential_blocker(report: dict[str, object]) -> dict[str, object]:
    risk = report.get("risk_snapshot") if isinstance(report.get("risk_snapshot"), dict) else {}
    reasons = list(risk.get("kill_switch_reasons") or [])
    reasons.append("Kalshi credentials missing")
    risk["kill_switch_reasons"] = reasons
    report["risk_snapshot"] = risk
    report["status"] = "kalshi_live_blocked"
    return report


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config()
    mode = str(args.execution_mode or config.kalshi_live.execution_mode)
    arming = live_arming_state(config, mode)
    client = client_or_none(config, execution_mode=mode) if arming.armed else None
    if client is None:
        paper_report = read_json_or_empty(args.paper_decisions_path)
        capture = public_market_snapshots(
            paper_report=paper_report,
            base_url=config.venues.kalshi.api_url,
            depth=10,
            timeout_seconds=10.0,
        )
        report = build_live_preflight_report(
            paper_decisions_path=args.paper_decisions_path,
            external_preflight_path=args.external_preflight_path,
            retirement_path=args.retirement_path,
            state_path=args.state_dir,
            market_snapshots=normalize_market_snapshot_index(capture),
            execution_mode=mode,
            config=config,
        )
        if arming.armed:
            report = add_credential_blocker(report)
    else:
        report = run_live_trader_once(
            client=client,
            state_store=LiveStateStore(args.state_dir),
            paper_decisions_path=args.paper_decisions_path,
            external_preflight_path=args.external_preflight_path,
            retirement_path=args.retirement_path,
            execution_mode=mode,
            dry_run=args.dry_run,
            config=config,
        )
    if args.write:
        write_and_print(
            report,
            out_dir=args.out_dir,
            stem="kalshi-live-trader",
            title="Kalshi Live Trader",
        )
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
