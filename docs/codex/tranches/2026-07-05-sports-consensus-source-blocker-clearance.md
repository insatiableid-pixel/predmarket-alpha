# Sports Consensus Source Blocker Clearance

Date: 2026-07-05

## North-Star Alignment

This tranche keeps the sports system pointed at timestamp-matched sharp no-vig
consensus as the sports probability source. It does not introduce projections,
Elo, discretionary picks, EV promotion, paper stake, live eligibility, account
paths, or order paths.

## What Changed

- Added a current ATP capture path to the strict consensus adapter so Wimbledon
  match-winner markets can be rebuilt from current The Odds API tennis H2H rows
  plus current Kalshi `KXATPMATCH` rows instead of stale donor JSONL snapshots.
- Refreshed public Kalshi game snapshots for `KXNFLGAME` and `KXWCGAME` before
  rebuilding NFL and World Cup consensus adapters, removing stale Kalshi-side
  timestamp skew from the strict consensus preflight.
- Split ETA accounting between true stale/source blockers and waiting-evidence
  blockers. ATP forward-OOS and NBA offseason/no-current-rows no longer make the
  cycle point at stale consensus refresh when active current consensus rows are
  actually waiting for exact settlement labels.
- Probed the existing legal odds feed for soccer Asian-sharp providers
  `sbobet`, `singbet`, and `ibc`. The feed returned current World Cup events but
  zero rows from those providers, so the soccer maturity gap remains an external
  provider-coverage gap, not a repo wiring blocker.

## Latest State

- Strict consensus preflight: `91` candidates, `85` valid, `6` rejected.
- Timestamp blockers: `0`.
- Rejected rows: `6` MLB single-book rows, all blocked by
  `insufficient_distinct_books`.
- Current valid consensus rows by surface: MLB, ATP, NFL, and World Cup soccer
  are admitted into observation; NBA remains offseason/no-current-rows.
- Consensus observation archive: `642` observations and `72` exact Kalshi
  settlement labels.
- 21:30Z public settlement probe added `24` new labels.
- Consensus falsification remains correctly blocked:
  `18/30` independent labels and `6/10` OOS labels, with `0` tested hypotheses
  and `0` FDR survivors.
- Event-velocity ETA now reports `0` stale/external source blockers,
  `4` actionable calendar label blockers, `2` waiting-evidence blockers, and no
  due surface until the next settlement clock.
- Live remains blocked; this tranche did not alter execution arming.

## Verification

- Focused tests: `17 passed`.
- `make test-unit`: `1330 passed / 15 deselected`.
- `make test-integration`: `14 passed`.
- `make lint-baseline-check`: `OK lint 98/1422 format 7/94`.
- Touched-file Ruff: clean.
- `git diff --check`: clean except existing CRLF warnings.

## Remaining Honest Blockers

- Consensus FDR needs exact Kalshi labels to reach `30` independent and `10`
  OOS before testing any rule.
- Soccer has strict rows from Pinnacle/exchange anchors, but no observed
  legal Asian-sharp feed rows; do not fake this with soft books.
- NBA has no current strict rows in the active sports universe.
- The remaining MLB rejects are single-book rows; do not lower the two-book
  consensus gate.
