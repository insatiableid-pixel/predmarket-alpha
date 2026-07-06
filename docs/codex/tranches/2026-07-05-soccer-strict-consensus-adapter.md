# 2026-07-05 Soccer Strict Consensus Adapter

## North Star

Extract and exploit mispricings in Kalshi sports contracts before the crowd corrects them, with no discretionary model opinion. For sports, the model surface is timestamp-matched sharp no-vig consensus, then OOS/FDR falsification, then cost/capacity/correlation/decay gates.

## Cleanup And Fixes First

- Fixed provider-audit sport normalization so `soccer_fifa_world_cup` rows count as canonical `soccer`.
- Split provider coverage into two explicit measures:
  - strict consensus row coverage: target sports that have rows in the strict manifest.
  - mature provider-policy coverage: target sports that satisfy the current provider maturity policy.
- Propagated both measures into the sports evidence cycle report.

## New Work

- Added `predmarket/sports_consensus_soccer_adapter.py`.
- Added `scripts/kalshi_sports_consensus_soccer_adapter.py`.
- Added `tests/test_kalshi_sports_consensus_soccer_adapter.py`.
- Added `make kalshi-sports-consensus-soccer-adapter`.
- Wired the adapter into `make kalshi-sports-consensus-refresh` before strict preflight.

The adapter handles World Cup soccer's 3-way H2H shape correctly:

- normalize home / away / draw implied probabilities within each sharp book.
- map each exact `KXWCGAME` binary outcome ticker to the selected 3-way outcome probability.
- set the opposite Kalshi side to `1 - selected_probability`, so the existing binary preflight can validate the row without inventing a soccer projection model.

## Real Run

- Kalshi public `KXWCGAME` capture: `21` markets, `7` games, `3` outcomes per game.
- Soccer adapter: `sports_consensus_soccer_adapter_ready`.
- Soccer strict reference rows: `84`.
- Exact soccer Kalshi tickers: `21`.
- Matched games: `7`.
- Soccer providers: `pinnacle`, `betfair_exchange`, `matchbook`, `smarkets`.
- Skipped rows: `0`.
- Strict preflight: `sports_consensus_preflight_ready_with_rejected_rows`.
- Valid strict candidates: `53` total (`32` NFL, `21` World Cup).
- Rejected stale candidates: `46` ATP/MLB rows rejected by timestamp skew.
- Consensus observations: `247` total, `21` new World Cup rows.
- Consensus labels: `16`.
- Independent labels: `8`.
- OOS labels: `3`.
- Tested hypotheses: `0`.
- FDR survivors: `0`.
- Paper stake: `$0`.
- Live eligible rows: `0`.

## Honest Coverage

- Strict sports consensus wrapping: `4/5` target sports = `80%`.
  - Wrapped: `mlb`, `tennis`, `soccer`, `nfl`.
  - Missing: `nba`.
- Mature provider-policy coverage: `3/5` target sports = `60%`.
  - Mature: `mlb`, `tennis`, `nfl`.
  - Gaps: `soccer` lacks an Asian sharp source (`SBOBet`/`Singbet`/`IBC`); `nba` lacks a strict feed.
- Full Claude advice implementation estimate: roughly `70%`.
  - Remaining gaps are label velocity, OOS/FDR survival, paper promotion, NBA, soccer Asian sharp enrichment, cadence hardening, and live-autonomous hygiene.

## Verification

- `pytest -s tests/test_kalshi_sports_consensus_soccer_adapter.py tests/test_kalshi_sports_consensus_nfl_adapter.py -q` -> `8 passed`.
- `pytest -s tests/test_kalshi_sports_consensus_provider_policy.py tests/test_kalshi_sports_consensus_soccer_adapter.py -q` -> `15 passed`.
- `pytest -s tests/test_kalshi_sports_evidence_cycle_report.py tests/test_kalshi_sports_consensus_provider_policy.py -q` -> `14 passed`.
- Touched-file Ruff check and format checks pass.
- `make kalshi-sports-consensus-soccer-adapter` exits `0`.
- `make kalshi-sports-consensus-preflight` exits `0`.
- `make kalshi-sports-consensus-observation-loop` exits `0`.
- `make kalshi-sports-consensus-falsification` exits `0`.
- `make kalshi-sports-consensus-provider-audit` exits `0`.
- `make kalshi-sports-evidence-cycle-report` exits `0`.
- `make test-unit` -> `1290 passed / 15 deselected`.
- `make test-integration` -> `14 passed`.
- `make lint-baseline-check` -> `OK lint 100/1422 format 8/94`.
- `make quality` exits `0` with existing advisory Ruff/deptry backlog.
- `git diff --check` reports only existing line-ending warnings.

## Next Machine Action

Do not promote sports consensus rows to EV/paper/live merely because they exist. The highest-value next actions are:

1. add NBA strict consensus only if current Kalshi NBA markets are real and timestamp-matchable;
2. source legal soccer Asian sharp data or explicitly revise the maturity policy if unavailable;
3. keep the always-on consensus collector running until the lane reaches at least `30` independent labels and `10` OOS labels;
4. only after OOS/FDR survival, wire surviving consensus hypotheses to fee-aware EV replay and paper sizing.
