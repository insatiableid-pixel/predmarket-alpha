"""WeatherProxyFamily — the weather proxy signal family descriptor.

Weather is a near-exact structural twin of crypto: api.weather.gov (keyless
NWS forecast + observation) is a feature PROXY for the NWS Daily Climate
Report ("CLI" product) official settlement.  The basis risk between the
observation and the CLI IS the mispricing surface — exactly mirroring crypto's
Coinbase proxy -> CF Benchmarks RTI.

``family_id = "weather_proxy"``
``classification_tag`` covers ``KXHIGH`` (high temperature), ``KXLOW`` (low
temperature), and precipitation/weather contract prefixes.
``cluster_key_composer`` produces ``station | bracket | date`` so each
station-bracket-day triple is an INDEPENDENT correlation cluster.
``prediction_rule`` computes bracket probability from forecast + observation
trajectory, then applies the threshold rule (|- yes_ask| >= tau) to produce
YES/NO predictions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from predmarket.signal_family import SignalFamily

WEATHER_OFFICIAL_SETTLEMENT_SOURCE = "NWS Daily Climate Report (CLI product)"

# ── Classification tags ──────────────────────────────────────────────────
# Kalshi weather contracts: KXHIGH (high temperature), KXLOW (low temperature),
# plus precipitation families.

WEATHER_CLASSIFICATION_TAGS = ("KXHIGH", "KXLOW")

WEATHER_CITY_STATION_ALIASES = {
    "ATL": "KATL",
    "AUS": "KAUS",
    "BOS": "KBOS",
    "CHI": "KORD",
    "DAL": "KDFW",
    "DC": "KDCA",
    "DEN": "KDEN",
    "DFW": "KDFW",
    "HOU": "KIAH",
    "LAX": "KLAX",
    "LV": "KLAS",
    "MIA": "KMIA",
    "MIN": "KMSP",
    "NOLA": "KMSY",
    "NY": "KNYC",
    "NYC": "KNYC",
    "OKC": "KOKC",
    "PHIL": "KPHL",
    "PHL": "KPHL",
    "PHX": "KPHX",
    "SATX": "KSAT",
    "SEA": "KSEA",
    "SFO": "KSFO",
}

# ── Prediction rule ──────────────────────────────────────────────────────


def weather_prediction_rule(row: Mapping[str, Any]) -> tuple[int | None, float | None]:
    """Weather bracket prediction rule.

    Uses the row's ``bracket_probability`` (a float in [0,1] computed from
    NWS forecast + observation trajectory) and the threshold rule:
    YES when ``(bracket_probability - yes_ask) >= +tau``,
    NO  when ``(bracket_probability - yes_ask) <= -tau``,
    None otherwise.

    Returns:
        (1, bracket_probability) for YES, (0, bracket_probability) for NO,
        (None, None) when no edge.
    """
    p = row.get("bracket_probability")
    yes_ask = row.get("yes_ask")
    tau = float(row.get("prediction_tau", 0.05))
    if p is None or yes_ask is None:
        return None, None
    try:
        p = float(p)
        yes_ask = float(yes_ask)
    except (TypeError, ValueError):
        return None, None
    delta = p - yes_ask
    if delta >= tau:
        return 1, p
    if delta <= -tau:
        return 0, p
    return None, None


# ── Cluster-key composer ─────────────────────────────────────────────────


def weather_cluster_key_composer(row: Mapping[str, Any]) -> str:
    """Compose correlation cluster key: station | bracket | date.

    Each station-bracket-day triple is an INDEPENDENT correlation cluster,
    exactly mirroring sports' ``league | game_winner | date``.
    """
    from predmarket.shared_helpers import bucket_time

    return "|".join(
        str(part or "unknown")
        for part in (
            row.get("station_id"),
            row.get("bracket", row.get("series_ticker", "unknown")),
            bucket_time(row.get("close_time")),
        )
    )


# ── Model evaluators ─────────────────────────────────────────────────────


def evaluate_weather_bracket_directional(
    *,
    rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    prediction_rule: Any = None,
    min_independent_labels: int = 30,
    min_oos_labels: int = 10,
) -> dict[str, Any]:
    """Evaluate weather bracket-model directional accuracy on OOS rows."""
    from predmarket.shared_helpers import binomial_survival

    scored = [
        row
        for row in oos_rows
        if prediction_rule is not None and prediction_rule(row)[0] is not None
    ]
    wins = 0
    for row in scored:
        pred, _ = prediction_rule(row) if prediction_rule else (None, None)
        outcome = row.get("yes_outcome")
        if isinstance(outcome, bool):
            outcome = int(outcome)
        if pred is not None and outcome is not None:
            try:
                if pred == int(outcome):
                    wins += 1
            except (TypeError, ValueError):
                pass
    p_value = (
        binomial_survival(wins, len(scored), 0.5)
        if len(rows) >= min_independent_labels and len(scored) >= min_oos_labels
        else None
    )
    if len(rows) < min_independent_labels:
        status = "blocked_insufficient_independent_labels"
    elif len(scored) < min_oos_labels:
        status = "blocked_insufficient_oos_labels"
    else:
        status = "testable_research_candidate"
    return {
        "model_id": "weather_bracket_directional_accuracy",
        "status": status,
        "independent_label_count": len(rows),
        "oos_count": len(scored),
        "oos_correct_count": wins,
        "oos_accuracy": wins / len(scored) if scored else None,
        "p_value": p_value,
        "q_value": None,
        "feature_rule": "Predict YES when bracket_probability - yes_ask >= +tau; NO when <= -tau.",
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


def evaluate_weather_market_baseline(
    *,
    rows: Sequence[Mapping[str, Any]],
    oos_rows: Sequence[Mapping[str, Any]],
    prediction_rule: Any = None,
    min_independent_labels: int | None = None,
    min_oos_labels: int | None = None,
) -> dict[str, Any]:
    """Evaluate market YES ask as a baseline Brier-score diagnostic (weather)."""
    from predmarket.shared_helpers import probability

    scored = [row for row in oos_rows if probability(row.get("yes_ask")) is not None]
    briers = [(float(row["yes_ask"]) - float(row["yes_outcome"])) ** 2 for row in scored]
    return {
        "model_id": "weather_market_yes_ask_probability_baseline",
        "status": "diagnostic_baseline_only",
        "independent_label_count": len(rows),
        "oos_count": len(scored),
        "mean_market_brier": sum(briers) / len(briers) if briers else None,
        "p_value": None,
        "q_value": None,
        "feature_rule": "Market YES ask is recorded as a baseline probability diagnostic, not a model promotion.",
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


WEATHER_MODEL_EVALUATORS: list[dict[str, Any]] = [
    {
        "model_id": "weather_bracket_directional_accuracy",
        "evaluate_fn": evaluate_weather_bracket_directional,
    },
    {
        "model_id": "weather_market_yes_ask_probability_baseline",
        "evaluate_fn": evaluate_weather_market_baseline,
    },
]


# ── Station / gridpoint resolver (api.weather.gov /points chain) ─────────


# Map of known city -> (lat, lon) for resolving NWS gridpoints.
# These are the stations referenced by Kalshi KXHIGH/KXLOW contracts.
# In production, the feature-packet builder would parse lat/lon from the
# contract's metadata or a station registry; the resolver below handles
# the NWS API chain given any (lat, lon).
WEATHER_REFERENCE_STATIONS: dict[str, dict[str, float]] = {
    "KNYC": {"lat": 40.7128, "lon": -74.0060},  # New York City (Central Park)
    "KORD": {"lat": 41.8781, "lon": -87.6298},  # Chicago O'Hare
    "KLAX": {"lat": 33.9425, "lon": -118.4081},  # Los Angeles
    "KATL": {"lat": 33.7490, "lon": -84.3880},  # Atlanta
    "KDFW": {"lat": 32.7767, "lon": -96.7970},  # Dallas/Fort Worth
    "KDEN": {"lat": 39.7392, "lon": -104.9903},  # Denver
    "KSEA": {"lat": 47.6062, "lon": -122.3321},  # Seattle
    "KMIA": {"lat": 25.7617, "lon": -80.1918},  # Miami
    "KBOS": {"lat": 42.3601, "lon": -71.0589},  # Boston
    "KPHL": {"lat": 39.9526, "lon": -75.1652},  # Philadelphia
    "KDCA": {"lat": 38.9072, "lon": -77.0369},  # Washington DC
    "KAUS": {"lat": 30.1975, "lon": -97.6664},  # Austin-Bergstrom
    "KIAH": {"lat": 29.9844, "lon": -95.3414},  # Houston Intercontinental
    "KMSP": {"lat": 44.8848, "lon": -93.2223},  # Minneapolis-St Paul
    "KMSY": {"lat": 29.9934, "lon": -90.2580},  # New Orleans
    "KOKC": {"lat": 35.3931, "lon": -97.6007},  # Oklahoma City
    "KSAT": {"lat": 29.5337, "lon": -98.4698},  # San Antonio
    "KPHX": {"lat": 33.4343, "lon": -112.0116},  # Phoenix
    "KLAS": {"lat": 36.0801, "lon": -115.1522},  # Las Vegas
    "KSFO": {"lat": 37.6213, "lon": -122.3790},  # San Francisco
}


def resolve_weather_station_id_from_ticker(*values: Any) -> str | None:
    """Resolve Kalshi weather series/ticker city suffixes to NWS station IDs."""
    for value in values:
        token = str(value or "")
        head = token.split("-", 1)[0]
        for prefix in WEATHER_CLASSIFICATION_TAGS:
            if head.startswith(prefix):
                station_id = normalize_weather_station_code(head[len(prefix) :])
                if station_id:
                    return station_id
        parts = token.split("-")
        if len(parts) >= 3:
            station_id = normalize_weather_station_code(parts[2])
            if station_id:
                return station_id
    return None


def normalize_weather_station_code(value: str) -> str | None:
    """Normalize Kalshi city codes and NWS station IDs to known station IDs."""
    code = value.strip().upper()
    if not code:
        return None
    candidates = [code]
    if code.startswith("T") and len(code) > 1:
        candidates.append(code[1:])
    for candidate in candidates:
        if candidate in WEATHER_REFERENCE_STATIONS:
            return candidate
        if candidate in WEATHER_CITY_STATION_ALIASES:
            return WEATHER_CITY_STATION_ALIASES[candidate]
        station_id = f"K{candidate}"
        if station_id in WEATHER_REFERENCE_STATIONS:
            return station_id
    return None


def weather_station_resolver(lat: float, lon: float, fetch_json: Any = None) -> dict[str, Any]:
    """Resolve a (lat, lon) to the NWS gridpoint and nearest station.

    Calls ``https://api.weather.gov/points/{lat},{lon}`` to get the gridpoint
    (office, gridX, gridY) and the ``observationStations`` collection.

    Returns a dict with:
        - ``status``: "resolved" or "unresolved"
        - ``office``: NWS weather forecast office ID (e.g. "OKX")
        - ``grid_x``, ``grid_y``: gridpoint coordinates
        - ``station_id``: nearest observation station ID (e.g. "KNYC")
        - ``station_name``: human-readable station name
        - ``error``: error message if unresolved

    If ``fetch_json`` is None, returns a synthetic resolution based on the
    known ``WEATHER_REFERENCE_STATIONS`` for test/offline mode.
    """
    if fetch_json is None:
        # Offline/test mode: look up by approximate lat/lon
        best_station = "KNYC"
        best_dist = float("inf")
        for sid, coords in WEATHER_REFERENCE_STATIONS.items():
            dist = ((coords["lat"] - lat) ** 2 + (coords["lon"] - lon) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_station = sid
        return {
            "status": "resolved",
            "office": "OKX" if best_station == "KNYC" else "TOP",
            "grid_x": 50,
            "grid_y": 50,
            "station_id": best_station,
            "station_name": best_station,
            "lat": lat,
            "lon": lon,
            "error": None,
        }
    try:
        points_url = f"https://api.weather.gov/points/{lat},{lon}"
        points_data = fetch_json(points_url)
        props = points_data.get("properties", {})
        office = props.get("cwa", "")
        grid_x = props.get("gridX")
        grid_y = props.get("gridY")
        stations_url = props.get("observationStations", "")
        station_data = fetch_json(stations_url) if stations_url else {}
        station_features = station_data.get("features", [])
        nearest_station = station_features[0] if station_features else {}
        station_id = (
            nearest_station.get("properties", {}).get("stationIdentifier", "")
            if nearest_station
            else ""
        )
        station_name = (
            nearest_station.get("properties", {}).get("name", station_id)
            if nearest_station
            else station_id
        )
        return {
            "status": "resolved"
            if office and grid_x is not None and grid_y is not None
            else "unresolved",
            "office": office,
            "grid_x": grid_x,
            "grid_y": grid_y,
            "station_id": station_id,
            "station_name": station_name,
            "lat": lat,
            "lon": lon,
            "error": None,
        }
    except Exception as exc:
        return {
            "status": "unresolved",
            "office": None,
            "grid_x": None,
            "grid_y": None,
            "station_id": None,
            "station_name": None,
            "lat": lat,
            "lon": lon,
            "error": f"{type(exc).__name__}: {str(exc)[:240]}",
        }


def fetch_weather_forecast(
    office: str, grid_x: int, grid_y: int, fetch_json: Any = None
) -> dict[str, Any]:
    """Fetch NWS forecast for a gridpoint.

    Calls ``https://api.weather.gov/gridpoints/{office}/{grid_x},{grid_y}/forecast``
    and returns the parsed forecast periods.

    If ``fetch_json`` is None, returns a synthetic forecast for testing.
    """
    if fetch_json is None:
        return {
            "status": "synthetic",
            "forecast_high": 75.0,
            "forecast_low": 55.0,
            "forecast_source": "api.weather.gov",
        }
    try:
        forecast_url = f"https://api.weather.gov/gridpoints/{office}/{grid_x},{grid_y}/forecast"
        data = fetch_json(forecast_url)
        props = data.get("properties", {})
        periods = props.get("periods", [])
        today = next(
            (p for p in periods if p.get("isDaytime") is True), periods[0] if periods else {}
        )
        return {
            "status": "resolved",
            "forecast_high": today.get("temperature"),
            "forecast_low": today.get("temperature"),
            "forecast_source": "api.weather.gov",
            "periods_returned": len(periods),
        }
    except Exception as exc:
        return {
            "status": "unresolved",
            "forecast_high": None,
            "forecast_low": None,
            "forecast_source": "api.weather.gov",
            "error": f"{type(exc).__name__}: {str(exc)[:240]}",
        }


def fetch_weather_observations(station_id: str, fetch_json: Any = None) -> dict[str, Any]:
    """Fetch latest weather observations for a station.

    Calls ``https://api.weather.gov/stations/{station_id}/observations``
    and returns the most recent temperature observation.

    If ``fetch_json`` is None, returns a synthetic observation for testing.
    """
    if fetch_json is None:
        return {
            "status": "synthetic",
            "observation_temperature": 72.0,
            "observation_timestamp": "2026-07-03T12:00:00Z",
            "observation_source": "api.weather.gov",
        }
    try:
        obs_url = f"https://api.weather.gov/stations/{station_id}/observations"
        data = fetch_json(obs_url)
        features = data.get("features", [])
        latest = features[0] if features else {}
        obs_props = latest.get("properties", {})
        temp_value = obs_props.get("temperature", {}).get("value")
        timestamp = obs_props.get("timestamp")
        return {
            "status": "resolved" if temp_value is not None else "missing",
            "observation_temperature": temp_value,
            "observation_timestamp": timestamp,
            "observation_source": "api.weather.gov",
        }
    except Exception as exc:
        return {
            "status": "unresolved",
            "observation_temperature": None,
            "observation_timestamp": None,
            "observation_source": "api.weather.gov",
            "error": f"{type(exc).__name__}: {str(exc)[:240]}",
        }


def compute_bracket_probability(
    *,
    forecast_high: float | None,
    forecast_low: float | None,
    observation_temperature: float | None,
    strike: float | None = None,
    bracket_type: str = "KXHIGH",
) -> float | None:
    """Compute a mechanical bracket probability from forecast + observation.

    KXHIGH: probability that the high temp exceeds or equals ``strike``.
    KXLOW:  probability that the low temp is at or below ``strike``.

    This is a simple frozen model:
    - If the forecast is far above/below the strike, probability is high/low.
    - The observation trajectory shifts the probability (recent obs trending
      toward/away from the bracket adds confidence).

    Returns a float in [0, 1] or None when insufficient data.
    """
    if strike is None:
        return None
    if bracket_type == "KXHIGH":
        forecast = forecast_high
    elif bracket_type == "KXLOW":
        forecast = forecast_low
    else:
        return 0.5  # unknown bracket type -> no edge
    if forecast is None:
        return None
    try:
        forecast = float(forecast)
        strike = float(strike)
    except (TypeError, ValueError):
        return None

    # Simple mechanical model: z-score of forecast relative to strike
    # With an observation trajectory adjustment
    diff = forecast - strike if bracket_type == "KXHIGH" else strike - forecast
    # Scale factor: each degree away from strike adds ~10% confidence
    raw_prob = 0.5 + min(max(diff / 10.0, -0.5), 0.5)
    # Observation trajectory adjustment: if observation is moving toward bracket,
    # add up to 0.10 confidence; if moving away, subtract up to 0.10
    if observation_temperature is not None:
        try:
            obs = float(observation_temperature)
            obs_diff = obs - strike if bracket_type == "KXHIGH" else strike - obs
            obs_factor = min(max(obs_diff / 20.0, -0.10), 0.10)
            raw_prob += obs_factor * 0.5  # blend
        except (TypeError, ValueError):
            pass
    return max(0.0, min(1.0, raw_prob))


# ── WeatherProxyFamily factory ──────────────────────────────────────────


def make_weather_family(**overrides: Any) -> SignalFamily:
    """Factory that returns the canonical WeatherProxyFamily descriptor.

    Accepts optional overrides (e.g. for tests to inject a ``prediction_rule``
    or ``fetcher``).
    """
    import dataclasses

    base = SignalFamily(
        family_id="weather_proxy",
        status_prefix="weather_proxy",
        classification_tag=list(WEATHER_CLASSIFICATION_TAGS),
        official_settlement_source=WEATHER_OFFICIAL_SETTLEMENT_SOURCE,
        reference_source_registry=dict(WEATHER_REFERENCE_STATIONS),
        fetcher=None,
        feature_definitions={},
        prediction_rule=weather_prediction_rule,
        model_evaluators=list(WEATHER_MODEL_EVALUATORS),
        cluster_key_composer=weather_cluster_key_composer,
    )
    if overrides:
        return dataclasses.replace(base, **overrides)
    return base
