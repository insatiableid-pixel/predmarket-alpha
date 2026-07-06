from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_passive_liquidity_paper_fill_loop.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_passive_liquidity_paper_fill_loop", SCRIPT_PATH
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
    ask: float = 0.56,
    ticker: str = "KXMLBGAME-26JUL04-BOS",
) -> dict[str, object]:
    return {
        "snapshot_id": snapshot_id,
        "contract_ticker": ticker,
        "observed_at_utc": observed_at,
        "best_yes_bid": 0.54,
        "best_yes_ask": ask,
        "best_no_bid": 0.44,
        "best_no_ask": 0.46,
        "yes_mid": 0.55,
        "research_only": True,
        "execution_enabled": False,
        "usable": False,
    }


def virtual_order(
    snapshot_id: str,
    expires_at: str,
    *,
    ticker: str = "KXMLBGAME-26JUL04-BOS",
) -> dict[str, object]:
    return {
        "virtual_order_id": f"virtual-{snapshot_id}",
        "contract_ticker": ticker,
        "side": "yes",
        "quote_price": 0.55,
        "quote_size_contracts": 1,
        "quote_rule": "improve_best_bid_one_tick",
        "snapshot_id": snapshot_id,
        "order_expires_at_utc": expires_at,
        "ttl_seconds": 180,
        "research_only": True,
        "execution_enabled": False,
    }


def test_passive_paper_fill_loop_labels_only_prior_intents(tmp_path: Path) -> None:
    module = load_module()
    state_dir = tmp_path / "state"
    out_dir = tmp_path / "out"
    passive_first = write_json(
        tmp_path / "passive-first.json",
        safe_artifact(
            "passive_liquidity_provision_blocked_proxy_only_no_real_fill_labels",
            virtual_order_rows=[
                virtual_order("snap-1", "2026-07-04T00:03:00Z"),
            ],
        ),
    )
    micro_first = write_json(
        tmp_path / "micro-first.json",
        safe_artifact(
            "sports_microstructure_observation_loop_ready",
            observation_packet={"rows": [micro_row("snap-1", "2026-07-04T00:00:00Z", ask=0.56)]},
        ),
    )

    first = module.build_passive_liquidity_paper_fill_loop(
        passive_path=passive_first,
        microstructure_path=micro_first,
        state_dir=state_dir,
        generated_utc="2026-07-04T00:00:30Z",
    )
    assert first["status"] == "passive_liquidity_paper_fill_loop_accumulating_intents"
    assert first["summary"]["new_paper_intent_count"] == 1
    assert first["summary"]["paper_fill_label_count"] == 0
    assert first["summary"]["new_intent_same_run_label_count"] == 0
    module.write_outputs(first, out_dir=out_dir, state_dir=state_dir)

    history_dir = tmp_path / "history"
    write_json(
        history_dir / "observations.json",
        safe_artifact(
            rows=[
                micro_row("snap-1", "2026-07-04T00:00:00Z", ask=0.56),
                micro_row("snap-2", "2026-07-04T00:01:00Z", ask=0.54),
                micro_row("snap-3", "2026-07-04T00:02:00Z", ask=0.53),
            ]
        ),
    )
    passive_second = write_json(
        tmp_path / "passive-second.json",
        safe_artifact(
            "passive_liquidity_provision_blocked_proxy_only_no_real_fill_labels",
            virtual_order_rows=[
                virtual_order("snap-2", "2026-07-04T00:04:00Z"),
            ],
        ),
    )
    micro_second = write_json(
        tmp_path / "micro-second.json",
        safe_artifact(
            "sports_microstructure_observation_loop_ready",
            inputs={"observation_dir": str(history_dir)},
            observation_packet={"rows": [micro_row("snap-2", "2026-07-04T00:01:00Z", ask=0.54)]},
        ),
    )

    second = module.build_passive_liquidity_paper_fill_loop(
        passive_path=passive_second,
        microstructure_path=micro_second,
        state_dir=state_dir,
        generated_utc="2026-07-04T00:02:30Z",
    )

    assert second["status"] == "passive_liquidity_paper_fill_loop_ready_with_paper_fill_labels"
    assert second["summary"]["persisted_prior_intent_count"] == 1
    assert second["summary"]["new_paper_intent_count"] == 1
    assert second["summary"]["paper_intent_count"] == 2
    assert second["summary"]["paper_fill_label_count"] == 1
    assert second["summary"]["new_paper_fill_label_count"] == 1
    assert second["summary"]["paper_filled_count"] == 1
    assert second["summary"]["open_paper_intent_count"] == 1
    assert second["summary"]["new_intent_same_run_label_count"] == 0
    label = second["paper_fill_label_rows"][0]
    assert label["paper_fill_status"] == "paper_filled_from_later_public_touch"
    assert label["label_snapshot_id"] == "snap-2"
    assert label["real_exchange_fill"] is False
    assert second["execution_enabled"] is False
    assert second["account_or_order_paths"] is False


