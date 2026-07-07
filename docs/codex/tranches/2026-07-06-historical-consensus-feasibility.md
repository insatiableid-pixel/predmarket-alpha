# 2026-07-06 Historical Consensus Feasibility

## Summary

Added the Fable-required feasibility gate for historical sharp-consensus divergence backfill. This target decides whether historical sportsbook snapshots can be timestamp-matched tightly enough before any historical divergence rows enter falsification.

## Landed

- Added `scripts/kalshi_sports_historical_consensus_feasibility.py`.
- Added `make kalshi-sports-historical-consensus-feasibility`.
- Added focused tests in `tests/test_kalshi_sports_historical_consensus_feasibility.py`.
- Default run does not call the paid historical endpoint.

## Evidence

- Status: `kalshi_sports_historical_consensus_feasibility_ready_paid_access_unverified`
- Historical snapshot interval: `300s`
- Nearest-snapshot max expected absolute skew: `150s`
- Configured max allowed skew: `180s`
- Skew gate: pass
- Historical endpoint cost: `10` credits per region/market
- Paid access verified: `false`

## Guardrails

- No historical divergence backfill is run by this target.
- No sportsbook labels are treated as settlement labels.
- No probabilities, EV, paper stake, live execution, account access, or order path.
