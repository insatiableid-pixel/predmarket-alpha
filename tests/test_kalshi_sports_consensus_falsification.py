from __future__ import annotations

import importlib.util
import json
import random
from pathlib import Path

from predmarket.sports_consensus_falsification import (
    DEFAULT_FDR_ALPHA,
    DEFAULT_MIN_OOS_LABELS,
    build_sports_consensus_falsification,
)

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_consensus_falsification.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_script_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_sports_consensus_falsification", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _preflight(*, valid: int = 1, reference_rows: int = 2, books: int = 2) -> dict:
    return {
        "status": "sports_consensus_preflight_ready",
        "summary": {
            "valid_candidate_count": valid,
            "reference_row_count": reference_rows,
            "distinct_book_count": books,
        },
    }


def _observation(
    *,
    ticker: str,
    side: str,
    consensus: float,
    kalshi_mid: float,
    observed_utc: str,
    event_ticker: str | None = None,
    book_count: int = 2,
) -> dict:
    return {
        "contract_ticker": ticker,
        "event_ticker": event_ticker or ticker.split("-", 1)[0],
        "side": side,
        "consensus_probability_for_side": consensus,
        "kalshi_mid_for_side": kalshi_mid,
        "observed_utc": observed_utc,
        "sport_key": "mlb",
        "market_key": "KXMLBGAME",
        "book_count": book_count,
        "distinct_books": ["circa", "pinnacle"],
        "source_reference_sha256": f"sha-{ticker}",
    }


def _label(*, ticker: str, side: str, outcome: int, settled_utc: str) -> dict:
    return {
        "contract_ticker": ticker,
        "side": side,
        "yes_outcome": outcome,
        "settled_time": settled_utc,
        "settlement_result": "yes" if outcome == 1 else "no",
    }


def test_missing_preflight_blocks_safely() -> None:
    report = build_sports_consensus_falsification(
        preflight_report=None,
        consensus_observations=[],
        settlement_labels=[],
    )

    assert report["status"] == "sports_consensus_falsification_blocked_missing_inputs"
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["market_execution"] is False
    assert report["account_or_order_paths"] is False
    assert report["inputs"]["preflight_present"] is False
    assert report["summary"]["joined_label_count"] == 0
    assert report["summary"]["fdr_survivor_count"] == 0


def test_empty_valid_consensus_rows_blocks_safely() -> None:
    report = build_sports_consensus_falsification(
        preflight_report=_preflight(valid=0, reference_rows=0, books=0),
        consensus_observations=[],
        settlement_labels=[],
    )

    assert report["status"] == ("sports_consensus_falsification_blocked_no_valid_consensus_rows")
    assert report["inputs"]["preflight_valid_candidate_count"] == 0
    assert report["summary"]["fdr_survivor_count"] == 0


def test_valid_consensus_rows_without_settlement_labels_blocks() -> None:
    observations = [
        _observation(
            ticker="KXMLBGAME-26JUL041910TEAM001-YES",
            side="yes",
            consensus=0.55,
            kalshi_mid=0.50,
            observed_utc="2026-07-01T10:00:00Z",
        )
    ]
    report = build_sports_consensus_falsification(
        preflight_report=_preflight(),
        consensus_observations=observations,
        settlement_labels=[],
    )

    assert report["status"] == ("sports_consensus_falsification_blocked_insufficient_labels")
    assert report["summary"]["joined_label_count"] == 0
    assert report["summary"]["independent_label_count"] == 0
    assert report["summary"]["fdr_survivor_count"] == 0


def test_synthetic_labeled_rows_produce_testable_candidate() -> None:
    """Below the FDR survival bar but above the testable floor."""
    observations: list[dict] = []
    labels: list[dict] = []
    # 40 contracts with no real signal (random 50/50 outcomes) for favorite rule
    random.seed(7)
    contract_count = 40
    for i in range(contract_count):
        consensus = 0.70
        kalshi = 0.60  # divergence = 0.10 >= any threshold
        outcome = random.choice([0, 1])
        ticker = f"KXMLBGAME-26JUL041910TEAM{i:03d}-YES"
        observations.append(
            _observation(
                ticker=ticker,
                side="yes",
                consensus=consensus,
                kalshi_mid=kalshi,
                observed_utc=f"2026-07-01T{(i % 24):02d}:00:00Z",
            )
        )
        labels.append(
            _label(
                ticker=ticker,
                side="yes",
                outcome=outcome,
                settled_utc=f"2026-07-02T{(i % 24):02d}:00:00Z",
            )
        )

    report = build_sports_consensus_falsification(
        preflight_report=_preflight(),
        consensus_observations=observations,
        settlement_labels=labels,
    )

    assert report["summary"]["independent_label_count"] == contract_count
    assert report["summary"]["oos_label_count"] >= DEFAULT_MIN_OOS_LABELS
    assert report["summary"]["tested_hypothesis_count"] >= 1
    assert (
        report["status"] == "sports_consensus_falsification_ready_no_research_candidates"
        or report["status"] == "sports_consensus_falsification_ready_with_research_candidates"
        or report["status"] == "sports_consensus_falsification_blocked_insufficient_labels"
    )


