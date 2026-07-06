from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_near_resolution_flow_replay_gates.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_near_resolution_flow_replay_gates", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def safe_envelope(status: str, **extra):
    return {
        "schema_version": 1,
        "status": status,
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
        **extra,
    }


def evidence_payload(status: str = "research_candidate_fdr_passed") -> dict[str, object]:
    return safe_envelope(
        "near_resolution_informed_flow_research_candidates_ready",
        evaluations=[
            {
                "model_id": "flow_depth_imbalance_settlement_directional",
                "status": status,
                "oos_label_count": 33,
                "oos_correct_count": 30,
                "oos_accuracy": 30 / 33,
                "p_value": 0.000001,
                "q_value": 0.000001,
            }
        ],
        flow_rows=[],
    )


def micro_row(
    ticker: str,
    *,
    observed_at: str,
    close_time: str,
    event_ticker: str,
    side: str,
    outcome: int | None,
    surface: str = "mlb",
) -> dict[str, object]:
    yes_signal = side == "yes"
    return {
        "snapshot_id": f"{ticker}-{observed_at}",
        "contract_ticker": ticker,
        "event_ticker": event_ticker,
        "series_ticker": ticker.split("-")[0],
        "sport_surface": surface,
        "observed_at_utc": observed_at,
        "settlement_time": close_time,
        "time_to_settlement_seconds": 1800,
        "best_yes_bid": 0.38 if yes_signal else 0.82,
        "best_yes_ask": 0.4 if yes_signal else 0.84,
        "best_no_bid": 0.58 if yes_signal else 0.14,
        "best_no_ask": 0.6 if yes_signal else 0.16,
        "yes_ask_depth_top1": 5.0,
        "yes_bid_depth_top1": 5.0,
        "no_ask_depth_top1": 5.0,
        "no_bid_depth_top1": 5.0,
        "depth_imbalance_yes": 0.8 if yes_signal else -0.8,
        "depth_imbalance_delta": None,
        "settlement_yes_outcome": outcome,
        "usable": False,
        "research_only": True,
        "execution_enabled": False,
    }


def micro_payload(rows: list[dict[str, object]]) -> dict[str, object]:
    return safe_envelope(
        "sports_microstructure_observation_loop_ready_with_settlement_labels",
        observation_packet={"rows": rows},
        summary={"observation_row_count": len(rows)},
    )


def test_near_resolution_flow_replay_gates_can_clear_downstream_gates(
    tmp_path: Path,
) -> None:
    module = load_module()
    rows: list[dict[str, object]] = []
    for index in range(120):
        day = 1 + index // 40
        side = "yes" if index % 2 == 0 else "no"
        ticker = f"KXFLOW-26JUL0{day}-GAME{index:03d}-{side.upper()}"
        rows.append(
            micro_row(
                ticker,
                observed_at=f"2026-07-0{day}T00:{index % 40:02d}:00Z",
                close_time=f"2026-07-0{day}T01:{index % 40:02d}:00Z",
                event_ticker=f"KXFLOW-26JUL0{day}-GAME{index:03d}",
                side=side,
                outcome=1 if side == "yes" else 0,
            )
        )
    rows.extend(
        [
            micro_row(
                "KXFLOW-26JUL04-CURRENTA-YES",
                observed_at="2026-07-04T00:00:00Z",
                close_time="2026-07-04T01:00:00Z",
                event_ticker="KXFLOW-26JUL04-CURRENTA",
                side="yes",
                outcome=None,
            ),
            micro_row(
                "KXFLOW-26JUL04-CURRENTB-NO",
                observed_at="2026-07-04T00:00:00Z",
                close_time="2026-07-04T01:00:00Z",
                event_ticker="KXFLOW-26JUL04-CURRENTB",
                side="no",
                outcome=None,
            ),
        ]
    )
    evidence_path = write_json(tmp_path / "evidence.json", evidence_payload())
    micro_path = write_json(tmp_path / "micro.json", micro_payload(rows))

    report = module.build_near_resolution_flow_replay_gates(
        evidence_path=evidence_path,
        microstructure_path=micro_path,
        generated_utc="2026-07-04T00:05:00Z",
        max_cluster_share=1.0,
        max_observation_age_seconds=600,
    )

    assert report["status"] == "near_resolution_flow_replay_gates_ready_for_ev_ledger_promotion"
    assert report["summary"]["replay_row_count"] == 120
    assert report["summary"]["positive_expected_value_row_count"] == 120
    assert report["summary"]["current_candidate_row_count"] == 2
    assert report["summary"]["positive_depth_contracts"] > 0
    assert report["summary"]["decay_status"] == "recent_bucket_not_worse_than_random"
    assert report["summary"]["usable_row_count"] == 0
    assert len(report["paper_decision_blocker_rows"]) == 2
    assert all(row["usable"] is False for row in report["paper_decision_blocker_rows"])


