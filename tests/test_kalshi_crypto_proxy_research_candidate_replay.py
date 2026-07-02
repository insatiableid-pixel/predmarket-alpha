from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "kalshi_crypto_proxy_research_candidate_replay.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_replay_module():
    spec = importlib.util.spec_from_file_location("kalshi_crypto_proxy_research_candidate_replay", SCRIPT_PATH)
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


def model_report(*, research_candidate: bool = True):
    status = "research_candidate_fdr_passed" if research_candidate else "testable_research_candidate"
    return safe_packet(
        status="crypto_proxy_feature_model_falsification_ready_with_research_candidates"
        if research_candidate
        else "crypto_proxy_feature_model_falsification_ready_no_research_candidates",
        method={"test_fraction": 0.30},
        summary={"research_candidate_count": 1 if research_candidate else 0},
        evaluations=[
            {
                "model_id": "proxy_state_directional_accuracy",
                "status": status,
                "independent_label_count": 40,
                "oos_count": 12,
                "oos_correct_count": 12 if research_candidate else 6,
                "oos_accuracy": 1.0 if research_candidate else 0.5,
                "p_value": 0.001,
                "q_value": 0.001,
                "usable": False,
                "calibrated_probability": None,
                "expected_value_per_contract": None,
            }
        ],
    )


def label_row(idx: int, *, proxy_state: str = "proxy_above_floor_not_label", outcome: int = 1):
    hour = 1 + idx // 12
    minute = (idx % 12) * 4
    return {
        "contract_ticker": f"KXBTC15M-26JUL02{idx:04d}-15",
        "event_ticker": f"KXBTC15M-26JUL02{idx:04d}",
        "series_ticker": "KXBTC15M",
        "asset_symbol": "BTC",
        "contract_family": "fifteen_minute_up_down",
        "proxy_state": proxy_state,
        "yes_bid": 0.80 if "below" in proxy_state else 0.10,
        "yes_ask": 0.20 if "above" in proxy_state else 0.90,
        "yes_spread": 0.10,
        "yes_outcome": outcome,
        "decision_time": f"2026-07-02T{hour:02d}:{minute:02d}:00Z",
        "close_time": f"2026-07-02T{hour:02d}:{minute + 1:02d}:00Z",
        "settled_time": f"2026-07-02T{hour:02d}:{minute + 2:02d}:00Z",
        "label_status": "labeled_from_public_kalshi_settled_market",
        "usable": False,
        "calibrated_probability": None,
        "expected_value_per_contract": None,
    }


def test_replay_blocks_without_research_candidate(tmp_path: Path) -> None:
    module = load_replay_module()
    label_dir = tmp_path / "labels"
    model_path = tmp_path / "model.json"
    write_json(label_dir / "labels.json", safe_packet(rows=[label_row(idx) for idx in range(12)]))
    write_json(model_path, model_report(research_candidate=False))

    report = module.build_crypto_proxy_research_candidate_replay(
        label_dir=label_dir,
        model_falsification_path=model_path,
        generated_utc="2026-07-02T02:30:00Z",
        min_side_oos_labels=3,
        min_decay_buckets=2,
        min_decay_labels=10,
    )

    assert report["status"] == "crypto_proxy_research_candidate_replay_blocked_missing_research_candidate"
    assert report["summary"]["candidate_research_model_present"] is False
    assert report["safety"]["market_execution"] is False


def test_replay_uses_no_ask_from_yes_bid_and_blocks_predeployment_gates(tmp_path: Path) -> None:
    module = load_replay_module()
    label_dir = tmp_path / "labels"
    model_path = tmp_path / "model.json"
    rows = [
        label_row(idx, proxy_state="proxy_below_floor_not_label", outcome=0)
        if idx % 2
        else label_row(idx, proxy_state="proxy_above_floor_not_label", outcome=1)
        for idx in range(40)
    ]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))
    write_json(model_path, model_report())

    report = module.build_crypto_proxy_research_candidate_replay(
        label_dir=label_dir,
        model_falsification_path=model_path,
        generated_utc="2026-07-02T02:30:00Z",
        min_side_oos_labels=3,
        min_decay_buckets=2,
        min_decay_labels=10,
    )

    no_row = next(row for row in report["replay_rows"] if row["predicted_side"] == "no")
    assert no_row["selected_side_executable_price"] == 0.2
    assert no_row["all_in_break_even_probability"] > 0.2
    assert report["summary"]["positive_expected_value_row_count"] > 0
    assert report["summary"]["usable_row_count"] == 0
    assert report["status"] == "crypto_proxy_research_candidate_replay_blocked_predeployment_gates"
    gates = {item["name"]: item for item in report["gates"]}
    assert gates["capacity_depth_available"]["status"] == "blocked"
    assert gates["correlation_control_available"]["status"] == "blocked"
    assert gates["no_usable_ev_sizing_or_execution"]["status"] == "pass"


