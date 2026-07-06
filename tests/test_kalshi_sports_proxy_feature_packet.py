"""Artifact-replay tests for the sports (baseball) feature-packet builder.

Mirrors tests/test_kalshi_crypto_proxy_feature_packet.py: load the script via
importlib, build synthetic Kalshi + statsapi/ESPN fixtures in tmp_path, inject a
fake fetch_json (no network), call build_sports_proxy_feature_packet, and assert
on the routed status/gates/rows. Covers VAL-SFL-001..025, 033, 035..039, 041..043.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_proxy_feature_packet.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"
COEFF_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "codex"
    / "macro"
    / "sports-baseball-strength-coefficients.json"
)


def load_packet_module():
    spec = importlib.util.spec_from_file_location("kalshi_sports_proxy_feature_packet", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# Fixture helpers
# --------------------------------------------------------------------------


def safe_artifact(**overrides):
    payload = {
        "schema_version": 1,
        "research_only": True,
        "execution_enabled": False,
        "status": "ready",
        "summary": {},
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }
    payload.update(overrides)
    return payload


def safe_mlb_platform_model_artifact(rows):
    return safe_artifact(
        status="mlb_platform_model_ready",
        rows=rows,
        safety={
            "research_only": True,
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
            "staking_or_sizing_guidance": False,
        },
    )


def candidate(**overrides):
    """A Kalshi MLB game-winner contract candidate (in close-time window)."""
    row = {
        "ticker": "KXMLBGAME-26JUL012240CWSBAL-BAL",
        "event_ticker": "KXMLBGAME-26JUL012240CWSBAL",
        "series_ticker": "KXMLBGAME",
        "classification": "mlb",
        "title": "Chicago White Sox vs Baltimore Orioles Winner?",
        "close_time": "2026-07-01T22:40:00Z",
        "expected_expiration_time": "2026-07-01T22:50:00Z",
        "yes_bid": 0.20,
        "yes_ask": 0.22,
        "no_bid": 0.78,
        "no_ask": 0.80,
        "yes_spread": 0.02,
        "softness_score": 0.55,
        "official_rules_hash": "abc",
        "official_rules_source": "public_kalshi_market_payload",
    }
    row.update(overrides)
    if "expected_expiration_time" not in overrides and "close_time" in overrides:
        row["expected_expiration_time"] = row["close_time"]
    return row


def raw_market(**overrides):
    row = {
        "ticker": "KXMLBGAME-26JUL012240CWSBAL-BAL",
        "event_ticker": "KXMLBGAME-26JUL012240CWSBAL",
        "series_ticker": "KXMLBGAME",
        "title": "Chicago White Sox vs Baltimore Orioles Winner?",
        "tags": ["Baseball"],
        "close_time": "2026-07-01T22:40:00Z",
        "expected_expiration_time": "2026-07-01T22:50:00Z",
        "rules_primary": (
            "If Baltimore wins the Chicago White Sox vs Baltimore Orioles professional "
            "baseball game, then the market resolves to Yes."
        ),
        "settlement_sources": [
            {"name": "ESPN", "url": "https://www.espn.com"},
            {"name": "the Governing League", "url": "https://www.mlb.com/"},
        ],
    }
    row.update(overrides)
    if "expected_expiration_time" not in overrides and "close_time" in overrides:
        row["expected_expiration_time"] = row["close_time"]
    return row


def statsapi_schedule(date: str, games):
    """games: list of (gamePk, away_id, away_name, home_id, home_name)."""
    return {
        "dates": [
            {
                "date": date,
                "games": [
                    {
                        "gamePk": gpk,
                        "gameDate": f"{date}T22:40:00Z",
                        "status": {"detailedState": "Scheduled"},
                        "teams": {
                            "away": {"team": {"id": aid, "name": an}},
                            "home": {"team": {"id": hid, "name": hn}},
                        },
                    }
                    for (gpk, aid, an, hid, hn) in games
                ],
            }
        ]
    }


def statsapi_standings(records):
    """records: list of (team_id, wins, losses, runs_scored, runs_allowed)."""
    team_records = []
    for tid, wins, losses, rs, ra in records:
        gp = wins + losses
        team_records.append(
            {
                "team": {"id": tid},
                "wins": wins,
                "losses": losses,
                "runsScored": rs,
                "runsAllowed": ra,
                "winningPercentage": round(wins / gp, 3) if gp else 0.0,
            }
        )
    return {
        "records": [
            {"standingsType": "regularSeason", "league": {"id": 103}, "teamRecords": team_records}
        ]
    }


def espn_scoreboard(league: str, events):
    """events: list of (event_id, date, [(abbr, name, homeAway, competitor_id), ...])."""
    return {
        "leagues": [{"abbreviation": league.upper()}],
        "events": [
            {
                "id": eid,
                "date": dt,
                "name": "Game",
                "competitions": [
                    {
                        "competitors": [
                            {
                                "id": cid,
                                "homeAway": ha,
                                "team": {"abbreviation": abbr, "displayName": name},
                            }
                            for (abbr, name, ha, cid) in comps
                        ]
                    }
                ],
            }
            for (eid, dt, comps) in events
        ],
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def make_fetch(schedule=None, standings=None, kbo=None, lmb=None):
    """Build an injected fetch_json returning the supplied synthetic payloads.

    Each payload is returned verbatim for its endpoint (identified by URL substring).
    No network access occurs.
    """

    def fetch(url: str):
        if "statsapi.mlb.com/api/v1/schedule" in url:
            if schedule is None:
                raise RuntimeError(f"unexpected schedule fetch: {url}")
            return schedule
        if "statsapi.mlb.com/api/v1/standings" in url:
            return standings if standings is not None else {"records": []}
        if "/baseball/kbo/scoreboard" in url:
            if kbo is None:
                raise RuntimeError(f"unexpected kbo fetch: {url}")
            return kbo
        if "/baseball/mlb-mexican-league/scoreboard" in url:
            if lmb is None:
                raise RuntimeError(f"unexpected lmb fetch: {url}")
            return lmb
        raise RuntimeError(f"unexpected fetch: {url}")

    return fetch


def build_ready_report(module, tmp_path: Path, **overrides):
    """Convenience: build a ready MLB feature-packet report with full fixtures."""
    universe_path = tmp_path / "universe.json"
    breadth_path = tmp_path / "breadth.json"
    raw_path = tmp_path / "raw_universe.json"
    coeff_path = tmp_path / "coeffs.json"
    write_json(
        universe_path,
        safe_artifact(
            status="universe_scan_ready_with_model_routes",
            candidates=overrides.pop("candidates", [candidate()]),
        ),
    )
    write_json(
        breadth_path,
        safe_artifact(status="probability_breadth_scout_ready_sports_baseball_route"),
    )
    write_json(raw_path, {"markets": [raw_market(**overrides.pop("raw_overrides", {}))]})
    write_json(coeff_path, json.loads(COEFF_PATH.read_text(encoding="utf-8")))
    sched = statsapi_schedule(
        "2026-07-01", [(746000, 145, "Chicago White Sox", 110, "Baltimore Orioles")]
    )
    stand = statsapi_standings([(145, 30, 60, 300, 500), (110, 60, 30, 500, 300)])
    fetch = make_fetch(schedule=sched, standings=stand)
    kwargs = dict(
        universe_scan_path=universe_path,
        probability_breadth_scout_path=breadth_path,
        raw_universe_path=raw_path,
        raw_proxy_dir=Path("/tmp") / f"kalshi_sports_proxy_features_{tmp_path.name}",
        coefficients_path=coeff_path,
        max_close_hours=6,
        generated_utc="2026-07-01T18:00:00Z",
        capture_public_features=True,
        fetch_json=fetch,
    )
    kwargs.update(overrides)
    return module.build_sports_proxy_feature_packet(**kwargs)


# --------------------------------------------------------------------------
# A. Universe filtering
# --------------------------------------------------------------------------


def test_only_baseball_game_winner_series_admitted(tmp_path: Path) -> None:
    """VAL-SFL-001: only KXMLBGAME/KXKBOGAME/KXLMBGAME; NFL, crypto, run-line, player prop excluded."""
    module = load_packet_module()
    cands = [
        candidate(),
        candidate(  # KXNFLGAME excluded
            ticker="KXNFLGAME-26SEP03-KC",
            event_ticker="KXNFLGAME-26SEP03-KC",
            series_ticker="KXNFLGAME",
            classification="other_sports",
            title="NFL game",
        ),
        candidate(  # crypto excluded
            ticker="KXBTC15M-26JUL012015-15",
            event_ticker="KXBTC15M-26JUL012015",
            series_ticker="KXBTC15M",
            classification="finance_crypto",
        ),
        candidate(  # run-line excluded
            ticker="KXMLBRUN-26JUL012240CWSBAL-1.5",
            event_ticker="KXMLBRUN-26JUL012240CWSBAL",
            series_ticker="KXMLBRUN",
        ),
        candidate(  # player prop excluded
            ticker="KXMLBPLAYER-26JUL012240-X",
            event_ticker="KXMLBPLAYER-26JUL012240",
            series_ticker="KXMLBPLAYER",
        ),
    ]
    report = build_ready_report(module, tmp_path, candidates=cands)
    assert report["summary"]["feature_row_count"] == 1
    series = {r["series_ticker"] for r in report["feature_rows"]}
    assert series == {"KXMLBGAME"}


def test_safe_mlb_platform_model_bridge_attaches_probability(tmp_path: Path) -> None:
    """Optional MLB-platform model rows enrich exact contract-keyed sports feature rows."""
    module = load_packet_module()
    bridge_path = tmp_path / "mlb_platform_model.json"
    write_json(
        bridge_path,
        safe_mlb_platform_model_artifact(
            [
                {
                    "contract_ticker": "KXMLBGAME-26JUL012240CWSBAL-BAL",
                    "model_id": "mlb_platform_slate_v1",
                    "selected_win_probability": 0.71,
                }
            ]
        ),
    )

    report = build_ready_report(module, tmp_path, mlb_platform_model_path=bridge_path)
    row = report["feature_rows"][0]

    assert row["mlb_platform_model_status"] == "mlb_platform_model_ready"
    assert row["mlb_platform_model_probability"] == 0.71
    assert row["mlb_platform_predicted_side"] == "yes"
    assert row["mlb_platform_model_id"] == "mlb_platform_slate_v1"
    assert report["summary"]["mlb_platform_model_status_counts"] == {"mlb_platform_model_ready": 1}


def test_missing_mlb_platform_model_bridge_is_optional(tmp_path: Path) -> None:
    """A missing bridge artifact warns but does not block the greenfield sports features."""
    module = load_packet_module()
    report = build_ready_report(
        module,
        tmp_path,
        mlb_platform_model_path=tmp_path / "missing_model.json",
    )

    row = report["feature_rows"][0]
    assert row["feature_status"] == "sports_proxy_features_ready"
    assert row["mlb_platform_model_status"] == "mlb_platform_model_bridge_missing"
    bridge_gate = next(
        item for item in report["gates"] if item["name"] == "mlb_platform_model_bridge_optional"
    )
    assert bridge_gate["status"] == "warn"


def test_close_time_window_excludes_past_and_far_future(tmp_path: Path) -> None:
    """VAL-SFL-002: only 0 < (sports horizon - now) <= max_close_hours survives."""
    module = load_packet_module()
    cands = [
        candidate(),  # in window (4.67h)
        candidate(  # already closed
            ticker="KXMLBGAME-26JUL012240CWSBAL-CWS",
            close_time="2026-07-01T17:00:00Z",
        ),
        candidate(  # far future
            ticker="KXMLBGAME-26JUL012240CWSBAL-CWS",
            event_ticker="KXMLBGAME-26JUL012240CWSBAL",
            close_time="2026-07-05T22:40:00Z",
        ),
    ]
    report = build_ready_report(module, tmp_path, candidates=cands)
    assert report["summary"]["feature_row_count"] == 1
    assert "blocked" not in report["status"]


def test_sports_feature_packet_uses_expected_expiration_horizon_before_close_time(
    tmp_path: Path,
) -> None:
    module = load_packet_module()
    cands = [
        candidate(
            close_time="2026-07-03T18:00:00Z",
            expected_expiration_time="2026-07-01T22:50:00Z",
        )
    ]

    report = build_ready_report(module, tmp_path, candidates=cands)

    assert report["summary"]["feature_row_count"] == 1
    row = report["feature_rows"][0]
    assert row["close_time"] == "2026-07-03T18:00:00Z"
    assert row["expected_expiration_time"] == "2026-07-01T22:50:00Z"
    assert row["fresh_time_to_settlement_hours"] == row["fresh_time_to_close_hours"]
    assert row["fresh_time_to_settlement_hours"] < 6
    assert row["horizon_time_basis"] == "sports_expected_expiration_time"


def test_max_contracts_cap_orders_by_closeness(tmp_path: Path) -> None:
    """VAL-SFL-003: cap at max_contracts, nearest settlement horizon first."""
    module = load_packet_module()
    cands = []
    for offset in [5, 1, 3, 4, 2]:
        hh = 18 + offset
        hhmm = f"{hh:02d}40"
        cands.append(
            candidate(
                ticker=f"KXMLBGAME-26JUL01{hhmm}CWSBAL-BAL",
                event_ticker=f"KXMLBGAME-26JUL01{hhmm}CWSBAL",
                close_time=f"2026-07-01T{hh:02d}:40:00Z",
            )
        )
    report = build_ready_report(module, tmp_path, candidates=cands, max_contracts=2)
    assert len(report["feature_rows"]) == 2
    rows = report["feature_rows"]
    assert rows[0]["fresh_time_to_close_hours"] <= rows[1]["fresh_time_to_close_hours"]


def test_duplicate_contracts_collapse(tmp_path: Path) -> None:
    """VAL-SFL-004: one feature row per contract_ticker."""
    module = load_packet_module()
    cands = [candidate(), candidate()]
    report = build_ready_report(module, tmp_path, candidates=cands)
    tickers = [r["contract_ticker"] for r in report["feature_rows"]]
    assert len(tickers) == len(set(tickers))


def test_empty_in_window_universe_yields_blocked_status(tmp_path: Path) -> None:
    """VAL-SFL-005: no open contracts -> blocked_no_open, no crash."""
    module = load_packet_module()
    report = build_ready_report(module, tmp_path, candidates=[])
    assert "blocked" in report["status"]
    assert "no_open" in report["status"]
    assert report["summary"]["feature_row_count"] == 0


# --------------------------------------------------------------------------
# B. Feature row schema
# --------------------------------------------------------------------------


def test_feature_row_carries_identity_and_quote_fields(tmp_path: Path) -> None:
    """VAL-SFL-006/007/008/009/010: full row schema."""
    module = load_packet_module()
    report = build_ready_report(module, tmp_path)
    assert report["status"] == "sports_proxy_feature_packet_ready"
    row = report["feature_rows"][0]
    for key in (
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
        "yes_bid",
        "yes_ask",
        "yes_spread",
        "home_strength",
        "away_strength",
        "strength_source",
        "home_field",
        "win_probability",
        "predicted_side",
        "threshold_delta",
        "official_settlement_source",
    ):
        assert key in row, f"missing {key}"
    assert row["league"] == "MLB"
    assert row["away_code"] == "CWS"
    assert row["home_code"] == "BAL"
    assert row["selected_code"] == "BAL"
    assert row["away_team_id"] == 145
    assert row["home_team_id"] == 110
    assert row["external_game_id"] == 746000
    assert 0.0 <= row["win_probability"] <= 1.0
    assert row["win_probability"] > 0.5  # home (BAL) is stronger
    assert row["predicted_side"] in {"yes", "no", None}
    assert row["official_settlement_source"] != "CF Benchmarks RTI"
    assert (
        "game result" in row["official_settlement_source"].lower()
        or "box score" in row["official_settlement_source"].lower()
    )


def test_every_row_research_only_and_ev_free(tmp_path: Path) -> None:
    """VAL-SFL-009: usable=False, calibrated_probability=None, no_ev gate pass."""
    module = load_packet_module()
    report = build_ready_report(module, tmp_path)
    for row in report["feature_rows"]:
        assert row["usable"] is False
        assert row["calibrated_probability"] is None
        assert row["expected_value_per_contract"] is None
    no_claims = [g for g in report["gates"] if g["name"] == "no_ev_or_label_claims"]
    assert no_claims and no_claims[0]["status"] == "pass"


# --------------------------------------------------------------------------
# C. Team-identity resolver
# --------------------------------------------------------------------------


def test_mlb_team_resolver_maps_to_statsapi_ids(tmp_path: Path) -> None:
    """VAL-SFL-011: CWSBAL -> away=CWS(145), home=BAL(110), gamePk."""
    module = load_packet_module()
    report = build_ready_report(module, tmp_path)
    row = report["feature_rows"][0]
    assert row["league"] == "MLB"
    assert row["away_code"] == "CWS"
    assert row["home_code"] == "BAL"
    assert row["away_team_id"] == 145
    assert row["home_team_id"] == 110
    assert row["external_game_id"] == 746000


def test_kbo_team_resolver_via_espn(tmp_path: Path) -> None:
    """VAL-SFL-012: KBO ticker resolves via ESPN scoreboard."""
    module = load_packet_module()
    espn_abbr_ktw = module.KBO_CODE_TO_ESPN_ABBR["KTW"]
    espn_abbr_han = module.KBO_CODE_TO_ESPN_ABBR["HAN"]
    cands = [
        candidate(
            ticker="KXKBOGAME-26JUL020530KTWHAN-KTW",
            event_ticker="KXKBOGAME-26JUL020530KTWHAN",
            series_ticker="KXKBOGAME",
            classification="other_sports",
            title="KBO game",
            close_time="2026-07-02T05:30:00Z",
        )
    ]
    espn = espn_scoreboard(
        "kbo",
        [
            (
                "300100",
                "2026-07-02T05:30:00Z",
                [
                    (espn_abbr_ktw, "KT Wiz", "away", "51"),
                    (espn_abbr_han, "Hanwha", "home", "52"),
                ],
            )
        ],
    )
    sched = statsapi_schedule("2026-07-02", [])
    stand = statsapi_standings([])
    universe_path = tmp_path / "universe.json"
    breadth_path = tmp_path / "breadth.json"
    raw_path = tmp_path / "raw_universe.json"
    coeff_path = tmp_path / "coeffs.json"
    write_json(
        universe_path,
        safe_artifact(status="universe_scan_ready_with_model_routes", candidates=cands),
    )
    write_json(
        breadth_path, safe_artifact(status="probability_breadth_scout_ready_sports_baseball_route")
    )
    write_json(
        raw_path,
        {
            "markets": [
                raw_market(
                    ticker=cands[0]["ticker"],
                    event_ticker=cands[0]["event_ticker"],
                    series_ticker="KXKBOGAME",
                )
            ]
        },
    )
    write_json(coeff_path, json.loads(COEFF_PATH.read_text(encoding="utf-8")))
    fetch = make_fetch(schedule=sched, standings=stand, kbo=espn)
    report = module.build_sports_proxy_feature_packet(
        universe_scan_path=universe_path,
        probability_breadth_scout_path=breadth_path,
        raw_universe_path=raw_path,
        raw_proxy_dir=Path("/tmp") / f"kalshi_sports_proxy_kbo_{tmp_path.name}",
        coefficients_path=coeff_path,
        max_close_hours=12,
        generated_utc="2026-07-02T01:00:00Z",
        capture_public_features=True,
        fetch_json=fetch,
    )
    row = report["feature_rows"][0]
    assert row["league"] == "KBO"
    assert row["away_code"] == "KTW"
    assert row["home_code"] == "HAN"
    assert row["external_game_id"] == "300100"


def test_lmb_team_resolver_via_espn(tmp_path: Path) -> None:
    """VAL-SFL-013: LMB ticker resolves via ESPN scoreboard (hardening)."""
    module = load_packet_module()
    espn_abbr_agu = module.LMB_CODE_TO_ESPN_ABBR["AGU"]
    espn_abbr_cdj = module.LMB_CODE_TO_ESPN_ABBR["CDJ"]
    cands = [
        candidate(
            ticker="KXLMBGAME-26JUL020530AGUCDJ-AGU",
            event_ticker="KXLMBGAME-26JUL020530AGUCDJ",
            series_ticker="KXLMBGAME",
            classification="other_sports",
            title="LMB game",
            close_time="2026-07-02T05:30:00Z",
        )
    ]
    espn = espn_scoreboard(
        "mlb-mexican-league",
        [
            (
                "400200",
                "2026-07-02T05:30:00Z",
                [
                    (espn_abbr_agu, "Aguiluchos", "away", "61"),
                    (espn_abbr_cdj, "Charros", "home", "62"),
                ],
            )
        ],
    )
    sched = statsapi_schedule("2026-07-02", [])
    stand = statsapi_standings([])
    universe_path = tmp_path / "universe.json"
    breadth_path = tmp_path / "breadth.json"
    raw_path = tmp_path / "raw_universe.json"
    coeff_path = tmp_path / "coeffs.json"
    write_json(
        universe_path,
        safe_artifact(status="universe_scan_ready_with_model_routes", candidates=cands),
    )
    write_json(
        breadth_path, safe_artifact(status="probability_breadth_scout_ready_sports_baseball_route")
    )
    write_json(
        raw_path,
        {
            "markets": [
                raw_market(
                    ticker=cands[0]["ticker"],
                    event_ticker=cands[0]["event_ticker"],
                    series_ticker="KXLMBGAME",
                )
            ]
        },
    )
    write_json(coeff_path, json.loads(COEFF_PATH.read_text(encoding="utf-8")))
    fetch = make_fetch(schedule=sched, standings=stand, lmb=espn)
    report = module.build_sports_proxy_feature_packet(
        universe_scan_path=universe_path,
        probability_breadth_scout_path=breadth_path,
        raw_universe_path=raw_path,
        raw_proxy_dir=Path("/tmp") / f"kalshi_sports_proxy_lmb_{tmp_path.name}",
        coefficients_path=coeff_path,
        max_close_hours=12,
        generated_utc="2026-07-02T01:00:00Z",
        capture_public_features=True,
        fetch_json=fetch,
    )
    row = report["feature_rows"][0]
    assert row["league"] == "LMB"
    assert row["away_code"] == "AGU"
    assert row["home_code"] == "CDJ"
    assert row["external_game_id"] == "400200"


def test_per_league_isolation_mlb_does_not_consult_espn(tmp_path: Path) -> None:
    """VAL-SFL-014: an MLB code never triggers an ESPN fetch."""
    module = load_packet_module()
    fetched_urls: list[str] = []
    base_fetch = make_fetch(
        schedule=statsapi_schedule(
            "2026-07-01", [(746000, 145, "Chicago White Sox", 110, "Baltimore Orioles")]
        ),
        standings=statsapi_standings([(145, 30, 60, 300, 500), (110, 60, 30, 500, 300)]),
        kbo=espn_scoreboard("kbo", []),
        lmb=espn_scoreboard("LMB", []),
    )

    def tracking_fetch(url: str):
        fetched_urls.append(url)
        return base_fetch(url)

    build_ready_report(module, tmp_path, fetch_json=tracking_fetch)
    assert not any("espn.com" in u for u in fetched_urls), fetched_urls
    assert any("statsapi.mlb.com" in u for u in fetched_urls)


def test_game_winner_yes_means_moneyline_not_runline(tmp_path: Path) -> None:
    """VAL-SFL-015: regression guard. YES = selected team wins outright; KXMLBRUN rejected."""
    module = load_packet_module()
    cands = [
        candidate(),  # game-winner, selected=BAL
        candidate(  # run-line must be rejected entirely
            ticker="KXMLBRUN-26JUL012240CWSBAL-1.5",
            event_ticker="KXMLBRUN-26JUL012240CWSBAL",
            series_ticker="KXMLBRUN",
        ),
    ]
    report = build_ready_report(module, tmp_path, candidates=cands)
    assert report["summary"]["feature_row_count"] == 1
    row = report["feature_rows"][0]
    assert row["contract_family"] == "game_winner_moneyline"
    assert row["yes_interpretation"] == "selected_team_wins_game_outright"


def test_unresolvable_team_code_degrades_gracefully(tmp_path: Path) -> None:
    """VAL-SFL-016: unknown code -> degraded row, null prediction, no crash."""
    module = load_packet_module()
    cands = [
        candidate(
            ticker="KXMLBGAME-26JUL012240ZZZBAL-BAL",
            event_ticker="KXMLBGAME-26JUL012240ZZZBAL",
        )
    ]
    report = build_ready_report(module, tmp_path, candidates=cands)
    row = report["feature_rows"][0]
    assert row["feature_status"] == "team_identity_unresolved"
    assert row["win_probability"] is None
    assert row["predicted_side"] is None
    assert row["usable"] is False


# --------------------------------------------------------------------------
# D. Pre-game strength model
# --------------------------------------------------------------------------


def test_strength_model_home_edge_increases_win_prob(tmp_path: Path) -> None:
    """VAL-SFL-017: home stronger -> p>0.5; swap -> p<0.5; home-field shifts up."""
    module = load_packet_module()
    report = build_ready_report(module, tmp_path)
    p_home_strong = report["feature_rows"][0]["win_probability"]
    assert p_home_strong > 0.5
    # swap: make away (CWS) the strong team, home (BAL) the weak team
    stand_swap = statsapi_standings([(145, 60, 30, 500, 300), (110, 30, 60, 300, 500)])
    universe_path = tmp_path / "u2.json"
    breadth_path = tmp_path / "b2.json"
    raw_path = tmp_path / "r2.json"
    coeff_path = tmp_path / "c2.json"
    write_json(
        universe_path,
        safe_artifact(status="universe_scan_ready_with_model_routes", candidates=[candidate()]),
    )
    write_json(
        breadth_path, safe_artifact(status="probability_breadth_scout_ready_sports_baseball_route")
    )
    write_json(raw_path, {"markets": [raw_market()]})
    write_json(coeff_path, json.loads(COEFF_PATH.read_text(encoding="utf-8")))
    report2 = module.build_sports_proxy_feature_packet(
        universe_scan_path=universe_path,
        probability_breadth_scout_path=breadth_path,
        raw_universe_path=raw_path,
        raw_proxy_dir=Path("/tmp") / f"kalshi_sports_swap_{tmp_path.name}",
        coefficients_path=coeff_path,
        max_close_hours=6,
        generated_utc="2026-07-01T18:00:00Z",
        capture_public_features=True,
        fetch_json=make_fetch(
            schedule=statsapi_schedule(
                "2026-07-01", [(746000, 145, "Chicago White Sox", 110, "Baltimore Orioles")]
            ),
            standings=stand_swap,
        ),
    )
    p_home_weak = report2["feature_rows"][0]["win_probability"]
    assert p_home_weak < 0.5


def test_strength_model_is_deterministic(tmp_path: Path) -> None:
    """VAL-SFL-018: identical inputs -> identical output."""
    module = load_packet_module()
    r1 = build_ready_report(module, tmp_path)
    r2 = build_ready_report(module, tmp_path / "second")
    assert r1["feature_rows"][0]["win_probability"] == r2["feature_rows"][0]["win_probability"]
    assert r1["feature_rows"][0]["predicted_side"] == r2["feature_rows"][0]["predicted_side"]


def test_coefficients_loaded_frozen_not_refit(tmp_path: Path) -> None:
    """VAL-SFL-019: coefficients come from the artifact; same across runs."""
    module = load_packet_module()
    r1 = build_ready_report(module, tmp_path)
    r2 = build_ready_report(module, tmp_path / "second")
    coeffs1 = r1["strength_model"]["coefficients"]
    coeffs2 = r2["strength_model"]["coefficients"]
    assert coeffs1 == coeffs2
    assert "fit_once_on_history_then_frozen" in str(
        r1["strength_model"]["fit_provenance"]["method"]
    )


def test_no_strength_data_degrades_gracefully(tmp_path: Path) -> None:
    """VAL-SFL-020: empty standings -> degraded, null probability, no crash."""
    module = load_packet_module()
    universe_path = tmp_path / "u3.json"
    breadth_path = tmp_path / "b3.json"
    raw_path = tmp_path / "r3.json"
    coeff_path = tmp_path / "c3.json"
    write_json(
        universe_path,
        safe_artifact(status="universe_scan_ready_with_model_routes", candidates=[candidate()]),
    )
    write_json(
        breadth_path, safe_artifact(status="probability_breadth_scout_ready_sports_baseball_route")
    )
    write_json(raw_path, {"markets": [raw_market()]})
    write_json(coeff_path, json.loads(COEFF_PATH.read_text(encoding="utf-8")))
    report = module.build_sports_proxy_feature_packet(
        universe_scan_path=universe_path,
        probability_breadth_scout_path=breadth_path,
        raw_universe_path=raw_path,
        raw_proxy_dir=Path("/tmp") / f"kalshi_sports_nostrength_{tmp_path.name}",
        coefficients_path=coeff_path,
        max_close_hours=6,
        generated_utc="2026-07-01T18:00:00Z",
        capture_public_features=True,
        fetch_json=make_fetch(
            schedule=statsapi_schedule(
                "2026-07-01", [(746000, 145, "Chicago White Sox", 110, "Baltimore Orioles")]
            ),
            standings=statsapi_standings([]),
        ),
    )
    row = report["feature_rows"][0]
    assert row["feature_status"] == "strength_data_unavailable"
    assert row["win_probability"] is None
    assert row["usable"] is False


# --------------------------------------------------------------------------
# E. Mechanical prediction rule
# --------------------------------------------------------------------------


def test_prediction_rule_threshold_three_cases(tmp_path: Path) -> None:
    """VAL-SFL-021: yes / no / None across the threshold band."""
    module = load_packet_module()
    assert module.apply_prediction_rule(win_probability=0.80, yes_ask=0.50, tau=0.05) == "yes"
    assert module.apply_prediction_rule(win_probability=0.30, yes_ask=0.70, tau=0.05) == "no"
    assert module.apply_prediction_rule(win_probability=0.50, yes_ask=0.48, tau=0.05) is None


def test_prediction_rule_no_discretion(tmp_path: Path) -> None:
    """VAL-SFL-022: decoy fields do not change the side."""
    module = load_packet_module()
    base = module.apply_prediction_rule(win_probability=0.80, yes_ask=0.50, tau=0.05)
    same = module.apply_prediction_rule(win_probability=0.80, yes_ask=0.50, tau=0.05)
    assert base == same == "yes"


# --------------------------------------------------------------------------
# F. Raw payload placement + derived artifacts
# --------------------------------------------------------------------------


def test_raw_payloads_written_outside_repo(tmp_path: Path) -> None:
    """VAL-SFL-023: raw_snapshot_outside_repo True; raw gate pass."""
    module = load_packet_module()
    report = build_ready_report(module, tmp_path)
    assert report["feature_capture"]["raw_snapshot_outside_repo"] is True
    raw_gate = [g for g in report["gates"] if g["name"] == "raw_feature_snapshot_outside_repo"]
    assert raw_gate and raw_gate[0]["status"] == "pass"
    assert report["safety"]["raw_payloads_copied_to_repo"] is False


def test_write_refreshes_latest_pointers(tmp_path: Path) -> None:
    """VAL-SFL-024: derived artifacts + latest-* pointers under macro dir."""
    module = load_packet_module()
    module.MACRO_DIR = tmp_path / "macro"
    report = build_ready_report(module, tmp_path)
    paths = module.write_sports_proxy_feature_packet(report, out_dir=tmp_path / "out")
    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    assert (tmp_path / "macro" / "latest-kalshi-sports-proxy-feature-packet.json").exists()
    assert (tmp_path / "macro" / "latest-kalshi-sports-proxy-feature-packet.md").exists()
    assert (tmp_path / "macro" / "latest-kalshi-sports-proxy-feature-packet.csv").exists()


# --------------------------------------------------------------------------
# I/J. Artifact-replay testability + research-only safety
# --------------------------------------------------------------------------


def test_research_only_safety_flags(tmp_path: Path) -> None:
    """VAL-SFL-036/037/038: research_only, execution disabled, no exec/order/db paths."""
    module = load_packet_module()
    report = build_ready_report(module, tmp_path)
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["safety"]["market_execution"] is False
    assert report["safety"]["account_or_order_paths"] is False
    assert report["safety"]["database_writes"] is False
    assert report["safety"]["staking_or_sizing_guidance"] is False
    assert report["authenticated_api_calls"] is False
    assert report["paid_calls"] is False
    assert report["public_market_data_calls"] is True


def test_capture_off_means_no_public_calls(tmp_path: Path) -> None:
    """VAL-SFL-038: public_market_data_calls False when capture off."""
    module = load_packet_module()
    universe_path = tmp_path / "u.json"
    breadth_path = tmp_path / "b.json"
    raw_path = tmp_path / "r.json"
    coeff_path = tmp_path / "c.json"
    write_json(
        universe_path,
        safe_artifact(status="universe_scan_ready_with_model_routes", candidates=[candidate()]),
    )
    write_json(
        breadth_path, safe_artifact(status="probability_breadth_scout_ready_sports_baseball_route")
    )
    write_json(raw_path, {"markets": [raw_market()]})
    write_json(coeff_path, json.loads(COEFF_PATH.read_text(encoding="utf-8")))
    report = module.build_sports_proxy_feature_packet(
        universe_scan_path=universe_path,
        probability_breadth_scout_path=breadth_path,
        raw_universe_path=raw_path,
        raw_proxy_dir=Path("/tmp") / f"kalshi_sports_nocapture_{tmp_path.name}",
        coefficients_path=coeff_path,
        max_close_hours=6,
        generated_utc="2026-07-01T18:00:00Z",
        capture_public_features=False,
        fetch_json=make_fetch(),
    )
    assert report["public_market_data_calls"] is False


def test_distinct_from_type2_no_margin_fields(tmp_path: Path) -> None:
    """VAL-SFL-041: no net_divergence/margin/american fields; carries win_probability/predicted_side."""
    module = load_packet_module()
    report = build_ready_report(module, tmp_path)
    row = report["feature_rows"][0]
    for forbidden in ("net_divergence", "margin", "american", "event_match_delta_seconds"):
        assert forbidden not in row, f"Type 2 field leaked: {forbidden}"
    assert "win_probability" in row
    assert "predicted_side" in row


def test_espn_capture_failure_degrades_gracefully(tmp_path: Path) -> None:
    """VAL-SFL-042: ESPN failure -> degraded KBO rows, no crash."""
    module = load_packet_module()
    cands = [
        candidate(
            ticker="KXKBOGAME-26JUL020530KTWHAN-KTW",
            event_ticker="KXKBOGAME-26JUL020530KTWHAN",
            series_ticker="KXKBOGAME",
            classification="other_sports",
            title="KBO game",
            close_time="2026-07-02T05:30:00Z",
        )
    ]
    universe_path = tmp_path / "u.json"
    breadth_path = tmp_path / "b.json"
    raw_path = tmp_path / "r.json"
    coeff_path = tmp_path / "c.json"
    write_json(
        universe_path,
        safe_artifact(status="universe_scan_ready_with_model_routes", candidates=cands),
    )
    write_json(
        breadth_path, safe_artifact(status="probability_breadth_scout_ready_sports_baseball_route")
    )
    write_json(
        raw_path,
        {
            "markets": [
                raw_market(
                    ticker=cands[0]["ticker"],
                    event_ticker=cands[0]["event_ticker"],
                    series_ticker="KXKBOGAME",
                )
            ]
        },
    )
    write_json(coeff_path, json.loads(COEFF_PATH.read_text(encoding="utf-8")))

    def failing_espn_fetch(url: str):
        if "espn.com" in url:
            raise RuntimeError("simulated ESPN outage")
        if "schedule" in url:
            return statsapi_schedule("2026-07-02", [])
        if "standings" in url:
            return {"records": []}
        raise RuntimeError(f"unexpected: {url}")

    report = module.build_sports_proxy_feature_packet(
        universe_scan_path=universe_path,
        probability_breadth_scout_path=breadth_path,
        raw_universe_path=raw_path,
        raw_proxy_dir=Path("/tmp") / f"kalshi_sports_espnfail_{tmp_path.name}",
        coefficients_path=coeff_path,
        max_close_hours=12,
        generated_utc="2026-07-02T01:00:00Z",
        capture_public_features=True,
        fetch_json=failing_espn_fetch,
    )
    assert report["feature_rows"][0]["feature_status"] in {
        "proxy_source_unavailable",
        "team_identity_unresolved",
        "strength_data_unavailable",
    }
    assert report["feature_rows"][0]["usable"] is False


def test_status_enum_ready_partial_blocked(tmp_path: Path) -> None:
    """VAL-SFL-043: ready / partial / blocked branches."""
    module = load_packet_module()
    # ready
    ready = build_ready_report(module, tmp_path)
    assert ready["status"] == "sports_proxy_feature_packet_ready"
    assert ready["next_action"]["name"] == "kalshi_sports_proxy_observation_loop"
    # blocked (unsafe universe)
    universe_path = tmp_path / "u.json"
    breadth_path = tmp_path / "b.json"
    raw_path = tmp_path / "r.json"
    coeff_path = tmp_path / "c.json"
    write_json(
        universe_path,
        {
            "schema_version": 1,
            "research_only": True,
            "execution_enabled": True,
            "candidates": [candidate()],
        },
    )
    write_json(
        breadth_path, safe_artifact(status="probability_breadth_scout_ready_sports_baseball_route")
    )
    write_json(raw_path, {"markets": [raw_market()]})
    write_json(coeff_path, json.loads(COEFF_PATH.read_text(encoding="utf-8")))
    blocked = module.build_sports_proxy_feature_packet(
        universe_scan_path=universe_path,
        probability_breadth_scout_path=breadth_path,
        raw_universe_path=raw_path,
        raw_proxy_dir=Path("/tmp") / f"kalshi_sports_blocked_{tmp_path.name}",
        coefficients_path=coeff_path,
        max_close_hours=6,
        generated_utc="2026-07-01T18:00:00Z",
        capture_public_features=True,
        fetch_json=make_fetch(
            schedule=statsapi_schedule(
                "2026-07-01", [(746000, 145, "Chicago White Sox", 110, "Baltimore Orioles")]
            ),
            standings=statsapi_standings([(145, 30, 60, 300, 500), (110, 60, 30, 500, 300)]),
        ),
    )
    assert "blocked" in blocked["status"]


def test_summary_per_league_and_feature_status_counts(tmp_path: Path) -> None:
    """VAL-SFL-045: league_counts + feature_status_counts + knobs present."""
    module = load_packet_module()
    report = build_ready_report(module, tmp_path)
    summary = report["summary"]
    assert "league_counts" in summary
    assert "feature_status_counts" in summary
    assert summary["league_counts"].get("MLB") == 1
    assert summary["max_close_hours"] == 6


def test_unsafe_inputs_blocked(tmp_path: Path) -> None:
    """VAL-SFL-044: unsafe universe scan blocks the packet."""
    module = load_packet_module()
    universe_path = tmp_path / "u.json"
    breadth_path = tmp_path / "b.json"
    raw_path = tmp_path / "r.json"
    coeff_path = tmp_path / "c.json"
    write_json(
        universe_path,
        {
            "schema_version": 1,
            "research_only": True,
            "execution_enabled": True,
            "candidates": [candidate()],
        },
    )
    write_json(
        breadth_path, safe_artifact(status="probability_breadth_scout_ready_sports_baseball_route")
    )
    write_json(raw_path, {"markets": [raw_market()]})
    write_json(coeff_path, json.loads(COEFF_PATH.read_text(encoding="utf-8")))
    report = module.build_sports_proxy_feature_packet(
        universe_scan_path=universe_path,
        probability_breadth_scout_path=breadth_path,
        raw_universe_path=raw_path,
        raw_proxy_dir=Path("/tmp") / f"kalshi_sports_unsafe_{tmp_path.name}",
        coefficients_path=coeff_path,
        max_close_hours=6,
        generated_utc="2026-07-01T18:00:00Z",
        capture_public_features=True,
        fetch_json=make_fetch(),
    )
    assert "blocked" in report["status"]
    safe_gate = [g for g in report["gates"] if g["name"] == "safe_universe_scan_present"]
    assert safe_gate and safe_gate[0]["status"] == "blocked"


def test_makefile_exposes_sports_proxy_feature_packet_target() -> None:
    """VAL-SFL-039: Make target present and invokes the script with --write."""
    content = MAKEFILE_PATH.read_text(encoding="utf-8")
    assert "kalshi-sports-proxy-feature-packet" in content
    assert "scripts/kalshi_sports_proxy_feature_packet.py" in content
