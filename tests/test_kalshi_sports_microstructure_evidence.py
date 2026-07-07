from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


def load_script(name: str):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def safe_universe(settlement_time: str = "2026-07-04T03:00:00Z") -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "universe_scan_ready_with_model_routes",
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
                "ticker": "KXWCGAME-26JUL04-USA-USA",
                "event_ticker": "KXWCGAME-26JUL04-USA",
                "series_ticker": "KXWCGAME",
                "classification": "other_sports",
                "gate_status": "pass",
                "settlement_time": settlement_time,
            }
        ],
    }


def sports_candidate(
    ticker: str,
    *,
    classification: str,
    series_ticker: str,
    settlement_time: str,
    yes_bid: float | None = None,
    yes_ask: float | None = None,
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "event_ticker": ticker.rsplit("-", maxsplit=1)[0],
        "series_ticker": series_ticker,
        "classification": classification,
        "gate_status": "pass",
        "settlement_time": settlement_time,
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "volume": 10_000.0 if yes_bid is not None and yes_ask is not None else None,
        "open_interest": 5_000.0 if yes_bid is not None and yes_ask is not None else None,
    }


def fake_orderbook(_url: str) -> dict[str, object]:
    return {
        "orderbook_fp": {
            "yes_dollars": [["0.4500", "10"], ["0.4400", "5"]],
            "no_dollars": [["0.5200", "20"], ["0.5100", "8"]],
        }
    }


def test_selection_diversifies_quote_hinted_match_markets() -> None:
    module = load_script("kalshi_sports_microstructure_observation_loop")
    candidates = [
        sports_candidate(
            f"KXMLBHIT-26JUL05GAME-PLAYER{i}",
            classification="mlb",
            series_ticker="KXMLBHIT",
            settlement_time="2026-07-05T01:00:00Z",
        )
        for i in range(20)
    ]
    candidates.extend(
        sports_candidate(
            f"KXMLBGAME-26JUL05TEAM{i}-HOME",
            classification="mlb",
            series_ticker="KXMLBGAME",
            settlement_time="2026-07-05T10:00:00Z",
            yes_bid=0.48,
            yes_ask=0.52,
        )
        for i in range(6)
    )
    candidates.extend(
        sports_candidate(
            f"KXATPMATCH-26JUL05MATCH{i}-FAV",
            classification="atp",
            series_ticker="KXATPMATCH",
            settlement_time="2026-07-05T12:00:00Z",
            yes_bid=0.64,
            yes_ask=0.65,
        )
        for i in range(6)
    )
    universe = {
        "schema_version": 1,
        "status": "universe_scan_ready_with_model_routes",
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
        "candidates": candidates,
    }

    selected = module.select_current_sports_candidates(
        universe,
        generated_utc="2026-07-05T00:00:00Z",
        max_tickers=6,
        max_close_hours=48,
    )

    selected_tickers = [row["ticker"] for row in selected]
    assert any(str(ticker).startswith("KXATPMATCH") for ticker in selected_tickers)
    assert any(str(ticker).startswith("KXMLBGAME") for ticker in selected_tickers)
    assert not any(str(ticker).startswith("KXMLBHIT") for ticker in selected_tickers)
    assert {row["_sport_surface"] for row in selected} == {"mlb", "atp"}
    assert all(float(row["_quote_hint_score"]) > 0 for row in selected)


def fake_orderbook_touched(_url: str) -> dict[str, object]:
    return {
        "orderbook_fp": {
            "yes_dollars": [["0.4300", "10"], ["0.4200", "5"]],
            "no_dollars": [["0.5500", "20"], ["0.5400", "8"]],
        }
    }


# --- Depth metric invariant helpers ---


def make_observation_row(
    ticker: str,
    observed_at: str,
    yes_mid: float | None = 0.5,
    depth_imbalance: float | None = 0.0,
    yes_spread: float | None = 0.02,
) -> dict[str, object]:
    return {
        "snapshot_id": f"{ticker}-{observed_at}",
        "contract_ticker": ticker,
        "observed_at_utc": observed_at,
        "yes_mid": yes_mid,
        "depth_imbalance_yes": depth_imbalance,
        "yes_spread": yes_spread,
        "mid_delta_from_previous_snapshot": None,
        "label_status": None,
        "usable": False,
        "execution_enabled": False,
        "research_only": True,
    }


# --- Zero-candidate path test ---


