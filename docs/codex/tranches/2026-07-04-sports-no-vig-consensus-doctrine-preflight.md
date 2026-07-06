# Sports No-Vig Consensus Doctrine Preflight

Date: 2026-07-04

## Why

Claude/Fable's advice changed the sports lane policy: for sports, the sharp timestamp-matched no-vig consensus line is the primary model. Internal Elo/projection/simulation systems are not the default sports probability source. They may remain metadata or separately falsified hypotheses, but they cannot directly create tradable sports probabilities.

The tractable sports edge families are now explicitly:

- Kalshi price vs timestamp-matched multi-book no-vig consensus
- Stale Kalshi quote or slow update after consensus line moves
- Settlement-window probability decay
- Resolved-archive longshot/favorite bucket bias

All still require OOS/FDR, all-in Kalshi cost replay, capacity/depth, correlation-cluster control, and decay survival before paper sizing.

## What Changed

- Added `predmarket/sports_consensus.py`, a strict research-only validator for sports no-vig consensus rows.
- Added `scripts/kalshi_sports_consensus_preflight.py` and `make kalshi-sports-consensus-preflight`.
- The preflight requires exact Kalshi ticker mapping, two-sided no-vig odds, at least two distinct books, and timestamp match to the Kalshi observation.
- The preflight rejects projection/model/Elo/simulation rows as the primary sports probability source.
- Wired the consensus artifact into `scripts/kalshi_sports_evidence_cycle_report.py` as a fifth sports surface: `sports_no_vig_consensus`.
- Wired `make kalshi-sports-evidence-cycle` to run the consensus preflight before the final report.
- Updated `docs/codex/manual-drops/predmarket-type2-sportsbook-reference-contract.md` to mark single-book Type 2 as legacy/manual review rather than the sports model.
- Hardened `scripts/kalshi_contract_ev_ledger.py` so old sports strength-model CCD rows are blocked audit rows under this doctrine even if their capacity/correlation/decay fields pass.

## Latest Real State

`make kalshi-sports-consensus-preflight` exits 0 and writes:

- Status: `sports_consensus_preflight_blocked_missing_reference`
- Valid consensus candidates: 0
- Blocker: missing `/home/mrwatson/manual_drops/predmarket/sports-no-vig-consensus.json`

`make kalshi-sports-evidence-cycle` exits 0 and writes:

- Sports evidence status: `sports_evidence_cycle_ready_with_label_progress`
- Safe artifacts: 21/21
- Sports surfaces: 5
- Total observations: 5,567
- Total labels: 1,210
- Total proxy labels: 164
- Consensus valid candidates: 0
- EV ledger rows: 383
- EV ledger usable rows: 23
- Paper candidates: 443
- Paper usable rows: 11
- Total paper stake: 1,815.60097
- Paper portfolio cap status: `paper_portfolio_caps_observed`
- Live preflight: `kalshi_live_blocked`, 0 eligible

## Guardrails Preserved

- No live credentials used.
- No account/order path enabled.
- No manual approval queue added.
- No thresholds lowered.
- No single sportsbook shortcut promoted as a model.
- No projection-model probability promoted as a sports consensus probability.
- No old sports strength-model CCD row can become usable EV without a valid non-projection sports probability-source family.
- Live remains blocked despite paper-sized rows.

## Verification

- Focused ledger/consensus/cycle tests: 11 passed
- `make test-unit`: 820 passed, 14 deselected
- `make test-integration`: 14 passed
- `make quality`: exits 0 with expected advisory Ruff/deptry backlog
- `make lint-baseline-check`: `lint 118/1422`, `format 93/94`
- `make modularize`: 2 contracts kept, 0 broken
- `make kalshi-sports-consensus-preflight`: exits 0
- `make kalshi-sports-evidence-cycle`: exits 0

## Next Machine Action

Build or ingest the first timestamp-matched multi-book no-vig consensus feed at:

`/home/mrwatson/manual_drops/predmarket/sports-no-vig-consensus.json`

Then rerun:

```bash
make kalshi-sports-consensus-preflight
make kalshi-sports-evidence-cycle
```

If consensus rows pass, they still must enter the normal OOS/FDR, cost, capacity, cluster, and decay gates. Keep live blocked until paper P&L, calibration, retirement, and live-risk preflight justify an explicit live tranche.
