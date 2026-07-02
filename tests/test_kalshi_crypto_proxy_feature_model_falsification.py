from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "kalshi_crypto_proxy_feature_model_falsification.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_model_module():
    spec = importlib.util.spec_from_file_location("kalshi_crypto_proxy_feature_model_falsification", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def safe_packet(rows=None, **overrides):
    payload = {
        "schema_version": 1,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "rows": rows or [],
        "safety": {
            "research_only": True,
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
            "staking_or_sizing_guidance": False,
        },
    }
    payload.update(overrides)
    return payload


def label_row(idx: int, *, ticker: str | None = None, proxy_state: str = "proxy_above_floor_not_label", outcome: int = 1):
    day = 2
    hour = 1 + idx // 8
    minute = (idx % 8) * 5
    return {
        "contract_ticker": ticker or f"KXBTC15M-26JUL{idx:06d}-15",
        "event_ticker": f"KXBTC15M-26JUL{idx:06d}",
        "series_ticker": "KXBTC15M",
        "asset_symbol": "BTC",
        "contract_family": "fifteen_minute_up_down",
        "proxy_state": proxy_state,
        "proxy_price": 60000 + idx,
        "yes_ask": 0.60,
        "yes_outcome": outcome,
        "decision_time": f"2026-07-{day:02d}T{hour:02d}:{minute:02d}:00Z",
        "close_time": f"2026-07-{day:02d}T{hour + 1:02d}:{minute:02d}:00Z",
        "settled_time": f"2026-07-{day:02d}T{hour + 1:02d}:{minute + 1:02d}:00Z",
        "label_status": "labeled_from_public_kalshi_settled_market",
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


def test_feature_model_falsification_blocks_when_labels_missing(tmp_path: Path) -> None:
    module = load_model_module()

    report = module.build_crypto_proxy_feature_model_falsification(
        label_dir=tmp_path / "missing-labels",
        generated_utc="2026-07-02T01:30:00Z",
    )

    assert report["status"] == "crypto_proxy_feature_model_falsification_blocked_missing_labels"
    assert report["summary"]["independent_contract_label_count"] == 0
    assert report["safety"]["market_execution"] is False


def test_feature_model_falsification_collapses_duplicate_contract_labels(tmp_path: Path) -> None:
    module = load_model_module()
    label_dir = tmp_path / "labels"
    rows = [
        label_row(0, ticker="KXBTC15M-26JUL012115-15", proxy_state="proxy_below_floor_not_label", outcome=0),
        label_row(1, ticker="KXBTC15M-26JUL012115-15", proxy_state="proxy_above_floor_not_label", outcome=1),
        label_row(2, ticker="KXETH15M-26JUL012115-15", proxy_state="proxy_above_floor_not_label", outcome=1),
    ]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))

    report = module.build_crypto_proxy_feature_model_falsification(
        label_dir=label_dir,
        generated_utc="2026-07-02T01:30:00Z",
        min_independent_labels=3,
        min_oos_labels=1,
    )

    assert report["summary"]["valid_label_row_count"] == 3
    assert report["summary"]["independent_contract_label_count"] == 2
    assert report["summary"]["duplicate_label_row_count"] == 1
    assert report["status"] == "crypto_proxy_feature_model_falsification_blocked_insufficient_independent_labels"


def test_feature_model_falsification_promotes_only_after_oos_fdr_pass(tmp_path: Path) -> None:
    module = load_model_module()
    label_dir = tmp_path / "labels"
    rows = [label_row(idx, proxy_state="proxy_above_floor_not_label", outcome=1) for idx in range(20)]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))

    report = module.build_crypto_proxy_feature_model_falsification(
        label_dir=label_dir,
        generated_utc="2026-07-02T01:30:00Z",
        min_independent_labels=12,
        min_oos_labels=5,
        fdr_alpha=0.10,
    )

    directional = next(item for item in report["evaluations"] if item["model_id"] == "proxy_state_directional_accuracy")
    assert report["status"] == "crypto_proxy_feature_model_falsification_ready_with_research_candidates"
    assert report["summary"]["research_candidate_count"] == 1
    assert directional["status"] == "research_candidate_fdr_passed"
    assert directional["q_value"] <= 0.10
    assert directional["usable"] is False
    assert directional["calibrated_probability"] is None
    assert directional["expected_value_per_contract"] is None


def test_feature_model_falsification_writer_emits_latest_outputs(tmp_path: Path) -> None:
    module = load_model_module()
    module.MACRO_DIR = tmp_path / "macro"
    label_dir = tmp_path / "labels"
    write_json(label_dir / "labels.json", safe_packet(rows=[label_row(0)]))
    report = module.build_crypto_proxy_feature_model_falsification(
        label_dir=label_dir,
        generated_utc="2026-07-02T01:30:00Z",
    )

    paths = module.write_crypto_proxy_feature_model_falsification(report, out_dir=tmp_path / "out")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    assert Path(paths["latest_json_path"]).exists()
    assert "Kalshi Crypto Proxy Feature Model Falsification" in Path(paths["markdown_path"]).read_text(
        encoding="utf-8"
    )


def test_feature_model_falsification_makefile_target_exists() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-crypto-proxy-feature-model-falsification" in makefile
    assert "scripts/kalshi_crypto_proxy_feature_model_falsification.py" in makefile
    watch_target = makefile.split("kalshi-crypto-proxy-observation-watch-once:", 1)[1].split("\n\n", 1)[0]
    assert "kalshi-crypto-proxy-observation-loop" in watch_target
    assert "kalshi-crypto-proxy-feature-model-falsification" in watch_target
    assert watch_target.index("kalshi-crypto-proxy-observation-loop") < watch_target.index(
        "kalshi-crypto-proxy-feature-model-falsification"
    )
    assert watch_target.index("kalshi-crypto-proxy-feature-model-falsification") < watch_target.index(
        "kalshi-signal-factory-status"
    )
