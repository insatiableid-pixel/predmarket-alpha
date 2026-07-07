# 2026-07-07 Fable Makefile Root Config

## Purpose

Close the remaining Makefile-level portability gap from the Fable advice:
evidence-acquisition scripts had become configurable, but Make defaults still
pinned many data and donor paths to `/home/mrwatson/...`.

## Changes

- Added `PREDMARKET_MANUAL_DROPS_ROOT ?= $(HOME)/manual_drops`.
- Added `PREDMARKET_PROJECTS_ROOT ?= $(HOME)/projects`.
- Replaced all Makefile defaults under `/home/mrwatson/manual_drops` with
  `$(PREDMARKET_MANUAL_DROPS_ROOT)`.
- Replaced all Makefile defaults under `/home/mrwatson/projects` with
  `$(PREDMARKET_PROJECTS_ROOT)`.
- Added a path-default regression test proving the Makefile does not hardcode
  those local roots.

## Scope

This is path policy only. The defaults still resolve to the same locations on
the current workstation through `$(HOME)`, but another clone can now redirect
all Make-driven local evidence roots without editing the Makefile.

## Guardrails

- No thresholds changed.
- No labels inferred.
- No candidate promotion.
- No EV/paper/live behavior change.
- No account/order/live execution path touched.

## Verification

- `rg -n "/home/mrwatson/(manual_drops|projects)" Makefile` returns no rows.
- `make -n kalshi-sports-consensus-preflight`
- `make -n kalshi-tick-recorder`
- `make -n kalshi-resolved-archive-backfill`
- `make -n kalshi-sports-blocker-clearance-cycle`
- `python -m pytest tests/test_kalshi_path_defaults.py -q`

Result: Make dry-runs expand successfully and path-default tests pass.
