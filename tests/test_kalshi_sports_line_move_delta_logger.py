from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_line_move_delta_logger.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_sports_line_move_delta_logger", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def payload(price: int = -120) -> list[dict]:
    return [
        {
            "id": "evt-det-tex",
            "sport_key": "baseball_mlb",
            "commence_time": "2026-07-04T20:06:00Z",
            "away_team": "Detroit Tigers",
            "home_team": "Texas Rangers",
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "title": "Pinnacle",
                    "last_update": "2026-07-04T20:00:00Z",
                    "markets": [
                        {
                            "key": "h2h",
                            "last_update": "2026-07-04T20:00:00Z",
                            "outcomes": [
                                {"name": "Detroit Tigers", "price": price},
                                {"name": "Texas Rangers", "price": 110},
                            ],
                        }
                    ],
                }
            ],
        }
    ]


def test_extract_quotes_builds_stable_quote_keys() -> None:
    module = load_module()

    rows = module.extract_quotes(
        payload(),
        sport_key="baseball_mlb",
        captured_at_utc="2026-07-04T20:01:00Z",
    )

    assert len(rows) == 2
    assert rows[0]["quote_key"]
    assert rows[0]["sport_key"] == "baseball_mlb"
    assert rows[0]["bookmaker_key"] == "pinnacle"
    assert rows[0]["market_key"] == "h2h"


def test_delta_logger_writes_initial_then_only_changed_quotes(tmp_path: Path) -> None:
    module = load_module()
    key_file = tmp_path / "odds.key"
    key_file.write_text("secret-key", encoding="utf-8")
    state_dir = tmp_path / "state"
    price = -120

    def transport(url: str, timeout: float):
        assert "secret-key" in url
        assert timeout == 2.0
        return module.HttpResponse(
            status_code=200,
            headers={"x-requests-used": "1"},
            body=json.dumps(payload(price)).encode("utf-8"),
        )

    first = module.run_delta_logger(
        sport_keys=["baseball_mlb"],
        bookmakers=["pinnacle"],
        markets=["h2h"],
        state_dir=state_dir,
        api_key_file=key_file,
        timeout_seconds=2.0,
        generated_utc="2026-07-04T20:01:00Z",
        transport=transport,
    )
    assert first["status"] == "kalshi_sports_line_move_delta_logger_ready_with_deltas"
    assert first["summary"]["initial_quote_count"] == 2
    assert first["summary"]["line_move_count"] == 0

    second = module.run_delta_logger(
        sport_keys=["baseball_mlb"],
        bookmakers=["pinnacle"],
        markets=["h2h"],
        state_dir=state_dir,
        api_key_file=key_file,
        timeout_seconds=2.0,
        generated_utc="2026-07-04T20:02:00Z",
        transport=transport,
    )
    assert second["status"] == "kalshi_sports_line_move_delta_logger_ready_no_deltas"
    assert second["summary"]["delta_count"] == 0

    price = -130
    third = module.run_delta_logger(
        sport_keys=["baseball_mlb"],
        bookmakers=["pinnacle"],
        markets=["h2h"],
        state_dir=state_dir,
        api_key_file=key_file,
        timeout_seconds=2.0,
        generated_utc="2026-07-04T20:03:00Z",
        transport=transport,
    )
    assert third["status"] == "kalshi_sports_line_move_delta_logger_ready_with_deltas"
    assert third["summary"]["line_move_count"] == 1

    lines = (
        (state_dir / "sports_line_move_deltas_20260704.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(lines) == 3
    last = json.loads(lines[-1])
    assert last["delta_type"] == "line_move"
    assert last["previous_price"] == -120
    assert last["new_price"] == -130
    assert last["signal_or_probability"] is False


def test_delta_logger_missing_key_blocks_without_provider_call(tmp_path: Path) -> None:
    module = load_module()

    result = module.run_delta_logger(
        sport_keys=["baseball_mlb"],
        bookmakers=["pinnacle"],
        markets=["h2h"],
        state_dir=tmp_path / "state",
        api_key_file=tmp_path / "missing.key",
        generated_utc="2026-07-04T20:01:00Z",
    )

    assert result["status"] == "kalshi_sports_line_move_delta_logger_blocked_missing_api_key"
    assert result["provider_api_calls"] is False
    assert result["api_key_printed"] is False
    assert result["execution_enabled"] is False
    assert result["market_execution"] is False


def test_generic_tennis_key_falls_back_to_wimbledon(tmp_path: Path) -> None:
    module = load_module()
    key_file = tmp_path / "odds.key"
    key_file.write_text("secret-key", encoding="utf-8")
    requested_urls: list[str] = []

    def transport(url: str, timeout: float):
        requested_urls.append(url)
        if "/tennis_atp/odds/" in url:
            return module.HttpResponse(
                status_code=404,
                headers={},
                body=json.dumps({"message": "sport not found"}).encode("utf-8"),
            )
        assert "/tennis_atp_wimbledon/odds/" in url
        tennis_payload = payload()
        tennis_payload[0]["sport_key"] = "tennis_atp_wimbledon"
        return module.HttpResponse(
            status_code=200,
            headers={"x-requests-used": "2"},
            body=json.dumps(tennis_payload).encode("utf-8"),
        )

    result = module.run_delta_logger(
        sport_keys=["tennis_atp"],
        bookmakers=["pinnacle"],
        markets=["h2h"],
        state_dir=tmp_path / "state",
        api_key_file=key_file,
        timeout_seconds=2.0,
        generated_utc="2026-07-04T20:01:00Z",
        transport=transport,
    )

    assert result["status"] == "kalshi_sports_line_move_delta_logger_ready_with_deltas"
    assert len(requested_urls) == 2
    assert result["summary"]["sport_key_fallback_count"] == 1
    assert result["summary"]["error_count"] == 0
    assert result["sport_key_fallbacks"][0]["requested_sport_key"] == "tennis_atp"
    assert result["sport_key_fallbacks"][0]["resolved_sport_key"] == "tennis_atp_wimbledon"
