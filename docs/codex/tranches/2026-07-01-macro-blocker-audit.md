# Macro Blocker Audit

Date: 2026-07-01

## Summary

Added a command-center blocker audit that proves whether every active macro lane is blocked by a named missing input with a concrete next command. This is the stop-condition proof for the research-only federated Kalshi EV goal when no lane can emit usable rows without external evidence.

## Changes

- Added `scripts/codex_macro_blocker_audit.py`.
- Added `make macro-blocker-audit`.
- Added `tests/test_codex_macro_blocker_audit.py`.
- Tightened `scripts/codex_macro_unlock_scout.py` so NBA and NFL route lanes name exact missing inputs instead of generic parked-state text.
- Added latest audit outputs:
  - `docs/codex/macro/macro-blocker-audit-latest/macro-blocker-audit.json`
  - `docs/codex/macro/macro-blocker-audit-latest/macro-blocker-audit.md`
  - `docs/codex/macro/latest-macro-blocker-audit.json`
  - `docs/codex/macro/latest-macro-blocker-audit.md`

## Result

Latest status is `macro_blocker_audit_all_lanes_blocked_with_exact_inputs`.

- Lanes: `5`
- Blocked lanes: `5`
- Specific missing-input lanes: `5`
- Next-command lanes: `5`
- Usable EV rows: `0`
- Ready NFL target matches: `0`
- NFL overlays written: `false`

## Lane Inputs

| Repo | Missing Input |
| --- | --- |
| `predmarket-alpha` | Local Kalshi NFL contract snapshot for one selected work-order game, including exact ticker, official terms, clean timing, and executable cost. |
| `mlb-platform` | Broader book/line/source coverage, an independent clean slate, or stronger true closing-line validation. |
| `atp-oracle` | Fresh validation/promotion evidence plus D3/G5/P5 external proof. |
| `nba-analytics-platform` | New source-backed NBA signal or market dataset that can beat the current market-parity baseline. |
| `nfl_quant_glm51_greenfield` | Forward-context evidence when due or manually dropped outside the repo: injuries, weather, official starting QBs/depth chart changes, and closing/reference line evidence. |

## Verification

- `TMPDIR=.tmp PYTHONPATH=. .venv/bin/pytest -q tests/test_codex_macro_blocker_audit.py tests/test_codex_macro_unlock_scout.py`
  - 21 passed
- `.venv/bin/ruff check scripts/codex_macro_blocker_audit.py scripts/codex_macro_unlock_scout.py tests/test_codex_macro_blocker_audit.py tests/test_codex_macro_unlock_scout.py`
  - all checks passed
- `make macro-unlock-scout`
  - all five lanes have specific missing inputs
- `make macro-blocker-audit`
  - `macro_blocker_audit_all_lanes_blocked_with_exact_inputs`

No provider/API calls, paid calls, database writes, account/order paths, market execution, or raw payload copies into the repo were introduced.
