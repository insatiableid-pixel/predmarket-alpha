from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "kalshi_sports_proxy_capacity_correlation_decay.py"
)


def load_ccd_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_sports_proxy_capacity_correlation_decay", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kalshi_sports_proxy_capacity_correlation_decay"] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def feature_packet(*rows: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "sports_proxy_feature_packet_ready",
        "research_only": True,
        "execution_enabled": False,
        "feature_rows": list(rows),
        "summary": {"feature_row_count": len(rows), "feature_ready_count": len(rows)},
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }


def feature_row(
    ticker: str,
    *,
    league: str = "MLB",
    series_ticker: str = "KXMLBGAME",
    close_time: str = "2026-07-02T01:00:00Z",
    predicted_side: str = "yes",
) -> dict[str, object]:
    return {
        "contract_ticker": ticker,
        "event_ticker": ticker.rsplit("-", 1)[0],
        "league": league,
        "series_ticker": series_ticker,
        "close_time": close_time,
        "predicted_side": predicted_side,
    }


def replay_payload(
    *,
    probability: float = 0.8,
    decay_status: str = "recent_bucket_not_worse_than_random",
    decay_bucket_count: int = 3,
    label_count: int = 120,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "sports_proxy_research_candidate_replay_blocked_predeployment_gates",
        "research_only": True,
        "execution_enabled": False,
        "summary": {
            "conservative_calibrated_side_probability": probability,
            "decay_status": decay_status,
            "decay_bucket_count": decay_bucket_count,
            "independent_contract_label_count": label_count,
        },
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }


def test_sports_prediction_yes_returns_1() -> None:
    module = load_ccd_module()
    assert module.sports_strength_win_prob_prediction({"predicted_side": "yes"}) == 1
    assert module.sports_strength_win_prob_prediction({"predicted_side": "no"}) == 0
    assert module.sports_strength_win_prob_prediction({"predicted_side": None}) is None
    assert module.sports_strength_win_prob_prediction({}) is None


def test_sports_cluster_key_league_game_winner_date() -> None:
    module = load_ccd_module()
    key = module.correlation_cluster_key(
        {
            "contract_ticker": "KXMLBGAME-26JUL02-CWSBAL-CWS",
            "league": "MLB",
            "close_time": "2026-07-02T01:00:00Z",
        }
    )
    assert "MLB" in key
    assert "KXMLBGAME-26JUL02-CWSBAL-CWS" in key
    assert "2026-07-02" in key
    assert key.count("|") >= 2


def test_different_games_have_different_cluster_keys() -> None:
    module = load_ccd_module()
    key1 = module.correlation_cluster_key(
        {
            "contract_ticker": "KXMLBGAME-26JUL02-CWSBAL-CWS",
            "league": "MLB",
            "close_time": "2026-07-02T01:00:00Z",
        }
    )
    key2 = module.correlation_cluster_key(
        {
            "contract_ticker": "KXMLBGAME-26JUL02-NYYBOS-NYY",
            "league": "MLB",
            "close_time": "2026-07-02T03:00:00Z",
        }
    )
    assert key1 != key2


def test_select_current_candidates_round_robins_sports_clusters() -> None:
    module = load_ccd_module()
    rows = [
        feature_row(f"KXMLBGAME-26JUL02-CWSBAL-CWS{i}", league="MLB", predicted_side="yes")
        for i in range(5)
    ] + [
        feature_row("KXKBOGAME-26JUL02-KTWHAN-KT", league="KBO", predicted_side="yes"),
        feature_row("KXLMBGAME-26JUL02-MONLAR-MON", league="LMB", predicted_side="no"),
    ]
    selected = module.select_current_candidates(
        feature_packet=feature_packet(*rows),
        generated_ts=module.timestamp("2026-07-02T00:00:00Z"),
        max_close_hours=6,
        max_tickers=3,
    )

    # Round-robin should select 1 from each of 3 distinct clusters
    assert len(selected) == 3
    assert len({module.correlation_cluster_key(row) for row in selected}) == 3


