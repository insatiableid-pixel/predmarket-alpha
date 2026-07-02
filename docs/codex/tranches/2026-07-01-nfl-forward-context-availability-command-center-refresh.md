# 2026-07-01 NFL Forward Context Availability Command-Center Refresh

## What Changed

- Predmarket macro router now reads NFL's forward-context availability artifact.
- New NFL status: `line_readiness_profiled_slate_forward_context_not_yet_due_research_only`.
- Scheduler parks NFL when the fair-line/current-market machinery is ready but missing injury/weather/official-QB/closing inputs are not due yet.

## Current Route

`make macro-route` now reports `all_lanes_parked=true` and recommends predmarket as command center.

NFL moved from priority `22` to `-5`.

## Why

NFL Week 1 is still too far away for the missing forward-context inputs to be responsibly collected. The real NFL artifact says:

- earliest cached game date: `2026-09-09`
- weather due: `2026-08-30`
- starting QBs due: `2026-09-02`
- injuries due: `2026-09-05`
- closing reference due: `2026-09-09`

## Verification

- `TMPDIR=.tmp PYTHONPATH=. .venv/bin/pytest -q tests/test_codex_macro_router.py`
- `.venv/bin/ruff check scripts/codex_macro_router.py tests/test_codex_macro_router.py`
- `make macro-route`
- `make macro-unlock-scout`
