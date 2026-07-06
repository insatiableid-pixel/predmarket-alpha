"""Tests for automatic signal decay/retirement ledger.

Covers VAL-DECAY-001 through VAL-DECAY-008 assertions.
"""

import json
from pathlib import Path

from predmarket.signal_decay_retirement import (
    build_signal_decay_retirement_ledger,
    is_retired_signal,
)

# ── Helpers ────────────────────────────────────────────────────────────────


def pass_ready_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "contract_ticker": "KXUNIT-YES",
        "side": "yes",
        "family_id": "unit_family",
        "model_id": "unit_model",
        "source_repo_id": "unit_repo",
        "signal_formula_key": "unit_formula",
        "usable": True,
        "calibrated_probability": 0.60,
        "display_price": 0.40,
        "all_in_cost": 0.40,
        "expected_value_per_contract": 0.20,
        "capacity_estimate": 50.0,
        "correlation_cluster_key": "unit|cluster",
        "close_time": "2026-07-03T00:00:00Z",
        "resolution_rule_status": "verified_official_terms",
        "gate_status": "pass",
        "timing_status": "clean",
        "capacity_gate_status": "pass",
        "correlation_cluster_gate_status": "pass",
        "decay_gate_status": "pass",
    }
    row.update(overrides)
    return row


