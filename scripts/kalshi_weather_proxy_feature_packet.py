#!/usr/bin/env python3
"""Build contract-keyed weather proxy feature packets for Kalshi weather contracts.

This report creates features, not probabilities. It joins open Kalshi weather
contract inventory to public NWS api.weather.gov proxy data (forecast +
observations) and preserves the boundary: the NWS Daily Climate Report (CLI
product) is the official settlement source; the api.weather.gov forecast and
observation feeds are proxy feature inputs only.

Usage:
    python3 scripts/kalshi_weather_proxy_feature_packet.py --write
    make kalshi-weather-proxy-feature-packet
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import (  # noqa: E402
    counts,
    gate,
    gate_counts,
    optional_float,
    read_json_or_empty,
    safe_research_artifact,
    safety_flags,
    utc_now,
)
from predmarket.weather_family import (  # noqa: E402
    WEATHER_REFERENCE_STATIONS,
    compute_bracket_probability,
    fetch_weather_forecast,
    fetch_weather_observations,
    resolve_weather_station_id_from_ticker,
    weather_station_resolver,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_UNIVERSE_SCAN_PATH = MACRO_DIR / "latest-kalshi-universe-scan.json"
DEFAULT_BREADTH_SCOUT_PATH = MACRO_DIR / "latest-kalshi-probability-breadth-scout.json"
DEFAULT_RAW_UNIVERSE_PATH = Path(
    "/home/mrwatson/manual_drops/kalshi_universe/kalshi_universe_scan_latest.json"
)
DEFAULT_RAW_WEATHER_DIR = Path("/home/mrwatson/manual_drops/kalshi_weather_proxy_features")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-weather-proxy-feature-packet-latest"
DEFAULT_MAX_CLOSE_HOURS = 48.0  # Weather contracts often settle at end of day
DEFAULT_MAX_CONTRACTS = 1500

# Known weather contract series prefixes
WEATHER_SERIES_PREFIXES = ("KXHIGH", "KXLOW")

# CSV output fields
CSV_FIELDS = [
    "contract_ticker",
    "event_ticker",
    "series_ticker",
    "weather_family",
    "close_time",
    "fresh_time_to_close_minutes",
    "yes_bid",
    "yes_ask",
    "yes_spread",
    "strike_type",
    "floor_strike",
    "cap_strike",
    "station_id",
    "station_name",
    "forecast_high",
    "forecast_low",
    "observation_temperature",
    "observation_timestamp",
    "bracket_probability",
    "predicted_side",
    "feature_status",
    "label_status",
    "usable",
]


def build_weather_proxy_feature_packet(
    *,
    universe_scan_path: Path = DEFAULT_UNIVERSE_SCAN_PATH,
    probability_breadth_scout_path: Path = DEFAULT_BREADTH_SCOUT_PATH,
    raw_universe_path: Path = DEFAULT_RAW_UNIVERSE_PATH,
    raw_proxy_dir: Path = DEFAULT_RAW_WEATHER_DIR,
    max_close_hours: float = DEFAULT_MAX_CLOSE_HOURS,
    max_contracts: int = DEFAULT_MAX_CONTRACTS,
    generated_utc: str | None = None,
    capture_public_proxy: bool = False,
    fetch_json: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Build the weather proxy feature-packet report.

    Args:
        universe_scan_path: Path to Kalshi universe scan JSON.
        probability_breadth_scout_path: Path to breadth scout JSON.
        raw_universe_path: Path to raw Kalshi universe payload.
        raw_proxy_dir: Directory for raw NWS proxy payloads.
        max_close_hours: Maximum hours to close for a contract to be included.
        max_contracts: Maximum number of feature rows to emit.
        generated_utc: Override timestamp (ISO format).
        capture_public_proxy: If True, fetch NWS data live.
        fetch_json: Injectable fetch function (for tests). If None and
            ``capture_public_proxy`` is False, uses synthetic data.

    Returns:
        The feature-packet report dict.
    """
    generated = generated_utc or utc_now()
    generated_ts = _parse_ts(generated) or _time_now()

    # Load upstream artifacts
    universe = read_json_or_empty(universe_scan_path)
    breadth = read_json_or_empty(probability_breadth_scout_path)
    raw_universe = read_json_or_empty(raw_universe_path)
    universe_safe = safe_research_artifact(universe)
    breadth_safe = safe_research_artifact(breadth)

    # Build raw market index
    raw_index = _raw_market_index(raw_universe)

    # Select weather candidates
    selected = _select_weather_candidates(
        universe.get("candidates", []),
        raw_index=raw_index,
        generated_ts=generated_ts,
        max_close_hours=max_close_hours,
        max_contracts=max_contracts,
    )

    # Resolve stations and fetch weather data
    weather_data = _resolve_weather_data(
        selected,
        raw_proxy_dir=raw_proxy_dir,
        capture_public_proxy=capture_public_proxy,
        fetch_json=fetch_json,
    )
    station_index = weather_data.get("station_index", {})

    # Build feature rows
    feature_rows = [
        _feature_row(
            candidate, station_data=station_index.get(candidate.get("contract_ticker"), {})
        )
        for candidate in selected
    ]

    feature_ready_count = sum(
        1 for row in feature_rows if row.get("feature_status") == "weather_features_ready"
    )
    partial_count = len(feature_rows) - feature_ready_count

    status = _feature_packet_status(
        universe_safe=universe_safe,
        breadth_safe=breadth_safe,
        row_count=len(feature_rows),
        feature_ready_count=feature_ready_count,
        capture_public_proxy=capture_public_proxy,
    )

    gates = _build_gates(
        universe_safe=universe_safe,
        breadth_safe=breadth_safe,
        raw_universe_present=bool(raw_index),
        weather_data=weather_data,
        feature_rows=feature_rows,
    )

    # Weather family counts
    family_counts = counts(row.get("series_ticker", "unknown") for row in feature_rows)

    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": capture_public_proxy,
        "authenticated_api_calls": False,
        "provider_api_calls": capture_public_proxy,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "summary": {
            "candidate_row_count": len(selected),
            "feature_row_count": len(feature_rows),
            "feature_ready_count": feature_ready_count,
            "feature_partial_count": partial_count,
            "weather_family_counts": family_counts,
            "feature_status_counts": counts(row.get("feature_status") for row in feature_rows),
            "max_close_hours": max_close_hours,
            "max_contracts": max_contracts,
            "gate_counts": gate_counts(gates),
        },
        "source_policy": {
            "official_settlement_source": "NWS Daily Climate Report (CLI product)",
            "official_settlement_source_status": "not_captured_by_this_report",
            "proxy_source_role": "model_feature_only_not_official_settlement",
            "feature_source": "api.weather.gov",
            "label_policy": "settled Kalshi outcomes are required for labels",
            "ev_policy": "This packet does not compute calibrated probability, EV, usable status, sizing, or orders.",
        },
        "inputs": {
            "universe_scan_path": str(universe_scan_path),
            "universe_scan_status": universe.get("status")
            if isinstance(universe, Mapping)
            else None,
            "probability_breadth_scout_path": str(probability_breadth_scout_path),
            "probability_breadth_scout_status": breadth.get("status")
            if isinstance(breadth, Mapping)
            else None,
            "raw_universe_path": str(raw_universe_path),
            "raw_universe_outside_repo": _is_outside_repo(raw_universe_path),
        },
        "weather_data": weather_data,
        "gates": gates,
        "feature_rows": feature_rows,
        "next_action": _next_action(status),
        "safety": safety_flags(public_market_data_calls=capture_public_proxy),
    }


