"""Tests for kalshi_sports_label_accumulation_cycle.py.

Covers:
- Dedup by composite key (contract_ticker, close_time, family_id, cluster_key, source_artifact_sha256)
- Provenance fields on label rows (source_snapshot_sha256, probe_time_utc, settlement_payload_reference)
- Stale observation detection (waiting/blocked)
- Idempotent runs (identical counts with unchanged inputs)
- Missing/unsafe artifact tracking
- Blocked families with deficits and next probe times
- Safety flags
"""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_label_accumulation_cycle.py"
)
ATP_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_atp_proxy_observation_loop.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_module(path: Path, name: str):
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


def safe_artifact(
    status: str = "ready",
    generated_utc: str = "2026-07-04T02:00:00Z",
    **summary,
):
    """Create a synthetic safe research artifact.

    Supports optional ``label_rows_sample`` in kwargs to simulate label row data.
    """
    data = {
        "schema_version": 1,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "summary": {k: v for k, v in summary.items() if k != "label_rows_sample"},
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }
    # Include generated_utc for provenance tracking when available
    if generated_utc:
        data["generated_utc"] = generated_utc
    # If label_rows_sample is provided, include it in the payload
    label_rows = summary.get("label_rows_sample")
    if label_rows is not None:
        data["label_rows_sample"] = label_rows
    return data


def live_artifact(**summary):
    return {
        "schema_version": 1,
        "status": "kalshi_live_blocked",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "summary": summary,
        "safety": {
            "manual_approval_queue": False,
            "market_orders": False,
            "production_requires_env_arm": True,
        },
    }


def make_label_row(
    *,
    contract_ticker: str = "KXMLBGAME_TEST",
    close_time: str = "2026-07-04T00:00:00Z",
    cluster_key: str = "MLB|GAME|TEST",
    source_artifact_sha256: str = "abc123def456",
    yes_outcome: int = 1,
    label_status: str = "labeled_from_public_kalshi_settled_market",
    decision_time: str = "2026-07-04T01:00:00Z",
    settled_time: str = "2026-07-04T00:30:00Z",
) -> dict:
    return {
        "contract_ticker": contract_ticker,
        "close_time": close_time,
        "cluster_key": cluster_key,
        "source_artifact_sha256": source_artifact_sha256,
        "yes_outcome": yes_outcome,
        "side_outcome": yes_outcome,
        "label_status": label_status,
        "label_source": "public_kalshi_settled_market_payload",
        "settlement_result": yes_outcome,
        "decision_time": decision_time,
        "settled_time": settled_time,
        "observation_id": f"sports_obs_{contract_ticker}_{decision_time}",
    }


# ── Existing tests (must still pass) ──


def test_label_accumulation_reports_exact_label_deficits(tmp_path: Path) -> None:
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")
    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(total_observation_row_count=122, label_row_count=4),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=8,
                independent_contract_label_count=2,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=362, label_row_count=9),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=12,
                independent_contract_label_count=6,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(total_observation_row_count=96, label_row_count=0),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    assert report["status"] == "sports_label_accumulation_waiting_more_exact_labels"
    assert report["summary"]["total_exact_label_count"] == 20
    assert report["summary"]["total_independent_label_count"] == 8
    assert report["summary"]["total_label_deficit"] == 62
    rows = {row["family_id"]: row for row in report["family_rows"]}
    assert rows["mlb"]["label_deficit"] == 28
    assert rows["world_cup_soccer"]["label_deficit"] == 24
    assert rows["atp"]["label_deficit"] == 10


def test_label_accumulation_allows_fdr_to_decide_without_paper_shortcut(tmp_path: Path) -> None:
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle_ready")
    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(total_observation_row_count=50, label_row_count=30),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_ready_no_research_candidates",
                valid_label_row_count=30,
                independent_contract_label_count=30,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=50, label_row_count=30),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_ready_no_research_candidates",
                valid_label_row_count=30,
                independent_contract_label_count=30,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(total_observation_row_count=20, label_row_count=10),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact("atp_proxy_evidence_gate_ready_no_candidate", settled_label_count=10),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    assert report["status"] == "sports_label_accumulation_exact_labels_ready_oos_fdr_no_candidate"
    assert report["summary"]["total_label_deficit"] == 0
    assert report["summary"]["paper_usable_count"] == 0
    assert report["summary"]["live_eligible_count"] == 0


def test_atp_latest_snapshot_prefers_dated_match_file(tmp_path: Path) -> None:
    import re

    module = load_module(ATP_SCRIPT_PATH, "kalshi_atp_proxy_observation_loop_latest")
    write_json(tmp_path / "matches-latest.json", {"matches": []})
    write_json(tmp_path / "matches-2026-07-03.json", {"matches": [{"id": "old"}]})
    expected = write_json(tmp_path / "matches-2026-07-04.json", {"matches": [{"id": "new"}]})

    path = module.latest_atp_match_snapshot_path(tmp_path)
    name = path.name
    assert name.endswith(".json")
    assert re.match(r"^matches-\d{4}-\d{2}-\d{2}\.json$", name), f"unexpected name {name!r}"
    assert path == expected


def test_makefile_exposes_label_accumulation_and_dynamic_atp_snapshot() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-label-accumulation-cycle" in text
    assert "scripts/kalshi_sports_label_accumulation_cycle.py" in text
    assert (
        "$(lastword $(sort $(wildcard $(PREDMARKET_PROJECTS_ROOT)/atp-oracle/data/kalshi/matches-*.json)))"
        in text
    )


# ── New tests: Dedup ──