def test_global_label_floor_without_rule_bucket_floor_has_precise_status() -> None:
    observations: list[dict] = []
    labels: list[dict] = []
    bucket_mids = [0.06, 0.16, 0.31, 0.51, 0.71, 0.86, 0.06, 0.16, 0.31, 0.51]
    for i in range(31):
        kalshi_mid = 0.40 if i < 21 else bucket_mids[i - 21]
        ticker = f"KXMLBGAME-26JUL041910TEAM{i:03d}-YES"
        observations.append(
            _observation(
                ticker=ticker,
                side="yes",
                consensus=kalshi_mid,
                kalshi_mid=kalshi_mid,
                observed_utc=f"2026-07-{1 + i // 24:02d}T{i % 24:02d}:00:00Z",
            )
        )
        labels.append(
            _label(
                ticker=ticker,
                side="yes",
                outcome=i % 2,
                settled_utc=f"2026-07-{2 + i // 24:02d}T{i % 24:02d}:00:00Z",
            )
        )

    report = build_sports_consensus_falsification(
        preflight_report=_preflight(),
        consensus_observations=observations,
        settlement_labels=labels,
    )

    assert report["summary"]["independent_label_count"] == 31
    assert report["summary"]["oos_label_count"] == DEFAULT_MIN_OOS_LABELS
    assert report["summary"]["tested_hypothesis_count"] == 0
    assert report["summary"]["testable_candidate_count"] == 0
    assert report["summary"]["max_hypothesis_oos_count"] < DEFAULT_MIN_OOS_LABELS
    assert report["summary"]["hypothesis_accumulation_plan_count"] > 0
    assert report["summary"]["nearest_hypothesis_oos_deficit"] > 0
    plan = report["hypothesis_accumulation_plan"]
    assert plan
    assert all(item["research_only"] is True for item in plan)
    assert all(item["usable"] is False for item in plan)
    assert plan[0]["current_oos_label_count"] == report["summary"]["max_hypothesis_oos_count"]
    assert plan[0]["oos_label_deficit"] == (
        DEFAULT_MIN_OOS_LABELS - report["summary"]["max_hypothesis_oos_count"]
    )
    assert report["status"] == "sports_consensus_falsification_blocked_no_testable_hypotheses"
    assert report["next_action"]["name"] == "kalshi_sports_consensus_rule_bucket_label_accumulation"


def test_accumulation_opportunities_route_current_pending_observations() -> None:
    observations: list[dict] = []
    labels: list[dict] = []
    bucket_mids = [0.06, 0.16, 0.31, 0.51, 0.71, 0.86, 0.06, 0.16, 0.31, 0.51]
    for i in range(31):
        kalshi_mid = 0.40 if i < 21 else bucket_mids[i - 21]
        ticker = f"KXMLBGAME-26JUL041910TEAM{i:03d}-YES"
        observations.append(
            _observation(
                ticker=ticker,
                side="yes",
                consensus=kalshi_mid,
                kalshi_mid=kalshi_mid,
                observed_utc=f"2026-07-{1 + i // 24:02d}T{i % 24:02d}:00:00Z",
            )
        )
        labels.append(
            _label(
                ticker=ticker,
                side="yes",
                outcome=i % 2,
                settled_utc=f"2026-07-{2 + i // 24:02d}T{i % 24:02d}:00:00Z",
            )
        )
    pending = _observation(
        ticker="KXMLBGAME-26JUL062020AAABBB-AAA",
        side="yes",
        consensus=0.07,
        kalshi_mid=0.06,
        observed_utc="2026-07-06T18:00:00Z",
    )
    pending["close_time"] = "2026-07-07T02:20:00Z"
    observations.append(pending)

    report = build_sports_consensus_falsification(
        preflight_report=_preflight(),
        consensus_observations=observations,
        settlement_labels=labels,
    )

    opportunities = report["hypothesis_accumulation_opportunities"]
    model_id = report["summary"]["nearest_hypothesis_model_id"]
    matching = [row for row in opportunities if row["model_id"] == model_id]
    assert matching
    assert matching[0]["contract_ticker"] == pending["contract_ticker"]
    assert matching[0]["opportunity_status"] == "pending_exact_kalshi_settlement_label"
    assert matching[0]["research_only"] is True
    assert matching[0]["usable"] is False
    assert report["summary"]["hypothesis_accumulation_opportunity_count"] >= 1
    assert report["summary"]["nearest_hypothesis_current_opportunity_count"] >= 1