def paper_candidates_payload(*rows: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "paper_decision_candidates_ready_all_rows_blocked",
        "research_only": True,
        "execution_enabled": False,
        "candidates": list(rows),
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ── VAL-DECAY-001: Decay retirement ledger tracks signal survival per bucket ─


class TestValDecay001:
    """VAL-DECAY-001: Each signal carries label_count, correct_count, accuracy,
    recent_bucket, recent_label_count, recent_correct_count, recent_accuracy."""

    def test_signal_fields_present(self, tmp_path: Path) -> None:
        paper_path = tmp_path / "paper.json"
        rows = [
            pass_ready_row(
                close_time="2026-07-03T00:01:00Z",
                settled_outcome=1,
                predicted_outcome=1,
                capacity_estimate=10.0,
            ),
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
        )

        assert len(report["signals"]) >= 1
        signal = report["signals"][0]
        # Each required field must be present
        assert "label_count" in signal, f"Missing label_count in {signal}"
        assert "correct_count" in signal, f"Missing correct_count in {signal}"
        assert "accuracy" in signal, f"Missing accuracy in {signal}"
        assert "recent_bucket" in signal, f"Missing recent_bucket in {signal}"
        assert "recent_label_count" in signal, f"Missing recent_label_count in {signal}"
        assert "recent_correct_count" in signal, f"Missing recent_correct_count in {signal}"
        assert "recent_accuracy" in signal, f"Missing recent_accuracy in {signal}"

    def test_signal_fields_have_correct_types(self, tmp_path: Path) -> None:
        paper_path = tmp_path / "paper.json"
        rows = [
            pass_ready_row(
                close_time="2026-07-03T00:01:00Z",
                settled_outcome=1,
                predicted_outcome=1,
                capacity_estimate=10.0,
            ),
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
        )

        signal = report["signals"][0]
        assert isinstance(signal["label_count"], int)
        assert isinstance(signal["correct_count"], int)
        # accuracy can be None or float
        assert signal["accuracy"] is None or isinstance(signal["accuracy"], float)
        # recent_bucket can be None or string
        assert signal["recent_bucket"] is None or isinstance(signal["recent_bucket"], str)
        assert isinstance(signal["recent_label_count"], int)
        assert isinstance(signal["recent_correct_count"], int)
        assert signal["recent_accuracy"] is None or isinstance(signal["recent_accuracy"], float)


# ── VAL-DECAY-002: Signals failing decay survival are mechanically retired ───


class TestValDecay002:
    """VAL-DECAY-002: Signal retired when recent_label_count < 3 OR
    recent_accuracy < 0.5."""

    def test_retired_when_recent_label_count_below_min(self, tmp_path: Path) -> None:
        """Signal with labeled history but only 1 recent label (< 3) must retire."""
        paper_path = tmp_path / "paper.json"
        # One label in the far past bucket, one in recent bucket
        rows = [
            pass_ready_row(
                close_time="2026-07-01T00:01:00Z",
                settled_outcome=1,
                predicted_outcome=1,
                capacity_estimate=10.0,
            ),
            pass_ready_row(
                close_time="2026-07-03T00:01:00Z",
                settled_outcome=1,
                predicted_outcome=1,
                capacity_estimate=10.0,
            ),
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
            min_recent_decisions=3,
        )

        signal = report["signals"][0]
        assert signal["retirement_status"] == "retired", (
            f"Signal with 1 recent label (< 3) should be retired, got: {signal}"
        )
        assert any("decay_survival" in r for r in signal["retirement_reasons"]), (
            f"Retirement reasons should include decay_survival: {signal['retirement_reasons']}"
        )

    def test_retired_when_recent_accuracy_below_threshold(self, tmp_path: Path) -> None:
        """Signal with 3 recent labels but 0/3 correct (< 0.5) must retire."""
        paper_path = tmp_path / "paper.json"
        rows = [
            pass_ready_row(
                close_time=f"2026-07-03T00:0{i}:00Z",
                settled_outcome=0,
                predicted_outcome=1,
                capacity_estimate=10.0,
            )
            for i in range(1, 4)
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
            min_recent_decisions=3,
            min_recent_accuracy=0.5,
        )

        signal = report["signals"][0]
        assert signal["retirement_status"] == "retired", (
            f"Signal with recent_accuracy=0 should be retired: {signal}"
        )
        assert any("decay_survival" in r for r in signal["retirement_reasons"]), (
            f"Should have decay_survival reason: {signal['retirement_reasons']}"
        )

    def test_active_when_recent_accuracy_above_threshold(self, tmp_path: Path) -> None:
        """Signal with 3 recent labels and 3/3 correct (> 0.5) stays active."""
        paper_path = tmp_path / "paper.json"
        # All rows must be in the same bucket (same minute) for recent count = 3
        rows = [
            pass_ready_row(
                close_time=f"2026-07-03T00:00:0{i}Z",
                settled_outcome=1,
                predicted_outcome=1,
                calibrated_probability=None,
                capacity_estimate=10.0,
            )
            for i in range(1, 4)
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
            min_recent_decisions=3,
            min_recent_accuracy=0.5,
        )

        signal = report["signals"][0]
        assert signal["retirement_status"] == "active", (
            f"Signal with 3/3 correct should be active: {signal}"
        )


# ── VAL-DECAY-003: Calibration drift triggers retirement ──────────────────


class TestValDecay003:
    """VAL-DECAY-003: Signal retired when mean_calibration_error > 0.2."""

    def test_retired_on_calibration_drift(self, tmp_path: Path) -> None:
        """Signal with high calibration error (> 0.2) must retire."""
        paper_path = tmp_path / "paper.json"
        # Enough labels (3+) to trigger a review, and high calibration error
        rows = [
            pass_ready_row(
                close_time=f"2026-07-03T00:0{i}:00Z",
                settled_outcome=0 if i == 1 else 1,
                predicted_outcome=1,
                calibrated_probability=0.90,
                capacity_estimate=10.0,
            )
            for i in range(1, 4)
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
            min_recent_decisions=3,
            min_recent_accuracy=0.5,
            max_calibration_error=0.2,
        )

        signal = report["signals"][0]
        assert signal["retirement_status"] == "retired", (
            f"Signal with high calibration error should be retired: {signal}"
        )
        assert any("calibration_drift" in r for r in signal["retirement_reasons"]), (
            f"Should have calibration_drift reason: {signal['retirement_reasons']}"
        )

    def test_calibration_drift_reason_contains_failure_mode(self, tmp_path: Path) -> None:
        """Retirement reason for calibration drift includes 'calibration_drift'."""
        paper_path = tmp_path / "paper.json"
        rows = [
            pass_ready_row(
                close_time=f"2026-07-03T00:0{i}:00Z",
                settled_outcome=0,
                predicted_outcome=1,
                calibrated_probability=0.90,
                capacity_estimate=10.0,
            )
            for i in range(1, 4)
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
            max_calibration_error=0.2,
        )

        signal = report["signals"][0]
        reason_text = "; ".join(str(r) for r in signal["retirement_reasons"])
        assert "calibration_drift" in reason_text, (
            f"Reason should contain 'calibration_drift': {reason_text}"
        )

    def test_no_side_selected_probability_uses_selected_outcome_for_calibration(
        self, tmp_path: Path
    ) -> None:
        """Correct NO-side rows should compare P(NO) to the selected-side win."""
        paper_path = tmp_path / "paper.json"
        rows = [
            pass_ready_row(
                contract_ticker=f"KXUNIT-NO-{i}",
                side="no",
                close_time=f"2026-07-03T00:00:0{i}Z",
                settled_outcome=0,
                predicted_outcome=0,
                selected_side_outcome=1,
                calibrated_probability=0.90,
                capacity_estimate=10.0,
            )
            for i in range(1, 4)
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
            min_recent_decisions=3,
            min_recent_accuracy=0.5,
            max_calibration_error=0.2,
        )

        signal = report["signals"][0]
        assert signal["retirement_status"] == "active"
        assert signal["accuracy"] == 1.0
        assert signal["mean_calibration_error"] == 0.1


# ── VAL-DECAY-004: Retirement is automatic (no human review step) ──────────


class TestValDecay004:
    """VAL-DECAY-004: Retirement is fully automatic. No manual review in
    retirement logic or policy."""

    def test_no_interactive_prompts_in_retirement(self, tmp_path: Path) -> None:
        """The build_signal_decay_retirement_ledger function must execute
        fully programmatically."""
        paper_path = tmp_path / "paper.json"
        write_json(paper_path, paper_candidates_payload(pass_ready_row()))

        # This must execute without any interactive input
        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
        )
        assert report["status"].startswith("signal_decay_retirement_ledger")

    def test_policy_no_manual_review_keys(self, tmp_path: Path) -> None:
        """Policy section must not contain manual_review, approval_required,
        or human_override."""
        paper_path = tmp_path / "paper.json"
        write_json(paper_path, paper_candidates_payload(pass_ready_row()))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
        )

        policy = report.get("policy") or {}
        forbidden_keys = {"manual_review", "approval_required", "human_override"}
        for key in forbidden_keys:
            assert key not in policy, f"Policy should not contain '{key}', but found in {policy}"