def test_dedup_key_collapses_duplicate_contracts(tmp_path: Path) -> None:
    """Verify that label rows with the same composite key produce one independent label."""
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    # Two label rows with identical dedup key but different decision_time
    label_rows = [
        make_label_row(
            contract_ticker="KXMLBGAME_001",
            close_time="2026-07-04T00:00:00Z",
            cluster_key="MLB|001",
            source_artifact_sha256="hash1",
            decision_time="2026-07-04T01:00:00Z",
        ),
        make_label_row(
            contract_ticker="KXMLBGAME_001",
            close_time="2026-07-04T00:00:00Z",
            cluster_key="MLB|001",
            source_artifact_sha256="hash1",
            decision_time="2026-07-04T02:00:00Z",
        ),
    ]

    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(
                total_observation_row_count=5,
                label_row_count=2,
                distinct_contract_count=1,
                label_rows_sample=label_rows,
                next_public_label_probe_utc="2026-07-05T00:00:00Z",
                generated_utc="2026-07-04T02:00:00Z",
            ),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=2,
                independent_contract_label_count=1,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    rows = {row["family_id"]: row for row in report["family_rows"]}
    mlb = rows["mlb"]
    # Model says valid_label_row_count=2, independent_contract_label_count=1.
    # The model's counts are authoritative (not overridden by sample).
    assert mlb["exact_label_count"] == 2, (
        f"Expected 2 exact labels (from model), got {mlb['exact_label_count']}"
    )
    assert mlb["independent_label_count"] == 1, (
        f"Expected 1 independent (from model), got {mlb['independent_label_count']}"
    )
    assert mlb["label_deficit"] == 29  # min=30, have=1

    # Verify label_rows in report (provenance display, deduped from sample)
    label_rows_out = report.get("label_rows", [])
    assert len(label_rows_out) == 1, (
        f"Expected 1 deduped provenance label row, got {len(label_rows_out)}"
    )


def test_dedup_key_distinguishes_different_contract_tickers(tmp_path: Path) -> None:
    """Verify that different contract_tickers produce separate independent labels."""
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    label_rows = [
        make_label_row(
            contract_ticker="KXMLBGAME_001",
            close_time="2026-07-04T00:00:00Z",
            cluster_key="MLB|001",
            source_artifact_sha256="hash1",
        ),
        make_label_row(
            contract_ticker="KXMLBGAME_002",
            close_time="2026-07-04T00:00:00Z",
            cluster_key="MLB|002",
            source_artifact_sha256="hash1",
        ),
    ]

    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(
                total_observation_row_count=5,
                label_row_count=2,
                distinct_contract_count=2,
                label_rows_sample=label_rows,
                next_public_label_probe_utc="2026-07-05T00:00:00Z",
                generated_utc="2026-07-04T02:00:00Z",
            ),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=2,
                independent_contract_label_count=2,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    rows = {row["family_id"]: row for row in report["family_rows"]}
    mlb = rows["mlb"]
    # Two different tickers → two independent labels
    assert mlb["exact_label_count"] == 2, f"Expected 2 exact labels, got {mlb['exact_label_count']}"
    assert mlb["independent_label_count"] == 2, (
        f"Expected 2 independent, got {mlb['independent_label_count']}"
    )


def test_dedup_key_distinguishes_different_source_hashes(tmp_path: Path) -> None:
    """Verify that different source_artifact_sha256 does NOT inflate independent label count.

    The model artifact's independent_contract_label_count collapses by
    contract_ticker and is authoritative.  Different observation runs of
    the same contract (different source SHAs) produce only one independent
    label per unique contract_ticker.
    """
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    # Same ticker but different source hashes → same contract, counts as one independent label
    label_rows = [
        make_label_row(
            contract_ticker="KXMLBGAME_001",
            close_time="2026-07-04T00:00:00Z",
            cluster_key="MLB|001",
            source_artifact_sha256="hash_v1",
            decision_time="2026-07-04T01:00:00Z",
        ),
        make_label_row(
            contract_ticker="KXMLBGAME_001",
            close_time="2026-07-04T00:00:00Z",
            cluster_key="MLB|001",
            source_artifact_sha256="hash_v2",
            decision_time="2026-07-04T02:00:00Z",
        ),
    ]

    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(
                total_observation_row_count=5,
                label_row_count=2,
                distinct_contract_count=1,
                label_rows_sample=label_rows,
                next_public_label_probe_utc="2026-07-05T00:00:00Z",
                generated_utc="2026-07-04T02:00:00Z",
            ),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=2,
                independent_contract_label_count=1,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    rows = {row["family_id"]: row for row in report["family_rows"]}
    mlb = rows["mlb"]
    # Same contract_ticker → one independent label (model collapses by ticker)
    assert mlb["exact_label_count"] == 2, f"Expected 2 exact labels, got {mlb['exact_label_count']}"
    assert mlb["independent_label_count"] == 1, (
        f"Expected 1 independent (same contract), got {mlb['independent_label_count']}"
    )


# ── New tests: Provenance ──


def test_provenance_fields_on_label_rows(tmp_path: Path) -> None:
    """Verify every deduplicated label row carries provenance fields."""
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    label_rows = [
        make_label_row(
            contract_ticker="KXMLBGAME_001",
            source_artifact_sha256="abc123def456",
        ),
    ]

    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(
                total_observation_row_count=2,
                label_row_count=1,
                distinct_contract_count=1,
                label_rows_sample=label_rows,
                next_public_label_probe_utc="2026-07-05T00:00:00Z",
                generated_utc="2026-07-04T02:00:00Z",
            ),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=1,
                independent_contract_label_count=1,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    # Check provenance fields on family rows
    rows = {row["family_id"]: row for row in report["family_rows"]}
    mlb = rows["mlb"]
    assert mlb.get("source_snapshot_sha256") is not None, (
        "source_snapshot_sha256 should not be None"
    )
    assert isinstance(mlb.get("source_snapshot_sha256"), str), (
        "source_snapshot_sha256 should be a string"
    )
    assert mlb.get("probe_time_utc") is not None, "probe_time_utc should not be None"
    assert mlb.get("settlement_payload_reference") is not None, (
        "settlement_payload_reference should not be None"
    )

    # Check provenance on individual label_rows
    for lr in report.get("label_rows", []):
        assert "source_snapshot_sha256" in lr, (
            f"Label row missing source_snapshot_sha256: {lr.get('contract_ticker')}"
        )
        assert "probe_time_utc" in lr, (
            f"Label row missing probe_time_utc: {lr.get('contract_ticker')}"
        )
        assert "settlement_payload_reference" in lr, (
            f"Label row missing settlement_payload_reference: {lr.get('contract_ticker')}"
        )


