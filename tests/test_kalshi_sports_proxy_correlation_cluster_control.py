from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "kalshi_sports_proxy_correlation_cluster_control.py"
)


def load_cluster_control_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_sports_proxy_correlation_cluster_control", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kalshi_sports_proxy_correlation_cluster_control"] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def capacity_row(
    ticker: str,
    *,
    cluster: str,
    league: str = "MLB",
    cost: float = 100.0,
    contracts: float = 10.0,
    margin: float = 0.08,
) -> dict[str, object]:
    return {
        "contract_ticker": ticker,
        "event_ticker": ticker.rsplit("-", 1)[0],
        "league": league,
        "series_ticker": "KXMLBGAME",
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
    status: str = "sports_proxy_capacity_correlation_decay_blocked_correlation_concentration",
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
    """VAL-SGATE-028: Single sports cluster positive depth is blocked (controlled cost zero)."""
    module = load_cluster_control_module()
    ccd_path = tmp_path / "ccd.json"
    write_json(
        ccd_path,
        ccd_payload(
            capacity_row(
                "KXMLBGAME-26JUL02-CWSBAL-CWS",
                cluster="MLB|KXMLBGAME-26JUL02-CWSBAL-CWS|2026-07-02T05:00Z",
                league="MLB",
                cost=90,
            ),
            capacity_row(
                "KXMLBGAME-26JUL02-CWSBAL-CWS2",
                cluster="MLB|KXMLBGAME-26JUL02-CWSBAL-CWS|2026-07-02T05:00Z",
                league="MLB",
                cost=60,
                margin=0.07,
            ),
        ),
    )

    report = module.build_sports_proxy_correlation_cluster_control(
        ccd_path=ccd_path,
        generated_utc="2026-07-02T00:00:00Z",
        max_cluster_share=0.35,
    )

    assert (
        report["status"] == "sports_proxy_correlation_cluster_control_blocked_insufficient_clusters"
    )
    assert report["summary"]["positive_cluster_count"] == 1
    assert report["summary"]["required_positive_cluster_count"] == 3
    assert report["summary"]["largest_positive_cluster_share"] == 1.0
    assert report["summary"]["total_controlled_depth_cost"] == 0
    assert report["summary"]["usable_row_count"] == 0
    assert report["next_action"]["name"] == "kalshi_sports_proxy_cluster_breadth_accumulation"
    assert report["market_execution"] is False
    assert report["staking_or_sizing_guidance"] is False
    assert all(row["usable"] is False for row in report["controlled_rows"])


def test_cluster_control_ready_with_three_balanced_clusters(tmp_path: Path) -> None:
    """VAL-SGATE-026: Cluster control caps controlled exposure at 35% via binary search on sports rows."""
    module = load_cluster_control_module()
    ccd_path = tmp_path / "ccd.json"
    write_json(
        ccd_path,
        ccd_payload(
            capacity_row(
                "KXMLBGAME-26JUL02-CWSBAL-CWS",
                cluster="MLB|KXMLBGAME-26JUL02-CWSBAL-CWS|2026-07-02T05:00Z",
                league="MLB",
                cost=100,
            ),
            capacity_row(
                "KXKBOGAME-26JUL02-KTWHAN-KT",
                cluster="KBO|KXKBOGAME-26JUL02-KTWHAN-KT|2026-07-02T05:00Z",
                league="KBO",
                cost=100,
            ),
            capacity_row(
                "KXLMBGAME-26JUL02-MONLAR-MON",
                cluster="LMB|KXLMBGAME-26JUL02-MONLAR-MON|2026-07-02T05:00Z",
                league="LMB",
                cost=100,
            ),
        ),
    )

    report = module.build_sports_proxy_correlation_cluster_control(
        ccd_path=ccd_path,
        generated_utc="2026-07-02T00:00:00Z",
        max_cluster_share=0.35,
    )

    assert report["status"] == "sports_proxy_correlation_cluster_control_ready_for_paper_overlay"
    assert report["summary"]["positive_cluster_count"] == 3
    assert report["summary"]["largest_controlled_cluster_share"] <= 0.35
    assert report["summary"]["controlled_positive_row_count"] == 3
    assert report["summary"]["usable_row_count"] == 0
    assert {row["gate_status"] for row in report["controlled_rows"]} == {"pass"}
    assert all(row["usable"] is False for row in report["controlled_rows"])


def test_cluster_control_blocks_upstream_invalid_ccd(tmp_path: Path) -> None:
    """Cluster control blocks when upstream CCD has no positive capacity."""
    module = load_cluster_control_module()
    ccd_path = tmp_path / "ccd.json"
    write_json(
        ccd_path,
        ccd_payload(
            capacity_row(
                "KXMLBGAME-26JUL02-CWSBAL-CWS",
                cluster="MLB|KXMLBGAME-26JUL02-CWSBAL-CWS|2026-07-02T05:00Z",
                league="MLB",
                cost=100,
            ),
            capacity_status="capacity_depth_blocked",
        ),
    )

    report = module.build_sports_proxy_correlation_cluster_control(
        ccd_path=ccd_path,
        generated_utc="2026-07-02T00:00:00Z",
        max_cluster_share=0.35,
    )

    assert report["status"] == "sports_proxy_correlation_cluster_control_blocked_upstream_ccd"
    assert report["next_action"]["name"] == "kalshi_sports_proxy_correlation_cluster_control_audit"


def test_cluster_control_two_clusters_not_enough(tmp_path: Path) -> None:
    """VAL-SGATE-027: required_cluster_count = ceil(1/0.35) = 3 minimum."""
    module = load_cluster_control_module()
    ccd_path = tmp_path / "ccd.json"
    write_json(
        ccd_path,
        ccd_payload(
            capacity_row(
                "KXMLBGAME-26JUL02-CWSBAL-CWS",
                cluster="MLB|GAME1|2026-07-02T05:00Z",
                league="MLB",
                cost=100,
            ),
            capacity_row(
                "KXKBOGAME-26JUL02-KTWHAN-KT",
                cluster="KBO|GAME2|2026-07-02T05:00Z",
                league="KBO",
                cost=100,
            ),
        ),
    )

    report = module.build_sports_proxy_correlation_cluster_control(
        ccd_path=ccd_path,
        generated_utc="2026-07-02T00:00:00Z",
        max_cluster_share=0.35,
    )

    assert report["summary"]["positive_cluster_count"] == 2
    assert report["summary"]["required_positive_cluster_count"] == 3
    assert (
        report["status"] == "sports_proxy_correlation_cluster_control_blocked_insufficient_clusters"
    )


def test_cluster_control_writer_skips_latest_for_tmp_out_dir_by_default(tmp_path: Path) -> None:
    module = load_cluster_control_module()
    report = {
        "schema_version": 1,
        "status": "sports_proxy_correlation_cluster_control_blocked_no_positive_depth",
        "research_only": True,
        "execution_enabled": False,
        "summary": {"positive_cluster_count": 0},
        "gates": [],
        "controlled_rows": [],
    }

    paths = module.write_sports_proxy_correlation_cluster_control(report, out_dir=tmp_path / "out")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    assert "latest_json_path" not in paths


def test_all_controlled_rows_usable_false(tmp_path: Path) -> None:
    """VAL-SGATE-037: Sports cluster-control controlled_rows are usable=false."""
    module = load_cluster_control_module()
    ccd_path = tmp_path / "ccd.json"
    write_json(
        ccd_path,
        ccd_payload(
            capacity_row(
                "KXMLBGAME-26JUL02-CWSBAL-CWS",
                cluster="MLB|GAME1|2026-07-02T05:00Z",
                league="MLB",
                cost=100,
            ),
            capacity_row(
                "KXKBOGAME-26JUL02-KTWHAN-KT",
                cluster="KBO|GAME2|2026-07-02T05:00Z",
                league="KBO",
                cost=100,
            ),
            capacity_row(
                "KXLMBGAME-26JUL02-MONLAR-MON",
                cluster="LMB|GAME3|2026-07-02T05:00Z",
                league="LMB",
                cost=100,
            ),
        ),
    )

    report = module.build_sports_proxy_correlation_cluster_control(
        ccd_path=ccd_path,
        generated_utc="2026-07-02T00:00:00Z",
        max_cluster_share=0.35,
    )

    for row in report["controlled_rows"]:
        assert row["usable"] is False
    assert report["summary"]["usable_row_count"] == 0