def test_zero_candidates_graceful_blocked_status(tmp_path: Path) -> None:
    """Snapshot loop exits 0 with blocked status when no candidates exist."""
    module = load_script("kalshi_sports_microstructure_observation_loop")
    empty_universe = {
        "schema_version": 1,
        "status": "universe_scan_ready",
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
        "candidates": [],
    }
    universe_path = write_json(tmp_path / "universe.json", empty_universe)
    with tempfile.TemporaryDirectory(prefix="kalshi-microstructure-", dir="/tmp") as external_dir:
        external = Path(external_dir)
        report = module.build_sports_microstructure_observation_loop(
            universe_scan_path=universe_path,
            raw_orderbook_dir=external / "raw-orderbooks",
            observation_dir=external / "observations",
            settled_snapshot_path=external / "settled" / "latest.json",
            label_dir=external / "labels",
            generated_utc="2026-07-04T00:00:00Z",
            capture_orderbooks=True,
            fetch_json=fake_orderbook,
        )
    assert "blocked" in report["status"], (
        f"Status should contain 'blocked' but got {report['status']}"
    )
    assert report["summary"]["selected_candidate_count"] == 0
    assert report["summary"]["observation_row_count"] == 0
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    # current_sports_candidates_present gate must be blocked
    gates = {g["name"]: g for g in report["gates"]}
    assert gates["current_sports_candidates_present"]["status"] == "blocked"


def test_zero_candidates_with_no_orderbook_dir(tmp_path: Path) -> None:
    """Snapshot loop exits 0 even when orderbook dir doesn't exist and no candidates."""
    module = load_script("kalshi_sports_microstructure_observation_loop")
    empty_universe = {
        "schema_version": 1,
        "status": "universe_scan_ready",
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
        "candidates": [],
    }
    universe_path = write_json(tmp_path / "universe.json", empty_universe)
    # Use non-existent external dirs (no orderbook file exists)
    external = tmp_path / "nonexistent-external"
    report = module.build_sports_microstructure_observation_loop(
        universe_scan_path=universe_path,
        raw_orderbook_dir=external / "raw-orderbooks",
        observation_dir=external / "observations",
        settled_snapshot_path=external / "settled" / "latest.json",
        label_dir=external / "labels",
        generated_utc="2026-07-04T00:00:00Z",
        capture_orderbooks=False,
    )
    assert "blocked" in report["status"]
    assert report["summary"]["selected_candidate_count"] == 0
    assert report["summary"]["observation_row_count"] == 0
    assert report["summary"]["orderbook_count"] == 0


# --- Dedup tests ---


def test_dedup_observation_rows_by_composite_key(tmp_path: Path) -> None:
    """Snapshots deduped by (contract_ticker, observed_at_utc, snapshot_id) triple."""
    module = load_script("kalshi_sports_microstructure_observation_loop")

    # Two identical key triples should collapse to one
    rows = [
        make_observation_row("TICKER-A", "2026-07-04T00:00:00Z"),
        make_observation_row("TICKER-A", "2026-07-04T00:00:00Z"),
    ]
    deduped = module.dedupe_observation_rows(rows)
    assert len(deduped) == 1, f"Expected 1 row after dedup, got {len(deduped)}"

    # Different contract_ticker should produce 2 rows
    rows2 = [
        make_observation_row("TICKER-A", "2026-07-04T00:00:00Z"),
        make_observation_row("TICKER-B", "2026-07-04T00:00:00Z"),
    ]
    deduped2 = module.dedupe_observation_rows(rows2)
    assert len(deduped2) == 2, f"Expected 2 rows after dedup, got {len(deduped2)}"

    # Different observed_at_utc should produce 2 rows
    rows3 = [
        make_observation_row("TICKER-A", "2026-07-04T00:00:00Z"),
        make_observation_row("TICKER-A", "2026-07-04T01:00:00Z"),
    ]
    deduped3 = module.dedupe_observation_rows(rows3)
    assert len(deduped3) == 2, f"Expected 2 rows after dedup, got {len(deduped3)}"

    # Different snapshot_id should produce 2 rows (same ticker and time)
    rows4 = [
        dict(make_observation_row("TICKER-A", "2026-07-04T00:00:00Z"), snapshot_id="snap-1"),
        dict(make_observation_row("TICKER-A", "2026-07-04T00:00:00Z"), snapshot_id="snap-2"),
    ]
    deduped4 = module.dedupe_observation_rows(rows4)
    assert len(deduped4) == 2, f"Expected 2 rows with different snapshot_ids, got {len(deduped4)}"


def test_dedup_allows_historical_sequence(tmp_path: Path) -> None:
    """Multiple snapshots across times for the same ticker are preserved (forward pairs)."""
    module = load_script("kalshi_sports_microstructure_observation_loop")
    rows = [
        make_observation_row("TICKER-A", "2026-07-04T00:00:00Z"),
        make_observation_row("TICKER-A", "2026-07-04T00:01:00Z"),
        make_observation_row("TICKER-A", "2026-07-04T00:02:00Z"),
        make_observation_row("TICKER-B", "2026-07-04T00:00:00Z"),
    ]
    deduped = module.dedupe_observation_rows(rows)
    assert len(deduped) == 4, f"Expected 4 rows (3 timepoints + 1 other), got {len(deduped)}"