def test_near_resolution_flow_replay_gates_block_missing_candidate(tmp_path: Path) -> None:
    module = load_module()
    evidence_path = write_json(
        tmp_path / "evidence.json", evidence_payload(status="blocked_insufficient_oos_labels")
    )
    micro_path = write_json(tmp_path / "micro.json", micro_payload([]))

    report = module.build_near_resolution_flow_replay_gates(
        evidence_path=evidence_path,
        microstructure_path=micro_path,
        generated_utc="2026-07-04T00:00:00Z",
    )

    assert (
        report["status"] == "near_resolution_flow_replay_gates_blocked_missing_research_candidate"
    )
    assert report["summary"]["candidate_research_model_present"] is False


def test_near_resolution_flow_replay_makefile_target_exists() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-near-resolution-flow-replay-gates" in text
    assert "scripts/kalshi_near_resolution_flow_replay_gates.py" in text


# ── VAL-FDR-002 / VAL-FDR-007: All minimum required semantic gates present ──


def test_all_minimum_required_semantic_gates_present(tmp_path: Path) -> None:
    """VAL-FDR-002 / VAL-FDR-007: All 10 required gates present with no skip-like reasons."""
    module = load_module()
    rows: list[dict[str, object]] = []
    for index in range(120):
        day = 1 + index // 40
        side = "yes" if index % 2 == 0 else "no"
        ticker = f"KXFLOW-26JUL0{day}-GAME{index:03d}-{side.upper()}"
        rows.append(
            micro_row(
                ticker,
                observed_at=f"2026-07-0{day}T00:{index % 40:02d}:00Z",
                close_time=f"2026-07-0{day}T01:{index % 40:02d}:00Z",
                event_ticker=f"KXFLOW-26JUL0{day}-GAME{index:03d}",
                side=side,
                outcome=1 if side == "yes" else 0,
            )
        )
    rows.extend(
        [
            micro_row(
                "KXFLOW-26JUL04-CURRENTA-YES",
                observed_at="2026-07-04T00:00:00Z",
                close_time="2026-07-04T01:00:00Z",
                event_ticker="KXFLOW-26JUL04-CURRENTA",
                side="yes",
                outcome=None,
            ),
            micro_row(
                "KXFLOW-26JUL04-CURRENTB-NO",
                observed_at="2026-07-04T00:00:00Z",
                close_time="2026-07-04T01:00:00Z",
                event_ticker="KXFLOW-26JUL04-CURRENTB",
                side="no",
                outcome=None,
            ),
        ]
    )
    evidence_path = write_json(tmp_path / "evidence.json", evidence_payload())
    micro_path = write_json(tmp_path / "micro.json", micro_payload(rows))

    report = module.build_near_resolution_flow_replay_gates(
        evidence_path=evidence_path,
        microstructure_path=micro_path,
        generated_utc="2026-07-04T00:05:00Z",
        max_cluster_share=1.0,
        max_observation_age_seconds=600,
    )

    gates = report["gates"]
    # VAL-FDR-007: Exactly 10 gates
    assert len(gates) == 10, f"Expected 10 gates, got {len(gates)}"

    # VAL-FDR-002: All minimum required gates present
    required = [
        "evidence_artifact_safe",
        "research_candidate_present",
        "conservative_probability_ready",
        "historical_all_in_cost_replay",
        "positive_cost_adjusted_replay_rows",
        "current_candidates_present",
        "positive_capacity_depth",
        "correlation_cluster_limit",
        "decay_survival",
        "no_usable_sizing_or_execution",
    ]
    gate_names = [g["name"] for g in gates]
    for name in required:
        assert name in gate_names, f"Required gate '{name}' missing"

    # VAL-FDR-007: No blocked gate has "not applicable", "skipped", or "n/a" as reason
    for g in gates:
        reason = str(g.get("reason", "")).lower()
        assert "not applicable" not in reason, f"Gate '{g['name']}' has 'not applicable' in reason"
        assert "skipped" not in reason, f"Gate '{g['name']}' has 'skipped' in reason"
        assert reason.strip() != "n/a", f"Gate '{g['name']}' has reason 'n/a'"

    # Every gate has name, status, and non-empty reason (VAL-FDR-006)
    for g in gates:
        assert g.get("name"), "Gate missing name"
        assert g.get("status") in {"pass", "blocked", "fail", "warn"}, (
            f"Gate '{g['name']}' has invalid status"
        )
        assert g.get("reason") and len(str(g["reason"]).strip()) > 0, (
            f"Gate '{g['name']}' has empty reason"
        )


# ── VAL-FDR-003 / VAL-FDR-004: Decay bucket counts machine-readable ──


