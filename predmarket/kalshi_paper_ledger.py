"""Standalone Kalshi paper-ledger audit reports."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from predmarket.config import load_config
from predmarket.kalshi_research_cycle import (
    KalshiPaperConfig,
    open_paper_intents_missing_close_time,
    paper_promotion_readiness,
    recent_paper_events,
    stale_open_paper_intents,
    summarize_paper_ledger,
)
from predmarket.kalshi_dataset import _stable_hash
from predmarket.store import PointInTimeStore


@dataclass
class KalshiPaperLedgerArtifacts:
    report: Dict[str, Any]
    json_path: Path
    markdown_path: Path


def build_paper_ledger_report(
    intents: Sequence[Mapping[str, Any]],
    *,
    events: Sequence[Mapping[str, Any]] = (),
    config: Optional[KalshiPaperConfig] = None,
    created_ts: Optional[float] = None,
) -> Dict[str, Any]:
    paper_config = config or KalshiPaperConfig()
    ts = float(created_ts or time.time())
    ledger = [dict(intent) for intent in intents]
    paper_events = [dict(event) for event in events]
    summary = summarize_paper_ledger(ledger)
    stale_open = stale_open_paper_intents(
        ledger,
        now_ts=ts,
        grace_hours=paper_config.stale_open_grace_hours,
    )
    unknown_close_open = open_paper_intents_missing_close_time(ledger)
    readiness = paper_promotion_readiness(
        summary,
        paper_config,
        stale_open_count=len(stale_open),
        unknown_close_open_count=len(unknown_close_open),
    )
    return {
        "run_id": stable_ledger_report_id(ledger, paper_events, paper_config),
        "created_ts": ts,
        "research_only": True,
        "execution_enabled": False,
        "ledger": {
            "count": len(ledger),
            "stale_open_count": len(stale_open),
            "unknown_close_open_count": len(unknown_close_open),
            **summary,
        },
        "promotion_readiness": readiness,
        "open_intents": [
            intent for intent in ledger if str(intent.get("status", "")) == "PAPER_INTENDED"
        ],
        "settled_intents": [
            intent for intent in ledger if str(intent.get("status", "")) == "SETTLED"
        ],
        "stale_open_intents": stale_open,
        "unknown_close_open_intents": unknown_close_open,
        "events": {
            "count": len(paper_events),
            "status_counts": _status_counts(paper_events),
            "recent": recent_paper_events(paper_events),
        },
        "integrity": {
            "artifact_schema_version": 2,
            "ledger_hash": _stable_hash(ledger),
            "events_hash": _stable_hash(paper_events),
            "config_hash": _stable_hash({"paper": paper_config.__dict__}),
        },
    }


def write_paper_ledger_report(
    report: Mapping[str, Any],
    *,
    reports_dir: Path,
) -> KalshiPaperLedgerArtifacts:
    reports_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(report.get("run_id") or f"kalshi-ledger-{int(time.time())}")
    json_path = reports_dir / f"{run_id}.json"
    markdown_path = reports_dir / f"{run_id}.md"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True, default=str)
    with markdown_path.open("w", encoding="utf-8") as f:
        f.write(render_paper_ledger_markdown(report))
    return KalshiPaperLedgerArtifacts(dict(report), json_path, markdown_path)


def render_paper_ledger_markdown(report: Mapping[str, Any]) -> str:
    ledger = report.get("ledger", {})
    readiness = report.get("promotion_readiness", {})
    stale_open = report.get("stale_open_intents", [])
    unknown_close_open = report.get("unknown_close_open_intents", [])
    lines = [
        f"# Kalshi Paper Ledger: {report.get('run_id', '')}",
        "",
        "## Scope",
        "",
        "- Mode: research-only",
        "- Execution enabled: false",
        "",
        "## Ledger Summary",
        "",
        f"- Count: {ledger.get('count', 0)}",
        f"- Status counts: {ledger.get('status_counts', {})}",
        f"- Open stake: ${float(ledger.get('open_stake_usd', 0.0)):.2f}",
        f"- Settled stake: ${float(ledger.get('settled_stake_usd', 0.0)):.2f}",
        f"- Settled PnL: ${float(ledger.get('settled_pnl_usd', 0.0)):.2f}",
        f"- Win rate: {ledger.get('win_rate')}",
        f"- Brier score: {ledger.get('brier_score')}",
        f"- Stale open intents: {ledger.get('stale_open_count', 0)}",
        f"- Unknown-close open intents: {ledger.get('unknown_close_open_count', 0)}",
        f"- Open event exposure: {ledger.get('open_event_exposure_usd', {})}",
        "",
        "## Stale Open Intents",
        "",
    ]
    if not stale_open:
        lines.append("No stale open paper intents.")
    for item in stale_open:
        lines.append(
            f"- {item.get('market_id', '')} {item.get('side', '')}: "
            f"{float(item.get('hours_past_stale', 0.0)):.2f} hours past stale threshold"
        )
    if unknown_close_open:
        lines.extend(["", "Open intents missing close-time estimates:", ""])
    for item in unknown_close_open:
        lines.append(f"- {item.get('market_id', '')} {item.get('side', '')}")
    lines.extend(
        [
            "",
            "## Event History",
            "",
            f"- Events: {report.get('events', {}).get('count', 0)}",
            f"- Event status counts: {report.get('events', {}).get('status_counts', {})}",
            "",
            "Recent events:",
            "",
        ]
    )
    recent = report.get("events", {}).get("recent", [])
    if not recent:
        lines.append("No paper events recorded.")
    for item in recent:
        lines.append(
            f"- {item.get('paper_event_type', '')} {item.get('market_id', '')} "
            f"{item.get('side', '')} at {float(item.get('paper_event_ts', 0.0)):.0f}"
        )
    lines.extend(
        [
            "",
            "## Promotion Readiness",
            "",
            f"- Status: {readiness.get('status', '')}",
            f"- Reasons: {readiness.get('reasons', [])}",
            f"- Observed: {readiness.get('observed', {})}",
            "",
            "## Open Intents",
            "",
        ]
    )
    open_intents = report.get("open_intents", [])
    if not open_intents:
        lines.append("No open paper intents.")
    for idx, intent in enumerate(open_intents, start=1):
        lines.extend(
            [
                f"### {idx}. {intent.get('market_id', '')}",
                "",
                str(intent.get("title", "")),
                "",
                f"- Side: {intent.get('side', '')}",
                f"- Stake: ${float(intent.get('stake_usd', 0.0)):.2f}",
                f"- Entry/model: {float(intent.get('entry_price', 0.0)):.2%} / {float(intent.get('side_probability', 0.0)):.2%}",
                "",
            ]
        )
    lines.extend(
        [
            "## Settled Intents",
            "",
        ]
    )
    settled_intents = report.get("settled_intents", [])
    if not settled_intents:
        lines.append("No settled paper intents.")
    for idx, intent in enumerate(settled_intents[:10], start=1):
        lines.extend(
            [
                f"### {idx}. {intent.get('market_id', '')}",
                "",
                str(intent.get("title", "")),
                "",
                f"- Side: {intent.get('side', '')}",
                f"- Outcome: {intent.get('side_outcome')}",
                f"- PnL: ${float(intent.get('pnl_usd', 0.0)):.2f}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def run_paper_ledger_audit(
    store: PointInTimeStore,
    *,
    config: Optional[KalshiPaperConfig] = None,
    reports_dir: Optional[Path] = None,
) -> KalshiPaperLedgerArtifacts:
    ledger = store.load_kalshi_paper_intents()
    events = store.load_kalshi_paper_events()
    report = build_paper_ledger_report(ledger, events=events, config=config)
    out_dir = reports_dir or (store.research_dir / "reports")
    return write_paper_ledger_report(report, reports_dir=out_dir)


def stable_ledger_report_id(
    ledger: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    config: KalshiPaperConfig,
) -> str:
    return "kalshi-ledger-" + _stable_hash(
        {
            "ledger": list(ledger),
            "events": list(events),
            "config": {"paper": config.__dict__},
        }
    )[:16]


def _status_counts(items: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for item in items:
        status = str(item.get("status", "UNKNOWN"))
        out[status] = out.get(status, 0) + 1
    return dict(sorted(out.items()))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audit the Kalshi research-only paper ledger")
    parser.add_argument("--reports-dir", default=None)
    parser.add_argument("--min-settled-for-review", type=int, default=30)
    parser.add_argument("--max-brier-for-review", type=float, default=0.20)
    parser.add_argument("--min-win-rate-for-review", type=float, default=0.55)
    parser.add_argument("--min-pnl-for-review", type=float, default=0.0)
    parser.add_argument("--stale-open-grace-hours", type=float, default=24.0)
    args = parser.parse_args(argv)

    app_config = load_config()
    store = PointInTimeStore(app_config.global_cfg.data_dir)
    try:
        artifacts = run_paper_ledger_audit(
            store,
            config=KalshiPaperConfig(
                min_settled_for_promotion_review=args.min_settled_for_review,
                max_brier_for_promotion_review=args.max_brier_for_review,
                min_win_rate_for_promotion_review=args.min_win_rate_for_review,
                min_pnl_for_promotion_review=args.min_pnl_for_review,
                stale_open_grace_hours=args.stale_open_grace_hours,
            ),
            reports_dir=Path(args.reports_dir) if args.reports_dir else None,
        )
    finally:
        store.close()

    print(
        json.dumps(
            {
                "run_id": artifacts.report["run_id"],
                "ledger_count": artifacts.report["ledger"]["count"],
                "stale_open": artifacts.report["ledger"]["stale_open_count"],
                "events": artifacts.report["events"]["count"],
                "readiness": artifacts.report["promotion_readiness"]["status"],
                "json_path": str(artifacts.json_path),
                "markdown_path": str(artifacts.markdown_path),
                "research_only": True,
                "execution_enabled": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI smoke path
    raise SystemExit(main())
