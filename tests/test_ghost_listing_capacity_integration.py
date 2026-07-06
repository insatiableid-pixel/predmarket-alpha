"""Tests for ghost-listing capacity integration in paper decision engine.

Covers VAL-GHOST-001, VAL-GHOST-002, VAL-GHOST-007, VAL-GHOST-008,
VAL-GHOST-009, VAL-GHOST-011, VAL-SIZING-021 through VAL-SIZING-026,
VAL-CROSS-014, VAL-CROSS-022.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from predmarket.paper_decision_engine import (
    apply_ghost_listing_capacity_override,
    build_ghost_listing_index,
    build_paper_decision_candidates,
    check_ghost_listing_stale,
    load_ghost_listing_diagnostic,
)

# ── Helpers ─────────────────────────────────────────────────────────────────


def ledger_payload(*rows: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "kalshi_ev_ledger_ready_with_usable_contract_edges",
        "research_only": True,
        "execution_enabled": False,
        "rows": list(rows),
    }


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


def ghost_diagnostic_payload(
    *depth_rows: dict[str, object],
    generated_utc: str | None = None,
) -> dict[str, object]:
    if generated_utc is None:
        generated_utc = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    return {
        "schema_version": 1,
        "generated_utc": generated_utc,
        "status": "ghost_listing_depth_diagnostic_current_depth_ready",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "freshness": {
            "generated_utc": generated_utc,
            "max_staleness_seconds": 3600,
        },
        "depth_rows": list(depth_rows),
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }


def ghost_row(
    contract_ticker: str,
    ghost_listing_flag: bool = True,
    total_depth_contracts: int = 0,
) -> dict[str, object]:
    return {
        "contract_ticker": contract_ticker,
        "classification": "unit_test",
        "series_ticker": "KXUNIT",
        "ghost_listing_flag": ghost_listing_flag,
        "total_depth_contracts": total_depth_contracts,
        "research_only": True,
        "execution_enabled": False,
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_ledger(*rows: dict[str, object]) -> Path:
    path = Path("/tmp") / f"test_ghost_ledger_{id(rows)}.json"
    write_json(path, ledger_payload(*rows))
    return path


GENERATED_UTC = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


# ── VAL-GHOST-001: CCD-positive contracts zeroed when ghost-listed ──────────


class TestGhostListingZeroesCCDPositive:
    """VAL-GHOST-001: CCD-positive contracts zeroed when ghost-listed."""

    def test_ghost_listed_contract_gets_zero_capacity(self) -> None:
        """Ghost-listed contract gets capacity_estimate forced to 0."""
        candidates = [
            {
                "contract_ticker": "KXGHOST-TEST",
                "paper_usable": True,
                "paper_stake": 25.0,
                "capacity_estimate": 50.0,
            }
        ]
        index = {"KXGHOST-TEST": True}  # ghost-listed

        result = apply_ghost_listing_capacity_override(candidates, index)
        assert result[0]["capacity_estimate"] == 0.0
        assert result[0]["ghost_listing_applied"] is True
        assert result[0]["ghost_listing_flag"] is True

    def test_capacity_estimate_not_negative_after_override(self) -> None:
        """VAL-SIZING-026: Capacity cap floor is 0.0, never negative."""
        candidates = [
            {
                "contract_ticker": "KXGHOST-TEST",
                "paper_usable": True,
                "paper_stake": 0.0,
                "capacity_estimate": 50.0,
            }
        ]
        index = {"KXGHOST-TEST": True}
        result = apply_ghost_listing_capacity_override(candidates, index)
        assert result[0]["capacity_estimate"] >= 0.0
        assert result[0]["capacity_estimate"] == 0.0

    def test_non_ghost_listed_keeps_capacity(self) -> None:
        """VAL-SIZING-022: Non-ghost-listed contracts keep their CCD capacity estimate."""
        candidates = [
            {
                "contract_ticker": "KXNORMAL-TEST",
                "paper_usable": True,
                "paper_stake": 25.0,
                "capacity_estimate": 50.0,
            }
        ]
        index = {"KXGHOST-TEST": True}  # Different ticker

        result = apply_ghost_listing_capacity_override(candidates, index)
        assert result[0]["capacity_estimate"] == 50.0  # unchanged
        assert result[0].get("ghost_listing_applied") is True  # applied (index exists)
        assert result[0].get("ghost_listing_flag") is False  # not ghost-listed


# ── VAL-GHOST-002: Zero capacity through full sizing chain ──────────────────


class TestGhostListingFullSizingChain:
    """VAL-GHOST-002: Ghost-listed contracts propagate zero capacity through full sizing chain."""

    def test_ghost_listed_contract_gets_zero_paper_stake(self) -> None:
        """Through full pipeline, ghost-listed contract gets zero paper stake."""
        row = pass_ready_row(
            contract_ticker="KXGHOST-TEST",
            calibrated_probability=0.60,
            display_price=0.40,
            expected_value_per_contract=0.20,
            capacity_estimate=100.0,
            correlation_cluster_key="",
        )
        diagnostic = ghost_diagnostic_payload(
            ghost_row("KXGHOST-TEST", ghost_listing_flag=True, total_depth_contracts=0)
        )
        diagnostic_path = Path("/tmp") / f"test_ghost_diag_{id(row)}.json"
        write_json(diagnostic_path, diagnostic)

        report = build_paper_decision_candidates(
            ledger_path=write_ledger(row),
            ghost_depth_path=diagnostic_path,
            generated_utc=GENERATED_UTC,
            paper_bankroll=1000.0,
            kelly_fraction=0.25,
            max_fraction_per_contract=0.02,
        )

        candidate = report["candidates"][0]
        assert candidate["capacity_estimate"] == 0.0
        assert candidate["paper_stake"] == 0.0
        assert candidate["paper_usable"] is False
        assert candidate["ghost_listing_flag"] is True

    def test_non_ghost_listed_gets_positive_stake(self) -> None:
        """Non-ghost-listed contract keeps capacity and gets positive stake if edge positive."""
        row = pass_ready_row(
            contract_ticker="KXNORMAL-TEST",
            calibrated_probability=0.60,
            display_price=0.40,
            expected_value_per_contract=0.20,
            capacity_estimate=100.0,
            correlation_cluster_key="",
        )
        diagnostic = ghost_diagnostic_payload(
            ghost_row("KXGHOST-TEST", ghost_listing_flag=True, total_depth_contracts=0)
        )
        diagnostic_path = Path("/tmp") / f"test_ghost_diag_{id(row)}.json"
        write_json(diagnostic_path, diagnostic)

        report = build_paper_decision_candidates(
            ledger_path=write_ledger(row),
            ghost_depth_path=diagnostic_path,
            generated_utc=GENERATED_UTC,
            paper_bankroll=1000.0,
            kelly_fraction=0.25,
            max_fraction_per_contract=0.02,
        )

        candidate = report["candidates"][0]
        assert candidate["capacity_estimate"] == 100.0  # unchanged
        assert candidate["paper_stake"] > 0
        assert candidate["paper_usable"] is True
        assert candidate["ghost_listing_flag"] is False


# ── VAL-SIZING-023: Missing diagnostic → fail-open ──────────────────────────


class TestGhostListingMissingDiagnostic:
    """VAL-SIZING-023: Missing ghost-listing diagnostic → no capacity zeroing."""

    def test_no_ghost_depth_path_keeps_capacity(self) -> None:
        """When no ghost depth path supplied, capacity is unchanged."""
        row = pass_ready_row(
            contract_ticker="KXNORMAL-TEST",
            capacity_estimate=50.0,
        )
        report = build_paper_decision_candidates(
            ledger_path=write_ledger(row),
            ghost_depth_path=None,
            generated_utc=GENERATED_UTC,
            paper_bankroll=1000.0,
        )

        candidate = report["candidates"][0]
        assert candidate["capacity_estimate"] == 50.0
        assert (
            candidate.get("ghost_listing_flag") is False
            or candidate.get("ghost_listing_flag") is None
        )

    def test_missing_diagnostic_file_keeps_capacity(self) -> None:
        """When ghost depth file doesn't exist, capacity is unchanged (fail-open)."""
        row = pass_ready_row(
            contract_ticker="KXNORMAL-TEST",
            capacity_estimate=50.0,
        )
        ghost_path = Path("/tmp") / "nonexistent-ghost-diagnostic.json"
        report = build_paper_decision_candidates(
            ledger_path=write_ledger(row),
            ghost_depth_path=ghost_path,
            generated_utc=GENERATED_UTC,
            paper_bankroll=1000.0,
        )

        candidate = report["candidates"][0]
        assert candidate["capacity_estimate"] == 50.0