def test_decay_bucket_fields_machine_readable(tmp_path: Path) -> None:
    """VAL-FDR-003 / VAL-FDR-004: Decay bucket counts, accuracy, and survival are machine-readable."""
    module = load_module()
    rows: list[dict[str, object]] = []
    for index in range(120):
        day = 1 + index // 40
        side = "yes" if index % 2 == 0 else "no"
        ticker = f"KXFLOW-26JUL0{day}-GAME{index:03d}-{side.upper()}"
        rows.append(
            micro_row(
                ticker,
                observed_at=f"2026-07-0{day}T00:{index % 40:02d}:00Z",
                close_time=f"2026-07-0{day}T01:{index % 40:02d}:00Z",
                event_ticker=f"KXFLOW-26JUL0{day}-GAME{index:03d}",
                side=side,
                outcome=1 if side == "yes" else 0,
            )
        )
    rows.extend(
        [
            micro_row(
                "KXFLOW-26JUL04-CURRENTA-YES",
                observed_at="2026-07-04T00:00:00Z",
                close_time="2026-07-04T01:00:00Z",
                event_ticker="KXFLOW-26JUL04-CURRENTA",
                side="yes",
                outcome=None,
            ),
            micro_row(
                "KXFLOW-26JUL04-CURRENTB-NO",
                observed_at="2026-07-04T00:00:00Z",
                close_time="2026-07-04T01:00:00Z",
                event_ticker="KXFLOW-26JUL04-CURRENTB",
                side="no",
                outcome=None,
            ),
        ]
    )
    evidence_path = write_json(tmp_path / "evidence.json", evidence_payload())
    micro_path = write_json(tmp_path / "micro.json", micro_payload(rows))

    report = module.build_near_resolution_flow_replay_gates(
        evidence_path=evidence_path,
        microstructure_path=micro_path,
        generated_utc="2026-07-04T00:05:00Z",
        max_cluster_share=1.0,
        max_observation_age_seconds=600,
    )

    summary = report["summary"]

    # VAL-FDR-003: Decay bucket count is an int
    assert isinstance(summary["decay_bucket_count"], int), "decay_bucket_count should be int"

    # decay_buckets is an array
    assert isinstance(summary["decay_buckets"], list), "decay_buckets should be list"

    # min_decay_buckets is an int
    assert isinstance(summary["min_decay_buckets"], int), "min_decay_buckets should be int"

    # Each bucket has bucket, label_count, correct_count, accuracy, pass_threshold
    for bucket in summary["decay_buckets"]:
        assert "bucket" in bucket, "Bucket missing 'bucket' key"
        assert isinstance(bucket["label_count"], int), (
            f"Bucket '{bucket['bucket']}' label_count not int"
        )
        assert isinstance(bucket["correct_count"], int), (
            f"Bucket '{bucket['bucket']}' correct_count not int"
        )
        assert bucket["accuracy"] is None or isinstance(bucket["accuracy"], float), (
            f"Bucket '{bucket['bucket']}' accuracy not float or None"
        )
        assert isinstance(bucket["pass_threshold"], bool), (
            f"Bucket '{bucket['bucket']}' pass_threshold not bool"
        )

    # VAL-FDR-004: Decay survival status explicitly reported
    assert "decay_status" in summary, "Missing decay_status in summary"
    assert "passing_bucket_count" in summary, "Missing passing_bucket_count"
    assert isinstance(summary["passing_bucket_count"], int), "passing_bucket_count should be int"
    assert "total_decay_labels" in summary, "Missing total_decay_labels"
    assert isinstance(summary["total_decay_labels"], int), "total_decay_labels should be int"
    assert "recent_bucket_accuracy" in summary, "Missing recent_bucket_accuracy"
    assert "recent_bucket_label_count" in summary, "Missing recent_bucket_label_count"
    assert isinstance(summary["recent_bucket_label_count"], int), (
        "recent_bucket_label_count should be int"
    )

    # Decay survival gate has specific sub-condition in reason
    decay_gate = None
    for g in report["gates"]:
        if g["name"] == "decay_survival":
            decay_gate = g
            break
    assert decay_gate is not None, "decay_survival gate missing"
    reason = str(decay_gate.get("reason", "")).lower()
    # Reason should mention bucket count, label count, or accuracy
    has_sub_condition = any(term in reason for term in ["bucket", "label", "accuracy"])
    assert has_sub_condition, f"decay_survival reason lacks sub-condition: {reason}"


# ── VAL-FDR-005: Current candidates refreshed from fresh snapshots ──