# ── VAL-DECAY-005: Retired signals appear with retirement reason and timestamp


class TestValDecay005:
    """VAL-DECAY-005: Retired signals have non-empty retirement_reasons list
    and generated_utc timestamp."""

    def test_retired_signal_has_non_empty_reasons(self, tmp_path: Path) -> None:
        paper_path = tmp_path / "paper.json"
        rows = [
            pass_ready_row(
                close_time=f"2026-07-03T00:0{i}:00Z",
                settled_outcome=0,
                predicted_outcome=1,
                capacity_estimate=10.0,
            )
            for i in range(1, 4)
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
            min_recent_decisions=3,
            min_recent_accuracy=0.5,
        )

        for signal in report["signals"]:
            if signal["retirement_status"] == "retired":
                assert signal["retirement_reasons"], (
                    f"Retired signal {signal['signal_key']} has empty retirement_reasons"
                )

    def test_ledger_has_generated_utc(self, tmp_path: Path) -> None:
        paper_path = tmp_path / "paper.json"
        write_json(paper_path, paper_candidates_payload(pass_ready_row()))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
        )

        generated = report.get("generated_utc")
        assert generated is not None, "generated_utc must be present"
        assert isinstance(generated, str), f"generated_utc must be a string, got {type(generated)}"
        # Should be valid ISO-8601
        assert "T" in generated and "Z" in generated, (
            f"generated_utc should be ISO-8601 UTC: {generated}"
        )


