#!/usr/bin/env python3
"""Build contract-keyed proxy feature packets for Kalshi baseball contracts.

This report creates MODEL FEATURES + a strength-derived prediction, not a
sportsbook-reference margin (that is the Type 2 lane's job). It joins open
Kalshi MLB/KBO/LMB game-winner contracts (KXMLBGAME/KXKBOGAME/KXLMBGAME) to
public pre-game strength features from keyless sources (MLB Stats API for MLB,
ESPN hidden API for KBO/LMB) and preserves the boundary:

- The official settlement source is the official GAME RESULT (league box score),
  read at label time from Kalshi's own public settlement.
- The strength model is fit ONCE on history then FROZEN (loaded from a checked-in
  artifact); at build time the model only evaluates the frozen linear predictor
  (no-discretion axiom).
- A game-winner contract's YES means the SELECTED team wins the game outright
  (moneyline) -- never a run-line/spread margin (the prior sign-convention bug).
- Every row is research-only: ``usable=false``, ``calibrated_probability=null``.

Mirrors ``scripts/kalshi_crypto_proxy_feature_packet.py`` (report envelope,
``safe_research_artifact``, ``safety_flags``, ``build_gates``, ``write_*`` +
``latest-*`` pointers, close-time-windowed selection).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.mlb_platform_bridge import (  # noqa: E402
    attach_mlb_platform_model,
    load_mlb_platform_model_bridge,
    mlb_platform_model_index,
)
from predmarket.shared_helpers import (  # noqa: E402
    manual_drop_path,
    optional_float,
    outside_repo,
    read_json_or_empty,
    safe_research_artifact,
    sha256_or_none,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_UNIVERSE_SCAN_PATH = MACRO_DIR / "latest-kalshi-universe-scan.json"
DEFAULT_BREADTH_SCOUT_PATH = MACRO_DIR / "latest-kalshi-probability-breadth-scout.json"
DEFAULT_RAW_UNIVERSE_PATH = manual_drop_path(
    "kalshi_universe", "kalshi_universe_scan_latest.json"
)
DEFAULT_RAW_PROXY_DIR = manual_drop_path("kalshi_sports_proxy_features")
DEFAULT_STRENGTH_COEFFICIENTS_PATH = MACRO_DIR / "sports-baseball-strength-coefficients.json"
DEFAULT_MLB_PLATFORM_MODEL_PATH = manual_drop_path(
    "mlb_platform_signal_features", "mlb_platform_sports_model_latest.json"
)
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-proxy-feature-packet-latest"
DEFAULT_MAX_CLOSE_HOURS = 6.0
DEFAULT_MAX_CONTRACTS = 1500

SPORTS_SERIES_PREFIXES = ("KXMLBGAME", "KXKBOGAME", "KXLMBGAME")
SERIES_TO_LEAGUE = {"KXMLBGAME": "MLB", "KXKBOGAME": "KBO", "KXLMBGAME": "LMB"}

MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

# Kalshi MLB team codes (identical to statsapi standings abbreviations; Arizona = "AZ").
MLB_TEAM_CODES = frozenset(
    {
        "LAA",
        "AZ",
        "BAL",
        "BOS",
        "CHC",
        "CIN",
        "CLE",
        "COL",
        "DET",
        "HOU",
        "KC",
        "LAD",
        "WSH",
        "NYM",
        "ATH",
        "PIT",
        "SD",
        "SEA",
        "SF",
        "STL",
        "TB",
        "TEX",
        "TOR",
        "MIN",
        "PHI",
        "ATL",
        "CWS",
        "MIA",
        "NYY",
        "MIL",
    }
)
# Kalshi code -> statsapi team id + display name (stable MLB team identifiers).
MLB_CODE_TO_INFO: dict[str, dict[str, Any]] = {
    "LAA": {"id": 108, "name": "Los Angeles Angels"},
    "AZ": {"id": 109, "name": "Arizona Diamondbacks"},
    "BAL": {"id": 110, "name": "Baltimore Orioles"},
    "BOS": {"id": 111, "name": "Boston Red Sox"},
    "CHC": {"id": 112, "name": "Chicago Cubs"},
    "CIN": {"id": 113, "name": "Cincinnati Reds"},
    "CLE": {"id": 114, "name": "Cleveland Guardians"},
    "COL": {"id": 115, "name": "Colorado Rockies"},
    "DET": {"id": 116, "name": "Detroit Tigers"},
    "HOU": {"id": 117, "name": "Houston Astros"},
    "KC": {"id": 118, "name": "Kansas City Royals"},
    "LAD": {"id": 119, "name": "Los Angeles Dodgers"},
    "WSH": {"id": 120, "name": "Washington Nationals"},
    "NYM": {"id": 121, "name": "New York Mets"},
    "ATH": {"id": 133, "name": "Athletics"},
    "PIT": {"id": 134, "name": "Pittsburgh Pirates"},
    "SD": {"id": 135, "name": "San Diego Padres"},
    "SEA": {"id": 136, "name": "Seattle Mariners"},
    "SF": {"id": 137, "name": "San Francisco Giants"},
    "STL": {"id": 138, "name": "St. Louis Cardinals"},
    "TB": {"id": 139, "name": "Tampa Bay Rays"},
    "TEX": {"id": 140, "name": "Texas Rangers"},
    "TOR": {"id": 141, "name": "Toronto Blue Jays"},
    "MIN": {"id": 142, "name": "Minnesota Twins"},
    "PHI": {"id": 143, "name": "Philadelphia Phillies"},
    "ATL": {"id": 144, "name": "Atlanta Braves"},
    "CWS": {"id": 145, "name": "Chicago White Sox"},
    "MIA": {"id": 146, "name": "Miami Marlins"},
    "NYY": {"id": 147, "name": "New York Yankees"},
    "MIL": {"id": 158, "name": "Milwaukee Brewers"},
}

# KBO (Korean Baseball Organization) -- 10 teams.
KBO_TEAM_CODES = frozenset({"KTW", "HAN", "LG", "KIW", "LOT", "DOO", "SAM", "NCD", "SSG", "KIA"})
KBO_CODE_TO_INFO: dict[str, dict[str, str]] = {
    "KTW": {"name": "KT Wiz", "espn_abbr": "KT"},
    "HAN": {"name": "Hanwha Eagles", "espn_abbr": "HH"},
    "LG": {"name": "LG Twins", "espn_abbr": "LG"},
    "KIW": {"name": "Kiwoom Heroes", "espn_abbr": "WOOM"},
    "LOT": {"name": "Lotte Giants", "espn_abbr": "LT"},
    "DOO": {"name": "Doosan Bears", "espn_abbr": "OB"},
    "SAM": {"name": "Samsung Lions", "espn_abbr": "SS"},
    "NCD": {"name": "NC Dinos", "espn_abbr": "NC"},
    "SSG": {"name": "SSG Landers", "espn_abbr": "SK"},
    "KIA": {"name": "KIA Tigers", "espn_abbr": "HT"},
}
KBO_CODE_TO_ESPN_ABBR = {code: info["espn_abbr"] for code, info in KBO_CODE_TO_INFO.items()}

# LMB (Liga Mexicana de Beisbol) -- 20 teams (all 3-letter codes).
LMB_TEAM_CODES = frozenset(
    {
        "AGU",
        "TDQ",
        "CDJ",
        "CAL",
        "DOR",
        "SDM",
        "PDC",
        "CON",
        "RDA",
        "ALG",
        "TDT",
        "ADM",
        "LDY",
        "PDP",
        "DIA",
        "GUE",
        "ODT",
        "BLE",
        "TEL",
        "SDS",
    }
)
LMB_CODE_TO_INFO: dict[str, dict[str, str]] = {
    "AGU": {"name": "Aguiluchos de Tabasco", "espn_abbr": "AGU"},
    "TDQ": {"name": "Tabasco", "espn_abbr": "TDQ"},
    "CDJ": {"name": "Charros de Jalisco", "espn_abbr": "CDJ"},
    "CAL": {"name": "Caliente", "espn_abbr": "CAL"},
    "DOR": {"name": "Dorados", "espn_abbr": "DOR"},
    "SDM": {"name": "Sultanes de Monterrey", "espn_abbr": "SDM"},
    "PDC": {"name": "Perdiceros", "espn_abbr": "PDC"},
    "CON": {"name": "Conspiradores", "espn_abbr": "CON"},
    "RDA": {"name": "Rieleros", "espn_abbr": "RDA"},
    "ALG": {"name": "Algodoneros", "espn_abbr": "ALG"},
    "TDT": {"name": "Toros de Tijuana", "espn_abbr": "TDT"},
    "ADM": {"name": "Diablos Rojos", "espn_abbr": "ADM"},
    "LDY": {"name": "Leones de Yucatan", "espn_abbr": "LDY"},
    "PDP": {"name": "Pericos de Puebla", "espn_abbr": "PDP"},
    "DIA": {"name": "Diablos", "espn_abbr": "DIA"},
    "GUE": {"name": "Guerreros", "espn_abbr": "GUE"},
    "ODT": {"name": "Olmecas", "espn_abbr": "ODT"},
    "BLE": {"name": "Bravos", "espn_abbr": "BLE"},
    "TEL": {"name": "Tecolotes", "espn_abbr": "TEL"},
    "SDS": {"name": "Saraperos", "espn_abbr": "SDS"},
}
LMB_CODE_TO_ESPN_ABBR = {code: info["espn_abbr"] for code, info in LMB_CODE_TO_INFO.items()}

LEAGUE_TO_CODES = {"MLB": MLB_TEAM_CODES, "KBO": KBO_TEAM_CODES, "LMB": LMB_TEAM_CODES}
LEAGUE_TO_ESPN_PATH = {"KBO": "kbo", "LMB": "mlb-mexican-league"}
LEAGUE_TO_ESPN_ABBR = {"KBO": KBO_CODE_TO_ESPN_ABBR, "LMB": LMB_CODE_TO_ESPN_ABBR}

CSV_FIELDS = [
    "contract_ticker",
    "event_ticker",
    "series_ticker",
    "league",
    "away_code",
    "home_code",
    "selected_code",
    "away_team_id",
    "home_team_id",
    "external_game_id",
    "close_time",
    "expected_expiration_time",
    "fresh_time_to_close_minutes",
    "fresh_time_to_close_hours",
    "fresh_time_to_settlement_minutes",
    "fresh_time_to_settlement_hours",
    "horizon_time_basis",
    "yes_bid",
    "yes_ask",
    "yes_spread",
    "no_bid",
    "no_ask",
    "home_strength",
    "away_strength",
    "home_field",
    "strength_source",
    "home_win_probability",
    "win_probability",
    "predicted_side",
    "threshold_delta",
    "mlb_platform_model_status",
    "mlb_platform_model_probability",
    "mlb_platform_predicted_side",
    "mlb_platform_threshold_delta",
    "mlb_platform_model_id",
    "mlb_platform_match_key",
    "contract_family",
    "yes_interpretation",
    "official_settlement_source",
    "official_label_status",
    "feature_status",
    "label_status",
    "ev_status",
    "usable",
]

# event_ticker: SERIES-YY{MON}{DD}{HH}{MM}{AWAY}{HOME}
EVENT_RE = re.compile(
    r"^(?P<series>KXMLBGAME|KXKBOGAME|KXLMBGAME)-"
    r"(?P<year>\d{2})(?P<month>[A-Z]{3})(?P<day>\d{2})"
    r"(?P<hour>\d{2})(?P<minute>\d{2})(?P<teams>[A-Z]+)$"
)


def parse_sports_event_ticker(event_ticker: str) -> dict[str, Any] | None:
    """Parse a Kalshi sports event ticker into its league/date/team components.

    Returns None if the ticker is not a recognized baseball game-winner event
    (so run-line / player-prop / NFL / crypto tickers are rejected by construction).
    """
    match = EVENT_RE.match(str(event_ticker or ""))
    if not match:
        return None
    series = match.group("series")
    league = SERIES_TO_LEAGUE[series]
    codes = LEAGUE_TO_CODES[league]
    teams = match.group("teams")
    split = split_team_suffix(teams, codes)
    away_code, home_code = split if split is not None else (None, None)
    month = MONTHS.get(match.group("month"))
    if month is None:
        return None
    year = 2000 + int(match.group("year"))
    try:
        game_start = datetime(
            year,
            month,
            int(match.group("day")),
            int(match.group("hour")),
            int(match.group("minute")),
            tzinfo=UTC,
        )
    except ValueError:
        return None
    return {
        "series": series,
        "league": league,
        "away_code": away_code,
        "home_code": home_code,
        "teams_suffix": teams,
        "game_start_utc": game_start.isoformat(timespec="minutes").replace("+00:00", "Z"),
        "game_date": f"{year:04d}-{month:02d}-{int(match.group('day')):02d}",
        "season_year": year,
        "yyyymmdd": f"{year:04d}{month:02d}{int(match.group('day')):02d}",
    }


def split_team_suffix(suffix: str, codes: frozenset[str]) -> tuple[str, str] | None:
    """Split a concatenated team-code suffix into (away, home) using the known code set.

    Tries every split position where both halves are known team codes; returns the
    first valid split (shortest first code). This is unambiguous for the MLB/KBO/LMB
    code sets (no code is a prefix of another within a league).
    """
    text = str(suffix or "").upper()
    for split in range(2, len(text) - 1):
        first, second = text[:split], text[split:]
        if first in codes and second in codes:
            return first, second
    return None


def selected_team_code(contract_ticker: str, event_ticker: str) -> str | None:
    """Extract the selected-team code (the side whose win resolves YES) from the contract ticker."""
    ct = str(contract_ticker or "")
    et = str(event_ticker or "")
    if not ct.startswith(et) or len(ct) <= len(et) + 1:
        return None
    return ct[len(et) + 1 :].strip().upper() or None


def load_strength_coefficients(path: Path) -> dict[str, Any]:
    raw = read_json_or_empty(path)
    coeffs = raw.get("coefficients") if isinstance(raw, Mapping) else None
    if not isinstance(coeffs, Mapping) or "strength_diff" not in coeffs:
        # Fall back to a safe frozen default if the artifact is missing/corrupt.
        return _DEFAULT_COEFFICIENTS_PAYLOAD
    raw.setdefault("prediction_threshold_tau", 0.05)
    raw.setdefault("strength_composition", _DEFAULT_COEFFICIENTS_PAYLOAD["strength_composition"])
    raw.setdefault("fit_provenance", _DEFAULT_COEFFICIENTS_PAYLOAD["fit_provenance"])
    raw.setdefault("model", "pregame_strength_logistic")
    return raw


_DEFAULT_COEFFICIENTS_PAYLOAD: dict[str, Any] = {
    "model": "pregame_strength_logistic",
    "version": "builtin-frozen-default",
    "coefficients": {"intercept": 0.0, "strength_diff": 2.0, "home_field": 0.2},
    "prediction_threshold_tau": 0.05,
    "strength_composition": {
        "win_percentage_weight": 0.5,
        "pythagorean_weight": 0.5,
        "pythagorean_exponent": 2.0,
    },
    "fit_provenance": {
        "method": "fit_once_on_history_then_frozen",
        "training_window": "builtin default (offline fit on MLB history)",
        "source": "builtin frozen default",
    },
}


def pythagorean_expectation(
    runs_scored: float, runs_allowed: float, exponent: float
) -> float | None:
    if runs_scored < 0 or runs_allowed <= 0:
        return None
    rs_e = runs_scored**exponent
    ra_e = runs_allowed**exponent
    denom = rs_e + ra_e
    if denom <= 0:
        return None
    return rs_e / denom


def compute_team_strength(
    wins: float | None,
    losses: float | None,
    runs_scored: float | None,
    runs_allowed: float | None,
    blend: Mapping[str, Any],
) -> float | None:
    """Blend win-percentage and pythagorean expectation into a [0,1] strength score."""
    gp = (wins or 0) + (losses or 0)
    if not gp or gp <= 0:
        return None
    win_pct = (wins or 0) / gp
    pyth = pythagorean_expectation(
        runs_scored or 0, runs_allowed or 0, float(blend.get("pythagorean_exponent", 2.0))
    )
    if pyth is None:
        pyth = win_pct
    w_wp = float(blend.get("win_percentage_weight", 0.5))
    w_pyth = float(blend.get("pythagorean_weight", 0.5))
    total = w_wp + w_pyth
    if total <= 0:
        return None
    return float((w_wp * win_pct + w_pyth * pyth) / total)


def sigmoid(z: float) -> float:
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def predict_home_win_probability(
    *,
    home_strength: float,
    away_strength: float,
    home_field: float,
    coefficients: Mapping[str, Any],
) -> float:
    intercept = float(coefficients.get("intercept", 0.0))
    sd = float(coefficients.get("strength_diff", 2.0))
    hf = float(coefficients.get("home_field", 0.2))
    z = intercept + sd * (home_strength - away_strength) + hf * home_field
    return round(sigmoid(z), 6)


def apply_prediction_rule(
    *,
    win_probability: float | None,
    yes_ask: float | None,
    tau: float,
) -> str | None:
    """Mechanical prediction rule (no discretion).

    predicted_side = 'yes' when (win_probability - yes_ask) >= +tau,
                     'no'  when (win_probability - yes_ask) <= -tau,
                     None  otherwise (inside the dead band).
    """
    if win_probability is None or yes_ask is None:
        return None
    delta = win_probability - yes_ask
    if delta >= tau:
        return "yes"
    if delta <= -tau:
        return "no"
    return None


def capture_feature_sources(
    parsed_rows: Sequence[Mapping[str, Any]],
    *,
    raw_proxy_dir: Path,
    fetch_json: Callable[[str], Any] | None,
) -> dict[str, Any]:
    """Fetch statsapi/ESPN feeds for the selected games and persist a raw snapshot outside the repo."""
    raw_proxy_dir.mkdir(parents=True, exist_ok=True)
    fetched_at = utc_now()
    getter = fetch_json or fetch_public_json
    payloads: dict[str, Any] = {}
    league_status: dict[str, str] = {"MLB": "available", "KBO": "available", "LMB": "available"}

    mlb_years = sorted({int(r["season_year"]) for r in parsed_rows if r["league"] == "MLB"})
    mlb_dates = sorted({r["game_date"] for r in parsed_rows if r["league"] == "MLB"})
    if mlb_dates:
        start, end = mlb_dates[0], mlb_dates[-1]
        try:
            start_adj, end_adj = _shift_day(start, -1), _shift_day(end, 1)
            sched_url = (
                "https://statsapi.mlb.com/api/v1/schedule?sportId=1&"
                + urllib.parse.urlencode({"startDate": start_adj, "endDate": end_adj})
            )
            payloads["mlb_schedule"] = {"url": sched_url, "payload": getter(sched_url)}
        except Exception as exc:
            payloads["mlb_schedule"] = {
                "url": "statsapi_schedule",
                "error": f"{type(exc).__name__}: {str(exc)[:240]}",
            }
            league_status["MLB"] = "schedule_unavailable"
    for year in mlb_years:
        try:
            stand_url = "https://statsapi.mlb.com/api/v1/standings?" + urllib.parse.urlencode(
                {"leagueId": "103,104", "season": str(year)}
            )
            payloads.setdefault("mlb_standings", {})[str(year)] = {
                "url": stand_url,
                "payload": getter(stand_url),
            }
        except Exception as exc:
            payloads.setdefault("mlb_standings", {})[str(year)] = {
                "error": f"{type(exc).__name__}: {str(exc)[:240]}"
            }
            league_status["MLB"] = "standings_unavailable"

    for league in ("KBO", "LMB"):
        dates = sorted({r["yyyymmdd"] for r in parsed_rows if r["league"] == league})
        if not dates:
            continue
        path = LEAGUE_TO_ESPN_PATH[league]
        for yyyymmdd in dates:
            url = (
                f"https://site.api.espn.com/apis/site/v2/sports/baseball/{path}/scoreboard?"
                + urllib.parse.urlencode({"dates": yyyymmdd})
            )
            try:
                payloads.setdefault(f"espn_{league.lower()}", {})[yyyymmdd] = {
                    "url": url,
                    "payload": getter(url),
                }
            except Exception as exc:
                payloads.setdefault(f"espn_{league.lower()}", {})[yyyymmdd] = {
                    "url": url,
                    "error": f"{type(exc).__name__}: {str(exc)[:240]}",
                }
                league_status[league] = "scoreboard_unavailable"

    raw_snapshot = {
        "schema_version": 1,
        "fetched_at_utc": fetched_at,
        "research_only": True,
        "execution_enabled": False,
        "source_role": "sports_proxy_feature_source_not_official_settlement",
        "official_settlement_source": "official game result (league box score)",
        "league_status": league_status,
        "payloads": payloads,
        "safety": safety_flags(public_market_data_calls=True),
    }
    stamp = fetched_at.replace("-", "").replace(":", "")
    raw_snapshot_path = raw_proxy_dir / f"sports_proxy_feature_capture_{stamp}.json"
    raw_text = json.dumps(raw_snapshot, indent=2, sort_keys=True, default=str) + "\n"
    raw_snapshot_path.write_text(raw_text, encoding="utf-8")
    latest_path = raw_proxy_dir / "sports_proxy_feature_capture_latest.json"
    latest_path.write_text(raw_text, encoding="utf-8")
    return {
        "status": "public_sports_feature_capture_completed",
        "fetched_at_utc": fetched_at,
        "raw_snapshot_path": str(raw_snapshot_path),
        "latest_raw_snapshot_path": str(latest_path),
        "raw_snapshot_outside_repo": outside_repo(raw_snapshot_path, CONTROL_REPO),
        "league_status": league_status,
    }


def no_feature_capture(raw_proxy_dir: Path) -> dict[str, Any]:
    return {
        "status": "public_sports_feature_capture_not_run",
        "raw_proxy_dir": str(raw_proxy_dir),
        "raw_snapshot_outside_repo": outside_repo(raw_proxy_dir, CONTROL_REPO),
        "league_status": {"MLB": "not_captured", "KBO": "not_captured", "LMB": "not_captured"},
    }


def _shift_day(iso_date: str, delta_days: int) -> str:
    try:
        dt = datetime.strptime(iso_date, "%Y-%m-%d").date() + timedelta(days=delta_days)
        return dt.isoformat()
    except ValueError:
        return iso_date


def resolve_mlb_identity(
    parsed: Mapping[str, Any],
    schedule_payload: Any,
) -> dict[str, Any]:
    """Match a statsapi schedule for the (away_id, home_id) pair -> gamePk + team ids."""
    away_id = MLB_CODE_TO_INFO.get(str(parsed["away_code"]), {}).get("id")
    home_id = MLB_CODE_TO_INFO.get(str(parsed["home_code"]), {}).get("id")
    if away_id is None or home_id is None:
        return {"resolved": False, "reason": "unknown_mlb_team_code"}
    game_pk = _find_statsapi_game_pk(schedule_payload, away_id, home_id)
    if game_pk is None:
        return {"resolved": False, "reason": "game_not_in_schedule"}
    return {
        "resolved": True,
        "league": "MLB",
        "external_game_id": game_pk,
        "away_team_id": away_id,
        "home_team_id": home_id,
        "away_team_name": MLB_CODE_TO_INFO[str(parsed["away_code"])]["name"],
        "home_team_name": MLB_CODE_TO_INFO[str(parsed["home_code"])]["name"],
    }


def _find_statsapi_game_pk(schedule_payload: Any, away_id: int, home_id: int) -> int | str | None:
    if not isinstance(schedule_payload, Mapping):
        return None
    for date_block in schedule_payload.get("dates", []) or []:
        if not isinstance(date_block, Mapping):
            continue
        for game in date_block.get("games", []) or []:
            if not isinstance(game, Mapping):
                continue
            try:
                away = int(game["teams"]["away"]["team"]["id"])
                home = int(game["teams"]["home"]["team"]["id"])
            except (KeyError, TypeError, ValueError):
                continue
            if {away, home} == {away_id, home_id}:
                return game.get("gamePk")
    return None


def mlb_strength_index(standings_payload: Any) -> dict[int, dict[str, float]]:
    index: dict[int, dict[str, float]] = {}
    if not isinstance(standings_payload, Mapping):
        return index
    for record in standings_payload.get("records", []) or []:
        if not isinstance(record, Mapping):
            continue
        for tr in record.get("teamRecords", []) or []:
            if not isinstance(tr, Mapping):
                continue
            try:
                tid = int(tr.get("team", {}).get("id"))
            except (KeyError, TypeError, ValueError):
                continue
            index[tid] = {
                "wins": optional_float(tr.get("wins")) or 0.0,
                "losses": optional_float(tr.get("losses")) or 0.0,
                "runs_scored": optional_float(tr.get("runsScored")) or 0.0,
                "runs_allowed": optional_float(tr.get("runsAllowed")) or 0.0,
            }
    return index


def resolve_espn_identity(
    parsed: Mapping[str, Any],
    league: str,
    scoreboard_payload: Any,
) -> dict[str, Any]:
    """Match an ESPN scoreboard event for the (away, home) team pair -> event id + competitor ids."""
    abbr_map = LEAGUE_TO_ESPN_ABBR[league]
    away_abbr = abbr_map.get(str(parsed["away_code"])) or str(parsed["away_code"])
    home_abbr = abbr_map.get(str(parsed["home_code"])) or str(parsed["home_code"])
    if not isinstance(scoreboard_payload, Mapping):
        return {"resolved": False, "reason": "scoreboard_unavailable"}
    for event in scoreboard_payload.get("events", []) or []:
        if not isinstance(event, Mapping):
            continue
        competitions = event.get("competitions", []) or []
        if not competitions or not isinstance(competitions[0], Mapping):
            continue
        competitors = competitions[0].get("competitors", []) or []
        by_abbr: dict[str, Mapping[str, Any]] = {}
        for comp in competitors:
            if not isinstance(comp, Mapping):
                continue
            abbr = str(comp.get("team", {}).get("abbreviation") or "").strip()
            if abbr:
                by_abbr[abbr] = comp
        if away_abbr in by_abbr and home_abbr in by_abbr:
            return {
                "resolved": True,
                "league": league,
                "external_game_id": str(event.get("id")),
                "away_team_id": str(by_abbr[away_abbr].get("id") or away_abbr),
                "home_team_id": str(by_abbr[home_abbr].get("id") or home_abbr),
                "away_team_name": str(by_abbr[away_abbr].get("team", {}).get("displayName") or ""),
                "home_team_name": str(by_abbr[home_abbr].get("team", {}).get("displayName") or ""),
            }
    return {"resolved": False, "reason": "game_not_in_scoreboard"}


def feature_row(
    candidate_row: Mapping[str, Any],
    parsed: Mapping[str, Any],
    *,
    raw: Mapping[str, Any],
    feeds: Mapping[str, Any],
    coefficients: Mapping[str, Any],
    mlb_platform_bridge: Mapping[str, Any],
    mlb_platform_index: Mapping[str, Mapping[str, Any]],
    generated_ts: float,
) -> dict[str, Any]:
    selected = selected_team_code(
        str(candidate_row.get("ticker") or ""), str(candidate_row.get("event_ticker") or "")
    )
    league = parsed["league"]
    yes_ask = optional_float(candidate_row.get("yes_ask"))
    tau = float(coefficients.get("prediction_threshold_tau", 0.05))
    blend = (
        coefficients.get("strength_composition")
        if isinstance(coefficients.get("strength_composition"), Mapping)
        else _DEFAULT_COEFFICIENTS_PAYLOAD["strength_composition"]
    )

    # Identity resolution (per-league isolation by construction).
    identity: dict[str, Any] = {"resolved": False, "reason": "not_attempted"}
    strength_source: str | None = None
    home_strength: float | None = None
    away_strength: float | None = None
    feed_error = False

    if parsed["away_code"] is None or parsed["home_code"] is None:
        # Team suffix could not be decomposed into known league codes -> degrade.
        identity = {"resolved": False, "reason": "unresolvable_team_suffix"}
    elif selected not in (parsed["away_code"], parsed["home_code"]):
        identity = {"resolved": False, "reason": "selected_team_not_in_matchup"}
    else:
        if league == "MLB":
            identity = resolve_mlb_identity(parsed, feeds.get("mlb_schedule", {}).get("payload"))
            stand_payload = (
                feeds.get("mlb_standings", {}).get(str(parsed["season_year"]), {}).get("payload")
            )
            stand_index = mlb_strength_index(stand_payload)
            strength_source = "statsapi_standings"
            home_strength = _strength_from_index(stand_index, identity.get("home_team_id"), blend)
            away_strength = _strength_from_index(stand_index, identity.get("away_team_id"), blend)
            feed_error = bool(feeds.get("mlb_schedule", {}).get("error"))
        else:
            espn_entry = feeds.get(f"espn_{league.lower()}", {}).get(parsed["yyyymmdd"], {})
            sb_payload = espn_entry.get("payload")
            feed_error = bool(espn_entry.get("error")) or sb_payload is None
            identity = resolve_espn_identity(parsed, league, sb_payload)
            strength_source = f"espn_{league.lower()}_scoreboard"
            home_strength = _espn_strength(
                identity.get("home_team_id"), sb_payload, league, parsed["home_code"], blend
            )
            away_strength = _espn_strength(
                identity.get("away_team_id"), sb_payload, league, parsed["away_code"], blend
            )

    home_win_probability: float | None = None
    win_probability: float | None = None
    predicted_side: str | None = None
    threshold_delta: float | None = None
    feature_status = _decide_feature_status(identity, home_strength, away_strength, feed_error)

    if feature_status == "sports_proxy_features_ready":
        home_field = 1.0
        home_win_probability = predict_home_win_probability(
            home_strength=home_strength or 0.0,
            away_strength=away_strength or 0.0,
            home_field=home_field,
            coefficients=coefficients["coefficients"],
        )
        win_probability = (
            home_win_probability
            if selected == parsed["home_code"]
            else round(1.0 - home_win_probability, 6)
        )
        predicted_side = apply_prediction_rule(
            win_probability=win_probability, yes_ask=yes_ask, tau=tau
        )
        threshold_delta = (
            round(abs(win_probability - (yes_ask or 0.0)), 6) if yes_ask is not None else None
        )

    mlb_platform_fields = attach_mlb_platform_model(
        row=candidate_row,
        identity=identity,
        selected_code=selected,
        home_code=parsed["home_code"],
        away_code=parsed["away_code"],
        yes_ask=yes_ask,
        tau=tau,
        bridge=mlb_platform_bridge,
        index=mlb_platform_index,
    )

    return {
        "contract_ticker": candidate_row.get("ticker"),
        "event_ticker": candidate_row.get("event_ticker"),
        "series_ticker": candidate_row.get("series_ticker") or raw.get("series_ticker"),
        "league": league,
        "contract_family": "game_winner_moneyline",
        "yes_interpretation": "selected_team_wins_game_outright",
        "away_code": parsed["away_code"],
        "home_code": parsed["home_code"],
        "selected_code": selected,
        "away_team_id": identity.get("away_team_id"),
        "home_team_id": identity.get("home_team_id"),
        "external_game_id": identity.get("external_game_id"),
        "away_team_name": identity.get("away_team_name"),
        "home_team_name": identity.get("home_team_name"),
        "cluster_key": f"{league}|game_winner|{parsed['game_date']}",
        "title": candidate_row.get("title") or raw.get("title"),
        "close_time": candidate_row.get("close_time") or raw.get("close_time"),
        "expected_expiration_time": candidate_row.get("expected_expiration_time")
        or raw.get("expected_expiration_time"),
        "fresh_time_to_close_hours": round(
            float(candidate_row.get("fresh_time_to_close_hours") or 0.0), 6
        ),
        "fresh_time_to_close_minutes": round(
            float(candidate_row.get("fresh_time_to_close_hours") or 0.0) * 60, 4
        ),
        "fresh_time_to_settlement_hours": round(
            float(
                candidate_row.get("fresh_time_to_settlement_hours")
                or candidate_row.get("fresh_time_to_close_hours")
                or 0.0
            ),
            6,
        ),
        "fresh_time_to_settlement_minutes": round(
            float(
                candidate_row.get("fresh_time_to_settlement_hours")
                or candidate_row.get("fresh_time_to_close_hours")
                or 0.0
            )
            * 60,
            4,
        ),
        "horizon_time_basis": candidate_row.get("horizon_time_basis")
        or "sports_expected_expiration_time",
        "yes_bid": candidate_row.get("yes_bid"),
        "yes_ask": candidate_row.get("yes_ask"),
        "no_bid": candidate_row.get("no_bid"),
        "no_ask": candidate_row.get("no_ask"),
        "yes_spread": candidate_row.get("yes_spread"),
        "home_strength": round(home_strength, 6) if home_strength is not None else None,
        "away_strength": round(away_strength, 6) if away_strength is not None else None,
        "home_field": 1,
        "strength_source": strength_source,
        "home_win_probability": home_win_probability,
        "win_probability": win_probability,
        "predicted_side": predicted_side,
        "threshold_delta": threshold_delta,
        **mlb_platform_fields,
        "official_settlement_source": "official game result (league box score)",
        "official_label_status": "not_captured_feature_packet_only",
        "official_rules_hash": candidate_row.get("official_rules_hash"),
        "official_rules_source": candidate_row.get("official_rules_source"),
        "feature_status": feature_status,
        "feature_policy": "proxy_feature_only_not_official_settlement_label",
        "label_status": "not_labeled_feature_packet_only",
        "calibrated_probability": None,
        "edge_probability": None,
        "expected_value_per_contract": None,
        "ev_status": "not_evaluated_feature_packet_only",
        "usable": False,
        "generated_ts": generated_ts,
    }


def _strength_from_index(
    index: Mapping[int, Mapping[str, float]], team_id: Any, blend: Mapping[str, Any]
) -> float | None:
    if team_id is None:
        return None
    try:
        rec = index.get(int(team_id))
    except (TypeError, ValueError):
        rec = None
    if not rec:
        return None
    return compute_team_strength(
        rec["wins"], rec["losses"], rec["runs_scored"], rec["runs_allowed"], blend
    )


def _espn_strength(
    team_id: Any, scoreboard_payload: Any, league: str, code: str, blend: Mapping[str, Any]
) -> float | None:
    """Best-effort strength from ESPN competitor records (often absent for KBO/LMB)."""
    if not isinstance(scoreboard_payload, Mapping) or team_id is None:
        return None
    abbr_map = LEAGUE_TO_ESPN_ABBR[league]
    abbr = abbr_map.get(code) or code
    for event in scoreboard_payload.get("events", []) or []:
        if not isinstance(event, Mapping):
            continue
        for competition in event.get("competitions", []) or []:
            if not isinstance(competition, Mapping):
                continue
            for comp in competition.get("competitors", []) or []:
                if not isinstance(comp, Mapping):
                    continue
                if str(comp.get("team", {}).get("abbreviation") or "") != abbr:
                    continue
                recs = comp.get("records", [])
                if isinstance(recs, list) and recs:
                    summary = recs[0].get("summary") if isinstance(recs[0], Mapping) else None
                    if isinstance(summary, str) and "-" in summary:
                        parts = summary.split("-")
                        try:
                            wins, losses = float(parts[0]), float(parts[1])
                            return compute_team_strength(wins, losses, None, None, blend)
                        except (ValueError, IndexError):
                            return None
    return None


def _decide_feature_status(
    identity: Mapping[str, Any],
    home_strength: float | None,
    away_strength: float | None,
    feed_error: bool,
) -> str:
    if not identity.get("resolved"):
        if feed_error:
            return "proxy_source_unavailable"
        return "team_identity_unresolved"
    if home_strength is None or away_strength is None:
        return "strength_data_unavailable"
    return "sports_proxy_features_ready"


def build_sports_proxy_feature_packet(
    *,
    universe_scan_path: Path = DEFAULT_UNIVERSE_SCAN_PATH,
    probability_breadth_scout_path: Path = DEFAULT_BREADTH_SCOUT_PATH,
    raw_universe_path: Path = DEFAULT_RAW_UNIVERSE_PATH,
    raw_proxy_dir: Path = DEFAULT_RAW_PROXY_DIR,
    coefficients_path: Path = DEFAULT_STRENGTH_COEFFICIENTS_PATH,
    mlb_platform_model_path: Path | None = DEFAULT_MLB_PLATFORM_MODEL_PATH,
    max_close_hours: float = DEFAULT_MAX_CLOSE_HOURS,
    max_contracts: int = DEFAULT_MAX_CONTRACTS,
    generated_utc: str | None = None,
    capture_public_features: bool = False,
    fetch_json: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    generated_ts = parse_ts(generated) or time.time()
    universe = read_json_or_empty(universe_scan_path)
    breadth = read_json_or_empty(probability_breadth_scout_path)
    raw_universe = read_json_or_empty(raw_universe_path)
    universe_safe = safe_research_artifact(universe)
    breadth_safe = safe_research_artifact(breadth)
    raw_index = raw_market_index(raw_universe)

    coefficients = load_strength_coefficients(coefficients_path)
    mlb_platform_bridge = load_mlb_platform_model_bridge(mlb_platform_model_path)
    mlb_platform_index = mlb_platform_model_index(mlb_platform_bridge)
    selected = select_sports_candidates(
        universe.get("candidates", []),
        raw_index=raw_index,
        generated_ts=generated_ts,
        max_close_hours=max_close_hours,
        max_contracts=max_contracts,
    )
    capture = (
        capture_feature_sources(
            [row["__parsed__"] for row in selected],
            raw_proxy_dir=raw_proxy_dir,
            fetch_json=fetch_json,
        )
        if capture_public_features
        else no_feature_capture(raw_proxy_dir)
    )
    feeds = assemble_feeds(capture)

    feature_rows = [
        feature_row(
            {k: v for k, v in row.items() if k != "__parsed__"},
            parsed=row["__parsed__"],
            raw=raw_index.get(row["ticker"], {}),
            feeds=feeds,
            coefficients=coefficients,
            mlb_platform_bridge=mlb_platform_bridge,
            mlb_platform_index=mlb_platform_index,
            generated_ts=generated_ts,
        )
        for row in selected
    ]
    ready_count = sum(
        1 for r in feature_rows if r["feature_status"] == "sports_proxy_features_ready"
    )
    status = feature_packet_status(
        universe_safe=universe_safe,
        breadth_safe=breadth_safe,
        row_count=len(feature_rows),
        feature_ready_count=ready_count,
        capture_public_features=capture_public_features,
    )
    gates = build_gates(
        universe_safe=universe_safe,
        breadth_safe=breadth_safe,
        raw_universe_present=bool(raw_index),
        capture=capture,
        feature_rows=feature_rows,
    )
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "family_id": "sports_baseball",
        "public_market_data_calls": capture_public_features,
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "summary": {
            "candidate_row_count": len(selected),
            "feature_row_count": len(feature_rows),
            "feature_ready_count": ready_count,
            "feature_partial_count": sum(
                1 for r in feature_rows if r["feature_status"] != "sports_proxy_features_ready"
            ),
            "league_counts": counts(r.get("league") for r in feature_rows),
            "feature_status_counts": counts(r.get("feature_status") for r in feature_rows),
            "predicted_side_counts": counts(r.get("predicted_side") for r in feature_rows),
            "mlb_platform_model_status_counts": counts(
                r.get("mlb_platform_model_status") for r in feature_rows
            ),
            "mlb_platform_predicted_side_counts": counts(
                r.get("mlb_platform_predicted_side") for r in feature_rows
            ),
            "max_close_hours": max_close_hours,
            "max_contracts": max_contracts,
            "gate_counts": gate_counts(gates),
        },
        "source_policy": {
            "official_settlement_source": "official game result (league box score)",
            "official_settlement_source_status": "not_captured_by_this_report",
            "proxy_source_role": "model_feature_only_not_official_settlement",
            "label_policy": "settled Kalshi outcomes (the official game result) are required for labels",
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
            "raw_universe_outside_repo": outside_repo(raw_universe_path, CONTROL_REPO),
            "coefficients_path": str(coefficients_path),
            "mlb_platform_model_path": str(mlb_platform_model_path)
            if mlb_platform_model_path
            else None,
            "mlb_platform_model_sha256": sha256_or_none(mlb_platform_model_path)
            if mlb_platform_model_path and mlb_platform_model_path.exists()
            else None,
        },
        "feature_capture": capture,
        "mlb_platform_model_bridge": {
            key: value for key, value in mlb_platform_bridge.items() if key != "rows"
        },
        "strength_model": {
            "model": coefficients.get("model"),
            "version": coefficients.get("version"),
            "coefficients": coefficients.get("coefficients"),
            "prediction_threshold_tau": coefficients.get("prediction_threshold_tau"),
            "strength_composition": coefficients.get("strength_composition"),
            "fit_provenance": coefficients.get("fit_provenance"),
        },
        "gates": gates,
        "feature_rows": feature_rows,
        "next_action": next_action(status),
        "safety": safety_flags(public_market_data_calls=capture_public_features),
    }


def select_sports_candidates(
    candidates: Any,
    *,
    raw_index: Mapping[str, Mapping[str, Any]],
    generated_ts: float,
    max_close_hours: float,
    max_contracts: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_tickers: set[str] = set()
    for row in candidates if isinstance(candidates, list) else []:
        if not isinstance(row, Mapping):
            continue
        series = str(row.get("series_ticker") or "").upper()
        if series not in SPORTS_SERIES_PREFIXES:
            continue
        event_ticker = str(row.get("event_ticker") or "")
        parsed = parse_sports_event_ticker(event_ticker)
        if parsed is None:
            continue
        ticker = str(row.get("ticker") or "")
        if not ticker or ticker in seen_tickers:
            continue
        raw = raw_index.get(ticker, {})
        horizon_ts, horizon_source = settlement_timestamp(row, raw)
        if horizon_ts is None:
            continue
        fresh_hours = (horizon_ts - generated_ts) / 3600
        if fresh_hours <= 0 or fresh_hours > max_close_hours:
            continue
        enriched = {
            **dict(row),
            "ticker": ticker,
            "series_ticker": series,
            "fresh_time_to_settlement_hours": fresh_hours,
            "fresh_time_to_close_hours": fresh_hours,
            "horizon_time_basis": f"sports_{horizon_source or 'settlement_time'}",
            "__parsed__": parsed,
        }
        rows.append(enriched)
        seen_tickers.add(ticker)
    rows.sort(
        key=lambda item: (
            float(item.get("fresh_time_to_close_hours") or 999999.0),
            str(item.get("league") or ""),
            str(item.get("ticker") or ""),
        )
    )
    return rows[:max_contracts]


def assemble_feeds(capture: Mapping[str, Any]) -> dict[str, Any]:
    """Re-read the raw snapshot payloads written by capture_feature_sources.

    Captured payloads are written to disk (outside the repo) and re-read here so the
    in-memory build always reflects the persisted snapshot (replayable). When capture
    was not run or a fetch failed, the feed entry carries an ``error`` marker.
    """
    feeds: dict[str, Any] = {}
    raw_path = capture.get("latest_raw_snapshot_path")
    snapshot: Mapping[str, Any] = {}
    if raw_path:
        try:
            data = json.loads(Path(raw_path).read_text(encoding="utf-8"))
            if isinstance(data, Mapping):
                snapshot = data
        except (OSError, json.JSONDecodeError):
            snapshot = {}
    payloads = snapshot.get("payloads", {}) if isinstance(snapshot, Mapping) else {}
    if isinstance(payloads.get("mlb_schedule"), Mapping):
        sched = payloads["mlb_schedule"]
        feeds["mlb_schedule"] = (
            {"payload": sched.get("payload"), "error": sched.get("error")}
            if sched.get("error")
            else {"payload": sched.get("payload")}
        )
    else:
        feeds["mlb_schedule"] = {"error": "not_captured"}
    if isinstance(payloads.get("mlb_standings"), Mapping):
        feeds["mlb_standings"] = payloads["mlb_standings"]
    else:
        feeds["mlb_standings"] = {}
    for league in ("KBO", "LMB"):
        key = f"espn_{league.lower()}"
        if isinstance(payloads.get(key), Mapping):
            feeds[key] = payloads[key]
        else:
            feeds[key] = {}
    return feeds


def feature_packet_status(
    *,
    universe_safe: bool,
    breadth_safe: bool,
    row_count: int,
    feature_ready_count: int,
    capture_public_features: bool,
) -> str:
    if not universe_safe:
        return "sports_proxy_feature_packet_blocked_missing_safe_universe_scan"
    if not breadth_safe:
        return "sports_proxy_feature_packet_blocked_missing_probability_breadth_scout"
    if row_count == 0:
        return "sports_proxy_feature_packet_blocked_no_open_fast_sports_contracts"
    if not capture_public_features:
        return "sports_proxy_feature_packet_blocked_feature_capture_missing"
    if feature_ready_count == row_count:
        return "sports_proxy_feature_packet_ready"
    if feature_ready_count > 0:
        return "sports_proxy_feature_packet_partial_feature_coverage"
    # Capture ran but every row degraded (sources probed but unresolved/unavailable).
    return "sports_proxy_feature_packet_blocked_feature_sources_unavailable"


def build_gates(
    *,
    universe_safe: bool,
    breadth_safe: bool,
    raw_universe_present: bool,
    capture: Mapping[str, Any],
    feature_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    return [
        gate(
            "safe_universe_scan_present",
            "pass" if universe_safe else "blocked",
            "A safe, research-only universe scan is required.",
        ),
        gate(
            "probability_breadth_scout_present",
            "pass" if breadth_safe else "blocked",
            "A safe probability breadth scout is required.",
        ),
        gate(
            "raw_universe_snapshot_available",
            "pass" if raw_universe_present else "warn",
            "Raw Kalshi snapshot enriches contract parsing.",
        ),
        gate(
            "raw_feature_snapshot_outside_repo",
            "pass" if capture.get("raw_snapshot_outside_repo") is True else "blocked",
            "Raw public sports feature payloads must stay outside the repo.",
        ),
        gate(
            "feature_rows_keyed",
            "pass" if feature_rows else "blocked",
            "Feature rows must be keyed to exact game-winner contract tickers.",
        ),
        gate(
            "mlb_platform_model_bridge_optional",
            "pass"
            if any(
                r.get("mlb_platform_model_status") == "mlb_platform_model_ready"
                for r in feature_rows
            )
            else "warn",
            "Optional MLB-platform model artifact may enrich rows but never blocks feature-packet creation.",
        ),
        gate(
            "no_ev_or_label_claims",
            "pass"
            if all(
                r.get("usable") is False and r.get("calibrated_probability") is None
                for r in feature_rows
            )
            else "fail",
            "Feature packet must not compute EV, labels, sizing, or usable rows.",
        ),
    ]


def gate(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def next_action(status: str) -> dict[str, str]:
    if status == "sports_proxy_feature_packet_ready":
        return {
            "name": "kalshi_sports_proxy_observation_loop",
            "why": (
                "Contract-keyed sports proxy features are available. The next useful step is repeated "
                "feature snapshots plus settled Kalshi outcome matching for OOS falsification."
            ),
            "stop_condition": (
                "Stop before treating proxy feeds as official settlement labels, computing usable EV, "
                "sizing, execution, or account/order paths."
            ),
        }
    if status == "sports_proxy_feature_packet_partial_feature_coverage":
        return {
            "name": "kalshi_sports_proxy_feature_hardening",
            "why": "Some feature rows are ready, but feature-source coverage is incomplete.",
            "stop_condition": "Stop before fabricating strength data, labels, calibrated probabilities, or EV.",
        }
    return {
        "name": "kalshi_sports_proxy_feature_packet_blocker_review",
        "why": "The sports feature packet is blocked or empty.",
        "stop_condition": "Stop before inventing features, labels, calibrated probabilities, EV, or execution evidence.",
    }


def write_sports_proxy_feature_packet(
    report: Mapping[str, Any], out_dir: Path = DEFAULT_OUT_DIR
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-proxy-feature-packet.json"
    md_path = out_dir / "kalshi-sports-proxy-feature-packet.md"
    csv_path = out_dir / "kalshi-sports-proxy-feature-packet.csv"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_feature_csv(report.get("feature_rows", []), csv_path)
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    latest_json = MACRO_DIR / "latest-kalshi-sports-proxy-feature-packet.json"
    latest_md = MACRO_DIR / "latest-kalshi-sports-proxy-feature-packet.md"
    latest_csv = MACRO_DIR / "latest-kalshi-sports-proxy-feature-packet.csv"
    latest_json.write_text(text, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    write_feature_csv(report.get("feature_rows", []), latest_csv)
    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
        "latest_csv_path": str(latest_csv),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    next_step = report.get("next_action") if isinstance(report.get("next_action"), Mapping) else {}
    lines = [
        "# Kalshi Sports Proxy Feature Packet",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Research only: `{str(report.get('research_only')).lower()}`",
        f"- Execution enabled: `{str(report.get('execution_enabled')).lower()}`",
        f"- Feature rows: `{summary.get('feature_row_count')}`",
        f"- Feature-ready rows: `{summary.get('feature_ready_count')}`",
        f"- League counts: `{summary.get('league_counts')}`",
        "",
        "## Source Policy",
        "",
        "- Official settlement source: `official game result (league box score)`",
        "- Public feature feeds (statsapi/ESPN) role: `model feature only`",
        "- Optional MLB-platform model artifacts role: `model feature only, FDR-gated separately`",
        "- Labels require settled Kalshi outcomes (the official game result).",
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


def write_feature_csv(rows: Any, path: Path) -> None:
    feature_rows = [row for row in rows if isinstance(row, Mapping)]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in feature_rows:
            writer.writerow(dict(row))


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def raw_market_index(raw_universe: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row.get("ticker")): row
        for row in raw_universe.get("markets", [])
        if isinstance(row, Mapping) and row.get("ticker")
    }


def settlement_timestamp(
    candidate: Mapping[str, Any], raw: Mapping[str, Any]
) -> tuple[float | None, str | None]:
    for source in (candidate, raw):
        for key in ("expected_expiration_time", "expiration_time", "settlement_time", "close_time"):
            value = parse_ts(source.get(key))
            if value is not None:
                return value, key
    fallback = optional_float(candidate.get("settlement_ts") or candidate.get("close_ts"))
    return fallback, "candidate_settlement_ts_or_close_ts" if fallback is not None else None


def parse_ts(value: Any) -> float | None:
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


def fetch_public_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "predmarket-alpha research-only"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def safety_flags(*, public_market_data_calls: bool) -> dict[str, Any]:
    return {
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
    }


def gate_counts(gates: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counter = Counter(str(item.get("status") or "blocked") for item in gates)
    return {
        "pass": counter["pass"],
        "warn": counter["warn"],
        "blocked": counter["blocked"],
        "fail": counter["fail"],
    }


def counts(values: Iterable[Any]) -> dict[str, int]:
    counter = Counter(str(value or "unknown") for value in values)
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-scan-path", type=Path, default=DEFAULT_UNIVERSE_SCAN_PATH)
    parser.add_argument(
        "--probability-breadth-scout-path", type=Path, default=DEFAULT_BREADTH_SCOUT_PATH
    )
    parser.add_argument("--raw-universe-path", type=Path, default=DEFAULT_RAW_UNIVERSE_PATH)
    parser.add_argument("--raw-proxy-dir", type=Path, default=DEFAULT_RAW_PROXY_DIR)
    parser.add_argument(
        "--coefficients-path", type=Path, default=DEFAULT_STRENGTH_COEFFICIENTS_PATH
    )
    parser.add_argument(
        "--mlb-platform-model-path", type=Path, default=DEFAULT_MLB_PLATFORM_MODEL_PATH
    )
    parser.add_argument("--max-close-hours", type=float, default=DEFAULT_MAX_CLOSE_HOURS)
    parser.add_argument("--max-contracts", type=int, default=DEFAULT_MAX_CONTRACTS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--capture-public-features", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_sports_proxy_feature_packet(
        universe_scan_path=args.universe_scan_path,
        probability_breadth_scout_path=args.probability_breadth_scout_path,
        raw_universe_path=args.raw_universe_path,
        raw_proxy_dir=args.raw_proxy_dir,
        coefficients_path=args.coefficients_path,
        mlb_platform_model_path=args.mlb_platform_model_path,
        max_close_hours=args.max_close_hours,
        max_contracts=args.max_contracts,
        capture_public_features=args.capture_public_features,
    )
    if args.write:
        paths = write_sports_proxy_feature_packet(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
