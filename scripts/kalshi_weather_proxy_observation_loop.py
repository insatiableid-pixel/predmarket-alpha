#!/usr/bin/env python3
"""Archive weather proxy feature observations and attach settled Kalshi labels.

This is the first repeatability loop after weather proxy features are built.
It records point-in-time features outside the repo, then labels only from public
settled Kalshi market payloads. Proxy data (NWS forecast/observation) remain
features, never labels, calibrated probabilities, EV, sizing, or execution evidence.

Usage:
    python3 scripts/kalshi_weather_proxy_observation_loop.py --write
    make kalshi-weather-proxy-observation-loop
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_FEATURE_PACKET_PATH = MACRO_DIR / "latest-kalshi-weather-proxy-feature-packet.json"
DEFAULT_SETTLED_SNAPSHOT_PATH = Path(
    "/home/mrwatson/manual_drops/kalshi_oos_settlements/kalshi_settled_markets_latest.json"
)
DEFAULT_SETTLED_RAW_DIR = Path("/home/mrwatson/manual_drops/kalshi_oos_settlements")
DEFAULT_OBSERVATION_DIR = Path("/home/mrwatson/manual_drops/kalshi_weather_proxy_observations")
DEFAULT_LABEL_DIR = Path("/home/mrwatson/manual_drops/kalshi_weather_proxy_labels")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-weather-proxy-observation-loop-latest"
KALSHI_PUBLIC_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
CSV_FIELDS = [
    "observation_id",
    "contract_ticker",
    "weather_family",
    "decision_time",
    "close_time",
    "yes_ask",
    "bracket_probability",
    "predicted_side",
    "label_status",
    "yes_outcome",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_weather_proxy_observation_loop(
    *,
    feature_packet_path: Path = DEFAULT_FEATURE_PACKET_PATH,
    settled_snapshot_path: Path = DEFAULT_SETTLED_SNAPSHOT_PATH,
    settled_raw_dir: Path = DEFAULT_SETTLED_RAW_DIR,
    observation_dir: Path = DEFAULT_OBSERVATION_DIR,
    label_dir: Path = DEFAULT_LABEL_DIR,
    out_dir: Path = DEFAULT_OUT_DIR,
    generated_utc: str | None = None,
    public_market_data_calls: bool = False,
    capture_settled_public: bool = False,
    fetch_json: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Build the weather proxy observation/label loop report.

    Args:
        feature_packet_path: Path to the weather feature packet JSON.
        settled_snapshot_path: Path to Kalshi settled markets JSON.
        settled_raw_dir: Directory for raw settled payloads.
        observation_dir: Directory for persisted observations.
        label_dir: Directory for persisted labels.
        out_dir: Output directory for the report.
        generated_utc: Override timestamp (ISO format).
        public_market_data_calls: Whether public market data was fetched.
        capture_settled_public: If True, fetch settled data live.
        fetch_json: Injectable fetch function (for tests).

    Returns:
        The observation/label loop report dict.
    """
    generated = _parse_ts(generated_utc or utc_now())
    generated_iso = generated_utc or utc_now()

    # Load feature packet
    feature_packet = _read_json_or_empty(feature_packet_path)
    feature_rows = (
        feature_packet.get("feature_rows", []) if isinstance(feature_packet, Mapping) else []
    )

    # Load settled snapshot
    settled_snapshot = _read_json_or_empty(settled_snapshot_path)
    settled_index = _build_settled_index(settled_snapshot)

    # Build observation dir structure
    observation_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)

    # Process ready feature rows -> observations
    existing_observations = set()
    if observation_dir.exists():
        for fpath in observation_dir.iterdir():
            if fpath.suffix == ".json":
                existing_observations.add(fpath.stem)

    new_observations: list[dict[str, Any]] = []
    for row in feature_rows:
        if not isinstance(row, Mapping):
            continue
        if row.get("feature_status") != "weather_features_ready":
            continue
        ticker = str(row.get("contract_ticker") or "")
        decision_time = generated_iso
        source_index = 0
        obs_id = _observation_id(ticker, decision_time, source_index)
        if obs_id in existing_observations:
            continue
        obs = {
            "observation_id": obs_id,
            "contract_ticker": ticker,
            "event_ticker": row.get("event_ticker"),
            "series_ticker": row.get("series_ticker"),
            "weather_family": row.get("weather_family", row.get("series_ticker")),
            "station_id": row.get("station_id"),
            "decision_time": decision_time,
            "close_time": row.get("close_time"),
            "expected_expiration_time": row.get("expected_expiration_time"),
            "yes_bid": row.get("yes_bid"),
            "yes_ask": row.get("yes_ask"),
            "no_bid": row.get("no_bid"),
            "no_ask": row.get("no_ask"),
            "bracket_probability": row.get("bracket_probability"),
            "predicted_side": row.get("predicted_side"),
            "forecast_high": row.get("forecast_high"),
            "forecast_low": row.get("forecast_low"),
            "observation_temperature": row.get("observation_temperature"),
            "feature_source": "api.weather.gov",
            "source_row_index": source_index,
        }
        # Persist observation
        obs_path = observation_dir / f"{obs_id}.json"
        obs_path.write_text(json.dumps(obs, default=str, sort_keys=True), encoding="utf-8")
        new_observations.append(obs)

    # Determine tickers that are due for label probing (past close_time)
    due_tickers: list[str] = []
    for obs in new_observations:
        close_ts = _parse_ts(obs.get("close_time"))
        if close_ts is not None and close_ts <= generated:
            ticker = str(obs.get("contract_ticker") or "")
            if ticker:
                due_tickers.append(ticker)
    # Also check existing observations
    for obs_id in existing_observations:
        obs_path = observation_dir / f"{obs_id}.json"
        try:
            obs_data = json.loads(obs_path.read_text(encoding="utf-8"))
            close_ts = _parse_ts(obs_data.get("close_time"))
            if close_ts is not None and close_ts <= generated:
                ticker = str(obs_data.get("contract_ticker") or "")
                if ticker and ticker not in due_tickers:
                    due_tickers.append(ticker)
        except (OSError, json.JSONDecodeError):
            pass

    due_tickers = list(dict.fromkeys(due_tickers))  # dedup preserving order
    observation_index = _latest_observation_by_ticker(
        [*new_observations, *_load_observation_rows(observation_dir)]
    )

    # Probe labels from settled markets
    new_labels: list[dict[str, Any]] = []
    blocked_labels = 0
    for ticker in due_tickers:
        settled = settled_index.get(ticker)
        if settled is None:
            blocked_labels += 1
            continue
        yes_outcome = _settlement_outcome(settled)
        if yes_outcome is None:
            blocked_labels += 1
            continue
        label = {
            **observation_index.get(ticker, {}),
            "label_id": hashlib.sha256(
                f"weather_label_{ticker}_{generated_iso}".encode()
            ).hexdigest()[:16],
            "contract_ticker": ticker,
            "event_ticker": settled.get("event_ticker"),
            "series_ticker": settled.get("series_ticker"),
            "weather_family": "KXHIGH" if "KXHIGH" in ticker else "KXLOW",
            "yes_outcome": yes_outcome,
            "label_source": "public_kalshi_settled_market",
            "label_status": "labeled_from_public_kalshi_settled_market",
            "decision_time": generated_iso,
            "close_time": settled.get("close_time"),
            "settlement_time": _first_present(
                settled,
                ("settlement_timestamp", "settlement_ts", "settled_time", "expiration_time"),
            ),
            "usable": False,
            "calibrated_probability": None,
            "expected_value_per_contract": None,
            "research_only": True,
            "execution_enabled": False,
        }
        # Persist label
        label_path = label_dir / f"weather_label_{ticker}.json"
        label_path.write_text(
            json.dumps(
                _safe_packet(
                    generated_utc=generated_iso,
                    packet_type="weather_proxy_label",
                    rows=[label],
                    inputs={"settled_snapshot_path": str(settled_snapshot_path)},
                ),
                default=str,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        new_labels.append(label)

    status = _observation_status(
        new_obs_count=len(new_observations),
        new_label_count=len(new_labels),
    )

    gates = _build_observation_gates(
        feature_packet_safe=_is_feature_packet_safe(feature_packet),
        feature_rows_present=bool(feature_rows),
    )

    observation_packet = _safe_packet(
        generated_utc=generated_iso,
        packet_type="weather_proxy_observation",
        rows=new_observations,
        inputs={"feature_packet_path": str(feature_packet_path)},
    )
    label_packet = _safe_packet(
        generated_utc=generated_iso,
        packet_type="weather_proxy_label",
        rows=new_labels,
        inputs={
            "observation_dir": str(observation_dir),
            "settled_snapshot_path": str(settled_snapshot_path),
        },
    )
    if new_labels:
        stamp = generated_iso.replace("-", "").replace(":", "").replace("+00:00", "Z")
        stamp = "".join(ch for ch in stamp if ch.isalnum() or ch in {"T", "Z"})
        label_text = json.dumps(label_packet, indent=2, sort_keys=True, default=str) + "\n"
        (label_dir / f"weather_proxy_labels_{stamp}.json").write_text(label_text, encoding="utf-8")
        (label_dir / "weather_proxy_labels_latest.json").write_text(label_text, encoding="utf-8")

    return {
        "schema_version": 1,
        "generated_utc": generated_iso,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": public_market_data_calls,
        "authenticated_api_calls": False,
        "provider_api_calls": public_market_data_calls,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "summary": {
            "feature_row_count": len(feature_rows),
            "ready_feature_row_count": sum(
                1
                for r in feature_rows
                if isinstance(r, Mapping) and r.get("feature_status") == "weather_features_ready"
            ),
            "new_observation_row_count": len(new_observations),
            "existing_observation_row_count": len(existing_observations),
            "due_observed_tickers": due_tickers,
            "due_observed_ticker_count": len(due_tickers),
            "new_label_row_count": len(new_labels),
            "blocked_label_row_count": blocked_labels,
        },
        "observation_packet": observation_packet,
        "label_packet": label_packet,
        "gates": gates,
        "next_action": _next_observation_action(status),
        "safety": {
            "research_only": True,
            "public_market_data_calls": public_market_data_calls,
            "authenticated_api_calls": False,
            "account_or_order_paths": False,
            "market_execution": False,
            "database_writes": False,
            "paid_calls": False,
            "raw_secrets_copied": False,
            "raw_payloads_copied_to_repo": False,
            "staking_or_sizing_guidance": False,
        },
    }


def _observation_id(ticker: str, decision_time: str, source_index: int) -> str:
    raw = f"weather_obs_{ticker}_{decision_time}_{source_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _build_settled_index(settled: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(settled, Mapping):
        return {}
    markets = settled.get("markets") or settled.get("events") or []
    return {
        str(m.get("ticker")): m
        for m in (markets if isinstance(markets, list) else [])
        if isinstance(m, Mapping) and m.get("ticker") and _settlement_outcome(m) is not None
    }


def capture_public_settled_snapshot(
    *,
    raw_dir: Path = DEFAULT_SETTLED_RAW_DIR,
    limit: int = 1000,
    max_pages: int = 1,
    generated_utc: str | None = None,
    fetch_json: Callable[[str], Any] | None = None,
) -> Path:
    generated = generated_utc or utc_now()
    fetch = fetch_json or _fetch_json_url
    raw_dir.mkdir(parents=True, exist_ok=True)
    markets: list[Mapping[str, Any]] = []
    cursor = ""
    for _ in range(max(1, max_pages)):
        query = urllib.parse.urlencode(
            {
                "status": "settled",
                "limit": max(1, min(int(limit), 1000)),
                "mve_filter": "exclude",
                **({"cursor": cursor} if cursor else {}),
            }
        )
        payload = fetch(f"{KALSHI_PUBLIC_BASE_URL}/markets?{query}")
        if not isinstance(payload, Mapping):
            break
        markets.extend(row for row in payload.get("markets", []) if isinstance(row, Mapping))
        cursor = str(payload.get("cursor") or "")
        if not cursor:
            break
    snapshot = _safe_settled_snapshot(
        generated_utc=generated,
        status="kalshi_public_settled_fetch_ok" if markets else "kalshi_public_settled_fetch_empty",
        markets=markets,
        query={
            "status": "settled",
            "limit": max(1, min(int(limit), 1000)),
            "max_pages": max_pages,
            "mve_filter": "exclude",
        },
    )
    return _write_settled_snapshot(
        snapshot, raw_dir=raw_dir, generated_utc=generated, stem="settled"
    )


def capture_public_observed_markets_snapshot(
    *,
    tickers: Sequence[str],
    raw_dir: Path = DEFAULT_SETTLED_RAW_DIR,
    base_snapshot_path: Path | None = None,
    generated_utc: str | None = None,
    fetch_json: Callable[[str], Any] | None = None,
) -> Path:
    generated = generated_utc or utc_now()
    fetch = fetch_json or _fetch_json_url
    raw_dir.mkdir(parents=True, exist_ok=True)
    base_snapshot = _read_json_or_empty(base_snapshot_path) if base_snapshot_path else {}
    base_markets = (
        base_snapshot.get("markets", []) if isinstance(base_snapshot.get("markets"), list) else []
    )
    markets: list[Mapping[str, Any]] = [row for row in base_markets if isinstance(row, Mapping)]
    seen = {str(row.get("ticker") or "") for row in markets}
    probe_errors: list[dict[str, str]] = []
    for ticker in tickers:
        ticker = str(ticker).strip()
        if not ticker or ticker in seen:
            continue
        try:
            payload = fetch(
                f"{KALSHI_PUBLIC_BASE_URL}/markets/{urllib.parse.quote(ticker, safe='')}"
            )
        except Exception as exc:
            probe_errors.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})
            continue
        market = payload.get("market") if isinstance(payload, Mapping) else None
        if isinstance(market, Mapping):
            markets.append(market)
            seen.add(ticker)
    snapshot = _safe_settled_snapshot(
        generated_utc=generated,
        status="kalshi_public_observed_market_fetch_ok"
        if markets
        else "kalshi_public_observed_market_fetch_empty",
        markets=markets,
        query={
            "mode": "exact_observed_ticker_probe",
            "observed_ticker_count": len(tickers),
            "base_snapshot_path": str(base_snapshot_path) if base_snapshot_path else None,
        },
        extra={
            "probe_errors_sample": probe_errors[:50],
            "summary": {
                "market_count": len(markets),
                "base_market_count": len(base_markets),
                "observed_ticker_count": len(tickers),
                "probe_error_count": len(probe_errors),
                "settled_label_ready_count": sum(
                    1 for market in markets if _settlement_outcome(market) is not None
                ),
            },
        },
    )
    return _write_settled_snapshot(
        snapshot, raw_dir=raw_dir, generated_utc=generated, stem="observed"
    )


