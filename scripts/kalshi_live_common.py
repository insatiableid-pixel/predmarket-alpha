"""Shared helpers for Kalshi live CLI scripts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.config import Config  # noqa: E402
from predmarket.kalshi_live_artifacts import write_live_report  # noqa: E402
from predmarket.kalshi_live_client import (  # noqa: E402
    KalshiTradingClient,
    trading_client_config_from_app_config,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_STATE_DIR = CONTROL_REPO / "data" / "kalshi_live"
DEFAULT_PAPER_DECISIONS = MACRO_DIR / "latest-paper-decision-candidates.json"
DEFAULT_EXTERNAL_PREFLIGHT = MACRO_DIR / "latest-external-artifact-preflight.json"
DEFAULT_RETIREMENT = MACRO_DIR / "latest-signal-decay-retirement-ledger.json"


def client_or_none(config: Config, *, execution_mode: str) -> KalshiTradingClient | None:
    if not config.venues.kalshi.api_key or not config.venues.kalshi.api_secret:
        return None
    try:
        return KalshiTradingClient(
            trading_client_config_from_app_config(config, execution_mode=execution_mode)
        )
    except ValueError:
        return None


def write_and_print(
    report: dict[str, Any], *, out_dir: Path, stem: str, title: str
) -> dict[str, str]:
    paths = write_live_report(report, out_dir=out_dir, macro_dir=MACRO_DIR, stem=stem, title=title)
    print(json.dumps({"status": report.get("status"), **paths}, indent=2, sort_keys=True))
    return paths
