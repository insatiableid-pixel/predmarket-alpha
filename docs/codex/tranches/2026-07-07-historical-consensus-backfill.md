# Historical Consensus Backfill

Implemented the Fable-requested replay surface that was still only feasibility-gated.

## What Changed

- Added `scripts/kalshi_sports_historical_consensus_backfill.py`.
- Added `make kalshi-sports-historical-consensus-backfill`.
- Added focused tests in `tests/test_kalshi_sports_historical_consensus_backfill.py`.

The runner consumes a replayable historical sharp no-vig consensus archive, exact
Kalshi settled-market labels, and Kalshi candlesticks. It enforces exact
`contract_ticker`, side, provider snapshot skew, Kalshi quote skew, and public
Kalshi settlement joins before routing rows through the existing
`sports_consensus_falsification` 30-cell OOS/FDR grid.

## Real Run

Commands:

```bash
make kalshi-sports-historical-consensus-feasibility
make kalshi-sports-historical-consensus-backfill
```

Result:

- Feasibility: `kalshi_sports_historical_consensus_feasibility_ready_paid_access_unverified`
- Backfill: `kalshi_sports_historical_consensus_backfill_blocked_missing_historical_archive`
- Historical consensus rows: `0`
- Valid observations: `0`
- Tested hypotheses: `0`
- FDR survivors: `0`
- Kalshi raw settled-market sha256: `14af356170bc2b1fc6b09b667a8bff79aa72717203183dc5c6f224b9344f6937`
- Kalshi raw candlestick sha256: `bbf1a6d095bebd0540b704fd3a33c42f4c077c854df49dac5b5e105f8e79d0a8`

The current blocker is now exact and external: no normalized historical
consensus archive exists at
`/home/mrwatson/manual_drops/kalshi_sports_historical_consensus/kalshi_sports_historical_consensus_latest.json`.

## Verification

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp python -m pytest \
  tests/test_kalshi_sports_historical_consensus_backfill.py \
  tests/test_kalshi_sports_historical_consensus_feasibility.py \
  tests/test_kalshi_resolved_archive_backfill.py
```

`14 passed`.

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp ruff check \
  scripts/kalshi_sports_historical_consensus_backfill.py \
  tests/test_kalshi_sports_historical_consensus_backfill.py
```

`All checks passed`.

No thresholds were lowered, no sportsbook settlement labels were used, no EV or
paper stake was emitted, and no live/account/order path was touched.
