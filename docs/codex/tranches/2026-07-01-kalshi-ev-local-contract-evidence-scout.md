# Kalshi EV Local Contract Evidence Scout

Date: 2026-07-01

## Summary

Added a read-only local contract-evidence scout for the federated Kalshi EV ledger. The scout answers whether the command center already has local JSON evidence for exact Kalshi ticker/event_ticker, official terms, and executable cost before a worker fills contract-mapping/probability overlays.

## Changes

- Added `scripts/kalshi_ev_local_contract_evidence_scout.py`.
- Added `make kalshi-ev-local-contract-evidence-scout`.
- Added focused tests in `tests/test_kalshi_ev_local_contract_evidence_scout.py`.
- Wired the scout into `scripts/codex_macro_router.py` and `scripts/codex_macro_unlock_scout.py`.
- Added the missing-input contract at `docs/codex/manual-drops/kalshi-ev-nfl-contract-snapshot-contract.md`.
- Regenerated:
  - `docs/codex/macro/kalshi-ev-local-contract-evidence-scout-latest/kalshi-ev-local-contract-evidence-scout.json`
  - `docs/codex/macro/kalshi-ev-local-contract-evidence-scout-latest/kalshi-ev-local-contract-evidence-scout.md`
  - `docs/codex/macro/latest-kalshi-ev-local-contract-evidence-scout.json`
  - `docs/codex/macro/latest-kalshi-ev-local-contract-evidence-scout.md`
  - `docs/codex/macro/latest-status.json`
  - `docs/codex/macro/latest-decision.json`
  - `docs/codex/macro/latest-unlock-scout.json`

## Result

Latest scout status is `local_contract_evidence_blocked_no_nfl_target_snapshot`.

- Local JSON files scanned: `9`
- Local Kalshi-like contract rows extracted: `10576`
- Rows with official terms: `10576`
- Rows with executable-cost fields: `10576`
- NFL contract-evidence rows: `0`
- Selected NFL work-order sides: `32`
- Possible target matches: `0`
- Ready target matches: `0`

The scout originally surfaced two false positives from non-NFL text. The implementation now prevents CFL rows and strings such as `inflation` from matching the NFL target lane.

## Router State

`make macro-route` now recommends `predmarket-alpha` with status `kalshi_ev_local_contract_evidence_blocked_no_nfl_target_snapshot`, priority `21`, and the stop condition against guessing tickers, inventing terms/costs, making provider/live calls without authorization, or touching account/order paths.

## Next Input

Drop a local Kalshi NFL contract snapshot for one selected work-order game under `/home/mrwatson/manual_drops/kalshi/`. It must include exact `ticker`/`event_ticker`, official rules, clean timing, and YES ask or ticket payout/cost evidence. The exact contract is documented in `docs/codex/manual-drops/kalshi-ev-nfl-contract-snapshot-contract.md`.

## Verification

- `TMPDIR=.tmp PYTHONPATH=. .venv/bin/pytest -q tests/test_kalshi_ev_local_contract_evidence_scout.py`
  - 4 passed
- `TMPDIR=.tmp PYTHONPATH=. .venv/bin/pytest -q tests/test_kalshi_execution_cost.py tests/test_kalshi_contract_ev_ledger.py tests/test_kalshi_ev_local_contract_evidence_scout.py tests/test_codex_macro_router.py tests/test_codex_macro_unlock_scout.py`
  - 94 passed
- `.venv/bin/ruff check scripts/kalshi_ev_local_contract_evidence_scout.py scripts/codex_macro_router.py scripts/codex_macro_unlock_scout.py tests/test_kalshi_ev_local_contract_evidence_scout.py tests/test_codex_macro_router.py tests/test_codex_macro_unlock_scout.py`
  - all checks passed
- `make kalshi-ev-contract-mapping-work-order`
  - `contract_mapping_work_order_ready`
- `make kalshi-ev-local-contract-evidence-scout`
  - `local_contract_evidence_blocked_no_nfl_target_snapshot`
- `make kalshi-ev-ledger`
  - `kalshi_ev_ledger_candidates_present_but_not_usable`
- `make kalshi-ev-overlay-preflight`
  - `overlay_preflight_blocked_missing_or_unjoined_inputs`
- `make macro-route`
  - recommended repo `predmarket-alpha`
- `make macro-unlock-scout`
  - missing input is a local Kalshi NFL contract snapshot
- `make macro-status`
  - status `kalshi_ev_local_contract_evidence_blocked_no_nfl_target_snapshot`

No provider/API calls, paid calls, database writes, account/order paths, market execution, or raw payload copies into the repo were introduced.
