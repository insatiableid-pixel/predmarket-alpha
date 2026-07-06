from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "kalshi_sports_blocker_clearance_cycle.py"
)
MAKEFILE_PATH = Path(__file__).resolve().parents[1] / "Makefile"


def load_module():
    spec = importlib.util.spec_from_file_location("kalshi_sports_blocker_clearance_cycle", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def event_velocity(next_probe: str):
    return {
        "schema_version": 1,
        "status": "sports_event_velocity_eta_ready_with_label_deficits",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "summary": {
            "total_label_deficit": 110,
            "total_oos_deficit": 51,
            "next_probe_surface": {
                "surface_id": "sports_consensus_rule_bucket_accumulation",
                "next_probe_utc": next_probe,
                "oos_deficit": 5,
            },
        },
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }


def atp_gate(*, resolved: int = 8, minimum: int = 10, next_probe: str = "2026-07-07T06:00:00Z"):
    return {
        "schema_version": 1,
        "status": "atp_proxy_evidence_gate_blocked_forward_oos",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "summary": {
            "forward_oos_resolved": resolved,
            "forward_oos_min_probe": minimum,
            "next_expected_expiration_utc": next_probe,
        },
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
            "database_writes": False,
        },
    }


def audit():
    return {
        "schema_version": 1,
        "status": "claude_advice_audit_ready_with_open_clock_or_statistical_items",
        "summary": {
            "open_requirement_ids": ["CLAUDE-005", "CLAUDE-008"],
            "implementation_satisfied_count": 10,
            "implementation_open_requirement_ids": [],
        },
    }


def build_report(module, tmp_path: Path, *, event_probe: str, atp_probe: str, run_due=False):
    event_path = write_json(tmp_path / "event.json", event_velocity(event_probe))
    atp_path = write_json(tmp_path / "atp.json", atp_gate(next_probe=atp_probe))
    audit_path = write_json(tmp_path / "audit.json", audit())
    return module.build_report(
        event_velocity_path=event_path,
        atp_gate_path=atp_path,
        audit_path=audit_path,
        atp_repo=tmp_path / "atp-oracle",
        now=datetime(2026, 7, 6, 19, 15, tzinfo=UTC),
        run_due=run_due,
    )


def test_blocker_clearance_cycle_waits_when_no_clock_is_due(tmp_path: Path) -> None:
    module = load_module()

    report = build_report(
        module,
        tmp_path,
        event_probe="2026-07-06T21:10:00Z",
        atp_probe="2026-07-07T06:00:00Z",
    )

    assert report["status"] == "sports_blocker_clearance_cycle_waiting_for_next_clock"
    assert report["summary"]["due_task_count"] == 0
    assert report["summary"]["waiting_task_count"] == 2
    assert report["summary"]["next_clock_utc"] == "2026-07-06T21:10:00Z"
    assert report["summary"]["implementation_satisfied_count"] == 10
    assert report["summary"]["implementation_open_requirement_ids"] == []
    assert report["command_results"] == []
    assert report["execution_enabled"] is False
    assert report["account_or_order_paths"] is False


def test_blocker_clearance_cycle_lists_due_commands_without_running(tmp_path: Path) -> None:
    module = load_module()

    report = build_report(
        module,
        tmp_path,
        event_probe="2026-07-06T18:10:00Z",
        atp_probe="2026-07-07T06:00:00Z",
    )

    due_tasks = [task for task in report["tasks"] if task["due"]]
    assert report["status"] == "sports_blocker_clearance_cycle_due_actions_available"
    assert report["summary"]["due_task_count"] == 1
    assert due_tasks[0]["task_id"] == "sports_consensus_settlement_probe"
    assert due_tasks[0]["commands"][0] == [
        "make",
        "kalshi-sports-paper-burn-in-cycle",
        "KALSHI_SPORTS_PAPER_BURN_IN_FETCH=1",
    ]
    assert report["command_results"] == []


def test_blocker_clearance_cycle_run_due_executes_due_commands(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    calls = []

    def fake_run(command, *, cwd, timeout_seconds, task_id):
        calls.append((tuple(command), cwd, timeout_seconds, task_id))
        return {
            "task_id": task_id,
            "command": list(command),
            "returncode": 0,
            "stdout_tail": "ok",
            "stderr_tail": "",
        }

    monkeypatch.setattr(module, "run_command", fake_run)

    report = build_report(
        module,
        tmp_path,
        event_probe="2026-07-06T18:10:00Z",
        atp_probe="2026-07-07T06:00:00Z",
        run_due=True,
    )

    assert report["status"] == "sports_blocker_clearance_cycle_ran_due_actions"
    assert report["summary"]["commands_executed_count"] == 2
    assert calls[0][0] == (
        "make",
        "kalshi-sports-paper-burn-in-cycle",
        "KALSHI_SPORTS_PAPER_BURN_IN_FETCH=1",
    )
    assert calls[1][0] == ("make", "kalshi-claude-advice-audit")
    assert report["public_market_data_calls"] is True


def test_blocker_clearance_cycle_makefile_target_exists() -> None:
    text = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "kalshi-sports-blocker-clearance-cycle" in text
    assert "scripts/kalshi_sports_blocker_clearance_cycle.py" in text
