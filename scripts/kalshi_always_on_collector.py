#!/usr/bin/env python3
"""Run a research-only always-on collector for Kalshi labels and orderbooks."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[1]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from predmarket.shared_helpers import (  # noqa: E402
    iso_from_timestamp,
    read_json_or_empty,
    safe_stamp,
    safety_flags,
    sha256_or_none,
    timestamp,
    utc_now,
)

MACRO_DIR = CONTROL_REPO / "docs" / "codex" / "macro"
DEFAULT_OUT_DIR = MACRO_DIR / "kalshi-always-on-collector-latest"
DEFAULT_BASE_INTERVAL_SECONDS = 300
DEFAULT_NEAR_INTERVAL_SECONDS = 60
DEFAULT_DUE_INTERVAL_SECONDS = 60
DEFAULT_NEAR_CLOSE_WINDOW_SECONDS = 1800
DEFAULT_COMMAND_TIMEOUT_SECONDS = 600

CSV_FIELDS = [
    "target_id",
    "status",
    "returncode",
    "artifact_status",
    "duration_seconds",
    "next_probe_utc",
    "due_count",
    "label_count",
]


@dataclass(frozen=True)
class CollectorTarget:
    target_id: str
    make_target: str
    artifact_path: Path
    env: Mapping[str, str]
    cadence_group: str
    purpose: str


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0


DEFAULT_TARGETS: dict[str, CollectorTarget] = {
    "sports_consensus": CollectorTarget(
        target_id="sports_consensus",
        make_target="kalshi-sports-consensus-observation-watch-once",
        artifact_path=MACRO_DIR / "latest-kalshi-sports-consensus-observation-loop.json",
        env={"KALSHI_SPORTS_CONSENSUS_PROBE_OBSERVED": "1"},
        cadence_group="fast_sports_consensus_settlement",
        purpose=(
            "Refresh timestamp-matched sharp no-vig consensus observations, probe exact "
            "public Kalshi settlements, and rerun sports consensus falsification."
        ),
    ),
    "sports": CollectorTarget(
        target_id="sports",
        make_target="kalshi-sports-paper-burn-in-cycle",
        artifact_path=MACRO_DIR / "latest-kalshi-sports-paper-burn-in-cycle.json",
        env={"KALSHI_SPORTS_PAPER_BURN_IN_FETCH": "1"},
        cadence_group="fast_sports_settlement",
        purpose="Refresh sports orderbook evidence, exact settlement labels, paper settlement, and retirement state.",
    ),
    "crypto": CollectorTarget(
        target_id="crypto",
        make_target="kalshi-crypto-proxy-observation-watch-once",
        artifact_path=MACRO_DIR / "latest-kalshi-crypto-proxy-observation-loop.json",
        env={
            "KALSHI_CRYPTO_PROXY_OBSERVATION_CAPTURE_SETTLED": "1",
            "KALSHI_CRYPTO_PROXY_OBSERVATION_PROBE_OBSERVED": "1",
        },
        cadence_group="fast_crypto_settlement",
        purpose="Refresh crypto proxy observations and exact public settlement labels.",
    ),
}


def selected_targets(target_names: Sequence[str]) -> list[CollectorTarget]:
    targets: list[CollectorTarget] = []
    for raw in target_names:
        name = raw.strip()
        if not name:
            continue
        if name not in DEFAULT_TARGETS:
            raise ValueError(f"unknown collector target: {name}")
        targets.append(DEFAULT_TARGETS[name])
    return targets


def run_make_target(
    target: CollectorTarget,
    *,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> CommandResult:
    env = os.environ.copy()
    env.update(target.env)
    started = time.monotonic()
    completed = subprocess.run(
        ["make", "--no-print-directory", target.make_target],
        cwd=CONTROL_REPO,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_seconds=time.monotonic() - started,
    )


def execute_collector_cycle(
    *,
    targets: Sequence[CollectorTarget],
    generated_utc: str | None = None,
    completed_utc: str | None = None,
    runner: Callable[[CollectorTarget], CommandResult] | None = None,
    dry_run: bool = False,
    base_interval_seconds: int = DEFAULT_BASE_INTERVAL_SECONDS,
    near_interval_seconds: int = DEFAULT_NEAR_INTERVAL_SECONDS,
    due_interval_seconds: int = DEFAULT_DUE_INTERVAL_SECONDS,
    near_close_window_seconds: int = DEFAULT_NEAR_CLOSE_WINDOW_SECONDS,
) -> dict[str, Any]:
    generated = generated_utc or utc_now()
    run = runner or run_make_target
    target_results: list[dict[str, Any]] = []
    for target in targets:
        if dry_run:
            command_result = CommandResult(returncode=0, stdout="", stderr="", duration_seconds=0.0)
        else:
            command_result = run(target)
        artifact = read_json_or_empty(target.artifact_path)
        target_results.append(
            target_result_row(
                target,
                command_result=command_result,
                artifact=artifact,
                dry_run=dry_run,
            )
        )
    completed = completed_utc or (generated if generated_utc is not None else utc_now())
    cadence = cadence_decision(
        target_results,
        generated_utc=completed,
        base_interval_seconds=base_interval_seconds,
        near_interval_seconds=near_interval_seconds,
        due_interval_seconds=due_interval_seconds,
        near_close_window_seconds=near_close_window_seconds,
    )
    summary = build_summary(target_results, cadence=cadence, dry_run=dry_run)
    status = report_status(target_results=target_results, dry_run=dry_run)
    return {
        "schema_version": 1,
        "generated_utc": generated,
        "completed_utc": completed,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "public_market_data_calls": not dry_run and bool(target_results),
        "authenticated_api_calls": False,
        "provider_api_calls": False,
        "paid_calls": False,
        "database_writes": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "staking_or_sizing_guidance": False,
        "method": {
            "purpose": "Continuously feed falsification by running existing safe collectors on a mechanical cadence.",
            "cadence_rule": "Run tight when settlements are due or close windows are near; cadence is computed from cycle completion, not start.",
            "execution_boundary": "This daemon only invokes research collectors. It never reads account state or submits orders.",
            "label_boundary": "Only exact public Kalshi settlement payloads may become labels.",
        },
        "summary": summary,
        "cadence": cadence,
        "targets": target_results,
        "next_action": next_action(status, cadence),
        "safety": safety_flags(public_market_data_calls=not dry_run and bool(target_results)),
    }


def target_result_row(
    target: CollectorTarget,
    *,
    command_result: CommandResult,
    artifact: Mapping[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    summary = artifact.get("summary") if isinstance(artifact.get("summary"), Mapping) else {}
    due_count = first_int(
        summary,
        [
            "due_after_fetch_count",
            "due_unresolved_paper_usable_count",
            "due_distinct_contract_count",
            "due_observation_row_count",
        ],
    )
    label_count = first_int(
        summary,
        [
            "total_exact_label_count",
            "label_row_count",
            "settled_label_count",
            "total_independent_label_count",
        ],
    )
    next_probe = first_time(
        summary,
        [
            "next_paper_close_time_utc",
            "next_public_label_probe_utc",
            "next_expected_expiration_utc",
            "oldest_due_expected_expiration_utc",
        ],
    )
    return {
        "target_id": target.target_id,
        "make_target": target.make_target,
        "cadence_group": target.cadence_group,
        "purpose": target.purpose,
        "status": "planned" if dry_run else ("pass" if command_result.returncode == 0 else "fail"),
        "returncode": command_result.returncode,
        "duration_seconds": round(command_result.duration_seconds, 3),
        "artifact_path": str(target.artifact_path),
        "artifact_sha256": sha256_or_none(target.artifact_path),
        "artifact_status": artifact.get("status"),
        "artifact_safe": artifact_is_safe(artifact),
        "due_count": due_count,
        "label_count": label_count,
        "next_probe_utc": next_probe,
        "stdout_tail": tail(command_result.stdout),
        "stderr_tail": tail(command_result.stderr),
        "env_overrides": dict(target.env),
    }


def artifact_is_safe(artifact: Mapping[str, Any]) -> bool:
    if not artifact:
        return False
    return (
        artifact.get("research_only") is True
        and artifact.get("execution_enabled") is False
        and artifact.get("market_execution") is False
        and artifact.get("account_or_order_paths") is False
    )


def cadence_decision(
    target_results: Sequence[Mapping[str, Any]],
    *,
    generated_utc: str,
    base_interval_seconds: int,
    near_interval_seconds: int,
    due_interval_seconds: int,
    near_close_window_seconds: int,
) -> dict[str, Any]:
    generated_ts = timestamp(generated_utc)
    due_targets = [
        str(row.get("target_id")) for row in target_results if int_value(row.get("due_count")) > 0
    ]
    future_times: list[tuple[float, str, str]] = []
    for row in target_results:
        ts = timestamp(row.get("next_probe_utc"))
        if ts is None:
            continue
        if generated_ts is not None and ts < generated_ts:
            continue
        future_times.append((ts, str(row.get("target_id")), str(row.get("next_probe_utc"))))
    future_times.sort()
    next_due = future_times[0] if future_times else None
    seconds_to_next = (
        round(next_due[0] - generated_ts, 3)
        if next_due is not None and generated_ts is not None
        else None
    )
    if due_targets:
        interval = due_interval_seconds
        reason = "due_settlement_rows_present"
    elif seconds_to_next is not None and seconds_to_next <= near_close_window_seconds:
        interval = near_interval_seconds
        reason = "near_close_or_probe_window"
    else:
        interval = base_interval_seconds
        reason = "base_collection_interval"
    next_run_ts = generated_ts + max(1, interval) if generated_ts is not None else None
    return {
        "interval_seconds": max(1, int(interval)),
        "reason": reason,
        "due_targets": due_targets,
        "next_probe_utc": next_due[2] if next_due else None,
        "next_probe_target_id": next_due[1] if next_due else None,
        "seconds_to_next_probe": seconds_to_next,
        "next_run_utc": iso_from_timestamp(next_run_ts),
        "base_interval_seconds": base_interval_seconds,
        "near_interval_seconds": near_interval_seconds,
        "due_interval_seconds": due_interval_seconds,
        "near_close_window_seconds": near_close_window_seconds,
    }


def build_summary(
    target_results: Sequence[Mapping[str, Any]],
    *,
    cadence: Mapping[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "target_count": len(target_results),
        "successful_target_count": sum(
            1 for row in target_results if row.get("status") in {"pass", "planned"}
        ),
        "failed_target_count": sum(1 for row in target_results if row.get("status") == "fail"),
        "safe_artifact_count": sum(1 for row in target_results if row.get("artifact_safe") is True),
        "total_due_count": sum(int_value(row.get("due_count")) for row in target_results),
        "total_label_count": sum(int_value(row.get("label_count")) for row in target_results),
        "targets": [row.get("target_id") for row in target_results],
        "dry_run": dry_run,
        "cadence_reason": cadence.get("reason"),
        "next_run_utc": cadence.get("next_run_utc"),
        "interval_seconds": cadence.get("interval_seconds"),
    }


def report_status(
    *,
    target_results: Sequence[Mapping[str, Any]],
    dry_run: bool,
) -> str:
    if dry_run:
        return "kalshi_always_on_collector_planned"
    if not target_results:
        return "kalshi_always_on_collector_blocked_no_targets"
    failures = sum(1 for row in target_results if row.get("status") == "fail")
    if failures == len(target_results):
        return "kalshi_always_on_collector_failed_all_targets"
    if failures:
        return "kalshi_always_on_collector_partial_target_failure"
    if any(row.get("artifact_safe") is not True for row in target_results):
        return "kalshi_always_on_collector_warn_unsafe_or_missing_artifact"
    return "kalshi_always_on_collector_ready"


def next_action(status: str, cadence: Mapping[str, Any]) -> dict[str, Any]:
    if status.endswith("failed_all_targets") or "partial_target_failure" in status:
        return {
            "name": "collector_failure_triage",
            "why": "At least one collector target failed. Inspect stderr tail before continuing.",
            "stop_condition": "Stop before treating stale artifacts as fresh labels.",
        }
    return {
        "name": "collector_sleep_then_repeat",
        "why": f"Next cadence reason: {cadence.get('reason')}.",
        "next_run_utc": cadence.get("next_run_utc"),
        "interval_seconds": cadence.get("interval_seconds"),
        "stop_condition": "Stop before account/order paths, live execution, threshold lowering, or non-Kalshi labels.",
    }


def run_collector(
    *,
    targets: Sequence[CollectorTarget],
    out_dir: Path,
    once: bool,
    write: bool,
    max_cycles: int,
    dry_run: bool,
    base_interval_seconds: int,
    near_interval_seconds: int,
    due_interval_seconds: int,
    near_close_window_seconds: int,
) -> dict[str, Any]:
    cycle_index = 0
    last_report: dict[str, Any] = {}
    while True:
        last_report = execute_collector_cycle(
            targets=targets,
            dry_run=dry_run,
            base_interval_seconds=base_interval_seconds,
            near_interval_seconds=near_interval_seconds,
            due_interval_seconds=due_interval_seconds,
            near_close_window_seconds=near_close_window_seconds,
        )
        last_report["cycle_index"] = cycle_index
        if write:
            write_outputs(last_report, out_dir=out_dir)
        cycle_index += 1
        if once or (max_cycles > 0 and cycle_index >= max_cycles):
            return last_report
        sleep_seconds = int(
            last_report.get("cadence", {}).get("interval_seconds") or base_interval_seconds
        )
        time.sleep(max(1, sleep_seconds))


def first_int(summary: Mapping[str, Any], keys: Sequence[str]) -> int:
    for key in keys:
        if key in summary:
            return int_value(summary.get(key))
    return 0


def first_time(summary: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = summary.get(key)
        parsed = timestamp(value)
        if parsed is not None:
            return iso_from_timestamp(parsed)
    return None


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def tail(text: str, *, limit: int = 4000) -> str:
    return text[-limit:] if len(text) > limit else text


def write_outputs(report: Mapping[str, Any], *, out_dir: Path = DEFAULT_OUT_DIR) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kalshi-always-on-collector.json"
    md_path = out_dir / "kalshi-always-on-collector.md"
    csv_path = out_dir / "kalshi-always-on-collector.csv"
    timer_path = out_dir / "kalshi-always-on-collector.timer.example"
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_csv(report.get("targets", []), csv_path)
    timer_path.write_text(render_timer_example(report), encoding="utf-8")

    latest_json = MACRO_DIR / "latest-kalshi-always-on-collector.json"
    latest_md = MACRO_DIR / "latest-kalshi-always-on-collector.md"
    latest_csv = MACRO_DIR / "latest-kalshi-always-on-collector.csv"
    latest_timer = MACRO_DIR / "latest-kalshi-always-on-collector.timer.example"
    if _path_is_within(out_dir, MACRO_DIR):
        latest_json.write_text(text, encoding="utf-8")
        latest_md.write_text(render_markdown(report), encoding="utf-8")
        write_csv(report.get("targets", []), latest_csv)
        latest_timer.write_text(render_timer_example(report), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
        "timer_template_path": str(timer_path),
        "latest_json_path": str(latest_json),
        "latest_markdown_path": str(latest_md),
        "latest_csv_path": str(latest_csv),
        "latest_timer_template_path": str(latest_timer),
    }


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    cadence = report.get("cadence") if isinstance(report.get("cadence"), Mapping) else {}
    lines = [
        "# Kalshi Always-On Collector",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Targets: `{summary.get('targets')}`",
        f"- Safe artifacts: `{summary.get('safe_artifact_count')}/{summary.get('target_count')}`",
        f"- Total due count: `{summary.get('total_due_count')}`",
        f"- Total label count: `{summary.get('total_label_count')}`",
        f"- Cadence: `{cadence.get('interval_seconds')}` seconds (`{cadence.get('reason')}`)",
        f"- Next run: `{cadence.get('next_run_utc')}`",
        "",
        "| Target | Status | Artifact | Due | Labels | Next Probe |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    rows = report.get("targets") if isinstance(report.get("targets"), list) else []
    for row in rows:
        if isinstance(row, Mapping):
            lines.append(
                f"| `{row.get('target_id')}` | `{row.get('status')}` | "
                f"`{row.get('artifact_status')}` | `{row.get('due_count')}` | "
                f"`{row.get('label_count')}` | `{row.get('next_probe_utc')}` |"
            )
    lines.extend(
        [
            "",
            "Research-only collector. No account, order, approval queue, or live execution path.",
            "",
        ]
    )
    return "\n".join(lines)


def render_timer_example(report: Mapping[str, Any]) -> str:
    stamp = safe_stamp(str(report.get("generated_utc") or "latest"))
    return "\n".join(
        [
            "# Example systemd user service/timer for the Kalshi always-on collector.",
            "# Copy into ~/.config/systemd/user/ only after reviewing local paths.",
            "",
            "[Unit]",
            f"Description=Kalshi always-on collector ({stamp})",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={CONTROL_REPO}",
            "ExecStart=/usr/bin/env make kalshi-always-on-collector",
            "Restart=always",
            "RestartSec=15",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )


def write_csv(rows: Any, path: Path) -> None:
    target_rows = rows if isinstance(rows, list) else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in target_rows:
            if isinstance(row, Mapping):
                writer.writerow(dict(row))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", default="sports,crypto")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--base-interval-seconds", type=int, default=DEFAULT_BASE_INTERVAL_SECONDS)
    parser.add_argument("--near-interval-seconds", type=int, default=DEFAULT_NEAR_INTERVAL_SECONDS)
    parser.add_argument("--due-interval-seconds", type=int, default=DEFAULT_DUE_INTERVAL_SECONDS)
    parser.add_argument(
        "--near-close-window-seconds", type=int, default=DEFAULT_NEAR_CLOSE_WINDOW_SECONDS
    )
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    targets = selected_targets(args.targets.split(","))
    report = run_collector(
        targets=targets,
        out_dir=args.out_dir,
        once=args.once,
        write=args.write,
        max_cycles=args.max_cycles,
        dry_run=args.dry_run,
        base_interval_seconds=args.base_interval_seconds,
        near_interval_seconds=args.near_interval_seconds,
        due_interval_seconds=args.due_interval_seconds,
        near_close_window_seconds=args.near_close_window_seconds,
    )
    if args.write:
        paths = write_outputs(report, out_dir=args.out_dir)
        print(json.dumps({"status": report["status"], **paths}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