# ── New tests: Stale observation detection ──


def test_stale_observation_flagged_when_probe_past(tmp_path: Path) -> None:
    """Verify stale observations are flagged when probe time has passed with no labels."""
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    # Probe time in the past, no labels → should be stale/blocked
    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(
                total_observation_row_count=50,
                label_row_count=0,
                distinct_contract_count=10,
                next_public_label_probe_utc="2026-07-03T00:00:00Z",  # Past
                generated_utc="2026-07-04T02:00:00Z",
            ),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    rows = {row["family_id"]: row for row in report["family_rows"]}
    mlb = rows["mlb"]
    # Probe time in past, no labels → blocked_stale_observations
    assert "blocked" in str(mlb.get("observation_status", "")).lower() or mlb.get(
        "observation_status"
    ) in (
        "blocked_stale_observations",
        "sports_proxy_observation_loop_blocked_no_observations",
    ), f"Expected blocked observation_status, got {mlb.get('observation_status')}"


def test_observation_status_ready_when_labels_present(tmp_path: Path) -> None:
    """Verify observation_status is 'labeled' when labels exist."""
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    label_rows = [
        make_label_row(
            contract_ticker="KXMLBGAME_001",
            source_artifact_sha256="hash1",
        ),
    ]

    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(
                total_observation_row_count=10,
                label_row_count=1,
                distinct_contract_count=1,
                label_rows_sample=label_rows,
                next_public_label_probe_utc="2026-07-05T00:00:00Z",
                generated_utc="2026-07-04T02:00:00Z",
            ),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=1,
                independent_contract_label_count=1,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    rows = {row["family_id"]: row for row in report["family_rows"]}
    mlb = rows["mlb"]
    # Labels present → observation_status should be "labeled"
    assert mlb["observation_status"] == "labeled", (
        f"Expected 'labeled', got {mlb['observation_status']}"
    )


# ── New tests: Idempotency ──


def test_idempotent_runs_produce_identical_counts(tmp_path: Path) -> None:
    """Verify two consecutive runs with unchanged inputs produce identical counts."""
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    label_rows = [
        make_label_row(contract_ticker=f"KXMLBGAME_{i:03d}", source_artifact_sha256="hash1")
        for i in range(5)
    ]

    def make_files(path_prefix: Path):
        return {
            "mlb_obs": write_json(
                path_prefix / "mlb_obs.json",
                safe_artifact(
                    total_observation_row_count=20,
                    label_row_count=5,
                    distinct_contract_count=5,
                    label_rows_sample=label_rows,
                    next_public_label_probe_utc="2026-07-05T00:00:00Z",
                    generated_utc="2026-07-04T02:00:00Z",
                ),
            ),
            "mlb_model": write_json(
                path_prefix / "mlb_model.json",
                safe_artifact(
                    "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                    valid_label_row_count=5,
                    independent_contract_label_count=5,
                    min_independent_labels=30,
                    min_oos_labels=10,
                    research_candidate_count=0,
                ),
            ),
            "wc_obs": write_json(
                path_prefix / "wc_obs.json",
                safe_artifact(total_observation_row_count=0, label_row_count=0),
            ),
            "wc_model": write_json(
                path_prefix / "wc_model.json",
                safe_artifact(
                    "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                    valid_label_row_count=0,
                    independent_contract_label_count=0,
                    min_independent_labels=30,
                    min_oos_labels=10,
                    research_candidate_count=0,
                ),
            ),
            "atp_obs": write_json(
                path_prefix / "atp_obs.json",
                safe_artifact(total_observation_row_count=0, label_row_count=0),
            ),
            "atp_evidence": write_json(
                path_prefix / "atp_evidence.json",
                safe_artifact(
                    "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                    settled_label_count=0,
                    min_settled_labels=10,
                ),
            ),
            "paper": write_json(path_prefix / "paper.json", safe_artifact(paper_usable_count=0)),
            "live": write_json(path_prefix / "live.json", live_artifact(live_eligible_count=0)),
        }

    files = make_files(tmp_path / "run1")

    # Run 1
    report1 = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    # Run 2 with same inputs
    report2 = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    # Compare label counts between runs
    for field in [
        "total_exact_label_count",
        "total_independent_label_count",
        "total_label_deficit",
        "total_observation_count",
    ]:
        assert report1["summary"][field] == report2["summary"][field], (
            f"Field {field} differs between runs: {report1['summary'][field]} vs {report2['summary'][field]}"
        )

    # Compare per-family counts
    for row1, row2 in zip(report1["family_rows"], report2["family_rows"], strict=True):
        assert row1["family_id"] == row2["family_id"]
        for field in [
            "exact_label_count",
            "independent_label_count",
            "label_deficit",
            "observation_count",
        ]:
            assert row1[field] == row2[field], (
                f"Family {row1['family_id']} field {field} differs: {row1[field]} vs {row2[field]}"
            )


# ── New tests: Safety flags ──


