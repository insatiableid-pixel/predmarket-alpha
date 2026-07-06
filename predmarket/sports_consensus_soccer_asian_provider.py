"""Audit soccer Asian sharp-provider availability for sports consensus.

The sports no-vig consensus policy intentionally treats World Cup soccer as
immature until an Asian sharp anchor such as SBOBet, Singbet, or IBC is present.
This module does not make provider calls. It classifies already-captured local
provider payloads so the missing-source state is auditable and machine-readable.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from predmarket.sports_consensus_provider_policy import normalize_provider_id

DEFAULT_TARGET_PROVIDERS = ("sbobet", "singbet", "ibc")
DEFAULT_SOCCER_SPORT_KEYS = ("soccer", "soccer_fifa_world_cup")


def build_soccer_asian_provider_diagnostic(
    *,
    sources: Sequence[Mapping[str, Any]],
    run_id: str | None = None,
    created_ts: float | None = None,
    target_providers: Sequence[str] = DEFAULT_TARGET_PROVIDERS,
    soccer_sport_keys: Sequence[str] = DEFAULT_SOCCER_SPORT_KEYS,
) -> dict[str, Any]:
    ts = float(created_ts or time.time())
    target = tuple(dict.fromkeys(normalize_provider_id(item) for item in target_providers if item))
    soccer_keys = {
        _canonical_sport_key(item) for item in soccer_sport_keys if _canonical_sport_key(item)
    }
    source_rows: list[dict[str, Any]] = []
    target_provider_rows: list[dict[str, Any]] = []
    observed_counter: Counter[str] = Counter()
    requested_counter: Counter[str] = Counter()
    event_count = 0
    provider_api_call_count = 0
    latest_capture_utc: str | None = None
    quota_remaining: str | None = None

    for source in sources:
        payload = source.get("payload")
        meta = source.get("meta") if isinstance(source.get("meta"), Mapping) else {}
        source_path = source.get("source_path")
        source_id = str(source.get("source_id") or source_path or "local_soccer_provider_source")
        source_kind = str(source.get("source_kind") or "raw_provider_capture")
        requested = _requested_target_providers(meta, target)
        for provider_id in requested:
            requested_counter[provider_id] += 1
        if bool(meta.get("provider_api_calls")):
            provider_api_call_count += 1
        capture_utc = _text(meta.get("created_at_utc"))
        quota_headers = meta.get("quota_headers") if isinstance(meta.get("quota_headers"), Mapping) else {}
        if capture_utc and (latest_capture_utc is None or capture_utc >= latest_capture_utc):
            latest_capture_utc = capture_utc
            quota_remaining = _text(quota_headers.get("x-requests-remaining")) or quota_remaining

        events = _soccer_events(payload, soccer_keys=soccer_keys)
        event_count += len(events)
        source_observed: Counter[str] = Counter()
        for event in events:
            sport_key = _text(event.get("sport_key")) or _text(meta.get("sport_key")) or "soccer"
            for bookmaker in event.get("bookmakers") or []:
                if not isinstance(bookmaker, Mapping):
                    continue
                provider_id = normalize_provider_id(bookmaker.get("key") or bookmaker.get("title"))
                if not provider_id or provider_id == "unknown":
                    continue
                observed_counter[provider_id] += 1
                source_observed[provider_id] += 1
                if provider_id in target:
                    target_provider_rows.append(
                        {
                            "source_id": source_id,
                            "source_kind": source_kind,
                            "source_path": source_path,
                            "provider": provider_id,
                            "provider_id": provider_id,
                            "sport_key": sport_key,
                            "market_key": _market_keys(bookmaker),
                            "event_id": event.get("id"),
                            "home_team": event.get("home_team"),
                            "away_team": event.get("away_team"),
                            "commence_time": event.get("commence_time"),
                            "research_only": True,
                            "usable": False,
                        }
                    )
        source_rows.append(
            {
                "source_id": source_id,
                "source_kind": source_kind,
                "source_path": source_path,
                "source_sha256": _sha256(Path(source_path)) if isinstance(source_path, str) else None,
                "meta_path": source.get("meta_path"),
                "meta_sha256": _sha256(Path(source["meta_path"]))
                if isinstance(source.get("meta_path"), str)
                else None,
                "created_at_utc": capture_utc,
                "soccer_event_count": len(events),
                "requested_target_providers": sorted(requested),
                "observed_providers": sorted(source_observed),
                "observed_target_providers": sorted(
                    provider_id for provider_id in source_observed if provider_id in target
                ),
            }
        )

    observed_targets = sorted(provider_id for provider_id in observed_counter if provider_id in target)
    requested_targets = sorted(requested_counter)
    missing_targets = sorted(provider_id for provider_id in target if provider_id not in observed_targets)
    status = _status(
        source_count=len(sources),
        observed_target_count=len(observed_targets),
        requested_target_count=len(requested_targets),
    )
    summary = {
        "source_file_count": len(sources),
        "soccer_event_count": event_count,
        "target_provider_count": len(target),
        "requested_target_provider_count": len(requested_targets),
        "observed_target_provider_count": len(observed_targets),
        "missing_target_provider_count": len(missing_targets),
        "provider_api_call_count": provider_api_call_count,
        "latest_capture_utc": latest_capture_utc,
        "quota_remaining": quota_remaining,
        "target_providers": list(target),
        "requested_target_providers": requested_targets,
        "observed_target_providers": observed_targets,
        "missing_target_providers": missing_targets,
        "observed_providers": sorted(observed_counter),
    }
    return {
        "schema_version": 1,
        "run_id": run_id or _stable_run_id(source_rows, target),
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
        "paid_calls": False,
        "database_writes": False,
        "raw_provider_payload_copied": False,
        "safety": {
            "provider_api_calls": provider_api_call_count > 0,
            "paid_calls": False,
            "database_writes": False,
            "account_or_order_paths": False,
            "market_execution": False,
            "raw_provider_payload_copied": False,
            "api_key_printed": False,
        },
        "policy": {
            "purpose": "Prove whether soccer Asian sharp anchors are locally available.",
            "target_providers": list(target),
            "soccer_sport_keys": sorted(soccer_keys),
            "maturity_boundary": (
                "This artifact can clear the provider-source blocker only when at least one "
                "target provider is observed in a timestamped soccer feed. It never creates "
                "probabilities, EV, paper stakes, or live eligibility."
            ),
        },
        "summary": summary,
        "source_rows": source_rows,
        "target_provider_rows": target_provider_rows,
        "next_action": _next_action(status, missing_targets),
    }


def render_soccer_asian_provider_diagnostic_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# Soccer Asian Sharp Provider Diagnostic",
        "",
        f"- Status: `{report.get('status')}`",
        "- Mode: research-only",
        "- Execution enabled: `false`",
        "",
        "## Summary",
        "",
        f"- Source files: `{summary.get('source_file_count')}`",
        f"- Soccer events inspected: `{summary.get('soccer_event_count')}`",
        f"- Target providers: `{summary.get('target_providers')}`",
        f"- Requested target providers: `{summary.get('requested_target_providers')}`",
        f"- Observed target providers: `{summary.get('observed_target_providers')}`",
        f"- Missing target providers: `{summary.get('missing_target_providers')}`",
        f"- Provider API call artifacts: `{summary.get('provider_api_call_count')}`",
        f"- Latest capture UTC: `{summary.get('latest_capture_utc')}`",
        f"- Quota remaining: `{summary.get('quota_remaining')}`",
        "",
        "## Source Rows",
        "",
    ]
    for row in report.get("source_rows", []):
        if isinstance(row, Mapping):
            lines.append(
                "- "
                f"`{row.get('source_id')}` events `{row.get('soccer_event_count')}` "
                f"requested `{row.get('requested_target_providers')}` "
                f"observed targets `{row.get('observed_target_providers')}`"
            )
    next_action = (
        report.get("next_action") if isinstance(report.get("next_action"), Mapping) else {}
    )
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            f"- Name: `{next_action.get('name')}`",
            f"- Why: {next_action.get('why')}",
            f"- Stop condition: {next_action.get('stop_condition')}",
            "",
            "> Diagnostic only. No probability, stake, order, account, or execution path is authorized by this artifact.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _status(*, source_count: int, observed_target_count: int, requested_target_count: int) -> str:
    if source_count <= 0:
        return "soccer_asian_provider_diagnostic_blocked_missing_raw_inputs"
    if observed_target_count > 0:
        return "soccer_asian_provider_diagnostic_ready_with_asian_sharp_rows"
    if requested_target_count > 0:
        return "soccer_asian_provider_diagnostic_blocked_target_books_unavailable_in_feed"
    return "soccer_asian_provider_diagnostic_blocked_target_books_not_requested"


def _next_action(status: str, missing_targets: Sequence[str]) -> dict[str, str]:
    if status == "soccer_asian_provider_diagnostic_ready_with_asian_sharp_rows":
        return {
            "name": "kalshi_sports_consensus_soccer_adapter_with_asian_anchor",
            "why": "At least one target Asian sharp soccer provider is present in local source rows.",
            "stop_condition": "Stop before treating provider presence as OOS/FDR evidence.",
        }
    if status == "soccer_asian_provider_diagnostic_blocked_missing_raw_inputs":
        return {
            "name": "kalshi_sports_consensus_soccer_asian_provider_probe",
            "why": "No local soccer provider payload was available to inspect.",
            "stop_condition": "Stop before claiming soccer provider maturity from stale or absent source files.",
        }
    if status == "soccer_asian_provider_diagnostic_blocked_target_books_not_requested":
        return {
            "name": "kalshi_sports_consensus_soccer_asian_provider_probe",
            "why": "Local soccer payloads exist, but the Asian target provider set was not explicitly requested.",
            "stop_condition": "Stop before treating non-Asian exchange coverage as a substitute for the Asian sharp source requirement.",
        }
    return {
        "name": "source_legal_soccer_asian_sharp_feed",
        "why": (
            "The current legal feed was explicitly probed for "
            f"{', '.join(missing_targets)} and returned no target provider rows."
        ),
        "stop_condition": "Stop before downgrading or bypassing the soccer Asian sharp maturity rule.",
    }


def _requested_target_providers(meta: Mapping[str, Any], target: Sequence[str]) -> set[str]:
    requested = {
        normalize_provider_id(item)
        for item in meta.get("bookmakers", [])
        if isinstance(item, str) and item.strip()
    }
    request = meta.get("request") if isinstance(meta.get("request"), Mapping) else {}
    params = request.get("params") if isinstance(request.get("params"), Mapping) else {}
    for item in str(params.get("bookmakers") or "").split(","):
        if item.strip():
            requested.add(normalize_provider_id(item))
    target_set = set(target)
    return {provider_id for provider_id in requested if provider_id in target_set}


def _soccer_events(payload: Any, *, soccer_keys: set[str]) -> list[Mapping[str, Any]]:
    rows = payload if isinstance(payload, list) else []
    out: list[Mapping[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if _canonical_sport_key(row.get("sport_key")) in soccer_keys:
            out.append(row)
    return out


def _market_keys(bookmaker: Mapping[str, Any]) -> str:
    keys = [
        str(market.get("key"))
        for market in bookmaker.get("markets", [])
        if isinstance(market, Mapping) and market.get("key")
    ]
    return ",".join(sorted(set(keys)))


def _canonical_sport_key(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text.startswith("soccer"):
        return text
    return text


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _stable_run_id(rows: Sequence[Mapping[str, Any]], target: Sequence[str]) -> str:
    payload = {"rows": list(rows), "target": list(target)}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return f"soccer-asian-provider-diagnostic-{digest[:12]}"


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