def test_current_candidates_age_within_limit(tmp_path: Path) -> None:
    """VAL-FDR-005: Each current candidate has age <= max_observation_age_seconds."""
    module = load_module()
    rows: list[dict[str, object]] = []
    for index in range(120):
        day = 1 + index // 40
        side = "yes" if index % 2 == 0 else "no"
        ticker = f"KXFLOW-26JUL0{day}-GAME{index:03d}-{side.upper()}"
        rows.append(
            micro_row(
                ticker,
                observed_at=f"2026-07-0{day}T00:{index % 40:02d}:00Z",
                close_time=f"2026-07-0{day}T01:{index % 40:02d}:00Z",
                event_ticker=f"KXFLOW-26JUL0{day}-GAME{index:03d}",
                side=side,
                outcome=1 if side == "yes" else 0,
            )
        )
    rows.extend(
        [
            micro_row(
                "KXFLOW-26JUL04-CURRENTA-YES",
                observed_at="2026-07-04T00:00:00Z",
                close_time="2026-07-04T01:00:00Z",
                event_ticker="KXFLOW-26JUL04-CURRENTA",
                side="yes",
                outcome=None,
            ),
            micro_row(
                "KXFLOW-26JUL04-CURRENTB-NO",
                observed_at="2026-07-04T00:00:00Z",
                close_time="2026-07-04T01:00:00Z",
                event_ticker="KXFLOW-26JUL04-CURRENTB",
                side="no",
                outcome=None,
            ),
        ]
    )
    evidence_path = write_json(tmp_path / "evidence.json", evidence_payload())
    micro_path = write_json(tmp_path / "micro.json", micro_payload(rows))

    max_age = 600.0  # 10 minutes
    report = module.build_near_resolution_flow_replay_gates(
        evidence_path=evidence_path,
        microstructure_path=micro_path,
        generated_utc="2026-07-04T00:05:00Z",
        max_cluster_share=1.0,
        max_observation_age_seconds=max_age,
    )

    # current_candidates_present gate should pass
    for g in report["gates"]:
        if g["name"] == "current_candidates_present":
            assert g["status"] == "pass", f"current_candidates_present gate: {g['reason']}"

    # Each capacity row has current_observation_age_seconds <= max_observation_age_seconds
    for row in report.get("capacity_rows", []):
        age = row.get("current_observation_age_seconds")
        if age is not None:
            assert float(age) <= max_age + 1e-6, (
                f"Row {row.get('contract_ticker')}: age {age} > max {max_age}"
            )


# ── VAL-FDR-006: Each blocked gate has specific, non-generic reason ──


def test_blocked_gates_have_specific_reasons(tmp_path: Path) -> None:
    """VAL-FDR-006: Every blocked gate has a non-empty, specific reason."""
    module = load_module()
    # Create evidence with no candidate and empty micro to force all gates blocked
    evidence_path = write_json(
        tmp_path / "evidence.json",
        safe_envelope("blocked_insufficient_oos_labels", evaluations=[], flow_rows=[]),
    )
    micro_path = write_json(tmp_path / "micro.json", micro_payload([]))

    report = module.build_near_resolution_flow_replay_gates(
        evidence_path=evidence_path,
        microstructure_path=micro_path,
        generated_utc="2026-07-04T00:00:00Z",
    )

    for g in report["gates"]:
        reason = str(g.get("reason", "")).strip()
        if g["status"] in {"blocked", "fail"}:
            assert reason, f"Gate '{g['name']}' is blocked but has empty reason"
            assert len(reason) > 10, f"Gate '{g['name']}' has unreasonably short reason: '{reason}'"


# ── VAL-FDR-008: FDR survivor metadata preserved through replay, cross-checked dynamically ──