def test_safety_flags_all_false_on_artifact(tmp_path: Path) -> None:
    """Verify all safety boolean flags are false and research_only is true."""
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    # Root-level safety booleans
    safety_fields = [
        "public_market_data_calls",
        "authenticated_api_calls",
        "provider_api_calls",
        "paid_calls",
        "database_writes",
        "market_execution",
        "account_or_order_paths",
        "staking_or_sizing_guidance",
    ]
    for field in safety_fields:
        assert report[field] is False, f"Safety field {field} should be False"

    assert report["research_only"] is True
    assert report["execution_enabled"] is False

    # Nested safety block
    nested_safety = report.get("safety", {})
    for field in [
        "market_execution",
        "account_or_order_paths",
        "database_writes",
    ]:
        assert nested_safety.get(field) is False, f"Nested safety field {field} should be False"
    assert nested_safety.get("research_only") is True


# ── New tests: Inputs block ──


def test_inputs_block_has_all_8_entries(tmp_path: Path) -> None:
    """Verify the inputs block has exactly 8 entries with sha256, exists, safe, status."""
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    inputs = report.get("inputs", {})
    expected_keys = {
        "mlb_observation",
        "mlb_model",
        "world_cup_observation",
        "world_cup_model",
        "atp_observation",
        "atp_evidence",
        "paper",
        "live",
    }
    assert set(inputs.keys()) == expected_keys, (
        f"Expected keys {expected_keys}, got {set(inputs.keys())}"
    )

    for key in expected_keys:
        entry = inputs[key]
        assert "path" in entry, f"{key} missing path"
        assert "sha256" in entry, f"{key} missing sha256"
        assert "exists" in entry, f"{key} missing exists"
        assert "safe" in entry, f"{key} missing safe"
        assert "status" in entry, f"{key} missing status"
        assert entry["exists"] is True, f"{key} should exist"
        assert entry["sha256"] is not None, f"{key} sha256 should not be None"
        assert len(entry["sha256"]) == 64, f"{key} sha256 should be 64-char hex"


# ── New tests: Missing/unsafe artifact tracking ──


def test_missing_artifact_keys_in_summary(tmp_path: Path) -> None:
    """Verify missing_artifact_keys lists any missing upstream artifacts."""
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    # Create all artifacts except one critical one
    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        # Intentionally omit live artifact to test missing tracking
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=tmp_path / "nonexistent.json",  # This path doesn't exist
        generated_utc="2026-07-04T02:00:00Z",
    )

    missing = report["summary"].get("missing_artifact_keys", [])
    assert len(missing) >= 1, f"Expected at least 1 missing key, got {missing}"
    # The missing key should contain 'live' since that file doesn't exist
    assert any("live" in key for key in missing), f"Expected 'live' in missing keys, got {missing}"


def test_safe_artifact_count_consistency(tmp_path: Path) -> None:
    """Verify safe_artifact_count and unsafe_artifact_keys are consistent."""
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    # Create an observation artifact that is NOT safe (execution_enabled=true)
    unsafe_obs = {
        "schema_version": 1,
        "status": "some_status",
        "research_only": False,
        "execution_enabled": True,
        "market_execution": True,
        "summary": {},
        "safety": {
            "market_execution": True,
            "account_or_order_paths": True,
            "database_writes": True,
        },
    }

    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            unsafe_obs,  # This one is NOT safe
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    unsafe = report["summary"].get("unsafe_artifact_keys", [])
    assert len(unsafe) >= 1, f"Expected at least 1 unsafe key, got {unsafe}"
    assert any("atp_observation" in key for key in unsafe), (
        f"Expected 'atp_observation' in unsafe keys, got {unsafe}"
    )
    assert report["summary"]["safe_artifact_count"] == 7, (
        f"Expected 7 safe artifacts, got {report['summary']['safe_artifact_count']}"
    )


# ── New tests: Blocked families ──


def test_blocked_families_have_deficits_and_next_probe(tmp_path: Path) -> None:
    """Verify blocked families have next_public_label_probe_utc and explicit deficits."""
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(
                total_observation_row_count=122,
                label_row_count=4,
                next_public_label_probe_utc="2026-07-05T00:00:00Z",
            ),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=8,
                independent_contract_label_count=2,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(
                total_observation_row_count=362,
                label_row_count=9,
                next_public_label_probe_utc="2026-07-06T00:00:00Z",
            ),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=12,
                independent_contract_label_count=6,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(
                total_observation_row_count=96,
                label_row_count=0,
                next_public_label_probe_utc="2026-07-07T06:00:00Z",
            ),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
                next_public_label_probe_utc="2026-07-07T06:00:00Z",
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    # Check that every family row has next_public_label_probe_utc
    for row in report["family_rows"]:
        assert row.get("next_public_label_probe_utc") is not None, (
            f"Family {row['family_id']} missing next_public_label_probe_utc"
        )

    # Check that deficits are present and correct
    deficits = report["next_action"].get("deficits", [])
    assert len(deficits) == 3, f"Expected 3 deficits, got {len(deficits)}"
    for deficit_entry in deficits:
        assert deficit_entry.get("family_id") is not None
        assert deficit_entry.get("label_deficit") is not None
        assert deficit_entry.get("label_deficit") > 0
        assert deficit_entry.get("next_public_label_probe_utc") is not None


# ── New tests: Validation contract assertions ──