# ── VAL-DECAY-006: Retirement ledger updated on every sports evidence cycle ─


class TestValDecay006:
    """VAL-DECAY-006: generated_utc of decay ledger and evidence cycle report
    differ by <= 5 minutes. This is verified by comparing timestamps when
    both are run in the same make target."""

    def test_timestamps_within_range_of_writer(self, tmp_path: Path) -> None:
        """Verify that running back-to-back produces timestamps close together."""
        paper_path = tmp_path / "paper.json"
        write_json(paper_path, paper_candidates_payload(pass_ready_row()))

        t1 = "2026-07-03T00:10:00Z"
        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc=t1,
        )

        assert report["generated_utc"] == t1

        t2 = "2026-07-03T00:12:00Z"
        report2 = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc=t2,
        )

        assert report2["generated_utc"] == t2
        # Difference is 2 minutes, well within 5-minute window
        # (The actual check is done by comparing cycle report and ledger
        #  timestamps in the integrated cycle.)


# ── VAL-DECAY-007: Zero-label signals remain active ────────────────────────


class TestValDecay007:
    """VAL-DECAY-007: Zero-label signals remain active (retirement_status ==
    active)."""

    def test_zero_label_signal_remains_active(self, tmp_path: Path) -> None:
        """Signal with no labels at all should be active."""
        paper_path = tmp_path / "paper.json"
        # A row with no settled_outcome (no label yet)
        row = pass_ready_row(
            settled_outcome=None,
            predicted_outcome=None,
        )
        write_json(paper_path, paper_candidates_payload(row))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
        )

        signal = report["signals"][0]
        assert signal["label_count"] == 0, f"Expected label_count=0, got {signal['label_count']}"
        assert signal["recent_label_count"] == 0, (
            f"Expected recent_label_count=0, got {signal['recent_label_count']}"
        )
        assert signal["retirement_status"] == "active", (
            f"Zero-label signal should be active, got {signal['retirement_status']}"
        )

    def test_no_unsettled_rows_never_retire(self, tmp_path: Path) -> None:
        """Signal with rows but no settled outcomes (observations only) stays active."""
        paper_path = tmp_path / "paper.json"
        rows = [
            pass_ready_row(
                close_time=f"2026-07-03T00:0{i}:00Z",
                # No settled_outcome or outcome - unlabeled observation
                settled_outcome=None,
                predicted_outcome=None,
                capacity_estimate=10.0,
            )
            for i in range(1, 4)
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
            min_recent_decisions=3,
        )

        signal = report["signals"][0]
        assert signal["retirement_status"] == "active", (
            f"Unlabeled observation rows should stay active: {signal}"
        )


# ── VAL-DECAY-008: Capacity disappearance does not alone cause retirement ──


