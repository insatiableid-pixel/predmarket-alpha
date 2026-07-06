# Sports Consensus Autonomous Refresh Burn-In

Date: 2026-07-05

## Summary

Cleared the remaining software/source blockers in the sharp no-vig sports consensus lane and proved the burn-in path can refresh current Kalshi sports snapshots, capture current consensus references, probe exact settlements, rerun OOS/FDR, rebuild paper decisions, and keep live blocked without manual environment flags.

## Changes

- Changed `KALSHI_SPORTS_CONSENSUS_PROBE_OBSERVED` default from `0` to `1`, so normal evidence-cycle runs probe already-observed contracts for public Kalshi settlements.
- Added `kalshi-sports-consensus-public-kalshi-refresh`, refreshing current public Kalshi snapshots for:
  - `KXNFLGAME` into `/home/mrwatson/manual_drops/kalshi/kalshi_nfl_game_series_latest.json`
  - `KXWCGAME` into `/home/mrwatson/manual_drops/kalshi/kalshi_world_cup_game_series_latest.json`
- Updated `kalshi-sports-consensus-refresh` to run the full autonomous intake sequence:
  - universe scan
  - public NFL/World Cup Kalshi refresh
  - MLB sharp consensus capture
  - ATP, NFL, soccer, and NBA strict adapters with capture enabled
  - consensus preflight
- Updated `kalshi-sports-evidence-cycle` to call the full consensus refresh instead of a partial ATP-only refresh.
- Added Makefile regression coverage proving the default probe and public Kalshi refresh wiring are present.

## Real Refreshed State

After the 23:00Z burn-in run:

- Consensus preflight: `sports_consensus_preflight_ready`
- Consensus candidates: `76`
- Valid candidates: `76`
- Blocked candidates: `0`
- Timestamp blockers: `0`
- Single-book blockers: `0`
- Consensus labels: `172`
- Falsification joined labels: `163`
- Independent labels: `29/30`
- OOS labels: `9/10`
- Tested hypotheses: `0`
- FDR survivors: `0`
- Sports consensus source blockers: `0`
- Provider audit strict sports: `mlb`, `tennis`, `soccer`, `nfl`
- Provider audit remaining sport gaps: `2` (`nba` offseason/no current rows; one non-current target gap)
- Paper usable rows: `18`
- Paper stake: `$2029.188553`
- Paper settlement: `paper_settlement_reconciliation_waiting_for_close`
- Next paper close: `2026-07-05T23:30:00Z`
- Live preflight: `kalshi_live_blocked`
- Live eligible rows: `0`

The remaining sharp-consensus blocker is evidence-bound, not software-bound: `sports_consensus_all` is now `29/30` independent labels and `9/10` OOS labels, one label short on both gates. No thresholds were lowered.

## Verification

- Focused tests: `24 passed`
- Unit tests: `1330 passed / 15 deselected`
- Integration tests: `14 passed`
- `make lint-baseline-check`: exits `0` (`lint 98/1422`, `format 7/94`)
- `make quality`: exits `0` with the existing advisory Ruff/deptry backlog
- Python Ruff on touched test file: clean
- `make -n kalshi-sports-consensus-refresh`: confirms the full autonomous refresh chain
- `make kalshi-sports-paper-burn-in-cycle KALSHI_SPORTS_PAPER_BURN_IN_FETCH=1`: exits `0` after both 22:30Z and 23:00Z settlement clocks

## Guardrails

- No live execution was enabled.
- No account/order path was touched.
- No manual trade approval path was added.
- No sportsbook line was treated as a settlement label.
- No donor probability was promoted directly.
- No FDR, label-count, cost, capacity, correlation, or decay threshold was relaxed.
