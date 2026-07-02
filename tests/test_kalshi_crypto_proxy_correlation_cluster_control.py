from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kalshi_crypto_proxy_correlation_cluster_control.py"


def load_cluster_control_module():
    spec = importlib.util.spec_from_file_location("kalshi_crypto_proxy_correlation_cluster_control", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kalshi_crypto_proxy_correlation_cluster_control"] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def capacity_row(
    ticker: str,
    *,
    cluster: str,
    asset: str,
    cost: float,
    contracts: float = 10.0,
    margin: float = 0.08,
) -> dict[str, object]:
    return {
        "contract_ticker": ticker,
        "event_ticker": ticker.rsplit("-", 1)[0],
        "asset_symbol": asset,
        "contract_family": "range",
        "close_time": "2026-07-02T05:00:00Z",
        "predicted_side": "yes",
        "correlation_cluster_key": cluster,
        "best_margin_probability": margin,
        "positive_depth_contracts": contracts,
        "positive_depth_cost": cost,
        "usable": False,
    }


def ccd_payload(
    *rows: dict[str, object],
    status: str = "crypto_proxy_capacity_correlation_decay_blocked_correlation_concentration",
    capacity_status: str = "capacity_depth_positive",
    decay_status: str = "decay_survival_pass",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "summary": {
            "capacity_status": capacity_status,
            "decay_status": decay_status,
        },
        "capacity_rows": list(rows),
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }


def test_cluster_control_blocks_single_cluster_under_max_share(tmp_path: Path) -> None:
    module = load_cluster_control_module()
    ccd_path = tmp_path / "ccd.json"
    write_json(
        ccd_path,
        ccd_payload(
            capacity_row("KXBNB-26JUL0205-B400", cluster="BNB|range|2026-07-02T05:00Z", asset="BNB", cost=90),
            capacity_row(
                "KXBNB-26JUL0205-B410",
                cluster="BNB|range|2026-07-02T05:00Z",
                asset="BNB",
                cost=60,
                margin=0.07,
            ),
        ),
    )

    report = module.build_crypto_proxy_correlation_cluster_control(
        ccd_path=ccd_path,
        generated_utc="2026-07-02T00:00:00Z",
        max_cluster_share=0.35,
    )

    assert report["status"] == "crypto_proxy_correlation_cluster_control_blocked_insufficient_clusters"
    assert report["summary"]["positive_cluster_count"] == 1
    assert report["summary"]["required_positive_cluster_count"] == 3
    assert report["summary"]["largest_positive_cluster_share"] == 1.0
    assert report["summary"]["total_controlled_depth_cost"] == 0
    assert report["summary"]["usable_row_count"] == 0
    assert report["next_action"]["name"] == "kalshi_crypto_proxy_cluster_breadth_accumulation"
    assert report["market_execution"] is False
    assert report["staking_or_sizing_guidance"] is False
    assert all(row["usable"] is False for row in report["controlled_rows"])


def test_cluster_control_ready_with_three_balanced_clusters(tmp_path: Path) -> None:
    module = load_cluster_control_module()
    ccd_path = tmp_path / "ccd.json"
    write_json(
        ccd_path,
        ccd_payload(
            capacity_row("KXBTC-26JUL0205-B100", cluster="BTC|range|2026-07-02T05:00Z", asset="BTC", cost=100),
            capacity_row("KXETH-26JUL0205-B100", cluster="ETH|range|2026-07-02T05:00Z", asset="ETH", cost=100),
            capacity_row("KXSOL-26JUL0205-B100", cluster="SOL|range|2026-07-02T05:00Z", asset="SOL", cost=100),
        ),
    )

    report = module.build_crypto_proxy_correlation_cluster_control(
        ccd_path=ccd_path,
        generated_utc="2026-07-02T00:00:00Z",
        max_cluster_share=0.35,
    )

    assert report["status"] == "crypto_proxy_correlation_cluster_control_ready_for_paper_overlay"
    assert report["summary"]["positive_cluster_count"] == 3
    assert report["summary"]["largest_controlled_cluster_share"] <= 0.35
    assert report["summary"]["controlled_positive_row_count"] == 3
    assert report["summary"]["usable_row_count"] == 0
    assert {row["gate_status"] for row in report["controlled_rows"]} == {"pass"}
    assert all(row["usable"] is False for row in report["controlled_rows"])


def test_cluster_control_blocks_upstream_invalid_ccd(tmp_path: Path) -> None:
    module = load_cluster_control_module()
    ccd_path = tmp_path / "ccd.json"
    write_json(
        ccd_path,
        ccd_payload(
            capacity_row("KXBTC-26JUL0205-B100", cluster="BTC|range|2026-07-02T05:00Z", asset="BTC", cost=100),
            capacity_status="capacity_depth_blocked",
        ),
    )

    report = module.build_crypto_proxy_correlation_cluster_control(
        ccd_path=ccd_path,
        generated_utc="2026-07-02T00:00:00Z",
        max_cluster_share=0.35,
    )

    assert report["status"] == "crypto_proxy_correlation_cluster_control_blocked_upstream_ccd"
    assert report["next_action"]["name"] == "kalshi_crypto_proxy_correlation_cluster_control_audit"


def test_cluster_control_writer_skips_latest_for_tmp_out_dir_by_default(tmp_path: Path) -> None:
    module = load_cluster_control_module()
    report = {
        "schema_version": 1,
        "status": "crypto_proxy_correlation_cluster_control_blocked_no_positive_depth",
        "research_only": True,
        "execution_enabled": False,
        "summary": {"positive_cluster_count": 0},
        "gates": [],
        "controlled_rows": [],
    }

    paths = module.write_crypto_proxy_correlation_cluster_control(report, out_dir=tmp_path / "out")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    assert "latest_json_path" not in paths
