# 2026-07-06 Sports Event-Velocity Due-Backlog Precision

## Cleanup And Fixes From The Last Tranche

The sports sharp-consensus evidence lane had a control-plane blocker, not a model blocker.

`latest-kalshi-sports-consensus-observation-loop.json` already knew there were due observed contracts ready for public Kalshi settlement probing, but `latest-kalshi-sports-event-velocity-eta.json` could hide that backlog when `next_expected_expiration_utc` was still in the future. After the first repair, the ETA artifact exposed the due backlog but over-applied the global due count to every sport row when sport-level counts were unavailable.

Fixes landed:

- `scripts/kalshi_sports_consensus_observation_loop.py` now emits due observation rows and due distinct contracts by sport, plus not-yet-due distinct contracts by sport.
- The observation loop now separates already-labeled due contracts from unresolved due contracts, so historical labels do not keep triggering phantom probe work.
- The observation loop now defers to current public Kalshi market state when available: an archived expected-expiration timestamp does not make a contract due if the current Kalshi market payload still reports the market as active with a future close/expiration time.
- `scripts/kalshi_sports_event_velocity_eta.py` now preserves due backlog when `next_public_label_probe_utc` is due, even if the next expected expiration is in the future.
- Sport-specific ETA rows now use sport-specific due counts only. If an older observation artifact lacks per-sport due counts, the global rollup remains visible but individual sport rows do not inherit fake due counts.
- `next_due_surface` now prefers concrete non-rollup surfaces and ranks by largest due count, so the next action points at the sport with the most immediate settlement-label work.
- `scripts/kalshi_sports_evidence_cycle_report.py` now surfaces event-velocity ETA status counts and bottleneck type counts directly in the sports evidence-cycle summary.

## Current State

Latest sports consensus observation loop:

- Status: `sports_consensus_observation_loop_label_rows_ready`
- Public probe fetched observed tickers: `47`
- Public probe finalized/settlement-ready rows: `31`
- Public probe errors: `0`
- New labels in latest refresh: `0` because the `31` finalized rows were already in the label archive
- Unresolved due distinct contracts: `0`
- Already-labeled due distinct contracts: `31`
- Already-labeled due distinct contracts by sport: `{"baseball_mlb": 28, "soccer_world_cup": 3}`
- Not-yet-due distinct contracts by sport: `{"baseball_mlb": 32, "football_nfl": 32, "soccer_world_cup": 18, "tennis_atp": 20}`
- Existing consensus labels: `194`
- Next public label probe: `2026-07-06T02:20:00Z`
- Next expected expiration: `2026-07-06T02:20:00Z`

Latest sports event-velocity ETA:

- Status: `sports_event_velocity_eta_ready_with_label_deficits`
- Next due surface: `null`
- Next action: `kalshi_sports_wait_for_next_settlement_clock`
- Total label deficit: `119`
- Total OOS deficit: `49`
- Actionable calendar label deficit: `89`
- Actionable calendar OOS deficit: `31`
- ETA status counts: `{"blocked_atp_forward_oos": 1, "blocked_no_current_nba_consensus_rows": 1, "label_threshold_met": 3, "label_threshold_met_downstream_gates_active": 1, "label_threshold_met_no_fdr_survivor": 1, "waiting_for_next_probe_or_settlement": 4}`
- Bottleneck type counts: `{"calendar_or_offseason_no_current_markets": 1, "calendar_settlement_labels": 7, "compute_or_downstream_gates": 2, "external_forward_oos": 1}`

Latest sports evidence-cycle summary:

- Sports event-velocity next due surface: `null`
- Consensus falsification remains `sports_consensus_falsification_blocked_no_testable_hypotheses`
- Joined consensus labels: `185`
- Nearest hypothesis OOS deficit: `5`
- FDR survivors: `0`
- Paper usable rows: `17`
- Paper stake: `$2119.664117`
- Live eligible rows: `0`

## Guardrails

- No label threshold was lowered.
- No non-Kalshi settlement label was used.
- No post-hoc hypothesis was created.
- No EV, paper, live, account, or order promotion was added.
- This tranche only improves evidence-clock precision and report observability.

## Verification

- `PYTHONPATH=. .venv/bin/python -m pytest -s -q tests/test_kalshi_sports_consensus_observation_loop.py tests/test_kalshi_sports_event_velocity_eta.py tests/test_kalshi_sports_evidence_cycle_report.py` -> `26 passed`
- `.venv/bin/ruff check scripts/kalshi_sports_consensus_observation_loop.py scripts/kalshi_sports_event_velocity_eta.py scripts/kalshi_sports_evidence_cycle_report.py tests/test_kalshi_sports_consensus_observation_loop.py tests/test_kalshi_sports_event_velocity_eta.py tests/test_kalshi_sports_evidence_cycle_report.py` -> pass
- `python -m py_compile scripts/kalshi_sports_consensus_observation_loop.py scripts/kalshi_sports_event_velocity_eta.py scripts/kalshi_sports_evidence_cycle_report.py` -> pass
- `make kalshi-sports-consensus-observation-loop` -> `0`
- `make kalshi-sports-event-velocity-eta` -> `0`
- `make kalshi-sports-evidence-cycle-report` -> `0`
- `make test-unit` -> `1354 passed / 15 deselected`
- `make test-integration` -> `14 passed`
- `make lint-baseline-check` -> `0` (`lint 98/1422`, `format 12/94`)
- `make quality` -> `0` with existing advisory Ruff/deptry backlog
- Selected `git diff --check` -> clean

## Next Move

Wait for the next public settlement clock at `2026-07-06T02:20:00Z`, then rerun `make kalshi-sports-consensus-observation-loop && make kalshi-sports-event-velocity-eta && make kalshi-sports-evidence-cycle-report`. Stop before using non-Kalshi labels or unsettled outcomes.