# --- Depth metric invariant tests ---


def test_depth_metric_invariants(tmp_path: Path) -> None:
    """Depth metrics satisfy invariants: imbalance in [-1,1], mid in [0,1], spread >= 0."""
    module = load_script("kalshi_sports_microstructure_observation_loop")
    universe_path = write_json(tmp_path / "universe.json", safe_universe())

    def extreme_orderbook(_url: str) -> dict[str, object]:
        return {
            "orderbook_fp": {
                # yes bids at extreme prices
                "yes_dollars": [["0.0100", "100"], ["0.0050", "50"]],
                # no bids at extreme prices
                "no_dollars": [["0.9900", "10"], ["0.9800", "5"]],
            }
        }

    with tempfile.TemporaryDirectory(prefix="kalshi-microstructure-", dir="/tmp") as external_dir:
        external = Path(external_dir)
        report = module.build_sports_microstructure_observation_loop(
            universe_scan_path=universe_path,
            raw_orderbook_dir=external / "raw-orderbooks",
            observation_dir=external / "observations",
            settled_snapshot_path=external / "settled" / "latest.json",
            label_dir=external / "labels",
            generated_utc="2026-07-04T00:00:00Z",
            capture_orderbooks=True,
            fetch_json=extreme_orderbook,
        )

    rows = report["observation_packet"]["rows"]
    assert len(rows) >= 1
    for row in rows:
        yes_mid = row.get("yes_mid")
        imbalance = row.get("depth_imbalance_yes")
        spread = row.get("yes_spread")
        total_depth = row.get("total_depth_contracts")

        if yes_mid is not None:
            assert 0.0 <= yes_mid <= 1.0, (
                f"yes_mid={yes_mid} not in [0, 1] for ticker {row.get('contract_ticker')}"
            )
        if imbalance is not None:
            assert -1.0 <= imbalance <= 1.0, (
                f"depth_imbalance_yes={imbalance} not in [-1, 1] for ticker {row.get('contract_ticker')}"
            )
        if spread is not None:
            assert spread >= 0, (
                f"yes_spread={spread} is negative for ticker {row.get('contract_ticker')}"
            )
        assert total_depth is None or total_depth >= 0, (
            f"total_depth_contracts={total_depth} is negative for ticker {row.get('contract_ticker')}"
        )


def test_mid_delta_null_for_first_observation(tmp_path: Path) -> None:
    """mid_delta_from_previous_snapshot is null for first observation of each contract."""
    module = load_script("kalshi_sports_microstructure_observation_loop")
    universe_path = write_json(tmp_path / "universe.json", safe_universe())

    with tempfile.TemporaryDirectory(prefix="kalshi-microstructure-", dir="/tmp") as external_dir:
        external = Path(external_dir)
        report = module.build_sports_microstructure_observation_loop(
            universe_scan_path=universe_path,
            raw_orderbook_dir=external / "raw-orderbooks",
            observation_dir=external / "observations",
            settled_snapshot_path=external / "settled" / "latest.json",
            label_dir=external / "labels",
            generated_utc="2026-07-04T00:00:00Z",
            capture_orderbooks=True,
            fetch_json=fake_orderbook,
        )

    rows = report["observation_packet"]["rows"]
    # Since this is the first call with no prior history and only one snapshot per ticker,
    # all mid_delta values should be None (no previous reference to compute delta)
    for row in rows:
        assert row.get("mid_delta_from_previous_snapshot") is None, (
            f"First observation should have null mid_delta for {row.get('contract_ticker')}, "
            f"got {row.get('mid_delta_from_previous_snapshot')}"
        )


# --- Forward quote pair count test ---


