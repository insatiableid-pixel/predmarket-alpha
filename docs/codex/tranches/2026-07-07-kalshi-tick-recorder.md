# Kalshi Tick Recorder

Date: 2026-07-07

## Landing

Implemented the Fable tick-capture surface as a small standalone split:

- Added raw receive-timestamped WebSocket messages to `predmarket/kalshi_websocket.py`.
- Allowed read-only multi-channel subscriptions so `ticker` and `orderbook_delta` can be recorded together.
- Added `scripts/kalshi_tick_recorder.py`.
- Added `make kalshi-tick-recorder`.
- Added focused unit coverage in `tests/test_kalshi_tick_recorder.py`.

## Real Run

Command:

```bash
make kalshi-tick-recorder KALSHI_TICK_RECORDER_DURATION_SECONDS=1
```

Result:

- Status: `kalshi_tick_recorder_blocked_missing_or_invalid_auth`
- Selected sports tickers: `250`
- Channels: `ticker,orderbook_delta`
- Recorded JSONL lines: `0`
- JSONL path: `/home/mrwatson/manual_drops/kalshi_ticks/kalshi_sports_ticks_20260707T005439Z.jsonl`
- JSONL sha256: `null`
- Error: `Kalshi private key is required: set venues.kalshi.api_secret or KALSHI_API_SECRET`

This is the correct fail-closed state for this environment: evidence cannot accrue until read-only Kalshi auth is configured.

## Guardrails

- Research-only.
- No database writes.
- No provider or paid sportsbook calls.
- No live account/order paths.
- No market execution.
- No paper stake, EV, or probability generation.
- Raw payload target remains outside the repo under `/home/mrwatson/manual_drops/kalshi_ticks/`.

## Verification

```bash
TMPDIR=/home/mrwatson/projects/predmarket-alpha-worktrees/fable-tick-recorder/.tmp \
  python3 -m pytest tests/test_kalshi_tick_recorder.py tests/test_kalshi_websocket.py -q
python3 -m ruff check predmarket/kalshi_websocket.py scripts/kalshi_tick_recorder.py tests/test_kalshi_tick_recorder.py
make kalshi-tick-recorder KALSHI_TICK_RECORDER_DURATION_SECONDS=1
```

Focused tests: `24 passed`.
