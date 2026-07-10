# Fable Historical Consensus Cached-Probe Gate

Date: 2026-07-10

## Outcome

- Corrected the archive planner to anchor MLB pregame snapshot selection to the
  exact `KXMLBGAME` ticker-encoded start, rather than the resolved archive's
  `occurrence_datetime` field. The latter is systematically offset by three
  hours in the current raw archive.
- The initial cached Cardinals–Reds plan row was correctly rejected: its
  provider payload represented a postponed/doubleheader case, so a team-only
  fallback would have been ambiguous. No mapping relaxation was made.
- Replayed the same cached 00:00Z provider payload against the corrected plan.
  It yielded four exact rows across Texas–Angels and Athletics–Padres, with two
  or more books and 37-second provider/Kalshi skew. This satisfied the required
  cached `>0` exact-row gate without another paid call.
- Ran the resumed MLB-only capture with caching and an explicit 3,000-credit
  cap. It made 255 new historical calls (2,550 credits), plus the one cached
  snapshot: 1,108 exact rows across 554 events, 1,108 contracts, zero capture
  errors, and maximum provider/Kalshi skew of 38 seconds.

## Evidence and Current Gates

- Final provider quota is exactly `2,580` used and `17,420` remaining. The
  tranche consumed exactly `2,550` additional credits, within the cap.
- Historical backfill is
  `kalshi_sports_historical_consensus_backfill_ready_no_research_candidates`:
  1,108 archive rows and valid observations, 1,098 Kalshi settlement labels,
  five tested hypotheses, maximum OOS count 186, and zero FDR survivors.
- Fable audit remains implementation-complete (`15/15`) and now has open
  requirements `CLAUDE-005`, `CLAUDE-008`, and `CLAUDE-015`; no statistical
  survivor was forced.
- Preserved hard boundaries: exact ticker mapping; at least two distinct books;
  provider/Kalshi skew at most 180 seconds; median book-level two-way no-vig
  consensus; public Kalshi-only settlement labels downstream. No threshold was
  changed and no survivor was forced.
- Research-only throughout: no orders, accounts, approvals, execution, paper
  promotion, sizing, or staking paths were touched.

## Verification

- `make kalshi-sports-historical-consensus-archive` — cached gate passed, then
  bounded capture exited 0.
- `make kalshi-sports-historical-consensus-backfill` — exited 0.
- `make kalshi-claude-advice-audit` — exited 0.
- Focused archive, feasibility, backfill, and audit tests — `27 passed`.
- Touched-file Ruff, `py_compile`, and `git diff --check` — passed.

## Remaining Blocker

The historical evidence lane is now replayable and all hard data-quality gates
pass, but the five pre-registered hypotheses have zero FDR survivors. Research
remains blocked from promotion; no paper, sizing, execution, or live path is
authorized.
