from pathlib import Path

import pytest

from scripts.kalshi_always_on_collector import (
    MACRO_DIR,
    CollectorTarget,
    CommandResult,
    cadence_decision,
    execute_collector_cycle,
    selected_targets,
    write_outputs,
)


def safe_artifact(status: str, **summary: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": status,
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "database_writes": False,
        "summary": summary,
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "market_execution": False,
            "account_or_order_paths": False,
        },
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_cadence_tightens_when_due_rows_exist() -> None:
    cadence = cadence_decision(
        [{"target_id": "sports", "due_count": 2, "next_probe_utc": None}],
        generated_utc="2026-07-04T18:00:00Z",
        base_interval_seconds=300,
        near_interval_seconds=60,
        due_interval_seconds=30,
        near_close_window_seconds=1800,
    )

    assert cadence["interval_seconds"] == 30
    assert cadence["reason"] == "due_settlement_rows_present"
    assert cadence["due_targets"] == ["sports"]


def test_cadence_tightens_near_next_probe() -> None:
    cadence = cadence_decision(
        [
            {
                "target_id": "sports",
                "due_count": 0,
                "next_probe_utc": "2026-07-04T18:10:00Z",
            }
        ],
        generated_utc="2026-07-04T18:00:00Z",
        base_interval_seconds=300,
        near_interval_seconds=45,
        due_interval_seconds=30,
        near_close_window_seconds=1800,
    )

    assert cadence["interval_seconds"] == 45
    assert cadence["reason"] == "near_close_or_probe_window"
    assert cadence["next_probe_target_id"] == "sports"


def test_execute_collector_cycle_runs_targets_and_preserves_safety(tmp_path: Path) -> None:
    artifact_path = tmp_path / "sports.json"
    target = CollectorTarget(
        target_id="sports",
        make_target="kalshi-sports-paper-burn-in-cycle",
        artifact_path=artifact_path,
        env={"KALSHI_SPORTS_PAPER_BURN_IN_FETCH": "1"},
        cadence_group="fast_sports_settlement",
        purpose="test",
        poll_interval_seconds=None,
    )

    def fake_runner(received: CollectorTarget) -> CommandResult:
        assert received == target
        write_json(
            artifact_path,
            safe_artifact(
                "sports_paper_burn_in_waiting_for_next_close",
                due_after_fetch_count=0,
                total_exact_label_count=327,
                next_paper_close_time_utc="2026-07-04T18:10:00Z",
            ),
        )
        return CommandResult(returncode=0, stdout="ok", stderr="", duration_seconds=1.25)

    report = execute_collector_cycle(
        targets=[target],
        generated_utc="2026-07-04T18:00:00Z",
        runner=fake_runner,
        base_interval_seconds=300,
        near_interval_seconds=60,
        due_interval_seconds=30,
        near_close_window_seconds=1800,
    )

    assert report["status"] == "kalshi_always_on_collector_ready"
    assert report["summary"]["safe_artifact_count"] == 1
    assert report["summary"]["total_label_count"] == 327
    assert report["summary"]["total_capture_count"] == 0
    assert report["cadence"]["reason"] == "near_close_or_probe_window"
    assert report["targets"][0]["status"] == "pass"
    assert report["targets"][0]["artifact_safe"] is True
    assert report["execution_enabled"] is False
    assert report["safety"]["market_execution"] is False


def test_execute_collector_cycle_schedules_from_completion_time(tmp_path: Path) -> None:
    artifact_path = tmp_path / "crypto.json"
    target = CollectorTarget(
        target_id="crypto",
        make_target="kalshi-crypto-proxy-observation-watch-once",
        artifact_path=artifact_path,
        env={"KALSHI_CRYPTO_PROXY_OBSERVATION_PROBE_OBSERVED": "1"},
        cadence_group="fast_crypto_settlement",
        purpose="test",
        poll_interval_seconds=None,
    )

    def fake_runner(received: CollectorTarget) -> CommandResult:
        assert received == target
        write_json(
            artifact_path,
            safe_artifact(
                "crypto_proxy_observation_loop_label_rows_ready",
                due_after_fetch_count=10,
                label_row_count=100,
                next_public_label_probe_utc="2026-07-04T18:20:00Z",
            ),
        )
        return CommandResult(returncode=0, stdout="ok", stderr="", duration_seconds=420)

    report = execute_collector_cycle(
        targets=[target],
        generated_utc="2026-07-04T18:00:00Z",
        completed_utc="2026-07-04T18:07:00Z",
        runner=fake_runner,
        base_interval_seconds=300,
        near_interval_seconds=60,
        due_interval_seconds=60,
        near_close_window_seconds=1800,
    )

    assert report["generated_utc"] == "2026-07-04T18:00:00Z"
    assert report["completed_utc"] == "2026-07-04T18:07:00Z"
    assert report["cadence"]["reason"] == "due_settlement_rows_present"
    assert report["cadence"]["next_run_utc"] == "2026-07-04T18:08:00Z"


