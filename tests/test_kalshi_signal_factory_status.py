from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kalshi_signal_factory_status.py"
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_status_module():
    spec = importlib.util.spec_from_file_location("kalshi_signal_factory_status", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kalshi_signal_factory_status"] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


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


def write_crypto_signal_foundation(module, tmp_path: Path):
    """Write upstream artifacts and return an Artifacts bundle.

    Observation-loop, model-falsification, and replay paths are left as
    missing files so callers can override them via ``replace``.
    """
    universe = tmp_path / "universe.json"
    ledger = tmp_path / "ledger.json"
    queue = tmp_path / "queue.json"
    robustness = tmp_path / "robustness.json"
    registry = tmp_path / "registry.json"
    falsification = tmp_path / "falsification.json"
    builder = tmp_path / "builder.json"
    oos = tmp_path / "oos.json"
    breadth = tmp_path / "breadth.json"
    feature = tmp_path / "feature-packet.json"
    write_json(
        universe,
        safe_artifact(
            summary={
                "candidate_count": 100,
                "model_route_candidate_count": 2,
                "soft_watch_candidate_count": 98,
            }
        ),
    )
    write_json(ledger, safe_artifact(summary={"row_count": 4}))
    write_json(queue, safe_artifact(summary={"queued_row_count": 0}))
    write_json(robustness, safe_artifact(summary={"repeat_positive_row_count": 0}))
    write_json(
        registry, safe_artifact(summary={"hypothesis_count": 6, "multiple_testing_family_count": 6})
    )
    write_json(
        falsification,
        safe_artifact(
            status="falsification_gate_blocked_missing_labeled_oos_evidence",
            registered_hypothesis_count=6,
            tested_hypothesis_count=0,
            promoted_hypothesis_count=0,
        ),
    )
    write_json(
        builder,
        safe_artifact(
            status="labeled_observation_builder_pending_observations_waiting_settlement",
            summary={"total_pending_row_count": 44, "label_row_count": 0},
        ),
    )
    write_json(
        oos,
        safe_artifact(
            status="labeled_oos_backtest_blocked_missing_labeled_observations",
            summary={"valid_observation_count": 0},
        ),
    )
    write_json(
        breadth,
        safe_artifact(
            status="probability_breadth_scout_ready_crypto_proxy_feature_route",
            summary={
                "fast_candidate_count": 1538,
                "crypto_fast_candidate_count": 1256,
                "available_proxy_source_count": 3,
            },
        ),
    )
    write_json(
        feature,
        safe_artifact(
            status="crypto_proxy_feature_packet_ready",
            summary={
                "feature_row_count": 1210,
                "feature_ready_count": 1210,
                "proxy_available_asset_count": 9,
            },
        ),
    )
    return replace(
        module.Artifacts.isolated(tmp_path),
        universe_scan_path=universe,
        ev_ledger_path=ledger,
        review_queue_path=queue,
        robustness_path=robustness,
        hypothesis_registry_path=registry,
        falsification_gate_path=falsification,
        labeled_observation_builder_path=builder,
        labeled_oos_backtest_path=oos,
        probability_breadth_scout_path=breadth,
        crypto_proxy_feature_packet_path=feature,
    )


# ---------------------------------------------------------------------------
# Hermeticity regression test
# ---------------------------------------------------------------------------


def test_signal_factory_status_is_hermetic_with_isolated_bundle(tmp_path: Path) -> None:
    """An isolated bundle must never leak real on-disk artifacts into the
    routing decision, even when every upstream artifact is missing."""
    module = load_status_module()
    report = module.build_signal_factory_status(
        artifacts=module.Artifacts.isolated(tmp_path),
        generated_utc="2026-07-02T12:00:00Z",
    )
    assert report["status"] == "signal_factory_blocked_missing_universe_inventory"
    # next_tranche must not reference capacity/correlation/decay (leaked from disk)
    assert report["next_tranche"]["name"] != "kalshi_crypto_proxy_capacity_correlation_decay"


# ---------------------------------------------------------------------------
# Stage-by-stage routing tests
# ---------------------------------------------------------------------------


def test_signal_factory_status_names_falsification_as_next_gap(tmp_path: Path) -> None:
    module = load_status_module()
    universe = tmp_path / "universe.json"
    ledger = tmp_path / "ledger.json"
    queue = tmp_path / "queue.json"
    robustness = tmp_path / "robustness.json"
    write_json(
        universe,
        safe_artifact(
            status="universe_scan_ready_with_model_routes",
            summary={
                "candidate_count": 6070,
                "model_route_candidate_count": 725,
                "soft_watch_candidate_count": 5345,
                "classification_counts": {"mlb": 725},
            },
        ),
    )
    write_json(
        ledger,
        safe_artifact(
            status="kalshi_ev_ledger_ready_with_usable_contract_edges",
            summary={
                "row_count": 348,
                "usable_row_count": 12,
                "calibrated_probability_overlay_row_count": 32,
            },
        ),
    )
    write_json(queue, safe_artifact(summary={"queued_row_count": 12}))
    write_json(robustness, safe_artifact(summary={"repeat_positive_row_count": 12}))

    report = module.build_signal_factory_status(
        artifacts=replace(
            module.Artifacts.isolated(tmp_path),
            universe_scan_path=universe,
            ev_ledger_path=ledger,
            review_queue_path=queue,
            robustness_path=robustness,
        ),
        generated_utc="2026-07-01T23:00:00Z",
    )

    assert report["status"] == "signal_factory_foundation_ready_falsification_missing"
    assert report["north_star"].startswith("Extract and exploit")
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["safety"]["market_execution"] is False
    assert report["summary"]["universe_candidate_count"] == 6070
    assert report["summary"]["legacy_usable_ev_row_count"] == 12
    gates = {item["name"]: item for item in report["capabilities"]}
    assert gates["kalshi_universe_inventory"]["status"] == "pass"
    assert gates["fdr_controlled_falsification_gate"]["status"] == "blocked"
    assert gates["fractional_kelly_sizing_policy"]["status"] == "blocked"
    assert report["next_tranche"]["name"] == "kalshi_hypothesis_registry_and_falsification_gate"
    assert "Stop before adding sizing or execution" in report["next_tranche"]["stop_condition"]


def test_signal_factory_status_blocks_without_universe_scan(tmp_path: Path) -> None:
    module = load_status_module()

    report = module.build_signal_factory_status(
        artifacts=module.Artifacts.isolated(tmp_path),
        generated_utc="2026-07-01T23:00:00Z",
    )

    assert report["status"] == "signal_factory_blocked_missing_universe_inventory"
    assert report["summary"]["capability_gate_counts"]["blocked"] >= 1


def test_signal_factory_status_advances_when_registry_exists(tmp_path: Path) -> None:
    module = load_status_module()
    universe = tmp_path / "universe.json"
    ledger = tmp_path / "ledger.json"
    queue = tmp_path / "queue.json"
    robustness = tmp_path / "robustness.json"
    registry = tmp_path / "registry.json"
    falsification = tmp_path / "falsification.json"
    write_json(
        universe,
        safe_artifact(
            summary={
                "candidate_count": 10,
                "model_route_candidate_count": 2,
                "soft_watch_candidate_count": 8,
            }
        ),
    )
    write_json(ledger, safe_artifact(summary={"row_count": 4, "usable_row_count": 0}))
    write_json(queue, safe_artifact(summary={"queued_row_count": 0}))
    write_json(robustness, safe_artifact(summary={"repeat_positive_row_count": 0}))
    write_json(
        registry,
        safe_artifact(
            status="hypothesis_registry_ready_falsification_blocked_missing_labeled_oos_evidence",
            summary={
                "hypothesis_count": 6,
                "candidate_unvalidated_count": 6,
                "multiple_testing_family_count": 6,
                "blocked_by_falsification_count": 6,
                "falsification_status": "falsification_gate_blocked_missing_labeled_oos_evidence",
            },
        ),
    )
    write_json(
        falsification,
        safe_artifact(
            status="falsification_gate_blocked_missing_labeled_oos_evidence",
            registered_hypothesis_count=6,
            tested_hypothesis_count=0,
            promoted_hypothesis_count=0,
            blocked_hypothesis_count=6,
        ),
    )

    report = module.build_signal_factory_status(
        artifacts=replace(
            module.Artifacts.isolated(tmp_path),
            universe_scan_path=universe,
            ev_ledger_path=ledger,
            review_queue_path=queue,
            robustness_path=robustness,
            hypothesis_registry_path=registry,
            falsification_gate_path=falsification,
        ),
        generated_utc="2026-07-01T23:00:00Z",
    )

    assert (
        report["status"]
        == "signal_factory_hypothesis_registry_ready_falsification_blocked_missing_labeled_oos_evidence"
    )
    assert report["summary"]["hypothesis_count"] == 6
    assert report["summary"]["multiple_testing_family_count"] == 6
    assert (
        report["summary"]["falsification_status"]
        == "falsification_gate_blocked_missing_labeled_oos_evidence"
    )
    gates = {item["name"]: item for item in report["capabilities"]}
    assert gates["agentic_hypothesis_registry"]["status"] == "pass"
    assert gates["fdr_controlled_falsification_gate"]["status"] == "blocked"
    assert report["next_tranche"]["name"] == "kalshi_labeled_oos_backtest_harness"
    assert "OOS cost-aware FDR evidence" in report["next_tranche"]["stop_condition"]


def test_signal_factory_status_routes_to_label_packet_builder_when_oos_harness_exists(
    tmp_path: Path,
) -> None:
    module = load_status_module()
    universe = tmp_path / "universe.json"
    ledger = tmp_path / "ledger.json"
    queue = tmp_path / "queue.json"
    robustness = tmp_path / "robustness.json"
    registry = tmp_path / "registry.json"
    falsification = tmp_path / "falsification.json"
    oos = tmp_path / "oos.json"
    write_json(
        universe,
        safe_artifact(
            summary={
                "candidate_count": 10,
                "model_route_candidate_count": 2,
                "soft_watch_candidate_count": 8,
            }
        ),
    )
    write_json(ledger, safe_artifact(summary={"row_count": 4}))
    write_json(queue, safe_artifact(summary={"queued_row_count": 0}))
    write_json(robustness, safe_artifact(summary={"repeat_positive_row_count": 0}))
    write_json(
        registry, safe_artifact(summary={"hypothesis_count": 6, "multiple_testing_family_count": 6})
    )
    write_json(
        falsification,
        safe_artifact(
            status="falsification_gate_blocked_missing_labeled_oos_evidence",
            registered_hypothesis_count=6,
            tested_hypothesis_count=0,
            promoted_hypothesis_count=0,
        ),
    )
    write_json(
        oos,
        safe_artifact(
            status="labeled_oos_backtest_blocked_missing_labeled_observations",
            summary={
                "valid_observation_count": 0,
                "testable_hypothesis_count": 0,
                "promoted_research_hypothesis_count": 0,
            },
        ),
    )

    report = module.build_signal_factory_status(
        artifacts=replace(
            module.Artifacts.isolated(tmp_path),
            universe_scan_path=universe,
            ev_ledger_path=ledger,
            review_queue_path=queue,
            robustness_path=robustness,
            hypothesis_registry_path=registry,
            falsification_gate_path=falsification,
            labeled_oos_backtest_path=oos,
        ),
        generated_utc="2026-07-01T23:00:00Z",
    )

    assert (
        report["status"] == "signal_factory_oos_backtest_harness_ready_labeled_observations_missing"
    )
    gates = {item["name"]: item for item in report["capabilities"]}
    assert gates["labeled_oos_backtest_harness"]["status"] == "pass"
    assert (
        report["summary"]["labeled_oos_backtest_status"]
        == "labeled_oos_backtest_blocked_missing_labeled_observations"
    )
    assert report["next_tranche"]["name"] == "kalshi_labeled_observation_packet_builder"


def test_signal_factory_status_surfaces_pending_observations(tmp_path: Path) -> None:
    module = load_status_module()
    universe = tmp_path / "universe.json"
    ledger = tmp_path / "ledger.json"
    queue = tmp_path / "queue.json"
    robustness = tmp_path / "robustness.json"
    registry = tmp_path / "registry.json"
    falsification = tmp_path / "falsification.json"
    builder = tmp_path / "builder.json"
    oos = tmp_path / "oos.json"
    write_json(
        universe,
        safe_artifact(
            summary={
                "candidate_count": 10,
                "model_route_candidate_count": 2,
                "soft_watch_candidate_count": 8,
            }
        ),
    )
    write_json(ledger, safe_artifact(summary={"row_count": 4}))
    write_json(queue, safe_artifact(summary={"queued_row_count": 0}))
    write_json(robustness, safe_artifact(summary={"repeat_positive_row_count": 0}))
    write_json(
        registry, safe_artifact(summary={"hypothesis_count": 6, "multiple_testing_family_count": 6})
    )
    write_json(
        falsification,
        safe_artifact(
            status="falsification_gate_blocked_missing_labeled_oos_evidence",
            registered_hypothesis_count=6,
            tested_hypothesis_count=0,
            promoted_hypothesis_count=0,
        ),
    )
    write_json(
        builder,
        safe_artifact(
            status="labeled_observation_builder_pending_observations_waiting_settlement",
            summary={"total_pending_row_count": 32, "label_row_count": 0},
        ),
    )
    write_json(
        oos,
        safe_artifact(
            status="labeled_oos_backtest_blocked_missing_labeled_observations",
            summary={
                "valid_observation_count": 0,
                "testable_hypothesis_count": 0,
                "promoted_research_hypothesis_count": 0,
            },
        ),
    )

    report = module.build_signal_factory_status(
        artifacts=replace(
            module.Artifacts.isolated(tmp_path),
            universe_scan_path=universe,
            ev_ledger_path=ledger,
            review_queue_path=queue,
            robustness_path=robustness,
            hypothesis_registry_path=registry,
            falsification_gate_path=falsification,
            labeled_observation_builder_path=builder,
            labeled_oos_backtest_path=oos,
        ),
        generated_utc="2026-07-01T23:00:00Z",
    )

    assert report["status"] == "signal_factory_oos_pending_observations_waiting_settlement"
    assert report["summary"]["labeled_observation_pending_count"] == 32
    gates = {item["name"]: item for item in report["capabilities"]}
    assert gates["labeled_observation_packet_builder"]["status"] == "pass"
    assert (
        report["next_tranche"]["name"] == "kalshi_probability_breadth_while_oos_observations_settle"
    )


def test_signal_factory_status_advances_to_crypto_feature_packets_when_breadth_scout_ready(
    tmp_path: Path,
) -> None:
    module = load_status_module()
    universe = tmp_path / "universe.json"
    ledger = tmp_path / "ledger.json"
    queue = tmp_path / "queue.json"
    robustness = tmp_path / "robustness.json"
    registry = tmp_path / "registry.json"
    falsification = tmp_path / "falsification.json"
    builder = tmp_path / "builder.json"
    oos = tmp_path / "oos.json"
    breadth = tmp_path / "breadth.json"
    write_json(
        universe,
        safe_artifact(
            summary={
                "candidate_count": 100,
                "model_route_candidate_count": 2,
                "soft_watch_candidate_count": 98,
            }
        ),
    )
    write_json(ledger, safe_artifact(summary={"row_count": 4}))
    write_json(queue, safe_artifact(summary={"queued_row_count": 0}))
    write_json(robustness, safe_artifact(summary={"repeat_positive_row_count": 0}))
    write_json(
        registry, safe_artifact(summary={"hypothesis_count": 6, "multiple_testing_family_count": 6})
    )
    write_json(
        falsification,
        safe_artifact(
            status="falsification_gate_blocked_missing_labeled_oos_evidence",
            registered_hypothesis_count=6,
            tested_hypothesis_count=0,
            promoted_hypothesis_count=0,
        ),
    )
    write_json(
        builder,
        safe_artifact(
            status="labeled_observation_builder_pending_observations_waiting_settlement",
            summary={"total_pending_row_count": 44, "label_row_count": 0},
        ),
    )
    write_json(
        oos,
        safe_artifact(
            status="labeled_oos_backtest_blocked_missing_labeled_observations",
            summary={"valid_observation_count": 0},
        ),
    )
    write_json(
        breadth,
        safe_artifact(
            status="probability_breadth_scout_ready_crypto_proxy_feature_route",
            summary={
                "fast_candidate_count": 1538,
                "crypto_fast_candidate_count": 1256,
                "weather_fast_candidate_count": 194,
                "available_proxy_source_count": 3,
                "selected_route": "crypto_proxy_fast_label_route",
            },
        ),
    )

    report = module.build_signal_factory_status(
        artifacts=replace(
            module.Artifacts.isolated(tmp_path),
            universe_scan_path=universe,
            ev_ledger_path=ledger,
            review_queue_path=queue,
            robustness_path=robustness,
            hypothesis_registry_path=registry,
            falsification_gate_path=falsification,
            labeled_observation_builder_path=builder,
            labeled_oos_backtest_path=oos,
            probability_breadth_scout_path=breadth,
        ),
        generated_utc="2026-07-02T00:00:00Z",
    )

    assert report["status"] == "signal_factory_probability_breadth_scout_ready_crypto_proxy_route"
    assert report["summary"]["probability_breadth_crypto_fast_candidate_count"] == 1256
    assert report["summary"]["probability_breadth_available_proxy_source_count"] == 3
    gates = {item["name"]: item for item in report["capabilities"]}
    assert gates["probability_breadth_scout"]["status"] == "pass"
    assert report["next_tranche"]["name"] == "kalshi_crypto_proxy_feature_packet"
    assert "proxy prices as official settlement labels" in report["next_tranche"]["stop_condition"]


def test_signal_factory_status_advances_to_crypto_observation_loop_when_feature_packet_ready(
    tmp_path: Path,
) -> None:
    module = load_status_module()
    universe = tmp_path / "universe.json"
    ledger = tmp_path / "ledger.json"
    queue = tmp_path / "queue.json"
    robustness = tmp_path / "robustness.json"
    registry = tmp_path / "registry.json"
    falsification = tmp_path / "falsification.json"
    builder = tmp_path / "builder.json"
    oos = tmp_path / "oos.json"
    breadth = tmp_path / "breadth.json"
    feature_packet = tmp_path / "crypto-feature-packet.json"
    write_json(
        universe,
        safe_artifact(
            summary={
                "candidate_count": 100,
                "model_route_candidate_count": 2,
                "soft_watch_candidate_count": 98,
            }
        ),
    )
    write_json(ledger, safe_artifact(summary={"row_count": 4}))
    write_json(queue, safe_artifact(summary={"queued_row_count": 0}))
    write_json(robustness, safe_artifact(summary={"repeat_positive_row_count": 0}))
    write_json(
        registry, safe_artifact(summary={"hypothesis_count": 6, "multiple_testing_family_count": 6})
    )
    write_json(
        falsification,
        safe_artifact(
            status="falsification_gate_blocked_missing_labeled_oos_evidence",
            registered_hypothesis_count=6,
            tested_hypothesis_count=0,
            promoted_hypothesis_count=0,
        ),
    )
    write_json(
        builder,
        safe_artifact(
            status="labeled_observation_builder_pending_observations_waiting_settlement",
            summary={"total_pending_row_count": 44, "label_row_count": 0},
        ),
    )
    write_json(
        oos,
        safe_artifact(
            status="labeled_oos_backtest_blocked_missing_labeled_observations",
            summary={"valid_observation_count": 0},
        ),
    )
    write_json(
        breadth,
        safe_artifact(
            status="probability_breadth_scout_ready_crypto_proxy_feature_route",
            summary={
                "fast_candidate_count": 1538,
                "crypto_fast_candidate_count": 1256,
                "weather_fast_candidate_count": 194,
                "available_proxy_source_count": 3,
                "selected_route": "crypto_proxy_fast_label_route",
            },
        ),
    )
    write_json(
        feature_packet,
        safe_artifact(
            status="crypto_proxy_feature_packet_ready",
            summary={
                "feature_row_count": 1210,
                "feature_ready_count": 1210,
                "proxy_available_asset_count": 9,
                "asset_counts": {"BTC": 400, "ETH": 300},
            },
        ),
    )

    report = module.build_signal_factory_status(
        artifacts=replace(
            module.Artifacts.isolated(tmp_path),
            universe_scan_path=universe,
            ev_ledger_path=ledger,
            review_queue_path=queue,
            robustness_path=robustness,
            hypothesis_registry_path=registry,
            falsification_gate_path=falsification,
            labeled_observation_builder_path=builder,
            labeled_oos_backtest_path=oos,
            probability_breadth_scout_path=breadth,
            crypto_proxy_feature_packet_path=feature_packet,
        ),
        generated_utc="2026-07-02T00:20:00Z",
    )

    assert report["status"] == "signal_factory_crypto_proxy_feature_packet_ready"
    assert report["summary"]["crypto_proxy_feature_row_count"] == 1210
    assert report["summary"]["crypto_proxy_feature_ready_count"] == 1210
    gates = {item["name"]: item for item in report["capabilities"]}
    assert gates["crypto_proxy_feature_packet"]["status"] == "pass"
    assert report["next_tranche"]["name"] == "kalshi_crypto_proxy_observation_loop"
    assert "settled Kalshi outcome matching" in report["next_tranche"]["why"]
    assert "official settlement labels" in report["next_tranche"]["stop_condition"]


def test_signal_factory_status_advances_to_crypto_observation_accumulation_when_waiting(
    tmp_path: Path,
) -> None:
    module = load_status_module()
    foundation = write_crypto_signal_foundation(module, tmp_path)
    observation = tmp_path / "observation-loop.json"
    write_json(
        observation,
        safe_artifact(
            status="crypto_proxy_observation_loop_ready_waiting_settlement",
            summary={
                "total_observation_row_count": 1210,
                "new_observation_row_count": 1210,
                "label_row_count": 0,
            },
        ),
    )

    report = module.build_signal_factory_status(
        artifacts=replace(foundation, crypto_proxy_observation_loop_path=observation),
        generated_utc="2026-07-02T00:35:00Z",
    )

    assert report["status"] == "signal_factory_crypto_proxy_observations_waiting_settlement"
    assert report["summary"]["crypto_proxy_observation_total_count"] == 1210
    assert report["summary"]["crypto_proxy_observation_label_count"] == 0
    gates = {item["name"]: item for item in report["capabilities"]}
    assert gates["crypto_proxy_observation_loop"]["status"] == "pass"
    assert report["next_tranche"]["name"] == "kalshi_crypto_proxy_observation_accumulation"
    assert "proxy states as labels" in report["next_tranche"]["stop_condition"]


def test_signal_factory_status_advances_to_crypto_feature_model_when_labels_ready(
    tmp_path: Path,
) -> None:
    module = load_status_module()
    foundation = write_crypto_signal_foundation(module, tmp_path)
    observation = tmp_path / "observation-loop.json"
    write_json(
        observation,
        safe_artifact(
            status="crypto_proxy_observation_loop_label_rows_ready",
            summary={
                "total_observation_row_count": 1210,
                "new_observation_row_count": 1210,
                "label_row_count": 185,
            },
        ),
    )

    report = module.build_signal_factory_status(
        artifacts=replace(foundation, crypto_proxy_observation_loop_path=observation),
        generated_utc="2026-07-02T00:35:00Z",
    )

    assert report["status"] == "signal_factory_crypto_proxy_labels_ready"
    assert report["summary"]["crypto_proxy_observation_label_count"] == 185
    assert report["next_tranche"]["name"] == "kalshi_crypto_proxy_feature_model_falsification"
    assert "FDR-controlled OOS survival" in report["next_tranche"]["stop_condition"]


def test_signal_factory_status_routes_to_observation_when_crypto_model_has_insufficient_labels(
    tmp_path: Path,
) -> None:
    module = load_status_module()
    foundation = write_crypto_signal_foundation(module, tmp_path)
    observation = tmp_path / "observation-loop.json"
    model = tmp_path / "model.json"
    write_json(
        observation,
        safe_artifact(
            status="crypto_proxy_observation_loop_label_rows_ready",
            summary={"total_observation_row_count": 2478, "label_row_count": 18},
        ),
    )
    write_json(
        model,
        safe_artifact(
            status="crypto_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
            summary={
                "raw_label_row_count": 36,
                "independent_contract_label_count": 9,
                "duplicate_label_row_count": 27,
                "research_candidate_count": 0,
            },
        ),
    )

    report = module.build_signal_factory_status(
        artifacts=replace(
            foundation,
            crypto_proxy_observation_loop_path=observation,
            crypto_proxy_model_falsification_path=model,
        ),
        generated_utc="2026-07-02T01:35:00Z",
    )

    assert report["status"] == "signal_factory_crypto_proxy_feature_model_insufficient_labels"
    assert report["summary"]["crypto_proxy_model_independent_label_count"] == 9
    assert report["summary"]["crypto_proxy_model_duplicate_label_row_count"] == 27
    gates = {item["name"]: item for item in report["capabilities"]}
    assert gates["crypto_proxy_feature_model_falsification"]["status"] == "warn"
    assert report["next_tranche"]["name"] == "kalshi_crypto_proxy_observation_accumulation"
    assert "duplicate contract labels" in report["next_tranche"]["stop_condition"]


def test_signal_factory_status_routes_research_candidate_to_replay(tmp_path: Path) -> None:
    module = load_status_module()
    foundation = write_crypto_signal_foundation(module, tmp_path)
    observation = tmp_path / "observation-loop.json"
    model = tmp_path / "model.json"
    write_json(
        observation,
        safe_artifact(
            status="crypto_proxy_observation_loop_label_rows_ready",
            summary={"total_observation_row_count": 6195, "label_row_count": 1191},
        ),
    )
    write_json(
        model,
        safe_artifact(
            status="crypto_proxy_feature_model_falsification_ready_with_research_candidates",
            summary={
                "raw_label_row_count": 2355,
                "independent_contract_label_count": 309,
                "duplicate_label_row_count": 2046,
                "research_candidate_count": 1,
            },
        ),
    )

    report = module.build_signal_factory_status(
        artifacts=replace(
            foundation,
            crypto_proxy_observation_loop_path=observation,
            crypto_proxy_model_falsification_path=model,
        ),
        generated_utc="2026-07-02T02:10:00Z",
    )

    assert report["status"] == "signal_factory_crypto_proxy_feature_model_research_candidates"
    assert report["summary"]["crypto_proxy_model_research_candidate_count"] == 1
    assert report["next_tranche"]["name"] == "kalshi_crypto_proxy_research_candidate_replay"
    assert "cost replay" in report["next_tranche"]["why"]


def test_signal_factory_status_routes_replay_blocker_to_capacity_correlation_decay(
    tmp_path: Path,
) -> None:
    module = load_status_module()
    foundation = write_crypto_signal_foundation(module, tmp_path)
    observation = tmp_path / "observation-loop.json"
    model = tmp_path / "model.json"
    replay = tmp_path / "replay.json"
    write_json(
        observation,
        safe_artifact(
            status="crypto_proxy_observation_loop_label_rows_ready",
            summary={"total_observation_row_count": 6195, "label_row_count": 1191},
        ),
    )
    write_json(
        model,
        safe_artifact(
            status="crypto_proxy_feature_model_falsification_ready_with_research_candidates",
            summary={"independent_contract_label_count": 309, "research_candidate_count": 1},
        ),
    )
    write_json(
        replay,
        safe_artifact(
            status="crypto_proxy_research_candidate_replay_blocked_predeployment_gates",
            summary={
                "replay_row_count": 309,
                "positive_expected_value_row_count": 188,
                "conservative_calibrated_side_probability": 0.51,
                "usable_row_count": 0,
            },
        ),
    )

    report = module.build_signal_factory_status(
        artifacts=replace(
            foundation,
            crypto_proxy_observation_loop_path=observation,
            crypto_proxy_model_falsification_path=model,
            crypto_proxy_research_candidate_replay_path=replay,
        ),
        generated_utc="2026-07-02T02:20:00Z",
    )

    assert report["status"] == "signal_factory_crypto_proxy_replay_blocked_predeployment_gates"
    assert report["summary"]["crypto_proxy_replay_positive_expected_value_row_count"] == 188
    gates = {item["name"]: item for item in report["capabilities"]}
    assert gates["crypto_proxy_research_candidate_replay"]["status"] == "pass"
    assert report["next_tranche"]["name"] == "kalshi_crypto_proxy_capacity_correlation_decay"
    assert "capacity depth" in report["next_tranche"]["why"]


def test_signal_factory_status_consumes_capacity_correlation_decay_gate(tmp_path: Path) -> None:
    module = load_status_module()
    foundation = write_crypto_signal_foundation(module, tmp_path)
    observation = tmp_path / "observation-loop.json"
    model = tmp_path / "model.json"
    replay = tmp_path / "replay.json"
    ccd = tmp_path / "ccd.json"
    write_json(
        observation,
        safe_artifact(
            status="crypto_proxy_observation_loop_label_rows_ready",
            summary={"total_observation_row_count": 6195, "label_row_count": 1191},
        ),
    )
    write_json(
        model,
        safe_artifact(
            status="crypto_proxy_feature_model_falsification_ready_with_research_candidates",
            summary={"independent_contract_label_count": 309, "research_candidate_count": 1},
        ),
    )
    write_json(
        replay,
        safe_artifact(
            status="crypto_proxy_research_candidate_replay_blocked_predeployment_gates",
            summary={"replay_row_count": 309, "positive_expected_value_row_count": 188},
        ),
    )
    write_json(
        ccd,
        safe_artifact(
            status="crypto_proxy_capacity_correlation_decay_blocked_correlation_concentration",
            summary={
                "candidate_row_count": 12,
                "orderbook_count": 12,
                "positive_depth_contracts": 34,
                "largest_correlation_cluster_share": 0.82,
                "capacity_status": "capacity_depth_positive",
                "correlation_status": "correlation_cluster_concentrated_or_missing",
                "decay_status": "decay_survival_pass",
            },
        ),
    )

    report = module.build_signal_factory_status(
        artifacts=replace(
            foundation,
            crypto_proxy_observation_loop_path=observation,
            crypto_proxy_model_falsification_path=model,
            crypto_proxy_research_candidate_replay_path=replay,
            crypto_proxy_capacity_correlation_decay_path=ccd,
        ),
        generated_utc="2026-07-02T02:25:00Z",
    )

    assert report["status"] == "signal_factory_crypto_proxy_correlation_concentration_blocked"
    assert report["summary"]["crypto_proxy_capacity_correlation_decay_status"] == (
        "crypto_proxy_capacity_correlation_decay_blocked_correlation_concentration"
    )
    gates = {item["name"]: item for item in report["capabilities"]}
    assert gates["crypto_proxy_capacity_correlation_decay"]["status"] == "warn"
    assert gates["capacity_model"]["status"] == "pass"
    assert gates["correlation_model"]["status"] == "blocked"
    assert report["next_tranche"]["name"] == "kalshi_crypto_proxy_correlation_cluster_control"


def test_signal_factory_status_consumes_correlation_cluster_control_gate(tmp_path: Path) -> None:
    module = load_status_module()
    foundation = write_crypto_signal_foundation(module, tmp_path)
    observation = tmp_path / "observation-loop.json"
    model = tmp_path / "model.json"
    replay = tmp_path / "replay.json"
    ccd = tmp_path / "ccd.json"
    cluster = tmp_path / "cluster-control.json"
    write_json(
        observation,
        safe_artifact(
            status="crypto_proxy_observation_loop_label_rows_ready",
            summary={"total_observation_row_count": 6195, "label_row_count": 1191},
        ),
    )
    write_json(
        model,
        safe_artifact(
            status="crypto_proxy_feature_model_falsification_ready_with_research_candidates",
            summary={"independent_contract_label_count": 309, "research_candidate_count": 1},
        ),
    )
    write_json(
        replay,
        safe_artifact(
            status="crypto_proxy_research_candidate_replay_blocked_predeployment_gates",
            summary={"replay_row_count": 309, "positive_expected_value_row_count": 188},
        ),
    )
    write_json(
        ccd,
        safe_artifact(
            status="crypto_proxy_capacity_correlation_decay_blocked_correlation_concentration",
            summary={
                "candidate_row_count": 60,
                "orderbook_count": 60,
                "positive_depth_contracts": 492018,
                "largest_correlation_cluster_share": 1.0,
                "capacity_status": "capacity_depth_positive",
                "correlation_status": "correlation_cluster_concentrated_or_missing",
                "decay_status": "decay_survival_pass",
            },
        ),
    )
    write_json(
        cluster,
        safe_artifact(
            status="crypto_proxy_correlation_cluster_control_blocked_insufficient_clusters",
            summary={
                "positive_cluster_count": 1,
                "required_positive_cluster_count": 3,
                "total_controlled_depth_cost": 0,
                "largest_controlled_cluster_share": None,
                "usable_row_count": 0,
            },
        ),
    )

    report = module.build_signal_factory_status(
        artifacts=replace(
            foundation,
            crypto_proxy_observation_loop_path=observation,
            crypto_proxy_model_falsification_path=model,
            crypto_proxy_research_candidate_replay_path=replay,
            crypto_proxy_capacity_correlation_decay_path=ccd,
            crypto_proxy_correlation_cluster_control_path=cluster,
        ),
        generated_utc="2026-07-02T02:30:00Z",
    )

    assert report["status"] == "signal_factory_crypto_proxy_cluster_breadth_blocked"
    assert report["summary"]["crypto_proxy_correlation_cluster_control_status"] == (
        "crypto_proxy_correlation_cluster_control_blocked_insufficient_clusters"
    )
    assert report["summary"]["crypto_proxy_cluster_positive_count"] == 1
    gates = {item["name"]: item for item in report["capabilities"]}
    assert gates["crypto_proxy_correlation_cluster_control"]["status"] == "warn"
    assert gates["correlation_model"]["status"] == "blocked"
    assert report["next_tranche"]["name"] == "kalshi_crypto_proxy_cluster_breadth_accumulation"
    assert "independent correlation clusters" in report["next_tranche"]["why"]


def test_signal_factory_status_routes_cluster_control_upstream_decay_to_decay_tranche(
    tmp_path: Path,
) -> None:
    module = load_status_module()
    foundation = write_crypto_signal_foundation(module, tmp_path)
    observation = tmp_path / "observation-loop.json"
    model = tmp_path / "model.json"
    replay = tmp_path / "replay.json"
    ccd = tmp_path / "ccd.json"
    cluster = tmp_path / "cluster-control.json"
    write_json(
        observation,
        safe_artifact(
            status="crypto_proxy_observation_loop_label_rows_ready",
            summary={"total_observation_row_count": 7443, "label_row_count": 1200},
        ),
    )
    write_json(
        model,
        safe_artifact(
            status="crypto_proxy_feature_model_falsification_ready_with_research_candidates",
            summary={"independent_contract_label_count": 318, "research_candidate_count": 1},
        ),
    )
    write_json(
        replay,
        safe_artifact(
            status="crypto_proxy_research_candidate_replay_blocked_predeployment_gates",
            summary={"replay_row_count": 315, "positive_expected_value_row_count": 159},
        ),
    )
    write_json(
        ccd,
        safe_artifact(
            status="crypto_proxy_capacity_correlation_decay_blocked_correlation_concentration",
            summary={
                "candidate_row_count": 9,
                "candidate_cluster_count": 9,
                "orderbook_count": 9,
                "positive_depth_contracts": 41177.87,
                "largest_correlation_cluster_share": 0.906,
                "capacity_status": "capacity_depth_positive",
                "correlation_status": "correlation_cluster_concentrated_or_missing",
                "decay_status": "decay_survival_blocked",
            },
        ),
    )
    write_json(
        cluster,
        safe_artifact(
            status="crypto_proxy_correlation_cluster_control_blocked_upstream_ccd",
            summary={
                "positive_cluster_count": 3,
                "required_positive_cluster_count": 3,
                "total_controlled_depth_cost": 1409.9663,
                "largest_controlled_cluster_share": 0.35,
                "usable_row_count": 0,
            },
        ),
    )

    report = module.build_signal_factory_status(
        artifacts=replace(
            foundation,
            crypto_proxy_observation_loop_path=observation,
            crypto_proxy_model_falsification_path=model,
            crypto_proxy_research_candidate_replay_path=replay,
            crypto_proxy_capacity_correlation_decay_path=ccd,
            crypto_proxy_correlation_cluster_control_path=cluster,
        ),
        generated_utc="2026-07-02T05:15:00Z",
    )

    assert report["status"] == "signal_factory_crypto_proxy_decay_survival_blocked"
    assert report["next_tranche"]["name"] == "kalshi_crypto_proxy_decay_and_sample_accumulation"
    assert "repeated settled-bucket decay survival" in report["next_tranche"]["why"]


def test_signal_factory_writer_emits_latest_json_and_markdown(tmp_path: Path) -> None:
    module = load_status_module()
    module.MACRO_DIR = tmp_path / "macro"
    report = module.build_signal_factory_status(
        artifacts=module.Artifacts.isolated(tmp_path),
        generated_utc="2026-07-01T23:00:00Z",
    )

    paths = module.write_signal_factory_status(
        report,
        out_dir=tmp_path / "out",
        latest_dir=module.MACRO_DIR,
        write_latest=True,
    )

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["latest_json_path"]).exists()
    assert "Kalshi Signal Factory Status" in Path(paths["markdown_path"]).read_text(
        encoding="utf-8"
    )


