# Fable Tick Recorder Rotation

Date: 2026-07-07

## Why

Fable's stale-quote tranche requires append-only Kalshi sports tick/orderbook capture with gap/reconnect accounting and disk-growth control. The WebSocket auth blocker is external, but the recorder should already be ready to run for long capture windows once the read-only Kalshi private key is configured.

## What Changed

- Added monotonic receive timestamps to every JSONL row:
  - `received_monotonic_ns`
- Added configurable JSONL rotation:
  - CLI: `--rotate-bytes`
  - Make: `KALSHI_TICK_RECORDER_ROTATE_BYTES`
  - default: `250000000`
- Added per-file safety/provenance metadata:
  - `path`
  - `sha256`
  - `byte_count`
  - `jsonl_file_count`
  - `rotation_count`
- Preserved append-only behavior:
  - rotation creates `.part-0002.jsonl`, `.part-0003.jsonl`, etc.
  - existing files are not rewritten.

## Real Run

Command:

```bash
KALSHI_TICK_RECORDER_DURATION_SECONDS=1 \
KALSHI_TICK_RECORDER_ROTATE_BYTES=1024 \
make kalshi-tick-recorder
```

Result:

- status: `kalshi_tick_recorder_blocked_missing_or_invalid_auth`
- selected sports tickers: `250`
- recorded lines: `0`
- JSONL files: `0`
- rotations: `0`
- blocker: `Kalshi private key is required: set venues.kalshi.api_secret or KALSHI_API_SECRET`

The blocker is external credential configuration, not a statistical or execution-policy blocker. The recorder still exits `0` and writes a safe artifact so unattended loops can surface the problem without touching account/order paths.

## Guardrails

- No probabilities generated.
- No labels inferred.
- No EV, paper stake, or candidate promotion.
- No threshold changes.
- No live/account/order paths touched.
- WebSocket client remains read-only.

## Verification

- `/home/mrwatson/projects/predmarket-alpha/.venv/bin/python -m pytest -s tests/test_kalshi_tick_recorder.py tests/test_kalshi_websocket.py` -> `25 passed`
- `/home/mrwatson/projects/predmarket-alpha/.venv/bin/ruff check scripts/kalshi_tick_recorder.py tests/test_kalshi_tick_recorder.py` -> pass
- `/home/mrwatson/projects/predmarket-alpha/.venv/bin/python -m py_compile scripts/kalshi_tick_recorder.py predmarket/kalshi_websocket.py` -> pass