def test_candidate_metadata_matches_evidence_dynamically(tmp_path: Path) -> None:
    """VAL-FDR-008: FDR survivor metadata in replay matches evidence gate within tolerance."""
    module = load_module()
    rows: list[dict[str, object]] = []
    for index in range(120):
        day = 1 + index // 40
        side = "yes" if index % 2 == 0 else "no"
        ticker = f"KXFLOW-26JUL0{day}-GAME{index:03d}-{side.upper()}"
        rows.append(
            micro_row(
                ticker,
                observed_at=f"2026-07-0{day}T00:{index % 40:02d}:00Z",
                close_time=f"2026-07-0{day}T01:{index % 40:02d}:00Z",
                event_ticker=f"KXFLOW-26JUL0{day}-GAME{index:03d}",
                side=side,
                outcome=1 if side == "yes" else 0,
            )
        )
    rows.extend(
        [
            micro_row(
                "KXFLOW-26JUL04-CURRENTA-YES",
                observed_at="2026-07-04T00:00:00Z",
                close_time="2026-07-04T01:00:00Z",
                event_ticker="KXFLOW-26JUL04-CURRENTA",
                side="yes",
                outcome=None,
            ),
            micro_row(
                "KXFLOW-26JUL04-CURRENTB-NO",
                observed_at="2026-07-04T00:00:00Z",
                close_time="2026-07-04T01:00:00Z",
                event_ticker="KXFLOW-26JUL04-CURRENTB",
                side="no",
                outcome=None,
            ),
        ]
    )

    # Create evidence with specific OOS values that satisfy minimum thresholds
    eval_row = {
        "model_id": "flow_depth_imbalance_settlement_directional",
        "status": "research_candidate_fdr_passed",
        "oos_label_count": 33,
        "oos_correct_count": 30,
        "oos_accuracy": 30 / 33,
        "p_value": 7.006e-7,
        "q_value": 7.006e-7,
    }
    evidence_path = write_json(
        tmp_path / "evidence.json",
        safe_envelope(
            "near_resolution_informed_flow_research_candidates_ready",
            evaluations=[eval_row],
            flow_rows=[],
        ),
    )
    micro_path = write_json(tmp_path / "micro.json", micro_payload(rows))

    report = module.build_near_resolution_flow_replay_gates(
        evidence_path=evidence_path,
        microstructure_path=micro_path,
        generated_utc="2026-07-04T00:05:00Z",
        max_cluster_share=1.0,
        max_observation_age_seconds=600,
    )

    summary = report["summary"]
    calibration = report.get("calibration", {})

    # selected_replay_model_id matches
    assert summary["selected_replay_model_id"] == "flow_depth_imbalance_settlement_directional"

    # OOS counts match evidence within tolerance (rel_tol=1e-5)
    assert summary["candidate_oos_label_count"] == eval_row["oos_label_count"], (
        f"OOS label count mismatch: {summary['candidate_oos_label_count']} vs {eval_row['oos_label_count']}"
    )
    assert summary["candidate_oos_correct_count"] == eval_row["oos_correct_count"], (
        f"OOS correct count mismatch: {summary['candidate_oos_correct_count']} vs {eval_row['oos_correct_count']}"
    )

    # Minimum quality thresholds (dynamically checked, not hardcoded)
    oos_correct = int(summary["candidate_oos_correct_count"] or 0)
    oos_label = int(summary["candidate_oos_label_count"] or 0)
    assert oos_correct >= 30, f"candidate_oos_correct_count {oos_correct} < 30"
    assert oos_label >= 33, f"candidate_oos_label_count {oos_label} < 33"

    # OOS accuracy >= 0.85
    assert eval_row["oos_accuracy"] >= 0.85, f"OOS accuracy {eval_row['oos_accuracy']} < 0.85"

    # Conservative calibrated side probability in [0.7, 0.9]
    calibrated_prob = calibration.get("conservative_calibrated_side_probability")
    if calibrated_prob is not None:
        assert 0.7 <= float(calibrated_prob) <= 0.9, (
            f"Calibrated probability {calibrated_prob} not in [0.7, 0.9]"
        )

    # Source model p_value < 1e-5
    source_p = calibration.get("source_model_p_value")
    assert source_p is not None, "Missing source_model_p_value"
    assert float(source_p) < 1e-5, f"p_value {source_p} >= 1e-5"

    # Dynamic cross-check: replay values match evidence values (not hardcoded)
    from math import isclose

    assert isclose(
        float(calibration["oos_count"]), float(eval_row["oos_label_count"]), rel_tol=1e-5
    ), "oos_count mismatch"
    assert isclose(
        float(calibration["oos_correct_count"]), float(eval_row["oos_correct_count"]), rel_tol=1e-5
    ), "oos_correct_count mismatch"


# ── VAL-FDR-010: Replay preserves safety boundary ──


def test_safety_boundary_all_false(tmp_path: Path) -> None:
    """VAL-FDR-010: All safety flags false, research_only true, usable_row_count 0."""
    module = load_module()
    rows: list[dict[str, object]] = []
    for index in range(40):
        day = 1
        side = "yes" if index % 2 == 0 else "no"
        ticker = f"KXFLOW-26JUL0{day}-GAME{index:03d}-{side.upper()}"
        rows.append(
            micro_row(
                ticker,
                observed_at=f"2026-07-0{day}T00:{index % 40:02d}:00Z",
                close_time=f"2026-07-0{day}T01:{index % 40:02d}:00Z",
                event_ticker=f"KXFLOW-26JUL0{day}-GAME{index:03d}",
                side=side,
                outcome=1 if side == "yes" else 0,
            )
        )
    rows.append(
        micro_row(
            "KXFLOW-26JUL04-CURRENT-YES",
            observed_at="2026-07-04T00:00:00Z",
            close_time="2026-07-04T01:00:00Z",
            event_ticker="KXFLOW-26JUL04-CURRENT",
            side="yes",
            outcome=None,
        )
    )
    evidence_path = write_json(tmp_path / "evidence.json", evidence_payload())
    micro_path = write_json(tmp_path / "micro.json", micro_payload(rows))

    report = module.build_near_resolution_flow_replay_gates(
        evidence_path=evidence_path,
        microstructure_path=micro_path,
        generated_utc="2026-07-04T00:05:00Z",
    )

    # Root-level safety
    assert report.get("research_only") is True
    assert report.get("execution_enabled") is False
    assert report.get("market_execution") is False
    assert report.get("account_or_order_paths") is False
    assert report.get("database_writes") is False
    assert report.get("staking_or_sizing_guidance") is False
    assert report.get("authenticated_api_calls") is False
    assert report.get("provider_api_calls") is False
    assert report.get("paid_calls") is False
    assert report.get("public_market_data_calls") is False

    # Nested safety block
    safety = report.get("safety", {})
    assert safety.get("market_execution") is False
    assert safety.get("account_or_order_paths") is False
    assert safety.get("database_writes") is False

    # usable_row_count is 0
    assert report["summary"]["usable_row_count"] == 0

    # All paper blocker rows have usable=False, execution_enabled=False
    for row in report.get("paper_decision_blocker_rows", []):
        assert row.get("usable") is False, (
            f"Blocker row {row.get('contract_ticker')} has usable=True"
        )
        assert row.get("execution_enabled") is False, (
            f"Blocker row {row.get('contract_ticker')} has execution_enabled=True"
        )

    # All replay rows have usable=False, research_only=True
    for row in report.get("replay_rows", []):
        assert row.get("usable") is False, (
            f"Replay row {row.get('contract_ticker')} has usable=True"
        )
        assert row.get("research_only") is True, (
            f"Replay row {row.get('contract_ticker')} has research_only=False"
        )
        assert row.get("execution_enabled") is False, (
            f"Replay row {row.get('contract_ticker')} has execution_enabled=True"
        )

    # All capacity rows have usable=False
    for row in report.get("capacity_rows", []):
        assert row.get("usable") is False, (
            f"Capacity row {row.get('contract_ticker')} has usable=True"
        )
        assert row.get("research_only") is True, (
            f"Capacity row {row.get('contract_ticker')} has research_only=False"
        )
        assert row.get("execution_enabled") is False, (
            f"Capacity row {row.get('contract_ticker')} has execution_enabled=True"
        )


