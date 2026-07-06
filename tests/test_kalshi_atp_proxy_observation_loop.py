from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_atp_proxy_observation_loop.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_loop_module():
    spec = importlib.util.spec_from_file_location("kalshi_atp_proxy_observation_loop", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def outside_snapshot_path(tmp_path: Path) -> Path:
    return Path("/tmp") / "predmarket_atp_proxy_tests" / tmp_path.name / "matches.json"


def atp_snapshot(**overrides):
    payload = {
        "captured_at": "2026-07-03T15:00:00Z",
        "source": "atp-oracle",
        "series_ticker": "KXATPMATCH",
        "status_filter": "open",
        "n_matches": 1,
        "matches": [
            {
                "player_a": "Felix Auger-Aliassime",
                "player_b": "Michael Zheng",
                "kalshi_price_a": 0.97,
                "kalshi_price_b": 0.04,
                "kalshi_market_id_a": "KXATPMATCH-26JUL03AUGZHE-AUG",
                "kalshi_market_id_b": "KXATPMATCH-26JUL03AUGZHE-ZHE",
                "surface": "Grass",
                "best_of": 5,
                "tourney_name": "Wimbledon",
                "tourney_level": "G",
                "match_date": None,
                "_kalshi_event_ticker": "KXATPMATCH-26JUL03AUGZHE",
                "_yes_bid_a": 0.96,
                "_yes_bid_b": 0.03,
                "_yes_ask_a": 0.97,
                "_yes_ask_b": 0.04,
                "_no_bid_a": 0.03,
                "_no_bid_b": 0.96,
                "_no_ask_a": 0.04,
                "_no_ask_b": 0.97,
                "_last_price_a": 0.97,
                "_last_price_b": 0.03,
                "_volume_a": 904633.4,
                "_volume_b": 1526017.74,
                "_open_interest_a": 554747.97,
                "_open_interest_b": 974505.87,
                "_close_time_a": "2026-07-17T10:00:00Z",
                "_close_time_b": "2026-07-17T10:00:00Z",
            }
        ],
    }
    payload.update(overrides)
    return payload


def settled_snapshot(**overrides):
    payload = {
        "schema_version": 1,
        "created_at_utc": "2026-07-04T06:30:00Z",
        "status": "kalshi_public_observed_market_fetch_ok",
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
        "markets": [
            {
                "ticker": "KXATPMATCH-26JUL03AUGZHE-AUG",
                "event_ticker": "KXATPMATCH-26JUL03AUGZHE",
                "series_ticker": "KXATPMATCH",
                "result": "yes",
                "settlement_value_dollars": "1.0000",
                "close_time": "2026-07-03T18:00:00Z",
                "settlement_ts": "2026-07-03T19:30:00Z",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_atp_proxy_observation_loop_records_two_contract_observations_without_ev(
    tmp_path: Path,
) -> None:
    module = load_loop_module()
    snapshot_path = outside_snapshot_path(tmp_path)
    write_json(snapshot_path, atp_snapshot())

    report = module.build_atp_proxy_observation_loop(
        atp_match_snapshot_path=snapshot_path,
        settled_snapshot_path=tmp_path / "missing-settled.json",
        observation_dir=tmp_path / "observations",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-03T15:10:00Z",
    )

    assert report["status"] == "atp_proxy_observation_loop_ready_waiting_settlement"
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["summary"]["new_observation_row_count"] == 2
    assert report["summary"]["label_row_count"] == 0
    tickers = {row["contract_ticker"]: row for row in report["observation_packet"]["rows"]}
    assert set(tickers) == {
        "KXATPMATCH-26JUL03AUGZHE-AUG",
        "KXATPMATCH-26JUL03AUGZHE-ZHE",
    }
    row = tickers["KXATPMATCH-26JUL03AUGZHE-AUG"]
    assert row["player"] == "Felix Auger-Aliassime"
    assert row["opponent"] == "Michael Zheng"
    assert row["tourney_name"] == "Wimbledon"
    assert row["expected_expiration_time"] == "2026-07-04T06:00:00Z"
    assert row["expected_expiration_source"] == "event_ticker_date_next_morning_probe_schedule"
    assert row["calibrated_probability"] is None
    assert row["expected_value_per_contract"] is None
    assert row["usable"] is False


def test_atp_proxy_observation_loop_labels_exact_ticker_from_public_settlement(
    tmp_path: Path,
) -> None:
    module = load_loop_module()
    snapshot_path = outside_snapshot_path(tmp_path)
    settled_path = tmp_path / "settled.json"
    write_json(snapshot_path, atp_snapshot())
    write_json(settled_path, settled_snapshot())

    report = module.build_atp_proxy_observation_loop(
        atp_match_snapshot_path=snapshot_path,
        settled_snapshot_path=settled_path,
        observation_dir=tmp_path / "observations",
        label_dir=tmp_path / "labels",
        generated_utc="2026-07-04T06:30:00Z",
    )

    assert report["status"] == "atp_proxy_observation_loop_label_rows_ready"
    assert report["summary"]["label_row_count"] == 1
    label = report["label_packet"]["rows"][0]
    assert label["contract_ticker"] == "KXATPMATCH-26JUL03AUGZHE-AUG"
    assert label["label_status"] == "labeled_from_public_kalshi_settled_market"
    assert label["yes_outcome"] == 1
    assert label["label_source"] == "public_kalshi_settled_market_payload"
    assert label["usable"] is False


def test_due_observed_tickers_uses_event_date_probe_schedule(tmp_path: Path) -> None:
    module = load_loop_module()
    snapshot_path = outside_snapshot_path(tmp_path)
    write_json(snapshot_path, atp_snapshot())

    before = module.due_observed_tickers(
        atp_match_snapshot_path=snapshot_path,
        observation_dir=tmp_path / "observations",
        generated_utc="2026-07-04T05:59:00Z",
        max_tickers=10,
    )
    after = module.due_observed_tickers(
        atp_match_snapshot_path=snapshot_path,
        observation_dir=tmp_path / "observations",
        generated_utc="2026-07-04T06:01:00Z",
        max_tickers=10,
    )

    assert before == []
    assert after == [
        "KXATPMATCH-26JUL03AUGZHE-AUG",
        "KXATPMATCH-26JUL03AUGZHE-ZHE",
    ]


def test_capture_public_observed_markets_snapshot_fetches_exact_atp_tickers(
    tmp_path: Path,
) -> None:
    module = load_loop_module()
    calls: list[str] = []

    def fake_fetch(url: str):
        calls.append(url)
        return {
            "market": {
                "ticker": "KXATPMATCH-26JUL03AUGZHE-AUG",
                "result": "yes",
                "settlement_value_dollars": "1.0000",
            }
        }

    latest_path = module.capture_public_observed_markets_snapshot(
        tickers=["KXATPMATCH-26JUL03AUGZHE-AUG"],
        raw_dir=tmp_path / "settled",
        generated_utc="2026-07-04T06:30:00Z",
        fetch_json=fake_fetch,
    )
    payload = json.loads(latest_path.read_text(encoding="utf-8"))

    assert payload["status"] == "kalshi_public_observed_market_fetch_ok"
    assert payload["summary"]["settled_label_ready_count"] == 1
    assert payload["markets"][0]["ticker"] == "KXATPMATCH-26JUL03AUGZHE-AUG"
    assert calls == [
        "https://external-api.kalshi.com/trade-api/v2/markets/KXATPMATCH-26JUL03AUGZHE-AUG"
    ]


def test_atp_proxy_observation_loop_writes_latest_artifacts_and_packets(
    tmp_path: Path,
) -> None:
    module = load_loop_module()
    module.MACRO_DIR = tmp_path / "macro"
    snapshot_path = outside_snapshot_path(tmp_path)
    settled_path = tmp_path / "settled.json"
    observation_dir = tmp_path / "manual" / "observations"
    label_dir = tmp_path / "manual" / "labels"
    write_json(snapshot_path, atp_snapshot())
    write_json(settled_path, settled_snapshot())
    report = module.build_atp_proxy_observation_loop(
        atp_match_snapshot_path=snapshot_path,
        settled_snapshot_path=settled_path,
        observation_dir=observation_dir,
        label_dir=label_dir,
        generated_utc="2026-07-04T06:30:00Z",
    )

    paths = module.write_atp_proxy_observation_outputs(
        report,
        out_dir=tmp_path / "out",
        observation_dir=observation_dir,
        label_dir=label_dir,
    )

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    assert Path(paths["schedule_template_path"]).exists()
    assert Path(paths["latest_json_path"]).exists()
    assert Path(paths["observation_packet_latest_path"]).exists()
    assert Path(paths["label_packet_latest_path"]).exists()
    latest = json.loads(Path(paths["latest_json_path"]).read_text(encoding="utf-8"))
    assert latest["summary"]["label_row_count"] == 1


def test_atp_proxy_observation_makefile_targets_are_registered() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-atp-proxy-observation-loop" in text
    assert "kalshi-atp-proxy-observation-watch-once" in text
    assert "KALSHI_ATP_PROXY_MATCH_SNAPSHOT" in text
