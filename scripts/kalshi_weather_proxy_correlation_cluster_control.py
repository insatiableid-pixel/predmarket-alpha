#!/usr/bin/env python3
"""Apply deterministic cluster exposure controls to weather proxy candidates via the engine.

This is the weather analog of ``scripts/kalshi_sports_proxy_correlation_cluster_control.py``.
It reuses the engine's FULLY GENERIC ``controlled_capacity_rows`` and
``controlled_cluster_costs`` from shared_helpers — the control is family-agnostic given
opaque cluster tuples. Proves the spine is closed for modification (zero spine edits).

Weather-specific differences:
- Input: ``latest-kalshi-weather-proxy-capacity-correlation-decay.json`` capacity_rows.
- Output: ``docs/codex/macro/latest-kalshi-weather-proxy-correlation-cluster-control.*``.
- All controlled rows ``usable=false``.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.engine import controlled_capacity_rows  # noqa: E402
from predmarket.shared_helpers import (  # noqa: E402
    controlled_cluster_costs,
    counts,
    gate,
    json_float,
    nonnegative_float,
    path_is_within,
    read_json_or_empty,
    required_cluster_count,
    safety_flags,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_CCD_PATH = MACRO_DIR / "latest-kalshi-weather-proxy-capacity-correlation-decay.json"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-weather-proxy-correlation-cluster-control-latest"
DEFAULT_MAX_CLUSTER_SHARE = 0.35
DEFAULT_MIN_POSITIVE_CLUSTERS = 0

STATUS_PREFIX = "weather_proxy"

CSV_FIELDS = [
    "contract_ticker",
    "event_ticker",
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


def build_weather_proxy_correlation_cluster_control(
    *,
    ccd_path: Path = DEFAULT_CCD_PATH,
    generated_utc: str | None = None,
    max_cluster_share: float = DEFAULT_MAX_CLUSTER_SHARE,
    min_positive_clusters: int = DEFAULT_MIN_POSITIVE_CLUSTERS,
) -> dict[str, Any]:
    """Build the weather proxy cluster control report.

    Uses the engine's fully generic ``controlled_capacity_rows`` for the 35%
    max-share cap — the control is family-agnostic given opaque cluster tuples.

    Args:
        ccd_path: Path to the latest CCD report.
        generated_utc: Override timestamp (ISO format).
        max_cluster_share: Max share per correlation cluster (default 0.35 = 35%).
        min_positive_clusters: Minimum number of positive clusters required.

    Returns:
        The cluster control report dict.
    """
    generated = generated_utc or utc_now()
    ccd = read_json_or_empty(ccd_path)
    ccd_summary = _summary(ccd)

    # Extract capacity rows from CCD report
    capacity_rows = [dict(row) for row in ccd.get("capacity_rows", []) if isinstance(row, Mapping)]
    positive_rows = [row for row in capacity_rows if _positive_depth_cost(row) > 0]

    # Compute cluster costs
    cluster_costs = _positive_cluster_costs(positive_rows)
    req_clusters = required_cluster_count(max_cluster_share, min_positive_clusters)

    # Apply cluster control via shared helper
    controlled_clusters = controlled_cluster_costs(cluster_costs, max_cluster_share)

    # Apply controlled allocation via engine's fully generic function
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
        required_clusters=req_clusters,
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
            "required_positive_clusters": req_clusters,
        },
        "method": {
            "engine_stage": "controlled_capacity_rows + controlled_cluster_costs from predmarket.engine/shared_helpers",
            "cluster_key": "station|bracket|date via weather_cluster_key_composer (from upstream CCD).",
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
        "clusters": _cluster_rows(cluster_costs, controlled_clusters),
        "controlled_rows": controlled_rows,
        "next_action": _next_action(status),
        "safety": safety_flags(),
    }


def _positive_cluster_costs(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    costs: dict[str, float] = defaultdict(float)
    for row in rows:
        key = str(row.get("correlation_cluster_key") or "unknown")
        costs[key] += _positive_depth_cost(row)
    return dict(sorted(costs.items(), key=lambda item: (-item[1], item[0])))


def _positive_depth_cost(row: Mapping[str, Any]) -> float:
    return nonnegative_float(row.get("positive_depth_cost")) or 0.0


# ---------------------------------------------------------------------------
# Summary, gates, status
# ---------------------------------------------------------------------------


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
    largest_positive_key, largest_positive_cost = _largest_item(cluster_costs)
    largest_controlled_key, largest_controlled_cost = _largest_item(controlled_clusters)
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
        "weather_family_counts": counts(
            row.get("weather_family", row.get("series_ticker")) for row in positive_rows
        ),
        "gate_counts": {},
        "usable_row_count": 0,
    }


def build_gates(summary_data: Mapping[str, Any]) -> list[dict[str, str]]:
    gates_ = [
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
        summary_data["gate_counts"] = counts(item["status"] for item in gates_)
    return gates_


def report_status(summary_data: Mapping[str, Any], gates: Sequence[Mapping[str, Any]]) -> str:
    prefix = STATUS_PREFIX
    if any(item.get("status") == "fail" for item in gates):
        return f"{prefix}_correlation_cluster_control_failed_safety_gate"
    if _gate_status(gates, "ccd_report_ready") != "pass":
        return f"{prefix}_correlation_cluster_control_blocked_missing_ccd"
    if _gate_status(gates, "upstream_capacity_and_decay_pass") != "pass":
        return f"{prefix}_correlation_cluster_control_blocked_upstream_ccd"
    if int(summary_data.get("positive_depth_row_count") or 0) <= 0:
        return f"{prefix}_correlation_cluster_control_blocked_no_positive_depth"
    if _gate_status(gates, "positive_cluster_breadth") != "pass":
        return f"{prefix}_correlation_cluster_control_blocked_insufficient_clusters"
    if _gate_status(gates, "controlled_cluster_share_limit") != "pass":
        return f"{prefix}_correlation_cluster_control_blocked_share_limit"
    return f"{prefix}_correlation_cluster_control_ready_for_paper_overlay"


def _next_action(status: str) -> dict[str, str]:
    prefix = STATUS_PREFIX
    if status == f"{prefix}_correlation_cluster_control_ready_for_paper_overlay":
        return {
            "name": "kalshi_weather_proxy_paper_probability_overlay",
            "why": "Cluster exposure limits are machine-readable and passing for the current research-only candidate set.",
            "stop_condition": "Stop before real positions, execution, account/order paths, staking, or live edge claims.",
        }
    if status == f"{prefix}_correlation_cluster_control_blocked_insufficient_clusters":
        return {
            "name": "kalshi_weather_proxy_cluster_breadth_accumulation",
            "why": "Positive depth is not spread across enough independent station/bracket clusters to satisfy the configured max share.",
            "stop_condition": "Stop before reducing cluster breadth requirements without an explicit policy review.",
        }
    if status == f"{prefix}_correlation_cluster_control_blocked_share_limit":
        return {
            "name": "kalshi_weather_proxy_cluster_cap_refinement",
            "why": "Cluster breadth exists, but the deterministic cap still cannot produce a share-limited candidate set.",
            "stop_condition": "Stop before paper overlay until the controlled share limit is passing.",
        }
    return {
        "name": "kalshi_weather_proxy_correlation_cluster_control_audit",
        "why": "Cluster control is blocked by missing or upstream-invalid CCD evidence.",
        "stop_condition": "Stop before paper overlay, sizing, execution, or account/order paths.",
    }


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def write_weather_proxy_correlation_cluster_control(
    report: Mapping[str, Any],
    out_dir: Path = DEFAULT_OUT_DIR,
    *,
    latest_dir: Path | None = None,
    write_latest: bool | None = None,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-weather-proxy-correlation-cluster-control.json"
    markdown_path = out_dir / "kalshi-weather-proxy-correlation-cluster-control.md"
    csv_path = out_dir / "kalshi-weather-proxy-correlation-cluster-control.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    _write_csv(report, csv_path)
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
            target_latest_dir / "latest-kalshi-weather-proxy-correlation-cluster-control.json"
        )
        latest_md = (
            target_latest_dir / "latest-kalshi-weather-proxy-correlation-cluster-control.md"
        )
        latest_csv = (
            target_latest_dir / "latest-kalshi-weather-proxy-correlation-cluster-control.csv"
        )
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(_render_markdown(report), encoding="utf-8")
        _write_csv(report, latest_csv)
        paths["latest_json_path"] = str(latest_json)
        paths["latest_markdown_path"] = str(latest_md)
        paths["latest_csv_path"] = str(latest_csv)
    return paths


def _render_markdown(report: Mapping[str, Any]) -> str:
    data = _summary(report)
    lines = [
        "# Kalshi Weather Proxy Correlation Cluster Control",
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


def _write_csv(report: Mapping[str, Any], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in report.get("controlled_rows", []):
            if isinstance(row, Mapping):
                writer.writerow({field: row.get(field) for field in CSV_FIELDS})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cluster_rows(
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


def _largest_item(values: Mapping[str, float]) -> tuple[str | None, float]:
    if not values:
        return None, 0.0
    return max(values.items(), key=lambda item: (item[1], item[0]))


def _summary(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping) and isinstance(value.get("summary"), Mapping):
        return dict(value["summary"])
    return {}


def _gate_status(gates: Sequence[Mapping[str, Any]], name: str) -> str:
    for item in gates:
        if item.get("name") == name:
            return str(item.get("status") or "")
    return "blocked"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


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
    report = build_weather_proxy_correlation_cluster_control(
        ccd_path=args.ccd_path,
        max_cluster_share=args.max_cluster_share,
        min_positive_clusters=args.min_positive_clusters,
    )
    if args.write:
        paths = write_weather_proxy_correlation_cluster_control(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], "paths": paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