# ── VAL-FDR-011: Paper decision blockers reference the decay gate ──


def test_paper_blocker_rows_reference_decay_gate(tmp_path: Path) -> None:
    """VAL-FDR-011: When decay_survival is blocked, blocker rows reference it with sub-condition."""
    module = load_module()
    # Only 1 day of data = 1 close-time bucket → fails decay (needs 3 buckets)
    rows: list[dict[str, object]] = []
    for index in range(40):
        side = "yes" if index % 2 == 0 else "no"
        ticker = f"KXFLOW-26JUL01-GAME{index:03d}-{side.upper()}"
        rows.append(
            micro_row(
                ticker,
                observed_at=f"2026-07-01T00:{index:02d}:00Z",
                close_time="2026-07-01T01:00:00Z",
                event_ticker=f"KXFLOW-26JUL01-GAME{index:03d}",
                side=side,
                outcome=1 if side == "yes" else 0,
            )
        )
    rows.append(
        micro_row(
            "KXFLOW-26JUL04-CURRENT-YES",
            observed_at="2026-07-04T00:00:00Z",
            close_time="2026-07-04T01:00:00Z",
            event_ticker="KXFLOW-26JUL04-CURRENT",
            side="yes",
            outcome=None,
        )
    )
    evidence_path = write_json(tmp_path / "evidence.json", evidence_payload())
    micro_path = write_json(tmp_path / "micro.json", micro_payload(rows))

    report = module.build_near_resolution_flow_replay_gates(
        evidence_path=evidence_path,
        microstructure_path=micro_path,
        generated_utc="2026-07-04T00:05:00Z",
        max_cluster_share=1.0,
    )

    # Check decay_survival gate is blocked due to insufficient buckets
    decay_gate = None
    for g in report["gates"]:
        if g["name"] == "decay_survival":
            decay_gate = g
            break
    assert decay_gate is not None
    assert decay_gate["status"] == "blocked"

    # decay_survival gate reason has specific sub-condition
    reason = str(decay_gate.get("reason", ""))
    assert any(term in reason.lower() for term in ["bucket", "label", "accuracy"]), (
        f"decay_survival reason lacks sub-condition: {reason}"
    )

    # Blockers include "decay_survival not passing" when decay is the first blocked gate
    # (cost/depth/cluster gates pass first, then decay blocks)
    blocker_rows = report.get("paper_decision_blocker_rows", [])
    if blocker_rows:
        has_decay_blocker = any(
            "decay_survival" in str(b) for row in blocker_rows for b in row.get("blocker_list", [])
        )
        assert has_decay_blocker, "Expected 'decay_survival' in blocker list"


# ── VAL-FDR-012: Zero replay rows path handled gracefully ──


