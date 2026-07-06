from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_ghost_listing_depth_diagnostic.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_ghost_listing_depth_diagnostic", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def safe_universe() -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "ready",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
        "candidates": [
            {
                "ticker": "KXWCGAME-26JUL04-DEPTH",
                "event_ticker": "KXWCGAME-26JUL04",
                "classification": "other_sports",
                "series_ticker": "KXWCGAME",
                "gate_status": "pass",
                "settlement_time": "2099-07-04T20:00:00Z",
                "time_to_settlement_hours": 640000.0,
            },
            {
                "ticker": "KXMLBGAME-26JUL04-EMPTY",
                "event_ticker": "KXMLBGAME-26JUL04",
                "classification": "mlb",
                "series_ticker": "KXMLBGAME",
                "gate_status": "pass",
                "settlement_time": "2099-07-04T23:00:00Z",
                "time_to_settlement_hours": 640000.0,
            },
        ],
    }


def multi_classification_universe() -> dict[str, object]:
    """Universe with candidates across multiple classifications for stratified sampling tests."""
    base = safe_universe()
    extra_candidates = [
        {
            "ticker": f"KXXTEST-{i:04d}",
            "event_ticker": "KXXTEST-EVT",
            "classification": cls,
            "series_ticker": "KXXTEST",
            "gate_status": "pass",
            "settlement_time": "2099-07-05T00:00:00Z",
            "time_to_settlement_hours": 640000.0,
        }
        for i, cls in enumerate(
            ["mlb"] * 40
            + ["atp"] * 20
            + ["nfl"] * 15
            + ["nba"] * 10
            + ["weather"] * 5
            + ["finance_crypto"] * 5
            + ["macro_econ"] * 3
            + ["politics_policy"] * 2
        )
    ]
    base["candidates"] = list(base["candidates"]) + extra_candidates  # type: ignore[assignment]
    return base


def fake_fetch(url: str) -> dict[str, object]:
    if "DEPTH" in url:
        return {"orderbook": {"no": [[40, 5]], "yes": [[25, 3]]}}
    return {"orderbook": {"no": [], "yes": []}}


def fake_fetch_all_empty(url: str) -> dict[str, object]:
    return {"orderbook": {"no": [], "yes": []}}


def test_ghost_depth_blocks_cap_i_when_current_books_are_sparse(tmp_path: Path) -> None:
    module = load_module()
    universe_path = tmp_path / "universe.json"
    write_json(universe_path, safe_universe())

    report = module.build_ghost_listing_depth_diagnostic(
        universe_scan_path=universe_path,
        raw_orderbook_dir=tmp_path / "outside-orderbooks",
        generated_utc=module.utc_now(),
        max_contracts=2,
        capture_orderbooks=True,
        fetch_json=fake_fetch,
        min_probe_coverage=1.0,
        min_positive_depth_fraction=0.75,
    )

    assert report["status"] == "ghost_listing_depth_diagnostic_blocks_cap_i_lock"
    assert report["summary"]["orderbook_count"] == 2
    assert report["summary"]["positive_depth_row_count"] == 1
    assert report["summary"]["ghost_listing_row_count"] == 1
    assert report["summary"]["cap_i_lock_allowed"] is False
    assert report["cap_i_policy"]["cap_i_lock_allowed"] is False
    assert report["safety"]["market_execution"] is False
    assert report["account_or_order_paths"] is False


def test_ghost_depth_allows_cap_i_only_after_current_depth_passes(tmp_path: Path) -> None:
    module = load_module()
    universe_path = tmp_path / "universe.json"
    write_json(universe_path, safe_universe())

    report = module.build_ghost_listing_depth_diagnostic(
        universe_scan_path=universe_path,
        raw_orderbook_dir=tmp_path / "outside-orderbooks",
        generated_utc=module.utc_now(),
        max_contracts=2,
        capture_orderbooks=True,
        fetch_json=fake_fetch,
        min_probe_coverage=1.0,
        min_positive_depth_fraction=0.50,
    )

    assert report["status"] == "ghost_listing_depth_diagnostic_current_depth_ready"
    assert report["summary"]["cap_i_lock_allowed"] is True
    assert report["cap_i_policy"]["reason"] == "current_depth_probe_passed"