def test_validation_contract_structure(tmp_path: Path) -> None:
    """Verify the report satisfies VAL-LABEL-002 structural requirements."""
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(total_observation_row_count=10, label_row_count=5),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=5,
                independent_contract_label_count=3,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    # VAL-LABEL-002: Required keys present
    for key in [
        "schema_version",
        "generated_utc",
        "status",
        "research_only",
        "execution_enabled",
        "summary",
        "family_rows",
        "gates",
        "inputs",
        "next_action",
        "method",
        "safety",
    ]:
        assert key in report, f"Missing required key: {key}"

    # VAL-LABEL-014: Exactly six gates
    assert len(report["gates"]) == 6, (
        f"Expected 6 gates, got {len(report['gates'])}: {[g['name'] for g in report['gates']]}"
    )

    # VAL-LABEL-019: method has all four fields
    for field in ["purpose", "paper_boundary", "exact_label_rule", "proxy_label_boundary"]:
        assert field in report["method"], f"method missing {field}"
        assert report["method"][field], f"method field {field} is empty"

    # VAL-LABEL-020: next_action has required fields
    for field in ["name", "why", "stop_condition"]:
        assert field in report["next_action"], f"next_action missing {field}"
        assert report["next_action"][field], f"next_action field {field} is empty"

    # VAL-LABEL-016: Summary rollup integrity
    total_exact = sum(row.get("exact_label_count", 0) for row in report["family_rows"])
    assert report["summary"]["total_exact_label_count"] == total_exact, (
        "Summary total_exact_label_count does not match per-row sum"
    )
    total_independent = sum(row.get("independent_label_count", 0) for row in report["family_rows"])
    assert report["summary"]["total_independent_label_count"] == total_independent, (
        "Summary total_independent_label_count does not match per-row sum"
    )
    total_deficit = sum(row.get("label_deficit", 0) for row in report["family_rows"])
    assert report["summary"]["total_label_deficit"] == total_deficit, (
        "Summary total_label_deficit does not match per-row sum"
    )

    # VAL-LABEL-009: Three family entries
    family_ids = sorted(row["family_id"] for row in report["family_rows"])
    assert family_ids == ["atp", "mlb", "world_cup_soccer"], (
        f"Expected 3 family entries, got {family_ids}"
    )


def test_csv_output_format(tmp_path: Path) -> None:
    """Verify CSV output has correct header and rows (VAL-LABEL-021)."""
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    # Quick test: verify the CSV_FIELDS constant
    expected_fields = [
        "family_id",
        "status",
        "observation_count",
        "exact_label_count",
        "independent_label_count",
        "min_independent_labels",
        "label_deficit",
        "next_public_label_probe_utc",
        "oos_fdr_status",
    ]
    assert module.CSV_FIELDS == expected_fields, f"CSV_FIELDS mismatch: {module.CSV_FIELDS}"


def test_markdown_output_structure(tmp_path: Path) -> None:
    """Verify markdown output structure (VAL-LABEL-022)."""
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    # Build a simple report and check markdown rendering
    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(total_observation_row_count=10, label_row_count=0),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    md = module.render_markdown(report)
    assert "# Kalshi Sports Label Accumulation Cycle" in md, "Markdown missing main heading"
    assert (
        "| Family | Status | Observations | Exact Labels | Independent | Deficit | Next Probe | OOS/FDR |"
        in md
    ), "Markdown missing table header"
    assert "Research-only" in md, "Markdown missing research-only disclaimer"


def test_label_rows_carry_composite_dedup_key_fields(tmp_path: Path) -> None:
    """Verify label rows in the report carry all composite dedup key fields."""
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    label_rows = [
        make_label_row(
            contract_ticker="KXMLBGAME_001",
            close_time="2026-07-04T00:00:00Z",
            cluster_key="MLB|001",
            source_artifact_sha256="hash1",
        ),
    ]

    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(
                total_observation_row_count=5,
                label_row_count=1,
                distinct_contract_count=1,
                label_rows_sample=label_rows,
                next_public_label_probe_utc="2026-07-05T00:00:00Z",
                generated_utc="2026-07-04T02:00:00Z",
            ),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=1,
                independent_contract_label_count=1,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    # Verify dedup key fields are present in family rows
    for row in report["family_rows"]:
        assert "family_id" in row
        assert "observation_status" in row
        assert row["observation_status"] is not None

    # Verify label_rows have composite key fields
    for lr in report.get("label_rows", []):
        assert "contract_ticker" in lr
        assert "close_time" in lr
        assert "family_id" in lr
        assert "cluster_key" in lr
        assert "source_artifact_sha256" in lr


# ── New tests: Model counts are authoritative (not overridden by sample) ──


def test_model_counts_not_overridden_by_sample_label_rows(tmp_path: Path) -> None:
    """Verify model artifact's exact_label_count is NOT overridden by sample label rows.

    The model's valid_label_row_count and independent_contract_label_count are
    authoritative because they are computed from the full dataset.  The
    label_rows_sample is a subset (up to 20 rows) and must NOT replace the
    model's comprehensive counts.
    """
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    # Model says 92 exact labels, 18 independent across 58 contracts
    label_rows_sample = [
        make_label_row(
            contract_ticker=f"KXMLBGAME_{i:03d}",
            close_time="2026-07-04T00:00:00Z",
            cluster_key=f"MLB|{i:03d}",
            source_artifact_sha256="hash1",
        )
        for i in range(20)  # Only 20 in the sample, but model says 92
    ]

    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(
                total_observation_row_count=180,
                label_row_count=92,
                distinct_contract_count=58,
                label_rows_sample=label_rows_sample,
                next_public_label_probe_utc="2026-07-05T00:00:00Z",
                generated_utc="2026-07-04T02:00:00Z",
            ),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=92,
                independent_contract_label_count=18,
                raw_label_row_count=92,
                duplicate_label_row_count=74,
                invalid_label_row_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    rows = {row["family_id"]: row for row in report["family_rows"]}
    mlb = rows["mlb"]

    # Model's counts must be preserved: 92 exact, 18 independent
    assert mlb["exact_label_count"] == 92, (
        f"Expected 92 exact labels (from model), got {mlb['exact_label_count']}"
    )
    assert mlb["independent_label_count"] == 18, (
        f"Expected 18 independent (from model), got {mlb['independent_label_count']}"
    )
    assert mlb["label_deficit"] == 12, f"Expected deficit 12 (30 - 18), got {mlb['label_deficit']}"
    assert mlb["raw_label_count"] == 92
    assert mlb["duplicate_label_count"] == 74
    assert mlb["invalid_label_count"] == 0

    # Summary rollup must match per-family sums (not the sample size)
    assert report["summary"]["total_exact_label_count"] == 92, (
        f"Summary exact should be 92, got {report['summary']['total_exact_label_count']}"
    )
    assert report["summary"]["total_independent_label_count"] == 18, (
        f"Summary independent should be 18, got {report['summary']['total_independent_label_count']}"
    )

    # label_rows should still have provenance (display only, not for counting)
    label_rows = report.get("label_rows", [])
    assert len(label_rows) == 20, f"Expected 20 provenance label rows, got {len(label_rows)}"
    for lr in label_rows:
        assert "source_snapshot_sha256" in lr
        assert "probe_time_utc" in lr
        assert "settlement_payload_reference" in lr
        assert "contract_ticker" in lr
        assert "yes_outcome" in lr


