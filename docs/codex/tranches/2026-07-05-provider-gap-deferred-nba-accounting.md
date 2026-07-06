# Provider Gap Deferred NBA Accounting

Date: 2026-07-05

## Summary

Cleaned up the sports sharp-consensus provider audit so the current NBA offseason/no-current-row state is not counted as an active provider maturity blocker. NBA remains visible as a target sport, but is now explicitly `deferred_no_current_rows` when configured and when no local provider observations exist. The only active provider maturity gap in the latest artifact is soccer Asian-sharp coverage.

## Changes

- Added config-backed deferred target sport handling to `predmarket/sports_consensus_provider_policy.py`.
- Added `--deferred-target-sports` to `scripts/kalshi_sports_consensus_provider_audit.py`.
- Wired `KALSHI_SPORTS_CONSENSUS_PROVIDER_AUDIT_DEFERRED_SPORTS ?= nba` into `make kalshi-sports-consensus-provider-audit`.
- Surfaced deferred/actionable provider gap fields in the sports evidence cycle summary and markdown.
- Updated tests to preserve the old no-defer behavior and prove configured NBA defer semantics.

## Latest State

Refreshed provider audit:

- Status: `sports_consensus_provider_audit_ready_with_per_sport_gaps`
- Covered sports: `mlb`, `tennis`, `nfl`
- Deferred sports: `nba`
- Actionable gap sports: `soccer`
- Sport gap count: `1`
- Sport deferred count: `1`

Refreshed sports evidence cycle:

- Status: `sports_evidence_cycle_ready_with_label_progress`
- Provider actionable gaps: `["soccer"]`
- Provider deferred sports: `["nba"]`
- Consensus falsification remains correctly blocked on labels: `29/30` independent and `9/10` OOS before testing.
- Live remains blocked with `0` eligible rows.

## Verification

- Focused provider/evidence-cycle tests: `18 passed`
- Touched-file Ruff: clean
- `make kalshi-sports-consensus-provider-audit`: exits `0`
- `make kalshi-sports-evidence-cycle-report`: exits `0`

## Remaining Blockers

- Sports consensus still needs one more independent/OOS label before OOS/FDR can test the lane.
- Soccer remains the only active provider maturity gap because no SBOBet/Singbet/IBC-style Asian sharp reference has been observed locally.
- Passive liquidity has enough paper-fill labels to test, but no FDR survivor.
- Live stays correctly blocked.