def test_signal_factory_writer_skips_latest_for_tmp_out_dir_by_default(tmp_path: Path) -> None:
    module = load_status_module()
    original_macro_dir = module.MACRO_DIR
    report = module.build_signal_factory_status(
        artifacts=module.Artifacts.isolated(tmp_path),
        generated_utc="2026-07-01T23:00:00Z",
    )

    paths = module.write_signal_factory_status(report, out_dir=tmp_path / "out")

    assert Path(paths["json_path"]).exists()
    assert "latest_json_path" not in paths
    assert original_macro_dir == module.MACRO_DIR


def test_makefile_exposes_signal_factory_status_target() -> None:
    content = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-signal-factory-status" in content
    assert "scripts/kalshi_signal_factory_status.py" in content


# ---------------------------------------------------------------------------
# Family-aware orchestration tests (VAL-ORCH-001..006, 022..034)
# ---------------------------------------------------------------------------


def _sports_safe_artifact(**overrides):
    payload = safe_artifact(
        status="sports_proxy_feature_packet_ready", summary={"feature_row_count": 5}
    )
    payload.update(overrides)
    return payload


def test_status_reports_per_family_capabilities_from_registry(tmp_path: Path) -> None:
    """VAL-ORCH-001: capabilities iterate per family from a registry."""
    module = load_status_module()
    foundation = write_crypto_signal_foundation(module, tmp_path)

    report = module.build_signal_factory_status(
        artifacts=foundation,
        generated_utc="2026-07-02T12:00:00Z",
    )

    assert "families" in report
    assert "crypto_proxy" in report["families"]
    assert "sports_baseball" in report["families"]
    crypto_caps = report["families"]["crypto_proxy"]["capabilities"]
    sports_caps = report["families"]["sports_baseball"]["capabilities"]
    assert len(crypto_caps) > 0
    assert len(sports_caps) > 0
    crypto_names = {c["name"] for c in crypto_caps}
    sports_names = {c["name"] for c in sports_caps}
    assert "sports_baseball_feature_packet" in sports_names
    assert crypto_names != sports_names