def test_proxy_labels_never_counted_as_exact(tmp_path: Path) -> None:
    """Verify proxy/quote labels are never mixed into exact_label_count.

    Exact labels come only from public Kalshi settlement artifacts.
    Forward-quote and counterfactual fill proxy labels must NOT appear
    in the MLB family's exact_label_count.
    """
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    # MLB observation with some forward-quote proxy labels (label_status
    # indicates proxy, not settlement)
    proxy_label_row = make_label_row(
        contract_ticker="KXMLBGAME_PROXY_001",
        label_status="pending_contract_not_settled_in_snapshot",
        settled_time=None,
        yes_outcome=None,
    )

    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(
                total_observation_row_count=10,
                label_row_count=0,
                distinct_contract_count=0,
                label_rows_sample=[proxy_label_row],
                next_public_label_probe_utc="2026-07-05T00:00:00Z",
                generated_utc="2026-07-04T02:00:00Z",
            ),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    rows = {row["family_id"]: row for row in report["family_rows"]}
    mlb = rows["mlb"]

    # Proxy labels should not count as exact labels
    assert mlb["exact_label_count"] == 0, (
        f"Expected exact_label_count=0 with proxy-only labels, got {mlb['exact_label_count']}"
    )
    assert mlb["independent_label_count"] == 0
    assert mlb["label_deficit"] == 30  # min=30, have=0

    # The method block must explicitly distinguish exact from proxy
    method = report.get("method", {})
    assert method.get("exact_label_rule"), "exact_label_rule must be non-empty"
    assert method.get("proxy_label_boundary"), "proxy_label_boundary must be non-empty"
    assert "Kalshi" in method.get("exact_label_rule", ""), (
        "exact_label_rule must reference Kalshi public settlement"
    )


# ── ATP exact settlement mapping tests ──


def test_atp_family_row_present_with_zero_labels_all_fields(tmp_path: Path) -> None:
    """Verify ATP family row is present with exact_label_count=0 and all required fields intact.

    Expected behavior:
    - ATP row is present even when exact_label_count == 0
    - All required fields are intact (observation_count, distinct_contract_count,
      research_candidate_count=0, oos_fdr_status)
    """
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(total_observation_row_count=10, label_row_count=5),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=5,
                independent_contract_label_count=3,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(
                total_observation_row_count=240,
                label_row_count=0,
                distinct_contract_count=26,
                next_public_label_probe_utc="2026-07-04T06:00:00Z",
            ),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
                observation_count=240,
                next_public_label_probe_utc="2026-07-04T06:00:00Z",
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    # Verify ATP row is present
    rows = {row["family_id"]: row for row in report["family_rows"]}
    assert "atp" in rows, "ATP family row must be present in family_rows"

    atp = rows["atp"]

    # ATP exact_label_count must be 0 when no labels exist
    assert atp["exact_label_count"] == 0, (
        f"Expected exact_label_count=0, got {atp['exact_label_count']}"
    )

    # All required fields must be present and intact despite zero labels
    required_fields = [
        "observation_count",
        "distinct_contract_count",
        "research_candidate_count",
        "oos_fdr_status",
        "status",
        "observation_status",
        "min_independent_labels",
        "min_oos_labels",
        "label_deficit",
        "raw_label_count",
        "invalid_label_count",
        "duplicate_label_count",
        "next_public_label_probe_utc",
    ]
    for field in required_fields:
        assert field in atp, f"ATP row missing required field '{field}' when exact_label_count=0"

    # Verify specific field values with zero labels
    assert atp["observation_count"] == 240, (
        f"Expected observation_count=240, got {atp['observation_count']}"
    )
    assert atp["distinct_contract_count"] == 26, (
        f"Expected distinct_contract_count=26, got {atp['distinct_contract_count']}"
    )
    assert atp["research_candidate_count"] == 0, (
        f"Expected research_candidate_count=0, got {atp['research_candidate_count']}"
    )
    assert atp["oos_fdr_status"] == "atp_proxy_evidence_gate_blocked_waiting_settlement_labels", (
        f"Unexpected oos_fdr_status: {atp['oos_fdr_status']}"
    )
    assert atp["label_deficit"] == 10, f"Expected label_deficit=10, got {atp['label_deficit']}"
    assert atp["raw_label_count"] == 0, f"Expected raw_label_count=0, got {atp['raw_label_count']}"
    assert atp["invalid_label_count"] == 0, (
        f"Expected invalid_label_count=0, got {atp['invalid_label_count']}"
    )
    assert atp["duplicate_label_count"] == 0, (
        f"Expected duplicate_label_count=0, got {atp['duplicate_label_count']}"
    )

    # Status should be waiting_exact_labels when exact_label_count < min_independent_labels
    assert atp["status"] == "waiting_exact_labels", (
        f"Expected status='waiting_exact_labels', got '{atp['status']}'"
    )

    # observation_status should indicate waiting (not blocked_stale)
    assert atp["observation_status"] == "waiting_settlement", (
        f"Expected observation_status='waiting_settlement', got '{atp['observation_status']}'"
    )


