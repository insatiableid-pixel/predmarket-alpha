"""Capture and audit current sharp sports provider availability.

This module deliberately does not build consensus probabilities or exact Kalshi
mapping rows. Sport-specific adapters own that layer. The purpose here is to
record which configured sharp providers were observable in timestamped current
odds payloads across the requested sports, without turning unsupported mapper
coverage into a false provider failure.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from predmarket.sports_consensus_provider_policy import (
    collect_provider_observations,
    is_anchor_provider,
    normalize_provider_id,
    provider_spec,
)
from predmarket.sports_consensus_reference_builder import capture_the_odds_api_current

CaptureCurrent = Callable[..., tuple[list[Mapping[str, Any]], Mapping[str, Any], Path]]


def capture_sharp_provider_sources(
    *,
    api_key: str,
    sport_keys: Sequence[str],
    raw_output_dir: Path,
    regions: Sequence[str] = ("us",),
    bookmakers: Sequence[str] = (),
    markets: Sequence[str] = ("h2h",),
    odds_format: str = "american",
    timeout_seconds: float = 20.0,
    capture_current: CaptureCurrent = capture_the_odds_api_current,
) -> list[dict[str, Any]]:
    """Capture current odds payloads for each sport, preserving per-sport errors."""

    captures: list[dict[str, Any]] = []
    for sport_key in sport_keys:
        try:
            payload, meta, raw_path = capture_current(
                api_key=api_key,
                sport_key=sport_key,
                output_dir=raw_output_dir,
                regions=regions,
                bookmakers=bookmakers,
                markets=markets,
                odds_format=odds_format,
                timeout_seconds=timeout_seconds,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            captures.append(
                {
                    "sport_key": sport_key,
                    "payload": [],
                    "meta": {
                        "sport_key": sport_key,
                        "status": "sharp_provider_capture_error",
                        "error": str(exc),
                        "provider_api_calls": True,
                        "provider_api_call_count": 1,
                        "paid_calls": True,
                        "paid_call_count": 1,
                    },
                    "raw_path": None,
                    "error": str(exc),
                }
            )
            continue
        captures.append(
            {
                "sport_key": sport_key,
                "payload": list(payload),
                "meta": dict(meta),
                "raw_path": raw_path,
                "error": None,
            }
        )
    return captures


def build_sharp_provider_capture_report(
    *,
    captures: Sequence[Mapping[str, Any]],
    requested_sport_keys: Sequence[str],
    requested_bookmakers: Sequence[str] = (),
    requested_markets: Sequence[str] = ("h2h",),
    requested_regions: Sequence[str] = ("us",),
    run_id: str | None = None,
    created_ts: float | None = None,
) -> dict[str, Any]:
    ts = float(created_ts or time.time())
    provider_counter: Counter[str] = Counter()
    sport_provider_map: dict[str, Counter[str]] = defaultdict(Counter)
    sport_event_counter: Counter[str] = Counter()
    sport_error_map: dict[str, list[str]] = defaultdict(list)
    source_rows: list[dict[str, Any]] = []

    for capture in captures:
        payload = capture.get("payload")
        payload_rows = [row for row in payload if isinstance(row, Mapping)] if isinstance(payload, list) else []
        meta = capture.get("meta") if isinstance(capture.get("meta"), Mapping) else {}
        raw_path = capture.get("raw_path")
        raw_path_obj = raw_path if isinstance(raw_path, Path) else Path(raw_path) if raw_path else None
        sport_key = str(
            capture.get("sport_key")
            or meta.get("sport_key")
            or _infer_sport_key(payload_rows)
            or "unknown"
        )
        error = str(capture.get("error") or meta.get("error") or "").strip()
        if error:
            sport_error_map[sport_key].append(error)
        source_id = _source_id(sport_key=sport_key, raw_path=raw_path_obj)
        observations = collect_provider_observations(
            payload_rows,
            source_id=source_id,
            source_path=raw_path_obj,
            source_kind="raw_provider_capture",
        )
        provider_ids = sorted({row.provider_id for row in observations if row.provider_id != "unknown"})
        for provider_id in provider_ids:
            provider_counter[provider_id] += 1
            sport_provider_map[sport_key][provider_id] += 1
        sport_event_counter[sport_key] += len(payload_rows)
        source_rows.append(
            {
                "source_id": source_id,
                "sport_key": sport_key,
                "source_path": str(raw_path_obj) if raw_path_obj else None,
                "source_sha256": _sha256(raw_path_obj)
                if raw_path_obj and raw_path_obj.is_file()
                else None,
                "status": meta.get("status"),
                "error": error or None,
                "event_count": len(payload_rows),
                "provider_count": len(provider_ids),
                "providers": provider_ids,
                "anchor_providers": [provider_id for provider_id in provider_ids if is_anchor_provider(provider_id)],
                "created_at_utc": meta.get("created_at_utc"),
                "quota_headers": meta.get("quota_headers")
                if isinstance(meta.get("quota_headers"), Mapping)
                else {},
                "research_only": True,
                "usable": False,
            }
        )

    sport_rows = [
        _sport_row(
            sport_key=sport_key,
            requested=True,
            event_count=sport_event_counter.get(sport_key, 0),
            provider_counts=sport_provider_map.get(sport_key, Counter()),
            errors=sport_error_map.get(sport_key, []),
        )
        for sport_key in dict.fromkeys(requested_sport_keys)
    ]
    for sport_key in sorted(set(sport_provider_map) - set(requested_sport_keys)):
        sport_rows.append(
            _sport_row(
                sport_key=sport_key,
                requested=False,
                event_count=sport_event_counter.get(sport_key, 0),
                provider_counts=sport_provider_map.get(sport_key, Counter()),
                errors=sport_error_map.get(sport_key, []),
            )
        )

    error_count = sum(1 for row in source_rows if row.get("error"))
    provider_api_call_count = sum(
        _call_count(capture.get("meta"), "provider_api_call_count", "provider_api_calls")
        for capture in captures
    )
    paid_call_count = sum(
        _call_count(capture.get("meta"), "paid_call_count", "paid_calls")
        for capture in captures
    )
    provider_ids = sorted(provider_counter)
    status = _status(
        capture_count=len(captures),
        provider_count=len(provider_ids),
        error_count=error_count,
        full_error_count=len(source_rows),
    )
    requested = {
        "sport_keys": list(requested_sport_keys),
        "bookmakers": [normalize_provider_id(item) for item in requested_bookmakers if item],
        "markets": list(requested_markets),
        "regions": list(requested_regions),
    }
    summary = {
        "sport_count": len(sport_rows),
        "requested_sport_count": len(dict.fromkeys(requested_sport_keys)),
        "source_file_count": len(source_rows),
        "event_count": sum(sport_event_counter.values()),
        "provider_count": len(provider_ids),
        "anchor_provider_count": sum(1 for provider_id in provider_ids if is_anchor_provider(provider_id)),
        "capture_error_count": error_count,
        "sports_with_provider_rows": [
            row["sport_key"] for row in sport_rows if int(row.get("provider_count") or 0) > 0
        ],
        "sports_with_capture_errors": [
            row["sport_key"] for row in sport_rows if int(row.get("error_count") or 0) > 0
        ],
        "providers": provider_ids,
        "anchor_providers": [provider_id for provider_id in provider_ids if is_anchor_provider(provider_id)],
    }
    return {
        "schema_version": 1,
        "run_id": run_id or _stable_run_id(source_rows, requested),
        "created_ts": ts,
        "created_at_utc": datetime.fromtimestamp(ts, UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "provider_api_calls": provider_api_call_count > 0,
        "provider_api_call_count": provider_api_call_count,
        "paid_calls": paid_call_count > 0,
        "paid_call_count": paid_call_count,
        "database_writes": False,
        "raw_provider_payload_copied": False,
        "safety": {
            "provider_api_calls": provider_api_call_count > 0,
            "provider_api_call_count": provider_api_call_count,
            "paid_calls": paid_call_count > 0,
            "paid_call_count": paid_call_count,
            "database_writes": False,
            "account_or_order_paths": False,
            "market_execution": False,
            "raw_provider_payload_copied": False,
            "api_key_printed": False,
            "probabilities_computed": False,
            "paper_or_live_stakes_computed": False,
        },
        "policy": {
            "purpose": "Audit current sharp-provider availability by sport before exact mapping.",
            "boundary": (
                "This artifact records provider/source availability only. It does not create "
                "consensus probabilities, Kalshi ticker mappings, EV, paper stake, or live "
                "eligibility; sport-specific adapters and downstream gates own those steps."
            ),
            "requested": requested,
        },
        "summary": summary,
        "sport_rows": sport_rows,
        "source_rows": source_rows,
        "providers": [_provider_row(provider_id, provider_counter[provider_id]) for provider_id in provider_ids],
    }


def _call_count(meta_value: Any, count_key: str, bool_key: str) -> int:
    meta = meta_value if isinstance(meta_value, Mapping) else {}
    raw_count = meta.get(count_key)
    if isinstance(raw_count, int) and raw_count >= 0:
        return raw_count
    return 1 if meta.get(bool_key) is True else 0


def render_sharp_provider_capture_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Kalshi Sports Sharp Provider Capture",
        "",
        f"- Status: `{report.get('status')}`",
        "- Mode: research-only",
        "- Execution enabled: `false`",
        "- Probability computed: `false`",
        "",
        "## Summary",
        "",
        f"- Requested sports: `{summary.get('requested_sport_count', 0)}`",
        f"- Captured source files: `{summary.get('source_file_count', 0)}`",
        f"- Events: `{summary.get('event_count', 0)}`",
        f"- Providers: `{summary.get('provider_count', 0)}`",
        f"- Anchor providers: `{summary.get('anchor_provider_count', 0)}`",
        f"- Capture errors: `{summary.get('capture_error_count', 0)}`",
        f"- Sports with provider rows: `{summary.get('sports_with_provider_rows', [])}`",
        "",
        "## Sports",
        "",
    ]
    for row in report.get("sport_rows", []):
        if isinstance(row, Mapping):
            lines.append(
                "- "
                f"`{row.get('sport_key')}` events `{row.get('event_count')}` "
                f"providers `{row.get('provider_count')}` anchors `{row.get('anchor_provider_count')}` "
                f"errors `{row.get('error_count')}`"
            )
    lines.extend(["", "## Providers", ""])
    for row in report.get("providers", []):
        if isinstance(row, Mapping):
            lines.append(
                "- "
                f"`{row.get('provider_id')}` tier `{row.get('tier')}` "
                f"role `{row.get('role')}` observations `{row.get('observation_count')}`"
            )
    lines.extend(
        [
            "",
            "> Capture/audit only. Exact Kalshi mapping, OOS/FDR, EV, paper sizing, and live eligibility remain downstream gated steps.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def write_sharp_provider_capture_outputs(report: Mapping[str, Any], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-consensus-sharp-provider-capture.json"
    md_path = out_dir / "kalshi-sports-consensus-sharp-provider-capture.md"
    json_text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    md_text = render_sharp_provider_capture_markdown(report)
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    latest_json = out_dir.parent / "latest-kalshi-sports-consensus-sharp-provider-capture.json"
    latest_md = out_dir.parent / "latest-kalshi-sports-consensus-sharp-provider-capture.md"
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def _sport_row(
    *,
    sport_key: str,
    requested: bool,
    event_count: int,
    provider_counts: Counter[str],
    errors: Sequence[str],
) -> dict[str, Any]:
    providers = sorted(provider_counts)
    anchors = [provider_id for provider_id in providers if is_anchor_provider(provider_id)]
    return {
        "sport_key": sport_key,
        "requested": requested,
        "event_count": event_count,
        "provider_count": len(providers),
        "anchor_provider_count": len(anchors),
        "providers": providers,
        "anchor_providers": anchors,
        "error_count": len(errors),
        "errors": list(errors)[:5],
        "usable": False,
        "research_only": True,
    }


def _provider_row(provider_id: str, observation_count: int) -> dict[str, Any]:
    spec = provider_spec(provider_id)
    return {
        "provider_id": provider_id,
        "display_name": spec.display_name if spec else provider_id,
        "tier": spec.tier if spec else "unknown",
        "role": spec.role if spec else "unknown",
        "provider_kind": spec.provider_kind if spec else "unknown",
        "consensus_anchor_allowed": bool(spec and is_anchor_provider(provider_id)),
        "observation_count": observation_count,
    }


def _status(
    *,
    capture_count: int,
    provider_count: int,
    error_count: int,
    full_error_count: int,
) -> str:
    if capture_count <= 0:
        return "sports_consensus_sharp_provider_capture_blocked_no_captures"
    if error_count and error_count >= full_error_count:
        return "sports_consensus_sharp_provider_capture_blocked_all_captures_failed"
    if provider_count <= 0:
        return "sports_consensus_sharp_provider_capture_blocked_no_provider_rows"
    if error_count:
        return "sports_consensus_sharp_provider_capture_ready_with_capture_errors"
    return "sports_consensus_sharp_provider_capture_ready"


def _source_id(*, sport_key: str, raw_path: Path | None) -> str:
    if raw_path:
        return raw_path.stem
    return f"{sport_key}_current_error"


def _infer_sport_key(payload: Sequence[Mapping[str, Any]]) -> str | None:
    for row in payload:
        sport_key = row.get("sport_key")
        if sport_key:
            return str(sport_key)
    return None


def _stable_run_id(source_rows: Sequence[Mapping[str, Any]], requested: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps({"requested": requested, "sources": source_rows}, sort_keys=True, default=str)
        .encode("utf-8")
    ).hexdigest()
    return f"kalshi-sports-consensus-sharp-provider-capture-{digest[:12]}"


def _sha256(path: Path | None) -> str | None:
    if path is None:
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
