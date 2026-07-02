# Predmarket Type 2 Reference Builder Hardening

Date: 2026-06-28

## Summary

Turned the one-off local sportsbook-reference build into a repeatable, tested command.

## Implementation

- Added `predmarket/type2_reference_builder.py`.
- Added `make type2-reference-build`.
- Added `tests/test_type2_reference_builder.py`.
- Updated macro status to hash and summarize the builder artifacts.

## Builder Rule

The builder maps MLB game-winner rows by:

1. Exact sportsbook team pair.
2. Kalshi game event ticker time parsed as America/New_York game start.
3. Nearest event time to sportsbook `commence_time`, bounded by `TYPE2_REFERENCE_BUILD_MAX_DELTA_SECONDS`.

This fixes the repeated-team-matchup bug where two San Francisco/Miami, Washington/Tampa Bay, or Pittsburgh/Colorado games could collide on the same ticker.

## Result

- `make type2-reference-build`: `reference_built_with_warnings`.
- Reference rows: 42.
- Unique Kalshi tickers: 42.
- Duplicate Kalshi tickers: 0.
- Max event-match delta seconds: 60.
- Skipped events: 1 (`Minnesota Twins @ Arizona Diamondbacks`, no matched Kalshi event in the local snapshot).
- Downstream preflight: `reference_ready`.
- Downstream matcher: `review_candidates_present`.
- Downstream disposition: `candidate_disposition_all_passes_downgraded`.

## Verification

- `TMPDIR=$PWD/.tmp TMP=$PWD/.tmp TEMP=$PWD/.tmp PYTHONPATH=. .venv/bin/pytest tests/test_codex_macro_router.py tests/test_type2_reference_builder.py tests/test_type2_candidate_disposition.py tests/test_type2_reference_intake.py tests/test_type2_paper_matcher.py -q`
  - 40 passed.
- `.venv/bin/ruff check scripts/codex_macro_router.py predmarket/type2_reference_builder.py tests/test_type2_reference_builder.py`
  - All checks passed.
- `make macro-status`
  - Status: `kalshi_type2_candidate_disposition_all_passes_downgraded`.
  - Builder status: `reference_built_with_warnings`.
- `make macro-route`
  - `all_lanes_parked=true`.

## Guardrail

No provider/API calls, paid calls, database writes, account/order paths, market execution, staking/sizing language, or tradable claims were introduced.
