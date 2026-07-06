# Sports Blocker Clearance And Paper Covariance Fix

## Intent

Clear every sports blocker that can be cleared without weakening statistical gates, fabricating labels, or promoting live execution. Keep the north-star boundary intact: exact labels and OOS/FDR decide; paper can size only after all gates pass; live remains blocked until explicitly armed and justified.

## What Changed

- Ran the due sports evidence cycle with public observed-consensus probing enabled:
  - `KALSHI_SPORTS_CONSENSUS_PROBE_OBSERVED=1 make kalshi-sports-label-accumulation-cycle`
- Refreshed downstream paper, settlement, retirement, live-preflight, evidence-cycle, and label-accumulation artifacts.
- Fixed the paper sizing covariance penalty in `predmarket/paper_decision_engine.py`.
- Raised the research-only passive-liquidity paper TTL default from `3600` to `43200` seconds after the fill-clock diagnostic showed public snapshots were arriving outside the old TTL window.
- Split historical TTL/cadence mismatches from the active TTL setting so old short-lived paper intents remain auditable without being reported as the current blocker.
- Repaired the sports event-velocity ETA truth surface:
  - Passive paper-fill now reports `label_threshold_met_no_fdr_survivor` / `compute_or_downstream_gates` after fill/OOS thresholds are met but FDR finds no survivor.
  - Consensus settlement rows now wait for `next_expected_expiration_utc` instead of reporting stale last-probe timestamps as `next_probe_due_now`.
  - ATP now reports `external_forward_oos` after settlement labels are sufficient but ATP-oracle forward-OOS evidence is still short.

The bug: covariance penalty was computed as `lambda * rho * dollar_stake * same_cluster_dollar_stake`, which has dollar-squared units. With default settings, two `$200` positions in the same cluster produced a `$2000` penalty, zeroing all otherwise valid paper rows.

The fix: compute the penalty from exposure fractions:

```text
penalty_i = lambda * rho * stake_i * (same_cluster_other_stake / paper_bankroll)
```

The paper pipeline now passes the actual paper bankroll into the covariance function.

## Current Evidence State

- `latest-kalshi-sports-label-accumulation-cycle.json`
  - Status: `sports_label_accumulation_oos_fdr_paper_candidates_ready`
  - MLB: `340` exact labels, `56` independent labels, label deficit `0`
  - World Cup soccer: `1340` exact labels, `136` independent labels, `2` research candidates, label deficit `0`
  - ATP: `382` exact/independent labels, label deficit `0`
- `latest-kalshi-sports-consensus-falsification.json`
  - Status: `sports_consensus_falsification_blocked_insufficient_labels`
  - Latest post-`20:05Z` consensus watch added `63` observation rows and `8` new labels
  - `48` joined labels, `16` independent labels, `5` OOS labels
  - `0` tested hypotheses, `0` FDR survivors
  - Still below `30` independent / `10` OOS minimum
- `latest-kalshi-sports-event-velocity-eta.json`
  - Status: `sports_event_velocity_eta_ready_with_label_deficits`
  - `7` label-blocked surfaces, `0` paper-fill-blocked surfaces
  - Total label deficit `148`, total OOS deficit `58`, no immediate due surface
  - Next consensus probe is `2026-07-05T20:35:00Z`
  - ATP is `blocked_atp_forward_oos`, not waiting on Kalshi settlement labels
- `latest-kalshi-world-cup-outcome-independence-diagnostic.json`
  - Status: `world_cup_outcome_independence_diagnostic_ready_parallel_outcome_clocks`
  - Outcome-family clocks may be evaluated separately, while portfolio control still clusters by match.
- `latest-kalshi-near-resolution-flow-replay-gates.json`
  - Status: `near_resolution_flow_replay_gates_ready_for_ev_ledger_promotion`
  - `27` current candidates, `23` positive-depth rows, `14` raw correlation clusters
  - `12` controlled clusters
  - `60` OOS labels, `51` correct, q-value `6.16e-08`
  - Decay survival passes
- `latest-kalshi-near-resolution-flow-terms-capture.json`
  - Status: `near_resolution_flow_terms_capture_ready`
  - `23/23` current flow targets have official Kalshi rules captured
- `latest-paper-decision-candidates.json`
  - Status: `paper_decision_candidates_ready_with_paper_sized_rows`
  - `27` paper-usable rows
  - Total paper stake `$5060.815328`
  - `0` portfolio cap breaches
- `latest-kalshi-passive-liquidity-fill-clock-diagnostic.json`
  - Status: `passive_liquidity_fill_clock_diagnostic_ready_with_paper_fills`
  - `951` paper fill/timeout labels, `17` paper fills
  - `814` historical TTL/cadence mismatches, but `0` active TTL/cadence mismatches
  - Current TTL cadence aligned: `true`; recommended TTL `32460`, current max TTL `43200`
- `latest-kalshi-passive-liquidity-paper-fill-falsification.json`
  - Status: `passive_liquidity_paper_fill_falsification_ready_no_research_candidates`
  - `3` tested hypotheses, `0` FDR survivors, `0` research candidates
  - Public-touch paper fills remain separate from real exchange fills
- `latest-paper-settlement-reconciliation.json`
  - Status: `paper_settlement_reconciliation_waiting_for_close`
  - `27` paper-usable rows, `0` settled usable rows, `0` due unresolved usable rows
- `latest-kalshi-live-preflight.json`
  - Status: `kalshi_live_blocked`
  - `0` live-eligible rows, `$0` live stake

## Remaining Honest Blockers

- Sharp no-vig consensus lane is still label-bound: it needs `14` more independent labels and `5` more OOS labels before any hypothesis can be tested.
- ATP is no longer blocked on Kalshi settlement labels; its blocker is external forward-OOS/liquidity evidence from the ATP donor lane.
- Passive maker liquidity is no longer software/clock-blocked. It is now statistically blocked only: `17` paper fills and `3` tested hypotheses exist, but there are `0` FDR survivors.
- Live remains correctly blocked; this tranche produced paper evidence only.

## Verification

- Focused paper/covariance/portfolio-cap regression: `84 passed`
- Focused fill-clock/cycle regression: `8 passed`
- Focused sports ETA regression: `7 passed`
- Touched-file Ruff check/format and py-compile: clean
- `make test-unit`: `1327 passed / 15 deselected`
- `make test-integration`: `14 passed`
- `make lint-baseline-check`: exits `0` (`lint 98/1422`, `format 8/94`)
- `make quality`: exits `0` with existing advisory Ruff/deptry backlog
- `git diff --check`: exits `0` with only existing CRLF warnings