def test_status_reports_both_crypto_and_sports_simultaneously(tmp_path: Path) -> None:
    """VAL-ORCH-002/VAL-CROSS-003: both crypto_proxy and sports_baseball present."""
    module = load_status_module()
    foundation = write_crypto_signal_foundation(module, tmp_path)
    sports_feature = tmp_path / "sports-feature.json"
    write_json(sports_feature, _sports_safe_artifact())

    report = module.build_signal_factory_status(
        artifacts=replace(foundation, sports_proxy_feature_packet_path=sports_feature),
        generated_utc="2026-07-02T12:00:00Z",
    )

    assert "crypto_proxy" in report["families"]
    assert "sports_baseball" in report["families"]
    assert report["families"]["sports_baseball"]["status"].startswith("signal_factory_sports_")


def test_status_has_multi_family_summary_rollup(tmp_path: Path) -> None:
    """VAL-ORCH-003: summary carries per-family gate counts + overall."""
    module = load_status_module()
    foundation = write_crypto_signal_foundation(module, tmp_path)

    report = module.build_signal_factory_status(
        artifacts=foundation,
        generated_utc="2026-07-02T12:00:00Z",
    )

    assert "families" in report["summary"]
    assert "crypto_proxy" in report["summary"]["families"]
    assert "sports_baseball" in report["summary"]["families"]
    sports_gate_counts = report["summary"]["families"]["sports_baseball"]["capability_gate_counts"]
    assert set(sports_gate_counts.keys()) >= {"pass", "warn", "blocked"}
    assert "capability_gate_counts" in report["summary"]