def test_forward_quote_pair_count_non_negative(tmp_path: Path) -> None:
    """forward_quote_pair_count is non-negative and tracked across runs."""
    module = load_script("kalshi_sports_microstructure_observation_loop")
    universe_path = write_json(tmp_path / "universe.json", safe_universe())

    with tempfile.TemporaryDirectory(prefix="kalshi-microstructure-", dir="/tmp") as external_dir:
        external = Path(external_dir)
        report1 = module.build_sports_microstructure_observation_loop(
            universe_scan_path=universe_path,
            raw_orderbook_dir=external / "raw-orderbooks",
            observation_dir=external / "observations",
            settled_snapshot_path=external / "settled" / "latest.json",
            label_dir=external / "labels",
            generated_utc="2026-07-04T00:00:00Z",
            capture_orderbooks=True,
            fetch_json=fake_orderbook,
        )
        module.write_outputs(
            report1, out_dir=tmp_path / "run1", observation_dir=external / "observations"
        )
        report2 = module.build_sports_microstructure_observation_loop(
            universe_scan_path=universe_path,
            raw_orderbook_dir=external / "raw-orderbooks",
            observation_dir=external / "observations",
            settled_snapshot_path=external / "settled" / "latest.json",
            label_dir=external / "labels",
            generated_utc="2026-07-04T00:01:00Z",
            capture_orderbooks=True,
            fetch_json=fake_orderbook_touched,
        )

    # forward_quote_pair_count should be >= 0
    assert report1["summary"]["forward_quote_pair_count"] >= 0
    assert report2["summary"]["forward_quote_pair_count"] >= 0

    # With two observations of the same contract, forward_quote_pair_count should be >= 1
    assert report2["summary"]["forward_quote_pair_count"] >= 1, (
        f"Expected forward_quote_pair_count >= 1, got {report2['summary']['forward_quote_pair_count']}"
    )

    # historical_observation_row_count should increase or stay same
    assert (
        report2["summary"]["historical_observation_row_count"]
        >= report1["summary"]["historical_observation_row_count"]
    )

    # repeated_snapshot_contract_count should be >= 1 after two runs
    assert report2["summary"]["repeated_snapshot_contract_count"] >= 1


def test_temp_microstructure_output_does_not_mutate_macro_latest(tmp_path: Path) -> None:
    module = load_script("kalshi_sports_microstructure_observation_loop")
    module.MACRO_DIR = tmp_path / "macro"
    universe_path = write_json(tmp_path / "universe.json", safe_universe())

    with tempfile.TemporaryDirectory(prefix="kalshi-microstructure-", dir="/tmp") as external_dir:
        external = Path(external_dir)
        report = module.build_sports_microstructure_observation_loop(
            universe_scan_path=universe_path,
            raw_orderbook_dir=external / "raw-orderbooks",
            observation_dir=external / "observations",
            settled_snapshot_path=external / "settled" / "latest.json",
            label_dir=external / "labels",
            generated_utc="2026-07-04T00:00:00Z",
            capture_orderbooks=True,
            fetch_json=fake_orderbook,
        )
        paths = module.write_outputs(
            report,
            out_dir=tmp_path / "not-macro" / "run1",
            observation_dir=external / "observations",
        )

    assert "latest_json_path" not in paths
    assert not (
        module.MACRO_DIR / "latest-kalshi-sports-microstructure-observation-loop.json"
    ).exists()


# --- Settlement label source test ---


def test_settlement_labels_source_is_public_kalshi(tmp_path: Path) -> None:
    """Settlement labels are sourced from public Kalshi settled market payloads."""
    micro = load_script("kalshi_sports_microstructure_observation_loop")
    universe_path = write_json(
        tmp_path / "universe.json", safe_universe(settlement_time="2026-07-04T00:01:00Z")
    )

    def fake_fetch(url: str) -> dict[str, object]:
        if "/orderbook" in url:
            return fake_orderbook(url)
        return {
            "market": {
                "ticker": "KXWCGAME-26JUL04-USA-USA",
                "result": "yes",
                "settlement_value_dollars": "1.0000",
                "close_time": "2026-07-04T00:01:00Z",
                "settlement_ts": "2026-07-04T00:03:00Z",
            }
        }

    with tempfile.TemporaryDirectory(prefix="kalshi-microstructure-", dir="/tmp") as external_dir:
        external = Path(external_dir)
        report1 = micro.build_sports_microstructure_observation_loop(
            universe_scan_path=universe_path,
            raw_orderbook_dir=external / "raw-orderbooks",
            observation_dir=external / "observations",
            settled_snapshot_path=external / "settled" / "latest.json",
            settled_raw_dir=external / "settled",
            label_dir=external / "labels",
            generated_utc="2026-07-04T00:00:00Z",
            capture_orderbooks=True,
            fetch_json=fake_fetch,
        )
        micro.write_outputs(
            report1, out_dir=tmp_path / "micro1", observation_dir=external / "observations"
        )
        report2 = micro.build_sports_microstructure_observation_loop(
            universe_scan_path=universe_path,
            raw_orderbook_dir=external / "raw-orderbooks",
            observation_dir=external / "observations",
            settled_snapshot_path=external / "settled" / "latest.json",
            settled_raw_dir=external / "settled",
            label_dir=external / "labels",
            generated_utc="2026-07-04T00:04:00Z",
            capture_orderbooks=True,
            probe_observed_public=True,
            fetch_json=fake_fetch,
        )

    # Verify label_source field
    for label_row in report2["label_packet"]["rows"]:
        assert label_row.get("label_source") == "public_kalshi_settled_market_payload", (
            f"Expected public_kalshi_settled_market_payload, got {label_row.get('label_source')}"
        )
    assert report2["summary"]["settled_market_count"] > 0
    assert report2["summary"]["label_row_count"] >= 1