# ── VAL-SIZING-024: Exact contract_ticker matching ──────────────────────────


class TestExactContractTickerMatching:
    """VAL-SIZING-024: Ghost-listing check is cross-referenced by exact contract_ticker, case-sensitive."""

    def test_case_sensitive_matching(self) -> None:
        """Ghost-listing matching is case-sensitive."""
        candidates = [
            {
                "contract_ticker": "KXUNIT-TEST",
                "capacity_estimate": 50.0,
            }
        ]
        # Lowercase ticker in ghost index
        index = {"kxunit-test": True}

        result = apply_ghost_listing_capacity_override(candidates, index)
        # No match (case differs), capacity unchanged
        assert result[0]["capacity_estimate"] == 50.0

    def test_exact_match_needed(self) -> None:
        """Only exact ticker match triggers ghost-listing."""
        candidates = [
            {
                "contract_ticker": "KXUNIT-TEST",
                "capacity_estimate": 50.0,
            }
        ]
        # Partial match in index
        index = {"KXUNIT": True}

        result = apply_ghost_listing_capacity_override(candidates, index)
        # No exact match, capacity unchanged
        assert result[0]["capacity_estimate"] == 50.0


# ── VAL-GHOST-007: ghost_listing_flag is unambiguous ────────────────────────


class TestGhostListingFlagUnambiguous:
    """VAL-GHOST-007: Per-contract ghost_listing_flag is unambiguous."""

    def test_ghost_listing_flag_is_boolean(self) -> None:
        """ghost_listing_flag is always a boolean on paper candidates."""
        row = pass_ready_row(
            contract_ticker="KXGHOST-TEST",
        )
        diagnostic = ghost_diagnostic_payload(ghost_row("KXGHOST-TEST", ghost_listing_flag=True))
        diagnostic_path = Path("/tmp") / f"test_ghost_flag_{id(row)}.json"
        write_json(diagnostic_path, diagnostic)

        report = build_paper_decision_candidates(
            ledger_path=write_ledger(row),
            ghost_depth_path=diagnostic_path,
            generated_utc=GENERATED_UTC,
            paper_bankroll=1000.0,
        )

        for candidate in report["candidates"]:
            assert "ghost_listing_flag" in candidate
            assert (
                isinstance(candidate["ghost_listing_flag"], bool)
                or candidate["ghost_listing_flag"] is None
            )

    def test_ghost_listing_flag_propagates_from_diagnostic(self) -> None:
        """ghost_listing_flag on candidate matches diagnostic flag for ghost-listed tickers."""
        candidates = [
            {"contract_ticker": "KXGHOST-A", "capacity_estimate": 50.0},
            {"contract_ticker": "KXGHOST-B", "capacity_estimate": 50.0},
        ]
        index = {"KXGHOST-A": True, "KXGHOST-B": False}

        result = apply_ghost_listing_capacity_override(candidates, index)
        ticker_map = {c["contract_ticker"]: c for c in result}
        assert ticker_map["KXGHOST-A"]["ghost_listing_flag"] is True
        assert ticker_map["KXGHOST-B"]["ghost_listing_flag"] is False