def test_artifacts_carries_family_keyed_paths_without_breaking_crypto(tmp_path: Path) -> None:
    """VAL-ORCH-004: Artifacts has sports paths; crypto paths unchanged."""
    module = load_status_module()

    # Crypto fields on from_macro_dir are unchanged.
    prod = module.Artifacts.from_macro_dir(tmp_path / "macro")
    assert (
        prod.crypto_proxy_feature_packet_path
        == tmp_path / "macro" / "latest-kalshi-crypto-proxy-feature-packet.json"
    )

    # Sports fields exist and default to missing files under base.
    isolated = module.Artifacts.isolated(tmp_path)
    assert hasattr(isolated, "sports_proxy_feature_packet_path")
    assert hasattr(isolated, "sports_proxy_observation_loop_path")
    assert hasattr(isolated, "ghost_listing_depth_diagnostic_path")
    assert hasattr(isolated, "sports_stack_sequencing_path")
    assert str(isolated.sports_proxy_feature_packet_path).startswith(str(tmp_path))
    assert "missing" in isolated.sports_proxy_feature_packet_path.name
    assert "missing" in isolated.sports_proxy_observation_loop_path.name
    assert "missing" in isolated.ghost_listing_depth_diagnostic_path.name
    assert "missing" in isolated.sports_stack_sequencing_path.name

    # replace still works for every existing crypto field.
    replaced = replace(isolated, crypto_proxy_feature_packet_path=tmp_path / "feat.json")
    assert replaced.crypto_proxy_feature_packet_path == tmp_path / "feat.json"


