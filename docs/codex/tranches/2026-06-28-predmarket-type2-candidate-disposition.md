# Predmarket Type 2 Candidate Disposition

Date: 2026-06-28

## Summary

Added a review-only disposition layer for the Type 2 paper matcher and used it to test whether the newly derived sportsbook reference produced any timing-safe review candidates.

## Cleanup First

- Found that the first derived sportsbook reference had duplicate `kalshi_ticker` rows for repeated same-team MLB matchups.
- Rebuilt `/home/mrwatson/manual_drops/predmarket/type2-sportsbook-reference.json` outside the repo using team pair plus nearest Kalshi occurrence-time matching.
- The rebuilt reference has 42 rows, 42 unique tickers, 0 duplicate tickers, and max event-match delta of 60 seconds.

## Implementation

- Added `predmarket/type2_candidate_disposition.py`.
- Added `make type2-candidate-disposition`.
- Added `tests/test_type2_candidate_disposition.py`.
- Updated `scripts/codex_macro_router.py` so predmarket parks when all paper-matcher pass rows are downgraded by timing checks.

## Result

- Type 2 reference preflight: `reference_ready`, 42/42 valid.
- Type 2 paper matcher: `review_candidates_present`, 42 candidates, 2 pass and 40 watch.
- Type 2 candidate disposition: `candidate_disposition_all_passes_downgraded`.
- Timing-safe review candidates kept: 0.
- Timing mismatches downgraded: 6.
- Manual timing unknowns: 0.

## Verification

- `TMPDIR=$PWD/.tmp TMP=$PWD/.tmp TEMP=$PWD/.tmp PYTHONPATH=. .venv/bin/pytest tests/test_codex_macro_router.py tests/test_type2_candidate_disposition.py tests/test_type2_reference_intake.py tests/test_type2_paper_matcher.py -q`
  - 35 passed.
- `.venv/bin/ruff check scripts/codex_macro_router.py predmarket/type2_candidate_disposition.py tests/test_type2_candidate_disposition.py`
  - All checks passed.
- `make macro-status`
  - Status: `kalshi_type2_candidate_disposition_all_passes_downgraded`.
  - Priority: -3.
- `make macro-route`
  - `all_lanes_parked=true`.

## Guardrail

No provider/API calls, paid calls, database writes, account/order paths, market execution, staking/sizing language, or tradable claims were introduced.
