# Fable Capture-Target Collector Operationalization

Date: 2026-07-07

## Why

Fable's T2 advice was not just "create a tick recorder and line-move logger." The evidence clock has to run continuously before stale-quote features exist, because missed tick and line-move history cannot be reconstructed later.

Before this tranche, `make kalshi-tick-recorder` and `make kalshi-sports-line-move-delta-logger` existed as separate commands, but `make kalshi-always-on-collector` only scheduled sports settlement/burn-in and crypto targets by default.

## What Changed

- Added first-class always-on collector targets:
  - `line_moves` -> `make kalshi-sports-line-move-delta-logger`
  - `ticks` -> `make kalshi-tick-recorder`
- Changed `KALSHI_ALWAYS_ON_COLLECTOR_TARGETS` default to:
  - `line_moves,ticks,sports_consensus,sports,crypto`
- Added capture health to always-on collector artifacts:
  - `capture_count`
  - `gap_count`
  - summary `total_capture_count`
  - summary `total_gap_count`
- Added high-frequency capture cadence:
  - capture targets advertise `poll_interval_seconds=60`
  - collector emits cadence reason `high_frequency_capture_interval`
  - settlement due/near-close cadence still takes precedence when applicable

## Real Run

Command:

```bash
KALSHI_ALWAYS_ON_COLLECTOR_TARGETS=line_moves,ticks \
KALSHI_TICK_RECORDER_DURATION_SECONDS=1 \
make kalshi-always-on-collector-once
```

Result:

- collector status: `kalshi_always_on_collector_ready`
- safe artifacts: `2/2`
- cadence reason: `high_frequency_capture_interval`
- interval: `60`
- total capture count: `177`
- total gap/error count: `0`

Target details:

- `line_moves`: `kalshi_sports_line_move_delta_logger_ready_with_deltas`
  - `4` provider snapshots
  - `102` events
  - `242` deltas
  - `177` line moves
  - `0` provider errors
- `ticks`: `kalshi_tick_recorder_blocked_missing_or_invalid_auth`
  - `250` sports tickers selected
  - `ticker,orderbook_delta` channels configured
  - `0` recorded lines
  - blocker: missing read-only Kalshi private key via `KALSHI_API_SECRET` or `venues.kalshi.api_secret`

## Guardrails

- No probabilities generated.
- No settlement labels inferred.
- No EV, paper stake, or candidate promotion.
- No threshold changes.
- No live/account/order paths touched.
- Tick recorder remains read-only and safely blocked until market-data auth is configured.

## Verification

- `python -m py_compile scripts/kalshi_always_on_collector.py scripts/kalshi_tick_recorder.py scripts/kalshi_sports_line_move_delta_logger.py`
- `.venv/bin/python -m pytest -s tests/test_kalshi_always_on_collector.py tests/test_kalshi_tick_recorder.py tests/test_kalshi_sports_line_move_delta_logger.py` -> `18 passed`
