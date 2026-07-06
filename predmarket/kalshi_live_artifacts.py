"""Writers for live Kalshi operational audit artifacts."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CSV_FIELDS = [
    "contract_ticker",
    "side",
    "family_id",
    "model_id",
    "signal_key",
    "cluster_key",
    "calibrated_probability",
    "all_in_cost",
    "expected_value_per_contract",
    "current_ask_price",
    "limit_price",
    "modeled_limit_price",
    "execution_strategy",
    "fee_mode",
    "taker_fee_estimate",
    "maker_fee_estimate",
    "maker_fee_savings",
    "time_in_force",
    "post_only",
    "order_expiration_time",
    "order_count",
    "live_stake",
    "live_eligible",
    "client_order_id",
    "blocker_list",
]


def write_live_report(
    report: Mapping[str, Any],
    *,
    out_dir: Path,
    macro_dir: Path,
    stem: str,
    title: str,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    macro_dir.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_live_markdown(report, title=title)
    paths = {
        "json_path": out_dir / f"{stem}.json",
        "markdown_path": out_dir / f"{stem}.md",
        "csv_path": out_dir / f"{stem}.csv",
        "latest_json_path": macro_dir / f"latest-{stem}.json",
        "latest_markdown_path": macro_dir / f"latest-{stem}.md",
        "latest_csv_path": macro_dir / f"latest-{stem}.csv",
    }
    paths["json_path"].write_text(json_text, encoding="utf-8")
    paths["markdown_path"].write_text(markdown, encoding="utf-8")
    write_decision_csv(decision_rows(report), paths["csv_path"])
    paths["latest_json_path"].write_text(json_text, encoding="utf-8")
    paths["latest_markdown_path"].write_text(markdown, encoding="utf-8")
    write_decision_csv(decision_rows(report), paths["latest_csv_path"])
    return {key: str(value) for key, value in paths.items()}


def render_live_markdown(report: Mapping[str, Any], *, title: str) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    risk = report.get("risk_snapshot") if isinstance(report.get("risk_snapshot"), Mapping) else {}
    lines = [
        f"# {title}",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Execution mode: `{report.get('execution_mode')}`",
        f"- Armed: `{report.get('armed')}`",
        f"- Live eligible: `{summary.get('live_eligible_count')}`",
        f"- Blocked: `{summary.get('blocked_decision_count')}`",
        f"- Total live stake: `{summary.get('total_live_stake')}`",
        f"- Maker-first decisions: `{summary.get('maker_first_decision_count')}`",
        f"- Post-only decisions: `{summary.get('post_only_decision_count')}`",
        f"- Open exposure: `{risk.get('open_exposure_usd')}`",
        f"- Kill switches: `{'; '.join(str(item) for item in risk.get('kill_switch_reasons') or []) or 'none'}`",
        "",
        "| Contract | Side | Stake | Eligible | Blockers |",
        "| --- | --- | ---: | --- | --- |",
    ]
    rows = decision_rows(report)
    for row in rows[:50]:
        blockers = "; ".join(str(item) for item in row.get("blocker_list") or [])
        lines.append(
            f"| `{row.get('contract_ticker')}` | `{row.get('side')}` | "
            f"{row.get('live_stake')} | `{row.get('live_eligible')}` | {blockers or 'none'} |"
        )
    if not rows:
        lines.append("|  |  |  |  | No decisions |")
    lines.append("")
    return "\n".join(lines)


def decision_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("decisions") if isinstance(report.get("decisions"), list) else []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def write_decision_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            output = dict(row)
            output["blocker_list"] = "; ".join(str(item) for item in row.get("blocker_list") or [])
            writer.writerow(output)
