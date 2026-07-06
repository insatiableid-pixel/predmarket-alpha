"""Review-only threshold sensitivity for Type 2 paper matcher outputs."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_THRESHOLDS = (0.10, 0.075, 0.05, 0.025, 0.02, 0.015, 0.01, 0.005, 0.0)


@dataclass(frozen=True)
class Type2ThresholdSensitivityArtifacts:
    report: dict[str, Any]
    json_path: Path
    markdown_path: Path


def build_type2_threshold_sensitivity(
    paper_report: Mapping[str, Any],
    disposition_report: Mapping[str, Any] | None = None,
    *,
    paper_matcher_path: Path | None = None,
    disposition_path: Path | None = None,
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
    run_id: str | None = None,
    created_ts: float | None = None,
) -> dict[str, Any]:
    ts = float(created_ts or time.time())
    candidates = [
        _candidate_row(row, idx)
        for idx, row in enumerate(_rows(paper_report, "candidates"), start=1)
    ]
    disposition_by_ticker = _disposition_by_ticker(disposition_report or {})
    enriched = [_with_disposition(row, disposition_by_ticker) for row in candidates]
    timing_clean = [
        row
        for row in enriched
        if row["timing_status"] in {"timing_clean_watch", "timing_clean_review"}
    ]
    positive = [row for row in timing_clean if row["review_only_net_divergence"] > 0.0]
    sorted_positive = sorted(
        positive, key=lambda row: row["review_only_net_divergence"], reverse=True
    )
    current_threshold = _current_threshold(paper_report)
    max_net = sorted_positive[0]["review_only_net_divergence"] if sorted_positive else 0.0
    gap_to_current = max(0.0, current_threshold - max_net)
    threshold_rows = [
        _threshold_row(threshold, timing_clean)
        for threshold in sorted(
            {_finite_float(value) for value in thresholds if _finite_float(value) is not None},
            reverse=True,
        )
    ]
    status = (
        "threshold_sensitivity_current_threshold_has_candidates"
        if any(
            row["threshold"] == current_threshold and row["would_pass_count"] > 0
            for row in threshold_rows
        )
        else "threshold_sensitivity_no_current_threshold_candidates"
    )
    report = {
        "schema_version": 1,
        "run_id": run_id or f"type2-threshold-sensitivity-{int(ts)}",
        "created_ts": ts,
        "created_at_utc": datetime.fromtimestamp(ts, UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "safety": {
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "account_or_order_paths": False,
            "raw_provider_payload_copied": False,
        },
        "inputs": {
            "paper_matcher_json": str(paper_matcher_path) if paper_matcher_path else None,
            "disposition_json": str(disposition_path) if disposition_path else None,
            "paper_matcher_status": paper_report.get("status"),
            "disposition_status": (disposition_report or {}).get("status"),
        },
        "policy": {
            "current_threshold_preserved": True,
            "thresholds_are_hypothetical": True,
            "does_not_promote_candidates": True,
            "provider_calls_allowed": False,
        },
        "summary": {
            "candidate_count": len(enriched),
            "timing_clean_candidate_count": len(timing_clean),
            "positive_net_candidate_count": len(positive),
            "current_threshold": current_threshold,
            "max_positive_review_only_net_divergence": max_net,
            "gap_to_current_threshold": gap_to_current,
            "current_threshold_would_pass_count": sum(
                1 for row in timing_clean if row["review_only_net_divergence"] >= current_threshold
            ),
            "minimum_hypothetical_threshold_for_one_candidate": max_net if max_net > 0.0 else None,
            "temporal_downgrade_count": sum(
                1 for row in enriched if row["timing_status"] == "temporal_downgrade"
            ),
            "manual_timing_unknown_count": sum(
                1 for row in enriched if row["timing_status"] == "manual_timing_unknown"
            ),
        },
        "threshold_grid": threshold_rows,
        "top_candidates": sorted_positive[:10],
    }
    return report


def run_type2_threshold_sensitivity(
    *,
    paper_matcher_json: Path,
    disposition_json: Path | None = None,
    output_dir: Path,
    run_id: str | None = None,
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> Type2ThresholdSensitivityArtifacts:
    paper_report = _read_json(paper_matcher_json)
    disposition_report = _read_json(disposition_json) if disposition_json else None
    report = build_type2_threshold_sensitivity(
        paper_report,
        disposition_report,
        paper_matcher_path=paper_matcher_json,
        disposition_path=disposition_json,
        thresholds=thresholds,
        run_id=run_id,
    )
    return write_type2_threshold_sensitivity(report, output_dir=output_dir)


def write_type2_threshold_sensitivity(
    report: Mapping[str, Any],
    *,
    output_dir: Path,
) -> Type2ThresholdSensitivityArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(report.get("run_id") or f"type2-threshold-sensitivity-{int(time.time())}")
    json_path = output_dir / f"{run_id}.json"
    markdown_path = output_dir / f"{run_id}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_type2_threshold_sensitivity_markdown(report), encoding="utf-8")
    return Type2ThresholdSensitivityArtifacts(dict(report), json_path, markdown_path)


def render_type2_threshold_sensitivity_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        f"# Type 2 Threshold Sensitivity: {report.get('run_id', '')}",
        "",
        "## Scope",
        "",
        "- Mode: review-only",
        "- Research only: true",
        "- Execution enabled: false",
        f"- Status: `{report.get('status', '')}`",
        "- Threshold rows are hypothetical diagnostics only.",
        "",
        "## Summary",
        "",
        f"- Candidates: {summary.get('candidate_count', 0)}",
        f"- Timing-clean candidates: {summary.get('timing_clean_candidate_count', 0)}",
        f"- Positive net candidates: {summary.get('positive_net_candidate_count', 0)}",
        f"- Current threshold: {_fmt(summary.get('current_threshold'))}",
        f"- Max positive review-only net divergence: {_fmt(summary.get('max_positive_review_only_net_divergence'))}",
        f"- Gap to current threshold: {_fmt(summary.get('gap_to_current_threshold'))}",
        f"- Current-threshold candidate count: {summary.get('current_threshold_would_pass_count', 0)}",
        "",
        "## Threshold Grid",
        "",
        "| Hypothetical threshold | Would pass | Max net |",
        "| --- | ---: | ---: |",
    ]
    for row in report.get("threshold_grid", []):
        lines.append(
            f"| {_fmt(row.get('threshold'))} | {row.get('would_pass_count', 0)} | {_fmt(row.get('max_net_divergence'))} |"
        )
    lines.extend(["", "## Top Timing-Clean Candidates", ""])
    top = list(report.get("top_candidates", []))
    if not top:
        lines.append("No timing-clean positive-net candidates were found.")
    for idx, row in enumerate(top, start=1):
        lines.extend(
            [
                f"### {idx}. {row.get('kalshi_ticker', '')}",
                "",
                str(row.get("title") or ""),
                "",
                f"- Timing status: `{row.get('timing_status', '')}`",
                f"- Review-only net divergence: {_fmt(row.get('review_only_net_divergence'))}",
                f"- Raw divergence: {_fmt(row.get('raw_divergence'))}",
                f"- Kalshi midpoint: {_fmt(row.get('kalshi_midpoint'))}",
                f"- Sportsbook no-vig midpoint: {_fmt(row.get('sportsbook_no_vig_yes'))}",
                "",
            ]
        )
    lines.extend(
        [
            "## Guardrail",
            "",
            "This report does not change thresholds, promote candidates, authorize execution, or make a profitability claim.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _candidate_row(row: Mapping[str, Any], index: int) -> dict[str, Any]:
    return {
        "rank": index,
        "reference_id": row.get("reference_id"),
        "kalshi_ticker": row.get("kalshi_ticker"),
        "event_ticker": row.get("event_ticker"),
        "title": row.get("title"),
        "review_status": row.get("review_status"),
        "kalshi_midpoint": _float_or_zero(row.get("kalshi_midpoint")),
        "sportsbook_no_vig_yes": _float_or_zero(row.get("sportsbook_no_vig_yes")),
        "raw_divergence": _float_or_zero(row.get("raw_divergence")),
        "review_only_net_divergence": _float_or_zero(row.get("review_only_net_divergence")),
        "threshold": _float_or_zero(row.get("threshold")),
        "blockers": list(row.get("blockers", []))
        if isinstance(row.get("blockers", []), list)
        else [],
    }


def _with_disposition(
    row: Mapping[str, Any], disposition_by_ticker: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    out = dict(row)
    disposition = disposition_by_ticker.get(str(row.get("kalshi_ticker") or ""))
    status = str((disposition or {}).get("disposition") or "")
    if status == "KEPT_REVIEW_CANDIDATE":
        timing_status = "timing_clean_review"
    elif status == "WATCH_ONLY":
        timing_status = "timing_clean_watch"
    elif status == "DOWNGRADED_TEMPORAL_MISMATCH":
        timing_status = "temporal_downgrade"
    elif status:
        timing_status = "manual_timing_unknown"
    else:
        timing_status = "not_dispositioned"
    out["timing_status"] = timing_status
    out["disposition"] = status or None
    return out


def _threshold_row(threshold: float, candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    passing = [
        row
        for row in candidates
        if float(row.get("review_only_net_divergence") or 0.0) >= threshold
    ]
    max_net = max(
        (float(row.get("review_only_net_divergence") or 0.0) for row in candidates), default=0.0
    )
    return {
        "threshold": float(threshold),
        "would_pass_count": len(passing),
        "max_net_divergence": max_net,
        "tickers": [str(row.get("kalshi_ticker") or "") for row in passing[:10]],
    }


def _current_threshold(report: Mapping[str, Any]) -> float:
    config = report.get("config") if isinstance(report.get("config"), Mapping) else {}
    threshold = _finite_float(config.get("min_net_divergence"))
    if threshold is not None:
        return threshold
    candidate_thresholds = [
        _finite_float(row.get("threshold"))
        for row in _rows(report, "candidates")
        if _finite_float(row.get("threshold")) is not None
    ]
    return candidate_thresholds[0] if candidate_thresholds else 0.10


def _disposition_by_ticker(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for row in _rows(report, "dispositions"):
        ticker = str(row.get("kalshi_ticker") or "")
        if ticker:
            out[ticker] = row
    return out


def _rows(report: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    rows = report.get(key)
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, Mapping)]
    return []


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _float_or_zero(value: Any) -> float:
    number = _finite_float(value)
    return number if number is not None else 0.0


def _fmt(value: Any) -> str:
    number = _finite_float(value)
    if number is None:
        return ""
    return f"{number:.4f}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write a review-only Type 2 threshold sensitivity report."
    )
    parser.add_argument("--paper-matcher-json", required=True)
    parser.add_argument("--disposition-json")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", default="type2-threshold-sensitivity-latest")
    parser.add_argument(
        "--thresholds", default=",".join(str(value) for value in DEFAULT_THRESHOLDS)
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    thresholds = [
        value
        for value in (_finite_float(part.strip()) for part in str(args.thresholds).split(","))
        if value is not None
    ]
    artifacts = run_type2_threshold_sensitivity(
        paper_matcher_json=Path(args.paper_matcher_json),
        disposition_json=Path(args.disposition_json) if args.disposition_json else None,
        output_dir=Path(args.output_dir),
        run_id=args.run_id,
        thresholds=thresholds or DEFAULT_THRESHOLDS,
    )
    print(
        json.dumps(
            {
                "status": artifacts.report.get("status"),
                "research_only": True,
                "execution_enabled": False,
                "json_path": str(artifacts.json_path),
                "markdown_path": str(artifacts.markdown_path),
                "summary": artifacts.report.get("summary", {}),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