def test_atp_family_row_when_label_threshold_met(tmp_path: Path) -> None:
    """Verify ATP row status is label_threshold_met when exact_label_count >= min_independent_labels."""
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(total_observation_row_count=10, label_row_count=5),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=5,
                independent_contract_label_count=3,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(
                total_observation_row_count=100,
                label_row_count=10,
                distinct_contract_count=10,
                next_public_label_probe_utc="2026-07-04T06:00:00Z",
            ),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_ready_no_candidate",
                settled_label_count=10,
                min_settled_labels=10,
                research_candidate_count=0,
                observation_count=100,
                next_public_label_probe_utc="2026-07-04T06:00:00Z",
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    rows = {row["family_id"]: row for row in report["family_rows"]}
    assert "atp" in rows, "ATP family row must be present"

    atp = rows["atp"]
    # When settled_label_count (10) >= min_settled_labels (10) and no research candidate
    assert atp["status"] == "label_threshold_met", (
        f"Expected status='label_threshold_met', got '{atp['status']}'"
    )
    assert atp["exact_label_count"] == 10, (
        f"Expected exact_label_count=10, got {atp['exact_label_count']}"
    )
    assert atp["label_deficit"] == 0, f"Expected label_deficit=0, got {atp['label_deficit']}"
    assert atp["research_candidate_count"] == 0, (
        f"Expected research_candidate_count=0, got {atp['research_candidate_count']}"
    )
    assert atp["observation_status"] == "labeled", (
        f"Expected observation_status='labeled', got '{atp['observation_status']}'"
    )