def due_observed_tickers(
    *,
    feature_packet_path: Path,
    observation_dir: Path,
    generated_utc: str,
    max_tickers: int,
) -> list[str]:
    rows: list[Mapping[str, Any]] = []
    feature_packet = _read_json_or_empty(feature_packet_path)
    if _is_feature_packet_safe(feature_packet):
        feature_rows = feature_packet.get("feature_rows", [])
        if isinstance(feature_rows, list):
            rows.extend(row for row in feature_rows if isinstance(row, Mapping))
    if observation_dir.exists():
        for obs_path in sorted(observation_dir.glob("*.json")):
            payload = _read_json_or_empty(obs_path)
            if isinstance(payload, Mapping):
                rows.append(payload)
    cutoff = _parse_ts(generated_utc) or datetime.now(UTC).timestamp()
    output: list[str] = []
    seen: set[str] = set()
    for row in rows:
        ticker = str(row.get("contract_ticker") or "").strip()
        due_at = _parse_ts(
            _first_present(row, ("expected_expiration_time", "expiration_time", "close_time"))
        )
        if not ticker or ticker in seen or due_at is None or due_at > cutoff:
            continue
        seen.add(ticker)
        output.append(ticker)
        if len(output) >= max(0, max_tickers):
            break
    return output


def _load_observation_rows(observation_dir: Path) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    if not observation_dir.exists():
        return rows
    for obs_path in sorted(observation_dir.glob("*.json")):
        payload = _read_json_or_empty(obs_path)
        if not isinstance(payload, Mapping):
            continue
        packet_rows = payload.get("rows")
        if isinstance(packet_rows, list):
            rows.extend(row for row in packet_rows if isinstance(row, Mapping))
        elif payload.get("contract_ticker"):
            rows.append(payload)
    return rows


