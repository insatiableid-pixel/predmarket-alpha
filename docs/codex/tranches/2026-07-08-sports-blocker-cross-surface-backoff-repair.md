# Sports Blocker Cross-Surface Backoff Repair

Date: 2026-07-08

## Summary

Fixed a sports blocker-clearance scheduler defect where a future `next_probe_surface` from an unrelated sport could suppress a currently due `next_due_surface`.

The live failure mode was `sports_consensus_mlb` due at `2026-07-08T20:33:50Z`, while the blocker cycle waited for the unrelated `sports_consensus_nfl` clock at `2026-07-08T22:45:00Z`.

## Change

- `event_velocity_task()` now uses a future probe as fallback retry only when the due surface and future probe surface have the same `surface_id`.
- Previous `backoff_until_utc` values are carried forward only when they are still inside the normal cooldown window or valid under the same-surface fallback policy.
- Added regression tests for unrelated future probes, same-surface future probes, and stale cross-surface backoff carryover.

## Real Run

- Non-due blocker cycle exposed `sports_consensus_mlb` as due instead of waiting for NFL.
- Due blocker-clearance run exited `0`.
- ETA, Fable audit, and non-due blocker refresh exited `0`.

## Latest Counts

- Consensus falsification: `964` joined labels, `70` independent labels, `21` OOS labels, `1` tested hypothesis, `0` FDR survivors.
- Consensus observation loop: `1018` label rows, `36` due distinct contracts.
- Fable audit: `15/15` implementation, open evidence ids `CLAUDE-005`, `CLAUDE-008`, `CLAUDE-012`, `CLAUDE-014`, `CLAUDE-015`.
- ATP: `962` settled labels, `8/10` forward-OOS.
- Paper/live: `0` usable paper rows, `$0` paper stake, `0` live eligible rows, `$0` live stake.
- Next blocker clock: `2026-07-08T21:18:37Z`.

## Verification

- `TMPDIR=$PWD/.tmp TMP=$PWD/.tmp TEMP=$PWD/.tmp python3 -m pytest tests/test_kalshi_sports_blocker_clearance_cycle.py -q` -> `9 passed`
- `python3 -m ruff check scripts/kalshi_sports_blocker_clearance_cycle.py tests/test_kalshi_sports_blocker_clearance_cycle.py` -> pass
- `python3 -m py_compile scripts/kalshi_sports_blocker_clearance_cycle.py tests/test_kalshi_sports_blocker_clearance_cycle.py` -> pass
- `make kalshi-sports-blocker-clearance-cycle KALSHI_SPORTS_BLOCKER_CLEARANCE_RUN_DUE=1 VENV=/tmp/predmarket-alpha-fable-venv` -> exit `0`
- `make kalshi-sports-event-velocity-eta VENV=/tmp/predmarket-alpha-fable-venv` -> exit `0`
- `make kalshi-claude-advice-audit VENV=/tmp/predmarket-alpha-fable-venv` -> exit `0`
- `make kalshi-sports-blocker-clearance-cycle VENV=/tmp/predmarket-alpha-fable-venv` -> exit `0`

## Guardrails

No thresholds changed. No labels were inferred. No sportsbook results were used as settlement labels. No EV, paper, live, account, order, or execution promotion occurred.