def test_zero_replay_rows_handled_gracefully(tmp_path: Path) -> None:
    """VAL-FDR-012: Empty flow rows + empty micro rows → exit 0 with valid JSON."""
    module = load_module()
    # Evidence with empty flow_rows and micro with no rows
    evidence_path = write_json(
        tmp_path / "evidence.json",
        safe_envelope(
            "near_resolution_informed_flow_research_candidates_ready",
            evaluations=[
                {
                    "model_id": "flow_depth_imbalance_settlement_directional",
                    "status": "research_candidate_fdr_passed",
                    "oos_label_count": 33,
                    "oos_correct_count": 30,
                    "oos_accuracy": 30 / 33,
                    "p_value": 0.000001,
                    "q_value": 0.000001,
                }
            ],
            flow_rows=[],
        ),
    )
    micro_path = write_json(tmp_path / "micro.json", micro_payload([]))

    report = module.build_near_resolution_flow_replay_gates(
        evidence_path=evidence_path,
        microstructure_path=micro_path,
        generated_utc="2026-07-04T00:00:00Z",
    )

    # Exit 0 with valid JSON — function returns normally (no exception)
    assert report["status"] is not None
    summary = report["summary"]

    # replay_row_count == 0
    assert summary["replay_row_count"] == 0, (
        f"Expected 0 replay rows, got {summary['replay_row_count']}"
    )

    # decay_status == "blocked_missing_decay_buckets"
    assert summary["decay_status"] == "blocked_missing_decay_buckets", (
        f"Expected 'blocked_missing_decay_buckets', got '{summary['decay_status']}'"
    )

    # decay_bucket_count == 0
    assert summary["decay_bucket_count"] == 0, (
        f"Expected 0 decay buckets, got {summary['decay_bucket_count']}"
    )

    # Downstream gates are blocked (cost_replay and beyond)
    gates = {g["name"]: g for g in report["gates"]}
    # historical_all_in_cost_replay should be blocked (0 costed rows)
    assert gates["historical_all_in_cost_replay"]["status"] != "pass", (
        f"historical_all_in_cost_replay should be blocked: {gates['historical_all_in_cost_replay']['reason']}"
    )

    # Specific reasons
    for name, g in gates.items():
        if g["status"] == "blocked":
            assert len(str(g.get("reason", ""))) > 10, (
                f"Gate '{name}' blocked but reason is too generic: '{g.get('reason')}'"
            )

    # Independent rows = 0
    assert summary["independent_contract_label_count"] == 0


# ── VAL-FDR-013: No FDR survivor path handled gracefully ──


def test_no_fdr_survivor_handled_gracefully(tmp_path: Path) -> None:
    """VAL-FDR-013: Evidence with no FDR survivor → blocked_missing_research_candidate status."""
    module = load_module()
    # Evidence with no FDR-passed evaluations
    evidence_path = write_json(
        tmp_path / "evidence.json",
        safe_envelope(
            "near_resolution_informed_flow_falsification_ready_no_research_candidate",
            evaluations=[
                {
                    "model_id": "flow_depth_imbalance_settlement_directional",
                    "status": "blocked_insufficient_oos_labels",
                    "oos_label_count": 5,
                    "oos_correct_count": 3,
                    "oos_accuracy": 0.6,
                    "p_value": 0.5,
                    "q_value": None,
                }
            ],
            flow_rows=[],
        ),
    )
    micro_path = write_json(tmp_path / "micro.json", micro_payload([]))

    report = module.build_near_resolution_flow_replay_gates(
        evidence_path=evidence_path,
        microstructure_path=micro_path,
        generated_utc="2026-07-04T00:00:00Z",
    )

    # Status indicates missing research candidate
    assert (
        report["status"] == "near_resolution_flow_replay_gates_blocked_missing_research_candidate"
    ), f"Expected '...blocked_missing_research_candidate', got '{report['status']}'"

    # research_candidate_present gate is blocked
    gates = {g["name"]: g for g in report["gates"]}
    assert gates["research_candidate_present"]["status"] == "blocked"
    assert len(str(gates["research_candidate_present"].get("reason", ""))) > 5


# ── VAL-FDR-014: Independent row collapsing preserves contract uniqueness ──


def test_independent_row_collapsing_uniqueness(tmp_path: Path) -> None:
    """VAL-FDR-014: Collapsed rows have unique contract_tickers, independent_count <= replay_count."""
    module = load_module()
    # Create data where some contracts have duplicate rows (same ticker, different times)
    rows: list[dict[str, object]] = []
    # Day 1: 40 contracts, each duplicated
    for index in range(40):
        side = "yes" if index % 2 == 0 else "no"
        ticker = f"KXFLOW-26JUL01-GAME{index:03d}-{side.upper()}"
        # First observation
        rows.append(
            micro_row(
                ticker,
                observed_at="2026-07-01T00:00:00Z",
                close_time="2026-07-01T01:00:00Z",
                event_ticker=f"KXFLOW-26JUL01-GAME{index:03d}",
                side=side,
                outcome=1 if side == "yes" else 0,
            )
        )
        # Second observation (same contract, later time)
        rows.append(
            micro_row(
                ticker,
                observed_at="2026-07-01T00:30:00Z",
                close_time="2026-07-01T01:00:00Z",
                event_ticker=f"KXFLOW-26JUL01-GAME{index:03d}",
                side=side,
                outcome=1 if side == "yes" else 0,
            )
        )
    # Day 2: 40 more unique contracts (no dupes)
    for index in range(40):
        side = "yes" if index % 2 == 0 else "no"
        ticker = f"KXFLOW-26JUL02-GAME{index:03d}-{side.upper()}"
        rows.append(
            micro_row(
                ticker,
                observed_at=f"2026-07-02T00:{index:02d}:00Z",
                close_time="2026-07-02T01:00:00Z",
                event_ticker=f"KXFLOW-26JUL02-GAME{index:03d}",
                side=side,
                outcome=1 if side == "yes" else 0,
            )
        )

    evidence_path = write_json(tmp_path / "evidence.json", evidence_payload())
    micro_path = write_json(tmp_path / "micro.json", micro_payload(rows))

    report = module.build_near_resolution_flow_replay_gates(
        evidence_path=evidence_path,
        microstructure_path=micro_path,
        generated_utc="2026-07-04T00:05:00Z",
        max_cluster_share=1.0,
        max_observation_age_seconds=900,
    )

    summary = report["summary"]

    # independent_contract_label_count <= replay_row_count
    independent_count = summary["independent_contract_label_count"]
    replay_count = summary["replay_row_count"]
    assert independent_count <= replay_count, (
        f"Independent count {independent_count} > replay count {replay_count}"
    )

    # Each contract_ticker appears at most once in replay_rows
    replay_tickers = [row.get("contract_ticker") for row in report.get("replay_rows", [])]
    assert len(replay_tickers) == len(set(replay_tickers)), (
        "Duplicate contract_ticker in replay_rows"
    )


