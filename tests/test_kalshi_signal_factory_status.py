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
            summary={"candidate_count": 100, "model_route_candidate_count": 2, "soft_watch_candidate_count": 98}
        ),
    )
    write_json(ledger, safe_artifact(summary={"row_count": 4}))
    write_json(queue, safe_artifact(summary={"queued_row_count": 0}))
    write_json(robustness, safe_artifact(summary={"repeat_positive_row_count": 0}))
    write_json(registry, safe_artifact(summary={"hypothesis_count": 6, "multiple_testing_family_count": 6}))
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
            summary={"feature_row_count": 1210, "feature_ready_count": 1210, "proxy_available_asset_count": 9},
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
            summary={"candidate_count": 10, "model_route_candidate_count": 2, "soft_watch_candidate_count": 8}
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
    assert report["summary"]["falsification_status"] == "falsification_gate_blocked_missing_labeled_oos_evidence"
    gates = {item["name"]: item for item in report["capabilities"]}
    assert gates["agentic_hypothesis_registry"]["status"] == "pass"
    assert gates["fdr_controlled_falsification_gate"]["status"] == "blocked"
    assert report["next_tranche"]["name"] == "kalshi_labeled_oos_backtest_harness"
    assert "OOS cost-aware FDR evidence" in report["next_tranche"]["stop_condition"]


def test_signal_factory_status_routes_to_label_packet_builder_when_oos_harness_exists(tmp_path: Path) -> None:
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
            summary={"candidate_count": 10, "model_route_candidate_count": 2, "soft_watch_candidate_count": 8}
        ),
    )
    write_json(ledger, safe_artifact(summary={"row_count": 4}))
    write_json(queue, safe_artifact(summary={"queued_row_count": 0}))
    write_json(robustness, safe_artifact(summary={"repeat_positive_row_count": 0}))
    write_json(registry, safe_artifact(summary={"hypothesis_count": 6, "multiple_testing_family_count": 6}))
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

    assert report["status"] == "signal_factory_oos_backtest_harness_ready_labeled_observations_missing"
    gates = {item["name"]: item for item in report["capabilities"]}
    assert gates["labeled_oos_backtest_harness"]["status"] == "pass"
    assert (
        report["summary"]["labeled_oos_backtest_status"] == "labeled_oos_backtest_blocked_missing_labeled_observations"
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
            summary={"candidate_count": 10, "model_route_candidate_count": 2, "soft_watch_candidate_count": 8}
        ),
    )
    write_json(ledger, safe_artifact(summary={"row_count": 4}))
    write_json(queue, safe_artifact(summary={"queued_row_count": 0}))
    write_json(robustness, safe_artifact(summary={"repeat_positive_row_count": 0}))
    write_json(registry, safe_artifact(summary={"hypothesis_count": 6, "multiple_testing_family_count": 6}))
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
    assert report["next_tranche"]["name"] == "kalshi_probability_breadth_while_oos_observations_settle"


def test_signal_factory_status_advances_to_crypto_feature_packets_when_breadth_scout_ready(tmp_path: Path) -> None:
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
            summary={"candidate_count": 100, "model_route_candidate_count": 2, "soft_watch_candidate_count": 98}
        ),
    )
    write_json(ledger, safe_artifact(summary={"row_count": 4}))
    write_json(queue, safe_artifact(summary={"queued_row_count": 0}))
    write_json(robustness, safe_artifact(summary={"repeat_positive_row_count": 0}))
    write_json(registry, safe_artifact(summary={"hypothesis_count": 6, "multiple_testing_family_count": 6}))
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


def test_signal_factory_status_advances_to_crypto_observation_loop_when_feature_packet_ready(tmp_path: Path) -> None:
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
            summary={"candidate_count": 100, "model_route_candidate_count": 2, "soft_watch_candidate_count": 98}
        ),
    )
    write_json(ledger, safe_artifact(summary={"row_count": 4}))
    write_json(queue, safe_artifact(summary={"queued_row_count": 0}))
    write_json(robustness, safe_artifact(summary={"repeat_positive_row_count": 0}))
    write_json(registry, safe_artifact(summary={"hypothesis_count": 6, "multiple_testing_family_count": 6}))
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


def test_signal_factory_status_routes_replay_blocker_to_capacity_correlation_decay(tmp_path: Path) -> None:
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


def test_signal_factory_status_routes_cluster_control_upstream_decay_to_decay_tranche(tmp_path: Path) -> None:
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
    assert "Kalshi Signal Factory Status" in Path(paths["markdown_path"]).read_text(encoding="utf-8")


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
