# Tranche: MLB dense-panel reschedule provenance repair

Date: 2026-07-10
Branch: `codex/kalshi-sports-mlb-reschedule-repair-20260710T065908Z`
Base: `origin/main` @ `6ae9287` (merged PR #74)

## Why this repair was required

An outcome-blind operational audit reproduced a contradiction with the panel
registration.  Coverage and confirmation selected the earliest start ever
observed for an event, while the registered rule says a postponement updates
`game_start_ts`.  A synthetic July 12 -> July 13 reschedule therefore retained
the July 12 slate and T-60 decision book.

## Repair

- Resolve each event's effective start from the latest timestamped public
  market observation, not the earliest historical schedule.
- Retain older schedule revisions as audit evidence, but exclude their books
  from the current schedule's clocks.
- When the per-minute public market listing changes the start of an already
  known event, append one research-only schedule-revision marker without an
  order-book request.  This invalidates an old T-60/T-15 book immediately even
  when the next registered book window has not opened.
- Schedule-revision markers cannot satisfy primary-book counts or enter the
  frozen candidate sample.
- Coverage now reports `schedule_resolution` and
  `schedule_revision_event_count` without exposing outcomes or P&L.

## Outcome-blind confirmation contract v2

- Registered at: `2026-07-10T07:10:59Z`
- Contract hash:
  `cbfa0635b006cf451b02f2cb99a16a03c0e5d7e7326f73113968f8e071ca674c`
- Original panel registration hash preserved:
  `553135d7d1456aeda4a9115784aa423b81931cceed4d2a2f707b5ca8dcbe816e`
- Frozen formula hash preserved:
  `9cd76b9703cd167988fd94d53a9cc82ed9b37a7e3b30f316796f9dbb46cfa56d`
- The contract now pins all five capture-through-decision implementation files,
  including the public book capture, panel ops, schedule resolver, confirmation
  engine, and confirmation CLI.

The replacement occurred with zero candidate events, no attempt/final
sentinel, and `candidate_performance_revealed=false`.

## Verification

- Focused dense-panel/confirmation tests: 21 passed.
- Full repository suite: 1,507 passed.
- `make kalshi-verify`: 53 passed.
- Touched Ruff, format, and compilation: passed.
- Lint baseline: `98/1422`; format baseline: `23/94`.
- Tech debt: `22/22`; file-size, feature-flag, AGENTS, and import-boundary
  gates passed.
- Real raw replay: 30 rows, zero schedule revisions, panel still accumulating.
- Real preflight: registration, formula, contract, all implementation hashes,
  and raw integrity pass; confirmation remains pending and outcome-blind.

## Operations after landing

Move the one-minute collector and gate monitor to this landed repair worktree.
Do not run confirmation unless contract-v2 preflight reports
`confirmation_start_ready=true`; then use the existing single-shot command once.

Research-only.  No settlements were read, no candidate performance was
revealed, and no sizing, accounts, orders, execution, or approval paths were
touched.