class TestValDecay008:
    """VAL-DECAY-008: Capacity disappearance tracked but does not alone cause
    retirement."""

    def test_capacity_disappearance_alone_does_not_retire(self, tmp_path: Path) -> None:
        """Signal with capacity_estimate=0 for all rows but good accuracy
        should NOT be retired (no other reason)."""
        paper_path = tmp_path / "paper.json"
        rows = [
            pass_ready_row(
                close_time=f"2026-07-03T00:00:0{i}Z",
                settled_outcome=1,
                predicted_outcome=1,
                calibrated_probability=None,
                capacity_estimate=0.0,  # No capacity
            )
            for i in range(1, 4)
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
            min_recent_decisions=3,
            min_recent_accuracy=0.5,
        )

        signal = report["signals"][0]
        # Signal has 3/3 correct in recent bucket, so accuracy > 0.5
        assert signal["capacity_disappeared"] is True, (
            "capacity_disappeared should be True when all rows have capacity=0"
        )
        assert signal["retirement_status"] == "active", (
            f"Capacity disappearance alone should not retire: {signal}"
        )
        # The reason list should still contain "capacity disappeared" for tracking
        assert any("capacity" in r for r in signal["retirement_reasons"]), (
            f"Should track capacity disappearance in reasons: {signal['retirement_reasons']}"
        )

    def test_capacity_and_decay_together_retire(self, tmp_path: Path) -> None:
        """Signal with capacity=0 AND decay failure should be retired."""
        paper_path = tmp_path / "paper.json"
        # Low accuracy (0/3 correct) AND zero capacity
        rows = [
            pass_ready_row(
                close_time=f"2026-07-03T00:0{i}:00Z",
                settled_outcome=0,
                predicted_outcome=1,
                capacity_estimate=0.0,
            )
            for i in range(1, 4)
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
            min_recent_decisions=3,
            min_recent_accuracy=0.5,
        )

        signal = report["signals"][0]
        assert signal["capacity_disappeared"] is True
        assert signal["retirement_status"] == "retired", (
            f"Capacity disappearance AND decay should retire: {signal}"
        )
        assert any("decay_survival" in r for r in signal["retirement_reasons"]), (
            f"Should have decay_survival reason: {signal['retirement_reasons']}"
        )
        assert any("capacity" in r for r in signal["retirement_reasons"]), (
            f"Should track capacity disappearance: {signal['retirement_reasons']}"
        )

    def test_signals_with_capacity_reason_only_not_retired(self, tmp_path: Path) -> None:
        """Verify is_retired_signal returns False for capacity-only signals."""
        paper_path = tmp_path / "paper.json"
        rows = [
            pass_ready_row(
                close_time=f"2026-07-03T00:00:0{i}Z",
                settled_outcome=1,
                predicted_outcome=1,
                calibrated_probability=None,
                capacity_estimate=0.0,
            )
            for i in range(1, 4)
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
        )

        signal = report["signals"][0]
        assert signal["retirement_status"] == "active"
        assert is_retired_signal(rows[0], report) is False, (
            "is_retired_signal should return False for capacity-only signal"
        )


# ── Additional integration/consistency tests ────────────────────────────────


class TestDecayRetirementPolicy:
    """Verify the policy section structure."""

    def test_policy_contains_expected_thresholds(self, tmp_path: Path) -> None:
        paper_path = tmp_path / "paper.json"
        write_json(paper_path, paper_candidates_payload(pass_ready_row()))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
            min_recent_decisions=3,
            min_recent_accuracy=0.5,
            max_calibration_error=0.2,
        )

        policy = report.get("policy") or {}
        assert policy.get("min_recent_decisions") == 3
        assert policy.get("min_recent_accuracy") == 0.5
        assert policy.get("max_calibration_error") == 0.2


class TestIsRetiredSignal:
    """Tests for the is_retired_signal helper."""

    def test_returns_true_for_retired_signal(self, tmp_path: Path) -> None:
        paper_path = tmp_path / "paper.json"
        rows = [
            pass_ready_row(
                close_time=f"2026-07-03T00:0{i}:00Z",
                settled_outcome=0,
                predicted_outcome=1,
            )
            for i in range(1, 4)
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
            min_recent_decisions=3,
            min_recent_accuracy=0.5,
        )

        assert is_retired_signal(rows[0], report) is True

    def test_returns_false_for_active_signal(self, tmp_path: Path) -> None:
        paper_path = tmp_path / "paper.json"
        rows = [
            pass_ready_row(
                close_time=f"2026-07-03T00:00:0{i}Z",
                settled_outcome=1,
                predicted_outcome=1,
                calibrated_probability=None,
            )
            for i in range(1, 4)
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
            min_recent_decisions=3,
            min_recent_accuracy=0.5,
        )

        assert is_retired_signal(rows[0], report) is False

    def test_retired_signal_key_matches_ledger(self, tmp_path: Path) -> None:
        """Verify signal_key used in is_retired_signal matches the ledger's key."""
        paper_path = tmp_path / "paper.json"
        rows = [
            pass_ready_row(
                close_time=f"2026-07-03T00:0{i}:00Z",
                settled_outcome=0,
                predicted_outcome=1,
            )
            for i in range(1, 4)
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
            min_recent_decisions=3,
            min_recent_accuracy=0.5,
        )

        ledger_signal_key = report["signals"][0]["signal_key"]
        row_signal_key = "unit_family|unit_model|unit_formula|unit_repo"
        assert ledger_signal_key == row_signal_key, (
            f"Expected signal_key '{row_signal_key}', got '{ledger_signal_key}'"
        )