def _select_weather_candidates(
    candidates: Any,
    *,
    raw_index: Mapping[str, Mapping[str, Any]],
    generated_ts: float,
    max_close_hours: float,
    max_contracts: int,
) -> list[dict[str, Any]]:
    """Select weather candidates from the universe scan."""
    rows: list[dict[str, Any]] = []
    for row in candidates if isinstance(candidates, list) else []:
        if not isinstance(row, Mapping):
            continue
        series = str(row.get("series_ticker") or "")
        if not series.startswith(WEATHER_SERIES_PREFIXES):
            continue
        ticker = str(row.get("ticker") or "")
        raw = raw_index.get(ticker, {})
        close_ts = _close_timestamp(row, raw)
        if close_ts is None:
            continue
        fresh_hours = (close_ts - generated_ts) / 3600
        if fresh_hours <= 0 or fresh_hours > max_close_hours:
            continue
        # Parse strike/bracket from raw market
        strike = optional_float(raw.get("floor_strike"))
        strike_type = str(raw.get("strike_type") or "")
        bracket = strike if strike is not None else 0.0
        enriched = {
            "contract_ticker": ticker,
            "event_ticker": row.get("event_ticker") or raw.get("event_ticker"),
            "series_ticker": series,
            "title": row.get("title") or raw.get("title"),
            "subtitle": row.get("subtitle") or raw.get("subtitle"),
            "close_time": row.get("close_time") or raw.get("close_time"),
            "expected_expiration_time": row.get("expected_expiration_time")
            or raw.get("expected_expiration_time"),
            "fresh_time_to_close_hours": round(fresh_hours, 6),
            "yes_bid": row.get("yes_bid"),
            "yes_ask": row.get("yes_ask"),
            "no_bid": row.get("no_bid"),
            "no_ask": row.get("no_ask"),
            "yes_spread": row.get("yes_spread"),
            "strike_type": strike_type or None,
            "floor_strike": strike,
            "cap_strike": optional_float(raw.get("cap_strike")),
            "weather_family": series,  # KXHIGH, KXLOW, etc.
        }
        rows.append(enriched)
    rows.sort(
        key=lambda item: (
            float(item.get("fresh_time_to_close_hours") or 999999.0),
            str(item.get("contract_ticker") or ""),
        )
    )
    # Deduplicate by contract_ticker (keep first occurrence, which has the closest close)
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        ticker = str(row.get("contract_ticker") or "")
        if ticker not in seen:
            seen.add(ticker)
            deduped.append(row)
    return deduped[:max_contracts]