def test_replay_writer_emits_latest_outputs(tmp_path: Path) -> None:
    module = load_replay_module()
    module.MACRO_DIR = tmp_path / "macro"
    label_dir = tmp_path / "labels"
    model_path = tmp_path / "model.json"
    write_json(label_dir / "labels.json", safe_packet(rows=[label_row(idx) for idx in range(40)]))
    write_json(model_path, model_report())
    report = module.build_crypto_proxy_research_candidate_replay(
        label_dir=label_dir,
        model_falsification_path=model_path,
        generated_utc="2026-07-02T02:30:00Z",
        min_side_oos_labels=3,
        min_decay_buckets=2,
        min_decay_labels=10,
    )

    paths = module.write_crypto_proxy_research_candidate_replay(report, out_dir=tmp_path / "out")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    assert Path(paths["latest_json_path"]).exists()
    assert "Kalshi Crypto Proxy Research Candidate Replay" in Path(paths["markdown_path"]).read_text(
        encoding="utf-8"
    )


def test_replay_makefile_target_exists_and_watch_order() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-crypto-proxy-research-candidate-replay" in makefile
    assert "scripts/kalshi_crypto_proxy_research_candidate_replay.py" in makefile
    watch_target = makefile.split("kalshi-crypto-proxy-observation-watch-once:", 1)[1].split("\n\n", 1)[0]
    assert watch_target.index("kalshi-crypto-proxy-feature-model-falsification") < watch_target.index(
        "kalshi-crypto-proxy-research-candidate-replay"
    )
    assert watch_target.index("kalshi-crypto-proxy-research-candidate-replay") < watch_target.index(
        "kalshi-signal-factory-status"
    )


def test_decay_summary_provides_per_bucket_auditability_without_changing_gate(tmp_path: Path) -> None:
    """Decay evidence now carries per-bucket detail for auditability.

    Gate threshold is unchanged: recent bucket must be >= 0.5.
    """
    module = load_replay_module()

    # Build OOS rows across 3 distinct close-time buckets.
    # Buckets: T01:02Z (3 correct of 4), T02:02Z (2 correct of 4),
    #          T03:02Z (1 correct of 4 -- recent, below random).
    rows = []
    for bucket_hour, n_correct, n_total in [(1, 3, 4), (2, 2, 4), (3, 1, 4)]:
        for i in range(n_total):
            outcome = 1 if i < n_correct else 0
            rows.append({
                "proxy_state": "proxy_above_floor_not_label",
                "yes_outcome": outcome,
                "close_time": f"2026-07-02T{bucket_hour:02d}:02:00Z",
            })

    result = module.decay_summary(rows)

    assert result["bucket_count"] == 3
    assert result["status"] == "recent_bucket_below_random"
    assert result["recent_bucket_key"] == "2026-07-02T03:02Z"
    assert result["recent_bucket_accuracy"] == 0.25
    assert result["recent_bucket_label_count"] == 4
    assert result["total_decay_labels"] == 12
    assert result["passing_bucket_count"] == 2
    assert result["cumulative_accuracy"] == round(6 / 12, 10)
    assert len(result["decay_buckets"]) == 3
    # Per-bucket detail is chronologically ordered with exact fields.
    first = result["decay_buckets"][0]
    assert first["bucket"] == "2026-07-02T01:02Z"
    assert first["label_count"] == 4
    assert first["correct_count"] == 3
    assert first["accuracy"] == 0.75
    assert first["pass_threshold"] is True
    last = result["decay_buckets"][-1]
    assert last["bucket"] == "2026-07-02T03:02Z"
    assert last["pass_threshold"] is False


def test_decay_summary_empty_returns_full_zero_structure() -> None:
    module = load_replay_module()
    result = module.decay_summary([])
    assert result["bucket_count"] == 0
    assert result["status"] == "blocked_missing_decay_buckets"
    assert result["decay_buckets"] == []
    assert result["total_decay_labels"] == 0
    assert result["passing_bucket_count"] == 0
    assert result["cumulative_accuracy"] is None


def test_replay_report_surfaces_decay_detail_in_summary_and_gate_reason(tmp_path: Path) -> None:
    module = load_replay_module()
    label_dir = tmp_path / "labels"
    model_path = tmp_path / "model.json"
    rows = [
        label_row(idx, proxy_state="proxy_above_floor_not_label", outcome=1)
        for idx in range(40)
    ]
    write_json(label_dir / "labels.json", safe_packet(rows=rows))
    write_json(model_path, model_report())

    report = module.build_crypto_proxy_research_candidate_replay(
        label_dir=label_dir,
        model_falsification_path=model_path,
        generated_utc="2026-07-02T02:30:00Z",
        min_side_oos_labels=3,
        min_decay_buckets=2,
        min_decay_labels=10,
    )

    s = report["summary"]
    assert "decay_buckets" in s
    assert "total_decay_labels" in s
    assert "passing_bucket_count" in s
    assert "cumulative_decay_accuracy" in s
    assert "recent_bucket_key" in s
    assert "recent_bucket_label_count" in s
    decay_gate = next(g for g in report["gates"] if g["name"] == "decay_survival_available")
    assert "cumulative accuracy" in decay_gate["reason"]
    assert "pass" in decay_gate["reason"]
    assert report["summary"]["usable_row_count"] == 0

