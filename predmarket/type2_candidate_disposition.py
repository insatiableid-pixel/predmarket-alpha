"""Review-only disposition for Type 2 paper matcher candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


@dataclass(frozen=True)
class Type2CandidateDispositionArtifacts:
    report: Dict[str, Any]
    json_path: Path
    markdown_path: Path


def build_type2_candidate_disposition(
    paper_report: Mapping[str, Any],
    sportsbook_payload: Mapping[str, Any],
    kalshi_payload: Mapping[str, Any],
    *,
    paper_matcher_path: Optional[Path] = None,
    sportsbook_path: Optional[Path] = None,
    kalshi_path: Optional[Path] = None,
    run_id: Optional[str] = None,
    created_ts: Optional[float] = None,
) -> Dict[str, Any]:
    ts = float(created_ts or time.time())
    references, duplicate_reference_tickers = _reference_by_ticker(sportsbook_payload)
    kalshi_capture = _parse_time(kalshi_payload.get("created_at_utc"))
    dispositions = [
        _disposition_for_candidate(
            candidate,
            references.get(str(candidate.get("kalshi_ticker") or "")),
            kalshi_capture,
            duplicate_reference=str(candidate.get("kalshi_ticker") or "") in duplicate_reference_tickers,
        )
        for candidate in _candidates(paper_report)
    ]
    counts = _counts(dispositions, "disposition")
    original_counts = _counts(dispositions, "original_review_status")
    summary = {
        "candidate_count": len(dispositions),
        "original_review_only_pass": original_counts.get("REVIEW_ONLY_PASS", 0),
        "original_review_only_watch": original_counts.get("REVIEW_ONLY_WATCH", 0),
        "kept_review_candidate": counts.get("KEPT_REVIEW_CANDIDATE", 0),
        "watch_only": counts.get("WATCH_ONLY", 0),
        "downgraded_temporal_mismatch": counts.get("DOWNGRADED_TEMPORAL_MISMATCH", 0),
        "manual_review_timing_unknown": counts.get("MANUAL_REVIEW_TIMING_UNKNOWN", 0),
        "blocked": counts.get("BLOCKED", 0),
        "duplicate_reference_ticker_count": len(duplicate_reference_tickers),
    }
    status = _status(summary)
    report = {
        "schema_version": 1,
        "run_id": run_id or _stable_run_id(paper_report, sportsbook_payload, kalshi_payload),
        "created_ts": ts,
        "created_at_utc": datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z"),
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
            "sportsbook_json": str(sportsbook_path) if sportsbook_path else None,
            "kalshi_json": str(kalshi_path) if kalshi_path else None,
            "paper_matcher_status": paper_report.get("status"),
            "kalshi_capture_time_utc": kalshi_payload.get("created_at_utc"),
        },
        "policy": {
            "matching_policy": "explicit_kalshi_ticker_only",
            "timing_policy": "sportsbook_and_kalshi_captures_must_be_strictly_before_commence_time",
            "provider_calls_allowed": False,
        },
        "summary": summary,
        "dispositions": dispositions,
    }
    return report


def run_type2_candidate_disposition(
    *,
    paper_matcher_json: Path,
    sportsbook_json: Path,
    kalshi_json: Path,
    output_dir: Path,
    run_id: Optional[str] = None,
) -> Type2CandidateDispositionArtifacts:
    paper_report = _read_json(paper_matcher_json)
    sportsbook_payload = _read_json(sportsbook_json)
    kalshi_payload = _read_json(kalshi_json)
    report = build_type2_candidate_disposition(
        paper_report,
        sportsbook_payload,
        kalshi_payload,
        paper_matcher_path=paper_matcher_json,
        sportsbook_path=sportsbook_json,
        kalshi_path=kalshi_json,
        run_id=run_id,
    )
    return write_type2_candidate_disposition(report, output_dir=output_dir)


def write_type2_candidate_disposition(
    report: Mapping[str, Any],
    *,
    output_dir: Path,
) -> Type2CandidateDispositionArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(report.get("run_id") or f"type2-candidate-disposition-{int(time.time())}")
    json_path = output_dir / f"{run_id}.json"
    markdown_path = output_dir / f"{run_id}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_type2_candidate_disposition_markdown(report), encoding="utf-8")
    return Type2CandidateDispositionArtifacts(dict(report), json_path, markdown_path)


def render_type2_candidate_disposition_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# Type 2 Candidate Disposition: {report.get('run_id', '')}",
        "",
        "## Scope",
        "",
        "- Mode: review-only",
        "- Research only: true",
        "- Execution enabled: false",
        f"- Status: `{report.get('status', '')}`",
        f"- Timing policy: `{report.get('policy', {}).get('timing_policy', '')}`",
        "",
        "## Summary",
        "",
        f"- Candidates checked: {summary.get('candidate_count', 0)}",
        f"- Original pass/watch: {summary.get('original_review_only_pass', 0)} / {summary.get('original_review_only_watch', 0)}",
        f"- Kept review candidates: {summary.get('kept_review_candidate', 0)}",
        f"- Watch only: {summary.get('watch_only', 0)}",
        f"- Downgraded timing mismatches: {summary.get('downgraded_temporal_mismatch', 0)}",
        f"- Manual timing checks needed: {summary.get('manual_review_timing_unknown', 0)}",
        "",
        "## Kept Review Candidates",
        "",
    ]
    kept = [row for row in report.get("dispositions", []) if row.get("disposition") == "KEPT_REVIEW_CANDIDATE"]
    if not kept:
        lines.append("No rows survived the timing policy as review candidates.")
    for row in kept[:25]:
        lines.extend(
            [
                f"### {row.get('kalshi_ticker', '')}",
                "",
                f"- Title: {row.get('title', '')}",
                f"- Review-only net divergence: {float(row.get('review_only_net_divergence', 0.0)):.4f}",
                f"- Sportsbook capture: `{row.get('sportsbook_capture_time_utc')}`",
                f"- Kalshi capture: `{row.get('kalshi_capture_time_utc')}`",
                f"- First pitch: `{row.get('commence_time_utc')}`",
                "",
            ]
        )
    downgraded = [row for row in report.get("dispositions", []) if row.get("disposition") == "DOWNGRADED_TEMPORAL_MISMATCH"]
    if downgraded:
        lines.extend(["## Downgraded Timing Mismatches", ""])
        for row in downgraded[:25]:
            lines.append(
                f"- `{row.get('kalshi_ticker', '')}`: {row.get('reason', '')} "
                f"(first pitch `{row.get('commence_time_utc')}`)"
            )
    lines.extend(
        [
            "",
            "## Guardrail",
            "",
            "This report only narrows rows for manual research review. It does not authorize execution or account activity.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _disposition_for_candidate(
    candidate: Mapping[str, Any],
    reference: Optional[Mapping[str, Any]],
    kalshi_capture: Optional[datetime],
    *,
    duplicate_reference: bool = False,
) -> Dict[str, Any]:
    ticker = str(candidate.get("kalshi_ticker") or "")
    original_status = str(candidate.get("review_status") or "")
    reference = reference or {}
    sportsbook_capture = _parse_time(reference.get("capture_time_utc"))
    commence = _parse_time(reference.get("commence_time_utc"))
    reason = "Timing policy passed."
    disposition = "WATCH_ONLY"

    if duplicate_reference:
        disposition = "MANUAL_REVIEW_TIMING_UNKNOWN"
        reason = "Multiple sportsbook reference rows were found for this explicit ticker."
    elif original_status == "REVIEW_ONLY_BLOCKED":
        disposition = "BLOCKED"
        reason = "Paper matcher blocked this row."
    elif not reference:
        disposition = "MANUAL_REVIEW_TIMING_UNKNOWN"
        reason = "No sportsbook reference row was found for the explicit ticker."
    elif sportsbook_capture is None or kalshi_capture is None or commence is None:
        disposition = "MANUAL_REVIEW_TIMING_UNKNOWN"
        reason = "Sportsbook capture, Kalshi capture, or first-pitch time is missing or invalid."
    elif sportsbook_capture >= commence or kalshi_capture >= commence:
        disposition = "DOWNGRADED_TEMPORAL_MISMATCH"
        reason = "At least one snapshot was captured at or after first pitch."
    elif original_status == "REVIEW_ONLY_PASS":
        disposition = "KEPT_REVIEW_CANDIDATE"

    return {
        "reference_id": candidate.get("reference_id"),
        "kalshi_ticker": ticker,
        "event_ticker": candidate.get("event_ticker"),
        "title": candidate.get("title"),
        "team": reference.get("team"),
        "opponent": reference.get("opponent"),
        "sportsbook": reference.get("sportsbook"),
        "original_review_status": original_status,
        "disposition": disposition,
        "reason": reason,
        "kalshi_midpoint": candidate.get("kalshi_midpoint"),
        "sportsbook_no_vig_yes": candidate.get("sportsbook_no_vig_yes"),
        "review_only_net_divergence": candidate.get("review_only_net_divergence"),
        "sportsbook_capture_time_utc": reference.get("capture_time_utc"),
        "kalshi_capture_time_utc": _format_time(kalshi_capture),
        "commence_time_utc": reference.get("commence_time_utc"),
        "blockers": candidate.get("blockers", []),
    }


def _reference_by_ticker(payload: Mapping[str, Any]) -> tuple[Dict[str, Mapping[str, Any]], set[str]]:
    rows: Sequence[Any]
    if isinstance(payload, list):
        rows = payload
    else:
        rows = payload.get("markets") or payload.get("references") or payload.get("rows") or []
    out: Dict[str, Mapping[str, Any]] = {}
    duplicates: set[str] = set()
    for row in rows:
        if isinstance(row, Mapping):
            ticker = str(row.get("kalshi_ticker") or "").strip()
            if ticker and ticker in out:
                duplicates.add(ticker)
            elif ticker:
                out[ticker] = row
    return out, duplicates


def _candidates(payload: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    rows = payload.get("candidates") if isinstance(payload, Mapping) else []
    return [row for row in rows if isinstance(row, Mapping)]


def _status(summary: Mapping[str, int]) -> str:
    if summary.get("blocked", 0):
        return "candidate_disposition_blocked_rows_present"
    if summary.get("kept_review_candidate", 0):
        return "candidate_disposition_review_candidates_present"
    if summary.get("manual_review_timing_unknown", 0):
        return "candidate_disposition_manual_timing_review"
    if summary.get("downgraded_temporal_mismatch", 0) and summary.get("original_review_only_pass", 0):
        return "candidate_disposition_all_passes_downgraded"
    return "candidate_disposition_watch_only"


def _counts(rows: Sequence[Mapping[str, Any]], key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_time(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_run_id(
    paper_report: Mapping[str, Any],
    sportsbook_payload: Mapping[str, Any],
    kalshi_payload: Mapping[str, Any],
) -> str:
    payload = {
        "paper": paper_report,
        "sportsbook": sportsbook_payload,
        "kalshi_capture": kalshi_payload.get("created_at_utc"),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:12]
    return f"type2-candidate-disposition-{digest}"


def _read_json(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, Mapping):
        return payload
    if isinstance(payload, list):
        return {"markets": payload}
    raise ValueError(f"Expected JSON object or list in {path}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the review-only Type 2 candidate disposition.")
    parser.add_argument("--paper-matcher-json", default="docs/codex/artifacts/type2-paper-matcher-latest/type2-paper-matcher-latest.json")
    parser.add_argument("--sportsbook-json", default="/home/mrwatson/manual_drops/predmarket/type2-sportsbook-reference.json")
    parser.add_argument("--kalshi-json", default="data/kalshi_mlb_game_series_live_current_20260620T230203Z.json")
    parser.add_argument("--output-dir", default="docs/codex/artifacts/type2-candidate-disposition-latest")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)

    artifacts = run_type2_candidate_disposition(
        paper_matcher_json=Path(args.paper_matcher_json),
        sportsbook_json=Path(args.sportsbook_json),
        kalshi_json=Path(args.kalshi_json),
        output_dir=Path(args.output_dir),
        run_id=args.run_id,
    )
    print(
        json.dumps(
            {
                "status": artifacts.report.get("status"),
                "json_path": str(artifacts.json_path),
                "markdown_path": str(artifacts.markdown_path),
                "research_only": artifacts.report.get("research_only"),
                "execution_enabled": artifacts.report.get("execution_enabled"),
                "summary": artifacts.report.get("summary"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
