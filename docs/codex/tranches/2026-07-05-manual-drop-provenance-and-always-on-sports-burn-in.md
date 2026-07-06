# Manual-Drop Provenance And Always-On Sports Burn-In

Date: 2026-07-05

## Summary

Cleaned up landing residue from the sports consensus tranche and removed another automation blocker in Claude's advice: passive-liquidity paper-fill accumulation now runs through the default always-on collector path instead of requiring a human to remember the broader `sports` target.

## Changes

- Fixed `predmarket/kalshi_manual_drop_capture.py` so non-MLB captures no longer write timestamped raw files with the legacy `kalshi_mlb_game_series_*` prefix.
  - `KXNFLGAME` now writes `kalshi_nfl_game_series_<stamp>.json`.
  - `KXWCGAME` now writes `kalshi_world_cup_game_series_<stamp>.json`.
  - Other custom series get a deterministic generic series prefix.
- Changed the generic public-fetch snapshot status from MLB-specific to `kalshi_manual_drop_public_fetch_ok` / `kalshi_manual_drop_public_fetch_empty`.
- Changed always-on collector defaults from `sports_consensus,crypto` to `sports,crypto`.
  - The `sports` target runs `kalshi-sports-paper-burn-in-cycle` with settlement fetch enabled.
  - That path includes sports consensus refresh, exact labels, nondirectional microstructure, passive paper fills, paper settlement, decay, and live preflight.
  - The narrower `sports_consensus` target remains available for focused consensus-only runs.
- Added a latest-pointer safety guard to `scripts/kalshi_always_on_collector.py`: temp or dry-run output directories no longer overwrite root macro latest pointers.

## Real Refreshed State

One real `make kalshi-always-on-collector-once` run from the canonical macro output produced:

- Always-on status: `kalshi_always_on_collector_ready`
- Targets: `sports` and `crypto`
- Failed targets: `0`
- Safe artifacts: `2/2`
- Cadence: `60` seconds because crypto had due settlement rows
- NFL snapshot path: `/home/mrwatson/manual_drops/kalshi/kalshi_nfl_game_series_20260705T233914Z.json`
- World Cup snapshot path: `/home/mrwatson/manual_drops/kalshi/kalshi_world_cup_game_series_20260705T233915Z.json`

Sports state after the same collector run:

- Consensus preflight: `66` candidates, `66` valid, `0` timestamp blockers
- Consensus falsification: still `29/30` independent labels and `9/10` OOS labels
- Consensus tested hypotheses: `0`
- Consensus FDR survivors: `0`
- Passive paper intents: `3042`
- Passive valid paper-fill labels: `1378`
- Passive paper fills: `149` valid labels / `154` raw filled count
- Passive tested hypotheses: `3`
- Passive FDR survivors: `0`
- Best passive candidate net EV: `-0.0332520548`
- Paper usable rows: `22`
- Paper stake: `$3465.373827`
- Live preflight: `kalshi_live_blocked`, `0` eligible

Remaining blockers are now honest:

- Sharp sports consensus is one independent label and one OOS label short of OOS/FDR.
- Passive liquidity has enough paper labels to test, but no FDR survivor yet.
- Soccer still lacks an observed Asian-sharp provider reference.
- NBA has no current strict consensus rows.

## Verification

- Manual drop focused tests: passed
- Always-on collector focused tests: passed
- Sports consensus focused tests: passed
- Unit suite: `1333 passed / 15 deselected`
- Integration suite: `14 passed`
- `make lint-baseline-check`: exits `0` (`lint 98/1422`, `format 7/94`)
- Touched-file Ruff checks: clean
- Real `make kalshi-sports-paper-burn-in-cycle KALSHI_SPORTS_PAPER_BURN_IN_FETCH=1`: exits `0`
- Real `make kalshi-always-on-collector-once`: exits `0`

## Guardrails

- No live execution was enabled.
- No account/order path was touched.
- No paper or live gate threshold was lowered.
- No sportsbook line was treated as a settlement label.
- Temp/dry-run collector output can no longer overwrite canonical latest pointers.
