"""Safe wrappers for external donor artifacts entering the Kalshi EV engine."""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from predmarket.shared_helpers import probability, sha256_or_none, utc_now
from predmarket.source_inventory import SourceRepoDescriptor

DEFAULT_WRAP_ROOT = Path("/home/mrwatson/manual_drops/predmarket_external_artifacts")
ARTIFACT_KIND_PATTERNS = (
    ("kalshi_ev_contract_mappings", "contract_mapping_overlay"),
    ("kalshi_ev_probabilities", "probability_overlay"),
    ("fair-line-review", "fair_line_review"),
    ("historical-line-backtest", "historical_line_backtest"),
    ("calibration-overlay", "calibration_overlay"),
    ("betexplorer", "closing_comparison"),
    ("settled-outcome-validation", "settled_validation"),
    ("kalshi-forward-oos-liquidity", "forward_oos_liquidity"),
    ("kalshi-forward-oos-price-observations", "forward_oos_price_observations"),
    ("kalshi-forward-oos", "forward_oos_report"),
    ("nba-market-claim-gate", "market_claim_gate"),
)
ARTIFACT_KIND_FILE_PATTERNS = (
    ("matches-", "kalshi_match_snapshot"),
    ("public_snapshot_adapter_audit", "public_snapshot_adapter_audit"),
    ("daily_gate_summary", "daily_gate_summary"),
)


def wrap_descriptor_artifacts(
    descriptor: SourceRepoDescriptor,
    *,
    wrap_root: Path = DEFAULT_WRAP_ROOT,
    generated_utc: str | None = None,
) -> list[dict[str, Any]]:
    return [
        wrap_external_artifact(
            source_repo_id=descriptor.repo_id,
            family_id=descriptor.family_ids[0] if descriptor.family_ids else "unknown",
            source_path=Path(source_path),
            wrap_root=wrap_root,
            generated_utc=generated_utc,
        )
        for source_path in descriptor.admissible_artifacts
    ]


