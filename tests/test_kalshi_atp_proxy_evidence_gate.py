from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kalshi_atp_proxy_evidence_gate.py"
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_gate_module():
    spec = importlib.util.spec_from_file_location("kalshi_atp_proxy_evidence_gate", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def observation_report(label_count: int = 0):
    return {
        "schema_version": 1,
        "status": "atp_proxy_observation_loop_ready_waiting_settlement",
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": False,
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "staking_or_sizing_guidance": False,
        "summary": {
            "total_observation_row_count": 24,
            "label_row_count": label_count,
            "next_public_label_probe_utc": "2026-07-04T06:00:00Z",
            "next_expected_expiration_utc": "2026-07-04T10:00:00Z",
        },
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }


def forward_report(resolved: int = 2, clv_lower: float = -20.0):
    return {
        "verdict": "blocked",
        "summary": "2 resolved (need >= 10). Collecting evidence.",
        "n_resolved": resolved,
        "min_resolved_for_probe": 10,
        "min_resolved_for_stake": 25,
        "probe_bankroll_eligible": resolved >= 10,
        "first_real_stake_eligible": resolved >= 25 and clv_lower > 0,
        "true_clv_ci95_lower_pp": clv_lower,
        "true_clv_mean_pp": clv_lower + 10,
        "true_clv_threshold_pp": 0,
    }


def liquidity_report(passing: int = 6):
    return {
        "summary": {
            "gate_passes_for_first_stake": passing >= 25,
            "passing_candidates": passing,
            "required_passing_candidates": 25,
            "reason": "insufficient_executable_liquidity_depth",
        }
    }


def bettable_report(status: str = "blocked"):
    return {
        "status": status,
        "bettable_count": 0 if status == "blocked" else 3,
        "candidate_count": 24,
    }


def prices_report():
    return {"summary": {"usable_for_true_clv_total": 143, "errors_count": 0}}


def build_report(
    module, tmp_path: Path, *, labels=0, resolved=2, clv_lower=-20, liquidity=6, bettable="blocked"
):
    paths = {
        "observation": tmp_path / "observation.json",
        "forward": tmp_path / "forward.json",
        "liquidity": tmp_path / "liquidity.json",
        "bettable": tmp_path / "bettable.json",
        "prices": tmp_path / "prices.json",
    }
    write_json(paths["observation"], observation_report(labels))
    write_json(paths["forward"], forward_report(resolved, clv_lower))
    write_json(paths["liquidity"], liquidity_report(liquidity))
    write_json(paths["bettable"], bettable_report(bettable))
    write_json(paths["prices"], prices_report())
    return module.build_atp_proxy_evidence_gate(
        observation_loop_path=paths["observation"],
        forward_oos_path=paths["forward"],
        liquidity_path=paths["liquidity"],
        bettable_gate_path=paths["bettable"],
        price_observations_path=paths["prices"],
        min_settled_labels=10,
        generated_utc="2026-07-03T20:10:00Z",
    )


def test_atp_proxy_evidence_gate_blocks_waiting_for_settlement_labels(tmp_path: Path) -> None:
    module = load_gate_module()

    report = build_report(module, tmp_path)

    assert report["status"] == "atp_proxy_evidence_gate_blocked_waiting_settlement_labels"
    assert report["research_only"] is True
    assert report["execution_enabled"] is False
    assert report["summary"]["settled_label_count"] == 0
    assert report["summary"]["next_expected_expiration_utc"] == "2026-07-04T10:00:00Z"
    gates = {item["gate"]: item for item in report["gates"]}
    assert gates["settled_labels_available"]["status"] == "blocked"
    assert gates["forward_oos_probe_sample"]["status"] == "blocked"
    assert gates["executable_liquidity_depth"]["status"] == "blocked"
    assert gates["bettable_line_gate"]["status"] == "blocked"
    assert gates["no_ev_sizing_or_execution"]["status"] == "pass"


def test_atp_proxy_evidence_gate_ready_only_when_all_upstream_gates_pass(tmp_path: Path) -> None:
    module = load_gate_module()

    report = build_report(
        module,
        tmp_path,
        labels=12,
        resolved=30,
        clv_lower=1.5,
        liquidity=30,
        bettable="ready",
    )

    assert report["status"] == "atp_proxy_evidence_gate_ready_for_falsification"
    assert all(item["status"] == "pass" for item in report["gates"])


def test_atp_proxy_evidence_gate_writer_emits_latest_artifacts(tmp_path: Path) -> None:
    module = load_gate_module()
    module.MACRO_DIR = tmp_path / "macro"
    report = build_report(module, tmp_path)

    paths = module.write_atp_proxy_evidence_gate(report, out_dir=tmp_path / "out")

    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["csv_path"]).exists()
    assert Path(paths["latest_json_path"]).exists()
    latest = json.loads(Path(paths["latest_json_path"]).read_text(encoding="utf-8"))
    assert latest["status"] == "atp_proxy_evidence_gate_blocked_waiting_settlement_labels"


def test_atp_proxy_evidence_gate_makefile_target_registered() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-atp-proxy-evidence-gate" in text
    assert "scripts/kalshi_atp_proxy_evidence_gate.py" in text