def _latest_observation_by_ticker(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("contract_ticker") or "").strip()
        if not ticker:
            continue
        current = output.get(ticker)
        if current is None or str(row.get("decision_time") or "") >= str(
            current.get("decision_time") or ""
        ):
            output[ticker] = dict(row)
    return output


def _observation_status(
    *,
    new_obs_count: int,
    new_label_count: int,
) -> str:
    if new_obs_count == 0 and new_label_count == 0:
        return "weather_proxy_observation_loop_blocked_no_new_observations_or_labels"
    if new_obs_count > 0 and new_label_count == 0:
        return "weather_proxy_observation_loop_partial_observations_no_labels"
    return "weather_proxy_observation_loop_ready_with_labels"


def _build_observation_gates(
    *,
    feature_packet_safe: bool,
    feature_rows_present: bool,
) -> list[dict[str, str]]:
    return [
        {
            "name": "weather_feature_packet_safe",
            "status": "pass" if feature_packet_safe else "blocked",
            "reason": "Feature packet must be research-only-safe.",
        },
        {
            "name": "weather_feature_rows_present",
            "status": "pass" if feature_rows_present else "blocked",
            "reason": "At least one feature row is needed for observations.",
        },
    ]


def _settlement_outcome(market: Mapping[str, Any]) -> int | None:
    settlement = _safe_float(market.get("settlement_value_dollars", market.get("settlement_value")))
    if settlement is not None:
        if settlement >= 0.999:
            return 1
        if settlement <= 0.001:
            return 0
    result = str(market.get("result") or market.get("expiration_value") or "").strip().lower()
    if result in {"yes", "true", "1"}:
        return 1
    if result in {"no", "false", "0"}:
        return 0
    return None