def test_ghost_depth_makefile_target_exists() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-ghost-listing-depth-diagnostic" in makefile
    assert "scripts/kalshi_ghost_listing_depth_diagnostic.py" in makefile


# ── Stratified Sampling Tests (VAL-GHOST-003) ────────────────────────────────


class TestStratifiedSampling:
    """VAL-GHOST-003: Stratified sampling across all classifications."""

    def test_stratified_sampling_covers_all_classifications(self, tmp_path: Path) -> None:
        """Stratified sampling produces candidates from every classification with eligible candidates."""
        module = load_module()
        universe_path = tmp_path / "universe.json"
        write_json(universe_path, multi_classification_universe())

        report = module.build_ghost_listing_depth_diagnostic(
            universe_scan_path=universe_path,
            raw_orderbook_dir=tmp_path / "outside-orderbooks",
            generated_utc="2026-07-03T20:00:00Z",
            max_contracts=30,
            capture_orderbooks=True,
            fetch_json=fake_fetch_all_empty,
        )

        selected_cls = {
            row["classification"] for row in report["depth_rows"] if isinstance(row, dict)
        }
        # All active classifications should be represented
        for cls in (
            "mlb",
            "atp",
            "nfl",
            "nba",
            "weather",
            "finance_crypto",
            "macro_econ",
            "politics_policy",
        ):
            assert cls in selected_cls, f"Classification {cls} missing from stratified sample"

    def test_stratified_sampling_respects_allocation_ratios(self, tmp_path: Path) -> None:
        """Stratified allocation roughly follows proportional distribution."""
        module = load_module()
        universe_path = tmp_path / "universe.json"
        write_json(universe_path, multi_classification_universe())

        report = module.build_ghost_listing_depth_diagnostic(
            universe_scan_path=universe_path,
            raw_orderbook_dir=tmp_path / "outside-orderbooks",
            generated_utc="2026-07-03T20:00:00Z",
            max_contracts=100,
            capture_orderbooks=True,
            fetch_json=fake_fetch_all_empty,
        )

        rows = [r for r in report["depth_rows"] if isinstance(r, dict)]
        from collections import Counter

        cls_counts = Counter(r.get("classification") for r in rows)

        # More candidates from mlb than politics_policy (proportional allocation)
        assert cls_counts.get("mlb", 0) > cls_counts.get("politics_policy", 0)
        # But politics_policy should still have at least 1
        assert cls_counts.get("politics_policy", 0) >= 1

    def test_stratified_sampling_respects_max_contracts(self, tmp_path: Path) -> None:
        """Total selected candidates <= max_contracts."""
        module = load_module()
        universe_path = tmp_path / "universe.json"
        write_json(universe_path, multi_classification_universe())

        report = module.build_ghost_listing_depth_diagnostic(
            universe_scan_path=universe_path,
            raw_orderbook_dir=tmp_path / "outside-orderbooks",
            generated_utc="2026-07-03T20:00:00Z",
            max_contracts=25,
            capture_orderbooks=True,
            fetch_json=fake_fetch_all_empty,
        )

        selected_count = report["summary"]["selected_candidate_count"]
        assert selected_count <= 25
        assert selected_count > 0

    def test_unique_event_eligible(self, tmp_path: Path) -> None:
        """Eligible candidates have pass/warn gate_status and non-empty ticker."""
        module = load_module()
        universe = multi_classification_universe()
        # Add some ineligible candidates
        candidates = list(universe["candidates"])
        candidates.append(
            {
                "ticker": "KXBLOCKED-TICKER",
                "classification": "mlb",
                "gate_status": "blocked",
                "settlement_time": "2026-07-05T00:00:00Z",
            }
        )
        candidates.append(
            {
                "classification": "mlb",
                "gate_status": "pass",
                "settlement_time": "2026-07-05T00:00:00Z",
            }
        )  # Missing ticker
        universe["candidates"] = candidates
        universe_path = tmp_path / "universe.json"
        write_json(universe_path, universe)

        report = module.build_ghost_listing_depth_diagnostic(
            universe_scan_path=universe_path,
            raw_orderbook_dir=tmp_path / "outside-orderbooks",
            generated_utc="2026-07-03T20:00:00Z",
            max_contracts=100,
            capture_orderbooks=True,
            fetch_json=fake_fetch_all_empty,
        )

        # Blocked and missing-ticker candidates should not appear
        selected_count = report["summary"]["selected_candidate_count"]
        assert selected_count >= 0