def test_top_level_status_is_sports_led_when_sports_advanced(tmp_path: Path) -> None:
    """VAL-ORCH-005: sports-led input -> sports status, with status_selection note."""
    module = load_status_module()
    # Crypto foundation present but at an early stage; sports feature packet ready.
    foundation = write_crypto_signal_foundation(module, tmp_path)
    sports_feature = tmp_path / "sports-feature.json"
    write_json(sports_feature, _sports_safe_artifact())

    report = module.build_signal_factory_status(
        artifacts=replace(foundation, sports_proxy_feature_packet_path=sports_feature),
        generated_utc="2026-07-02T12:00:00Z",
    )

    # Crypto is at feature_packet_ready (rank 9); sports is also feature_packet_ready (rank 9).
    # With a tie, crypto should win. But let's make sports strictly more advanced:
    # give sports labels ready while crypto is only at feature_packet_ready.
    sports_obs = tmp_path / "sports-obs.json"
    write_json(
        sports_obs,
        safe_artifact(
            status="sports_proxy_observation_loop_label_rows_ready",
            summary={"total_observation_row_count": 30, "label_row_count": 30},
        ),
    )

    report = module.build_signal_factory_status(
        artifacts=replace(
            foundation,
            sports_proxy_feature_packet_path=sports_feature,
            sports_proxy_observation_loop_path=sports_obs,
        ),
        generated_utc="2026-07-02T12:00:00Z",
    )

    assert report["status"].startswith("signal_factory_sports_")
    assert "status_selection" in report
    assert "sports_baseball" in report["status_selection"].get("selected_family", "")


