# Macro Unlock Scout

Date: 2026-06-28

## Summary

Added a local-only command-center report that turns parked macro blockers into concrete file/input checks.

## Implementation

- Added `scripts/codex_macro_unlock_scout.py`.
- Added `make macro-unlock-scout`.
- Added `tests/test_codex_macro_unlock_scout.py`.
- Wrote `docs/codex/macro/latest-unlock-scout.json`.
- Wrote `docs/codex/macro/latest-unlock-scout.md`.

## Result

The latest scout reports:

- All lanes parked: true.
- Manual drop root: `/home/mrwatson/manual_drops`.
- Odds API JSON files: 2.
- Kalshi manual-drop JSON files: 0.
- Predmarket reference exists: true.
- Predmarket is blocked because timing-safe candidates are 0.
- MLB is blocked because same-slate pregame Kalshi/drop evidence is missing.
- ATP is blocked on fresh validation/promotion evidence plus D3/G5/P5 external proof.
- NBA is blocked on a new source-backed signal or market dataset.
- NFL has fresh governance snapshots and no immediate work.

## Verification

- `TMPDIR=$PWD/.tmp TMP=$PWD/.tmp TEMP=$PWD/.tmp PYTHONPATH=. .venv/bin/pytest tests/test_codex_macro_unlock_scout.py tests/test_codex_macro_router.py tests/test_type2_reference_builder.py tests/test_type2_candidate_disposition.py -q`
  - 30 passed.
- `.venv/bin/ruff check scripts/codex_macro_unlock_scout.py tests/test_codex_macro_unlock_scout.py`
  - All checks passed.
- `make macro-unlock-scout`
  - Wrote latest unlock scout JSON/Markdown.

## Guardrail

No provider/API calls, paid calls, database writes, account/order paths, market execution, staking/sizing language, tradable claims, or invented evidence were introduced.