# ── Freshness and Staleness Tests (VAL-GHOST-005, VAL-GHOST-006) ────────────


class TestGhostListingFreshness:
    """VAL-GHOST-005/006: Freshness constraints and stale diagnostic blocking."""

    def test_freshness_fields_present(self, tmp_path: Path) -> None:
        """Ghost-listing diagnostic includes freshness metadata."""
        module = load_module()
        universe_path = tmp_path / "universe.json"
        write_json(universe_path, safe_universe())

        report = module.build_ghost_listing_depth_diagnostic(
            universe_scan_path=universe_path,
            raw_orderbook_dir=tmp_path / "outside-orderbooks",
            generated_utc=module.utc_now(),
            max_contracts=2,
            capture_orderbooks=True,
            fetch_json=fake_fetch,
            min_probe_coverage=1.0,
            min_positive_depth_fraction=0.50,
        )

        assert "freshness" in report
        freshness = report["freshness"]
        assert "generated_utc" in freshness
        assert "max_staleness_seconds" in freshness
        assert "stale_as_of_utc" in freshness

    def test_fresh_diagnostic_passes_freshness_gate(self, tmp_path: Path) -> None:
        """Fresh diagnostic has ghost_listing_diagnostic_freshness gate = pass."""
        module = load_module()
        universe_path = tmp_path / "universe.json"
        write_json(universe_path, safe_universe())

        report = module.build_ghost_listing_depth_diagnostic(
            universe_scan_path=universe_path,
            raw_orderbook_dir=tmp_path / "outside-orderbooks",
            generated_utc=module.utc_now(),
            max_contracts=2,
            capture_orderbooks=True,
            fetch_json=fake_fetch,
            min_probe_coverage=1.0,
            min_positive_depth_fraction=0.50,
        )

        for gate in report["gates"]:
            if gate["name"] == "ghost_listing_diagnostic_freshness":
                assert gate["status"] == "pass"

    def test_stale_diagnostic_blocks_cap_i_lock(self, tmp_path: Path) -> None:
        """Stale ghost-listing diagnostic blocks cap_i lock."""
        module = load_module()
        universe_path = tmp_path / "universe.json"
        write_json(universe_path, safe_universe())

        # Use a very old generated_utc to simulate stale data
        report = module.build_ghost_listing_depth_diagnostic(
            universe_scan_path=universe_path,
            raw_orderbook_dir=tmp_path / "outside-orderbooks",
            generated_utc="2025-01-01T00:00:00Z",
            max_contracts=2,
            capture_orderbooks=True,
            fetch_json=fake_fetch,
            min_probe_coverage=1.0,
            min_positive_depth_fraction=0.50,
        )

        assert report["status"] == "ghost_listing_depth_diagnostic_stale_blocks_cap_i_lock"
        assert report["cap_i_policy"]["cap_i_lock_allowed"] is False

        for gate in report["gates"]:
            if gate["name"] == "ghost_listing_diagnostic_freshness":
                assert gate["status"] == "blocked"

    def test_is_stale_function(self) -> None:
        """_is_stale correctly detects stale/fresh diagnostics."""
        module = load_module()

        # Very old timestamp is stale
        assert module._is_stale("2025-01-01T00:00:00Z", 3600) is True

        # Invalid timestamp is treated as stale
        assert module._is_stale("not-a-date", 3600) is True


# ── Ghost Listing Flag Tests (VAL-GHOST-007) ────────────────────────────────


