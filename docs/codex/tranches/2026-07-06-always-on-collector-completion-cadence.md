# Tranche Note: Always-On Collector Completion-Time Cadence

## North-Star Alignment

The sports evidence system needs unattended collection to keep feeding exact
Kalshi settlement labels and future OOS samples. A collector that schedules its
next run from cycle start can emit a stale next-run time whenever public-data
refreshes take longer than the cadence interval. That creates operator
confusion and weakens the path to a self-improving evidence loop.

## What Changed

- `scripts/kalshi_always_on_collector.py` now records `completed_utc`.
- Cadence is computed from cycle completion time, not `generated_utc`.
- `generated_utc` remains the provenance/start timestamp.
- The method text now states the completion-time cadence rule.
- Added a regression test proving a long-running cycle schedules
  `next_run_utc` after `completed_utc`.

## Real Run Evidence

After the fix, a real collector cycle completed:

- Status: `kalshi_always_on_collector_ready`
- `generated_utc`: `2026-07-06T19:36:22Z`
- `completed_utc`: `2026-07-06T19:41:16Z`
- `next_run_utc`: `2026-07-06T19:42:16Z`
- `next_run_utc > completed_utc`: true
- Targets: `sports`, `crypto`
- Successful targets: `2/2`
- Safe artifacts: `2/2`

Sports remains correctly clock-bound: next consensus rule-bucket settlement
probe is `2026-07-06T21:10:00Z`. ATP remains `8/10` forward-OOS with next exact
clock `2026-07-07T06:00:00Z`.

## Verification

- `pytest tests/test_kalshi_always_on_collector.py tests/test_kalshi_sports_blocker_clearance_cycle.py tests/test_kalshi_claude_advice_audit.py -v`: `16 passed`
- `ruff check` on touched collector/blocker files: clean
- `python3 -m py_compile` on touched scripts: clean
- `make kalshi-always-on-collector-once`: exits `0`
- `make kalshi-sports-event-velocity-eta`: exits `0`
- `make kalshi-claude-advice-audit`: exits `0`
- `make kalshi-sports-blocker-clearance-cycle`: exits `0`

No thresholds were lowered, no labels were inferred, and no account/order/live
execution path was touched.