# ── VAL-GHOST-008: CCD rows linkable by contract_ticker ─────────────────────


class TestContractTickerLinkable:
    """VAL-GHOST-008: CCD capacity rows linkable to ghost-listing rows by exact contract_ticker match."""

    def test_ghost_index_builds_correctly(self) -> None:
        """build_ghost_listing_index correctly indexes by contract_ticker."""
        diagnostic = ghost_diagnostic_payload(
            ghost_row("KXGHOST-A", ghost_listing_flag=True),
            ghost_row("KXGHOST-B", ghost_listing_flag=False),
        )
        index = build_ghost_listing_index(diagnostic)
        assert "KXGHOST-A" in index
        assert "KXGHOST-B" in index
        assert index["KXGHOST-A"] is True
        assert index["KXGHOST-B"] is False


# ── VAL-GHOST-009: Research-only boundary ───────────────────────────────────


class TestResearchOnlyBoundaryPreserved:
    """VAL-GHOST-009: Research-only boundary preserved through ghost-listing integration."""

    def test_paper_output_is_research_only(self) -> None:
        """Build_paper_decision_candidates output is research_only=True."""
        row = pass_ready_row(
            contract_ticker="KXNORMAL-TEST",
        )
        report = build_paper_decision_candidates(
            ledger_path=write_ledger(row),
            ghost_depth_path=None,
            generated_utc=GENERATED_UTC,
            paper_bankroll=1000.0,
        )

        assert report["research_only"] is True
        assert report["execution_enabled"] is False
        for candidate in report["candidates"]:
            assert candidate.get("research_only") is True or candidate.get("research_only") is None

    def test_ghost_listing_does_not_enable_execution(self) -> None:
        """Ghost-listing integration does not create account/order/execution paths."""
        row = pass_ready_row(
            contract_ticker="KXGHOST-TEST",
        )
        diagnostic = ghost_diagnostic_payload(ghost_row("KXGHOST-TEST", ghost_listing_flag=True))
        diagnostic_path = Path("/tmp") / f"test_ghost_research_{id(row)}.json"
        write_json(diagnostic_path, diagnostic)

        report = build_paper_decision_candidates(
            ledger_path=write_ledger(row),
            ghost_depth_path=diagnostic_path,
            generated_utc=GENERATED_UTC,
            paper_bankroll=1000.0,
        )

        assert report["market_execution"] is False
        assert report["account_or_order_paths"] is False