def test_synthetic_strong_rule_produces_fdr_survivor() -> None:
    random.seed(42)
    observations: list[dict] = []
    labels: list[dict] = []
    for i in range(40):
        consensus = 0.70
        kalshi = 0.66  # divergence = 0.04 — large enough for thresholds <= 0.04
        outcome = 1 if random.random() < 0.90 else 0
        ticker = f"KXMLBGAME-26JUL041910TEAM{i:03d}-YES"
        observations.append(
            _observation(
                ticker=ticker,
                side="yes",
                consensus=consensus,
                kalshi_mid=kalshi,
                observed_utc=f"2026-07-01T{(i % 24):02d}:00:00Z",
            )
        )
        labels.append(
            _label(
                ticker=ticker,
                side="yes",
                outcome=outcome,
                settled_utc=f"2026-07-02T{(i % 24):02d}:00:00Z",
            )
        )

    report = build_sports_consensus_falsification(
        preflight_report=_preflight(),
        consensus_observations=observations,
        settlement_labels=labels,
    )

    assert report["status"] == ("sports_consensus_falsification_ready_with_research_candidates")
    assert report["summary"]["fdr_survivor_count"] >= 1
    assert report["best_survivor"] is not None
    assert report["best_survivor"]["candidate_rule"] == ("kalshi_vs_consensus_favorite_underpriced")
    assert report["best_survivor"]["q_value"] <= DEFAULT_FDR_ALPHA


def test_every_row_remains_research_only_with_no_execution_flags() -> None:
    random.seed(42)
    observations: list[dict] = []
    labels: list[dict] = []
    for i in range(40):
        consensus = 0.70
        kalshi = 0.66
        outcome = 1 if random.random() < 0.90 else 0
        ticker = f"KXMLBGAME-26JUL041910TEAM{i:03d}-YES"
        observations.append(
            _observation(
                ticker=ticker,
                side="yes",
                consensus=consensus,
                kalshi_mid=kalshi,
                observed_utc=f"2026-07-01T{(i % 24):02d}:00:00Z",
            )
        )
        labels.append(
            _label(
                ticker=ticker,
                side="yes",
                outcome=outcome,
                settled_utc=f"2026-07-02T{(i % 24):02d}:00:00Z",
            )
        )

    report = build_sports_consensus_falsification(
        preflight_report=_preflight(),
        consensus_observations=observations,
        settlement_labels=labels,
    )

    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["market_execution"] is False
    assert report["account_or_order_paths"] is False
    assert report["staking_or_sizing_guidance"] is False
    assert all(row["usable"] is False for row in report["rows"])
    assert all(row["research_only"] is True for row in report["rows"])
    # All evaluation rows also remain research-only
    for evaluation in report["evaluations"]:
        assert evaluation["usable"] is False
        assert evaluation["calibrated_probability"] is None
        assert evaluation["expected_value_per_contract"] is None