def test_sports_stack_sequencing_leads_when_current_depth_passes(tmp_path: Path) -> None:
    module = load_status_module()
    foundation = write_crypto_signal_foundation(module, tmp_path)
    ghost_depth = tmp_path / "ghost-depth.json"
    sports_stack = tmp_path / "sports-stack.json"
    write_json(
        ghost_depth,
        safe_artifact(
            status="ghost_listing_depth_diagnostic_current_depth_ready",
            summary={
                "selected_candidate_count": 120,
                "orderbook_count": 120,
                "positive_depth_fraction": 1.0,
                "cap_i_lock_allowed": True,
            },
        ),
    )
    write_json(
        sports_stack,
        safe_artifact(
            status="sports_stack_sequencing_ready_current_depth_passed",
            summary={
                "near_term_active_candidate_count": 3109,
                "recommended_order": ["world_cup_soccer", "mlb", "atp", "nfl", "nba"],
                "top_surface": "world_cup_soccer",
                "cap_i_lock_allowed": True,
                "cap_i_lock_state": "current_depth_passed",
            },
        ),
    )

    report = module.build_signal_factory_status(
        artifacts=replace(
            foundation,
            ghost_listing_depth_diagnostic_path=ghost_depth,
            sports_stack_sequencing_path=sports_stack,
        ),
        generated_utc="2026-07-03T21:45:00Z",
    )

    assert report["status"] == "signal_factory_sports_stack_sequencing_ready_current_depth_passed"
    assert report["status_selection"]["selected_family"] == "sports_baseball"
    assert report["next_tranche"]["name"] == "kalshi_world_cup_mlb_atp_evidence_loop"
    assert report["summary"]["sports_stack_top_surface"] == "world_cup_soccer"
    assert report["summary"]["sports_stack_recommended_order"][:3] == [
        "world_cup_soccer",
        "mlb",
        "atp",
    ]
    assert report["summary"]["ghost_listing_depth_cap_i_lock_allowed"] is True