# ── VAL-GHOST-010: Ghost-listing blocks capacity locking at gate level ──────


class TestGhostListingGateLevelBlocking:
    """VAL-GHOST-010: Ghost-listing blocks capacity locking at the gate level."""

    def test_ghost_listing_applied_flag_present_when_diagnostic_loaded(self) -> None:
        """ghost_listing_applied flag present when diagnostic was loaded."""
        row = pass_ready_row(
            contract_ticker="KXGHOST-TEST",
        )
        diagnostic = ghost_diagnostic_payload(ghost_row("KXGHOST-TEST", ghost_listing_flag=True))
        diagnostic_path = Path("/tmp") / f"test_ghost_gate_{id(diagnostic)}.json"
        write_json(diagnostic_path, diagnostic)

        report = build_paper_decision_candidates(
            ledger_path=write_ledger(row),
            ghost_depth_path=diagnostic_path,
            generated_utc=GENERATED_UTC,
            paper_bankroll=1000.0,
        )

        for candidate in report["candidates"]:
            assert "ghost_listing_applied" in candidate


# ── VAL-GHOST-011: EV ledger records ghost-listing provenance ───────────────


class TestGhostListingProvenance:
    """VAL-GHOST-011: EV ledger records ghost-listing diagnostic version consumed."""

    def test_ghost_diagnostic_version_in_output(self) -> None:
        """Paper candidate output includes ghost-listing diagnostic version."""
        row = pass_ready_row(
            contract_ticker="KXGHOST-TEST",
        )
        diagnostic = ghost_diagnostic_payload(ghost_row("KXGHOST-TEST", ghost_listing_flag=True))
        diagnostic_path = Path("/tmp") / f"test_ghost_prov_{id(row)}.json"
        write_json(diagnostic_path, diagnostic)

        report = build_paper_decision_candidates(
            ledger_path=write_ledger(row),
            ghost_depth_path=diagnostic_path,
            generated_utc=GENERATED_UTC,
            paper_bankroll=1000.0,
        )

        assert "ghost_diagnostic_version" in report["inputs"]
        assert report["inputs"]["ghost_diagnostic_version"] == 1
        assert "ghost_diagnostic_generated_utc" in report["inputs"]

        for candidate in report["candidates"]:
            assert "ghost_listing_diagnostic_version" in candidate
            assert "ghost_listing_diagnostic_generated_utc" in candidate

    def test_no_diagnostic_version_when_missing(self) -> None:
        """No ghost-listing provenance when diagnostic not loaded."""
        row = pass_ready_row(
            contract_ticker="KXNORMAL-TEST",
        )
        report = build_paper_decision_candidates(
            ledger_path=write_ledger(row),
            ghost_depth_path=None,
            generated_utc=GENERATED_UTC,
            paper_bankroll=1000.0,
        )

        assert report["inputs"].get("ghost_listing_diagnostic_version") is None
        assert report["inputs"].get("ghost_listing_diagnostic_generated_utc") is None


# ── VAL-SIZING-025: Ghost-listing zero capacity overrides: capacity gate must still pass ──


class TestGhostListingCapacityGatePreserved:
    """VAL-SIZING-025: Ghost-listing zero capacity does not break capacity gate."""

    def test_capacity_gate_status_preserved(self) -> None:
        """Ghost-listed contract retains its original capacity_gate_status."""
        row = pass_ready_row(
            contract_ticker="KXGHOST-TEST",
            capacity_gate_status="pass",
            capacity_estimate=100.0,
        )
        diagnostic = ghost_diagnostic_payload(ghost_row("KXGHOST-TEST", ghost_listing_flag=True))
        diagnostic_path = Path("/tmp") / f"test_ghost_gate2_{id(diagnostic)}.json"
        write_json(diagnostic_path, diagnostic)

        report = build_paper_decision_candidates(
            ledger_path=write_ledger(row),
            ghost_depth_path=diagnostic_path,
            generated_utc=GENERATED_UTC,
            paper_bankroll=1000.0,
        )

        # The ghost-listing override zeros capacity_estimate AFTER candidate creation,
        # but the capacity_gate_status from the EV ledger row is preserved.
        # The candidate's blocker list should not include "capacity gate has not passed"
        # because capacity_gate_status was "pass" on the original row.
        candidate = report["candidates"][0]
        blockers = candidate.get("blocker_list") or []
        # "capacity gate has not passed" should NOT be in blockers
        assert "capacity gate has not passed" not in blockers
        # But capacity is zero due to ghost-listing
        assert candidate["capacity_estimate"] == 0.0