def _safe_settled_snapshot(
    *,
    generated_utc: str,
    status: str,
    markets: Sequence[Mapping[str, Any]],
    query: Mapping[str, Any],
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = {
        "schema_version": 1,
        "created_at_utc": generated_utc,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "query": dict(query),
        "summary": {"market_count": len(markets)},
        "safety": {
            "research_only": True,
            "public_market_data_calls": True,
            "authenticated_api_calls": False,
            "provider_api_calls": True,
            "paid_calls": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "raw_payloads_copied_to_repo": False,
            "staking_or_sizing_guidance": False,
        },
        "markets": list(markets),
    }
    if extra:
        snapshot.update(extra)
    return snapshot


def _safe_packet(
    *,
    generated_utc: str,
    packet_type: str,
    rows: Sequence[Mapping[str, Any]],
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_utc": generated_utc,
        "packet_type": packet_type,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "staking_or_sizing_guidance": False,
        "inputs": dict(inputs),
        "rows": list(rows),
        "safety": {
            "research_only": True,
            "public_market_data_calls": False,
            "authenticated_api_calls": False,
            "provider_api_calls": False,
            "paid_calls": False,
            "database_writes": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "raw_payloads_copied_to_repo": False,
            "staking_or_sizing_guidance": False,
        },
    }


def _write_settled_snapshot(
    snapshot: Mapping[str, Any], *, raw_dir: Path, generated_utc: str, stem: str
) -> Path:
    stamp = "".join(
        ch
        for ch in generated_utc.replace("-", "").replace(":", "").replace("+00:00", "Z")
        if ch.isalnum() or ch in {"T", "Z"}
    )
    snapshot_path = raw_dir / f"kalshi_weather_{stem}_markets_{stamp}.json"
    latest_path = raw_dir / "kalshi_weather_settled_markets_latest.json"
    text = json.dumps(snapshot, indent=2, sort_keys=True, default=str) + "\n"
    snapshot_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return latest_path


def _fetch_json_url(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.load(response)
    return payload if isinstance(payload, dict) else {}


def _first_present(row: Mapping[str, Any], keys: Sequence[str], fallback: Any = None) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return fallback


def _is_feature_packet_safe(packet: Any) -> bool:
    if not isinstance(packet, Mapping):
        return False
    safety = packet.get("safety") if isinstance(packet.get("safety"), Mapping) else {}
    return (
        packet.get("research_only") is True
        and packet.get("execution_enabled") is False
        and safety.get("market_execution") is False
        and safety.get("account_or_order_paths") is False
        and safety.get("database_writes") is False
    )


def _next_observation_action(status: str) -> dict[str, str]:
    if status == "weather_proxy_observation_loop_ready_with_labels":
        return {
            "name": "kalshi_weather_proxy_feature_model_falsification",
            "why": "Weather observations with settled labels are available for out-of-sample falsification.",
            "stop_condition": "Stop before treating proxy data as settlement labels or computing usable EV.",
        }
    return {
        "name": "kalshi_weather_proxy_observation_loop_blocker_review",
        "why": "No new observations or labels were emitted.",
        "stop_condition": "Stop before fabricating labels or observations.",
    }


def write_weather_proxy_observation_loop(
    report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR
) -> dict[str, str]:
    """Write the observation-loop report and refresh latest-* pointers."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-weather-proxy-observation-loop.json"
    md_path = out_dir / "kalshi-weather-proxy-observation-loop.md"
    csv_path = out_dir / "kalshi-weather-proxy-observation-loop.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    _write_csv(report, csv_path)
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-weather-proxy-observation-loop.json"
    latest_md = MACRO_DIR / "latest-kalshi-weather-proxy-observation-loop.md"
    latest_csv = MACRO_DIR / "latest-kalshi-weather-proxy-observation-loop.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(_render_markdown(report), encoding="utf-8")
    _write_csv(report, latest_csv)
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
        "# Kalshi Weather Proxy Observation Loop",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Research only: `{str(report.get('research_only')).lower()}`",
        f"- New observations: `{summary.get('new_observation_row_count')}`",
        f"- New labels: `{summary.get('new_label_row_count')}`",
        f"- Blocked labels: `{summary.get('blocked_label_row_count')}`",
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


def _write_csv(report: Mapping[str, Any], path: Path) -> None:
    rows = []
    for row in report.get("label_packet", {}).get("rows", []):
        if isinstance(row, Mapping):
            rows.append(row)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def _read_json_or_empty(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-packet-path", type=Path, default=DEFAULT_FEATURE_PACKET_PATH)
    parser.add_argument("--settled-snapshot-path", type=Path, default=DEFAULT_SETTLED_SNAPSHOT_PATH)
    parser.add_argument("--settled-raw-dir", type=Path, default=DEFAULT_SETTLED_RAW_DIR)
    parser.add_argument("--observation-dir", type=Path, default=DEFAULT_OBSERVATION_DIR)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--capture-settled-public", action="store_true")
    parser.add_argument("--settled-limit", type=int, default=1000)
    parser.add_argument("--settled-max-pages", type=int, default=1)
    parser.add_argument("--observed-probe-max-tickers", type=int, default=300)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    generated = utc_now()
    settled_snapshot_path = args.settled_snapshot_path
    if args.capture_settled_public:
        settled_snapshot_path = capture_public_settled_snapshot(
            raw_dir=args.settled_raw_dir,
            limit=args.settled_limit,
            max_pages=args.settled_max_pages,
            generated_utc=generated,
        )
        due_tickers = due_observed_tickers(
            feature_packet_path=args.feature_packet_path,
            observation_dir=args.observation_dir,
            generated_utc=generated,
            max_tickers=args.observed_probe_max_tickers,
        )
        if due_tickers:
            settled_snapshot_path = capture_public_observed_markets_snapshot(
                tickers=due_tickers,
                raw_dir=args.settled_raw_dir,
                base_snapshot_path=settled_snapshot_path,
                generated_utc=generated,
            )
    report = build_weather_proxy_observation_loop(
        feature_packet_path=args.feature_packet_path,
        settled_snapshot_path=settled_snapshot_path,
        settled_raw_dir=args.settled_raw_dir,
        observation_dir=args.observation_dir,
        label_dir=args.label_dir,
        out_dir=args.out_dir,
        generated_utc=generated,
        capture_settled_public=args.capture_settled_public,
        public_market_data_calls=args.capture_settled_public,
    )
    if args.write:
        paths = write_weather_proxy_observation_loop(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