def test_build_ccd_uses_diversified_candidates_under_ticker_cap(tmp_path: Path) -> None:
    module = load_ccd_module()
    feature_path = tmp_path / "feature.json"
    replay_path = tmp_path / "replay.json"
    # 5 MLB contracts for the same game (same event_ticker), plus 1 KBO, 1 LMB game
    rows = [
        feature_row(f"KXMLBGAME-26JUL02-CWSBAL-CWS{i}", league="MLB", predicted_side="yes")
        for i in range(5)
    ] + [
        feature_row("KXKBOGAME-26JUL02-KTWHAN-KT", league="KBO", predicted_side="yes"),
        feature_row("KXLMBGAME-26JUL02-MONLAR-MON", league="LMB", predicted_side="no"),
    ]
    write_json(feature_path, feature_packet(*rows))
    write_json(replay_path, replay_payload(probability=0.8))

    # Use max_cluster_share=0.5 to cover 2 positive-depth clusters (MLB + KBO),
    # which works because with 2 positive clusters, the largest share is 0.5
    report = module.build_sports_proxy_capacity_correlation_decay(
        feature_packet_path=feature_path,
        replay_path=replay_path,
        raw_orderbook_dir=tmp_path / "raw-orderbooks",
        generated_utc="2026-07-02T00:00:00Z",
        capture_orderbooks=True,
        fetch_json=lambda _url: {"orderbook": {"no": [[40, 5]]}},
        delay_seconds=0,
        max_tickers=3,
        max_cluster_share=0.5,
    )

    assert report["status"] == "sports_proxy_capacity_correlation_decay_ready_for_paper_overlay"
    assert report["summary"]["candidate_row_count"] == 3
    assert report["summary"]["candidate_cluster_count"] == 3
    assert report["summary"]["largest_correlation_cluster_share"] is not None
    assert report["summary"]["largest_correlation_cluster_share"] <= 0.5


def test_build_ccd_ready_when_depth_cluster_and_decay_pass(tmp_path: Path) -> None:
    module = load_ccd_module()
    feature_path = tmp_path / "feature.json"
    replay_path = tmp_path / "replay.json"
    write_json(
        feature_path,
        feature_packet(
            feature_row("KXMLBGAME-26JUL02-CWSBAL-CWS", league="MLB", predicted_side="yes"),
            feature_row("KXKBOGAME-26JUL02-KTWHAN-KT", league="KBO", predicted_side="no"),
        ),
    )
    write_json(replay_path, replay_payload(probability=0.8))

    def fake_fetch(url: str) -> dict[str, object]:
        if "CWSBAL" in url:
            return {"orderbook": {"no": [[40, 5]]}}
        return {"orderbook": {"yes": [[30, 4]]}}

    report = module.build_sports_proxy_capacity_correlation_decay(
        feature_packet_path=feature_path,
        replay_path=replay_path,
        raw_orderbook_dir=tmp_path / "raw-orderbooks",
        generated_utc="2026-07-02T00:00:00Z",
        capture_orderbooks=True,
        fetch_json=fake_fetch,
        delay_seconds=0,
        max_cluster_share=1.0,
    )

    assert report["status"] == "sports_proxy_capacity_correlation_decay_ready_for_paper_overlay"
    assert report["summary"]["candidate_row_count"] == 2
    assert report["summary"]["orderbook_count"] == 2
    assert report["summary"]["capacity_status"] == "capacity_depth_positive"
    assert report["summary"]["correlation_status"] == "correlation_cluster_within_limit"
    assert report["summary"]["decay_status"] == "decay_survival_pass"
    assert report["summary"]["usable_row_count"] == 0
    assert report["market_execution"] is False
    assert report["account_or_order_paths"] is False


def test_build_ccd_blocks_concentrated_positive_depth(tmp_path: Path) -> None:
    module = load_ccd_module()
    feature_path = tmp_path / "feature.json"
    replay_path = tmp_path / "replay.json"
    # Two contracts from the SAME game (same event_ticker KXMLBGAME-26JUL02-CWSBAL)
    write_json(
        feature_path,
        feature_packet(
            feature_row("KXMLBGAME-26JUL02-CWSBAL-CWS", league="MLB", predicted_side="yes"),
            feature_row("KXMLBGAME-26JUL02-CWSBAL-BAL", league="MLB", predicted_side="no"),
        ),
    )
    write_json(replay_path, replay_payload(probability=0.8))

    report = module.build_sports_proxy_capacity_correlation_decay(
        feature_packet_path=feature_path,
        replay_path=replay_path,
        raw_orderbook_dir=tmp_path / "raw-orderbooks",
        generated_utc="2026-07-02T00:00:00Z",
        capture_orderbooks=True,
        fetch_json=lambda _url: {"orderbook": {"no": [[40, 5]], "yes": [[60, 5]]}},
        delay_seconds=0,
        max_cluster_share=0.35,
    )

    assert (
        report["status"]
        == "sports_proxy_capacity_correlation_decay_blocked_correlation_concentration"
    )
    assert report["summary"]["capacity_status"] == "capacity_depth_positive"
    assert report["summary"]["largest_correlation_cluster_share"] == 1.0
    assert report["next_action"]["name"] == "kalshi_sports_proxy_correlation_cluster_control"