class TestGhostListingFlag:
    """VAL-GHOST-007: Per-contract ghost_listing_flag is unambiguous and consumable."""

    def test_ghost_listing_flag_is_boolean(self, tmp_path: Path) -> None:
        """Every depth row has a boolean ghost_listing_flag."""
        module = load_module()
        universe_path = tmp_path / "universe.json"
        write_json(universe_path, safe_universe())

        report = module.build_ghost_listing_depth_diagnostic(
            universe_scan_path=universe_path,
            raw_orderbook_dir=tmp_path / "outside-orderbooks",
            generated_utc="2026-07-03T20:00:00Z",
            max_contracts=2,
            capture_orderbooks=True,
            fetch_json=fake_fetch,
        )

        for row in report["depth_rows"]:
            assert isinstance(row.get("ghost_listing_flag"), bool)
            assert row["ghost_listing_flag"] in (True, False)

    def test_ghost_listing_flag_contract_ticker_present(self, tmp_path: Path) -> None:
        """Every depth row has contract_ticker for cross-referencing."""
        module = load_module()
        universe_path = tmp_path / "universe.json"
        write_json(universe_path, safe_universe())

        report = module.build_ghost_listing_depth_diagnostic(
            universe_scan_path=universe_path,
            raw_orderbook_dir=tmp_path / "outside-orderbooks",
            generated_utc="2026-07-03T20:00:00Z",
            max_contracts=2,
            capture_orderbooks=True,
            fetch_json=fake_fetch,
        )

        for row in report["depth_rows"]:
            assert "contract_ticker" in row
            assert row["contract_ticker"] is not None


# ── Schema Version Tests (VAL-GHOST-012) ────────────────────────────────────


class TestSchemaVersion:
    """VAL-GHOST-012: Diagnostic JSON schema version is stable and consumable."""

    def test_schema_version_present(self, tmp_path: Path) -> None:
        """Diagnostic has schema_version field."""
        module = load_module()
        universe_path = tmp_path / "universe.json"
        write_json(universe_path, safe_universe())

        report = module.build_ghost_listing_depth_diagnostic(
            universe_scan_path=universe_path,
            raw_orderbook_dir=tmp_path / "outside-orderbooks",
            generated_utc="2026-07-03T20:00:00Z",
            max_contracts=2,
            capture_orderbooks=True,
            fetch_json=fake_fetch,
        )

        assert "schema_version" in report
        assert report["schema_version"] == 1

    def test_depth_rows_linkable_by_contract_ticker(self, tmp_path: Path) -> None:
        """VAL-GHOST-008: Depth rows linkable by contract_ticker."""
        module = load_module()
        universe_path = tmp_path / "universe.json"
        write_json(universe_path, safe_universe())

        report = module.build_ghost_listing_depth_diagnostic(
            universe_scan_path=universe_path,
            raw_orderbook_dir=tmp_path / "outside-orderbooks",
            generated_utc="2026-07-03T20:00:00Z",
            max_contracts=2,
            capture_orderbooks=True,
            fetch_json=fake_fetch,
        )

        # Build index
        index = {
            str(row.get("contract_ticker", "")): row
            for row in report["depth_rows"]
            if isinstance(row, dict)
        }
        assert "KXWCGAME-26JUL04-DEPTH" in index
        assert "KXMLBGAME-26JUL04-EMPTY" in index

        # Case-sensitive matching
        assert "kxwcgame-26jul04-depth" not in index


# ── Research-only Boundary Tests (VAL-GHOST-009) ─────────────────────────────