def test_weather_observations_waiting_settlement_status_leads_feature_packet(
    tmp_path: Path,
) -> None:
    module = load_status_module()
    foundation = write_crypto_signal_foundation(module, tmp_path)
    weather_feature = tmp_path / "weather-feature.json"
    weather_observation = tmp_path / "weather-observation.json"
    write_json(
        weather_feature,
        safe_artifact(
            status="weather_proxy_feature_packet_ready",
            summary={"feature_row_count": 480, "feature_ready_count": 480},
        ),
    )
    write_json(
        weather_observation,
        safe_artifact(
            status="weather_proxy_observation_loop_partial_observations_no_labels",
            summary={
                "new_observation_row_count": 480,
                "existing_observation_row_count": 312,
                "new_label_row_count": 0,
                "blocked_label_row_count": 72,
            },
        ),
    )

    report = module.build_signal_factory_status(
        artifacts=replace(
            foundation,
            weather_proxy_feature_packet_path=weather_feature,
            weather_proxy_observation_loop_path=weather_observation,
        ),
        generated_utc="2026-07-03T21:45:00Z",
    )

    assert (
        report["families"]["weather_proxy"]["status"]
        == "signal_factory_weather_proxy_observations_waiting_settlement"
    )
    assert report["status"] == "signal_factory_weather_proxy_observations_waiting_settlement"


def test_per_family_status_strings_exposed_even_when_crypto_leads(tmp_path: Path) -> None:
    """VAL-ORCH-006: blocked sports status visible even when crypto leads."""
    module = load_status_module()
    foundation = write_crypto_signal_foundation(module, tmp_path)

    report = module.build_signal_factory_status(
        artifacts=foundation,
        generated_utc="2026-07-02T12:00:00Z",
    )

    # Sports artifacts are missing -> sports is blocked.
    sports_status = report["summary"]["families"]["sports_baseball"]["status"]
    assert sports_status.startswith("signal_factory_sports_")
    assert "blocked" in sports_status or "missing" in sports_status
    # Crypto is leading (feature_packet_ready).
    assert report["status"] == "signal_factory_crypto_proxy_feature_packet_ready"