# --- Blocked label status test ---


def test_blocked_label_rows_have_non_empty_status(tmp_path: Path) -> None:
    """Every blocked label row has a non-empty label_status field."""
    micro = load_script("kalshi_sports_microstructure_observation_loop")

    # Create observation rows that have no settled market (will be blocked)
    obs_rows = [
        make_observation_row("TICKER-UNSETTLED", "2026-07-04T00:00:00Z"),
    ]
    # Ensure snapshot_id is set
    for row in obs_rows:
        if not row.get("snapshot_id"):
            row["snapshot_id"] = f"{row['contract_ticker']}-{row['observed_at_utc']}"

    # Call label_observations with empty settled index (all rows will be blocked)
    _computed_labels, blocked_labels = micro.label_observations(obs_rows, {})

    # There should be blocked labels
    assert len(blocked_labels) >= 1
    for row in blocked_labels:
        assert row.get("label_status") is not None, "blocked label row has null label_status"
        assert len(str(row.get("label_status") or "")) > 0, (
            "blocked label row has empty label_status"
        )
        assert row["label_status"] in (
            "pending_contract_not_settled_in_snapshot",
            "settlement_outcome_missing",
        ), f"Unexpected label_status: {row['label_status']}"


# --- Network failure graceful test ---


def test_network_failure_graceful_blocked_status(tmp_path: Path) -> None:
    """Network/API failure during orderbook capture produces blocked status with descriptive reason."""
    module = load_script("kalshi_sports_microstructure_observation_loop")
    universe_path = write_json(tmp_path / "universe.json", safe_universe())

    # fetch_json that always raises (simulating network failure)
    def failing_fetch(_url: str) -> dict[str, object]:
        msg = "Connection refused"
        raise ConnectionError(msg)

    with tempfile.TemporaryDirectory(prefix="kalshi-microstructure-", dir="/tmp") as external_dir:
        external = Path(external_dir)
        report = module.build_sports_microstructure_observation_loop(
            universe_scan_path=universe_path,
            raw_orderbook_dir=external / "raw-orderbooks",
            observation_dir=external / "observations",
            settled_snapshot_path=external / "settled" / "latest.json",
            label_dir=external / "labels",
            generated_utc="2026-07-04T00:00:00Z",
            capture_orderbooks=True,
            fetch_json=failing_fetch,
        )

    assert "blocked" in report["status"], (
        f"Status should contain 'blocked' on network failure, got {report['status']}"
    )
    gates = {g["name"]: g for g in report["gates"]}
    assert gates["public_orderbooks_present"]["status"] == "blocked", (
        "public_orderbooks_present gate should be blocked"
    )
    assert len(gates["public_orderbooks_present"]["reason"]) > 0, (
        "Gate reason should be descriptive"
    )


# --- Raw payloads outside repo test ---


def test_raw_payloads_outside_repo_gate_passes(tmp_path: Path) -> None:
    """raw_payloads_outside_repo gate passes when external dirs are outside repo."""
    module = load_script("kalshi_sports_microstructure_observation_loop")
    universe_path = write_json(tmp_path / "universe.json", safe_universe())

    with tempfile.TemporaryDirectory(prefix="kalshi-microstructure-", dir="/tmp") as external_dir:
        external = Path(external_dir)
        report = module.build_sports_microstructure_observation_loop(
            universe_scan_path=universe_path,
            raw_orderbook_dir=external / "raw-orderbooks",
            observation_dir=external / "observations",
            settled_snapshot_path=external / "settled" / "latest.json",
            label_dir=external / "labels",
            generated_utc="2026-07-04T00:00:00Z",
            capture_orderbooks=True,
            fetch_json=fake_orderbook,
        )

    gates = {g["name"]: g for g in report["gates"]}
    assert gates["raw_payloads_outside_repo"]["status"] == "pass", (
        f"raw_payloads_outside_repo gate should pass, got {gates['raw_payloads_outside_repo']['status']}"
    )


def test_sports_microstructure_loop_emits_research_only_rows(tmp_path: Path) -> None:
    module = load_script("kalshi_sports_microstructure_observation_loop")
    universe_path = write_json(tmp_path / "universe.json", safe_universe())

    with tempfile.TemporaryDirectory(prefix="kalshi-microstructure-", dir="/tmp") as external_dir:
        external = Path(external_dir)
        report = module.build_sports_microstructure_observation_loop(
            universe_scan_path=universe_path,
            raw_orderbook_dir=external / "raw-orderbooks",
            observation_dir=external / "observations",
            settled_snapshot_path=external / "settled" / "latest.json",
            label_dir=external / "labels",
            generated_utc="2026-07-04T00:00:00Z",
            capture_orderbooks=True,
            fetch_json=fake_orderbook,
        )

    row = report["observation_packet"]["rows"][0]
    assert report["status"] == "sports_microstructure_observation_loop_ready"
    assert report["summary"]["observation_row_count"] == 1
    assert row["sport_surface"] == "world_cup_soccer"
    assert row["best_yes_bid"] == 0.45
    assert row["best_yes_ask"] == 0.48
    assert row["usable"] is False
    assert row["execution_enabled"] is False