def test_selected_targets_rejects_unknown_target() -> None:
    with pytest.raises(ValueError, match="unknown collector target"):
        selected_targets(["sports", "unknown"])


def test_selected_targets_include_sports_consensus_collector() -> None:
    targets = selected_targets(["line_moves", "ticks", "sports_consensus", "sports", "crypto"])

    assert [target.target_id for target in targets] == [
        "line_moves",
        "ticks",
        "sports_consensus",
        "sports",
        "crypto",
    ]
    line_moves = targets[0]
    assert line_moves.make_target == "kalshi-sports-line-move-delta-logger"
    assert line_moves.poll_interval_seconds == 60
    ticks = targets[1]
    assert ticks.make_target == "kalshi-tick-recorder"
    assert ticks.poll_interval_seconds == 60
    consensus = targets[2]
    assert consensus.make_target == "kalshi-sports-consensus-observation-watch-once"
    assert consensus.artifact_path.name == "latest-kalshi-sports-consensus-observation-loop.json"
    assert consensus.env["KALSHI_SPORTS_CONSENSUS_PROBE_OBSERVED"] == "1"


def test_default_collector_targets_run_full_sports_burn_in() -> None:
    from scripts.kalshi_always_on_collector import parse_args

    args = parse_args([])
    targets = selected_targets(args.targets.split(","))

    assert [target.target_id for target in targets] == [
        "line_moves",
        "ticks",
        "sports_consensus",
        "sports",
        "crypto",
    ]
    sports = targets[3]
    assert sports.make_target == "kalshi-sports-paper-burn-in-cycle"
    assert sports.env["KALSHI_SPORTS_PAPER_BURN_IN_FETCH"] == "1"


def test_capture_targets_force_high_frequency_cadence(tmp_path: Path) -> None:
    artifact_path = tmp_path / "ticks.json"
    target = CollectorTarget(
        target_id="ticks",
        make_target="kalshi-tick-recorder",
        artifact_path=artifact_path,
        env={},
        cadence_group="high_frequency_kalshi_sports_ticks",
        purpose="test",
        poll_interval_seconds=60,
    )

    def fake_runner(received: CollectorTarget) -> CommandResult:
        assert received == target
        write_json(
            artifact_path,
            safe_artifact(
                "kalshi_tick_recorder_ready",
                recorded_line_count=42,
                gap_count=1,
            ),
        )
        return CommandResult(returncode=0, stdout="ok", stderr="", duration_seconds=30.0)

    report = execute_collector_cycle(
        targets=[target],
        generated_utc="2026-07-07T00:00:00Z",
        runner=fake_runner,
        base_interval_seconds=300,
        near_interval_seconds=60,
        due_interval_seconds=60,
        near_close_window_seconds=1800,
    )

    assert report["cadence"]["reason"] == "high_frequency_capture_interval"
    assert report["cadence"]["interval_seconds"] == 60
    assert report["summary"]["total_capture_count"] == 42
    assert report["summary"]["total_gap_count"] == 1
    assert report["targets"][0]["capture_count"] == 42
    assert report["targets"][0]["gap_count"] == 1


def test_makefile_exposes_always_on_collector_targets() -> None:
    text = Path("Makefile").read_text(encoding="utf-8")

    assert "kalshi-always-on-collector-once:" in text
    assert "kalshi-always-on-collector:" in text
    assert (
        "KALSHI_ALWAYS_ON_COLLECTOR_TARGETS ?= "
        "line_moves,ticks,sports_consensus,sports,crypto"
    ) in text
    assert "kalshi-sports-line-move-delta-logger:" in text
    assert "kalshi-tick-recorder:" in text
    assert "kalshi-sports-consensus-observation-watch-once:" in text
    assert "scripts/kalshi_always_on_collector.py" in text


def test_temp_output_does_not_mutate_macro_latest(tmp_path: Path) -> None:
    latest = MACRO_DIR / "latest-kalshi-always-on-collector.json"
    before = latest.read_text(encoding="utf-8") if latest.exists() else None
    report = safe_artifact("kalshi_always_on_collector_planned", target_count=0)
    report["targets"] = []
    report["cadence"] = {"interval_seconds": 300}

    write_outputs(report, out_dir=tmp_path / "collector")

    after = latest.read_text(encoding="utf-8") if latest.exists() else None
    assert after == before
