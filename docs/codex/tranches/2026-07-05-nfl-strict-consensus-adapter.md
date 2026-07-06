# NFL Strict Consensus Adapter

## Why

Claude's sports advice says the sharp timestamp-matched no-vig consensus line is the sports model. Before this tranche, NFL had raw sharp-provider availability and local Kalshi game rows, but those rows did not enter the strict sports consensus manifest or downstream OOS/FDR chain.

## What Changed

- Added `predmarket/sports_consensus_nfl_adapter.py`.
- Added `scripts/kalshi_sports_consensus_nfl_adapter.py`.
- Added `tests/test_kalshi_sports_consensus_nfl_adapter.py`.
- Added `make kalshi-sports-consensus-nfl-adapter`.
- Wired the NFL adapter into `make kalshi-sports-consensus-refresh` before strict preflight.
- Refreshed current public Kalshi `KXNFLGAME` data through the existing research-only manual-drop capture path.
- Captured current NFL sharp/exchange h2h odds through The Odds API into `/home/mrwatson/manual_drops/odds_api/`.

## Landing State

- NFL adapter: `sports_consensus_nfl_adapter_ready_with_warnings`
- NFL matched games: `16`
- NFL strict reference rows: `64`
- NFL unique Kalshi tickers: `32`
- NFL distinct books: `2` (`pinnacle`, `smarkets`)
- Combined strict reference rows: `198`
- Strict reference sports: MLB, tennis, NFL
- Provider audit: `sports_consensus_provider_audit_ready_with_per_sport_gaps`
- Covered target sports: `3/5` (`mlb`, `tennis`, `nfl`)
- Remaining target gaps: soccer, NBA

## Gate State

- Consensus preflight: `sports_consensus_preflight_ready_with_rejected_rows`
- Valid current candidates: `32`, all NFL
- Rejected stale candidates: `46` MLB/ATP rows blocked by `timestamp_skew_exceeds_policy`
- Observation loop: `sports_consensus_observation_loop_label_rows_ready`
- New observations: `32`
- Total consensus observations: `226`
- Distinct observed contracts: `92`
- Falsification: `sports_consensus_falsification_blocked_insufficient_labels`
- Joined labels: `16`
- Independent labels: `8`
- OOS labels: `3`
- Tested hypotheses: `0`
- FDR survivors: `0`

## Claude Advice Completion Audit

- Always-on collector: partial. Collector target exists and archives sports consensus plus crypto, but not all sports/crypto order books and trades at production cadence.
- Sports sharp consensus as model: partial and improving. MLB, ATP/tennis, and NFL are strict-manifest surfaces; soccer and NBA remain missing.
- Stale quote, settlement-window decay, longshot/favorite bias: partial. Families/gates exist, but they are still label-starved.
- Continuous paper ledger: partial. Paper decision machinery exists, but consensus has no FDR survivor and therefore no paper stake.
- Pre-registered promotion policy: partial. Gates and live preflight exist, but no consensus signal has cleared the auto-promotion boundary.
- Breadth/correlation control: partial. Cluster/cap controls exist, but breadth is not yet real while sport coverage and labels are thin.
- Hygiene: partial. Guardrails are much better, but the worktree remains very dirty and generated artifacts are numerous.

Honest estimate after this tranche: sports sharp consensus coverage is about `60%` by target sport count (`3/5`), but less than half of a complete production-grade sharp-consensus operation because labels, cadence, soccer/NBA, and paper/live graduation are not done. Claude's whole advice set is roughly `60%` implemented.

## Verification

- `python -m pytest -s tests/test_kalshi_sports_consensus_nfl_adapter.py tests/test_kalshi_sports_consensus_atp_adapter.py tests/test_kalshi_sports_consensus_provider_policy.py -q` -> `18 passed`
- Touched-file Ruff check and format -> clean
- `make kalshi-manual-drop-capture` with `KXNFLGAME` -> exit `0`
- `make kalshi-sports-consensus-nfl-adapter` with current NFL capture -> exit `0`
- `make kalshi-sports-consensus-preflight` -> exit `0`
- `make kalshi-sports-consensus-provider-audit` -> exit `0`
- `make kalshi-sports-consensus-observation-loop` -> exit `0`
- `make kalshi-sports-consensus-falsification` -> exit `0`
- `make kalshi-sports-evidence-cycle-report` -> exit `0`

## Next

1. Source legal soccer sharp/Asian reference and exact Kalshi World Cup mappings.
2. Add NBA strict consensus when Kalshi NBA game markets and sharp h2h provider rows are simultaneously available.
3. Add cadence policy so far-future NFL does not burn provider credits every collector tick.
4. Keep accumulating exact settlement labels until the consensus family reaches at least `30` independent labels and `10` OOS labels.
