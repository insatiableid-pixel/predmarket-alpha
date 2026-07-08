#!/usr/bin/env python3
"""Run or plan the next sports blocker-clearance cycle.

This is a control-plane runner. It only refreshes research artifacts when a
known settlement/probe clock is due; it never promotes candidates, sizes stake,
or touches account/order paths.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import (  # noqa: E402
    path_is_within,
    project_path,
    read_json_or_empty,
    safety_flags,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_EVENT_VELOCITY_PATH = MACRO_DIR / "latest-kalshi-sports-event-velocity-eta.json"
DEFAULT_ATP_GATE_PATH = MACRO_DIR / "latest-kalshi-atp-proxy-evidence-gate.json"
DEFAULT_AUDIT_PATH = MACRO_DIR / "latest-kalshi-claude-advice-audit.json"
DEFAULT_ATP_REPO = project_path("atp-oracle")
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-sports-blocker-clearance-cycle-latest"
DEFAULT_PREVIOUS_CYCLE_PATH = MACRO_DIR / "latest-kalshi-sports-blocker-clearance-cycle.json"
DEFAULT_DUE_RETRY_COOLDOWN_SECONDS = 900


@dataclass(frozen=True)
class PlannedTask:
    task_id: str
    surface_id: str
    due_utc: str | None
    due: bool
    reason: str
    commands: tuple[tuple[str, ...], ...]
    backoff_until_utc: str | None = None
    fallback_retry_utc: str | None = None


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_string(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_utc(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def build_report(
    *,
    event_velocity_path: Path = DEFAULT_EVENT_VELOCITY_PATH,
    atp_gate_path: Path = DEFAULT_ATP_GATE_PATH,
    audit_path: Path = DEFAULT_AUDIT_PATH,
    atp_repo: Path = DEFAULT_ATP_REPO,
    previous_cycle_path: Path | None = None,
    now: datetime | None = None,
    run_due: bool = False,
    command_timeout_seconds: int = 900,
    due_retry_cooldown_seconds: int = DEFAULT_DUE_RETRY_COOLDOWN_SECONDS,
) -> dict[str, Any]:
    generated = now or utc_now()
    event_velocity = read_json_or_empty(event_velocity_path)
    atp_gate = read_json_or_empty(atp_gate_path)
    audit = read_json_or_empty(audit_path)
    previous_cycle = read_json_or_empty(previous_cycle_path) if previous_cycle_path else {}
    tasks = build_tasks(
        event_velocity=event_velocity,
        atp_gate=atp_gate,
        atp_repo=atp_repo,
        now=generated,
    )
    tasks = apply_recent_due_backoff(
        tasks,
        previous_cycle=previous_cycle,
        now=generated,
        cooldown_seconds=due_retry_cooldown_seconds,
    )
    due_tasks = [task for task in tasks if task.due]
    results: list[dict[str, Any]] = []
    if run_due:
        for task in due_tasks:
            results.extend(run_task(task, timeout_seconds=command_timeout_seconds))
        if due_tasks:
            results.append(
                run_command(
                    ("make", "kalshi-claude-advice-audit"),
                    cwd=CONTROL_REPO,
                    timeout_seconds=command_timeout_seconds,
                    task_id="post_run_claude_advice_audit",
                )
            )

    failed = [item for item in results if int(item.get("returncode") or 0) != 0]
    status = report_status(due_tasks=due_tasks, run_due=run_due, failed=failed, audit=audit)
    return {
        "schema_version": 1,
        "generated_utc": utc_string(generated),
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": bool(run_due and due_tasks),
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "inputs": {
            "event_velocity_path": str(event_velocity_path),
            "atp_gate_path": str(atp_gate_path),
            "audit_path": str(audit_path),
            "atp_repo": str(atp_repo),
            "previous_cycle_path": str(previous_cycle_path) if previous_cycle_path else None,
            "due_retry_cooldown_seconds": due_retry_cooldown_seconds,
        },
        "summary": summary(tasks=tasks, results=results, run_due=run_due, audit=audit),
        "tasks": [task_to_dict(task) for task in tasks],
        "command_results": results,
        "next_action": next_action(tasks=tasks, run_due=run_due, failed=failed),
        "safety": safety_flags(public_market_data_calls=bool(run_due and due_tasks)),
    }


def build_tasks(
    *,
    event_velocity: Mapping[str, Any],
    atp_gate: Mapping[str, Any],
    atp_repo: Path,
    now: datetime,
) -> list[PlannedTask]:
    tasks: list[PlannedTask] = []
    event_task = event_velocity_task(event_velocity, now=now)
    if event_task:
        tasks.append(event_task)
    atp_task = atp_forward_oos_task(atp_gate, atp_repo=atp_repo, now=now)
    if atp_task:
        tasks.append(atp_task)
    return tasks


def apply_recent_due_backoff(
    tasks: Sequence[PlannedTask],
    *,
    previous_cycle: Mapping[str, Any],
    now: datetime,
    cooldown_seconds: int,
) -> list[PlannedTask]:
    if cooldown_seconds <= 0:
        return list(tasks)
    adjusted: list[PlannedTask] = []
    for task in tasks:
        retry_at = due_retry_time(
            task,
            previous_cycle=previous_cycle,
            now=now,
            cooldown_seconds=cooldown_seconds,
        )
        if task.due and retry_at is not None and retry_at > now:
            retry_text = utc_string(retry_at)
            adjusted.append(
                PlannedTask(
                    task_id=task.task_id,
                    surface_id=task.surface_id,
                    due_utc=retry_text,
                    due=False,
                    reason=(
                        f"{task.reason} A recent successful due run or active backoff is present; "
                        f"retry backoff is active until {retry_text}."
                    ),
                    commands=task.commands,
                    backoff_until_utc=retry_text,
                    fallback_retry_utc=task.fallback_retry_utc,
                )
            )
        else:
            adjusted.append(task)
    return adjusted


def due_retry_time(
    task: PlannedTask,
    *,
    previous_cycle: Mapping[str, Any],
    now: datetime,
    cooldown_seconds: int,
) -> datetime | None:
    if not task.due:
        return None
    retry_candidates: list[datetime] = []
    generated = parse_utc(previous_cycle.get("generated_utc"))
    successful_task_ids = successful_due_task_ids(previous_cycle)
    if (
        generated is not None
        and generated <= now
        and previous_cycle.get("status") == "sports_blocker_clearance_cycle_ran_due_actions"
        and task.task_id in successful_task_ids
    ):
        retry_candidates.append(generated + timedelta(seconds=cooldown_seconds))
    previous_backoff = previous_backoff_until(previous_cycle, task_id=task.task_id)
    if valid_previous_backoff(
        previous_backoff,
        previous_cycle=previous_cycle,
        task=task,
        now=now,
        cooldown_seconds=cooldown_seconds,
    ):
        retry_candidates.append(previous_backoff)
    fallback_retry = parse_utc(task.fallback_retry_utc)
    if retry_candidates and fallback_retry and fallback_retry > now:
        retry_candidates.append(fallback_retry)
    future = [candidate for candidate in retry_candidates if candidate > now]
    return max(future) if future else None


def valid_previous_backoff(
    previous_backoff: datetime | None,
    *,
    previous_cycle: Mapping[str, Any],
    task: PlannedTask,
    now: datetime,
    cooldown_seconds: int,
) -> bool:
    if previous_backoff is None or previous_backoff <= now:
        return False
    fallback_retry = parse_utc(task.fallback_retry_utc)
    if fallback_retry is not None and previous_backoff <= fallback_retry:
        return True
    generated = parse_utc(previous_cycle.get("generated_utc"))
    if generated is None:
        return False
    return previous_backoff <= generated + timedelta(seconds=cooldown_seconds)


def previous_backoff_until(previous_cycle: Mapping[str, Any], *, task_id: str) -> datetime | None:
    tasks = previous_cycle.get("tasks")
    if not isinstance(tasks, Sequence) or isinstance(tasks, (str, bytes)):
        return None
    for item in tasks:
        if not isinstance(item, Mapping) or item.get("task_id") != task_id:
            continue
        parsed = parse_utc(item.get("backoff_until_utc"))
        if parsed is not None:
            return parsed
    return None


def successful_due_task_ids(previous_cycle: Mapping[str, Any]) -> set[str]:
    results = previous_cycle.get("command_results")
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        return set()
    succeeded: set[str] = set()
    failed: set[str] = set()
    for item in results:
        if not isinstance(item, Mapping):
            continue
        task_id = str(item.get("task_id") or "")
        if not task_id or task_id == "post_run_claude_advice_audit":
            continue
        if int_value(item.get("returncode")) == 0:
            succeeded.add(task_id)
        else:
            failed.add(task_id)
    return succeeded - failed


def event_velocity_task(event_velocity: Mapping[str, Any], *, now: datetime) -> PlannedTask | None:
    summary = value_mapping(event_velocity.get("summary"))
    due_surface = value_mapping(summary.get("next_due_surface"))
    probe_surface = value_mapping(summary.get("next_probe_surface"))
    surface = due_surface or probe_surface
    if not surface:
        return None
    due_text = first_text(
        surface.get("next_probe_utc"),
        surface.get("next_due_utc"),
        surface.get("next_expected_expiration_utc"),
    )
    due_at = parse_utc(due_text)
    return PlannedTask(
        task_id="sports_consensus_settlement_probe",
        surface_id=str(surface.get("surface_id") or "sports_consensus_unknown"),
        due_utc=due_text,
        due=bool(due_at and due_at <= now),
        reason=(
            f"Event-velocity surface {surface.get('surface_id')} needs "
            f"OOS deficit {surface.get('oos_deficit')} at {due_text}."
        ),
        commands=(
            (
                "make",
                "kalshi-sports-paper-burn-in-cycle",
                "KALSHI_SPORTS_PAPER_BURN_IN_FETCH=1",
            ),
        ),
        fallback_retry_utc=same_surface_probe_retry_utc(
            due_surface=due_surface,
            probe_surface=probe_surface,
        ),
    )


def same_surface_probe_retry_utc(
    *, due_surface: Mapping[str, Any], probe_surface: Mapping[str, Any]
) -> str | None:
    if not due_surface or not probe_surface:
        return None
    due_id = str(due_surface.get("surface_id") or "")
    probe_id = str(probe_surface.get("surface_id") or "")
    if not due_id or due_id != probe_id:
        return None
    return first_text(probe_surface.get("next_probe_utc"))


def atp_forward_oos_task(
    atp_gate: Mapping[str, Any], *, atp_repo: Path, now: datetime
) -> PlannedTask | None:
    summary = value_mapping(atp_gate.get("summary"))
    resolved = int_value(summary.get("forward_oos_resolved"))
    minimum = int_value(summary.get("forward_oos_min_probe"))
    if minimum <= 0 or resolved >= minimum:
        return None
    due_text = first_text(
        summary.get("next_expected_expiration_utc"),
        summary.get("next_public_label_probe_utc"),
    )
    due_at = parse_utc(due_text)
    return PlannedTask(
        task_id="atp_forward_oos_probe",
        surface_id="atp_forward_oos",
        due_utc=due_text,
        due=bool(due_at and due_at <= now),
        reason=(
            f"ATP forward-OOS has {resolved}/{minimum} resolved candidates; "
            f"next exact settlement/probe clock is {due_text}."
        ),
        commands=(
            ("make", "-C", str(atp_repo), "kalshi-forward-oos-capture-prices"),
            ("make", "-C", str(atp_repo), "kalshi-forward-oos-capture-liquidity"),
            ("make", "-C", str(atp_repo), "kalshi-forward-oos-funnel-audit"),
            ("make", "-C", str(atp_repo), "kalshi-forward-oos-report"),
            ("make", "-C", str(atp_repo), "kalshi-method-satisfaction"),
            ("make", "-C", str(atp_repo), "kalshi-bettable-line-gate"),
            (
                "make",
                "kalshi-atp-proxy-observation-loop",
                "KALSHI_ATP_PROXY_OBSERVATION_PROBE_OBSERVED=1",
                "KALSHI_ATP_PROXY_OBSERVATION_CAPTURE_SETTLED=1",
            ),
            ("make", "kalshi-atp-proxy-evidence-gate"),
            ("make", "kalshi-sports-event-velocity-eta"),
        ),
        fallback_retry_utc=None,
    )


def run_task(task: PlannedTask, *, timeout_seconds: int) -> list[dict[str, Any]]:
    return [
        run_command(
            command,
            cwd=CONTROL_REPO,
            timeout_seconds=timeout_seconds,
            task_id=task.task_id,
        )
        for command in task.commands
    ]


def run_command(
    command: Sequence[str], *, cwd: Path, timeout_seconds: int, task_id: str
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
        return {
            "task_id": task_id,
            "command": list(command),
            "returncode": completed.returncode,
            "stdout_tail": tail(completed.stdout),
            "stderr_tail": tail(completed.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "task_id": task_id,
            "command": list(command),
            "returncode": 124,
            "stdout_tail": tail(exc.stdout or ""),
            "stderr_tail": tail(exc.stderr or "command timed out"),
        }


def report_status(
    *,
    due_tasks: Sequence[PlannedTask],
    run_due: bool,
    failed: Sequence[Mapping[str, Any]],
    audit: Mapping[str, Any],
) -> str:
    if failed:
        return "sports_blocker_clearance_cycle_failed_due_action"
    if due_tasks and run_due:
        return "sports_blocker_clearance_cycle_ran_due_actions"
    if due_tasks:
        return "sports_blocker_clearance_cycle_due_actions_available"
    if not open_audit_ids(audit):
        return "sports_blocker_clearance_cycle_no_open_clock_blockers"
    return "sports_blocker_clearance_cycle_waiting_for_next_clock"


def summary(
    *,
    tasks: Sequence[PlannedTask],
    results: Sequence[Mapping[str, Any]],
    run_due: bool,
    audit: Mapping[str, Any],
) -> dict[str, Any]:
    due_tasks = [task for task in tasks if task.due]
    waiting_tasks = [task for task in tasks if not task.due]
    failed = [item for item in results if int(item.get("returncode") or 0) != 0]
    return {
        "run_due": run_due,
        "task_count": len(tasks),
        "due_task_count": len(due_tasks),
        "waiting_task_count": len(waiting_tasks),
        "next_clock_utc": next_clock(tasks),
        "open_requirement_ids": open_audit_ids(audit),
        "implementation_satisfied_count": implementation_satisfied_count(audit),
        "implementation_open_requirement_ids": implementation_open_ids(audit),
        "commands_executed_count": len(results),
        "failed_command_count": len(failed),
    }


def next_clock(tasks: Sequence[PlannedTask]) -> str | None:
    future = sorted(
        task.due_utc
        for task in tasks
        if task.due_utc and not task.due and parse_utc(task.due_utc)
    )
    return future[0] if future else None


def next_action(
    *,
    tasks: Sequence[PlannedTask],
    run_due: bool,
    failed: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    if failed:
        return {
            "name": "repair_failed_due_refresh",
            "why": f"{len(failed)} due refresh command(s) failed.",
            "stop_condition": "Repair the failing public-data refresh before re-running.",
        }
    due_tasks = [task for task in tasks if task.due]
    if due_tasks and not run_due:
        return {
            "name": "run_due_sports_blocker_clearance",
            "why": ", ".join(task.task_id for task in due_tasks),
            "stop_condition": "Run with --run-due or KALSHI_SPORTS_BLOCKER_CLEARANCE_RUN_DUE=1.",
        }
    if due_tasks:
        return {
            "name": "review_refreshed_claude_advice_audit",
            "why": "Due public-data refresh commands were run.",
            "stop_condition": "Inspect latest Claude advice audit for remaining statistical or clock-bound items.",
        }
    return {
        "name": "wait_for_next_sports_clock",
        "why": f"Next clock: {next_clock(tasks)}.",
        "stop_condition": "Do not lower thresholds or infer labels before the exact settlement/probe clock.",
    }


def task_to_dict(task: PlannedTask) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "surface_id": task.surface_id,
        "due_utc": task.due_utc,
        "due": task.due,
        "reason": task.reason,
        "commands": [list(command) for command in task.commands],
        "backoff_until_utc": task.backoff_until_utc,
        "fallback_retry_utc": task.fallback_retry_utc,
    }


def write_outputs(report: Mapping[str, Any], *, out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-sports-blocker-clearance-cycle.json"
    md_path = out_dir / "kalshi-sports-blocker-clearance-cycle.md"
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    paths = {"json_path": str(json_path), "markdown_path": str(md_path)}
    if path_is_within(out_dir, MACRO_DIR):
        latest_json = MACRO_DIR / "latest-kalshi-sports-blocker-clearance-cycle.json"
        latest_md = MACRO_DIR / "latest-kalshi-sports-blocker-clearance-cycle.md"
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        paths.update({"latest_json_path": str(latest_json), "latest_markdown_path": str(latest_md)})
    return paths


def render_markdown(report: Mapping[str, Any]) -> str:
    summary_map = value_mapping(report.get("summary"))
    lines = [
        "# Kalshi Sports Blocker Clearance Cycle",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Due tasks: `{summary_map.get('due_task_count')}`",
        f"- Waiting tasks: `{summary_map.get('waiting_task_count')}`",
        f"- Next clock: `{summary_map.get('next_clock_utc')}`",
        f"- Implementation satisfied: `{summary_map.get('implementation_satisfied_count')}`",
        f"- Implementation open ids: `{summary_map.get('implementation_open_requirement_ids')}`",
        f"- Commands executed: `{summary_map.get('commands_executed_count')}`",
        "",
        "| Task | Surface | Due | Clock | Reason |",
        "| --- | --- | --- | --- | --- |",
    ]
    for task in report.get("tasks", []):
        if isinstance(task, Mapping):
            lines.append(
                f"| `{task.get('task_id')}` | `{task.get('surface_id')}` | "
                f"`{task.get('due')}` | `{task.get('due_utc')}` | {task.get('reason')} |"
            )
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            f"- Name: `{value_mapping(report.get('next_action')).get('name')}`",
            f"- Why: {value_mapping(report.get('next_action')).get('why')}",
            f"- Stop condition: {value_mapping(report.get('next_action')).get('stop_condition')}",
            "",
            "> Research-only public-data refresh control. No probabilities, EV, sizing, account paths, or orders.",
            "",
        ]
    )
    return "\n".join(lines)


def value_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def first_text(*values: Any) -> str | None:
    for value in values:
        if value not in {None, ""}:
            return str(value)
    return None


def int_value(value: Any) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def tail(text: str, *, limit: int = 4000) -> str:
    return text[-limit:] if len(text) > limit else text


def open_audit_ids(audit: Mapping[str, Any]) -> list[str]:
    summary_map = value_mapping(audit.get("summary"))
    ids = summary_map.get("open_requirement_ids")
    return [str(item) for item in ids] if isinstance(ids, list) else []


def implementation_open_ids(audit: Mapping[str, Any]) -> list[str]:
    summary_map = value_mapping(audit.get("summary"))
    ids = summary_map.get("implementation_open_requirement_ids")
    return [str(item) for item in ids] if isinstance(ids, list) else []


def implementation_satisfied_count(audit: Mapping[str, Any]) -> int:
    summary_map = value_mapping(audit.get("summary"))
    return int_value(summary_map.get("implementation_satisfied_count"))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-velocity-path", type=Path, default=DEFAULT_EVENT_VELOCITY_PATH)
    parser.add_argument("--atp-gate-path", type=Path, default=DEFAULT_ATP_GATE_PATH)
    parser.add_argument("--audit-path", type=Path, default=DEFAULT_AUDIT_PATH)
    parser.add_argument("--atp-repo", type=Path, default=DEFAULT_ATP_REPO)
    parser.add_argument("--previous-cycle-path", type=Path, default=DEFAULT_PREVIOUS_CYCLE_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--run-due", action="store_true")
    parser.add_argument("--command-timeout-seconds", type=int, default=900)
    parser.add_argument(
        "--due-retry-cooldown-seconds",
        type=int,
        default=DEFAULT_DUE_RETRY_COOLDOWN_SECONDS,
    )
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        event_velocity_path=args.event_velocity_path,
        atp_gate_path=args.atp_gate_path,
        audit_path=args.audit_path,
        atp_repo=args.atp_repo,
        previous_cycle_path=args.previous_cycle_path,
        run_due=args.run_due,
        command_timeout_seconds=args.command_timeout_seconds,
        due_retry_cooldown_seconds=args.due_retry_cooldown_seconds,
    )
    if args.write:
        paths = write_outputs(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] != "sports_blocker_clearance_cycle_failed_due_action" else 1


if __name__ == "__main__":
    raise SystemExit(main())