def test_nondirectional_gates_block_until_real_labels(tmp_path: Path) -> None:
    micro = load_script("kalshi_sports_microstructure_observation_loop")
    flow = load_script("kalshi_near_resolution_informed_flow_evidence_gate")
    passive = load_script("kalshi_passive_liquidity_provision_evidence_gate")
    universe_path = write_json(tmp_path / "universe.json", safe_universe())
    with tempfile.TemporaryDirectory(prefix="kalshi-microstructure-", dir="/tmp") as external_dir:
        external = Path(external_dir)
        micro_report = micro.build_sports_microstructure_observation_loop(
            universe_scan_path=universe_path,
            raw_orderbook_dir=external / "raw-orderbooks",
            observation_dir=external / "observations",
            settled_snapshot_path=external / "settled" / "latest.json",
            label_dir=external / "labels",
            generated_utc="2026-07-04T00:00:00Z",
            capture_orderbooks=True,
            fetch_json=fake_orderbook,
        )
    micro_path = write_json(tmp_path / "micro.json", micro_report)

    flow_report = flow.build_near_resolution_informed_flow_evidence_gate(
        microstructure_path=micro_path,
        generated_utc="2026-07-04T00:01:00Z",
    )
    passive_report = passive.build_passive_liquidity_provision_evidence_gate(
        microstructure_path=micro_path,
        generated_utc="2026-07-04T00:01:00Z",
    )

    assert flow_report["status"] == "near_resolution_informed_flow_blocked_missing_settled_labels"
    assert flow_report["summary"]["flow_row_count"] == 1
    assert passive_report["status"] == (
        "passive_liquidity_provision_blocked_proxy_only_no_real_fill_labels"
    )
    assert passive_report["summary"]["virtual_order_count"] == 2
    assert passive_report["summary"]["real_fill_label_count"] == 0


def test_microstructure_history_creates_forward_and_touch_proxy_labels(tmp_path: Path) -> None:
    micro = load_script("kalshi_sports_microstructure_observation_loop")
    flow = load_script("kalshi_near_resolution_informed_flow_evidence_gate")
    passive = load_script("kalshi_passive_liquidity_provision_evidence_gate")
    universe_path = write_json(tmp_path / "universe.json", safe_universe())
    with tempfile.TemporaryDirectory(prefix="kalshi-microstructure-", dir="/tmp") as external_dir:
        external = Path(external_dir)
        report1 = micro.build_sports_microstructure_observation_loop(
            universe_scan_path=universe_path,
            raw_orderbook_dir=external / "raw-orderbooks",
            observation_dir=external / "observations",
            settled_snapshot_path=external / "settled" / "latest.json",
            label_dir=external / "labels",
            generated_utc="2026-07-04T00:00:00Z",
            capture_orderbooks=True,
            fetch_json=fake_orderbook,
        )
        micro.write_outputs(
            report1, out_dir=tmp_path / "micro1", observation_dir=external / "observations"
        )
        report2 = micro.build_sports_microstructure_observation_loop(
            universe_scan_path=universe_path,
            raw_orderbook_dir=external / "raw-orderbooks",
            observation_dir=external / "observations",
            settled_snapshot_path=external / "settled" / "latest.json",
            label_dir=external / "labels",
            generated_utc="2026-07-04T00:01:00Z",
            capture_orderbooks=True,
            fetch_json=fake_orderbook_touched,
        )
        micro_path = write_json(tmp_path / "micro.json", report2)
        flow_report = flow.build_near_resolution_informed_flow_evidence_gate(
            microstructure_path=micro_path,
            generated_utc="2026-07-04T00:02:00Z",
        )
        passive_report = passive.build_passive_liquidity_provision_evidence_gate(
            microstructure_path=micro_path,
            generated_utc="2026-07-04T00:02:00Z",
            ttl_seconds=180,
        )

    assert report2["summary"]["historical_observation_row_count"] == 2
    assert report2["summary"]["repeated_snapshot_contract_count"] == 1
    assert flow_report["summary"]["forward_quote_label_count"] == 1
    assert passive_report["summary"]["counterfactual_fill_proxy_label_count"] >= 1
    assert passive_report["summary"]["adverse_selection_window_count"] >= 1
    assert any(
        row["fill_proxy_status"] == "would_touch_within_ttl"
        for row in passive_report["virtual_order_rows"]
    )