def test_passive_paper_fill_loop_expires_prior_intent_without_touch(tmp_path: Path) -> None:
    module = load_module()
    state_dir = tmp_path / "state"
    passive_first = write_json(
        tmp_path / "passive-first.json",
        safe_artifact(virtual_order_rows=[virtual_order("snap-1", "2026-07-04T00:03:00Z")]),
    )
    micro_first = write_json(
        tmp_path / "micro-first.json",
        safe_artifact(
            observation_packet={"rows": [micro_row("snap-1", "2026-07-04T00:00:00Z", ask=0.58)]},
        ),
    )
    first = module.build_passive_liquidity_paper_fill_loop(
        passive_path=passive_first,
        microstructure_path=micro_first,
        state_dir=state_dir,
        generated_utc="2026-07-04T00:00:30Z",
    )
    module.write_outputs(first, out_dir=tmp_path / "out", state_dir=state_dir)

    history_dir = tmp_path / "history"
    write_json(
        history_dir / "observations.json",
        safe_artifact(
            rows=[
                micro_row("snap-1", "2026-07-04T00:00:00Z", ask=0.58),
                micro_row("snap-4", "2026-07-04T00:04:00Z", ask=0.57),
            ]
        ),
    )
    second = module.build_passive_liquidity_paper_fill_loop(
        passive_path=write_json(tmp_path / "passive-second.json", safe_artifact()),
        microstructure_path=write_json(
            tmp_path / "micro-second.json",
            safe_artifact(
                inputs={"observation_dir": str(history_dir)},
                observation_packet={
                    "rows": [micro_row("snap-4", "2026-07-04T00:04:00Z", ask=0.57)]
                },
            ),
        ),
        state_dir=state_dir,
        generated_utc="2026-07-04T00:04:30Z",
    )

    assert second["summary"]["paper_fill_label_count"] == 1
    assert second["summary"]["paper_expired_unfilled_count"] == 1
    assert second["paper_fill_label_rows"][0]["paper_fill_status"] == (
        "paper_expired_unfilled_no_public_touch"
    )


def test_passive_paper_fill_loop_temp_out_dir_does_not_mutate_macro_latest(
    tmp_path: Path, monkeypatch
) -> None:
    module = load_module()
    macro_dir = tmp_path / "macro"
    monkeypatch.setattr(module, "MACRO_DIR", macro_dir)
    passive_path = write_json(
        tmp_path / "passive.json",
        safe_artifact(virtual_order_rows=[virtual_order("snap-1", "2026-07-04T00:03:00Z")]),
    )
    micro_path = write_json(
        tmp_path / "micro.json",
        safe_artifact(
            observation_packet={"rows": [micro_row("snap-1", "2026-07-04T00:00:00Z", ask=0.56)]},
        ),
    )
    report = module.build_passive_liquidity_paper_fill_loop(
        passive_path=passive_path,
        microstructure_path=micro_path,
        state_dir=tmp_path / "state",
        generated_utc="2026-07-04T00:00:30Z",
    )
    paths = module.write_outputs(
        report,
        out_dir=tmp_path / "not-macro",
        state_dir=tmp_path / "state",
    )

    assert "latest_json_path" not in paths
    assert not (macro_dir / "latest-kalshi-passive-liquidity-paper-fill-loop.json").exists()
