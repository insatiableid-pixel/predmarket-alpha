"""Generic external artifact bridge for research-only donor inputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from predmarket.shared_helpers import (
    outside_repo,
    probability,
    read_json_or_empty,
    safe_research_artifact,
    sha256_or_none,
)


@dataclass(frozen=True, slots=True)
class ExternalArtifactManifest:
    source_repo_id: str
    source_path: str
    artifact_sha256: str
    family_id: str
    model_id: str | None = None
    schema_version: int = 1
    requires_exact_contract_mapping: bool = False
    generated_utc: str | None = None
    artifact_kind: str | None = None
    wrapper_path: str | None = None


def build_file_manifest(
    *,
    source_repo_id: str,
    path: Path,
    family_id: str,
    model_id: str | None = None,
    requires_exact_contract_mapping: bool = False,
    generated_utc: str | None = None,
) -> ExternalArtifactManifest | None:
    digest = sha256_or_none(path)
    if digest is None:
        return None
    return ExternalArtifactManifest(
        source_repo_id=source_repo_id,
        source_path=str(path),
        artifact_sha256=digest,
        family_id=family_id,
        model_id=model_id,
        requires_exact_contract_mapping=requires_exact_contract_mapping,
        generated_utc=generated_utc,
    )


def manifest_from_payload(
    payload: Mapping[str, Any],
    fallback: ExternalArtifactManifest | None,
) -> ExternalArtifactManifest | None:
    manifest_payload = payload.get("external_manifest")
    if not isinstance(manifest_payload, Mapping):
        return fallback
    source_path = str(manifest_payload.get("source_path") or "").strip()
    artifact_sha256 = str(
        manifest_payload.get("artifact_sha256") or manifest_payload.get("source_sha256") or ""
    ).strip()
    return ExternalArtifactManifest(
        source_repo_id=str(manifest_payload.get("source_repo_id") or "").strip(),
        source_path=source_path,
        artifact_sha256=artifact_sha256,
        family_id=str(manifest_payload.get("family_id") or "").strip(),
        model_id=str(manifest_payload.get("model_id") or "").strip() or None,
        schema_version=int(manifest_payload.get("schema_version") or 1),
        requires_exact_contract_mapping=bool(
            manifest_payload.get("requires_exact_contract_mapping")
        ),
        generated_utc=str(manifest_payload.get("generated_utc") or "").strip() or None,
        artifact_kind=str(manifest_payload.get("artifact_kind") or "").strip() or None,
        wrapper_path=str(manifest_payload.get("wrapper_path") or "").strip() or None,
    )


def validate_external_artifact(
    *,
    payload: Mapping[str, Any],
    manifest: ExternalArtifactManifest | None,
    control_repo: Path,
    require_outside_repo: bool = True,
) -> dict[str, Any]:
    errors: list[str] = []
    if manifest is None:
        errors.append("missing artifact sha256 or source path")
    else:
        errors.extend(validate_manifest(manifest))
        if require_outside_repo and not outside_repo(Path(manifest.source_path), control_repo):
            errors.append("external artifact path is inside control repo")
        source_sha256 = sha256_or_none(Path(manifest.source_path))
        if source_sha256 is None:
            errors.append("manifest source_path is missing")
        elif source_sha256 != manifest.artifact_sha256:
            errors.append("manifest source_path sha256 does not match artifact_sha256")
    if not safe_research_artifact(payload):
        errors.append("artifact is not a safe research-only artifact")
    rows = artifact_rows(payload)
    if manifest and manifest.requires_exact_contract_mapping:
        errors.extend(validate_exact_contract_rows(rows))
    errors.extend(validate_probability_rows(rows))
    return {
        "status": "external_artifact_preflight_pass"
        if not errors
        else "external_artifact_preflight_blocked",
        "safe": not errors,
        "errors": errors,
        "row_count": len(rows),
        "manifest": asdict(manifest) if manifest else None,
    }


def validate_manifest(manifest: ExternalArtifactManifest) -> list[str]:
    errors: list[str] = []
    if not manifest.source_repo_id.strip():
        errors.append("source_repo_id is required")
    if not manifest.source_path.strip():
        errors.append("source_path is required")
    if not manifest.artifact_sha256.strip():
        errors.append("artifact_sha256 is required")
    if not manifest.family_id.strip():
        errors.append("family_id is required")
    if manifest.schema_version < 1:
        errors.append("schema_version must be >= 1")
    return errors


def artifact_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in ("rows", "feature_rows", "predictions", "model_rows", "candidates"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, Mapping)]
    return []


def validate_exact_contract_rows(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    for index, row in enumerate(rows):
        ticker = str(row.get("contract_ticker") or row.get("kalshi_ticker") or "").strip()
        side = str(row.get("side") or row.get("selected_side") or "").strip().lower()
        if not ticker:
            errors.append(f"row {index} missing exact contract_ticker")
        if side not in {"yes", "no"}:
            errors.append(f"row {index} missing side yes/no")
    return errors


def validate_probability_rows(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    for index, row in enumerate(rows):
        for key in (
            "calibrated_probability",
            "model_probability",
            "win_probability",
            "selected_win_probability",
            "selected_team_win_probability",
            "probability",
        ):
            if key in row and row.get(key) is not None and probability(row.get(key)) is None:
                errors.append(f"row {index} has malformed probability field {key}")
    return errors


def load_external_artifact(
    *,
    path: Path | None,
    source_repo_id: str,
    family_id: str,
    control_repo: Path,
    model_id: str | None = None,
    requires_exact_contract_mapping: bool = False,
    require_outside_repo: bool = True,
) -> dict[str, Any]:
    if path is None:
        return {
            "status": "external_artifact_not_configured",
            "safe": False,
            "path": None,
            "row_count": 0,
            "rows": [],
            "preflight": {
                "status": "external_artifact_preflight_blocked",
                "errors": ["path not configured"],
            },
        }
    if not path.exists():
        return {
            "status": "external_artifact_missing",
            "safe": False,
            "path": str(path),
            "row_count": 0,
            "rows": [],
            "outside_repo": outside_repo(path, control_repo),
            "preflight": {
                "status": "external_artifact_preflight_blocked",
                "errors": ["path missing"],
            },
        }
    payload = read_json_or_empty(path)
    manifest = build_file_manifest(
        source_repo_id=source_repo_id,
        path=path,
        family_id=family_id,
        model_id=model_id,
        requires_exact_contract_mapping=requires_exact_contract_mapping,
        generated_utc=str(payload.get("generated_utc") or "") or None,
    )
    manifest = manifest_from_payload(payload, manifest)
    preflight = validate_external_artifact(
        payload=payload,
        manifest=manifest,
        control_repo=control_repo,
        require_outside_repo=require_outside_repo,
    )
    rows = artifact_rows(payload) if preflight["safe"] else []
    return {
        "status": "external_artifact_loaded"
        if rows
        else "external_artifact_empty"
        if preflight["safe"]
        else "external_artifact_unsafe_ignored",
        "safe": preflight["safe"],
        "path": str(path),
        "sha256": sha256_or_none(path),
        "row_count": len(rows),
        "rows": rows,
        "outside_repo": outside_repo(path, control_repo),
        "source_status": payload.get("status"),
        "preflight": preflight,
    }
