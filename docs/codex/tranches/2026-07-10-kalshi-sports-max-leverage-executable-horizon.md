# Tranche: Kalshi Sports max-leverage executable-horizon program

Date: 2026-07-10
Branch: codex/kalshi-sports-max-leverage-20260710T043635Z
Base: origin/codex/fable-sports-evidence-2118 @ 87a62d6 (origin/main lacked prerequisite)

## Actions

- Created clean collision-safe worktree; left dirty canonical checkout untouched.
- Reconciled frozen starting evidence checksums (4/4).
- Phase 0 truth/leakage audit with synthetic leakage suite.
- Phase 1 fixed-horizon executable labels (ask entry / bid exit + taker fees + censoring).
- Phase 2–3 three distinct families (microstructure, cross-contract lead-lag, thin-book fade)
  with event-grouped walk-forward, complete-family FDR, hard gates.
- All three families **falsified** (0 FDR survivors; all testable mean nets negative).
- Negative-result registry extended; frontier ranked; final audit written.
- No paper stake, sizing, accounts, orders, or live execution.

## Evidence

- `make kalshi-sports-executable-horizon-research` → `executable_horizon_research_family_falsified`
- Executable labels: 3,584; censored: 29,119; obs: 11,061
- Latest: `docs/codex/macro/latest-kalshi-sports-executable-horizon-research.json`
- Final audit: `docs/codex/macro/latest-kalshi-sports-max-leverage-final-audit.md`

## Verification

- `pytest tests/test_kalshi_sports_executable_horizon.py` → 6 passed
- Ruff clean on touched files

## Next highest-leverage move

Dense read-only MLB tick/orderbook capture to unlock true 1–5m labels — a new
data surface, not a re-tune of retired specs. ATP/settlement velocity remain
calendar monitors; Asian-sharp soccer remains deferred.