def test_crypto_characterization_unchanged_for_crypto_only_inputs(tmp_path: Path) -> None:
    """VAL-ORCH-022/023: crypto status string unchanged when only crypto present."""
    module = load_status_module()
    foundation = write_crypto_signal_foundation(module, tmp_path)

    report = module.build_signal_factory_status(
        artifacts=foundation,
        generated_utc="2026-07-02T12:00:00Z",
    )

    assert report["status"] == "signal_factory_crypto_proxy_feature_packet_ready"
    assert not report["status"].startswith("signal_factory_sports_")
    # Crypto capability gate states preserved.
    gates = {item["name"]: item for item in report["capabilities"]}
    assert gates["crypto_proxy_feature_packet"]["status"] == "pass"
    assert gates["kalshi_universe_inventory"]["status"] == "pass"


def test_status_research_only_safety_holds_for_multi_family(tmp_path: Path) -> None:
    """VAL-ORCH-026: research_only=true, execution disabled for multi-family report."""
    module = load_status_module()
    foundation = write_crypto_signal_foundation(module, tmp_path)
    sports_feature = tmp_path / "sports-feature.json"
    write_json(sports_feature, _sports_safe_artifact())

    report = module.build_signal_factory_status(
        artifacts=replace(foundation, sports_proxy_feature_packet_path=sports_feature),
        generated_utc="2026-07-02T12:00:00Z",
    )

    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["safety"]["market_execution"] is False
    assert report["safety"]["account_or_order_paths"] is False
    assert report["safety"]["database_writes"] is False
    assert report["safety"]["raw_payloads_copied_to_repo"] is False
    assert report["safety"]["staking_or_sizing_guidance"] is False


def test_sports_all_blocked_does_not_crash_or_corrupt_crypto(tmp_path: Path) -> None:
    """VAL-ORCH-030: missing sports artifacts -> sports blocked, crypto unaffected."""
    module = load_status_module()
    foundation = write_crypto_signal_foundation(module, tmp_path)

    report = module.build_signal_factory_status(
        artifacts=foundation,
        generated_utc="2026-07-02T12:00:00Z",
    )

    sports_status = report["summary"]["families"]["sports_baseball"]["status"]
    assert "blocked" in sports_status or "missing" in sports_status
    # Crypto is unaffected.
    assert report["status"] == "signal_factory_crypto_proxy_feature_packet_ready"
    crypto_gate_counts = report["summary"]["families"]["crypto_proxy"]["capability_gate_counts"]
    assert crypto_gate_counts["pass"] >= 1


def test_hermeticity_holds_for_family_keyed_artifacts_bundle(tmp_path: Path) -> None:
    """VAL-ORCH-032: isolated bundle resolves ALL family paths under tmp_path."""
    module = load_status_module()
    report = module.build_signal_factory_status(
        artifacts=module.Artifacts.isolated(tmp_path),
        generated_utc="2026-07-02T12:00:00Z",
    )

    assert report["status"] == "signal_factory_blocked_missing_universe_inventory"
    assert report["next_tranche"]["name"] != "kalshi_crypto_proxy_capacity_correlation_decay"
    # Every input path resolves under tmp_path.
    for path_val in report["inputs"].values():
        assert str(tmp_path) in str(path_val)
    # Sports is blocked but present.
    assert "sports_baseball" in report["families"]


# ═══════════════════════════════════════════════════════════════════════════
# VAL-SIGNAL-012: Both new families registered in the signal factory registry
# ═══════════════════════════════════════════════════════════════════════════


class TestNewFamiliesRegistered:
    """Both new families are enumerated in the signal factory registry."""

    def test_favorite_longshot_bias_registered(self) -> None:
        """VAL-SIGNAL-012: Favorite-longshot bias is registered in the family registry."""
        import scripts.kalshi_signal_factory_families as families_mod

        assert hasattr(families_mod, "FAVORITE_LONGSHOT_FAMILY_ID")
        assert families_mod.FAVORITE_LONGSHOT_FAMILY_ID == "favorite_longshot_bias"
        assert hasattr(families_mod, "FAVORITE_LONGSHOT_CAPABILITY_NAMES")
        assert len(families_mod.FAVORITE_LONGSHOT_CAPABILITY_NAMES) > 0
        assert hasattr(families_mod, "build_favorite_longshot_capabilities")
        assert callable(families_mod.build_favorite_longshot_capabilities)
        assert hasattr(families_mod, "compute_favorite_longshot_status")
        assert callable(families_mod.compute_favorite_longshot_status)

    def test_passive_liquidity_provision_registered(self) -> None:
        """VAL-SIGNAL-012: Passive liquidity provision is registered in the family registry."""
        import scripts.kalshi_signal_factory_families as families_mod

        assert hasattr(families_mod, "PASSIVE_LIQUIDITY_FAMILY_ID")
        assert families_mod.PASSIVE_LIQUIDITY_FAMILY_ID == "passive_liquidity_provision"
        assert hasattr(families_mod, "PASSIVE_LIQUIDITY_CAPABILITY_NAMES")
        assert len(families_mod.PASSIVE_LIQUIDITY_CAPABILITY_NAMES) > 0
        assert hasattr(families_mod, "build_passive_liquidity_capabilities")
        assert callable(families_mod.build_passive_liquidity_capabilities)
        assert hasattr(families_mod, "compute_passive_liquidity_status")
        assert callable(families_mod.compute_passive_liquidity_status)

    def test_status_module_includes_new_families(self) -> None:
        """VAL-SIGNAL-012: Status report families dict includes both new families."""
        import scripts.kalshi_signal_factory_families as families_mod

        # Verify the status module maps family IDs
        assert hasattr(families_mod, "FAVORITE_LONGSHOT_FAMILY_ID")
        assert hasattr(families_mod, "PASSIVE_LIQUIDITY_FAMILY_ID")

        # Build capabilities for both families to verify they work
        fav_caps = families_mod.build_favorite_longshot_capabilities()
        assert len(fav_caps) > 0

        pl_caps = families_mod.build_passive_liquidity_capabilities()
        assert len(pl_caps) > 0

    def test_select_leading_family_includes_new_families(self) -> None:
        """VAL-SIGNAL-012: select_leading_family includes both new families."""
        import scripts.kalshi_signal_factory_families as families_mod

        assert hasattr(families_mod, "select_leading_family")

        # Test that the function accepts new family status params
        leading_id, leading_status, leading_class = families_mod.select_leading_family(
            crypto_status="signal_factory_crypto_proxy_labels_ready",
            sports_status="signal_factory_sports_baseball_labels_ready",
            weather_status="signal_factory_weather_proxy_blocked_missing_feature_packet",
            favorite_longshot_status="signal_factory_favorite_longshot_bias_blocked_missing_feature_packet",
            passive_liquidity_status="signal_factory_passive_liquidity_provision_blocked_missing_feature_packet",
        )
        assert leading_id is not None
        assert leading_status is not None
        assert leading_class is not None
