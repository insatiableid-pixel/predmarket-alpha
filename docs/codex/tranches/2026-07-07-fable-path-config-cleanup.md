# Fable Path/Config Cleanup

Date: 2026-07-07

## Why

Fable called out hardcoded `/home/mrwatson/...` path assumptions as a portability and disaster-recovery liability, especially in the always-on collector, passive-fill loop, and labeled-observation builder. The always-on collector no longer had that hardcoding, but several evidence acquisition scripts still did.

## What Changed

- Added shared path helpers in `predmarket.shared_helpers`:
  - `configured_path(default, *env_vars)`
  - `manual_drop_path(*parts, env_vars=...)`
  - `project_path(repo_name, *parts, env_vars=...)`
- Moved Fable-critical manual-drop defaults to `PREDMARKET_MANUAL_DROPS_ROOT`, while preserving script-specific env overrides:
  - `scripts/kalshi_labeled_observation_builder.py`
  - `scripts/kalshi_labeled_oos_backtest.py`
  - `scripts/kalshi_passive_liquidity_paper_fill_loop.py`
  - `scripts/kalshi_tick_recorder.py`
  - `scripts/kalshi_sports_line_move_delta_logger.py`
  - `scripts/kalshi_resolved_archive_backfill.py`
- Added regression coverage in `tests/test_kalshi_path_defaults.py`.

## Guardrails

- No thresholds changed.
- No labels inferred.
- No EV, paper, or live promotion changed.
- No account, order, or execution path touched.
- Existing Make/CLI path overrides remain valid.

## Verification

- Focused path and collector tests: `40 passed`.