def test_microstructure_exact_settlement_labels_join_from_public_kalshi_payload(
    tmp_path: Path,
) -> None:
    micro = load_script("kalshi_sports_microstructure_observation_loop")
    flow = load_script("kalshi_near_resolution_informed_flow_evidence_gate")
    universe_path = write_json(
        tmp_path / "universe.json", safe_universe(settlement_time="2026-07-04T00:01:00Z")
    )

    def fake_fetch(url: str) -> dict[str, object]:
        if "/orderbook" in url:
            return fake_orderbook(url)
        return {
            "market": {
                "ticker": "KXWCGAME-26JUL04-USA-USA",
                "result": "yes",
                "settlement_value_dollars": "1.0000",
                "close_time": "2026-07-04T00:01:00Z",
                "settlement_ts": "2026-07-04T00:03:00Z",
            }
        }

    with tempfile.TemporaryDirectory(prefix="kalshi-microstructure-", dir="/tmp") as external_dir:
        external = Path(external_dir)
        report1 = micro.build_sports_microstructure_observation_loop(
            universe_scan_path=universe_path,
            raw_orderbook_dir=external / "raw-orderbooks",
            observation_dir=external / "observations",
            settled_snapshot_path=external / "settled" / "latest.json",
            settled_raw_dir=external / "settled",
            label_dir=external / "labels",
            generated_utc="2026-07-04T00:00:00Z",
            capture_orderbooks=True,
            fetch_json=fake_fetch,
        )
        micro.write_outputs(
            report1, out_dir=tmp_path / "micro1", observation_dir=external / "observations"
        )
        report2 = micro.build_sports_microstructure_observation_loop(
            universe_scan_path=universe_path,
            raw_orderbook_dir=external / "raw-orderbooks",
            observation_dir=external / "observations",
            settled_snapshot_path=external / "settled" / "latest.json",
            settled_raw_dir=external / "settled",
            label_dir=external / "labels",
            generated_utc="2026-07-04T00:04:00Z",
            capture_orderbooks=True,
            probe_observed_public=True,
            fetch_json=fake_fetch,
        )
        micro_path = write_json(tmp_path / "micro.json", report2)
        flow_report = flow.build_near_resolution_informed_flow_evidence_gate(
            microstructure_path=micro_path,
            generated_utc="2026-07-04T00:05:00Z",
        )

    assert report2["summary"]["due_distinct_contract_count"] == 1
    assert report2["summary"]["label_row_count"] == 1
    assert report2["label_packet"]["rows"][0]["settlement_yes_outcome"] == 1
    assert report2["label_packet"]["rows"][0]["label_source"] == (
        "public_kalshi_settled_market_payload"
    )
    assert flow_report["summary"]["settled_contract_label_count"] == 1
    assert flow_report["flow_rows"][0]["settlement_yes_outcome"] == 1


def test_near_resolution_flow_falsification_can_find_preregistered_candidate(
    tmp_path: Path,
) -> None:
    flow = load_script("kalshi_near_resolution_informed_flow_evidence_gate")
    rows: list[dict[str, object]] = []
    for index in range(40):
        ticker = f"KXMLBTEST-26JUL04-{index:03d}"
        direction_is_yes = index % 2 == 0
        first_mid = 0.4 if direction_is_yes else 0.6
        second_mid = 0.6 if direction_is_yes else 0.4
        imbalance = 0.8 if direction_is_yes else -0.8
        rows.extend(
            [
                {
                    "snapshot_id": f"{ticker}-a",
                    "contract_ticker": ticker,
                    "observed_at_utc": f"2026-07-04T00:{index:02d}:00Z",
                    "time_to_settlement_seconds": 1800,
                    "yes_mid": first_mid,
                    "depth_imbalance_yes": imbalance,
                    "depth_imbalance_delta": None,
                    "settlement_yes_outcome": 1 if direction_is_yes else 0,
                    "usable": False,
                },
                {
                    "snapshot_id": f"{ticker}-b",
                    "contract_ticker": ticker,
                    "observed_at_utc": f"2026-07-04T01:{index:02d}:00Z",
                    "time_to_settlement_seconds": 1200,
                    "yes_mid": second_mid,
                    "depth_imbalance_yes": imbalance,
                    "depth_imbalance_delta": 0.4 if direction_is_yes else -0.4,
                    "settlement_yes_outcome": 1 if direction_is_yes else 0,
                    "usable": False,
                },
            ]
        )
    micro_path = write_json(
        tmp_path / "micro.json",
        {
            "schema_version": 1,
            "status": "sports_microstructure_observation_loop_ready_with_settlement_labels",
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
            "observation_packet": {"rows": rows},
        },
    )

    report = flow.build_near_resolution_informed_flow_evidence_gate(
        microstructure_path=micro_path,
        generated_utc="2026-07-04T02:00:00Z",
    )

    assert report["status"] == "near_resolution_informed_flow_research_candidates_ready"
    assert report["summary"]["testable_candidate_count"] >= 1
    assert report["summary"]["research_candidate_count"] >= 1
    assert any(row["status"] == "research_candidate_fdr_passed" for row in report["evaluations"])
    assert report["summary"]["usable_row_count"] == 0