# ── VAL-FDR-015: All-in cost includes Kalshi fee markup ──


def test_all_in_cost_includes_fees(tmp_path: Path) -> None:
    """VAL-FDR-015: all_in_cost >= selected_side_executable_price (fees included)."""
    module = load_module()
    rows: list[dict[str, object]] = []
    for index in range(40):
        day = 1
        side = "yes" if index % 2 == 0 else "no"
        ticker = f"KXFLOW-26JUL0{day}-GAME{index:03d}-{side.upper()}"
        rows.append(
            micro_row(
                ticker,
                observed_at=f"2026-07-0{day}T00:{index:02d}:00Z",
                close_time=f"2026-07-0{day}T01:00:00Z",
                event_ticker=f"KXFLOW-26JUL0{day}-GAME{index:03d}",
                side=side,
                outcome=1 if side == "yes" else 0,
            )
        )
    evidence_path = write_json(tmp_path / "evidence.json", evidence_payload())
    micro_path = write_json(tmp_path / "micro.json", micro_payload(rows))

    report = module.build_near_resolution_flow_replay_gates(
        evidence_path=evidence_path,
        microstructure_path=micro_path,
        generated_utc="2026-07-04T00:05:00Z",
        max_cluster_share=1.0,
        max_observation_age_seconds=900,
    )

    # Every replay row with all_in_cost should have all_in_cost >= selected_side_executable_price
    for row in report.get("replay_rows", []):
        all_in = row.get("all_in_cost")
        executable = row.get("selected_side_executable_price")
        if all_in is not None and executable is not None:
            assert float(all_in) >= float(executable) - 1e-6, (
                f"Row {row.get('contract_ticker')}: all_in_cost {all_in} < "
                f"selected_side_executable_price {executable}"
            )
        # all_in_cost should be in [0, 1.05] (allowing for fees pushing above 1.0)
        if all_in is not None:
            assert 0.0 <= float(all_in) <= 1.05, (
                f"Row {row.get('contract_ticker')}: all_in_cost {all_in} outside [0, 1.05]"
            )


# ── VAL-FDR-016: Blocker list respects gate dependency ordering ──


def test_blocker_list_respects_dependency_ordering(tmp_path: Path) -> None:
    """VAL-FDR-016: When upstream gates blocked, downstream gates do not appear in blockers."""
    module = load_module()
    # Evidence with no FDR survivor — blocks research_candidate_present
    evidence_path = write_json(
        tmp_path / "evidence.json",
        safe_envelope(
            "blocked_insufficient_oos_labels",
            evaluations=[],
            flow_rows=[],
        ),
    )
    micro_path = write_json(tmp_path / "micro.json", micro_payload([]))

    report = module.build_near_resolution_flow_replay_gates(
        evidence_path=evidence_path,
        microstructure_path=micro_path,
        generated_utc="2026-07-04T00:00:00Z",
    )

    # Verify blocker rows only reference the first upstream blocked gate
    blocker_rows = report.get("paper_decision_blocker_rows", [])
    for row in blocker_rows:
        blockers = row.get("blocker_list", [])
        for b in blockers:
            # Downstream gate names that should NOT appear when upstream is blocked
            downstream_names = [
                "conservative_probability_ready",
                "historical_all_in_cost_replay",
                "positive_cost_adjusted_replay_rows",
                "current_candidates_present",
                "positive_capacity_depth",
                "correlation_cluster_limit",
                "decay_survival",
            ]
            for downstream in downstream_names:
                assert downstream not in b, (
                    f"Downstream blocker '{b}' appears when upstream gate is blocked"
                )
        # Should only reference the first upstream blocked gate (or its parent dependency)
        has_related_blocker = any(
            "research_candidate_present" in b or "evidence_artifact_safe" in b for b in blockers
        )
        # If the blocker list is non-empty, it should reference an upstream gate
        # (if evidence_artifact_safe is also blocked, that may be first)
        if blockers:
            assert has_related_blocker or not blockers, (
                f"Blocker doesn't reference upstream gate: {blockers}"
            )
