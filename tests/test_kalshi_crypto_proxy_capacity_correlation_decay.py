from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "kalshi_crypto_proxy_capacity_correlation_decay.py"
)


def load_ccd_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_crypto_proxy_capacity_correlation_decay", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kalshi_crypto_proxy_capacity_correlation_decay"] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def feature_packet(*rows: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "crypto_proxy_feature_packet_ready",
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
    asset: str = "BTC",
    contract_family: str = "range",
    close_time: str = "2026-07-02T01:00:00Z",
    proxy_state: str = "proxy_above_range_not_label",
) -> dict[str, object]:
    return {
        "contract_ticker": ticker,
        "event_ticker": ticker.rsplit("-", 1)[0],
        "asset_symbol": asset,
        "contract_family": contract_family,
        "close_time": close_time,
        "proxy_state": proxy_state,
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
        "status": "crypto_proxy_research_candidate_replay_blocked_predeployment_gates",
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


def test_ask_levels_derive_yes_and_no_asks_from_opposing_bids() -> None:
    module = load_ccd_module()

    yes_levels = module.ask_levels({"orderbook": {"no": [[40, 5]]}}, "yes")
    no_levels = module.ask_levels({"orderbook": {"yes": [[25, 3]]}}, "no")

    assert yes_levels == [{"ask_price": 0.6, "contracts": 5.0}]
    assert no_levels == [{"ask_price": 0.75, "contracts": 3.0}]


def test_select_current_candidates_round_robins_clusters_before_truncating() -> None:
    module = load_ccd_module()
    rows = [
        feature_row(f"KXBNB-26JUL0201-B{strike}", asset="BNB")
        for strike in (100, 105, 110, 115, 120)
    ] + [
        feature_row("KXETH-26JUL0201-B100", asset="ETH"),
        feature_row("KXSOL-26JUL0201-B100", asset="SOL", contract_family="above"),
    ]
    selected = module.select_current_candidates(
        feature_packet=feature_packet(*rows),
        generated_ts=module.timestamp("2026-07-02T00:00:00Z"),
        max_close_hours=6,
        max_tickers=3,
    )

    assert [row["asset_symbol"] for row in selected] == ["BNB", "ETH", "SOL"]
    assert {module.correlation_cluster_key(row) for row in selected} == {
        "BNB|range|2026-07-02T01:00Z",
        "ETH|range|2026-07-02T01:00Z",
        "SOL|above|2026-07-02T01:00Z",
    }


def test_build_ccd_uses_diversified_candidates_under_ticker_cap(tmp_path: Path) -> None:
    module = load_ccd_module()
    feature_path = tmp_path / "feature.json"
    replay_path = tmp_path / "replay.json"
    rows = [
        feature_row(f"KXBNB-26JUL0201-B{strike}", asset="BNB")
        for strike in (100, 105, 110, 115, 120)
    ] + [
        feature_row("KXETH-26JUL0201-B100", asset="ETH"),
        feature_row("KXSOL-26JUL0201-B100", asset="SOL", contract_family="above"),
    ]
    write_json(feature_path, feature_packet(*rows))
    write_json(replay_path, replay_payload(probability=0.8))

    report = module.build_crypto_proxy_capacity_correlation_decay(
        feature_packet_path=feature_path,
        replay_path=replay_path,
        raw_orderbook_dir=tmp_path / "raw-orderbooks",
        generated_utc="2026-07-02T00:00:00Z",
        capture_orderbooks=True,
        fetch_json=lambda _url: {"orderbook": {"no": [[40, 5]]}},
        delay_seconds=0,
        max_tickers=3,
        max_cluster_share=0.35,
    )

    assert report["status"] == "crypto_proxy_capacity_correlation_decay_ready_for_paper_overlay"
    assert report["summary"]["candidate_row_count"] == 3
    assert report["summary"]["candidate_cluster_count"] == 3
    assert report["summary"]["largest_correlation_cluster_share"] <= 0.35
    assert report["summary"]["asset_counts"] == {"BNB": 1, "ETH": 1, "SOL": 1}


def test_build_ccd_ready_when_depth_cluster_and_decay_pass(tmp_path: Path) -> None:
    module = load_ccd_module()
    feature_path = tmp_path / "feature.json"
    replay_path = tmp_path / "replay.json"
    write_json(
        feature_path,
        feature_packet(
            feature_row("KXBTC-26JUL0201-B100", asset="BTC"),
            feature_row(
                "KXETH-26JUL0201-B200", asset="ETH", proxy_state="proxy_below_range_not_label"
            ),
        ),
    )
    write_json(replay_path, replay_payload(probability=0.8))

    def fake_fetch(url: str) -> dict[str, object]:
        if "KXBTC" in url:
            return {"orderbook": {"no": [[40, 5]]}}
        return {"orderbook": {"yes": [[30, 4]]}}

    report = module.build_crypto_proxy_capacity_correlation_decay(
        feature_packet_path=feature_path,
        replay_path=replay_path,
        raw_orderbook_dir=tmp_path / "raw-orderbooks",
        generated_utc="2026-07-02T00:00:00Z",
        capture_orderbooks=True,
        fetch_json=fake_fetch,
        delay_seconds=0,
        max_cluster_share=1.0,
    )

    assert report["status"] == "crypto_proxy_capacity_correlation_decay_ready_for_paper_overlay"
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
    write_json(
        feature_path,
        feature_packet(
            feature_row("KXBTC-26JUL0201-B100", asset="BTC"),
            feature_row("KXBTC-26JUL0201-B110", asset="BTC"),
        ),
    )
    write_json(replay_path, replay_payload(probability=0.8))

    report = module.build_crypto_proxy_capacity_correlation_decay(
        feature_packet_path=feature_path,
        replay_path=replay_path,
        raw_orderbook_dir=tmp_path / "raw-orderbooks",
        generated_utc="2026-07-02T00:00:00Z",
        capture_orderbooks=True,
        fetch_json=lambda _url: {"orderbook": {"no": [[40, 5]]}},
        delay_seconds=0,
        max_cluster_share=0.35,
    )

    assert (
        report["status"]
        == "crypto_proxy_capacity_correlation_decay_blocked_correlation_concentration"
    )
    assert report["summary"]["capacity_status"] == "capacity_depth_positive"
    assert report["summary"]["largest_correlation_cluster_share"] == 1.0
    assert report["next_action"]["name"] == "kalshi_crypto_proxy_correlation_cluster_control"


def test_build_ccd_blocks_decay_when_replay_decay_is_not_surviving(tmp_path: Path) -> None:
    module = load_ccd_module()
    feature_path = tmp_path / "feature.json"
    replay_path = tmp_path / "replay.json"
    write_json(feature_path, feature_packet(feature_row("KXBTC-26JUL0201-B100")))
    write_json(
        replay_path, replay_payload(probability=0.8, decay_status="recent_bucket_worse_than_random")
    )

    report = module.build_crypto_proxy_capacity_correlation_decay(
        feature_packet_path=feature_path,
        replay_path=replay_path,
        raw_orderbook_dir=tmp_path / "raw-orderbooks",
        generated_utc="2026-07-02T00:00:00Z",
        capture_orderbooks=True,
        fetch_json=lambda _url: {"orderbook": {"no": [[40, 5]]}},
        delay_seconds=0,
        max_cluster_share=1.0,
    )

    assert report["status"] == "crypto_proxy_capacity_correlation_decay_blocked_decay_survival"
    assert report["summary"]["decay_status"] == "decay_survival_blocked"
    assert report["next_action"]["name"] == "kalshi_crypto_proxy_decay_and_sample_accumulation"


def test_ccd_writer_skips_latest_for_tmp_out_dir_by_default(tmp_path: Path) -> None:
    module = load_ccd_module()
    report = {
        "schema_version": 1,
        "status": "crypto_proxy_capacity_correlation_decay_blocked_no_current_candidates",
        "research_only": True,
        "execution_enabled": False,
        "summary": {"candidate_row_count": 0},
        "gates": [],
        "capacity_rows": [],
    }

    paths = module.write_crypto_proxy_capacity_correlation_decay(report, out_dir=tmp_path / "out")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    assert "latest_json_path" not in paths