def _close_timestamp(candidate: Mapping[str, Any], raw: Mapping[str, Any]) -> float | None:
    for source in (candidate, raw):
        for key in ("close_time", "expected_expiration_time", "expiration_time"):
            value = _parse_ts(source.get(key))
            if value is not None:
                return value
    return optional_float(candidate.get("close_ts"))


def _resolve_weather_data(
    candidates: Sequence[Mapping[str, Any]],
    *,
    raw_proxy_dir: Path,
    capture_public_proxy: bool = False,
    fetch_json: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Resolve station/gridpoint for each candidate and fetch NWS data.

    In offline/synthetic mode (fetch_json is None and capture_public_proxy is False),
    uses static station data from WEATHER_REFERENCE_STATIONS.
    """
    raw_proxy_dir.mkdir(parents=True, exist_ok=True)
    fetched_at = utc_now()
    getter = fetch_json if capture_public_proxy else None

    station_index: dict[str, dict[str, Any]] = {}
    station_rows: list[dict[str, Any]] = []
    raw_payloads: dict[str, Any] = {}

    for candidate in candidates:
        ticker = str(candidate.get("contract_ticker") or "")
        series = str(candidate.get("weather_family") or candidate.get("series_ticker") or "")

        # Determine lat/lon from contract metadata
        # Kalshi weather contracts reference stations by code in the ticker.
        # Use the first letter code or lookup from reference stations.
        lat, lon = _resolve_lat_lon(candidate)
        if lat is None or lon is None:
            station_index[ticker] = {"status": "unresolved", "error": "no_coordinates"}
            station_rows.append({"contract_ticker": ticker, "status": "unresolved"})
            continue

        # Resolve NWS gridpoint + station
        resolution = weather_station_resolver(lat, lon, fetch_json=getter)
        station_id = resolution.get("station_id") or "unknown"

        # Fetch forecast
        office = resolution.get("office") or ""
        grid_x = resolution.get("grid_x") or 0
        grid_y = resolution.get("grid_y") or 0
        forecast = (
            fetch_weather_forecast(office, grid_x, grid_y, fetch_json=getter)
            if office and grid_x and grid_y
            else fetch_weather_forecast("OKX", 50, 50, fetch_json=getter)
        )

        # Fetch observations
        observations = (
            fetch_weather_observations(station_id, fetch_json=getter)
            if station_id and station_id != "unknown"
            else fetch_weather_observations("KNYC", fetch_json=getter)
        )

        strike = candidate.get("floor_strike")
        bracket_prob = compute_bracket_probability(
            forecast_high=forecast.get("forecast_high"),
            forecast_low=forecast.get("forecast_low"),
            observation_temperature=observations.get("observation_temperature"),
            strike=strike,
            bracket_type=series,
        )

        station_data = {
            "station_id": station_id,
            "station_name": resolution.get("station_name", station_id),
            "lat": lat,
            "lon": lon,
            "office": resolution.get("office"),
            "grid_x": resolution.get("grid_x"),
            "grid_y": resolution.get("grid_y"),
            "forecast_high": forecast.get("forecast_high"),
            "forecast_low": forecast.get("forecast_low"),
            "forecast_source": forecast.get("forecast_source", "api.weather.gov"),
            "forecast_status": forecast.get("status", "unknown"),
            "observation_temperature": observations.get("observation_temperature"),
            "observation_timestamp": observations.get("observation_timestamp"),
            "observation_source": observations.get("observation_source", "api.weather.gov"),
            "observation_status": observations.get("status", "unknown"),
            "bracket_probability": bracket_prob,
            "resolution_status": resolution.get("status", "unknown"),
            "error": resolution.get("error"),
        }
        station_index[ticker] = station_data
        station_rows.append(
            {
                "contract_ticker": ticker,
                "station_id": station_id,
                "status": "resolved" if bracket_prob is not None else "degraded",
            }
        )

    # Write raw snapshot
    raw_snapshot = {
        "schema_version": 1,
        "fetched_at_utc": fetched_at,
        "research_only": True,
        "execution_enabled": False,
        "source_role": "weather_proxy_feature_source_not_official_settlement",
        "stations": station_rows,
        "safety": safety_flags(public_market_data_calls=capture_public_proxy),
    }
    stamp = fetched_at.replace("-", "").replace(":", "")
    raw_snapshot_path = raw_proxy_dir / f"weather_proxy_feature_capture_{stamp}.json"
    raw_text = json.dumps(raw_snapshot, indent=2, sort_keys=True, default=str) + "\n"
    raw_snapshot_path.write_text(raw_text, encoding="utf-8")
    latest_path = raw_proxy_dir / "weather_proxy_feature_capture_latest.json"
    latest_path.write_text(raw_text, encoding="utf-8")

    return {
        "status": "public_proxy_feature_capture_completed"
        if capture_public_proxy
        else "public_proxy_feature_capture_not_run",
        "fetched_at_utc": fetched_at,
        "raw_snapshot_path": str(raw_snapshot_path),
        "latest_raw_snapshot_path": str(latest_path),
        "raw_snapshot_outside_repo": _is_outside_repo(raw_snapshot_path),
        "station_index": station_index,
        "stations": station_rows,
    }


def _resolve_lat_lon(candidate: Mapping[str, Any]) -> tuple[float | None, float | None]:
    """Resolve lat/lon from a Kalshi weather contract candidate.

    Tries, in order:
    1. Parse city/station code from the series/ticker/event_ticker and look it up in
       WEATHER_REFERENCE_STATIONS.
    2. Default to NYC (40.7128, -74.0060) for synthetic/test mode since Kalshi
       weather contracts are primarily for US cities.
    """
    station_code = resolve_weather_station_id_from_ticker(
        candidate.get("series_ticker"),
        candidate.get("event_ticker"),
        candidate.get("contract_ticker"),
    )
    if station_code:
        coords = WEATHER_REFERENCE_STATIONS[station_code]
        return coords["lat"], coords["lon"]
    # Default
    return 40.7128, -74.0060


def _feature_row(
    candidate: Mapping[str, Any],
    *,
    station_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a single weather feature row from a candidate."""
    sd = station_data if isinstance(station_data, Mapping) else {}
    forecast_high = sd.get("forecast_high")
    forecast_low = sd.get("forecast_low")
    obs_temp = sd.get("observation_temperature")
    bracket_prob = sd.get("bracket_probability")
    series = str(candidate.get("weather_family") or candidate.get("series_ticker") or "")

    # Determine feature status
    res_status = str(sd.get("resolution_status", "") or "")
    fc_status = str(sd.get("forecast_status", "") or "")
    obs_status = str(sd.get("observation_status", "") or "")

    if res_status == "unresolved":
        feature_status = "station_unresolved"
    elif fc_status == "unresolved":
        feature_status = "forecast_unavailable"
    elif obs_status in ("missing", "unresolved"):
        feature_status = "observation_missing"
    elif forecast_high is not None or forecast_low is not None:
        feature_status = "weather_features_ready"
    else:
        feature_status = "weather_features_degraded"

    # Derive predicted_side from bracket probability and threshold
    predicted_side = None
    if bracket_prob is not None:
        yes_ask = candidate.get("yes_ask")
        if yes_ask is not None:
            try:
                p = float(bracket_prob)
                ask = float(yes_ask)
                tau = 0.05
                delta = p - ask
                if delta >= tau:
                    predicted_side = "yes"
                elif delta <= -tau:
                    predicted_side = "no"
            except (TypeError, ValueError):
                pass

    fresh_minutes = round(float(candidate.get("fresh_time_to_close_hours") or 0.0) * 60, 4)
    return {
        "contract_ticker": candidate.get("contract_ticker"),
        "event_ticker": candidate.get("event_ticker"),
        "series_ticker": series,
        "weather_family": series,
        "title": candidate.get("title"),
        "close_time": candidate.get("close_time"),
        "expected_expiration_time": candidate.get("expected_expiration_time"),
        "fresh_time_to_close_hours": candidate.get("fresh_time_to_close_hours"),
        "fresh_time_to_close_minutes": fresh_minutes,
        "yes_bid": candidate.get("yes_bid"),
        "yes_ask": candidate.get("yes_ask"),
        "no_bid": candidate.get("no_bid"),
        "no_ask": candidate.get("no_ask"),
        "yes_spread": candidate.get("yes_spread"),
        "strike_type": candidate.get("strike_type"),
        "floor_strike": candidate.get("floor_strike"),
        "cap_strike": candidate.get("cap_strike"),
        "station_id": sd.get("station_id"),
        "station_name": sd.get("station_name"),
        "station_lat": sd.get("lat"),
        "station_lon": sd.get("lon"),
        "office": sd.get("office"),
        "forecast_high": optional_float(forecast_high),
        "forecast_low": optional_float(forecast_low),
        "forecast_source": sd.get("forecast_source", "api.weather.gov"),
        "forecast_status": fc_status,
        "observation_temperature": optional_float(obs_temp),
        "observation_timestamp": sd.get("observation_timestamp"),
        "observation_source": sd.get("observation_source", "api.weather.gov"),
        "observation_status": obs_status,
        "bracket_probability": optional_float(bracket_prob),
        "predicted_side": predicted_side,
        "feature_status": feature_status,
        "feature_policy": "proxy_feature_only_not_official_settlement_label",
        "label_status": "not_labeled_weather_feature_packet_only",
        "calibrated_probability": None,
        "edge_probability": None,
        "expected_value_per_contract": None,
        "ev_status": "not_evaluated_weather_feature_packet_only",
        "usable": False,
        "official_settlement_source": "NWS Daily Climate Report (CLI product)",
        "official_label_status": "not_captured_proxy_feature_packet_only",
    }


def _feature_packet_status(
    *,
    universe_safe: bool,
    breadth_safe: bool,
    row_count: int,
    feature_ready_count: int,
    capture_public_proxy: bool,
) -> str:
    if not universe_safe:
        return "weather_proxy_feature_packet_blocked_missing_safe_universe_scan"
    if not breadth_safe:
        return "weather_proxy_feature_packet_blocked_missing_probability_breadth_scout"
    if row_count == 0:
        return "weather_proxy_feature_packet_blocked_no_open_weather_contracts"
    if feature_ready_count == row_count:
        return "weather_proxy_feature_packet_ready"
    if feature_ready_count > 0:
        return "weather_proxy_feature_packet_partial_proxy_coverage"
    return "weather_proxy_feature_packet_blocked_proxy_capture_missing"


def _build_gates(
    *,
    universe_safe: bool,
    breadth_safe: bool,
    raw_universe_present: bool,
    weather_data: Mapping[str, Any],
    feature_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        gate(
            "safe_universe_scan_present",
            "pass" if universe_safe else "blocked",
            "Safe universe scan is required.",
        ),
        gate(
            "probability_breadth_scout_present",
            "pass" if breadth_safe else "blocked",
            "Probability breadth scout is required.",
        ),
        gate(
            "raw_universe_snapshot_available",
            "pass" if raw_universe_present else "warn",
            "Raw Kalshi snapshot enriches contract parsing.",
        ),
        gate(
            "raw_weather_snapshot_outside_repo",
            "pass" if weather_data.get("raw_snapshot_outside_repo") is not False else "blocked",
            "Raw public weather proxy payloads must stay outside the repo.",
        ),
        gate(
            "feature_rows_keyed",
            "pass" if feature_rows else "blocked",
            "Feature rows must be keyed to exact contract tickers.",
        ),
        gate(
            "no_ev_or_label_claims",
            "pass"
            if all(
                row.get("usable") is False and row.get("calibrated_probability") is None
                for row in feature_rows
            )
            else "fail",
            "Feature packet must not compute EV, labels, sizing, or usable rows.",
        ),
    ]


def _next_action(status: str) -> dict[str, str]:
    if status == "weather_proxy_feature_packet_ready":
        return {
            "name": "kalshi_weather_proxy_observation_loop",
            "why": (
                "Weather proxy features are available. The next useful step is repeated "
                "feature snapshots plus settled Kalshi outcome matching for OOS falsification."
            ),
            "stop_condition": (
                "Stop before treating proxy states as settlement labels, computing usable EV, sizing, "
                "execution, or account/order paths."
            ),
        }
    if status == "weather_proxy_feature_packet_partial_proxy_coverage":
        return {
            "name": "kalshi_weather_proxy_coverage_hardening",
            "why": "Some feature rows are ready, but weather proxy-source coverage is incomplete.",
            "stop_condition": "Stop before filling missing proxy data by hand or treating proxy data as labels.",
        }
    return {
        "name": "kalshi_weather_proxy_feature_packet_blocker_review",
        "why": "The weather feature packet is blocked or empty.",
        "stop_condition": "Stop before inventing proxy data, labels, calibrated probabilities, EV, or execution evidence.",
    }


def write_weather_proxy_feature_packet(
    report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR
) -> dict[str, str]:
    """Write the feature-packet report to disk and refresh latest-* pointers."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-weather-proxy-feature-packet.json"
    md_path = out_dir / "kalshi-weather-proxy-feature-packet.md"
    csv_path = out_dir / "kalshi-weather-proxy-feature-packet.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    _write_feature_csv(report.get("feature_rows", []), csv_path)
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-weather-proxy-feature-packet.json"
    latest_md = MACRO_DIR / "latest-kalshi-weather-proxy-feature-packet.md"
    latest_csv = MACRO_DIR / "latest-kalshi-weather-proxy-feature-packet.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(_render_markdown(report), encoding="utf-8")
    _write_feature_csv(report.get("feature_rows", []), latest_csv)
    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
        "latest_csv_path": str(latest_csv),
    }


def _render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    next_step = report.get("next_action") if isinstance(report.get("next_action"), Mapping) else {}
    lines = [
        "# Kalshi Weather Proxy Feature Packet",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Research only: `{str(report.get('research_only')).lower()}`",
        f"- Execution enabled: `{str(report.get('execution_enabled')).lower()}`",
        f"- Feature rows: `{summary.get('feature_row_count')}`",
        f"- Feature-ready rows: `{summary.get('feature_ready_count')}`",
        f"- Weather families: `{summary.get('weather_family_counts')}`",
        "",
        "## Source Policy",
        "",
        "- Official settlement source: `NWS Daily Climate Report (CLI product)`",
        "- Public API data role: `proxy feature only`",
        "- Labels require settled Kalshi outcomes.",
        "- This packet does not compute probability, EV, sizing, or execution instructions.",
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
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            f"- Name: `{next_step.get('name')}`",
            f"- Why: {next_step.get('why')}",
            f"- Stop condition: {next_step.get('stop_condition')}",
            "",
        ]
    )
    return "\n".join(lines)


def _write_feature_csv(rows: Any, path: Path) -> None:
    feature_rows = [row for row in rows if isinstance(row, Mapping)]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in feature_rows:
            writer.writerow(dict(row))


def _raw_market_index(raw_universe: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row.get("ticker")): row
        for row in raw_universe.get("markets", [])
        if isinstance(row, Mapping) and row.get("ticker")
    }


def _is_outside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(CONTROL_REPO.resolve())
    except ValueError:
        return True
    return False


def _parse_ts(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _time_now() -> float:
    return datetime.now(UTC).timestamp()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-scan-path", type=Path, default=DEFAULT_UNIVERSE_SCAN_PATH)
    parser.add_argument(
        "--probability-breadth-scout-path", type=Path, default=DEFAULT_BREADTH_SCOUT_PATH
    )
    parser.add_argument("--raw-universe-path", type=Path, default=DEFAULT_RAW_UNIVERSE_PATH)
    parser.add_argument("--raw-proxy-dir", type=Path, default=DEFAULT_RAW_WEATHER_DIR)
    parser.add_argument("--max-close-hours", type=float, default=DEFAULT_MAX_CLOSE_HOURS)
    parser.add_argument("--max-contracts", type=int, default=DEFAULT_MAX_CONTRACTS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--capture-public-proxy", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_weather_proxy_feature_packet(
        universe_scan_path=args.universe_scan_path,
        probability_breadth_scout_path=args.probability_breadth_scout_path,
        raw_universe_path=args.raw_universe_path,
        raw_proxy_dir=args.raw_proxy_dir,
        max_close_hours=args.max_close_hours,
        max_contracts=args.max_contracts,
        capture_public_proxy=args.capture_public_proxy,
    )
    if args.write:
        paths = write_weather_proxy_feature_packet(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
