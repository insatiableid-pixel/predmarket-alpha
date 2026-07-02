# Kalshi EV NFL Overlay Assembler

Date: 2026-07-01

## Summary

Added a guarded NFL overlay assembler to remove the next manual hand-editing step after a local Kalshi NFL contract snapshot appears. The assembler reads local command-center artifacts only and writes safe outside-repo overlays only when the scout has a ready target match.

## Changes

- Added `scripts/kalshi_ev_nfl_overlay_assembler.py`.
- Added `make kalshi-ev-nfl-overlay-assembler`.
- Added focused tests in `tests/test_kalshi_ev_nfl_overlay_assembler.py`.
- Tightened `scripts/kalshi_ev_local_contract_evidence_scout.py` so a target match is ready only when ticker, official terms, executable cost, and clean timing are all present.
- Wired assembler status into:
  - `scripts/codex_macro_router.py`
  - `scripts/codex_macro_unlock_scout.py`
  - `docs/codex/current-state.md`

## Current Result

Latest assembler status is `nfl_overlay_assembler_blocked_no_ready_local_contract_evidence`.

- Target NFL work-order sides: `32`
- Scout target matches: `0`
- Ready target matches: `0`
- Assembled overlay pairs: `0`
- Overlays written: `false`

The assembler correctly wrote no overlays because the local contract-evidence scout still reports `local_contract_evidence_blocked_no_nfl_target_snapshot`.

## Ready Path

The synthetic ready-path test proves that when a local target match includes:

- exact Kalshi `contract_ticker`
- exact `event_ticker`
- verified official resolution rule
- executable YES ask/cost
- clean timing status
- validated NFL calibrated probability from the work order

the assembler writes matching JSON overlays under the outside-repo manual-drop directories consumed by the EV ledger.

## Verification

- `TMPDIR=.tmp PYTHONPATH=. .venv/bin/pytest -q tests/test_kalshi_ev_local_contract_evidence_scout.py tests/test_kalshi_ev_nfl_overlay_assembler.py tests/test_codex_macro_router.py tests/test_codex_macro_unlock_scout.py`
  - 65 passed
- `.venv/bin/ruff check scripts/kalshi_ev_local_contract_evidence_scout.py scripts/kalshi_ev_nfl_overlay_assembler.py scripts/codex_macro_router.py scripts/codex_macro_unlock_scout.py tests/test_kalshi_ev_local_contract_evidence_scout.py tests/test_kalshi_ev_nfl_overlay_assembler.py tests/test_codex_macro_router.py tests/test_codex_macro_unlock_scout.py`
  - all checks passed
- `make kalshi-ev-contract-mapping-work-order`
  - `contract_mapping_work_order_ready`
- `make kalshi-ev-local-contract-evidence-scout`
  - `local_contract_evidence_blocked_no_nfl_target_snapshot`
- `make kalshi-ev-nfl-overlay-assembler`
  - `nfl_overlay_assembler_blocked_no_ready_local_contract_evidence`
- `make kalshi-ev-ledger`
  - `kalshi_ev_ledger_candidates_present_but_not_usable`
- `make kalshi-ev-overlay-preflight`
  - `overlay_preflight_blocked_missing_or_unjoined_inputs`
- `make macro-route`
  - recommended repo `predmarket-alpha`
- `make macro-unlock-scout`
  - missing input remains a local Kalshi NFL contract snapshot
- `make macro-status`
  - status `kalshi_ev_local_contract_evidence_blocked_no_nfl_target_snapshot`

No provider/API calls, paid calls, database writes, account/order paths, market execution, or raw payload copies into the repo were introduced.