def test_build_ccd_blocks_decay_when_replay_decay_not_surviving(tmp_path: Path) -> None:
    module = load_ccd_module()
    feature_path = tmp_path / "feature.json"
    replay_path = tmp_path / "replay.json"
    write_json(
        feature_path, feature_packet(feature_row("KXMLBGAME-26JUL02-CWSBAL-CWS", league="MLB"))
    )
    write_json(
        replay_path, replay_payload(probability=0.8, decay_status="recent_bucket_below_random")
    )

    report = module.build_sports_proxy_capacity_correlation_decay(
        feature_packet_path=feature_path,
        replay_path=replay_path,
        raw_orderbook_dir=tmp_path / "raw-orderbooks",
        generated_utc="2026-07-02T00:00:00Z",
        capture_orderbooks=True,
        fetch_json=lambda _url: {"orderbook": {"no": [[40, 5]]}},
        delay_seconds=0,
        max_cluster_share=1.0,
    )

    assert report["status"] == "sports_proxy_capacity_correlation_decay_blocked_decay_survival"
    assert report["summary"]["decay_status"] == "decay_survival_blocked"


def test_build_ccd_blocks_no_current_candidates(tmp_path: Path) -> None:
    module = load_ccd_module()
    feature_path = tmp_path / "feature.json"
    replay_path = tmp_path / "replay.json"
    # Feature row in the past (expired)
    write_json(
        feature_path,
        feature_packet(
            feature_row(
                "KXMLBGAME-26JUL02-CWSBAL-CWS", league="MLB", close_time="2026-07-01T01:00:00Z"
            )
        ),
    )
    write_json(replay_path, replay_payload(probability=0.8))

    report = module.build_sports_proxy_capacity_correlation_decay(
        feature_packet_path=feature_path,
        replay_path=replay_path,
        raw_orderbook_dir=tmp_path / "raw-orderbooks",
        generated_utc="2026-07-02T00:00:00Z",
        capture_orderbooks=True,
        fetch_json=lambda _url: {"orderbook": {"no": [[40, 5]]}},
        delay_seconds=0,
        max_cluster_share=1.0,
    )

    # Should be blocked - candidates have expired close time
    assert "blocked" in report["status"]


def test_build_ccd_blocks_no_depth(tmp_path: Path) -> None:
    module = load_ccd_module()
    feature_path = tmp_path / "feature.json"
    replay_path = tmp_path / "replay.json"
    write_json(
        feature_path,
        feature_packet(
            feature_row("KXMLBGAME-26JUL02-CWSBAL-CWS", league="MLB", predicted_side="yes"),
        ),
    )
    write_json(replay_path, replay_payload(probability=0.8))

    # Orderbook with no_bid=0.10 => yes_ask=0.90, break-even ~0.90+fee > 0.80 calibrated probability
    # So no level clears the conservative probability hurdle
    report = module.build_sports_proxy_capacity_correlation_decay(
        feature_packet_path=feature_path,
        replay_path=replay_path,
        raw_orderbook_dir=tmp_path / "raw-orderbooks",
        generated_utc="2026-07-02T00:00:00Z",
        capture_orderbooks=True,
        fetch_json=lambda _url: {"orderbook": {"no": [[10, 5]]}},  # no_bid=0.10 => yes_ask=0.90
        delay_seconds=0,
        max_cluster_share=1.0,
    )

    assert report["summary"]["capacity_status"] == "capacity_depth_missing_or_not_positive"
    assert report["summary"]["positive_depth_contracts"] == 0