def test_multiple_threshold_and_rule_tests_increment_tested_hypothesis_count() -> None:
    random.seed(11)
    observations: list[dict] = []
    labels: list[dict] = []
    # Mix of favorites and underdogs to exercise multiple divergence rules.
    contract_count = 80
    for i in range(contract_count):
        is_favorite = i % 2 == 0
        consensus = 0.70 if is_favorite else 0.30
        kalshi = consensus - 0.04
        outcome = 1 if is_favorite else 0
        ticker = f"KXMLBGAME-26JUL041910TEAM{i:03d}-YES"
        observations.append(
            _observation(
                ticker=ticker,
                side="yes",
                consensus=consensus,
                kalshi_mid=kalshi,
                observed_utc=f"2026-07-01T{(i % 24):02d}:00:00Z",
            )
        )
        labels.append(
            _label(
                ticker=ticker,
                side="yes",
                outcome=outcome,
                settled_utc=f"2026-07-02T{(i % 24):02d}:00:00Z",
            )
        )

    report = build_sports_consensus_falsification(
        preflight_report=_preflight(),
        consensus_observations=observations,
        settlement_labels=labels,
    )

    # Favorite rule fires on half of contracts; underdog rule fires on the other half.
    # Multiple thresholds must each increment the family.
    favorite_tested = sum(
        1
        for item in report["evaluations"]
        if item["candidate_rule"] == "kalshi_vs_consensus_favorite_underpriced"
        and item.get("p_value") is not None
    )
    underdog_tested = sum(
        1
        for item in report["evaluations"]
        if item["candidate_rule"] == "kalshi_vs_consensus_underdog_underpriced"
        and item.get("p_value") is not None
    )
    assert favorite_tested >= 1
    assert underdog_tested >= 1
    assert report["summary"]["tested_hypothesis_count"] == (
        favorite_tested
        + underdog_tested
        + sum(
            1
            for item in report["evaluations"]
            if item["candidate_rule"] == "sports_consensus_price_bucket_bias"
            and item.get("p_value") is not None
        )
        + sum(
            1
            for item in report["evaluations"]
            if item["candidate_rule"] == "kalshi_vs_consensus_fade_overpriced"
            and item.get("p_value") is not None
        )
    )


def test_cli_writes_latest_research_only_artifacts(tmp_path: Path) -> None:
    module = load_script_module()
    preflight_path = tmp_path / "preflight.json"
    observation_dir = tmp_path / "observations"
    label_dir = tmp_path / "labels"
    out_dir = tmp_path / "out"
    latest_json = module.MACRO_DIR / "latest-kalshi-sports-consensus-falsification.json"
    latest_before = latest_json.read_text(encoding="utf-8") if latest_json.exists() else None

    observation_dir.mkdir()
    label_dir.mkdir()

    preflight_path.write_text(json.dumps(_preflight()), encoding="utf-8")
    # Provide a single observation with no matching settlement label so the
    # join yields zero rows; status must be blocked_insufficient_labels.
    observation_path = observation_dir / "obs.json"
    observation_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "research_only": True,
                "execution_enabled": False,
                "market_execution": False,
                "account_or_order_paths": False,
                "database_writes": False,
                "provider_api_calls": False,
                "paid_calls": False,
                "raw_provider_payload_copied": False,
                "staking_or_sizing_guidance": False,
                "packet_type": "kalshi_sports_consensus_observations",
                "rows": [
                    _observation(
                        ticker="KXMLBGAME-26JUL041910TEAM001-YES",
                        side="yes",
                        consensus=0.55,
                        kalshi_mid=0.50,
                        observed_utc="2026-07-01T10:00:00Z",
                    )
                ],
            }
        ),
        encoding="utf-8",
    )

    report = module.run_sports_consensus_falsification(
        preflight_path=preflight_path,
        observation_dir=observation_dir,
        label_dir=label_dir,
        output_dir=out_dir,
        write=True,
    )

    paths = report["output_paths"]
    assert "latest_json_path" not in paths
    latest_after = latest_json.read_text(encoding="utf-8") if latest_json.exists() else None
    assert latest_after == latest_before
    loaded = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    csv_text = Path(paths["csv_path"]).read_text(encoding="utf-8")
    assert loaded["status"] == ("sports_consensus_falsification_blocked_insufficient_labels")
    assert loaded["research_only"] is True
    assert loaded["execution_enabled"] is False
    assert loaded["market_execution"] is False
    assert loaded["account_or_order_paths"] is False
    assert "Falsification Ledger" in markdown
    assert "research-only" in markdown.lower()
    forbidden = ["Kelly", "bankroll", "place a bet", "wager", "stake size"]
    assert not any(term.lower() in markdown.lower() for term in forbidden)
    # CSV header must include the directive's required columns.
    header = csv_text.splitlines()[0]
    for column in (
        "contract_ticker",
        "family_id",
        "model_id",
        "candidate_rule",
        "threshold",
        "price_bucket",
        "kalshi_mid_for_side",
        "consensus_probability_for_side",
        "divergence",
        "selected_side_prediction",
        "settlement_outcome",
        "correct",
        "research_only",
        "usable",
    ):
        assert column in header


def test_makefile_target_exists() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-consensus-falsification" in text
    assert "scripts/kalshi_sports_consensus_falsification.py" in text