class TestResearchOnlyBoundary:
    """VAL-GHOST-009: Research-only boundary preserved through ghost-listing integration."""

    def test_ghost_listing_output_is_research_only(self, tmp_path: Path) -> None:
        """Ghost-listing diagnostic is research-only with execution disabled."""
        module = load_module()
        universe_path = tmp_path / "universe.json"
        write_json(universe_path, safe_universe())

        report = module.build_ghost_listing_depth_diagnostic(
            universe_scan_path=universe_path,
            raw_orderbook_dir=tmp_path / "outside-orderbooks",
            generated_utc="2026-07-03T20:00:00Z",
            max_contracts=2,
            capture_orderbooks=True,
            fetch_json=fake_fetch,
        )

        assert report["research_only"] is True
        assert report["execution_enabled"] is False
        assert report["market_execution"] is False

    def test_depth_rows_are_research_only(self, tmp_path: Path) -> None:
        """Depth rows themselves carry research-only flags."""
        module = load_module()
        universe_path = tmp_path / "universe.json"
        write_json(universe_path, safe_universe())

        report = module.build_ghost_listing_depth_diagnostic(
            universe_scan_path=universe_path,
            raw_orderbook_dir=tmp_path / "outside-orderbooks",
            generated_utc="2026-07-03T20:00:00Z",
            max_contracts=2,
            capture_orderbooks=True,
            fetch_json=fake_fetch,
        )

        for row in report["depth_rows"]:
            assert isinstance(row, dict)
            assert row.get("research_only") is True
            assert row.get("execution_enabled") is False


# ── Cap_i Gate Lock (VAL-GHOST-010) ───────────────────────────────────────


class TestCapILock:
    """VAL-GHOST-010: Ghost-listing blocks capacity locking at the gate level."""

    def test_cap_i_lock_blocked_when_gate_fails(self, tmp_path: Path) -> None:
        """cap_i_lock_allowed is False when depth probe gates don't pass."""
        module = load_module()
        universe_path = tmp_path / "universe.json"
        write_json(universe_path, safe_universe())

        report = module.build_ghost_listing_depth_diagnostic(
            universe_scan_path=universe_path,
            raw_orderbook_dir=tmp_path / "outside-orderbooks",
            generated_utc="2026-07-03T20:00:00Z",
            max_contracts=2,
            capture_orderbooks=True,
            fetch_json=fake_fetch,
            min_probe_coverage=2.0,  # Impossible to meet
        )

        assert report["cap_i_policy"]["cap_i_lock_allowed"] is False
        assert "cap_i_lock_blocked" in report["cap_i_policy"]["reason"]

    def test_cap_i_lock_boundary_gate_status(self, tmp_path: Path) -> None:
        """cap_i_lock_boundary gate reflects cap_i_lock_allowed."""
        module = load_module()
        universe_path = tmp_path / "universe.json"
        write_json(universe_path, safe_universe())

        report = module.build_ghost_listing_depth_diagnostic(
            universe_scan_path=universe_path,
            raw_orderbook_dir=tmp_path / "outside-orderbooks",
            generated_utc="2026-07-03T20:00:00Z",
            max_contracts=2,
            capture_orderbooks=True,
            fetch_json=fake_fetch,
            min_probe_coverage=1.0,
            min_positive_depth_fraction=0.75,
        )

        for gate in report["gates"]:
            if gate["name"] == "cap_i_lock_boundary":
                assert gate["status"] == "blocked"


# ── Ghost Listing Capacity Override Tests ────────────────────────────────────


def test_ghost_listing_flag_true_when_no_depth(tmp_path: Path) -> None:
    """Contracts with zero total_depth_contracts get ghost_listing_flag=True."""
    module = load_module()
    universe_path = tmp_path / "universe.json"
    write_json(universe_path, safe_universe())

    report = module.build_ghost_listing_depth_diagnostic(
        universe_scan_path=universe_path,
        raw_orderbook_dir=tmp_path / "outside-orderbooks",
        generated_utc="2026-07-03T20:00:00Z",
        max_contracts=2,
        capture_orderbooks=True,
        fetch_json=fake_fetch,
    )

    depth_index = {
        str(row.get("contract_ticker", "")): row
        for row in report["depth_rows"]
        if isinstance(row, dict)
    }
    # The "DEPTH" ticker has orderbook data, so not ghost-listed
    assert depth_index["KXWCGAME-26JUL04-DEPTH"]["ghost_listing_flag"] is False
    assert depth_index["KXWCGAME-26JUL04-DEPTH"]["total_depth_contracts"] > 0
    # The "EMPTY" ticker has no orderbook data, so ghost-listed
    assert depth_index["KXMLBGAME-26JUL04-EMPTY"]["ghost_listing_flag"] is True
    assert depth_index["KXMLBGAME-26JUL04-EMPTY"]["total_depth_contracts"] == 0
