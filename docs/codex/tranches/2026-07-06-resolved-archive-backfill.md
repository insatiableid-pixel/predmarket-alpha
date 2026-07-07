# 2026-07-06 Resolved Archive Backfill

## Summary

Added the Kalshi-only resolved sports archive backfill Fable called out as the highest label-velocity bottleneck. The runner reads hashed settled-market and candlestick snapshots, reconstructs entry-price-at-horizon observations, and routes only the pre-registered price-bucket bias family through existing OOS/FDR falsification.

## Landed

- Added `scripts/kalshi_resolved_archive_backfill.py`.
- Added `make kalshi-resolved-archive-backfill`.
- Added focused tests in `tests/test_kalshi_resolved_archive_backfill.py`.
- Raw settled markets and candlesticks stay outside the repo under `/home/mrwatson/manual_drops/kalshi_resolved_archive_backfill/`.
- Per-ticker candlestick failures are tolerated for public API 404/422/429 behavior.
- Existing candlestick snapshots can be reused without recapturing.

## Real Evidence

- Status: `kalshi_resolved_archive_backfill_ready_no_fdr_survivors`
- Raw settled markets: `1200`
- Exact independent Kalshi labels: `1184`
- Horizon observations: `3552`
- Tested bucket-bias hypotheses: `2`
- Max hypothesis OOS count: `188`
- FDR survivors: `0`
- Raw markets sha256: `14af356170bc2b1fc6b09b667a8bff79aa72717203183dc5c6f224b9344f6937`
- Raw candlesticks sha256: `bbf1a6d095bebd0540b704fd3a33c42f4c077c854df49dac5b5e105f8e79d0a8`

## Guardrails

- Kalshi settlement labels only.
- No sportsbook-inferred labels.
- No threshold lowering or post-hoc bucket additions.
- No probability overlay, paper stake, live execution, account access, or order path.
