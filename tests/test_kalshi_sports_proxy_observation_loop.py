"""Artifact-replay tests for the sports (baseball) observation/label loop.

Mirrors tests/test_kalshi_crypto_proxy_observation_loop.py: load the script via
importlib, build a synthetic sports feature packet + settled Kalshi snapshot in
tmp_path, call build_sports_proxy_observation_loop(...), and assert on the routed
status/gates/observation+label rows. Covers VAL-SFL-026..032, 034, 035, 040.

Key sports-specific differences from crypto (asserted below):
- feature_status ready value is ``sports_proxy_features_ready``.
- observation_id prefix is ``sports_obs_``.
- packet_type strings are ``kalshi_sports_proxy_feature_*``.
- Labels come from Kalshi public settlement (the contract's actual settlement
  outcome; the official game result / league box score is Kalshi's documented
  settlement source) -- never from the strength-model win_probability.
- No orderbook-depth enrichment (crypto-proxy-specific, dropped for sports).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_proxy_observation_loop.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_loop_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_sports_proxy_observation_loop", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# --------------------------------------------------------------------------
# Fixture helpers
# --------------------------------------------------------------------------


def safe_feature_packet(**overrides):
    payload = {
        "schema_version": 1,
        "generated_utc": "2026-07-02T00:05:00Z",
        "status": "sports_proxy_feature_packet_ready",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "summary": {"feature_row_count": 1, "feature_ready_count": 1},
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
        "feature_rows": [feature_row()],
    }
    payload.update(overrides)
    return payload


def feature_row(**overrides):
    """A ready sports feature row (moneyline game-winner, strength model resolved)."""
    row = {
        "contract_ticker": "KXMLBGAME-26JUL012240CWSBAL-BAL",
        "event_ticker": "KXMLBGAME-26JUL012240CWSBAL",
        "series_ticker": "KXMLBGAME",
        "league": "MLB",
        "contract_family": "game_winner_moneyline",
        "yes_interpretation": "selected_team_wins_game_outright",
        "away_code": "CWS",
        "home_code": "BAL",
        "selected_code": "BAL",
        "away_team_id": 145,
        "home_team_id": 110,
        "external_game_id": 123456,
        "cluster_key": "MLB|game_winner|2026-07-01",
        "close_time": "2026-07-01T22:40:00Z",
        "expected_expiration_time": "2026-07-02T01:40:00Z",
        "yes_bid": 0.20,
        "yes_ask": 0.22,
        "no_bid": 0.78,
        "no_ask": 0.80,
        "yes_spread": 0.02,
        "home_strength": 0.42,
        "away_strength": 0.48,
        "home_field": 1,
        "strength_source": "statsapi_standings",
        "home_win_probability": 0.40,
        "win_probability": 0.60,
        "predicted_side": "yes",
        "threshold_delta": 0.38,
        "mlb_platform_model_status": "mlb_platform_model_ready",
        "mlb_platform_model_probability": 0.66,
        "mlb_platform_predicted_side": "yes",
        "mlb_platform_threshold_delta": 0.44,
        "mlb_platform_model_id": "mlb_platform_slate_v1",
        "mlb_platform_match_key": "contract:KXMLBGAME-26JUL012240CWSBAL-BAL",
        "official_settlement_source": "official game result (league box score)",
        "official_label_status": "not_captured_feature_packet_only",
        "feature_status": "sports_proxy_features_ready",
        "feature_policy": "proxy_feature_only_not_official_settlement_label",
        "label_status": "not_labeled_feature_packet_only",
        "calibrated_probability": None,
        "expected_value_per_contract": None,
        "usable": False,
    }
    row.update(overrides)
    return row


def settled_snapshot(**overrides):
    """A Kalshi public settled-markets snapshot (research-only)."""
    payload = {
        "schema_version": 1,
        "created_at_utc": "2026-07-02T01:45:00Z",
        "status": "kalshi_public_settled_fetch_ok",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
        "markets": [
            {
                "ticker": "KXMLBGAME-26JUL012240CWSBAL-BAL",
                "event_ticker": "KXMLBGAME-26JUL012240CWSBAL",
                "series_ticker": "KXMLBGAME",
                "result": "yes",
                "settlement_value_dollars": "1.0000",
                "close_time": "2026-07-01T22:40:00Z",
                "settlement_ts": "2026-07-02T01:40:00Z",
            }
        ],
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------
# Tests: VAL-SFL-026 (ready rows only), 031/036/037/038 (research-only safety)
# --------------------------------------------------------------------------


def test_sports_proxy_observation_loop_records_ready_feature_rows_without_ev_or_probability_claims(
    tmp_path: Path,
) -> None:
    module = load_loop_module()
    feature_path = tmp_path / "feature.json"
    settled_path = tmp_path / "missing-settled.json"
    write_json(feature_path, safe_feature_packet())

    report = module.build_sports_proxy_observation_loop(
        feature_packet_path=feature_path,
        settled_snapshot_path=settled_path,
        observation_dir=tmp_path / "observations",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-02T00:06:00Z",
    )

    assert report["status"] == "sports_proxy_observation_loop_ready_waiting_settlement"
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["summary"]["new_observation_row_count"] == 1
    assert report["summary"]["label_row_count"] == 0
    assert report["summary"]["next_expected_expiration_utc"] == "2026-07-02T01:40:00Z"
    assert report["summary"]["due_observation_row_count"] == 0
    row = report["observation_packet"]["rows"][0]
    assert row["contract_ticker"] == "KXMLBGAME-26JUL012240CWSBAL-BAL"
    assert row["observation_id"].startswith("sports_obs_")
    assert row["label_status"] == "pending_settled_kalshi_outcome"
    assert row["calibrated_probability"] is None
    assert row["expected_value_per_contract"] is None
    assert row["usable"] is False
    # Sports-specific fields are carried through.
    assert row["league"] == "MLB"
    assert row["cluster_key"] == "MLB|game_winner|2026-07-01"
    assert row["predicted_side"] == "yes"
    assert row["mlb_platform_model_probability"] == 0.66
    assert row["mlb_platform_predicted_side"] == "yes"
    assert row["win_probability"] == 0.60
    assert report["safety"]["market_execution"] is False
    assert report["safety"]["account_or_order_paths"] is False
    assert report["safety"]["database_writes"] is False
    assert report["safety"]["staking_or_sizing_guidance"] is False


def test_sports_proxy_observation_loop_only_snapshots_ready_feature_rows(tmp_path: Path) -> None:
    """VAL-SFL-026: degraded/unresolved rows are excluded from observation emission."""
    module = load_loop_module()
    feature_path = tmp_path / "feature.json"
    write_json(
        feature_path,
        safe_feature_packet(
            feature_rows=[
                feature_row(contract_ticker="KXMLBGAME-26JUL012240CWSBAL-BAL"),
                feature_row(
                    contract_ticker="KXMLBGAME-26JUL012240CWSBAL-CWS",
                    selected_code="CWS",
                    feature_status="team_identity_unresolved",
                    win_probability=None,
                    predicted_side=None,
                ),
            ],
            summary={"feature_row_count": 2, "feature_ready_count": 1},
        ),
    )

    report = module.build_sports_proxy_observation_loop(
        feature_packet_path=feature_path,
        settled_snapshot_path=tmp_path / "missing-settled.json",
        observation_dir=tmp_path / "observations",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-02T00:06:00Z",
    )

    assert report["summary"]["new_observation_row_count"] == 1
    tickers = [r["contract_ticker"] for r in report["observation_packet"]["rows"]]
    assert tickers == ["KXMLBGAME-26JUL012240CWSBAL-BAL"]


# --------------------------------------------------------------------------
# Tests: VAL-SFL-029, 030, 031 (labels from Kalshi public settlement)
# --------------------------------------------------------------------------


def test_sports_proxy_observation_loop_labels_exact_ticker_from_public_settlement(
    tmp_path: Path,
) -> None:
    module = load_loop_module()
    feature_path = tmp_path / "feature.json"
    settled_path = tmp_path / "settled.json"
    write_json(feature_path, safe_feature_packet())
    write_json(settled_path, settled_snapshot())

    report = module.build_sports_proxy_observation_loop(
        feature_packet_path=feature_path,
        settled_snapshot_path=settled_path,
        observation_dir=tmp_path / "observations",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-02T01:45:00Z",
    )

    assert report["status"] == "sports_proxy_observation_loop_label_rows_ready"
    assert report["summary"]["label_row_count"] == 1
    assert report["summary"]["due_observation_row_count"] == 1
    assert report["summary"]["due_distinct_contract_count"] == 1
    assert report["summary"]["next_public_label_probe_utc"] == "2026-07-02T01:45:00Z"
    assert report["summary"]["blocked_label_row_count"] == 0
    label = report["label_packet"]["rows"][0]
    assert label["label_status"] == "labeled_from_public_kalshi_settled_market"
    assert label["yes_outcome"] == 1
    assert label["mlb_platform_model_probability"] == 0.66
    assert label["mlb_platform_predicted_side"] == "yes"
    assert label["label_source"] == "public_kalshi_settled_market_payload"
    assert label["calibrated_probability"] is None
    assert label["expected_value_per_contract"] is None
    assert label["usable"] is False


def test_label_follows_settlement_not_model_probability(tmp_path: Path) -> None:
    """VAL-SFL-030: the label follows Kalshi settlement even when the model disagreed.

    Construct a case where the model predicted 'no' (win_probability < 0.5) but Kalshi
    settled YES; the label's yes_outcome must follow the settlement (1), not the model.
    """
    module = load_loop_module()
    feature_path = tmp_path / "feature.json"
    settled_path = tmp_path / "settled.json"
    write_json(
        feature_path,
        safe_feature_packet(
            feature_rows=[
                feature_row(
                    win_probability=0.25,
                    home_win_probability=0.75,
                    predicted_side="no",
                    threshold_delta=0.03,
                ),
            ],
        ),
    )
    write_json(settled_path, settled_snapshot())

    report = module.build_sports_proxy_observation_loop(
        feature_packet_path=feature_path,
        settled_snapshot_path=settled_path,
        observation_dir=tmp_path / "observations",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-02T01:45:00Z",
    )

    label = report["label_packet"]["rows"][0]
    assert label["yes_outcome"] == 1  # follows settlement, NOT the model's predicted_side='no'
    assert label["label_source"] == "public_kalshi_settled_market_payload"


# --------------------------------------------------------------------------
# Tests: VAL-SFL-027 (dedupe by observation_id)
# --------------------------------------------------------------------------


def test_sports_proxy_observation_loop_dedupes_by_observation_id_across_runs(
    tmp_path: Path,
) -> None:
    module = load_loop_module()
    feature_path = tmp_path / "feature.json"
    settled_path = tmp_path / "settled.json"
    observation_dir = tmp_path / "observations"
    label_dir = tmp_path / "labels"
    write_json(feature_path, safe_feature_packet())
    write_json(settled_path, settled_snapshot())
    first = module.build_sports_proxy_observation_loop(
        feature_packet_path=feature_path,
        settled_snapshot_path=settled_path,
        observation_dir=observation_dir,
        label_dir=label_dir,
        generated_utc="2026-07-02T01:45:00Z",
    )
    write_json(observation_dir / "observations.json", first["observation_packet"])
    write_json(label_dir / "labels.json", first["label_packet"])

    second = module.build_sports_proxy_observation_loop(
        feature_packet_path=feature_path,
        settled_snapshot_path=settled_path,
        observation_dir=observation_dir,
        label_dir=label_dir,
        generated_utc="2026-07-02T01:46:00Z",
    )

    assert second["summary"]["existing_observation_row_count"] == 1
    assert second["summary"]["new_observation_row_count"] == 0
    assert second["summary"]["existing_label_row_count"] == 1
    assert second["summary"]["new_label_row_count"] == 0
    assert second["summary"]["label_row_count"] == 1
    assert second["observation_packet"]["rows"] == []
    assert second["label_packet"]["rows"] == []


# --------------------------------------------------------------------------
# Tests: VAL-SFL-032 (missing settlement blocks label)
# --------------------------------------------------------------------------


def test_missing_kalshi_settlement_blocks_label_without_guessing(tmp_path: Path) -> None:
    """VAL-SFL-032: a due observation with no settled Kalshi entry blocks the label."""
    module = load_loop_module()
    feature_path = tmp_path / "feature.json"
    settled_path = tmp_path / "settled.json"
    write_json(feature_path, safe_feature_packet())
    # Settled snapshot exists but does NOT contain our ticker (game ended but not yet settled).
    write_json(settled_path, settled_snapshot(markets=[]))

    report = module.build_sports_proxy_observation_loop(
        feature_packet_path=feature_path,
        settled_snapshot_path=settled_path,
        observation_dir=tmp_path / "observations",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-02T01:45:00Z",
    )

    assert report["summary"]["label_row_count"] == 0
    assert report["summary"]["blocked_label_row_count"] >= 1
    blocked = report["blocked_label_rows_sample"][0]
    assert blocked["label_status"] == "pending_contract_not_settled_in_snapshot"
    assert blocked["contract_ticker"] == "KXMLBGAME-26JUL012240CWSBAL-BAL"


# --------------------------------------------------------------------------
# Tests: blocked feature packet
# --------------------------------------------------------------------------


def test_sports_proxy_observation_loop_blocks_missing_or_unsafe_feature_packet(
    tmp_path: Path,
) -> None:
    module = load_loop_module()
    feature_path = tmp_path / "unsafe-feature.json"
    write_json(feature_path, safe_feature_packet(execution_enabled=True))

    report = module.build_sports_proxy_observation_loop(
        feature_packet_path=feature_path,
        settled_snapshot_path=tmp_path / "settled.json",
        observation_dir=tmp_path / "observations",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-02T00:06:00Z",
    )

    assert report["status"] == "sports_proxy_observation_loop_blocked_missing_feature_packet"
    assert report["summary"]["feature_packet_safe"] is False
    gates = {item["name"]: item for item in report["gates"]}
    assert gates["sports_proxy_feature_packet_safe"]["status"] == "blocked"


# --------------------------------------------------------------------------
# Tests: VAL-SFL-028 (probe after game end only)
# --------------------------------------------------------------------------


def test_due_observed_tickers_only_includes_past_expected_expiration(tmp_path: Path) -> None:
    module = load_loop_module()
    feature_path = tmp_path / "feature.json"
    write_json(
        feature_path,
        safe_feature_packet(
            feature_rows=[
                feature_row(
                    contract_ticker="KXMLBGAME-26JUL012240CWSBAL-BAL",
                    expected_expiration_time="2026-07-02T01:40:00Z",
                ),
                feature_row(
                    contract_ticker="KXMLBGAME-26JUL022240BOSNYY-NYY",
                    event_ticker="KXMLBGAME-26JUL022240BOSNYY",
                    selected_code="NYY",
                    home_code="NYY",
                    away_code="BOS",
                    cluster_key="MLB|game_winner|2026-07-02",
                    expected_expiration_time="2026-07-02T05:40:00Z",
                ),
            ],
        ),
    )

    tickers = module.due_observed_tickers(
        feature_packet_path=feature_path,
        observation_dir=tmp_path / "observations",
        generated_utc="2026-07-02T02:00:00Z",
        max_tickers=10,
    )

    assert tickers == ["KXMLBGAME-26JUL012240CWSBAL-BAL"]


def test_observation_due_summary_reports_next_probe_time() -> None:
    module = load_loop_module()

    summary = module.observation_due_summary(
        [
            feature_row(
                contract_ticker="KXMLBGAME-26JUL012240CWSBAL-BAL",
                expected_expiration_time="2026-07-02T01:40:00Z",
            ),
            feature_row(
                contract_ticker="KXMLBGAME-26JUL022240BOSNYY-NYY",
                expected_expiration_time="2026-07-02T05:40:00Z",
            ),
        ],
        generated_utc="2026-07-02T02:00:00Z",
    )

    assert summary["due_observation_row_count"] == 1
    assert summary["due_distinct_contract_count"] == 1
    assert summary["not_due_distinct_contract_count"] == 1
    assert summary["oldest_due_expected_expiration_utc"] == "2026-07-02T01:40:00Z"
    assert summary["next_expected_expiration_utc"] == "2026-07-02T05:40:00Z"
    assert summary["next_public_label_probe_utc"] == "2026-07-02T02:00:00Z"


# --------------------------------------------------------------------------
# Tests: capture helpers (injected fetch_json, no network)
# --------------------------------------------------------------------------


def test_capture_public_observed_markets_snapshot_fetches_exact_tickers(tmp_path: Path) -> None:
    module = load_loop_module()
    calls: list[str] = []

    def fake_fetch(url: str):
        calls.append(url)
        return {
            "market": {
                "ticker": "KXMLBGAME-26JUL012240CWSBAL-BAL",
                "result": "no",
                "settlement_value_dollars": "0.0000",
                "close_time": "2026-07-01T22:40:00Z",
                "settlement_ts": "2026-07-02T01:40:00Z",
            }
        }

    latest_path = module.capture_public_observed_markets_snapshot(
        tickers=["KXMLBGAME-26JUL012240CWSBAL-BAL"],
        raw_dir=tmp_path / "settled",
        generated_utc="2026-07-02T01:45:00Z",
        fetch_json=fake_fetch,
    )
    payload = json.loads(latest_path.read_text(encoding="utf-8"))

    assert payload["status"] == "kalshi_public_observed_market_fetch_ok"
    assert payload["summary"]["observed_ticker_count"] == 1
    assert payload["summary"]["settled_label_ready_count"] == 1
    assert payload["markets"][0]["ticker"] == "KXMLBGAME-26JUL012240CWSBAL-BAL"
    assert calls == [
        "https://external-api.kalshi.com/trade-api/v2/markets/KXMLBGAME-26JUL012240CWSBAL-BAL"
    ]


# --------------------------------------------------------------------------
# Tests: writer (VAL-SFL-024 derived artifacts + outside-repo packets)
# --------------------------------------------------------------------------


def test_sports_proxy_observation_loop_writes_latest_repo_artifacts_and_outside_packets(
    tmp_path: Path,
) -> None:
    module = load_loop_module()
    module.MACRO_DIR = tmp_path / "macro"
    feature_path = tmp_path / "feature.json"
    settled_path = tmp_path / "settled.json"
    observation_dir = tmp_path / "manual" / "observations"
    label_dir = tmp_path / "manual" / "labels"
    write_json(feature_path, safe_feature_packet())
    write_json(settled_path, settled_snapshot())
    report = module.build_sports_proxy_observation_loop(
        feature_packet_path=feature_path,
        settled_snapshot_path=settled_path,
        observation_dir=observation_dir,
        label_dir=label_dir,
        generated_utc="2026-07-02T01:45:00Z",
    )

    paths = module.write_sports_proxy_observation_outputs(
        report,
        out_dir=tmp_path / "out",
        observation_dir=observation_dir,
        label_dir=label_dir,
    )

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    assert Path(paths["schedule_template_path"]).exists()
    assert Path(paths["latest_json_path"]).exists()
    assert Path(paths["observation_packet_latest_path"]).exists()
    assert Path(paths["label_packet_latest_path"]).exists()
    latest = json.loads(Path(paths["latest_json_path"]).read_text(encoding="utf-8"))
    assert latest["summary"]["label_row_count"] == 1
    assert "Kalshi Sports Proxy Observation Loop" in Path(paths["markdown_path"]).read_text(
        encoding="utf-8"
    )
    assert "OnUnitActiveSec=10min" in Path(paths["schedule_template_path"]).read_text(
        encoding="utf-8"
    )


# --------------------------------------------------------------------------
# Tests: VAL-SFL-040 (Make targets) + VAL-SFL-035 (importlib load)
# --------------------------------------------------------------------------


def test_sports_proxy_observation_makefile_targets_are_registered() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-proxy-observation-loop" in text
    assert "kalshi-sports-proxy-observation-watch-once" in text
    assert "KALSHI_SPORTS_PROXY_OBSERVATION_CAPTURE_SETTLED" in text
    assert "KALSHI_SPORTS_PROXY_OBSERVATION_PROBE_OBSERVED" in text


def test_loop_module_is_loaded_via_importlib() -> None:
    """VAL-SFL-035: the script is loadable via importlib (no predmarket import of scripts)."""
    module = load_loop_module()
    assert hasattr(module, "build_sports_proxy_observation_loop")
    assert hasattr(module, "write_sports_proxy_observation_outputs")
    assert hasattr(module, "main")
    # Sports-specific cosmetic constants.
    assert (
        module.DEFAULT_FEATURE_PACKET_PATH.name == "latest-kalshi-sports-proxy-feature-packet.json"
    )
    assert "kalshi_sports_proxy_observations" in str(module.DEFAULT_OBSERVATION_DIR)
    assert "kalshi_sports_proxy_labels" in str(module.DEFAULT_LABEL_DIR)
