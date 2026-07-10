from __future__ import annotations

import importlib.util
from pathlib import Path

from predmarket.sports_mlb_settlement_miscalibration import (
    build_fixed_clock_labels,
    hold_to_settlement_economics,
    hypothesis_registry,
    normalize_observation_row,
    select_asof_book,
    taker_fee,
    validate_book,
)
from predmarket.sports_mlb_settlement_miscalibration_eval import (
    apply_fdr,
    collapse_event_independence,
    eligible_signal_rows,
    evaluate_hypothesis,
    synthetic_tests,
)


def load_script():
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "kalshi_sports_mlb_settlement_miscalibration.py"
    )
    spec = importlib.util.spec_from_file_location(
        "kalshi_sports_mlb_settlement_miscalibration", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _obs(
    *,
    ticker: str,
    event: str,
    observed_at: str,
    yes_mid: float,
    snapshot_id: str,
) -> dict:
    half_spread = 0.01
    row = normalize_observation_row(
        {
            "snapshot_id": snapshot_id,
            "contract_ticker": ticker,
            "event_ticker": event,
            "series_ticker": "KXMLBGAME",
            "observed_at_utc": observed_at,
            "best_yes_bid": round(yes_mid - half_spread, 4),
            "best_yes_ask": round(yes_mid + half_spread, 4),
            "best_no_bid": round(1 - (yes_mid + half_spread), 4),
            "best_no_ask": round(1 - (yes_mid - half_spread), 4),
            "yes_bid_depth_top1": 20.0,
            "yes_ask_depth_top1": 18.0,
            "no_bid_depth_top1": 15.0,
            "no_ask_depth_top1": 16.0,
            "yes_mid": yes_mid,
            "yes_spread": 0.02,
            "total_depth_contracts": 100.0,
            "entry_source": "test",
        },
        source_path="test",
        source_sha256="test",
        index=0,
    )
    assert row is not None
    return row


def test_validate_book_and_fee() -> None:
    ok, reason = validate_book(0.6, 0.5)
    assert not ok
    assert reason == "crossed_book"
    fee = taker_fee(0.5)
    assert fee > 0
    econ = hold_to_settlement_economics(
        side="yes",
        yes_ask=0.5,
        no_ask=0.5,
        yes_outcome=1,
        yes_ask_depth=10,
        no_ask_depth=10,
    )
    assert econ["label_status"] == "hold_to_settlement_labeled"
    assert econ["net_payoff_per_contract"] == econ["gross_payoff_per_contract"] - econ["entry_fee"]
    assert econ["entry_fee"] == fee


def test_asof_never_future_and_staleness() -> None:
    books = [
        _obs(
            ticker="KXMLBGAME-26JUL081805BOSNYY-BOS",
            event="KXMLBGAME-26JUL081805BOSNYY",
            observed_at="2026-07-08T21:55:00Z",
            yes_mid=0.55,
            snapshot_id="a",
        ),
        _obs(
            ticker="KXMLBGAME-26JUL081805BOSNYY-BOS",
            event="KXMLBGAME-26JUL081805BOSNYY",
            observed_at="2026-07-08T22:05:00Z",
            yes_mid=0.80,
            snapshot_id="future",
        ),
    ]
    # clock at 22:00 — prior book is 5m old; future book must not win.
    clock_ts = books[0]["observed_ts"] + 300
    selected, status = select_asof_book(books, clock_ts=clock_ts, max_staleness_seconds=900)
    assert status == "matched"
    assert selected is not None
    assert selected["snapshot_id"] == "a"

    stale_only = [books[0]]
    selected2, status2 = select_asof_book(
        stale_only, clock_ts=clock_ts + 7200, max_staleness_seconds=900
    )
    assert selected2 is None
    assert status2 == "censored_stale_book"


def test_synthetic_suite_passes() -> None:
    results = synthetic_tests()
    assert results
    failed = [item for item in results if not item.get("passed")]
    assert not failed, failed


def test_fixed_clock_labels_and_independence() -> None:
    game = "KXMLBGAME-26JUL081805BOSNYY"
    observations = []
    for team, mid in (("BOS", 0.58), ("NYY", 0.42)):
        for hour, snap in ((20, "h20"), (21, "h21"), (22, "h22")):
            observations.append(
                _obs(
                    ticker=f"{game}-{team}",
                    event=game,
                    observed_at=f"2026-07-08T{hour}:50:00Z",
                    yes_mid=mid + (0.01 if hour == 22 else 0.0),
                    snapshot_id=f"{team}-{snap}",
                )
            )
    settlements = {
        f"{game}-BOS": {
            "ticker": f"{game}-BOS",
            "event_ticker": game,
            "result": "yes",
            "occurrence_datetime": "2026-07-08T23:05:00Z",
            "open_time": "2026-07-06T12:00:00Z",
        },
        f"{game}-NYY": {
            "ticker": f"{game}-NYY",
            "event_ticker": game,
            "result": "no",
            "occurrence_datetime": "2026-07-08T23:05:00Z",
            "open_time": "2026-07-06T12:00:00Z",
        },
    }
    labels, summary = build_fixed_clock_labels(
        observations,
        settlements,
        clocks={"T-60m": 3600, "T-15m": 900},
        staleness={"T-60m": 15 * 60, "T-15m": 10 * 60},
    )
    labeled = [row for row in labels if row["label_status"] == "labeled"]
    assert labeled
    assert summary["labeled_row_count"] == len(labeled)
    # Fees applied on yes side for winner.
    yes_row = next(row for row in labeled if row["contract_ticker"].endswith("-BOS"))
    assert yes_row["yes_net_payoff"] < yes_row["yes_gross_payoff"]
    assert yes_row["yes_settlement_payoff"] == 1.0

    fired = eligible_signal_rows(
        labeled,
        {
            "clock_name": "T-60m",
            "side": "yes",
            "feature": "p_hat",
            "direction": "gt",
            "threshold": 0.01,
        },
    )
    collapsed = collapse_event_independence(fired)
    assert len(collapsed) == 1


def test_registry_finite_and_evaluation_runs() -> None:
    registry = hypothesis_registry()
    assert 8 <= len(registry) <= 12
    assert any(row.get("baseline_only") for row in registry)
    assert sum(1 for row in registry if row.get("negative_control")) >= 2
    assert (
        sum(
            1
            for row in registry
            if not row.get("baseline_only") and not row.get("negative_control")
        )
        <= 10
    )

    # Build a tiny multi-event panel with known economics for evaluation plumbing.
    labels = []
    for index in range(30):
        event = f"KXMLBGAME-26JUL{index:02d}1800AAAABB"
        ticker = f"{event}-AAA"
        mid = 0.30 if index % 2 == 0 else 0.75
        obs = _obs(
            ticker=ticker,
            event=event,
            observed_at=f"2026-07-{(index % 28) + 1:02d}T17:00:00Z",
            yes_mid=mid,
            snapshot_id=f"s{index}",
        )
        settlements = {
            ticker: {
                "ticker": ticker,
                "event_ticker": event,
                "result": "yes" if index % 3 != 0 else "no",
                "occurrence_datetime": f"2026-07-{(index % 28) + 1:02d}T18:00:00Z",
                "open_time": f"2026-07-{(index % 28) + 1:02d}T00:00:00Z",
            }
        }
        built, _ = build_fixed_clock_labels(
            [obs],
            settlements,
            clocks={"T-60m": 3600},
            staleness={"T-60m": 2 * 3600},
        )
        labels.extend(built)

    evaluations = [
        evaluate_hypothesis(labels, spec, min_oos_labels=5, min_events=5)
        for spec in registry
        if spec["clock_name"] == "T-60m"
    ]
    evaluations = apply_fdr(evaluations, alpha=0.05)
    assert evaluations
    assert all("status" in row for row in evaluations)


def test_script_builds_report_without_network(tmp_path: Path) -> None:
    module = load_script()
    obs_dir = tmp_path / "obs"
    sett_dir = tmp_path / "sett"
    obs_dir.mkdir()
    sett_dir.mkdir()
    # Minimal packet.
    packet = {
        "rows": [
            {
                "snapshot_id": "snap1",
                "contract_ticker": "KXMLBGAME-26JUL081805BOSNYY-BOS",
                "event_ticker": "KXMLBGAME-26JUL081805BOSNYY",
                "series_ticker": "KXMLBGAME",
                "observed_at_utc": "2026-07-08T22:00:00Z",
                "best_yes_bid": 0.54,
                "best_yes_ask": 0.56,
                "best_no_bid": 0.44,
                "best_no_ask": 0.46,
                "yes_bid_depth_top1": 10,
                "yes_ask_depth_top1": 12,
                "no_bid_depth_top1": 8,
                "no_ask_depth_top1": 9,
                "yes_mid": 0.55,
                "yes_spread": 0.02,
            }
        ]
    }
    (obs_dir / "obs.json").write_text(__import__("json").dumps(packet), encoding="utf-8")
    markets = {
        "markets": [
            {
                "ticker": "KXMLBGAME-26JUL081805BOSNYY-BOS",
                "event_ticker": "KXMLBGAME-26JUL081805BOSNYY",
                "result": "yes",
                "occurrence_datetime": "2026-07-08T23:05:00Z",
                "open_time": "2026-07-05T12:00:00Z",
            }
        ]
    }
    (sett_dir / "sett.json").write_text(__import__("json").dumps(markets), encoding="utf-8")
    report = module.build_report(
        observation_dirs=[obs_dir],
        settlement_dirs=[sett_dir],
        proxy_label_dir=tmp_path / "empty_labels",
        raw_dir=tmp_path / "raw",
        discovery_cutoff_utc="2026-07-10T00:00:00Z",
        fetch_public_settlements=False,
        fdr_alpha=0.05,
        min_oos_events=5,
    )
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["family_id"] == "sports_mlb_settlement_miscalibration_v1"
    assert "evaluations" in report
    written = module.write_outputs(report, out_dir=tmp_path / "out")
    assert Path(written["json"]).is_file()
    assert Path(written["md"]).is_file()
