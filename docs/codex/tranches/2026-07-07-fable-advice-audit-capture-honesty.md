# Fable Advice Audit Capture Honesty

Date: 2026-07-07

## Why

The Fable checklist was reporting implementation complete while two evidence-acquisition surfaces were only indirectly represented by tranche notes and collector output:

- 60s sharp-provider line-move delta capture
- Kalshi sports `ticker` / `orderbook_delta` tick capture

That made the machine audit too flattering. A code-complete recorder that has not recorded rows because WebSocket auth is missing is not an evidence-complete surface.

## What Changed

- Added `CLAUDE-011` to `scripts/kalshi_claude_advice_audit.py`:
  - `sharp_line_move_delta_capture`
  - satisfied only when the line-move delta logger has provider snapshots, events, and no provider errors
- Added `CLAUDE-012`:
  - `kalshi_tick_orderbook_delta_capture`
  - satisfied only after append-only Kalshi WebSocket rows are recorded
  - reports `blocked_external` when the recorder is wired but missing/invalid market-data auth
- Added focused tests proving:
  - line-move capture can satisfy evidence
  - tick capture remains externally blocked when auth is absent
  - tick capture becomes satisfied only after recorded rows exist

## Refreshed Real State

`make kalshi-claude-advice-audit` now reports:

- requirements: `12`
- implementation satisfied: `12/12`
- evidence satisfied: `9/12`
- open evidence IDs: `CLAUDE-005`, `CLAUDE-008`, `CLAUDE-012`
- line-move capture: `4` snapshots, `99` events, `23` deltas, `23` line moves, `0` errors
- tick capture: `250` sports tickers selected, `ticker` + `orderbook_delta` configured, `0` recorded lines
- tick blocker: `kalshi_tick_recorder_blocked_missing_or_invalid_auth`

## Guardrails

- No thresholds changed.
- No labels inferred.
- No EV, paper stake, candidate promotion, or live eligibility changed.
- No account, order, or execution path touched.

## Verification

```bash
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp /home/mrwatson/projects/predmarket-alpha/.venv/bin/python -m pytest tests/test_kalshi_claude_advice_audit.py -q
/home/mrwatson/projects/predmarket-alpha/.venv/bin/ruff check scripts/kalshi_claude_advice_audit.py tests/test_kalshi_claude_advice_audit.py
/home/mrwatson/projects/predmarket-alpha/.venv/bin/python -m py_compile scripts/kalshi_claude_advice_audit.py
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-claude-advice-audit
```

Results:

- focused tests: `5 passed`
- Ruff: pass
- py-compile: pass
- audit target: exit `0`
