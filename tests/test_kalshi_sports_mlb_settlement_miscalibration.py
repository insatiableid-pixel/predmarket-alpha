from __future__ import annotations

import importlib.util
from pathlib import Path

from predmarket.shared_helpers import benjamini_hochberg
from predmarket.sports_mlb_settlement_miscalibration import (
    build_fixed_clock_labels,
    hold_to_settlement_economics,
    hypothesis_registry,
    normalize_observation_row,
    resolve_kxmlbgame_taker_fee,
    select_asof_book,
    taker_fee,
    validate_book,
)
from predmarket.sports_mlb_settlement_miscalibration_eval import (
    apply_fdr,
    collapse_event_independence,
    eligible_signal_rows,
    evaluate_hypothesis,
    family_resolution_counts,
    hard_gate_assessment,
    lifecycle_status,
    resolve_spec_status,
    slate_cluster_sign_flip_test,
    synthetic_tests,
)


def load_script():
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "kalshi_sports_mlb_settlement_miscalibration.py"
    )
    spec = importlib.util.spec_from_file_location(
        "kalshi_sports_mlb_settlement_miscalibration", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _obs(
    *,
    ticker: str,
    event: str,
    observed_at: str,
    yes_mid: float,
    snapshot_id: str,
) -> dict:
    half_spread = 0.01
    row = normalize_observation_row(
        {
            "snapshot_id": snapshot_id,
            "contract_ticker": ticker,
            "event_ticker": event,
            "series_ticker": "KXMLBGAME",
            "observed_at_utc": observed_at,
            "best_yes_bid": round(yes_mid - half_spread, 4),
            "best_yes_ask": round(yes_mid + half_spread, 4),
            "best_no_bid": round(1 - (yes_mid + half_spread), 4),
            "best_no_ask": round(1 - (yes_mid - half_spread), 4),
            "yes_bid_depth_top1": 20.0,
            "yes_ask_depth_top1": 18.0,
            "no_bid_depth_top1": 15.0,
            "no_ask_depth_top1": 16.0,
            "yes_mid": yes_mid,
            "yes_spread": 0.02,
            "total_depth_contracts": 100.0,
            "entry_source": "test",
        },
        source_path="test",
        source_sha256="test",
        index=0,
    )
    assert row is not None
    return row


def test_validate_book_and_fee_provenance() -> None:
    ok, reason = validate_book(0.6, 0.5)
    assert not ok
    assert reason == "crossed_book"
    fee = taker_fee(0.5)
    assert fee > 0
    meta = resolve_kxmlbgame_taker_fee(0.5)
    assert meta["fee"] == fee
    assert meta["fee_type"] == "quadratic"
    assert meta["fee_source"]
    assert meta["fee_fallback_state"] == "conservative_general_quadratic"
    assert meta["fee_series_ticker"] == "KXMLBGAME"
    econ = hold_to_settlement_economics(
        side="yes",
        yes_ask=0.5,
        no_ask=0.5,
        yes_outcome=1,
        yes_ask_depth=10,
        no_ask_depth=10,
    )
    assert econ["label_status"] == "hold_to_settlement_labeled"
    assert econ["net_payoff_per_contract"] == econ["gross_payoff_per_contract"] - econ["entry_fee"]
    assert econ["entry_fee"] == fee
    assert econ["fee_source"] == meta["fee_source"]
    assert econ["fee_mode"] == "taker"


def test_fee_multiplier_and_flat_fallback() -> None:
    from decimal import Decimal

    from predmarket.kalshi_execution_cost import FeeType

    doubled = resolve_kxmlbgame_taker_fee(
        0.5,
        fee_type=FeeType(kind="quadratic", multiplier=Decimal("2.0")),
    )
    base = resolve_kxmlbgame_taker_fee(0.5)
    assert doubled["fee"] > base["fee"]
    assert doubled["fee_multiplier"] == 2.0
    assert doubled["fee_fallback_state"] == "none"

    flat = resolve_kxmlbgame_taker_fee(
        0.5,
        fee_type=FeeType(kind="flat", multiplier=Decimal("1.0")),
    )
    assert flat["fee_type"] == "quadratic"
    assert "fallback" in flat["fee_fallback_state"] or flat["fee_source"].startswith("flat")


def test_asof_never_future_and_staleness() -> None:
    books = [
        _obs(
            ticker="KXMLBGAME-26JUL081805BOSNYY-BOS",
            event="KXMLBGAME-26JUL081805BOSNYY",
            observed_at="2026-07-08T21:55:00Z",
            yes_mid=0.55,
            snapshot_id="a",
        ),
        _obs(
            ticker="KXMLBGAME-26JUL081805BOSNYY-BOS",
            event="KXMLBGAME-26JUL081805BOSNYY",
            observed_at="2026-07-08T22:05:00Z",
            yes_mid=0.80,
            snapshot_id="future",
        ),
    ]
    clock_ts = books[0]["observed_ts"] + 300
    selected, status = select_asof_book(books, clock_ts=clock_ts, max_staleness_seconds=900)
    assert status == "matched"
    assert selected is not None
    assert selected["snapshot_id"] == "a"

    stale_only = [books[0]]
    selected2, status2 = select_asof_book(
        stale_only, clock_ts=clock_ts + 7200, max_staleness_seconds=900
    )
    assert selected2 is None
    assert status2 == "censored_stale_book"


def test_synthetic_suite_passes() -> None:
    results = synthetic_tests()
    assert results
    failed = [item for item in results if not item.get("passed")]
    assert not failed, failed


def test_fixed_clock_labels_and_independence() -> None:
    game = "KXMLBGAME-26JUL081805BOSNYY"
    observations = []
    for team, mid in (("BOS", 0.58), ("NYY", 0.42)):
        for hour, snap in ((20, "h20"), (21, "h21"), (22, "h22")):
            observations.append(
                _obs(
                    ticker=f"{game}-{team}",
                    event=game,
                    observed_at=f"2026-07-08T{hour}:50:00Z",
                    yes_mid=mid + (0.01 if hour == 22 else 0.0),
                    snapshot_id=f"{team}-{snap}",
                )
            )
    settlements = {
        f"{game}-BOS": {
            "ticker": f"{game}-BOS",
            "event_ticker": game,
            "result": "yes",
            "occurrence_datetime": "2026-07-08T23:05:00Z",
            "open_time": "2026-07-06T12:00:00Z",
        },
        f"{game}-NYY": {
            "ticker": f"{game}-NYY",
            "event_ticker": game,
            "result": "no",
            "occurrence_datetime": "2026-07-08T23:05:00Z",
            "open_time": "2026-07-06T12:00:00Z",
        },
    }
    labels, summary = build_fixed_clock_labels(
        observations,
        settlements,
        clocks={"T-60m": 3600, "T-15m": 900},
        staleness={"T-60m": 15 * 60, "T-15m": 10 * 60},
    )
    labeled = [row for row in labels if row["label_status"] == "labeled"]
    assert labeled
    assert summary["labeled_row_count"] == len(labeled)
    assert "slates_by_clock" in summary
    yes_row = next(row for row in labeled if row["contract_ticker"].endswith("-BOS"))
    assert yes_row["yes_net_payoff"] < yes_row["yes_gross_payoff"]
    assert yes_row["yes_settlement_payoff"] == 1.0
    assert yes_row.get("fee_source")

    fired = eligible_signal_rows(
        labeled,
        {
            "clock_name": "T-60m",
            "side": "yes",
            "feature": "p_hat",
            "direction": "gt",
            "threshold": 0.01,
        },
    )
    collapsed = collapse_event_independence(fired)
    assert len(collapsed) == 1


def test_slate_sign_flip_hand_computable_and_deterministic() -> None:
    # 6 slates, each with one +1 event: observed mean = 1.0.
    # Any cluster flip reduces the mean, so only the all-positive flip matches.
    rows = [
        {
            "event_ticker": f"E{i}",
            "game_start_ts": 1_720_000_000 + i * 86400,
            "selected_net_return": 1.0,
            "selected_calibration_residual": 1.0,
        }
        for i in range(6)
    ]
    a = slate_cluster_sign_flip_test(
        rows, "selected_net_return", n_resamples=200, seed=42, min_clusters=6
    )
    b = slate_cluster_sign_flip_test(
        rows, "selected_net_return", n_resamples=200, seed=42, min_clusters=6
    )
    assert a["p_value"] == b["p_value"]
    assert a["observed_mean"] == 1.0
    assert a["method"] == "slate_cluster_sign_flip"
    assert a["null"] == "E[value] <= 0"
    # With 200 resamples, chance of all 6 signs positive is 1/64; p is small.
    assert float(a["p_value"]) < 0.1
    # Zero-mean should not reject.
    zeros = [{**row, "selected_net_return": 0.0} for row in rows]
    z = slate_cluster_sign_flip_test(
        zeros, "selected_net_return", n_resamples=200, seed=7, min_clusters=6
    )
    assert float(z["p_value"]) > 0.2


def test_complements_and_duplicates_do_not_inflate_power() -> None:
    complements = [
        {
            "event_ticker": "EVT0",
            "contract_ticker": "EVT0-A",
            "decision_ts": 1.0,
            "selected_net_return": 0.9,
            "game_start_ts": 1_720_000_000,
        },
        {
            "event_ticker": "EVT0",
            "contract_ticker": "EVT0-B",
            "decision_ts": 2.0,
            "selected_net_return": -0.9,
            "game_start_ts": 1_720_000_000,
        },
    ]
    collapsed = collapse_event_independence(complements)
    assert len(collapsed) == 1
    assert collapsed[0]["contract_ticker"] == "EVT0-A"
    # Duplicated snapshots collapse by event.
    dups = complements + complements
    assert len(collapse_event_independence(dups)) == 1


def test_bh_on_p_joint_hand_computable() -> None:
    # Hand-check BH ranks for three novel p_joint values.
    indexed = [(0, 0.01), (1, 0.04), (2, 0.20)]
    q_map = benjamini_hochberg(indexed)
    # largest p: q = min(1, 0.20 * 3/3) = 0.20
    # mid: min(0.20, 0.04 * 3/2) = 0.06
    # small: min(0.06, 0.01 * 3/1) = 0.03
    assert abs(q_map[2] - 0.20) < 1e-12
    assert abs(q_map[1] - 0.06) < 1e-12
    assert abs(q_map[0] - 0.03) < 1e-12

    evaluations = [
        {
            "model_id": "novel_a",
            "status": "testable",
            "p_joint": 0.01,
            "p_economic": 0.01,
            "p_calibration": 0.005,
            "oos_mean_net_return": 0.05,
            "oos_mean_calibration_residual": 0.04,
            "negative_control": False,
            "baseline_only": False,
        },
        {
            "model_id": "control_b",
            "status": "testable",
            "p_joint": 0.001,
            "p_economic": 0.001,
            "p_calibration": 0.001,
            "oos_mean_net_return": 0.2,
            "oos_mean_calibration_residual": 0.2,
            "negative_control": True,
            "baseline_only": False,
        },
        {
            "model_id": "novel_c",
            "status": "underpowered",
            "p_joint": 0.02,
            "p_economic": 0.02,
            "p_calibration": 0.01,
            "oos_mean_net_return": 0.05,
            "oos_mean_calibration_residual": 0.04,
            "negative_control": False,
            "baseline_only": False,
        },
    ]
    out = apply_fdr(evaluations, alpha=0.05)
    # Only novel_a enters FDR family.
    assert out[0]["fdr_family_size"] == 1
    assert out[0]["status"] == "research_candidate_fdr_passed"
    assert out[1]["q_value"] is None  # control excluded
    assert out[2]["q_value"] is None  # underpowered excluded


def test_lifecycle_underpowered_blocks_outcome_b() -> None:
    evaluations = [
        {
            "model_id": "a",
            "status": "powered_falsified",
            "power_met": True,
            "negative_control": False,
            "baseline_only": False,
        },
        {
            "model_id": "b",
            "status": "underpowered",
            "power_met": False,
            "negative_control": False,
            "baseline_only": False,
        },
    ]
    assert lifecycle_status(evaluations) == "evidence_incomplete"
    counts = family_resolution_counts(evaluations)
    assert counts["underpowered_count"] == 1
    assert counts["powered_falsified_count"] == 1

    all_falsified = [
        {
            "model_id": "a",
            "status": "powered_falsified",
            "power_met": True,
            "negative_control": False,
            "baseline_only": False,
        },
        {
            "model_id": "b",
            "status": "powered_falsified",
            "power_met": True,
            "negative_control": False,
            "baseline_only": False,
        },
    ]
    assert lifecycle_status(all_falsified) == "falsified"


def test_breadth_failure_freezes_not_falsifies() -> None:
    evaluation = {
        "model_id": "path_slope_continuation_buy_yes_t60m",
        "status": "research_candidate_fdr_passed",
        "power_met": True,
        "negative_control": False,
        "baseline_only": False,
        "oos_mean_net_return": 0.1,
        "oos_mean_calibration_residual": 0.1,
        "p_economic": 0.01,
        "p_calibration": 0.01,
        "p_joint": 0.01,
        "q_value": 0.02,
    }
    assessment = {
        "research_ready": False,
        "discovery_gates_pass": False,
        "breadth_only_failure": True,
        "failed_non_confirmation_gates": ["cluster_share_le_max"],
        "gates": [],
    }
    resolved = resolve_spec_status(evaluation, assessment)
    assert resolved["status"] == "frozen_candidate_waiting_multi_slate_confirmation"
    assert lifecycle_status([resolved]) == "confirmation_pending"


def test_hard_gate_uses_joint_inference_fields() -> None:
    evaluation = {
        "oos_event_count": 25,
        "oos_slate_count": 8,
        "oos_mean_net_return": 0.05,
        "oos_mean_calibration_residual": 0.04,
        "p_economic": 0.01,
        "p_calibration": 0.02,
        "p_joint": 0.02,
        "q_value": 0.03,
        "bootstrap_mean_net_lower_95": 0.01,
        "positive_temporal_buckets": 4,
        "recent_bucket_mean_net": 0.02,
        "positive_capacity_event_count": 5,
        "mean_capacity_contracts": 10.0,
        "orderbook_entry_share": 0.9,
        "largest_slate_cluster_share": 0.2,
        "negative_control": False,
        "baseline_only": False,
    }
    assessment = hard_gate_assessment(evaluation, min_oos=20, confirmation=None)
    assert assessment["discovery_gates_pass"] is True
    names = {gate["name"] for gate in assessment["gates"]}
    assert "economic_inference" in names
    assert "calibration_inference" in names
    assert "fdr_q_le_alpha_on_p_joint" in names


def test_registry_finite_and_evaluation_runs() -> None:
    registry = hypothesis_registry()
    assert 8 <= len(registry) <= 12
    assert any(row.get("baseline_only") for row in registry)
    assert sum(1 for row in registry if row.get("negative_control")) >= 2
    assert (
        sum(
            1
            for row in registry
            if not row.get("baseline_only") and not row.get("negative_control")
        )
        <= 10
    )

    labels = []
    for index in range(30):
        event = f"KXMLBGAME-26JUL{index:02d}1800AAAABB"
        ticker = f"{event}-AAA"
        mid = 0.30 if index % 2 == 0 else 0.75
        obs = _obs(
            ticker=ticker,
            event=event,
            observed_at=f"2026-07-{(index % 28) + 1:02d}T17:00:00Z",
            yes_mid=mid,
            snapshot_id=f"s{index}",
        )
        settlements = {
            ticker: {
                "ticker": ticker,
                "event_ticker": event,
                "result": "yes" if index % 3 != 0 else "no",
                "occurrence_datetime": f"2026-07-{(index % 28) + 1:02d}T18:00:00Z",
                "open_time": f"2026-07-{(index % 28) + 1:02d}T00:00:00Z",
            }
        }
        built, _ = build_fixed_clock_labels(
            [obs],
            settlements,
            clocks={"T-60m": 3600},
            staleness={"T-60m": 2 * 3600},
        )
        labels.extend(built)

    evaluations = [
        evaluate_hypothesis(labels, spec, min_oos_labels=5, min_events=5, min_oos_slates=2)
        for spec in registry
        if spec["clock_name"] == "T-60m"
    ]
    evaluations = apply_fdr(evaluations, alpha=0.05)
    assert evaluations
    assert all("p_economic" in row for row in evaluations)
    assert all("p_calibration" in row for row in evaluations)
    assert all("p_joint" in row for row in evaluations)
    assert all(row.get("p_value_mean_net_positive") == row.get("p_economic") for row in evaluations)


def test_script_builds_report_without_network(tmp_path: Path) -> None:
    module = load_script()
    obs_dir = tmp_path / "obs"
    sett_dir = tmp_path / "sett"
    obs_dir.mkdir()
    sett_dir.mkdir()
    packet = {
        "rows": [
            {
                "snapshot_id": "snap1",
                "contract_ticker": "KXMLBGAME-26JUL081805BOSNYY-BOS",
                "event_ticker": "KXMLBGAME-26JUL081805BOSNYY",
                "series_ticker": "KXMLBGAME",
                "observed_at_utc": "2026-07-08T22:00:00Z",
                "best_yes_bid": 0.54,
                "best_yes_ask": 0.56,
                "best_no_bid": 0.44,
                "best_no_ask": 0.46,
                "yes_bid_depth_top1": 10,
                "yes_ask_depth_top1": 12,
                "no_bid_depth_top1": 8,
                "no_ask_depth_top1": 9,
                "yes_mid": 0.55,
                "yes_spread": 0.02,
            }
        ]
    }
    (obs_dir / "obs.json").write_text(__import__("json").dumps(packet), encoding="utf-8")
    markets = {
        "markets": [
            {
                "ticker": "KXMLBGAME-26JUL081805BOSNYY-BOS",
                "event_ticker": "KXMLBGAME-26JUL081805BOSNYY",
                "result": "yes",
                "occurrence_datetime": "2026-07-08T23:05:00Z",
                "open_time": "2026-07-05T12:00:00Z",
            }
        ]
    }
    (sett_dir / "sett.json").write_text(__import__("json").dumps(markets), encoding="utf-8")
    report = module.build_report(
        observation_dirs=[obs_dir],
        settlement_dirs=[sett_dir],
        proxy_label_dir=tmp_path / "empty_labels",
        raw_dir=tmp_path / "raw",
        discovery_cutoff_utc="2026-07-10T00:00:00Z",
        fetch_public_settlements=False,
        fdr_alpha=0.05,
        min_oos_events=5,
    )
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["family_id"] == "sports_mlb_settlement_miscalibration_v1"
    assert report["schema_version"] == 2
    assert "historical_discovery_data_cutoff_utc" in report
    assert report["discovery_cutoff_provenance"].startswith("runtime_censor")
    assert report["capture_readiness"]["capture_infrastructure_ready"] is True
    assert report["capture_readiness"]["evidence_panel_ready"] is False
    assert "panel_insufficient" in report["capture_readiness"]["status"]
    assert (
        report["family_status"] != "falsified"
        or report["resolution_counts"]["underpowered_count"] == 0
    )
    # With tiny sample, honest state is evidence incomplete / discovery pending-like.
    assert report["family_status"] in {
        "evidence_incomplete",
        "confirmation_pending",
        "research_ready",
        "falsified",
    }
    assert "evaluations" in report
    written = module.write_outputs(report, out_dir=tmp_path / "out")
    assert Path(written["json"]).is_file()
    assert Path(written["md"]).is_file()