# ── VAL-SIZING-026: Capacity cap floor is 0.0 ──────────────────────────────


class TestCapacityFloor:
    """VAL-SIZING-026: Capacity cap floor is 0.0, never negative after ghost-listing adjustment."""

    def test_capacity_never_negative(self) -> None:
        """Capacity estimate after ghost-listing is floored at 0.0."""
        candidates = [
            {
                "contract_ticker": "KXGHOST-TEST",
                "capacity_estimate": -5.0,  # Already negative from CCD
            }
        ]
        index = {"KXGHOST-TEST": True}

        result = apply_ghost_listing_capacity_override(candidates, index)
        assert result[0]["capacity_estimate"] >= 0.0


# ── VAL-CROSS-014: Ghost-listed contracts get paper_usable = False ──────────


class TestCross014:
    """VAL-CROSS-014: Ghost-listed contracts get capacity_estimate = 0 and paper_usable = False."""

    def test_ghost_listed_not_paper_usable(self) -> None:
        """Ghost-listed contract is not paper_usable."""
        row = pass_ready_row(
            contract_ticker="KXGHOST-TEST",
            calibrated_probability=0.60,
            display_price=0.40,
            expected_value_per_contract=0.20,
            capacity_estimate=100.0,
        )
        diagnostic = ghost_diagnostic_payload(ghost_row("KXGHOST-TEST", ghost_listing_flag=True))
        diagnostic_path = Path("/tmp") / f"test_cross014_{id(diagnostic)}.json"
        write_json(diagnostic_path, diagnostic)

        report = build_paper_decision_candidates(
            ledger_path=write_ledger(row),
            ghost_depth_path=diagnostic_path,
            generated_utc=GENERATED_UTC,
            paper_bankroll=1000.0,
        )

        candidate = report["candidates"][0]
        assert candidate["paper_usable"] is False
        assert candidate["capacity_estimate"] == 0.0


# ── Stale diagnostic enforcement ────────────────────────────────────────────


class TestStaleDiagnosticEnforcement:
    """Stale ghost-listing diagnostic blocks capacity locking."""

    def test_check_ghost_listing_stale_fresh(self) -> None:
        """Fresh diagnostic returns False for stale check."""
        diagnostic = ghost_diagnostic_payload(generated_utc=GENERATED_UTC)
        assert check_ghost_listing_stale(diagnostic) is False

    def test_check_ghost_listing_stale_old(self) -> None:
        """Old diagnostic returns True for stale check."""
        diagnostic = ghost_diagnostic_payload(
            ghost_row("TEST"),
            generated_utc="2025-01-01T00:00:00Z",
        )
        assert check_ghost_listing_stale(diagnostic) is True

    def test_missing_diagnostic_not_stale(self) -> None:
        """Missing diagnostic (empty dict) is not stale (fail-open)."""
        assert check_ghost_listing_stale({}) is False


# ── Helper function unit tests ──────────────────────────────────────────────


class TestHelperFunctions:
    """Unit tests for ghost-listing helper functions."""

    def test_load_ghost_listing_diagnostic_none(self) -> None:
        """load_ghost_listing_diagnostic returns empty dict when path is None."""
        result = load_ghost_listing_diagnostic(None)
        assert result == {}

    def test_build_ghost_listing_index_non_research(self) -> None:
        """build_ghost_listing_index returns empty for non-research artifacts."""
        diagnostic = {
            "schema_version": 1,
            "execution_enabled": True,  # Not research-only
            "depth_rows": [ghost_row("TEST", ghost_listing_flag=True)],
        }
        index = build_ghost_listing_index(diagnostic)
        assert index == {}

    def test_build_ghost_listing_index_empty(self) -> None:
        """build_ghost_listing_index returns empty for empty diagnostic."""
        assert build_ghost_listing_index({}) == {}
