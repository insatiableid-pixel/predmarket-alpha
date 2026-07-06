from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_near_resolution_flow_terms_capture.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "kalshi_near_resolution_flow_terms_capture", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def test_flow_terms_capture_fetches_public_market_rules(tmp_path: Path) -> None:
    module = load_module()
    flow_path = write_json(
        tmp_path / "flow.json",
        {
            "status": "near_resolution_flow_replay_gates_ready_for_ev_ledger_promotion",
            "capacity_rows": [
                {
                    "contract_ticker": "KXFLOW-YES",
                    "gate_status": "pass",
                },
                {
                    "contract_ticker": "KXFLOW-BLOCKED",
                    "gate_status": "blocked",
                },
            ],
        },
    )

    def fake_fetch(url: str) -> dict[str, object]:
        assert url.endswith("/markets/KXFLOW-YES")
        return {
            "market": {
                "ticker": "KXFLOW-YES",
                "event_ticker": "KXFLOW",
                "status": "active",
                "rules_primary": "If the selected side wins, this market resolves to Yes.",
                "rules_secondary": "Official Kalshi terms govern postponements.",
            }
        }

    with tempfile.TemporaryDirectory(prefix="kalshi-flow-terms-", dir="/tmp") as raw_dir:
        report = module.build_flow_terms_capture(
            flow_replay_path=flow_path,
            raw_terms_dir=Path(raw_dir),
            generated_utc="2026-07-04T12:00:00Z",
            capture_terms=True,
            fetch_json=fake_fetch,
            delay_seconds=0.0,
        )

        assert report["status"] == "near_resolution_flow_terms_capture_ready"
        assert report["summary"]["selected_ticker_count"] == 1
        assert report["summary"]["captured_target_count"] == 1
        assert report["summary"]["official_rules_market_count"] == 1
        raw_path = Path(str(report["summary"]["raw_terms_path"]))
        assert raw_path.name.startswith("kalshi_scored_sports_flow_terms_")
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        assert raw["all_scored"][0]["ticker"] == "KXFLOW-YES"
        assert raw["safety"]["market_execution"] is False


def test_flow_terms_capture_makefile_target_registered() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-near-resolution-flow-terms-capture:" in text
    assert "scripts/kalshi_near_resolution_flow_terms_capture.py" in text