def test_ask_levels_derive_yes_and_no_asks_from_opposing_bids() -> None:
    module = load_ccd_module()

    yes_levels = module.ask_levels({"orderbook": {"no": [[40, 5]]}}, "yes")
    no_levels = module.ask_levels({"orderbook": {"yes": [[25, 3]]}}, "no")

    assert yes_levels == [{"ask_price": 0.6, "contracts": 5.0}]
    assert no_levels == [{"ask_price": 0.75, "contracts": 3.0}]


def test_ccd_writer_skips_latest_for_tmp_out_dir_by_default(tmp_path: Path) -> None:
    module = load_ccd_module()
    report = {
        "schema_version": 1,
        "status": "sports_proxy_capacity_correlation_decay_blocked_no_current_candidates",
        "research_only": True,
        "execution_enabled": False,
        "summary": {"candidate_row_count": 0},
        "gates": [],
        "capacity_rows": [],
    }

    paths = module.write_sports_proxy_capacity_correlation_decay(report, out_dir=tmp_path / "out")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    assert "latest_json_path" not in paths


def test_summary_records_positive_depth_fraction_and_prior(tmp_path: Path) -> None:
    """VAL-SGATE-058: capacity model records observed positive-depth fraction alongside ~0.18 prior."""
    module = load_ccd_module()
    feature_path = tmp_path / "feature.json"
    replay_path = tmp_path / "replay.json"
    write_json(
        feature_path,
        feature_packet(
            feature_row("KXMLBGAME-26JUL02-CWSBAL-CWS", league="MLB", predicted_side="yes"),
            feature_row("KXKBOGAME-26JUL02-KTWHAN-KT", league="KBO", predicted_side="no"),
        ),
    )
    write_json(replay_path, replay_payload(probability=0.8))

    def fake_fetch(url: str) -> dict[str, object]:
        # One orderbook has depth, one doesn't
        if "CWSBAL" in url:
            return {"orderbook": {"no": [[40, 5]]}}
        return {"orderbook": {"yes": [[90, 3]]}}  # ask=0.10, below calibrated so no positive depth

    report = module.build_sports_proxy_capacity_correlation_decay(
        feature_packet_path=feature_path,
        replay_path=replay_path,
        raw_orderbook_dir=tmp_path / "raw-orderbooks",
        generated_utc="2026-07-02T00:00:00Z",
        capture_orderbooks=True,
        fetch_json=fake_fetch,
        delay_seconds=0,
        max_cluster_share=1.0,
    )

    assert report["summary"]["positive_depth_prior_axiom3"] == 0.18
    assert report["summary"]["observed_positive_depth_fraction"] is not None
    assert report["summary"]["observed_positive_depth_fraction"] > 0


def test_sports_cluster_key_not_crypto_style(tmp_path: Path) -> None:
    """VAL-SGATE-021: Sports cluster key is NOT the crypto asset|family|bucket key."""
    module = load_ccd_module()
    key = module.correlation_cluster_key(
        {
            "contract_ticker": "KXMLBGAME-26JUL02-CWSBAL-CWS",
            "league": "MLB",
            "close_time": "2026-07-02T01:00:00Z",
        }
    )
    # Should NOT contain asset_symbol or contract_family patterns
    assert "BTC" not in key
    assert "range" not in key
    assert "|unknown|" not in key or "MLB" in key


def test_all_capacity_rows_usable_false(tmp_path: Path) -> None:
    module = load_ccd_module()
    feature_path = tmp_path / "feature.json"
    replay_path = tmp_path / "replay.json"
    write_json(
        feature_path,
        feature_packet(
            feature_row("KXMLBGAME-26JUL02-CWSBAL-CWS", league="MLB", predicted_side="yes"),
        ),
    )
    write_json(replay_path, replay_payload(probability=0.8))

    report = module.build_sports_proxy_capacity_correlation_decay(
        feature_packet_path=feature_path,
        replay_path=replay_path,
        raw_orderbook_dir=tmp_path / "raw-orderbooks",
        generated_utc="2026-07-02T00:00:00Z",
        capture_orderbooks=True,
        fetch_json=lambda _url: {"orderbook": {"no": [[40, 5]]}},
        delay_seconds=0,
        max_cluster_share=1.0,
    )

    for row in report["capacity_rows"]:
        assert row["usable"] is False
    assert report["summary"]["usable_row_count"] == 0