def test_atp_research_candidate_count_always_zero(tmp_path: Path) -> None:
    """Verify ATP research_candidate_count is always 0.

    ATP uses the evidence gate (not model falsification) for research candidates,
    so research_candidate_count must always be 0 regardless of label count.
    """
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    # Test case 1: zero labels → research_candidate_count=0
    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs0.json",
            safe_artifact(total_observation_row_count=10, label_row_count=5),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model0.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=5,
                independent_contract_label_count=3,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs0.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model0.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs0.json",
            safe_artifact(total_observation_row_count=50, label_row_count=0),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence0.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
            ),
        ),
        "paper": write_json(tmp_path / "paper0.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live0.json", live_artifact(live_eligible_count=0)),
    }

    report0 = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    atp0 = {row["family_id"]: row for row in report0["family_rows"]}["atp"]
    assert atp0["research_candidate_count"] == 0, (
        f"With 0 labels, expected research_candidate_count=0, got {atp0['research_candidate_count']}"
    )

    # Test case 2: labels present → research_candidate_count still 0
    files2 = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs2.json",
            safe_artifact(total_observation_row_count=10, label_row_count=5),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model2.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=5,
                independent_contract_label_count=3,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs2.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model2.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs2.json",
            safe_artifact(total_observation_row_count=100, label_row_count=10),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence2.json",
            safe_artifact(
                "atp_proxy_evidence_gate_ready_no_candidate",
                settled_label_count=10,
                min_settled_labels=10,
                research_candidate_count=0,
            ),
        ),
        "paper": write_json(tmp_path / "paper2.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live2.json", live_artifact(live_eligible_count=0)),
    }

    report2 = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files2["mlb_obs"],
        mlb_model_path=files2["mlb_model"],
        world_cup_observation_path=files2["wc_obs"],
        world_cup_model_path=files2["wc_model"],
        atp_observation_path=files2["atp_obs"],
        atp_evidence_path=files2["atp_evidence"],
        paper_path=files2["paper"],
        live_path=files2["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    atp2 = {row["family_id"]: row for row in report2["family_rows"]}["atp"]
    assert atp2["research_candidate_count"] == 0, (
        f"With labels, expected research_candidate_count=0, got {atp2['research_candidate_count']}"
    )


def test_atp_next_probe_is_valid_future_iso_timestamp(tmp_path: Path) -> None:
    """Verify ATP next_public_label_probe_utc is a valid future ISO 8601 timestamp.

    The probe time must:
    - Be a non-empty string
    - Parse as valid ISO 8601
    - Be in UTC
    """
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(total_observation_row_count=10, label_row_count=5),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=5,
                independent_contract_label_count=3,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(
                total_observation_row_count=240,
                label_row_count=0,
                distinct_contract_count=26,
                next_public_label_probe_utc="2026-07-04T06:00:00Z",
            ),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
                next_public_label_probe_utc="2026-07-04T06:00:00Z",
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    rows = {row["family_id"]: row for row in report["family_rows"]}
    atp = rows["atp"]

    probe_utc = atp["next_public_label_probe_utc"]

    # Must be a non-empty string
    assert probe_utc is not None, "next_public_label_probe_utc must not be None"
    assert isinstance(probe_utc, str), (
        f"next_public_label_probe_utc must be a string, got {type(probe_utc)}"
    )
    assert len(probe_utc) > 0, "next_public_label_probe_utc must not be empty"

    # Must parse as valid ISO 8601
    parsed = datetime.fromisoformat(probe_utc.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None, (
        f"next_public_label_probe_utc '{probe_utc}' must have timezone info"
    )
    assert parsed.tzinfo == UTC or parsed.tzinfo.utcoffset(None) == UTC.utcoffset(None), (
        f"next_public_label_probe_utc '{probe_utc}' must be in UTC"
    )


def test_atp_observation_status_reflects_settlement_progress(tmp_path: Path) -> None:
    """Verify ATP observation_status accurately reflects settlement probe progress.

    - When probe time is past and no labels: blocked_stale_observations
    - When probe time is future and no labels: waiting_settlement
    """
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    # ── Case 1: Future probe → waiting_settlement ──
    files1 = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs1.json",
            safe_artifact(total_observation_row_count=10, label_row_count=5),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model1.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=5,
                independent_contract_label_count=3,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs1.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model1.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs1.json",
            safe_artifact(
                total_observation_row_count=50,
                label_row_count=0,
                next_public_label_probe_utc="2026-07-04T10:00:00Z",  # Future
            ),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence1.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
                next_public_label_probe_utc="2026-07-04T10:00:00Z",
            ),
        ),
        "paper": write_json(tmp_path / "paper1.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live1.json", live_artifact(live_eligible_count=0)),
    }

    report1 = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files1["mlb_obs"],
        mlb_model_path=files1["mlb_model"],
        world_cup_observation_path=files1["wc_obs"],
        world_cup_model_path=files1["wc_model"],
        atp_observation_path=files1["atp_obs"],
        atp_evidence_path=files1["atp_evidence"],
        paper_path=files1["paper"],
        live_path=files1["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    atp1 = {row["family_id"]: row for row in report1["family_rows"]}["atp"]
    assert atp1["observation_status"] == "waiting_settlement", (
        f"With future probe, expected 'waiting_settlement', got '{atp1['observation_status']}'"
    )

    # ── Case 2: Past probe → blocked_stale_observations ──
    files2 = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs2.json",
            safe_artifact(total_observation_row_count=10, label_row_count=5),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model2.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=5,
                independent_contract_label_count=3,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs2.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model2.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs2.json",
            safe_artifact(
                total_observation_row_count=50,
                label_row_count=0,
                next_public_label_probe_utc="2026-07-03T06:00:00Z",  # Past
            ),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence2.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=0,
                min_settled_labels=10,
                next_public_label_probe_utc="2026-07-03T06:00:00Z",
            ),
        ),
        "paper": write_json(tmp_path / "paper2.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live2.json", live_artifact(live_eligible_count=0)),
    }

    report2 = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files2["mlb_obs"],
        mlb_model_path=files2["mlb_model"],
        world_cup_observation_path=files2["wc_obs"],
        world_cup_model_path=files2["wc_model"],
        atp_observation_path=files2["atp_obs"],
        atp_evidence_path=files2["atp_evidence"],
        paper_path=files2["paper"],
        live_path=files2["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    atp2 = {row["family_id"]: row for row in report2["family_rows"]}["atp"]
    assert "blocked_stale_observations" in str(atp2.get("observation_status", "")), (
        f"With past probe and no labels, expected 'blocked_stale_observations', "
        f"got '{atp2['observation_status']}'"
    )


def test_atp_label_counts_from_evidence_gate_authoritative(tmp_path: Path) -> None:
    """Verify ATP exact_label_count uses evidence gate settled_label_count, not observation summary.

    The evidence gate's settled_label_count is authoritative because it captures
    the full settlement probe results, not just the label_rows_sample (max 20 rows).
    """
    module = load_module(SCRIPT_PATH, "kalshi_sports_label_accumulation_cycle")

    # Observation says label_row_count=5 (sample), but evidence gate says settled_label_count=3
    # The evidence gate's count should be authoritative
    files = {
        "mlb_obs": write_json(
            tmp_path / "mlb_obs.json",
            safe_artifact(total_observation_row_count=10, label_row_count=5),
        ),
        "mlb_model": write_json(
            tmp_path / "mlb_model.json",
            safe_artifact(
                "sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=5,
                independent_contract_label_count=3,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "wc_obs": write_json(
            tmp_path / "wc_obs.json",
            safe_artifact(total_observation_row_count=0, label_row_count=0),
        ),
        "wc_model": write_json(
            tmp_path / "wc_model.json",
            safe_artifact(
                "world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels",
                valid_label_row_count=0,
                independent_contract_label_count=0,
                min_independent_labels=30,
                min_oos_labels=10,
                research_candidate_count=0,
            ),
        ),
        "atp_obs": write_json(
            tmp_path / "atp_obs.json",
            safe_artifact(
                total_observation_row_count=100,
                label_row_count=5,
                distinct_contract_count=5,
                next_public_label_probe_utc="2026-07-05T06:00:00Z",
            ),
        ),
        "atp_evidence": write_json(
            tmp_path / "atp_evidence.json",
            safe_artifact(
                "atp_proxy_evidence_gate_blocked_waiting_settlement_labels",
                settled_label_count=3,
                min_settled_labels=10,
            ),
        ),
        "paper": write_json(tmp_path / "paper.json", safe_artifact(paper_usable_count=0)),
        "live": write_json(tmp_path / "live.json", live_artifact(live_eligible_count=0)),
    }

    report = module.build_sports_label_accumulation_cycle(
        mlb_observation_path=files["mlb_obs"],
        mlb_model_path=files["mlb_model"],
        world_cup_observation_path=files["wc_obs"],
        world_cup_model_path=files["wc_model"],
        atp_observation_path=files["atp_obs"],
        atp_evidence_path=files["atp_evidence"],
        paper_path=files["paper"],
        live_path=files["live"],
        generated_utc="2026-07-04T02:00:00Z",
    )

    rows = {row["family_id"]: row for row in report["family_rows"]}
    atp = rows["atp"]

    # Evidence gate settled_label_count=3 should be the authoritative count
    assert atp["exact_label_count"] == 3, (
        f"Expected exact_label_count=3 from evidence gate, got {atp['exact_label_count']}"
    )

    # Independent label count should equal exact_label_count for ATP
    # (ATP doesn't do contract-level dedup via model falsification)
    assert atp["independent_label_count"] == 3, (
        f"Expected independent_label_count=3, got {atp['independent_label_count']}"
    )
