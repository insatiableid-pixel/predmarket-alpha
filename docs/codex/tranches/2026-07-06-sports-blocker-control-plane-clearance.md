# Sports Blocker Control-Plane Clearance

Date: 2026-07-06

## Objective

Clear software/reporting blockers in the Kalshi sports evidence factory while preserving the hard statistical gates:

- paper settlement next-close state must be visible in every wrapper report;
- sports consensus label deficits must point to current pending observations that can fill the deficient pre-registered cells after exact Kalshi settlement.

## Landing

- `scripts/kalshi_paper_settlement_reconcile.py` now computes `next_unresolved_close_time_utc` from unresolved usable paper rows.
- `scripts/kalshi_sports_paper_burn_in_cycle.py` now prefers the settlement reconciliation next-close field and falls back to candidate close times only if needed.
- `scripts/kalshi_sports_evidence_cycle_report.py` now surfaces paper next close and consensus accumulation-opportunity counters.
- `predmarket/sports_consensus_falsification.py` now emits `hypothesis_accumulation_opportunities`: current pending exact Kalshi consensus observations mapped to deficient pre-registered rule/threshold or price-bucket cells.
- `tests/test_kalshi_paper_settlement_reconcile.py`, `tests/test_kalshi_sports_paper_burn_in_cycle.py`, `tests/test_kalshi_sports_consensus_falsification.py`, and `tests/test_kalshi_sports_evidence_cycle_report.py` pin the new contracts.

## Latest State

- Paper settlement: `paper_settlement_reconciliation_waiting_for_close`.
- Paper usable rows: `22`.
- Unresolved paper usable rows: `22`.
- Due unresolved paper usable rows: `0`.
- Total paper stake: `$1792.624803`.
- Next unresolved paper close: `2026-07-06T02:20:00Z`.
- Consensus falsification: `sports_consensus_falsification_blocked_no_testable_hypotheses`.
- Joined consensus labels: `185`.
- Independent consensus labels: `31`.
- OOS consensus labels: `10`.
- Tested consensus hypotheses: `0`.
- FDR survivors: `0`.
- Nearest deficient consensus model: `sports_consensus_price_bucket_bias_bucket_0.50_0.70`.
- Nearest OOS deficit: `5`.
- Current accumulation opportunities: `239`.
- Distinct opportunity contracts: `101`.
- Nearest-model opportunities: `32`.
- Live eligible rows: `0`.

## Guardrails

- No threshold lowering.
- No sportsbook-derived settlement labels.
- No inferred outcomes.
- No EV, paper, or live promotion from the consensus opportunity rows.
- Live execution remains blocked/unarmed.

## Verification

- Focused tests: `25 passed`.
- `make test-unit`: `1357 passed / 15 deselected`.
- `make test-integration`: `14 passed`.
- `make lint-baseline-check`: exit `0` (`lint 98/1422`, `format 12/94`).
- `make quality`: exit `0` with existing advisory Ruff/deptry backlog.
- Touched-file Ruff: clean.
- Py-compile: clean.
- Selected `git diff --check`: clean.

## Next Clock

Run the sports settlement/paper burn-in cycle after `2026-07-06T02:20:00Z`. The expected honest result is either new exact Kalshi labels/paper settlements or a refreshed wait state if the public market payloads still report the contracts as open/unsettled.
