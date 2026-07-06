"""Optional MLB-platform artifact bridge for sports signal features.

This module deliberately consumes files, not Python imports from
``/home/mrwatson/projects/mlb-platform``. The MLB platform can produce richer
baseball model rows, but predmarket keeps the dependency boundary at a safe,
research-only artifact.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from predmarket.external_artifact_bridge import load_external_artifact
from predmarket.shared_helpers import outside_repo, probability, sha256_or_none

CONTROL_REPO = Path(__file__).resolve().parents[1]
SERIES_TO_LEAGUE = {"KXMLBGAME": "MLB", "KXKBOGAME": "KBO", "KXLMBGAME": "LMB"}


def load_mlb_platform_model_bridge(path: Path | None) -> dict[str, Any]:
    """Load an optional MLB-platform model artifact without a repo dependency."""
    if path is None:
        return {
            "status": "mlb_platform_model_bridge_not_configured",
            "path": None,
            "safe": False,
            "row_count": 0,
            "rows": [],
            "outside_repo": None,
        }
    loaded = load_external_artifact(
        path=path,
        source_repo_id="mlb-platform",
        family_id="sports_baseball",
        control_repo=CONTROL_REPO,
        model_id="mlb_platform_model",
        requires_exact_contract_mapping=False,
        require_outside_repo=False,
    )
    if loaded["status"] == "external_artifact_missing":
        return {
            "status": "mlb_platform_model_bridge_missing",
            "path": str(path),
            "safe": False,
            "row_count": 0,
            "rows": [],
            "outside_repo": outside_repo(path, CONTROL_REPO),
        }
    if not loaded.get("safe"):
        return {
            "status": "mlb_platform_model_bridge_unsafe_ignored",
            "path": str(path),
            "safe": False,
            "row_count": 0,
            "rows": [],
            "outside_repo": outside_repo(path, CONTROL_REPO),
            "sha256": sha256_or_none(path),
            "external_artifact_preflight": loaded.get("preflight"),
        }
    rows = loaded.get("rows") if isinstance(loaded.get("rows"), list) else []
    return {
        "status": "mlb_platform_model_bridge_loaded" if rows else "mlb_platform_model_bridge_empty",
        "path": str(path),
        "safe": True,
        "row_count": len(rows),
        "rows": rows,
        "outside_repo": outside_repo(path, CONTROL_REPO),
        "sha256": sha256_or_none(path),
        "source_status": loaded.get("source_status"),
        "source_repo_id": "mlb-platform",
        "family_id": "sports_baseball",
        "external_artifact_preflight": loaded.get("preflight"),
    }


def _bridge_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in ("rows", "feature_rows", "predictions", "model_rows"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, Mapping)]
    return []


def mlb_platform_model_index(bridge: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Build exact and fallback match keys for MLB-platform model rows."""
    index: dict[str, Mapping[str, Any]] = {}
    rows = bridge.get("rows", [])
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, Mapping):
            continue
        contract = str(row.get("contract_ticker") or "").strip()
        if contract:
            index[f"contract:{contract}"] = row
        league = str(row.get("league") or row.get("sport_league") or "").strip().upper()
        external = str(
            row.get("external_game_id") or row.get("game_pk") or row.get("gamePk") or ""
        ).strip()
        selected = str(row.get("selected_code") or row.get("team_code") or "").strip().upper()
        if league and external and selected:
            index[f"external:{league}:{external}:{selected}"] = row
        event = str(row.get("event_ticker") or "").strip()
        if event and selected:
            index[f"event:{event}:{selected}"] = row
    return index


def attach_mlb_platform_model(
    *,
    row: Mapping[str, Any],
    identity: Mapping[str, Any],
    selected_code: str | None,
    home_code: str | None,
    away_code: str | None,
    yes_ask: float | None,
    tau: float,
    bridge: Mapping[str, Any],
    index: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Return deterministic MLB-platform bridge fields for a feature row."""
    base = {
        "mlb_platform_model_status": bridge.get("status") or "mlb_platform_model_bridge_missing",
        "mlb_platform_model_probability": None,
        "mlb_platform_predicted_side": None,
        "mlb_platform_threshold_delta": None,
        "mlb_platform_model_id": None,
        "mlb_platform_match_key": None,
        "mlb_platform_model_artifact": bridge.get("path"),
        "mlb_platform_model_artifact_sha256": bridge.get("sha256"),
    }
    if bridge.get("status") != "mlb_platform_model_bridge_loaded":
        return base

    contract_key = f"contract:{row.get('ticker')}"
    league = SERIES_TO_LEAGUE.get(str(row.get("series_ticker") or "").upper(), "")
    external_key = f"external:{league}:{identity.get('external_game_id')}:{selected_code}"
    event_key = f"event:{row.get('event_ticker')}:{selected_code}"
    model_row = index.get(contract_key) or index.get(external_key) or index.get(event_key)
    match_key = (
        contract_key
        if contract_key in index
        else external_key
        if external_key in index
        else event_key
        if event_key in index
        else None
    )
    if model_row is None:
        base["mlb_platform_model_status"] = "mlb_platform_model_not_matched"
        return base

    probability_value = selected_model_probability(
        model_row,
        selected_code=selected_code,
        home_code=home_code,
        away_code=away_code,
    )
    if probability_value is None:
        base["mlb_platform_model_status"] = "mlb_platform_model_probability_missing"
        base["mlb_platform_match_key"] = match_key
        base["mlb_platform_model_id"] = model_row.get("model_id") or model_row.get(
            "source_model_id"
        )
        return base

    predicted = _prediction_rule(probability_value, yes_ask, tau)
    return {
        **base,
        "mlb_platform_model_status": "mlb_platform_model_ready",
        "mlb_platform_model_probability": probability_value,
        "mlb_platform_predicted_side": predicted,
        "mlb_platform_threshold_delta": round(abs(probability_value - (yes_ask or 0.0)), 6)
        if yes_ask is not None
        else None,
        "mlb_platform_model_id": model_row.get("model_id")
        or model_row.get("source_model_id")
        or "mlb_platform_model",
        "mlb_platform_match_key": match_key,
    }


def selected_model_probability(
    row: Mapping[str, Any],
    *,
    selected_code: str | None,
    home_code: Any,
    away_code: Any,
) -> float | None:
    for key in (
        "selected_win_probability",
        "selected_team_win_probability",
        "model_probability",
        "win_probability",
        "probability",
    ):
        value = probability(row.get(key))
        if value is not None:
            return value
    home_prob = probability(row.get("home_win_probability"))
    if home_prob is None:
        return None
    if selected_code and str(selected_code).upper() == str(home_code or "").upper():
        return home_prob
    if selected_code and str(selected_code).upper() == str(away_code or "").upper():
        return round(1.0 - home_prob, 6)
    return None


def _prediction_rule(
    win_probability: float | None, yes_ask: float | None, tau: float
) -> str | None:
    if win_probability is None or yes_ask is None:
        return None
    delta = win_probability - yes_ask
    if delta >= tau:
        return "yes"
    if delta <= -tau:
        return "no"
    return None
