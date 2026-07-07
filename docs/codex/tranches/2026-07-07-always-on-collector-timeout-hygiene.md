# Always-On Collector Timeout Hygiene

Date: 2026-07-07

## Purpose

Continue the Fable sports EV evidence-acquisition program by making the always-on collector robust to slow individual targets. A single hanging target must not prevent other safe collectors from recording timestamped line moves, exact settlement labels, or blocker-clock evidence.

## Changes

- `scripts/kalshi_always_on_collector.py`
  - Catches `subprocess.TimeoutExpired` in `run_make_target()`.
  - Emits a target-level `CommandResult` with `returncode=124`, captured stdout/stderr tails, and duration instead of crashing the whole cycle.
  - Adds `--command-timeout-seconds` to the CLI.

- `Makefile`
  - Adds `KALSHI_ALWAYS_ON_COLLECTOR_COMMAND_TIMEOUT_SECONDS ?= 600`.
  - Wires the timeout into `kalshi-always-on-collector-once` and `kalshi-always-on-collector`.

- `tests/test_kalshi_always_on_collector.py`
  - Adds regression coverage proving a target timeout becomes an auditable target failure row.
  - Extends Makefile wiring coverage for the new timeout knob.

## Fresh Evidence Run

Command:

```bash
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp \
KALSHI_ALWAYS_ON_COLLECTOR_TARGETS=line_moves,ticks,sports_consensus,sports \
KALSHI_ALWAYS_ON_COLLECTOR_COMMAND_TIMEOUT_SECONDS=240 \
make kalshi-always-on-collector-once
```

Result:

- Collector status: `kalshi_always_on_collector_ready`
- Targets: `line_moves,ticks,sports_consensus,sports`
- Successful targets: `4/4`
- Safe artifacts: `4/4`
- Total label count surfaced by collector: `5,661`
- Total capture count surfaced by collector: `82`
- Total gap/error count: `0`

Target details:

- `line_moves`: `kalshi_sports_line_move_delta_logger_ready_with_deltas`, `82` deltas, `0` errors.
- `ticks`: `kalshi_tick_recorder_blocked_missing_or_invalid_auth`, still safe and explicit.
- `sports_consensus`: `sports_consensus_observation_loop_label_rows_ready`, `768` label rows.
- `sports`: `sports_paper_burn_in_ready_no_paper_usable_rows`, `4,893` exact labels, no paper-usable rows.

Post-run refresh:

- `make kalshi-sports-event-velocity-eta`
- `make kalshi-claude-advice-audit`
- `make kalshi-sports-blocker-clearance-cycle`

## Current Gate State

No statistical gate cleared:

- Fable audit: `15/15` implementation satisfied, `10/15` evidence satisfied.
- Open requirements: `CLAUDE-005`, `CLAUDE-008`, `CLAUDE-012`, `CLAUDE-014`, `CLAUDE-015`.
- Sports consensus falsification: `723` joined labels, `61` independent labels, `19` OOS labels, `0` tested hypotheses, `0` FDR survivors.
- Nearest consensus hypothesis: `kalshi_vs_consensus_fade_overpriced_threshold_0.005`, OOS deficit `3`.
- ATP: `8/10` forward-OOS resolved, next expected expiration `2026-07-08T06:00:00Z`.
- Tick recorder: `0` recorded lines, blocked by missing/invalid auth.
- Historical consensus: blocked on paid/archive access.
- Provider coverage: soccer remains the actionable gap.
- Paper: `0` usable, `$0` stake.
- Live: `0` eligible, `$0` stake.
- Next blocker clock: `2026-07-07T23:00:00Z`.

## Verification

```bash
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/test_kalshi_always_on_collector.py
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check scripts/kalshi_always_on_collector.py tests/test_kalshi_always_on_collector.py
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m py_compile scripts/kalshi_always_on_collector.py
```

Results:

- Focused tests: `11 passed`
- Ruff: passed
- Py-compile: passed
- One-shot collector: exited `0`
- ETA/Fable/blocker refresh targets: exited `0`

## Guardrails

- No thresholds changed.
- No labels inferred from sportsbooks.
- No Elo/projection probabilities added.
- No EV, paper, or live promotion occurred.
- No account/order/live execution path was touched.
