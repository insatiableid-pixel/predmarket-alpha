"""Research-only sportsbook reference intake preflight for Type 2 paper work."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from predmarket.type2_paper_matcher import (
    _index_kalshi_rows,
    _kalshi_rows,
    _sportsbook_references,
    no_vig_midpoint_from_reference,
)


@dataclass(frozen=True)
class Type2ReferencePreflightArtifacts:
    report: dict[str, Any]
    json_path: Path
    markdown_path: Path


def build_type2_reference_preflight(
    kalshi_payload: Mapping[str, Any],
    sportsbook_payload: Mapping[str, Any] | None,
    *,
    kalshi_path: Path | None = None,
    sportsbook_path: Path | None = None,
    run_id: str | None = None,
    created_ts: float | None = None,
) -> dict[str, Any]:
    ts = float(created_ts or time.time())
    rows = _kalshi_rows(kalshi_payload)
    row_by_ticker = _index_kalshi_rows(rows)
    references = _sportsbook_references(sportsbook_payload)
    reference_results: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []

    if sportsbook_payload is None:
        blockers.append(
            {
                "reason": "missing_sportsbook_reference",
                "detail": "Supply a small local sportsbook reference JSON with explicit kalshi_ticker mappings.",
            }
        )
    elif not references:
        blockers.append(
            {
                "reason": "empty_sportsbook_reference",
                "detail": "Reference JSON must include a non-empty markets, references, rows, or top-level list.",
            }
        )

    for idx, reference in enumerate(references, start=1):
        result = _validate_reference_row(reference, row_by_ticker=row_by_ticker, row_index=idx)
        reference_results.append(result)
        blockers.extend(result["blockers"])

    ready = sportsbook_payload is not None and bool(references) and not blockers
    status = _preflight_status(
        ready=ready,
        sportsbook_payload=sportsbook_payload,
        references=references,
        blockers=blockers,
    )
    gates = _preflight_gates(
        sportsbook_payload=sportsbook_payload,
        references=references,
        reference_results=reference_results,
        blockers=blockers,
    )
    report = {
        "schema_version": 1,
        "run_id": run_id or _stable_run_id(kalshi_payload, sportsbook_payload or {}),
        "created_ts": ts,
        "created_at_utc": datetime.fromtimestamp(ts, UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "ready": ready,
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
            "kalshi_sha256": _sha256(kalshi_path)
            if kalshi_path and kalshi_path.is_file()
            else None,
            "sportsbook_sha256": _sha256(sportsbook_path)
            if sportsbook_path and sportsbook_path.is_file()
            else None,
            "kalshi_rows": len(rows),
            "sportsbook_references": len(references),
        },
        "policy": {
            "matching_policy": "explicit_kalshi_ticker_only",
            "odds_policy": "two_sided_yes_no_required",
            "provider_calls_allowed": False,
        },
        "summary": {
            "reference_count": len(references),
            "valid_reference_count": sum(1 for result in reference_results if result["valid"]),
            "missing_ticker_count": sum(
                1
                for result in reference_results
                if "missing_explicit_kalshi_ticker" in result["blocker_reasons"]
            ),
            "unknown_ticker_count": sum(
                1
                for result in reference_results
                if "kalshi_ticker_not_found" in result["blocker_reasons"]
            ),
            "invalid_odds_count": sum(
                1
                for result in reference_results
                if "invalid_sportsbook_reference" in result["blocker_reasons"]
            ),
            "blocker_count": len(blockers),
        },
        "gates": gates,
        "references": reference_results,
        "blockers": blockers,
    }
    return report


def run_type2_reference_preflight(
    *,
    kalshi_json: Path,
    sportsbook_json: Path | None = None,
    output_dir: Path,
    run_id: str | None = None,
) -> Type2ReferencePreflightArtifacts:
    kalshi_payload = _read_json(kalshi_json)
    sportsbook_payload = _read_json(sportsbook_json) if sportsbook_json else None
    report = build_type2_reference_preflight(
        kalshi_payload,
        sportsbook_payload,
        kalshi_path=kalshi_json,
        sportsbook_path=sportsbook_json,
        run_id=run_id,
    )
    return write_type2_reference_preflight(report, output_dir=output_dir)


def write_type2_reference_preflight(
    report: Mapping[str, Any],
    *,
    output_dir: Path,
) -> Type2ReferencePreflightArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(report.get("run_id") or f"type2-reference-preflight-{int(time.time())}")
    json_path = output_dir / f"{run_id}.json"
    markdown_path = output_dir / f"{run_id}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_type2_reference_preflight_markdown(report), encoding="utf-8")
    return Type2ReferencePreflightArtifacts(dict(report), json_path, markdown_path)


def render_type2_reference_preflight_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# Type 2 Reference Intake Preflight: {report.get('run_id', '')}",
        "",
        "## Scope",
        "",
        "- Mode: review-only",
        "- Research only: true",
        "- Execution enabled: false",
        f"- Ready: `{str(report.get('ready', False)).lower()}`",
        f"- Status: `{report.get('status', '')}`",
        f"- Matching policy: `{report.get('policy', {}).get('matching_policy', '')}`",
        "",
        "## Summary",
        "",
        f"- References: {summary.get('reference_count', 0)}",
        f"- Valid references: {summary.get('valid_reference_count', 0)}",
        f"- Missing tickers: {summary.get('missing_ticker_count', 0)}",
        f"- Unknown tickers: {summary.get('unknown_ticker_count', 0)}",
        f"- Invalid odds rows: {summary.get('invalid_odds_count', 0)}",
        f"- Blockers: {summary.get('blocker_count', 0)}",
        "",
        "## Gates",
        "",
    ]
    for gate in report.get("gates", []):
        lines.append(
            f"- `{gate.get('name', '')}`: `{gate.get('status', '')}` - {'; '.join(gate.get('reasons', []))}"
        )
    references = list(report.get("references", []))
    if references:
        lines.extend(["", "## References", ""])
        for result in references[:25]:
            lines.extend(
                [
                    f"### {result.get('reference_id', '')}",
                    "",
                    f"- Kalshi ticker: `{result.get('kalshi_ticker', '')}`",
                    f"- Valid: `{str(result.get('valid', False)).lower()}`",
                    f"- Blockers: {result.get('blocker_reasons', [])}",
                    "",
                ]
            )
    blockers = list(report.get("blockers", []))
    if blockers:
        lines.extend(["## Blockers", ""])
        for blocker in blockers[:25]:
            lines.append(f"- `{blocker.get('reason', '')}`: {blocker.get('detail', '')}")
    lines.extend(
        [
            "",
            "## Guardrail",
            "",
            "A ready preflight only means the local reference can be used by the paper matcher for manual review.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _validate_reference_row(
    reference: Mapping[str, Any],
    *,
    row_by_ticker: Mapping[str, Mapping[str, Any]],
    row_index: int,
) -> dict[str, Any]:
    reference_id = str(reference.get("reference_id") or f"row-{row_index}")
    kalshi_ticker = str(reference.get("kalshi_ticker") or "").strip()
    blockers: list[dict[str, Any]] = []

    if not kalshi_ticker:
        blockers.append(
            {
                "reference_id": reference_id,
                "reason": "missing_explicit_kalshi_ticker",
                "detail": "Each reference row must include kalshi_ticker.",
            }
        )
    elif kalshi_ticker not in row_by_ticker:
        blockers.append(
            {
                "reference_id": reference_id,
                "kalshi_ticker": kalshi_ticker,
                "reason": "kalshi_ticker_not_found",
                "detail": kalshi_ticker,
            }
        )

    odds_summary: dict[str, float] | None = None
    try:
        odds_summary = no_vig_midpoint_from_reference(reference)
    except ValueError as exc:
        blockers.append(
            {
                "reference_id": reference_id,
                "kalshi_ticker": kalshi_ticker,
                "reason": "invalid_sportsbook_reference",
                "detail": str(exc),
            }
        )

    return {
        "reference_id": reference_id,
        "kalshi_ticker": kalshi_ticker,
        "valid": not blockers,
        "blocker_reasons": [blocker["reason"] for blocker in blockers],
        "no_vig_yes": odds_summary.get("no_vig_yes") if odds_summary else None,
        "no_vig_no": odds_summary.get("no_vig_no") if odds_summary else None,
        "blockers": blockers,
    }


def _preflight_status(
    *,
    ready: bool,
    sportsbook_payload: Mapping[str, Any] | None,
    references: Sequence[Mapping[str, Any]],
    blockers: Sequence[Mapping[str, Any]],
) -> str:
    if ready:
        return "reference_ready"
    if sportsbook_payload is None:
        return "blocked_missing_sportsbook_reference"
    if not references:
        return "blocked_empty_reference"
    if blockers:
        return "blocked_invalid_reference"
    return "blocked_unknown"


def _preflight_gates(
    *,
    sportsbook_payload: Mapping[str, Any] | None,
    references: Sequence[Mapping[str, Any]],
    reference_results: Sequence[Mapping[str, Any]],
    blockers: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    blocker_reasons = {str(blocker.get("reason")) for blocker in blockers}
    return [
        _gate(
            "research_only_safety",
            "pass",
            ["No provider, paid, database, account, order, or execution calls are used."],
        ),
        _gate(
            "reference_file_available",
            "pass" if sportsbook_payload is not None else "blocked",
            [
                "Sportsbook reference JSON supplied."
                if sportsbook_payload is not None
                else "Sportsbook reference JSON is missing."
            ],
        ),
        _gate(
            "reference_rows_present",
            "pass" if references else "blocked",
            [f"Reference rows: {len(references)}."],
        ),
        _gate(
            "explicit_kalshi_mappings",
            "blocked"
            if "missing_explicit_kalshi_ticker" in blocker_reasons
            else ("pass" if reference_results else "blocked"),
            [
                "Every reference row has kalshi_ticker."
                if reference_results and "missing_explicit_kalshi_ticker" not in blocker_reasons
                else (
                    "At least one row is missing kalshi_ticker."
                    if reference_results
                    else "No reference rows are available to check for kalshi_ticker."
                )
            ],
        ),
        _gate(
            "kalshi_tickers_resolve",
            "blocked"
            if "kalshi_ticker_not_found" in blocker_reasons
            else ("pass" if reference_results else "blocked"),
            [
                "All mapped tickers resolve to the local Kalshi artifact."
                if reference_results and "kalshi_ticker_not_found" not in blocker_reasons
                else (
                    "At least one mapped ticker is not present in the local Kalshi artifact."
                    if reference_results
                    else "No mapped tickers are available to resolve."
                )
            ],
        ),
        _gate(
            "two_sided_odds_valid",
            "blocked"
            if "invalid_sportsbook_reference" in blocker_reasons
            else ("pass" if reference_results else "blocked"),
            [
                "Every mapped row has usable two-sided YES/NO odds."
                if reference_results and "invalid_sportsbook_reference" not in blocker_reasons
                else (
                    "At least one row lacks usable two-sided YES/NO odds."
                    if reference_results
                    else "No reference rows are available to check for YES/NO odds."
                )
            ],
        ),
        _gate(
            "no_fuzzy_matching",
            "pass",
            ["Only exact kalshi_ticker mappings are allowed."],
        ),
    ]


def _gate(name: str, status: str, reasons: list[str]) -> dict[str, Any]:
    return {"name": name, "status": status, "reasons": reasons}


def _stable_run_id(kalshi_payload: Mapping[str, Any], sportsbook_payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {"kalshi": kalshi_payload, "sportsbook": sportsbook_payload},
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()[:12]
    return f"type2-reference-preflight-{digest}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path | None) -> Mapping[str, Any]:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, Mapping):
        return payload
    if isinstance(payload, list):
        return {"markets": payload}
    raise ValueError(f"Expected JSON object or list in {path}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the local Type 2 sportsbook reference intake preflight."
    )
    parser.add_argument("--kalshi-json", default="data/kalshi_scored_refined_2026-06-16.json")
    parser.add_argument("--sportsbook-json", default=None)
    parser.add_argument(
        "--output-dir", default="docs/codex/artifacts/type2-reference-preflight-latest"
    )
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)

    artifacts = run_type2_reference_preflight(
        kalshi_json=Path(args.kalshi_json),
        sportsbook_json=Path(args.sportsbook_json) if args.sportsbook_json else None,
        output_dir=Path(args.output_dir),
        run_id=args.run_id,
    )
    print(
        json.dumps(
            {
                "status": artifacts.report.get("status"),
                "ready": artifacts.report.get("ready"),
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
