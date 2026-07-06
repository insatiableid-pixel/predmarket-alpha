#!/usr/bin/env python3
"""Apply deterministic cluster exposure controls to sports (baseball) proxy candidates.

This is the sports analog of ``scripts/kalshi_crypto_proxy_correlation_cluster_control.py``.
It reuses the FULLY GENERIC cluster-control machinery: the binary-search capping at 35%
max-share, controlled_capacity_rows, and the `(cluster_key, cost, contracts, margin)` tuple
abstraction. The control is family-agnostic given opaque cluster tuples.

Sports-specific differences:
- Input: ``latest-kalshi-sports-proxy-capacity-correlation-decay.json`` capacity_rows.
- Output: ``docs/codex/macro/latest-kalshi-sports-proxy-correlation-cluster-control.*``.
- All controlled rows ``usable=false``.

This is a research-only gate between capacity/depth evidence and any paper probability
overlay. It reports controlled capacity accounting only; it never sizes positions, creates
usable rows, touches account/order paths, or executes.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))


MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_CCD_PATH = MACRO_DIR / "latest-kalshi-sports-proxy-capacity-correlation-decay.json"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-proxy-correlation-cluster-control-latest"
DEFAULT_MAX_CLUSTER_SHARE = 0.35
DEFAULT_MIN_POSITIVE_CLUSTERS = 0

CSV_FIELDS = [
    "contract_ticker",
    "event_ticker",
    "league",
    "series_ticker",
    "close_time",
    "predicted_side",
    "correlation_cluster_key",
    "best_margin_probability",
    "positive_depth_contracts",
    "positive_depth_cost",
    "controlled_depth_contracts",
    "controlled_depth_cost",
    "controlled_cluster_share",
    "gate_status",
    "usable",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_sports_proxy_correlation_cluster_control(
    *,
    ccd_path: Path = DEFAULT_CCD_PATH,
    generated_utc: str | None = None,
    max_cluster_share: float = DEFAULT_MAX_CLUSTER_SHARE,
    min_positive_clusters: int = DEFAULT_MIN_POSITIVE_CLUSTERS,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    ccd = read_json_or_empty(ccd_path)
    ccd_summary = summary(ccd)
    capacity_rows = [dict(row) for row in ccd.get("capacity_rows", []) if isinstance(row, Mapping)]
    positive_rows = [row for row in capacity_rows if positive_depth_cost(row) > 0]
    cluster_costs = positive_cluster_costs(positive_rows)
    required_clusters = required_cluster_count(max_cluster_share, min_positive_clusters)
    controlled_clusters = controlled_cluster_costs(cluster_costs, max_cluster_share)
    controlled_rows = controlled_capacity_rows(positive_rows, controlled_clusters)
    summary_data = build_summary(
        ccd=ccd,
        ccd_summary=ccd_summary,
        capacity_rows=capacity_rows,
        positive_rows=positive_rows,
        cluster_costs=cluster_costs,
        controlled_clusters=controlled_clusters,
        controlled_rows=controlled_rows,
        max_cluster_share=max_cluster_share,
        required_clusters=required_clusters,
    )
    gates = build_gates(summary_data)
    status = report_status(summary_data, gates)
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": False,
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "inputs": {
            "ccd_path": str(ccd_path),
            "ccd_status": ccd.get("status"),
            "max_cluster_share": max_cluster_share,
            "min_positive_clusters": min_positive_clusters,
            "required_positive_clusters": required_clusters,
        },
        "method": {
            "cluster_key": "league|game_winner_ticker|date from the upstream CCD report.",
            "control_rule": (
                "Positive-depth capacity may advance only when the selected clusters can satisfy the "
                "configured maximum share. With a single positive cluster and max share below 1, controlled "
                "capacity is zero."
            ),
            "row_order_rule": "Within each cluster, rows are retained by descending margin, then contract ticker.",
            "boundary": "Controlled depth is capacity accounting for a future paper overlay, not sizing or staking guidance.",
        },
        "summary": summary_data,
        "gates": gates,
        "clusters": cluster_rows(cluster_costs, controlled_clusters),
        "controlled_rows": controlled_rows,
        "next_action": next_action(status),
        "safety": safety_flags(),
    }


def positive_cluster_costs(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    costs: dict[str, float] = defaultdict(float)
    for row in rows:
        key = str(row.get("correlation_cluster_key") or "unknown")
        costs[key] += positive_depth_cost(row)
    return dict(sorted(costs.items(), key=lambda item: (-item[1], item[0])))


def required_cluster_count(max_cluster_share: float, min_positive_clusters: int) -> int:
    if max_cluster_share <= 0:
        return max(1, min_positive_clusters)
    return max(min_positive_clusters, math.ceil(1 / max_cluster_share))


def controlled_capacity_rows(
    rows: Sequence[Mapping[str, Any]],
    controlled_clusters: Mapping[str, float],
) -> list[dict[str, Any]]:
    remaining = dict(controlled_clusters)
    cluster_totals = dict(controlled_clusters)
    output: list[dict[str, Any]] = []
    ordered = sorted(
        rows,
        key=lambda row: (
            str(row.get("correlation_cluster_key") or "unknown"),
            -float(row.get("best_margin_probability") or 0.0),
            str(row.get("contract_ticker") or ""),
        ),
    )
    for row in ordered:
        key = str(row.get("correlation_cluster_key") or "unknown")
        available = remaining.get(key, 0.0)
        source_cost = float(row.get("positive_depth_cost") or 0.0)
        if available <= 1e-9 or source_cost <= 0:
            controlled_cost = 0.0
        else:
            controlled_cost = min(source_cost, available)
            remaining[key] = available - controlled_cost
        source_contracts = float(row.get("positive_depth_contracts") or 0.0)
        ratio = controlled_cost / source_cost if source_cost > 0 else 0.0
        controlled_contracts = source_contracts * ratio
        row_copy = dict(row)
        row_copy["controlled_depth_cost"] = json_float(controlled_cost)
        row_copy["controlled_depth_contracts"] = json_float(controlled_contracts)
        row_copy["controlled_cluster_share"] = None
        row_copy["gate_status"] = "pass" if controlled_cost > 0 else "blocked"
        row_copy["usable"] = False
        row_copy["research_only"] = True
        row_copy["execution_enabled"] = False
        if cluster_totals.get(key) and sum(cluster_totals.values()) > 0:
            row_copy["controlled_cluster_share"] = json_float(
                cluster_totals[key] / sum(cluster_totals.values())
            )
        output.append(row_copy)
    return output


def build_summary(
    *,
    ccd: Mapping[str, Any],
    ccd_summary: Mapping[str, Any],
    capacity_rows: Sequence[Mapping[str, Any]],
    positive_rows: Sequence[Mapping[str, Any]],
    cluster_costs: Mapping[str, float],
    controlled_clusters: Mapping[str, float],
    controlled_rows: Sequence[Mapping[str, Any]],
    max_cluster_share: float,
    required_clusters: int,
) -> dict[str, Any]:
    positive_cluster_count = len([value for value in cluster_costs.values() if value > 0])
    total_positive_cost = sum(cluster_costs.values())
    total_controlled_cost = sum(controlled_clusters.values())
    largest_positive_key, largest_positive_cost = largest_item(cluster_costs)
    largest_controlled_key, largest_controlled_cost = largest_item(controlled_clusters)
    largest_positive_share = (
        largest_positive_cost / total_positive_cost if total_positive_cost > 0 else None
    )
    largest_controlled_share = (
        largest_controlled_cost / total_controlled_cost if total_controlled_cost > 0 else None
    )
    controlled_positive_rows = [
        row for row in controlled_rows if float(row.get("controlled_depth_cost") or 0.0) > 0
    ]
    return {
        "ccd_status": ccd.get("status"),
        "ccd_capacity_status": ccd_summary.get("capacity_status"),
        "ccd_decay_status": ccd_summary.get("decay_status"),
        "capacity_row_count": len(capacity_rows),
        "positive_depth_row_count": len(positive_rows),
        "positive_cluster_count": positive_cluster_count,
        "required_positive_cluster_count": required_clusters,
        "max_cluster_share": max_cluster_share,
        "total_positive_depth_cost": json_float(total_positive_cost),
        "total_controlled_depth_cost": json_float(total_controlled_cost),
        "controlled_positive_row_count": len(controlled_positive_rows),
        "largest_positive_cluster_key": largest_positive_key,
        "largest_positive_cluster_cost": json_float(largest_positive_cost),
        "largest_positive_cluster_share": json_float(largest_positive_share),
        "largest_controlled_cluster_key": largest_controlled_key,
        "largest_controlled_cluster_cost": json_float(largest_controlled_cost),
        "largest_controlled_cluster_share": json_float(largest_controlled_share),
        "cluster_counts": counts(row.get("correlation_cluster_key") for row in positive_rows),
        "league_counts": counts(row.get("league") for row in positive_rows),
        "gate_counts": {},
        "usable_row_count": 0,
    }


def build_gates(summary_data: Mapping[str, Any]) -> list[dict[str, str]]:
    gates = [
        gate(
            "ccd_report_ready",
            "pass" if summary_data.get("ccd_status") else "blocked",
            f"CCD status is {summary_data.get('ccd_status')}.",
        ),
        gate(
            "upstream_capacity_and_decay_pass",
            "pass"
            if (
                summary_data.get("ccd_capacity_status") == "capacity_depth_positive"
                and summary_data.get("ccd_decay_status") == "decay_survival_pass"
            )
            else "blocked",
            (
                f"Capacity status {summary_data.get('ccd_capacity_status')}; "
                f"decay status {summary_data.get('ccd_decay_status')}."
            ),
        ),
        gate(
            "positive_cluster_breadth",
            "pass"
            if int(summary_data.get("positive_cluster_count") or 0)
            >= int(summary_data.get("required_positive_cluster_count") or 0)
            else "blocked",
            (
                f"{summary_data.get('positive_cluster_count')} positive cluster(s); "
                f"requires {summary_data.get('required_positive_cluster_count')}."
            ),
        ),
        gate(
            "controlled_cluster_share_limit",
            "pass"
            if (
                summary_data.get("largest_controlled_cluster_share") is not None
                and float(summary_data.get("largest_controlled_cluster_share") or 0.0)
                <= float(summary_data.get("max_cluster_share") or 0.0)
            )
            else "blocked",
            (
                f"Largest controlled cluster share {summary_data.get('largest_controlled_cluster_share')}; "
                f"max is {summary_data.get('max_cluster_share')}."
            ),
        ),
        gate(
            "no_usable_sizing_or_execution",
            "pass" if int(summary_data.get("usable_row_count") or 0) == 0 else "fail",
            "Cluster-control report remains research-only with zero usable rows and no sizing or execution.",
        ),
    ]
    if isinstance(summary_data, dict):
        summary_data["gate_counts"] = counts(item["status"] for item in gates)
    return gates


def report_status(summary_data: Mapping[str, Any], gates: Sequence[Mapping[str, Any]]) -> str:
    if any(item.get("status") == "fail" for item in gates):
        return "sports_proxy_correlation_cluster_control_failed_safety_gate"
    if gate_status(gates, "ccd_report_ready") != "pass":
        return "sports_proxy_correlation_cluster_control_blocked_missing_ccd"
    if gate_status(gates, "upstream_capacity_and_decay_pass") != "pass":
        return "sports_proxy_correlation_cluster_control_blocked_upstream_ccd"
    if int(summary_data.get("positive_depth_row_count") or 0) <= 0:
        return "sports_proxy_correlation_cluster_control_blocked_no_positive_depth"
    if gate_status(gates, "positive_cluster_breadth") != "pass":
        return "sports_proxy_correlation_cluster_control_blocked_insufficient_clusters"
    if gate_status(gates, "controlled_cluster_share_limit") != "pass":
        return "sports_proxy_correlation_cluster_control_blocked_share_limit"
    return "sports_proxy_correlation_cluster_control_ready_for_paper_overlay"


def next_action(status: str) -> dict[str, str]:
    if status == "sports_proxy_correlation_cluster_control_ready_for_paper_overlay":
        return {
            "name": "kalshi_sports_proxy_paper_probability_overlay",
            "why": "Cluster exposure limits are machine-readable and passing for the current research-only candidate set.",
            "stop_condition": "Stop before real positions, execution, account/order paths, staking, or live edge claims.",
        }
    if status == "sports_proxy_correlation_cluster_control_blocked_insufficient_clusters":
        return {
            "name": "kalshi_sports_proxy_cluster_breadth_accumulation",
            "why": "Positive depth is not spread across enough independent game clusters to satisfy the configured max share.",
            "stop_condition": "Stop before reducing cluster breadth requirements without an explicit policy review.",
        }
    if status == "sports_proxy_correlation_cluster_control_blocked_share_limit":
        return {
            "name": "kalshi_sports_proxy_cluster_cap_refinement",
            "why": "Cluster breadth exists, but the deterministic cap still cannot produce a share-limited candidate set.",
            "stop_condition": "Stop before paper overlay until the controlled share limit is passing.",
        }
    return {
        "name": "kalshi_sports_proxy_correlation_cluster_control_audit",
        "why": "Cluster control is blocked by missing or upstream-invalid CCD evidence.",
        "stop_condition": "Stop before paper overlay, sizing, execution, or account/order paths.",
    }


def write_sports_proxy_correlation_cluster_control(
    report: Mapping[str, Any],
    out_dir: Path = DEFAULT_OUT_DIR,
    *,
    latest_dir: Path | None = None,
    write_latest: bool | None = None,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-proxy-correlation-cluster-control.json"
    markdown_path = out_dir / "kalshi-sports-proxy-correlation-cluster-control.md"
    csv_path = out_dir / "kalshi-sports-proxy-correlation-cluster-control.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report, csv_path)
    paths = {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "csv_path": str(csv_path),
    }
    target_latest_dir = latest_dir or MACRO_DIR
    should_write_latest = (
        path_is_within(out_dir, MACRO_DIR) if write_latest is None else write_latest
    )
    if should_write_latest:
        target_latest_dir.mkdir(parents=True, exist_ok=True)
        latest_json = (
            target_latest_dir / "latest-kalshi-sports-proxy-correlation-cluster-control.json"
        )
        latest_md = target_latest_dir / "latest-kalshi-sports-proxy-correlation-cluster-control.md"
        latest_csv = (
            target_latest_dir / "latest-kalshi-sports-proxy-correlation-cluster-control.csv"
        )
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        write_csv(report, latest_csv)
        paths["latest_json_path"] = str(latest_json)
        paths["latest_markdown_path"] = str(latest_md)
        paths["latest_csv_path"] = str(latest_csv)
    return paths


def render_markdown(report: Mapping[str, Any]) -> str:
    data = summary(report)
    lines = [
        "# Kalshi Sports Proxy Correlation Cluster Control",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Positive clusters: `{data.get('positive_cluster_count')}`",
        f"- Required positive clusters: `{data.get('required_positive_cluster_count')}`",
        f"- Total positive-depth cost: `{data.get('total_positive_depth_cost')}`",
        f"- Total controlled-depth cost: `{data.get('total_controlled_depth_cost')}`",
        f"- Largest positive cluster share: `{data.get('largest_positive_cluster_share')}`",
        f"- Largest controlled cluster share: `{data.get('largest_controlled_cluster_share')}`",
        f"- Usable rows: `{data.get('usable_row_count')}`",
        "",
        "## Gates",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for item in report.get("gates", []):
        if isinstance(item, Mapping):
            lines.append(
                f"| `{item.get('name')}` | `{item.get('status')}` | {item.get('reason')} |"
            )
    next_step = report.get("next_action") if isinstance(report.get("next_action"), Mapping) else {}
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            f"- Name: `{next_step.get('name')}`",
            f"- Why: {next_step.get('why')}",
            f"- Stop condition: {next_step.get('stop_condition')}",
            "",
            "## Guardrail",
            "",
            "This report is not a betting recommendation and never authorizes sizing or execution.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(report: Mapping[str, Any], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in report.get("controlled_rows", []):
            if isinstance(row, Mapping):
                writer.writerow({field: row.get(field) for field in CSV_FIELDS})


def cluster_rows(
    cluster_costs: Mapping[str, float], controlled_clusters: Mapping[str, float]
) -> list[dict[str, Any]]:
    total_positive = sum(cluster_costs.values())
    total_controlled = sum(controlled_clusters.values())
    keys = sorted(set(cluster_costs) | set(controlled_clusters))
    return [
        {
            "correlation_cluster_key": key,
            "positive_depth_cost": json_float(cluster_costs.get(key, 0.0)),
            "positive_cluster_share": json_float(
                cluster_costs.get(key, 0.0) / total_positive if total_positive > 0 else None
            ),
            "controlled_depth_cost": json_float(controlled_clusters.get(key, 0.0)),
            "controlled_cluster_share": json_float(
                controlled_clusters.get(key, 0.0) / total_controlled
                if total_controlled > 0
                else None
            ),
        }
        for key in keys
    ]


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def gate_status(gates: Sequence[Mapping[str, Any]], name: str) -> str:
    for item in gates:
        if item.get("name") == name:
            return str(item.get("status") or "")
    return "blocked"


def largest_item(values: Mapping[str, float]) -> tuple[str | None, float]:
    if not values:
        return None, 0.0
    return max(values.items(), key=lambda item: (item[1], item[0]))


def positive_depth_cost(row: Mapping[str, Any]) -> float:
    return nonnegative_float(row.get("positive_depth_cost")) or 0.0


def read_json_or_empty(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def summary(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping) and isinstance(value.get("summary"), Mapping):
        return dict(value["summary"])
    return {}


from predmarket.shared_helpers import controlled_cluster_costs, path_is_within  # noqa: E402


def nonnegative_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip().rstrip("%")
            if not value:
                return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def json_float(value: Any) -> float | None:
    number = nonnegative_float(value)
    return round(number, 10) if number is not None else None


def counts(values: Sequence[Any]) -> dict[str, int]:
    counter = Counter(str(value if value is not None else "unknown") for value in values)
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def safety_flags() -> dict[str, bool]:
    return {
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": False,
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "raw_payloads_copied_to_repo": False,
        "staking_or_sizing_guidance": False,
    }


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
    report = build_sports_proxy_correlation_cluster_control(
        ccd_path=args.ccd_path,
        max_cluster_share=args.max_cluster_share,
        min_positive_clusters=args.min_positive_clusters,
    )
    if args.write:
        paths = write_sports_proxy_correlation_cluster_control(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], "paths": paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
