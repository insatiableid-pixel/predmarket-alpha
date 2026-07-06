# Sports Consensus No-Testable-Hypotheses Status

Date: 2026-07-05

## Summary

The post-00:00Z consensus probe cleared the global sports no-vig consensus label floor, but revealed a more precise blocker: no pre-registered rule or price bucket has enough applicable OOS labels to enter FDR. The artifact now reports `sports_consensus_falsification_blocked_no_testable_hypotheses` instead of the stale/coarse `blocked_insufficient_labels` status.

## Changes

- Added `sports_consensus_falsification_blocked_no_testable_hypotheses` to `predmarket/sports_consensus_falsification.py`.
- Added `evaluation_status_counts` and `max_hypothesis_oos_count` to the falsification summary.
- Updated the falsification next-action guidance to accumulate rule/bucket OOS labels without lowering floors or adding post-hoc rules.
- Added regression coverage for the exact state where global independent/OOS floors pass but every pre-registered hypothesis remains below the per-hypothesis OOS floor.

## Latest State

Focused post-00:00Z probe:

- Observation loop status: `sports_consensus_observation_loop_label_rows_ready`
- New exact consensus label rows: `22`
- Total consensus labels: `194`
- Joined labels: `185`
- Independent labels: `31/30`
- OOS labels: `10/10`
- Tested hypotheses: `0`
- FDR survivors: `0`
- Max hypothesis OOS count: `5/10`
- Evaluation status counts: `{"blocked_insufficient_oos_labels": 30}`
- Falsification status: `sports_consensus_falsification_blocked_no_testable_hypotheses`

Provider state after the same refresh:

- Active provider gap sports: `soccer`
- Deferred target sports: `nba`
- Covered sports: `mlb`, `tennis`, `nfl`

## Verification

- Focused falsification/evidence-cycle tests: `14 passed`
- Touched-file Ruff: clean
- `make kalshi-sports-consensus-observation-loop KALSHI_SPORTS_CONSENSUS_PROBE_OBSERVED=1`: exits `0`
- `make kalshi-sports-consensus-falsification`: exits `0`
- `make kalshi-sports-evidence-cycle-report`: exits `0`

## Remaining Blockers

- Sports consensus needs more exact labels concentrated inside pre-registered rule/price-bucket cells, not just more global labels.
- Soccer still needs a legal timestamped Asian-sharp reference before World Cup consensus is mature.
- Passive liquidity remains statistically rejected/no-survivor so far.
- Live remains blocked.