def test_near_resolution_flow_uses_price_implied_null_not_coin_flip(
    tmp_path: Path,
) -> None:
    flow = load_script("kalshi_near_resolution_informed_flow_evidence_gate")
    rows: list[dict[str, object]] = []
    for index in range(40):
        ticker = f"KXPRICEIMPLIED-26JUL04-{index:03d}"
        correct = index % 6 != 0
        rows.extend(
            [
                {
                    "snapshot_id": f"{ticker}-a",
                    "contract_ticker": ticker,
                    "observed_at_utc": f"2026-07-04T00:{index:02d}:00Z",
                    "time_to_settlement_seconds": 1800,
                    "yes_mid": 0.90,
                    "best_yes_ask": 0.92,
                    "depth_imbalance_yes": 0.85,
                    "depth_imbalance_delta": None,
                    "settlement_yes_outcome": 1 if correct else 0,
                    "usable": False,
                },
                {
                    "snapshot_id": f"{ticker}-b",
                    "contract_ticker": ticker,
                    "observed_at_utc": f"2026-07-04T01:{index:02d}:00Z",
                    "time_to_settlement_seconds": 1200,
                    "yes_mid": 0.91,
                    "best_yes_ask": 0.93,
                    "depth_imbalance_yes": 0.85,
                    "depth_imbalance_delta": 0.4,
                    "settlement_yes_outcome": 1 if correct else 0,
                    "usable": False,
                },
            ]
        )
    micro_path = write_json(
        tmp_path / "micro.json",
        {
            "schema_version": 1,
            "status": "sports_microstructure_observation_loop_ready_with_settlement_labels",
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
            "observation_packet": {"rows": rows},
        },
    )

    report = flow.build_near_resolution_informed_flow_evidence_gate(
        microstructure_path=micro_path,
        generated_utc="2026-07-04T02:00:00Z",
    )
    depth_eval = next(
        row
        for row in report["evaluations"]
        if row["model_id"] == "flow_depth_imbalance_settlement_directional"
    )

    assert depth_eval["status"] == "testable_research_candidate"
    assert depth_eval["coin_flip_p_value_legacy"] < 0.05
    assert depth_eval["p_value"] > 0.5
    assert depth_eval["mean_price_implied_null_probability"] == 0.92
    assert not any(
        row["status"] == "research_candidate_fdr_passed" for row in report["evaluations"]
    )


def test_near_resolution_flow_blocks_when_price_implied_null_missing(
    tmp_path: Path,
) -> None:
    flow = load_script("kalshi_near_resolution_informed_flow_evidence_gate")
    rows: list[dict[str, object]] = []
    for index in range(40):
        ticker = f"KXMISSINGNULL-26JUL04-{index:03d}"
        rows.append(
            {
                "snapshot_id": f"{ticker}-a",
                "contract_ticker": ticker,
                "observed_at_utc": f"2026-07-04T00:{index:02d}:00Z",
                "time_to_settlement_seconds": 1800,
                "depth_imbalance_yes": 0.85,
                "settlement_yes_outcome": 1,
                "usable": False,
            }
        )
    micro_path = write_json(
        tmp_path / "micro.json",
        {
            "schema_version": 1,
            "status": "sports_microstructure_observation_loop_ready_with_settlement_labels",
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
            "observation_packet": {"rows": rows},
        },
    )

    report = flow.build_near_resolution_informed_flow_evidence_gate(
        microstructure_path=micro_path,
        generated_utc="2026-07-04T02:00:00Z",
    )
    depth_eval = next(
        row
        for row in report["evaluations"]
        if row["model_id"] == "flow_depth_imbalance_settlement_directional"
    )

    assert depth_eval["status"] == "blocked_missing_price_implied_null"
    assert depth_eval["missing_price_implied_null_count"] == depth_eval["oos_label_count"]
    assert depth_eval["p_value"] is None


def test_makefile_exposes_near_resolution_flow_microstructure_path_override() -> None:
    text = (Path(__file__).resolve().parents[1] / "Makefile").read_text(encoding="utf-8")

    assert "KALSHI_NEAR_RESOLUTION_FLOW_MICROSTRUCTURE_PATH ?=" in text
    assert "--microstructure-path $(KALSHI_NEAR_RESOLUTION_FLOW_MICROSTRUCTURE_PATH)" in text
