from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "kalshi_passive_liquidity_paper_fill_falsification.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_passive_liquidity_paper_fill_falsification", SCRIPT_PATH
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


def safe_artifact(status: str = "ready", **extra):
    payload = {
        "schema_version": 1,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "summary": {},
        "safety": {
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }
    payload.update(extra)
    return payload


def micro_row(
    snapshot_id: str,
    observed_at: str,
    *,
    ticker: str = "KXMLBGAME-26JUL04-BOS",
    yes_mid: float = 0.50,
) -> dict[str, object]:
    return {
        "snapshot_id": snapshot_id,
        "contract_ticker": ticker,
        "observed_at_utc": observed_at,
        "best_yes_bid": round(yes_mid - 0.01, 4),
        "best_yes_ask": round(yes_mid + 0.01, 4),
        "best_no_bid": round(1 - yes_mid - 0.01, 4),
        "best_no_ask": round(1 - yes_mid + 0.01, 4),
        "yes_mid": yes_mid,
        "research_only": True,
        "execution_enabled": False,
    }


def paper_intent(
    index: int,
    *,
    side: str = "yes",
    ticker: str = "KXMLBGAME-26JUL04-BOS",
    quote_price: float = 0.50,
) -> dict[str, object]:
    return {
        "paper_intent_id": f"paper-{index}",
        "virtual_order_id": f"virtual-{index}",
        "contract_ticker": ticker,
        "side": side,
        "quote_price": quote_price,
        "quote_size_contracts": 1,
        "entry_snapshot_id": f"entry-{index}",
        "entry_observed_at_utc": f"2026-07-04T00:{index:02d}:00Z",
        "order_expires_at_utc": f"2026-07-04T00:{index:02d}:30Z",
        "research_only": True,
        "execution_enabled": False,
    }


def paper_label(index: int, *, status: str) -> dict[str, object]:
    return {
        "paper_intent_id": f"paper-{index}",
        "virtual_order_id": f"virtual-{index}",
        "contract_ticker": "KXMLBGAME-26JUL04-BOS",
        "side": "yes",
        "quote_price": 0.50,
        "entry_observed_at_utc": f"2026-07-04T00:{index:02d}:00Z",
        "order_expires_at_utc": f"2026-07-04T00:{index:02d}:30Z",
        "paper_fill_status": status,
        "paper_fill_label_utc": f"2026-07-04T00:{index:02d}:45Z",
        "label_snapshot_id": f"label-{index}",
        "label_observed_at_utc": f"2026-07-04T00:{index:02d}:20Z",
        "label_source": "later_public_orderbook_snapshot",
        "real_exchange_fill": False,
        "research_only": True,
        "execution_enabled": False,
    }


def write_inputs(
    tmp_path: Path,
    *,
    count: int,
    status: str,
    label_mid: float = 0.52,
) -> tuple[Path, Path]:
    intents = [paper_intent(index) for index in range(count)]
    labels = [paper_label(index, status=status) for index in range(count)]
    paper_fill_path = write_json(
        tmp_path / "paper-fill.json",
        safe_artifact(
            "passive_liquidity_paper_fill_loop_ready_with_paper_fill_labels",
            summary={
                "paper_intent_count": len(intents),
                "paper_fill_label_count": len(labels),
                "real_exchange_fill_label_count": 0,
            },
            paper_intent_rows=intents,
            paper_fill_label_rows=labels,
        ),
    )
    micro_rows = []
    for index in range(count):
        micro_rows.append(
            micro_row(f"entry-{index}", f"2026-07-04T00:{index:02d}:00Z", yes_mid=0.50)
        )
        micro_rows.append(
            micro_row(f"label-{index}", f"2026-07-04T00:{index:02d}:20Z", yes_mid=label_mid)
        )
    micro_path = write_json(
        tmp_path / "micro.json",
        safe_artifact(
            "sports_microstructure_observation_loop_ready",
            observation_packet={"rows": micro_rows},
        ),
    )
    return paper_fill_path, micro_path


def test_paper_fill_falsification_blocks_without_labels(tmp_path: Path) -> None:
    module = load_module()
    paper_fill = write_json(
        tmp_path / "paper-fill.json",
        safe_artifact(
            "passive_liquidity_paper_fill_loop_accumulating_intents",
            paper_intent_rows=[],
            paper_fill_label_rows=[],
        ),
    )
    micro = write_json(tmp_path / "micro.json", safe_artifact())

    report = module.build_passive_liquidity_paper_fill_falsification(
        paper_fill_path=paper_fill,
        microstructure_path=micro,
        generated_utc="2026-07-04T00:00:00Z",
        min_independent_labels=3,
        min_oos_labels=1,
        min_oos_fills=1,
    )

    assert report["status"] == (
        "passive_liquidity_paper_fill_falsification_blocked_no_paper_fill_labels"
    )
    assert report["summary"]["valid_paper_fill_label_count"] == 0
    assert report["execution_enabled"] is False
    assert report["account_or_order_paths"] is False


def test_paper_fill_falsification_blocks_timeout_only_labels(tmp_path: Path) -> None:
    module = load_module()
    paper_fill, micro = write_inputs(
        tmp_path,
        count=8,
        status="paper_expired_unfilled_no_public_touch",
    )

    report = module.build_passive_liquidity_paper_fill_falsification(
        paper_fill_path=paper_fill,
        microstructure_path=micro,
        generated_utc="2026-07-04T00:00:00Z",
        min_independent_labels=4,
        min_oos_labels=3,
        min_oos_fills=1,
        test_fraction=0.5,
    )

    assert report["status"] == "passive_liquidity_paper_fill_falsification_blocked_no_paper_fills"
    assert report["summary"]["valid_paper_fill_label_count"] == 8
    assert report["summary"]["paper_filled_count"] == 0
    assert report["summary"]["fdr_survivor_count"] == 0
    assert all(row["usable"] is False for row in report["evaluations"])


def test_paper_fill_falsification_can_fdr_pass_positive_paper_fills(tmp_path: Path) -> None:
    module = load_module()
    paper_fill, micro = write_inputs(
        tmp_path,
        count=8,
        status="paper_filled_from_later_public_touch",
        label_mid=0.52,
    )

    report = module.build_passive_liquidity_paper_fill_falsification(
        paper_fill_path=paper_fill,
        microstructure_path=micro,
        generated_utc="2026-07-04T00:00:00Z",
        min_independent_labels=4,
        min_oos_labels=3,
        min_oos_fills=3,
        test_fraction=0.5,
        fdr_alpha=0.10,
    )

    assert report["status"] == (
        "passive_liquidity_paper_fill_falsification_ready_with_research_candidates"
    )
    assert report["summary"]["paper_filled_count"] == 8
    assert report["summary"]["fdr_survivor_count"] >= 1
    winner = next(
        row for row in report["evaluations"] if row["status"] == "research_candidate_fdr_passed"
    )
    assert winner["maker_fill_net_ev_after_adverse_selection"] > 0
    assert winner["q_value"] <= 0.10
    assert winner["expected_value_per_contract"] is None
    assert winner["execution_enabled"] is False


def test_paper_fill_falsification_temp_out_dir_does_not_mutate_macro_latest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    macro_dir = tmp_path / "macro"
    monkeypatch.setattr(module, "MACRO_DIR", macro_dir)
    paper_fill, micro = write_inputs(
        tmp_path,
        count=1,
        status="paper_expired_unfilled_no_public_touch",
    )

    report = module.build_passive_liquidity_paper_fill_falsification(
        paper_fill_path=paper_fill,
        microstructure_path=micro,
        generated_utc="2026-07-04T00:00:00Z",
    )
    paths = module.write_outputs(report, out_dir=tmp_path / "out")

    assert "latest_json_path" not in paths
    assert not (
        macro_dir / "latest-kalshi-passive-liquidity-paper-fill-falsification.json"
    ).exists()