def wrap_external_artifact(
    *,
    source_repo_id: str,
    family_id: str,
    source_path: Path,
    wrap_root: Path = DEFAULT_WRAP_ROOT,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    if not source_path.exists():
        return {
            "status": "external_artifact_wrap_blocked_missing_source",
            "source_repo_id": source_repo_id,
            "family_id": family_id,
            "source_path": str(source_path),
            "wrapped": False,
            "wrapped_path": None,
            "row_count": 0,
            "errors": ["source path missing"],
        }
    source_sha = sha256_or_none(source_path)
    payload = read_source_payload(source_path)
    rows = normalized_rows(
        payload,
        source_repo_id=source_repo_id,
        family_id=family_id,
        source_path=source_path,
        source_sha256=source_sha or "",
    )
    kind = artifact_kind(source_path)
    wrapped_payload = {
        "schema_version": 1,
        "generated_utc": generated_utc or utc_now(),
        "status": "external_artifact_wrapped" if rows else "external_artifact_wrapped_empty",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "source_repo_id": source_repo_id,
        "family_id": family_id,
        "model_id": model_id_for(source_repo_id, source_path),
        "artifact_kind": kind,
        "external_manifest": {
            "schema_version": 1,
            "source_repo_id": source_repo_id,
            "source_path": str(source_path),
            "artifact_sha256": source_sha,
            "family_id": family_id,
            "model_id": model_id_for(source_repo_id, source_path),
            "artifact_kind": kind,
            "generated_utc": source_generated_utc(payload),
            "requires_exact_contract_mapping": requires_exact_contract_mapping(source_path),
        },
        "summary": {
            "source_status": source_status(payload),
            "source_row_count": source_row_count(payload),
            "wrapped_row_count": len(rows),
        },
        "rows": rows,
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "paper_sizing_only": False,
            "runtime_dependency_imports_from_donor_repos": False,
        },
    }
    wrapped_path = wrapped_artifact_path(
        source_repo_id=source_repo_id,
        source_path=source_path,
        source_sha256=source_sha or "missing",
        wrap_root=wrap_root,
    )
    wrapped_payload["external_manifest"]["wrapper_path"] = str(wrapped_path)
    wrapped_path.parent.mkdir(parents=True, exist_ok=True)
    wrapped_path.write_text(
        json.dumps(wrapped_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "status": wrapped_payload["status"],
        "source_repo_id": source_repo_id,
        "family_id": family_id,
        "source_path": str(source_path),
        "source_sha256": source_sha,
        "artifact_kind": kind,
        "model_id": model_id_for(source_repo_id, source_path),
        "wrapped": True,
        "wrapped_path": str(wrapped_path),
        "row_count": len(rows),
        "errors": [],
    }


def read_source_payload(path: Path) -> Any:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def normalized_rows(
    payload: Any,
    *,
    source_repo_id: str,
    family_id: str,
    source_path: Path,
    source_sha256: str,
) -> list[dict[str, Any]]:
    raw_rows = extract_rows(payload)
    if not raw_rows:
        raw_rows = summary_rows(payload)
    rows = [
        normalize_row(
            row,
            index=index,
            source_repo_id=source_repo_id,
            family_id=family_id,
            source_path=source_path,
            source_sha256=source_sha256,
        )
        for index, row in enumerate(raw_rows)
        if isinstance(row, Mapping)
    ]
    return [row for row in rows if row]


def extract_rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in (
        "rows",
        "probability_rows",
        "mapping_rows",
        "top_rows",
        "top_settled_rows",
        "candidates",
        "observations",
        "latest_observations",
        "matches",
        "market_summary",
        "blocker_resolution_counts",
        "blocker_type_counts",
        "gates",
    ):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return [row for row in value if isinstance(row, Mapping)]
    return []


def summary_rows(payload: Any) -> list[Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    row = {
        "source_status": source_status(payload),
        "summary": summary,
    }
    for key in (
        "status",
        "verdict",
        "ready",
        "paper_trading_only",
        "live_execution_enabled",
        "readiness_completion_blockers",
        "freshness_blockers",
        "manifest_integrity_failures",
        "live_safety_failures",
    ):
        if key in payload:
            row[key] = payload.get(key)
    return [row]


def normalize_row(
    row: Mapping[str, Any],
    *,
    index: int,
    source_repo_id: str,
    family_id: str,
    source_path: Path,
    source_sha256: str,
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "source_repo_id": source_repo_id,
        "family_id": family_id,
        "model_id": model_id_for(source_repo_id, source_path),
        "artifact_kind": artifact_kind(source_path),
        "source_path": str(source_path),
        "source_sha256": source_sha256,
        "source_row_index": index,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "usable": False,
        "paper_usable": False,
    }
    output.update(contract_identity(row))
    output.update(selection_identity(row))
    output.update(probability_fields(row))
    output.update(outcome_fields(row))
    output["source_status"] = str(
        row.get("status") or row.get("gate_verdict") or row.get("direction_result") or ""
    )
    output["source_payload"] = compact_payload(row)
    return output


def contract_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    ticker = first_value(
        row,
        "contract_ticker",
        "kalshi_ticker",
        "selected_market_ticker",
        "market_ticker",
        "exchange_market_id",
        "kalshi_market_id",
        "kalshi_market_id_a",
    )
    side = str(first_value(row, "side", "selected_side", "hypothetical_side") or "").lower()
    if ticker and side not in {"yes", "no"}:
        side = "yes" if ticker else ""
    output: dict[str, Any] = {}
    if ticker:
        output["contract_ticker"] = str(ticker)
    event = first_value(row, "event_ticker", "_kalshi_event_ticker", "game_id", "game")
    if event:
        output["event_ticker"] = str(event)
    if side in {"yes", "no"}:
        output["side"] = side
    return output


def selection_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key in (
        "game",
        "match_label",
        "selection",
        "selected_player",
        "selected_team",
        "home_team",
        "away_team",
        "market",
        "line",
        "adapter_id",
        "dataset",
        "source",
    ):
        if key in row and row.get(key) not in (None, ""):
            output[key] = row.get(key)
    return output


def probability_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    model_value = first_probability(
        row,
        "calibrated_probability",
        "model_probability",
        "model_prob_home",
        "entry_model_prob",
        "entry_model_probability",
        "probability",
    )
    market_value = first_probability(
        row,
        "market_probability",
        "market_prob_home",
        "closing_home_prob",
        "exchange_prob",
        "entry_kalshi_price",
        "kalshi_price_a",
        "close_kalshi_price",
        "executable_price",
    )
    if model_value is not None:
        output["model_probability"] = model_value
    if market_value is not None:
        output["market_probability"] = market_value
    if probability(row.get("calibrated_probability")) is not None:
        output["calibrated_probability"] = probability(row.get("calibrated_probability"))
    for key in ("expected_value_per_contract", "net_edge", "raw_edge", "entry_edge_pp"):
        value = row.get(key)
        if isinstance(value, int | float):
            output[key] = value
    return output


def outcome_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    result = str(row.get("settlement_result") or row.get("outcome_for_side") or "").lower()
    if result in {"win", "won"}:
        return {"settled_outcome": 1}
    if result in {"loss", "lost"}:
        return {"settled_outcome": 0}
    return {}


def compact_payload(row: Mapping[str, Any], *, limit: int = 40) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for index, (key, value) in enumerate(row.items()):
        if index >= limit:
            break
        if isinstance(value, str | int | float | bool) or value is None:
            output[str(key)] = value
        elif isinstance(value, Mapping):
            output[str(key)] = {
                str(child_key): child_value
                for child_key, child_value in value.items()
                if isinstance(child_value, str | int | float | bool) or child_value is None
            }
    return output


def first_value(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def first_probability(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = probability(row.get(key))
        if value is not None:
            return value
    return None


def source_generated_utc(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    value = (
        payload.get("generated_utc")
        or payload.get("generated_at")
        or payload.get("captured_at")
        or payload.get("created_at_utc")
    )
    return str(value) if value else None


def source_status(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    value = payload.get("status") or payload.get("verdict")
    return str(value) if value else None


def source_row_count(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, Mapping):
        return 0
    for key in ("row_count", "n_matches", "n_resolved"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    return len(extract_rows(payload))


def artifact_kind(path: Path) -> str:
    text = str(path)
    for pattern, kind in ARTIFACT_KIND_PATTERNS:
        if pattern in text:
            return kind
    for pattern, kind in ARTIFACT_KIND_FILE_PATTERNS:
        if pattern in path.name:
            return kind
    return "generic_external_artifact"


def model_id_for(source_repo_id: str, path: Path) -> str:
    kind = artifact_kind(path)
    return f"{source_repo_id}:{kind}"


def requires_exact_contract_mapping(path: Path) -> bool:
    kind = artifact_kind(path)
    return kind in {
        "contract_mapping_overlay",
        "probability_overlay",
        "closing_comparison",
        "settled_validation",
        "forward_oos_report",
        "kalshi_match_snapshot",
    }


def wrapped_artifact_path(
    *,
    source_repo_id: str,
    source_path: Path,
    source_sha256: str,
    wrap_root: Path,
) -> Path:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(source_path).strip("/"))[-140:]
    return wrap_root / source_repo_id / f"{slug}-{source_sha256[:12]}.json"


def wrap_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    wrapped = [row for row in rows if row.get("wrapped")]
    return {
        "source_artifact_count": len(rows),
        "wrapped_artifact_count": len(wrapped),
        "blocked_artifact_count": len(rows) - len(wrapped),
        "wrapped_row_count": sum(int(row.get("row_count") or 0) for row in wrapped),
    }
