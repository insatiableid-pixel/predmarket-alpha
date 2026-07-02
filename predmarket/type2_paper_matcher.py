"""Paper-only Type 2 Kalshi-vs-sportsbook matcher.

The matcher consumes local artifacts only. It compares explicitly mapped Kalshi
tickers to manually supplied sportsbook reference prices and emits review
signals, not orders, stakes, or execution instructions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from predmarket.feature_flags import FeatureFlag, is_enabled


@dataclass(frozen=True)
class Type2PaperMatcherArtifacts:
    report: Dict[str, Any]
    json_path: Path
    markdown_path: Path


def implied_probability_from_odds(price: Any) -> float:
    """Convert an American, decimal, or direct probability payload to implied probability."""
    if isinstance(price, Mapping):
        for key in ("implied_probability", "probability", "prob", "p"):
            if key in price:
                value = _optional_float(price.get(key))
                if value is not None and 0.0 < value < 1.0:
                    return value
        for key in ("american", "american_odds"):
            if key in price:
                value = _optional_float(price.get(key))
                if value is None or value == 0:
                    raise ValueError("American odds must be non-zero")
                if value > 0:
                    return 100.0 / (value + 100.0)
                return abs(value) / (abs(value) + 100.0)
        for key in ("decimal", "decimal_odds"):
            if key in price:
                value = _optional_float(price.get(key))
                if value is None or value <= 1.0:
                    raise ValueError("Decimal odds must be greater than 1")
                return 1.0 / value
    value = _optional_float(price)
    if value is not None and 0.0 < value < 1.0:
        return value
    raise ValueError("Unsupported odds payload")


def no_vig_midpoint_from_reference(reference: Mapping[str, Any]) -> Dict[str, float]:
    """Return no-vig YES/NO midpoint probabilities from a two-outcome reference."""
    yes_payload = _side_payload(reference, "yes")
    no_payload = _side_payload(reference, "no")
    raw_yes = implied_probability_from_odds(yes_payload)
    raw_no = implied_probability_from_odds(no_payload)
    overround = raw_yes + raw_no - 1.0
    mid_yes = raw_yes - (overround / 2.0)
    mid_no = raw_no - (overround / 2.0)
    if not (math.isfinite(mid_yes) and math.isfinite(mid_no)):
        raise ValueError("No-vig midpoint is not finite")
    if mid_yes <= 0.0 or mid_yes >= 1.0 or mid_no <= 0.0 or mid_no >= 1.0:
        raise ValueError("No-vig midpoint must be inside (0, 1)")
    return {
        "raw_yes_implied": raw_yes,
        "raw_no_implied": raw_no,
        "overround": overround,
        "no_vig_yes": mid_yes,
        "no_vig_no": mid_no,
    }


def build_type2_paper_match_report(
    kalshi_payload: Mapping[str, Any],
    sportsbook_payload: Optional[Mapping[str, Any]],
    *,
    kalshi_path: Optional[Path] = None,
    sportsbook_path: Optional[Path] = None,
    run_id: Optional[str] = None,
    min_net_divergence: float = 0.10,
    uncertainty_buffer: float = 0.0,
    created_ts: Optional[float] = None,
) -> Dict[str, Any]:
    ts = float(created_ts or time.time())
    rows = _kalshi_rows(kalshi_payload)
    row_by_ticker = _index_kalshi_rows(rows)
    references = _sportsbook_references(sportsbook_payload)
    candidates: List[Dict[str, Any]] = []
    blockers: List[Dict[str, Any]] = []

    if sportsbook_payload is None:
        blockers.append(
            {
                "reason": "missing_sportsbook_reference",
                "detail": "Provide a local sportsbook reference JSON with explicit kalshi_ticker mappings.",
            }
        )

    for reference in references:
        candidate, candidate_blockers = _candidate_from_reference(
            reference,
            row_by_ticker=row_by_ticker,
            min_net_divergence=min_net_divergence,
            uncertainty_buffer=uncertainty_buffer,
        )
        if candidate is not None:
            candidates.append(candidate)
        blockers.extend(candidate_blockers)

    counts = _status_counts(candidates)
    report_status = _report_status(candidates, blockers, sportsbook_payload)

    # Feature flag: real-time enhanced matching with tighter divergence thresholds.
    # When enabled, run a secondary pass at half the divergence threshold to catch
    # smaller mispricings that would be filtered in the standard batch pass.
    real_time_enabled = is_enabled(FeatureFlag.TYPE2_REAL_TIME_MATCHER)
    enhanced_candidates: List[Dict[str, Any]] = []
    if real_time_enabled and references:
        enhanced_threshold = min_net_divergence / 2.0
        for reference in references:
            candidate, _ = _candidate_from_reference(
                reference,
                row_by_ticker=row_by_ticker,
                min_net_divergence=enhanced_threshold,
                uncertainty_buffer=uncertainty_buffer,
            )
            if candidate is not None and candidate not in candidates:
                candidate["matching_mode"] = "enhanced_real_time"
                enhanced_candidates.append(candidate)

    report = {
        "schema_version": 1,
        "run_id": run_id
        or _stable_run_id(
            kalshi_payload,
            sportsbook_payload or {},
            min_net_divergence=min_net_divergence,
            uncertainty_buffer=uncertainty_buffer,
        ),
        "created_ts": ts,
        "created_at_utc": datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": report_status,
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
            "kalshi_json": str(kalshi_path) if kalshi_path else None,
            "sportsbook_json": str(sportsbook_path) if sportsbook_path else None,
            "kalshi_rows": len(rows),
            "sportsbook_references": len(references),
        },
        "config": {
            "min_net_divergence": float(min_net_divergence),
            "uncertainty_buffer": float(uncertainty_buffer),
            "matching_policy": "explicit_kalshi_ticker_only",
            "no_vig_method": "two_outcome_symmetric_overround_removal",
            "real_time_matcher_enabled": real_time_enabled,
        },
        "summary": {
            "candidate_count": len(candidates),
            "enhanced_candidate_count": len(enhanced_candidates),
            "review_only_pass": counts.get("REVIEW_ONLY_PASS", 0),
            "review_only_watch": counts.get("REVIEW_ONLY_WATCH", 0),
            "review_only_blocked": counts.get("REVIEW_ONLY_BLOCKED", 0),
            "blocker_count": len(blockers),
        },
        "candidates": candidates,
        "enhanced_candidates": enhanced_candidates,
        "blockers": blockers,
    }
    return report


def run_type2_paper_matcher(
    *,
    kalshi_json: Path,
    sportsbook_json: Optional[Path] = None,
    output_dir: Path,
    run_id: Optional[str] = None,
    min_net_divergence: float = 0.10,
    uncertainty_buffer: float = 0.0,
) -> Type2PaperMatcherArtifacts:
    kalshi_payload = _read_json(kalshi_json)
    sportsbook_payload = _read_json(sportsbook_json) if sportsbook_json else None
    report = build_type2_paper_match_report(
        kalshi_payload,
        sportsbook_payload,
        kalshi_path=kalshi_json,
        sportsbook_path=sportsbook_json,
        run_id=run_id,
        min_net_divergence=min_net_divergence,
        uncertainty_buffer=uncertainty_buffer,
    )
    return write_type2_paper_match_report(report, output_dir=output_dir)


def write_type2_paper_match_report(
    report: Mapping[str, Any],
    *,
    output_dir: Path,
) -> Type2PaperMatcherArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(report.get("run_id") or f"type2-paper-matcher-{int(time.time())}")
    json_path = output_dir / f"{run_id}.json"
    markdown_path = output_dir / f"{run_id}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_type2_paper_match_markdown(report), encoding="utf-8")
    return Type2PaperMatcherArtifacts(dict(report), json_path, markdown_path)


def render_type2_paper_match_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# Type 2 Paper Matcher: {report.get('run_id', '')}",
        "",
        "## Scope",
        "",
        "- Mode: review-only",
        "- Research only: true",
        "- Execution enabled: false",
        f"- Status: `{report.get('status', '')}`",
        f"- Matching policy: `{report.get('config', {}).get('matching_policy', '')}`",
        "",
        "## Summary",
        "",
        f"- Candidates: {summary.get('candidate_count', 0)}",
        f"- Review pass/watch/blocked: {summary.get('review_only_pass', 0)} / {summary.get('review_only_watch', 0)} / {summary.get('review_only_blocked', 0)}",
        f"- Blockers: {summary.get('blocker_count', 0)}",
        "",
        "## Candidates",
        "",
    ]
    candidates = list(report.get("candidates", []))
    if not candidates:
        lines.append("No review candidates were produced.")
    for idx, candidate in enumerate(candidates, start=1):
        lines.extend(
            [
                f"### {idx}. {candidate.get('kalshi_ticker', '')}",
                "",
                str(candidate.get("title") or ""),
                "",
                f"- Review status: `{candidate.get('review_status', '')}`",
                f"- Kalshi midpoint: {float(candidate.get('kalshi_midpoint', 0.0)):.4f}",
                f"- Sportsbook no-vig midpoint: {float(candidate.get('sportsbook_no_vig_yes', 0.0)):.4f}",
                f"- Raw divergence: {float(candidate.get('raw_divergence', 0.0)):.4f}",
                f"- Review-only net divergence: {float(candidate.get('review_only_net_divergence', 0.0)):.4f}",
                f"- Blockers: {candidate.get('blockers', [])}",
                "",
            ]
        )
    blockers = list(report.get("blockers", []))
    if blockers:
        lines.extend(["## Blockers", ""])
        for blocker in blockers[:20]:
            lines.append(f"- `{blocker.get('reason', '')}`: {blocker.get('detail', '')}")
    lines.extend(
        [
            "",
            "## Guardrail",
            "",
            "`REVIEW_ONLY_PASS` means the row is eligible for manual research review only.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _candidate_from_reference(
    reference: Mapping[str, Any],
    *,
    row_by_ticker: Mapping[str, Mapping[str, Any]],
    min_net_divergence: float,
    uncertainty_buffer: float,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    blockers: List[Dict[str, Any]] = []
    kalshi_ticker = str(
        reference.get("kalshi_ticker")
        or reference.get("ticker")
        or reference.get("market_id")
        or ""
    ).strip()
    reference_id = str(reference.get("reference_id") or kalshi_ticker or "unknown")
    if not kalshi_ticker:
        return None, [{"reference_id": reference_id, "reason": "missing_explicit_kalshi_ticker", "detail": "Reference row has no kalshi_ticker."}]
    kalshi_row = row_by_ticker.get(kalshi_ticker)
    if kalshi_row is None:
        return None, [{"reference_id": reference_id, "reason": "kalshi_ticker_not_found", "detail": kalshi_ticker}]

    quote, quote_blockers = _kalshi_quote(kalshi_row)
    blockers.extend(
        {"reference_id": reference_id, "kalshi_ticker": kalshi_ticker, **blocker}
        for blocker in quote_blockers
    )
    try:
        sportsbook = no_vig_midpoint_from_reference(reference)
    except ValueError as exc:
        blockers.append(
            {
                "reference_id": reference_id,
                "kalshi_ticker": kalshi_ticker,
                "reason": "invalid_sportsbook_reference",
                "detail": str(exc),
            }
        )
        sportsbook = None

    if quote is None or sportsbook is None:
        return (
            {
                "reference_id": reference_id,
                "kalshi_ticker": kalshi_ticker,
                "title": kalshi_row.get("title"),
                "review_status": "REVIEW_ONLY_BLOCKED",
                "blockers": [blocker["reason"] for blocker in blockers if blocker.get("reference_id") == reference_id],
            },
            blockers,
        )

    raw_divergence = abs(quote["midpoint"] - sportsbook["no_vig_yes"])
    net_divergence = raw_divergence - quote["half_spread"] - float(uncertainty_buffer)
    review_status = (
        "REVIEW_ONLY_PASS"
        if net_divergence >= float(min_net_divergence)
        else "REVIEW_ONLY_WATCH"
    )
    return (
        {
            "reference_id": reference_id,
            "kalshi_ticker": kalshi_ticker,
            "event_ticker": kalshi_row.get("event_ticker"),
            "title": kalshi_row.get("title"),
            "review_status": review_status,
            "kalshi_bid": quote["bid"],
            "kalshi_ask": quote["ask"],
            "kalshi_midpoint": quote["midpoint"],
            "kalshi_half_spread": quote["half_spread"],
            "sportsbook_raw_yes_implied": sportsbook["raw_yes_implied"],
            "sportsbook_raw_no_implied": sportsbook["raw_no_implied"],
            "sportsbook_overround": sportsbook["overround"],
            "sportsbook_no_vig_yes": sportsbook["no_vig_yes"],
            "sportsbook_no_vig_no": sportsbook["no_vig_no"],
            "raw_divergence": raw_divergence,
            "review_only_net_divergence": net_divergence,
            "threshold": float(min_net_divergence),
            "uncertainty_buffer": float(uncertainty_buffer),
            "blockers": [],
        },
        blockers,
    )


def _kalshi_quote(row: Mapping[str, Any]) -> Tuple[Optional[Dict[str, float]], List[Dict[str, str]]]:
    bid = _optional_float(row.get("bid", row.get("yes_bid", row.get("yes_bid_dollars"))))
    ask = _optional_float(row.get("ask", row.get("yes_ask", row.get("yes_ask_dollars"))))
    if bid is None or ask is None:
        return None, [{"reason": "missing_kalshi_bid_ask", "detail": "Kalshi row must include bid and ask."}]
    if bid < 0.0 or ask > 1.0 or ask < bid:
        return None, [{"reason": "invalid_kalshi_bid_ask", "detail": f"bid={bid}, ask={ask}"}]
    midpoint = (bid + ask) / 2.0
    return {
        "bid": bid,
        "ask": ask,
        "midpoint": midpoint,
        "half_spread": (ask - bid) / 2.0,
    }, []


def _side_payload(reference: Mapping[str, Any], side: str) -> Any:
    payload = reference.get(side)
    if payload is not None:
        return payload
    for suffix in ("implied_probability", "probability", "prob", "american", "american_odds", "decimal", "decimal_odds"):
        key = f"{side}_{suffix}"
        if key in reference:
            return {suffix: reference[key]}
    raise ValueError(f"Missing {side.upper()} odds")


def _kalshi_rows(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    for key in ("all_scored", "markets", "rows", "top_50"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, Mapping)]
    return []


def _index_kalshi_rows(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    out: Dict[str, Mapping[str, Any]] = {}
    for row in rows:
        for key in ("ticker", "market_id"):
            value = str(row.get(key) or "").strip()
            if value and value not in out:
                out[value] = row
    return out


def _sportsbook_references(payload: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, Mapping)]
    for key in ("markets", "references", "rows"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [dict(item) for item in rows if isinstance(item, Mapping)]
    return []


def _status_counts(candidates: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for candidate in candidates:
        status = str(candidate.get("review_status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _report_status(
    candidates: Sequence[Mapping[str, Any]],
    blockers: Sequence[Mapping[str, Any]],
    sportsbook_payload: Optional[Mapping[str, Any]],
) -> str:
    if sportsbook_payload is None:
        return "blocked_missing_sportsbook_reference"
    if not candidates and blockers:
        return "blocked_no_matched_references"
    if any(candidate.get("review_status") == "REVIEW_ONLY_PASS" for candidate in candidates):
        return "review_candidates_present"
    if candidates:
        return "watch_only_no_review_candidates"
    return "blocked_empty_reference"


def _stable_run_id(
    kalshi_payload: Mapping[str, Any],
    sportsbook_payload: Mapping[str, Any],
    *,
    min_net_divergence: float,
    uncertainty_buffer: float,
) -> str:
    payload = {
        "kalshi": kalshi_payload,
        "sportsbook": sportsbook_payload,
        "min_net_divergence": min_net_divergence,
        "uncertainty_buffer": uncertainty_buffer,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:12]
    return f"type2-paper-matcher-{digest}"


def _read_json(path: Optional[Path]) -> Mapping[str, Any]:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, Mapping):
        return payload
    if isinstance(payload, list):
        return {"markets": payload}
    raise ValueError(f"Expected JSON object or list in {path}")


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the paper-only Type 2 Kalshi sportsbook matcher.")
    parser.add_argument("--kalshi-json", default="data/kalshi_scored_refined_2026-06-16.json")
    parser.add_argument("--sportsbook-json", default=None)
    parser.add_argument("--output-dir", default="docs/codex/artifacts/type2-paper-matcher-latest")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--min-net-divergence", type=float, default=0.10)
    parser.add_argument("--uncertainty-buffer", type=float, default=0.0)
    args = parser.parse_args(argv)

    artifacts = run_type2_paper_matcher(
        kalshi_json=Path(args.kalshi_json),
        sportsbook_json=Path(args.sportsbook_json) if args.sportsbook_json else None,
        output_dir=Path(args.output_dir),
        run_id=args.run_id,
        min_net_divergence=args.min_net_divergence,
        uncertainty_buffer=args.uncertainty_buffer,
    )
    print(
        json.dumps(
            {
                "status": artifacts.report.get("status"),
                "json_path": str(artifacts.json_path),
                "markdown_path": str(artifacts.markdown_path),
                "research_only": artifacts.report.get("research_only"),
                "execution_enabled": artifacts.report.get("execution_enabled"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