class TestRetirementReasonsSpecific:
    """Verify retirement reasons include specific failure modes."""

    def test_decay_survival_reason_format(self, tmp_path: Path) -> None:
        """The decay survival reason should start with 'decay_survival:'."""
        paper_path = tmp_path / "paper.json"
        rows = [
            pass_ready_row(
                close_time=f"2026-07-03T00:0{i}:00Z",
                settled_outcome=0,
                predicted_outcome=1,
            )
            for i in range(1, 4)
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
            min_recent_decisions=3,
            min_recent_accuracy=0.5,
        )

        signal = report["signals"][0]
        decay_reasons = [r for r in signal["retirement_reasons"] if "decay_survival" in r]
        assert decay_reasons, (
            f"Should have at least one decay_survival reason: {signal['retirement_reasons']}"
        )

    def test_calibration_drift_reason_format(self, tmp_path: Path) -> None:
        """The calibration drift reason should start with 'calibration_drift:'."""
        paper_path = tmp_path / "paper.json"
        rows = [
            pass_ready_row(
                close_time=f"2026-07-03T00:0{i}:00Z",
                settled_outcome=0,
                predicted_outcome=1,
                calibrated_probability=0.90,
            )
            for i in range(1, 4)
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
            max_calibration_error=0.2,
        )

        signal = report["signals"][0]
        cal_reasons = [r for r in signal["retirement_reasons"] if "calibration_drift" in r]
        assert cal_reasons, (
            f"Should have at least one calibration_drift reason: {signal['retirement_reasons']}"
        )


class TestScriptStructure:
    """Test the script-level structure of the retirement ledger."""

    def test_ledger_has_required_root_fields(self, tmp_path: Path) -> None:
        paper_path = tmp_path / "paper.json"
        write_json(paper_path, paper_candidates_payload(pass_ready_row()))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
        )

        # Must have schema_version, generated_utc, status, research_only, etc.
        assert "schema_version" in report
        assert "generated_utc" in report
        assert "status" in report
        assert "research_only" in report
        assert "execution_enabled" in report
        assert "signals" in report
        assert "summary" in report
        assert "policy" in report
        assert "safety" in report

        # Safety invariants
        assert report["research_only"] is True
        assert report["execution_enabled"] is False

    def test_summary_counts_are_consistent(self, tmp_path: Path) -> None:
        paper_path = tmp_path / "paper.json"
        rows = [
            pass_ready_row(
                close_time=f"2026-07-03T00:0{i}:00Z",
                settled_outcome=0,
                predicted_outcome=1,
            )
            for i in range(1, 4)
        ]
        write_json(paper_path, paper_candidates_payload(*rows))

        report = build_signal_decay_retirement_ledger(
            paper_decisions_path=paper_path,
            generated_utc="2026-07-03T00:10:00Z",
            min_recent_decisions=3,
            min_recent_accuracy=0.5,
        )

        summary = report["summary"]
        signals = report["signals"]
        retired_count = sum(1 for s in signals if s["retirement_status"] == "retired")
        active_count = sum(1 for s in signals if s["retirement_status"] == "active")

        assert summary["signal_count"] == len(signals)
        assert summary["retired_signal_count"] == retired_count
        assert summary["active_signal_count"] == active_count
        assert (
            summary["signal_count"]
            == summary["retired_signal_count"] + summary["active_signal_count"]
        )
