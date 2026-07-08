# Make Venv Repair For Fable Evidence Cycles

Date: 2026-07-08

## Summary

Fixed the environment failure that caused Fable sports blocker-clearance due runs to fail when the configured Make Python pointed at a broken `.venv/bin/python` symlink. The failure surfaced inside `kalshi-sports-paper-burn-in-cycle` when `kalshi-universe-scan` attempted to run `predmarket.kalshi_universe_scan` through the broken venv interpreter.

## Change

- Made `VENV`, `PYTHON`, `PIP`, `PYTEST`, and `ALEMBIC` overridable Make defaults with `?=`.
- Added `venv-ready`, which recreates the configured venv and installs pinned runtime requirements when `$(PYTHON)` is missing or not executable.
- Routed `setup`, `check-env`, and `kalshi-universe-scan` through `venv-ready`.
- Added a regression test proving the Makefile contract remains present.

## Verification

- `TMPDIR=$PWD/.tmp TMP=$PWD/.tmp TEMP=$PWD/.tmp python3 -m pytest tests/test_kalshi_universe_scan.py::test_makefile_repairs_broken_venv_before_universe_scan -q` -> `1 passed`
- `TMPDIR=$PWD/.tmp TMP=$PWD/.tmp TEMP=$PWD/.tmp python3 -m pytest tests/test_kalshi_universe_scan.py::test_makefile_exposes_universe_scan_targets tests/test_kalshi_universe_scan.py::test_makefile_repairs_broken_venv_before_universe_scan -q` -> `2 passed`
- `python3 -m py_compile tests/test_kalshi_universe_scan.py` -> pass
- `PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make check-env VENV=/tmp/predmarket-alpha-fable-venv` -> `runtime imports ok`
- `make -n kalshi-universe-scan VENV=/tmp/predmarket-alpha-fable-venv` -> shows `venv-ready` before the scan
- Broken-venv repair proof: `make check-env VENV=/tmp/predmarket-alpha-make-repair-test` recreated the venv and ended with `runtime imports ok`

## Latest Artifact State

- Blocker cycle: `sports_blocker_clearance_cycle_waiting_for_next_clock`, `0` due tasks, `2` waiting tasks, next clock `2026-07-08T22:45:00Z`
- Fable audit: `15/15` implementation, evidence still open for `CLAUDE-005`, `CLAUDE-008`, `CLAUDE-012`, `CLAUDE-014`, and `CLAUDE-015`
- Consensus falsification: `964` joined labels, `70` independent labels, `21` OOS labels, `1` tested hypothesis, `0` FDR survivors
- ATP evidence gate: `962` settled labels, `8/10` forward-OOS
- Paper/live: `0` usable paper rows, `$0` paper stake, `0` live eligible rows, `$0` live stake

## Guardrails

No thresholds changed. No labels were inferred. No sportsbook results were used as settlement labels. No EV, paper, live, account, order, or execution promotion occurred.
